"""Dependency Discovery orchestrator -- thin wrapper over src/ package."""
import json
import sys
import tempfile
import shutil
import time
from datetime import datetime
from pathlib import Path

SKILLS_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(SKILLS_ROOT / "shared"))

from agent_logger import AgentType, ReviewDecision, ConfidenceCalculator, calculate_cost

from app.gateway.model_gateway import get_model
_SKILL = "dependency_discovery"

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

RUNBOOK_SYSTEM = """\
You are an expert AWS-to-OCI migration engineer. Generate a comprehensive migration runbook
for moving the discovered AWS infrastructure to Oracle Cloud Infrastructure (OCI).

The runbook must be production-grade and include:

1. **Document Control** — maintenance window estimate, risk level, estimated downtime, rollback time
2. **Executive Summary** — what is being migrated, key risks, critical dependencies
3. **Pre-Migration Checklist** — prerequisites, validation steps, team notifications
4. **Migration Phases** (organize by dependency order — foundation first, compute last):
   - Phase name and timing (e.g., T+0→T+2h)
   - OCI service equivalents for each AWS service
   - Step-by-step migration commands/procedures
   - Validation checkpoints after each phase
   - Rollback procedure for each phase
5. **Cutover Procedure** — traffic switch, DNS updates, monitoring
6. **Post-Migration Validation** — smoke tests, performance checks
7. **Rollback Plan** — full rollback sequence if migration fails

Use concrete OCI service names (OCI Compute, OCI Object Storage, OCI NoSQL, OCI Database,
OCI Functions, OCI API Gateway, OCI Queue, OCI Notifications, VCN, NSG, etc.).

Format as Markdown with clear headers, tables, and code blocks.
Make it detailed enough for an on-call engineer to execute without additional context.
"""

ANOMALY_SYSTEM = """\
You are an expert AWS infrastructure security and reliability analyst.
Analyze the discovered dependency graph for anomalies, risks, and migration concerns.

Focus on:
1. **Data Quality Issues** — sample size limitations, collapsed/ambiguous edges, missing services
2. **Ghost Dependencies** — IP addresses with no CloudTrail attribution, unknown internal services
3. **Single Points of Failure** — resources accessed by 3+ services, god services, bottlenecks
4. **Security Concerns** — cross-account roles, unencrypted paths, unlogged services, stale data
5. **Data Consistency Risks** — dual-writes, lack of transaction patterns, cache invalidation
6. **Migration Sequencing Risks** — circular dependencies, undocumented external services
7. **Observability Gaps** — services with insufficient logging to understand traffic patterns

For each anomaly:
- Describe what was detected and why it's concerning
- Assess severity (CRITICAL / HIGH / MEDIUM / LOW)
- Provide specific recommendations

End with a prioritized migration sequencing recommendation (Phase 0 through Phase N).

Format as Markdown with clear sections and a summary risk table.
"""


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
        model=get_model(_SKILL, "review"),
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


