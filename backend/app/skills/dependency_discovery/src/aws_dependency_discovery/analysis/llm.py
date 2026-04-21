"""AI-powered dependency analysis.

Provides:
1. Anomaly detection — unusual dependency patterns
2. Migration runbook generation — step-by-step cutover plans
3. Risk narratives — CTO-readable impact assessments
4. Cross-correlation — CloudTrail + Flow Log pattern matching

Targets any OpenAI-compatible chat completions endpoint; defaults to the
Oracle internal Llama Stack gateway (anonymous). Configure via
``LLM_BASE_URL`` / ``LLM_API_KEY`` env vars.
"""

from __future__ import annotations

import os

from ..config import (
    get_llm_api_key,
    get_llm_base_url,
    has_llm_credentials,
)
from .classifier import DependencyInfo

# Standalone CLI: can't import app.gateway.model_gateway (pulls in FastAPI).
# Reads the same env vars the main app reads → one source of truth.
_DEFAULT_MODEL = os.environ.get("LLM_WRITER_MODEL", "oci/openai.gpt-5.4")


def is_available() -> bool:
    """Check if an LLM endpoint is reachable (base URL configured)."""
    return has_llm_credentials()


def _get_client():
    """Return an OpenAI client pointed at the configured LLM endpoint."""
    from openai import OpenAI
    # API key is optional; the OpenAI SDK demands a non-empty string even
    # for anonymous endpoints, so fall back to a placeholder.
    api_key = get_llm_api_key() or "anonymous"
    return OpenAI(api_key=api_key, base_url=get_llm_base_url())


def _is_reasoning_model(model: str) -> bool:
    """Detect reasoning-family models that need max_completion_tokens."""
    lower = model.lower()
    return any(tag in lower for tag in ("gpt-5", ".o1", ".o3", ".o4", "-reasoning"))


