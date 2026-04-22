"""Run-scoped context passed to every tool via ``RunContextWrapper``.

The orchestrator and any skill-group agent invoked under it share the same
``MigrationContext`` instance. Tools read trusted fields (like ``migration_id``)
from the context rather than as LLM-provided arguments — the LLM cannot
spoof the migration it's operating on.

``MigrationContext`` also carries a mutable ``run_state`` dict that
orchestrator tools append to (skill invocations, tool calls, novel-type
decisions). The Python wrapper around the LLM orchestrator reads this
state at end-of-run to assemble ``OrchestratorResult`` — so the LLM
doesn't have to emit telemetry in its final message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MigrationContext:
    """Trusted run-time context for one migration run.

    Populated by the caller (e.g., ``run_migration`` or a future job runner
    integration); tools read it through ``RunContextWrapper[MigrationContext]``.
    """
    migration_id: str | None = None
    tenant_id: str | None = None
    aws_connection_id: str | None = None

    # Mutable accumulator. Orchestrator-level tools append per-skill
    # invocation records here; the Python composer reads it after the agent
    # finishes. Never exposed to the LLM — tools can write but don't echo it
    # back in their return values.
    run_state: dict[str, Any] = field(default_factory=dict)
