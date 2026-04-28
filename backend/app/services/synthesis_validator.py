"""Post-synthesis validate-and-repair loop.

Runs after build_hybrid_bundle returns but BEFORE the orchestrator stores
the bundle. Catches issues like undeclared variables, missing OCI resource
types from the resource mapping, and skill failures (504s).

Architecture (writer/reviewer agent loop):

1. Static checks (no LLM) run first to identify gaps.
2. Gaps are classified as auto_fixable or needs_human.
3. A **Writer Agent** (LLM-based) uses tools to read/write bundle files
   and fix auto_fixable gaps.
4. A **Deterministic Reviewer** re-runs _static_checks + classify_gap to
   decide ACCEPT (no auto_fixable gaps remain) or REJECT (feed remaining
   gaps back to the writer).
5. Loop repeats until: no auto_fixable gaps, no progress, or hard cap hit.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# ── OCI resource type mapping ──────────────────────────────────────────────
# Maps human-readable oci_resource_type labels (from resource_mapper output)
# to Terraform resource type prefixes we expect to find in HCL.
_OCI_TYPE_TO_TF_PREFIX: dict[str, str] = {
    "VCN": "oci_core_vcn",
    "Virtual Cloud Network": "oci_core_vcn",
    "Subnet": "oci_core_subnet",
    "Internet Gateway": "oci_core_internet_gateway",
    "NAT Gateway": "oci_core_nat_gateway",
    "Route Table": "oci_core_route_table",
    "Security List": "oci_core_security_list",
    "Network Security Group": "oci_core_network_security_group",
    "Compute Instance": "oci_core_instance",
    "Instance": "oci_core_instance",
    "Block Volume": "oci_core_volume",
    "Boot Volume": "oci_core_boot_volume",
    "Load Balancer": "oci_load_balancer_load_balancer",
    "Network Load Balancer": "oci_network_load_balancer_network_load_balancer",
    "Object Storage Bucket": "oci_objectstorage_bucket",
    "File Storage": "oci_file_storage_file_system",
    "DB System": "oci_database_db_system",
    "MySQL DB System": "oci_mysql_mysql_db_system",
    "Autonomous Database": "oci_database_autonomous_database",
    "Vault": "oci_kms_vault",
    "Key": "oci_kms_key",
    "Secret": "oci_vault_secret",
    "Function": "oci_functions_function",
    "API Gateway": "oci_apigateway_gateway",
    "Container Instance": "oci_container_instances_container_instance",
    "OKE Cluster": "oci_containerengine_cluster",
    "Monitoring Alarm": "oci_monitoring_alarm",
    "Log Group": "oci_logging_log_group",
    "Notification Topic": "oci_ons_notification_topic",
    "Queue": "oci_queue_queue",
    "Streaming": "oci_streaming_stream",
    "WAF Policy": "oci_waf_web_app_firewall_policy",
    "Certificate": "oci_certificates_management_certificate",
    "Dynamic Group": "oci_identity_dynamic_group",
    "Policy": "oci_identity_policy",
    "Cloud Migration": "oci_cloud_migrations_migration",
    "Migration Plan": "oci_cloud_migrations_migration_plan",
    "Target Asset": "oci_cloud_migrations_target_asset",
}

# Regex to find var.<name> references in HCL
_VAR_REF_RE = re.compile(r'\bvar\.([a-zA-Z_][a-zA-Z0-9_]*)\b')

# Regex to find variable declarations
_VAR_DECL_RE = re.compile(r'variable\s+"([^"]+)"\s*\{')


def _find_var_references(tf_content: str) -> set[str]:
    """Find all var.<name> references in a .tf file."""
    return set(_VAR_REF_RE.findall(tf_content))


def _find_var_declarations(tf_content: str) -> set[str]:
    """Find all variable "name" declarations in a .tf file."""
    return set(_VAR_DECL_RE.findall(tf_content))


def _static_checks(
    bundle: dict[str, str],
    resource_mapping: list[dict],
    skill_logs: list[str],
) -> list[dict]:
    """Run static validation checks (no LLM). Returns list of gap dicts."""
    gaps: list[dict] = []

    # ── 1. Check OCI resource coverage ─────────────────────────────────
    # Collect all terraform content (excluding OCM submodule for this check)
    root_tf_content = ""
    ocm_tf_content = ""
    for path, content in bundle.items():
        if path.startswith("terraform/ocm/") and path.endswith(".tf"):
            ocm_tf_content += "\n" + content
        elif path.startswith("terraform/") and path.endswith(".tf"):
            root_tf_content += "\n" + content

    all_tf_content = root_tf_content + "\n" + ocm_tf_content

    for entry in resource_mapping:
        oci_type = entry.get("oci_resource_type") or ""
        oci_tf = entry.get("oci_terraform") or ""
        if not oci_type and not oci_tf:
            continue
        # Try oci_terraform first (more precise), fall back to label mapping
        tf_prefix = oci_tf or _OCI_TYPE_TO_TF_PREFIX.get(oci_type, "")
        if not tf_prefix:
            continue
        # Check if at least one resource of this type exists in the bundle
        if tf_prefix not in all_tf_content:
            aws_type = entry.get("aws_type", "unknown")
            aws_name = entry.get("aws_name", "")
            gaps.append({
                "check": "missing_oci_resource",
                "severity": "HIGH",
                "description": (
                    f"Resource mapping expects {tf_prefix} for "
                    f"{aws_type} '{aws_name}' but none found in bundle"
                ),
                "file": "",
                "skill": entry.get("skill", ""),
            })

    # ── 2. Check undeclared variables (root module) ────────────────────
    root_var_refs: set[str] = set()
    root_var_decls: set[str] = set()
    for path, content in bundle.items():
        if not path.startswith("terraform/") or path.startswith("terraform/ocm/"):
            continue
        if not path.endswith(".tf"):
            continue
        root_var_refs |= _find_var_references(content)
        root_var_decls |= _find_var_declarations(content)

    undeclared_root = root_var_refs - root_var_decls
    for var_name in sorted(undeclared_root):
        gaps.append({
            "check": "undeclared_variable",
            "severity": "HIGH",
            "description": f"var.{var_name} is referenced in terraform/ but never declared",
            "file": "terraform/variables.tf",
            "skill": "synthesis",
        })

    # ── 3. Check undeclared variables (OCM submodule) ──────────────────
    ocm_var_refs: set[str] = set()
    ocm_var_decls: set[str] = set()
    for path, content in bundle.items():
        if not path.startswith("terraform/ocm/"):
            continue
        if not path.endswith(".tf"):
            continue
        ocm_var_refs |= _find_var_references(content)
        ocm_var_decls |= _find_var_declarations(content)

    undeclared_ocm = ocm_var_refs - ocm_var_decls
    for var_name in sorted(undeclared_ocm):
        gaps.append({
            "check": "undeclared_variable",
            "severity": "HIGH",
            "description": f"var.{var_name} is referenced in terraform/ocm/ but never declared",
            "file": "terraform/ocm/variables.tf",
            "skill": "ocm_handoff_translation",
        })

    # ── 4. Scan skill logs for failures ────────────────────────────────
    failure_patterns = ("504", "failed", "produced no output", "timed out", "timeout")
    for line in skill_logs:
        line_lower = line.lower()
        for pattern in failure_patterns:
            if pattern in line_lower:
                # Extract skill name from log line if possible
                skill = ""
                if "]" in line and "[" in line:
                    try:
                        skill = line.split("[")[1].split("]")[0]
                    except (IndexError, ValueError):
                        pass
                gaps.append({
                    "check": "skill_failure",
                    "severity": "INFO",
                    "description": f"Skill log indicates possible failure: {line.strip()[:200]}",
                    "file": "",
                    "skill": skill,
                })
                break  # only one gap per log line

    return gaps


def classify_gap(gap: dict) -> str:
    """Classify a gap as 'auto_fixable' or 'needs_human'.

    auto_fixable: issues the LLM repair pass can plausibly resolve:
      - undeclared_variable: just needs a variable block added
      - missing_oci_resource where the type has a known TF prefix
      - Simple HCL syntax issues

    needs_human: issues requiring external data or operator judgment:
      - skill_failure: upstream LLM call failed; we can't invent the output
      - missing_oci_resource where the AWS source data is absent
      - Any gap explicitly marked needs_human
    """
    check = gap.get("check", "")
    description = (gap.get("description") or "").lower()

    # Explicit marker
    if gap.get("needs_human"):
        return "needs_human"

    # Skill failures (504, timeout, etc.) can't be auto-fixed
    if check == "skill_failure":
        return "needs_human"

    # Undeclared variables are straightforward to add
    if check == "undeclared_variable":
        return "auto_fixable"

    # Missing OCI resource — auto-fixable if we know the TF type
    if check == "missing_oci_resource":
        # If description mentions "no entry in resources.yaml" or similar → human
        if "no entry" in description or "unmapped" in description or "unknown" in description:
            return "needs_human"
        return "auto_fixable"

    # HCL syntax issues are auto-fixable
    if check in ("hcl_syntax", "undeclared_ref", "cross_file_ref"):
        return "auto_fixable"

    # Default: if severity is INFO, likely informational/needs_human
    if gap.get("severity") == "INFO":
        return "needs_human"

    # Unknown check types default to auto_fixable (LLM should try)
    return "auto_fixable"


def _why_not_auto_fixed(gap: dict) -> str:
    """Generate a human-readable reason why a gap needs manual intervention."""
    check = gap.get("check", "")
    description = (gap.get("description") or "").lower()

    if check == "skill_failure":
        return "Upstream skill failed (timeout/504) — re-run the plan or check LLM gateway health"

    if check == "missing_oci_resource":
        if "no entry" in description or "unmapped" in description:
            return "AWS resource type has no mapping in resources.yaml — add mapping or translate manually"
        return "AWS source data may be incomplete — verify resource inventory"

    return "Requires operator decision or external data not available to the repair loop"


# ── Writer Agent infrastructure ────────────────────────────────────────────
#
# The writer agent reads/writes bundle files via tools. We use a module-level
# reference so the tool closures can access the bundle without needing to
# thread it through the Agent SDK's context (which expects a specific type).
# This is the same pattern used in synthesis_polish.py.

_current_bundle: dict[str, str] = {}
_current_resource_mapping: list[dict] = []


def _build_writer_tools():
    """Build the set of tools the writer agent can use.

    Each tool is a function_tool-decorated function that closes over the
    module-level _current_bundle reference. We import function_tool here
    to avoid importing the heavy agents SDK at module load time.
    """
    from agents import function_tool
    from app.agents.tools import terraform_validate

    @function_tool
    def read_bundle_file(path: str) -> str:
        """Read a file from the migration bundle.

        Args:
            path: Bundle-relative path, e.g. "terraform/main.tf" or
                  "terraform/variables.tf".

        Returns:
            The file content, or an error message if the path does not exist.
        """
        if path in _current_bundle:
            return _current_bundle[path]
        # List available paths to help the agent discover files
        available = sorted(_current_bundle.keys())[:50]
        return json.dumps({
            "error": f"Path {path!r} not found in bundle",
            "available_paths": available,
        })

    @function_tool
    def write_bundle_file(path: str, content: str) -> str:
        """Write or overwrite a file in the migration bundle.

        Use this to fix gaps by adding missing variable declarations,
        adding missing resource blocks, or correcting HCL syntax.

        Args:
            path: Bundle-relative path, e.g. "terraform/variables.tf".
            content: The complete new file content.

        Returns:
            JSON confirmation with the path and content length.
        """
        _current_bundle[path] = content
        return json.dumps({
            "status": "ok",
            "path": path,
            "content_length": len(content),
        })

    @function_tool
    def list_bundle_files() -> str:
        """List all file paths currently in the migration bundle.

        Returns:
            JSON array of bundle file paths.
        """
        return json.dumps(sorted(_current_bundle.keys()))

    @function_tool
    def classify_gap_tool(
        check: str,
        severity: str,
        description: str,
        needs_human: bool = False,
    ) -> str:
        """Classify a validation gap as auto_fixable or needs_human.

        Use this to understand which gaps you should attempt to fix and
        which ones require human intervention.

        Args:
            check: The gap check type (e.g. "undeclared_variable",
                   "missing_oci_resource", "skill_failure").
            severity: "HIGH", "MEDIUM", "LOW", or "INFO".
            description: Human-readable description of the gap.
            needs_human: Explicit flag; if True, always returns "needs_human".

        Returns:
            JSON with the classification result.
        """
        gap = {
            "check": check,
            "severity": severity,
            "description": description,
            "needs_human": needs_human,
        }
        result = classify_gap(gap)
        return json.dumps({"classification": result, "gap": gap})

    @function_tool
    def get_resource_mapping_summary() -> str:
        """Get a summary of the resource mapping for this migration.

        Returns the first 50 entries from the resource mapping, showing
        what OCI resources are expected in the bundle.

        Returns:
            JSON array of mapping entries.
        """
        summary = [
            {
                "aws_type": e.get("aws_type", ""),
                "aws_name": e.get("aws_name", ""),
                "oci_resource_type": e.get("oci_resource_type", ""),
                "oci_terraform": e.get("oci_terraform", ""),
            }
            for e in _current_resource_mapping[:50]
        ]
        return json.dumps(summary)

    return [
        read_bundle_file,
        write_bundle_file,
        list_bundle_files,
        classify_gap_tool,
        get_resource_mapping_summary,
        terraform_validate,
    ]


_WRITER_SYSTEM_PROMPT = """\
You are a Terraform repair agent fixing validation gaps in an OCI migration bundle.

