#!/usr/bin/env python3
"""
EC2 -> OCI Compute Terraform Orchestrator -- refactored to use BaseTranslationOrchestrator.

Translates AWS EC2 instances (with EBS volumes and Auto Scaling Groups) into
OCI Compute Terraform HCL (oci_core_instance, oci_core_volume,
oci_autoscaling_auto_scaling_configuration).

Runs the enhancement -> review -> fix agent loop and returns results as dicts
instead of writing files. Accepts an Anthropic client from the caller.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
SKILLS_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(SKILLS_ROOT / "shared"))

from base_orchestrator import BaseTranslationOrchestrator  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# EC2 Translation Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class EC2TranslationOrchestrator(BaseTranslationOrchestrator):
    """EC2 -> OCI Compute Terraform translation orchestrator."""

    # ── Class constants ─────────────────────────────────────────────────────
    SKILL_TYPE = "ec2_translation"
    PROJECT_TYPE = "ec2"
    REPORT_FILENAME = "ec2-translation.md"

    # ── System prompts ──────────────────────────────────────────────────────

    ENHANCEMENT_SYSTEM = """\
You are an expert AWS EC2 to OCI Compute Terraform translator.
Convert the provided EC2 instance inventory (instances, EBS volumes, Auto Scaling Groups)
to production-ready OCI Terraform HCL.

Resource mapping rules:
- EC2 instance → oci_core_instance
- EBS root volume → part of oci_core_instance.source_details (boot volume, size_in_gbs)
- EBS data volume → oci_core_volume + oci_core_volume_attachment
- Auto Scaling Group → oci_autoscaling_auto_scaling_configuration + oci_core_instance_configuration
- IAM Instance Profile → reference OCI dynamic group + instance principal (comment only, not Terraform resource)

Instance type mapping guide:
  t3.micro/small  → VM.Standard.E4.Flex (1/2 OCPU, 1/4 GB)
  t3.medium       → VM.Standard.E4.Flex (1 OCPU, 4 GB)
  t3.large        → VM.Standard.E4.Flex (1 OCPU, 8 GB)
  t3.xlarge       → VM.Standard.E4.Flex (2 OCPU, 16 GB)
  t3.2xlarge      → VM.Standard.E4.Flex (4 OCPU, 32 GB)
  m5.large        → VM.Standard.E4.Flex (1 OCPU, 8 GB)
  m5.xlarge       → VM.Standard.E4.Flex (2 OCPU, 16 GB)
  m5.2xlarge      → VM.Standard.E4.Flex (4 OCPU, 32 GB)
  m5.4xlarge      → VM.Standard.E4.Flex (8 OCPU, 64 GB)
  c5.large        → VM.Standard.E4.Flex (1 OCPU, 4 GB)
  c5.xlarge       → VM.Standard.E4.Flex (2 OCPU, 8 GB)
  r5.large        → VM.Standard.E4.Flex (1 OCPU, 16 GB)  [memory-optimized]
  r5.xlarge       → VM.Standard.E4.Flex (2 OCPU, 32 GB)
  For unmapped types: use VM.Standard.E4.Flex with nearest OCPU/memory ratio.

Volume type mapping:
  gp3/gp2 → Balanced performance (vpusPerGB = 10)
  io1/io2  → Higher performance (vpusPerGB = 20)
  st1/sc1  → Lower cost (vpusPerGB = 0)

Additional rules:
- Use only valid OCI Terraform provider resources (hashicorp/oci)
- Never use AWS resource types in the output
- Use variables for all compartment_id, subnet_id, nsg_ids, image_id, ssh_public_key
- Add freeform_tags to all resources (copy from EC2 tags where present)
- SSH key pair: reference var.ssh_public_key
- NSG IDs: use var.nsg_ids for security group equivalent
- For ASG: oci_autoscaling_auto_scaling_configuration must reference an
  oci_core_instance_configuration that specifies the shape and config

Output ONLY a JSON object with this schema:
{
  "main_tf": "complete HCL for oci_core_instance, oci_core_volume, oci_core_volume_attachment, oci_autoscaling_auto_scaling_configuration, oci_core_instance_configuration",
  "variables_tf": "HCL content for variables.tf with compartment_id, subnet_id, nsg_ids, image_id, ssh_public_key",
  "outputs_tf": "HCL content for outputs.tf with instance_ids, private_ips",
  "tfvars_example": "terraform.tfvars.example content with placeholder values",
  "resource_count": 5,
  "resource_mappings": [
    {
      "aws_type": "EC2 i-0abc123",
      "aws_instance_type": "t3.large",
      "oci_type": "oci_core_instance.web_server_1",
      "oci_shape": "VM.Standard.E4.Flex",
      "oci_ocpu": 1,
      "oci_memory_gb": 8,
      "notes": ""
    }
  ],
  "gaps": [
    {"gap": "Description", "severity": "CRITICAL|HIGH|MEDIUM|LOW", "mitigation": "How to address"}
  ],
  "migration_prerequisites": [
    "Create OCI VCN and subnets first (networking phase)",
    "Upload or import SSH public key",
    "Find equivalent OCI image (Oracle Linux 8 recommended)"
  ],
  "architecture_notes": "Brief description of the OCI compute architecture"
}
"""

    REVIEW_SYSTEM = """\
