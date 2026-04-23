"""Turn an agent-runtime ``SkillRunResult`` into a persisted job-result dict.

The DB + UI job pipeline consumes a specific shape:
``{artifacts, interactions, confidence, decision, cost, iterations, ...}``.
``to_job_result()`` maps the agent runtime's native output into that shape.
``run_skill_sync()`` is the sync entry point every sync call site uses
(ARQ worker subprocesses, the plan orchestrator, etc.) so there's exactly
one place the mapping happens.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agents.orchestrator import run_skill as _run_agent_skill
from app.agents.skill_group import SKILL_SPECS
from app.config import settings


# Known filename suffixes LLMs commonly emit as underscore-separated JSON keys
# (e.g. ``main_tf`` meaning ``main.tf``, ``handoff_md`` meaning ``handoff.md``).
# Without normalization, _extract_artifacts used to append ``.txt`` to these
# which made the plan bundle produce ``main_tf.txt`` files that lost their
# syntax-highlighting / editor-affordance context. Ordered: longest first so
# ``_yaml`` wins over a hypothetical ``_y`` check.
_KEY_EXTENSION_SUFFIXES = (
    ("_yaml", ".yaml"),
    ("_json", ".json"),
    ("_html", ".html"),
    ("_yml",  ".yml"),
    ("_tf",   ".tf"),
    ("_md",   ".md"),
    ("_sh",   ".sh"),
    ("_py",   ".py"),
    ("_csv",  ".csv"),
    ("_txt",  ".txt"),
)


def _normalize_artifact_name(key: str) -> str:
    """Turn an LLM's dict key into a proper filename.

    Rules (first match wins):
      - Already contains a '.' → leave alone (``main.tf`` stays ``main.tf``)
      - Ends with a known extension suffix (``_tf``, ``_md``, …) → convert
        that underscore to a dot (``main_tf`` → ``main.tf``)
      - Otherwise → append ``.txt`` (same as before) so callers never see a
        dotless file path.
    """
    if not key:
        return "artifact.txt"
    if "." in key:
        return key
    low = key.lower()
    for suf, ext in _KEY_EXTENSION_SUFFIXES:
        if low.endswith(suf) and len(key) > len(suf):
            return key[:-len(suf)] + ext
    return f"{key}.txt"


def _extract_artifacts(draft: Any) -> dict[str, str]:
    """Lift a writer draft into a ``{filename → content}`` artifact map.

    Strings keyed by a name that looks like a filename become files. Keys
    that use the common ``main_tf`` / ``handoff_md`` JSON convention get
    normalized to ``main.tf`` / ``handoff.md``. A copy of the full draft
    is always saved as ``draft.json`` for traceability (the bundle_builder
    routes that to ``debug/`` so it doesn't clutter the Terraform tab).
    """
    artifacts: dict[str, str] = {}
    if isinstance(draft, dict) and draft:
        for k, v in draft.items():
            if isinstance(v, str) and v.strip():
                artifacts[_normalize_artifact_name(k)] = v
        artifacts.setdefault("draft.json", json.dumps(draft, indent=2, default=str))
    else:
        artifacts["draft.json"] = json.dumps(draft, indent=2, default=str)
    return artifacts


def to_job_result(agent_result: dict) -> dict:
    """Map one ``SkillRunResult.as_dict()`` into the persisted-job shape.

    Returns a dict with keys:
      artifacts         — {filename: content}
      interactions      — list[{agent_type, model, iteration, tokens_*, cost_usd,
                                decision, confidence, issues, duration_seconds}]
      confidence        — float
      decision          — APPROVED | APPROVED_WITH_NOTES | NEEDS_FIXES
      cost              — float (0.0 today; pricing TBD)
      iterations        — int
      writer_tool_calls / reviewer_tool_calls / stopped_early — passed through
    """
    draft = agent_result.get("draft") or {}
    review = agent_result.get("review") or {}

    artifacts = _extract_artifacts(draft)
    if review:
        artifacts["review.json"] = json.dumps(review, indent=2, default=str)

    confidence = float(review.get("confidence", 0.0) or 0.0)
    decision = review.get("decision") or "APPROVED"
    iterations = int(agent_result.get("iterations", 1))

    # Synthesize one "interaction" per iteration so the UI's per-iteration
    # timeline still has something to render.
    interactions: list[dict] = [{
        "agent_type": "writer",
        "model": settings.LLM_WRITER_MODEL,
        "iteration": iterations,
        "tokens_input": 0,
        "tokens_output": 0,
        "tokens_cache_read": 0,
        "tokens_cache_write": 0,
        "cost_usd": 0.0,
        "decision": decision,
        "confidence": confidence,
        "issues": review.get("issues", []) or [],
        "duration_seconds": 0.0,
    }]

    return {
        "artifacts": artifacts,
        "interactions": interactions,
        "confidence": confidence,
        "decision": decision,
        "cost": 0.0,
        "iterations": iterations,
        "writer_tool_calls": agent_result.get("writer_tool_calls", 0),
        "reviewer_tool_calls": agent_result.get("reviewer_tool_calls", 0),
        "stopped_early": agent_result.get("stopped_early", False),
    }


def run_skill_sync(
    skill_type: str,
    input_content: str,
    max_iterations: int = 3,
    migration_id: str | None = None,
) -> dict:
    """Sync wrapper: dispatch to the agent runtime and return a job-result dict.

    Called from synchronous contexts (ARQ worker subprocesses, spawn()
    children) that can't ``await`` directly. Each call sets up a fresh
    event loop so it plays nicely with nested asyncio.
    """
    if skill_type not in SKILL_SPECS:
        raise ValueError(
            f"Unknown skill type: {skill_type!r}. "
            f"Registered agent skills: {sorted(SKILL_SPECS)}"
        )
    agent_result = asyncio.run(_run_agent_skill(
        skill_type,
        input_content,
        max_iterations=max_iterations,
        migration_id=migration_id,
    ))
    return to_job_result(agent_result)
