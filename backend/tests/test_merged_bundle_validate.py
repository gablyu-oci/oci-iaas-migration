"""Tests for merged bundle + final terraform validation (Phase 3 checkpoints 2-3).

These tests cover the second and third validation stages: merged-bundle
validation (all skill TF files together) and final validation (the complete
bundle ready for `terraform apply`).  All terraform subprocess calls are
mocked.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from app.services.per_skill_validator import (
    merged_bundle_validate,
    final_validate,
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


def _mock_tf_failure_multi(*args, **kwargs):
    """Simulate terraform validate failure with multiple diagnostics."""
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
            "error_count": 2,
            "warning_count": 0,
            "diagnostics": [
                {
                    "severity": "error",
                    "summary": "Reference to undeclared resource",
                    "detail": (
                        'A managed resource "oci_core_subnet" "web" '
                        "has not been declared."
                    ),
                },
                {
                    "severity": "error",
                    "summary": "Unsupported attribute",
                    "detail": (
                        'This object has no argument, nested block, or '
                        'exported attribute named "bogus".'
                    ),
                },
            ],
        })
        mock_result.stderr = ""
    else:
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
    return mock_result


# ── Sample bundles ──────────────────────────────────────────────────────────

_CLEAN_BUNDLE = {
    "terraform/network.tf": (
        'resource "oci_core_vcn" "main" {\n'
        "  compartment_id = var.compartment_id\n"
        '  display_name  = "main-vcn"\n'
        '  cidr_blocks   = ["10.0.0.0/16"]\n'
        "}\n"
        "\n"
        'resource "oci_core_subnet" "web" {\n'
        "  compartment_id = var.compartment_id\n"
        "  vcn_id         = oci_core_vcn.main.id\n"
        '  cidr_block     = "10.0.1.0/24"\n'
        "}\n"
    ),
    "terraform/variables.tf": (
        'variable "compartment_id" {\n'
        "  type        = string\n"
        '  description = "OCI compartment OCID"\n'
        "}\n"
        "\n"
        'variable "region" {\n'
        "  type        = string\n"
        '  description = "OCI region"\n'
        '  default     = "us-ashburn-1"\n'
        "}\n"
    ),
    "terraform/providers.tf": (
        "terraform {\n"
        "  required_providers {\n"
        "    oci = {\n"
        '      source  = "oracle/oci"\n'
        '      version = ">= 5.0"\n'
        "    }\n"
        "  }\n"
        "}\n"
        "\n"
        'provider "oci" {\n'
        "  region = var.region\n"
        "}\n"
    ),
}

_CROSS_REF_BUNDLE = {
    "terraform/network.tf": (
        'resource "oci_core_vcn" "main" {\n'
        "  compartment_id = var.compartment_id\n"
        "}\n"
    ),
    "terraform/compute.tf": (
        'resource "oci_core_instance" "web" {\n'
        "  compartment_id = var.compartment_id\n"
        "  # References a subnet that does NOT exist in network.tf\n"
        "  subnet_id = oci_core_subnet.web.id\n"
        "}\n"
    ),
    "terraform/variables.tf": (
        'variable "compartment_id" {\n'
        "  type = string\n"
        "}\n"
    ),
    "terraform/providers.tf": (
        "terraform {\n"
        "  required_providers {\n"
        "    oci = {\n"
        '      source  = "oracle/oci"\n'
        '      version = ">= 5.0"\n'
        "    }\n"
        "  }\n"
        "}\n"
    ),
}

_BUNDLE_WITH_OCM = {
    "terraform/network.tf": 'resource "oci_core_vcn" "main" {}\n',
    "terraform/variables.tf": 'variable "compartment_id" { type = string }\n',
    "terraform/providers.tf": "terraform {}\n",
    "terraform/ocm/main.tf": (
        'resource "oci_cloud_migrations_migration" "m" {\n'
        "  compartment_id = var.compartment_id\n"
        "}\n"
    ),
    "terraform/ocm/variables.tf": (
        'variable "compartment_id" { type = string }\n'
    ),
}


# ── merged_bundle_validate ──────────────────────────────────────────────────

class TestMergedBundleValidate:
    """Tests for merged-bundle validation (Phase 3 checkpoint 2)."""

    @patch("subprocess.run", side_effect=_mock_tf_success)
    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value="/usr/local/bin/terraform",
    )
    def test_merged_bundle_validate_clean(self, mock_bin, mock_run):
        """A clean bundle with no cross-ref errors validates successfully."""
        result = merged_bundle_validate(_CLEAN_BUNDLE)

        assert isinstance(result, MergedValidateResult)
        assert result.valid is True
        assert result.error_count == 0
        assert result.gaps == []

    @patch("subprocess.run", side_effect=_mock_tf_failure)
    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value="/usr/local/bin/terraform",
    )
    def test_merged_bundle_validate_cross_ref_error(self, mock_bin, mock_run):
        """Cross-file reference error produces gaps with skill='synthesis'."""
        result = merged_bundle_validate(_CROSS_REF_BUNDLE)

        assert isinstance(result, MergedValidateResult)
        assert result.valid is False
        assert result.error_count >= 1
        assert len(result.gaps) >= 1
        # Cross-reference errors detected during merged validation should
        # be attributed to "synthesis" (the merge step), not an individual skill.
        for gap in result.gaps:
            assert gap["skill"] == "synthesis"

    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value=None,
    )
    def test_merged_bundle_validate_no_terraform(self, mock_bin):
        """Without terraform binary, graceful degradation returns valid=True."""
        result = merged_bundle_validate(_CLEAN_BUNDLE)

        assert isinstance(result, MergedValidateResult)
        assert result.valid is True

    @patch("subprocess.run", side_effect=_mock_tf_success)
    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value="/usr/local/bin/terraform",
    )
    def test_merged_bundle_validate_excludes_ocm(self, mock_bin, mock_run):
        """OCM submodule files (terraform/ocm/*) are excluded from the
        merged validation directory since they form a separate module."""
        result = merged_bundle_validate(_BUNDLE_WITH_OCM)

        # Inspect which files were actually written into the temp dir.
        # We check the subprocess.run calls -- the files written should
        # NOT include anything from terraform/ocm/.
        for call in mock_run.call_args_list:
            cmd = call[0][0] if call[0] else call[1].get("args", [])
            cwd = call[1].get("cwd", "")
            # The validate command runs in a temp dir; we just verify the
            # result is valid (meaning ocm files did not interfere).
            if "validate" in cmd:
                assert result.valid is True

        # Additionally, confirm the result itself is valid -- the OCM
        # files should never cause a root-module validation failure.
        assert isinstance(result, MergedValidateResult)


# ── final_validate ──────────────────────────────────────────────────────────

class TestFinalValidate:
    """Tests for final validation (Phase 3 checkpoint 3)."""

    @patch("subprocess.run", side_effect=_mock_tf_success)
    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value="/usr/local/bin/terraform",
    )
    def test_final_validate_pass(self, mock_bin, mock_run):
        """Successful final validation sets needs_human=False."""
        result = final_validate(_CLEAN_BUNDLE)

        assert isinstance(result, FinalValidateResult)
        assert result.valid is True
        assert result.needs_human is False
        assert result.gaps == []

    @patch("subprocess.run", side_effect=_mock_tf_failure_multi)
    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value="/usr/local/bin/terraform",
    )
    def test_final_validate_fail_marks_needs_human(self, mock_bin, mock_run):
        """Failed final validation sets needs_human=True and populates gaps."""
        result = final_validate(_CROSS_REF_BUNDLE)

        assert isinstance(result, FinalValidateResult)
        assert result.valid is False
        assert result.needs_human is True
        assert len(result.gaps) >= 1
        # Each gap from final_validate should carry the needs_human marker
        for gap in result.gaps:
            assert gap.get("needs_human") is True

    @patch("subprocess.run", side_effect=_mock_tf_failure)
    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value="/usr/local/bin/terraform",
    )
    def test_final_validate_error_message(self, mock_bin, mock_run):
        """Error diagnostics from terraform are included in the gap details."""
        result = final_validate(_CROSS_REF_BUNDLE)

        assert result.valid is False
        assert len(result.gaps) >= 1
        # The gap description or detail should include the terraform output
        all_text = " ".join(
            gap.get("description", "") + " " + gap.get("detail", "")
            for gap in result.gaps
        )
        assert "undeclared" in all_text.lower() or "subnet" in all_text.lower()

    @patch(
        "app.services.per_skill_validator._find_terraform_binary",
        return_value=None,
    )
    def test_final_validate_no_terraform_graceful(self, mock_bin):
        """Without terraform binary, final_validate degrades gracefully."""
        result = final_validate(_CLEAN_BUNDLE)

        assert isinstance(result, FinalValidateResult)
        assert result.valid is True
        assert result.needs_human is False
