"""Per-skill and merged-bundle Terraform validation.

Runs ``terraform validate`` at three checkpoints in the plan pipeline:

1. **Per-skill** -- right after each skill writer produces HCL, before the
   reviewer loop.  Catches syntax errors and unknown resource types early so
   the writer/reviewer can self-correct without polluting downstream stages.

2. **Merged bundle** -- after synthesis_composer merges all skill outputs into
   a single Terraform root module.  Catches cross-skill reference errors
   (e.g. a compute resource referencing a VCN name that the network skill
   spelled differently).

3. **Final** -- after the validate-and-repair loop in synthesis_validator has
   had its chance to fix issues.  If errors remain here, they are surfaced as
   ``needs_human`` gaps in the bundle metadata.

All three checkpoints degrade gracefully: if the ``terraform`` binary is not
on PATH, they log a warning and return ``valid=True`` so the pipeline keeps
moving.  This lets developers run the backend locally without Terraform
installed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger(__name__)

# Regex to find var.<name> references in HCL (same pattern used in
# synthesis_validator._VAR_REF_RE).
_VAR_REF_RE = re.compile(r'\bvar\.([a-zA-Z_][a-zA-Z0-9_]*)\b')


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PerSkillValidateResult:
    """Result of validating a single skill's HCL fragments."""
    valid: bool
    skill_type: str
    error_count: int
    warning_count: int
    diagnostics: list[dict]
    errors_text: str  # human-readable error summary


@dataclass
class MergedValidateResult:
    """Result of validating the merged Terraform bundle."""
    valid: bool
    error_count: int
    warning_count: int
    diagnostics: list[dict]
    errors_text: str
    gaps: list[dict] = field(default_factory=list)


@dataclass
class FinalValidateResult:
    """Result of the final validation checkpoint."""
    valid: bool
    error_count: int
    warning_count: int
    diagnostics: list[dict]
    errors_text: str
    gaps: list[dict] = field(default_factory=list)
    needs_human: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_terraform_binary() -> str | None:
    """Return the resolved path to the terraform binary, or None."""
    tf_bin = os.environ.get("TERRAFORM_BIN", "terraform")
    resolved = shutil.which(tf_bin)
    if resolved is None:
        _log.warning(
            "Terraform binary %r not found on PATH. "
            "Validation will be skipped (graceful degradation).",
            tf_bin,
        )
    return resolved


def _build_stub_variables_tf(hcl_fragments: dict[str, str]) -> str:
    """Generate a ``variables.tf`` with stub declarations for every
    ``var.NAME`` reference found across *hcl_fragments*.

    This ensures ``terraform validate`` does not fail simply because the
    skill output references variables that would normally be declared in a
    shared variables file.
    """
    var_names: set[str] = set()
    for content in hcl_fragments.values():
        var_names.update(_VAR_REF_RE.findall(content))

    if not var_names:
        return ""

    blocks: list[str] = []
    for name in sorted(var_names):
        blocks.append(
            f'variable "{name}" {{\n'
            f'  type    = string\n'
            f'  default = "stub"\n'
            f'}}'
        )
    return "\n\n".join(blocks) + "\n"


def _build_stub_providers_tf() -> str:
    """Return the canonical OCI provider block used by synthesis_composer."""
    return '''\
terraform {
  required_version = ">= 1.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = ">= 6.0.0"
    }
  }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}
'''


def _diagnostics_to_text(diagnostics: list[dict]) -> str:
    """Join diagnostic summaries into a human-readable string."""
    lines: list[str] = []
    for diag in diagnostics:
        severity = diag.get("severity", "error")
        summary = diag.get("summary", "unknown error")
        detail = diag.get("detail", "")
        entry = f"[{severity}] {summary}"
        if detail:
            entry += f": {detail}"
        lines.append(entry)
    return "\n".join(lines)