Your job is to fix auto_fixable gaps in the bundle. You must NOT attempt to fix
needs_human gaps (skill failures, unmapped resources, etc.).

## Available tools

- read_bundle_file(path): Read a file from the bundle to inspect its contents.
- write_bundle_file(path, content): Write the complete new content for a bundle file.
- list_bundle_files(): List all file paths in the bundle.
- classify_gap_tool(check, severity, description, needs_human): Check if a gap is auto_fixable.
- get_resource_mapping_summary(): See what OCI resources are expected.
- terraform_validate(main_tf, variables_tf, outputs_tf): Validate HCL correctness.

## Workflow

1. Read the gaps provided in the prompt. Only fix gaps classified as auto_fixable.
2. Use read_bundle_file to inspect the relevant files.
3. For undeclared_variable gaps: read the current variables.tf, add the missing
   variable declarations with sensible types and descriptions, then write_bundle_file.
4. For missing_oci_resource gaps: read the relevant .tf files and the resource mapping,
   then add stub resource blocks with the correct Terraform type. Use
   get_resource_mapping_summary to understand what types are expected.
5. After making fixes, use terraform_validate to verify your changes compile.
6. When done fixing all auto_fixable gaps, say "REPAIR COMPLETE" and summarize
   what you fixed.

## Important rules

