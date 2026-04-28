"""Agentic synthesis polish pass.

Runs AFTER ``synthesis_composer.compose_terraform()`` produces the bundle
and BEFORE ``synthesis_validator.validate_and_repair()`` runs.  The goal
is composition-level clean-up that the per-skill writers cannot do because
they only see their own slice:

- Cross-skill resource references (e.g. compute.tf referencing a subnet
  should point at ``oci_core_subnet.<actual>.id`` from network.tf, not
  ``var.subnet_id``).
- Sensible renaming when the composer's auto-rename appended unhelpful
  ``_from_<skill>`` suffixes.
- Collapse trivial duplicate ``locals`` across files.
- Add missing ``required_providers`` entries if a resource type's provider
  is not covered by ``providers.tf``.
- Does NOT touch ``ocm/*`` submodule files.
- Does NOT move resources between files or change file paths.
- Stops as soon as ``terraform validate`` passes.

Architecture: single writer Agent (no reviewer) using the ``openai-agents``
SDK.  The agent has four tools: ``terraform_validate``,
``lookup_aws_mapping``, ``read_bundle_file``, and ``write_bundle_file``.
The last two operate on a module-level ``_current_bundle`` dict reference
that is swapped in before each run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agents import Agent, ModelSettings, Runner, function_tool

from app.agents.config import build_model
from app.agents.tools import lookup_aws_mapping, terraform_validate
from app.gateway.model_gateway import get_model

_log = logging.getLogger(__name__)

_WRITER_MAX_OUTPUT_TOKENS = 32_000

# Module-level bundle reference.  Set by ``polish()`` before launching the
# agent so that the ``read_bundle_file`` / ``write_bundle_file`` tools can
# reach the bundle without needing closure hacks around @function_tool.
_current_bundle: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Tools that operate on the in-memory bundle
# ---------------------------------------------------------------------------

@function_tool
def read_bundle_file(path: str) -> str:
    """Read the content of a file from the in-memory Terraform bundle.

    Args:
        path: Bundle-relative path, e.g. ``"terraform/main.tf"``.

    Returns:
        The file content as a string, or an error message if the path
        does not exist in the bundle.
    """
    content = _current_bundle.get(path)
    if content is None:
        available = sorted(_current_bundle.keys())[:40]
        return json.dumps({
            "error": f"Path {path!r} not found in bundle.",
            "available_paths": available,
        })
    return content


@function_tool
def write_bundle_file(path: str, content: str) -> str:
    """Write (overwrite) a file in the in-memory Terraform bundle.

    Use this to apply your fixes.  You MUST write the complete file
    content -- partial patches are not supported.

    Args:
        path: Bundle-relative path, e.g. ``"terraform/network.tf"``.
              Must NOT start with ``"terraform/ocm/"`` (OCM submodule
              files are read-only).
        content: Full replacement content for the file.

    Returns:
        JSON confirmation or error message.
    """
    if path.startswith("terraform/ocm/"):
        return json.dumps({
            "error": "OCM submodule files are read-only. Do not modify terraform/ocm/* files.",
        })
    _current_bundle[path] = content
    return json.dumps({"ok": True, "path": path, "bytes": len(content)})


# ---------------------------------------------------------------------------
# Helper: run terraform_validate on the root-module .tf files in the bundle
# ---------------------------------------------------------------------------

def _extract_root_tf(bundle: dict[str, str]) -> tuple[str, str, str]:
    """Extract concatenated main / variables / outputs HCL from root module.

    All ``terraform/*.tf`` files excluding ``terraform/ocm/**`` are
    considered root-module files.  We concatenate them by role:

    - ``variables.tf`` content -> variables_tf
    - ``outputs.tf``   content -> outputs_tf
    - everything else          -> main_tf  (providers.tf, network.tf, ...)

    Returns:
        (main_tf, variables_tf, outputs_tf)
    """
    main_parts: list[str] = []
    variables_tf = ""
    outputs_tf = ""

    for path, content in sorted(bundle.items()):
        if not path.startswith("terraform/") or path.startswith("terraform/ocm/"):
            continue
        if not path.endswith(".tf"):
            continue

        basename = path.rsplit("/", 1)[-1]
        if basename == "variables.tf":
            variables_tf += "\n" + content
        elif basename == "outputs.tf":
            outputs_tf += "\n" + content
        else:
            main_parts.append(f"# --- {path} ---\n{content}")

    main_tf = "\n\n".join(main_parts)
    return main_tf.strip(), variables_tf.strip(), outputs_tf.strip()


def _run_tf_validate_on_bundle(bundle: dict[str, str]) -> dict:
    """Run ``terraform validate`` synchronously on the root-module HCL.

    Replicates the core subprocess logic from
    ``app.agents.tools.terraform_validate`` (which is a ``@function_tool``
    and not directly callable as a plain function) so we can gate the
    fast-path check without the agent SDK's tool invocation machinery.

    Returns the parsed result dict.
    """
    # Import the sandbox helper from tools -- it is a plain function, not
    # decorated, so it is safe to call directly.
    from app.agents.tools import _build_sandboxed_cmd

    main_tf, variables_tf, outputs_tf = _extract_root_tf(bundle)
    if not main_tf:
        return {"valid": False, "output": "No root-module .tf content found in bundle."}

    tf_bin = os.environ.get("TERRAFORM_BIN", "terraform")
    if not shutil.which(tf_bin):
        return {
            "valid": False,
            "output": "terraform binary not available on PATH. Skipping validation.",
            "skipped": True,
        }

    with tempfile.TemporaryDirectory(prefix="tf_polish_validate_") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "main.tf").write_text(main_tf)
        if variables_tf.strip():
            (tmp_path / "variables.tf").write_text(variables_tf)
        if outputs_tf.strip():
            (tmp_path / "outputs.tf").write_text(outputs_tf)

        init_cmd = _build_sandboxed_cmd(
            [tf_bin, "init", "-backend=false", "-input=false", "-no-color"],
            tmp_path,
        )
        val_cmd = _build_sandboxed_cmd(
            [tf_bin, "validate", "-no-color", "-json"],
            tmp_path,
        )

        try:
            init = subprocess.run(
                init_cmd, capture_output=True, text=True, timeout=120,
            )
            if init.returncode != 0:
                return {
                    "valid": False,
                    "output": (
                        f"terraform init failed:\n{init.stdout}\n{init.stderr}"
                    )[:4000],
                }
            val = subprocess.run(
                val_cmd, capture_output=True, text=True, timeout=60,
            )
            try:
                parsed = json.loads(val.stdout)
                return {
                    "valid": bool(parsed.get("valid")),
                    "error_count": parsed.get("error_count", 0),
                    "warning_count": parsed.get("warning_count", 0),
                    "diagnostics": parsed.get("diagnostics", [])[:20],
                }
            except json.JSONDecodeError:
                return {
                    "valid": val.returncode == 0,
                    "output": f"{val.stdout}\n{val.stderr}"[:4000],
                }
        except subprocess.TimeoutExpired:
            return {"valid": False, "output": "terraform timed out (>120s)"}


# ---------------------------------------------------------------------------
# Agent construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a **Terraform composition polish** agent.  You receive a Terraform
bundle that was assembled by merging per-skill translation outputs.  Your
job is to make the bundle pass `terraform validate` and clean up
composition-level issues.

## What you MUST fix
1. **Cross-skill resource references** -- e.g. a compute resource
   referencing `var.subnet_id` when the actual subnet is declared in
   network.tf as `oci_core_subnet.main`.  Replace dangling `var.*`
   references with the real resource attribute (`oci_core_subnet.main.id`).
2. **Unhelpful renames** -- the composer sometimes appends `_from_<skill>`
   suffixes to resource names.  Rename to something meaningful if the
   original name is clear from context.
3. **Duplicate locals** -- if multiple files declare the same `locals`
   block key with identical values, consolidate into one file.
4. **Missing `required_providers`** -- if a resource uses a provider not
   listed in `providers.tf`, add the entry.
5. **Any issue reported by `terraform_validate`** -- fix syntax errors,
   undeclared variables, duplicate resources, etc.

## What you MUST NOT do
- Do NOT touch files under `terraform/ocm/` (the OCM submodule is
  managed separately).
- Do NOT move resources between files or rename file paths.
- Do NOT delete resources -- only fix references and declarations.
- Do NOT invent new resources that are not already in the bundle.

## Workflow
1. Read the bundle files you need using `read_bundle_file`.
2. Identify issues by inspecting cross-references and the
   `terraform_validate` diagnostics provided in the prompt.
3. Write fixes using `write_bundle_file`.
4. Call `terraform_validate` to verify your changes.
5. Repeat until `terraform_validate` reports valid=true, then stop.

## Tools
- `read_bundle_file(path)` -- read a file from the bundle.
- `write_bundle_file(path, content)` -- overwrite a file in the bundle.
- `terraform_validate(main_tf, variables_tf, outputs_tf)` -- run
  `terraform init && terraform validate` on HCL strings.
- `lookup_aws_mapping(aws_type)` -- look up the canonical OCI mapping
  for an AWS type.

When calling `terraform_validate`, concatenate all root-module .tf files
(excluding terraform/ocm/*) into `main_tf`, with `variables.tf` content
in `variables_tf` and `outputs.tf` content in `outputs_tf`.
"""


def _build_polish_agent() -> Agent:
    """Construct the single polish writer agent."""
    model_id = get_model("synthesis", "enhancement")
    return Agent(
        name="Synthesis Polish Agent",
        instructions=_SYSTEM_PROMPT,
        model=build_model(model_id),
        model_settings=ModelSettings(max_tokens=_WRITER_MAX_OUTPUT_TOKENS),
        tools=[
            terraform_validate,
            lookup_aws_mapping,
            read_bundle_file,
            write_bundle_file,
        ],
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_initial_prompt(
    bundle: dict[str, str],
    resource_mapping: list[dict],
    tf_result: dict,
) -> str:
    """Build the initial user prompt for the polish agent."""
    # File inventory with sizes
    file_list: list[str] = []
    for path in sorted(bundle.keys()):
        size = len(bundle[path])
        tag = " (ocm submodule -- read-only)" if path.startswith("terraform/ocm/") else ""
        file_list.append(f"  {path}  ({size} bytes){tag}")

    # Per-skill source dirs under debug/
    debug_dirs: list[str] = sorted(
        {p.split("/")[0] + "/" + p.split("/")[1]
         for p in bundle if p.startswith("debug/") and "/" in p}
    )

    # Resource mapping summary (compact)
    mapping_lines: list[str] = []
    for entry in resource_mapping[:60]:
        aws_t = entry.get("aws_type", "?")
        aws_n = entry.get("aws_name", "")
        oci_tf = entry.get("oci_terraform", "")
        mapping_lines.append(f"  {aws_t} ({aws_n}) -> {oci_tf}")

    # terraform validate diagnostics
    diag_text = json.dumps(tf_result, indent=2)

    parts = [
        "## Bundle files",
        "\n".join(file_list),
        "",
        "## Debug / per-skill source directories",
        "\n".join(f"  {d}" for d in debug_dirs) if debug_dirs else "  (none)",
        "",
        "## Resource mapping summary",
        "\n".join(mapping_lines) if mapping_lines else "  (empty)",
        "",
        "## Initial terraform validate result",
        f"```json\n{diag_text}\n```",
        "",
        "Please read the files that need fixing, apply your changes, and "
        "verify with terraform_validate.  Stop when valid=true.",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def polish(
    bundle: dict[str, str],
    resource_mapping: list[dict],
    _progress: Any | None = None,
) -> tuple[dict[str, str], int, bool]:
    """Run the agentic polish pass on a synthesis bundle.

    Args:
        bundle: The bundle dict (path -> content) from
            ``synthesis_composer.compose_terraform()``.  Modified in place
            if fixes are applied.
        resource_mapping: The ``resource_mapper.compute()`` output for
            the current app group.
        _progress: Optional ``(phase, message)`` callback for UI updates.

    Returns:
        ``(possibly_polished_bundle, iterations_used, terraform_validate_clean)``
        where *iterations_used* counts how many agent-run iterations were
        executed (0 if the fast-path no-op fired) and
        *terraform_validate_clean* is True when the final bundle passes
        ``terraform validate``.
    """
    global _current_bundle  # noqa: PLW0603

    # ── Fast-path: if terraform validate already passes, skip entirely ──
    initial_result = _run_tf_validate_on_bundle(bundle)
    if initial_result.get("valid"):
        _log.info("synthesis_polish: bundle already valid, skipping polish pass")
        if _progress:
            _progress("polish", "Bundle already passes terraform validate -- skipping polish")
        return bundle, 0, True

    if initial_result.get("skipped"):
        _log.info("synthesis_polish: terraform binary not available, skipping polish pass")
        if _progress:
            _progress("polish", "terraform not available -- skipping polish")
        return bundle, 0, False

    _log.info(
        "synthesis_polish: initial validate failed (%s), starting polish agent",
        initial_result.get("output", "")[:200],
    )
    if _progress:
        _progress("polish", "Initial terraform validate failed -- starting polish agent")

    # ── Set the module-level bundle reference for the tools ──
    _current_bundle = bundle

    agent = _build_polish_agent()
    prompt = _build_initial_prompt(bundle, resource_mapping, initial_result)

    max_outer_iterations = 5
    iterations_used = 0
    tf_clean = False

    try:
        for outer in range(1, max_outer_iterations + 1):
            iterations_used = outer
            if _progress:
                _progress("polish", f"Polish iteration {outer}/{max_outer_iterations}")

            _log.info("synthesis_polish: outer iteration %d/%d", outer, max_outer_iterations)

            result = await Runner.run(agent, input=prompt, max_turns=20)

            # Check if terraform validate now passes
            post_result = _run_tf_validate_on_bundle(bundle)
            if post_result.get("valid"):
                _log.info("synthesis_polish: bundle now valid after iteration %d", outer)
                if _progress:
                    _progress("polish", f"Bundle passes terraform validate after iteration {outer}")
                tf_clean = True
                break

            # Not valid yet -- feed diagnostics back as the next prompt
            _log.info(
                "synthesis_polish: still invalid after iteration %d: %s",
                outer,
                json.dumps(post_result.get("diagnostics", [])[:5]),
            )
            if _progress:
                _progress(
                    "polish",
                    f"Still invalid after iteration {outer} "
                    f"({post_result.get('error_count', '?')} errors) -- retrying",
                )

            # Build a shorter follow-up prompt with the remaining diagnostics
            prompt = (
                "## terraform validate still failing\n\n"
                f"```json\n{json.dumps(post_result, indent=2)}\n```\n\n"
                "Read the relevant files, fix the remaining issues, and "
                "re-validate.  Stop when valid=true."
            )
    finally:
        # Clear the module-level reference to avoid holding the bundle
        # in memory after the polish pass completes.
        _current_bundle = {}

    if not tf_clean:
        _log.warning(
            "synthesis_polish: exhausted %d iterations without achieving valid bundle",
            max_outer_iterations,
        )
        if _progress:
            _progress(
                "polish",
                f"Polish exhausted {max_outer_iterations} iterations -- "
                "bundle may still have validation errors",
            )

    return bundle, iterations_used, tf_clean


def polish_sync(
    bundle: dict[str, str],
    resource_mapping: list[dict],
    _progress: Any | None = None,
) -> tuple[dict[str, str], int, bool]:
    """Synchronous wrapper around :func:`polish`.

    Safe to call from ``plan_orchestrator.py`` which runs synchronously.
    If there is already a running event loop (e.g. inside an async web
    handler), spins up a new thread to avoid ``RuntimeError``.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is None:
        # No event loop running -- just create one.
        return asyncio.run(polish(bundle, resource_mapping, _progress))

    # An event loop is already running (e.g. FastAPI handler).  We cannot
    # call asyncio.run() from within a running loop, so offload to a
    # background thread with its own loop.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            asyncio.run,
            polish(bundle, resource_mapping, _progress),
        )
        return future.result()
