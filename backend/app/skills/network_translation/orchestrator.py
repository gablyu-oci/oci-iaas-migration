#!/usr/bin/env python3
"""
AWS VPC/Networking -> OCI VCN Terraform Orchestrator -- refactored to use
BaseTranslationOrchestrator.

Translates AWS VPC networking resources (VPC, subnets, security groups,
route tables, internet gateways, NAT gateways) into OCI Terraform HCL
(VCN, subnets, NSGs, security lists, route tables, DRGs).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

# ── Path setup ────────────────────────────────────────────────────────────────
SKILLS_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(SKILLS_ROOT / "shared"))

from base_orchestrator import BaseTranslationOrchestrator  # noqa: E402


# ── System prompts ────────────────────────────────────────────────────────────

_ENHANCEMENT_SYSTEM = """\
You are an expert AWS VPC to OCI VCN Terraform translator.
Convert the provided AWS VPC/networking resource description to production-ready OCI Terraform HCL.

Resource mappings:
- VPC -> oci_core_vcn
- Subnets -> oci_core_subnet (public subnets get route to internet gateway; private to NAT gateway)
- Security Groups -> oci_core_network_security_group + oci_core_network_security_group_security_rule
- Internet Gateway -> route in oci_core_route_table pointing to oci_core_internet_gateway
- NAT Gateway -> oci_core_nat_gateway + route in private route table
- Route Tables -> oci_core_route_table + oci_core_route_table_attachment
- Network Interface (ENI) -> oci_core_vnic_attachment (secondary VNICs; primary VNIC is auto-created with the instance)

Rules:
- Use only valid OCI Terraform provider resources (hashicorp/oci)
- Never use AWS resource types in the output
- Use variables for all OCIDs, region, and environment-specific values
- Add freeform_tags to all resources, carrying over AWS tags where applicable
- OCI subnets are regional (not per-AZ); map availability_zone to prohibit_public_ip_on_vnic instead
- OCI VCN CIDR must be /16 to /30; validate the input CIDR fits this range
- OCI NAT Gateway is a standalone regional resource (not per-AZ like AWS)
- Prefer NSGs (oci_core_network_security_group_security_rule) over security lists for flexibility
- Protocol numbers: TCP=6, UDP=17, ICMP=1, ALL=-1 (map AWS protocol "-1" to "all" in OCI stateless=false rules)
- For ENIs (network_interfaces): the primary ENI (device_index=0) becomes the instance's primary VNIC (auto-created with the instance, no Terraform resource needed); secondary ENIs (device_index>0) become oci_core_vnic_attachment resources
- Map AWS ingress/egress rules to OCI NSG security rules with correct direction (INGRESS/EGRESS)
- For security group rules without port range (protocol=-1), use source_type/destination_type CIDR_BLOCK and omit tcp_options/udp_options
- Output ONLY a JSON object with this schema:
{
  "main_tf": "complete HCL for VCN, subnets, NSGs, route tables",
  "variables_tf": "variables for compartment_id, vcn_display_name, etc.",
  "outputs_tf": "output vcn_id, subnet_ids map, nsg_ids map",
  "tfvars_example": "example variable values",
  "resource_count": 8,
  "resource_mappings": [
    {"aws_type": "VPC vpc-0abc123", "oci_type": "oci_core_vcn.main", "notes": ""}
  ],
  "gaps": [
    {"gap": "description", "severity": "CRITICAL|HIGH|MEDIUM|LOW", "mitigation": "how to fix"}
  ],
  "migration_prerequisites": ["Create OCI compartment", "..."],
  "architecture_notes": "Single VCN with public/private subnets using NSGs"
}
"""

_REVIEW_SYSTEM = """\
You are an OCI networking expert reviewing an AWS VPC -> OCI VCN Terraform translation.
Check the translation for correctness and completeness.

Review checklist:
- VCN CIDR is valid (/16 to /30 range)
- Subnets don't overlap with each other or the VCN CIDR boundary
- NSG rules correctly map security group rules (protocol numbers: TCP=6, UDP=17, ICMP=1, ALL=all)
- Port ranges are correctly specified in tcp_options/udp_options blocks
- Route tables have correct targets (internet gateway for public, NAT gateway for private, DRG for on-prem)
- All public subnets have a route to the internet gateway
- Private subnets have a route to the NAT gateway if a NAT gateway exists in the input
- ENIs: primary ENI (device_index=0) is noted as auto-created with instance; secondary ENIs have oci_core_vnic_attachment
- Resources use variables for compartment_id and other environment-specific values
- freeform_tags are applied to all resources
- No AWS resource types appear in the output

