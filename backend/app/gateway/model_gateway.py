"""LLM client factory, model routing, and secret scrubbing.

This module is the **single source of truth** for model selection. Every
orchestrator and service that picks a model should call ``get_model(
skill_type, agent_type)`` rather than hardcode a model ID.

Model identities live in only three places:

    app.config.settings.LLM_WRITER_MODEL        # writer/enhancement/fix/runbook
    app.config.settings.LLM_REVIEWER_MODEL      # review/classifier/anomalies
    app.config.settings.LLM_ORCHESTRATOR_MODEL  # top-level orchestrator planning

``MODEL_ROUTING`` below binds each (skill, agent) pair to one of those three
roles. Change the env var (or override ``MODEL_ROUTING[...]`` at runtime)
and every call site picks up the new model on next ``get_model`` invocation.
"""

import re

from app.config import settings
from app.gateway.llm_client import LLMClient


def _writer() -> str:
    return settings.LLM_WRITER_MODEL


def _reviewer() -> str:
    return settings.LLM_REVIEWER_MODEL


def _orchestrator() -> str:
    return settings.LLM_ORCHESTRATOR_MODEL


# skill_type -> agent_type -> role resolver.
# Using callables (instead of materialized strings) so that changing the
# settings values at runtime — e.g. in a test — is picked up immediately.
MODEL_ROUTING: dict[str, dict[str, object]] = {
    "cfn_terraform": {
        "enhancement": _writer,
        "review": _reviewer,
        "fix": _writer,
    },
    "iam_translation": {
        "enhancement": _writer,
        "review": _reviewer,
        "fix": _writer,
    },
    "dependency_discovery": {
        "runbook": _writer,
        "anomalies": _reviewer,
        "review": _reviewer,
    },
    "network_translation": {
        "enhancement": _writer,
        "review": _reviewer,
        "fix": _writer,
    },
    "ec2_translation": {
        "enhancement": _writer,
        "review": _reviewer,
        "fix": _writer,
    },
    "database_translation": {
        "enhancement": _writer,
        "review": _reviewer,
        "fix": _writer,
    },
    "loadbalancer_translation": {
        "enhancement": _writer,
        "review": _reviewer,
        "fix": _writer,
    },
    "storage_translation": {
        "enhancement": _writer,
        "review": _reviewer,
        "fix": _writer,
    },
    "synthesis": {
        "enhancement": _writer,
        "review": _reviewer,
        "fix": _writer,
    },
    "workload_planning": {
        "review": _reviewer,
        "enhancement": _writer,
    },
    "data_migration_planning": {
        "enhancement": _writer,
        "review": _reviewer,
        "fix": _writer,
    },
    # Top-level orchestrator — separate model role because it does
    # multi-step planning + tool coordination, not drafting or reviewing.
    "orchestrator": {
        "plan":     _orchestrator,
        "dispatch": _orchestrator,
    },

    # Non-skill services that still need to talk to an LLM.
    "sixr_classification": {"classify": _reviewer},
    "app_grouping":        {"group":    _reviewer},
    "migration_execution": {"generate": _writer},
    "resource_mapping":    {"map":      _reviewer},
}


def get_model(skill_type: str, agent_type: str) -> str:
    """Look up the LLM model for a given (skill, agent) pair.

    Falls back to the writer model if the pair is not in ``MODEL_ROUTING``.
    Callers MUST route model selection through this function — do not
    hardcode model strings elsewhere.
    """
    role = MODEL_ROUTING.get(skill_type, {}).get(agent_type)
    if role is None:
        return _writer()
    # Resolvers are stored as callables so settings changes are hot.
    if callable(role):
        return role()
    return role  # tolerate a plain string override for tests


SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)secret.{0,20}[=:]\s*\S+"),
    re.compile(r"\b\d{12}\b"),
    re.compile(r"ocid1\.[a-z]+\.[a-z]+\.[a-z-]+\.[a-z0-9]+"),
]


def scrub_secrets(text: str) -> str:
    """Replace known secret patterns with [REDACTED]."""
    for pat in SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def get_llm_client(api_key: str | None = None) -> LLMClient:
    """Build an LLM client pointed at the configured endpoint.

    Anonymous endpoints (like the internal Llama Stack gateway) are
    supported: an empty API key becomes a placeholder string since the
    OpenAI SDK requires a non-empty value.
    """
    return LLMClient(
        api_key=api_key or settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
    )


# Legacy aliases — kept so older call sites keep working. Prefer ``get_llm_client``.
def get_anthropic_client(api_key: str | None = None) -> LLMClient:
    return get_llm_client(api_key)


def get_genai_client(api_key: str | None = None) -> LLMClient:
    return get_llm_client(api_key)


def guard_input(text: str, skill_type: str = "unknown") -> str:
    """Run input guardrails. Returns scrubbed text. Raises ValueError if blocked."""
    from app.gateway.guardrails import check_input
    result = check_input(text)
    if result["blocked"]:
        raise ValueError(f"Input blocked by guardrail: {result['block_reason']}")
    if result["warnings"]:
        import logging
        logging.getLogger(__name__).warning("Input guardrail warnings: %s", result["warnings"])
    return result["scrubbed_text"]


def guard_output(text: str, skill_type: str = "unknown") -> dict:
    """Run output guardrails. Returns check result dict."""
    from app.gateway.guardrails import check_output
    result = check_output(text, skill_type)
    if result["warnings"] or not result["valid"]:
        import logging
        logging.getLogger(__name__).warning(
            "Output guardrail [%s] issues=%s warnings=%s",
            skill_type, result["issues"], result["warnings"]
        )
    return result