def _call_llm(prompt: str, max_tokens: int = 4096) -> str:
    """Chat-completion call with the given prompt."""
    client = _get_client()
    params: dict = {
        "model": _DEFAULT_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Reasoning models reject max_tokens
    params["max_completion_tokens" if _is_reasoning_model(_DEFAULT_MODEL) else "max_tokens"] = max_tokens
    response = client.chat.completions.create(**params)
    return response.choices[0].message.content or ""


def _build_dependency_context(
    dependencies: list[DependencyInfo],
    migration_steps: list[dict],
    network_deps: list[dict] | None = None,
    limit: int = 40,
) -> str:
    """Build a concise context string from dependencies and steps."""
    dep_lines = []
    for d in dependencies[:limit]:
        dep_lines.append(
            f"- [{d.risk_level.upper()}] {d.source} -> {d.target}: "
            f"{d.reason} (breaks: {d.breaks_if_wrong})"
        )
    dep_text = "\n".join(dep_lines)

    step_lines = []
    for s in migration_steps:
        deps_str = ", ".join(s["depends_on"]) if s["depends_on"] else "none"
        fan_out = len(s.get("depended_by", []))
        warn = f" [FAN-OUT={fan_out}]" if fan_out >= 3 else ""
        step_lines.append(f"  Step {s['step']}: {s['node_id']} (after: {deps_str}){warn}")
    steps_text = "\n".join(step_lines)

    net_text = ""
    if network_deps:
        net_lines = []
        for nd in network_deps[:20]:
            net_lines.append(
                f"- {nd['src_addr']} -> {nd['dst_addr']}:{nd['dst_port']} "
                f"({nd['service_guess']}, {nd['total_bytes']} bytes, "
                f"{nd['connection_count']} connections)"
            )
        net_text = "\n\n## Network-Level Dependencies (VPC Flow Logs)\n" + "\n".join(net_lines)

    return f"""## Discovered Dependencies (ranked by risk)
{dep_text}

## Proposed Migration Order
{steps_text}{net_text}"""


def summarize_dependencies(
    dependencies: list[DependencyInfo],
    migration_steps: list[dict],
    network_deps: list[dict] | None = None,
) -> str:
    """Generate an AI-powered executive summary of dependencies and migration plan."""
    context = _build_dependency_context(dependencies, migration_steps, network_deps)

    prompt = f"""You are an AWS migration architect. Analyze these discovered service dependencies
and migration ordering from CloudTrail log analysis and VPC Flow Log analysis.
Produce a CTO-readable migration brief.

{context}

## Instructions
1. Summarize the key findings in 3-5 bullet points
2. Highlight the most critical dependencies that could cause outages if migration order is wrong
3. Flag any cross-account trust chains that need special attention
4. If network-level dependencies are present, highlight data-plane risks not visible in API logs
5. Provide a recommended migration sequence with rationale
6. List pre-migration verification steps
7. Keep the language accessible to a CTO — no deep AWS jargon without explanation
"""

    return _call_llm(prompt)


def detect_anomalies(
    dependencies: list[DependencyInfo],
    network_deps: list[dict] | None = None,
) -> str:
    """Use AI to detect unusual dependency patterns that indicate hidden risks."""
    dep_lines = []
    for d in dependencies:
        dep_lines.append(
            f"- {d.source} -> {d.target} [{d.edge_type}] "
            f"freq={d.frequency} risk={d.risk_level}"
        )
    dep_text = "\n".join(dep_lines[:50])

    net_text = ""
    if network_deps:
        net_lines = []
        for nd in network_deps[:30]:
            net_lines.append(
                f"- {nd['src_addr']} -> {nd['dst_addr']}:{nd['dst_port']} "
                f"({nd['service_guess']}, {nd['total_bytes']}B, {nd['connection_count']}x)"
            )
        net_text = "\n\nNetwork traffic (VPC Flow Logs):\n" + "\n".join(net_lines)

    prompt = f"""You are a senior AWS infrastructure analyst performing pre-migration dependency analysis.
Review these discovered dependencies and identify ANOMALIES — patterns that indicate hidden risks
that a team might miss during migration planning.

API-level dependencies (CloudTrail):
{dep_text}{net_text}

Identify and explain:
1. **Unexpected Coupling**: Services communicating in ways that suggest undocumented integrations
   (e.g., a Lambda calling a service it shouldn't need to, or cross-account access patterns
   that suggest shadow IT or legacy configurations)

2. **Tight Coupling Hotspots**: Services with unusually high call frequency that suggest
   synchronous dependencies which will cause cascading failures during migration

3. **Ghost Dependencies**: If network traffic shows connections to IPs/ports that don't
   correspond to any CloudTrail API calls, these are "ghost" data-plane dependencies
   (e.g., direct DB connections, hardcoded IPs, service mesh traffic)

4. **Single Points of Failure**: Services that many others depend on (fan-out > 3)
   where migration downtime will cascade

5. **Temporal Anomalies**: If the same dependency appears at very different frequencies
   across edge types, it may indicate batch vs real-time dual-path dependencies

For each anomaly, explain:
- What the pattern is
- Why it's risky for migration
- What the team should investigate before cutover

Be specific and actionable. Reference actual services and IPs from the data.
"""

    return _call_llm(prompt, max_tokens=4096)


def generate_runbook(
    dependencies: list[DependencyInfo],
    migration_steps: list[dict],
    network_deps: list[dict] | None = None,
) -> str:
    """Generate a detailed migration runbook with pre/during/post cutover steps."""
    context = _build_dependency_context(dependencies, migration_steps, network_deps)

    prompt = f"""You are an AWS-to-OCI migration architect. Generate a detailed MIGRATION RUNBOOK
based on the discovered dependencies below. This runbook will be used by the operations team
during the actual cutover.

{context}

Generate a runbook with these sections:

## PRE-MIGRATION CHECKLIST (T-7 days)
- Verification steps to confirm all dependencies are accounted for
- DNS TTL reduction steps
- Data sync preparation
- Rollback plan outline

## CUTOVER SEQUENCE (T-0)
For EACH migration step, provide:
1. The specific service being migrated
2. Pre-flight checks (what to verify before starting this step)
3. Migration action (what specifically to do)
4. Smoke test (how to verify this step succeeded)
5. Rollback trigger (what failure condition means "abort and rollback")
6. Estimated impact window

## POST-MIGRATION VALIDATION (T+1)
- End-to-end verification steps
- Monitoring alerts to watch
- Common failure modes and their symptoms
- When to declare migration complete

## ROLLBACK PLAN
- Point-of-no-return identification
- Service-by-service rollback sequence (reverse of cutover)
- Data consistency verification after rollback

Be concrete and specific. Reference the actual services and dependencies from the data.
Use the migration ordering as the basis for the cutover sequence.
Format as markdown suitable for pasting into a Confluence/Notion page.
"""

    return _call_llm(prompt, max_tokens=8192)
