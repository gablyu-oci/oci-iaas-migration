#!/usr/bin/env python3
"""
CloudFormation -> OCI Terraform Orchestrator -- backend-adapted version.

Runs the enhancement -> review -> fix agent loop and returns results as dicts
instead of writing files. Accepts an Anthropic client from the caller.
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime

import anthropic
import yaml

# ── Path setup ────────────────────────────────────────────────────────────────
SKILLS_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(SKILLS_ROOT / "shared"))

from agent_logger import (
    AgentLogger, AgentType, ReviewDecision, ConfidenceCalculator, calculate_cost
)

# ── Model config ──────────────────────────────────────────────────────────────
ENHANCEMENT_MODEL = "claude-opus-4-6"
REVIEW_MODEL      = "claude-sonnet-4-6"
FIX_MODEL         = "claude-opus-4-6"

# ── Paths ─────────────────────────────────────────────────────────────────────
WORKFLOWS_DIR = SKILLS_ROOT / "cfn_terraform" / "workflows"


# ── JSON extraction ───────────────────────────────────────────────────────────

def _parse_json_response(response: anthropic.types.Message) -> dict:
    """
    Robustly extract a JSON object from an API response.

    Handles:
    - stop_reason=max_tokens (truncated output)
    - Markdown code fences (```json ... ```)
    - Preamble/postamble text around the JSON object
    """
    if response.stop_reason == "max_tokens":
        raise json.JSONDecodeError(
            "Response truncated (stop_reason=max_tokens) -- retry needed", "", 0
        )

    raw = response.content[0].text.strip()

    # Strip code fences if present
    if "```" in raw:
        inner = raw.split("```", 2)
        if len(inner) >= 3:
            raw = inner[1]
            if raw.startswith("json"):
                raw = raw[4:]
        else:
            raw = inner[-1]

    # Extract outermost JSON object
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found in response", raw, 0)
    raw = raw[start:end]

    return json.loads(raw)


# ── Token extraction ──────────────────────────────────────────────────────────

def extract_usage(response: anthropic.types.Message) -> dict:
    """Extract all token fields from a real API response. Never estimated."""
    u = response.usage
    return {
        "tokens_input":        u.input_tokens,
        "tokens_output":       u.output_tokens,
        "tokens_cache_read":   u.cache_read_input_tokens  or 0,
        "tokens_cache_write":  u.cache_creation_input_tokens or 0,
    }


# ── Workflow rules loading ─────────────────────────────────────────────────────

def load_workflow_rules() -> str:
    """Load the CFN conversion rules for use in prompts."""
    rules_path = WORKFLOWS_DIR / "conversion-rules.md"
    if rules_path.exists():
        return rules_path.read_text(encoding="utf-8")
    return "[conversion-rules.md not found]"


# ── System prompts ────────────────────────────────────────────────────────────

ENHANCEMENT_SYSTEM = """\
You are an expert AWS CloudFormation to OCI Terraform translator.
Convert the provided CloudFormation template to production-ready OCI Terraform HCL.

Rules:
- Use only valid OCI Terraform provider resources (hashicorp/oci)
- Map each CloudFormation resource to its OCI equivalent
- Never use AWS resource types in the output
- Use variables for all OCIDs, region, and environment-specific values
- Add freeform_tags to all resources
- Output ONLY a JSON object with this schema:
{
  "main_tf": "complete HCL content for main.tf / resource.tf",
  "variables_tf": "HCL content for variables.tf",
  "outputs_tf": "HCL content for outputs.tf",
  "tfvars_example": "terraform.tfvars.example content",
  "resource_count": 12,
  "resource_mappings": [
    {"cfn_type": "AWS::S3::Bucket", "cfn_name": "MyBucket", "oci_type": "oci_objectstorage_bucket", "oci_name": "my_bucket", "notes": ""}
  ],
  "gaps": [
    {"gap": "Description", "severity": "CRITICAL|HIGH|MEDIUM|LOW", "mitigation": "How to address"}
  ],
  "migration_prerequisites": ["Create compartment", "..."],
  "architecture_notes": "Brief description of the OCI architecture"
}
"""

REVIEW_SYSTEM = """\
You are an expert OCI Terraform reviewer with deep knowledge of both AWS CloudFormation and OCI Terraform.
Review an AWS CloudFormation -> OCI Terraform translation for correctness.

