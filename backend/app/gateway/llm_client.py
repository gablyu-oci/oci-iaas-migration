"""Factory for the OpenAI client used across the app.

Every service that needs to talk to an LLM uses the native
``openai`` Python SDK pointed at the configured OpenAI-compatible
chat-completions endpoint. The default target is the Oracle internal
Llama Stack gateway (anonymous, no API key). Swap via the
``LLM_BASE_URL`` / ``LLM_API_KEY`` env vars or at runtime through the
Settings page. The same client also works against the OCI Generative
AI OpenAI-compatible endpoint, OpenAI itself, vLLM, and so on.

Shared helpers for reasoning-model parameter handling live in
:mod:`app.gateway.reasoning` (see ``call_chat_completion``).
"""

from __future__ import annotations

from typing import Any


def make_openai_client(
    api_key: str | None,
    base_url: str,
    project: str | None = None,
) -> Any:
    """Build an ``openai.OpenAI`` instance pointed at ``base_url``.

    The OpenAI SDK requires a non-empty ``api_key`` string even when the
    server doesn't enforce auth, so we fall back to a placeholder for
    anonymous endpoints (like the internal Llama Stack gateway).
    """
    from openai import OpenAI  # local import keeps module import cheap

    kwargs: dict[str, Any] = {
        "api_key": api_key or "anonymous",
        "base_url": base_url,
    }
    if project:
        kwargs["project"] = project
    return OpenAI(**kwargs)
