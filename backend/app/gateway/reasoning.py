"""Shared OpenAI chat-completion helpers and reasoning-model handling.

This module centralises:

  * ``is_reasoning_model`` — heuristic that picks ``max_completion_tokens``
    over ``max_tokens`` (and drops ``temperature``) for OpenAI reasoning
    families (gpt-5.x / o1 / o3 / o4) and xAI ``*-reasoning`` variants.
  * ``build_completion_kwargs`` — assembles the request kwargs given a
    model id, token budget, and optional temperature.
  * ``call_chat_completion`` — wraps ``client.chat.completions.create``
    with the reasoning-model switch, a system-message preamble built
    from a string (or a list of ``{"type": "text", "text": ...}`` blocks
    for backward compatibility with legacy call sites), a small
    backoff loop, and a transparent retry that swaps ``max_tokens``
    <-> ``max_completion_tokens`` if the server rejects whichever one
    we picked.  Returns the raw ``openai.types.chat.ChatCompletion``.
  * ``get_cached_tokens`` — safe accessor for
    ``usage.prompt_tokens_details.cached_tokens`` (the Llama Stack
    gateway does not return that field today; this returns 0 in that
    case, preserving prior behaviour).

The OpenAI Python SDK is the only client surface used across the app —
see :func:`app.gateway.model_gateway.get_llm_client` for the
factory.
"""

from __future__ import annotations

import time
from typing import Any, Iterable


def is_reasoning_model(model: str) -> bool:
    """Detect models that must be called with ``max_completion_tokens``.

    Covers:
      - OpenAI reasoning families (gpt-5.x, o1/o3/o4) -- regardless of any
        ``oci/`` or other namespace prefix the gateway prepends to the ID.
      - xAI reasoning variants identified by the ``-reasoning`` suffix
        (e.g., ``xai.grok-4.20-reasoning``), carefully excluding the
        matching ``-non-reasoning`` variants which are plain chat models.

    The client auto-corrects on the server's 400 error either way, but
    doing this up-front saves a round trip on every call.
    """
    mid = model.lower()
    if "-non-reasoning" in mid:
        return False
    if "-reasoning" in mid:
        return True
    # OpenAI reasoning families -- match anywhere in the ID so namespace
    # prefixes like ``oci/`` or ``openai/`` don't hide them.
    needles = ("openai.gpt-5", "openai.o1", "openai.o3", "openai.o4")
    return any(n in mid for n in needles)


def _flatten_system(system: Any) -> str:
    """Collapse a system payload into plain text.

    Accepts a string or a list of ``{"type": "text", "text": ...}`` style
    blocks (a small backward-compat shim for the one legacy call site
    that still passes the block form). Returns the joined text.
    """
    if system is None:
        return ""
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        parts: list[str] = []
        for block in system:
            if isinstance(block, dict):
                txt = block.get("text", "")
            else:
                txt = str(block)
            if txt:
                parts.append(txt)
        return "\n\n".join(parts)
    return str(system)


def build_completion_kwargs(
    model: str,
    *,
    max_tokens: int = 8192,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Build the request kwargs for ``chat.completions.create``.

    Reasoning models (gpt-5/o1/o3/o4 families) require
    ``max_completion_tokens`` instead of ``max_tokens`` and reject any
    non-default ``temperature``; this function picks the right shape
    based on :func:`is_reasoning_model`.
    """
    kwargs: dict[str, Any] = {"model": model}
    if is_reasoning_model(model):
        kwargs["max_completion_tokens"] = max_tokens
    else:
        kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            kwargs["temperature"] = temperature
    return kwargs


def _build_messages(system: Any, messages: Iterable[dict] | None) -> list[dict]:
    """Fold ``system`` into a leading system message and pass the rest through."""
    out: list[dict] = []
    sys_text = _flatten_system(system)
    if sys_text.strip():
        out.append({"role": "system", "content": sys_text})
    for msg in messages or []:
        out.append(dict(msg))
    return out


def call_chat_completion(
    client: Any,
    *,
    model: str,
    max_tokens: int = 8192,
    system: Any = None,
    messages: list[dict] | None = None,
    temperature: float | None = None,
    **extra: Any,
) -> Any:
    """Call ``client.chat.completions.create`` with reasoning-model handling.

    * Folds ``system`` (string or list of text blocks) into a leading
      ``{"role": "system", ...}`` message.
    * Picks ``max_tokens`` vs ``max_completion_tokens`` based on the model.
    * On a ``BadRequestError`` complaining about the token-limit field,
      swaps and retries once without counting it against the backoff
      budget — this is the same behaviour the previous LLM adapter had,
      kept here so callers don't have to know the model taxonomy.
    * Up to 3 attempts with linear backoff for other transient errors.
    """
    kwargs = build_completion_kwargs(model, max_tokens=max_tokens, temperature=temperature)
    kwargs["messages"] = _build_messages(system, messages)
    kwargs.update(extra)

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:
            msg = str(exc)
            # Server rejected our token-limit field name -> swap and retry
            # without consuming a backoff attempt.
            if "max_tokens" in msg and "max_completion_tokens" in msg and "max_tokens" in kwargs:
                kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
                kwargs.pop("temperature", None)
                continue
            if "max_completion_tokens" in msg and "max_tokens" in msg and "max_completion_tokens" in kwargs:
                kwargs["max_tokens"] = kwargs.pop("max_completion_tokens")
                continue
            last_err = exc
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))

    raise last_err or RuntimeError("chat.completions.create failed")


def get_cached_tokens(usage: Any) -> int:
    """Return ``usage.prompt_tokens_details.cached_tokens`` or 0.

    The Llama Stack OpenAI-compatible gateway does not populate
    ``prompt_tokens_details`` today, so this normally returns 0; native
    OpenAI endpoints will surface a real value when prompt caching is
    active.
    """
    if usage is None:
        return 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None and isinstance(usage, dict):
        details = usage.get("prompt_tokens_details")
    if details is None:
        return 0
    val = getattr(details, "cached_tokens", None)
    if val is None and isinstance(details, dict):
        val = details.get("cached_tokens")
    return int(val or 0)
