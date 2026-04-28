"""Tests for the post-synthesis validate-and-repair loop."""
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.synthesis_validator import (
    validate_and_repair,
    classify_gap,
    _static_checks,
    _find_var_references,
    _find_var_declarations,
)

import app.services.synthesis_validator as _sv_mod


class TestStaticChecks:
    """Test the static validation checks (no LLM)."""

    def test_finds_undeclared_variable(self):
        """A var.X reference with no matching variable declaration is flagged."""
        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" {\n  compartment_id = var.compartment_id\n  subnet_id = var.subnet_id\n}\n',
            "terraform/variables.tf": 'variable "compartment_id" {\n  type = string\n}\n',
        }
        gaps = _static_checks(bundle, [], [])
        undeclared = [g for g in gaps if g["check"] == "undeclared_variable"]
        assert len(undeclared) == 1
        assert "subnet_id" in undeclared[0]["description"]

    def test_no_gap_when_all_vars_declared(self):
        """When every referenced var is declared, no undeclared_variable gaps."""
        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" {\n  compartment_id = var.compartment_id\n}\n',
            "terraform/variables.tf": 'variable "compartment_id" {\n  type = string\n}\n',
        }
        gaps = _static_checks(bundle, [], [])
        undeclared = [g for g in gaps if g["check"] == "undeclared_variable"]
        assert len(undeclared) == 0

    def test_finds_missing_oci_resource(self):
        """When resource_mapping expects oci_core_vcn but bundle has none, flag it."""
        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" {}\n',
            "terraform/variables.tf": "",
        }
        resource_mapping = [
            {"aws_type": "AWS::EC2::VPC", "aws_name": "main-vpc",
             "oci_resource_type": "VCN", "oci_terraform": "oci_core_vcn"},
        ]
        gaps = _static_checks(bundle, resource_mapping, [])
        missing = [g for g in gaps if g["check"] == "missing_oci_resource"]
        assert len(missing) == 1
        assert "oci_core_vcn" in missing[0]["description"]

    def test_no_gap_when_resource_present(self):
        """When the expected OCI resource type exists in the bundle, no gap."""
        bundle = {
            "terraform/network.tf": 'resource "oci_core_vcn" "main" {}\n',
            "terraform/variables.tf": "",
        }
        resource_mapping = [
            {"aws_type": "AWS::EC2::VPC", "aws_name": "main-vpc",
             "oci_resource_type": "VCN", "oci_terraform": "oci_core_vcn"},
        ]
        gaps = _static_checks(bundle, resource_mapping, [])
        missing = [g for g in gaps if g["check"] == "missing_oci_resource"]
        assert len(missing) == 0

    def test_finds_504_in_skill_logs(self):
        """Skill logs with '504' are flagged as INFO gaps."""
        bundle = {"terraform/variables.tf": ""}
        logs = [
            "[network_translation] completed in 45s",
            "[network_translation] failed with 504 Gateway Time-out at 686s",
            "[ec2_translation] completed in 12s",
        ]
        gaps = _static_checks(bundle, [], logs)
        failure_gaps = [g for g in gaps if g["check"] == "skill_failure"]
        assert len(failure_gaps) == 1
        assert "504" in failure_gaps[0]["description"]

    def test_finds_failed_in_skill_logs(self):
        """Skill logs with 'failed' are flagged."""
        bundle = {"terraform/variables.tf": ""}
        logs = ["[storage_translation] failed: connection reset"]
        gaps = _static_checks(bundle, [], logs)
        failure_gaps = [g for g in gaps if g["check"] == "skill_failure"]
        assert len(failure_gaps) == 1

    def test_ocm_submodule_var_check(self):
        """Undeclared vars in terraform/ocm/ are flagged separately."""
        bundle = {
            "terraform/variables.tf": 'variable "compartment_id" { type = string }\n',
            "terraform/ocm/main.tf": 'resource "oci_cloud_migrations_migration" "main" {\n  compartment_id = var.compartment_id\n  display_name = var.migration_name\n}\n',
            "terraform/ocm/variables.tf": 'variable "compartment_id" { type = string }\n',
        }
        gaps = _static_checks(bundle, [], [])
        undeclared_ocm = [g for g in gaps if g["check"] == "undeclared_variable" and "ocm" in g.get("file", "")]
        assert len(undeclared_ocm) == 1
        assert "migration_name" in undeclared_ocm[0]["description"]

    def test_multiple_log_patterns_detected(self):
        """Multiple failure patterns in different log lines all get flagged."""
        bundle = {"terraform/variables.tf": ""}
        logs = [
            "[storage_translation] timed out after 300s",
            "[database_translation] produced no output",
        ]
        gaps = _static_checks(bundle, [], logs)
        failure_gaps = [g for g in gaps if g["check"] == "skill_failure"]
        assert len(failure_gaps) == 2

    def test_only_one_gap_per_log_line(self):
        """A log line matching multiple patterns ('failed' and '504') produces only one gap."""
        bundle = {"terraform/variables.tf": ""}
        logs = ["[network_translation] failed with 504 Gateway Time-out"]
        gaps = _static_checks(bundle, [], logs)
        failure_gaps = [g for g in gaps if g["check"] == "skill_failure"]
        assert len(failure_gaps) == 1


