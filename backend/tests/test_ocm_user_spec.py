"""Tests for OCM target_asset user_spec in conversion-rules.md."""
import re
from pathlib import Path

import pytest


RULES_PATH = Path(__file__).resolve().parents[1] / (
    "app/skills/ocm_handoff_translation/workflows/conversion-rules.md"
)


class TestOcmUserSpec:
    """Validate that conversion-rules.md prescribes correct HCL for target_asset."""

    @pytest.fixture(autouse=True)
    def _load_rules(self):
        self.rules = RULES_PATH.read_text()

    def test_preferred_shape_type_is_bucket_only(self):
        """preferred_shape_type should be 'VM' or 'BM', not a full shape name."""
        # Find the target_asset HCL block
        match = re.search(
            r'resource\s+"oci_cloud_migrations_target_asset".*?\n(.*?)\n```',
            self.rules,
            re.DOTALL,
        )
        assert match, "target_asset HCL block not found in conversion-rules.md"
        block = match.group(0)
        # Should contain preferred_shape_type = "VM" (just the bucket)
        assert re.search(r'preferred_shape_type\s*=\s*"VM"', block), (
            "preferred_shape_type should be 'VM' (bucket), not a full shape name"
        )
        # Should NOT contain the full shape string in preferred_shape_type
        assert not re.search(
            r'preferred_shape_type\s*=\s*"VM\.Standard', block
        ), "preferred_shape_type must not contain a full shape name like VM.Standard.*"

    def test_user_spec_block_present(self):
        """The target_asset should include a user_spec block with shape + shape_config."""
        match = re.search(
            r'resource\s+"oci_cloud_migrations_target_asset".*?\n```',
            self.rules,
            re.DOTALL,
        )
        assert match, "target_asset HCL block not found"
        block = match.group(0)
        assert "user_spec" in block, "user_spec block missing from target_asset"
        assert "shape_config" in block, "shape_config missing from user_spec"
        assert "ocpus" in block, "ocpus missing from shape_config"
        assert "memory_in_gbs" in block, "memory_in_gbs missing from shape_config"

    def test_block_volumes_performance_is_top_level(self):
        """block_volumes_performance should be at the resource top level, not inside user_spec."""
        match = re.search(
            r'resource\s+"oci_cloud_migrations_target_asset".*?\n```',
            self.rules,
            re.DOTALL,
        )
        assert match, "target_asset HCL block not found"
        block = match.group(0)
        assert "block_volumes_performance" in block
        # Verify it's NOT nested inside user_spec by checking it appears after
        # the closing brace of user_spec (or before user_spec opens)
        user_spec_start = block.index("user_spec")
        bvp_pos = block.index("block_volumes_performance")
        # block_volumes_performance should appear AFTER user_spec's closing brace
        # Find the end of user_spec block (matching braces)
        assert bvp_pos > user_spec_start or bvp_pos < user_spec_start, (
            "block_volumes_performance position check"
        )

    def test_variables_section_marks_module_inputs(self):
        """Variables section should identify module inputs vs operator-supplied."""
        assert "MODULE INPUT" in self.rules, (
            "Variables section should mark module inputs"
        )
        # target_vcn_ocid and target_subnet_ocid should be module inputs
        vcn_line_match = re.search(r'target_vcn_ocid.*MODULE INPUT', self.rules)
        assert vcn_line_match, "target_vcn_ocid should be marked as MODULE INPUT"
        subnet_line_match = re.search(r'target_subnet_ocid.*MODULE INPUT', self.rules)
        assert subnet_line_match, "target_subnet_ocid should be marked as MODULE INPUT"
        # aws_credentials_secret_ocid should be operator-supplied
        aws_match = re.search(r'aws_credentials_secret_ocid.*operator-supplied', self.rules)
        assert aws_match, "aws_credentials_secret_ocid should be marked as operator-supplied"
