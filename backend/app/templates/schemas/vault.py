"""
Pydantic v2 schemas for OCI Vault / Key Management resources.

Maps to ``oci_kms_vault``, ``oci_kms_key``, and ``oci_vault_secret``
Terraform resources.
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

class KeyShape(BaseModel):
    """Key shape configuration for a KMS key."""
    model_config = ConfigDict(populate_by_name=True)

    algorithm: Annotated[
        Literal["AES", "RSA", "ECDSA"],
        Field(description="Encryption algorithm"),
    ]
    length: Annotated[
        int,
        Field(description="Key length in bytes (e.g. 16, 24, 32 for AES)"),
    ]


class SecretContentDetails(BaseModel):
    """Content details for a vault secret."""
    model_config = ConfigDict(populate_by_name=True)

    content_type: Annotated[
        Literal["BASE64"],
        Field(default="BASE64", description="Content encoding type"),
    ]
    content: Annotated[
        str,
        Field(description="Base64-encoded secret value placeholder"),
    ]


# ===================================================================
# Top-level resource schemas (3 models)
# ===================================================================

class VaultParams(BaseModel):
    """Parameters for ``oci_kms_vault``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "display_name": "migration-vault",
                    "vault_type": "DEFAULT",
                    "aws_source_id": "arn:aws:kms:us-east-1:123456789012:key/abc-def",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name for the vault")]
    vault_type: Annotated[
        Literal["DEFAULT", "VIRTUAL_PRIVATE"],
        Field(default="DEFAULT", description="Vault type — DEFAULT or VIRTUAL_PRIVATE"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS KMS key ARN or Secrets Manager ARN for traceability")]


class KeyParams(BaseModel):
    """Parameters for ``oci_kms_key``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "display_name": "migration-key",
                    "management_endpoint": "oci_kms_vault.main.management_endpoint",
                    "protection_mode": "SOFTWARE",
                    "key_shape": {"algorithm": "AES", "length": 32},
                    "aws_source_id": "arn:aws:kms:us-east-1:123456789012:key/abc-def",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name for the key")]
    management_endpoint: Annotated[
        str, Field(description="Terraform reference to the vault management_endpoint")
    ]
    protection_mode: Annotated[
        Literal["SOFTWARE", "HSM"],
        Field(default="SOFTWARE", description="Key protection mode — SOFTWARE or HSM"),
    ]
    key_shape: Annotated[
        KeyShape, Field(description="Key shape defining algorithm and length")
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS KMS key ARN for traceability")]


class SecretParams(BaseModel):
    """Parameters for ``oci_vault_secret``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "vault_id": "oci_kms_vault.main.id",
                    "key_id": "oci_kms_key.main.id",
                    "secret_name": "db-password",
                    "description": "Database password migrated from AWS Secrets Manager",
                    "secret_content": {
                        "content_type": "BASE64",
                        "content": "cGxhY2Vob2xkZXI=",
                    },
                    "aws_source_id": "arn:aws:secretsmanager:us-east-1:123456789012:secret:db-password",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    vault_id: Annotated[str, Field(description="Terraform reference to the vault")]
    key_id: Annotated[str, Field(description="Terraform reference to the encryption key")]
    secret_name: Annotated[str, Field(description="Secret name")]
    description: Annotated[
        Optional[str], Field(default=None, description="Human-readable description")
    ]
    secret_content: Annotated[
        SecretContentDetails, Field(description="Secret content details")
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Secrets Manager secret ARN for traceability")]