class TestValidateAndRepair:
    """Test the full validate_and_repair function."""

    def test_no_gaps_returns_bundle_unchanged(self):
        """When no gaps are found, bundle is returned as-is."""
        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" {\n  compartment_id = var.compartment_id\n}\n',
            "terraform/variables.tf": 'variable "compartment_id" {\n  type = string\n}\n',
        }
        result_bundle, remaining = validate_and_repair(bundle, [], [])
        assert remaining == []
        assert result_bundle == bundle

    @patch("app.services.synthesis_validator._run_writer_agent")
    def test_repair_loop_applies_patches(self, mock_agent):
        """When writer agent fixes the gap, the repaired bundle is returned."""
        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" {\n  compartment_id = var.compartment_id\n  subnet_id = var.subnet_id\n}\n',
            "terraform/variables.tf": 'variable "compartment_id" {\n  type = string\n}\n',
        }

        # Simulate the writer agent adding the missing variable via tools
        async def fake_agent(gaps):
            _sv_mod._current_bundle["terraform/variables.tf"] = (
                'variable "compartment_id" {\n  type = string\n}\n'
                'variable "subnet_id" {\n  type = string\n}\n'
            )
        mock_agent.side_effect = fake_agent

        result_bundle, remaining = validate_and_repair(bundle, [], [])
        undeclared = [g for g in remaining if g["check"] == "undeclared_variable"]
        assert len(undeclared) == 0
        assert 'variable "subnet_id"' in result_bundle["terraform/variables.tf"]

    @patch("app.services.synthesis_validator._run_writer_agent")
    def test_repair_loop_stops_on_empty_patches(self, mock_agent):
        """Repair loop stops when writer agent makes no changes (no progress)."""
        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" { subnet_id = var.missing_var }\n',
            "terraform/variables.tf": "",
        }

        # Writer agent does nothing -- bundle stays the same
        async def fake_agent(gaps):
            pass
        mock_agent.side_effect = fake_agent

        result_bundle, remaining = validate_and_repair(
            bundle, [], [], max_iterations=2
        )
        # Should still have gaps since agent fixed nothing
        undeclared = [g for g in remaining if g["check"] == "undeclared_variable"]
        assert len(undeclared) > 0
        # Should have been called once, then no-progress detected on next iteration
        assert mock_agent.call_count == 1

    @patch("app.services.synthesis_validator._run_writer_agent")
    def test_repair_stops_when_no_progress(self, mock_agent):
        """If repair does not reduce gap count, it stops iterating."""
        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" { x = var.a\n y = var.b }\n',
            "terraform/variables.tf": "",
        }

        # Fix one var but add a reference to another -- net no decrease
        async def fake_agent(gaps):
            _sv_mod._current_bundle["terraform/variables.tf"] = 'variable "a" { type = string }\n'
            _sv_mod._current_bundle["terraform/compute.tf"] = (
                'resource "oci_core_instance" "web" { x = var.a\n y = var.b\n z = var.c }\n'
            )
        mock_agent.side_effect = fake_agent

        result_bundle, remaining = validate_and_repair(
            bundle, [], [], max_iterations=3
        )
        # Should have stopped because gap count did not decrease
        assert mock_agent.call_count <= 2

    @patch("app.services.synthesis_validator._run_writer_agent")
    def test_info_gaps_do_not_trigger_repair(self, mock_agent):
        """INFO-severity gaps (skill failures) do not trigger LLM repair."""
        bundle = {
            "terraform/variables.tf": "",
        }
        # Only have skill-failure log gaps (INFO severity)
        result_bundle, remaining = validate_and_repair(
            bundle, [], ["[storage_translation] failed: timeout"]
        )
        # Writer agent should not have been called
        mock_agent.assert_not_called()
        # But the INFO gap should still be in remaining
        failure_gaps = [g for g in remaining if g["check"] == "skill_failure"]
        assert len(failure_gaps) == 1


