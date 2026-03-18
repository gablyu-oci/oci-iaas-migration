"""CTO-readable plain-text migration report."""

from __future__ import annotations

from ..analysis.classifier import DependencyInfo

RISK_SYMBOLS = {
    "critical": "[!!!]",
    "high": "[!! ]",
    "medium": "[!  ]",
    "low": "[   ]",
}


def format_report(
    dependencies: list[DependencyInfo],
    migration_steps: list[dict],
    *,
    limit: int = 20,
    has_cycles: bool = False,
    cycles: list[list[str]] | None = None,
) -> str:
    """Generate a CTO-readable migration sequencing report."""
    lines: list[str] = []

    lines.append("=" * 72)
    lines.append("  AWS DEPENDENCY DISCOVERY — MIGRATION SEQUENCING REPORT")
    lines.append("=" * 72)
    lines.append("")

    # Summary stats
    total = len(dependencies)
    critical = sum(1 for d in dependencies if d.risk_level == "critical")
    high = sum(1 for d in dependencies if d.risk_level == "high")
    lines.append(f"  Total dependencies discovered: {total}")
    lines.append(f"  Critical: {critical}  |  High: {high}  |  "
                 f"Medium: {sum(1 for d in dependencies if d.risk_level == 'medium')}  |  "
                 f"Low: {sum(1 for d in dependencies if d.risk_level == 'low')}")
    lines.append("")

    # Cycle warnings
    if has_cycles and cycles:
        lines.append("-" * 72)
        lines.append("  WARNING: CIRCULAR DEPENDENCIES DETECTED")
        lines.append("-" * 72)
        for cycle in cycles[:5]:
            lines.append(f"    Cycle: {' -> '.join(cycle)} -> {cycle[0]}")
        lines.append("")
        lines.append("  These services have mutual dependencies and cannot be migrated")
        lines.append("  independently. They must be migrated together or with a cutover plan.")
        lines.append("")

    # Top dependencies
    lines.append("-" * 72)
    lines.append("  TOP DEPENDENCIES (ranked by risk)")
    lines.append("-" * 72)
    lines.append("")
    for i, dep in enumerate(dependencies[:limit], 1):
        sym = RISK_SYMBOLS.get(dep.risk_level, "[   ]")
        lines.append(f"  {i:3d}. {sym} {dep.source}  -->  {dep.target}")
        lines.append(f"       {dep.reason}")
        lines.append(f"       BREAKS IF WRONG: {dep.breaks_if_wrong}")
        lines.append("")

    # Migration order
    lines.append("-" * 72)
    lines.append("  RECOMMENDED MIGRATION ORDER")
    lines.append("-" * 72)
    lines.append("")
    lines.append("  Migrate in this order to minimize breakage:")
    lines.append("")
    for step in migration_steps:
        deps = step["depends_on"]
        dep_str = ""
        if deps:
            dep_str = f" (after: {', '.join(deps)})"
        dependents = step.get("depended_by", [])
        warn = ""
        if len(dependents) >= 3:
            warn = f"  *** HIGH FAN-OUT: {len(dependents)} services depend on this ***"
        lines.append(f"  Step {step['step']:3d}: {step['node_id']}{dep_str}")
        if warn:
            lines.append(f"           {warn}")

    lines.append("")
    lines.append("=" * 72)
    lines.append("  END OF REPORT")
    lines.append("=" * 72)

    return "\n".join(lines)
