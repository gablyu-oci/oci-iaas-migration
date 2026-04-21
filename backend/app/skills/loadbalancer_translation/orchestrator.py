#!/usr/bin/env python3
"""
AWS ALB/NLB -> OCI Load Balancer Terraform Orchestrator -- backend-adapted version.

Runs the enhancement -> review -> fix agent loop via BaseTranslationOrchestrator
and returns results as dicts instead of writing files.
Accepts an Anthropic client from the caller.
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
# LoadBalancer Translation Orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

class LoadBalancerTranslationOrchestrator(BaseTranslationOrchestrator):
    """AWS ALB/NLB -> OCI Load Balancer Terraform translation orchestrator."""

    SKILL_TYPE     = "loadbalancer_translation"
    PROJECT_TYPE   = "loadbalancer"
    REPORT_FILENAME = "loadbalancer-translation.md"

    # ── System prompts (copied exactly from original) ────────────────────────

    ENHANCEMENT_SYSTEM = """\
You are an expert AWS ALB/NLB to OCI Load Balancer Terraform translator.
Convert the provided AWS load balancer definitions to production-ready OCI Terraform HCL.

Load balancer type mapping rules:
- ALB (type: "application") → oci_load_balancer_load_balancer (flexible shape)
  - Add oci_load_balancer_backend_set for each target group
  - Add oci_load_balancer_listener for each listener
- NLB (type: "network") → oci_network_load_balancer_network_load_balancer
  - Add oci_network_load_balancer_backend_set for each target group
  - Add oci_network_load_balancer_listener for each listener

Scheme mapping:
- internet-facing → is_private = false
- internal → is_private = true

Target group → backend set mapping:
- Each target group becomes a backend set
- health_check block maps to health_checker block in backend set
- health_check.path → health_checker url_path (for HTTP/HTTPS protocols)
- health_check.interval → health_checker interval_ms (multiply by 1000)
- health_check.timeout → health_checker timeout_in_millis (multiply by 1000)
- health_check.healthy_threshold → health_checker retries

Listener mapping:
- HTTP → HTTP in OCI LB, port maps directly
- HTTPS → HTTPS in OCI LB; NOTE as a gap that SSL certificate must be imported or created in OCI Certificate Service
- TCP → TCP for NLB

ALB flexible shape:
- Use shape = "flexible" with shape_details block
- Set minimum_bandwidth_in_mbps = 10 and maximum_bandwidth_in_mbps = 100 (or appropriate values)

Additional rules:
- Use variables for compartment_id, subnet_ids (list), backend_instance_ids (list)
- Add freeform_tags to all resources
- For HTTPS listeners: create a placeholder certificate_ids variable with a comment explaining the requirement
- Backend sets for ALB use ROUND_ROBIN or LEAST_CONNECTIONS policy

Output ONLY a JSON object with this schema:
{
  "main_tf": "complete HCL content for main.tf (oci_load_balancer_load_balancer, backend_set, listener resources)",
  "variables_tf": "HCL content for variables.tf (compartment_id, subnet_ids, backend_instance_ids)",
  "outputs_tf": "HCL content for outputs.tf (load_balancer_id, ip_addresses)",
  "tfvars_example": "terraform.tfvars.example content",
  "resource_count": 3,
  "resource_mappings": [
    {"aws_type": "ALB prod-alb", "oci_type": "oci_load_balancer_load_balancer.prod_alb", "notes": ""}
  ],
  "gaps": [
    {"gap": "Description", "severity": "CRITICAL|HIGH|MEDIUM|LOW", "mitigation": "How to address"}
  ],
  "migration_prerequisites": [
    "Deploy backend EC2 equivalents first (compute phase)",
    "Import or create SSL certificate in OCI Certificate Service if using HTTPS"
  ],
  "architecture_notes": "Brief description of the OCI load balancer architecture"
}
"""

    REVIEW_SYSTEM = """\
You are an expert OCI Terraform reviewer with deep knowledge of both AWS ALB/NLB and OCI Load Balancer.
Review an AWS ALB/NLB -> OCI Load Balancer Terraform translation for correctness.

