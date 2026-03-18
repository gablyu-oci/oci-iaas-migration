"""Graphviz DOT format exporter."""

from __future__ import annotations

from ..graph.builder import GraphBackend

EDGE_STYLE = {
    "trust": 'style=dashed, color=red',
    "sync_call": 'color=blue',
    "async": 'style=dotted, color=green',
    "data_read": 'color=orange',
    "data_write": 'color=purple',
    "network": 'style=bold, color=brown',
}


def _sanitize_id(node_id: str) -> str:
    """Make a node ID safe for Graphviz DOT (must start with letter, no special chars)."""
    safe = node_id.replace(":", "_").replace("-", "_").replace("/", "_")
    safe = safe.replace("@", "_at_").replace(".", "_")
    # DOT IDs starting with a digit are ambiguous — prefix with 'n'
    if safe and safe[0].isdigit():
        safe = "n" + safe
    return safe


def export_dot(backend: GraphBackend) -> str:
    """Export the graph as a Graphviz DOT diagram."""
    lines = ["digraph aws_dependencies {", "    rankdir=LR;", "    node [shape=box];", ""]

    for node_id, data in backend.get_nodes():
        safe_id = _sanitize_id(node_id)
        service = data.get("service", node_id)
        account = data.get("account_id", "")
        label = f"{service}\\n({account})" if account and account != "unknown" else service
        lines.append(f'    {safe_id} [label="{label}"];')

    lines.append("")

    for src, tgt, data in backend.get_edges():
        safe_src = _sanitize_id(src)
        safe_tgt = _sanitize_id(tgt)
        edge_type = data.get("edge_type", "unknown")
        freq = data.get("frequency", 1)
        style = EDGE_STYLE.get(edge_type, "")
        label = f"{edge_type} x{freq}"
        attrs = f'label="{label}"'
        if style:
            attrs += f", {style}"
        lines.append(f"    {safe_src} -> {safe_tgt} [{attrs}];")

    lines.append("}")
    return "\n".join(lines)
