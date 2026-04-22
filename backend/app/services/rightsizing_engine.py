"""OCI rightsizing engine — maps AWS instance types to optimal OCI shapes.

Given an AWS instance type and optional CloudWatch metrics, this module
computes the best-fit OCI shape, the number of OCPUs and memory, the
projected monthly cost, and a confidence level.

Selection logic (in order):

1. **GPU workloads** (AWS ``gpu: true``) → map via ``aws_family_to_oci`` to
   a shape in ``oci_fixed_shapes`` (bare-metal / virtual GPU SKUs). Fixed
   shapes have a flat hourly rate; we don't do per-OCPU sizing on them.

2. **Architecture filter** — Graviton AWS (``aarch64``) maps only to
   Ampere OCI shapes (A1/A2.Flex); x86 AWS maps only to x86 OCI shapes
   (E4/E5/Standard3/Optimized3/DenseIO.E5.Flex). We never cross-arch a
   workload silently — if no compatible shape fits, we fall back to the
   default E5.Flex with a warning note.

3. **Family preference** — ``aws_family_to_oci`` carries the
   rightsizing-engine-preferred OCI flex shape per AWS family (e.g.
   ``i4i → VM.DenseIO.E5.Flex`` for NVMe-heavy workloads). If that shape
   is in the surviving candidate set and fits the sizing constraints, it
   wins. Otherwise the cheapest-that-fits inside the arch filter wins.

Instance specs and shape catalog live in
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
OCI_FIXED_SHAPES: dict[str, dict[str, Any]] = mappings.oci_fixed_shapes()
AWS_FAMILY_TO_OCI: dict[str, str] = mappings.aws_family_to_oci_shape()
HOURS_PER_MONTH: float = mappings.hours_per_month()

DEFAULT_X86_SHAPE = "VM.Standard.E5.Flex"
DEFAULT_ARM_SHAPE = "VM.Standard.A2.Flex"


def _family_of(instance_type: str) -> str:
    """Parse the AWS family prefix (``m5.large`` → ``m5``, ``db.r6g.xlarge`` → ``r6g``)."""
    parts = instance_type.split(".")
    if not parts:
        return ""
    # RDS-style prefix: drop the leading "db"
    if parts[0] == "db" and len(parts) >= 3:
        return parts[1]
    return parts[0]


def _monthly_cost(shape: dict[str, Any], ocpus: int, memory_gb: int) -> float:
    """Monthly cost for a flex shape at the given OCPU/memory config."""
    cpu_cost = ocpus * shape["per_ocpu_cost"] * HOURS_PER_MONTH
    mem_cost = memory_gb * shape["per_gb_cost"] * HOURS_PER_MONTH
    return round(cpu_cost + mem_cost, 2)


def _fixed_monthly_cost(shape: dict[str, Any]) -> float:
    """Monthly cost for a fixed (non-flex) shape at its flat hourly rate."""
    return round(shape["hourly_cost"] * HOURS_PER_MONTH, 2)


def _gpu_recommendation(
    instance_type: str,
    aws_spec: dict[str, Any],
    aws_cost: float,
    metrics: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a recommendation for GPU AWS instances, or None if we can't
    route this GPU family to a fixed OCI shape."""
    family = _family_of(instance_type)
    preferred = AWS_FAMILY_TO_OCI.get(family)
    if not preferred or preferred not in OCI_FIXED_SHAPES:
        return None

    shape = OCI_FIXED_SHAPES[preferred]
    monthly = _fixed_monthly_cost(shape)

    has_cpu = "cpu_p95" in metrics
    has_mem = "mem_p95" in metrics
    confidence = "high" if has_cpu and has_mem else ("medium" if has_cpu or has_mem else "low")

    notes: list[str] = [
        f"GPU workload ({aws_spec.get('gpu_type', 'unknown')} × {aws_spec.get('gpu_count', 1)}) "
        f"→ {shape.get('gpu_type', '?')} × {shape.get('gpu_count', 1)} on {preferred}.",
        "Fixed-shape pricing: per-shape hourly rate, not per-OCPU — resize by switching SKU.",
    ]
    if monthly < aws_cost:
        savings = round((1 - monthly / aws_cost) * 100, 1)
        notes.append(f"Estimated {savings}% monthly savings vs. AWS On-Demand.")

    return {
        "recommended_oci_shape": preferred,
        "ocpus": shape["vcpus"],
        "memory_gb": shape["memory_gb"],
        "monthly_cost": monthly,
        "aws_monthly_cost": aws_cost,
        "confidence": confidence,
        "notes": notes,
    }


