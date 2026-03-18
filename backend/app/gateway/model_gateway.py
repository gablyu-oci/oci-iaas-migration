"""Anthropic client factory, model routing, and secret scrubbing."""

import re

import anthropic

from app.config import settings

# Maps skill_type -> agent_type -> model name
MODEL_ROUTING = {
    "cfn_terraform": {
        "enhancement": "claude-opus-4-6",
        "review": "claude-sonnet-4-6",
        "fix": "claude-opus-4-6",
    },
    "iam_translation": {
        "enhancement": "claude-opus-4-6",
        "review": "claude-sonnet-4-6",
        "fix": "claude-opus-4-6",
    },
    "dependency_discovery": {
        "runbook": "claude-opus-4-6",
        "anomalies": "claude-sonnet-4-6",
    },
}

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


def get_anthropic_client(api_key: str | None = None):
    """
    Return an Anthropic-compatible client.

    Priority:
    1. Explicit api_key argument
    2. ANTHROPIC_API_KEY env / settings
    3. Claude Code OAuth via AgentSDKClient (no key needed)
    """
    key = api_key or settings.ANTHROPIC_API_KEY
    if key:
        return anthropic.Anthropic(api_key=key)
    from app.gateway.agent_adapter import AgentSDKClient
    return AgentSDKClient()


def get_model(skill_type: str, agent_type: str) -> str:
    """Look up the model to use for a given skill + agent type combination."""
    skill_models = MODEL_ROUTING.get(skill_type, {})
    return skill_models.get(agent_type, "claude-sonnet-4-6")