def _run_terraform_validate(tf_dir: Path) -> dict:
    """Run ``terraform init`` then ``terraform validate -json`` in *tf_dir*.

    Uses plain ``subprocess.run`` -- no sandboxing. This function is called
    server-side on content we control (stub providers + skill HCL), not on
    arbitrary LLM-generated shell commands.

    Returns a dict with keys: valid, error_count, warning_count,
    diagnostics, output.
    """
    tf_bin = _find_terraform_binary()
    if tf_bin is None:
        return {
            "valid": True,
            "error_count": 0,
            "warning_count": 0,
            "diagnostics": [],
            "output": "terraform binary not found; validation skipped",
        }

    # -- terraform init -------------------------------------------------------
    init_cmd = [tf_bin, "init", "-backend=false", "-input=false", "-no-color"]
    try:
        init_result = subprocess.run(
            init_cmd,
            cwd=str(tf_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        _log.error("terraform init timed out after 120s in %s", tf_dir)
        return {
            "valid": False,
            "error_count": 1,
            "warning_count": 0,
            "diagnostics": [{"severity": "error", "summary": "terraform init timed out"}],
            "output": "terraform init timed out after 120s",
        }

    if init_result.returncode != 0:
        _log.warning(
            "terraform init failed (rc=%d) in %s:\n%s",
            init_result.returncode, tf_dir, init_result.stderr[:2000],
        )
        return {
            "valid": False,
            "error_count": 1,
            "warning_count": 0,
            "diagnostics": [{
                "severity": "error",
                "summary": "terraform init failed",
                "detail": init_result.stderr[:2000],
            }],
            "output": init_result.stderr[:2000],
        }

    # -- terraform validate ---------------------------------------------------
    validate_cmd = [tf_bin, "validate", "-no-color", "-json"]
    try:
        val_result = subprocess.run(
            validate_cmd,
            cwd=str(tf_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        _log.error("terraform validate timed out after 60s in %s", tf_dir)
        return {
            "valid": False,
            "error_count": 1,
            "warning_count": 0,
            "diagnostics": [{"severity": "error", "summary": "terraform validate timed out"}],
            "output": "terraform validate timed out after 60s",
        }

    # Parse the JSON output from terraform validate.
    try:
        parsed = json.loads(val_result.stdout)
    except json.JSONDecodeError:
        _log.error(
            "Failed to parse terraform validate JSON output in %s:\n%s",
            tf_dir, val_result.stdout[:2000],
        )
        return {
            "valid": False,
            "error_count": 1,
            "warning_count": 0,
            "diagnostics": [{
                "severity": "error",
                "summary": "Failed to parse terraform validate output",
                "detail": val_result.stdout[:2000],
            }],
            "output": val_result.stdout[:2000],
        }

    return {
        "valid": parsed.get("valid", False),
        "error_count": parsed.get("error_count", 0),
        "warning_count": parsed.get("warning_count", 0),
        "diagnostics": parsed.get("diagnostics", []),
        "output": val_result.stdout[:4000],
    }


# ---------------------------------------------------------------------------
# Gap helper
# ---------------------------------------------------------------------------

def make_validate_gap(
    skill_type: str,
    error_summary: str,
    check_name: str = "terraform_validate",
) -> dict:
    """Create a gap dict from a validation error.

    Compatible with the gap format used by synthesis_validator.
    """
    return {
        "skill": skill_type,
        "severity": "HIGH",
        "check": check_name,
        "description": error_summary,
        "recommendation": (
            "Fix the HCL errors in the skill output. If auto-retry failed, "
            "review the terraform validate output and correct manually."
        ),
    }


# ---------------------------------------------------------------------------
# Checkpoint 1: per-skill validation
# ---------------------------------------------------------------------------

def per_skill_validate(
    skill_type: str,
    hcl_fragments: dict[str, str],
) -> PerSkillValidateResult:
    """Validate HCL fragments from a single skill.

    Creates a temporary Terraform root module containing the skill's
    ``.tf`` files plus stub providers and variables, then runs
    ``terraform validate``.

    Args:
        skill_type: e.g. ``"network_translation"``.
        hcl_fragments: mapping of filename to HCL content,
            e.g. ``{"network.tf": "resource ..."}``

    Returns:
        PerSkillValidateResult with the validation outcome.
    """
    tf_bin = _find_terraform_binary()
    if tf_bin is None:
        _log.info(
            "Skipping per-skill validation for %s (no terraform binary).",
            skill_type,
        )
        return PerSkillValidateResult(
            valid=True,
            skill_type=skill_type,
            error_count=0,
            warning_count=0,
            diagnostics=[],
            errors_text="",
        )

    with tempfile.TemporaryDirectory(prefix="tf_validate_") as tmp:
        tmp_path = Path(tmp)

        # Write skill fragment files.
        for filename, content in hcl_fragments.items():
            (tmp_path / filename).write_text(content)

        # Write stub providers and variables.
        (tmp_path / "providers.tf").write_text(_build_stub_providers_tf())

        stub_vars = _build_stub_variables_tf(hcl_fragments)
        if stub_vars:
            (tmp_path / "variables.tf").write_text(stub_vars)

        result = _run_terraform_validate(tmp_path)

    errors_text = _diagnostics_to_text(result["diagnostics"])

    _log.info(
        "per_skill_validate(%s): valid=%s errors=%d warnings=%d",
        skill_type, result["valid"], result["error_count"], result["warning_count"],
    )
    if not result["valid"]:
        _log.warning(
            "Terraform validation failed for skill %s:\n%s",
            skill_type, errors_text,
        )

    return PerSkillValidateResult(
        valid=result["valid"],
        skill_type=skill_type,
        error_count=result["error_count"],
        warning_count=result["warning_count"],
        diagnostics=result["diagnostics"],
        errors_text=errors_text,
    )


# ---------------------------------------------------------------------------
# Checkpoint 2: merged-bundle validation
# ---------------------------------------------------------------------------

def merged_bundle_validate(bundle: dict[str, str]) -> MergedValidateResult:
    """Validate the merged Terraform bundle after synthesis.

    Writes all ``terraform/*`` files (excluding ``terraform/ocm/`` submodule
    files) into a temp directory and runs ``terraform validate``.

    Args:
        bundle: full bundle dict with keys like ``"terraform/network.tf"``,
            ``"terraform/variables.tf"``, etc.

    Returns:
        MergedValidateResult with gaps pre-formatted for ``all_gaps``.
    """
    tf_bin = _find_terraform_binary()
    if tf_bin is None:
        _log.info("Skipping merged-bundle validation (no terraform binary).")
        return MergedValidateResult(
            valid=True,
            error_count=0,
            warning_count=0,
            diagnostics=[],
            errors_text="",
            gaps=[],
        )

    with tempfile.TemporaryDirectory(prefix="tf_validate_") as tmp:
        tmp_path = Path(tmp)

        for key, content in bundle.items():
            # Only include files directly under terraform/ (not submodules
            # like terraform/ocm/).
            if not key.startswith("terraform/"):
                continue
            relative = key[len("terraform/"):]
            # Skip submodule files (contain a slash after stripping prefix).
            if "/" in relative:
                continue
            (tmp_path / relative).write_text(content)

        result = _run_terraform_validate(tmp_path)

    errors_text = _diagnostics_to_text(result["diagnostics"])

    # Build gap dicts from error diagnostics.
    gaps: list[dict] = []
    for diag in result["diagnostics"]:
        if diag.get("severity") == "error":
            summary = diag.get("summary", "unknown error")
            detail = diag.get("detail", "")
            desc = f"Merged bundle validate: {summary}"
            if detail:
                desc += f" -- {detail[:200]}"
            gaps.append(make_validate_gap("synthesis", desc))

    _log.info(
        "merged_bundle_validate: valid=%s errors=%d warnings=%d gaps=%d",
        result["valid"], result["error_count"], result["warning_count"], len(gaps),
    )
    if not result["valid"]:
        _log.warning("Merged bundle validation failed:\n%s", errors_text)

    return MergedValidateResult(
        valid=result["valid"],
        error_count=result["error_count"],
        warning_count=result["warning_count"],
        diagnostics=result["diagnostics"],
        errors_text=errors_text,
        gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Checkpoint 3: final validation
# ---------------------------------------------------------------------------

def final_validate(bundle: dict[str, str]) -> FinalValidateResult:
    """Final validation after the validate-and-repair loop.

    Same mechanics as :func:`merged_bundle_validate`, but if errors remain
    the gaps are marked ``needs_human=True`` -- the pipeline has exhausted
    its auto-repair budget and a human must intervene.

    Args:
        bundle: full bundle dict.

    Returns:
        FinalValidateResult with ``needs_human`` flag.
    """
    tf_bin = _find_terraform_binary()
    if tf_bin is None:
        _log.info("Skipping final validation (no terraform binary).")
        return FinalValidateResult(
            valid=True,
            error_count=0,
            warning_count=0,
            diagnostics=[],
            errors_text="",
            gaps=[],
            needs_human=False,
        )

    with tempfile.TemporaryDirectory(prefix="tf_validate_") as tmp:
        tmp_path = Path(tmp)

        for key, content in bundle.items():
            if not key.startswith("terraform/"):
                continue
            relative = key[len("terraform/"):]
            if "/" in relative:
                continue
            (tmp_path / relative).write_text(content)

        result = _run_terraform_validate(tmp_path)

    errors_text = _diagnostics_to_text(result["diagnostics"])
    has_errors = not result["valid"]

    # Build gap dicts.
    gaps: list[dict] = []
    for diag in result["diagnostics"]:
        if diag.get("severity") == "error":
            summary = diag.get("summary", "unknown error")
            detail = diag.get("detail", "")
            desc = (
                "After polish and validation iterations, terraform validate "
                f"still reports: {summary}"
            )
            if detail:
                desc += f" -- {detail[:200]}"
            gap = make_validate_gap("synthesis", desc, check_name="terraform_validate_final")
            if has_errors:
                gap["needs_human"] = True
            gaps.append(gap)

    _log.info(
        "final_validate: valid=%s errors=%d warnings=%d needs_human=%s",
        result["valid"], result["error_count"], result["warning_count"], has_errors,
    )
    if has_errors:
        _log.warning("Final validation still has errors:\n%s", errors_text)

    return FinalValidateResult(
        valid=result["valid"],
        error_count=result["error_count"],
        warning_count=result["warning_count"],
        diagnostics=result["diagnostics"],
        errors_text=errors_text,
        gaps=gaps,
        needs_human=has_errors,
    )
