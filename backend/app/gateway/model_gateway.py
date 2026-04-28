"""LLM client factory, model routing, and secret scrubbing.

This module is the **single source of truth** for model selection. Every
orchestrator and service that picks a model should call ``get_model(
skill_type, agent_type)`` rather than hardcode a model ID.

Model identities live in five places:

    app.config.settings.LLM_WRITER_MODEL              # default writer
    app.config.settings.LLM_REVIEWER_MODEL            # review/classifier/anomalies
    app.config.settings.LLM_ORCHESTRATOR_MODEL        # top-level orchestrator planning
    app.config.settings.LLM_TEMPLATED_WRITER_MODEL    # templated (structured-output) skills
    app.config.settings.LLM_FREEFORM_WRITER_MODEL     # free-form HCL generation skills

Templated skills (the 9 STRUCTURED_OUTPUT_SKILLS) emit small JSON payloads
that the template renderer converts to HCL. They don't need reasoning and
can run on a fast, cheap model. Free-form skills (cfn_terraform) generate
raw HCL directly and benefit from a reasoning-capable model. Both fall back
to ``LLM_WRITER_MODEL`` when no override is configured.

``MODEL_ROUTING`` below binds each (skill, agent) pair to one of those
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


def _templated_writer() -> str:
    """Fast non-reasoning model for templated skills (small JSON output)."""
    return settings.LLM_TEMPLATED_WRITER_MODEL or settings.LLM_WRITER_MODEL


def _freeform_writer() -> str:
    """Reasoning model for free-form HCL generation (cfn_terraform)."""
    return settings.LLM_FREEFORM_WRITER_MODEL or settings.LLM_WRITER_MODEL


# skill_type -> agent_type -> role resolver.
# Using callables (instead of materialized strings) so that changing the
# settings values at runtime — e.g. in a test — is picked up immediately.
#
# Routing rationale:
#   _templated_writer  — for STRUCTURED_OUTPUT_SKILLS that emit small JSON
#                        (network, ec2, storage, loadbalancer, iam, security,
#                        serverless, observability, ocm_handoff). These
#                        don't need reasoning; a fast model reduces latency.
#   _freeform_writer   — for cfn_terraform which generates raw HCL and
#                        benefits from reasoning capability.
#   _writer            — fallback / non-skill services.
#   _reviewer          — review/scoring agents (always non-reasoning).
#   _orchestrator      — top-level planning + dispatch.
MODEL_ROUTING: dict[str, dict[str, object]] = {
    # ── Free-form skill (raw HCL generation) ──────────────────────────
    "cfn_terraform": {
        "enhancement": _freeform_writer,
        "review": _reviewer,
        "fix": _freeform_writer,
    },
    # ── Templated / structured-output skills ──────────────────────────
    "network_translation": {
        "enhancement": _templated_writer,
        "review": _reviewer,
        "fix": _templated_writer,
    },
    "ec2_translation": {
        "enhancement": _templated_writer,
        "review": _reviewer,
        "fix": _templated_writer,
    },
    "storage_translation": {
        "enhancement": _templated_writer,
        "review": _reviewer,
        "fix": _templated_writer,
    },
    "database_translation": {
        "enhancement": _writer,
        "review": _reviewer,
        "fix": _writer,
    },
    "loadbalancer_translation": {
        "enhancement": _templated_writer,
        "review": _reviewer,
        "fix": _templated_writer,
    },
    "iam_translation": {
        "enhancement": _templated_writer,
        "review": _reviewer,
        "fix": _templated_writer,
    },
    "security_translation": {
        "enhancement": _templated_writer,
        "review": _reviewer,
        "fix": _templated_writer,
    },
    "serverless_translation": {
        "enhancement": _templated_writer,
        "review": _reviewer,
        "fix": _templated_writer,
    },
    "observability_translation": {
        "enhancement": _templated_writer,
        "review": _reviewer,
        "fix": _templated_writer,
    },
    "ocm_handoff_translation": {
        "enhancement": _templated_writer,
        "review": _reviewer,
        "fix": _templated_writer,
    },
    # ── Non-templated planning skills ─────────────────────────────────
    "data_migration_planning": {
        "enhancement": _templated_writer,
        "review": _reviewer,
        "fix": _templated_writer,
    },
    # ── Other skills (keep on default _writer) ────────────────────────
    "dependency_discovery": {
        "runbook": _writer,
        "anomalies": _reviewer,
        "review": _reviewer,
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
