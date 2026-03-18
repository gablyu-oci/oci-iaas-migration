"""Dependency Discovery orchestrator -- thin wrapper over src/ package."""
import json
import tempfile
import shutil
from pathlib import Path

SKILLS_ROOT = Path(__file__).parent.parent.resolve()


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
        anthropic_client: Anthropic client instance (unused by deterministic pipeline)
        max_iterations: Max review iterations (unused by deterministic pipeline)

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

    try:
        progress_callback("ingestion", 0, 0.0, None)

        # Parse CloudTrail input
        events = json.loads(input_content)
        if isinstance(events, dict) and "Records" in events:
            events = events["Records"]

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
        nodes_data = [{"id": nid, **attrs} for nid, attrs in backend.get_nodes()]
        edges_data = [{"source": s, "target": t, **d} for s, t, d in backend.get_edges()]
        dependency_json = json.dumps(
            {"nodes": nodes_data, "edges": edges_data, "migration_order": migration_steps},
            indent=2,
        )

        progress_callback("complete", 1, 0.85, "APPROVED")

        artifacts = {
            "dependency.json": dependency_json,
            "graph.mmd": graph_mmd,
            "graph.dot": graph_dot,
            "report.md": report_md,
        }

        db.close()

        return {
            "artifacts": artifacts,
            "confidence": 0.85,
            "decision": "APPROVED",
            "iterations": 1,
            "cost": 0.0,
            "interactions": [],
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