- Always write COMPLETE file contents (not patches/diffs) when using write_bundle_file.
- Do not modify files that are unrelated to the gaps.
- Do not attempt to fix needs_human gaps.
- Prefer minimal, correct fixes over ambitious rewrites.
- When adding variable declarations, use type = string as the default unless
  the usage context clearly indicates another type.
"""


def _build_writer_agent():
    """Construct the writer Agent using the agent SDK infrastructure."""
    from agents import Agent, ModelSettings
    from app.agents.config import build_model
    from app.gateway.model_gateway import get_model

    return Agent(
        name="Synthesis Validator Writer",
        instructions=_WRITER_SYSTEM_PROMPT,
        model=build_model(get_model("synthesis", "enhancement")),
        model_settings=ModelSettings(max_tokens=32_000),
        tools=_build_writer_tools(),
    )


async def _run_writer_agent(gaps: list[dict]) -> None:
    """Run the writer agent to fix auto_fixable gaps in the current bundle.

    The agent modifies _current_bundle in-place via write_bundle_file tool calls.
    """
    from agents import Runner

    auto_fixable = [g for g in gaps if classify_gap(g) == "auto_fixable"]
    if not auto_fixable:
        return

    gap_descriptions = [
        {
            "check": g["check"],
            "severity": g["severity"],
            "description": g["description"],
            "file": g.get("file", ""),
        }
        for g in auto_fixable[:30]  # cap context size
    ]

    prompt = (
        "## Validation gaps to fix\n\n"
        f"```json\n{json.dumps(gap_descriptions, indent=2)}\n```\n\n"
        f"There are {len(auto_fixable)} auto-fixable gap(s). "
        "Use your tools to inspect the bundle, apply fixes, and validate.\n\n"
        "Start by listing the bundle files, then read the relevant ones, "
        "fix the gaps, and validate your changes."
    )

    writer = _build_writer_agent()
    # max_turns=20 gives the agent enough room to read files, write fixes,
    # and validate, without letting it spin indefinitely.
    await Runner.run(writer, input=prompt, max_turns=20)


def _deterministic_review(
    bundle: dict[str, str],
    resource_mapping: list[dict],
    skill_logs: list[str],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Deterministic reviewer: re-run static checks and classify gaps.

    Returns:
        (all_gaps, auto_fixable_gaps, needs_human_gaps)
    """
    gaps = _static_checks(bundle, resource_mapping, skill_logs)
    auto_fixable = [g for g in gaps if classify_gap(g) == "auto_fixable"]
    needs_human = [g for g in gaps if classify_gap(g) == "needs_human"]
    return gaps, auto_fixable, needs_human


