"""Tests for bundle_builder OCM-module VCN/subnet auto-wiring."""
import pytest
from app.services.bundle_builder import build_hybrid_bundle


class TestBundleBuilderVcnWire:
    """Verify modules.tf wires to actual VCN/subnet labels from network.tf."""

    def test_custom_vcn_and_private_subnet_labels(self):
        """Custom labels like multi_tier_vpc_vpc and private_subnet_1 are wired correctly."""
        artifacts = {
            "synthesis/network.tf": (
                'resource "oci_core_vcn" "foo_vcn" {\n'
                '  compartment_id = var.compartment_id\n'
                '  cidr_blocks    = ["10.0.0.0/16"]\n'
                '}\n'
                'resource "oci_core_subnet" "public_subnet_1" {\n'
                '  vcn_id = oci_core_vcn.foo_vcn.id\n'
                '}\n'
                'resource "oci_core_subnet" "private_subnet_1" {\n'
                '  vcn_id = oci_core_vcn.foo_vcn.id\n'
                '}\n'
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
        assert "oci_core_vcn.foo_vcn.id" in content
        assert "oci_core_subnet.private_subnet_1.id" in content
        # Should NOT contain free variable fallback
        assert "var.target_vcn_ocid" not in content

    def test_no_private_subnet_falls_back_to_first_subnet(self):
        """When no subnet label contains 'private', the first subnet is used."""
        artifacts = {
            "synthesis/network.tf": (
                'resource "oci_core_vcn" "my_vcn" {\n'
                '  compartment_id = var.compartment_id\n'
                '}\n'
                'resource "oci_core_subnet" "web_subnet" {\n'
                '  vcn_id = oci_core_vcn.my_vcn.id\n'
                '}\n'
                'resource "oci_core_subnet" "db_subnet" {\n'
                '  vcn_id = oci_core_vcn.my_vcn.id\n'
                '}\n'
            ),
            "ocm_handoff_translation/main.tf": 'resource "oci_cloud_migrations_migration" "main" {}',
            "ocm_handoff_translation/variables.tf": 'variable "compartment_id" {}',
        }
        result = build_hybrid_bundle(
            artifacts,
            migration_name="test-mig",
            resource_count=3,
            skills_ran=["network_translation", "ocm_handoff_translation"],
        )
        content = result["terraform/modules.tf"]
        assert "oci_core_vcn.my_vcn.id" in content
        assert "oci_core_subnet.web_subnet.id" in content

    def test_no_vcn_falls_back_to_free_vars(self):
        """When network.tf has no VCN, fall back to var references."""
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
        content = result["terraform/modules.tf"]
        assert "var.target_vcn_ocid" in content
        assert "var.target_subnet_ocid" in content
        # Should have a gap warning
        assert "OCM module wired to free var" in result.get("reports/gaps.md", "")

    def test_vcn_without_subnet_falls_back_to_free_vars(self):
        """When network.tf has VCN but no subnet, fall back to var references."""
        artifacts = {
            "synthesis/network.tf": 'resource "oci_core_vcn" "main" { compartment_id = var.compartment_id }\n',
            "ocm_handoff_translation/main.tf": 'resource "oci_cloud_migrations_migration" "main" {}',
            "ocm_handoff_translation/variables.tf": 'variable "compartment_id" {}',
        }
        result = build_hybrid_bundle(
            artifacts,
            migration_name="test-mig",
            resource_count=2,
            skills_ran=["ocm_handoff_translation"],
        )
        content = result["terraform/modules.tf"]
        assert "var.target_vcn_ocid" in content
        assert "var.target_subnet_ocid" in content
