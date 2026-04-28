"""Tests for per-skill terraform validation (Phase 3 checkpoint 1).

These tests validate the per_skill_validator module which runs `terraform
validate` against individual skill outputs and merged bundles.  The actual
terraform binary is never invoked -- all subprocess calls are mocked so
the suite stays fast and portable.
"""
import json
import os
import stat
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.per_skill_validator import (
    per_skill_validate,
    merged_bundle_validate,
    final_validate,
    make_validate_gap,
    _find_terraform_binary,
    _build_stub_variables_tf,
    _build_stub_providers_tf,
    PerSkillValidateResult,
    MergedValidateResult,
    FinalValidateResult,
)


# ── Mock helpers ────────────────────────────────────────────────────────────

def _mock_tf_success(*args, **kwargs):
    """Simulate terraform init + validate success."""
    cmd = args[0] if args else kwargs.get("args", [])
    mock_result = MagicMock()
    if "init" in cmd:
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
    elif "validate" in cmd:
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "valid": True,
            "error_count": 0,
            "warning_count": 0,
            "diagnostics": [],
        })
        mock_result.stderr = ""
    else:
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
    return mock_result


def _mock_tf_failure(*args, **kwargs):
    """Simulate terraform validate failure."""
    cmd = args[0] if args else kwargs.get("args", [])
    mock_result = MagicMock()
    if "init" in cmd:
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
    elif "validate" in cmd:
        mock_result.returncode = 1
        mock_result.stdout = json.dumps({
            "valid": False,
            "error_count": 1,
            "warning_count": 0,
            "diagnostics": [
                {
                    "severity": "error",
                    "summary": "Reference to undeclared resource",
                    "detail": (
                        'A managed resource "oci_core_subnet" "web" '
                        "has not been declared."
                    ),
                }
            ],
        })
        mock_result.stderr = ""
    else:
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
    return mock_result


# ── _find_terraform_binary ──────────────────────────────────────────────────

class TestFindTerraformBinary:
    """Tests for locating the terraform/tofu binary."""

    @patch("shutil.which", return_value="/usr/local/bin/terraform")
    def test_find_terraform_binary_on_path(self, mock_which):
        """When terraform is on PATH, _find_terraform_binary returns its path."""
        result = _find_terraform_binary()
        assert result is not None
        assert "terraform" in result

    @patch("shutil.which", return_value=None)
    def test_find_terraform_binary_missing(self, mock_which):
        """When terraform is absent, _find_terraform_binary returns None."""
        result = _find_terraform_binary()
        assert result is None


# ── _build_stub_variables_tf ────────────────────────────────────────────────

class TestBuildStubVariablesTf:
    """Tests for generating stub variable declarations from HCL content."""

    def test_build_stub_variables_tf_extracts_vars(self):
        """HCL referencing var.compartment_id and var.region produces both."""
        fragments = {
            "network.tf": (
                'resource "oci_core_vcn" "main" {\n'
                "  compartment_id = var.compartment_id\n"
                '  display_name  = "vcn-${var.region}"\n'
                "}\n"
            ),
        }
        stub = _build_stub_variables_tf(fragments)
        assert "compartment_id" in stub
        assert "region" in stub
        # Each variable should have a declaration block
        assert stub.count("variable") >= 2

    def test_build_stub_variables_tf_no_vars(self):
        """HCL with no var references produces empty or minimal output."""
        fragments = {
            "network.tf": (
                'resource "oci_core_vcn" "main" {\n'
                '  display_name = "static-name"\n'
                "}\n"
            ),
        }
        stub = _build_stub_variables_tf(fragments)
        # Should not contain any variable blocks
        assert "variable" not in stub or stub.strip() == ""


# ── _build_stub_providers_tf ────────────────────────────────────────────────

class TestBuildStubProvidersTf:
    """Tests for generating a stub providers.tf."""

    def test_build_stub_providers_tf(self):
        """Stub providers.tf contains the oracle/oci provider source."""
        stub = _build_stub_providers_tf()
        assert "oracle/oci" in stub
        # Should have a terraform required_providers block
        assert "required_providers" in stub


# ── per_skill_validate ──────────────────────────────────────────────────────

class TestPerSkillValidate:
    """Tests for validating a single skill's HCL output."""

    @patch("subprocess.run", side_effect=_mock_tf_success)
    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value="/usr/local/bin/terraform",
    )
    def test_per_skill_validate_valid_hcl(self, mock_bin, mock_run):
        """Valid HCL returns a passing PerSkillValidateResult."""
        fragments = {
            "network.tf": (
                'resource "oci_core_vcn" "main" {\n'
                "  compartment_id = var.compartment_id\n"
                "}\n"
            ),
        }
        result = per_skill_validate("network_translation", fragments)

        assert isinstance(result, PerSkillValidateResult)
        assert result.valid is True
        assert result.error_count == 0

    @patch("subprocess.run", side_effect=_mock_tf_failure)
    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value="/usr/local/bin/terraform",
    )
    def test_per_skill_validate_invalid_hcl(self, mock_bin, mock_run):
        """Invalid HCL returns a failing result with error details."""
        fragments = {
            "compute.tf": (
                'resource "oci_core_instance" "web" {\n'
                "  subnet_id = oci_core_subnet.web.id\n"
                "}\n"
            ),
        }
        result = per_skill_validate("ec2_translation", fragments)

        assert isinstance(result, PerSkillValidateResult)
        assert result.valid is False
        assert result.error_count > 0
        # Diagnostics should be populated
        assert len(result.diagnostics) > 0

    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value=None,
    )
    def test_per_skill_validate_no_terraform(self, mock_bin):
        """When terraform is missing, graceful degradation returns valid=True."""
        fragments = {"network.tf": 'resource "oci_core_vcn" "main" {}\n'}
        result = per_skill_validate("network_translation", fragments)

        assert isinstance(result, PerSkillValidateResult)
        assert result.valid is True
        assert result.error_count == 0

    @patch("subprocess.run", side_effect=_mock_tf_failure)
    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value="/usr/local/bin/terraform",
    )
    def test_per_skill_validate_known_bad_spec(self, mock_bin, mock_run):
        """Known-bad HCL referencing undefined resource types is caught."""
        fragments = {
            "main.tf": (
                'resource "oci_nonexistent_thing" "bad" {\n'
                "  compartment_id = var.compartment_id\n"
                "}\n"
            ),
        }
        result = per_skill_validate("custom_translation", fragments)

        assert result.valid is False
        assert result.error_count >= 1
        # At least one diagnostic should mention the problem
        summaries = [d.get("summary", "") for d in result.diagnostics]
        assert any("undeclared" in s.lower() or "resource" in s.lower() for s in summaries)


# ── make_validate_gap ───────────────────────────────────────────────────────

class TestMakeValidateGap:
    """Tests for the gap factory function."""

    def test_make_validate_gap(self):
        """Gap dict has the expected structure and keys."""
        gap = make_validate_gap(
            skill_type="network_translation",
            error_summary="Unexpected token in network.tf",
            check_name="hcl_syntax",
        )
        assert gap["check"] == "hcl_syntax"
        assert gap["severity"] == "HIGH"
        assert gap["skill"] == "network_translation"
        assert "Unexpected token" in gap["description"]
        assert "recommendation" in gap

    def test_make_validate_gap_defaults(self):
        """Gap dict uses default check_name when not specified."""
        gap = make_validate_gap(
            skill_type="synthesis",
            error_summary="Something broke",
        )
        assert gap["check"] == "terraform_validate"
        assert gap["skill"] == "synthesis"
        assert gap["severity"] == "HIGH"
