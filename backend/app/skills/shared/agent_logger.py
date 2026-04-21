#!/usr/bin/env python3
"""
Agent Interaction Logger & Visualizer

Tracks all agent interactions across translation/migration workflows:
- Enhancement agent responses
- Review agent feedback with confidence scores
- Fix agent iterations
- Back-and-forth dialogue
- Confidence trends over iterations

Used by:
- iam-translation
- cfn-terraform
- aws-dependency-discovery

Adapted for backend use: no filesystem I/O, returns reports as strings.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class AgentType(Enum):
    """Agent types in the orchestration workflow."""
    TRANSLATOR = "translator"
    ENHANCEMENT = "enhancement"
    REVIEW = "review"
    FIX = "fix"
    DISCOVERY = "discovery"
    VALIDATION = "validation"


class ReviewDecision(Enum):
    """Review agent decision types."""
    APPROVED = "APPROVED"
    APPROVED_WITH_NOTES = "APPROVED_WITH_NOTES"
    NEEDS_FIXES = "NEEDS_FIXES"
    FAILED = "FAILED"


@dataclass
class AgentInteraction:
    """Single agent interaction record."""
    timestamp: str
    iteration: int
    agent_type: AgentType
    model: Optional[str]            # e.g. "claude-sonnet-4-6", "claude-opus-4-6"
    input_summary: str
    output_summary: str
    full_output: Optional[str]      # Can be large, optional for storage
    confidence_score: Optional[float]  # 0.0-1.0
    decision: Optional[ReviewDecision]
    issues_found: List[str]
    fixes_applied: List[str]
    duration_seconds: float
    # Token tracking — all sourced from real API response.usage, never LLM self-report
    tokens_input: Optional[int]         # Billed input tokens (non-cached)
    tokens_output: Optional[int]        # Output tokens
    tokens_cache_read: Optional[int]    # Tokens read from prompt cache (cheap)
    tokens_cache_write: Optional[int]   # Tokens written to prompt cache
    tokens_total: Optional[int]         # Sum of all above
    cost_usd: Optional[float]           # Calculated from tokens + model pricing
    metadata: Dict[str, Any]


@dataclass
class OrchestrationSession:
    """Full orchestration session with all interactions."""
    session_id: str
    project_type: str  # iam, cfn, discovery
    source_file: str
    start_time: str
    end_time: Optional[str]
    total_iterations: int
    final_decision: Optional[ReviewDecision]
    final_confidence: Optional[float]
    interactions: List[AgentInteraction]
    summary_stats: Dict[str, Any]


def _sum_tokens(*args: Optional[int]) -> Optional[int]:
    """Sum token counts, returning None only if all values are None."""
    vals = [v for v in args if v is not None]
    return sum(vals) if vals else None


# Pricing per million tokens for Oracle Generative AI models.
# OCI GenAI does not expose prompt caching through the OpenAI-compatible
# endpoint, so cache_read / cache_write are left at 0 — usage reporting
# will always show zero cached tokens.
_MODEL_PRICING = {
    "google.gemini-2.5-pro":        {"input": 1.25, "output": 10.0, "cache_read": 0.0, "cache_write": 0.0},
    "google.gemini-2.5-flash":      {"input": 0.30, "output": 2.50, "cache_read": 0.0, "cache_write": 0.0},
    "meta.llama-3.3-70b-instruct":  {"input": 0.65, "output": 0.65, "cache_read": 0.0, "cache_write": 0.0},
    "meta.llama-3.1-405b-instruct": {"input": 5.32, "output": 16.0, "cache_read": 0.0, "cache_write": 0.0},
    "cohere.command-r-plus-08-2024":{"input": 2.50, "output": 10.0, "cache_read": 0.0, "cache_write": 0.0},
    "cohere.command-r-08-2024":     {"input": 0.15, "output": 0.60, "cache_read": 0.0, "cache_write": 0.0},
    "openai.gpt-4":                 {"input": 30.0, "output": 60.0, "cache_read": 0.0, "cache_write": 0.0},
    "openai.gpt-4o":                {"input": 2.50, "output": 10.0, "cache_read": 0.0, "cache_write": 0.0},
    "openai.gpt-4o-mini":           {"input": 0.15, "output": 0.60, "cache_read": 0.0, "cache_write": 0.0},
    "openai.gpt-4.1":               {"input": 2.00, "output": 8.00, "cache_read": 0.0, "cache_write": 0.0},
    "openai.gpt-4.1-mini":          {"input": 0.40, "output": 1.60, "cache_read": 0.0, "cache_write": 0.0},
    "openai.o1":                    {"input": 15.0, "output": 60.0, "cache_read": 0.0, "cache_write": 0.0},
    "openai.o3-mini":               {"input": 1.10, "output": 4.40, "cache_read": 0.0, "cache_write": 0.0},
    "xai.grok-3":                   {"input": 3.00, "output": 15.0, "cache_read": 0.0, "cache_write": 0.0},
    "xai.grok-4":                   {"input": 5.00, "output": 15.0, "cache_read": 0.0, "cache_write": 0.0},
}


def calculate_cost(
    model: str,
    tokens_input: Optional[int] = None,
    tokens_output: Optional[int] = None,
    tokens_cache_read: Optional[int] = None,
    tokens_cache_write: Optional[int] = None,
) -> Optional[float]:
    """Calculate USD cost from real token counts. Returns None if model unknown."""
    pricing = _MODEL_PRICING.get(model)
    if pricing is None:
        return None
    M = 1_000_000
    cost = (
        (tokens_input       or 0) / M * pricing["input"] +
        (tokens_output      or 0) / M * pricing["output"] +
        (tokens_cache_read  or 0) / M * pricing["cache_read"] +
        (tokens_cache_write or 0) / M * pricing["cache_write"]
    )
    return round(cost, 6)


class AgentLogger:
    """
    Comprehensive agent interaction logger.

    Backend-adapted version: no filesystem writes.
    Call end_session() to receive (json_str, markdown_str).
    """

    def __init__(self, project_type: str, source_file: str):
        """
        Initialize logger.

        Args:
            project_type: iam, cfn, or discovery
            source_file: Source file being processed
        """
        self.project_type = project_type
        self.source_file = source_file

        # Generate session ID
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        source_name = Path(source_file).stem
        self.session_id = f"{project_type}-{source_name}-{timestamp}"

        # Session state
        self.session: Optional[OrchestrationSession] = None
        self.interactions: List[AgentInteraction] = []
        self.start_time: Optional[float] = None

    def start_session(self):
        """Start a new orchestration session."""
        self.start_time = time.time()
        self.session = OrchestrationSession(
            session_id=self.session_id,
            project_type=self.project_type,
            source_file=self.source_file,
            start_time=datetime.now().isoformat(),
            end_time=None,
            total_iterations=0,
            final_decision=None,
            final_confidence=None,
            interactions=[],
            summary_stats={}
        )

        print(f"Started orchestration session: {self.session_id}")

    def log_agent_call(
        self,
        iteration: int,
        agent_type: AgentType,
        input_summary: str,
        output_summary: str,
        full_output: Optional[Any] = None,
        confidence_score: Optional[float] = None,
        duration_seconds: float = 0.0,
        model: Optional[str] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        tokens_cache_read: Optional[int] = None,
        tokens_cache_write: Optional[int] = None,
        cost_usd: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log a generic agent call."""
        tokens_total = _sum_tokens(tokens_input, tokens_output, tokens_cache_read, tokens_cache_write)

        interaction = AgentInteraction(
            timestamp=datetime.now().isoformat(),
            iteration=iteration,
            agent_type=agent_type,
            model=model,
            input_summary=input_summary,
            output_summary=output_summary,
            full_output=json.dumps(full_output) if full_output else None,
            confidence_score=confidence_score,
            decision=None,
            issues_found=[],
            fixes_applied=[],
            duration_seconds=duration_seconds,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_cache_read=tokens_cache_read,
            tokens_cache_write=tokens_cache_write,
            tokens_total=tokens_total,
            cost_usd=cost_usd,
            metadata=metadata or {}
        )

        self.interactions.append(interaction)

        conf_str = f" (confidence: {confidence_score:.2f})" if confidence_score else ""
        tok_str = f" [{tokens_total:,} tok]" if tokens_total else ""
        cost_str = f" (${cost_usd:.4f})" if cost_usd else ""
        model_str = f" [{model}]" if model else ""
        print(f"  [{iteration}] {agent_type.value}{model_str}: {output_summary}{conf_str}{tok_str}{cost_str}")

    def log_review_call(
        self,
        iteration: int,
        decision: ReviewDecision,
        confidence: float,
        issues_found: List[str],
        review_output: Dict[str, Any],
        duration_seconds: float,
        model: Optional[str] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        tokens_cache_read: Optional[int] = None,
        tokens_cache_write: Optional[int] = None,
        cost_usd: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log a review agent call with structured feedback."""
        tokens_total = _sum_tokens(tokens_input, tokens_output, tokens_cache_read, tokens_cache_write)
        input_summary = f"Review translation from iteration {iteration}"
        output_summary = f"{decision.value} -- {len(issues_found)} issues -- confidence {confidence:.2f}"

        interaction = AgentInteraction(
            timestamp=datetime.now().isoformat(),
            iteration=iteration,
            agent_type=AgentType.REVIEW,
            model=model,
            input_summary=input_summary,
            output_summary=output_summary,
            full_output=json.dumps(review_output),
            confidence_score=confidence,
            decision=decision,
            issues_found=issues_found,
            fixes_applied=[],
            duration_seconds=duration_seconds,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_cache_read=tokens_cache_read,
            tokens_cache_write=tokens_cache_write,
            tokens_total=tokens_total,
            cost_usd=cost_usd,
            metadata=metadata or {}
        )

        self.interactions.append(interaction)

        icon = "OK" if decision in [ReviewDecision.APPROVED, ReviewDecision.APPROVED_WITH_NOTES] else "RETRY"
        tok_str = f" [{tokens_total:,} tok]" if tokens_total else ""
        cost_str = f" (${cost_usd:.4f})" if cost_usd else ""
        model_str = f" [{model}]" if model else ""
        print(f"  [{iteration}] review{model_str}: {icon} {decision.value} (confidence: {confidence:.2f}){tok_str}{cost_str}")
        if issues_found:
            for issue in issues_found[:3]:
                print(f"           -> {issue}")
            if len(issues_found) > 3:
                print(f"           -> ... ({len(issues_found) - 3} more)")

    def log_fix_call(
        self,
        iteration: int,
        fixes_applied: List[str],
        output_summary: str,
        full_output: Optional[Any] = None,
        duration_seconds: float = 0.0,
        model: Optional[str] = None,
        tokens_input: Optional[int] = None,
        tokens_output: Optional[int] = None,
        tokens_cache_read: Optional[int] = None,
        tokens_cache_write: Optional[int] = None,
        cost_usd: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log a fix agent call."""
        tokens_total = _sum_tokens(tokens_input, tokens_output, tokens_cache_read, tokens_cache_write)
        input_summary = f"Fix issues from review iteration {iteration}"

        interaction = AgentInteraction(
            timestamp=datetime.now().isoformat(),
            iteration=iteration,
            agent_type=AgentType.FIX,
            model=model,
            input_summary=input_summary,
            output_summary=output_summary,
            full_output=json.dumps(full_output) if full_output else None,
            confidence_score=None,
            decision=None,
            issues_found=[],
            fixes_applied=fixes_applied,
            duration_seconds=duration_seconds,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_cache_read=tokens_cache_read,
            tokens_cache_write=tokens_cache_write,
            tokens_total=tokens_total,
            cost_usd=cost_usd,
            metadata=metadata or {}
        )

        self.interactions.append(interaction)

        tok_str = f" [{tokens_total:,} tok]" if tokens_total else ""
        cost_str = f" (${cost_usd:.4f})" if cost_usd else ""
        model_str = f" [{model}]" if model else ""
        print(f"  [{iteration}] fix{model_str}: Applied {len(fixes_applied)} fixes{tok_str}{cost_str}")
        for fix in fixes_applied[:3]:
            print(f"           - {fix}")
        if len(fixes_applied) > 3:
            print(f"           - ... ({len(fixes_applied) - 3} more)")

    def end_session(
        self,
        final_decision: ReviewDecision,
        final_confidence: Optional[float] = None
    ) -> tuple[str, str]:
        """
        End the orchestration session and build reports.

        Returns:
            (json_report_str, markdown_report_str)
        """
        if not self.session:
            raise RuntimeError("No active session. Call start_session() first.")

        # Update session
        self.session.end_time = datetime.now().isoformat()
        self.session.interactions = self.interactions
        self.session.final_decision = final_decision
        self.session.final_confidence = final_confidence
        self.session.total_iterations = max([i.iteration for i in self.interactions], default=0)

        # Calculate summary stats
        self.session.summary_stats = self._calculate_summary_stats()

        # Build reports as strings
        json_str = self._build_json_report()
        markdown_str = self._build_markdown_report()

        duration = time.time() - self.start_time if self.start_time else 0

        print(f"\nOrchestration complete!")
        print(f"   Final decision: {final_decision.value}")
        if final_confidence:
            print(f"   Final confidence: {final_confidence:.2f}")
        print(f"   Total iterations: {self.session.total_iterations}")
        print(f"   Duration: {duration:.1f}s")

        return json_str, markdown_str

    def _calculate_summary_stats(self) -> Dict[str, Any]:
        """Calculate summary statistics from interactions."""

        if not self.interactions:
            return {}

        # Count by agent type
        agent_counts = {}
        for interaction in self.interactions:
            agent_type = interaction.agent_type.value
            agent_counts[agent_type] = agent_counts.get(agent_type, 0) + 1

        # Confidence progression
        confidence_scores = [
            (i.iteration, i.confidence_score)
            for i in self.interactions
            if i.confidence_score is not None
        ]

        # Total issues found and fixed
        total_issues = sum(len(i.issues_found) for i in self.interactions)
        total_fixes = sum(len(i.fixes_applied) for i in self.interactions)

        # Total duration
        total_duration = sum(i.duration_seconds for i in self.interactions)

        # Token totals (from real API usage -- never LLM self-report)
        def _tot(field): return sum(getattr(i, field) or 0 for i in self.interactions)
        total_tokens_input        = _tot('tokens_input')
        total_tokens_output       = _tot('tokens_output')
        total_tokens_cache_read   = _tot('tokens_cache_read')
        total_tokens_cache_write  = _tot('tokens_cache_write')
        total_tokens              = _tot('tokens_total')
        total_cost                = sum(i.cost_usd or 0 for i in self.interactions)

        # Per-model breakdown: {model: {input, output, cache_read, cache_write, total, cost}}
        by_model: Dict[str, Any] = {}
        for ix in self.interactions:
            m = ix.model or "unknown"
            if m not in by_model:
                by_model[m] = {"input": 0, "output": 0, "cache_read": 0,
                               "cache_write": 0, "total": 0, "cost": 0.0, "calls": 0}
            by_model[m]["input"]       += ix.tokens_input       or 0
            by_model[m]["output"]      += ix.tokens_output      or 0
            by_model[m]["cache_read"]  += ix.tokens_cache_read  or 0
            by_model[m]["cache_write"] += ix.tokens_cache_write or 0
            by_model[m]["total"]       += ix.tokens_total       or 0
            by_model[m]["cost"]        += ix.cost_usd           or 0.0
            by_model[m]["calls"]       += 1

        # Per-agent-type token totals
        tokens_by_agent: Dict[str, int] = {}
        for ix in self.interactions:
            at = ix.agent_type.value
            tokens_by_agent[at] = tokens_by_agent.get(at, 0) + (ix.tokens_total or 0)

        return {
            'total_agent_calls': len(self.interactions),
            'agent_type_counts': agent_counts,
            'confidence_progression': confidence_scores,
            'total_issues_found': total_issues,
            'total_fixes_applied': total_fixes,
            'total_duration_seconds': total_duration,
            'avg_duration_per_call': total_duration / len(self.interactions) if self.interactions else 0,
            'total_tokens': total_tokens,
            'total_tokens_input': total_tokens_input,
            'total_tokens_output': total_tokens_output,
            'total_tokens_cache_read': total_tokens_cache_read,
            'total_tokens_cache_write': total_tokens_cache_write,
            'total_cost_usd': round(total_cost, 6),
            'tokens_by_agent_type': tokens_by_agent,
            'tokens_by_model': by_model,
        }

    def _build_json_report(self) -> str:
        """Build structured JSON report string."""

        # Convert session to dict
        session_dict = asdict(self.session)

        # Convert enums to strings
        session_dict['final_decision'] = session_dict['final_decision'].value if session_dict['final_decision'] else None

        for interaction in session_dict['interactions']:
            interaction['agent_type'] = interaction['agent_type'].value
            interaction['decision'] = interaction['decision'].value if interaction['decision'] else None

        return json.dumps(session_dict, indent=2)

    def _build_markdown_report(self) -> str:
        """Build human-readable markdown report string."""

        if not self.session:
            return ""

        lines = []

        # Header
        lines.append(f"# Orchestration Report: {self.session_id}")
        lines.append(f"")
        lines.append(f"**Project:** {self.project_type}")
        lines.append(f"**Source:** `{self.source_file}`")
        lines.append(f"**Started:** {self.session.start_time}")
        lines.append(f"**Completed:** {self.session.end_time}")
        lines.append(f"**Total Iterations:** {self.session.total_iterations}")
        lines.append(f"")

        # Final result
        lines.append(f"## Final Result")
        lines.append(f"")
        _icon_map = {
            ReviewDecision.APPROVED: "✅",
            ReviewDecision.APPROVED_WITH_NOTES: "⚠️",
            ReviewDecision.NEEDS_FIXES: "❌",
        }
        decision_icon = _icon_map.get(self.session.final_decision, "❌")
        lines.append(f"**Decision:** {decision_icon} {self.session.final_decision.value if self.session.final_decision else 'N/A'}")

        if self.session.final_confidence:
            lines.append(f"**Confidence:** {self.session.final_confidence:.2%}")
        lines.append(f"")

        # Summary stats
        stats = self.session.summary_stats
        lines.append(f"## Summary Statistics")
        lines.append(f"")
        lines.append(f"- **Total agent calls:** {stats.get('total_agent_calls', 0)}")
        lines.append(f"- **Issues found:** {stats.get('total_issues_found', 0)}")
        lines.append(f"- **Fixes applied:** {stats.get('total_fixes_applied', 0)}")
        lines.append(f"- **Total duration:** {stats.get('total_duration_seconds', 0):.1f}s")
        lines.append(f"- **Avg call duration:** {stats.get('avg_duration_per_call', 0):.1f}s")

        lines.append(f"")

        # Agent type breakdown
        lines.append(f"### Agent Type Breakdown")
        lines.append(f"")
        for agent_type, count in stats.get('agent_type_counts', {}).items():
            lines.append(f"- **{agent_type}:** {count} calls")
        lines.append(f"")

        # Token usage stats -- sourced from real API response.usage
        lines.append(f"### Token Usage")
        lines.append(f"")
        lines.append(f"- **Total tokens:** {stats.get('total_tokens', 0):,}")
        lines.append(f"- **Input tokens:** {stats.get('total_tokens_input', 0):,}")
        lines.append(f"- **Output tokens:** {stats.get('total_tokens_output', 0):,}")
        lines.append(f"- **Cache read tokens:** {stats.get('total_tokens_cache_read', 0):,}")
        lines.append(f"- **Cache write tokens:** {stats.get('total_tokens_cache_write', 0):,}")
        lines.append(f"- **Total cost:** ${stats.get('total_cost_usd', 0):.6f}")
        if stats.get('tokens_by_agent_type'):
            lines.append(f"")
            lines.append(f"**By Agent Type:**")
            for agent_type, tokens in stats['tokens_by_agent_type'].items():
                if tokens:
                    lines.append(f"- **{agent_type}:** {tokens:,} tokens")
        if stats.get('tokens_by_model'):
            lines.append(f"")
            lines.append(f"**By Model:**")
            for model, mdata in stats['tokens_by_model'].items():
                lines.append(f"- **{model}:** {mdata.get('total', 0):,} tokens (${mdata.get('cost', 0):.4f}, {mdata.get('calls', 0)} calls)")
        lines.append(f"")

        # Confidence progression
        if stats.get('confidence_progression'):
            lines.append(f"### Confidence Progression")
            lines.append(f"")
            lines.append(f"```")
            for iteration, confidence in stats['confidence_progression']:
                bar_length = int(confidence * 40)
                bar = "#" * bar_length + "." * (40 - bar_length)
                lines.append(f"Iteration {iteration}: {bar} {confidence:.2%}")
            lines.append(f"```")
            lines.append(f"")

        # Timeline
        lines.append(f"## Timeline")
        lines.append(f"")
        lines.append(f"```")
        for interaction in self.interactions:
            timestamp = datetime.fromisoformat(interaction.timestamp).strftime("%H:%M:%S")
            agent_label = {
                AgentType.TRANSLATOR: "TRANSLATOR",
                AgentType.ENHANCEMENT: "ENHANCEMENT",
                AgentType.REVIEW: "REVIEW",
                AgentType.FIX: "FIX",
                AgentType.DISCOVERY: "DISCOVERY",
                AgentType.VALIDATION: "VALIDATION"
            }.get(interaction.agent_type, "OTHER")
            lines.append(f"{timestamp} [{interaction.iteration}] {agent_label}")
            lines.append(f"         -> {interaction.output_summary}")
            if interaction.confidence_score:
                lines.append(f"            Confidence: {interaction.confidence_score:.2%}")
            if interaction.tokens_total:
                cost_str = f" (${interaction.cost_usd:.4f})" if interaction.cost_usd else ""
                lines.append(f"            Tokens: {interaction.tokens_total:,}{cost_str}")
            if interaction.issues_found:
                lines.append(f"            Issues: {len(interaction.issues_found)}")
            if interaction.fixes_applied:
                lines.append(f"            Fixes: {len(interaction.fixes_applied)}")
            lines.append(f"")
        lines.append(f"```")

        return '\n'.join(lines)


class ConfidenceCalculator:
    """
    Calculates confidence from actual review metrics rather than hardcoded values.
    Shared across all orchestrators (cfn-terraform, iam-translation, aws-dependency-discovery).
    """

    SEVERITY_WEIGHTS = {'CRITICAL': 0.15, 'HIGH': 0.05, 'MEDIUM': 0.02, 'LOW': 0.0}

    @staticmethod
    def calculate(total_items: int, mapped_count: int, issues: list,
                  architectural_mismatch: bool = False) -> float:
        """
        Derive confidence from review metrics.

        Args:
            total_items: Total items to translate/map (resources, statements, services)
            mapped_count: Items successfully mapped/translated
            issues: List of issue dicts with 'severity' key (CRITICAL/HIGH/MEDIUM/LOW)
            architectural_mismatch: Whether a fundamental target/approach is wrong
        """
        if total_items == 0:
            return 0.0

        # Base: percentage of items successfully mapped
        base = mapped_count / total_items

        # Penalties by severity
        penalty = sum(
            ConfidenceCalculator.SEVERITY_WEIGHTS.get(i.get('severity', 'LOW'), 0.0)
            for i in issues
        )

        # Architectural mismatch penalty (e.g. wrong container platform, wrong IAM model)
        if architectural_mismatch:
            penalty += 0.25

        result = max(0.0, min(0.95, base - penalty))
        # Floor: if no issues and not architectural mismatch, confidence should be at least 0.6
        if total_items > 0 and not issues and not architectural_mismatch:
            result = max(0.6, result)
        return result

    @staticmethod
    def make_decision(confidence: float, issues: list) -> 'ReviewDecision':
        """
        Determine approval decision from confidence and issues.

        Returns:
            ReviewDecision enum value
        """
        has_critical = any(i.get('severity') == 'CRITICAL' for i in issues)
        has_high = any(i.get('severity') == 'HIGH' for i in issues)

        if has_critical:
            return ReviewDecision.NEEDS_FIXES
        elif confidence >= 0.85:
            return ReviewDecision.APPROVED
        elif confidence >= 0.65 and not has_high:
            return ReviewDecision.APPROVED_WITH_NOTES
        else:
            return ReviewDecision.NEEDS_FIXES
