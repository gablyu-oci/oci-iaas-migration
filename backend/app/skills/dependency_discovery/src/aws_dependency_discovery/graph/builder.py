"""Graph construction with swappable backend (GraphBackend ABC)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import networkx as nx

from .db import Database

# Map event types to edge classifications
EDGE_TYPE_MAP: dict[str, str] = {
    # Phase 1: original 7 event types
    "AssumeRole": "trust",
    "Invoke": "sync_call",
    "InvokeFunction": "sync_call",
    "Invoke20150331": "sync_call",
    "SendMessage": "async",
    "ReceiveMessage": "async",
    "GetObject": "data_read",
    "PutObject": "data_write",
    "GetSecretValue": "data_read",
    "Publish": "async",
    # Phase 2: DynamoDB
    "GetItem": "data_read",
    "PutItem": "data_write",
    "Query": "data_read",
    "Scan": "data_read",
    "UpdateItem": "data_write",
    "DeleteItem": "data_write",
    "BatchGetItem": "data_read",
    "BatchWriteItem": "data_write",
    # Phase 2: EventBridge
    "PutEvents": "async",
    "PutRule": "async",
    # Phase 2: KMS
    "Decrypt": "data_read",
    "Encrypt": "data_write",
    "GenerateDataKey": "data_read",
    # Phase 2: RDS / Aurora
    "CreateDBSnapshot": "data_write",
    # Phase 2: Step Functions
    "StartExecution": "sync_call",
    "SendTaskSuccess": "async",
    # Phase 2: ECS
    "RunTask": "sync_call",
    # Phase 2: Kinesis
    "PutRecord": "async",
    "PutRecords": "async",
    "GetRecords": "data_read",
}


def _make_node_id(account_id: str, service: str) -> str:
    """Create a composite node ID from account and service."""
    acct = account_id or "unknown"
    return f"{acct}:{service}"


class GraphBackend(ABC):
    """Abstract interface for graph backends — swap NetworkX for Neo4j/etc later."""

    @abstractmethod
    def add_node(self, node_id: str, **attrs: Any) -> None: ...

    @abstractmethod
    def add_edge(self, source: str, target: str, **attrs: Any) -> None: ...

    @abstractmethod
    def get_graph(self) -> Any: ...

    @abstractmethod
    def topological_sort(self) -> list[str]: ...

    @abstractmethod
    def get_predecessors(self, node_id: str) -> list[str]: ...

    @abstractmethod
    def get_successors(self, node_id: str) -> list[str]: ...

    @abstractmethod
    def get_nodes(self) -> list[tuple[str, dict]]: ...

    @abstractmethod
    def get_edges(self) -> list[tuple[str, str, dict]]: ...

    @abstractmethod
    def has_cycles(self) -> bool: ...

    @abstractmethod
    def get_cycles(self) -> list[list[str]]: ...


class NetworkXBackend(GraphBackend):
    """NetworkX-based graph backend."""

    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()

    def add_node(self, node_id: str, **attrs: Any) -> None:
        if self._graph.has_node(node_id):
            self._graph.nodes[node_id].update(attrs)
        else:
            self._graph.add_node(node_id, **attrs)

    def add_edge(self, source: str, target: str, **attrs: Any) -> None:
        if self._graph.has_edge(source, target):
            edge_data = self._graph.edges[source, target]
            edge_data["frequency"] = edge_data.get("frequency", 1) + 1
            if "last_seen" in attrs:
                edge_data["last_seen"] = max(
                    edge_data.get("last_seen", ""), attrs["last_seen"]
                )
        else:
            self._graph.add_edge(source, target, frequency=1, **attrs)

    def get_graph(self) -> nx.DiGraph:
        return self._graph

    def topological_sort(self) -> list[str]:
        try:
            return list(nx.topological_sort(self._graph))
        except nx.NetworkXUnfeasible:
            # Graph has cycles — break them and sort
            g = self._graph.copy()
            while True:
                try:
                    cycle = nx.find_cycle(g, orientation="original")
                    u, v, _ = cycle[-1]
                    g.remove_edge(u, v)
                except nx.NetworkXNoCycle:
                    break
            return list(nx.topological_sort(g))

    def get_predecessors(self, node_id: str) -> list[str]:
        if node_id not in self._graph:
            return []
        return list(self._graph.predecessors(node_id))

    def get_successors(self, node_id: str) -> list[str]:
        if node_id not in self._graph:
            return []
        return list(self._graph.successors(node_id))

    def get_nodes(self) -> list[tuple[str, dict]]:
        return list(self._graph.nodes(data=True))

    def get_edges(self) -> list[tuple[str, str, dict]]:
        return list(self._graph.edges(data=True))

    def has_cycles(self) -> bool:
        try:
            nx.find_cycle(self._graph, orientation="original")
            return True
        except nx.NetworkXNoCycle:
            return False

    def get_cycles(self) -> list[list[str]]:
        return list(nx.simple_cycles(self._graph))


def build_graph(db: Database, backend: GraphBackend | None = None) -> GraphBackend:
    """Build a dependency graph from events stored in the database.

    Persists nodes and edges back to SQLite and populates the in-memory graph backend.
    """
    if backend is None:
        backend = NetworkXBackend()

    rows = db.conn.execute(
        """SELECT event_source, event_name, source_account_id, source_principal,
                  target_resource, target_service, target_account_id, event_time
           FROM events ORDER BY event_time"""
    ).fetchall()

    for row in rows:
        source_service = row[0].split(".")[0]  # e.g. "sts" from "sts.amazonaws.com"
        event_name = row[1]
        source_account = row[2]
        target_service = row[5]
        target_account = row[6] or source_account
        event_time = row[7]
        target_resource = row[4]

        source_node_id = _make_node_id(source_account, source_service)
        target_node_id = _make_node_id(target_account, target_service)

        edge_type = EDGE_TYPE_MAP.get(event_name, "unknown")

        # Persist to SQLite
        db.upsert_node(source_node_id, source_account, source_service, event_time)
        db.upsert_node(target_node_id, target_account, target_service, event_time)
        db.upsert_edge(
            source_node_id, target_node_id, edge_type, event_name, event_time, target_resource
        )

        # Add to in-memory graph
        backend.add_node(source_node_id, account_id=source_account, service=source_service)
        backend.add_node(target_node_id, account_id=target_account, service=target_service)
        backend.add_edge(
            source_node_id,
            target_node_id,
            edge_type=edge_type,
            event_name=event_name,
            last_seen=event_time,
            sample_resource=target_resource,
        )

    db.commit()
    return backend


def enrich_graph_with_network_deps(db: Database, backend: GraphBackend) -> GraphBackend:
    """Enrich an existing dependency graph with VPC Flow Log network dependencies.

    Creates nodes like "10.0.1.50:postgres/rds" and edges with type "network".
    This reveals data-plane dependencies invisible to CloudTrail.
    """
    net_deps = db.get_all_network_deps()

    for dep in net_deps:
        src_addr = dep["src_addr"]
        dst_addr = dep["dst_addr"]
        service_guess = dep["service_guess"]
        account_id = dep.get("account_id", "")
        first_seen = dep.get("first_seen", "")
        total_bytes = dep.get("total_bytes", 0)
        connection_count = dep.get("connection_count", 1)

        # Create node IDs that encode the IP + service
        src_node_id = f"{account_id or 'unknown'}:{src_addr}"
        dst_node_id = f"{account_id or 'unknown'}:{service_guess}@{dst_addr}"

        backend.add_node(
            src_node_id,
            account_id=account_id,
            service=f"host:{src_addr}",
            node_type="network",
        )
        backend.add_node(
            dst_node_id,
            account_id=account_id,
            service=service_guess,
            node_type="network",
        )

        # Persist to SQLite
        db.upsert_node(src_node_id, account_id, f"host:{src_addr}", first_seen)
        db.upsert_node(dst_node_id, account_id, service_guess, first_seen)

        event_name = f"network:{dep['dst_port']}/{dep['protocol']}"
        db.upsert_edge(
            src_node_id, dst_node_id, "network", event_name,
            first_seen, f"{dst_addr}:{dep['dst_port']}",
        )

        backend.add_edge(
            src_node_id,
            dst_node_id,
            edge_type="network",
            event_name=event_name,
            last_seen=dep.get("last_seen", ""),
            sample_resource=f"{dst_addr}:{dep['dst_port']}",
            total_bytes=total_bytes,
            connection_count=connection_count,
        )

    db.commit()
    return backend
