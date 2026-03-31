"""Migration readiness scoring engine.

Computes a weighted readiness score (0-100) for each resource based on
multiple assessment factors such as OS compatibility, shape mapping,
dependency complexity, and data volume.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Factor weights (must sum to 1.0)
# ---------------------------------------------------------------------------
WEIGHTS: dict[str, float] = {
    "os_compatibility": 0.20,
    "resource_mapping": 0.20,
    "dependency_complexity": 0.15,
    "data_volume": 0.15,
    "performance_data": 0.10,
    "sw_inventory": 0.10,
    "compliance": 0.10,
}


def _score_os_compatibility(status: str) -> int:
    """Map OS compatibility status to a 0-100 score."""
    mapping = {
        "compatible": 100,
        "compatible_with_remediation": 70,
        "unknown": 40,
        "incompatible": 10,
    }
    return mapping.get(status, 40)


def _score_dependency_complexity(count: int) -> int:
    """Score inversely proportional to dependency count."""
    if count == 0:
        return 100
    if count < 5:
        return 80
    if count < 15:
        return 60
    if count < 30:
        return 40
    return 20


def _score_data_volume(gb: float) -> int:
    """Score inversely proportional to data volume."""
    if gb < 100:
        return 100
    if gb < 500:
        return 80
    if gb < 2000:
        return 60
    if gb < 10000:
        return 40
    return 20


def compute_readiness_score(
    os_compat_status: str,
    has_oci_shape: bool,
    dependency_count: int,
    data_volume_gb: float,
    has_metrics: bool,
    sw_inventory_pct: float,
) -> tuple[int, dict[str, dict[str, float]]]:
    """Compute a weighted migration readiness score.

    Args:
        os_compat_status: One of "compatible", "compatible_with_remediation",
            "unknown", or "incompatible".
        has_oci_shape: Whether an OCI shape recommendation exists.
        dependency_count: Number of upstream/downstream dependencies.
        data_volume_gb: Total attached storage in gigabytes.
        has_metrics: Whether CloudWatch performance metrics are available.
        sw_inventory_pct: Percentage (0-100) of software inventory collected.

    Returns:
        A tuple of (final_score, factors) where *factors* is a dict mapping
        each factor name to its individual score, weight, and weighted
        contribution.
    """
    raw_scores: dict[str, int] = {
        "os_compatibility": _score_os_compatibility(os_compat_status),
        "resource_mapping": 100 if has_oci_shape else 30,
        "dependency_complexity": _score_dependency_complexity(dependency_count),
        "data_volume": _score_data_volume(data_volume_gb),
        "performance_data": 100 if has_metrics else 40,
        "sw_inventory": min(round(sw_inventory_pct), 100),
        "compliance": 80,  # default placeholder until compliance checks are wired
    }

    factors: dict[str, dict[str, float]] = {}
    total: float = 0.0

    for factor_name, weight in WEIGHTS.items():
        score = raw_scores[factor_name]
        contribution = score * weight
        total += contribution
        factors[factor_name] = {
            "score": float(score),
            "weight": weight,
            "contribution": round(contribution, 2),
        }

    final_score = round(total)
    return final_score, factors
