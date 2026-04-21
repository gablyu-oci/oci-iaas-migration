"""Configuration and environment variable loading for the standalone CLI.

Kept deliberately independent of ``app.gateway`` so this package can run
without pulling in FastAPI / pydantic_settings. It reads the same env vars
the main app reads, so a single ``.env`` configures both.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_db_path() -> Path:
    """Return the SQLite database path, creating parent dirs if needed."""
    raw = os.environ.get("DISCOVERY_DB_PATH", "~/.aws-discovery/discovery.db")
    path = Path(raw).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_llm_api_key() -> str | None:
    """Return the LLM API key if set, or None for anonymous endpoints."""
    return os.environ.get("LLM_API_KEY") or None


def get_llm_base_url() -> str:
    """Return the LLM OpenAI-compatible chat-completions base URL.

    Default: Oracle internal Llama Stack gateway (anonymous).
    """
    return os.environ.get(
        "LLM_BASE_URL",
        "https://llama-stack.ai-apps-ord.oci-incubations.com/v1",
    )


def has_llm_credentials() -> bool:
    """The endpoint is anonymous by default, so we only need a base URL."""
    return bool(get_llm_base_url())
