"""Reorganize plan_orchestrator's raw per-skill artifacts into a hybrid
migration bundle the operator can ship to production.

Input: the ``completed_artifacts`` dict the plan pipeline accumulates, keyed
like ``{skill}/{filename}`` (plus a few top-level files like
``resource-mapping.json``).

Output: a new flat dict keyed by the hybrid layout:

    terraform/        — synthesis output; the HCL you terraform-apply
    terraform/ocm/    — OCM handoff HCL (parallel stack when hybrid routing runs)
    runbooks/         — handoff.md, data-migration/*, cutover/*
    reports/          — resource-mapping.json, gaps.md, prerequisites.md,
                        special-attention.md, cost-compare.md (optional)
    debug/            — every per-skill intermediate HCL (collapsed in UI)
    README.md         — top-level "how to use this bundle" doc
    manifest.json     — machine-readable file index + metadata + SHA256s

Separate module so plan_orchestrator stays under 1k LOC.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Skills whose per-skill HCL is merged by synthesis — their bundles are
# traceability-only; move them to debug/.
_INTERMEDIATE_SKILLS = {
    "network_translation",
    "ec2_translation",
    "storage_translation",
    "database_translation",
    "loadbalancer_translation",
    "iam_translation",
    "security_translation",
    "serverless_translation",
    "observability_translation",
    "cfn_terraform",
}


def build_hybrid_bundle(
    completed_artifacts: dict[str, str],
    *,
    migration_name: str,
    resource_count: int,
    skills_ran: list[str] | None = None,
    elapsed_seconds: float | None = None,
    synthesis_ok: bool = True,
    ocm_instance_count: int = 0,
    native_instance_count: int = 0,
) -> dict[str, str]:
    """Reorganize completed_artifacts into the hybrid bundle layout.

    The input dict is not mutated — we return a fresh dict with the new
    keys. Call this at the end of the plan pipeline, just before storing
    results in the DB.
    """
    out: dict[str, str] = {}
    skills_ran = skills_ran or []

    # Track what we saw for the manifest + README.
    sections: dict[str, list[str]] = {"terraform": [], "runbooks": [], "reports": [], "debug": []}
    gaps_collected: list[dict[str, Any]] = []

    for key, content in completed_artifacts.items():
        if not isinstance(content, str):
            continue
        new_key = _map_key(key)
        if new_key is None:
            continue
        out[new_key] = content
        top = new_key.split("/", 1)[0]
        if top in sections:
            sections[top].append(new_key)

    # Aggregate gaps from every skill's review metadata if the caller
    # embedded them in the artifact payload (plan_orchestrator can pass
    # them via a sentinel key, documented below).
    sentinel = completed_artifacts.get("_review_gaps_sentinel")
    if isinstance(sentinel, str) and sentinel:
        try:
            gaps_collected = json.loads(sentinel) or []
        except (ValueError, TypeError):
            gaps_collected = []

    # Generate the gaps report + README + manifest last so they reflect
    # the final set of files.
    out["reports/gaps.md"] = _render_gaps_md(gaps_collected, skills_ran)
    sections["reports"].append("reports/gaps.md")

    readme = _render_readme(
        migration_name=migration_name,
        resource_count=resource_count,
        skills_ran=skills_ran,
        elapsed_seconds=elapsed_seconds,
        synthesis_ok=synthesis_ok,
        ocm_instance_count=ocm_instance_count,
        native_instance_count=native_instance_count,
        sections=sections,
    )
    out["README.md"] = readme

    manifest = _render_manifest(
        migration_name=migration_name,
        resource_count=resource_count,
        skills_ran=skills_ran,
        elapsed_seconds=elapsed_seconds,
        bundle=out,
    )
    out["manifest.json"] = manifest

    return out


# ─── Key mapping ─────────────────────────────────────────────────────────────

def _map_key(key: str) -> str | None:
    """Translate ``completed_artifacts`` keys into hybrid bundle paths."""
    # Top-level files
    if key == "resource-mapping.json":
        return "reports/resource-mapping.json"
    if "/" not in key:
        # Other bare top-level files fall under reports/
        return f"reports/{key}"

    prefix, rest = key.split("/", 1)

    # synthesis/ — the primary Terraform output
    if prefix == "synthesis":
        # Sub-docs like prerequisites.md / special-attention.md are actually reports
        if rest in ("prerequisites.md", "special-attention.md"):
            return f"reports/{rest}"
        return f"terraform/{rest}"

    # ocm_handoff_translation/ — parallel OCM Terraform + its handoff runbook
    if prefix == "ocm_handoff_translation":
        if rest == "handoff.md":
            return "runbooks/handoff.md"
        return f"terraform/ocm/{rest}"

    # data_migration/ and workload_planning/ are pure runbooks
    if prefix == "data_migration":
        return f"runbooks/data-migration/{rest}"
    if prefix == "workload_planning":
        return f"runbooks/cutover/{rest}"
    if prefix == "dependency_discovery":
        return f"reports/dependency-analysis/{rest}"

    # Everything else that's a known intermediate skill → debug/
    if prefix in _INTERMEDIATE_SKILLS:
        return f"debug/{prefix}/{rest}"

    # Unknown skill — keep under debug to avoid polluting the top level
    return f"debug/{prefix}/{rest}"


# ─── Report generators ──────────────────────────────────────────────────────

def _render_gaps_md(gaps: list[dict[str, Any]], skills_ran: list[str]) -> str:
    """Aggregate every skill reviewer's ``issues`` / ``gaps`` array into one
    operator-facing document.

    Expects entries like:
        {"skill": "ec2_translation", "severity": "HIGH",
         "description": "...", "recommendation": "..."}

    Returns a grouped markdown doc with CRITICAL/HIGH first, LOW last.
    """
    if not gaps:
        return (
            "# Gaps & Manual Follow-ups\n\n"
            "No gaps were reported by any skill reviewer. This doesn't mean "
            "zero manual work — re-read each runbook in `runbooks/` for "
            "service-specific steps. But nothing was flagged as blocking.\n"
        )

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "": 4}
    gaps_sorted = sorted(
        gaps,
        key=lambda g: (
            severity_order.get((g.get("severity") or "").upper(), 5),
            g.get("skill", ""),
        ),
    )

    lines = ["# Gaps & Manual Follow-ups", ""]
    lines.append(
        f"Aggregated from {len(skills_ran)} skill reviewers. Severity order: "
        f"CRITICAL → HIGH → MEDIUM → LOW."
    )
    lines.append("")

    current_sev = None
    for g in gaps_sorted:
        sev = (g.get("severity") or "INFO").upper()
        if sev != current_sev:
            lines.append(f"## {sev}\n")
            current_sev = sev
        skill = g.get("skill") or "—"
        desc = g.get("description") or g.get("issue") or ""
        rec = g.get("recommendation") or g.get("fix") or ""
        lines.append(f"### [{skill}] {desc}" if desc else f"### [{skill}]")
        if rec:
            lines.append(f"**Recommendation:** {rec}")
        lines.append("")

    return "\n".join(lines)


def _render_readme(
    *,
    migration_name: str,
    resource_count: int,
    skills_ran: list[str],
    elapsed_seconds: float | None,
    synthesis_ok: bool,
    ocm_instance_count: int,
    native_instance_count: int,
    sections: dict[str, list[str]],
) -> str:
    """The top-level README that lives at the root of the bundle."""
    hybrid_line = ""
    if ocm_instance_count or native_instance_count:
        hybrid_line = (
            f"- **EC2 routing:** {ocm_instance_count} instance(s) routed through "
            f"Oracle Cloud Migrations (OCM), {native_instance_count} via native "
            f"Terraform.\n"
        )

    tf_count = len(sections["terraform"])
    runbook_count = len(sections["runbooks"])
    report_count = len(sections["reports"])
    debug_count = len(sections["debug"])

    lines = [
        f"# Migration bundle — {migration_name}",
        "",
        f"- **Source resources:** {resource_count}",
        f"- **Skills ran:** {', '.join(skills_ran) or 'none'}",
        f"- **Generated in:** {elapsed_seconds:.1f}s" if elapsed_seconds is not None else "",
        f"- **Synthesis:** {'succeeded' if synthesis_ok else 'FAILED — see debug/'}",
        hybrid_line.rstrip(),
        "",
        "## Directory layout",
        "",
        f"- `terraform/` ({tf_count} file(s)) — the HCL you `terraform apply`. If `terraform/ocm/` exists, that's a parallel stack for OCM-handed-off EC2 instances; apply it after the main `terraform/`.",
        f"- `runbooks/` ({runbook_count} file(s)) — human-ordered checklists:",
        "  - `handoff.md` — OCM handoff prerequisites + asset-link + execute steps (present only in hybrid mode)",
        "  - `data-migration/` — per-DB and per-volume migration recipes with downtime estimates",
        "  - `cutover/` — per-workload cutover runbook + anomalies to watch",
        f"- `reports/` ({report_count} file(s)) — non-executable context:",
        "  - `resource-mapping.json` — deterministic AWS→OCI resource map (what each resource becomes)",
        "  - `gaps.md` — aggregated manual-follow-ups from every skill reviewer, sorted by severity",
        "  - `prerequisites.md`, `special-attention.md` — synthesis-flagged setup items",
        f"- `debug/` ({debug_count} file(s)) — per-skill intermediate HCL, kept for traceability. You generally don't apply anything here; the merged `terraform/` bundle supersedes it.",
        "- `manifest.json` — machine-readable file index with SHA256 checksums.",
        "",
        "## Apply order",
        "",
        "1. Review `reports/gaps.md` and `runbooks/handoff.md` (if present).",
        "2. Verify OCI credentials, target compartment, and pre-existing Vault / IAM policies.",
        "3. `cd terraform && terraform init && terraform plan` — inspect the plan.",
        "4. `terraform apply` — provisions the unified stack.",
        "5. If `terraform/ocm/` exists: `cd terraform/ocm && terraform apply` — kicks off OCM replication; monitor via the OCM progress card in the UI or `oci work-requests work-request list`.",
        "6. Follow `runbooks/data-migration/` for any DB / volume data moves.",
        "7. Follow `runbooks/cutover/` for the ordered switchover.",
        "8. Run post-cutover validation per `runbooks/cutover/validation.md` (if present).",
        "",
        "## Rollback",
        "",
        "- `cd terraform && terraform destroy` reverses the TF stack.",
        "- OCM-launched instances: use the Migrate → Rollback button in the UI (calls OCM's delete-migration-plan API), or manually delete the OCM plan in the OCI console — this removes the OCI VMs but leaves the golden volumes for forensics.",
        "- DNS flip-back + session redirection steps are in `runbooks/cutover/rollback.md` if present.",
    ]
    return "\n".join(l for l in lines if l is not None)


def _render_manifest(
    *,
    migration_name: str,
    resource_count: int,
    skills_ran: list[str],
    elapsed_seconds: float | None,
    bundle: dict[str, str],
) -> str:
    """JSON manifest with file list + SHA256s for tamper detection."""
    files = []
    for path, content in bundle.items():
        if path == "manifest.json":  # don't hash ourselves
            continue
        sha = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
        files.append({
            "path": path,
            "size_bytes": len(content.encode("utf-8", errors="replace")),
            "sha256": sha,
        })
    files.sort(key=lambda f: f["path"])
    return json.dumps({
        "schema_version": "1",
        "migration_name": migration_name,
        "resource_count": resource_count,
        "skills_ran": skills_ran,
        "elapsed_seconds": round(elapsed_seconds, 1) if elapsed_seconds is not None else None,
        "file_count": len(files),
        "files": files,
    }, indent=2)
