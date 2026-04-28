"""
Central template schema registry.

``TEMPLATE_REGISTRY`` maps each template name (matching the Jinja2 file path
relative to the ``oci/`` directory, e.g. ``core/vcn``) to its Pydantic v2
schema class.  Consumers can look up the schema, validate LLM output, and
call ``model_json_schema()`` to inject the schema into prompts.
"""

from __future__ import annotations

import json as _json
from pydantic import BaseModel

# -- Core networking --------------------------------------------------------
from app.templates.schemas.core import (
    InternetGatewayParams,
    NatGatewayParams,
    NetworkSecurityGroupParams,
    NsgSecurityRuleParams,
    PublicIpParams,
    RouteTableAttachmentParams,
    RouteTableParams,
    SecurityListAttachmentParams,
    SecurityListParams,
    SubnetParams,
    VcnParams,
)

# -- Load balancer ----------------------------------------------------------
from app.templates.schemas.load_balancer import (
    BackendSetParams,
    CertificateParams,
    HostnameParams,
    ListenerParams,
    LoadBalancerParams,
    PathRouteSetParams,
    RuleSetParams,
)

# -- Cloud Migrations (OCM) ------------------------------------------------
from app.templates.schemas.cloud_migrations import (
    MigrationParams,
    MigrationPlanParams,
    ReplicationScheduleParams,
    TargetAssetParams,
)

# -- Compute / Storage (Phase 4) -------------------------------------------
from app.templates.schemas.compute import (
    AutoScalingConfigurationParams,
    BlockVolumeAttachmentParams,
    BlockVolumeParams,
    BootVolumeParams,
    InstanceConfigurationParams,
    InstanceParams,
    InstancePoolParams,
)

# -- Identity / IAM (Phase 4) ----------------------------------------------
from app.templates.schemas.identity import (
    DynamicGroupParams,
    GroupParams,
    PolicyParams,
    UserParams,
)

# -- Vault / KMS (Phase 4) -------------------------------------------------
from app.templates.schemas.vault import (
    KeyParams,
    SecretParams,
    VaultParams,
)

# -- Functions / Serverless (Phase 4) --------------------------------------
from app.templates.schemas.functions import (
    FunctionParams,
    FunctionsApplicationParams,
)

# -- Observability (Phase 4) -----------------------------------------------
from app.templates.schemas.observability import (
    LogGroupParams,
    LogParams,
    MetricAlarmParams,
)

# -- Free-form fallback -----------------------------------------------------
from app.templates.schemas.free_form import FreeFormHclParams

# ---------------------------------------------------------------------------
# Registry: template name -> Pydantic schema class
#
# Keys use the path format "domain/resource_type" matching the Jinja2
# template file layout under templates/oci/.  For example, the template
# at templates/oci/core/vcn.tf.j2 is registered as "core/vcn".
# ---------------------------------------------------------------------------
TEMPLATE_REGISTRY: dict[str, type[BaseModel]] = {
    # Core networking (11)
    "core/vcn": VcnParams,
    "core/subnet": SubnetParams,
    "core/internet_gateway": InternetGatewayParams,
    "core/nat_gateway": NatGatewayParams,
    "core/route_table": RouteTableParams,
    "core/route_table_attachment": RouteTableAttachmentParams,
    "core/security_list": SecurityListParams,
    "core/security_list_attachment": SecurityListAttachmentParams,
    "core/network_security_group": NetworkSecurityGroupParams,
    "core/network_security_group_security_rule": NsgSecurityRuleParams,
    "core/public_ip": PublicIpParams,
    # Load balancer (7)
    "load_balancer/load_balancer": LoadBalancerParams,
    "load_balancer/backend_set": BackendSetParams,
    "load_balancer/listener": ListenerParams,
    "load_balancer/certificate": CertificateParams,
    "load_balancer/hostname": HostnameParams,
    "load_balancer/path_route_set": PathRouteSetParams,
    "load_balancer/rule_set": RuleSetParams,
    # Cloud Migrations / OCM (4)
    "cloud_migrations/migration": MigrationParams,
    "cloud_migrations/migration_plan": MigrationPlanParams,
    "cloud_migrations/target_asset": TargetAssetParams,
    "cloud_migrations/replication_schedule": ReplicationScheduleParams,
    # Compute / EC2 (7) — Phase 4
    "core/instance": InstanceParams,
    "core/instance_configuration": InstanceConfigurationParams,
    "core/instance_pool": InstancePoolParams,
    "core/autoscaling_configuration": AutoScalingConfigurationParams,
    "core/boot_volume": BootVolumeParams,
    "core/block_volume": BlockVolumeParams,
    "core/block_volume_attachment": BlockVolumeAttachmentParams,
    # Identity / IAM (4) — Phase 4
    "identity/dynamic_group": DynamicGroupParams,
    "identity/policy": PolicyParams,
    "identity/group": GroupParams,
    "identity/user": UserParams,
    # Vault / KMS (3) — Phase 4
    "vault/vault": VaultParams,
    "vault/key": KeyParams,
    "vault/secret": SecretParams,
    # Functions / Serverless (2) — Phase 4
    "functions/application": FunctionsApplicationParams,
    "functions/function": FunctionParams,
    # Observability (3) — Phase 4
    "observability/log_group": LogGroupParams,
    "observability/log": LogParams,
    "observability/metric_alarm": MetricAlarmParams,
    # Free-form fallback (1)
    "free_form_hcl": FreeFormHclParams,
}

