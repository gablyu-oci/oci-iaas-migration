"""
Pydantic v2 schemas for OCI Cloud Migrations (OCM) resources.

Maps to ``oci_cloud_migrations_*`` Terraform resources used to orchestrate
VM-level migration from AWS to OCI.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared defaults
# ---------------------------------------------------------------------------
def _default_tags() -> dict[str, str]:
    return {"managed_by": "oci-iaas-migration", "aws_source_id": "PLACEHOLDER"}


# ===================================================================
# Top-level resource schemas (4 models)
# ===================================================================

class MigrationParams(BaseModel):
    """Parameters for ``oci_cloud_migrations_migration``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "display_name": "aws-to-oci-migration",
                    "aws_source_id": "migration-level",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name for the migration")]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[
        Optional[str],
        Field(default="migration-level", description="AWS identifier (migration-level if not applicable)"),
    ]


class MigrationPlanParams(BaseModel):
    """Parameters for ``oci_cloud_migrations_migration_plan``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "migration_id": "oci_cloud_migrations_migration.main.id",
                    "display_name": "plan-web-tier",
                    "strategy_type": "AS_IS",
                    "resource_type": "VM",
                    "aws_source_id": "plan-web-tier",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    migration_id: Annotated[str, Field(description="Terraform reference to the parent migration")]
    display_name: Annotated[str, Field(description="Display name for the migration plan")]
    strategy_type: Annotated[
        str,
        Field(
            default="AS_IS",
            description="Migration strategy: AS_IS | AS_IS_OPTIMIZED | CUSTOM",
        ),
    ]
    resource_type: Annotated[
        str,
        Field(default="VM", description="Type of resource being migrated"),
    ]
    aws_source_id: Annotated[
        Optional[str],
        Field(default=None, description="AWS identifier for traceability"),
    ]


class TargetAssetParams(BaseModel):
    """
    Parameters for ``oci_cloud_migrations_target_asset``.

    Represents a single VM (EC2 instance) being migrated to OCI.
    ``aws_source_id`` is **required** here because it is the EC2 instance ID
    used to correlate the source and target.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "migration_plan_id": "oci_cloud_migrations_migration_plan.main.id",
                    "type": "INSTANCE",
                    "is_excluded_from_execution": False,
                    "preferred_shape_type": "VM",
                    "shape": "VM.Standard.E5.Flex",
                    "ocpus": 4,
                    "memory_in_gbs": 16,
                    "block_volumes_performance": 10,
                    "aws_source_id": "i-0abc123def456",
                }
            ]
        }
    )

    compartment_id: Annotated[
        Optional[str],
        Field(default=None, description="OCI compartment OCID (inherits from plan if omitted)"),
    ]
    migration_plan_id: Annotated[
        str, Field(description="Terraform reference to the migration plan")
    ]
    type: Annotated[
        str, Field(default="INSTANCE", description="Target asset type")
    ]
    is_excluded_from_execution: Annotated[
        bool, Field(default=False, description="If true, asset is planned but not executed")
    ]
    preferred_shape_type: Annotated[
        Literal["VM", "BM"],
        Field(default="VM", description="VM (virtual machine) or BM (bare metal)"),
    ]
    shape: Annotated[
        str,
        Field(description="OCI compute shape (e.g., VM.Standard.E5.Flex)"),
    ]
    ocpus: Annotated[int, Field(ge=1, description="Number of OCPUs")]
    memory_in_gbs: Annotated[int, Field(ge=1, description="Memory in GB")]
    block_volumes_performance: Annotated[
        int,
        Field(
            default=10,
            ge=0,
            le=120,
            description="VPUs/GB for block volume performance (0=lower, 10=balanced, 20+=higher)",
        ),
    ]
    aws_source_id: Annotated[
        str, Field(description="EC2 instance ID (REQUIRED for source-target correlation)")
    ]


class ReplicationScheduleParams(BaseModel):
    """Parameters for ``oci_cloud_migrations_replication_schedule``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "display_name": "daily-replication",
                    "execution_recurrences": "FREQ=DAILY;BYHOUR=2;BYMINUTE=0",
                    "aws_source_id": "replication-schedule",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name")]
    execution_recurrences: Annotated[
        str,
        Field(description="iCalendar RRULE recurrence string (e.g., FREQ=DAILY;BYHOUR=2;BYMINUTE=0)"),
    ]
    aws_source_id: Annotated[
        Optional[str],
        Field(default=None, description="AWS identifier for traceability"),
    ]
