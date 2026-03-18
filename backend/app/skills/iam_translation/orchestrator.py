#!/usr/bin/env python3
"""
IAM Policy Orchestrator -- backend-adapted version.

AWS -> OCI IAM translation with real token tracking.
Runs enhancement -> review -> fix agent loop and returns results as dicts.
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime

import anthropic

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
WORKFLOWS_DIR  = SKILLS_ROOT / "iam_translation" / "workflows"
DOCS_BASE      = SKILLS_ROOT / "iam_translation" / "docs"


# ── Reference doc loading ─────────────────────────────────────────────────────

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return f"[doc not found: {path.name}]"


def load_core_oci_docs() -> str:
    """
    Load the most important OCI reference docs into a single string.
    This block is passed with cache_control so iterations 2+ read from cache.
    """
    paths = [
        DOCS_BASE / "oci-reference" / "permissions" / "20260306T012058Z__docs-oracle-com__verbs.md",
        DOCS_BASE / "oci-reference" / "permissions" / "20260306T012134Z__docs-oracle-com__resources.md",
        DOCS_BASE / "oci-reference" / "policies"    / "20260306T012045Z__docs-oracle-com__policy-syntax.md",
        DOCS_BASE / "oci-reference" / "policies"    / "20260306T012044Z__docs-oracle-com__how-policies-work.md",
        DOCS_BASE / "oci-reference" / "conditions"  / "20260306T012135Z__docs-oracle-com__conditions.md",
    ]
    parts = []
    for p in paths:
        if p.exists():
            parts.append(f"=== {p.name} ===\n{p.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def load_service_docs(services: list[str]) -> str:
    """Load service-specific OCI permission docs based on detected AWS services."""
    service_doc_map = {
        "ec2":    DOCS_BASE / "oci-reference" / "permissions" / "20260306T012137Z__docs-oracle-com__details-for-the-core-services.md",
        "vpc":    DOCS_BASE / "oci-reference" / "permissions" / "20260306T012137Z__docs-oracle-com__details-for-the-core-services.md",
        "s3":     DOCS_BASE / "oci-reference" / "permissions" / "20260306T012148Z__docs-oracle-com__details-for-object-storage-and-archive-storage.md",
        "iam":    DOCS_BASE / "oci-reference" / "permissions" / "20260306T012059Z__docs-oracle-com__details-for-iam-without-identity-domains.md",
    }
    seen = set()
    parts = []
    for svc in services:
        p = service_doc_map.get(svc.lower())
        if p and p not in seen and p.exists():
            seen.add(p)
            parts.append(f"=== {p.name} ===\n{p.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def load_workflow_rules() -> str:
    """Load translation rules, verb mappings, and condition mappings."""
    rules_file = WORKFLOWS_DIR / "translation-rules.md"
    verbs_file = WORKFLOWS_DIR / "action-verb-mappings.md"
    conds_file = WORKFLOWS_DIR / "condition-mappings.md"

    parts = []
    if rules_file.exists():
        parts.append(f"## Translation Rules\n{rules_file.read_text(encoding='utf-8')}")
    if verbs_file.exists():
        parts.append(f"## Action->Verb Mappings\n{verbs_file.read_text(encoding='utf-8')}")
    if conds_file.exists():
        parts.append(f"## Condition Mappings\n{conds_file.read_text(encoding='utf-8')}")
    return "\n\n".join(parts) if parts else "[workflow rules not found]"


# ── JSON extraction ───────────────────────────────────────────────────────────

def _parse_json_response(response: anthropic.types.Message) -> dict:
    """Robustly extract a JSON object from an API response."""
    if response.stop_reason == "max_tokens":
        raise json.JSONDecodeError(
            "Response truncated (stop_reason=max_tokens) -- retry needed", "", 0
        )

    raw = response.content[0].text.strip()

    if "```" in raw:
        inner = raw.split("```", 2)
        if len(inner) >= 3:
            raw = inner[1]
            if raw.startswith("json"):
                raw = raw[4:]
        else:
            raw = inner[-1]

    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found in response", raw, 0)
    raw = raw[start:end]

    return json.loads(raw)


# ── Token extraction ──────────────────────────────────────────────────────────

def extract_usage(response: anthropic.types.Message) -> dict:
    """Extract all token fields from a real API response."""
    u = response.usage
    return {
        "tokens_input":        u.input_tokens,
        "tokens_output":       u.output_tokens,
        "tokens_cache_read":   u.cache_read_input_tokens  or 0,
        "tokens_cache_write":  u.cache_creation_input_tokens or 0,
    }


# ── Confidence calculation ────────────────────────────────────────────────────

def make_decision_from_review(review: dict, gap_analysis: dict) -> tuple[ReviewDecision, float]:
    """Deterministic decision from translator metrics + reviewer issues."""
    issues = review.get("issues", [])
    total  = gap_analysis.get("total_statements", 1)
    mapped = gap_analysis.get("mapped_statements", total)

    confidence = ConfidenceCalculator.calculate(
        total_items=total,
        mapped_count=mapped,
        issues=issues,
        architectural_mismatch=review.get("architectural_mismatch", False),
    )
    decision = ConfidenceCalculator.make_decision(confidence, issues)
    return decision, confidence


# ── System prompts ────────────────────────────────────────────────────────────

ENHANCEMENT_SYSTEM = """\
You are an expert AWS-to-OCI IAM policy translator. Your job is to convert
AWS IAM JSON policies into accurate OCI IAM policy statements.

