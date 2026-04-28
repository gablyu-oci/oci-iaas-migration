"""
Pydantic v2 schemas for OCI Observability resources.

Maps to ``oci_logging_log_group``, ``oci_logging_log``, and
``oci_monitoring_alarm`` Terraform resources.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared defaults
# ---------------------------------------------------------------------------
def _default_tags() -> dict[str, str]:
    return {"managed_by": "oci-iaas-migration", "aws_source_id": "PLACEHOLDER"}


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class LogSource(BaseModel):
    """Source configuration for a service log."""
    model_config = ConfigDict(populate_by_name=True)

    service: Annotated[str, Field(description="OCI service name (e.g. \"flowlogs\", \"objectstorage\")")]
    resource: Annotated[str, Field(description="Resource OCID or TF reference emitting the log")]
    category: Annotated[str, Field(description="Log category (e.g. \"all\", \"write\", \"read\")")]


class LogConfiguration(BaseModel):
    """Configuration block for a service log."""
    model_config = ConfigDict(populate_by_name=True)

    source: Annotated[LogSource, Field(description="Log source definition")]
    compartment_id: Annotated[
        str, Field(description="Compartment OCID where the source resource resides")
    ]


# ===================================================================
# Top-level resource schemas (3 models)
# ===================================================================

class LogGroupParams(BaseModel):
    """Parameters for ``oci_logging_log_group``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "display_name": "migration-log-group",
                    "description": "Log group for migrated workloads",
                    "aws_source_id": "arn:aws:logs:us-east-1:123456789012:log-group:/aws/my-app",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name for the log group")]
    description: Annotated[
        Optional[str], Field(default=None, description="Human-readable description")
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS CloudWatch log group ARN for traceability")]


class LogParams(BaseModel):
    """Parameters for ``oci_logging_log``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "log_group_id": "oci_logging_log_group.main.id",
                    "display_name": "migration-app-log",
                    "log_type": "CUSTOM",
                    "is_enabled": True,
                    "retention_duration": 30,
                    "aws_source_id": "arn:aws:logs:us-east-1:123456789012:log-group:/aws/my-app:log-stream:stream1",
                }
            ]
        }
    )

    log_group_id: Annotated[
        str, Field(description="Terraform reference to the log group")
    ]
    display_name: Annotated[str, Field(description="Display name for the log")]
    log_type: Annotated[
        Literal["CUSTOM", "SERVICE"],
        Field(default="CUSTOM", description="Log type — CUSTOM or SERVICE"),
    ]
    is_enabled: Annotated[
        Optional[bool], Field(default=True, description="Whether the log is enabled")
    ]
    retention_duration: Annotated[
        Optional[int],
        Field(default=30, ge=30, description="Retention duration in days"),
    ]
    configuration: Annotated[
        Optional[LogConfiguration],
        Field(default=None, description="Required for SERVICE log type — source and compartment config"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS CloudWatch log stream ARN for traceability")]


class MetricAlarmParams(BaseModel):
    """Parameters for ``oci_monitoring_alarm``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "display_name": "high-cpu-alarm",
                    "metric_compartment_id": "var.compartment_id",
                    "namespace": "oci_computeagent",
                    "query": "CpuUtilization[5m].mean() > 80",
                    "severity": "WARNING",
                    "destinations": ["oci_ons_notification_topic.ops.id"],
                    "is_enabled": True,
                    "body": "CPU utilization exceeded 80%",
                    "pending_duration": "PT5M",
                    "aws_source_id": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:high-cpu",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name for the alarm")]
    metric_compartment_id: Annotated[
        str, Field(description="Compartment OCID where metrics are emitted")
    ]
    namespace: Annotated[
        str, Field(description="Metric namespace (e.g. \"oci_computeagent\")")
    ]
    query: Annotated[
        str, Field(description="MQL query (e.g. \"CpuUtilization[5m].mean() > 80\")")
    ]
    severity: Annotated[
        Literal["CRITICAL", "ERROR", "WARNING", "INFO"],
        Field(default="WARNING", description="Alarm severity level"),
    ]
    destinations: Annotated[
        list[str],
        Field(min_length=1, description="Terraform references to notification topics"),
    ]
    is_enabled: Annotated[
        Optional[bool], Field(default=True, description="Whether the alarm is enabled")
    ]
    body: Annotated[
        Optional[str], Field(default=None, description="Alarm body / description text")
    ]
    pending_duration: Annotated[
        Optional[str],
        Field(default=None, description="ISO 8601 duration before firing (e.g. \"PT5M\")"),
    ]
    repeat_notification_duration: Annotated[
        Optional[str],
        Field(default=None, description="ISO 8601 duration between repeated notifications"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS CloudWatch alarm ARN for traceability")]