class TestHelpers:
    """Test helper functions."""

    def test_find_var_references(self):
        assert _find_var_references('compartment_id = var.compartment_id') == {"compartment_id"}
        assert _find_var_references('x = var.foo\ny = var.bar') == {"foo", "bar"}
        assert _find_var_references('no vars here') == set()

    def test_find_var_declarations(self):
        hcl = 'variable "foo" {\n  type = string\n}\nvariable "bar" {\n  type = number\n}\n'
        assert _find_var_declarations(hcl) == {"foo", "bar"}
        assert _find_var_declarations("no variables") == set()

    def test_find_var_references_does_not_match_partial(self):
        """var. must be a word boundary match, not a substring."""
        # 'var.foo' in a comment should still match (regex does not skip comments)
        assert _find_var_references('# var.foo') == {"foo"}
        # But 'avar.foo' should not match due to word boundary
        assert _find_var_references('avar.foo') == set()


class TestClassifyGap:
    """Test the classify_gap helper."""

    def test_undeclared_variable_is_auto_fixable(self):
        gap = {"check": "undeclared_variable", "severity": "HIGH", "description": "var.x undeclared"}
        assert classify_gap(gap) == "auto_fixable"

    def test_skill_failure_is_needs_human(self):
        gap = {"check": "skill_failure", "severity": "INFO", "description": "504 timeout"}
        assert classify_gap(gap) == "needs_human"

    def test_missing_oci_resource_auto_fixable(self):
        gap = {"check": "missing_oci_resource", "severity": "HIGH",
               "description": "Resource mapping expects oci_core_vcn"}
        assert classify_gap(gap) == "auto_fixable"

    def test_missing_oci_resource_unmapped_needs_human(self):
        gap = {"check": "missing_oci_resource", "severity": "HIGH",
               "description": "No entry in resources.yaml for this type"}
        assert classify_gap(gap) == "needs_human"

    def test_explicit_needs_human_flag(self):
        gap = {"check": "undeclared_variable", "needs_human": True}
        assert classify_gap(gap) == "needs_human"

    def test_info_severity_defaults_to_needs_human(self):
        gap = {"check": "unknown_check", "severity": "INFO", "description": "informational"}
        assert classify_gap(gap) == "needs_human"

    def test_unknown_check_defaults_to_auto_fixable(self):
        gap = {"check": "some_new_check", "severity": "HIGH", "description": "something"}
        assert classify_gap(gap) == "auto_fixable"

    def test_hcl_syntax_is_auto_fixable(self):
        gap = {"check": "hcl_syntax", "severity": "HIGH", "description": "bad syntax"}
        assert classify_gap(gap) == "auto_fixable"


