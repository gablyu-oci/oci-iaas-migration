"""Integration: mock writer emits structured specs -> renderer produces HCL.

Tests the SkillGroup structured output pipeline without calling any LLM:
  1. STRUCTURED_OUTPUT_SKILLS membership
  2. _extract_specs_from_draft normalization
  3. _process_structured_output rendering + metadata preservation
  4. Error propagation from bad specs
"""

import json
import pytest

from app.agents.skill_group import (
    SKILL_SPECS,
    STRUCTURED_OUTPUT_SKILLS,
    SkillGroup,
)


class TestSkillGroupStructuredOutput:
    """SkillGroup structured output integration."""

    def test_structured_output_skills_defined(self):
        assert "network_translation" in STRUCTURED_OUTPUT_SKILLS
        assert "ocm_handoff_translation" in STRUCTURED_OUTPUT_SKILLS
        assert "loadbalancer_translation" in STRUCTURED_OUTPUT_SKILLS

    def test_structured_output_skills_count(self):
        """Phase 1 + Phase 4 gives exactly 9 structured output skills."""
        assert len(STRUCTURED_OUTPUT_SKILLS) == 9

    def test_non_structured_skills_unchanged(self):
        assert "database_translation" not in STRUCTURED_OUTPUT_SKILLS

    def test_all_structured_skills_have_specs(self):
        """Every STRUCTURED_OUTPUT_SKILLS entry has a SKILL_SPECS entry."""
        for skill in STRUCTURED_OUTPUT_SKILLS:
            assert skill in SKILL_SPECS, f"{skill} missing from SKILL_SPECS"


class TestExtractSpecsFromDraft:
    """SkillGroup._extract_specs_from_draft handles various writer output shapes."""

    def test_extract_specs_from_dict_with_specs_key(self):
        draft = {
            "specs": [
                {"template": "core/vcn", "label": "main", "params": {"compartment_id": "var.c"}}
            ]
        }
        specs = SkillGroup._extract_specs_from_draft(draft)
        assert len(specs) == 1
        assert specs[0]["template"] == "core/vcn"

    def test_extract_specs_from_resources_key(self):
        draft = {
            "resources": [
                {"template": "core/vcn", "label": "main", "params": {}}
            ]
        }
        specs = SkillGroup._extract_specs_from_draft(draft)
        assert len(specs) == 1

    def test_extract_specs_from_list(self):
        draft = [{"template": "core/vcn", "label": "main", "params": {}}]
        specs = SkillGroup._extract_specs_from_draft(draft)
        assert len(specs) == 1

    def test_extract_specs_from_single_spec(self):
        draft = {"template": "core/vcn", "label": "main", "params": {}}
        specs = SkillGroup._extract_specs_from_draft(draft)
        assert len(specs) == 1
        assert specs[0]["template"] == "core/vcn"

    def test_extract_specs_from_raw_json_string(self):
        """raw key containing a JSON string of a list."""
        inner = [{"template": "core/vcn", "label": "x", "params": {}}]
        draft = {"raw": json.dumps(inner)}
        specs = SkillGroup._extract_specs_from_draft(draft)
        assert len(specs) == 1

    def test_extract_specs_from_raw_non_json(self):
        """raw key with non-JSON text returns empty."""
        draft = {"raw": "This is not JSON"}
        specs = SkillGroup._extract_specs_from_draft(draft)
        assert specs == []

    def test_extract_specs_empty_draft(self):
        draft = {"some_other_key": "value"}
        specs = SkillGroup._extract_specs_from_draft(draft)
        assert specs == []

    def test_extract_specs_empty_specs_list(self):
        draft = {"specs": []}
        specs = SkillGroup._extract_specs_from_draft(draft)
        assert specs == []

    def test_extract_specs_specs_key_not_list(self):
        """specs key present but not a list -- should not extract."""
        draft = {"specs": "not a list"}
        specs = SkillGroup._extract_specs_from_draft(draft)
        assert specs == []

    def test_extract_specs_multiple_items(self):
        """Multiple specs are all extracted."""
        draft = {
            "specs": [
                {"template": "core/vcn", "label": "a", "params": {}},
                {"template": "core/subnet", "label": "b", "params": {}},
                {"template": "core/internet_gateway", "label": "c", "params": {}},
            ]
        }
        specs = SkillGroup._extract_specs_from_draft(draft)
        assert len(specs) == 3


