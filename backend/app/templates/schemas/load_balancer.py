"""
Pydantic v2 schemas for OCI Load Balancer resources.

Maps to ``oci_load_balancer_*`` Terraform resources.
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

class ShapeDetails(BaseModel):
    """Flexible load balancer bandwidth configuration."""
    model_config = ConfigDict(populate_by_name=True)

    minimum_bandwidth_in_mbps: Annotated[
        int, Field(ge=10, description="Minimum bandwidth in Mbps")
    ]
    maximum_bandwidth_in_mbps: Annotated[
        int, Field(ge=10, description="Maximum bandwidth in Mbps")
    ]


class HealthChecker(BaseModel):
    """Health check configuration for a backend set."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "protocol": "HTTP",
                    "port": 80,
                    "url_path": "/health",
                    "interval_ms": 10000,
                    "timeout_in_millis": 3000,
                    "retries": 3,
                    "return_code": 200,
                }
            ]
        }
    )

    protocol: Annotated[str, Field(description="HTTP | HTTPS | TCP")]
    port: Annotated[int, Field(ge=1, le=65535, description="Health check port")]
    url_path: Annotated[
        Optional[str],
        Field(default=None, description="URL path for HTTP/HTTPS health checks"),
    ]
    interval_ms: Annotated[
        int, Field(default=10000, ge=1000, description="Interval between checks in ms")
    ]
    timeout_in_millis: Annotated[
        int, Field(default=3000, ge=1000, description="Timeout per check in ms")
    ]
    retries: Annotated[
        int, Field(default=3, ge=1, description="Number of retries before marking unhealthy")
    ]
    return_code: Annotated[
        int, Field(default=200, ge=100, le=599, description="Expected HTTP return code")
    ]


class SslConfig(BaseModel):
    """SSL/TLS configuration for a listener."""
    model_config = ConfigDict(populate_by_name=True)

    certificate_name: Annotated[str, Field(description="Name of the certificate resource")]
    verify_peer_certificate: Annotated[
        bool, Field(default=False, description="Whether to verify peer certificates")
    ]


class ConnectionConfig(BaseModel):
    """Connection-level configuration for a listener."""
    model_config = ConfigDict(populate_by_name=True)

    idle_timeout_in_seconds: Annotated[
        int, Field(default=60, ge=1, description="Idle timeout in seconds")
    ]


class PathRoute(BaseModel):
    """A single path route in a path route set."""
    model_config = ConfigDict(populate_by_name=True)

    path_string: Annotated[str, Field(description="URL path (e.g., '/api')")]
    backend_set_name: Annotated[str, Field(description="Target backend set name")]
    match_type: Annotated[
        str,
        Field(
            default="EXACT_MATCH",
            description="EXACT_MATCH | FORCE_LONGEST_PREFIX_MATCH | PREFIX_MATCH | SUFFIX_MATCH",
        ),
    ]


class RuleSetItem(BaseModel):
    """A single item in a rule set."""
    model_config = ConfigDict(populate_by_name=True)

    action: Annotated[str, Field(description="Rule action (e.g., ADD_HTTP_REQUEST_HEADER)")]
    header: Annotated[Optional[str], Field(default=None, description="HTTP header name")]
    value: Annotated[Optional[str], Field(default=None, description="Header value")]
    description: Annotated[Optional[str], Field(default=None)]


# ===================================================================
# Top-level resource schemas (7 models)
# ===================================================================

class LoadBalancerParams(BaseModel):
    """Parameters for ``oci_load_balancer_load_balancer``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "display_name": "lb-web",
                    "shape": "flexible",
                    "is_private": False,
                    "shape_details": {
                        "minimum_bandwidth_in_mbps": 10,
                        "maximum_bandwidth_in_mbps": 100,
                    },
                    "subnet_ids": ["oci_core_subnet.public.id"],
                    "aws_source_id": "arn:aws:elasticloadbalancing:...:loadbalancer/app/web/abc",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name")]
    shape: Annotated[str, Field(default="flexible", description="Load balancer shape")]
    is_private: Annotated[
        bool, Field(default=False, description="True for internal load balancers")
    ]
    shape_details: Annotated[
        Optional[ShapeDetails],
        Field(default=None, description="Required when shape is 'flexible'"),
    ]
    subnet_ids: Annotated[
        list[str], Field(min_length=1, description="Terraform references to subnets")
    ]
    network_security_group_ids: Annotated[
        Optional[list[str]],
        Field(default=None, description="Terraform references to NSGs"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS ALB/NLB ARN")]


class BackendSetParams(BaseModel):
    """Parameters for ``oci_load_balancer_backend_set``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "load_balancer_id": "oci_load_balancer_load_balancer.web.id",
                    "name": "bs-web",
                    "policy": "ROUND_ROBIN",
                    "health_checker": {
                        "protocol": "HTTP",
                        "port": 80,
                        "url_path": "/health",
                        "interval_ms": 10000,
                        "timeout_in_millis": 3000,
                        "retries": 3,
                        "return_code": 200,
                    },
                    "aws_source_id": "arn:aws:elasticloadbalancing:...:targetgroup/web/abc",
                }
            ]
        }
    )

    load_balancer_id: Annotated[str, Field(description="Terraform reference to the load balancer")]
    name: Annotated[str, Field(description="Backend set name")]
    policy: Annotated[
        str,
        Field(
            default="ROUND_ROBIN",
            description="ROUND_ROBIN | LEAST_CONNECTIONS | IP_HASH",
        ),
    ]
    health_checker: Annotated[HealthChecker, Field(description="Health check configuration")]
    aws_source_id: Annotated[str, Field(description="AWS Target Group ARN")]