You are an expert OCI Compute Terraform reviewer with deep knowledge of both AWS EC2
and OCI Terraform.
Review an AWS EC2 -> OCI Compute Terraform translation for correctness.

Checklist:
- Shape mapping is appropriate (OCPU/memory ratio matches original instance type)
- Boot volume size and type correctly mapped (gp3/gp2 → balanced, io1/io2 → higher performance)
- VCN/subnet references use variables (not hardcoded OCIDs)
- SSH key is referenced correctly via var.ssh_public_key
- ASG mapping: oci_autoscaling_auto_scaling_configuration has correct min/max/desired capacity
- instance_configuration references the correct instance shape and OCPU/memory
- NSG IDs referenced via var.nsg_ids for security group equivalent
- oci_core_volume_attachment uses correct attachment_type (iscsi or paravirtualized)
- Data volumes have correct vpusPerGB for volume type mapping
- freeform_tags applied to all resources
- outputs include instance_ids and private_ips

Severity rules (STRICT):
  CRITICAL -- Wrong OCI resource type, invalid HCL syntax, resource will fail terraform validate
  HIGH     -- Missing required fields, wrong property mapping, architectural mismatch
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
You are an OCI Compute Terraform expert. Fix specific issues in an EC2->OCI Terraform translation.
Target ONLY the issues listed. Do not change correct resources.

