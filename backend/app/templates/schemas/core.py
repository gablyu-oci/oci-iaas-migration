"""
Pydantic v2 schemas for OCI Core networking resources.

Every model maps 1-to-1 with a Jinja2 Terraform template and carries
an ``aws_source_id`` field so generated HCL can be traced back to the
original AWS resource.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Reusable regex patterns
# ---------------------------------------------------------------------------
_CIDR_RE = re.compile(
    r"^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(25[0-5]|2[0-4]\d|[01]?\d\d?)"
    r"/(3[0-2]|[12]?\d)$"
)


def _validate_cidr(value: str) -> str:
    if not _CIDR_RE.match(value):
        raise ValueError(f"Invalid CIDR notation: {value!r}")
    return value


# ---------------------------------------------------------------------------
# Shared defaults
# ---------------------------------------------------------------------------
def _default_tags() -> dict[str, str]:
    return {"managed_by": "oci-iaas-migration", "aws_source_id": "PLACEHOLDER"}


# ---------------------------------------------------------------------------
# Sub-models used by multiple top-level schemas
# ---------------------------------------------------------------------------

class TcpUdpOptions(BaseModel):
    """Port range for TCP or UDP options."""
    model_config = ConfigDict(populate_by_name=True)

    min: Annotated[int, Field(ge=1, le=65535, description="Minimum port number")]
    max: Annotated[int, Field(ge=1, le=65535, description="Maximum port number")]


class IcmpOptions(BaseModel):
    """ICMP type / code pair."""
    model_config = ConfigDict(populate_by_name=True)

    type: Annotated[int, Field(ge=0, le=255, description="ICMP type")]
    code: Annotated[int, Field(ge=-1, le=255, default=-1, description="ICMP code (-1 means all)")]


class RouteRule(BaseModel):
    """A single route rule inside a route table."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "destination": "0.0.0.0/0",
                    "destination_type": "CIDR_BLOCK",
                    "network_entity_id": "oci_core_internet_gateway.main.id",
                    "description": "Default route to IGW",
                }
            ]
        }
    )

    destination: Annotated[str, Field(description="Destination CIDR or service CIDR")]
    destination_type: Annotated[
        Literal["CIDR_BLOCK", "SERVICE_CIDR_BLOCK"],
        Field(description="Type of the destination"),
    ]
    network_entity_id: Annotated[
        str, Field(description="Terraform reference to the gateway / entity")
    ]
    description: Annotated[
        Optional[str], Field(default=None, description="Human-readable description")
    ]


class SecurityRule(BaseModel):
    """Ingress or egress security rule for a security list."""
    model_config = ConfigDict(populate_by_name=True)

    protocol: Annotated[
        str,
        Field(description="IP protocol number ('6'=TCP, '17'=UDP, '1'=ICMP, 'all')"),
    ]
    source: Annotated[
        Optional[str],
        Field(default=None, description="Source CIDR (ingress rules)"),
    ]
    source_type: Annotated[
        Optional[str],
        Field(default=None, description="CIDR_BLOCK | NETWORK_SECURITY_GROUP | SERVICE_CIDR_BLOCK"),
    ]
    destination: Annotated[
        Optional[str],
        Field(default=None, description="Destination CIDR (egress rules)"),
    ]
    destination_type: Annotated[
        Optional[str],
        Field(default=None, description="CIDR_BLOCK | NETWORK_SECURITY_GROUP | SERVICE_CIDR_BLOCK"),
    ]
    stateless: Annotated[bool, Field(default=False, description="Whether the rule is stateless")]
    description: Annotated[Optional[str], Field(default=None)]
    tcp_options: Annotated[Optional[TcpUdpOptions], Field(default=None)]
    udp_options: Annotated[Optional[TcpUdpOptions], Field(default=None)]
    icmp_options: Annotated[Optional[IcmpOptions], Field(default=None)]

    @field_validator("protocol")
    @classmethod
    def _validate_protocol(cls, v: str) -> str:
        allowed = {"1", "6", "17", "58", "all"}
        if v not in allowed:
            raise ValueError(f"protocol must be one of {allowed}, got {v!r}")
        return v


# ===================================================================
# Top-level resource schemas (11 models)
# ===================================================================