# ---------------------------------------------------------------------------
# Skill -> template mapping: which templates each structured-output skill uses.
# ---------------------------------------------------------------------------
_SKILL_TO_TEMPLATES: dict[str, list[str]] = {
    "network_translation": [
        "core/vcn", "core/subnet", "core/internet_gateway", "core/nat_gateway",
        "core/route_table", "core/route_table_attachment",
        "core/security_list", "core/security_list_attachment",
        "core/network_security_group", "core/network_security_group_security_rule",
        "core/public_ip",
    ],
    "loadbalancer_translation": [
        "load_balancer/load_balancer", "load_balancer/backend_set",
        "load_balancer/listener", "load_balancer/certificate",
        "load_balancer/hostname", "load_balancer/path_route_set",
        "load_balancer/rule_set",
    ],
    "ocm_handoff_translation": [
        "cloud_migrations/migration", "cloud_migrations/migration_plan",
        "cloud_migrations/target_asset", "cloud_migrations/replication_schedule",
    ],
    "ec2_translation": [
        "core/instance", "core/instance_configuration", "core/instance_pool",
        "core/autoscaling_configuration", "core/boot_volume",
    ],
    "storage_translation": [
        "core/block_volume", "core/block_volume_attachment",
    ],
    "iam_translation": [
        "identity/dynamic_group", "identity/policy", "identity/group", "identity/user",
    ],
    "security_translation": [
        "vault/vault", "vault/key", "vault/secret",
    ],
    "serverless_translation": [
        "functions/application", "functions/function",
    ],
    "observability_translation": [
        "observability/log_group", "observability/log", "observability/metric_alarm",
    ],
}


def get_schemas_for_skill(skill_type: str) -> str:
    """Return formatted JSON Schema text for templates relevant to a skill.

    Each template's Pydantic schema is dumped via ``model_json_schema()`` and
    presented under a heading so the LLM writer knows exactly what ``params``
    object each template expects.

    Always includes ``free_form_hcl`` as a fallback option.
    """
    template_names = _SKILL_TO_TEMPLATES.get(skill_type)
    if not template_names:
        # Fallback: show all registered templates
        template_names = sorted(TEMPLATE_REGISTRY.keys())
    else:
        # Always include free_form_hcl
        template_names = list(template_names) + ["free_form_hcl"]

    sections: list[str] = []
    for name in template_names:
        schema_cls = TEMPLATE_REGISTRY.get(name)
        if schema_cls is None:
            continue
        schema = schema_cls.model_json_schema()
        sections.append(
            f"### `{name}`\n"
            f"```json\n{_json.dumps(schema, indent=2)}\n```"
        )

    return "\n\n".join(sections) if sections else "_(no schemas available)_"


__all__ = [
    "TEMPLATE_REGISTRY",
    "get_schemas_for_skill",
    # Core
    "VcnParams",
    "SubnetParams",
    "InternetGatewayParams",
    "NatGatewayParams",
    "RouteTableParams",
    "RouteTableAttachmentParams",
    "SecurityListParams",
    "SecurityListAttachmentParams",
    "NetworkSecurityGroupParams",
    "NsgSecurityRuleParams",
    "PublicIpParams",
    # Load balancer
    "LoadBalancerParams",
    "BackendSetParams",
    "ListenerParams",
    "CertificateParams",
    "HostnameParams",
    "PathRouteSetParams",
    "RuleSetParams",
    # Cloud Migrations
    "MigrationParams",
    "MigrationPlanParams",
    "TargetAssetParams",
    "ReplicationScheduleParams",
    # Compute / Storage (Phase 4)
    "InstanceParams",
    "InstanceConfigurationParams",
    "InstancePoolParams",
    "AutoScalingConfigurationParams",
    "BootVolumeParams",
    "BlockVolumeParams",
    "BlockVolumeAttachmentParams",
    # Identity / IAM (Phase 4)
    "DynamicGroupParams",
    "GroupParams",
    "PolicyParams",
    "UserParams",
    # Vault / KMS (Phase 4)
    "VaultParams",
    "KeyParams",
    "SecretParams",
    # Functions / Serverless (Phase 4)
    "FunctionsApplicationParams",
    "FunctionParams",
    # Observability (Phase 4)
    "LogGroupParams",
    "LogParams",
    "MetricAlarmParams",
    # Free-form
    "FreeFormHclParams",
]
