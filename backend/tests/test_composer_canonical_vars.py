"""Tests for canonical root variable emission in synthesis_composer."""
import re
import pytest

from app.services.synthesis_composer import (
    compose_terraform,
    CANONICAL_ROOT_VARS,
)


class TestCanonicalRootVars:
    """Verify CANONICAL_ROOT_VARS are always present in the output."""

    def test_empty_skill_input_produces_all_canonical_vars(self):
        """Even with zero skill artifacts, variables.tf contains every canonical var."""
        result = compose_terraform({}, migration_name="test")
        assert "variables.tf" in result.files
        content = result.files["variables.tf"]
        for var_def in CANONICAL_ROOT_VARS:
            assert f'variable "{var_def["name"]}"' in content, (
                f"Canonical var '{var_def['name']}' missing from variables.tf"
            )

    def test_canonical_vars_present_with_skill_output(self):
        """When skills produce artifacts, canonical vars are still present."""
        skill_artifacts = {
            "network_translation": {
                "main.tf": 'resource "oci_core_vcn" "main" { compartment_id = var.compartment_id }',
                "variables.tf": 'variable "custom_var" { type = string }',
            },
        }
        result = compose_terraform(skill_artifacts, migration_name="test")
        content = result.files["variables.tf"]
        # Custom var from skill
        assert 'variable "custom_var"' in content
        # All canonical vars
        for var_def in CANONICAL_ROOT_VARS:
            assert f'variable "{var_def["name"]}"' in content

    def test_skill_declared_var_takes_precedence(self):
        """When a skill declares a canonical var, the skill's version wins."""
        skill_artifacts = {
            "network_translation": {
                "variables.tf": (
                    'variable "region" {\n'
                    '  type        = string\n'
                    '  description = "My custom region description"\n'
                    '}\n'
                ),
            },
        }
        result = compose_terraform(skill_artifacts, migration_name="test")
        content = result.files["variables.tf"]
        assert 'variable "region"' in content
        assert "My custom region description" in content

    def test_compartment_id_is_canonical(self):
        """compartment_id (not compartment_ocid) is the canonical variable name."""
        var_names = [v["name"] for v in CANONICAL_ROOT_VARS]
        assert "compartment_id" in var_names
        assert "compartment_ocid" not in var_names

    def test_sensitive_vars_marked(self):
        """Variables with sensitive=True are rendered with sensitive = true."""
        result = compose_terraform({}, migration_name="test")
        content = result.files["variables.tf"]
        # aws_credentials_secret_ocid should be sensitive
        idx = content.find('variable "aws_credentials_secret_ocid"')
        assert idx >= 0, "aws_credentials_secret_ocid not found in variables.tf"
        block_end = content.find("}", idx)
        block = content[idx:block_end]
        assert "sensitive" in block

    def test_providers_tf_references_canonical_vars(self):
        """providers.tf references var.tenancy_ocid etc. which must be in variables.tf."""
        result = compose_terraform({}, migration_name="test")
        providers = result.files.get("providers.tf", "")
        variables = result.files.get("variables.tf", "")
        # Every var. reference in providers.tf should be declared in variables.tf
        var_refs = set(re.findall(r'var\.(\w+)', providers))
        for ref in var_refs:
            assert f'variable "{ref}"' in variables, (
                f"providers.tf references var.{ref} but it's not in variables.tf"
            )

    def test_providers_tf_always_emitted(self):
        """providers.tf is always emitted, even with no skill artifacts."""
        result = compose_terraform({}, migration_name="test")
        assert "providers.tf" in result.files

    def test_canonical_var_count(self):
        """There are exactly 10 canonical root variables defined."""
        assert len(CANONICAL_ROOT_VARS) == 10

    def test_default_values_rendered(self):
        """Variables with default values have them rendered in the output."""
        result = compose_terraform({}, migration_name="test")
        content = result.files["variables.tf"]
        # migration_name has default = "migration"
        idx = content.find('variable "migration_name"')
        assert idx >= 0
        block_end = content.find("}", idx)
        block = content[idx:block_end]
        assert "default" in block
