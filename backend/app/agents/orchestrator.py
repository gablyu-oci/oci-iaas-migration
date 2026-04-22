"""LLM-driven migration orchestrator.

A full agent (not a Python dispatcher) sits at the top of the migration
pipeline. It:

1. Inspects the discovered inventory via ``count_resources_by_type`` +
   ``list_discovered_resources``.
2. Classifies novel / unclaimed AWS types via ``classify_resource_type``
   and decides how to route them (fallback skill, flag as unsupported).
3. Plans a dispatch order informed by ``get_dependency_guidance`` (the
   canonical IaaS wave order) but is free to deviate when the guidance
   doesn't fit.
4. Spawns writer+reviewer skill groups via ``run_skill_group`` /
   ``run_skills_parallel`` — each call blocks until the group's internal
   writer→reviewer loop finishes with APPROVED.
5. Validates the final artifact bundle via ``terraform_validate``.
6. Returns a narrative summary of what ran, what was skipped, and what
   needs human follow-up.

The Python ``run_migration`` entry point wraps the agent run, seeds a
``MigrationContext`` with an ``invocation_log`` accumulator that the
orchestrator's tools append to, and composes the final
``OrchestratorResult`` from that accumulator (so the LLM doesn't have to
emit telemetry in its final message).

Why LLM-driven: dispatch decisions that used to be fixed (strict
dependency waves) were fine for a well-formed inventory but brittle for
partial or novel inputs. Giving the orchestrator tools + agency lets it
adapt — handle unknown resource types, retry a failed skill with a
different input shape, or skip a wave entirely when nothing applies.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from agents import Agent, Runner

from app.agents.config import build_model
from app.agents.context import MigrationContext
from app.agents.skill_group import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_ITERATIONS,
    KNOWN_AWS_TYPES,
    SKILL_SPECS,
    SKILL_TO_AWS_TYPES,
)
from app.agents.tools import (
    classify_resource_type,
    count_resources_by_type,
    get_dependency_guidance,
    get_skill_catalog,
    list_discovered_resources,
    list_resources_for_skill,
    lookup_aws_mapping,
    run_skill_group,
    run_skills_parallel,
    terraform_validate,
)
from app.config import settings

_log = logging.getLogger(__name__)


# ─── Canonical wave ordering (guidance only, also exported to the UI) ─────────
DEPENDENCY_WAVES: list[tuple[str, ...]] = (
    ("iam_translation", "security_translation"),
    ("network_translation",),
    ("storage_translation", "database_translation", "data_migration_planning"),
    ("ec2_translation",),
    ("loadbalancer_translation",),
    ("serverless_translation",),
    ("observability_translation",),
    ("cfn_terraform",),
    ("workload_planning", "dependency_discovery"),
    ("synthesis",),
)


# ─── Orchestrator result ──────────────────────────────────────────────────────

@dataclass
class OrchestratorResult:
    """Structured return shape for one full migration orchestration run.

    Composed by Python from (a) the LLM's final summary text and (b) the
    ``invocation_log`` accumulator that orchestrator tools appended to
    during the run. Every telemetry field (tool-call counts, elapsed time,
    failure lists) is derived from the accumulator — the LLM doesn't have
    to emit them.
    """
    migration_id: str
    max_iterations: int
    confidence_threshold: float
    elapsed_seconds: float
    total_resources: int
    matched_resources: int
    unmatched_resource_count: int
    unknown_resource_types: list[str]
    skipped_skills: list[str]
    invocations: list[dict]                  # per-skill call log w/ timings
    skills: dict[str, dict]                  # skill_type → last SkillRunResult.as_dict()
    total_writer_tool_calls: int
    total_reviewer_tool_calls: int
    failed_skills: list[str]
    orchestrator_narrative: str              # the LLM's final message
    summary: str                             # short human-readable line

    def as_dict(self) -> dict:
        return asdict(self)


# ─── Agent definition ─────────────────────────────────────────────────────────

def _orchestrator_instructions(max_iterations: int, confidence_threshold: float) -> str:
    return f"""You are the **Migration Orchestrator** for an AWS → OCI migration.
You have full dispatch authority — you decide which skills to run, in what
order, with what inputs, and when to stop. You are an agent, not a script.

## Your tools

- `count_resources_by_type()` — start here. Gives you an inventory summary
  grouped by AWS CFN type. No arguments.
