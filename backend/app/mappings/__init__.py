"""Single source of truth for AWS→OCI mapping data.

Loads ``backend/data/mappings/*.yaml`` once at import time and exposes typed
accessors used by:
  • app.services.resource_mapper        (deterministic per-resource mapping)
  • app.services.rightsizing_engine     (shape catalog + AWS specs)
  • app.services.tco_calculator         (storage / network / discount rates)
  • skill orchestrators                 (table injected into LLM prompts)

Prose rules — ordering constraints, edge cases, examples — stay in the
per-skill ``workflows/*.md`` files. Those files reference the mapping
tables via the ``render_resource_table_md`` / ``render_iam_table_md``
helpers below, so the LLM sees the same facts the Python code is reading.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

_MAPPINGS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "mappings"


@functools.lru_cache(maxsize=None)
def _load(name: str) -> dict[str, Any]:
    """Load + cache one YAML file. Raises FileNotFoundError on bad name."""
    path = _MAPPINGS_DIR / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def reload() -> None:
    """Clear the cache — useful in tests or if files change on disk."""
    _load.cache_clear()


# ─── Resources ────────────────────────────────────────────────────────────────

def all_resources() -> list[dict[str, Any]]:
    """Return every ``resources[]`` entry, ordered as in resources.yaml."""
    return _load("resources").get("resources", []) or []


def resource_by_aws_type(aws_type: str) -> dict[str, Any] | None:
    """Look up one resource row by exact ``aws_type`` match."""
    for r in all_resources():
        if r.get("aws_type") == aws_type:
            return r
    return None


def resources_for_skill(skill: str) -> list[dict[str, Any]]:
    """Return every resource row whose ``skill`` field matches."""
    return [r for r in all_resources() if r.get("skill") == skill]


def volume_type_mapping() -> dict[str, dict[str, Any]]:
    return _load("resources").get("storage", {}).get("ebs_to_block_volume", {}) or {}


def rds_engine_mapping() -> dict[str, dict[str, Any]]:
    return _load("resources").get("database", {}).get("rds_engine", {}) or {}


def non_rds_engine_mapping() -> dict[str, dict[str, Any]]:
    """Managed-DB engines we encounter outside RDS (Redis, Mongo, OpenSearch,
    Kafka, Cassandra, etc.). Consumed by database_translation when input
    originates from ElastiCache / DocumentDB / OpenSearch / MSK / etc."""
    return _load("resources").get("database", {}).get("non_rds_engine", {}) or {}


def local_db_keywords() -> dict[str, dict[str, Any]]:
    return _load("resources").get("database", {}).get("local_db_keywords", {}) or {}


# ─── Instance shapes ──────────────────────────────────────────────────────────

def aws_instance_specs() -> dict[str, dict[str, Any]]:
    return _load("instance_shapes").get("aws_instances", {}) or {}


def oci_flex_shapes() -> dict[str, dict[str, Any]]:
    return _load("instance_shapes").get("oci_flex_shapes", {}) or {}


def oci_fixed_shapes() -> dict[str, dict[str, Any]]:
    """OCI non-flex shapes (GPU + bare metal). Billed per-shape-per-hour
    instead of per-OCPU/per-GB like flex shapes."""
    return _load("instance_shapes").get("oci_fixed_shapes", {}) or {}


def aws_family_to_oci_shape() -> dict[str, str]:
    """AWS family prefix ('m7i', 't4g', 'p5', …) → preferred OCI shape name.
    Used by rightsizing to pick an arch-appropriate OCI target before falling
    back to a default general-purpose shape."""
    return _load("instance_shapes").get("aws_family_to_oci", {}) or {}


def hours_per_month() -> float:
    return float(_load("instance_shapes").get("hours_per_month", 730.0))


# ─── IAM ──────────────────────────────────────────────────────────────────────

def iam_actions() -> dict[str, dict[str, Any]]:
    return _load("iam").get("actions", {}) or {}


# ─── Pricing ──────────────────────────────────────────────────────────────────

def pricing() -> dict[str, Any]:
    """Whole pricing.yaml document."""
    return _load("pricing")


def aws_ebs_per_gb() -> float:
    return float(_load("pricing").get("storage", {}).get("aws_ebs_per_gb_month", 0.10))


def oci_block_per_gb() -> float:
    return float(_load("pricing").get("storage", {}).get("oci_block_per_gb_month", 0.0255))


def aws_egress_per_gb() -> float:
    return float(_load("pricing").get("network", {}).get("aws_egress_per_gb", 0.09))


def oci_egress_per_gb() -> float:
    return float(_load("pricing").get("network", {}).get("oci_egress_per_gb", 0.0085))


def oci_annual_flex_discount() -> float:
    return float(_load("pricing").get("oci_commitment_discounts", {}).get("annual_flex", 0.33))


def oci_monthly_flex_discount() -> float:
    return float(_load("pricing").get("oci_commitment_discounts", {}).get("monthly_flex", 0.17))


def oci_four_year_discount() -> float:
    return float(_load("pricing").get("oci_commitment_discounts", {}).get("four_year_flex", 0.50))


# New-section accessors. These return the whole sub-dict so callers can pick
# the specific rate they need without a thicket of individual getters.

def load_balancer_pricing() -> dict[str, float]:
    """Hourly LB rates (ALB/NLB/OCI LB shapes, OCI NLB per-GB)."""
    return _load("pricing").get("load_balancer", {}) or {}


def kms_pricing() -> dict[str, float]:
    """KMS / Vault key monthly + API request rates."""
    return _load("pricing").get("kms", {}) or {}


def secrets_pricing() -> dict[str, float]:
    """Secrets Manager / OCI Vault Secret monthly + API rates."""
    return _load("pricing").get("secrets", {}) or {}


def compute_discounts() -> dict[str, float]:
    """Spot / preemptible discount multipliers."""
    return _load("pricing").get("compute", {}) or {}


def database_markups() -> dict[str, float]:
    """Managed-DB markup multipliers (RDS, OCI DB, Autonomous)."""
    return _load("pricing").get("database", {}) or {}


def network_pricing() -> dict[str, float]:
    """Full network pricing section (NAT Gateway, TGW/DRG, VPN, DirectConnect/FastConnect)."""
    return _load("pricing").get("network", {}) or {}


def storage_pricing() -> dict[str, float]:
    """Full storage pricing section (EBS tiers, S3 tiers, EFS, FSS, request rates)."""
    return _load("pricing").get("storage", {}) or {}


# ─── Prompt injection helpers ─────────────────────────────────────────────────

def render_resource_table_md(skill: str | None = None) -> str:
    """Render the resource mapping as a markdown table for LLM prompts.

    When ``skill`` is supplied, only rows targeting that skill are included,
    which keeps each skill's prompt focused on resources it can translate.
    """
    rows = resources_for_skill(skill) if skill else all_resources()
    if not rows:
        return "_(no mapping rows)_"

    lines = [
        "| AWS Type | OCI Service | Terraform Resource | Confidence | Notes |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        notes_list = r.get("notes") or []
        gaps_list = r.get("gaps") or []
        parts = []
        if notes_list:
            parts.extend(notes_list)
        if gaps_list:
            parts.extend(f"⚠ {g}" for g in gaps_list)
        notes = " / ".join(parts).replace("\n", " ").replace("|", "\\|")
        lines.append(
            f"| `{r.get('aws_type','')}` "
            f"| {r.get('oci_service','')} "
            f"| `{r.get('oci_terraform') or '—'}` "
            f"| {r.get('mapping_confidence','?')} "
            f"| {notes} |"
        )
    return "\n".join(lines)


def render_iam_table_md() -> str:
    """Render the IAM action → OCI verb mapping as a markdown table."""
    actions = iam_actions()
    if not actions:
        return "_(no IAM mapping rows)_"

    lines = [
        "| AWS Action | OCI Verb | OCI Resource | OCI Service | Notes |",
        "|---|---|---|---|---|",
    ]
    for action, info in actions.items():
        notes = str(info.get("notes", "")).replace("|", "\\|")
        lines.append(
            f"| `{action}` "
            f"| `{info.get('oci_verb','')}` "
            f"| `{info.get('oci_resource','')}` "
            f"| `{info.get('oci_service','')}` "
            f"| {notes} |"
        )
    return "\n".join(lines)


def render_shape_table_md() -> str:
    """Render the OCI flex shape catalog as a markdown table.

    Injected into the ec2_translation system prompt so the writer LLM sees
    the same shapes the rightsizing engine is picking from.
    """
    shapes = oci_flex_shapes()
    if not shapes:
        return "_(no shape catalog)_"
    lines = [
        "| OCI Shape | Arch | OCPU Range | Memory Range (GB) | $/OCPU/hr | $/GB/hr | Description |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, s in shapes.items():
        lines.append(
            f"| `{name}` "
            f"| {s.get('arch','')} "
            f"| {s.get('min_ocpu','?')}–{s.get('max_ocpu','?')} "
            f"| {s.get('min_mem','?')}–{s.get('max_mem','?')} "
            f"| {s.get('per_ocpu_cost','?')} "
            f"| {s.get('per_gb_cost','?')} "
            f"| {s.get('description','')} |"
        )
    return "\n".join(lines)
