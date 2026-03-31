"""Data Migration Planning Orchestrator.

Generates a detailed data migration procedure for moving database data
from AWS (RDS or local DB on EC2) to OCI.  Outputs markdown, not Terraform.

Uses the Enhancement → Review → Fix loop from BaseTranslationOrchestrator.
"""

import json
from datetime import datetime, timezone
from typing import Any

from app.skills.shared.base_orchestrator import BaseTranslationOrchestrator


ENHANCEMENT_SYSTEM = """\
You are an expert AWS-to-OCI data migration architect. Generate a comprehensive \
data migration plan for moving database data from AWS to Oracle Cloud Infrastructure.

Your plan MUST cover:

1. **Source Analysis**: Database engine, version, size, replication status, current load
2. **Tool Selection**: Choose the right migration tool:
   - Oracle DB: Zero Downtime Migration (ZDM) or OCI Database Migration Service (DMS)
   - MySQL/MariaDB: mysqldump + mysql import, or OCI DMS, or MySQL Shell dump/load
   - PostgreSQL: pg_dump/pg_restore, or OCI DMS, or logical replication
   - Local DB on EC2 (not RDS): SSH + dump tool export, transfer via OCI CLI, import
   - SQL Server: Backup/restore to self-hosted on OCI Compute
   - DynamoDB: Export to S3 + ETL to OCI NoSQL
   - S3 data: rclone sync or OCI CLI bulk-upload to Object Storage
   - Redis/ElastiCache: RDB dump + restore, or cold migration
3. **Pre-Migration Steps**: Schema audit, capacity planning, connectivity setup, \
   test migration run, backup verification
4. **Migration Procedure**: Step-by-step commands (actual CLI commands where possible), \
   with estimated duration per step
5. **Cutover Plan**: Final sync, application freeze, DNS/connection string switch, \
   monitoring checkpoints
6. **Validation**: Row count verification, checksum comparison, application smoke tests
7. **Rollback Plan**: How to revert if migration fails at each stage
8. **Downtime Estimate**: Expected downtime window with breakdown

For LOCAL databases on EC2 (not managed RDS):
- Include SSH access for dump export
- Include scp/rsync or OCI CLI for data transfer
- Recommend upgrading to managed OCI DB service
- Address application connection string changes

Return JSON with this schema:
{
  "migration_tool": "primary tool name",
  "source_summary": "brief source description",
  "target_summary": "brief OCI target description",
  "estimated_downtime": "e.g., 30 minutes",
  "estimated_data_size": "e.g., 500 MB",
  "risk_level": "low|medium|high",
  "pre_migration_steps": ["step1", "step2"],
  "migration_procedure": [
    {"step": 1, "action": "...", "command": "...", "duration": "5 min", "notes": "..."}
  ],
  "cutover_steps": ["step1", "step2"],
  "validation_steps": ["step1", "step2"],
  "rollback_plan": ["step1", "step2"],
  "gaps_and_risks": ["risk1", "risk2"],
  "architecture_notes": ["note1", "note2"]
}
"""

REVIEW_SYSTEM = """\
You are a senior database migration engineer reviewing a data migration plan for \
AWS-to-OCI migration. Check for:

1. **Completeness**: All databases covered? Pre-migration, cutover, validation, rollback?
2. **Correctness**: Right tool for each engine? Correct CLI commands? Valid OCI targets?
3. **Risk Management**: Downtime realistic? Rollback tested? Data loss prevention?
4. **Production Readiness**: Connection string changes? Application freeze timing? Monitoring?
5. **Security**: Credentials handling? Encrypted transfer? Network security?

Classify issues by severity:
  CRITICAL -- Data loss risk, wrong migration tool, missing rollback plan
  HIGH     -- Missing validation steps, incorrect commands, unrealistic timing
  MEDIUM   -- Missing optimization, incomplete documentation
  LOW      -- Style, formatting, minor suggestions

Return ONLY JSON:
{
  "decision": "APPROVED|APPROVED_WITH_NOTES|NEEDS_FIXES",
  "issues": [
    {
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "location": "section reference",
      "description": "what's wrong",
      "fix_suggestion": "how to fix"
    }
  ],
  "review_summary": "2-3 sentence summary"
}
"""

FIX_SYSTEM = """\
You are an expert data migration engineer. Fix the issues found during review of \
an AWS-to-OCI data migration plan. Return the corrected plan in the same JSON schema \
as the original, addressing all CRITICAL and HIGH severity issues.
"""


