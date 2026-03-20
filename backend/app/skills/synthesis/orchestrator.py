"""Migration Synthesis Orchestrator.

Reads all completed translation job artifacts for a migration and synthesizes
them into a unified, apply-ready OCI Terraform plan:

  01-networking.tf    VCN, subnets, NSGs, route tables, gateways
  02-database.tf      OCI DB / MySQL systems
  03-compute.tf       OCI Compute instances, instance pools
  04-storage.tf       OCI Block Volumes and attachments
  05-loadbalancer.tf  OCI Load Balancers
  variables.tf        Shared/deduplicated input variables
  outputs.tf          Shared/deduplicated outputs
  iam-setup.md        Step-by-step OCI IAM policy creation instructions
  migration-runbook.md  Phase-by-phase apply guide with terraform commands
  special-attention.md  Items needing manual review before applying

Uses a single Enhancement → Review → Fix loop (up to max_iterations rounds).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

import anthropic

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers shared with other orchestrators
# ---------------------------------------------------------------------------

_JSON_PREFILL = "{"


def _parse_json(response: anthropic.types.Message, prefilled: bool = False) -> dict:
    if response.stop_reason == "max_tokens":
        raise json.JSONDecodeError("Truncated response", "", 0)
    raw = response.content[0].text.strip()

    # When assistant prefilling was used, the API returns only the continuation
    # after the prefill character. Prepend it so we have valid JSON.
    if prefilled:
        raw = _JSON_PREFILL + raw

    # Unwrap code fences (```json ... ``` or ``` ... ```)
    if "```" in raw:
        parts = raw.split("```", 2)
        if len(parts) >= 3:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[4:]
            raw = inner.strip() or raw  # fallback to original if extraction empty

    # Try to narrow to the outermost JSON object
    start, end = raw.find("{"), raw.rfind("}") + 1
    candidate = raw[start:end] if (start != -1 and end > start) else raw

    # 1. Standard parse
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 2. Lenient parse — allows literal newlines/control chars inside strings
    try:
        return json.loads(candidate, strict=False)
    except json.JSONDecodeError:
        pass

    # 3. json_repair — handles unescaped quotes in HCL, truncated values, etc.
    #    Also works when no { } was found at all (candidate == raw full text).
    from json_repair import repair_json
    repaired = repair_json(candidate, return_objects=True)
    if isinstance(repaired, dict) and repaired:
        return repaired
    # json_repair gave up or returned empty — propagate failure
    _log.error(
        "_parse_json: could not extract JSON from response "
        "(stop_reason=%s, first 500 chars): %s",
        response.stop_reason,
        (response.content[0].text if response.content else "")[:500],
    )
    raise json.JSONDecodeError("No JSON object found", raw, 0)


def _usage(response: anthropic.types.Message) -> dict:
    u = response.usage
    return {
        "tokens_input":       u.input_tokens,
        "tokens_output":      u.output_tokens,
        "tokens_cache_read":  u.cache_read_input_tokens or 0,
        "tokens_cache_write": u.cache_creation_input_tokens or 0,
    }


def _cost(model: str, tokens_input: int, tokens_output: int,
          tokens_cache_read: int, tokens_cache_write: int) -> float:
    try:
        from app.skills.shared.agent_logger import calculate_cost
        return calculate_cost(model, tokens_input=tokens_input,
                              tokens_output=tokens_output,
                              tokens_cache_read=tokens_cache_read,
                              tokens_cache_write=tokens_cache_write)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

ENHANCEMENT_SYSTEM = """\
You are an OCI migration architect synthesizing multiple translated Terraform files \
into a single, production-ready migration plan.

INPUT: JSON containing "migration_name" and "jobs" — each job has a "skill_type" \
and "artifacts" dict of filename→content for already-translated OCI Terraform.

YOUR TASK:
1. Combine all Terraform into numbered files by apply order:
   - networking_tf  : VCN, subnets, NSGs, route tables, internet/NAT gateways
   - database_tf    : OCI DB systems, MySQL systems (empty string if none)
   - compute_tf     : OCI Compute instances, instance pools, autoscaling (empty if none)
   - storage_tf     : OCI block volumes and attachments (empty if none)
   - loadbalancer_tf: OCI load balancers, backend sets, listeners (empty if none)
   - variables_tf   : ALL input variables from all files, DEDUPLICATED. Merge \
common ones (compartment_id, region, availability_domain, etc.) into a single declaration.
   - outputs_tf     : ALL outputs from all files, DEDUPLICATED.

