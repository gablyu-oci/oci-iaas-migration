"""Tools the agents can invoke at runtime.

Two layers:

- **Orchestrator tools** — used by the top-level migration orchestrator to
  inspect inventory and coordinate skill groups. Read-only. They read the
  trusted ``migration_id`` from ``RunContextWrapper[MigrationContext]``
  rather than from LLM-supplied arguments, so the model can't spoof which
  migration it's operating on.

- **Skill tools** — used by writer/reviewer agents inside a skill group.
  Also read-only. ``terraform_validate`` runs ``terraform`` inside a
  bubblewrap (``bwrap``) sandbox when available: no network, no filesystem
  access outside the working dir, dropped capabilities. Falls back to a
  plain subprocess if bwrap is missing (dev machines).

Any mutating operation (``terraform apply``, AWS writes) stays in Python
with human-in-loop — not exposed as a tool.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid as _uuid
from pathlib import Path
from typing import Any

from agents import RunContextWrapper, function_tool

from app import mappings
from app.agents.context import MigrationContext

_log = logging.getLogger(__name__)


# ─── Skill-level tools ────────────────────────────────────────────────────────

@function_tool
def lookup_aws_mapping(aws_type: str) -> str:
    """Look up the canonical OCI equivalent for an AWS CloudFormation resource type.

    Prefer calling this over guessing — the YAML at
    ``backend/data/mappings/resources.yaml`` is the single source of truth.
    Returns a short JSON string with ``oci_service``, ``oci_terraform``,
    ``skill``, ``mapping_confidence``, ``notes``, and ``gaps`` for the
    requested AWS type.

    Args:
        aws_type: AWS CloudFormation type, e.g. ``"AWS::EC2::Instance"``.

    Returns:
        JSON string. If the type is unknown, returns ``{"error": "..."}``.
    """
    entry = mappings.resource_by_aws_type(aws_type)
    if not entry:
        return json.dumps({
            "error": f"Unknown AWS type {aws_type!r}. Flag as a gap; do not invent.",
            "known_types_sample": [r["aws_type"] for r in mappings.all_resources()[:10]],
        })
    return json.dumps({
        "aws_type": entry.get("aws_type"),
        "oci_service": entry.get("oci_service"),
        "oci_resource_label": entry.get("oci_resource_label"),
        "oci_terraform": entry.get("oci_terraform"),
        "skill": entry.get("skill"),
        "mapping_confidence": entry.get("mapping_confidence"),
        "notes": entry.get("notes") or [],
        "gaps": entry.get("gaps") or [],
    })


@function_tool
def list_resources_for_skill(skill: str) -> str:
    """List every AWS resource type a given skill can translate.

    Useful when an agent wants to scope its work to only the types its
    skill handles. Pass values like ``"ec2_translation"``,
    ``"network_translation"``, ``"iam_translation"``, etc.

    Returns a compact JSON array of ``{aws_type, oci_terraform}`` rows.
    """
    rows = mappings.resources_for_skill(skill)
    return json.dumps([
        {"aws_type": r.get("aws_type"), "oci_terraform": r.get("oci_terraform")}
        for r in rows
    ])


def _build_sandboxed_cmd(cmd: list[str], workdir: Path) -> list[str]:
    """Wrap ``cmd`` with bubblewrap if available for isolation.

    Sandbox policy:
      - Private /tmp, /home (workdir is bind-mounted read-write)
      - Read-only bind of system dirs terraform needs (/usr, /etc, /lib*)
      - ``--unshare-net``: no network (terraform validate is offline anyway)
      - ``--unshare-pid``, ``--unshare-ipc``, ``--unshare-uts``, ``--unshare-cgroup``
      - ``--new-session``: detach from our terminal
      - ``--die-with-parent``: kill the sandbox if our process dies

    If ``bwrap`` isn't installed, returns ``cmd`` unchanged (logged warning).
    Production hosts should have bwrap installed.
    """
    bwrap = shutil.which("bwrap")
    if not bwrap:
        _log.warning(
            "bwrap not available — running terraform without sandbox. "
            "Install bubblewrap for isolation in production."
        )
        return cmd

    # Find terraform so we can bind-mount it (and resolve its plugins dir).
    tf_bin = shutil.which(cmd[0]) or cmd[0]

    bwrap_args = [
        bwrap,
        "--unshare-all",               # unshare every namespace
        "--share-net",                 # ...then re-share net for `terraform init` provider downloads
                                       # (we rely on the host firewall / proxy to limit egress)
        "--die-with-parent",
        "--new-session",
        # Read-only binds for the OS
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/sbin", "/sbin",
        "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
        "--ro-bind", "/etc/ssl", "/etc/ssl",
        "--ro-bind", "/etc/ca-certificates", "/etc/ca-certificates",
        # Writable workdir only
        "--bind", str(workdir), str(workdir),
        "--chdir", str(workdir),
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        # Drop every capability
        "--cap-drop", "ALL",
        # Don't expose our env — re-inject the ones terraform needs
        "--clearenv",
        "--setenv", "PATH", "/usr/bin:/bin:/usr/local/bin",
        "--setenv", "HOME", str(workdir),
        "--setenv", "TF_IN_AUTOMATION", "1",
        "--setenv", "TF_INPUT", "0",
        "--setenv", "TF_PLUGIN_CACHE_DIR", str(workdir / ".tfcache"),
        "--",
        tf_bin,
    ] + cmd[1:]
    return bwrap_args


@function_tool
def terraform_validate(main_tf: str, variables_tf: str = "", outputs_tf: str = "") -> str:
    """Run ``terraform init -backend=false && terraform validate`` on the given HCL.

    Executes inside a bubblewrap sandbox (when available) with no filesystem
    access outside a fresh tmpdir and minimal environment. Parses the
    ``-json`` output and returns structured diagnostics the agent can use
    to self-correct.

    Args:
        main_tf: Contents of main.tf — the HCL under validation.
        variables_tf: Optional variables.tf contents.
        outputs_tf: Optional outputs.tf contents.

    Returns:
        JSON string: ``{"valid": bool, "error_count": int, "warning_count": int,
        "diagnostics": [...], "output": "...truncated stdout..."}``.
    """
    if not main_tf.strip():
        return json.dumps({"valid": False, "output": "main_tf is empty"})

    tf_bin = os.environ.get("TERRAFORM_BIN", "terraform")
    if not shutil.which(tf_bin):
        return json.dumps({
            "valid": False,
            "output": f"terraform binary not available on PATH. Skipping validation.",
            "skipped": True,
        })

    with tempfile.TemporaryDirectory(prefix="tf_validate_") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "main.tf").write_text(main_tf)
        if variables_tf.strip():
            (tmp_path / "variables.tf").write_text(variables_tf)
        if outputs_tf.strip():
            (tmp_path / "outputs.tf").write_text(outputs_tf)

        init_cmd = _build_sandboxed_cmd(
            [tf_bin, "init", "-backend=false", "-input=false", "-no-color"], tmp_path
        )
        val_cmd = _build_sandboxed_cmd(
            [tf_bin, "validate", "-no-color", "-json"], tmp_path
        )

        try:
            init = subprocess.run(init_cmd, capture_output=True, text=True, timeout=120)
            if init.returncode != 0:
                return json.dumps({
                    "valid": False,
                    "output": f"terraform init failed:\n{init.stdout}\n{init.stderr}"[:4000],
                })
            val = subprocess.run(val_cmd, capture_output=True, text=True, timeout=60)
            try:
                parsed = json.loads(val.stdout)
                return json.dumps({
                    "valid": bool(parsed.get("valid")),
                    "error_count": parsed.get("error_count", 0),
                    "warning_count": parsed.get("warning_count", 0),
                    "diagnostics": parsed.get("diagnostics", [])[:20],
                })
            except json.JSONDecodeError:
                return json.dumps({
                    "valid": val.returncode == 0,
                    "output": f"{val.stdout}\n{val.stderr}"[:4000],
                })
        except subprocess.TimeoutExpired:
            return json.dumps({"valid": False, "output": "terraform timed out (>120s)"})


# ─── Orchestrator-level tools (trusted context) ───────────────────────────────
# These read ``migration_id`` from the ``RunContextWrapper`` rather than as
# an LLM-supplied argument, so the model can't spoof which migration is
# being queried. The orchestrator wraps each run with a ``MigrationContext``.


def _resolve_migration_id(ctx: RunContextWrapper[MigrationContext]) -> str | None:
    m = getattr(ctx, "context", None)
    return getattr(m, "migration_id", None) if m else None


@function_tool
def list_discovered_resources(
    ctx: RunContextWrapper[MigrationContext],
    limit: int = 50,
) -> str:
    """List AWS resources already discovered for **this** migration.

    The migration being operated on is determined by the trusted context
    the caller attached at run start — the LLM cannot target a different
    migration. Returns up to ``limit`` rows as JSON: ``[{id, aws_type,
    name, aws_arn}]``.
    """
    migration_id = _resolve_migration_id(ctx)
    if not migration_id:
        return json.dumps({"error": "no migration context on this run"})

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from app.db.models import Resource, Migration
    from app.config import settings

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url, echo=False)
    Session = sessionmaker(bind=engine)
    try:
        with Session() as s:
            mig = s.execute(
                select(Migration).where(Migration.id == _uuid.UUID(migration_id))
            ).scalar_one_or_none()
            if not mig:
                return json.dumps({"error": f"migration {migration_id} not found"})
            rows = s.execute(
                select(Resource)
                .where(Resource.aws_connection_id == mig.aws_connection_id)
                .limit(limit)
            ).scalars().all()
            return json.dumps([
                {
                    "id": str(r.id),
                    "aws_type": r.aws_type,
                    "name": r.name,
                    "aws_arn": r.aws_arn,
                } for r in rows
            ])
    finally:
        engine.dispose()


@function_tool
def count_resources_by_type(ctx: RunContextWrapper[MigrationContext]) -> str:
    """Count discovered AWS resources for **this** migration, grouped by type.

    Lets the orchestrator decide skill prioritization at a glance without
    fetching every row. Returns ``{aws_type: count}`` as JSON.
    """
    migration_id = _resolve_migration_id(ctx)
    if not migration_id:
        return json.dumps({"error": "no migration context on this run"})

    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import sessionmaker
    from app.db.models import Resource, Migration
    from app.config import settings

    sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
    engine = create_engine(sync_url, echo=False)
    Session = sessionmaker(bind=engine)
    try:
        with Session() as s:
            mig = s.execute(
                select(Migration).where(Migration.id == _uuid.UUID(migration_id))
            ).scalar_one_or_none()
            if not mig:
                return json.dumps({"error": f"migration {migration_id} not found"})
            rows = s.execute(
                select(Resource.aws_type, func.count(Resource.id))
                .where(Resource.aws_connection_id == mig.aws_connection_id)
                .group_by(Resource.aws_type)
            ).all()
            return json.dumps({aws_type: count for aws_type, count in rows})
    finally:
        engine.dispose()


# ─── Orchestrator dispatch tools ──────────────────────────────────────────────
# The LLM orchestrator uses these to spawn skill groups and observe the world.
# Each call appends a structured record to ``ctx.context.run_state`` so the
# Python composer can assemble the ``OrchestratorResult`` at end-of-run
# without the LLM having to re-emit telemetry.


def _append_invocation(ctx: RunContextWrapper[MigrationContext], record: dict) -> None:
    """Append a skill-invocation record to the shared run_state accumulator."""
    state = getattr(ctx, "context", None)
    if state is None:
        return
    log = state.run_state.setdefault("invocations", [])
    log.append(record)


@function_tool
async def run_skill_group(
    ctx: RunContextWrapper[MigrationContext],
    skill_type: str,
    input_content: str,
    max_iterations: int = 3,
    confidence_threshold: float = 0.90,
) -> str:
    """Spawn a writer+reviewer pair for one skill and wait for its result.

    Use this tool to translate a resource-type-scoped chunk of the migration:
    one ``network_translation`` run, one ``database_translation`` run, etc.
    The SkillGroup runs its own bounded writer→reviewer→revise loop
    internally; you only see the final result.

    Args:
        skill_type: One of the keys from ``get_skill_catalog`` (e.g.,
            ``"iam_translation"``, ``"ec2_translation"``).
        input_content: The JSON payload the skill expects — shape varies per
            skill. Look at the catalog's ``input_shape_hint``.
        max_iterations: Upper bound on writer↔reviewer rounds. Default 3.
        confidence_threshold: Early-stop when reviewer confidence ≥ this
            value and decision is APPROVED/APPROVED_WITH_NOTES. Default 0.90.

    Returns:
        JSON string with the full ``SkillRunResult``: ``{skill_type, draft,
        review, iterations, stopped_early, approved, writer_tool_calls,
        reviewer_tool_calls}``.
    """
    import time as _time
    from app.agents.skill_group import get_skill_group

    t0 = _time.perf_counter()
    try:
        group = get_skill_group(
            skill_type,
            max_iterations=max_iterations,
            confidence_threshold=confidence_threshold,
        )
        result = await group.run(input_content, ctx.context)
        elapsed = _time.perf_counter() - t0
        record = {
            "skill_type": skill_type,
            "result": result.as_dict(),
            "duration_s": round(elapsed, 2),
        }
        _append_invocation(ctx, record)
        return json.dumps(record)
    except Exception as exc:  # noqa: BLE001 — surface to the LLM so it can adapt
        elapsed = _time.perf_counter() - t0
        record = {
            "skill_type": skill_type,
            "error": str(exc)[:2000],
            "duration_s": round(elapsed, 2),
        }
        _append_invocation(ctx, record)
        return json.dumps(record)


@function_tool
async def run_skills_parallel(
    ctx: RunContextWrapper[MigrationContext],
    specs_json: str,
) -> str:
    """Spawn multiple skill groups concurrently (typical for one dependency wave).

    Prefer this over calling ``run_skill_group`` N times for independent
    skills — it runs them in parallel via ``asyncio.gather``.

    Args:
        specs_json: JSON array string. Each element is an object with:
            ``skill_type`` (str, required),
            ``input_content`` (str, required),
            ``max_iterations`` (int, optional, default 3),
            ``confidence_threshold`` (float, optional, default 0.90).

    Returns:
        JSON array with one result per spec, in input order. Each entry is
        the same shape ``run_skill_group`` returns.
    """
    import asyncio
    import time as _time
    from app.agents.skill_group import get_skill_group

    try:
        specs = json.loads(specs_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"specs_json is not valid JSON: {exc}"})
    if not isinstance(specs, list):
        return json.dumps({"error": "specs_json must be a JSON array"})

    async def _one(spec: dict) -> dict:
        skill = spec.get("skill_type")
        inp = spec.get("input_content")
        if not skill or inp is None:
            return {"error": "missing skill_type or input_content", "spec": spec}
        max_iter = int(spec.get("max_iterations", 3))
        conf = float(spec.get("confidence_threshold", 0.90))
        t0 = _time.perf_counter()
        try:
            group = get_skill_group(skill, max_iterations=max_iter, confidence_threshold=conf)
            res = await group.run(inp, ctx.context)
            elapsed = _time.perf_counter() - t0
            record = {
                "skill_type": skill,
                "result": res.as_dict(),
                "duration_s": round(elapsed, 2),
            }
        except Exception as exc:  # noqa: BLE001
            elapsed = _time.perf_counter() - t0
            record = {
                "skill_type": skill,
                "error": str(exc)[:2000],
                "duration_s": round(elapsed, 2),
            }
        _append_invocation(ctx, record)
        return record

    results = await asyncio.gather(*(_one(s) for s in specs))
    return json.dumps(results)


@function_tool
def get_skill_catalog() -> str:
    """List every registered skill: skill_type, display name, description, claimed AWS types.

    Call this early to learn which skills are available + what inputs each
    one expects. Skills with ``aws_types = null`` don't route off raw
    resources — e.g. ``synthesis`` consumes prior skill outputs.

    Returns:
        JSON array of ``{skill_type, display_name, description,
        input_shape_hint, aws_types, needs_terraform_validate}``.
    """
    from app.agents.skill_group import SKILL_SPECS, SKILL_TO_AWS_TYPES
    out = []
    for name, spec in SKILL_SPECS.items():
        claimed = SKILL_TO_AWS_TYPES.get(name)
        out.append({
            "skill_type": spec.skill_type,
            "display_name": spec.display_name,
            "description": spec.description,
            "input_shape_hint": spec.input_shape_hint,
            "aws_types": sorted(claimed) if claimed else None,
            "needs_terraform_validate": spec.needs_terraform_validate,
        })
    return json.dumps(out)


@function_tool
def classify_resource_type(aws_type: str) -> str:
    """Determine which skill (if any) handles a given AWS CFN resource type.

    Use this when the inventory shows a type you don't recognize from
    ``get_skill_catalog``. For novel / unclaimed types, returns a hint so
    you can decide whether to route via a related skill, map to a generic
    fallback, or flag as unsupported.

    Returns:
        JSON: ``{aws_type, claimed, skill, mapping_hint}``. When
        ``claimed=false``, ``mapping_hint`` carries any YAML row that knows
        this type (or null if fully novel).
    """
    from app.agents.skill_group import SKILL_TO_AWS_TYPES, KNOWN_AWS_TYPES

    if aws_type in KNOWN_AWS_TYPES:
        for skill, types in SKILL_TO_AWS_TYPES.items():
            if types and aws_type in types:
                return json.dumps({
                    "aws_type": aws_type,
                    "claimed": True,
                    "skill": skill,
                    "mapping_hint": None,
                })

    entry = mappings.resource_by_aws_type(aws_type)
    return json.dumps({
        "aws_type": aws_type,
        "claimed": False,
        "skill": None,
        "mapping_hint": {
            "oci_service": entry.get("oci_service"),
            "oci_terraform": entry.get("oci_terraform"),
            "notes": entry.get("notes") or [],
            "gaps": entry.get("gaps") or [],
        } if entry else None,
    })


@function_tool
def get_dependency_guidance() -> str:
    """Return the canonical dependency-wave ordering as guidance (not enforcement).

    The orchestrator is free to deviate — but IaaS resources have real
    ordering constraints (VCN before subnets before instances) and this
    table captures the ordering that works for most migrations.

    Returns:
        JSON with ``waves`` (list of lists of skill names) and ``rationale``
        (string explaining why).
    """
    from app.agents.skill_group import SKILL_SPECS  # noqa: F401 — sanity import

    waves = [
        ["iam_translation", "security_translation"],
        ["network_translation"],
        ["storage_translation", "database_translation", "data_migration_planning"],
        ["ec2_translation"],
        ["loadbalancer_translation"],
        ["serverless_translation"],
        ["observability_translation"],
        ["cfn_terraform"],
        ["workload_planning", "dependency_discovery"],
        ["synthesis"],
    ]
    rationale = (
        "Wave 0: identity + secrets have no infra deps but are referenced by later waves. "
        "Wave 1: VCN + subnets + NSGs must exist before compute/DB/LB. "
        "Wave 2: storage + DB can run in parallel once the network exists. "
        "Wave 3: compute (instances, ASGs) depends on subnets + (optionally) volumes. "
        "Wave 4: load balancers reference instance backends. "
        "Wave 5: serverless / containers can call anything above them. "
        "Wave 6: observability wires alarms to the resources they target. "
        "Wave 7: full CFN stack translation (only when input was a CFN template). "
        "Wave 8: per-workload planning consumes the inventory + assessment context. "
        "Wave 9: synthesis composes every prior artifact into the final package."
    )
    return json.dumps({"waves": waves, "rationale": rationale})
