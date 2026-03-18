"""
Pytest configuration: patch Postgres-specific types (JSONB, BYTEA, UUID)
to SQLite-compatible equivalents so tests run without a live Postgres.
"""
import pytest
from sqlalchemy import JSON, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB, BYTEA
from sqlalchemy.dialects.postgresql import UUID as PGUUID


def pytest_configure(config):
    """Replace PG-only types with SQLite-compatible ones before models are used in tests."""
    # Patch JSONB → JSON
    import sqlalchemy.dialects.postgresql as pg_dialect
    pg_dialect.JSONB = JSON

    # Patch BYTEA → LargeBinary
    pg_dialect.BYTEA = LargeBinary

    # Patch UUID → String(36) for SQLite
    class _FakeUUID(String):
        def __init__(self, *args, as_uuid=True, **kwargs):
            super().__init__(36)

    pg_dialect.UUID = _FakeUUID

    # Re-import models so they pick up patched types
    import importlib
    import app.db.models as models_mod
    importlib.reload(models_mod)
