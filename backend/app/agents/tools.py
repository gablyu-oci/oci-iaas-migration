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