2. Resolve cross-file references:
   - Compute/storage/LB that reference subnet_id or vcn_id should use \
var.<name> or data source lookups consistent with networking_tf outputs.
   - Keep resource logical names consistent across files.

3. Write iam_setup_md: OCI IAM is applied separately from Terraform.
   Collect all IAM requirements implied by the resources and write clear \
step-by-step instructions for creating the needed policies in the OCI Console \
or via OCI CLI. Include exact policy statement syntax.

4. Write migration_runbook_md: Phase-by-phase apply guide with exact commands:
   Phase 1 — Networking: terraform init && terraform apply -target=...
   Phase 2 — Database: ...
   etc.
   Include: pre-requisites, variable file setup, plan/apply commands, \
expected outputs to note for the next phase.

5. Write special_attention_md: Flag ALL of the following found in the source \
translations:
   - Resources that couldn't be fully translated (placeholder comments)
   - AWS services with no direct OCI equivalent (manual workaround needed)
   - Data migration steps (RDS → OCI DB, EBS snapshots → Block Volume backups)
   - Licensing differences (BYOL vs OCI licensing)
   - DNS cutover requirements
   - Security rules with 0.0.0.0/0 on sensitive ports
   - kms_key_id / encryption gaps flagged by individual translations
   - Any TODO or FIXME comments in the source Terraform
   - Every issue, warning, or note flagged in the input .md reports from each skill

6. Write synthesis_summary_md: A COMPREHENSIVE human-readable summary of this entire \
migration. This is the single document a migration engineer reads first. Include:

   ## Overview
   One paragraph: what is being migrated, how many resources, confidence level, and \
overall recommendation.

   ## Migration Phases
   For each phase in the runbook, a subsection with:
   - What resources are created in this phase
   - Which .tf file to apply
   - Pre-requisites for this phase
   - Expected outputs to capture (IDs, endpoints) for use in later phases
   - Any risks specific to this phase

   ## Critical Attention Items
   Numbered list of ALL items from special_attention_md that require action \
BEFORE applying Terraform. Group by category: Security, Data Migration, \
Manual Steps, Unsupported Services.

   ## Per-Skill Translation Notes
   For each input skill job, a subsection summarizing:
   - What was translated (resource count, types)
   - Confidence and any issues the translator flagged
   - Anything that needs manual review specific to that skill
   Pull ALL of this from the input .md report files for each skill.

   ## Pre-Apply Checklist
   A markdown checklist (- [ ] items) of every step that must be completed \
before running terraform apply, including: OCI tenancy setup, compartment \
creation, IAM policies (reference iam-setup.md), variable file population, \
and any data migration prerequisites.

   ## Apply Order
   Numbered list of .tf files in apply order with a one-line description of \
what each file creates.

RULES:
- If a tf section is not needed (no resources of that type), use empty string "".
- Do NOT invent resources that were not in the input translations.
- Preserve all resource attribute values from the source translations exactly.
- synthesis_summary_md must be thorough — it is the primary document engineers use.
  Do NOT write a brief summary. Pull ALL relevant details from the input .md reports.
- Return ONLY a JSON object with these exact keys (string values):
  networking_tf, database_tf, compute_tf, storage_tf, loadbalancer_tf,
  variables_tf, outputs_tf, iam_setup_md, migration_runbook_md, special_attention_md,
  synthesis_summary_md
"""

REVIEW_SYSTEM = """\
You are an OCI Terraform expert reviewing a synthesized migration plan.

Review the following and score issues by severity (CRITICAL, HIGH, MEDIUM, LOW):

CRITICAL:
- Resources from the input jobs are missing from the output tf files
- Duplicate resource declarations (same resource type + name in multiple files)
- Variable used but not declared in variables_tf
- Apply order violations (compute referencing a subnet not defined in networking_tf)

HIGH:
- Cross-file reference inconsistencies (output name mismatch)
- IAM setup missing required policies for resources present
- Migration runbook missing a phase

MEDIUM:
- Variables declared but never used
- Output values referencing non-existent resources

LOW:
- Minor formatting or naming issues

Return JSON:
{
  "decision": "APPROVED" | "APPROVED_WITH_NOTES" | "NEEDS_FIXES",
  "confidence": <0.0-1.0>,
  "architectural_mismatch": false,
  "issues": [
    {"severity": "HIGH", "description": "..."}
  ]
}
"""

FIX_SYSTEM = """\
You are an OCI migration architect fixing issues in a synthesized migration plan.

