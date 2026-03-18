"""Dependency Discovery orchestrator -- thin wrapper over src/ package."""
import json
import sys
import tempfile
import shutil
import time
from datetime import datetime
from pathlib import Path

import anthropic as _anthropic

SKILLS_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(SKILLS_ROOT / "shared"))

from agent_logger import AgentType, ReviewDecision, ConfidenceCalculator, calculate_cost

REVIEW_MODEL = "claude-opus-4-6"

REVIEW_SYSTEM = """\
You are an expert AWS infrastructure migration analyst reviewing a dependency discovery graph.
Your job is to assess the quality and completeness of the discovered dependency graph
for migrating AWS resources to OCI.

Evaluate based on:
- Coverage: Are resources well-connected or are there isolated nodes suggesting missed dependencies?
- Cycle detection: Circular dependencies require special migration handling
- Migration order validity: Can the proposed migration steps be executed sequentially?
- Data quality: Are node/edge counts reasonable for the event volume?

Severity classification:
  CRITICAL -- Migration cannot proceed safely (e.g., unresolvable cycles, zero coverage)
  HIGH     -- Significant gaps that require manual review before migration
  MEDIUM   -- Minor coverage issues or optimization opportunities
  LOW      -- Informational notes, style, or cosmetic concerns

Return ONLY a JSON object with this exact schema:
{
  "decision": "APPROVED|APPROVED_WITH_NOTES|NEEDS_FIXES",
  "confidence": 0.85,
  "issues": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "category": "coverage|cycles|migration_order|data_quality|completeness",
      "description": "Specific description",
      "recommendation": "How to address this"
    }
  ],
  "review_summary": "2-3 sentence overall assessment"
}

Decision guidelines:
  APPROVED            -- Graph is complete, migration order is valid, no blocking issues
  APPROVED_WITH_NOTES -- Minor gaps or cycles, usable with caveats
  NEEDS_FIXES         -- Critical gaps or unresolvable cycles that block safe migration
"""


def _build_discovery_translation_log(
    session_start: float,
    event_count: int,
    node_count: int,
    edge_count: int,
    step_count: int,
    has_cycles: bool,
    flowlog_provided: bool,
    review: dict,
    final_confidence: float,
    final_decision: str,
    review_cost: float,
) -> str:
    """Build orchestration log for the dependency discovery run."""
    duration = time.time() - session_start
    now = datetime.utcnow()
    session_id = f"discovery-{now.strftime('%Y%m%d-%H%M%S')}"

    decision_icon = {"APPROVED": "✅", "APPROVED_WITH_NOTES": "⚠️", "NEEDS_FIXES": "❌"}.get(final_decision, "❓")

    issues = review.get("issues", [])
    issue_lines = []
    for iss in issues:
        sev = iss.get("severity", "?")
        desc = iss.get("description", "")
        rec = iss.get("recommendation", "")
        issue_lines.append(f"- **[{sev}]** {desc}")
        if rec:
            issue_lines.append(f"  - *Recommendation:* {rec}")

    lines = [
        f"# Orchestration Report: {session_id}",
        "",
        f"**Project:** Dependency Discovery",
        f"**Started:** {now.isoformat()}Z",
        f"**Duration:** {duration:.1f}s",
        f"**Review Cost:** ${review_cost:.4f}",
        "",
        "---",
        "",
        "## Final Result",
        "",
        f"**Decision:** {decision_icon} **{final_decision}**",
        f"**Final Confidence:** {final_confidence:.2f}",
        "**Total Iterations:** 2 (pipeline + LLM review)",
        "",
        "---",
        "",
        "## Summary Statistics",
        "",
        f"- **Pipeline:** Deterministic graph build + LLM review",
        f"- **CloudTrail events ingested:** {event_count}",
        f"- **Flow logs included:** {'Yes' if flowlog_provided else 'No'}",
        f"- **Duration:** {duration:.1f}s",
        "",
        "---",
        "",
        "## Detailed Interactions",
        "",
        "### [0] INGESTION",
        f"**Time:** {now.isoformat()}Z",
        "**Agent:** deterministic pipeline (no LLM)",
        "",
        f"**Input:** CloudTrail JSON ({event_count} events)" + (", VPC flow logs" if flowlog_provided else ""),
        "",
        "### [1] GRAPH BUILD",
        "",
        f"**Nodes discovered:** {node_count}",
        f"**Edges (dependencies):** {edge_count}",
        f"**Cycles detected:** {'Yes' if has_cycles else 'No'}",
        f"**Migration steps computed:** {step_count}",
        "",
        "### [2] LLM REVIEW",
        "",
        f"**Model:** {REVIEW_MODEL}",
        f"**Decision:** {final_decision}",
        f"**Confidence:** {final_confidence:.2f}",
        "",
        f"**Review Summary:** {review.get('review_summary', 'N/A')}",
        "",
    ]

    if issue_lines:
        lines += ["**Issues Found:**", ""] + issue_lines + [""]
    else:
        lines += ["**Issues Found:** None", ""]

    return "\n".join(lines)


