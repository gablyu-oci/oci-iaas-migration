"""6R migration strategy classifier using Claude AI.

Classifies application groups into one of the six canonical migration
strategies (Rehost, Replatform, Refactor, Repurchase, Retire, Retain)
by sending a structured prompt to the Anthropic API and parsing the
JSON response.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

SIXR_STRATEGIES: dict[str, str] = {
    "Rehost": "Lift-and-shift to OCI with minimal changes",
    "Replatform": "Migrate with some optimization (e.g., managed database)",
    "Refactor": "Re-architect for cloud-native OCI services",
    "Repurchase": "Replace with SaaS/OCI native service",
    "Retire": "Decommission the workload",
    "Retain": "Keep in current environment",
}

_VALID_STRATEGIES = set(SIXR_STRATEGIES.keys())
_VALID_CONFIDENCES = {"high", "medium", "low"}

CLASSIFICATION_PROMPT = '''You are a cloud migration architect. Classify each application group into one of the 6R migration strategies.

For each group, consider:
- Resource types and counts
- OS compatibility with OCI
- Performance metrics (CPU/memory utilization)
- Dependencies and complexity
- Readiness scores

Application Groups:
{groups_json}

Respond with valid JSON only. Format:
{{
  "classifications": {{
    "<group_name>": {{
      "strategy": "Rehost|Replatform|Refactor|Repurchase|Retire|Retain",
      "confidence": "high|medium|low",
      "rationale": "Brief explanation"
    }}
  }}
}}'''


def _build_default_classification(group_name: str) -> dict[str, str]:
    """Return a safe default when the model response cannot be parsed."""
    return {
        "strategy": "Rehost",
        "confidence": "low",
        "rationale": f"Default classification for '{group_name}' -- model response could not be parsed.",
    }


def _validate_classification(entry: dict) -> dict[str, str]:
    """Normalise and validate a single classification entry.

    Returns a cleaned dict with guaranteed valid strategy / confidence
    values, falling back to safe defaults when needed.
    """
    strategy = entry.get("strategy", "Rehost")
    if strategy not in _VALID_STRATEGIES:
        logger.warning("Unknown strategy '%s', falling back to Rehost", strategy)
        strategy = "Rehost"

    confidence = entry.get("confidence", "low")
    if confidence not in _VALID_CONFIDENCES:
        confidence = "low"

    rationale = entry.get("rationale", "")
    if not isinstance(rationale, str):
        rationale = str(rationale)

    return {
        "strategy": strategy,
        "confidence": confidence,
        "rationale": rationale,
    }


async def classify_workloads(
    app_groups_data: list[dict],
    anthropic_client: Any,
) -> dict[str, dict]:
    """Classify application groups into 6R strategies using Claude.

    Parameters
    ----------
    app_groups_data:
        List of dicts describing each application group.  Expected keys:
        ``name``, ``resource_types``, ``resource_count``, ``avg_readiness``,
        ``os_compat_summary``, ``avg_cpu``, ``avg_memory``.
    anthropic_client:
        An Anthropic client instance (or compatible adapter) as returned by
        ``model_gateway.get_anthropic_client()``.

    Returns
    -------
    dict mapping group_name -> {strategy, confidence, rationale}
    """
    if not app_groups_data:
        return {}

    group_names = [g.get("name", f"group-{i}") for i, g in enumerate(app_groups_data)]

    # Build the prompt
    groups_json = json.dumps(app_groups_data, indent=2, default=str)
    prompt_text = CLASSIFICATION_PROMPT.format(groups_json=groups_json)

    try:
        from app.gateway.model_gateway import get_model
        response = anthropic_client.messages.create(
            model=get_model("sixr_classification", "classify"),
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt_text}],
        )

        # Extract text content from the response
        raw_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text

        if not raw_text.strip():
            logger.error("Empty response from Claude for 6R classification")
            return {name: _build_default_classification(name) for name in group_names}

        # Strip markdown code fences if present
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (with optional language tag) and closing fence
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        parsed = json.loads(cleaned)
        classifications_raw = parsed.get("classifications", parsed)

        results: dict[str, dict] = {}
        for name in group_names:
            if name in classifications_raw and isinstance(classifications_raw[name], dict):
                results[name] = _validate_classification(classifications_raw[name])
            else:
                logger.warning("No classification returned for group '%s'", name)
                results[name] = _build_default_classification(name)

        return results

    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Claude JSON response for 6R classification: %s", exc)
        return {name: _build_default_classification(name) for name in group_names}

    except Exception as exc:
        logger.error("6R classification failed: %s", exc, exc_info=True)
        return {name: _build_default_classification(name) for name in group_names}
