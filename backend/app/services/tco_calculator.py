"""Total Cost of Ownership (TCO) calculator.

Aggregates per-resource cost data into a full TCO comparison between AWS
and OCI, including category breakdowns and multi-year projections with
OCI commitment discount tiers.
"""

from __future__ import annotations

from typing import Any

from app import mappings

# Storage / network / discount rates now live in
# backend/data/mappings/pricing.yaml — see app.mappings.
AWS_EBS_COST_PER_GB: float = mappings.aws_ebs_per_gb()
OCI_BLOCK_COST_PER_GB: float = mappings.oci_block_per_gb()
AWS_NETWORK_COST_PER_GB: float = mappings.aws_egress_per_gb()
OCI_NETWORK_COST_PER_GB: float = mappings.oci_egress_per_gb()
OCI_ANNUAL_FLEX_DISCOUNT: float = mappings.oci_annual_flex_discount()
OCI_MONTHLY_FLEX_DISCOUNT: float = mappings.oci_monthly_flex_discount()

# ---------------------------------------------------------------------------
# Resource-type to cost category mapping
# ---------------------------------------------------------------------------
_CATEGORY_MAP: dict[str, str] = {
    "ec2":       "compute",
    "compute":   "compute",
    "instance":  "compute",
    "rds":       "database",
    "database":  "database",
    "aurora":    "database",
    "ebs":       "storage",
    "s3":        "storage",
    "storage":   "storage",
    "elb":       "networking",
    "alb":       "networking",
    "nlb":       "networking",
    "nat":       "networking",
    "vpn":       "networking",
    "networking": "networking",
}


def _categorise(resource_type: str) -> str:
    """Map a resource_type string to one of the four cost categories."""
    key = resource_type.strip().lower()
    for token, category in _CATEGORY_MAP.items():
        if token in key:
            return category
    # Default unmapped resources to networking (covers Transit Gateway, etc.)
    return "networking"


def compute_tco(resource_assessments: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute a full TCO comparison from a list of resource assessments.

    Args:
        resource_assessments: Each dict should contain at minimum:
            - ``aws_monthly_cost`` (float)
            - ``oci_monthly_cost`` (float)
            - ``resource_type`` (str) -- used for category breakdown
            - ``storage_gb`` (float, optional) -- attached storage volume

    Returns:
        Dict with top-level monthly totals, annual savings, percentage
        savings, a per-category breakdown, and three-year TCO projections
        under different OCI commitment models.
    """
    # Initialise category buckets
    breakdown: dict[str, dict[str, float]] = {
        "compute":    {"aws": 0.0, "oci": 0.0},
        "storage":    {"aws": 0.0, "oci": 0.0},
        "database":   {"aws": 0.0, "oci": 0.0},
        "networking": {"aws": 0.0, "oci": 0.0},
    }

    for ra in resource_assessments:
        aws_cost = float(ra.get("aws_monthly_cost", 0.0))
        oci_cost = float(ra.get("oci_monthly_cost", 0.0))
        resource_type = ra.get("resource_type", "compute")
        storage_gb = float(ra.get("storage_gb", 0.0))

        category = _categorise(resource_type)
        breakdown[category]["aws"] += aws_cost
        breakdown[category]["oci"] += oci_cost

        # Add storage costs when storage volume information is present
        if storage_gb > 0:
            breakdown["storage"]["aws"] += storage_gb * AWS_EBS_COST_PER_GB
            breakdown["storage"]["oci"] += storage_gb * OCI_BLOCK_COST_PER_GB

    # Round category totals for cleaner output
    for cat in breakdown:
        breakdown[cat]["aws"] = round(breakdown[cat]["aws"], 2)
        breakdown[cat]["oci"] = round(breakdown[cat]["oci"], 2)

    aws_monthly = round(sum(b["aws"] for b in breakdown.values()), 2)
    oci_monthly = round(sum(b["oci"] for b in breakdown.values()), 2)
    annual_savings = round((aws_monthly - oci_monthly) * 12, 2)
    savings_pct = round((1 - oci_monthly / aws_monthly) * 100, 2) if aws_monthly > 0 else 0.0

    # Three-year projections
    months_3yr = 36
    aws_3yr = round(aws_monthly * months_3yr, 2)
    oci_paygo_3yr = round(oci_monthly * months_3yr, 2)
    oci_annual_flex_3yr = round(oci_monthly * (1 - OCI_ANNUAL_FLEX_DISCOUNT) * months_3yr, 2)
    oci_monthly_flex_3yr = round(oci_monthly * (1 - OCI_MONTHLY_FLEX_DISCOUNT) * months_3yr, 2)

    return {
        "aws_monthly": aws_monthly,
        "oci_monthly": oci_monthly,
        "annual_savings": annual_savings,
        "savings_pct": savings_pct,
        "breakdown": breakdown,
        "three_year_tco": {
            "aws_total": aws_3yr,
            "oci_paygo": oci_paygo_3yr,
            "oci_annual_flex": oci_annual_flex_3yr,
            "oci_monthly_flex": oci_monthly_flex_3yr,
        },
    }