class ListenerParams(BaseModel):
    """Parameters for ``oci_load_balancer_listener``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "load_balancer_id": "oci_load_balancer_load_balancer.web.id",
                    "name": "listener-https",
                    "default_backend_set_name": "bs-web",
                    "port": 443,
                    "protocol": "HTTPS",
                    "aws_source_id": "arn:aws:elasticloadbalancing:...:listener/app/web/abc/def",
                }
            ]
        }
    )

    load_balancer_id: Annotated[str, Field(description="Terraform reference to the load balancer")]
    name: Annotated[str, Field(description="Listener name")]
    default_backend_set_name: Annotated[str, Field(description="Default backend set name")]
    port: Annotated[int, Field(ge=1, le=65535, description="Listener port")]
    protocol: Annotated[
        Literal["HTTP", "HTTPS", "TCP"],
        Field(description="Listener protocol"),
    ]
    ssl_configuration: Annotated[Optional[SslConfig], Field(default=None)]
    connection_configuration: Annotated[Optional[ConnectionConfig], Field(default=None)]
    hostname_names: Annotated[
        Optional[list[str]], Field(default=None, description="Associated hostname resource names")
    ]
    path_route_set_name: Annotated[
        Optional[str], Field(default=None, description="Path route set name")
    ]
    rule_set_names: Annotated[
        Optional[list[str]], Field(default=None, description="Rule set names to apply")
    ]
    aws_source_id: Annotated[str, Field(description="AWS Listener ARN")]


class CertificateParams(BaseModel):
    """Parameters for ``oci_load_balancer_certificate``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "load_balancer_id": "oci_load_balancer_load_balancer.web.id",
                    "certificate_name": "web-cert",
                    "aws_source_id": "arn:aws:acm:...:certificate/abc",
                }
            ]
        }
    )

    load_balancer_id: Annotated[str, Field(description="Terraform reference to the load balancer")]
    certificate_name: Annotated[str, Field(description="Certificate display name")]
    public_certificate: Annotated[
        Optional[str],
        Field(default=None, description="PEM public certificate (placeholder — fill after migration)"),
    ]
    private_key: Annotated[
        Optional[str],
        Field(default=None, description="PEM private key (placeholder — fill after migration)"),
    ]
    ca_certificate: Annotated[
        Optional[str],
        Field(default=None, description="PEM CA certificate chain"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS ACM certificate ARN")]


class HostnameParams(BaseModel):
    """Parameters for ``oci_load_balancer_hostname``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "load_balancer_id": "oci_load_balancer_load_balancer.web.id",
                    "hostname": "www.example.com",
                    "name": "www-example",
                    "aws_source_id": "www.example.com",
                }
            ]
        }
    )

    load_balancer_id: Annotated[str, Field(description="Terraform reference to the load balancer")]
    hostname: Annotated[str, Field(description="Virtual hostname (FQDN)")]
    name: Annotated[str, Field(description="Hostname resource name")]
    aws_source_id: Annotated[str, Field(description="AWS hostname / domain identifier")]


class PathRouteSetParams(BaseModel):
    """Parameters for ``oci_load_balancer_path_route_set``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "load_balancer_id": "oci_load_balancer_load_balancer.web.id",
                    "name": "prs-api",
                    "path_routes": [
                        {
                            "path_string": "/api",
                            "backend_set_name": "bs-api",
                            "match_type": "PREFIX_MATCH",
                        }
                    ],
                    "aws_source_id": "arn:aws:elasticloadbalancing:...:listener-rule/abc",
                }
            ]
        }
    )

    load_balancer_id: Annotated[str, Field(description="Terraform reference to the load balancer")]
    name: Annotated[str, Field(description="Path route set name")]
    path_routes: Annotated[
        list[PathRoute], Field(min_length=1, description="Path route entries")
    ]
    aws_source_id: Annotated[str, Field(description="AWS listener rule ARN")]


class RuleSetParams(BaseModel):
    """Parameters for ``oci_load_balancer_rule_set``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "load_balancer_id": "oci_load_balancer_load_balancer.web.id",
                    "name": "rs-headers",
                    "items": [
                        {
                            "action": "ADD_HTTP_REQUEST_HEADER",
                            "header": "X-Forwarded-Proto",
                            "value": "https",
                        }
                    ],
                    "aws_source_id": "arn:aws:elasticloadbalancing:...:listener-rule/abc",
                }
            ]
        }
    )

    load_balancer_id: Annotated[str, Field(description="Terraform reference to the load balancer")]
    name: Annotated[str, Field(description="Rule set name")]
    items: Annotated[
        list[RuleSetItem], Field(min_length=1, description="Rule set items")
    ]
    aws_source_id: Annotated[str, Field(description="AWS listener rule ARN")]
