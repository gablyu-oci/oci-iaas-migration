"""Model routing tests: verify skill->model selection logic (Phase 5)."""
import pytest
from app.config import settings
from app.gateway.model_gateway import get_model, MODEL_ROUTING


class TestModelRoutingTemplatedSkills:
    """Templated skills use the fast non-reasoning model."""

    TEMPLATED_SKILLS = [
        "network_translation",
        "ec2_translation",
        "storage_translation",
        "loadbalancer_translation",
        "iam_translation",
        "security_translation",
        "serverless_translation",
        "observability_translation",
        "ocm_handoff_translation",
    ]

    def test_templated_skills_use_templated_model(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_TEMPLATED_WRITER_MODEL", "fast-model")
        monkeypatch.setattr(settings, "LLM_WRITER_MODEL", "default-model")
        for skill in self.TEMPLATED_SKILLS:
            model = get_model(skill, "enhancement")
            assert model == "fast-model", f"{skill} enhancement should use templated model, got {model}"

    def test_templated_skills_fix_uses_templated_model(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_TEMPLATED_WRITER_MODEL", "fast-model")
        monkeypatch.setattr(settings, "LLM_WRITER_MODEL", "default-model")
        for skill in self.TEMPLATED_SKILLS:
            model = get_model(skill, "fix")
            assert model == "fast-model", f"{skill} fix should use templated model, got {model}"

    def test_templated_skills_review_uses_reviewer(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_REVIEWER_MODEL", "reviewer-model")
        for skill in self.TEMPLATED_SKILLS:
            model = get_model(skill, "review")
            assert model == "reviewer-model", f"{skill} review should use reviewer model, got {model}"


class TestModelRoutingFreeformSkills:
    """cfn_terraform uses the reasoning model for free-form HCL."""

    def test_cfn_terraform_uses_freeform_model(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_FREEFORM_WRITER_MODEL", "reasoning-model")
        monkeypatch.setattr(settings, "LLM_WRITER_MODEL", "default-model")
        assert get_model("cfn_terraform", "enhancement") == "reasoning-model"

    def test_cfn_terraform_fix_uses_freeform_model(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_FREEFORM_WRITER_MODEL", "reasoning-model")
        monkeypatch.setattr(settings, "LLM_WRITER_MODEL", "default-model")
        assert get_model("cfn_terraform", "fix") == "reasoning-model"

    def test_cfn_terraform_review_uses_reviewer(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_REVIEWER_MODEL", "reviewer-model")
        assert get_model("cfn_terraform", "review") == "reviewer-model"


class TestModelRoutingFallback:
    """When new env vars are empty, fall back to LLM_WRITER_MODEL."""

    def test_templated_fallback_when_empty(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_TEMPLATED_WRITER_MODEL", "")
        monkeypatch.setattr(settings, "LLM_WRITER_MODEL", "fallback-model")
        assert get_model("network_translation", "enhancement") == "fallback-model"

    def test_freeform_fallback_when_empty(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_FREEFORM_WRITER_MODEL", "")
        monkeypatch.setattr(settings, "LLM_WRITER_MODEL", "fallback-model")
        assert get_model("cfn_terraform", "enhancement") == "fallback-model"

    def test_database_translation_uses_writer(self, monkeypatch):
        """database_translation is NOT a structured skill; uses _writer."""
        monkeypatch.setattr(settings, "LLM_WRITER_MODEL", "writer-model")
        monkeypatch.setattr(settings, "LLM_TEMPLATED_WRITER_MODEL", "templated-model")
        model = get_model("database_translation", "enhancement")
        assert model == "writer-model", f"database_translation should use writer model, got {model}"


class TestModelRoutingDataMigration:
    """data_migration_planning uses templated (non-reasoning) model."""

    def test_data_migration_uses_templated(self, monkeypatch):
        monkeypatch.setattr(settings, "LLM_TEMPLATED_WRITER_MODEL", "fast-model")
        monkeypatch.setattr(settings, "LLM_WRITER_MODEL", "default-model")
        assert get_model("data_migration_planning", "enhancement") == "fast-model"