def _call_review(
    client,
    node_count: int,
    edge_count: int,
    step_count: int,
    event_count: int,
    has_cycles: bool,
    cycles: list,
    flowlog_provided: bool,
    report_md: str,
) -> tuple[dict, dict]:
    """Call LLM reviewer on the discovered graph. Returns (review_dict, usage_dict)."""
    summary = (
        f"## Graph Discovery Summary\n\n"
        f"- CloudTrail events ingested: {event_count}\n"
        f"- VPC flow logs included: {'Yes' if flowlog_provided else 'No'}\n"
        f"- Nodes (resources) discovered: {node_count}\n"
        f"- Edges (dependencies) discovered: {edge_count}\n"
        f"- Migration steps: {step_count}\n"
        f"- Cycles detected: {'Yes — ' + str(len(cycles)) + ' cycle(s)' if has_cycles else 'No'}\n"
    )
    if has_cycles and cycles:
        cycle_strs = "; ".join(" → ".join(c) for c in cycles[:5])
        summary += f"- Cycle details: {cycle_strs}\n"

    start = time.perf_counter()
    response = client.messages.create(
        model=REVIEW_MODEL,
        max_tokens=2048,
        system=REVIEW_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"{summary}\n\n"
                f"## Dependency Report (excerpt)\n\n"
                f"{report_md[:6000]}\n\n"
                "Review this dependency graph and return your assessment as JSON."
            ),
        }],
    )
    duration = time.perf_counter() - start

    u = response.usage
    usage = {
        "tokens_input": u.input_tokens,
        "tokens_output": u.output_tokens,
        "tokens_cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
        "tokens_cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "duration_seconds": duration,
    }

    raw = response.content[0].text.strip()
    if "```" in raw:
        parts = raw.split("```", 2)
        raw = parts[1][4:] if parts[1].startswith("json") else parts[1]
    start_idx = raw.find("{")
    end_idx = raw.rfind("}") + 1
    review = json.loads(raw[start_idx:end_idx]) if start_idx >= 0 else {}

    return review, usage