Severity rules (STRICT):
  CRITICAL -- Wrong OCI resource type, invalid HCL syntax, resource will fail terraform validate
  HIGH     -- Missing required fields, wrong protocol mapping, missing route for public/private subnet
  MEDIUM   -- Suboptimal configuration, missing tags, non-critical best practice gaps
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

_FIX_SYSTEM = """\
You are an OCI networking Terraform expert. Fix specific issues in an AWS VPC -> OCI VCN Terraform translation.
Target ONLY the issues listed. Do not change correct resources.

Output ONLY a JSON object with the same schema as the enhancement output, plus:
{
  "main_tf": "complete fixed HCL for VCN, subnets, NSGs, route tables",
  "variables_tf": "variables for compartment_id, vcn_display_name, etc.",
  "outputs_tf": "output vcn_id, subnet_ids map, nsg_ids map",
  "tfvars_example": "example variable values",
  "resource_count": 8,
  "resource_mappings": [...],
  "gaps": [...],
  "migration_prerequisites": [...],
  "architecture_notes": "...",
  "fixes_applied": ["Fixed protocol mapping for TCP rule", "Added route to internet gateway for public subnet", ...]
}
"""


# ═══════════════════════════════════════════════════════════════════════════════
# NetworkTranslationOrchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class NetworkTranslationOrchestrator(BaseTranslationOrchestrator):
    """AWS VPC/Networking -> OCI VCN Terraform translation orchestrator."""

    SKILL_TYPE      = "network_translation"
    PROJECT_TYPE    = "network"
    REPORT_FILENAME = "network-translation.md"

    ENHANCEMENT_SYSTEM = _ENHANCEMENT_SYSTEM
    REVIEW_SYSTEM      = _REVIEW_SYSTEM
    FIX_SYSTEM         = _FIX_SYSTEM

    # ── Gap analysis ────────────────────────────────────────────────────────

    def run_gap_analysis(self, input_data: dict) -> dict:
        """
        Run a lightweight gap analysis from the parsed input JSON.
        Returns structured dict with resource metrics for ConfidenceCalculator.
        """
        try:
            vpc_count    = 1 if input_data.get("vpc_id") else 0
            subnet_count = len(input_data.get("subnets", []))
            sg_count     = len(input_data.get("security_groups", []))
            rt_count     = len(input_data.get("route_tables", []))
            igw_count    = len(input_data.get("internet_gateways", []))
            nat_count    = len(input_data.get("nat_gateways", []))
            eni_list     = input_data.get("network_interfaces", [])
            # Primary ENIs (device_index=0) map to auto-created VNICs — no Terraform resource
            # Secondary ENIs (device_index>0) → oci_core_vnic_attachment
            secondary_eni_count = sum(
                1 for e in eni_list if e.get("device_index", 0) != 0
            ) if eni_list else 0
            eni_note_count = len(eni_list) - secondary_eni_count  # primary ENIs noted only

            total_resources = (
                vpc_count + subnet_count + sg_count + rt_count + igw_count + nat_count
                + secondary_eni_count
            )
            if total_resources == 0:
                total_resources = 1

            # All network resources have OCI equivalents; actual gaps found by reviewer
            mapped_resources = total_resources

            resource_summary = {
                "vpcs": vpc_count,
                "subnets": subnet_count,
                "security_groups": sg_count,
                "route_tables": rt_count,
                "internet_gateways": igw_count,
                "nat_gateways": nat_count,
                "network_interfaces": len(eni_list),
            }

        except Exception:
            total_resources  = 1
            mapped_resources = 0
            resource_summary = {}

        return {
            "total_resources": total_resources,
            "mapped_resources": mapped_resources,
            "resource_summary": resource_summary,
        }

    # ── Prompt builders ─────────────────────────────────────────────────────

    def build_enhancement_prompt(
        self, input_content: str, input_data: dict,
        current_translation: dict | None, issues: list,
    ) -> str:
        prev = json.dumps(current_translation, indent=2) if current_translation else "None -- this is the initial translation."
        issues_text = json.dumps(issues, indent=2) if issues else "None"

        return (
            f"## AWS VPC Networking Input\n```json\n{json.dumps(input_data, indent=2)}\n```\n\n"
            f"## Current Translation\n```json\n{prev}\n```\n\n"
            f"## Issues to Fix\n```json\n{issues_text}\n```\n\n"
            "Produce the complete OCI Terraform VCN translation as a JSON object."
        )

    def build_review_prompt(
        self, input_content: str, input_data: dict, translation: dict,
    ) -> str:
        review_summary = {
            "resource_count": translation.get("resource_count", 0),
            "resource_mappings": translation.get("resource_mappings", []),
            "gaps": translation.get("gaps", []),
            "migration_prerequisites": translation.get("migration_prerequisites", []),
            "architecture_notes": translation.get("architecture_notes", ""),
            "main_tf_excerpt": translation.get("main_tf", "")[:4000],
        }

        return (
            f"## AWS VPC Networking Input\n```json\n{json.dumps(input_data, indent=2)[:3000]}\n```\n\n"
            f"## OCI Terraform Translation to Review\n```json\n{json.dumps(review_summary, indent=2)}\n```\n\n"
            "Review this translation according to your checklist and return a JSON object."
        )

    def build_fix_prompt(
        self, input_content: str, input_data: dict,
        translation: dict, issues: list,
    ) -> str:
        return (
            f"## AWS VPC Networking Input\n```json\n{json.dumps(input_data, indent=2)}\n```\n\n"
            f"## Current OCI Terraform Translation\n```json\n{json.dumps(translation, indent=2)}\n```\n\n"
            f"## Issues to Fix\n```json\n{json.dumps(issues, indent=2)}\n```\n\n"
            "Fix ONLY the listed issues. Return the complete updated translation as a JSON object."
        )

    # ── Report generation ───────────────────────────────────────────────────

    def generate_report_md(
        self, translation: dict, gap_analysis: dict, last_review: dict,
        final_decision: Any, final_confidence: float, iteration_count: int,
    ) -> str:
        return generate_rich_report_md(
            translation, gap_analysis, last_review,
            final_decision, final_confidence, iteration_count,
        )

    # ── Logger formatting ───────────────────────────────────────────────────

    def get_logger_source(self, input_data: dict) -> str:
        return input_data.get("vpc_id", "unknown-vpc")

    def format_gap_analysis_log(
        self, input_data: dict, gap_analysis: dict,
    ) -> tuple[str, str]:
        vpc_id = input_data.get("vpc_id", "unknown-vpc")
        resource_summary = gap_analysis.get("resource_summary", {})
        input_summary = f"AWS VPC networking input via API (vpc_id={vpc_id})"
        output_summary = (
            f"Gap analysis: {gap_analysis['total_resources']} resources detected "
            f"({', '.join(f'{v} {k}' for k, v in resource_summary.items() if v)})"
        )
        return input_summary, output_summary

    def format_enhancement_log(
        self, current_issues: list, translation: dict,
    ) -> tuple[str, str]:
        input_summary = f"Translate VPC networking, fix {len(current_issues)} issues"
        output_summary = f"Generated {translation.get('resource_count', 0)} OCI resources"
        return input_summary, output_summary


