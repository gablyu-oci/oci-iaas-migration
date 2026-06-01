"""Run-scoped context passed to every tool via ``RunContextWrapper``.

Every skill-group agent (writer + reviewer) shares the same
``MigrationContext`` instance for one run. Tools read trusted fields
(like ``migration_id``) from the context rather than as LLM-provided
arguments — the LLM cannot spoof the migration it's operating on.

``MigrationContext`` also carries a mutable ``run_state`` dict reserved
for future per-run accumulation (e.g. tool-call telemetry).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MigrationContext:
    """Trusted run-time context for one migration run.

    Populated by the caller (the plan orchestrator or single-skill API
    route); tools read it through ``RunContextWrapper[MigrationContext]``.
    """
    migration_id: str | None = None
    tenant_id: str | None = None
    aws_connection_id: str | None = None

    # Mutable accumulator reserved for per-run telemetry / state. Never
    # exposed back to the LLM — tools can write but don't echo it back in
    # their return values.
    run_state: dict[str, Any] = field(default_factory=dict)