Check specifically:
- ALB maps to oci_load_balancer_load_balancer (not network load balancer)
- NLB maps to oci_network_load_balancer_network_load_balancer
- Backend set health checker is correct (interval_ms, timeout_in_millis in milliseconds)
- Listener protocol and port match the source listener
- SSL/HTTPS listeners have a gap documented for certificate handling
- Subnet references use variables (not hardcoded OCIDs)
- is_private = false for internet-facing, true for internal
- ALB uses flexible shape with shape_details block
- Backend instance IDs use variables (not hardcoded)

Severity rules (STRICT):
  CRITICAL -- Wrong OCI resource type, invalid HCL syntax, resource will fail terraform validate
  HIGH     -- Missing required fields, wrong property mapping, hardcoded values where variables required, architectural mismatch
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
You are an OCI Terraform expert. Fix specific issues in an AWS ALB/NLB->OCI Load Balancer Terraform translation.
Target ONLY the issues listed. Do not change correct resources.

Output ONLY a JSON object with the same schema as the enhancement output, plus:
{
  "main_tf": "complete fixed HCL content for main.tf",
  "variables_tf": "HCL content for variables.tf",
  "outputs_tf": "HCL content for outputs.tf",
  "tfvars_example": "terraform.tfvars.example content",
  "resource_count": 3,
  "resource_mappings": [...],
  "gaps": [...],
  "migration_prerequisites": [...],
  "architecture_notes": "...",
  "fixes_applied": ["Fixed health checker interval to milliseconds", "Changed to flexible shape", ...]
}
"""

    # ── Cache control overrides ──────────────────────────────────────────────
    # LoadBalancer uses cache_control on both enhancement and fix system blocks.

    def get_enhancement_system_blocks(self) -> list[dict]:
        blocks = [{
            "type": "text", "text": self.ENHANCEMENT_SYSTEM,
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
            "type": "text", "text": self.FIX_SYSTEM,
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
        Run a lightweight gap analysis directly from parsed load balancer input.
        Returns structured dict with resource metrics for ConfidenceCalculator.
        """
        try:
            load_balancers = input_data.get("load_balancers", [])
            total_lbs = len(load_balancers)

            # Count total resources: each LB + its listeners + its backend sets
            total_resources = 0
            lb_types = []
            https_count = 0

            for lb in load_balancers:
                total_resources += 1  # The LB itself
                lb_types.append(lb.get("type", "application"))
                listeners = lb.get("listeners", [])
                target_groups = lb.get("target_groups", [])
                total_resources += len(listeners) + len(target_groups)
                https_count += sum(1 for lst in listeners if lst.get("protocol", "").upper() == "HTTPS")

            lb_types_unique = sorted(set(lb_types))
            # HTTPS listeners create a gap (certificate required) but are still mappable
            mapped_resources = total_resources

        except Exception:
            total_lbs = 1
            total_resources = 1
            lb_types_unique = []
            mapped_resources = 0
            https_count = 0

        return {
            "total_resources": total_resources,
            "mapped_resources": mapped_resources,
            "total_load_balancers": total_lbs,
            "lb_types": lb_types_unique,
            "https_listener_count": https_count,
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
            f"## AWS Load Balancer Definitions\n```json\n{input_text}\n```\n\n"
            f"## Current Translation\n```json\n{prev}\n```\n\n"
            f"## Issues to Fix\n```json\n{issues_text}\n```\n\n"
            "Produce the complete OCI Load Balancer Terraform translation as a JSON object."
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
            f"## AWS Load Balancer Definitions\n```json\n{input_text[:3000]}\n```\n\n"
            f"## OCI Load Balancer Terraform Translation to Review\n```json\n{json.dumps(review_summary, indent=2)}\n```\n\n"
            "Review this translation according to your checklist and return a JSON object."
        )

    def build_fix_prompt(
        self, input_content: str, input_data: dict,
        translation: dict, issues: list,
    ) -> str:
        input_text = input_content

        return (
            f"## AWS Load Balancer Definitions\n```json\n{input_text}\n```\n\n"
            f"## Current OCI Load Balancer Terraform Translation\n```json\n{json.dumps(translation, indent=2)}\n```\n\n"
            f"## Issues to Fix\n```json\n{json.dumps(issues, indent=2)}\n```\n\n"
            "Fix ONLY the listed issues. Return the complete updated translation as a JSON object."
        )

    # ── Logging helpers ──────────────────────────────────────────────────────

    def format_gap_analysis_log(
        self, input_data: dict, gap_analysis: dict,
    ) -> tuple[str, str]:
        input_summary = "AWS ALB/NLB definitions via API"
        output_summary = (
            f"Gap analysis: {gap_analysis['total_load_balancers']} load balancers detected, "
            f"{gap_analysis['total_resources']} total resources, "
            f"types: {', '.join(gap_analysis['lb_types']) or 'unknown'}"
        )
        return input_summary, output_summary

    def format_enhancement_log(
        self, current_issues: list, translation: dict,
    ) -> tuple[str, str]:
        input_summary = f"Translate load balancers, fix {len(current_issues)} issues"
        output_summary = f"Generated {translation.get('resource_count', 0)} OCI load balancer resources"
        return input_summary, output_summary

    # ── Report generation ────────────────────────────────────────────────────

    def generate_report_md(
        self, translation: dict, gap_analysis: dict, last_review: dict,
        final_decision: Any, final_confidence: float, iteration_count: int,
    ) -> str:
        """Generate a rich human-readable ALB/NLB->OCI Load Balancer migration guide."""
        resource_mappings = translation.get("resource_mappings", [])
        gaps = translation.get("gaps", [])
        prerequisites = translation.get("migration_prerequisites", [])
        arch_notes = translation.get("architecture_notes", "")
        resource_count = translation.get("resource_count", len(resource_mappings))

        review_issues = last_review.get("issues", [])
        review_summary = last_review.get("review_summary", "")

        total_resources = gap_analysis.get("total_resources", resource_count)
        total_lbs = gap_analysis.get("total_load_balancers", 1)
        lb_types = gap_analysis.get("lb_types", [])
        https_count = gap_analysis.get("https_listener_count", 0)

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

        complexity = "HIGH" if total_resources >= 10 else "MEDIUM" if total_resources >= 4 else "LOW"

        lines = []

        # ── Header ────────────────────────────────────────────────────────────
        lines += [
            "# OCI Load Balancer Terraform Translation",
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
            f"**AWS Load Balancers:** {total_lbs}",
            f"**Total AWS Resources (LBs + listeners + target groups):** {total_resources}",
            f"**OCI Terraform Resources:** {resource_count}",
            f"**LB Types:** {', '.join(lb_types) if lb_types else 'N/A'}",
        ]
        if https_count:
            lines.append(f"**HTTPS Listeners:** {https_count} (SSL certificate required in OCI Certificate Service)")
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
            "- [ ] Populate `subnet_ids` with OCI subnet OCIDs for the load balancer",
            "- [ ] Populate `backend_instance_ids` after deploying compute instances",
            "- [ ] Run `terraform validate` to check HCL syntax",
            "- [ ] Run `terraform plan` and review the execution plan",
        ]
        if https_count:
            lines.append("- [ ] Import or create SSL certificate in OCI Certificate Service and populate certificate OCID variable")
        for i, prereq in enumerate(prerequisites, 1):
            lines.append(f"- [ ] Complete prerequisite {i}: {prereq}")
        for gap in gaps:
            if gap.get("severity") in ("HIGH", "CRITICAL"):
                lines.append(f"- [ ] Address gap: {gap.get('gap', '')} -- {gap.get('mitigation', '')}")
        for issue in high_issues:
            lines.append(f"- [ ] Fix: {issue.get('description', '')}")
        lines += [
            "- [ ] Run `terraform apply` in a non-production environment first",
            "- [ ] Validate load balancer IP addresses and DNS are reachable",
            "- [ ] Update DNS records to point to OCI load balancer IP addresses",
            "",
            "---",
            "",
        ]

        # ── Gaps Summary ──────────────────────────────────────────────────────
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


# ── Module-level exports (backward compatibility) ────────────────────────────

_orchestrator = LoadBalancerTranslationOrchestrator()
def run(
    input_content: str,
    progress_callback,
    anthropic_client,
    max_iterations: int = 3,
) -> dict:
    """
    Full AWS ALB/NLB -> OCI Load Balancer Terraform orchestration.

    Args:
        input_content: JSON string with load_balancers array
        progress_callback: Called with (phase, iteration, confidence, decision)
        anthropic_client: Pre-configured Anthropic client
        max_iterations: Max enhancement/review/fix iterations

    Returns:
        dict with keys: artifacts, confidence, decision, iterations, cost, interactions
    """
    return _orchestrator.run(
        input_content=input_content,
        progress_callback=progress_callback,
        anthropic_client=anthropic_client,
        max_iterations=max_iterations,
    )
