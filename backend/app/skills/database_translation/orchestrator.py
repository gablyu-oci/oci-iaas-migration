#!/usr/bin/env python3
"""
AWS RDS -> OCI Database Service Terraform Orchestrator -- refactored to use
BaseTranslationOrchestrator for the Enhancement->Review->Fix loop.
"""

import json
from datetime import datetime, timezone
from typing import Any

from app.skills.shared.base_orchestrator import BaseTranslationOrchestrator


# ── System prompts ────────────────────────────────────────────────────────────

ENHANCEMENT_SYSTEM = """\
You are an expert AWS RDS to OCI Database Service Terraform translator.
Convert the provided AWS RDS instance definitions to production-ready OCI Terraform HCL.

Engine mapping rules:
- postgres → oci_database_db_system with db_workload = "OLTP"
- mysql → oci_mysql_mysql_db_system
- oracle-se2 / oracle-ee → oci_database_db_system
- sqlserver → NOTE as a gap: OCI has no managed SQL Server; recommend self-hosted on OCI Compute
- aurora-postgresql → oci_database_autonomous_database (ATP, db_workload = "OLTP")
- aurora-mysql → oci_mysql_mysql_db_system

DB instance class to OCI shape mapping:
- db.t3.medium  → 1 OCPU, 16 GB  (VM.Standard.E4.Flex)
- db.r6g.large  → 1 OCPU, 32 GB
- db.r6g.xlarge → 2 OCPU, 64 GB
- db.r6g.2xlarge → 4 OCPU, 128 GB
- db.r5.large   → 1 OCPU, 32 GB
- db.r5.xlarge  → 2 OCPU, 64 GB

Multi-AZ handling:
- multi_az = true → set node_count = 2 on oci_database_db_system
- data_storage_size_in_gb must be set from allocated_storage

Security:
- Admin password MUST use a sensitive variable (never hardcoded)
- SSH public key MUST use a variable for oci_database_db_system

Additional rules:
- Use variables for all OCIDs (compartment_id, subnet_id)
- Add freeform_tags to all resources using the source AWS tags
- For oci_mysql_mysql_db_system use shape_name appropriate to the instance class
- For oci_database_db_system set database_edition appropriately (ENTERPRISE_EDITION for oracle-ee, STANDARD_EDITION_TWO for oracle-se2, ENTERPRISE_EDITION for postgres)

Output ONLY a JSON object with this schema:
{
  "main_tf": "complete HCL content for main.tf",
  "variables_tf": "HCL content for variables.tf (include compartment_id, subnet_id, db_admin_password as sensitive, ssh_public_key)",
  "outputs_tf": "HCL content for outputs.tf (include db_system_id, connection_string)",
  "tfvars_example": "terraform.tfvars.example content (password = <CHANGE_ME>)",
  "resource_count": 1,
  "resource_mappings": [
    {"aws_type": "RDS db.r6g.large postgres", "oci_type": "oci_database_db_system.prod_postgres", "notes": ""}
  ],
  "gaps": [
    {"gap": "Description", "severity": "CRITICAL|HIGH|MEDIUM|LOW", "mitigation": "How to address"}
  ],
  "migration_prerequisites": [
    "Plan database migration using OCI Database Migration Service or pg_dump/restore",
    "Create DB subnet in correct VCN",
    "Set admin password in tfvars"
  ],
  "architecture_notes": "Brief description of the OCI database architecture"
}
"""

REVIEW_SYSTEM = """\
You are an expert OCI Terraform reviewer with deep knowledge of both AWS RDS and OCI Database Service.
Review an AWS RDS -> OCI Database Service Terraform translation for correctness.

Check specifically:
- Engine mapping is correct (postgres→oci_database_db_system, mysql→oci_mysql_mysql_db_system, etc.)
- Admin password uses a sensitive variable (never hardcoded)
- Subnet references use variables (not hardcoded OCIDs)
- data_storage_size_in_gb is adequate (at least the allocated_storage value)
- Multi-AZ is handled with node_count = 2 on oci_database_db_system
- SSH public key variable present for oci_database_db_system
- sqlserver engines are noted as gaps (no managed OCI equivalent)
- aurora-postgresql mapped to oci_database_autonomous_database

Severity rules (STRICT):
  CRITICAL -- Wrong OCI resource type, invalid HCL syntax, resource will fail terraform validate
  HIGH     -- Missing required fields, wrong property mapping, hardcoded sensitive values, architectural mismatch
  MEDIUM   -- Scope issue, suboptimal configuration, missing best practices
  LOW      -- Style, naming, non-blocking improvements

Return ONLY a JSON object:
{
  "decision": "APPROVED|APPROVED_WITH_NOTES|NEEDS_FIXES|REJECTED",
  "confidence_override": null,
  "architectural_mismatch": false,
  "issues": [
    {
      "id": 1,
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "category": "resource_mapping|property_translation|completeness|syntax|security|networking|iam|monitoring",
      "resource": "oci_resource_type.resource_name",
      "description": "Specific problem description",
      "recommendation": "How to fix"
    }
  ],
  "approved_notes": "",
  "review_summary": "2-3 sentence overall assessment"
}
"""

