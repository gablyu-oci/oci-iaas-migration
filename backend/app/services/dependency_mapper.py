"""Network dependency mapper using VPC Flow Logs and CloudTrail."""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# CloudTrail event sources that indicate API-level dependencies between resources
_CLOUDTRAIL_TRACKED_SOURCES = {
    "lambda.amazonaws.com",
    "s3.amazonaws.com",
    "sqs.amazonaws.com",
    "sns.amazonaws.com",
    "dynamodb.amazonaws.com",
    "secretsmanager.amazonaws.com",
    "rds.amazonaws.com",
    "ec2.amazonaws.com",
    "ecs.amazonaws.com",
    "states.amazonaws.com",
    "kinesis.amazonaws.com",
}

FLOW_LOG_QUERY = """
stats sum(bytes) as byte_count, count(*) as flow_count by srcAddr, dstAddr, dstPort, protocol
| filter action = "ACCEPT"
| sort byte_count desc
| limit 500
"""

# Maximum time (seconds) to wait for CloudWatch Logs Insights query
_QUERY_TIMEOUT_SECONDS = 60
_QUERY_POLL_INTERVAL = 2


def _build_session(credentials: dict, region: str) -> boto3.Session:
    """Build a boto3 Session from a credentials dict."""
    return boto3.Session(
        aws_access_key_id=credentials.get("aws_access_key_id"),
        aws_secret_access_key=credentials.get("aws_secret_access_key"),
        aws_session_token=credentials.get("aws_session_token"),
        region_name=region,
    )


def _build_logs_client(credentials: dict, region: str):
    """Create CloudWatch Logs client."""
    session = _build_session(credentials, region)
    return session.client("logs")


def _build_ec2_client(credentials: dict, region: str):
    """Create EC2 client."""
    session = _build_session(credentials, region)
    return session.client("ec2")


def _get_flow_log_groups(ec2_client, vpc_ids: list[str]) -> list[str]:
    """Return CloudWatch log group names associated with VPC Flow Logs.

    Uses ``describe_flow_logs`` filtered by the given VPC resource IDs and
    only returns log groups for flow logs that deliver to CloudWatch Logs.
    """
    if not vpc_ids:
        return []

    log_groups: list[str] = []
    try:
        paginator = ec2_client.get_paginator("describe_flow_logs")
        for page in paginator.paginate(
            Filters=[{"Name": "resource-id", "Values": vpc_ids}]
        ):
            for fl in page.get("FlowLogs", []):
                # Only include flow logs that deliver to CloudWatch Logs
                dest_type = fl.get("LogDestinationType", "cloud-watch-logs")
                if dest_type == "cloud-watch-logs":
                    group_name = fl.get("LogGroupName")
                    if group_name and group_name not in log_groups:
                        log_groups.append(group_name)
    except (ClientError, BotoCoreError) as exc:
        logger.error("Failed to describe flow logs for VPCs %s: %s", vpc_ids, exc)

    return log_groups


def _build_ip_resource_map(resources: list[dict]) -> dict[str, str]:
    """Build a mapping from private IP address to resource ID.

    Inspects the ``raw_config`` of each resource for:
    - ``PrivateIpAddress`` (top-level)
    - ``NetworkInterfaces[].PrivateIpAddress``
    - ``NetworkInterfaces[].PrivateIpAddresses[].PrivateIpAddress``

    *resources* is expected to be a list of dicts with ``id`` and
    ``raw_config`` keys.
    """
    ip_map: dict[str, str] = {}

    for resource in resources:
        resource_id = resource.get("id", "")
        raw = resource.get("raw_config") or {}

        # Direct PrivateIpAddress field
        top_ip = raw.get("PrivateIpAddress") or raw.get("private_ip")
        if top_ip:
            ip_map[top_ip] = resource_id

        # Walk network interfaces
        for nic in raw.get("NetworkInterfaces", []):
            nic_ip = nic.get("PrivateIpAddress")
            if nic_ip:
                ip_map[nic_ip] = resource_id

            # Secondary private IPs
            for addr in nic.get("PrivateIpAddresses", []):
                addr_ip = addr.get("PrivateIpAddress")
                if addr_ip:
                    ip_map[addr_ip] = resource_id

    return ip_map


def _run_insights_query(
    logs_client,
    log_group_names: list[str],
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, str]]:
    """Execute a CloudWatch Logs Insights query and poll for results.

    Returns a list of rows, where each row is a dict mapping field names
    to their string values.
    """
    try:
        resp = logs_client.start_query(
            logGroupNames=log_group_names,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=FLOW_LOG_QUERY,
        )
    except (ClientError, BotoCoreError) as exc:
        logger.error("Failed to start Logs Insights query: %s", exc)
        return []

    query_id = resp["queryId"]
    deadline = time.monotonic() + _QUERY_TIMEOUT_SECONDS

    while time.monotonic() < deadline:
        try:
            result = logs_client.get_query_results(queryId=query_id)
        except (ClientError, BotoCoreError) as exc:
            logger.error("Error polling query results: %s", exc)
            return []

        status = result.get("status", "")
        if status == "Complete":
            rows: list[dict[str, str]] = []
            for entry in result.get("results", []):
                row = {field["field"]: field["value"] for field in entry}
                rows.append(row)
            return rows

        if status in ("Failed", "Cancelled"):
            logger.error("Logs Insights query %s ended with status: %s", query_id, status)
            return []

        time.sleep(_QUERY_POLL_INTERVAL)

    logger.warning("Logs Insights query %s timed out after %ds", query_id, _QUERY_TIMEOUT_SECONDS)
    return []


