"""Test that data_migration_planning skill rejects .tf output."""
import pytest
from app.agents.skill_group import _reviewer_instructions, SKILL_SPECS


class TestDataMigrationNoTf:
    """Verify the data_migration_planning reviewer guard against .tf files."""

    def test_reviewer_instructions_contain_tf_guard(self):
        """The data_migration_planning reviewer must include the .tf guard."""
        spec = SKILL_SPECS["data_migration_planning"]
        instructions = _reviewer_instructions(spec)
        assert ".tf" in instructions
        assert "CRITICAL" in instructions
        assert "markdown only" in instructions.lower() or "runbook" in instructions.lower()

    def test_other_skill_reviewer_has_no_tf_guard(self):
        """Non-data-migration skills should NOT have the .tf guard."""
        spec = SKILL_SPECS["ec2_translation"]
        instructions = _reviewer_instructions(spec)
        # The generic reviewer might mention .tf but should NOT have the
        # specific "data_migration_planning emitted .tf" guard
        assert "data_migration_planning emitted .tf" not in instructions

    def test_conversion_rules_prohibit_tf(self):
        """conversion-rules.md must contain the no-.tf constraint."""
        from pathlib import Path
        rules_path = Path(__file__).resolve().parent.parent / "app" / "skills" / "data_migration" / "workflows" / "conversion-rules.md"
        content = rules_path.read_text()
        assert "NEVER emit .tf" in content or "NEVER emit `.tf`" in content
        assert "markdown" in content.lower()

    def test_bundle_builder_routes_md_to_runbooks(self):
        """data_migration .md files land in runbooks/data-migration/."""
        from app.services.bundle_builder import build_hybrid_bundle
        artifacts = {
            "data_migration/data-migration.md": "# No DB migration needed",
            "synthesis/compute.tf": 'resource "oci_core_instance" "web" {}',
        }
        result = build_hybrid_bundle(
            artifacts,
            migration_name="test",
            resource_count=1,
            skills_ran=["data_migration_planning"],
        )
        assert "runbooks/data-migration/data-migration.md" in result
        # No .tf files under runbooks/data-migration/
        dm_tf_files = [k for k in result if k.startswith("runbooks/data-migration/") and k.endswith(".tf")]
        assert dm_tf_files == [], f"Unexpected .tf files in runbooks: {dm_tf_files}"
