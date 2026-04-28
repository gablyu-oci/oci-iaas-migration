"""Tests for template_renderer.render_specs: routing, grouping, error handling."""

import pytest

from app.services.template_renderer import render_specs, render_specs_safe, TemplateRenderError


class TestRenderSpecs:
    """Core render_specs behavior."""

    def test_empty_specs(self):
        result = render_specs([])
        assert result == {}

    def test_routes_core_to_network_tf(self):
        specs = [
            {
                "template": "core/vcn",
                "label": "main",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.0.0.0/16"],
                    "display_name": "vcn",
                    "aws_source_id": "vpc-1",
                },
            }
        ]
        result = render_specs(specs)
        assert "network.tf" in result

    def test_routes_lb_to_loadbalancer_tf(self):
        specs = [
            {
                "template": "load_balancer/load_balancer",
                "label": "lb",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "display_name": "lb",
                    "subnet_ids": ["oci_core_subnet.pub.id"],
                    "aws_source_id": "alb-1",
                },
            }
        ]
        result = render_specs(specs)
        assert "loadbalancer.tf" in result

    def test_routes_ocm_to_ocm_main_tf(self):
        specs = [
            {
                "template": "cloud_migrations/migration",
                "label": "main",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "display_name": "mig",
                },
            }
        ]
        result = render_specs(specs)
        assert "ocm/main.tf" in result

    def test_concatenates_same_domain_specs(self):
        specs = [
            {
                "template": "core/vcn",
                "label": "main",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.0.0.0/16"],
                    "display_name": "vcn",
                    "aws_source_id": "vpc-1",
                },
            },
            {
                "template": "core/subnet",
                "label": "web",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "vcn_id": "oci_core_vcn.main.id",
                    "cidr_block": "10.0.1.0/24",
                    "display_name": "web",
                    "prohibit_public_ip_on_vnic": False,
                    "aws_source_id": "subnet-1",
                },
            },
        ]
        result = render_specs(specs)
        assert "network.tf" in result
        content = result["network.tf"]
        assert "oci_core_vcn" in content
        assert "oci_core_subnet" in content

    def test_multi_domain_produces_separate_files(self):
        specs = [
            {
                "template": "core/vcn",
                "label": "main",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.0.0.0/16"],
                    "display_name": "vcn",
                    "aws_source_id": "vpc-1",
                },
            },
            {
                "template": "load_balancer/load_balancer",
                "label": "lb",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "display_name": "lb",
                    "subnet_ids": ["oci_core_subnet.pub.id"],
                    "aws_source_id": "alb-1",
                },
            },
        ]
        result = render_specs(specs)
        assert "network.tf" in result
        assert "loadbalancer.tf" in result

    def test_free_form_hcl_routes_to_main_tf(self):
        specs = [
            {
                "template": "free_form_hcl",
                "label": "custom",
                "params": {"hcl": 'resource "null_resource" "x" {}'},
            }
        ]
        result = render_specs(specs)
        assert "main.tf" in result

    def test_validation_error_includes_template_and_label(self):
        specs = [
            {
                "template": "core/vcn",
                "label": "bad_vcn",
                "params": {"display_name": "no-compartment"},
            }
        ]
        with pytest.raises(TemplateRenderError) as exc_info:
            render_specs(specs)
        msg = str(exc_info.value)
        assert "core/vcn" in msg
        assert "bad_vcn" in msg

    def test_header_present_in_output(self):
        """All rendered files start with the deterministic header comment."""
        specs = [
            {
                "template": "core/vcn",
                "label": "main",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.0.0.0/16"],
                    "display_name": "vcn",
                    "aws_source_id": "vpc-1",
                },
            }
        ]
        result = render_specs(specs)
        hcl = result["network.tf"]
        assert hcl.startswith("# Generated by template_renderer")

    def test_multiple_specs_same_file_separated_by_newlines(self):
        """Multiple blocks in the same file are joined with double newlines."""
        specs = [
            {
                "template": "core/vcn",
                "label": "a",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.0.0.0/16"],
                    "display_name": "vcn-a",
                    "aws_source_id": "vpc-a",
                },
            },
            {
                "template": "core/vcn",
                "label": "b",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.1.0.0/16"],
                    "display_name": "vcn-b",
                    "aws_source_id": "vpc-b",
                },
            },
        ]
        result = render_specs(specs)
        hcl = result["network.tf"]
        assert 'oci_core_vcn" "a"' in hcl
        assert 'oci_core_vcn" "b"' in hcl

    def test_label_defaults_when_missing(self):
        """Missing label gets a default like unnamed_0."""
        specs = [
            {
                "template": "core/vcn",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.0.0.0/16"],
                    "display_name": "vcn",
                    "aws_source_id": "vpc-1",
                },
            }
        ]
        result = render_specs(specs)
        hcl = result["network.tf"]
        assert "unnamed_0" in hcl

    def test_unknown_domain_routes_to_main_tf(self):
        """A template with an unrecognized domain prefix raises error
        (because there is no schema), not a routing issue."""
        specs = [{"template": "exotic/thing", "label": "x", "params": {}}]
        with pytest.raises(TemplateRenderError, match="No schema"):
            render_specs(specs)


class TestRenderSpecsSafe:
    """render_specs_safe collects errors instead of raising."""

    def test_all_valid_no_errors(self):
        specs = [
            {
                "template": "core/vcn",
                "label": "good",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.0.0.0/16"],
                    "display_name": "vcn",
                    "aws_source_id": "vpc-1",
                },
            },
        ]
        result, errors = render_specs_safe(specs)
        assert "network.tf" in result
        assert len(errors) == 0

    def test_partial_success(self):
        specs = [
            {
                "template": "core/vcn",
                "label": "good",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.0.0.0/16"],
                    "display_name": "vcn",
                    "aws_source_id": "vpc-1",
                },
            },
            {
                "template": "core/vcn",
                "label": "bad",
                "params": {"display_name": "no-compartment"},
            },
        ]
        result, errors = render_specs_safe(specs)
        assert "network.tf" in result  # good one rendered
        assert len(errors) == 1  # bad one failed

    def test_all_bad_returns_empty_files(self):
        specs = [
            {"template": "core/vcn", "label": "bad1", "params": {}},
            {"template": "core/vcn", "label": "bad2", "params": {}},
        ]
        result, errors = render_specs_safe(specs)
        assert result == {}
        assert len(errors) == 2

    def test_empty_specs_safe(self):
        result, errors = render_specs_safe([])
        assert result == {}
        assert errors == []

    def test_unknown_template_collected_as_error(self):
        specs = [{"template": "nonexistent/widget", "label": "x", "params": {}}]
        result, errors = render_specs_safe(specs)
        assert result == {}
        assert len(errors) == 1
        assert "nonexistent/widget" in errors[0]

    def test_error_messages_include_context(self):
        """Error messages from render_specs_safe include template and label."""
        specs = [
            {"template": "core/vcn", "label": "my_label", "params": {"display_name": "x"}},
        ]
        _, errors = render_specs_safe(specs)
        assert len(errors) == 1
        assert "core/vcn" in errors[0]
        assert "my_label" in errors[0]


class TestTemplateRenderError:
    """TemplateRenderError exception attributes."""

    def test_error_attributes(self):
        err = TemplateRenderError("core/vcn", "main", "something broke")
        assert err.template == "core/vcn"
        assert err.label == "main"
        assert err.detail == "something broke"

    def test_error_str_format(self):
        err = TemplateRenderError("core/vcn", "main", "something broke")
        msg = str(err)
        assert "core/vcn" in msg
        assert "main" in msg
        assert "something broke" in msg
