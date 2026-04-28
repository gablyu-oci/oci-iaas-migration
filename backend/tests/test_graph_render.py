"""Tests for ResourceGraph.render(): template rendering, ref injection, domain grouping."""

import pytest

from app.services.resource_graph import ResourceGraph, ResourceNode


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
            "vcn_id": "PLACEHOLDER",
            "cidr_block": "10.0.1.0/24",
            "display_name": "test-subnet",
            "aws_source_id": "subnet-test1",
        },
        source_skill="network_translation",
        domain="network",
    )


# ── Ref injection ─────────────────────────────────────────────────────────

class TestGraphRenderWithRefs:
    """Render a graph containing cross-resource references."""

    def test_ref_resolves_to_terraform_expression(self):
        """A subnet's vcn_id ref to a VCN should render as
        oci_core_vcn.<label>.id in the output HCL."""
        graph = ResourceGraph()
        vcn_id = graph.add_node(_vcn_node(label="main"))
        sub_id = graph.add_node(_subnet_node(label="web"))
        graph.add_ref(sub_id, "vcn_id", vcn_id, dst_attr="id")

        rendered = graph.render()
        # The subnet's vcn_id should contain a terraform reference
        assert "network.tf" in rendered
        hcl = rendered["network.tf"]
        assert "oci_core_vcn.main.id" in hcl

    def test_ref_replaces_placeholder_in_vcn_id(self):
        """The subnet's vcn_id param (originally 'PLACEHOLDER') should be
        replaced by the terraform reference expression, not a literal string."""
        graph = ResourceGraph()
        vcn_id = graph.add_node(_vcn_node(label="main"))
        sub_id = graph.add_node(_subnet_node(label="web"))
        graph.add_ref(sub_id, "vcn_id", vcn_id)

        rendered = graph.render()
        hcl = rendered["network.tf"]
        # The subnet block's vcn_id line should use the terraform ref
        subnet_start = hcl.find('oci_core_subnet')
        assert subnet_start != -1, "subnet resource not found in rendered HCL"
        subnet_block = hcl[subnet_start:]
        # vcn_id should be the terraform ref, not the original PLACEHOLDER
        assert "oci_core_vcn.main.id" in subnet_block
        # The vcn_id line specifically should NOT contain PLACEHOLDER
        for line in subnet_block.splitlines():
            if "vcn_id" in line and "freeform" not in line.lower():
                assert "PLACEHOLDER" not in line, (
                    f"vcn_id line still contains PLACEHOLDER: {line}"
                )

    def test_custom_dst_attr_in_expression(self):
        """dst_attr other than 'id' should appear in the terraform expression."""
        graph = ResourceGraph()
        vcn_id = graph.add_node(_vcn_node(label="primary"))
        sub_id = graph.add_node(_subnet_node(label="app"))
        graph.add_ref(sub_id, "vcn_id", vcn_id, dst_attr="display_name")

        rendered = graph.render()
        hcl = rendered["network.tf"]
        assert "oci_core_vcn.primary.display_name" in hcl


# ── Domain grouping ───────────────────────────────────────────────────────

class TestGraphRenderDomainGrouping:
    """Output files are grouped by domain."""

    def test_network_nodes_land_in_network_tf(self):
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="main"))
        rendered = graph.render()
        assert "network.tf" in rendered
        assert "oci_core_vcn" in rendered["network.tf"]

    def test_both_vcn_and_subnet_in_network_tf(self):
        graph = ResourceGraph()
        vcn_id = graph.add_node(_vcn_node(label="main"))
        sub_id = graph.add_node(_subnet_node(label="web"))
        graph.add_ref(sub_id, "vcn_id", vcn_id)

        rendered = graph.render()
        assert "network.tf" in rendered
        hcl = rendered["network.tf"]
        assert "oci_core_vcn" in hcl
        assert "oci_core_subnet" in hcl


# ── Free-form files ───────────────────────────────────────────────────────

class TestGraphRenderFreeForm:
    """Free-form files pass through unchanged."""

    def test_free_form_file_passthrough(self):
        graph = ResourceGraph()
        graph.free_form_files["custom/extras.tf"] = (
            'resource "null_resource" "hook" {\n'
            '  triggers = { always = timestamp() }\n'
            '}\n'
        )
        rendered = graph.render()
        assert "custom/extras.tf" in rendered
        assert "null_resource" in rendered["custom/extras.tf"]

    def test_free_form_appended_to_existing_domain_file(self):
        """If a free-form file targets the same filename as a rendered domain,
        content is appended."""
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="main"))
        graph.free_form_files["network.tf"] = (
            '# Extra network config\n'
            'resource "oci_core_drg" "hub" {\n'
            '  compartment_id = var.compartment_id\n'
            '}\n'
        )
        rendered = graph.render()
        hcl = rendered["network.tf"]
        # Both graph-rendered VCN and free-form DRG should be present
        assert "oci_core_vcn" in hcl
        assert "oci_core_drg" in hcl

    def test_free_form_only_graph(self):
        """A graph with no nodes but free-form files still produces output."""
        graph = ResourceGraph()
        graph.free_form_files["extras.tf"] = 'resource "null_resource" "x" {}\n'
        rendered = graph.render()
        assert "extras.tf" in rendered


# ── No-ref rendering ──────────────────────────────────────────────────────

class TestGraphRenderNoRefs:
    """A graph with no refs renders cleanly."""

    def test_no_refs_renders_without_error(self):
        graph = ResourceGraph()
        graph.add_node(_vcn_node(label="standalone"))
        rendered = graph.render()
        assert "network.tf" in rendered
        hcl = rendered["network.tf"]
        assert "oci_core_vcn" in hcl
        assert 'standalone' in hcl

    def test_empty_graph_renders_empty(self):
        graph = ResourceGraph()
        rendered = graph.render()
        assert rendered == {}