Output ONLY a JSON object with the same schema as the enhancement output, plus:
{
  "main_tf": "complete fixed HCL content for main.tf",
  "variables_tf": "HCL content for variables.tf",
  "outputs_tf": "HCL content for outputs.tf",
  "tfvars_example": "terraform.tfvars.example content",
  "resource_count": 5,
  "resource_mappings": [...],
  "gaps": [...],
  "migration_prerequisites": [...],
  "architecture_notes": "...",
  "fixes_applied": ["Fixed shape mapping for t3.large", "Added nsg_ids variable reference", ...]
}
"""

    # ── Cache control overrides (EC2 uses cache_control on both) ────────────

    def get_enhancement_system_blocks(self) -> list[dict]:
        blocks = [{"type": "text", "text": self.ENHANCEMENT_SYSTEM, "cache_control": {"type": "ephemeral"}}]
        prose = self._workflow_rules_block()
        if prose:
            blocks.append(prose)
        table = self._canonical_mapping_block()
        if table:
            blocks.append(table)
        return blocks

    def get_fix_system_blocks(self) -> list[dict]:
        blocks = [{"type": "text", "text": self.FIX_SYSTEM, "cache_control": {"type": "ephemeral"}}]
        prose = self._workflow_rules_block()
        if prose:
            blocks.append(prose)
        table = self._canonical_mapping_block()
        if table:
            blocks.append(table)
        return blocks

    # ── Gap analysis ────────────────────────────────────────────────────────

    def run_gap_analysis(self, input_data: dict) -> dict:
        """
        Run a lightweight deterministic gap analysis from the parsed EC2 inventory.
        Returns structured dict with resource metrics for ConfidenceCalculator.
        """
        try:
            instances = input_data.get("instances", [])
            asgs      = input_data.get("auto_scaling_groups", [])

            instance_count = len(instances)
            asg_count      = len(asgs)

            # Count data volumes (non-root) across all instances
            volume_count = 0
            for inst in instances:
                bdms = inst.get("block_device_mappings", [])
                # Root device is typically /dev/xvda or /dev/sda1; extras are data volumes
                data_volumes = [
                    b for b in bdms
                    if b.get("device_name", "") not in ("/dev/xvda", "/dev/sda1", "/dev/sda")
                ]
                volume_count += len(data_volumes)

            # Total OCI resources:
            # - 1 oci_core_instance per EC2 instance
            # - 1 oci_core_volume + 1 oci_core_volume_attachment per data volume
            # - 1 oci_autoscaling_auto_scaling_configuration + 1 oci_core_instance_configuration per ASG
            total_resources = (
                instance_count
                + volume_count * 2
                + asg_count * 2
            )
            # All EC2 resources have OCI equivalents; actual gaps found by reviewer
            mapped_resources = total_resources

        except Exception:
            instance_count   = 1
            volume_count     = 0
            asg_count        = 0
            total_resources  = 1
            mapped_resources = 0

        return {
            "total_resources":  total_resources,
            "mapped_resources": mapped_resources,
            "instance_count":   instance_count,
            "volume_count":     volume_count,
            "asg_count":        asg_count,
        }

    # ── Prompt builders ─────────────────────────────────────────────────────

    def build_enhancement_prompt(
        self, input_content: str, input_data: dict,
        current_translation: dict | None, issues: list,
    ) -> str:
        prev = json.dumps(current_translation, indent=2) if current_translation else "None -- this is the initial translation."
        issues_text = json.dumps(issues, indent=2) if issues else "None"
        input_json = json.dumps(input_data, indent=2)

        return (
            f"## EC2 Instance Inventory\n```json\n{input_json}\n```\n\n"
            f"## Current Translation\n```json\n{prev}\n```\n\n"
            f"## Issues to Fix\n```json\n{issues_text}\n```\n\n"
            "Produce the complete OCI Compute Terraform translation as a JSON object."
        )

    def build_review_prompt(
        self, input_content: str, input_data: dict, translation: dict,
    ) -> str:
        # Summarize translation for review (omit raw HCL to keep context manageable)
        review_summary = {
            "resource_count": translation.get("resource_count", 0),
            "resource_mappings": translation.get("resource_mappings", []),
            "gaps": translation.get("gaps", []),
            "migration_prerequisites": translation.get("migration_prerequisites", []),
            "architecture_notes": translation.get("architecture_notes", ""),
            "main_tf_excerpt": translation.get("main_tf", "")[:4000],
        }

        # Summarize input for context (truncated)
        input_summary = {
            "instance_count": len(input_data.get("instances", [])),
            "asg_count": len(input_data.get("auto_scaling_groups", [])),
            "instances": [
                {
                    "instance_id": inst.get("instance_id", ""),
                    "instance_type": inst.get("instance_type", ""),
                    "tags": inst.get("tags", {}),
                }
                for inst in input_data.get("instances", [])[:5]
            ],
            "auto_scaling_groups": [
                {
                    "asg_name": asg.get("asg_name", ""),
                    "min_size": asg.get("min_size"),
                    "max_size": asg.get("max_size"),
                    "desired_capacity": asg.get("desired_capacity"),
                }
                for asg in input_data.get("auto_scaling_groups", [])[:5]
            ],
        }

        return (
            f"## EC2 Instance Inventory Summary\n```json\n{json.dumps(input_summary, indent=2)}\n```\n\n"
            f"## OCI Terraform Translation to Review\n```json\n{json.dumps(review_summary, indent=2)}\n```\n\n"
            "Review this translation according to your checklist and return a JSON object."
        )

    def build_fix_prompt(
        self, input_content: str, input_data: dict,
        translation: dict, issues: list,
    ) -> str:
        input_json = json.dumps(input_data, indent=2)

        return (
            f"## EC2 Instance Inventory\n```json\n{input_json}\n```\n\n"
            f"## Current OCI Terraform Translation\n```json\n{json.dumps(translation, indent=2)}\n```\n\n"
            f"## Issues to Fix\n```json\n{json.dumps(issues, indent=2)}\n```\n\n"
            "Fix ONLY the listed issues. Return the complete updated translation as a JSON object."
        )

    # ── Log formatters ──────────────────────────────────────────────────────

    def format_gap_analysis_log(
        self, input_data: dict, gap_analysis: dict,
    ) -> tuple[str, str]:
        input_summary = "EC2 instance inventory via API"
        output_summary = (
            f"Gap analysis: {gap_analysis['instance_count']} instances, "
            f"{gap_analysis['volume_count']} data volumes, "
            f"{gap_analysis['asg_count']} ASGs detected "
            f"({gap_analysis['total_resources']} total OCI resources)"
        )
        return input_summary, output_summary

    def format_enhancement_log(
        self, current_issues: list, translation: dict,
    ) -> tuple[str, str]:
        input_summary = f"Translate EC2 inventory, fix {len(current_issues)} issues"
        output_summary = f"Generated {translation.get('resource_count', 0)} OCI resources"
        return input_summary, output_summary

    # ── Report generation ───────────────────────────────────────────────────

    def generate_report_md(
        self, translation: dict, gap_analysis: dict, last_review: dict,
        final_decision: Any, final_confidence: float, iteration_count: int,
    ) -> str:
        """Generate a rich human-readable EC2->OCI Compute migration guide."""
        resource_mappings = translation.get("resource_mappings", [])
        gaps              = translation.get("gaps", [])
        prerequisites     = translation.get("migration_prerequisites", [])
        arch_notes        = translation.get("architecture_notes", "")
        resource_count    = translation.get("resource_count", len(resource_mappings))

        review_issues  = last_review.get("issues", [])
        review_summary = last_review.get("review_summary", "")

        instance_count  = gap_analysis.get("instance_count", 0)
        volume_count    = gap_analysis.get("volume_count", 0)
        asg_count       = gap_analysis.get("asg_count", 0)
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

        complexity = "HIGH" if total_resources >= 15 else "MEDIUM" if total_resources >= 5 else "LOW"

        lines = []

        # Header
        lines += [
            "# EC2 to OCI Compute Translation",
            "",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"**Status:** [{status_icon}] {decision_str} "
            f"({iteration_count} iteration{'s' if iteration_count != 1 else ''}, {issues_summary})",
            "",
            "---",
            "",
        ]

        # Executive Summary
        lines += ["## Executive Summary", ""]
        if review_summary:
            lines.append(review_summary)
            lines.append("")

        lines += [
            f"**Translation Complexity:** {complexity}",
            f"**EC2 Instances:** {instance_count}",
            f"**Data Volumes:** {volume_count}",
            f"**Auto Scaling Groups:** {asg_count}",
            f"**OCI Terraform Resources:** {resource_count}",
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
        med_issues  = [i for i in review_issues if i.get("severity") in ("MEDIUM", "LOW")]
        if high_issues or med_issues:
            lines.append("**Migration Impact:**")
            for i in high_issues:
                lines.append(f"- **High:** {i.get('description', '')}")
            for i in med_issues[:5]:
                sev = i.get("severity", "Low").title()
                lines.append(f"- **{sev}:** {i.get('description', '')}")
            lines.append("")

        lines += ["---", ""]

        # Resource Mappings
        if resource_mappings:
            lines += [
                "## Resource Mappings",
                "",
                "| AWS Resource | AWS Type | OCI Resource | OCI Shape | OCPU | Memory (GB) | Notes |",
                "|--------------|----------|--------------|-----------|------|-------------|-------|",
            ]
            for rm in resource_mappings:
                aws_res   = (rm.get("aws_type", "") or "").replace("|", "\\|")
                aws_type  = (rm.get("aws_instance_type", "") or "").replace("|", "\\|")
                oci_res   = (rm.get("oci_type", "") or "").replace("|", "\\|")
                oci_shape = (rm.get("oci_shape", "") or "").replace("|", "\\|")
                oci_ocpu  = rm.get("oci_ocpu", "")
                oci_mem   = rm.get("oci_memory_gb", "")
                note      = (rm.get("notes", "") or "").replace("|", "\\|")[:80]
                lines.append(f"| {aws_res} | `{aws_type}` | `{oci_res}` | `{oci_shape}` | {oci_ocpu} | {oci_mem} | {note} |")
            lines += ["", "---", ""]

        # Prerequisites
        if prerequisites:
            lines += ["## Prerequisites", ""]
            for i, prereq in enumerate(prerequisites, 1):
                lines.append(f"### {i}. {prereq}")
                lines.append("")
            lines += ["---", ""]

        # Deployment Checklist
        lines += ["## Deployment Checklist", ""]
        lines += [
            "- [ ] Complete networking phase: create OCI VCN, subnets, NSGs",
            "- [ ] Upload SSH public key to OCI",
            "- [ ] Identify equivalent OCI image OCID (Oracle Linux 8 recommended)",
            "- [ ] Run `terraform init` in the output directory",
            "- [ ] Copy `terraform.tfvars.example` to `terraform.tfvars` and fill in values",
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
            "- [ ] Validate all instances and volumes are created successfully",
            "",
            "---",
            "",
        ]

        # Gaps Summary
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

        # Review Issues
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

        # Validation Summary
        lines += ["## Validation Summary", ""]
        lines.append(f"**Final Decision:** [{status_icon}] {decision_str}")
        lines.append(f"**Confidence Score:** {final_confidence:.1%}")
        lines.append(f"**Iterations:** {iteration_count}")
        lines.append("")
        if final_confidence >= 0.85:
            lines.append(
                "Translation is approved. All CRITICAL and HIGH issues resolved. "
                "Ready for `terraform apply` after variable substitution."
            )
        elif final_confidence >= 0.65:
            lines.append(
                "Translation is approved with notes. "
                "Review documented issues above before running `terraform apply`."
            )
        else:
            lines.append(
                "Translation needs additional review. "
                "Address all CRITICAL and HIGH issues before deployment."
            )
        lines.append("")

        return "\n".join(lines)


# ── Module-level exports (backward compatibility) ─────────────────────────────

_orchestrator = EC2TranslationOrchestrator()
def run(input_content, progress_callback, anthropic_client, max_iterations=3):
    return _orchestrator.run(input_content, progress_callback, anthropic_client, max_iterations)
