"""OCI rightsizing engine -- maps AWS instance types to optimal OCI shapes.

Given an AWS instance type and optional CloudWatch metrics, this module
computes the best-fit OCI Flex shape, the number of OCPUs and memory,
the projected monthly cost, and a confidence level.
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# AWS instance specifications (top 30 common instance types)
# Monthly costs are approximate On-Demand prices (us-east-1, Linux).
# ---------------------------------------------------------------------------
AWS_INSTANCE_SPECS: dict[str, dict[str, Any]] = {
    # T3 family (burstable)
    "t3.micro":    {"vcpus": 2,  "memory_gb": 1,    "monthly_cost_usd": 7.59},
    "t3.small":    {"vcpus": 2,  "memory_gb": 2,    "monthly_cost_usd": 15.18},
    "t3.medium":   {"vcpus": 2,  "memory_gb": 4,    "monthly_cost_usd": 30.37},
    "t3.large":    {"vcpus": 2,  "memory_gb": 8,    "monthly_cost_usd": 60.74},
    "t3.xlarge":   {"vcpus": 4,  "memory_gb": 16,   "monthly_cost_usd": 121.47},
    "t3.2xlarge":  {"vcpus": 8,  "memory_gb": 32,   "monthly_cost_usd": 242.94},
    # T3a family (AMD burstable)
    "t3a.micro":   {"vcpus": 2,  "memory_gb": 1,    "monthly_cost_usd": 6.86},
    "t3a.small":   {"vcpus": 2,  "memory_gb": 2,    "monthly_cost_usd": 13.72},
    "t3a.medium":  {"vcpus": 2,  "memory_gb": 4,    "monthly_cost_usd": 27.45},
    "t3a.large":   {"vcpus": 2,  "memory_gb": 8,    "monthly_cost_usd": 54.90},
    "t3a.xlarge":  {"vcpus": 4,  "memory_gb": 16,   "monthly_cost_usd": 109.79},
    "t3a.2xlarge": {"vcpus": 8,  "memory_gb": 32,   "monthly_cost_usd": 219.58},
    # M5 family (general purpose)
    "m5.large":    {"vcpus": 2,  "memory_gb": 8,    "monthly_cost_usd": 70.08},
    "m5.xlarge":   {"vcpus": 4,  "memory_gb": 16,   "monthly_cost_usd": 140.16},
    "m5.2xlarge":  {"vcpus": 8,  "memory_gb": 32,   "monthly_cost_usd": 280.32},
    "m5.4xlarge":  {"vcpus": 16, "memory_gb": 64,   "monthly_cost_usd": 560.64},
    # M6i family (general purpose, latest gen)
    "m6i.large":   {"vcpus": 2,  "memory_gb": 8,    "monthly_cost_usd": 70.08},
    "m6i.xlarge":  {"vcpus": 4,  "memory_gb": 16,   "monthly_cost_usd": 140.16},
    "m6i.2xlarge": {"vcpus": 8,  "memory_gb": 32,   "monthly_cost_usd": 280.32},
    "m6i.4xlarge": {"vcpus": 16, "memory_gb": 64,   "monthly_cost_usd": 560.64},
    # C5 family (compute optimized)
    "c5.large":    {"vcpus": 2,  "memory_gb": 4,    "monthly_cost_usd": 62.05},
    "c5.xlarge":   {"vcpus": 4,  "memory_gb": 8,    "monthly_cost_usd": 124.10},
    "c5.2xlarge":  {"vcpus": 8,  "memory_gb": 16,   "monthly_cost_usd": 248.20},
    "c5.4xlarge":  {"vcpus": 16, "memory_gb": 32,   "monthly_cost_usd": 496.40},
    # C6i family (compute optimized, latest gen)
    "c6i.large":   {"vcpus": 2,  "memory_gb": 4,    "monthly_cost_usd": 62.05},
    "c6i.xlarge":  {"vcpus": 4,  "memory_gb": 8,    "monthly_cost_usd": 124.10},
    "c6i.2xlarge": {"vcpus": 8,  "memory_gb": 16,   "monthly_cost_usd": 248.20},
    "c6i.4xlarge": {"vcpus": 16, "memory_gb": 32,   "monthly_cost_usd": 496.40},
    # R5 family (memory optimized)
    "r5.large":    {"vcpus": 2,  "memory_gb": 16,   "monthly_cost_usd": 91.98},
    "r5.xlarge":   {"vcpus": 4,  "memory_gb": 32,   "monthly_cost_usd": 183.96},
    "r5.2xlarge":  {"vcpus": 8,  "memory_gb": 64,   "monthly_cost_usd": 367.92},
    # R6i family (memory optimized, latest gen)
    "r6i.large":   {"vcpus": 2,  "memory_gb": 16,   "monthly_cost_usd": 91.98},
    "r6i.xlarge":  {"vcpus": 4,  "memory_gb": 32,   "monthly_cost_usd": 183.96},
    "r6i.2xlarge": {"vcpus": 8,  "memory_gb": 64,   "monthly_cost_usd": 367.92},
}

# ---------------------------------------------------------------------------
# OCI Flex shape catalogue
# Costs are per-hour; we multiply by 730 hours/month in calculations.
# ---------------------------------------------------------------------------
HOURS_PER_MONTH: float = 730.0

OCI_FLEX_SHAPES: dict[str, dict[str, Any]] = {
    "VM.Standard.E5.Flex": {
        "per_ocpu_cost": 0.024,
        "per_gb_cost": 0.0015,
        "min_ocpu": 1,
        "max_ocpu": 94,
        "min_mem": 1,
        "max_mem": 1024,
        "arch": "x86_64",
        "description": "AMD EPYC (general purpose, best value x86)",
    },
    "VM.Standard3.Flex": {
        "per_ocpu_cost": 0.032,
        "per_gb_cost": 0.0020,
        "min_ocpu": 1,
        "max_ocpu": 56,
        "min_mem": 1,
        "max_mem": 896,
        "arch": "x86_64",
        "description": "Intel Xeon (general purpose)",
    },
    "VM.Optimized3.Flex": {
        "per_ocpu_cost": 0.036,
        "per_gb_cost": 0.0024,
        "min_ocpu": 1,
        "max_ocpu": 36,
        "min_mem": 1,
        "max_mem": 512,
        "arch": "x86_64",
        "description": "Intel Xeon (compute optimized, high frequency)",
    },
    "VM.Standard.A2.Flex": {
        "per_ocpu_cost": 0.020,
        "per_gb_cost": 0.0013,
        "min_ocpu": 1,
        "max_ocpu": 160,
        "min_mem": 1,
        "max_mem": 1024,
        "arch": "aarch64",
        "description": "Ampere Altra (ARM-based, best price-performance)",
    },
}


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
