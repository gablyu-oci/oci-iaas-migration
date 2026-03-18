"""Deterministic dependency classification and migration sequencing."""

from __future__ import annotations

from dataclasses import dataclass

from ..graph.builder import GraphBackend


def _format_bytes(n: int) -> str:
    """Format byte count as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


@dataclass
class DependencyInfo:
    """Classified dependency with risk assessment."""

    source: str
    target: str
    edge_type: str
    frequency: int
    risk_level: str  # "critical", "high", "medium", "low"
    reason: str
    breaks_if_wrong: str  # what breaks if migration order is wrong


def classify_edge_risk(
    source: str, target: str, edge_data: dict
) -> DependencyInfo:
    """Classify a single edge's risk level based on type and frequency."""
    edge_type = edge_data.get("edge_type", "unknown")
    frequency = edge_data.get("frequency", 1)
    event_name = edge_data.get("event_name", "")

    # Cross-account detection
    src_acct = source.split(":")[0]
    tgt_acct = target.split(":")[0]
    is_cross_account = src_acct != tgt_acct and src_acct != "unknown" and tgt_acct != "unknown"

    if edge_type == "trust" and is_cross_account:
        return DependencyInfo(
            source=source,
            target=target,
            edge_type=edge_type,
            frequency=frequency,
            risk_level="critical",
            reason=f"Cross-account trust chain ({event_name}) — {source} assumes roles in {target}",
            breaks_if_wrong=(
                f"Services in {source.split(':')[1]} will lose access to "
                f"{target.split(':')[1]} resources after migration"
            ),
        )

    if edge_type == "sync_call":
        risk = "critical" if frequency >= 100 else "high" if frequency >= 10 else "medium"
        return DependencyInfo(
            source=source,
            target=target,
            edge_type=edge_type,
            frequency=frequency,
            risk_level=risk,
            reason=f"Synchronous invocation ({event_name}, {frequency}x observed)",
            breaks_if_wrong=(
                f"{source.split(':')[1]} calls {target.split(':')[1]} synchronously — "
                f"will fail immediately if target is unavailable"
            ),
        )

    if edge_type == "async":
        risk = "high" if frequency >= 50 else "medium"
        return DependencyInfo(
            source=source,
            target=target,
            edge_type=edge_type,
            frequency=frequency,
            risk_level=risk,
            reason=f"Async messaging dependency ({event_name}, {frequency}x observed)",
            breaks_if_wrong=(
                f"Messages from {source.split(':')[1]} to {target.split(':')[1]} "
                f"will be lost or undeliverable"
            ),
        )

    if edge_type == "data_read":
        risk = "high" if frequency >= 50 else "medium" if frequency >= 5 else "low"
        return DependencyInfo(
            source=source,
            target=target,
            edge_type=edge_type,
            frequency=frequency,
            risk_level=risk,
            reason=f"Data read dependency ({event_name}, {frequency}x observed)",
            breaks_if_wrong=(
                f"{source.split(':')[1]} reads from {target.split(':')[1]} — "
                f"data unavailability will cause failures"
            ),
        )

    if edge_type == "data_write":
        return DependencyInfo(
            source=source,
            target=target,
            edge_type=edge_type,
            frequency=frequency,
            risk_level="medium",
            reason=f"Data write dependency ({event_name}, {frequency}x observed)",
            breaks_if_wrong=(
                f"{source.split(':')[1]} writes to {target.split(':')[1]} — "
                f"write failures may cause data loss"
            ),
        )

    if edge_type == "trust":
        return DependencyInfo(
            source=source,
            target=target,
            edge_type=edge_type,
            frequency=frequency,
            risk_level="high",
            reason=f"Trust relationship ({event_name}, {frequency}x observed)",
            breaks_if_wrong=(
                f"IAM trust from {source.split(':')[1]} to {target.split(':')[1]} — "
                f"permissions will break if trust is not re-established"
            ),
        )

    if edge_type == "network":
        total_bytes = edge_data.get("total_bytes", 0)
        conn_count = edge_data.get("connection_count", frequency)
        # High-traffic network paths are critical — they indicate heavy data-plane coupling
        if total_bytes > 1_000_000_000:  # > 1GB
            risk = "critical"
        elif total_bytes > 100_000_000 or conn_count >= 1000:  # > 100MB or 1000+ connections
            risk = "high"
        elif conn_count >= 100:
            risk = "medium"
        else:
            risk = "low"

        bytes_str = _format_bytes(total_bytes)
        return DependencyInfo(
            source=source,
            target=target,
            edge_type=edge_type,
            frequency=frequency,
            risk_level=risk,
            reason=(
                f"Network-level dependency ({event_name}, {conn_count} connections, "
                f"{bytes_str} transferred) — discovered from VPC Flow Logs"
            ),
            breaks_if_wrong=(
                f"Direct network traffic from {source} to {target} "
                f"will fail if network path is not re-established after migration"
            ),
        )

    return DependencyInfo(
        source=source,
        target=target,
        edge_type=edge_type,
        frequency=frequency,
        risk_level="low",
        reason=f"Observed dependency ({event_name}, {frequency}x)",
        breaks_if_wrong="Unknown impact — review manually",
    )


def classify_all(backend: GraphBackend) -> list[DependencyInfo]:
    """Classify all edges in the graph."""
    results = []
    for src, tgt, data in backend.get_edges():
        results.append(classify_edge_risk(src, tgt, data))
    # Sort: critical first, then high, medium, low
    priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    results.sort(key=lambda d: (priority.get(d.risk_level, 4), -d.frequency))
    return results


def compute_migration_order(backend: GraphBackend) -> list[dict]:
    """Compute a migration ordering using topological sort.

    Returns a list of steps, each with the service and its dependencies.
    """
    order = backend.topological_sort()
    steps = []
    for i, node_id in enumerate(order, 1):
        parts = node_id.split(":", 1)
        account_id = parts[0] if len(parts) > 1 else "unknown"
        service = parts[1] if len(parts) > 1 else parts[0]

        deps = backend.get_predecessors(node_id)
        dependents = backend.get_successors(node_id)

        steps.append({
            "step": i,
            "node_id": node_id,
            "account_id": account_id,
            "service": service,
            "depends_on": deps,
            "depended_by": dependents,
        })

    return steps
