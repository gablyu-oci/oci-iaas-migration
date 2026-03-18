"""Click CLI for AWS Dependency Discovery."""

from __future__ import annotations

import json
from pathlib import Path

import click

from .config import get_db_path
from .graph.db import Database


@click.group()
@click.option("--db", "db_path", type=click.Path(), default=None,
              help="SQLite database path (default: ~/.aws-discovery/discovery.db)")
@click.pass_context
def cli(ctx: click.Context, db_path: str | None) -> None:
    """AWS Dependency Discovery — find undocumented service dependencies from CloudTrail logs
    and VPC Flow Logs."""
    ctx.ensure_object(dict)
    ctx.obj["db_path"] = Path(db_path) if db_path else get_db_path()


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def ingest(ctx: click.Context, path: str) -> None:
    """Ingest CloudTrail JSON/gzip files from a directory or file."""
    from .ingestion.cloudtrail import parse_cloudtrail_dir, parse_cloudtrail_file

    target = Path(path)
    db = Database(ctx.obj["db_path"])

    try:
        if target.is_dir():
            events = list(parse_cloudtrail_dir(target))
        else:
            events = list(parse_cloudtrail_file(target))

        count = db.insert_events_batch(events)
        click.echo(f"Ingested {count} events from {path}")
        click.echo(f"Total events in database: {db.get_event_count()}")
    finally:
        db.close()


@cli.command("ingest-flowlogs")
@click.argument("path", type=click.Path(exists=True))
@click.option("--min-bytes", default=0, type=int,
              help="Minimum bytes transferred to include a dependency (filter noise)")
@click.pass_context
def ingest_flowlogs(ctx: click.Context, path: str, min_bytes: int) -> None:
    """Ingest VPC Flow Log files from a directory or file.

    Supports v2-v5 format (space-delimited .log/.txt files, plain or gzipped).
    Aggregates network-level dependencies by (src, dst, port, protocol).
    """
    from .ingestion.flowlogs import (
        aggregate_dependencies,
        parse_flow_log_dir,
        parse_flow_log_file,
    )

    target = Path(path)
    db = Database(ctx.obj["db_path"])

    try:
        if target.is_dir():
            records = parse_flow_log_dir(target)
        else:
            records = parse_flow_log_file(target)

        deps = aggregate_dependencies(records, min_bytes=min_bytes)
        count = db.insert_network_deps_batch(deps)

        click.echo(f"Ingested {count} network dependencies from {path}")
        click.echo(f"Total network dependencies in database: {db.get_network_dep_count()}")
    finally:
        db.close()


@cli.command()
@click.option("--include-network/--no-network", default=True,
              help="Include VPC Flow Log network dependencies in the graph")
@click.pass_context
def graph(ctx: click.Context, include_network: bool) -> None:
    """Build dependency graph from ingested events."""
    from .graph.builder import build_graph, enrich_graph_with_network_deps

    db = Database(ctx.obj["db_path"])
    try:
        backend = build_graph(db)
        nodes = len(backend.get_nodes())
        edges = len(backend.get_edges())
        click.echo(f"Graph built: {nodes} nodes, {edges} edges (CloudTrail)")

        if include_network and db.get_network_dep_count() > 0:
            enrich_graph_with_network_deps(db, backend)
            new_nodes = len(backend.get_nodes())
            new_edges = len(backend.get_edges())
            click.echo(
                f"Enriched with network deps: {new_nodes} nodes, {new_edges} edges (total)"
            )

        if backend.has_cycles():
            cycles = backend.get_cycles()
            click.echo(f"WARNING: {len(cycles)} circular dependencies detected")
    finally:
        db.close()


@cli.command()
@click.option("--limit", default=20, help="Number of top dependencies to show")
@click.option("--ai", is_flag=True,
              help="Enable AI-powered summarization (requires ANTHROPIC_API_KEY)")
