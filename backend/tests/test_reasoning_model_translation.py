"""
Tests for reasoning-model parameter translation, client timeout configuration,
and synthesis composition isolation.

Covers two bug fixes and one shared heuristic:

1. _ReasoningAwareCompletions translates max_tokens -> max_completion_tokens
   and strips temperature for reasoning models (gpt-5.x, o1/o3/o4, xai -reasoning).
2. build_client() sets a 1200s read timeout for long reasoning calls.
3. is_reasoning_model heuristic correctly classifies model IDs.
4. compose_terraform runs without invoking any LLM.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test 1: Reasoning model translates max_tokens to max_completion_tokens
# ---------------------------------------------------------------------------

class TestReasoningAwareCompletions:

    def test_reasoning_model_translates_max_tokens(self):
        """build_model('oci/openai.gpt-5.4') sends max_completion_tokens, not max_tokens."""
        from app.agents.config import _ReasoningAwareCompletions

        mock_completions = MagicMock()
        mock_completions.create = AsyncMock(return_value="fake-response")

        proxy = _ReasoningAwareCompletions(mock_completions)

        result = asyncio.run(
            proxy.create(
                model="oci/openai.gpt-5.4",
                max_tokens=32000,
                temperature=0.7,
                messages=[],
            )
        )

        mock_completions.create.assert_called_once()
        call_kwargs = mock_completions.create.call_args.kwargs

        # max_tokens must have been replaced by max_completion_tokens
        assert "max_tokens" not in call_kwargs
        assert call_kwargs["max_completion_tokens"] == 32000

        # temperature must be stripped for reasoning models
        assert "temperature" not in call_kwargs

        # model and messages should pass through unchanged
        assert call_kwargs["model"] == "oci/openai.gpt-5.4"
        assert call_kwargs["messages"] == []

    # -------------------------------------------------------------------
    # Test 2: Non-reasoning model preserves max_tokens
    # -------------------------------------------------------------------

    def test_non_reasoning_model_preserves_max_tokens(self):
        """gpt-4o (non-reasoning) should still send max_tokens."""
        from app.agents.config import _ReasoningAwareCompletions

        mock_completions = MagicMock()
        mock_completions.create = AsyncMock(return_value="fake-response")

        proxy = _ReasoningAwareCompletions(mock_completions)

        result = asyncio.run(
            proxy.create(
                model="gpt-4o",
                max_tokens=4096,
                temperature=0.5,
                messages=[],
            )
        )

        mock_completions.create.assert_called_once()
        call_kwargs = mock_completions.create.call_args.kwargs

        # max_tokens must be preserved for non-reasoning models
        assert call_kwargs["max_tokens"] == 4096
        assert "max_completion_tokens" not in call_kwargs

        # temperature must be preserved for non-reasoning models
        assert call_kwargs["temperature"] == 0.5

    def test_reasoning_model_o3_variant(self):
        """o3 models (with oci/ prefix) are reasoning models."""
        from app.agents.config import _ReasoningAwareCompletions

        mock_completions = MagicMock()
        mock_completions.create = AsyncMock(return_value="fake-response")

        proxy = _ReasoningAwareCompletions(mock_completions)
        asyncio.run(
            proxy.create(
                model="oci/openai.o3",
                max_tokens=16000,
                temperature=1.0,
                messages=[{"role": "user", "content": "hello"}],
            )
        )

        call_kwargs = mock_completions.create.call_args.kwargs
        assert "max_tokens" not in call_kwargs
        assert call_kwargs["max_completion_tokens"] == 16000
        assert "temperature" not in call_kwargs

    def test_proxy_delegates_unknown_attributes(self):
        """_ReasoningAwareCompletions proxies attribute access to the original."""
        from app.agents.config import _ReasoningAwareCompletions

        mock_completions = MagicMock()
        mock_completions.some_other_method = "sentinel"

        proxy = _ReasoningAwareCompletions(mock_completions)
        assert proxy.some_other_method == "sentinel"


# ---------------------------------------------------------------------------
# Test 3: build_client timeout is 1200s
# ---------------------------------------------------------------------------

def test_build_client_read_timeout(monkeypatch):
    """build_client() configures a 1200s read timeout for long reasoning calls."""
    from app.agents.config import build_client

    build_client.cache_clear()
    monkeypatch.setattr("app.config.settings.LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setattr("app.config.settings.LLM_API_KEY", "test-key")
    try:
        client = build_client()
        assert client.timeout.read == 1200.0
        assert client.timeout.connect == 10.0
        assert client.timeout.write == 60.0
        assert client.timeout.pool == 10.0
    finally:
        build_client.cache_clear()


# ---------------------------------------------------------------------------
# Test 4: Synthesis composition does NOT make LLM calls
# ---------------------------------------------------------------------------

def test_synthesis_no_llm_call():
    """compose_terraform completes without invoking any LLM client."""
    from app.services.synthesis_composer import compose_terraform

    per_skill = {
        "network_translation": {
            "main.tf": (
                'resource "oci_core_vcn" "main" {\n'
                '  display_name = "test"\n'
                '  cidr_blocks  = ["10.0.0.0/16"]\n'
                "}"
            ),
            "variables.tf": 'variable "compartment_id" {}',
        },
        "ec2_translation": {
            "main.tf": (
                'resource "oci_core_instance" "web" {\n'
                '  display_name = "web-1"\n'
                "}"
            ),
        },
    }

    # If any LLM path is invoked, blow up immediately.
    with patch(
        "app.agents.config.build_client",
        side_effect=AssertionError("LLM should not be called during synthesis"),
    ):
        result = compose_terraform(per_skill, migration_name="test-workload")

    # Basic structural assertions
    assert result.files, "compose_terraform should produce output files"
    assert "providers.tf" in result.files
    assert len(result.skills_included) == 2
    assert "network_translation" in result.skills_included
    assert "ec2_translation" in result.skills_included

    # The VCN resource should land in network.tf
    assert "network.tf" in result.files
    assert "oci_core_vcn" in result.files["network.tf"]

    # The instance resource should land in compute.tf
    assert "compute.tf" in result.files
    assert "oci_core_instance" in result.files["compute.tf"]

    # Variables should be consolidated
    assert "variables.tf" in result.files
    assert "compartment_id" in result.files["variables.tf"]


# ---------------------------------------------------------------------------
# Test 5: is_reasoning_model heuristic
# ---------------------------------------------------------------------------

class TestIsReasoningModel:

    def test_openai_gpt5_variants_are_reasoning(self):
        from app.gateway.reasoning import is_reasoning_model

        assert is_reasoning_model("oci/openai.gpt-5.4") is True
        assert is_reasoning_model("oci/openai.gpt-5.4-mini") is True

    def test_openai_o_series_are_reasoning(self):
        from app.gateway.reasoning import is_reasoning_model

        assert is_reasoning_model("oci/openai.o3") is True
        assert is_reasoning_model("oci/openai.o4-mini") is True

    def test_gpt4o_is_not_reasoning(self):
        from app.gateway.reasoning import is_reasoning_model

        assert is_reasoning_model("gpt-4o") is False
        assert is_reasoning_model("gpt-4o-mini") is False

    def test_xai_reasoning_suffix(self):
        from app.gateway.reasoning import is_reasoning_model

        assert is_reasoning_model("xai.grok-4.20-reasoning") is True

    def test_xai_non_reasoning_suffix(self):
        from app.gateway.reasoning import is_reasoning_model

        assert is_reasoning_model("xai.grok-4.20-non-reasoning") is False

    def test_case_insensitivity(self):
        from app.gateway.reasoning import is_reasoning_model

        assert is_reasoning_model("OCI/OPENAI.GPT-5.4") is True
        assert is_reasoning_model("GPT-4O") is False