def validate_and_repair(
    bundle: dict[str, str],
    resource_mapping: list[dict],
    skill_logs: list[str],
    max_iterations: int = 2,
    _progress: Any | None = None,
) -> tuple[dict[str, str], list[dict]]:
    """Validate a synthesis bundle and optionally repair via LLM.

    Args:
        bundle: The build_hybrid_bundle output (path -> content).
        resource_mapping: The resource_mapper.compute() output for this app group.
        skill_logs: The _progress() lines accumulated during the run.
        max_iterations: Ignored (kept for API compat). Hard cap is 8.
        _progress: Optional callable for logging progress lines to the UI.

    Returns:
        (possibly-repaired bundle, list of remaining gaps)
    """
    global _current_bundle, _current_resource_mapping

    HARD_CAP = 8

    gaps = _static_checks(bundle, resource_mapping, skill_logs)
    logger.info("Post-synthesis validation: %d initial gap(s)", len(gaps))

    if not gaps:
        return bundle, []

    # Classify initial gaps
    auto_fixable = [g for g in gaps if classify_gap(g) == "auto_fixable"]
    needs_human = [g for g in gaps if classify_gap(g) == "needs_human"]

    if not auto_fixable:
        # Nothing the agent can fix — return immediately
        for g in needs_human:
            g["why_not_auto_fixed"] = _why_not_auto_fixed(g)
        return bundle, needs_human

    prev_auto_count: int | None = None

    for iteration in range(HARD_CAP):
        # Classify current gaps
        auto_fixable = [g for g in gaps if classify_gap(g) == "auto_fixable"]
        needs_human = [g for g in gaps if classify_gap(g) == "needs_human"]

        total = len(gaps)
        a_count = len(auto_fixable)
        h_count = len(needs_human)

        if _progress:
            _progress(
                "validation",
                f"Validation iter {iteration + 1}: {total} total / "
                f"{a_count} auto-fixable / {h_count} needs human",
            )
        logger.info(
            "Validation iter %d: %d total / %d auto-fixable / %d needs human",
            iteration + 1, total, a_count, h_count,
        )

        # Stop if no auto-fixable gaps remain
        if not auto_fixable:
            logger.info("No auto-fixable gaps remain, stopping")
            break

        # No-progress detection: if auto_fixable count hasn't decreased
        if prev_auto_count is not None and a_count >= prev_auto_count:
            logger.info(
                "No progress detected (%d auto-fixable gaps, was %d), stopping",
                a_count, prev_auto_count,
            )
            if _progress:
                _progress("validation", "Validation no-progress — stopping repair loop")
            break
        prev_auto_count = a_count

        # ── Writer Agent round ────────────────────────────────────────
        # Set module-level refs so agent tools can access the bundle
        _current_bundle = bundle
        _current_resource_mapping = resource_mapping

        try:
            # Run the async writer agent from this sync context.
            # Use asyncio.run() for a clean event loop, matching the
            # pattern in app.agents.job_result.run_skill_sync.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                # We're inside an already-running event loop (e.g. an async
                # caller wrapped us). Create a new thread to avoid nesting.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(asyncio.run, _run_writer_agent(gaps)).result()
            else:
                asyncio.run(_run_writer_agent(gaps))

            # The agent may have modified _current_bundle via write_bundle_file
            bundle = _current_bundle

        except Exception as exc:
            logger.warning("Writer agent failed: %s", exc)
            if _progress:
                _progress("validation", f"Writer agent error: {str(exc)[:200]}")
            break

        # ── Deterministic Reviewer round ──────────────────────────────
        gaps, auto_fixable, needs_human = _deterministic_review(
            bundle, resource_mapping, skill_logs,
        )

        repaired = (prev_auto_count or 0) - len(auto_fixable)
        if _progress:
            _progress(
                "validation",
                f"Validation iter {iteration + 1}: {len(gaps)} total / "
                f"{len(auto_fixable)} auto-fixable / {len(needs_human)} needs human / "
                f"{max(repaired, 0)} repaired",
            )

        # ACCEPT: no auto_fixable gaps remain
        if not auto_fixable:
            logger.info("All auto-fixable gaps resolved after iteration %d", iteration + 1)
            break

    # Final classification for the return value
    final_gaps: list[dict] = []
    for g in gaps:
        kind = classify_gap(g)
        if kind == "needs_human":
            g["why_not_auto_fixed"] = _why_not_auto_fixed(g)
            final_gaps.append(g)
        else:
            # Auto-fixable gaps that survived (no-progress or hard-cap)
            g["why_not_auto_fixed"] = (
                "LLM repair could not resolve this gap within the iteration budget"
            )
            final_gaps.append(g)

    return bundle, final_gaps
