"""Phase 4: invalid spec JSON -> template renderer rejects -> error captured.

Tests that the renderer and SkillGroup correctly reject malformed specs:
  1. Missing required fields trigger TemplateRenderError
  2. Invalid enum values trigger TemplateRenderError
  3. Constraint violations (min_length, ge) trigger TemplateRenderError
  4. Unknown template names trigger TemplateRenderError
  5. SkillGroup._process_structured_output captures errors in _render_error
"""

import pytest

from app.agents.skill_group import SKILL_SPECS, SkillGroup
from app.services.template_renderer import render_specs, TemplateRenderError


class TestInvalidSpecsCaughtByRenderer:
    """Renderer rejects malformed specs with clear errors."""

    def test_missing_required_compartment_id(self):
        """Instance without compartment_id fails schema validation."""
        specs = [{
            "template": "core/instance",
            "label": "bad",
            "params": {
                "display_name": "test",
                "shape": "VM.Standard.E5.Flex",
                "availability_domain": "AD-1",
                "source_details": {
                    "source_type": "image",
                    "source_id": "x",
                },
                "aws_source_id": "i-bad",
            },
        }]
        with pytest.raises(TemplateRenderError) as exc_info:
            render_specs(specs)
        assert "compartment_id" in str(exc_info.value).lower() or \
               "validation" in str(exc_info.value).lower()

    def test_missing_required_statements(self):
        """Policy without statements fails."""
        specs = [{
            "template": "identity/policy",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "name": "p",
                "description": "d",
                "aws_source_id": "x",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_empty_statements_list(self):
        """Policy with empty statements list fails min_length=1."""
        specs = [{
            "template": "identity/policy",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "name": "p",
                "description": "d",
                "statements": [],
                "aws_source_id": "x",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_invalid_vault_type(self):
        """Vault with invalid vault_type fails Literal validation."""
        specs = [{
            "template": "vault/vault",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "display_name": "v",
                "vault_type": "INVALID",
                "aws_source_id": "x",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_empty_subnet_ids(self):
        """Functions application with empty subnet_ids fails min_length=1."""
        specs = [{
            "template": "functions/application",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "display_name": "app",
                "subnet_ids": [],
                "aws_source_id": "x",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_unknown_template_name(self):
        """Spec referencing non-existent template fails."""
        specs = [{
            "template": "nonexistent/thing",
            "label": "bad",
            "params": {"foo": "bar"},
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_alarm_missing_destinations(self):
        """Metric alarm without destinations fails."""
        specs = [{
            "template": "observability/metric_alarm",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "display_name": "a",
                "metric_compartment_id": "var.c",
                "namespace": "ns",
                "query": "q > 0",
                "severity": "WARNING",
                "aws_source_id": "x",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_alarm_empty_destinations(self):
        """Metric alarm with empty destinations fails min_length=1."""
        specs = [{
            "template": "observability/metric_alarm",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "display_name": "a",
                "metric_compartment_id": "var.c",
                "namespace": "ns",
                "query": "q > 0",
                "severity": "WARNING",
                "destinations": [],
                "aws_source_id": "x",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_block_volume_size_below_minimum(self):
        """Block volume with size_in_gbs < 50 fails ge=50 constraint."""
        specs = [{
            "template": "core/block_volume",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "availability_domain": "AD-1",
                "display_name": "tiny",
                "size_in_gbs": 10,
                "aws_source_id": "vol-bad",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_invalid_attachment_type(self):
        """Block volume attachment with invalid type fails Literal validation."""
        specs = [{
            "template": "core/block_volume_attachment",
            "label": "bad",
            "params": {
                "instance_id": "oci_core_instance.x.id",
                "volume_id": "oci_core_volume.x.id",
                "attachment_type": "nvme",
                "aws_source_id": "att-bad",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_invalid_key_algorithm(self):
        """KMS key with unsupported algorithm fails Literal validation."""
        specs = [{
            "template": "vault/key",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "display_name": "k",
                "management_endpoint": "https://example.com",
                "key_shape": {"algorithm": "DES", "length": 8},
                "aws_source_id": "kms-bad",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_invalid_log_type(self):
        """Log with invalid log_type fails Literal validation."""
        specs = [{
            "template": "observability/log",
            "label": "bad",
            "params": {
                "log_group_id": "oci_logging_log_group.x.id",
                "display_name": "log",
                "log_type": "INVALID",
                "aws_source_id": "log-bad",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_instance_missing_source_details(self):
        """Instance without source_details fails (required field)."""
        specs = [{
            "template": "core/instance",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "availability_domain": "AD-1",
                "display_name": "test",
                "shape": "VM.Standard.E5.Flex",
                "aws_source_id": "i-bad",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_function_memory_below_minimum(self):
        """Function with memory_in_mbs < 128 fails ge=128 constraint."""
        specs = [{
            "template": "functions/function",
            "label": "bad",
            "params": {
                "application_id": "oci_functions_application.x.id",
                "display_name": "fn",
                "image": "iad.ocir.io/ns/repo:latest",
                "memory_in_mbs": 64,
                "aws_source_id": "fn-bad",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_missing_template_key(self):
        """Spec with empty template string fails."""
        specs = [{
            "template": "",
            "label": "bad",
            "params": {"compartment_id": "var.c"},
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_invalid_alarm_severity(self):
        """Metric alarm with invalid severity fails Literal validation."""
        specs = [{
            "template": "observability/metric_alarm",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "display_name": "a",
                "metric_compartment_id": "var.c",
                "namespace": "ns",
                "query": "q > 0",
                "severity": "FATAL",
                "destinations": ["oci_ons_notification_topic.x.id"],
                "aws_source_id": "x",
            },
        }]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)


class TestSkillGroupCapturesRenderErrors:
    """_process_structured_output captures errors instead of crashing."""

    @pytest.mark.parametrize("skill_type,bad_spec", [
        (
            "ec2_translation",
            {
                "template": "core/instance",
                "label": "bad",
                "params": {
                    "display_name": "no-compartment",
                    "shape": "VM.Standard.E5.Flex",
                    "availability_domain": "AD-1",
                    "aws_source_id": "i-bad",
                },
            },
        ),
        (
            "iam_translation",
            {
                "template": "identity/policy",
                "label": "bad",
                "params": {
                    "compartment_id": "var.c",
                    "name": "no-statements",
                    "description": "d",
                    "aws_source_id": "x",
                },
            },
        ),
        (
            "security_translation",
            {
                "template": "vault/vault",
                "label": "bad",
                "params": {
                    "compartment_id": "var.c",
                    "display_name": "v",
                    "vault_type": "INVALID",
                    "aws_source_id": "x",
                },
            },
        ),
        (
            "serverless_translation",
            {
                "template": "functions/application",
                "label": "bad",
                "params": {
                    "compartment_id": "var.c",
                    "display_name": "app",
                    "subnet_ids": [],
                    "aws_source_id": "x",
                },
            },
        ),
        (
            "observability_translation",
            {
                "template": "observability/metric_alarm",
                "label": "bad",
                "params": {
                    "compartment_id": "var.c",
                    "display_name": "a",
                    "metric_compartment_id": "var.c",
                    "namespace": "ns",
                    "query": "q",
                    "severity": "WARNING",
                    "aws_source_id": "x",
                },
            },
        ),
        (
            "storage_translation",
            {
                "template": "core/block_volume",
                "label": "bad",
                "params": {
                    "compartment_id": "var.c",
                    "availability_domain": "AD-1",
                    "display_name": "tiny",
                    "size_in_gbs": 5,
                    "aws_source_id": "vol-bad",
                },
            },
        ),
    ])
    def test_bad_spec_produces_render_error(self, skill_type, bad_spec):
        group = SkillGroup(SKILL_SPECS[skill_type])
        draft = {"specs": [bad_spec]}
        result = group._process_structured_output(draft)
        assert "_render_error" in result

    def test_no_specs_returns_draft_unchanged(self):
        """When no specs are extractable, draft passes through as-is."""
        group = SkillGroup(SKILL_SPECS["ec2_translation"])
        draft = {"raw": "Not parseable as specs"}
        result = group._process_structured_output(draft)
        assert result == draft

    def test_render_error_is_string(self):
        """The _render_error value is a human-readable string."""
        group = SkillGroup(SKILL_SPECS["iam_translation"])
        draft = {"specs": [{
            "template": "identity/policy",
            "label": "bad",
            "params": {
                "compartment_id": "var.c",
                "name": "p",
                "description": "d",
                "aws_source_id": "x",
            },
        }]}
        result = group._process_structured_output(draft)
        assert "_render_error" in result
        assert isinstance(result["_render_error"], str)
        assert len(result["_render_error"]) > 0