class TestProcessStructuredOutput:
    """_process_structured_output renders specs to HCL via the template engine."""

    def _make_group(self, skill_type: str) -> SkillGroup:
        return SkillGroup(SKILL_SPECS[skill_type])

    def test_network_renders_vcn(self):
        group = self._make_group("network_translation")
        draft = {
            "specs": [
                {
                    "template": "core/vcn",
                    "label": "main",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "cidr_blocks": ["10.0.0.0/16"],
                        "display_name": "test-vcn",
                        "aws_source_id": "vpc-12345",
                    },
                }
            ]
        }
        result = group._process_structured_output(draft)
        assert "network.tf" in result
        assert "oci_core_vcn" in result["network.tf"]
        assert "_template_specs" in result

    def test_network_renders_vcn_and_subnet_together(self):
        """Multiple core resources land in the same network.tf."""
        group = self._make_group("network_translation")
        draft = {
            "specs": [
                {
                    "template": "core/vcn",
                    "label": "main",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "cidr_blocks": ["10.0.0.0/16"],
                        "display_name": "test-vcn",
                        "aws_source_id": "vpc-12345",
                    },
                },
                {
                    "template": "core/subnet",
                    "label": "web",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "vcn_id": "oci_core_vcn.main.id",
                        "cidr_block": "10.0.1.0/24",
                        "display_name": "web-subnet",
                        "prohibit_public_ip_on_vnic": False,
                        "aws_source_id": "subnet-abc",
                    },
                },
            ]
        }
        result = group._process_structured_output(draft)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert "oci_core_vcn" in hcl
        assert "oci_core_subnet" in hcl

    def test_preserves_gaps_metadata(self):
        group = self._make_group("network_translation")
        draft = {
            "specs": [
                {
                    "template": "core/vcn",
                    "label": "main",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "cidr_blocks": ["10.0.0.0/16"],
                        "display_name": "test-vcn",
                        "aws_source_id": "vpc-12345",
                    },
                }
            ],
            "gaps": [{"type": "VPN", "severity": "HIGH"}],
            "resource_mappings": [{"aws": "vpc-12345", "oci": "oci_core_vcn.main"}],
        }
        result = group._process_structured_output(draft)
        assert "gaps" in result
        assert result["gaps"] == [{"type": "VPN", "severity": "HIGH"}]
        assert "resource_mappings" in result

    def test_preserves_migration_prerequisites(self):
        group = self._make_group("network_translation")
        draft = {
            "specs": [
                {
                    "template": "core/vcn",
                    "label": "main",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "cidr_blocks": ["10.0.0.0/16"],
                        "display_name": "test",
                        "aws_source_id": "vpc-1",
                    },
                }
            ],
            "migration_prerequisites": ["Enable VCN in target region"],
        }
        result = group._process_structured_output(draft)
        assert "migration_prerequisites" in result

    def test_preserves_handoff_md(self):
        """handoff.md from OCM skill is preserved through rendering."""
        group = self._make_group("ocm_handoff_translation")
        draft = {
            "specs": [
                {
                    "template": "cloud_migrations/migration",
                    "label": "main",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "display_name": "test",
                    },
                }
            ],
            "handoff.md": "# OCM Handoff Runbook\n\nStep 1: ...",
        }
        result = group._process_structured_output(draft)
        assert "handoff.md" in result

    def test_render_error_captured_not_raised(self):
        """Bad specs produce _render_error field instead of crashing."""
        group = self._make_group("network_translation")
        draft = {
            "specs": [
                {
                    "template": "core/vcn",
                    "label": "bad",
                    "params": {"display_name": "no-compartment"},
                }
            ]
        }
        result = group._process_structured_output(draft)
        assert "_render_error" in result

    def test_no_specs_returns_draft_as_is(self):
        """When no specs found, returns draft unchanged."""
        group = self._make_group("network_translation")
        draft = {"raw": "Not parseable as specs"}
        result = group._process_structured_output(draft)
        assert result == draft

    def test_ocm_structured_output(self):
        """OCM skill produces correctly structured HCL with user_spec."""
        group = self._make_group("ocm_handoff_translation")
        draft = {
            "specs": [
                {
                    "template": "cloud_migrations/migration",
                    "label": "main",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "display_name": "aws-to-oci",
                    },
                },
                {
                    "template": "cloud_migrations/migration_plan",
                    "label": "plan",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "migration_id": "oci_cloud_migrations_migration.main.id",
                        "display_name": "plan",
                    },
                },
                {
                    "template": "cloud_migrations/target_asset",
                    "label": "asset_i_abc",
                    "params": {
                        "migration_plan_id": "oci_cloud_migrations_migration_plan.plan.id",
                        "preferred_shape_type": "VM",
                        "shape": "VM.Standard.E5.Flex",
                        "ocpus": 4,
                        "memory_in_gbs": 64,
                        "block_volumes_performance": 10,
                        "aws_source_id": "i-abc",
                    },
                },
            ]
        }
        result = group._process_structured_output(draft)
        assert "ocm/main.tf" in result
        hcl = result["ocm/main.tf"]
        assert "oci_cloud_migrations_migration" in hcl
        assert "oci_cloud_migrations_target_asset" in hcl
        assert "preferred_shape_type" in hcl
        assert "user_spec" in hcl
        assert "shape_config" in hcl

    def test_loadbalancer_structured_output(self):
        """LB skill renders load balancer + backend set to loadbalancer.tf."""
        group = self._make_group("loadbalancer_translation")
        draft = {
            "specs": [
                {
                    "template": "load_balancer/load_balancer",
                    "label": "web_lb",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "display_name": "web-lb",
                        "shape": "flexible",
                        "is_private": False,
                        "shape_details": {
                            "minimum_bandwidth_in_mbps": 10,
                            "maximum_bandwidth_in_mbps": 100,
                        },
                        "subnet_ids": ["oci_core_subnet.pub.id"],
                        "aws_source_id": "alb-123",
                    },
                },
                {
                    "template": "load_balancer/backend_set",
                    "label": "app_bs",
                    "params": {
                        "load_balancer_id": "oci_load_balancer_load_balancer.web_lb.id",
                        "name": "app-backend-set",
                        "policy": "ROUND_ROBIN",
                        "health_checker": {
                            "protocol": "HTTP",
                            "port": 8080,
                            "url_path": "/health",
                            "interval_ms": 30000,
                            "timeout_in_millis": 3000,
                            "retries": 3,
                        },
                        "aws_source_id": "tg-123",
                    },
                },
            ]
        }
        result = group._process_structured_output(draft)
        assert "loadbalancer.tf" in result
        hcl = result["loadbalancer.tf"]
        assert "oci_load_balancer_load_balancer" in hcl
        assert "oci_load_balancer_backend_set" in hcl
        assert "shape_details" in hcl

    def test_mixed_valid_and_free_form(self):
        """Structured output can mix template specs with free_form_hcl."""
        group = self._make_group("network_translation")
        draft = {
            "specs": [
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
                    "template": "free_form_hcl",
                    "label": "drg",
                    "params": {
                        "hcl": 'resource "oci_core_drg" "main" {\n  compartment_id = var.compartment_id\n}',
                    },
                },
            ]
        }
        result = group._process_structured_output(draft)
        assert "network.tf" in result
        assert "main.tf" in result
        assert "oci_core_drg" in result["main.tf"]

    def test_template_specs_stored_for_debugging(self):
        """The original spec list is saved under _template_specs."""
        group = self._make_group("network_translation")
        original_specs = [
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
        draft = {"specs": original_specs}
        result = group._process_structured_output(draft)
        assert result["_template_specs"] == original_specs


class TestIsStructuredOutput:
    """_is_structured_output flag matches STRUCTURED_OUTPUT_SKILLS."""

    @pytest.mark.parametrize(
        "skill_type",
        ["network_translation", "ocm_handoff_translation", "loadbalancer_translation"],
    )
    def test_structured_skills_return_true(self, skill_type):
        group = SkillGroup(SKILL_SPECS[skill_type])
        assert group._is_structured_output() is True

    @pytest.mark.parametrize(
        "skill_type",
        ["synthesis", "database_translation"],
    )
    def test_non_structured_skills_return_false(self, skill_type):
        group = SkillGroup(SKILL_SPECS[skill_type])
        assert group._is_structured_output() is False
