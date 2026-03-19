#!/usr/bin/env python3
"""
BaseTranslationOrchestrator -- common Enhancement->Review->Fix loop for all
translation skill orchestrators.

Subclasses override:
- System prompts (ENHANCEMENT_SYSTEM, REVIEW_SYSTEM, FIX_SYSTEM)
- build_enhancement_prompt(), build_review_prompt(), build_fix_prompt()
- run_gap_analysis()
- generate_report_md()
- Logger/artifact metadata (SKILL_TYPE, PROJECT_TYPE, REPORT_FILENAME)
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

import anthropic

# ── Path setup ────────────────────────────────────────────────────────────────
SKILLS_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(SKILLS_ROOT / "shared"))

from agent_logger import (           # noqa: E402
    AgentLogger, AgentType, ReviewDecision, ConfidenceCalculator, calculate_cost
)

_log = logging.getLogger(__name__)


# ── JSON extraction (shared by all orchestrators) ────────────────────────────

def _parse_json_response(response: anthropic.types.Message) -> dict:
    """Robustly extract a JSON object from an API response."""
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


# ── Token extraction ─────────────────────────────────────────────────────────

def extract_usage(response: anthropic.types.Message) -> dict:
    """Extract all token fields from a real API response. Never estimated."""
    u = response.usage
    return {
        "tokens_input":        u.input_tokens,
        "tokens_output":       u.output_tokens,
        "tokens_cache_read":   u.cache_read_input_tokens  or 0,
        "tokens_cache_write":  u.cache_creation_input_tokens or 0,
    }


# ── Confidence calculation ───────────────────────────────────────────────────

def make_decision_from_review(review: dict, gap_analysis: dict) -> tuple[ReviewDecision, float]:
    """Deterministic decision from gap_analysis counts + reviewer issues."""
    issues       = review.get("issues", [])
    total        = gap_analysis.get("total_resources", 1)
    # Use mapped_resources from gap analysis if present (reflects known gaps like SQL Server),
    # otherwise assume all resources are initially mappable.
    mapped_from_gap = gap_analysis.get("mapped_resources", total)
    critical_cnt = sum(1 for i in issues if i.get("severity") == "CRITICAL")
    mapped_count = max(0, mapped_from_gap - critical_cnt)

    confidence = ConfidenceCalculator.calculate(
        total_items=total,
        mapped_count=mapped_count,
        issues=issues,
        architectural_mismatch=review.get("architectural_mismatch", False),
    )
    decision = ConfidenceCalculator.make_decision(confidence, issues)
    return decision, confidence


# ── Artifact builder ─────────────────────────────────────────────────────────

def build_artifact_dict(translation: dict, summary: dict | None = None) -> dict:
    """Build a dict of filename -> content strings from the translation result."""
    artifacts = {}
    artifacts["main.tf"]                   = translation.get("main_tf", "# main.tf\n")
    artifacts["variables.tf"]              = translation.get("variables_tf", "# variables.tf\n")
    artifacts["outputs.tf"]                = translation.get("outputs_tf", "# outputs.tf\n")
    artifacts["terraform.tfvars.example"]  = translation.get("tfvars_example", "# terraform.tfvars.example\n")
    if summary:
        artifacts["summary.json"] = json.dumps(summary, indent=2)
    return artifacts


# ── Terraform validate ───────────────────────────────────────────────────────

def _try_terraform_validate(artifacts: dict) -> dict:
    """Write Terraform files to a temp dir and run terraform validate."""
    import subprocess
    import tempfile
    import shutil

    if not shutil.which("terraform"):
        return {"valid": None, "output": "terraform not installed", "available": False}

    with tempfile.TemporaryDirectory() as tmpdir:
        for filename, content in artifacts.items():
            if filename.endswith(".tf"):
                Path(tmpdir, filename).write_text(content or "")

        init_result = subprocess.run(
            ["terraform", "init", "-backend=false", "-no-color"],
            cwd=tmpdir, capture_output=True, text=True, timeout=60
        )
        if init_result.returncode != 0:
            return {"valid": False, "output": init_result.stderr[:2000], "available": True}

        validate_result = subprocess.run(
            ["terraform", "validate", "-no-color"],
            cwd=tmpdir, capture_output=True, text=True, timeout=30
        )
        return {
            "valid": validate_result.returncode == 0,
            "output": (validate_result.stdout + validate_result.stderr)[:2000],
            "available": True,
        }


# ── Guardrail integration ───────────────────────────────────────────────────

def _guard_input(text: str, skill_type: str) -> str:
    """Run input guardrails. Returns scrubbed text. Raises ValueError if blocked."""
    try:
        from app.gateway.model_gateway import guard_input
        return guard_input(text, skill_type)
    except ImportError:
        _log.debug("Guardrails not available -- skipping input guard")
        return text


def _guard_output(text: str, skill_type: str) -> None:
    """Run output guardrails. Logs warnings but does not block."""
    try:
        from app.gateway.model_gateway import guard_output
        result = guard_output(text, skill_type)
        if result.get("compliance_flags"):
            _log.warning(
                "Output guardrail compliance flags [%s]: %s",
                skill_type, result["compliance_flags"]
            )
        if result.get("issues"):
            _log.warning(
                "Output guardrail issues [%s]: %s",
                skill_type, result["issues"]
            )
    except ImportError:
        _log.debug("Guardrails not available -- skipping output guard")


# ═══════════════════════════════════════════════════════════════════════════════
# Base class
# ═══════════════════════════════════════════════════════════════════════════════

class BaseTranslationOrchestrator:
    """Abstract base for translation skill orchestrators.

    Subclasses MUST override:
      - ENHANCEMENT_SYSTEM, REVIEW_SYSTEM, FIX_SYSTEM  (system prompts)
      - SKILL_TYPE, PROJECT_TYPE, REPORT_FILENAME
      - run_gap_analysis(input_data) -> dict
      - build_enhancement_prompt(input_content, input_data, current_translation, issues) -> str
      - build_review_prompt(input_content, input_data, translation) -> str
      - build_fix_prompt(input_content, input_data, translation, issues) -> str
      - generate_report_md(translation, gap_analysis, last_review, final_decision, confidence, iterations) -> str
      - get_logger_source(input_data) -> str
      - format_gap_analysis_log(input_data, gap_analysis) -> tuple[str, str]  (input_summary, output_summary)
      - format_enhancement_log(current_issues, translation) -> tuple[str, str]

    Optionally override:
      - get_enhancement_system_blocks() -> list[dict]   (to add cache_control)
      - get_fix_system_blocks() -> list[dict]           (to add cache_control)
    """

    # Class-level constants -- override in subclasses
    ENHANCEMENT_MODEL: str = "claude-opus-4-6"
    REVIEW_MODEL: str      = "claude-sonnet-4-6"
    FIX_MODEL: str         = "claude-sonnet-4-6"

    SKILL_TYPE: str     = "unknown"
    PROJECT_TYPE: str   = "unknown"
    REPORT_FILENAME: str = "translation.md"

    # System prompts -- override in subclasses
    ENHANCEMENT_SYSTEM: str = ""
    REVIEW_SYSTEM: str      = ""
    FIX_SYSTEM: str         = ""

    # ── Abstract methods (subclasses must implement) ─────────────────────────

    def run_gap_analysis(self, input_data: dict) -> dict:
        raise NotImplementedError

    def build_enhancement_prompt(
        self, input_content: str, input_data: dict,
        current_translation: dict | None, issues: list,
    ) -> str:
        raise NotImplementedError

    def build_review_prompt(
        self, input_content: str, input_data: dict, translation: dict,
    ) -> str:
        raise NotImplementedError

    def build_fix_prompt(
        self, input_content: str, input_data: dict,
        translation: dict, issues: list,
    ) -> str:
        raise NotImplementedError

    def generate_report_md(
        self, translation: dict, gap_analysis: dict, last_review: dict,
        final_decision: Any, final_confidence: float, iteration_count: int,
    ) -> str:
        raise NotImplementedError

    def get_logger_source(self, input_data: dict) -> str:
        """Return the source_file string for AgentLogger."""
        return "api-input"

    def format_gap_analysis_log(
        self, input_data: dict, gap_analysis: dict,
    ) -> tuple[str, str]:
        """Return (input_summary, output_summary) for gap analysis log entry."""
        raise NotImplementedError

    def format_enhancement_log(
        self, current_issues: list, translation: dict,
    ) -> tuple[str, str]:
        """Return (input_summary, output_summary) for enhancement log entry."""
        raise NotImplementedError

    # ── Overridable hooks ────────────────────────────────────────────────────

    def get_enhancement_system_blocks(self) -> list[dict]:
        """Return system message blocks for enhancement agent.
        Override to add cache_control or extra system blocks."""
        return [{"type": "text", "text": self.ENHANCEMENT_SYSTEM}]

    def get_fix_system_blocks(self) -> list[dict]:
        """Return system message blocks for fix agent.
        Override to add cache_control or extra system blocks."""
        return [{"type": "text", "text": self.FIX_SYSTEM}]

    # ── Agent calls ──────────────────────────────────────────────────────────

    def _call_enhancement(
        self, client: anthropic.Anthropic,
        input_content: str, input_data: dict,
        current_translation: dict | None, issues: list,
    ) -> tuple[dict, dict]:
        """Call enhancement agent. Returns (translation_dict, usage_dict)."""
        user_content = self.build_enhancement_prompt(
            input_content, input_data, current_translation, issues
        )

        start = time.perf_counter()
        with client.messages.stream(
            model=self.ENHANCEMENT_MODEL,
            max_tokens=32768,
            system=self.get_enhancement_system_blocks(),
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            response = stream.get_final_message()
        duration = time.perf_counter() - start

        # Output guardrail (log only)
        raw_text = response.content[0].text if response.content else ""
        _guard_output(raw_text, self.SKILL_TYPE)

        translation = _parse_json_response(response)

        usage = extract_usage(response)
        usage["duration"] = duration
        usage["model"] = self.ENHANCEMENT_MODEL
        usage["cost"] = calculate_cost(self.ENHANCEMENT_MODEL, **{
            k: usage[k] for k in
            ["tokens_input", "tokens_output", "tokens_cache_read", "tokens_cache_write"]
        })
        return translation, usage

    def _call_review(
        self, client: anthropic.Anthropic,
        input_content: str, input_data: dict, translation: dict,
    ) -> tuple[dict, dict]:
        """Call review agent. Returns (review_dict, usage_dict)."""
        user_content = self.build_review_prompt(input_content, input_data, translation)

        start = time.perf_counter()
        response = client.messages.create(
            model=self.REVIEW_MODEL,
            max_tokens=4096,
            system=[{"type": "text", "text": self.REVIEW_SYSTEM}],
            messages=[{"role": "user", "content": user_content}],
        )
        duration = time.perf_counter() - start

        # Output guardrail (log only)
        raw_text = response.content[0].text if response.content else ""
        _guard_output(raw_text, self.SKILL_TYPE)

        review = _parse_json_response(response)

        usage = extract_usage(response)
        usage["duration"] = duration
        usage["model"] = self.REVIEW_MODEL
        usage["cost"] = calculate_cost(self.REVIEW_MODEL, **{
            k: usage[k] for k in
            ["tokens_input", "tokens_output", "tokens_cache_read", "tokens_cache_write"]
        })
        return review, usage

    def _call_fix(
        self, client: anthropic.Anthropic,
        input_content: str, input_data: dict,
        translation: dict, issues: list,
    ) -> tuple[dict, dict]:
        """Call fix agent. Returns (fixed_translation_dict, usage_dict)."""
        user_content = self.build_fix_prompt(input_content, input_data, translation, issues)

        start = time.perf_counter()
        with client.messages.stream(
            model=self.FIX_MODEL,
            max_tokens=32768,
            system=self.get_fix_system_blocks(),
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            response = stream.get_final_message()
        duration = time.perf_counter() - start

        # Output guardrail (log only)
        raw_text = response.content[0].text if response.content else ""
        _guard_output(raw_text, self.SKILL_TYPE)

        fixed = _parse_json_response(response)

        usage = extract_usage(response)
        usage["duration"] = duration
        usage["model"] = self.FIX_MODEL
        usage["cost"] = calculate_cost(self.FIX_MODEL, **{
            k: usage[k] for k in
            ["tokens_input", "tokens_output", "tokens_cache_read", "tokens_cache_write"]
        })
        return fixed, usage

    # ── Main orchestration loop ──────────────────────────────────────────────

    def run(
        self,
        input_content: str,
        progress_callback,
        anthropic_client,
        max_iterations: int = 3,
    ) -> dict:
        """Full Enhancement -> Review -> Fix orchestration.

        Args:
            input_content: JSON string describing AWS resources
            progress_callback: Called with (phase, iteration, confidence, decision)
            anthropic_client: Pre-configured Anthropic client
            max_iterations: Max enhancement/review/fix iterations

        Returns:
            dict with keys: artifacts, confidence, decision, iterations, cost, interactions
        """
        # 0. Input guardrail (raises ValueError if blocked)
        input_content = _guard_input(input_content, self.SKILL_TYPE)

        # 1. Parse input
        try:
            input_data = json.loads(input_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"input_content must be valid JSON: {e}")

        # 2. Run gap analysis
        progress_callback("gap_analysis", 0, 0.0, None)
        gap_analysis = self.run_gap_analysis(input_data)

        # 3. Init logger
        logger = AgentLogger(
            project_type=self.PROJECT_TYPE,
            source_file=self.get_logger_source(input_data),
        )
        logger.start_session()
        session_start = time.perf_counter()

        input_summary, output_summary = self.format_gap_analysis_log(input_data, gap_analysis)
        logger.log_agent_call(
            iteration=0,
            agent_type=AgentType.TRANSLATOR,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_seconds=time.perf_counter() - session_start,
            metadata=gap_analysis,
        )

        # 4. Enhancement -> Review -> Fix loop
        client = anthropic_client
        current_translation: dict | None = None
        current_issues: list = []
        final_decision    = ReviewDecision.NEEDS_FIXES
        final_confidence  = 0.0
        last_review: dict = {}
        interaction_records: list = []
        iteration = 0

        for iteration in range(1, max_iterations + 1):
            progress_callback("enhancement", iteration, final_confidence, None)

            # Enhancement (retry up to 3 times)
            translation = None
            for _attempt in range(3):
                try:
                    translation, enh_usage = self._call_enhancement(
                        client, input_content, input_data,
                        current_translation, current_issues,
                    )
                    break
                except json.JSONDecodeError as e:
                    if _attempt == 2:
                        raise RuntimeError(f"Enhancement agent failed after 3 attempts: {e}")
            if translation is None:
                raise RuntimeError("Enhancement agent returned no result")

            enh_input_summary, enh_output_summary = self.format_enhancement_log(
                current_issues, translation,
            )
            logger.log_agent_call(
                iteration=iteration,
                agent_type=AgentType.ENHANCEMENT,
                input_summary=enh_input_summary,
                output_summary=enh_output_summary,
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
                    review, rev_usage = self._call_review(
                        client, input_content, input_data, translation,
                    )
                    break
                except json.JSONDecodeError as e:
                    if _attempt == 2:
                        raise RuntimeError(f"Review agent failed after 3 attempts: {e}")
            if review is None:
                raise RuntimeError("Review agent returned no result")

            decision, confidence = make_decision_from_review(review, gap_analysis)
            final_decision   = decision
            final_confidence = confidence
            last_review      = review

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
                    fixed, fix_usage = self._call_fix(
                        client, input_content, input_data,
                        translation, fix_targets,
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
            current_issues      = high_issues

        # 5. End session, get reports
        json_report, md_report = logger.end_session(final_decision, final_confidence)

        # 6. Build artifacts
        summary_data = {
            "decision":     final_decision.value,
            "confidence":   final_confidence,
            "iterations":   iteration,
            "gap_analysis": gap_analysis,
        }
        artifacts = build_artifact_dict(current_translation or {}, summary_data)
        # Rich migration guide
        artifacts[self.REPORT_FILENAME] = self.generate_report_md(
            current_translation or {}, gap_analysis, last_review,
            final_decision, final_confidence, iteration,
        )
        # Orchestration log (what the agents actually did)
        artifacts["ORCHESTRATION-SUMMARY.md"] = md_report

        # Calculate total cost
        total_cost = sum(r.get("cost_usd", 0) or 0 for r in interaction_records)

        # Terraform validate (best-effort)
        tf_validate = _try_terraform_validate(artifacts)
        if tf_validate["available"]:
            if tf_validate["valid"]:
                artifacts["terraform-validate.txt"] = (
                    "\u2713 terraform validate passed\n" + tf_validate["output"]
                )
            else:
                artifacts["terraform-validate.txt"] = (
                    "\u2717 terraform validate FAILED\n" + tf_validate["output"]
                )

        return {
            "artifacts":       artifacts,
            "confidence":      final_confidence,
            "decision":        final_decision.value,
            "iterations":      iteration,
            "cost":            total_cost,
            "interactions":    interaction_records,
            "terraform_valid": tf_validate.get("valid"),
        }
