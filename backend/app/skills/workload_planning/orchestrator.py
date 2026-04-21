"""Workload Planning Orchestrator — per-workload runbook + anomaly analysis.

Runs the runbook and anomaly LLM agents scoped to a single workload (app group).
Reuses the proven prompts from the dependency_discovery orchestrator but focused
on the workload's specific resources, dependencies, and mapping.
"""

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

from app.gateway.model_gateway import get_model
_SKILL = "workload_planning"

RUNBOOK_SYSTEM = """\
You are an expert AWS-to-OCI migration engineer. Generate a comprehensive migration \
runbook for this specific workload being migrated from AWS to Oracle Cloud Infrastructure.

The runbook must be production-grade and include:

1. **Document Control** — maintenance window, risk level, estimated downtime, rollback time
2. **Executive Summary** — what is being migrated, key risks, critical dependencies
3. **Pre-Migration Checklist** — prerequisites, validation steps, team notifications
4. **Migration Phases** (organized by dependency order):
   - Phase name and timing (e.g., T+0→T+2h)
   - OCI service equivalents for each AWS resource
   - Step-by-step migration commands/procedures
   - Data migration steps (database dumps, transfers, imports)
   - Validation checkpoints after each phase
   - Rollback procedure for each phase
5. **Data Migration** — if databases are involved, include:
   - Dump/export commands with exact syntax
   - Transfer mechanism (SCP, OCI CLI, DMS)
   - Import/restore commands
   - Data validation (row counts, checksums)
6. **Cutover Procedure** — traffic switch, DNS updates, connection string changes
7. **Post-Migration Validation** — smoke tests, performance checks, data integrity
8. **Rollback Plan** — full rollback sequence if migration fails

Use concrete OCI service names and actual CLI commands where possible.
Format as Markdown. Detailed enough for an on-call engineer to execute without context.
"""

ANOMALY_SYSTEM = """\
You are an expert AWS infrastructure security and reliability analyst.
Analyze this workload for migration risks, anomalies, and concerns.

Focus on:
1. **Architecture Risks** — single points of failure, tight coupling, stateful components
2. **Data Risks** — data loss vectors, consistency concerns, backup gaps
3. **Security Concerns** — credential handling, encryption gaps, network exposure changes
4. **Performance Risks** — capacity mismatches, latency changes, cold start issues
5. **Dependency Risks** — external services, undocumented dependencies, DNS reliance
6. **Migration Sequencing** — what must happen first, parallel vs sequential steps
7. **Rollback Complexity** — which steps are irreversible, point-of-no-return identification

For each finding:
- Describe what was detected and why it's concerning
- Assess severity (CRITICAL / HIGH / MEDIUM / LOW)
- Provide specific mitigation recommendations

End with a prioritized action list and overall risk assessment.
Format as Markdown with clear sections and a summary risk table.
"""


def _call_agent(
    client,
    system: str,
    user_prompt: str,
    max_tokens: int = 8192,
) -> tuple[str, dict]:
    """Call an LLM agent and return (text, usage_dict)."""
    start = time.perf_counter()
    response = client.messages.create(
        model=get_model(_SKILL, "review"),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    duration = time.perf_counter() - start
    u = response.usage
    usage = {
        "tokens_input": u.input_tokens,
        "tokens_output": u.output_tokens,
        "duration_seconds": duration,
    }
    return response.content[0].text.strip(), usage


def run(
    input_content: str,
    progress_callback,
    anthropic_client,
    max_iterations: int = 3,
) -> dict:
    """Run workload planning pipeline: runbook + anomaly analysis.

    input_content should be a JSON string with:
    {
        "workload_name": "...",
        "resources": [...],
        "resource_mapping": [...],
        "dependency_edges": [...],
        "data_migration_plan": "..." (optional, if data migration skill ran)
    }
    """
    data = json.loads(input_content)
    workload_name = data.get("workload_name", "Unknown Workload")
    resources = data.get("resources", [])
    mapping = data.get("resource_mapping", [])
    edges = data.get("dependency_edges", [])
    data_mig = data.get("data_migration_plan", "")

    # Build context summary
    resource_summary = "\n".join(
        f"- {r.get('aws_type', '?')}: {r.get('name', '?')}"
        for r in resources
    )
    mapping_summary = "\n".join(
        f"- {m.get('aws_type', '?')} ({m.get('aws_name', '?')}) → {m.get('oci_resource_type', '?')} ({m.get('oci_config_summary', '')})"
        for m in mapping
    )
    edge_summary = ""
    if edges:
        edge_summary = "\n".join(
            f"- {e.get('source_resource_id', '?')[:8]} → {e.get('target_resource_id', '?')[:8]} ({e.get('edge_type', 'network')})"
            for e in edges[:20]
        )

    context = (
        f"# Workload: {workload_name}\n\n"
        f"## AWS Resources ({len(resources)})\n{resource_summary}\n\n"
        f"## AWS → OCI Mapping\n{mapping_summary}\n\n"
    )
    if edge_summary:
        context += f"## Dependencies ({len(edges)} edges)\n{edge_summary}\n\n"
    if data_mig:
        context += f"## Data Migration Plan\n{data_mig[:3000]}\n\n"

    artifacts: dict[str, str] = {}
    total_cost = 0.0

    # Agent 1: Runbook
    progress_callback("runbook", 1, 0.3, None)
    try:
        runbook_md, runbook_usage = _call_agent(
            anthropic_client,
            RUNBOOK_SYSTEM,
            context + "Generate a detailed migration runbook for this workload.",
        )
        artifacts["migration-runbook.md"] = runbook_md
        logger.info("Runbook generated: %d chars, %.1fs", len(runbook_md), runbook_usage["duration_seconds"])
    except Exception as exc:
        logger.warning("Runbook agent failed: %s", exc)
        artifacts["migration-runbook.md"] = f"# Runbook Generation Failed\n\nError: {exc}"

    # Agent 2: Anomaly Analysis
    progress_callback("anomaly", 1, 0.6, None)
    try:
        anomaly_md, anomaly_usage = _call_agent(
            anthropic_client,
            ANOMALY_SYSTEM,
            context + "Analyze this workload for migration risks and anomalies.",
            max_tokens=6144,
        )
        artifacts["anomaly-analysis.md"] = anomaly_md
        logger.info("Anomaly analysis generated: %d chars, %.1fs", len(anomaly_md), anomaly_usage["duration_seconds"])
    except Exception as exc:
        logger.warning("Anomaly agent failed: %s", exc)
        artifacts["anomaly-analysis.md"] = f"# Anomaly Analysis Failed\n\nError: {exc}"

    progress_callback("complete", 1, 1.0, "APPROVED")

    return {
        "artifacts": artifacts,
        "confidence": 0.85,
        "decision": "APPROVED",
        "iterations": 1,
        "cost": total_cost,
    }
