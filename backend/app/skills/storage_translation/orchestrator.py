#!/usr/bin/env python3
"""
AWS EBS Volume -> OCI Block Volume Terraform Orchestrator.

Translates AWS EBS volumes (gp2/gp3/io1/io2/st1/sc1) into OCI Block Volume
Terraform HCL (oci_core_volume + oci_core_volume_attachment).
"""

import json
from datetime import datetime, timezone
from typing import Any

from app.skills.shared.base_orchestrator import BaseTranslationOrchestrator


# ── System prompts ────────────────────────────────────────────────────────────

ENHANCEMENT_SYSTEM = """\
You are an expert AWS EBS to OCI Block Volume Terraform translator.
Convert the provided EBS volume inventory to production-ready OCI Terraform HCL.

Resource mapping rules:
- EBS volume → oci_core_volume
- EBS volume attachment → oci_core_volume_attachment
- Unattached EBS volume → oci_core_volume only (no attachment)

Volume type mapping:
  gp3 / gp2        → vpus_per_gb = 10  (Balanced Performance — default for most workloads)
  io1 / io2        → vpus_per_gb = 20  (Higher Performance — for latency-sensitive workloads)
  st1 / sc1        → vpus_per_gb = 0   (Lower Cost — for throughput/cold storage)
  (unknown/default) → vpus_per_gb = 10

Attachment type:
  Use attachment_type = "paravirtualized" for standard OCI instances (VM.Standard shapes).
  Use attachment_type = "iscsi" only when explicitly required.

Additional rules:
- Use only valid OCI Terraform provider resources (hashicorp/oci)
- Never use AWS resource types in the output
- Use variables for compartment_id, availability_domain, and instance_id references
- size_in_gbs must come from the source volume's size_gb field
- Set is_auto_tune_enabled = true for gp3/io1/io2 volumes
- Add freeform_tags to all oci_core_volume resources
- For encrypted volumes: note that OCI encrypts all block volumes by default (no extra config needed); add a comment
- Output ONLY a JSON object with this schema:
{
  "main_tf": "complete HCL for oci_core_volume and oci_core_volume_attachment resources",
  "variables_tf": "HCL for variables.tf with compartment_id, availability_domain, instance_ids map",
  "outputs_tf": "HCL for outputs.tf with volume_ids, attachment_ids",
  "tfvars_example": "terraform.tfvars.example content with placeholder values",
  "resource_count": 2,
  "resource_mappings": [
    {
      "aws_type": "EBS vol-0abc123 (gp3, 100 GiB)",
      "oci_type": "oci_core_volume.data_vol_1",
      "vpus_per_gb": 10,
      "notes": "Attached to instance i-0abc as /dev/xvdb"
    }
  ],
  "gaps": [
    {"gap": "Description", "severity": "CRITICAL|HIGH|MEDIUM|LOW", "mitigation": "How to address"}
  ],
  "migration_prerequisites": [
    "Create OCI compute instances first (compute phase)",
    "Identify OCI availability domain for volume placement",
    "Plan data migration: snapshot EBS → import to OCI Block Volume, or use rsync/DMS"
  ],
  "architecture_notes": "Brief description of the OCI storage architecture"
}
"""

