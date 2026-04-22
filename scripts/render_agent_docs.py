#!/usr/bin/env python3
"""Regenerate docs/agent-architecture.md from the registry.

Substitutes the ``{{REGISTRY_MARKDOWN}}`` placeholder (or the
BEGIN/END markers on subsequent runs) with ``render_registry_markdown()``.
Run whenever a tool, skill, or workflow wave changes.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.registry import render_registry_markdown  # noqa: E402

DOC = ROOT / "docs" / "agent-architecture.md"
PLACEHOLDER = "{{REGISTRY_MARKDOWN}}"
BEGIN = "<!-- BEGIN AUTO-GENERATED REGISTRY -->"
END = "<!-- END AUTO-GENERATED REGISTRY -->"


def main() -> int:
    text = DOC.read_text(encoding="utf-8")
    rendered = render_registry_markdown()
    wrapped = f"{BEGIN}\n{rendered}\n{END}"

    if PLACEHOLDER in text:
        new = text.replace(PLACEHOLDER, wrapped)
    elif BEGIN in text and END in text:
        head = text.split(BEGIN)[0]
        tail = text.split(END, 1)[1]
        new = f"{head}{wrapped}{tail}"
    else:
        new = text.rstrip() + "\n\n" + wrapped + "\n"

    DOC.write_text(new, encoding="utf-8")
    print(f"wrote {DOC} ({DOC.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