class VcnParams(BaseModel):
    """Parameters for ``oci_core_vcn``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.0.0.0/16"],
                    "display_name": "migration-vcn",
                    "dns_label": "migvcn",
                    "aws_source_id": "vpc-0abc123",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    cidr_blocks: Annotated[list[str], Field(min_length=1, description="One or more VCN CIDR blocks")]
    display_name: Annotated[str, Field(description="Display name for the VCN")]
    dns_label: Annotated[
        Optional[str],
        Field(default=None, max_length=15, pattern=r"^[a-z][a-z0-9]{0,14}$",
              description="DNS label (max 15 lowercase alphanumeric chars, must start with letter)"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS VPC ID for traceability")]

    @field_validator("cidr_blocks")
    @classmethod
    def _validate_cidrs(cls, v: list[str]) -> list[str]:
        for cidr in v:
            _validate_cidr(cidr)
        return v


class SubnetParams(BaseModel):
    """Parameters for ``oci_core_subnet``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "vcn_id": "oci_core_vcn.main.id",
                    "cidr_block": "10.0.1.0/24",
                    "display_name": "public-subnet-1",
                    "prohibit_public_ip_on_vnic": False,
                    "aws_source_id": "subnet-0abc123",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    vcn_id: Annotated[str, Field(description="Terraform reference to the VCN")]
    cidr_block: Annotated[str, Field(description="Subnet CIDR block")]
    display_name: Annotated[str, Field(description="Display name for the subnet")]
    dns_label: Annotated[
        Optional[str],
        Field(default=None, max_length=15, pattern=r"^[a-z][a-z0-9]{0,14}$",
              description="DNS label"),
    ]
    prohibit_public_ip_on_vnic: Annotated[
        bool, Field(default=False, description="True for private subnets")
    ]
    route_table_id: Annotated[
        Optional[str], Field(default=None, description="Terraform reference to a route table")
    ]
    security_list_ids: Annotated[
        Optional[list[str]],
        Field(default=None, description="List of Terraform references to security lists"),
    ]
    dhcp_options_id: Annotated[
        Optional[str], Field(default=None, description="Terraform reference to DHCP options")
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Subnet ID for traceability")]

    @field_validator("cidr_block")
    @classmethod
    def _validate_cidr_block(cls, v: str) -> str:
        return _validate_cidr(v)


class InternetGatewayParams(BaseModel):
    """Parameters for ``oci_core_internet_gateway``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "vcn_id": "oci_core_vcn.main.id",
                    "display_name": "igw-main",
                    "enabled": True,
                    "aws_source_id": "igw-0abc123",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    vcn_id: Annotated[str, Field(description="Terraform reference to the VCN")]
    display_name: Annotated[str, Field(description="Display name")]
    enabled: Annotated[bool, Field(default=True, description="Whether the gateway is enabled")]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Internet Gateway ID")]


class NatGatewayParams(BaseModel):
    """Parameters for ``oci_core_nat_gateway``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "vcn_id": "oci_core_vcn.main.id",
                    "display_name": "natgw-main",
                    "block_traffic": False,
                    "aws_source_id": "nat-0abc123",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    vcn_id: Annotated[str, Field(description="Terraform reference to the VCN")]
    display_name: Annotated[str, Field(description="Display name")]
    block_traffic: Annotated[bool, Field(default=False, description="Block all traffic through the NAT")]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS NAT Gateway ID")]


class RouteTableParams(BaseModel):
    """Parameters for ``oci_core_route_table``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "vcn_id": "oci_core_vcn.main.id",
                    "display_name": "rt-public",
                    "route_rules": [
                        {
                            "destination": "0.0.0.0/0",
                            "destination_type": "CIDR_BLOCK",
                            "network_entity_id": "oci_core_internet_gateway.main.id",
                        }
                    ],
                    "aws_source_id": "rtb-0abc123",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    vcn_id: Annotated[str, Field(description="Terraform reference to the VCN")]
    display_name: Annotated[str, Field(description="Display name")]
    route_rules: Annotated[list[RouteRule], Field(default_factory=list, description="Route rules")]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Route Table ID")]


class RouteTableAttachmentParams(BaseModel):
    """
    Attach a route table to a subnet.

    In OCI this is expressed through the subnet's ``route_table_id`` attribute,
    but we model it separately so the LLM can reason about attachments as
    discrete operations.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "subnet_id": "oci_core_subnet.public.id",
                    "route_table_id": "oci_core_route_table.public.id",
                }
            ]
        }
    )

    subnet_id: Annotated[str, Field(description="Terraform reference to the subnet")]
    route_table_id: Annotated[str, Field(description="Terraform reference to the route table")]


