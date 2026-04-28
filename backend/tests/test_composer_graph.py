"""Tests for compose_from_graph: graph-based Terraform synthesis."""

import pytest

from app.services.resource_graph import ResourceGraph, ResourceNode
from app.services.synthesis_composer import compose_from_graph, CANONICAL_ROOT_VARS


# ── Helpers ────────────────────────────────────────────────────────────────

def _vcn_node(label: str = "main") -> ResourceNode:
    return ResourceNode(
        template="core/vcn",
        label=label,
        params={
            "compartment_id": "var.compartment_id",
            "cidr_blocks": ["10.0.0.0/16"],
            "display_name": "test-vcn",
            "aws_source_id": "vpc-test1",
        },
        source_skill="network_translation",
        domain="network",
    )


def _subnet_node(label: str = "web") -> ResourceNode:
    return ResourceNode(
        template="core/subnet",
        label=label,
        params={
            "compartment_id": "var.compartment_id",
            "vcn_id": "oci_core_vcn.main.id",
            "cidr_block": "10.0.1.0/24",
            "display_name": "test-subnet",
            "aws_source_id": "subnet-test1",
        },
        source_skill="network_translation",
        domain="network",
    )


def _build_graph_with_vcn_subnet() -> ResourceGraph:
    """Build a small graph: VCN + subnet in network domain."""
    graph = ResourceGraph()
    vcn_id = graph.add_node(_vcn_node(label="main"))
    sub_id = graph.add_node(_subnet_node(label="web"))
    graph.add_ref(sub_id, "vcn_id", vcn_id)
    return graph


# ── Core compose_from_graph tests ─────────────────────────────────────────

class TestComposeFromGraph:
    """compose_from_graph produces a valid SynthesisResult."""

    def test_network_tf_contains_vcn_and_subnet(self):
        graph = _build_graph_with_vcn_subnet()
        result = compose_from_graph(graph, "test-migration")
        assert "network.tf" in result.files
        hcl = result.files["network.tf"]
        assert "oci_core_vcn" in hcl
        assert "oci_core_subnet" in hcl

    def test_providers_tf_present(self):
        graph = _build_graph_with_vcn_subnet()
        result = compose_from_graph(graph, "test-migration")
        assert "providers.tf" in result.files
        providers = result.files["providers.tf"]
        assert "oracle/oci" in providers
        assert "test-migration" in providers

    def test_variables_tf_has_canonical_root_vars(self):
        graph = _build_graph_with_vcn_subnet()
        result = compose_from_graph(graph, "test-migration")
        assert "variables.tf" in result.files
        variables = result.files["variables.tf"]
        for var_def in CANONICAL_ROOT_VARS:
            assert var_def["name"] in variables, (
                f"Canonical variable '{var_def['name']}' missing from variables.tf"
            )

    def test_skills_included_tracks_graph_skills(self):
        graph = _build_graph_with_vcn_subnet()
        result = compose_from_graph(graph, "test-migration")
        assert "network_translation" in result.skills_included

    def test_migration_name_in_providers(self):
        graph = _build_graph_with_vcn_subnet()
        result = compose_from_graph(graph, "my-cool-migration")
        assert "my-cool-migration" in result.files["providers.tf"]


# ── Free-form file merging ────────────────────────────────────────────────

class TestComposeFromGraphFreeForm:
    """Free-form files from graph.free_form_files are merged correctly."""

    def test_free_form_content_appears_in_result(self):
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="main"))
        graph.free_form_files["ec2_translation/main.tf"] = (
            'resource "oci_core_instance" "web_server" {\n'
            '  compartment_id = var.compartment_id\n'
            '  display_name   = "web-server"\n'
            '  shape          = "VM.Standard.E4.Flex"\n'
            '}\n'
        )
        result = compose_from_graph(graph, "test-migration")
        # The ec2_translation skill maps to compute.tf in the composer
        assert "compute.tf" in result.files
        assert "oci_core_instance" in result.files["compute.tf"]

    def test_free_form_does_not_clobber_graph_rendered(self):
        """When free-form targets the same concern as graph nodes, both appear."""
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="main"))
        # Free-form that also targets network (unlikely but possible)
        graph.free_form_files["network_translation/main.tf"] = (
            'resource "oci_core_drg" "hub_drg" {\n'
            '  compartment_id = var.compartment_id\n'
            '  display_name   = "hub"\n'
            '}\n'
        )
        result = compose_from_graph(graph, "test-migration")
        net_hcl = result.files["network.tf"]
        # Graph-rendered VCN should still be present
        assert "oci_core_vcn" in net_hcl
        # Free-form DRG should also be present
        assert "oci_core_drg" in net_hcl

    def test_free_form_skill_tracked_in_skills_included(self):
        graph = ResourceGraph()
        graph.free_form_files["ec2_translation/main.tf"] = (
            'resource "oci_core_instance" "app" {\n'
            '  compartment_id = var.compartment_id\n'
            '  display_name   = "app"\n'
            '  shape          = "VM.Standard.E4.Flex"\n'
            '}\n'
        )
        result = compose_from_graph(graph, "test-migration")
        assert "ec2_translation" in result.skills_included


# ── Empty / edge cases ────────────────────────────────────────────────────

class TestComposeFromGraphEdgeCases:
    """Edge cases for compose_from_graph."""

    def test_empty_graph_still_produces_providers_and_variables(self):
        graph = ResourceGraph()
        result = compose_from_graph(graph, "empty-mig")
        assert "providers.tf" in result.files
        assert "variables.tf" in result.files

    def test_graph_with_only_free_form(self):
        graph = ResourceGraph()
        graph.free_form_files["ec2_translation/main.tf"] = (
            'resource "oci_core_instance" "solo" {\n'
            '  compartment_id = var.compartment_id\n'
            '  display_name   = "solo"\n'
            '  shape          = "VM.Standard.E4.Flex"\n'
            '}\n'
        )
        result = compose_from_graph(graph, "ff-only")
        assert "compute.tf" in result.files
        assert "providers.tf" in result.files
