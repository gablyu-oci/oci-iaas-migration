"""
Adapter wrapping claude_agent_sdk.query() with an anthropic.Anthropic-compatible interface.
Used when no ANTHROPIC_API_KEY is configured — authenticates via Claude Code OAuth.
"""

import asyncio
import threading
from typing import Any


class _Usage:
    def __init__(self, usage_dict: dict | None = None):
        d = usage_dict or {}
        self.input_tokens = d.get("input_tokens", 0)
        self.output_tokens = d.get("output_tokens", 0)
        self.cache_read_input_tokens = d.get("cache_read_input_tokens", 0)
        self.cache_creation_input_tokens = d.get("cache_creation_input_tokens", 0)


class _ContentBlock:
    def __init__(self, text: str):
        self.text = text
        self.type = "text"


class _AgentMessage:
    """Mimics anthropic.types.Message for orchestrator compatibility."""

    def __init__(self, text: str, usage_dict: dict | None = None):
        self.content = [_ContentBlock(text)]
        self.usage = _Usage(usage_dict)
        self.stop_reason = "end_turn"


class _MessagesResource:
    def create(
        self,
        *,
        model: str = "claude-opus-4-6",
        max_tokens: int = 8192,
        system=None,
        messages: list | None = None,
        **kwargs,
    ) -> _AgentMessage:
        """
        Synchronous wrapper around claude_agent_sdk.query().

        Combines system instructions and user messages into a single prompt,
        runs the agent in an isolated thread+event loop (safe to call from
        inside an already-running asyncio event loop such as the ARQ worker),
        and returns an object that looks like an anthropic.types.Message.
        """
        from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

        # Build prompt: system block + user turns
        parts: list[str] = []

        if system:
            if isinstance(system, list):
                sys_texts = [
                    s.get("text", "") if isinstance(s, dict) else str(s)
                    for s in system
                ]
                sys_text = "\n\n".join(t for t in sys_texts if t.strip())
            else:
                sys_text = str(system)
            if sys_text.strip():
                parts.append(sys_text)

        prefill: str | None = None
        if messages:
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(
                        c.get("text", "") if isinstance(c, dict) else str(c)
                        for c in content
                    )
                if msg.get("role") == "user" and content.strip():
                    parts.append(content)
                elif msg.get("role") == "assistant" and content.strip():
                    # Capture assistant prefill — used by orchestrators to force
                    # JSON output. We'll inject it as an explicit instruction.
                    prefill = content.strip()

        # If the caller used assistant prefilling (e.g. `{"` to start JSON),
        # add an explicit instruction so the Agent SDK model honours it.
        if prefill is not None:
            parts.append(
                f"IMPORTANT: Your response MUST begin with exactly the following "
                f"characters and contain ONLY valid JSON — no prose, no markdown "
                f"fences, no explanation:\n{prefill}"
            )

        prompt = "\n\n".join(parts)

        # Holder: [result_text, exception, usage_dict]
        holder: list[Any] = [None, None, None]

        async def _run() -> None:
            options = ClaudeAgentOptions(
                allowed_tools=[],
                model=model,
            )
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    holder[0] = message.result or ""
                    holder[2] = message.usage  # dict with input_tokens etc.
                    return
            holder[0] = ""

        # Run in a fresh event loop in a new thread — avoids conflicts with
        # the caller's event loop (ARQ worker, FastAPI lifespan, etc.)
        def _thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_run())
            except Exception as exc:
                holder[1] = exc
            finally:
                loop.close()

        t = threading.Thread(target=_thread, daemon=True)
        t.start()
        t.join(timeout=300)  # 5-minute ceiling per LLM call

        if not t.is_alive() and holder[0] is None and holder[1] is None:
            raise TimeoutError("Agent SDK query timed out after 300s")
        if holder[1] is not None:
            raise holder[1]

        return _AgentMessage(holder[0] or "", holder[2])

    def stream(self, **kwargs) -> "_StreamContextManager":
        """Context manager shim: calls create() and wraps result for stream API compatibility."""
        message = self.create(**kwargs)
        return _StreamContextManager(message)


class _StreamContextManager:
    """Thin wrapper so `with client.messages.stream(...) as s:` works."""

    def __init__(self, message: "_AgentMessage"):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def get_final_message(self) -> "_AgentMessage":
        return self._message

    def get_final_text(self) -> str:
        blocks = self._message.content
        return blocks[0].text if blocks else ""


class AgentSDKClient:
    """
    Drop-in replacement for anthropic.Anthropic that authenticates via
    Claude Code OAuth instead of an API key.
    """

    def __init__(self):
        self.messages = _MessagesResource()
