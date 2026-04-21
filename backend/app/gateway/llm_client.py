"""LLM client with an Anthropic-compatible surface over OpenAI chat completions.

The orchestrators in ``app/skills/*`` were written against the Anthropic SDK
(``client.messages.create(...)`` and ``client.messages.stream(...)``). This
adapter keeps that surface intact while routing the actual call to any
OpenAI-compatible chat-completions endpoint.

Default target is the Oracle internal Llama Stack gateway (anonymous, no
API key). Swap via the ``LLM_BASE_URL`` / ``LLM_API_KEY`` env vars or at
runtime through the Settings page. The same client also works against the
OCI Generative AI OpenAI-compatible endpoint, OpenAI itself, vLLM, etc.
"""

from __future__ import annotations

import time
from typing import Any, Iterable


class _Usage:
    """Mimics ``anthropic.types.Usage``.

    OpenAI-compatible responses use ``prompt_tokens`` / ``completion_tokens``;
    we map those onto Anthropic's ``input_tokens`` / ``output_tokens``. The
    upstream endpoints we target don't expose cache-read/cache-write token
    counters through this surface, so those are always zero.
    """

    def __init__(self, usage: Any | None = None):
        self.input_tokens = _get(usage, "prompt_tokens", 0) or 0
        self.output_tokens = _get(usage, "completion_tokens", 0) or 0
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class _ContentBlock:
    def __init__(self, text: str):
        self.text = text
        self.type = "text"


class _GenAIMessage:
    """Mimics ``anthropic.types.Message`` so existing orchestrators work unchanged."""

    def __init__(self, text: str, usage: Any | None = None, finish_reason: str | None = None):
        self.content = [_ContentBlock(text or "")]
        self.usage = _Usage(usage)
        # Anthropic uses ``stop_reason``; orchestrators check for ``"max_tokens"``
        # to detect truncation. Map the OpenAI-style ``finish_reason`` value.
        if finish_reason == "length":
            self.stop_reason = "max_tokens"
        elif finish_reason in ("stop", None):
            self.stop_reason = "end_turn"
        else:
            self.stop_reason = finish_reason


class _StreamContextManager:
    """Thin context manager so ``with client.messages.stream(...) as s`` still works."""

    def __init__(self, message: _GenAIMessage):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def get_final_message(self) -> _GenAIMessage:
        return self._message

    def get_final_text(self) -> str:
        blocks = self._message.content
        return blocks[0].text if blocks else ""


def _get(obj: Any, attr: str, default: Any = None) -> Any:
    """Attribute or dict key accessor (OpenAI SDK uses pydantic models)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _flatten_system(system: Any) -> str:
    """Collapse Anthropic-style ``system`` (str | list[dict]) into plain text.

    Anthropic accepts either a string or a list of ``{"type": "text", "text": ...,
    "cache_control": ...}`` blocks. OCI GenAI only has a single ``system`` role
    message, so join the text blocks and drop cache_control (caching is a
    provider-specific feature not exposed by the OpenAI-compatible API).
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


def _flatten_content(content: Any) -> str:
    """Collapse Anthropic-style message ``content`` (str | list[dict]) into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", ""))
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)
    return str(content)


_REASONING_MODEL_PREFIXES = (
    "openai.gpt-5", "openai.o1", "openai.o3", "openai.o4",
)


def _is_reasoning_model(model: str) -> bool:
    """OpenAI reasoning models (o-series, gpt-5) use max_completion_tokens."""
    return any(model.startswith(p) for p in _REASONING_MODEL_PREFIXES)


def _to_openai_messages(system: Any, messages: Iterable[dict] | None) -> list[dict]:
    """Translate Anthropic-shape messages into OpenAI chat.completion messages."""
    out: list[dict] = []
    sys_text = _flatten_system(system)
    if sys_text.strip():
        out.append({"role": "system", "content": sys_text})
    for msg in messages or []:
        role = msg.get("role", "user")
        content = _flatten_content(msg.get("content", ""))
        if not content.strip():
            continue
        # Anthropic allows ``assistant`` role for prefilling. OCI GenAI accepts
        # assistant turns too, so pass them through unchanged.
        out.append({"role": role, "content": content})
    return out


class _MessagesResource:
    def __init__(self, client: "LLMClient"):
        self._client = client

    def create(
        self,
        *,
        model: str,
        max_tokens: int = 8192,
        system: Any = None,
        messages: list | None = None,
        temperature: float | None = None,
        **_kwargs,
    ) -> _GenAIMessage:
        """Synchronous chat completion call against OCI GenAI.

        Reasoning models (OpenAI's ``o1``/``o3``/``o4``/``gpt-5`` families) reject
        the ``max_tokens`` field and require ``max_completion_tokens`` instead,
        and they also reject non-default ``temperature``. Detect those by name
        and adjust the request — the first time a caller passes them plain
        ``max_tokens``, we translate; on ``BadRequestError`` complaining about
        the field, we also transparently retry with the other name.
        """
        openai_messages = _to_openai_messages(system, messages)
        uses_completion_tokens = _is_reasoning_model(model)

        kwargs: dict[str, Any] = {"model": model, "messages": openai_messages}
        if uses_completion_tokens:
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens
            if temperature is not None:
                kwargs["temperature"] = temperature

        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._client._openai.chat.completions.create(**kwargs)
                break
            except Exception as exc:
                msg = str(exc)
                # If the server says the tokens field is wrong, swap and retry
                # immediately without counting this as a backoff attempt.
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
        else:
            raise last_err or RuntimeError("OCI GenAI call failed")

        choice = resp.choices[0] if resp.choices else None
        message = _get(choice, "message")
        text = _get(message, "content", "") or ""
        finish_reason = _get(choice, "finish_reason")
        usage = _get(resp, "usage")
        return _GenAIMessage(text=text, usage=usage, finish_reason=finish_reason)

    def stream(self, **kwargs) -> _StreamContextManager:
        """Context-manager shim. Streaming is aggregated into one message so
        existing orchestrators that just call ``stream.get_final_message()``
        work without change.
        """
        message = self.create(**kwargs)
        return _StreamContextManager(message)


class LLMClient:
    """Drop-in replacement for ``anthropic.Anthropic``.

    Uses the OpenAI Python SDK pointed at any OpenAI-compatible chat
    completions endpoint (Llama Stack by default, OCI GenAI, OpenAI, vLLM,
    etc.). Exposes a ``.messages`` resource with the subset of the Anthropic
    SDK surface used by the migration skills.
    """

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        project: str | None = None,  # kept for backwards compat; ignored if empty
    ):
        from openai import OpenAI
        # OpenAI SDK requires a non-empty api_key string even when the server
        # doesn't enforce auth. Fall back to a placeholder for anonymous
        # endpoints (like the internal Llama Stack gateway).
        openai_kwargs: dict[str, Any] = {
            "api_key": api_key or "anonymous",
            "base_url": base_url,
        }
        if project:
            openai_kwargs["project"] = project
        self._openai = OpenAI(**openai_kwargs)
        self.messages = _MessagesResource(self)
