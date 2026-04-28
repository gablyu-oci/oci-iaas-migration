"""
Pydantic v2 schema for free-form HCL blocks.

Used as a fallback when no structured template exists for a given OCI
resource type.  The LLM emits raw HCL and validation is deferred to
``terraform validate``.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class FreeFormHclParams(BaseModel):
    """
    Raw HCL for resources that do not yet have a dedicated Jinja2 template.

    No ``aws_source_id`` field -- traceability comments should be embedded
    directly in the HCL string by the LLM.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "hcl": (
                        'resource "oci_core_drg" "main" {\n'
                        '  compartment_id = var.compartment_id\n'
                        '  display_name   = "drg-main"\n'
                        "}\n"
                    )
                }
            ]
        }
    )

    hcl: Annotated[
        str,
        Field(
            min_length=1,
            description="Raw HCL string for resources not covered by structured templates",
        ),
    ]