Rules you MUST follow:
- Use only the four OCI verbs: inspect, read, use, manage
  inspect = describe/list/get-status only
  read    = get/download/read data
  use     = start/stop/invoke/limited update (non-destructive operations)
  manage  = create/delete/full-admin (when full admin access is granted)
- Never invent OCI resource type names -- use only types from the reference docs
- For Deny statements: OCI supports deny natively; use "deny <subject> from ..."
- For PassRole: map to "manage instance-principals" or "use service-accounts"
- For cross-account: use cross-tenancy endorse/admit pattern
- Document anything that cannot be directly mapped as a gap_workaround

Output ONLY a JSON object with this exact schema:
{
  "statements": [
    {
      "sid": "OriginalAwsSid",
      "statement": "Allow group X to manage Y in compartment Z where condition",
      "aws_equivalent": "s3:GetObject, s3:PutObject",
      "notes": "Translation notes, warnings, or review flags"
    }
  ],
  "placeholders": {
    "GROUP_NAME": "Description of what group name to use",
    "COMPARTMENT_NAME": "Description of target compartment"
  },
  "critical_gaps": [
    {"gap": "Short description", "severity": "HIGH|MEDIUM|LOW", "mitigation": "How to address"}
  ],
  "migration_prerequisites": ["Create group BackendApp", "Create compartment Production"]
}
"""

REVIEW_SYSTEM = """\
You are an expert OCI IAM policy reviewer with deep knowledge of both AWS IAM and OCI IAM.
Review an AWS->OCI translation for correctness.

Severity classification rules (STRICT -- do not deviate):
  CRITICAL -- AWS statement has NO OCI equivalent at all, or fundamental model mismatch
             (e.g., translated as wrong service entirely, missing whole statement)
  HIGH     -- Wrong verb level: manage used instead of read/use, or read instead of manage
             for admin operations
  MEDIUM   -- Scope issue (too broad/narrow), condition mapping gap, single action omitted,
             cross-account pattern wrong
  LOW      -- Redundant statement, naming issue, non-security style concern

Return ONLY a JSON object with this exact schema:
{
  "decision": "APPROVED|APPROVED_WITH_NOTES|NEEDS_FIXES",
  "confidence_override": null,
  "architectural_mismatch": false,
  "issues": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "category": "verb_accuracy|scope|conditions|service_coverage|syntax|redundancy|security|gaps",
      "description": "Specific, actionable description",
      "fix_suggestion": "How to fix this"
    }
  ],
  "approved_notes": "",
  "review_summary": "2-3 sentence overall assessment"
}

