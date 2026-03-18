"""VPC Flow Logs parser for network-level dependency discovery.

Supports AWS VPC Flow Log v2-v5 formats (space-delimited text files).
Extracts IP-to-IP communication patterns that reveal data-plane dependencies
invisible to CloudTrail (e.g., direct DB connections, service mesh traffic).
"""

from __future__ import annotations

import csv
import gzip
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

# Well-known AWS service port ranges
SERVICE_PORT_MAP: dict[int, str] = {
    443: "https",
    80: "http",
    3306: "mysql/rds",
    5432: "postgres/rds",
    1521: "oracle/rds",
    1433: "mssql/rds",
    6379: "redis/elasticache",
    11211: "memcached/elasticache",
    27017: "mongodb/documentdb",
    9092: "kafka/msk",
    8443: "ecs/eks-api",
    2049: "efs/nfs",
    9200: "opensearch",
    9300: "opensearch-cluster",
    8080: "http-alt/app",
    8888: "http-alt/app",
    5439: "redshift",
    2484: "oracle-tls",
}

# Common ephemeral port range — traffic FROM these ports is usually a response
EPHEMERAL_LOW = 32768
EPHEMERAL_HIGH = 65535

# AWS internal IP ranges (approximate — link-local, metadata, DNS)
AWS_INTERNAL_PREFIXES = (
    "169.254.",  # link-local / metadata
    "127.",      # loopback
    "10.0.0.2",  # VPC DNS
)


@dataclass(frozen=True, slots=True)
class FlowRecord:
    """A normalized VPC Flow Log record."""

    version: int
    account_id: str
    interface_id: str
    src_addr: str
    dst_addr: str
    src_port: int
    dst_port: int
    protocol: int  # 6=TCP, 17=UDP, 1=ICMP
    packets: int
    bytes_transferred: int
    start_time: str
    end_time: str
    action: str  # ACCEPT or REJECT
    log_status: str  # OK, NODATA, SKIPDATA
    # Optional v3+ fields
    vpc_id: str
    subnet_id: str
    tcp_flags: int
    flow_direction: str  # ingress or egress


@dataclass(frozen=True, slots=True)
class NetworkDependency:
    """An aggregated network-level dependency between two endpoints."""

    src_addr: str
    dst_addr: str
    dst_port: int
    protocol: int
    service_guess: str  # best guess from port mapping
    total_bytes: int
    total_packets: int
    connection_count: int
    account_id: str
    vpc_id: str
    first_seen: str
    last_seen: str


def _is_aws_internal(addr: str) -> bool:
    """Check if an address is AWS-internal (metadata, DNS, loopback)."""
    return any(addr.startswith(p) for p in AWS_INTERNAL_PREFIXES)


def _is_ephemeral(port: int) -> bool:
    """Check if a port is in the ephemeral range."""
    return EPHEMERAL_LOW <= port <= EPHEMERAL_HIGH


def _guess_service(port: int) -> str:
    """Guess the service from a well-known port number."""
    return SERVICE_PORT_MAP.get(port, f"port-{port}")