def _extract_resource_arns(resources: list[dict]) -> set[str]:
    """Collect ARNs from the resource list for CloudTrail lookup."""
    arns: set[str] = set()
    for r in resources:
        raw = r.get("raw_config") or {}
        for key in ("Arn", "arn", "aws_arn", "DBInstanceArn", "FunctionArn"):
            val = raw.get(key) or r.get(key)
            if val and isinstance(val, str) and val.startswith("arn:"):
                arns.add(val)
    return arns


# ---------------------------------------------------------------------------
# Live CloudTrail extraction → standard JSON format
# ---------------------------------------------------------------------------

def extract_cloudtrail_json(
    credentials: dict,
    region: str,
    lookback_days: int = 30,
    max_events: int = 5000,
) -> str:
    """Pull CloudTrail events via lookup_events and return standard JSON.

    Returns a JSON string in the CloudTrail format::

        {"Records": [{CloudTrail event}, ...]}

    This is the same format that ``parse_cloudtrail_file()`` in the
    dependency_discovery skill expects.
    """
    import json as _json

    session = _build_session(credentials, region)
    ct = session.client("cloudtrail")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=lookback_days)

    all_events: list[dict] = []
    try:
        paginator = ct.get_paginator("lookup_events")
        for page in paginator.paginate(
            StartTime=start_time,
            EndTime=end_time,
            PaginationConfig={"MaxItems": max_events, "PageSize": 50},
        ):
            for event in page.get("Events", []):
                # Each event has a CloudTrailEvent field with the full JSON
                raw_json = event.get("CloudTrailEvent")
                if raw_json:
                    try:
                        all_events.append(_json.loads(raw_json))
                    except (ValueError, TypeError):
                        pass
    except (ClientError, BotoCoreError) as exc:
        logger.warning("CloudTrail lookup_events failed: %s", exc)

    logger.info(
        "Extracted %d CloudTrail events from %s (last %d days)",
        len(all_events), region, lookback_days,
    )
    return _json.dumps({"Records": all_events})


def extract_flowlog_text(
    credentials: dict,
    region: str,
    vpc_ids: list[str],
    lookback_days: int = 14,
) -> str | None:
    """Pull raw VPC Flow Log entries from CloudWatch Logs.

    Returns the text content in standard VPC Flow Log format (one record
    per line) suitable for ``parse_flow_log_file()``, or None if no flow
    logs are available.
    """
    ec2_client = _build_ec2_client(credentials, region)
    log_groups = _get_flow_log_groups(ec2_client, vpc_ids)
    if not log_groups:
        return None

    logs_client = _build_logs_client(credentials, region)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=lookback_days)

    lines: list[str] = []
    try:
        for log_group in log_groups:
            paginator = logs_client.get_paginator("filter_log_events")
            for page in paginator.paginate(
                logGroupName=log_group,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                limit=10000,
            ):
                for event in page.get("events", []):
                    msg = event.get("message", "").strip()
                    if msg:
                        lines.append(msg)
    except (ClientError, BotoCoreError) as exc:
        logger.warning("Failed to extract flow log text: %s", exc)
        return None

    if not lines:
        return None

    logger.info("Extracted %d flow log lines from %d log group(s)", len(lines), len(log_groups))
    return "\n".join(lines)


