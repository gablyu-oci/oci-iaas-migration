"""Run-scoped context passed to every tool via ``RunContextWrapper``.

The orchestrator and any skill-group agent invoked under it share the same
``MigrationContext`` instance. Tools read trusted fields (like ``migration_id``)
from the context rather than as LLM-provided arguments — the LLM cannot
spoof the migration it's operating on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MigrationContext:
    """Trusted run-time context for one migration run.

    Populated by the caller (e.g., ``run_migration`` or a future job runner
    integration); tools read it through ``RunContextWrapper[MigrationContext]``.
    """
    migration_id: str | None = None
    tenant_id: str | None = None
    aws_connection_id: str | None = None
