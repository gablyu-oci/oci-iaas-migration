"""Shared reasoning-model detection.

Centralises the heuristic so both the synchronous ``LLMClient`` (used by
skill orchestrators) and the async ``openai-agents`` path share the same
logic for deciding whether a model needs ``max_completion_tokens`` instead
of ``max_tokens``.
"""

from __future__ import annotations


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
