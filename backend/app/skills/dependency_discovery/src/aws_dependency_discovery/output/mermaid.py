"""Mermaid diagram exporter."""

from __future__ import annotations

from ..graph.builder import GraphBackend

EDGE_STYLE = {
    "trust": "-.->",
    "sync_call": "-->",
    "async": "-..->",
    "data_read": "-->",
    "data_write": "-->",
    "network": "==>",
}

EDGE_LABEL_PREFIX = {
    "trust": "trust",
    "sync_call": "call",
    "async": "async",
    "data_read": "read",
    "data_write": "write",
    "network": "net",
}


def _sanitize_id(node_id: str) -> str:
    """Make a node ID safe for Mermaid."""
    return node_id.replace(":", "_").replace("-", "_").replace("/", "_")


def export_mermaid(backend: GraphBackend) -> str:
    """Export the graph as a Mermaid flowchart."""
    lines = ["graph LR"]

    # Add nodes
    for node_id, data in backend.get_nodes():
        safe_id = _sanitize_id(node_id)
        service = data.get("service", node_id)
        account = data.get("account_id", "")
        label = f"{service}"
        if account and account != "unknown":
            label = f"{service}\\n({account})"
        lines.append(f"    {safe_id}[\"{label}\"]")

    # Add edges
    for src, tgt, data in backend.get_edges():
        safe_src = _sanitize_id(src)
        safe_tgt = _sanitize_id(tgt)
        edge_type = data.get("edge_type", "unknown")
        arrow = EDGE_STYLE.get(edge_type, "-->")
        freq = data.get("frequency", 1)
        label = EDGE_LABEL_PREFIX.get(edge_type, edge_type)
        lines.append(f"    {safe_src} {arrow}|{label} x{freq}| {safe_tgt}")

    return "\n".join(lines)
