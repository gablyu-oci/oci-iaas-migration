"""SQLite persistence for events, nodes, and edges."""

from __future__ import annotations

import sqlite3
from importlib import resources as pkg_resources
from pathlib import Path

from ..ingestion.flowlogs import NetworkDependency
from ..ingestion.normalizer import NormalizedEvent


def _get_schema_sql() -> str:
    """Read the schema.sql file from the package."""
    ref = pkg_resources.files("aws_dependency_discovery.graph").joinpath("schema.sql")
    return ref.read_text(encoding="utf-8")


class Database:
    """SQLite wrapper for dependency discovery data."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(_get_schema_sql())

    def insert_event(self, ev: NormalizedEvent) -> None:
        """Insert a normalized event, ignoring duplicates."""
        self.conn.execute(
            """INSERT OR IGNORE INTO events
               (event_id, event_time, event_source, event_name,
                source_account_id, source_principal, target_resource,
                target_service, target_account_id, region, raw_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ev.event_id,
                ev.event_time,
                ev.event_source,
                ev.event_name,
                ev.source_account_id,
                ev.source_principal,
                ev.target_resource,
                ev.target_service,
                ev.target_account_id,
                ev.region,
                ev.raw_json,
            ),
        )

    def insert_events_batch(self, events: list[NormalizedEvent]) -> int:
        """Insert a batch of events. Returns count inserted."""
        count = 0
        for ev in events:
            self.insert_event(ev)
            count += 1
        self.conn.commit()
        return count

    def upsert_node(self, node_id: str, account_id: str, service: str, event_time: str) -> None:
        """Insert or update a graph node."""
        self.conn.execute(
            """INSERT INTO nodes (node_id, account_id, service, first_seen, last_seen, event_count)
               VALUES (?, ?, ?, ?, ?, 1)
               ON CONFLICT(node_id) DO UPDATE SET
                   last_seen = MAX(excluded.last_seen, nodes.last_seen),
                   first_seen = MIN(excluded.first_seen, nodes.first_seen),
                   event_count = nodes.event_count + 1""",
            (node_id, account_id, service, event_time, event_time),
        )

    def upsert_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        event_name: str,
        event_time: str,
        sample_resource: str,
    ) -> None:
        """Insert or update a graph edge."""
        self.conn.execute(
            """INSERT INTO edges
               (source_node_id, target_node_id, edge_type, event_name,
                frequency, first_seen, last_seen, sample_resource)
               VALUES (?, ?, ?, ?, 1, ?, ?, ?)
               ON CONFLICT(source_node_id, target_node_id, edge_type, event_name) DO UPDATE SET
                   frequency = edges.frequency + 1,
                   last_seen = MAX(excluded.last_seen, edges.last_seen),
                   first_seen = MIN(excluded.first_seen, edges.first_seen)""",
            (source_node_id, target_node_id, edge_type, event_name, event_time, event_time,
             sample_resource),
        )

    def get_all_nodes(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM nodes ORDER BY event_count DESC").fetchall()
        return [dict(r) for r in rows]

    def get_all_edges(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM edges ORDER BY frequency DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_edges_for_service(self, service: str) -> list[dict]:
        """Get all edges where the service appears as source or target."""
        rows = self.conn.execute(
            """SELECT e.*, 'outgoing' as direction FROM edges e
               JOIN nodes n ON e.source_node_id = n.node_id
               WHERE n.service = ?
               UNION ALL
               SELECT e.*, 'incoming' as direction FROM edges e
               JOIN nodes n ON e.target_node_id = n.node_id
               WHERE n.service = ?
               ORDER BY frequency DESC""",
            (service, service),
        ).fetchall()
        return [dict(r) for r in rows]

    def insert_network_dep(self, dep: NetworkDependency) -> None:
        """Insert or update a network dependency from VPC Flow Logs."""
        self.conn.execute(
            """INSERT INTO network_deps
               (src_addr, dst_addr, dst_port, protocol, service_guess,
                total_bytes, total_packets, connection_count,
                account_id, vpc_id, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(src_addr, dst_addr, dst_port, protocol) DO UPDATE SET
                   total_bytes = network_deps.total_bytes + excluded.total_bytes,
                   total_packets = network_deps.total_packets + excluded.total_packets,
                   connection_count = network_deps.connection_count + excluded.connection_count,
                   first_seen = MIN(network_deps.first_seen, excluded.first_seen),
                   last_seen = MAX(network_deps.last_seen, excluded.last_seen)""",
            (
                dep.src_addr, dep.dst_addr, dep.dst_port, dep.protocol,
                dep.service_guess, dep.total_bytes, dep.total_packets,
                dep.connection_count, dep.account_id, dep.vpc_id,
                dep.first_seen, dep.last_seen,
            ),
        )

    def insert_network_deps_batch(self, deps: list[NetworkDependency]) -> int:
        """Insert a batch of network dependencies. Returns count inserted."""
        count = 0
        for dep in deps:
            self.insert_network_dep(dep)
            count += 1
        self.conn.commit()
        return count

    def get_all_network_deps(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM network_deps ORDER BY total_bytes DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_network_dep_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM network_deps").fetchone()
        return row[0]

    def get_event_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM events").fetchone()
        return row[0]

    def get_node_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
        return row[0]

    def get_edge_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        return row[0]

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