Decision guidelines (the orchestrator will override based on ConfidenceCalculator,
but you should set decision to your best assessment):
  APPROVED            -- No CRITICAL/HIGH issues, translation is accurate
  APPROVED_WITH_NOTES -- Minor issues only, usable with caveats
  NEEDS_FIXES         -- Has CRITICAL or HIGH issues, must be fixed
"""

FIX_SYSTEM = """\
You are an OCI IAM policy expert. Fix specific issues in a translation.
Target ONLY the issues listed. Do not change correct statements.

Output ONLY a JSON object:
{
  "statements": [...],
  "placeholders": {...},
  "critical_gaps": [...],
  "migration_prerequisites": [...],
  "fixes_applied": ["Changed manage->read for S3 read-only access", ...]
}
"""


# ── Agent calls ───────────────────────────────────────────────────────────────

def call_enhancement(
    client: anthropic.Anthropic,
    policy_text: str,
    current_translation: dict | None,
    issues: list,
    workflow_rules: str,
    oci_docs: str,
    service_docs: str,
) -> tuple[dict, dict]:
    """Call enhancement agent. Returns (translation_dict, usage_dict)."""

    prev = json.dumps(current_translation, indent=2) if current_translation else "None -- this is the initial translation."
    issues_text = json.dumps(issues, indent=2) if issues else "None"

    start = time.perf_counter()
    response = client.messages.create(
        model=ENHANCEMENT_MODEL,
        max_tokens=8192,
        system=[
            {"type": "text", "text": ENHANCEMENT_SYSTEM},
            {"type": "text", "text": f"## OCI Reference Documentation\n\n{oci_docs}\n\n{service_docs}",
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"## Workflow Rules\n\n{workflow_rules}",
             "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{
            "role": "user",
            "content": (
                f"## Original AWS Policy\n```json\n{policy_text}\n```\n\n"
                f"## Current Translation\n```json\n{prev}\n```\n\n"
                f"## Issues to Fix\n```json\n{issues_text}\n```\n\n"
                "Produce the improved OCI translation."
            )
        }],
    )
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
    policy_text: str,
    translation: dict,
    oci_docs: str,
) -> tuple[dict, dict]:
    """Call review agent. Returns (review_dict, usage_dict)."""

    start = time.perf_counter()
    response = client.messages.create(
        model=REVIEW_MODEL,
        max_tokens=4096,
        system=[
            {"type": "text", "text": REVIEW_SYSTEM},
            {"type": "text", "text": f"## OCI Reference Documentation\n\n{oci_docs}",
             "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{
            "role": "user",
            "content": (
                f"## Original AWS Policy\n```json\n{policy_text}\n```\n\n"
                f"## OCI Translation to Review\n```json\n{json.dumps(translation, indent=2)}\n```\n\n"
                "Review this translation according to your checklist."
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
    policy_text: str,
    translation: dict,
    issues: list,
    workflow_rules: str,
    oci_docs: str,
) -> tuple[dict, dict]:
    """Call fix agent. Returns (fixed_translation_dict, usage_dict)."""

    start = time.perf_counter()
    response = client.messages.create(
        model=FIX_MODEL,
        max_tokens=8192,
        system=[
            {"type": "text", "text": FIX_SYSTEM},
            {"type": "text", "text": f"## OCI Reference\n\n{oci_docs}\n\n{workflow_rules}",
             "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{
            "role": "user",
            "content": (
                f"## Original AWS Policy\n```json\n{policy_text}\n```\n\n"
                f"## Current OCI Translation\n```json\n{json.dumps(translation, indent=2)}\n```\n\n"
                f"## Issues to Fix\n```json\n{json.dumps(issues, indent=2)}\n```\n\n"
                "Fix ONLY the listed issues."
            )
        }],
    )
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

def run_gap_analysis(policy_text: str) -> dict:
    """
    Run lightweight gap analysis directly from policy text (no subprocess).
    Returns structured dict with mapping metrics for ConfidenceCalculator.
    """
    try:
        policy = json.loads(policy_text)
    except json.JSONDecodeError:
        return {
            "total_statements": 1,
            "mapped_statements": 0,
            "unmapped_count": 0,
            "gap_count": 0,
            "detected_services": [],
            "unmapped_services": [],
        }

    statements = policy.get("Statement", [])
    total = len(statements)

    detected_services = set()
    for stmt in statements:
        actions = stmt.get("Action", [])
        if isinstance(actions, str):
            actions = [actions]
        for action in actions:
            if ":" in action:
                detected_services.add(action.split(":")[0].lower())

    KNOWN_SERVICES = {"ec2", "s3", "rds", "dynamodb", "lambda", "iam",
                      "kms", "vpc", "logs", "cloudwatch", "sqs", "sns",
                      "ecs", "eks", "secretsmanager", "ssm", "elasticloadbalancing",
                      "autoscaling", "cloudformation", "codecommit", "codebuild",
                      "codepipeline", "ecr", "route53", "cloudfront", "waf"}
    unmapped = detected_services - KNOWN_SERVICES
    mapped_statements = max(0, total - len(unmapped))

    return {
        "total_statements":  total,
        "mapped_statements": mapped_statements,
        "unmapped_count":    len(unmapped),
        "gap_count":         len(unmapped),
        "detected_services": sorted(detected_services),
        "unmapped_services": sorted(unmapped),
    }


# ── Main orchestration ────────────────────────────────────────────────────────

def run(
    input_content: str,
    progress_callback,
    anthropic_client: anthropic.Anthropic,
    max_iterations: int = 3,
) -> dict:
    """
    Full IAM policy translation orchestration.

    Args:
        input_content: AWS IAM policy JSON string
        progress_callback: Called with (phase, iteration, confidence, decision)
        anthropic_client: Pre-configured Anthropic client
        max_iterations: Max enhancement/review/fix iterations

    Returns:
        dict with keys: artifacts, confidence, decision, iterations, cost, interactions
    """
    policy_text = input_content

    # 1. Gap analysis
    progress_callback("gap_analysis", 0, 0.0, None)
    gap_analysis = run_gap_analysis(policy_text)

    # 2. Init logger
    logger = AgentLogger(project_type="iam", source_file="api-input")
    logger.start_session()
    session_start = time.perf_counter()

    logger.log_agent_call(
        iteration=0,
        agent_type=AgentType.TRANSLATOR,
        input_summary="AWS IAM policy via API",
        output_summary=(
            f"Gap analysis: {gap_analysis['unmapped_count']} unmapped services, "
            f"{gap_analysis['mapped_statements']}/{gap_analysis['total_statements']} statements mapped"
        ),
        duration_seconds=time.perf_counter() - session_start,
        metadata=gap_analysis,
    )

    # 3. Load stable context (cached across iterations)
    oci_docs      = load_core_oci_docs()
    service_docs  = load_service_docs(gap_analysis.get("detected_services", []))
    workflow_rules = load_workflow_rules()

    # 4. Enhancement -> Review -> Fix loop
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
                    client, policy_text, current_translation, current_issues,
                    workflow_rules, oci_docs, service_docs
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
            input_summary=f"Enhance translation, fix {len(current_issues)} issues",
            output_summary=f"Generated {len(translation.get('statements', []))} OCI statements",
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
                review, rev_usage = call_review(client, policy_text, translation, oci_docs)
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
                    client, policy_text, translation, fix_targets, workflow_rules, oci_docs
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
            output_summary=fixed.get("translation_notes", f"Applied {len(fixes_applied)} fixes"),
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

    # 5. End session, get reports
    json_report, md_report = logger.end_session(final_decision, final_confidence)

    # 6. Build artifacts
    artifacts = {}
    if current_translation:
        artifacts["oci_policies.json"] = json.dumps(current_translation, indent=2)
    artifacts["report.md"] = md_report

    total_cost = sum(r.get("cost_usd", 0) or 0 for r in interaction_records)

    return {
        "artifacts": artifacts,
        "confidence": final_confidence,
        "decision": final_decision.value,
        "iterations": iteration,
        "cost": total_cost,
        "interactions": interaction_records,
    }
