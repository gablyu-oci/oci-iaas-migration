"""Agentic runtime for the OCI migration tool.

Built on the ``openai-agents`` SDK, pointed at the internal Llama Stack
endpoint. This is the **only** runtime — the old chat-completion pipeline
has been removed.

Layers (each maps to one module in this package):

- ``config``       — tracing-disabled OpenAI client + per-model wrapper builder
- ``context``      — ``MigrationContext`` dataclass, passed via ``RunContextWrapper``
- ``tools``        — ``@function_tool`` definitions shared across writer/reviewer agents
- ``skill_group``  — writer + reviewer agent pair + bounded review-edit loop
  + canonical ``DEPENDENCY_WAVES`` ordering + ``run_skill`` public entry point
- ``registry``     — machine-readable registry of tools + workflow metadata

The production migration orchestrator is a deterministic Python child-
process dispatcher in ``app/services/plan_orchestrator.py``; there is no
LLM agent at the orchestrator layer.
"""

from app.agents.config import build_client, build_model, disable_external_telemetry

__all__ = ["build_client", "build_model", "disable_external_telemetry"]