def _parse_int(val: str, default: int = 0) -> int:
    """Safe int parse with default."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# Default v2 column order
V2_COLUMNS = [
    "version", "account-id", "interface-id", "srcaddr", "dstaddr",
    "srcport", "dstport", "protocol", "packets", "bytes",
    "start", "end", "action", "log-status",
]


def _parse_line(fields: list[str], columns: list[str]) -> FlowRecord | None:
    """Parse a single flow log line given column headers."""
    if len(fields) < len(columns):
        return None

    col_map = {columns[i]: fields[i] for i in range(len(columns))}

    action = col_map.get("action", "")
    log_status = col_map.get("log-status", "")

    # Skip non-OK or REJECT records for dependency mapping
    if log_status not in ("OK", ""):
        return None

    src_addr = col_map.get("srcaddr", "-")
    dst_addr = col_map.get("dstaddr", "-")
    if src_addr == "-" or dst_addr == "-":
        return None

    return FlowRecord(
        version=_parse_int(col_map.get("version", "2"), 2),
        account_id=col_map.get("account-id", ""),
        interface_id=col_map.get("interface-id", ""),
        src_addr=src_addr,
        dst_addr=dst_addr,
        src_port=_parse_int(col_map.get("srcport", "0")),
        dst_port=_parse_int(col_map.get("dstport", "0")),
        protocol=_parse_int(col_map.get("protocol", "0")),
        packets=_parse_int(col_map.get("packets", "0")),
        bytes_transferred=_parse_int(col_map.get("bytes", "0")),
        start_time=col_map.get("start", ""),
        end_time=col_map.get("end", ""),
        action=action,
        log_status=log_status,
        vpc_id=col_map.get("vpc-id", ""),
        subnet_id=col_map.get("subnet-id", ""),
        tcp_flags=_parse_int(col_map.get("tcp-flags", "0")),
        flow_direction=col_map.get("flow-direction", ""),
    )


def parse_flow_log_file(path: Path) -> Iterator[FlowRecord]:
    """Parse a VPC Flow Log text file (plain or gzipped).

    Supports both v2 default format and custom formats with header lines.
    """
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        first_line = f.readline().strip()
        if not first_line:
            return

        # Detect if first line is a header (contains column names)
        first_fields = first_line.split()
        if first_fields[0].isdigit():
            # No header — assume v2 default format
            columns = V2_COLUMNS
            record = _parse_line(first_fields, columns)
            if record is not None:
                yield record
        else:
            # First line is a header
            columns = [f.strip().lower() for f in first_fields]

        for line in f:
            line = line.strip()
            if not line:
                continue
            fields = line.split()
            record = _parse_line(fields, columns)
            if record is not None:
                yield record


def parse_flow_log_dir(directory: Path) -> Iterator[FlowRecord]:
    """Parse all flow log files in a directory (*.log, *.txt, *.log.gz, *.txt.gz)."""
    patterns = ["*.log", "*.txt", "*.log.gz", "*.txt.gz", "*.csv", "*.csv.gz"]
    for pattern in patterns:
        for path in sorted(directory.rglob(pattern)):
            yield from parse_flow_log_file(path)


def aggregate_dependencies(
    records: Iterator[FlowRecord],
    *,
    min_bytes: int = 0,
    accepted_only: bool = True,
) -> list[NetworkDependency]:
    """Aggregate flow records into network-level dependencies.

    Groups by (src_addr, dst_addr, dst_port, protocol) and aggregates
    byte/packet counts. Filters out AWS-internal traffic and ephemeral
    source ports.
    """
    agg: dict[tuple[str, str, int, int], dict] = {}

    for rec in records:
        # Skip REJECT if only tracking accepted
        if accepted_only and rec.action == "REJECT":
            continue

        # Skip AWS-internal traffic
        if _is_aws_internal(rec.src_addr) or _is_aws_internal(rec.dst_addr):
            continue

        # Use the destination port for keying (it identifies the service)
        # If dst_port is ephemeral, this is likely a response — skip
        if _is_ephemeral(rec.dst_port) and not _is_ephemeral(rec.src_port):
            continue

        key = (rec.src_addr, rec.dst_addr, rec.dst_port, rec.protocol)

        if key not in agg:
            agg[key] = {
                "total_bytes": 0,
                "total_packets": 0,
                "connection_count": 0,
                "account_id": rec.account_id,
                "vpc_id": rec.vpc_id,
                "first_seen": rec.start_time,
                "last_seen": rec.end_time,
            }

        entry = agg[key]
        entry["total_bytes"] += rec.bytes_transferred
        entry["total_packets"] += rec.packets
        entry["connection_count"] += 1
        if rec.start_time and (not entry["first_seen"] or rec.start_time < entry["first_seen"]):
            entry["first_seen"] = rec.start_time
        if rec.end_time and (not entry["last_seen"] or rec.end_time > entry["last_seen"]):
            entry["last_seen"] = rec.end_time

    results = []
    for (src, dst, port, proto), data in agg.items():
        if data["total_bytes"] < min_bytes:
            continue
        results.append(NetworkDependency(
            src_addr=src,
            dst_addr=dst,
            dst_port=port,
            protocol=proto,
            service_guess=_guess_service(port),
            total_bytes=data["total_bytes"],
            total_packets=data["total_packets"],
            connection_count=data["connection_count"],
            account_id=data["account_id"],
            vpc_id=data["vpc_id"],
            first_seen=data["first_seen"],
            last_seen=data["last_seen"],
        ))

    # Sort by total bytes descending (heaviest traffic first)
    results.sort(key=lambda d: d.total_bytes, reverse=True)
    return results
