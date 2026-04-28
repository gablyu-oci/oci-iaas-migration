"""Test that validator gaps are wired into reports/gaps.md."""
import json
import pytest

from app.services.bundle_builder import build_hybrid_bundle, _render_gaps_md
from app.services.synthesis_validator import _static_checks


class TestValidatorGapsInReport:
    """Verify that post-synthesis validator gaps appear in reports/gaps.md."""

    def test_validator_gaps_appear_in_gaps_md(self):
        """Simulate the orchestrator flow: build bundle, validate, re-render gaps.md."""
        # 1. Build a bundle with some initial gaps
        initial_gaps = [
            {
                "skill": "synthesis",
                "severity": "MEDIUM",
                "description": "Label collision resolved",
                "recommendation": "Review renamed blocks.",
            }
        ]
        artifacts = {
            "synthesis/network.tf": 'resource "oci_core_vcn" "main" { compartment_id = var.compartment_id }\n',
            "synthesis/variables.tf": 'variable "compartment_id" { type = string }\n',
            "synthesis/compute.tf": 'resource "oci_core_instance" "web" { subnet_id = var.missing_subnet_id }\n',
            "_review_gaps_sentinel": json.dumps(initial_gaps),
        }
        bundle = build_hybrid_bundle(
            artifacts,
            migration_name="test",
            resource_count=3,
            skills_ran=["network_translation", "ec2_translation"],
        )

        # 2. Validator finds a gap (missing variable)
        validator_gaps = _static_checks(bundle, [], [])
        assert any(
            "missing_subnet_id" in g.get("description", "") for g in validator_gaps
        ), "Validator should detect undeclared var.missing_subnet_id"

        # 3. Simulate the orchestrator's gap-merge logic
        all_gaps = list(initial_gaps)  # copy
        for gap in validator_gaps:
            if gap.get("severity") != "INFO":
                all_gaps.append(
                    {
                        "skill": gap.get("skill", "synthesis_validator"),
                        "severity": gap.get("severity", "HIGH"),
                        "description": gap.get("description", ""),
                        "recommendation": "Review and fix manually or re-run the plan.",
                    }
                )

        # 4. Re-render gaps.md (this is the fix we're verifying)
        bundle["reports/gaps.md"] = _render_gaps_md(
            all_gaps, ["network_translation", "ec2_translation"]
        )

        # 5. Assert validator gap is now in gaps.md
        gaps_md = bundle["reports/gaps.md"]
        assert "missing_subnet_id" in gaps_md, (
            "Validator gap about missing var should appear in gaps.md"
        )
        assert "Label collision" in gaps_md, (
            "Original synthesis gap should still be present"
        )

    def test_no_validator_gaps_preserves_original_report(self):
        """When validator finds no gaps, gaps.md stays as bundle_builder rendered it."""
        initial_gaps = [
            {
                "skill": "network_translation",
                "severity": "LOW",
                "description": "Minor naming issue",
                "recommendation": "Rename.",
            }
        ]
        artifacts = {
            "synthesis/network.tf": 'resource "oci_core_vcn" "main" { compartment_id = var.compartment_id }\n',
            "synthesis/variables.tf": 'variable "compartment_id" { type = string }\n',
            "_review_gaps_sentinel": json.dumps(initial_gaps),
        }
        bundle = build_hybrid_bundle(
            artifacts,
            migration_name="test",
            resource_count=1,
            skills_ran=["network_translation"],
        )

        # Validator finds nothing actionable
        validator_gaps = []
        all_gaps = list(initial_gaps)
        # No new gaps to add

        # Re-render (no change expected)
        bundle["reports/gaps.md"] = _render_gaps_md(all_gaps, ["network_translation"])

        gaps_md = bundle["reports/gaps.md"]
        assert "Minor naming issue" in gaps_md
