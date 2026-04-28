"""Tests for bundle_builder graph integration: find_by_template replaces regex."""

import pytest

from app.services.bundle_builder import build_hybrid_bundle
from app.services.resource_graph import ResourceGraph, ResourceNode


# ── Helpers ────────────────────────────────────────────────────────────────

def _vcn_node(label: str = "main") -> ResourceNode:
    return ResourceNode(
        template="core/vcn",
        label=label,
        params={"compartment_id": "var.compartment_id"},
        source_skill="network_translation",
        domain="network",
    )


def _subnet_node(label: str = "web") -> ResourceNode:
    return ResourceNode(
        template="core/subnet",
        label=label,
        params={"compartment_id": "var.compartment_id"},
        source_skill="network_translation",
        domain="network",
    )


def _ocm_artifacts() -> dict[str, str]:
    """Minimal completed_artifacts that trigger OCM module wiring."""
    return {
        "synthesis/network.tf": (
            'resource "oci_core_vcn" "ignored_by_graph" {\n'
            '  compartment_id = var.compartment_id\n'
            '}\n'
            'resource "oci_core_subnet" "also_ignored" {\n'
            '  vcn_id = oci_core_vcn.ignored_by_graph.id\n'
            '}\n'
        ),
        "synthesis/compute.tf": 'resource "oci_core_instance" "web" {}',
        "ocm_handoff_translation/main.tf": (
            'resource "oci_cloud_migrations_migration" "main" {}\n'
        ),
        "ocm_handoff_translation/variables.tf": 'variable "compartment_id" {}',
    }


# ── Graph-based label lookup ──────────────────────────────────────────────

class TestBundleBuilderWithGraph:
    """When graph is provided, bundle_builder uses graph.find_by_template."""

    def test_modules_tf_uses_graph_vcn_label(self):
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="my_custom_vcn"))
        graph.add_node(_subnet_node(label="my_private_subnet"))

        result = build_hybrid_bundle(
            _ocm_artifacts(),
            migration_name="test-mig",
            resource_count=5,
            skills_ran=["network_translation", "ocm_handoff_translation"],
            graph=graph,
        )
        assert "terraform/modules.tf" in result
        content = result["terraform/modules.tf"]
        assert "oci_core_vcn.my_custom_vcn.id" in content

    def test_modules_tf_uses_graph_subnet_label(self):
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="my_custom_vcn"))
        graph.add_node(_subnet_node(label="my_private_subnet"))

        result = build_hybrid_bundle(
            _ocm_artifacts(),
            migration_name="test-mig",
            resource_count=5,
            skills_ran=["network_translation", "ocm_handoff_translation"],
            graph=graph,
        )
        content = result["terraform/modules.tf"]
        assert "oci_core_subnet.my_private_subnet.id" in content

    def test_graph_labels_override_regex_parsed_labels(self):
        """The graph label (my_custom_vcn) should appear, NOT the regex-parsed
        label from network.tf (ignored_by_graph)."""
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="my_custom_vcn"))
        graph.add_node(_subnet_node(label="my_private_subnet"))

        result = build_hybrid_bundle(
            _ocm_artifacts(),
            migration_name="test-mig",
            resource_count=5,
            skills_ran=["network_translation", "ocm_handoff_translation"],
            graph=graph,
        )
        content = result["terraform/modules.tf"]
        # Graph labels must be used
        assert "my_custom_vcn" in content
        # Regex-parsed labels from artifacts must NOT appear
        assert "ignored_by_graph" not in content
        assert "also_ignored" not in content

    def test_non_default_vcn_label_proves_no_regex(self):
        """Use a VCN label that would never appear in the artifacts to prove
        the graph path is used, not regex."""
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="zebra_vpc_network"))
        graph.add_node(_subnet_node(label="alpha_private_subnet"))

        result = build_hybrid_bundle(
            _ocm_artifacts(),
            migration_name="test-mig",
            resource_count=5,
            skills_ran=["network_translation", "ocm_handoff_translation"],
            graph=graph,
        )
        content = result["terraform/modules.tf"]
        assert "oci_core_vcn.zebra_vpc_network.id" in content
        assert "oci_core_subnet.alpha_private_subnet.id" in content

    def test_graph_prefers_private_subnet(self):
        """When multiple subnets exist, one with 'private' in the label wins."""
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="main"))
        graph.add_node(_subnet_node(label="public_subnet_1"))
        graph.add_node(_subnet_node(label="private_subnet_1"))

        result = build_hybrid_bundle(
            _ocm_artifacts(),
            migration_name="test-mig",
            resource_count=5,
            skills_ran=["network_translation", "ocm_handoff_translation"],
            graph=graph,
        )
        content = result["terraform/modules.tf"]
        assert "oci_core_subnet.private_subnet_1.id" in content


