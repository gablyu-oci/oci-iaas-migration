"""Agentic runtime for the OCI migration tool.

Built on the ``openai-agents`` SDK, pointed at the internal Llama Stack
endpoint. This is the **only** runtime — the old chat-completion pipeline
has been removed.

Layers (each maps to one module in this package):

- ``config``       — tracing-disabled OpenAI client + per-model wrapper builder
- ``context``      — ``MigrationContext`` dataclass, passed via ``RunContextWrapper``
- ``tools``        — ``@function_tool`` definitions shared across agents
- ``skill_group``  — writer + reviewer agent pair + bounded review-edit loop
- ``orchestrator`` — Python-driven dependency-wave dispatcher with parallel gather
- ``registry``     — machine-readable registry of tools + workflow metadata
"""

from app.agents.config import build_client, build_model, disable_external_telemetry

__all__ = ["build_client", "build_model", "disable_external_telemetry"]
