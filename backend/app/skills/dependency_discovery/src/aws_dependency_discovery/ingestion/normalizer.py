"""Unified event schema for normalized CloudTrail events."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NormalizedEvent:
    """A normalized CloudTrail event with fields relevant to dependency discovery."""

    event_id: str
    event_time: str
    event_source: str  # e.g. "sts.amazonaws.com"
    event_name: str  # e.g. "AssumeRole"
    source_account_id: str
    source_principal: str  # ARN of the caller
    target_resource: str  # ARN or identifier of the target
    target_service: str  # Extracted service name (e.g. "lambda", "s3")
    target_account_id: str  # Account owning the target resource
    region: str
    raw_json: str  # Original JSON for drill-down
