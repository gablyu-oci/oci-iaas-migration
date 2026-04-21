"""OCI rightsizing engine — maps AWS instance types to optimal OCI shapes.

Given an AWS instance type and optional CloudWatch metrics, this module
computes the best-fit OCI Flex shape, the number of OCPUs and memory,
the projected monthly cost, and a confidence level.

Instance specs and the OCI shape catalog now live in
``backend/data/mappings/instance_shapes.yaml`` — see ``app.mappings``.
"""

from __future__ import annotations

import math
from typing import Any

from app import mappings

# Back-compat re-exports: some modules still import these constants. They
# now resolve through the YAML loader at import time.
AWS_INSTANCE_SPECS: dict[str, dict[str, Any]] = mappings.aws_instance_specs()
OCI_FLEX_SHAPES: dict[str, dict[str, Any]] = mappings.oci_flex_shapes()
HOURS_PER_MONTH: float = mappings.hours_per_month()


def _monthly_cost(shape: dict[str, Any], ocpus: int, memory_gb: int) -> float:
    """Compute the monthly cost for a given shape configuration."""
    cpu_cost = ocpus * shape["per_ocpu_cost"] * HOURS_PER_MONTH
    mem_cost = memory_gb * shape["per_gb_cost"] * HOURS_PER_MONTH
    return round(cpu_cost + mem_cost, 2)


def compute_rightsizing(
    instance_type: str,
    metrics: dict[str, Any] | None = None,
    comfort_factor: float = 1.2,
) -> dict[str, Any]:
    """Compute the optimal OCI shape for an AWS instance type.

    Args:
        instance_type: AWS instance type (e.g. "m5.large").
        metrics: Optional dict with keys like ``cpu_p95`` (0-100) and
            ``mem_p95`` (0-100) representing utilisation percentages.
        comfort_factor: Multiplier applied to effective resource needs
            to provide headroom (default 1.2 = 20 % buffer).

    Returns:
        Dict with keys: recommended_oci_shape, ocpus, memory_gb,
        monthly_cost, confidence, notes.
    """
    if metrics is None:
        metrics = {}

    aws_spec = AWS_INSTANCE_SPECS.get(instance_type)
    if aws_spec is None:
        return {
            "recommended_oci_shape": "VM.Standard.E5.Flex",
            "ocpus": 2,
            "memory_gb": 8,
            "monthly_cost": _monthly_cost(OCI_FLEX_SHAPES["VM.Standard.E5.Flex"], 2, 8),
            "aws_monthly_cost": 0.0,
            "confidence": "low",
            "notes": [
                f"Unknown AWS instance type '{instance_type}'; using default shape.",
                "Manual review recommended.",
            ],
        }

    aws_vcpus: int = aws_spec["vcpus"]
    aws_memory: float = aws_spec["memory_gb"]
    aws_cost: float = aws_spec["monthly_cost_usd"]

    # Determine effective resource requirements based on utilisation metrics
    cpu_util = metrics.get("cpu_p95", 50) / 100.0
    mem_util = metrics.get("mem_p95", 70) / 100.0

    effective_cpu = max(1, math.ceil(cpu_util * aws_vcpus * comfort_factor))
    effective_mem = max(1, math.ceil(mem_util * aws_memory * comfort_factor))

    # Evaluate every OCI shape and pick the cheapest that fits
    best_shape_name: str | None = None
    best_cost: float = float("inf")
    best_ocpus: int = effective_cpu
    best_mem: int = effective_mem

    for shape_name, shape in OCI_FLEX_SHAPES.items():
        if effective_cpu < shape["min_ocpu"] or effective_cpu > shape["max_ocpu"]:
            continue
        if effective_mem < shape["min_mem"] or effective_mem > shape["max_mem"]:
            continue

        cost = _monthly_cost(shape, effective_cpu, effective_mem)
        if cost < best_cost:
            best_cost = cost
            best_shape_name = shape_name
            best_ocpus = effective_cpu
            best_mem = effective_mem

    # Fallback if no shape matched constraints (should not happen with
    # reasonable inputs, but handle gracefully)
    if best_shape_name is None:
        best_shape_name = "VM.Standard.E5.Flex"
        best_ocpus = min(effective_cpu, OCI_FLEX_SHAPES[best_shape_name]["max_ocpu"])
        best_mem = min(effective_mem, OCI_FLEX_SHAPES[best_shape_name]["max_mem"])
        best_cost = _monthly_cost(OCI_FLEX_SHAPES[best_shape_name], best_ocpus, best_mem)

    # Determine confidence level
    has_cpu = "cpu_p95" in metrics
    has_mem = "mem_p95" in metrics
    if has_cpu and has_mem:
        confidence = "high"
    elif has_cpu:
        confidence = "medium"
    else:
        confidence = "low"

    # Build advisory notes
    notes: list[str] = []
    if OCI_FLEX_SHAPES[best_shape_name]["arch"] == "aarch64":
        notes.append("ARM-based shape (Ampere Altra) -- verify application compatibility.")
    if not has_cpu:
        notes.append("No CPU utilisation metrics available; using 50 % estimate.")
    if not has_mem:
        notes.append("No memory utilisation metrics available; using 70 % estimate.")
    if best_cost < aws_cost:
        savings_pct = round((1 - best_cost / aws_cost) * 100, 1)
        notes.append(f"Estimated {savings_pct} % monthly savings vs. AWS On-Demand.")
    if comfort_factor != 1.2:
        notes.append(f"Custom comfort factor of {comfort_factor}x applied.")

    return {
        "recommended_oci_shape": best_shape_name,
        "ocpus": best_ocpus,
        "memory_gb": best_mem,
        "monthly_cost": best_cost,
        "aws_monthly_cost": aws_cost,
        "confidence": confidence,
        "notes": notes,
    }