def run(
    input_content: str,
    flowlog_content: str | None,
    progress_callback,
    anthropic_client,
    max_iterations: int = 3,
) -> dict:
    """
    Run dependency discovery pipeline.

    Args:
        input_content: CloudTrail JSON events (array or Records wrapper)
        flowlog_content: Optional VPC flow log text content
        progress_callback: Called with (phase, iteration, confidence, decision)
        anthropic_client: Anthropic client instance (used for LLM review)
        max_iterations: Unused (single review pass)

    Returns dict with keys: artifacts, confidence, decision, iterations, cost, interactions
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "src"))

    from aws_dependency_discovery.graph.db import Database
    from aws_dependency_discovery.ingestion.cloudtrail import parse_cloudtrail_file
    from aws_dependency_discovery.graph.builder import build_graph, enrich_graph_with_network_deps
    from aws_dependency_discovery.analysis.classifier import classify_all, compute_migration_order
    from aws_dependency_discovery.output.mermaid import export_mermaid
    from aws_dependency_discovery.output.dot import export_dot
    from aws_dependency_discovery.output.report import format_report

    # Create temp workspace
    tmp_dir = Path(tempfile.mkdtemp(prefix="oci-discovery-"))
    db_path = tmp_dir / "discovery.db"
    session_start = time.time()

    try:
        progress_callback("ingestion", 0, 0.0, None)

        # Parse CloudTrail input
        events = json.loads(input_content)
        if isinstance(events, dict) and "Records" in events:
            events = events["Records"]
        event_count = len(events)

        # Write events to temp file for ingestion
        ct_file = tmp_dir / "cloudtrail.json"
        ct_file.write_text(json.dumps({"Records": events}))

        db = Database(db_path)

        # Ingest CloudTrail
        ct_events = list(parse_cloudtrail_file(ct_file))
        count = db.insert_events_batch(ct_events)

        # Ingest flow logs if provided
        if flowlog_content:
            fl_file = tmp_dir / "flowlogs.log"
            fl_file.write_text(flowlog_content)
            from aws_dependency_discovery.ingestion.flowlogs import parse_flow_log_file, aggregate_dependencies
            records = list(parse_flow_log_file(fl_file))
            net_deps = aggregate_dependencies(iter(records))
            db.insert_network_deps_batch(net_deps)

        progress_callback("graph_build", 0, 0.1, None)

        # Build graph
        backend = build_graph(db)
        if flowlog_content and db.get_network_dep_count() > 0:
            enrich_graph_with_network_deps(db, backend)

        # Classify and compute migration order
        dependencies = classify_all(backend)
        migration_steps = compute_migration_order(backend)
        has_cycles = backend.has_cycles()
        cycles = backend.get_cycles() if has_cycles else []

        # Collect graph metrics for the log
        nodes_data = [{"id": nid, **attrs} for nid, attrs in backend.get_nodes()]
        edges_data = [{"source": s, "target": t, **d} for s, t, d in backend.get_edges()]

        progress_callback("analysis", 1, 0.3, None)

        # Generate reports
        report_md = format_report(
            dependencies, migration_steps,
            limit=50, has_cycles=has_cycles, cycles=cycles,
        )

        # Export formats
        graph_mmd = export_mermaid(backend)
        graph_dot = export_dot(backend)

        # Build dependency JSON
        dependency_json = json.dumps(
            {"nodes": nodes_data, "edges": edges_data, "migration_order": migration_steps},
            indent=2,
        )

        # LLM review step
        progress_callback("review", 1, 0.5, None)
        review, review_usage = _call_review(
            client=anthropic_client,
            node_count=len(nodes_data),
            edge_count=len(edges_data),
            step_count=len(migration_steps),
            event_count=event_count,
            has_cycles=has_cycles,
            cycles=cycles,
            flowlog_provided=bool(flowlog_content),
            report_md=report_md,
        )

        # Dynamic confidence from reviewer
        issues = review.get("issues", [])
        final_confidence = ConfidenceCalculator.calculate(
            total_items=max(len(nodes_data), 1),
            mapped_count=len(nodes_data),
            issues=issues,
        )
        # Apply reviewer's raw confidence if provided and no issues override it
        reviewer_conf = review.get("confidence")
        if reviewer_conf is not None and not issues:
            final_confidence = float(reviewer_conf)

        final_decision_enum = ConfidenceCalculator.make_decision(final_confidence, issues)
        final_decision = final_decision_enum.value

        review_cost = calculate_cost(
            REVIEW_MODEL,
            tokens_input=review_usage["tokens_input"],
            tokens_output=review_usage["tokens_output"],
            tokens_cache_read=review_usage["tokens_cache_read"],
            tokens_cache_write=review_usage["tokens_cache_write"],
        ) or 0.0

        # Build orchestration log
        translation_log = _build_discovery_translation_log(
            session_start=session_start,
            event_count=event_count,
            node_count=len(nodes_data),
            edge_count=len(edges_data),
            step_count=len(migration_steps),
            has_cycles=has_cycles,
            flowlog_provided=bool(flowlog_content),
            review=review,
            final_confidence=final_confidence,
            final_decision=final_decision,
            review_cost=review_cost,
        )

        progress_callback("complete", 1, final_confidence, final_decision)

        artifacts = {
            "dependency.json": dependency_json,
            "graph.mmd": graph_mmd,
            "graph.dot": graph_dot,
            "report.md": report_md,
            "translation_log.md": translation_log,
        }

        db.close()

        interaction = {
            "agent_type": AgentType.REVIEW.value,
            "model": REVIEW_MODEL,
            "iteration": 1,
            "tokens_input": review_usage["tokens_input"],
            "tokens_output": review_usage["tokens_output"],
            "tokens_cache_read": review_usage["tokens_cache_read"],
            "tokens_cache_write": review_usage["tokens_cache_write"],
            "cost_usd": review_cost,
            "decision": final_decision,
            "confidence": final_confidence,
            "issues": issues,
            "duration_seconds": review_usage["duration_seconds"],
        }

        return {
            "artifacts": artifacts,
            "confidence": final_confidence,
            "decision": final_decision,
            "iterations": 1,
            "cost": review_cost,
            "interactions": [interaction],
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
