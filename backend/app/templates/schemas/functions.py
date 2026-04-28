"""
Pydantic v2 schemas for OCI Functions resources.

Maps to ``oci_functions_application`` and ``oci_functions_function``
Terraform resources.
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
# Top-level resource schemas (2 models)
# ===================================================================

class FunctionsApplicationParams(BaseModel):
    """Parameters for ``oci_functions_application``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "display_name": "migration-fn-app",
                    "subnet_ids": ["oci_core_subnet.private.id"],
                    "config": {"ENV": "production"},
                    "aws_source_id": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name for the application")]
    subnet_ids: Annotated[
        list[str],
        Field(min_length=1, description="Terraform references to subnets for the application"),
    ]
    config: Annotated[
        Optional[dict[str, str]],
        Field(default=None, description="Application configuration key-value pairs"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Lambda function ARN for traceability")]


class FunctionParams(BaseModel):
    """Parameters for ``oci_functions_function``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "application_id": "oci_functions_application.main.id",
                    "display_name": "my-function",
                    "image": "iad.ocir.io/namespace/repo:latest",
                    "memory_in_mbs": 256,
                    "timeout_in_seconds": 30,
                    "aws_source_id": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
                }
            ]
        }
    )

    application_id: Annotated[
        str, Field(description="Terraform reference to the functions application")
    ]
    display_name: Annotated[str, Field(description="Display name for the function")]
    image: Annotated[
        str,
        Field(description="OCIR image URI, e.g. \"iad.ocir.io/namespace/repo:tag\""),
    ]
    memory_in_mbs: Annotated[
        int,
        Field(
            ge=128,
            default=256,
            description="Function memory in MB — 128, 256, 512, or 1024",
        ),
    ]
    timeout_in_seconds: Annotated[
        Optional[int],
        Field(ge=5, le=300, default=30, description="Function timeout in seconds (5-300)"),
    ]
    config: Annotated[
        Optional[dict[str, str]],
        Field(default=None, description="Function configuration key-value pairs"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Lambda function ARN for traceability")]