Severity rules (STRICT):
  CRITICAL -- Wrong OCI resource type, invalid HCL syntax, resource will fail terraform validate
  HIGH     -- Missing required fields, wrong property mapping, architectural mismatch
  MEDIUM   -- Scope issue, suboptimal configuration, missing best practices
  LOW      -- Style, naming, non-blocking improvements

Return ONLY a JSON object:
{
  "decision": "APPROVED|APPROVED_WITH_NOTES|NEEDS_FIXES|REJECTED",
  "confidence_override": null,
  "architectural_mismatch": false,
  "issues": [
    {
      "id": 1,
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "category": "resource_mapping|property_translation|completeness|syntax|security|networking|iam|monitoring",
      "resource": "oci_resource_type.resource_name",
      "description": "Specific problem description",
      "recommendation": "How to fix"
    }
  ],
  "approved_notes": "",
  "review_summary": "2-3 sentence overall assessment"
}
"""

FIX_SYSTEM = """\
You are an OCI Terraform expert. Fix specific issues in a CloudFormation->Terraform translation.
Target ONLY the issues listed. Do not change correct resources.

Output ONLY a JSON object with the same schema as the enhancement output, plus:
{
  "main_tf": "complete fixed HCL content for main.tf",
  "variables_tf": "HCL content for variables.tf",
  "outputs_tf": "HCL content for outputs.tf",
  "tfvars_example": "terraform.tfvars.example content",
  "resource_count": 12,
  "resource_mappings": [...],
  "gaps": [...],
  "migration_prerequisites": [...],
  "architecture_notes": "...",
  "fixes_applied": ["Fixed resource type for DB", "Added NSG rules", ...]
}
"""


# ── Confidence calculation ─────────────────────────────────────────────────────

def make_decision_from_review(review: dict, gap_analysis: dict) -> tuple[ReviewDecision, float]:
    """
    Deterministic decision from:
    - resource_count / mapped_count from gap_analysis
    - issue list from reviewer (categorized by strict rules)
    """
    issues        = review.get("issues", [])
    total         = gap_analysis.get("total_resources", 1)
    critical_cnt  = sum(1 for i in issues if i.get("severity") == "CRITICAL")
    mapped_count  = max(0, total - critical_cnt)

    confidence = ConfidenceCalculator.calculate(
        total_items=total,
        mapped_count=mapped_count,
        issues=issues,
        architectural_mismatch=review.get("architectural_mismatch", False),
    )
    decision = ConfidenceCalculator.make_decision(confidence, issues)
    return decision, confidence


# ── Agent calls ───────────────────────────────────────────────────────────────

def call_enhancement(
    client: anthropic.Anthropic,
    template_text: str,
    current_translation: dict | None,
    issues: list,
    workflow_rules: str,
) -> tuple[dict, dict]:
    """Call enhancement agent. Returns (translation_dict, usage_dict)."""

    prev = json.dumps(current_translation, indent=2) if current_translation else "None -- this is the initial translation."
    issues_text = json.dumps(issues, indent=2) if issues else "None"

    start = time.perf_counter()
    with client.messages.stream(
        model=ENHANCEMENT_MODEL,
        max_tokens=32768,
        system=[
            {"type": "text", "text": ENHANCEMENT_SYSTEM},
            {"type": "text", "text": f"## CloudFormation to OCI Conversion Rules\n\n{workflow_rules}",
             "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{
            "role": "user",
            "content": (
                f"## CloudFormation Template\n```yaml\n{template_text}\n```\n\n"
                f"## Current Translation\n```json\n{prev}\n```\n\n"
                f"## Issues to Fix\n```json\n{issues_text}\n```\n\n"
                "Produce the complete OCI Terraform translation as a JSON object."
            )
        }],
    ) as stream:
        response = stream.get_final_message()
    duration = time.perf_counter() - start

    translation = _parse_json_response(response)

    usage = extract_usage(response)
    usage["duration"] = duration
    usage["model"] = ENHANCEMENT_MODEL
    usage["cost"] = calculate_cost(ENHANCEMENT_MODEL, **{k: usage[k] for k in
                                    ["tokens_input", "tokens_output",
                                     "tokens_cache_read", "tokens_cache_write"]})
    return translation, usage


def call_review(
    client: anthropic.Anthropic,
    template_text: str,
    translation: dict,
) -> tuple[dict, dict]:
    """Call review agent. Returns (review_dict, usage_dict)."""

    # Summarize translation for review (omit raw HCL to keep context manageable)
    review_summary = {
        "resource_count": translation.get("resource_count", 0),
        "resource_mappings": translation.get("resource_mappings", []),
        "gaps": translation.get("gaps", []),
        "migration_prerequisites": translation.get("migration_prerequisites", []),
        "architecture_notes": translation.get("architecture_notes", ""),
        "main_tf_excerpt": translation.get("main_tf", "")[:4000],
    }

    start = time.perf_counter()
    response = client.messages.create(
        model=REVIEW_MODEL,
        max_tokens=4096,
        system=[
            {"type": "text", "text": REVIEW_SYSTEM},
        ],
        messages=[{
            "role": "user",
            "content": (
                f"## CloudFormation Template\n```yaml\n{template_text[:3000]}\n```\n\n"
                f"## OCI Terraform Translation to Review\n```json\n{json.dumps(review_summary, indent=2)}\n```\n\n"
                "Review this translation according to your checklist and return a JSON object."
            )
        }],
    )
    duration = time.perf_counter() - start

    review = _parse_json_response(response)

    usage = extract_usage(response)
    usage["duration"] = duration
    usage["model"] = REVIEW_MODEL
    usage["cost"] = calculate_cost(REVIEW_MODEL, **{k: usage[k] for k in
                                    ["tokens_input", "tokens_output",
                                     "tokens_cache_read", "tokens_cache_write"]})
    return review, usage


def call_fix(
    client: anthropic.Anthropic,
    template_text: str,
    translation: dict,
    issues: list,
    workflow_rules: str,
) -> tuple[dict, dict]:
    """Call fix agent. Returns (fixed_translation_dict, usage_dict)."""

    start = time.perf_counter()
    with client.messages.stream(
        model=FIX_MODEL,
        max_tokens=32768,
        system=[
            {"type": "text", "text": FIX_SYSTEM},
            {"type": "text", "text": f"## CloudFormation to OCI Conversion Rules\n\n{workflow_rules}",
             "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{
            "role": "user",
            "content": (
                f"## CloudFormation Template\n```yaml\n{template_text}\n```\n\n"
                f"## Current OCI Terraform Translation\n```json\n{json.dumps(translation, indent=2)}\n```\n\n"
                f"## Issues to Fix\n```json\n{json.dumps(issues, indent=2)}\n```\n\n"
                "Fix ONLY the listed issues. Return the complete updated translation as a JSON object."
            )
        }],
    ) as stream:
        response = stream.get_final_message()
    duration = time.perf_counter() - start

    fixed = _parse_json_response(response)

    usage = extract_usage(response)
    usage["duration"] = duration
    usage["model"] = FIX_MODEL
    usage["cost"] = calculate_cost(FIX_MODEL, **{k: usage[k] for k in
                                    ["tokens_input", "tokens_output",
                                     "tokens_cache_read", "tokens_cache_write"]})
    return fixed, usage


# ── Deterministic gap analysis ────────────────────────────────────────────────

def run_gap_analysis_from_text(template_text: str) -> dict:
    """
    Run a lightweight gap analysis directly from template text (no subprocess).
    Returns structured dict with resource metrics for ConfidenceCalculator.
    """
    try:
        tmpl = yaml.safe_load(template_text)
        resources_section = tmpl.get("Resources", {}) if isinstance(tmpl, dict) else {}
        total_resources = len(resources_section)

        detected_types = sorted({
            v.get("Type", "") for v in resources_section.values()
            if isinstance(v, dict) and v.get("Type", "").startswith("AWS::")
        })

        container_target = "NONE"
        if any("ECS" in t or "Fargate" in t for t in detected_types):
            container_target = "CONTAINER_INSTANCES"
        if any("EKS" in t for t in detected_types):
            container_target = "OKE"

        # Estimate: most resources can be mapped
        mapped_resources = max(0, total_resources - 1)  # conservative

    except Exception:
        total_resources = 1
        detected_types = []
        mapped_resources = 0
        container_target = "NONE"

    return {
        "total_resources": total_resources,
        "mapped_resources": mapped_resources,
        "detected_resource_types": detected_types,
        "container_target": container_target,
    }


# ── Artifact builder ──────────────────────────────────────────────────────────

def build_artifact_dict(translation: dict, summary: dict | None = None) -> dict:
    """
    Build a dict of filename -> content strings from the translation result.
    """
    artifacts = {}
    artifacts["main.tf"] = translation.get("main_tf", "# main.tf\n")
    artifacts["variables.tf"] = translation.get("variables_tf", "# variables.tf\n")
    artifacts["outputs.tf"] = translation.get("outputs_tf", "# outputs.tf\n")
    artifacts["terraform.tfvars.example"] = translation.get("tfvars_example", "# terraform.tfvars.example\n")
    if summary:
        artifacts["summary.json"] = json.dumps(summary, indent=2)
    return artifacts


# ── Main orchestration ────────────────────────────────────────────────────────

def run(
    input_content: str,
    progress_callback,
    anthropic_client: anthropic.Anthropic,
    max_iterations: int = 3,
) -> dict:
    """
    Full CFN->OCI Terraform orchestration.

    Args:
        input_content: CloudFormation template (YAML or JSON string)
        progress_callback: Called with (phase, iteration, confidence, decision)
        anthropic_client: Pre-configured Anthropic client
        max_iterations: Max enhancement/review/fix iterations

    Returns:
        dict with keys: artifacts, confidence, decision, iterations, cost, interactions
    """
    # 1. Parse input
    template_text = input_content

    # 2. Run gap analysis
    progress_callback("gap_analysis", 0, 0.0, None)
    gap_analysis = run_gap_analysis_from_text(template_text)

    # 3. Init logger
    logger = AgentLogger(project_type="cfn", source_file="api-input")
    logger.start_session()
    session_start = time.perf_counter()

    logger.log_agent_call(
        iteration=0,
        agent_type=AgentType.TRANSLATOR,
        input_summary="CloudFormation template via API",
        output_summary=(
            f"Gap analysis: {gap_analysis['total_resources']} resources detected, "
            f"{len(gap_analysis['detected_resource_types'])} types"
        ),
        duration_seconds=time.perf_counter() - session_start,
        metadata=gap_analysis,
    )

    # 4. Load stable context
    workflow_rules = load_workflow_rules()

    # 5. Enhancement -> Review -> Fix loop
    client = anthropic_client
    current_translation: dict | None = None
    current_issues: list = []
    final_decision = ReviewDecision.NEEDS_FIXES
    final_confidence = 0.0
    last_review: dict = {}
    interaction_records: list = []
    iteration = 0

    for iteration in range(1, max_iterations + 1):
        progress_callback("enhancement", iteration, final_confidence, None)

        # Enhancement (retry up to 3 times)
        translation = None
        for _attempt in range(3):
            try:
                translation, enh_usage = call_enhancement(
                    client, template_text, current_translation, current_issues,
                    workflow_rules
                )
                break
            except json.JSONDecodeError as e:
                if _attempt == 2:
                    raise RuntimeError(f"Enhancement agent failed after 3 attempts: {e}")
        if translation is None:
            raise RuntimeError("Enhancement agent returned no result")

        logger.log_agent_call(
            iteration=iteration,
            agent_type=AgentType.ENHANCEMENT,
            input_summary=f"Translate CloudFormation, fix {len(current_issues)} issues",
            output_summary=f"Generated {translation.get('resource_count', 0)} OCI resources",
            duration_seconds=enh_usage["duration"],
            model=enh_usage["model"],
            tokens_input=enh_usage["tokens_input"],
            tokens_output=enh_usage["tokens_output"],
            tokens_cache_read=enh_usage["tokens_cache_read"],
            tokens_cache_write=enh_usage["tokens_cache_write"],
            cost_usd=enh_usage["cost"],
        )
        interaction_records.append({
            "agent_type": "enhancement", "model": enh_usage["model"],
            "iteration": iteration,
            "tokens_input": enh_usage["tokens_input"],
            "tokens_output": enh_usage["tokens_output"],
            "tokens_cache_read": enh_usage["tokens_cache_read"],
            "tokens_cache_write": enh_usage["tokens_cache_write"],
            "cost_usd": enh_usage["cost"],
            "duration_seconds": enh_usage["duration"],
        })
        current_translation = translation

        # Review (retry up to 3 times)
        progress_callback("review", iteration, final_confidence, None)
        review = None
        for _attempt in range(3):
            try:
                review, rev_usage = call_review(client, template_text, translation)
                break
            except json.JSONDecodeError as e:
                if _attempt == 2:
                    raise RuntimeError(f"Review agent failed after 3 attempts: {e}")
        if review is None:
            raise RuntimeError("Review agent returned no result")

        decision, confidence = make_decision_from_review(review, gap_analysis)
        final_decision = decision
        final_confidence = confidence
        last_review = review

        issues_found = [
            f"[{i.get('severity')}] {i.get('description', '')}"
            for i in review.get("issues", [])
        ]
        logger.log_review_call(
            iteration=iteration,
            decision=decision,
            confidence=confidence,
            issues_found=issues_found,
            review_output=review,
            duration_seconds=rev_usage["duration"],
            model=rev_usage["model"],
            tokens_input=rev_usage["tokens_input"],
            tokens_output=rev_usage["tokens_output"],
            tokens_cache_read=rev_usage["tokens_cache_read"],
            tokens_cache_write=rev_usage["tokens_cache_write"],
            cost_usd=rev_usage["cost"],
        )
        interaction_records.append({
            "agent_type": "review", "model": rev_usage["model"],
            "iteration": iteration,
            "tokens_input": rev_usage["tokens_input"],
            "tokens_output": rev_usage["tokens_output"],
            "tokens_cache_read": rev_usage["tokens_cache_read"],
            "tokens_cache_write": rev_usage["tokens_cache_write"],
            "cost_usd": rev_usage["cost"],
            "duration_seconds": rev_usage["duration"],
            "decision": decision.value,
            "confidence": confidence,
            "issues": [{"severity": i.get("severity"), "description": i.get("description", "")}
                       for i in review.get("issues", [])],
        })

        progress_callback("review", iteration, confidence, decision.value)

        if decision in (ReviewDecision.APPROVED, ReviewDecision.APPROVED_WITH_NOTES):
            break

        if iteration == max_iterations:
            break

        # Fix
        progress_callback("fix", iteration, confidence, None)
        high_issues = [i for i in review.get("issues", [])
                       if i.get("severity") in ("CRITICAL", "HIGH")]
        fix_targets = high_issues or review.get("issues", [])

        fixed = None
        for _attempt in range(3):
            try:
                fixed, fix_usage = call_fix(
                    client, template_text, translation, fix_targets, workflow_rules
                )
                break
            except json.JSONDecodeError as e:
                if _attempt == 2:
                    raise RuntimeError(f"Fix agent failed after 3 attempts: {e}")
        if fixed is None:
            break

        fixes_applied = fixed.pop("fixes_applied", [])
        logger.log_fix_call(
            iteration=iteration,
            fixes_applied=fixes_applied,
            output_summary=f"Applied {len(fixes_applied)} fixes",
            duration_seconds=fix_usage["duration"],
            model=fix_usage["model"],
            tokens_input=fix_usage["tokens_input"],
            tokens_output=fix_usage["tokens_output"],
            tokens_cache_read=fix_usage["tokens_cache_read"],
            tokens_cache_write=fix_usage["tokens_cache_write"],
            cost_usd=fix_usage["cost"],
        )
        interaction_records.append({
            "agent_type": "fix", "model": fix_usage["model"],
            "iteration": iteration,
            "tokens_input": fix_usage["tokens_input"],
            "tokens_output": fix_usage["tokens_output"],
            "tokens_cache_read": fix_usage["tokens_cache_read"],
            "tokens_cache_write": fix_usage["tokens_cache_write"],
            "cost_usd": fix_usage["cost"],
            "duration_seconds": fix_usage["duration"],
        })

        current_translation = fixed
        current_issues = high_issues

    # 6. End session, get reports
    json_report, md_report = logger.end_session(final_decision, final_confidence)

    # 7. Build artifacts
    summary_data = {
        "decision": final_decision.value,
        "confidence": final_confidence,
        "iterations": iteration,
        "gap_analysis": gap_analysis,
    }
    artifacts = build_artifact_dict(current_translation or {}, summary_data)
    artifacts["report.md"] = md_report

    # Calculate total cost
    total_cost = sum(r.get("cost_usd", 0) or 0 for r in interaction_records)

    return {
        "artifacts": artifacts,
        "confidence": final_confidence,
        "decision": final_decision.value,
        "iterations": iteration,
        "cost": total_cost,
        "interactions": interaction_records,
    }