FIX_SYSTEM = """\
You are an OCI Terraform expert. Fix specific issues in an AWS RDS->OCI Database Terraform translation.
Target ONLY the issues listed. Do not change correct resources.

Output ONLY a JSON object with the same schema as the enhancement output, plus:
{
  "main_tf": "complete fixed HCL content for main.tf",
  "variables_tf": "HCL content for variables.tf",
  "outputs_tf": "HCL content for outputs.tf",
  "tfvars_example": "terraform.tfvars.example content",
  "resource_count": 1,
  "resource_mappings": [...],
  "gaps": [...],
  "migration_prerequisites": [...],
  "architecture_notes": "...",
  "fixes_applied": ["Fixed resource type for DB", "Added sensitive variable for password", ...]
}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# DatabaseTranslationOrchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class DatabaseTranslationOrchestrator(BaseTranslationOrchestrator):
    """AWS RDS -> OCI Database Service translation orchestrator."""

    SKILL_TYPE      = "database_translation"
    PROJECT_TYPE    = "database"
    REPORT_FILENAME = "database-translation.md"

    ENHANCEMENT_SYSTEM = ENHANCEMENT_SYSTEM
    REVIEW_SYSTEM      = REVIEW_SYSTEM
    FIX_SYSTEM         = FIX_SYSTEM

    # ── Cache-control overrides (database uses ephemeral caching) ────────────

    def get_enhancement_system_blocks(self) -> list[dict]:
        blocks = [{
            "type": "text",
            "text": self.ENHANCEMENT_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }]
        prose = self._workflow_rules_block()
        if prose:
            blocks.append(prose)
        table = self._canonical_mapping_block()
        if table:
            blocks.append(table)
        return blocks

    def get_fix_system_blocks(self) -> list[dict]:
        blocks = [{
            "type": "text",
            "text": self.FIX_SYSTEM,
            "cache_control": {"type": "ephemeral"},
        }]
        prose = self._workflow_rules_block()
        if prose:
            blocks.append(prose)
        table = self._canonical_mapping_block()
        if table:
            blocks.append(table)
        return blocks

    # ── Gap analysis ─────────────────────────────────────────────────────────

    def run_gap_analysis(self, input_data: dict) -> dict:
        """
        Run a lightweight gap analysis directly from parsed RDS input.
        Returns structured dict with resource metrics for ConfidenceCalculator.
        """
        try:
            db_instances = input_data.get("db_instances", [])
            total_resources = len(db_instances)

            engines = sorted({inst.get("engine", "unknown") for inst in db_instances})

            # SQL Server instances are gaps (no managed OCI equivalent)
            gap_count = sum(1 for inst in db_instances if inst.get("engine", "").startswith("sqlserver"))
            mapped_resources = max(0, total_resources - gap_count)

        except Exception:
            total_resources = 1
            engines = []
            mapped_resources = 0

        return {
            "total_resources": total_resources,
            "mapped_resources": mapped_resources,
            "detected_engines": engines,
        }

    # ── Prompt builders ──────────────────────────────────────────────────────

    def build_enhancement_prompt(
        self, input_content: str, input_data: dict,
        current_translation: dict | None, issues: list,
    ) -> str:
        input_text = input_content
        prev = json.dumps(current_translation, indent=2) if current_translation else "None -- this is the initial translation."
        issues_text = json.dumps(issues, indent=2) if issues else "None"

        return (
            f"## AWS RDS Instance Definitions\n```json\n{input_text}\n```\n\n"
            f"## Current Translation\n```json\n{prev}\n```\n\n"
            f"## Issues to Fix\n```json\n{issues_text}\n```\n\n"
            "Produce the complete OCI Database Service Terraform translation as a JSON object."
        )

    def build_review_prompt(
        self, input_content: str, input_data: dict, translation: dict,
    ) -> str:
        input_text = input_content

        review_summary = {
            "resource_count": translation.get("resource_count", 0),
            "resource_mappings": translation.get("resource_mappings", []),
            "gaps": translation.get("gaps", []),
            "migration_prerequisites": translation.get("migration_prerequisites", []),
            "architecture_notes": translation.get("architecture_notes", ""),
            "main_tf_excerpt": translation.get("main_tf", "")[:4000],
        }

        return (
            f"## AWS RDS Instance Definitions\n```json\n{input_text[:3000]}\n```\n\n"
            f"## OCI Database Terraform Translation to Review\n```json\n{json.dumps(review_summary, indent=2)}\n```\n\n"
            "Review this translation according to your checklist and return a JSON object."
        )

    def build_fix_prompt(
        self, input_content: str, input_data: dict,
        translation: dict, issues: list,
    ) -> str:
        input_text = input_content

        return (
            f"## AWS RDS Instance Definitions\n```json\n{input_text}\n```\n\n"
            f"## Current OCI Database Terraform Translation\n```json\n{json.dumps(translation, indent=2)}\n```\n\n"
            f"## Issues to Fix\n```json\n{json.dumps(issues, indent=2)}\n```\n\n"
            "Fix ONLY the listed issues. Return the complete updated translation as a JSON object."
        )

    # ── Logging formatters ───────────────────────────────────────────────────

    def format_gap_analysis_log(
        self, input_data: dict, gap_analysis: dict,
    ) -> tuple[str, str]:
        input_summary = "AWS RDS instance definitions via API"
        output_summary = (
            f"Gap analysis: {gap_analysis['total_resources']} DB instances detected, "
            f"engines: {', '.join(gap_analysis['detected_engines']) or 'unknown'}"
        )
        return input_summary, output_summary

    def format_enhancement_log(
        self, current_issues: list, translation: dict,
    ) -> tuple[str, str]:
        input_summary = f"Translate RDS instances, fix {len(current_issues)} issues"
        output_summary = f"Generated {translation.get('resource_count', 0)} OCI database resources"
        return input_summary, output_summary

    # ── Report generator ─────────────────────────────────────────────────────

    def generate_report_md(
        self, translation: dict, gap_analysis: dict, last_review: dict,
        final_decision: Any, final_confidence: float, iteration_count: int,
    ) -> str:
        """Generate a rich human-readable RDS->OCI Database migration guide."""
        resource_mappings = translation.get("resource_mappings", [])
        gaps = translation.get("gaps", [])
        prerequisites = translation.get("migration_prerequisites", [])
        arch_notes = translation.get("architecture_notes", "")
        resource_count = translation.get("resource_count", len(resource_mappings))

        review_issues = last_review.get("issues", [])
        review_summary = last_review.get("review_summary", "")

        total_resources = gap_analysis.get("total_resources", resource_count)
        detected_engines = gap_analysis.get("detected_engines", [])

        decision_str = final_decision.value if hasattr(final_decision, "value") else str(final_decision)
        approved = decision_str in ("APPROVED", "APPROVED_WITH_NOTES")
        status_icon = "OK" if approved else "WARN"

        critical_cnt = sum(1 for i in review_issues if i.get("severity") in ("CRITICAL", "HIGH"))
        med_low_cnt = sum(1 for i in review_issues if i.get("severity") in ("MEDIUM", "LOW"))
        if critical_cnt:
            issues_summary = f"{critical_cnt} critical/high issues require attention"
        elif med_low_cnt:
            issues_summary = f"{med_low_cnt} medium/low issues documented"
        else:
            issues_summary = "no issues"

        complexity = "HIGH" if total_resources >= 5 else "MEDIUM" if total_resources >= 2 else "LOW"

        lines = []

        # ── Header ────────────────────────────────────────────────────────────
        lines += [
            "# OCI Database Service Terraform Translation",
            "",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"**Status:** [{status_icon}] {decision_str} ({iteration_count} iteration{'s' if iteration_count != 1 else ''}, {issues_summary})",
            "",
            "---",
            "",
        ]

        # ── Executive Summary ─────────────────────────────────────────────────
        lines += ["## Executive Summary", ""]
        if review_summary:
            lines.append(review_summary)
            lines.append("")

        lines += [
            f"**Translation Complexity:** {complexity}",
            f"**AWS RDS Instances:** {total_resources}",
            f"**OCI Terraform Resources:** {resource_count}",
            f"**Detected Engines:** {', '.join(detected_engines) if detected_engines else 'N/A'}",
            "",
        ]

        if arch_notes:
            lines.append(f"**Architecture:** {arch_notes}")
            lines.append("")

        high_gaps = [g for g in gaps if g.get("severity") in ("CRITICAL", "HIGH")]
        if high_gaps:
            lines.append("**Key Challenges:**")
            for gap in high_gaps:
                lines.append(f"- {gap.get('gap', '')}")
            lines.append("")

        high_issues = [i for i in review_issues if i.get("severity") in ("CRITICAL", "HIGH")]
        med_issues = [i for i in review_issues if i.get("severity") in ("MEDIUM", "LOW")]
        if high_issues or med_issues:
            lines.append("**Migration Impact:**")
            for i in high_issues:
                lines.append(f"- **High:** {i.get('description', '')}")
            for i in med_issues[:5]:
                sev = i.get("severity", "Low").title()
                lines.append(f"- **{sev}:** {i.get('description', '')}")
            lines.append("")

        lines += ["---", ""]

        # ── Resource Mappings ─────────────────────────────────────────────────
        if resource_mappings:
            lines += [
                "## Resource Mappings",
                "",
                "| AWS Type | OCI Resource | Notes |",
                "|----------|--------------|-------|",
            ]
            for rm in resource_mappings:
                aws_type = (rm.get("aws_type", "") or "").replace("|", "\\|")
                oci_type = (rm.get("oci_type", "") or "").replace("|", "\\|")
                note = (rm.get("notes", "") or "").replace("|", "\\|")[:80]
                lines.append(f"| {aws_type} | `{oci_type}` | {note} |")
            lines += ["", "---", ""]

        # ── Prerequisites ─────────────────────────────────────────────────────
        if prerequisites:
            lines += ["## Prerequisites", ""]
            for i, prereq in enumerate(prerequisites, 1):
                lines.append(f"### {i}. {prereq}")
                lines.append("")
            lines += ["---", ""]

        # ── Deployment Checklist ──────────────────────────────────────────────
        lines += ["## Deployment Checklist", ""]
        lines += [
            "- [ ] Run `terraform init` in the output directory",
            "- [ ] Copy `terraform.tfvars.example` to `terraform.tfvars` and fill in values",
            "- [ ] Set `db_admin_password` to a strong password (never commit to source control)",
            "- [ ] Run `terraform validate` to check HCL syntax",
            "- [ ] Run `terraform plan` and review the execution plan",
        ]
        for i, prereq in enumerate(prerequisites, 1):
            lines.append(f"- [ ] Complete prerequisite {i}: {prereq}")
        for gap in gaps:
            if gap.get("severity") in ("HIGH", "CRITICAL"):
                lines.append(f"- [ ] Address gap: {gap.get('gap', '')} -- {gap.get('mitigation', '')}")
        for issue in high_issues:
            lines.append(f"- [ ] Fix: {issue.get('description', '')}")
        lines += [
            "- [ ] Run `terraform apply` in a non-production environment first",
            "- [ ] Validate all database resources are created successfully",
            "- [ ] Perform database migration (pg_dump/restore or OCI Database Migration Service)",
            "",
            "---",
            "",
        ]

        # ── Gaps Summary ─────────────────────────────────────────────────────
        if gaps:
            lines += [
                "## Migration Gaps",
                "",
                "| Severity | Gap | Mitigation |",
                "|----------|-----|------------|",
            ]
            for gap in gaps:
                sev = gap.get("severity", "MEDIUM")
                desc = (gap.get("gap", "") or "").replace("|", "\\|")
                mit = (gap.get("mitigation", "") or "").replace("|", "\\|")
                lines.append(f"| {sev} | {desc} | {mit} |")
            lines += ["", "---", ""]

        # ── Review Issues ─────────────────────────────────────────────────────
        if review_issues:
            lines += [
                "## Review Issues",
                "",
                "| Severity | Category | Resource | Description | Recommendation |",
                "|----------|----------|----------|-------------|----------------|",
            ]
            for issue in review_issues:
                sev = issue.get("severity", "LOW")
                cat = (issue.get("category", "") or "").replace("|", "\\|")
                res = (issue.get("resource", "") or "").replace("|", "\\|")
                desc = (issue.get("description", "") or "").replace("|", "\\|")[:100]
                rec = (issue.get("recommendation", "") or "").replace("|", "\\|")[:100]
                lines.append(f"| {sev} | {cat} | {res} | {desc} | {rec} |")
            lines += ["", "---", ""]

        # ── Validation Summary ────────────────────────────────────────────────
        lines += ["## Validation Summary", ""]
        lines.append(f"**Final Decision:** [{status_icon}] {decision_str}")
        lines.append(f"**Confidence Score:** {final_confidence:.1%}")
        lines.append(f"**Iterations:** {iteration_count}")
        lines.append("")
        if final_confidence >= 0.85:
            lines.append("Translation is approved. All CRITICAL and HIGH issues resolved. Ready for `terraform apply` after variable substitution.")
        elif final_confidence >= 0.65:
            lines.append("Translation is approved with notes. Review documented issues above before running `terraform apply`.")
        else:
            lines.append("Translation needs additional review. Address all CRITICAL and HIGH issues before deployment.")
        lines.append("")

        return "\n".join(lines)


# ── Module-level exports (backward compatibility) ─────────────────────────────

_orchestrator = DatabaseTranslationOrchestrator()
def run(input_content, progress_callback, anthropic_client, max_iterations=3):
    return _orchestrator.run(input_content, progress_callback, anthropic_client, max_iterations)
