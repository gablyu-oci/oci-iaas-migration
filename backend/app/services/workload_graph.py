"""Per-workload dependency graph renderer using Graphviz.

Generates a styled SVG graph for each application group (workload)
showing its member resources and dependency edges between them.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

import graphviz

logger = logging.getLogger(__name__)

# Service -> (fillcolor, fontcolor, shape)
_SERVICE_STYLES: dict[str, tuple[str, str, str]] = {
    "EC2::Instance":       ("#ff8c00", "#000000", "box"),
    "EC2::Volume":         ("#228b22", "#ffffff", "box"),
    "RDS":                 ("#6a0dad", "#ffffff", "box"),
    "Lambda":              ("#00ced1", "#000000", "box"),
    "S3":                  ("#ff69b4", "#000000", "box"),
    "DynamoDB":            ("#ff1493", "#ffffff", "box"),
    "ElastiCache":         ("#dc143c", "#ffffff", "box"),
    "SQS":                 ("#ffd700", "#000000", "box"),
    "SNS":                 ("#ffd700", "#000000", "box"),
    "ECS":                 ("#4169e1", "#ffffff", "box"),
    "EKS":                 ("#4169e1", "#ffffff", "box"),
    "CloudFormation":      ("#808080", "#ffffff", "box"),
    "IAM":                 ("#8b0000", "#ffffff", "box"),
    "VPC":                 ("#add8e6", "#000000", "box"),
    "Subnet":              ("#add8e6", "#000000", "box"),
    "SecurityGroup":       ("#add8e6", "#000000", "box"),
    "LoadBalancer":        ("#32cd32", "#000000", "box"),
    "NetworkInterface":    ("#87ceeb", "#000000", "box"),
    "APIGateway":          ("#00ff00", "#000000", "box"),
    "SecretsManager":      ("#a9a9a9", "#000000", "box"),
}

# Edge type -> (color, style, penwidth)
_EDGE_STYLES: dict[str, tuple[str, str, str]] = {
    "network":    ("#ff4500", "solid", "2.0"),
    "cloudtrail": ("#ffa500", "solid", "1.5"),
    "attachment": ("#228b22", "dashed", "1.5"),
    "stack":      ("#808080", "dotted", "1.0"),
}


def _match_service(aws_type: str) -> tuple[str, str, str]:
    """Find best matching style for an AWS resource type."""
    for key, style in _SERVICE_STYLES.items():
        if key in aws_type:
            return style
    return ("#2f4f4f", "#ffffff", "box")


def _short_type(aws_type: str) -> str:
    """Extract short type name from AWS::Service::Resource."""
    parts = aws_type.replace("AWS::", "").split("::")
    if len(parts) >= 2:
        return parts[-1]
    return parts[0] if parts else aws_type


def _short_service(aws_type: str) -> str:
    """Extract service name from AWS::Service::Resource."""
    parts = aws_type.replace("AWS::", "").split("::")
    return parts[0] if parts else aws_type


def render_workload_graph(
    workload_name: str,
    resources: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    attachment_edges: list[dict[str, Any]] | None = None,
) -> str:
    """Render a workload dependency graph as SVG string.

    Args:
        workload_name: Display name for the graph title.
        resources: List of resource dicts with id, name, aws_type.
        edges: List of dependency edge dicts with source_resource_id,
               target_resource_id, edge_type, byte_count, protocol.
        attachment_edges: Optional structural edges (EBS->EC2, etc).

    Returns:
        SVG string of the rendered graph.
    """
    dot = graphviz.Digraph(
        name=workload_name,
        format="svg",
        engine="dot",
    )
    dot.attr(
        rankdir="LR",
        bgcolor="#0d1221",
        fontcolor="#e2e8f0",
        fontname="Helvetica",
        fontsize="14",
        label=f"  {workload_name}  ",
        labelloc="t",
        labeljust="l",
        pad="0.5",
        nodesep="0.8",
        ranksep="1.2",
    )
    dot.attr("node",
        fontname="Helvetica",
        fontsize="11",
        style="filled,rounded",
        penwidth="1.5",
        margin="0.15,0.1",
    )
    dot.attr("edge",
        fontname="Helvetica",
        fontsize="9",
        fontcolor="#94a3b8",
    )

    # Track resource IDs in this workload
    resource_ids = set()
    resource_map: dict[str, dict] = {}

    for r in resources:
        rid = str(r.get("id", ""))
        resource_ids.add(rid)
        resource_map[rid] = r

        aws_type = r.get("aws_type", "")
        name = r.get("name", "") or rid[:8]
        fill, font, shape = _match_service(aws_type)
        service = _short_service(aws_type)
        short = _short_type(aws_type)

        label = f"{service}\\n{name}" if name != rid[:8] else f"{service}\\n{short}"

        dot.node(
            rid,
            label=label,
            fillcolor=fill,
            fontcolor=font,
            shape=shape,
            color=fill,
        )

    # Dependency edges (network / cloudtrail)
    for edge in edges:
        src = str(edge.get("source_resource_id", ""))
        tgt = str(edge.get("target_resource_id", ""))
        if src not in resource_ids or tgt not in resource_ids:
            continue
        if src == tgt:
            continue

        edge_type = edge.get("edge_type", edge.get("protocol", "network"))
        color, style, pw = _EDGE_STYLES.get(edge_type, _EDGE_STYLES["network"])

        # Build label
        parts = []
        byte_count = edge.get("byte_count")
        if byte_count and byte_count > 0:
            if byte_count > 1_000_000_000:
                parts.append(f"{byte_count/1e9:.1f}GB")
            elif byte_count > 1_000_000:
                parts.append(f"{byte_count/1e6:.1f}MB")
            elif byte_count > 1000:
                parts.append(f"{byte_count/1e3:.0f}KB")

        flow_count = edge.get("flow_count") or edge.get("packet_count")
        if flow_count and flow_count > 1:
            parts.append(f"({int(flow_count)})")

        label = edge_type
        if parts:
            label += " " + " ".join(parts)

        dot.edge(src, tgt, label=label, color=color, style=style, penwidth=pw)

    # Structural edges (attachment, stack membership)
    for edge in (attachment_edges or []):
        src = str(edge.get("source", ""))
        tgt = str(edge.get("target", ""))
        if src not in resource_ids or tgt not in resource_ids:
            continue
        etype = edge.get("type", "attachment")
        color, style, pw = _EDGE_STYLES.get(etype, _EDGE_STYLES["attachment"])
        dot.edge(src, tgt, label=etype, color=color, style=style, penwidth=pw)

    try:
        svg = dot.pipe(format="svg").decode("utf-8")
        return svg
    except Exception as exc:
        logger.error("Graphviz render failed for workload '%s': %s", workload_name, exc)
        return ""


def build_workload_graphs(
    app_groups: list[dict],
    resource_by_id: dict[str, dict],
    dependency_edges: list[dict],
    discovery_graph: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build SVG graphs for all non-singleton workloads.

    Args:
        app_groups: List of group dicts from compute_app_groups().
        resource_by_id: Mapping of resource_id -> resource dict.
        dependency_edges: All dependency edges from the assessment.
        discovery_graph: Optional parsed dependency.json from the
            dependency_discovery pipeline (nodes, edges, migration_order).
            Enriches the graph with classified edge types and risk levels.

    Returns:
        Mapping of group_name -> SVG string.
    """
    # Extract discovery edges for enrichment
    discovery_edges = (discovery_graph or {}).get("edges", [])
    discovery_nodes = (discovery_graph or {}).get("nodes", [])

    graphs: dict[str, str] = {}

    for group in app_groups:
        name = group.get("name", "")
        rids = group.get("resource_ids", [])

        # Skip singletons
        if group.get("strategy") == "singleton" or len(rids) < 2:
            continue

        resources = [resource_by_id[rid] for rid in rids if rid in resource_by_id]

        # Build structural edges from raw_config (EBS attachments, etc.)
        rid_set = set(rids)
        attachment_edges: list[dict] = []

        # Find instance_id -> resource_id mapping within this group
        iid_to_rid: dict[str, str] = {}
        for r in resources:
            raw = r.get("raw_config") or {}
            iid = raw.get("instance_id") or raw.get("InstanceId")
            if iid:
                iid_to_rid[iid] = str(r.get("id", ""))

        for r in resources:
            rid = str(r.get("id", ""))
            raw = r.get("raw_config") or {}
            aws_type = r.get("aws_type", "")

            # EBS -> EC2 attachment
            if "Volume" in aws_type:
                for att in raw.get("attachments", raw.get("Attachments", [])):
                    att_iid = att.get("instance_id") or att.get("InstanceId")
                    if att_iid and att_iid in iid_to_rid:
                        target_rid = iid_to_rid[att_iid]
                        if target_rid in rid_set and target_rid != rid:
                            attachment_edges.append({
                                "source": rid,
                                "target": target_rid,
                                "type": "attachment",
                            })

        svg = render_workload_graph(
            workload_name=name,
            resources=resources,
            edges=dependency_edges,
            attachment_edges=attachment_edges,
        )
        if svg:
            graphs[name] = svg

    return graphs