def _discover_from_cloudtrail(
    credentials: dict,
    region: str,
    resources: list[dict],
    lookback_days: int = 30,
) -> list[dict]:
    """Pull recent CloudTrail management events and derive API-level dependency edges.

    Uses ``cloudtrail.lookup_events()`` which requires no S3 bucket or VPC Flow
    Log setup — it queries the last 90 days of management event history directly.

    Returns a list of dependency edge dicts compatible with the VPC flow log
    format (``source_resource_id`` / ``target_resource_id`` populated, byte_count=0).
    """
    session = _build_session(credentials, region)
    ct = session.client("cloudtrail")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=lookback_days)

    # Build lookup structures from resources
    resource_arns = _extract_resource_arns(resources)
    ip_map = _build_ip_resource_map(resources)

    # Also map resource IDs to resource DB ids
    resource_id_map: dict[str, str] = {}
    for r in resources:
        raw = r.get("raw_config") or {}
        db_id = str(r.get("id", ""))
        if not db_id:
            continue
        for key in ("InstanceId", "instance_id", "DBInstanceIdentifier",
                    "FunctionName", "BucketName", "QueueUrl"):
            val = raw.get(key)
            if val:
                resource_id_map[str(val)] = db_id
        # Also index by ARN
        for key in ("Arn", "arn", "aws_arn", "DBInstanceArn", "FunctionArn"):
            val = raw.get(key) or r.get(key)
            if val:
                resource_id_map[str(val)] = db_id

    all_events: list[dict] = []
    try:
        paginator = ct.get_paginator("lookup_events")
        for page in paginator.paginate(
            StartTime=start_time,
            EndTime=end_time,
            PaginationConfig={"MaxItems": 2000, "PageSize": 50},
        ):
            all_events.extend(page.get("Events", []))
    except (ClientError, BotoCoreError) as exc:
        logger.warning("CloudTrail lookup_events failed: %s", exc)
        return []

    logger.info("CloudTrail returned %d events for dependency analysis", len(all_events))

    # Build edges: caller ARN → affected resource
    edges: dict[tuple, dict] = {}
    for event in all_events:
        source_str = event.get("EventSource", "")
        if source_str not in _CLOUDTRAIL_TRACKED_SOURCES:
            continue

        # The principal that made the call
        username = event.get("Username", "")
        ct_resources = event.get("Resources") or []

        # Find which of our resources appear in this event
        affected_ids: list[str] = []
        for ct_res in ct_resources:
            arn = ct_res.get("ResourceName", "")
            if arn in resource_id_map:
                affected_ids.append(resource_id_map[arn])

        # If the caller matches a resource ARN, link caller → affected
        caller_id = resource_id_map.get(username)

        for target_id in affected_ids:
            if caller_id and caller_id != target_id:
                key = (caller_id, target_id)
                if key not in edges:
                    edges[key] = {
                        "source_ip": "",
                        "target_ip": "",
                        "port": 0,
                        "protocol": "cloudtrail",
                        "byte_count": 0.0,
                        "flow_count": 1,
                        "source_resource_id": caller_id,
                        "target_resource_id": target_id,
                    }
                else:
                    edges[key]["flow_count"] += 1

    result = list(edges.values())
    logger.info("Derived %d dependency edges from CloudTrail events", len(result))
    return result


def discover_dependencies(
    credentials: dict,
    region: str,
    vpc_ids: list[str],
    resources: list[dict],
) -> list[dict]:
    """Discover network dependencies from VPC Flow Logs.

    Returns a list of dependency edge dicts::

        {
            "source_ip": str,
            "target_ip": str,
            "port": int,
            "protocol": str,
            "byte_count": float,
            "flow_count": int,
            "source_resource_id": str | None,
            "target_resource_id": str | None,
        }

    Only edges where at least one side maps to a known resource are
    included.  If no flow logs are found, an empty list is returned.
    """
    ec2_client = _build_ec2_client(credentials, region)

    # Step 1: Resolve flow log groups for the given VPCs
    log_groups = _get_flow_log_groups(ec2_client, vpc_ids)
    if not log_groups:
        logger.warning(
            "No CloudWatch flow log groups found for VPCs %s; "
            "falling back to CloudTrail event history.",
            vpc_ids,
        )
        return _discover_from_cloudtrail(credentials, region, resources)

    logger.info("Found %d flow log group(s): %s", len(log_groups), log_groups)

    # Step 2: Run the Insights query over the last 14 days
    logs_client = _build_logs_client(credentials, region)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=14)

    rows = _run_insights_query(logs_client, log_groups, start_time, end_time)
    if not rows:
        logger.info("Flow log query returned no results.")
        return []

    # Step 3: Map IPs back to known resources
    ip_map = _build_ip_resource_map(resources)

    # Step 4: Build de-duplicated edge list
    # Key: (src_ip, dst_ip, port, protocol) -> aggregated values
    seen: dict[tuple, dict] = {}

    for row in rows:
        src_ip = row.get("srcAddr", "")
        dst_ip = row.get("dstAddr", "")
        port_str = row.get("dstPort", "0")
        protocol = row.get("protocol", "")
        byte_count_str = row.get("byte_count", "0")
        flow_count_str = row.get("flow_count", "0")

        try:
            port = int(port_str)
        except (ValueError, TypeError):
            port = 0
        try:
            byte_count = float(byte_count_str)
        except (ValueError, TypeError):
            byte_count = 0.0
        try:
            flow_count = int(flow_count_str)
        except (ValueError, TypeError):
            flow_count = 0

        src_resource = ip_map.get(src_ip)
        dst_resource = ip_map.get(dst_ip)

        # Only keep edges where at least one side is a known resource
        if not src_resource and not dst_resource:
            continue

        key = (src_ip, dst_ip, port, protocol)
        if key in seen:
            seen[key]["byte_count"] += byte_count
            seen[key]["flow_count"] += flow_count
        else:
            seen[key] = {
                "source_ip": src_ip,
                "target_ip": dst_ip,
                "port": port,
                "protocol": protocol,
                "byte_count": byte_count,
                "flow_count": flow_count,
                "source_resource_id": src_resource,
                "target_resource_id": dst_resource,
            }

    edges = list(seen.values())
    logger.info(
        "Discovered %d dependency edges from %d flow log rows",
        len(edges),
        len(rows),
    )

    # Supplement with CloudTrail API-level edges
    ct_edges = _discover_from_cloudtrail(credentials, region, resources)
    edges.extend(ct_edges)

    return edges
