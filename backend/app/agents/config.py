"""Agentic-runtime configuration.

One place to set up the ``openai-agents`` SDK so every agent built later
in this package shares the same client, the same Llama Stack endpoint,
and has all external telemetry disabled. The SDK by default ships traces
to ``platform.openai.com``; we never want that for Oracle-internal data.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from openai import AsyncOpenAI

from app.config import settings

_log = logging.getLogger(__name__)


def disable_external_telemetry() -> None:
    """Turn off every SDK-level outbound telemetry channel.

    Called once at import time from ``app.agents.__init__`` via
    ``build_client``. Idempotent — safe to call repeatedly.
    """
    try:
        from agents import set_tracing_disabled
        set_tracing_disabled(True)
    except Exception:  # noqa: BLE001 — telemetry disable is best-effort
        _log.warning("couldn't disable openai-agents tracing; continuing")


@lru_cache(maxsize=1)
def build_client() -> AsyncOpenAI:
    """Return the single ``AsyncOpenAI`` client every agent should use.

    Points at ``settings.LLM_BASE_URL`` (our Llama Stack). The OpenAI SDK
    requires a non-empty API key even when the server is anonymous, so
    we pass a placeholder when one isn't configured.

    **Timeout + retries tuned for reasoning models + large prompts.**
    The Llama Stack nginx gateway times out individual requests at ~60s,
    but a ``gpt-5.4`` reasoning call on a 30 KB CloudFormation template
    can easily need longer. We give the client a 5-minute per-request
    timeout, and the SDK already retries on 5xx — but we bump the retry
    count so a transient upstream hiccup doesn't kill a long-running
    skill-group run.
    """
    import httpx
    disable_external_telemetry()
    return AsyncOpenAI(
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY or "anonymous",
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0),
        max_retries=5,
    )


def build_model(model_id: str):
    """Wrap a model ID into the right SDK model object.

    We always use the **Chat Completions** surface rather than Responses:
    - Llama Stack's OpenAI-compat layer covers every working model via chat.
    - The SDK's default Responses API requires models to be Responses-native
      (not all of them are — see ``docs/llm-models.md``).
    - It also sidesteps the SDK's ``multi_provider`` routing, which parses
      ``oci/`` as a provider prefix and rejects it with "Unknown prefix".

    If we later want to switch to Responses for OpenAI models (to unlock
    pro/codex), do it per-agent at the ``Agent`` construction site.
    """
    # Local import so the heavy ``agents`` package isn't imported until
    # someone actually uses the agent runtime.
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
    return OpenAIChatCompletionsModel(model=model_id, openai_client=build_client())