You will receive the current synthesis output and a list of CRITICAL and HIGH \
severity issues. Fix ONLY those issues. Do not change anything that is not broken.

Return the corrected synthesis as the same JSON object:
  networking_tf, database_tf, compute_tf, storage_tf, loadbalancer_tf,
  variables_tf, outputs_tf, iam_setup_md, migration_runbook_md, special_attention_md,
  synthesis_summary_md

Include a "fixes_applied" key listing what you changed (for logging).
"""

ENHANCEMENT_MODEL = "claude-opus-4-6"
REVIEW_MODEL = "claude-sonnet-4-6"
FIX_MODEL = "claude-opus-4-6"


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_enhancement_prompt(input_data: dict, current: Optional[dict],
                               issues: list) -> str:
    jobs = input_data.get("jobs", [])
    migration_name = input_data.get("migration_name", "Migration")

    parts = [f"Synthesize the OCI migration plan for: **{migration_name}**\n\n"]

    if issues:
        parts.append("## Issues to address in this pass\n")
        for issue in issues:
            parts.append(f"- [{issue.get('severity')}] {issue.get('description')}\n")
        parts.append("\n")

    parts.append("## Translated artifacts per skill\n\n")
    for job in jobs:
        skill = job.get("skill_type", "unknown")
        artifacts = job.get("artifacts", {})
        tf_files = {k: v for k, v in artifacts.items() if k.endswith(".tf")}
        md_files = {k: v for k, v in artifacts.items() if k.endswith(".md")}

        if not tf_files and not md_files:
            continue

        parts.append(f"### {skill}\n\n")
        for fname, content in sorted(tf_files.items()):
            if content and content.strip():
                parts.append(f"**{fname}**\n```hcl\n{content}\n```\n\n")
        for fname, content in sorted(md_files.items()):
            if content and content.strip():
                parts.append(f"**{fname}** (reference)\n{content}\n\n")

    if current:
        parts.append("## Current synthesis (improve this)\n\n")
        for key, val in current.items():
            if key != "fixes_applied" and val:
                parts.append(f"**{key}**:\n```\n{val}\n```\n\n")

    parts.append(
        "\nReturn ONLY the JSON object with keys: "
        "networking_tf, database_tf, compute_tf, storage_tf, loadbalancer_tf, "
        "variables_tf, outputs_tf, iam_setup_md, migration_runbook_md, special_attention_md, "
        "synthesis_summary_md"
    )
    return "".join(parts)


def _build_review_prompt(input_data: dict, synthesis: dict) -> str:
    jobs = input_data.get("jobs", [])
    skill_types = [j.get("skill_type") for j in jobs]
    parts = [
        f"Review this synthesized OCI migration plan.\n",
        f"Source skills: {', '.join(skill_types)}\n\n",
    ]
    for key, val in synthesis.items():
        if key != "fixes_applied" and val:
            parts.append(f"**{key}**:\n```\n{val}\n```\n\n")
    parts.append("\nReturn the review JSON with decision, confidence, and issues.")
    return "".join(parts)


def _build_fix_prompt(input_data: dict, synthesis: dict, issues: list) -> str:
    parts = ["Fix ONLY the following CRITICAL and HIGH issues:\n\n"]
    for issue in issues:
        parts.append(f"- [{issue.get('severity')}] {issue.get('description')}\n")
    parts.append("\n## Current synthesis\n\n")
    for key, val in synthesis.items():
        if key != "fixes_applied" and val:
            parts.append(f"**{key}**:\n```\n{val}\n```\n\n")
    parts.append("\nReturn the corrected JSON (all keys) plus fixes_applied list.")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------

def _decide(review: dict) -> tuple[str, float]:
    confidence = float(review.get("confidence", 0.5))
    issues = review.get("issues", [])
    critical = [i for i in issues if i.get("severity") == "CRITICAL"]
    high = [i for i in issues if i.get("severity") == "HIGH"]

    if critical or high or confidence < 0.65:
        return "NEEDS_FIXES", confidence
    if confidence >= 0.85:
        return "APPROVED", confidence
    return "APPROVED_WITH_NOTES", confidence


# ---------------------------------------------------------------------------
# Artifact assembly
# ---------------------------------------------------------------------------

_TF_FILE_MAP = {
    "networking_tf":     "01-networking.tf",
    "database_tf":       "02-database.tf",
    "compute_tf":        "03-compute.tf",
    "storage_tf":        "04-storage.tf",
    "loadbalancer_tf":   "05-loadbalancer.tf",
    "variables_tf":      "variables.tf",
    "outputs_tf":        "outputs.tf",
}

_MD_FILE_MAP = {
    "iam_setup_md":          "iam-setup.md",
    "migration_runbook_md":  "migration-runbook.md",
    "special_attention_md":  "special-attention.md",
    "synthesis_summary_md":  "synthesis-summary.md",
}


def _build_artifacts(synthesis: dict, confidence: float, decision: str,
                     iterations: int) -> dict:
    artifacts = {}
    for key, fname in _TF_FILE_MAP.items():
        content = synthesis.get(key, "")
        if content and content.strip():
            artifacts[fname] = content

    for key, fname in _MD_FILE_MAP.items():
        content = synthesis.get(key, "")
        if content and content.strip():
            artifacts[fname] = content

    # If the LLM didn't produce a synthesis summary, generate a minimal fallback
    if "synthesis-summary.md" not in artifacts:
        tf_apply_order = [
            f for f in ["01-networking.tf", "02-database.tf", "03-compute.tf",
                        "04-storage.tf", "05-loadbalancer.tf"]
            if f in artifacts
        ]
        artifacts["synthesis-summary.md"] = (
            f"# Migration Synthesis Summary\n\n"
            f"**Decision:** {decision}  \n"
            f"**Confidence:** {confidence:.0%}  \n"
            f"**Iterations:** {iterations}  \n\n"
            f"## Apply order\n\n"
            + "".join(f"{i+1}. `{f}`\n" for i, f in enumerate(tf_apply_order))
            + "\n> Apply each file separately using `terraform apply` in the order "
            "listed above.\n"
            + "> Initialize once with `terraform init` in a directory containing "
            "all files.\n"
        )
    return artifacts


# ---------------------------------------------------------------------------
# Main run() entry point
# ---------------------------------------------------------------------------

def run(
    input_content: str,
    progress_callback,
    anthropic_client,
    max_iterations: int = 3,
) -> dict:
    """Synthesize all completed translation job artifacts into a unified plan.

    Args:
        input_content: JSON string with keys migration_id, migration_name, jobs
        progress_callback: Called with (phase, iteration, confidence, decision)
        anthropic_client: Pre-configured Anthropic (or AgentSDKClient) client
        max_iterations: Max Enhancement→Review→Fix iterations

    Returns:
        dict with keys: artifacts, confidence, decision, iterations, cost, interactions
    """
    # Input guardrail
    try:
        from app.gateway.model_gateway import guard_input
        input_content = guard_input(input_content, "migration_synthesis")
    except ImportError:
        pass

    try:
        input_data = json.loads(input_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"input_content must be valid JSON: {e}")

    jobs = input_data.get("jobs", [])
    if not jobs:
        raise ValueError("No completed translation jobs found in synthesis input")

    _log.info("Starting migration synthesis for '%s' with %d job(s)",
              input_data.get("migration_name"), len(jobs))

    interaction_records: list[dict] = []
    total_cost = 0.0
    current_synthesis: Optional[dict] = None
    current_issues: list = []
    final_decision = "NEEDS_FIXES"
    final_confidence = 0.0
    iteration = 0

    progress_callback("gap_analysis", 0, 0.0, None)

    for iteration in range(1, max_iterations + 1):
        progress_callback("enhancement", iteration, final_confidence, None)

        # Enhancement
        user_msg = _build_enhancement_prompt(input_data, current_synthesis, current_issues)
        synthesis = None
        enh_resp = None
        enh_dur = 0.0
        for attempt in range(3):
            try:
                t0 = time.perf_counter()
                with anthropic_client.messages.stream(
                    model=ENHANCEMENT_MODEL,
                    max_tokens=32768,
                    system=[{"type": "text", "text": ENHANCEMENT_SYSTEM}],
                    messages=[
                        {"role": "user", "content": user_msg},
                        {"role": "assistant", "content": _JSON_PREFILL},
                    ],
                ) as stream:
                    enh_resp = stream.get_final_message()
                enh_dur = time.perf_counter() - t0

                raw = enh_resp.content[0].text if enh_resp.content else ""
                _log.info(
                    "Enhancement attempt %d/%d: stop_reason=%s output_tokens=%s first200=%r",
                    attempt + 1, 3,
                    enh_resp.stop_reason,
                    enh_resp.usage.output_tokens if enh_resp.usage else "?",
                    raw[:200],
                )
                try:
                    from app.gateway.model_gateway import guard_output
                    guard_output(raw, "migration_synthesis")
                except ImportError:
                    pass

                synthesis = _parse_json(enh_resp, prefilled=True)
                break
            except json.JSONDecodeError as e:
                _log.warning("Enhancement attempt %d failed to parse JSON: %s", attempt + 1, e)
                if attempt == 2:
                    raise RuntimeError(f"Enhancement failed after 3 attempts: {e}")

        if synthesis is None:
            raise RuntimeError("Enhancement returned no result")

        enh_use = _usage(enh_resp)
        enh_cost = _cost(ENHANCEMENT_MODEL, **enh_use)
        total_cost += enh_cost
        interaction_records.append({
            "agent_type": "enhancement", "model": ENHANCEMENT_MODEL,
            "iteration": iteration,
            **enh_use,
            "cost_usd": enh_cost, "duration_seconds": enh_dur,
        })
        current_synthesis = synthesis

        # Review
        progress_callback("review", iteration, final_confidence, None)
        review = None
        for attempt in range(3):
            try:
                t0 = time.perf_counter()
                rev_resp = anthropic_client.messages.create(
                    model=REVIEW_MODEL,
                    max_tokens=4096,
                    system=[{"type": "text", "text": REVIEW_SYSTEM}],
                    messages=[
                        {"role": "user", "content": _build_review_prompt(input_data, synthesis)},
                        {"role": "assistant", "content": _JSON_PREFILL},
                    ],
                )
                rev_dur = time.perf_counter() - t0
                review = _parse_json(rev_resp, prefilled=True)
                break
            except json.JSONDecodeError as e:
                if attempt == 2:
                    raise RuntimeError(f"Review failed after 3 attempts: {e}")

        if review is None:
            raise RuntimeError("Review returned no result")

        decision, confidence = _decide(review)
        final_decision = decision
        final_confidence = confidence

        rev_use = _usage(rev_resp)
        rev_cost = _cost(REVIEW_MODEL, **rev_use)
        total_cost += rev_cost
        interaction_records.append({
            "agent_type": "review", "model": REVIEW_MODEL,
            "iteration": iteration,
            **rev_use,
            "cost_usd": rev_cost, "duration_seconds": rev_dur,
            "decision": decision, "confidence": confidence,
            "issues": [{"severity": i.get("severity"), "description": i.get("description")}
                       for i in review.get("issues", [])],
        })
        progress_callback("review", iteration, confidence, decision)
        _log.info("Synthesis iteration %d: %s (confidence=%.2f)", iteration, decision, confidence)

        if decision in ("APPROVED", "APPROVED_WITH_NOTES"):
            break

        if iteration == max_iterations:
            break

        # Fix
        progress_callback("fix", iteration, confidence, None)
        high_issues = [i for i in review.get("issues", [])
                       if i.get("severity") in ("CRITICAL", "HIGH")]
        fix_targets = high_issues or review.get("issues", [])

        fixed = None
        for attempt in range(3):
            try:
                t0 = time.perf_counter()
                with anthropic_client.messages.stream(
                    model=FIX_MODEL,
                    max_tokens=32768,
                    system=[{"type": "text", "text": FIX_SYSTEM}],
                    messages=[
                        {"role": "user", "content": _build_fix_prompt(input_data, synthesis, fix_targets)},
                        {"role": "assistant", "content": _JSON_PREFILL},
                    ],
                ) as stream:
                    fix_resp = stream.get_final_message()
                fix_dur = time.perf_counter() - t0
                fixed = _parse_json(fix_resp, prefilled=True)
                break
            except json.JSONDecodeError as e:
                if attempt == 2:
                    break

        if fixed:
            fixed.pop("fixes_applied", None)
            current_synthesis = fixed

        fix_use = _usage(fix_resp) if fixed else {"tokens_input": 0, "tokens_output": 0, "tokens_cache_read": 0, "tokens_cache_write": 0}
        fix_cost = _cost(FIX_MODEL, **fix_use) if fixed else 0.0
        total_cost += fix_cost
        interaction_records.append({
            "agent_type": "fix", "model": FIX_MODEL,
            "iteration": iteration,
            **fix_use,
            "cost_usd": fix_cost, "duration_seconds": fix_dur if fixed else 0.0,
        })
        current_issues = high_issues

    artifacts = _build_artifacts(current_synthesis or {}, final_confidence,
                                 final_decision, iteration)

    return {
        "artifacts":    artifacts,
        "confidence":   final_confidence,
        "decision":     final_decision,
        "iterations":   iteration,
        "cost":         total_cost,
        "interactions": interaction_records,
    }