REVIEW_SYSTEM = """\
You are an OCI Block Volume Terraform expert reviewing an AWS EBS -> OCI Block Volume translation.

Review checklist:
- Volume size (size_in_gbs) correctly maps from source size_gb
- vpus_per_gb matches the source volume type (gp3/gp2→10, io1/io2→20, st1/sc1→0)
- oci_core_volume_attachment references the correct oci_core_volume and instance variables
- attachment_type is appropriate (paravirtualized for standard VM shapes)
- is_auto_tune_enabled set for performance-tier volumes
- compartment_id and availability_domain use variables (not hardcoded OCIDs)
- freeform_tags applied to all oci_core_volume resources
- Unattached volumes have no attachment resource
- No AWS resource types in the output

Severity rules (STRICT):
  CRITICAL -- Wrong OCI resource type, invalid HCL syntax, resource will fail terraform validate
  HIGH     -- Missing required fields, wrong volume type mapping, missing attachment for attached volumes
  MEDIUM   -- Suboptimal vpus_per_gb, missing auto-tune, non-critical best practice
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
      "category": "resource_mapping|property_translation|completeness|syntax|security|storage",
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
You are an OCI Block Volume Terraform expert. Fix specific issues in an EBS->OCI translation.
Target ONLY the issues listed. Do not change correct resources.

Output ONLY a JSON object with the same schema as the enhancement output, plus:
{
  "main_tf": "complete fixed HCL content",
  "variables_tf": "HCL content for variables.tf",
  "outputs_tf": "HCL content for outputs.tf",
  "tfvars_example": "terraform.tfvars.example content",
  "resource_count": 2,
  "resource_mappings": [...],
  "gaps": [...],
  "migration_prerequisites": [...],
  "architecture_notes": "...",
  "fixes_applied": ["Fixed vpus_per_gb for gp3 volume", "Added attachment for vol-0abc123", ...]
}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# StorageTranslationOrchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class StorageTranslationOrchestrator(BaseTranslationOrchestrator):
    """AWS EBS Volume -> OCI Block Volume Terraform translation orchestrator."""

    SKILL_TYPE      = "storage_translation"
    PROJECT_TYPE    = "storage"
    REPORT_FILENAME = "storage-translation.md"

    ENHANCEMENT_SYSTEM = ENHANCEMENT_SYSTEM
    REVIEW_SYSTEM      = REVIEW_SYSTEM
    FIX_SYSTEM         = FIX_SYSTEM

    # ── Gap analysis ────────────────────────────────────────────────────────

    def run_gap_analysis(self, input_data: dict) -> dict:
        try:
            volumes = input_data.get("volumes", [])
            volume_count = len(volumes)
            if volume_count == 0:
                volume_count = 1

            attached_count = sum(1 for v in volumes if v.get("attachments"))
            unattached_count = volume_count - attached_count

            # Each attached volume → 1 oci_core_volume + 1 oci_core_volume_attachment
            # Each unattached volume → 1 oci_core_volume
            total_resources = volume_count + attached_count
            mapped_resources = total_resources

        except Exception:
            volume_count     = 1
            attached_count   = 0
            unattached_count = 0
            total_resources  = 1
            mapped_resources = 0

        return {
            "total_resources":   total_resources,
            "mapped_resources":  mapped_resources,
            "volume_count":      volume_count,
            "attached_count":    attached_count,
            "unattached_count":  unattached_count,
        }

    # ── Prompt builders ─────────────────────────────────────────────────────

    def build_enhancement_prompt(
        self, input_content: str, input_data: dict,
        current_translation: dict | None, issues: list,
    ) -> str:
        prev = json.dumps(current_translation, indent=2) if current_translation else "None -- this is the initial translation."
        issues_text = json.dumps(issues, indent=2) if issues else "None"

        return (
            f"## EBS Volume Inventory\n```json\n{json.dumps(input_data, indent=2)}\n```\n\n"
            f"## Current Translation\n```json\n{prev}\n```\n\n"
            f"## Issues to Fix\n```json\n{issues_text}\n```\n\n"
            "Produce the complete OCI Block Volume Terraform translation as a JSON object."
        )

    def build_review_prompt(
        self, input_content: str, input_data: dict, translation: dict,
    ) -> str:
        review_summary = {
            "resource_count":       translation.get("resource_count", 0),
            "resource_mappings":    translation.get("resource_mappings", []),
            "gaps":                 translation.get("gaps", []),
            "migration_prerequisites": translation.get("migration_prerequisites", []),
            "architecture_notes":   translation.get("architecture_notes", ""),
            "main_tf_excerpt":      translation.get("main_tf", "")[:4000],
        }

        return (
            f"## EBS Volume Inventory\n```json\n{json.dumps(input_data, indent=2)[:3000]}\n```\n\n"
            f"## OCI Terraform Translation to Review\n```json\n{json.dumps(review_summary, indent=2)}\n```\n\n"
            "Review this translation according to your checklist and return a JSON object."
        )

    def build_fix_prompt(
        self, input_content: str, input_data: dict,
        translation: dict, issues: list,
    ) -> str:
        return (
            f"## EBS Volume Inventory\n```json\n{json.dumps(input_data, indent=2)}\n```\n\n"
            f"## Current OCI Terraform Translation\n```json\n{json.dumps(translation, indent=2)}\n```\n\n"
            f"## Issues to Fix\n```json\n{json.dumps(issues, indent=2)}\n```\n\n"
            "Fix ONLY the listed issues. Return the complete updated translation as a JSON object."
        )

    # ── Report generation ───────────────────────────────────────────────────

    def generate_report_md(
        self, translation: dict, gap_analysis: dict, last_review: dict,
        final_decision: Any, final_confidence: float, iteration_count: int,
    ) -> str:
        resource_mappings = translation.get("resource_mappings", [])
        gaps              = translation.get("gaps", [])
        prerequisites     = translation.get("migration_prerequisites", [])
        arch_notes        = translation.get("architecture_notes", "")
        resource_count    = translation.get("resource_count", len(resource_mappings))

        review_issues  = last_review.get("issues", [])
        review_summary = last_review.get("review_summary", "")

        volume_count    = gap_analysis.get("volume_count", 0)
        attached_count  = gap_analysis.get("attached_count", 0)
        total_resources = gap_analysis.get("total_resources", resource_count)

        decision_str = final_decision.value if hasattr(final_decision, "value") else str(final_decision)
        approved     = decision_str in ("APPROVED", "APPROVED_WITH_NOTES")
        status_icon  = "OK" if approved else "WARN"

        critical_cnt = sum(1 for i in review_issues if i.get("severity") in ("CRITICAL", "HIGH"))
        med_low_cnt  = sum(1 for i in review_issues if i.get("severity") in ("MEDIUM", "LOW"))
        if critical_cnt:
            issues_summary = f"{critical_cnt} critical/high issues require attention"
        elif med_low_cnt:
            issues_summary = f"{med_low_cnt} medium/low issues documented"
        else:
            issues_summary = "no issues"

        high_issues = [i for i in review_issues if i.get("severity") in ("CRITICAL", "HIGH")]

        lines = [
            "# EBS to OCI Block Volume Translation",
            "",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"**Status:** [{status_icon}] {decision_str} ({iteration_count} iteration{'s' if iteration_count != 1 else ''}, {issues_summary})",
            "",
            "---",
            "",
            "## Executive Summary",
            "",
        ]

        if review_summary:
            lines += [review_summary, ""]

        lines += [
            f"**EBS Volumes:** {volume_count}",
            f"**Attached Volumes:** {attached_count}",
            f"**OCI Terraform Resources:** {resource_count}",
            "",
        ]

        if arch_notes:
            lines += [f"**Architecture:** {arch_notes}", ""]

        lines += [
            "## OCI Block Volume Notes",
            "",
            "Key differences from AWS EBS:",
            "",
            "- **OCI encrypts all block volumes by default** — no extra configuration needed (unlike AWS where you opt in).",
            "- **Performance Tiers:** OCI uses `vpus_per_gb` (0=Lower Cost, 10=Balanced, 20=Higher Performance) instead of IOPS provisioning.",
            "- **Availability Domain scoped:** OCI Block Volumes are AD-scoped; ensure volume and instance are in the same AD.",
            "- **Data Migration:** Use OCI Block Volume Backup → restore, or rsync/DMS to move data from EBS to OCI.",
            "- **Attachment types:** `paravirtualized` is recommended for VM.Standard shapes; `iscsi` for bare metal or high-IOPS.",
            "",
            "---",
            "",
        ]

        if resource_mappings:
            lines += [
                "## Resource Mappings",
                "",
                "| AWS Resource | OCI Resource | vpus_per_gb | Notes |",
                "|--------------|--------------|-------------|-------|",
            ]
            for rm in resource_mappings:
                aws_res  = (rm.get("aws_type", "") or "").replace("|", "\\|")
                oci_res  = (rm.get("oci_type", "") or "").replace("|", "\\|")
                vpus     = rm.get("vpus_per_gb", "")
                note     = (rm.get("notes", "") or "").replace("|", "\\|")[:80]
                lines.append(f"| `{aws_res}` | `{oci_res}` | {vpus} | {note} |")
            lines += ["", "---", ""]

        if prerequisites:
            lines += ["## Prerequisites", ""]
            for i, prereq in enumerate(prerequisites, 1):
                lines.append(f"### {i}. {prereq}")
                lines.append("")
            lines += ["---", ""]

        lines += [
            "## Deployment Checklist",
            "",
            "- [ ] Complete compute phase: OCI instances must exist before attaching volumes",
            "- [ ] Identify target OCI availability domain for each volume",
            "- [ ] Plan data migration strategy (backup/restore or live sync)",
            "- [ ] Run `terraform init` in the output directory",
            "- [ ] Copy `terraform.tfvars.example` to `terraform.tfvars` and fill in instance_ids and availability_domain",
            "- [ ] Run `terraform validate` and `terraform plan`",
            "- [ ] Run `terraform apply` to create volumes",
            "- [ ] Migrate data from EBS to the new OCI block volumes",
            "",
            "---",
            "",
        ]

        if gaps:
            lines += [
                "## Migration Gaps",
                "",
                "| Severity | Gap | Mitigation |",
                "|----------|-----|------------|",
            ]
            for gap in gaps:
                sev  = gap.get("severity", "MEDIUM")
                desc = (gap.get("gap", "") or "").replace("|", "\\|")
                mit  = (gap.get("mitigation", "") or "").replace("|", "\\|")
                lines.append(f"| {sev} | {desc} | {mit} |")
            lines += ["", "---", ""]

        if review_issues:
            lines += [
                "## Review Issues",
                "",
                "| Severity | Category | Resource | Description | Recommendation |",
                "|----------|----------|----------|-------------|----------------|",
            ]
            for issue in review_issues:
                sev  = issue.get("severity", "LOW")
                cat  = (issue.get("category", "") or "").replace("|", "\\|")
                res  = (issue.get("resource", "") or "").replace("|", "\\|")
                desc = (issue.get("description", "") or "").replace("|", "\\|")[:100]
                rec  = (issue.get("recommendation", "") or "").replace("|", "\\|")[:100]
                lines.append(f"| {sev} | {cat} | {res} | {desc} | {rec} |")
            lines += ["", "---", ""]

        lines += [
            "## Validation Summary",
            "",
            f"**Final Decision:** [{status_icon}] {decision_str}",
            f"**Confidence Score:** {final_confidence:.1%}",
            f"**Iterations:** {iteration_count}",
            "",
        ]
        if final_confidence >= 0.85:
            lines.append("Translation approved. Ready for `terraform apply` after variable substitution and data migration planning.")
        elif final_confidence >= 0.65:
            lines.append("Translation approved with notes. Review documented issues before applying.")
        else:
            lines.append("Translation needs additional review. Address CRITICAL and HIGH issues before deployment.")
        lines.append("")

        return "\n".join(lines)

    # ── Logger formatting ───────────────────────────────────────────────────

    def get_logger_source(self, input_data: dict) -> str:
        volumes = input_data.get("volumes", [])
        return f"{len(volumes)}-volumes"

    def format_gap_analysis_log(
        self, input_data: dict, gap_analysis: dict,
    ) -> tuple[str, str]:
        input_summary = "EBS volume inventory via API"
        output_summary = (
            f"Gap analysis: {gap_analysis['volume_count']} volumes "
            f"({gap_analysis['attached_count']} attached) → "
            f"{gap_analysis['total_resources']} OCI resources"
        )
        return input_summary, output_summary

    def format_enhancement_log(
        self, current_issues: list, translation: dict,
    ) -> tuple[str, str]:
        input_summary = f"Translate EBS volumes, fix {len(current_issues)} issues"
        output_summary = f"Generated {translation.get('resource_count', 0)} OCI resources"
        return input_summary, output_summary


# ── Module-level exports ──────────────────────────────────────────────────────

_orchestrator = StorageTranslationOrchestrator()
ENHANCEMENT_MODEL = _orchestrator.ENHANCEMENT_MODEL
REVIEW_MODEL      = _orchestrator.REVIEW_MODEL
FIX_MODEL         = _orchestrator.FIX_MODEL


def run(input_content, progress_callback, anthropic_client, max_iterations=3):
    return _orchestrator.run(input_content, progress_callback, anthropic_client, max_iterations)