# ── Rich report generator (network-specific) ─────────────────────────────────

def generate_rich_report_md(
    translation: dict,
    gap_analysis: dict,
    last_review: dict,
    final_decision,
    final_confidence: float,
    iteration_count: int,
) -> str:
    """Generate a rich human-readable AWS VPC -> OCI VCN migration guide."""
    resource_mappings = translation.get("resource_mappings", [])
    gaps              = translation.get("gaps", [])
    prerequisites     = translation.get("migration_prerequisites", [])
    arch_notes        = translation.get("architecture_notes", "")
    resource_count    = translation.get("resource_count", len(resource_mappings))

    review_issues  = last_review.get("issues", [])
    review_summary = last_review.get("review_summary", "")

    total_resources  = gap_analysis.get("total_resources", resource_count)
    resource_summary = gap_analysis.get("resource_summary", {})

    decision_str = final_decision.value if hasattr(final_decision, "value") else str(final_decision)
    approved     = decision_str in ("APPROVED", "APPROVED_WITH_NOTES")
    status_icon  = "OK" if approved else "NEEDS REVIEW"

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

    # ── Header ─────────────────────────────────────────────────────────────────
    lines += [
        "# OCI VCN Network Translation",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        f"**Status:** {status_icon} {decision_str} ({iteration_count} iteration{'s' if iteration_count != 1 else ''}, {issues_summary})",
        "",
        "---",
        "",
    ]

    # ── Executive Summary ──────────────────────────────────────────────────────
    lines += ["## Executive Summary", ""]
    if review_summary:
        lines.append(review_summary)
        lines.append("")

    lines += [
        f"**Translation Complexity:** {complexity}",
        f"**AWS Input Resources:** {total_resources}",
        f"**OCI Terraform Resources:** {resource_count}",
        "",
    ]

    if resource_summary:
        lines.append("**Input Resource Breakdown:**")
        for rtype, count in resource_summary.items():
            if count:
                lines.append(f"- {rtype.replace('_', ' ').title()}: {count}")
        lines.append("")

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

    # ── Resource Mappings ──────────────────────────────────────────────────────
    if resource_mappings:
        lines += [
            "## Resource Mappings",
            "",
            "| AWS Resource | OCI Resource | Notes |",
            "|--------------|--------------|-------|",
        ]
        for rm in resource_mappings:
            aws_type = (rm.get("aws_type", "") or "").replace("|", "\\|")
            oci_type = (rm.get("oci_type", "") or "").replace("|", "\\|")
            note     = (rm.get("notes", "") or "").replace("|", "\\|")[:80]
            lines.append(f"| `{aws_type}` | `{oci_type}` | {note} |")
        lines += ["", "---", ""]

    # ── OCI Networking Notes ───────────────────────────────────────────────────
    lines += [
        "## OCI Networking Concepts",
        "",
        "Key differences from AWS networking:",
        "",
        "- **VCN (Virtual Cloud Network)** replaces the AWS VPC. CIDR must be /16 to /30.",
        "- **OCI Subnets are regional** -- they span all Availability Domains by default, unlike AWS subnets which are AZ-specific.",
        "- **Network Security Groups (NSGs)** are NIC-level constructs (equivalent to AWS security groups). They are attached to VNICs, not subnets.",
        "- **Security Lists** are subnet-level constructs (no direct AWS equivalent). NSGs are preferred for flexibility.",
        "- **Internet Gateway** serves the same purpose as AWS IGW. Route the subnet's route table to it for public access.",
        "- **NAT Gateway** is a standalone regional resource -- no per-AZ configuration needed.",
        "- **Dynamic Routing Gateway (DRG)** replaces AWS VGW/Transit Gateway for on-premises or inter-VCN connectivity.",
        "",
        "---",
        "",
    ]

    # ── Prerequisites ──────────────────────────────────────────────────────────
    if prerequisites:
        lines += ["## Prerequisites", ""]
        for i, prereq in enumerate(prerequisites, 1):
            lines.append(f"### {i}. {prereq}")
            lines.append("")
        lines += ["---", ""]

    # ── Deployment Checklist ───────────────────────────────────────────────────
    lines += ["## Deployment Checklist", ""]
    lines += [
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
        "- [ ] Validate all resources are created and reachable",
        "- [ ] Test connectivity: public subnets reach the internet, private subnets use NAT",
        "",
        "---",
        "",
    ]

    # ── Gaps Summary ──────────────────────────────────────────────────────────
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

    # ── Review Issues ──────────────────────────────────────────────────────────
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

    # ── Validation Summary ─────────────────────────────────────────────────────
    lines += ["## Validation Summary", ""]
    lines.append(f"**Final Decision:** {status_icon} {decision_str}")
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


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level exports for backward compatibility
# ═══════════════════════════════════════════════════════════════════════════════

_orchestrator = NetworkTranslationOrchestrator()
def run(input_content, progress_callback, anthropic_client, max_iterations=3):
    return _orchestrator.run(input_content, progress_callback, anthropic_client, max_iterations)