- `list_discovered_resources(limit)` — fetch up to `limit` raw resource
  rows (id, aws_type, name, aws_arn) when you need sample data to build
  a skill's input payload.
- `get_skill_catalog()` — list every registered skill + what it handles.
  Call this early so you know your arsenal.
- `get_dependency_guidance()` — canonical IaaS dependency-wave ordering
  (VCN before subnets before instances, etc.). Guidance, not enforcement —
  you're free to deviate when the guidance doesn't fit.
- `classify_resource_type(aws_type)` — check whether an AWS type has a
  registered skill. Use this for novel / unclaimed types so you can decide
  how to route them.
- `lookup_aws_mapping(aws_type)` — pull the canonical OCI target from
  data/mappings/resources.yaml for any AWS type.
- `list_resources_for_skill(skill)` — the inverse: which AWS types does a
  given skill claim?
- `run_skill_group(skill_type, input_content, ...)` — spawn a writer+reviewer
  pair for one skill and wait for its bounded loop to finish. The tool
  response is the SkillRunResult (draft, review, iterations, approved, …).
- `run_skills_parallel(specs_json)` — fan out to multiple skills
  concurrently. Use this for skills in the same dependency wave.
- `terraform_validate(main_tf, variables_tf, outputs_tf)` — run
  `terraform init -backend=false && terraform validate` in a sandbox.
  Use this at the end to sanity-check the synthesized HCL.

## Your job

1. **Inventory.** Call `count_resources_by_type()` first. Note how many
   resources of each type there are.