class DataMigrationOrchestrator(BaseTranslationOrchestrator):
    SKILL_TYPE = "data_migration_planning"
    PROJECT_TYPE = "data-migration"
    REPORT_FILENAME = "data-migration-plan.md"

    ENHANCEMENT_SYSTEM = ENHANCEMENT_SYSTEM
    REVIEW_SYSTEM = REVIEW_SYSTEM
    FIX_SYSTEM = FIX_SYSTEM

    def build_enhancement_prompt(self, input_content: str) -> str:
        return (
            "Generate a detailed data migration plan for the following workload:\n\n"
            f"{input_content}\n\n"
            "Return the migration plan as JSON following the schema in your instructions."
        )

    def build_review_prompt(self, enhancement_response: str) -> str:
        return (
            "Review this data migration plan for completeness, correctness, "
            "and production readiness:\n\n"
            f"```json\n{enhancement_response}\n```\n\n"
            "Return your review as JSON."
        )

    def build_fix_prompt(self, enhancement_response: str, issues: list[dict]) -> str:
        issues_text = "\n".join(
            f"- [{i['severity']}] {i['description']}: {i.get('fix_suggestion', '')}"
            for i in issues
        )
        return (
            f"Fix these issues in the data migration plan:\n\n{issues_text}\n\n"
            f"Original plan:\n```json\n{enhancement_response}\n```\n\n"
            "Return the corrected plan as JSON."
        )

    def run_gap_analysis(self, result: dict) -> dict:
        has_procedure = bool(result.get("migration_procedure"))
        has_validation = bool(result.get("validation_steps"))
        has_rollback = bool(result.get("rollback_plan"))
        has_tool = bool(result.get("migration_tool"))

        total = 4
        mapped = sum([has_procedure, has_validation, has_rollback, has_tool])

        return {
            "total_items": total,
            "mapped_items": mapped,
            "coverage_pct": round(mapped / total * 100, 1),
            "sections_present": {
                "migration_procedure": has_procedure,
                "validation_steps": has_validation,
                "rollback_plan": has_rollback,
                "tool_selected": has_tool,
            },
        }

    def generate_report_md(self, result: dict, gap_analysis: dict) -> str:
        lines = [
            f"# Data Migration Plan",
            "",
            f"**Migration Tool:** {result.get('migration_tool', 'TBD')}",
            f"**Source:** {result.get('source_summary', 'N/A')}",
            f"**Target:** {result.get('target_summary', 'N/A')}",
            f"**Estimated Downtime:** {result.get('estimated_downtime', 'TBD')}",
            f"**Data Size:** {result.get('estimated_data_size', 'TBD')}",
            f"**Risk Level:** {result.get('risk_level', 'TBD')}",
            "",
            "## Pre-Migration Steps",
            "",
        ]
        for step in result.get("pre_migration_steps", []):
            lines.append(f"- [ ] {step}")

        lines.extend(["", "## Migration Procedure", ""])
        for step in result.get("migration_procedure", []):
            lines.append(f"### Step {step.get('step', '?')}: {step.get('action', '')}")
            if step.get("command"):
                lines.append(f"```bash\n{step['command']}\n```")
            if step.get("duration"):
                lines.append(f"*Duration: {step['duration']}*")
            if step.get("notes"):
                lines.append(f"> {step['notes']}")
            lines.append("")

        lines.extend(["## Cutover Steps", ""])
        for step in result.get("cutover_steps", []):
            lines.append(f"- [ ] {step}")

        lines.extend(["", "## Validation", ""])
        for step in result.get("validation_steps", []):
            lines.append(f"- [ ] {step}")

        lines.extend(["", "## Rollback Plan", ""])
        for step in result.get("rollback_plan", []):
            lines.append(f"1. {step}")

        lines.extend(["", "## Gaps & Risks", ""])
        for risk in result.get("gaps_and_risks", []):
            lines.append(f"- {risk}")

        lines.extend(["", "## Architecture Notes", ""])
        for note in result.get("architecture_notes", []):
            lines.append(f"- {note}")

        return "\n".join(lines)


def run(
    input_content: str,
    progress_callback,
    anthropic_client,
    max_iterations: int = 3,
) -> dict:
    """Entry point for the data migration planning skill."""
    orch = DataMigrationOrchestrator()
    return orch.run(input_content, progress_callback, anthropic_client, max_iterations)