@click.pass_context
def report(ctx: click.Context, limit: int, ai: bool) -> None:
    """Print migration sequencing report."""
    from .analysis.classifier import classify_all, compute_migration_order
    from .graph.builder import build_graph, enrich_graph_with_network_deps
    from .output.report import format_report

    db = Database(ctx.obj["db_path"])
    try:
        backend = build_graph(db)

        if db.get_network_dep_count() > 0:
            enrich_graph_with_network_deps(db, backend)

        if len(backend.get_nodes()) == 0:
            click.echo("No data. Run 'discover ingest <path>' then 'discover graph' first.")
            return

        dependencies = classify_all(backend)
        migration_steps = compute_migration_order(backend)
        has_cycles = backend.has_cycles()
        cycles = backend.get_cycles() if has_cycles else []

        text = format_report(
            dependencies, migration_steps,
            limit=limit, has_cycles=has_cycles, cycles=cycles,
        )
        click.echo(text)

        if ai:
            from .analysis.llm import is_available, summarize_dependencies

            if not is_available():
                click.echo("\nANTHROPIC_API_KEY not set. Skipping AI summary.")
            else:
                network_deps = (
                    db.get_all_network_deps() if db.get_network_dep_count() > 0 else None
                )
                click.echo("\n" + "=" * 72)
                click.echo("  AI-POWERED MIGRATION BRIEF")
                click.echo("=" * 72 + "\n")
                summary = summarize_dependencies(
                    dependencies, migration_steps, network_deps
                )
                click.echo(summary)
    finally:
        db.close()


@cli.command()
@click.pass_context
def anomalies(ctx: click.Context) -> None:
    """AI-powered anomaly detection in dependency patterns (requires ANTHROPIC_API_KEY)."""
    from .analysis.classifier import classify_all
    from .analysis.llm import detect_anomalies, is_available
    from .graph.builder import build_graph, enrich_graph_with_network_deps

    if not is_available():
        click.echo("ANTHROPIC_API_KEY not set. This command requires AI capabilities.")
        return

    db = Database(ctx.obj["db_path"])
    try:
        backend = build_graph(db)

        if db.get_network_dep_count() > 0:
            enrich_graph_with_network_deps(db, backend)

        if len(backend.get_nodes()) == 0:
            click.echo("No data. Run 'discover ingest <path>' first.")
            return

        dependencies = classify_all(backend)
        network_deps = db.get_all_network_deps() if db.get_network_dep_count() > 0 else None

        click.echo("=" * 72)
        click.echo("  AI-POWERED ANOMALY DETECTION")
        click.echo("=" * 72 + "\n")
        result = detect_anomalies(dependencies, network_deps)
        click.echo(result)
    finally:
        db.close()


@cli.command()
@click.option("--output", "-o", "output_path", type=click.Path(), default=None,
              help="Output file (default: stdout)")
@click.pass_context
def runbook(ctx: click.Context, output_path: str | None) -> None:
    """AI-generated migration runbook with cutover steps (requires ANTHROPIC_API_KEY)."""
    from .analysis.classifier import classify_all, compute_migration_order
    from .analysis.llm import generate_runbook, is_available
    from .graph.builder import build_graph, enrich_graph_with_network_deps

    if not is_available():
        click.echo("ANTHROPIC_API_KEY not set. This command requires AI capabilities.")
        return

    db = Database(ctx.obj["db_path"])
    try:
        backend = build_graph(db)

        if db.get_network_dep_count() > 0:
            enrich_graph_with_network_deps(db, backend)

        if len(backend.get_nodes()) == 0:
            click.echo("No data. Run 'discover ingest <path>' first.")
            return

        dependencies = classify_all(backend)
        migration_steps = compute_migration_order(backend)
        network_deps = db.get_all_network_deps() if db.get_network_dep_count() > 0 else None

        click.echo("Generating migration runbook... (this may take a moment)")
        content = generate_runbook(dependencies, migration_steps, network_deps)

        if output_path:
            Path(output_path).write_text(content)
            click.echo(f"Runbook written to {output_path}")
        else:
            click.echo("\n" + "=" * 72)
            click.echo("  AI-GENERATED MIGRATION RUNBOOK")
            click.echo("=" * 72 + "\n")
            click.echo(content)
    finally:
        db.close()


