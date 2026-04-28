"""
Pydantic v2 schemas for OCI Identity and Access Management resources.

Maps to ``oci_identity_*`` Terraform resources.
"""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared defaults
# ---------------------------------------------------------------------------
def _default_tags() -> dict[str, str]:
    return {"managed_by": "oci-iaas-migration", "aws_source_id": "PLACEHOLDER"}


# ===================================================================
# Top-level resource schemas (4 models)
# ===================================================================

class DynamicGroupParams(BaseModel):
    """Parameters for ``oci_identity_dynamic_group``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.tenancy_ocid",
                    "name": "migration-instance-dg",
                    "description": "Dynamic group for migrated instances",
                    "matching_rule": "ALL {instance.compartment.id = 'ocid1.compartment.oc1..example'}",
                    "aws_source_id": "arn:aws:iam::123456789012:role/my-role",
                }
            ]
        }
    )

    compartment_id: Annotated[
        str, Field(description="Tenancy OCID — dynamic groups must be created at tenancy level")
    ]
    name: Annotated[str, Field(description="Dynamic group name")]
    description: Annotated[str, Field(description="Human-readable description")]
    matching_rule: Annotated[
        str,
        Field(description="Matching rule expression, e.g. \"ALL {instance.compartment.id = 'ocid1...'}\""),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS IAM role or resource ARN for traceability")]


class PolicyParams(BaseModel):
    """Parameters for ``oci_identity_policy``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.tenancy_ocid",
                    "name": "migration-admin-policy",
                    "description": "Policy granting admin access to migrated resources",
                    "statements": [
                        "Allow group admins to manage all-resources in compartment migration"
                    ],
                    "aws_source_id": "arn:aws:iam::123456789012:policy/my-policy",
                }
            ]
        }
    )

    compartment_id: Annotated[
        str, Field(description="Compartment OCID where the policy is scoped")
    ]
    name: Annotated[str, Field(description="Policy name")]
    description: Annotated[str, Field(description="Human-readable description")]
    statements: Annotated[
        list[str],
        Field(
            min_length=1,
            description="Policy statements, e.g. [\"Allow group admins to manage all-resources in compartment X\"]",
        ),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS IAM policy ARN for traceability")]


class GroupParams(BaseModel):
    """Parameters for ``oci_identity_group``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.tenancy_ocid",
                    "name": "migration-admins",
                    "description": "Group for migration administrators",
                    "aws_source_id": "arn:aws:iam::123456789012:group/admins",
                }
            ]
        }
    )

    compartment_id: Annotated[
        str, Field(description="Tenancy OCID — groups must be created at tenancy level")
    ]
    name: Annotated[str, Field(description="Group name")]
    description: Annotated[str, Field(description="Human-readable description")]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS IAM group ARN for traceability")]


class UserParams(BaseModel):
    """Parameters for ``oci_identity_user``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.tenancy_ocid",
                    "name": "migration-svc-user",
                    "description": "Service user for migration workloads",
                    "email": "svc-user@example.com",
                    "aws_source_id": "arn:aws:iam::123456789012:user/svc-user",
                }
            ]
        }
    )

    compartment_id: Annotated[
        str, Field(description="Tenancy OCID — users must be created at tenancy level")
    ]
    name: Annotated[str, Field(description="User name")]
    description: Annotated[str, Field(description="Human-readable description")]
    email: Annotated[
        Optional[str], Field(default=None, description="User email address")
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS IAM user ARN for traceability")]
