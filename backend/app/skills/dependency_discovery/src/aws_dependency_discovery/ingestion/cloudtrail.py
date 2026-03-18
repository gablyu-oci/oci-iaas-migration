"""CloudTrail JSON/gzip streaming parser."""

from __future__ import annotations

import gzip
import json
import uuid
from pathlib import Path
from typing import Iterator

from .normalizer import NormalizedEvent

# Tracked event types — Phase 1 originals + Phase 2 additions
TRACKED_EVENTS: dict[str, set[str]] = {
    # Phase 1
    "sts.amazonaws.com": {"AssumeRole"},
    "lambda.amazonaws.com": {"Invoke", "InvokeFunction", "Invoke20150331"},
    "sqs.amazonaws.com": {"SendMessage", "ReceiveMessage"},
    "s3.amazonaws.com": {"GetObject", "PutObject"},
    "secretsmanager.amazonaws.com": {"GetSecretValue"},
    "execute-api.amazonaws.com": {"Invoke"},
    "sns.amazonaws.com": {"Publish"},
    # Phase 2: DynamoDB
    "dynamodb.amazonaws.com": {
        "GetItem", "PutItem", "Query", "Scan",
        "UpdateItem", "DeleteItem", "BatchGetItem", "BatchWriteItem",
    },
    # Phase 2: EventBridge
    "events.amazonaws.com": {"PutEvents", "PutRule"},
    # Phase 2: KMS
    "kms.amazonaws.com": {"Decrypt", "Encrypt", "GenerateDataKey"},
    # Phase 2: RDS
    "rds.amazonaws.com": {"CreateDBSnapshot"},
    # Phase 2: Step Functions
    "states.amazonaws.com": {"StartExecution", "SendTaskSuccess"},
    # Phase 2: ECS
    "ecs.amazonaws.com": {"RunTask"},
    # Phase 2: Kinesis
    "kinesis.amazonaws.com": {"PutRecord", "PutRecords", "GetRecords"},
}


def _service_from_event_source(event_source: str) -> str:
    """Extract short service name from event source domain."""
    return event_source.split(".")[0]


def _extract_account_from_arn(arn: str) -> str:
    """Extract account ID from an ARN string."""
    # arn:aws:service:region:account-id:resource
    parts = arn.split(":")
    if len(parts) >= 5 and parts[4]:
        return parts[4]
    return ""