@cli.command()
@click.option("--format", "fmt", type=click.Choice(["mermaid", "dot", "json"]),
              default="json", help="Export format")
@click.option("--output", "-o", "output_path", type=click.Path(), default=None,
              help="Output file (default: stdout)")
@click.pass_context
def export(ctx: click.Context, fmt: str, output_path: str | None) -> None:
    """Export dependency graph in various formats."""
    from .graph.builder import build_graph, enrich_graph_with_network_deps

    db = Database(ctx.obj["db_path"])
    try:
        backend = build_graph(db)

        if db.get_network_dep_count() > 0:
            enrich_graph_with_network_deps(db, backend)

        if fmt == "mermaid":
            from .output.mermaid import export_mermaid
            content = export_mermaid(backend)
        elif fmt == "dot":
            from .output.dot import export_dot
            content = export_dot(backend)
        else:
            # JSON export
            data = {
                "nodes": [
                    {"id": nid, **attrs} for nid, attrs in backend.get_nodes()
                ],
                "edges": [
                    {"source": s, "target": t, **d} for s, t, d in backend.get_edges()
                ],
            }
            net_deps = db.get_all_network_deps()
            if net_deps:
                data["network_dependencies"] = net_deps
            content = json.dumps(data, indent=2)

        if output_path:
            Path(output_path).write_text(content)
            click.echo(f"Exported {fmt} to {output_path}")
        else:
            click.echo(content)
    finally:
        db.close()


@cli.command()
@click.option("--service", required=True, help="Service name to query (e.g., lambda, s3, sts)")
@click.pass_context
def query(ctx: click.Context, service: str) -> None:
    """Query dependencies for a specific service."""
    from .graph.builder import build_graph, enrich_graph_with_network_deps

    db = Database(ctx.obj["db_path"])
    try:
        backend = build_graph(db)

        if db.get_network_dep_count() > 0:
            enrich_graph_with_network_deps(db, backend)

        # Find matching nodes
        matching = [
            (nid, data) for nid, data in backend.get_nodes()
            if data.get("service", "").lower() == service.lower()
            or service.lower() in nid.lower()
        ]

        if not matching:
            click.echo(f"No nodes found matching service '{service}'")
            return

        for node_id, data in matching:
            click.echo(f"\n{'=' * 60}")
            click.echo(f"  Service: {node_id}")
            click.echo(f"  Account: {data.get('account_id', 'unknown')}")
            click.echo(f"{'=' * 60}")

            # Incoming dependencies (what calls this service)
            preds = backend.get_predecessors(node_id)
            if preds:
                click.echo(f"\n  Depends ON this service ({len(preds)}):")
                for p in preds:
                    edge_data = {}
                    for s, t, d in backend.get_edges():
                        if s == p and t == node_id:
                            edge_data = d
                            break
                    freq = edge_data.get("frequency", "?")
                    etype = edge_data.get("edge_type", "?")
                    click.echo(f"    <- {p}  ({etype}, {freq}x)")

            # Outgoing dependencies (what this service calls)
            succs = backend.get_successors(node_id)
            if succs:
                click.echo(f"\n  This service DEPENDS on ({len(succs)}):")
                for s in succs:
                    edge_data = {}
                    for src, tgt, d in backend.get_edges():
                        if src == node_id and tgt == s:
                            edge_data = d
                            break
                    freq = edge_data.get("frequency", "?")
                    etype = edge_data.get("edge_type", "?")
                    click.echo(f"    -> {s}  ({etype}, {freq}x)")

            if not preds and not succs:
                click.echo("\n  No dependencies found for this service.")

        # Also show SQLite-persisted edges for drill-down
        db_edges = db.get_edges_for_service(service)
        if db_edges:
            click.echo(f"\n{'=' * 60}")
            click.echo(f"  Raw edge data from database ({len(db_edges)} edges):")
            click.echo(f"{'=' * 60}")
            for e in db_edges[:20]:
                click.echo(
                    f"  {e['source_node_id']} -> {e['target_node_id']} "
                    f"[{e['edge_type']}] x{e['frequency']} "
                    f"({e['direction']})"
                )
    finally:
        db.close()