# ── Regex fallback when graph is None ─────────────────────────────────────

class TestBundleBuilderRegexFallback:
    """When graph is None, fall back to regex parsing of network.tf."""

    def test_fallback_parses_vcn_from_artifacts(self):
        result = build_hybrid_bundle(
            _ocm_artifacts(),
            migration_name="test-mig",
            resource_count=5,
            skills_ran=["network_translation", "ocm_handoff_translation"],
            graph=None,
        )
        content = result["terraform/modules.tf"]
        # Should use the regex-parsed label from the artifact HCL
        assert "oci_core_vcn.ignored_by_graph.id" in content

    def test_fallback_parses_subnet_from_artifacts(self):
        result = build_hybrid_bundle(
            _ocm_artifacts(),
            migration_name="test-mig",
            resource_count=5,
            skills_ran=["network_translation", "ocm_handoff_translation"],
            graph=None,
        )
        content = result["terraform/modules.tf"]
        assert "oci_core_subnet.also_ignored.id" in content

    def test_no_vcn_no_subnet_falls_back_to_free_vars(self):
        """When no VCN or subnet found at all, fall back to var references."""
        artifacts = {
            "synthesis/compute.tf": 'resource "oci_core_instance" "web" {}',
            "ocm_handoff_translation/main.tf": (
                'resource "oci_cloud_migrations_migration" "main" {}\n'
            ),
        }
        result = build_hybrid_bundle(
            artifacts,
            migration_name="test-mig",
            resource_count=2,
            skills_ran=["ocm_handoff_translation"],
            graph=None,
        )
        content = result["terraform/modules.tf"]
        assert "var.target_vcn_ocid" in content
        assert "var.target_subnet_ocid" in content


# ── Graph with no VCN/subnet ──────────────────────────────────────────────

class TestBundleBuilderGraphNoNetwork:
    """When graph is provided but has no VCN/subnet nodes."""

    def test_graph_without_vcn_falls_back_to_free_vars(self):
        graph = ResourceGraph()
        # Graph has no network nodes at all
        artifacts = {
            "synthesis/compute.tf": 'resource "oci_core_instance" "web" {}',
            "ocm_handoff_translation/main.tf": (
                'resource "oci_cloud_migrations_migration" "main" {}\n'
            ),
        }
        result = build_hybrid_bundle(
            artifacts,
            migration_name="test-mig",
            resource_count=2,
            skills_ran=["ocm_handoff_translation"],
            graph=graph,
        )
        content = result["terraform/modules.tf"]
        assert "var.target_vcn_ocid" in content
        assert "var.target_subnet_ocid" in content

    def test_graph_with_vcn_but_no_subnet_falls_back(self):
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="lonely_vcn"))
        # No subnet node

        artifacts = {
            "synthesis/network.tf": 'resource "oci_core_vcn" "x" {}',
            "ocm_handoff_translation/main.tf": (
                'resource "oci_cloud_migrations_migration" "main" {}\n'
            ),
            "ocm_handoff_translation/variables.tf": 'variable "compartment_id" {}',
        }
        result = build_hybrid_bundle(
            artifacts,
            migration_name="test-mig",
            resource_count=2,
            skills_ran=["ocm_handoff_translation"],
            graph=graph,
        )
        content = result["terraform/modules.tf"]
        # Both must be present to wire; without subnet it falls back
        assert "var.target_vcn_ocid" in content
        assert "var.target_subnet_ocid" in content
