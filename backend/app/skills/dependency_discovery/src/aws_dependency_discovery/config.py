"""Configuration and environment variable loading."""

from __future__ import annotations

import os
from pathlib import Path


def get_db_path() -> Path:
    """Return the SQLite database path, creating parent dirs if needed."""
    raw = os.environ.get("DISCOVERY_DB_PATH", "~/.aws-discovery/discovery.db")
    path = Path(raw).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_anthropic_api_key() -> str | None:
    """Return the Anthropic API key if set, or None if only OAuth is available."""
    return os.environ.get("ANTHROPIC_API_KEY")


def has_anthropic_credentials() -> bool:
    """Return True if any Anthropic credentials are available (API key or OAuth)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    creds_path = Path.home() / ".claude" / ".credentials.json"
    if creds_path.exists():
        import json
        try:
            creds = json.loads(creds_path.read_text())
            return bool(creds.get("claudeAiOauth", {}).get("accessToken"))
        except Exception:
            pass
    return False