def _extract_target(event: dict) -> tuple[str, str, str]:
    """Extract target resource ARN, service, and account from a CloudTrail event.

    Returns (target_resource, target_service, target_account_id).
    """
    event_source = event.get("eventSource", "")
    event_name = event.get("eventName", "")
    params = event.get("requestParameters") or {}
    resources = event.get("resources") or []

    service = _service_from_event_source(event_source)

    # Try to get target from resources list first
    for r in resources:
        arn = r.get("ARN", r.get("arn", ""))
        acct = r.get("accountId", _extract_account_from_arn(arn))
        if arn:
            return arn, service, acct

    # Service-specific extraction
    if service == "sts" and event_name == "AssumeRole":
        role_arn = params.get("roleArn", "")
        return role_arn, "sts", _extract_account_from_arn(role_arn)

    if service == "lambda":
        func = params.get("functionName", "")
        if func.startswith("arn:"):
            return func, "lambda", _extract_account_from_arn(func)
        return func, "lambda", ""

    if service == "sqs":
        queue_url = params.get("queueUrl", "")
        return queue_url, "sqs", ""

    if service == "s3":
        bucket = params.get("bucketName", "")
        key = params.get("key", "")
        resource = f"s3://{bucket}/{key}" if key else f"s3://{bucket}"
        return resource, "s3", ""

    if service == "secretsmanager":
        secret_id = params.get("secretId", "")
        return secret_id, "secretsmanager", ""

    if service == "sns":
        topic_arn = params.get("topicArn", params.get("targetArn", ""))
        return topic_arn, "sns", _extract_account_from_arn(topic_arn)

    if service == "execute-api":
        return event_source, "execute-api", ""

    # Phase 2: DynamoDB
    if service == "dynamodb":
        table_name = params.get("tableName", "")
        table_arn = params.get("tableArn", "")
        if table_arn:
            return table_arn, "dynamodb", _extract_account_from_arn(table_arn)
        return table_name, "dynamodb", ""

    # Phase 2: EventBridge
    if service == "events":
        bus_name = params.get("eventBusName", "default")
        entries = params.get("entries", [])
        if entries and isinstance(entries, list):
            bus_name = entries[0].get("eventBusName", bus_name) if entries[0] else bus_name
        return bus_name, "events", ""

    # Phase 2: KMS
    if service == "kms":
        key_id = params.get("keyId", "")
        if key_id.startswith("arn:"):
            return key_id, "kms", _extract_account_from_arn(key_id)
        return key_id, "kms", ""

    # Phase 2: Step Functions
    if service == "states":
        sm_arn = params.get("stateMachineArn", "")
        exec_arn = params.get("executionArn", "")
        arn = sm_arn or exec_arn
        if arn:
            return arn, "states", _extract_account_from_arn(arn)
        return "", "states", ""

    # Phase 2: ECS
    if service == "ecs":
        cluster = params.get("cluster", "")
        task_def = params.get("taskDefinition", "")
        resource = task_def or cluster
        if resource.startswith("arn:"):
            return resource, "ecs", _extract_account_from_arn(resource)
        return resource, "ecs", ""

    # Phase 2: Kinesis
    if service == "kinesis":
        stream_name = params.get("streamName", "")
        stream_arn = params.get("streamARN", "")
        if stream_arn:
            return stream_arn, "kinesis", _extract_account_from_arn(stream_arn)
        return stream_name, "kinesis", ""

    # Phase 2: RDS
    if service == "rds":
        db_id = params.get("dBInstanceIdentifier", params.get("dBClusterIdentifier", ""))
        return db_id, "rds", ""

    return "", service, ""


def _normalize_event(event: dict) -> NormalizedEvent | None:
    """Convert a raw CloudTrail event dict to a NormalizedEvent, or None if not tracked."""
    event_source = event.get("eventSource", "")
    event_name = event.get("eventName", "")

    tracked = TRACKED_EVENTS.get(event_source)
    if tracked is None or event_name not in tracked:
        return None

    # Skip failed events
    error_code = event.get("errorCode")
    if error_code:
        return None

    user_identity = event.get("userIdentity", {})
    source_account = user_identity.get("accountId", "")
    source_principal = user_identity.get("arn", "")

    # For assumed roles, prefer the session issuer ARN
    if user_identity.get("type") == "AssumedRole":
        session_ctx = user_identity.get("sessionContext", {})
        session_issuer = session_ctx.get("sessionIssuer", {})
        if session_issuer.get("arn"):
            source_principal = session_issuer["arn"]

    target_resource, target_service, target_account = _extract_target(event)

    if not target_account:
        target_account = source_account

    return NormalizedEvent(
        event_id=event.get("eventID", str(uuid.uuid4())),
        event_time=event.get("eventTime", ""),
        event_source=event_source,
        event_name=event_name,
        source_account_id=source_account,
        source_principal=source_principal,
        target_resource=target_resource,
        target_service=target_service,
        target_account_id=target_account,
        region=event.get("awsRegion", ""),
        raw_json=json.dumps(event),
    )


def parse_cloudtrail_file(path: Path) -> Iterator[NormalizedEvent]:
    """Stream-parse a CloudTrail JSON or gzip file, yielding NormalizedEvents."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        data = json.load(f)

    # CloudTrail JSON exports have a "Records" key
    records = data if isinstance(data, list) else data.get("Records", [])

    for event in records:
        normalized = _normalize_event(event)
        if normalized is not None:
            yield normalized


def parse_cloudtrail_dir(directory: Path) -> Iterator[NormalizedEvent]:
    """Parse all CloudTrail JSON/gzip files in a directory (recursive)."""
    patterns = ["*.json", "*.json.gz"]
    for pattern in patterns:
        for path in sorted(directory.rglob(pattern)):
            yield from parse_cloudtrail_file(path)
