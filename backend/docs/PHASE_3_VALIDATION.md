# Phase 3: Terraform Validation at Every Checkpoint

## Problem

- `terraform validate` only ran at the END of the pipeline (manually by operator after downloading the bundle)
- Errors from a single skill silently propagated through composer -> bundle_builder -> polish -> validator
- Hard to diagnose: a wrong NSG rule from `network_translation` gets blamed on synthesis or polish

## Solution: 3-Checkpoint Validation

### Checkpoint 1: Per-Skill Fragment Validation

- **When:** After each Phase-1/2 migrated skill renders its nodes to HCL fragments
- **Applicable skills:** `network_translation`, `ocm_handoff_translation`, `loadbalancer_translation` (STRUCTURED_OUTPUT_SKILLS)
- **How:** Creates temp dir with skill's .tf fragments + stub `providers.tf` + stub `variables.tf` (with defaults for all `var.NAME` references)
- **On failure:**
  1. Marks skill run as failed
  2. Injects HIGH gap into `reports/gaps.md` naming the skill + error message
  3. Triggers ONE retry of the skill writer with the validate error in prompt context
  4. If retry still fails, the gap survives
- **Skipped for:** Free-form HCL skills (`cfn_terraform`, `ec2_translation`, etc.) -- Phase 4 will migrate those

### Checkpoint 2: Merged Bundle Validation

- **When:** After `synthesis_composer` + `bundle_builder` produce the full `terraform/` directory
- **How:** Creates temp dir mirroring the bundle layout (`terraform/*.tf` files, excluding `terraform/ocm/`)
- **Purpose:** Catches cross-skill wiring issues (e.g., subnet ID reference from `compute.tf` to non-existent `oci_core_subnet` label)
- **On failure:** Injects HIGH gaps for each error; the existing agentic polish step then has them in its input

### Checkpoint 3: Final Output Validation

- **When:** After polish + validate-and-repair complete
- **How:** One last `terraform validate` on the bundle
- **On failure:** Marks gaps as `needs_human=true` with clear message about what failed after all automated repair attempts

## Gap Injection Contract

All validation gaps follow this schema:

```json
{
  "skill": "<source_skill_type>",
  "severity": "HIGH",
  "check": "terraform_validate",
  "description": "<human-readable error from terraform validate>",
  "recommendation": "Fix the HCL errors...",
  "needs_human": false
}
```

`needs_human` is set to `true` only at checkpoint 3, after all automated repair attempts have been exhausted.

Gaps appear in `reports/gaps.md` with the source skill named, grouped by severity.

## Graceful Degradation

- If the terraform binary is not available, all checkpoints log a warning and return `valid=True`
- This allows development/testing without terraform installed
- Detection: checks `TERRAFORM_BIN` env var, then `shutil.which("terraform")`

## Pipeline Flow

```
for each skill in skill_resources:
    run skill -> nodes/specs/free_form_files
    if skill in STRUCTURED_OUTPUT_SKILLS:
        per_skill_validate(skill_output)  # checkpoint 1: may retry once

... compose + bundle_build ...
merged_bundle_validate(out)  # checkpoint 2: injects gaps for polish

... polish + validate_and_repair ...
final_validate(out)  # checkpoint 3: last hard check
```

## Progress Log Lines

- `Per-skill validate [<skill>]: pass | fail (N errors)`
- `Merged bundle validate: pass | fail (N errors)`
- `Final validate: pass | fail (N errors)`

## Configuration

- No new config settings required
- Uses existing `SYNTHESIS_POLISH_ENABLED` and `SYNTHESIS_VALIDATE_AND_REPAIR` settings
- Terraform binary path configurable via `TERRAFORM_BIN` env var

## Files Changed

- **NEW:** `backend/app/services/per_skill_validator.py` -- validation module
- **UPDATED:** `backend/app/services/plan_orchestrator.py` -- wires in 3 checkpoints
- **NEW:** `backend/tests/test_per_skill_validator.py` -- per-skill validation tests
- **NEW:** `backend/tests/test_merged_bundle_validate.py` -- bundle validation tests
- **NEW:** `backend/docs/PHASE_3_VALIDATION.md` -- this document
