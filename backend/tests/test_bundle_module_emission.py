"""Tests for OCM child-module emission in bundle_builder."""
import pytest
from app.services.bundle_builder import build_hybrid_bundle


class TestOcmModuleEmission:
    """Verify terraform/modules.tf is emitted when OCM artifacts are present."""

    def test_modules_tf_emitted_with_ocm_artifacts(self):
        """When ocm_handoff_translation artifacts exist, modules.tf should appear."""
        artifacts = {
            "synthesis/network.tf": (
                'resource "oci_core_vcn" "main" {\n'
                '  compartment_id = var.compartment_id\n'
                '}\n'
                'resource "oci_core_subnet" "private" {\n'
                '  vcn_id = oci_core_vcn.main.id\n'
                '}\n'
                '# cross-ref: oci_core_subnet.private.id\n'
            ),
            "synthesis/compute.tf": 'resource "oci_core_instance" "web" {}',
            "ocm_handoff_translation/main.tf": 'resource "oci_cloud_migrations_migration" "main" {}',
            "ocm_handoff_translation/variables.tf": 'variable "compartment_id" {}',
        }
        result = build_hybrid_bundle(
            artifacts,
            migration_name="test-mig",
            resource_count=5,
            skills_ran=["network_translation", "ocm_handoff_translation"],
        )
        assert "terraform/modules.tf" in result
        content = result["terraform/modules.tf"]
        assert 'module "ocm"' in content
        assert 'source' in content and '"./ocm"' in content
        assert "oci_core_vcn.main.id" in content
        assert "oci_core_subnet.private.id" in content

    def test_modules_tf_not_emitted_without_ocm(self):
        """When no OCM artifacts exist, modules.tf should NOT appear."""
        artifacts = {
            "synthesis/network.tf": 'resource "oci_core_vcn" "main" {}',
            "synthesis/compute.tf": 'resource "oci_core_instance" "web" {}',
        }
        result = build_hybrid_bundle(
            artifacts,
            migration_name="test-mig",
            resource_count=3,
        )
        assert "terraform/modules.tf" not in result

    def test_modules_tf_falls_back_to_free_vars(self):
        """When no VCN/subnet in synthesis, module should use var references."""
        artifacts = {
            "synthesis/compute.tf": 'resource "oci_core_instance" "web" {}',
            "ocm_handoff_translation/main.tf": 'resource "oci_cloud_migrations_migration" "main" {}',
        }
        result = build_hybrid_bundle(
            artifacts,
            migration_name="test-mig",
            resource_count=2,
            skills_ran=["ocm_handoff_translation"],
        )
        assert "terraform/modules.tf" in result
        content = result["terraform/modules.tf"]
        assert "var.target_vcn_ocid" in content
        assert "var.target_subnet_ocid" in content
        # Should NOT contain resource references
        assert "oci_core_vcn.main.id" not in content
        # Gaps report should contain a warning
        assert "reports/gaps.md" in result
        assert "OCM module wired to free var" in result["reports/gaps.md"]