class SecurityListParams(BaseModel):
    """Parameters for ``oci_core_security_list``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "vcn_id": "oci_core_vcn.main.id",
                    "display_name": "sl-web",
                    "ingress_security_rules": [
                        {
                            "protocol": "6",
                            "source": "0.0.0.0/0",
                            "source_type": "CIDR_BLOCK",
                            "stateless": False,
                            "tcp_options": {"min": 443, "max": 443},
                        }
                    ],
                    "aws_source_id": "acl-0abc123",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    vcn_id: Annotated[str, Field(description="Terraform reference to the VCN")]
    display_name: Annotated[str, Field(description="Display name")]
    ingress_security_rules: Annotated[
        Optional[list[SecurityRule]],
        Field(default_factory=list, description="Ingress rules"),
    ]
    egress_security_rules: Annotated[
        Optional[list[SecurityRule]],
        Field(default_factory=list, description="Egress rules"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Network ACL or SG ID")]


class SecurityListAttachmentParams(BaseModel):
    """
    Attach a security list to a subnet.

    In OCI this is set via the subnet's ``security_list_ids``, but modelled
    separately for LLM composability.
    """
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "subnet_id": "oci_core_subnet.public.id",
                    "security_list_id": "oci_core_security_list.web.id",
                }
            ]
        }
    )

    subnet_id: Annotated[str, Field(description="Terraform reference to the subnet")]
    security_list_id: Annotated[str, Field(description="Terraform reference to the security list")]


class NetworkSecurityGroupParams(BaseModel):
    """Parameters for ``oci_core_network_security_group``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "vcn_id": "oci_core_vcn.main.id",
                    "display_name": "nsg-web",
                    "aws_source_id": "sg-0abc123",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    vcn_id: Annotated[str, Field(description="Terraform reference to the VCN")]
    display_name: Annotated[str, Field(description="Display name")]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Security Group ID")]


class NsgSecurityRuleParams(BaseModel):
    """Parameters for ``oci_core_network_security_group_security_rule``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "network_security_group_id": "oci_core_network_security_group.web.id",
                    "direction": "INGRESS",
                    "protocol": "6",
                    "source": "0.0.0.0/0",
                    "source_type": "CIDR_BLOCK",
                    "tcp_options": {"min": 443, "max": 443},
                    "aws_source_id": "sg-0abc123-rule-1",
                }
            ]
        }
    )

    network_security_group_id: Annotated[
        str, Field(description="Terraform reference to the NSG")
    ]
    direction: Annotated[
        Literal["INGRESS", "EGRESS"], Field(description="Rule direction")
    ]
    protocol: Annotated[
        str,
        Field(description="IP protocol number ('6'=TCP, '17'=UDP, '1'=ICMP, 'all')"),
    ]
    source: Annotated[Optional[str], Field(default=None, description="Source (INGRESS rules)")]
    source_type: Annotated[
        Optional[str],
        Field(default=None, description="CIDR_BLOCK | NETWORK_SECURITY_GROUP | SERVICE_CIDR_BLOCK"),
    ]
    destination: Annotated[Optional[str], Field(default=None, description="Destination (EGRESS rules)")]
    destination_type: Annotated[Optional[str], Field(default=None)]
    stateless: Annotated[bool, Field(default=False, description="Whether the rule is stateless")]
    description: Annotated[Optional[str], Field(default=None)]
    tcp_options: Annotated[Optional[TcpUdpOptions], Field(default=None)]
    udp_options: Annotated[Optional[TcpUdpOptions], Field(default=None)]
    icmp_options: Annotated[Optional[IcmpOptions], Field(default=None)]
    aws_source_id: Annotated[str, Field(description="AWS SG rule identifier")]

    @field_validator("protocol")
    @classmethod
    def _validate_protocol(cls, v: str) -> str:
        allowed = {"1", "6", "17", "58", "all"}
        if v not in allowed:
            raise ValueError(f"protocol must be one of {allowed}, got {v!r}")
        return v


class PublicIpParams(BaseModel):
    """Parameters for ``oci_core_public_ip``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "lifetime": "RESERVED",
                    "display_name": "eip-web",
                    "aws_source_id": "eipalloc-0abc123",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    lifetime: Annotated[
        Literal["RESERVED", "EPHEMERAL"],
        Field(default="RESERVED", description="Public IP lifetime"),
    ]
    display_name: Annotated[str, Field(description="Display name")]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Elastic IP allocation ID")]