def _call_runbook(
    client,
    nodes_data: list,
    edges_data: list,
    migration_steps: list,
    event_count: int,
    has_cycles: bool,
    flowlog_provided: bool,
    report_md: str,
) -> tuple[str, dict]:
    """Call LLM to generate a detailed migration runbook. Returns (runbook_md, usage_dict)."""
    # Build context for the runbook agent
    node_summary = "\n".join(
        f"- {n.get('id', n.get('name', 'unknown'))} ({n.get('service_type', n.get('type', 'unknown'))})"
        for n in nodes_data[:40]
    )
    if len(nodes_data) > 40:
        node_summary += f"\n- ... and {len(nodes_data) - 40} more resources"

    # Group migration steps by phase
    phase_summary = []
    for i, step in enumerate(migration_steps[:20], 1):
        if isinstance(step, dict):
            resources = step.get("resources", step.get("nodes", [step.get("node", "unknown")]))
            if isinstance(resources, str):
                resources = [resources]
            phase_summary.append(f"Phase {i}: {', '.join(str(r) for r in resources[:5])}")
        elif isinstance(step, (list, tuple)):
            phase_summary.append(f"Phase {i}: {', '.join(str(r) for r in step[:5])}")
        else:
            phase_summary.append(f"Phase {i}: {step}")

    context = (
        f"## Discovered Infrastructure\n\n"
        f"- Total resources: {len(nodes_data)}\n"
        f"- Total dependencies: {len(edges_data)}\n"
        f"- Migration phases: {len(migration_steps)}\n"
        f"- CloudTrail events analyzed: {event_count}\n"
        f"- VPC flow logs included: {'Yes' if flowlog_provided else 'No'}\n"
        f"- Circular dependencies: {'Yes' if has_cycles else 'No'}\n\n"
        f"## Resources Discovered\n\n{node_summary}\n\n"
        f"## Proposed Migration Order\n\n" + "\n".join(phase_summary) + "\n\n"
        f"## Dependency Analysis (excerpt)\n\n{report_md[:4000]}\n\n"
        f"Generate a comprehensive migration runbook for moving this AWS infrastructure to OCI."
    )

    start = time.perf_counter()
    response = client.messages.create(
        model=get_model(_SKILL, "review"),
        max_tokens=8192,
        system=RUNBOOK_SYSTEM,
        messages=[{"role": "user", "content": context}],
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

    runbook_md = response.content[0].text.strip()
    return runbook_md, usage


def _call_anomaly(
    client,
    nodes_data: list,
    edges_data: list,
    event_count: int,
    has_cycles: bool,
    cycles: list,
    flowlog_provided: bool,
    report_md: str,
) -> tuple[str, dict]:
    """Call LLM to generate anomaly and risk analysis. Returns (anomaly_md, usage_dict)."""
    # Summarize edges for anomaly detection
    edge_summary = "\n".join(
        f"- {e.get('source', '?')} → {e.get('target', '?')} ({e.get('type', e.get('dependency_type', 'unknown'))})"
        for e in edges_data[:50]
    )
    if len(edges_data) > 50:
        edge_summary += f"\n- ... and {len(edges_data) - 50} more dependencies"

    node_types: dict[str, int] = {}
    for n in nodes_data:
        svc = n.get("service_type", n.get("type", "unknown"))
        node_types[svc] = node_types.get(svc, 0) + 1

    context = (
        f"## Infrastructure Overview\n\n"
        f"- Total resources discovered: {len(nodes_data)}\n"
        f"- Total dependencies: {len(edges_data)}\n"
        f"- CloudTrail events analyzed: {event_count}\n"
        f"- VPC flow logs included: {'Yes' if flowlog_provided else 'No'}\n"
        f"- Circular dependencies detected: {'Yes' if has_cycles else 'No'}\n"
    )
    if has_cycles and cycles:
        cycle_strs = "; ".join(" → ".join(c) for c in cycles[:5])
        context += f"- Cycles: {cycle_strs}\n"

    context += f"\n## Service Type Distribution\n\n"
    for svc, count in sorted(node_types.items(), key=lambda x: -x[1]):
        context += f"- {svc}: {count} resource(s)\n"

    context += f"\n## Dependency Edges\n\n{edge_summary}\n\n"
    context += f"## Dependency Report (excerpt)\n\n{report_md[:4000]}\n\n"
    context += "Analyze this infrastructure for anomalies, risks, and migration concerns."

    start = time.perf_counter()
    response = client.messages.create(
        model=get_model(_SKILL, "review"),
        max_tokens=6144,
        system=ANOMALY_SYSTEM,
        messages=[{"role": "user", "content": context}],
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

    anomaly_md = response.content[0].text.strip()
    return anomaly_md, usage


def _build_readme(
    node_count: int,
    edge_count: int,
    step_count: int,
    event_count: int,
    has_cycles: bool,
    flowlog_provided: bool,
    final_decision: str,
    final_confidence: float,
    total_cost: float,
    session_start: float,
    review: dict,
) -> str:
    """Build an executive summary README for the discovery run."""
    duration = time.time() - session_start
    decision_icon = {"APPROVED": "✅", "APPROVED_WITH_NOTES": "⚠️", "NEEDS_FIXES": "❌"}.get(final_decision, "❓")
    issues = review.get("issues", [])
    high_issues = [i for i in issues if i.get("severity") in ("CRITICAL", "HIGH")]

    lines = [
        "# AWS → OCI Migration: Dependency Discovery Results",
        "",
        "## Summary",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Input | {event_count} CloudTrail events{', VPC Flow Logs' if flowlog_provided else ''} |",
        f"| Resources discovered | {node_count} |",
        f"| Dependencies mapped | {edge_count} |",
        f"| Migration phases | {step_count} |",
        f"| Circular dependencies | {'Yes' if has_cycles else 'No'} |",
        f"| Review decision | {decision_icon} {final_decision} |",
        f"| Confidence | {final_confidence:.0%} |",
        f"| Total cost | ${total_cost:.4f} |",
        f"| Analysis time | {duration:.0f}s |",
        "",
        "## Output Files",
        "",
        "| File | Description |",
        "|------|-------------|",
        "| `dependency.json` | Machine-readable dependency graph (nodes, edges, migration order) |",
        "| `graph.mmd` | Mermaid diagram for visualization |",
        "| `graph.dot` | Graphviz DOT format for rendering |",
        "| `migration-runbook.md` | Step-by-step migration runbook with OCI equivalents |",
        "| `anomaly-analysis.md` | Risk assessment and anomaly detection report |",
        "| `ORCHESTRATION-SUMMARY.md` | Agent execution log with token counts and costs |",
        "",
    ]

    if high_issues:
        lines += [
            "## Critical Risks",
            "",
        ]
        for issue in high_issues:
            lines.append(f"- **[{issue.get('severity')}]** {issue.get('description', '')}")
        lines.append("")

    review_summary = review.get("review_summary", "")
    if review_summary:
        lines += [
            "## Review Summary",
            "",
            review_summary,
            "",
        ]

    lines += [
        "## Next Steps",
        "",
        "1. Review `anomaly-analysis.md` to understand risks before proceeding",
        "2. Execute `migration-runbook.md` phases in order, validating after each",
        "3. Address all CRITICAL and HIGH issues before production cutover",
        "",
    ]

    return "\n".join(lines)


def _build_orchestration_summary(
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
    runbook_cost: float,
    anomaly_cost: float,
    review_usage: dict,
    runbook_usage: dict,
    anomaly_usage: dict,
) -> str:
    """Build orchestration summary log for the dependency discovery run."""
    duration = time.time() - session_start
    now = datetime.utcnow()
    session_id = f"discovery-{now.strftime('%Y%m%d-%H%M%S')}"
    total_cost = review_cost + runbook_cost + anomaly_cost

    def _tok(usage: dict) -> int:
        return (usage.get("tokens_input", 0) + usage.get("tokens_output", 0)
                + usage.get("tokens_cache_read", 0) + usage.get("tokens_cache_write", 0))

    total_tokens = _tok(review_usage) + _tok(runbook_usage) + _tok(anomaly_usage)

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
        f"# ORCHESTRATION-SUMMARY: {session_id}",
        "",
        f"**Project:** AWS → OCI Dependency Discovery",
        f"**Date:** {now.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"**Duration:** {duration:.1f}s (~{duration/60:.0f} min)",
        f"**Total Cost:** ${total_cost:.4f}",
        f"**Total Tokens:** {total_tokens:,}",
        "",
        "---",
        "",
        "## Final Status",
        "",
        f"**Decision:** {decision_icon} **{final_decision}**",
        f"**Confidence:** {final_confidence:.0%}",
        f"**Agent Calls:** 3 (Review, Runbook, Anomaly) + 1 deterministic pipeline",
        "",
        "---",
        "",
        "## Infrastructure Metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| CloudTrail events ingested | {event_count:,} |",
        f"| VPC Flow Logs included | {'Yes' if flowlog_provided else 'No'} |",
        f"| Resources (nodes) | {node_count} |",
        f"| Dependencies (edges) | {edge_count} |",
        f"| Migration phases | {step_count} |",
        f"| Circular dependencies | {'Yes' if has_cycles else 'No'} |",
        "",
        "---",
        "",
        "## Agent Execution Log",
        "",
        "### [0] INGESTION + GRAPH BUILD",
        "**Type:** Deterministic pipeline (no LLM)",
        f"**Input:** CloudTrail JSON ({event_count} events)" + (", VPC flow logs" if flowlog_provided else ""),
        f"**Output:** {node_count} nodes, {edge_count} edges, {step_count} migration phases",
        "",
        "### [1] REVIEW Agent",
        f"**Model:** {get_model(_SKILL, 'review')}",
        f"**Decision:** {final_decision}",
        f"**Confidence:** {final_confidence:.0%}",
        f"**Input tokens:** {review_usage.get('tokens_input', 0):,}",
        f"**Output tokens:** {review_usage.get('tokens_output', 0):,}",
        f"**Cache read:** {review_usage.get('tokens_cache_read', 0):,}",
        f"**Total tokens:** {_tok(review_usage):,}",
        f"**Cost:** ${review_cost:.4f}",
        f"**Duration:** {review_usage.get('duration_seconds', 0):.1f}s",
        "",
        "### [2] RUNBOOK Agent",
        f"**Model:** {get_model(_SKILL, 'review')}",
        "**Output:** migration-runbook.md",
        f"**Input tokens:** {runbook_usage.get('tokens_input', 0):,}",
        f"**Output tokens:** {runbook_usage.get('tokens_output', 0):,}",
        f"**Cache read:** {runbook_usage.get('tokens_cache_read', 0):,}",
        f"**Total tokens:** {_tok(runbook_usage):,}",
        f"**Cost:** ${runbook_cost:.4f}",
        f"**Duration:** {runbook_usage.get('duration_seconds', 0):.1f}s",
        "",
        "### [3] ANOMALY Agent",
        f"**Model:** {get_model(_SKILL, 'review')}",
        "**Output:** anomaly-analysis.md",
        f"**Input tokens:** {anomaly_usage.get('tokens_input', 0):,}",
        f"**Output tokens:** {anomaly_usage.get('tokens_output', 0):,}",
        f"**Cache read:** {anomaly_usage.get('tokens_cache_read', 0):,}",
        f"**Total tokens:** {_tok(anomaly_usage):,}",
        f"**Cost:** ${anomaly_cost:.4f}",
        f"**Duration:** {anomaly_usage.get('duration_seconds', 0):.1f}s",
        "",
        "---",
        "",
        "## Token Usage Summary",
        "",
        f"| Agent | Tokens | Cost |",
        f"|-------|--------|------|",
        f"| Review Agent | {_tok(review_usage):,} | ${review_cost:.4f} |",
        f"| Runbook Agent | {_tok(runbook_usage):,} | ${runbook_cost:.4f} |",
        f"| Anomaly Agent | {_tok(anomaly_usage):,} | ${anomaly_cost:.4f} |",
        f"| **Total** | **{total_tokens:,}** | **${total_cost:.4f}** |",
        "",
        "---",
        "",
        "## Review Issues",
        "",
    ]

    if issue_lines:
        lines += issue_lines + [""]
    else:
        lines += ["None identified.", ""]

    lines += [
        "---",
        "",
        "## Quality Assessment",
        "",
    ]
    if review.get("review_summary"):
        lines += [review["review_summary"], ""]

    return "\n".join(lines)


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

        # Generate dependency analysis report (used as context for LLM agents)
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

        # LLM Review step
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
            get_model(_SKILL, "review"),
            tokens_input=review_usage["tokens_input"],
            tokens_output=review_usage["tokens_output"],
            tokens_cache_read=review_usage["tokens_cache_read"],
            tokens_cache_write=review_usage["tokens_cache_write"],
        ) or 0.0

        # LLM Runbook Agent
        progress_callback("enhancement", 1, final_confidence, None)
        runbook_md, runbook_usage = _call_runbook(
            client=anthropic_client,
            nodes_data=nodes_data,
            edges_data=edges_data,
            migration_steps=migration_steps,
            event_count=event_count,
            has_cycles=has_cycles,
            flowlog_provided=bool(flowlog_content),
            report_md=report_md,
        )

        runbook_cost = calculate_cost(
            get_model(_SKILL, "review"),
            tokens_input=runbook_usage["tokens_input"],
            tokens_output=runbook_usage["tokens_output"],
            tokens_cache_read=runbook_usage["tokens_cache_read"],
            tokens_cache_write=runbook_usage["tokens_cache_write"],
        ) or 0.0

        # LLM Anomaly Agent
        anomaly_md, anomaly_usage = _call_anomaly(
            client=anthropic_client,
            nodes_data=nodes_data,
            edges_data=edges_data,
            event_count=event_count,
            has_cycles=has_cycles,
            cycles=cycles,
            flowlog_provided=bool(flowlog_content),
            report_md=report_md,
        )

        anomaly_cost = calculate_cost(
            get_model(_SKILL, "review"),
            tokens_input=anomaly_usage["tokens_input"],
            tokens_output=anomaly_usage["tokens_output"],
            tokens_cache_read=anomaly_usage["tokens_cache_read"],
            tokens_cache_write=anomaly_usage["tokens_cache_write"],
        ) or 0.0

        total_cost = review_cost + runbook_cost + anomaly_cost

        # Build orchestration summary
        orchestration_summary = _build_orchestration_summary(
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
            runbook_cost=runbook_cost,
            anomaly_cost=anomaly_cost,
            review_usage=review_usage,
            runbook_usage=runbook_usage,
            anomaly_usage=anomaly_usage,
        )

        # Build executive README
        readme_md = _build_readme(
            node_count=len(nodes_data),
            edge_count=len(edges_data),
            step_count=len(migration_steps),
            event_count=event_count,
            has_cycles=has_cycles,
            flowlog_provided=bool(flowlog_content),
            final_decision=final_decision,
            final_confidence=final_confidence,
            total_cost=total_cost,
            session_start=session_start,
            review=review,
        )

        progress_callback("complete", 1, final_confidence, final_decision)

        artifacts = {
            "dependency.json": dependency_json,
            "graph.mmd": graph_mmd,
            "graph.dot": graph_dot,
            "migration-runbook.md": runbook_md,
            "anomaly-analysis.md": anomaly_md,
            "README.md": readme_md,
            "ORCHESTRATION-SUMMARY.md": orchestration_summary,
        }

        db.close()

        interactions = [
            {
                "agent_type": AgentType.REVIEW.value,
                "model": get_model(_SKILL, "review"),
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
            },
            {
                "agent_type": "runbook",
                "model": get_model(_SKILL, "review"),
                "iteration": 1,
                "tokens_input": runbook_usage["tokens_input"],
                "tokens_output": runbook_usage["tokens_output"],
                "tokens_cache_read": runbook_usage["tokens_cache_read"],
                "tokens_cache_write": runbook_usage["tokens_cache_write"],
                "cost_usd": runbook_cost,
                "decision": None,
                "confidence": None,
                "duration_seconds": runbook_usage["duration_seconds"],
            },
            {
                "agent_type": "anomaly",
                "model": get_model(_SKILL, "review"),
                "iteration": 1,
                "tokens_input": anomaly_usage["tokens_input"],
                "tokens_output": anomaly_usage["tokens_output"],
                "tokens_cache_read": anomaly_usage["tokens_cache_read"],
                "tokens_cache_write": anomaly_usage["tokens_cache_write"],
                "cost_usd": anomaly_cost,
                "decision": None,
                "confidence": None,
                "duration_seconds": anomaly_usage["duration_seconds"],
            },
        ]

        return {
            "artifacts": artifacts,
            "confidence": final_confidence,
            "decision": final_decision,
            "iterations": 1,
            "cost": total_cost,
            "interactions": interactions,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_graph_only(
    input_content: str,
    flowlog_content: str | None,
    anthropic_client,
) -> dict:
    """Run dependency discovery pipeline: graph + LLM review only.

    Same as ``run()`` but skips the runbook and anomaly LLM agents.
    Returns graph artifacts (dependency.json, graph.mmd, graph.dot) and
    the review agent's confidence/decision.
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

    tmp_dir = Path(tempfile.mkdtemp(prefix="oci-discovery-"))
    db_path = tmp_dir / "discovery.db"

    try:
        # Parse CloudTrail
        events = json.loads(input_content)
        if isinstance(events, dict) and "Records" in events:
            events = events["Records"]
        event_count = len(events)

        ct_file = tmp_dir / "cloudtrail.json"
        ct_file.write_text(json.dumps({"Records": events}))

        db = Database(db_path)
        ct_events = list(parse_cloudtrail_file(ct_file))
        db.insert_events_batch(ct_events)

        # Ingest flow logs if provided
        if flowlog_content:
            fl_file = tmp_dir / "flowlogs.log"
            fl_file.write_text(flowlog_content)
            from aws_dependency_discovery.ingestion.flowlogs import (
                parse_flow_log_file,
                aggregate_dependencies,
            )
            records = list(parse_flow_log_file(fl_file))
            net_deps = aggregate_dependencies(iter(records))
            db.insert_network_deps_batch(net_deps)

        # Build graph
        backend = build_graph(db)
        if flowlog_content and db.get_network_dep_count() > 0:
            enrich_graph_with_network_deps(db, backend)

        # Classify and order
        dependencies = classify_all(backend)
        migration_steps = compute_migration_order(backend)
        has_cycles = backend.has_cycles()
        cycles = backend.get_cycles() if has_cycles else []

        nodes_data = [{"id": nid, **attrs} for nid, attrs in backend.get_nodes()]
        edges_data = [{"source": s, "target": t, **d} for s, t, d in backend.get_edges()]

        # Generate report for review context
        report_md = format_report(
            dependencies, migration_steps,
            limit=50, has_cycles=has_cycles, cycles=cycles,
        )

        # Export formats
        graph_mmd = export_mermaid(backend)
        graph_dot = export_dot(backend)
        dependency_json = json.dumps(
            {"nodes": nodes_data, "edges": edges_data, "migration_order": migration_steps},
            indent=2,
        )

        # LLM Review agent only (no runbook, no anomaly)
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

        issues = review.get("issues", [])
        final_confidence = ConfidenceCalculator.calculate(
            total_items=max(len(nodes_data), 1),
            mapped_count=len(nodes_data),
            issues=issues,
        )
        reviewer_conf = review.get("confidence")
        if reviewer_conf is not None and not issues:
            final_confidence = float(reviewer_conf)

        final_decision = ConfidenceCalculator.make_decision(final_confidence, issues).value

        review_cost = calculate_cost(
            get_model(_SKILL, "review"),
            tokens_input=review_usage["tokens_input"],
            tokens_output=review_usage["tokens_output"],
            tokens_cache_read=review_usage["tokens_cache_read"],
            tokens_cache_write=review_usage["tokens_cache_write"],
        ) or 0.0

        db.close()

        artifacts = {
            "dependency.json": dependency_json,
            "graph.mmd": graph_mmd,
            "graph.dot": graph_dot,
        }

        return {
            "artifacts": artifacts,
            "confidence": final_confidence,
            "decision": final_decision,
            "cost": review_cost,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