class TestSmartValidateLoop:
    """Test the upgraded validate-and-repair loop."""

    def test_loop_terminates_on_zero_auto_fixable(self):
        """When all gaps are needs_human, loop stops immediately."""
        bundle = {"terraform/variables.tf": ""}
        # Only skill-failure gaps (needs_human)
        result_bundle, remaining = validate_and_repair(
            bundle, [], ["[storage_translation] failed: timeout"]
        )
        failure_gaps = [g for g in remaining if g["check"] == "skill_failure"]
        assert len(failure_gaps) == 1
        assert "why_not_auto_fixed" in failure_gaps[0]

    @patch("app.services.synthesis_validator._run_writer_agent")
    def test_loop_terminates_on_no_progress(self, mock_agent):
        """If same auto-fixable gaps persist, loop breaks."""
        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" { x = var.stuck_var }\n',
            "terraform/variables.tf": "",
        }

        # Agent writes something that doesn't fix the problem
        async def fake_agent(gaps):
            _sv_mod._current_bundle["terraform/variables.tf"] = "# no vars here\n"
        mock_agent.side_effect = fake_agent

        result_bundle, remaining = validate_and_repair(bundle, [], [])
        undeclared = [g for g in remaining if g["check"] == "undeclared_variable"]
        assert len(undeclared) >= 1
        # Should have stopped after detecting no progress (1 call: agent runs,
        # reviewer sees same count, next iteration detects no-progress)
        assert mock_agent.call_count <= 2

    @patch("app.services.synthesis_validator._run_writer_agent")
    def test_loop_respects_hard_cap(self, mock_agent):
        """Loop never exceeds 8 iterations."""
        call_count = [0]

        async def fake_agent(gaps):
            call_count[0] += 1
            # Fix one var but add another -- always makes progress (count goes
            # down by one then back up, but the *set* changes each time so the
            # count-based check sees 1 -> 1 on the second round and breaks)
            _sv_mod._current_bundle["terraform/variables.tf"] = (
                f'variable "v{call_count[0]}" {{ type = string }}\n'
            )
            _sv_mod._current_bundle["terraform/compute.tf"] = (
                f'resource "oci_core_instance" "web" {{ x = var.v{call_count[0]+1} }}\n'
            )
        mock_agent.side_effect = fake_agent

        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" { x = var.v1 }\n',
            "terraform/variables.tf": "",
        }
        result_bundle, remaining = validate_and_repair(bundle, [], [])
        assert mock_agent.call_count <= 8

    def test_needs_human_gaps_carry_why_not_auto_fixed(self):
        """All needs_human gaps have a why_not_auto_fixed field."""
        bundle = {"terraform/variables.tf": ""}
        result_bundle, remaining = validate_and_repair(
            bundle, [], ["[x] failed: timeout", "[y] timed out at 300s"]
        )
        for g in remaining:
            if classify_gap(g) == "needs_human":
                assert "why_not_auto_fixed" in g
                assert len(g["why_not_auto_fixed"]) > 0

    @patch("app.services.synthesis_validator._run_writer_agent")
    def test_repaired_gaps_disappear_from_final_list(self, mock_agent):
        """Auto-fixable gaps that get repaired are not in the final list."""
        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" { x = var.missing_var }\n',
            "terraform/variables.tf": "",
        }

        async def fake_agent(gaps):
            _sv_mod._current_bundle["terraform/variables.tf"] = (
                'variable "missing_var" { type = string }\n'
            )
        mock_agent.side_effect = fake_agent

        result_bundle, remaining = validate_and_repair(bundle, [], [])
        undeclared = [g for g in remaining if g["check"] == "undeclared_variable"]
        assert len(undeclared) == 0

    @patch("app.services.synthesis_validator._run_writer_agent")
    def test_progress_callback_receives_iteration_logs(self, mock_agent):
        """The _progress callback receives iteration log lines."""
        async def fake_agent(gaps):
            _sv_mod._current_bundle["terraform/variables.tf"] = (
                'variable "missing_var" { type = string }\n'
            )
        mock_agent.side_effect = fake_agent

        bundle = {
            "terraform/compute.tf": 'resource "oci_core_instance" "web" { x = var.missing_var }\n',
            "terraform/variables.tf": "",
        }
        progress_lines = []

        def fake_progress(step, msg):
            progress_lines.append(msg)

        validate_and_repair(bundle, [], [], _progress=fake_progress)
        # Should have at least one "Validation iter" line
        assert any("Validation iter" in line for line in progress_lines)