2. **Learn the arsenal.** Call `get_skill_catalog()` once.
3. **Triage novel types.** For any AWS type in the inventory NOT covered
   by the catalog (check `aws_types` per skill), call
   `classify_resource_type` to confirm it's truly unclaimed, then decide:
   - Route to a related skill with a note explaining the gap, OR
   - Route to `cfn_terraform` as a generic fallback, OR
   - Flag as unsupported in your final summary (don't silently drop).
4. **Plan dispatch.** Call `get_dependency_guidance()`. Use its wave
   ordering unless you have a concrete reason to deviate. Skills whose
   claimed AWS types aren't present in the inventory should be skipped.
5. **Execute.** For each wave that has applicable skills:
   - Build the input payload per skill (the catalog's `input_shape_hint`
     tells you what shape each skill expects).
   - If multiple skills run in the same wave, use `run_skills_parallel`.
   - If only one runs, use `run_skill_group`.
6. **Handle failures.** If a skill returns an error or a NEEDS_FIXES
   review with low confidence, decide: retry with a different input,
   skip, or continue. Don't re-run a skill that already succeeded.
7. **Final validation.** After all per-skill work is done and (if
   applicable) the `synthesis` skill has produced a merged bundle, call
   `terraform_validate` on the synthesized main.tf + variables.tf +
   outputs.tf. Include its verdict in your narrative.
8. **Summarize.** Return a final message describing:
   - What ran and what was skipped (with counts).
   - Novel resource types you encountered and how you handled them.
   - Any skills that failed or that the reviewer marked NEEDS_FIXES.
   - The terraform_validate verdict.
   - What the operator still needs to do manually.

## Constraints

- Max iterations per skill loop is **{max_iterations}**; early-stop
  threshold is confidence ≥ **{confidence_threshold}**. You can override
  per-call via tool arguments but defaults are usually fine.
- Never run `synthesis` before the skills it would be composing are done.
- Never run `workload_planning` or `dependency_discovery` unless the
  caller explicitly asks — those need assessment context this
  orchestrator doesn't have today.
- Your final message is for humans — write prose, not JSON. Per-skill
  telemetry is collected automatically by the tools; you don't need to
  repeat it.
"""


def build_orchestrator_agent(
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> Agent:
    """Build the orchestrator Agent with its full tool set.

    Called per run (not cached) so settings changes (e.g., rotating the
    orchestrator model via the UI) take effect on the next invocation.
    """
    return Agent(
        name="Migration Orchestrator",
        instructions=_orchestrator_instructions(max_iterations, confidence_threshold),
        model=build_model(settings.LLM_ORCHESTRATOR_MODEL),
        tools=[
            # Inspection
            count_resources_by_type,
            list_discovered_resources,
            lookup_aws_mapping,
            list_resources_for_skill,
            get_skill_catalog,
            classify_resource_type,
            get_dependency_guidance,
            # Dispatch
            run_skill_group,
            run_skills_parallel,
            # Validation
            terraform_validate,
        ],
    )


# ─── Python wrapper: seed context, run agent, compose result ──────────────────

def _classify_inventory(resources: list[dict]) -> tuple[list[str], list[str], int]:
    """Split the inventory into (matched_aws_types, unknown_aws_types, unmatched_count)."""
    types_in_inventory: set[str] = set()
    unmatched = 0
    for r in resources:
        t = r.get("aws_type")
        if not t:
            continue
        types_in_inventory.add(t)
        if t not in KNOWN_AWS_TYPES:
            unmatched += 1
    matched = sorted(types_in_inventory & KNOWN_AWS_TYPES)
    unknown = sorted(types_in_inventory - KNOWN_AWS_TYPES)
    return matched, unknown, unmatched


def _compose_result(
    migration_id: str,
    max_iterations: int,
    confidence_threshold: float,
    resources: list[dict],
    ctx: MigrationContext,
    narrative: str,
    elapsed: float,
) -> OrchestratorResult:
    """Assemble OrchestratorResult from the run-state accumulator."""
    invocations: list[dict] = ctx.run_state.get("invocations", []) or []

    matched_types, unknown_types, unmatched_count = _classify_inventory(resources)
    matched_count = len(resources) - unmatched_count

    # Per-skill aggregation — keep the *last* successful call per skill_type
    # (the orchestrator may legitimately retry a skill with new input).
    skills_by_type: dict[str, dict] = {}
    failed: list[str] = []
    total_w, total_r = 0, 0
    for inv in invocations:
        skill = inv.get("skill_type") or "_unknown_"
        if "error" in inv:
            if skill not in failed:
                failed.append(skill)
            continue
        res = inv.get("result") or {}
        skills_by_type[skill] = res
        total_w += int(res.get("writer_tool_calls", 0) or 0)
        total_r += int(res.get("reviewer_tool_calls", 0) or 0)

    # Skipped: skills registered with a routing set whose AWS types are in
    # the inventory but were never invoked. (Skills with no claimed types
    # — synthesis, workload_planning, dependency_discovery — don't count
    # as skipped unless the orchestrator would have been expected to run
    # them. We conservatively only list resource-routed skills.)
    called = set(skills_by_type) | set(failed)
    skipped: list[str] = []
    for skill, types in SKILL_TO_AWS_TYPES.items():
        if types is None:
            continue
        if any(r.get("aws_type") in types for r in resources) and skill not in called:
            skipped.append(skill)

    summary_bits = [
        f"Ran {len(skills_by_type)} skills in {elapsed:.1f}s; "
        f"{len(failed)} failed."
    ]
    if unknown_types:
        summary_bits.append(
            f"⚠ {unmatched_count} resources of {len(unknown_types)} unhandled AWS "
            f"type(s): {', '.join(unknown_types[:5])}"
            + (" …" if len(unknown_types) > 5 else "")
        )
    if skipped:
        summary_bits.append(f"skipped {len(skipped)} skills: {', '.join(skipped)}")

    return OrchestratorResult(
        migration_id=migration_id,
        max_iterations=max_iterations,
        confidence_threshold=confidence_threshold,
        elapsed_seconds=round(elapsed, 2),
        total_resources=len(resources),
        matched_resources=matched_count,
        unmatched_resource_count=unmatched_count,
        unknown_resource_types=unknown_types,
        skipped_skills=skipped,
        invocations=invocations,
        skills=skills_by_type,
        total_writer_tool_calls=total_w,
        total_reviewer_tool_calls=total_r,
        failed_skills=failed,
        orchestrator_narrative=narrative,
        summary=" · ".join(summary_bits),
    )


async def _run_orchestrator_agent(
    migration_id: str,
    resources: list[dict],
    max_iterations: int,
    confidence_threshold: float,
    tenant_id: str | None,
    aws_connection_id: str | None,
    max_turns: int,
) -> OrchestratorResult:
    t_start = time.perf_counter()

    ctx = MigrationContext(
        migration_id=migration_id,
        tenant_id=tenant_id,
        aws_connection_id=aws_connection_id,
    )
    # Seed the accumulator so tools can append without None-checking.
    ctx.run_state["invocations"] = []

    agent = build_orchestrator_agent(
        max_iterations=max_iterations,
        confidence_threshold=confidence_threshold,
    )

    # Short priming prompt — the detailed workflow lives in the agent's
    # system instructions. This just kicks off the run.
    prime = (
        f"Begin the migration for migration_id={migration_id}. "
        f"Use your tools per the workflow in your instructions. "
        f"Your final message should be a human-readable report."
    )

    try:
        run = await Runner.run(agent, input=prime, context=ctx, max_turns=max_turns)
        narrative = (run.final_output or "").strip() if isinstance(run.final_output, str) else str(run.final_output)
    except Exception as exc:  # noqa: BLE001 — surface in the result
        _log.exception("orchestrator agent failed")
        narrative = f"Orchestrator agent raised an exception: {exc}"

    elapsed = time.perf_counter() - t_start
    return _compose_result(
        migration_id=migration_id,
        max_iterations=max_iterations,
        confidence_threshold=confidence_threshold,
        resources=resources,
        ctx=ctx,
        narrative=narrative,
        elapsed=elapsed,
    )


# ─── Public entry points ──────────────────────────────────────────────────────

async def run_migration(
    migration_id: str,
    resources: list[dict] | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    tenant_id: str | None = None,
    aws_connection_id: str | None = None,
    max_turns: int = 60,
) -> dict:
    """Run the full LLM-driven orchestrator for one migration.

    If ``resources`` isn't supplied, load them from the ``resources`` table
    for this migration's AWS connection. The orchestrator agent will call
    tools to inspect + dispatch; this function just seeds the context,
    invokes the agent, and composes the final OrchestratorResult.

    Args:
        migration_id: UUID string for the migration.
        resources: Optional pre-loaded list of {aws_type, raw_config, …}
            dicts. If None, loaded from the DB.
        max_iterations: Default max writer↔reviewer rounds per skill.
        confidence_threshold: Default early-stop threshold per skill.
        tenant_id / aws_connection_id: Threaded into MigrationContext for
            context-scoped tools.
        max_turns: Safety cap on total orchestrator LLM turns (default 60).

    Returns:
        ``OrchestratorResult.as_dict()``.
    """
    if resources is None:
        resources = _load_resources_sync(migration_id)

    result = await _run_orchestrator_agent(
        migration_id=migration_id,
        resources=resources,
        max_iterations=max_iterations,
        confidence_threshold=confidence_threshold,
        tenant_id=tenant_id,
        aws_connection_id=aws_connection_id,
        max_turns=max_turns,
    )
    return result.as_dict()


async def run_skill(
    skill_type: str,
    input_content: str,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    migration_id: str | None = None,
) -> dict:
    """Run a single skill group standalone (bypasses the orchestrator).

    Used by the single-skill-run API route and the plan orchestrator's
    per-app-group path — the orchestrator agent isn't useful when you
    already know which skill to run and on what input.
    """
    from app.agents.skill_group import get_skill_group

    group = get_skill_group(
        skill_type,
        max_iterations=max_iterations,
        confidence_threshold=confidence_threshold,
    )
    ctx = MigrationContext(migration_id=migration_id) if migration_id else MigrationContext()
    res = await group.run(input_content, ctx)
    return res.as_dict()


def _load_resources_sync(migration_id: str) -> list[dict]:
    """Fetch discovered resources for a migration via a sync engine.

    Called from async code but uses a sync session — short-lived, fine.
    """
    import uuid as _uuid
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from app.db.models import Migration, Resource

    engine = create_engine(settings.DATABASE_URL.replace("+asyncpg", ""), echo=False)
    Session = sessionmaker(bind=engine)
    try:
        with Session() as s:
            mig = s.execute(
                select(Migration).where(Migration.id == _uuid.UUID(migration_id))
            ).scalar_one_or_none()
            if not mig:
                return []
            rows = s.execute(
                select(Resource).where(
                    Resource.aws_connection_id == mig.aws_connection_id
                )
            ).scalars().all()
            return [{
                "id": str(r.id),
                "aws_type": r.aws_type,
                "name": r.name,
                "raw_config": r.raw_config or {},
            } for r in rows]
    finally:
        engine.dispose()