def _fallback_default(
    instance_type: str, aws_arch: str = "x86_64"
) -> dict[str, Any]:
    """Used when we can't identify the AWS instance at all."""
    shape_name = DEFAULT_ARM_SHAPE if aws_arch == "aarch64" else DEFAULT_X86_SHAPE
    return {
        "recommended_oci_shape": shape_name,
        "ocpus": 2,
        "memory_gb": 8,
        "monthly_cost": _monthly_cost(OCI_FLEX_SHAPES[shape_name], 2, 8),
        "aws_monthly_cost": 0.0,
        "confidence": "low",
        "notes": [
            f"Unknown AWS instance type '{instance_type}'; using default shape.",
            "Manual review recommended.",
        ],
    }


def compute_rightsizing(
    instance_type: str,
    metrics: dict[str, Any] | None = None,
    comfort_factor: float = 1.2,
) -> dict[str, Any]:
    """Compute the optimal OCI shape for an AWS instance type.

    Args:
        instance_type: AWS instance type (e.g. ``m5.large``, ``m7g.xlarge``,
            ``p4d.24xlarge``). RDS-style ``db.r6g.xlarge`` prefixes are
            stripped.
        metrics: Optional dict with keys like ``cpu_p95`` (0-100) and
            ``mem_p95`` (0-100) representing utilisation percentages.
        comfort_factor: Multiplier applied to effective resource needs
            to provide headroom (default 1.2 = 20% buffer).

    Returns:
        Dict with keys: recommended_oci_shape, ocpus, memory_gb,
        monthly_cost, aws_monthly_cost, confidence, notes.
    """
    if metrics is None:
        metrics = {}

    aws_spec = AWS_INSTANCE_SPECS.get(instance_type)
    if aws_spec is None:
        return _fallback_default(instance_type)

    aws_vcpus: int = aws_spec["vcpus"]
    aws_memory: float = aws_spec["memory_gb"]
    aws_cost: float = aws_spec["monthly_cost_usd"]
    aws_arch: str = aws_spec.get("arch", "x86_64")
    aws_is_gpu: bool = bool(aws_spec.get("gpu", False))
    aws_family = _family_of(instance_type)

    # ── GPU path ──────────────────────────────────────────────────────────
    # GPU workloads need a GPU shape; flex-shape math doesn't apply to bare-metal SKUs.
    if aws_is_gpu:
        gpu_rec = _gpu_recommendation(instance_type, aws_spec, aws_cost, metrics)
        if gpu_rec is not None:
            return gpu_rec
        # No GPU routing for this family — fall through to flex with a loud note.

    # ── Flex shape path ───────────────────────────────────────────────────
    cpu_util = metrics.get("cpu_p95", 50) / 100.0
    mem_util = metrics.get("mem_p95", 70) / 100.0

    effective_cpu = max(1, math.ceil(cpu_util * aws_vcpus * comfort_factor))
    effective_mem = max(1, math.ceil(mem_util * aws_memory * comfort_factor))

    preferred_name = AWS_FAMILY_TO_OCI.get(aws_family)

    # Hard-filter by arch. x86→x86, aarch64→aarch64. No silent cross-arch.
    arch_matched: list[str] = [
        name for name, shape in OCI_FLEX_SHAPES.items()
        if shape.get("arch") == aws_arch
    ]

    # If preferred shape is arch-compatible and known, make sure it's in the pool.
    if preferred_name and preferred_name in OCI_FLEX_SHAPES:
        pref_arch = OCI_FLEX_SHAPES[preferred_name].get("arch")
        if pref_arch == aws_arch and preferred_name not in arch_matched:
            arch_matched.insert(0, preferred_name)

    # Filter to shapes that fit the sizing envelope.
    fitting = [
        name for name in arch_matched
        if OCI_FLEX_SHAPES[name]["min_ocpu"] <= effective_cpu <= OCI_FLEX_SHAPES[name]["max_ocpu"]
        and OCI_FLEX_SHAPES[name]["min_mem"] <= effective_mem <= OCI_FLEX_SHAPES[name]["max_mem"]
    ]

    # Pick the winner. Family preference wins if it fits; otherwise cheapest-that-fits.
    notes: list[str] = []
    best_shape_name: str | None = None

    if preferred_name and preferred_name in fitting:
        best_shape_name = preferred_name
        if fitting[0] != preferred_name:  # would not have been picked by cost alone
            notes.append(
                f"Family preference: {aws_family} → {preferred_name} "
                f"(workload-appropriate target for this AWS family)."
            )
    elif fitting:
        best_shape_name = min(
            fitting,
            key=lambda n: _monthly_cost(OCI_FLEX_SHAPES[n], effective_cpu, effective_mem),
        )

    # Last-resort fallback if no arch-matching shape fit — return default with a warning.
    if best_shape_name is None:
        default_name = DEFAULT_ARM_SHAPE if aws_arch == "aarch64" else DEFAULT_X86_SHAPE
        best_shape_name = default_name
        shape = OCI_FLEX_SHAPES[best_shape_name]
        effective_cpu = min(effective_cpu, shape["max_ocpu"])
        effective_mem = min(effective_mem, shape["max_mem"])
        notes.append(
            f"No {aws_arch} flex shape fit the sizing envelope; using default "
            f"{default_name}. Manual review recommended."
        )

    best_cost = _monthly_cost(OCI_FLEX_SHAPES[best_shape_name], effective_cpu, effective_mem)

    # Confidence is driven by what metrics were supplied.
    has_cpu = "cpu_p95" in metrics
    has_mem = "mem_p95" in metrics
    if has_cpu and has_mem:
        confidence = "high"
    elif has_cpu:
        confidence = "medium"
    else:
        confidence = "low"

    # Advisory notes
    if aws_is_gpu:
        notes.append(
            f"Source is a GPU instance ({aws_spec.get('gpu_type', 'unknown')}) but "
            f"no OCI GPU shape is mapped for family '{aws_family}'. Mapped to flex "
            "shape — CRITICAL: review before accepting."
        )
    if OCI_FLEX_SHAPES[best_shape_name].get("arch") == "aarch64" and aws_arch != "aarch64":
        notes.append("ARM-based shape — ensure the application builds/runs on aarch64.")
    if OCI_FLEX_SHAPES[best_shape_name].get("arch") == "aarch64" and aws_arch == "aarch64":
        notes.append("Staying on Ampere ARM — same arch as source Graviton, no recompile required.")
    if aws_arch == "aarch64" and OCI_FLEX_SHAPES[best_shape_name].get("arch") == "x86_64":
        notes.append(
            "Source is Graviton (ARM) but target is x86 — application binaries must be rebuilt "
            "for x86_64. Consider VM.Standard.A2.Flex to avoid recompile."
        )
    if not has_cpu:
        notes.append("No CPU utilisation metrics available; using 50% estimate.")
    if not has_mem:
        notes.append("No memory utilisation metrics available; using 70% estimate.")
    if best_cost < aws_cost:
        savings_pct = round((1 - best_cost / aws_cost) * 100, 1)
        notes.append(f"Estimated {savings_pct}% monthly savings vs. AWS On-Demand.")
    if comfort_factor != 1.2:
        notes.append(f"Custom comfort factor of {comfort_factor}x applied.")

    return {
        "recommended_oci_shape": best_shape_name,
        "ocpus": effective_cpu,
        "memory_gb": effective_mem,
        "monthly_cost": best_cost,
        "aws_monthly_cost": aws_cost,
        "confidence": confidence,
        "notes": notes,
    }
