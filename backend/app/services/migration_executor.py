"""Migration Executor — runs terraform init/plan/apply for a workload.

Executes in a child process. Writes progress to the migrations table
so the frontend can poll status.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path("/tmp/oci-migrations")


def _sync_database_url() -> str:
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def _update_migrate_status(
    session, migration_id: str, *,
    status: str | None = None,
    step: str | None = None,
    log_line: str | None = None,
    terraform_plan: str | None = None,
    terraform_state: dict | None = None,
    started_at: bool = False,
) -> None:
    """Update migration execution progress using raw SQL."""
    row = session.execute(
        text("SELECT migrate_logs FROM migrations WHERE id = :id"),
        {"id": migration_id},
    ).fetchone()
    logs = (row[0] if row and row[0] else []) if row else []

    sets = []
    params: dict = {"id": migration_id}

    if status:
        sets.append("migrate_status = :status")
        params["status"] = status
    if step:
        sets.append("migrate_current_step = :step")
        params["step"] = step
    if log_line:
        logs.append(f"[{time.strftime('%H:%M:%S')}] {log_line}")
        logs = logs[-100:]
        sets.append("migrate_logs = :logs")
        params["logs"] = json.dumps(logs)
    if terraform_plan is not None:
        sets.append("migrate_terraform_plan = :tfplan")
        params["tfplan"] = terraform_plan
    if terraform_state is not None:
        sets.append("migrate_terraform_state = :tfstate")
        params["tfstate"] = json.dumps(terraform_state)
    if started_at:
        sets.append("migrate_started_at = NOW()")

    if sets:
        session.execute(
            text(f"UPDATE migrations SET {', '.join(sets)} WHERE id = :id"),
            params,
        )
        session.commit()


def execute_migration(
    migration_id: str,
    workload_name: str,
    oci_connection_id: str,
    variable_overrides: dict | None = None,
) -> None:
    """Main entry point — runs in a child process."""
    import os
    os.setpgrp()
    os.environ.pop("CLAUDECODE", None)  # Allow Agent SDK nested sessions

    logging.basicConfig(level=logging.INFO)

    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        _run_execution(session, migration_id, workload_name, oci_connection_id, variable_overrides or {})
    except Exception as exc:
        logger.error("Migration execution failed: %s\n%s", exc, traceback.format_exc())
        _update_migrate_status(session, migration_id, status="failed",
                               log_line=f"FATAL: {exc}")
    finally:
        session.close()


def _run_execution(
    session, migration_id: str, workload_name: str,
    oci_connection_id: str, variable_overrides: dict,
) -> None:
    from app.db.models import OCIConnection, Assessment
    from sqlalchemy import select

    _update_migrate_status(session, migration_id, status="running",
                           step="preflight", started_at=True,
                           log_line="Starting migration execution")

    # Load OCI connection
    oci_conn = session.execute(
        select(OCIConnection).where(OCIConnection.id == UUID(oci_connection_id))
    ).scalar_one_or_none()
    if not oci_conn:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line="OCI connection not found")
        return

    # Load plan artifacts
    assessment = session.execute(
        text("SELECT dependency_artifacts FROM assessments WHERE migration_id = :mid ORDER BY created_at DESC LIMIT 1"),
        {"mid": migration_id},
    ).fetchone()
    if not assessment or not assessment[0]:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line="No plan artifacts found")
        return

    arts = assessment[0]
    wp = arts.get("workload_plans", {}).get(workload_name, {})
    if wp.get("status") != "completed":
        _update_migrate_status(session, migration_id, status="failed",
                               log_line=f"Plan for '{workload_name}' is not completed")
        return

    plan_artifacts = wp.get("artifacts", {})
    _update_migrate_status(session, migration_id,
                           log_line=f"Found {len(plan_artifacts)} plan artifacts")

    # ── Step 1: Create workspace ──────────────────────────────────────
    _update_migrate_status(session, migration_id, step="workspace",
                           log_line="Creating Terraform workspace")

    workspace = WORKSPACE_ROOT / migration_id / workload_name.replace(" ", "_")
    workspace.mkdir(parents=True, exist_ok=True)

    # Write .tf files — use synthesis if available, otherwise individual skill files
    # Never mix both (causes duplicate provider/resource declarations)
    has_synthesis = any(k.startswith("synthesis/") and k.endswith(".tf") for k in plan_artifacts)
    tf_count = 0

    # Clean workspace of any previous .tf files
    for f in workspace.glob("*.tf"):
        f.unlink()

    for key, content in plan_artifacts.items():
        if not isinstance(content, str) or not key.endswith(".tf"):
            continue
        if has_synthesis and not key.startswith("synthesis/"):
            continue  # Skip individual skill files when synthesis exists
        fname = key.split("/")[-1]
        # Fix common LLM output issues in HCL
        # 1. Invalid escape sequences: \. should be \\. in HCL regex strings
        import re
        content = re.sub(r'(?<!\\)\\\.', r'\\\\.', content)
        (workspace / fname).write_text(content)
        tf_count += 1

    _update_migrate_status(session, migration_id,
                           log_line=f"Wrote {tf_count} Terraform files to workspace")

    # Write terraform.tfvars with OCI credentials
    tfvars_lines = [
        f'tenancy_ocid     = "{oci_conn.tenancy_ocid}"',
        f'user_ocid        = "{oci_conn.user_ocid}"',
        f'fingerprint      = "{oci_conn.fingerprint}"',
        f'region           = "{oci_conn.region}"',
    ]
    if oci_conn.compartment_id:
        tfvars_lines.append(f'compartment_id   = "{oci_conn.compartment_id}"')

    # Write private key to file
    key_path = workspace / "oci_api_key.pem"
    key_path.write_text(oci_conn.private_key)
    key_path.chmod(0o600)
    tfvars_lines.append(f'private_key_path = "{key_path}"')

    # Apply variable overrides
    for k, v in variable_overrides.items():
        if isinstance(v, str):
            tfvars_lines.append(f'{k} = "{v}"')
        else:
            tfvars_lines.append(f'{k} = {json.dumps(v)}')

    (workspace / "terraform.tfvars").write_text("\n".join(tfvars_lines))

    # Ensure provider block exists
    _ensure_provider_block(workspace, oci_conn)

    # ── Step 2: terraform init ────────────────────────────────────────
    _update_migrate_status(session, migration_id, step="init",
                           log_line="Running terraform init")

    init_result = subprocess.run(
        ["terraform", "init", "-no-color", "-input=false"],
        cwd=str(workspace), capture_output=True, text=True, timeout=300,
    )
    _update_migrate_status(session, migration_id,
                           log_line=f"terraform init exit code: {init_result.returncode}")
    if init_result.returncode != 0:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line=f"terraform init failed:\n{init_result.stderr[:2000]}")
        return

    # ── Step 3: terraform plan ────────────────────────────────────────
    _update_migrate_status(session, migration_id, step="plan",
                           log_line="Running terraform plan")

    plan_result = subprocess.run(
        ["terraform", "plan", "-no-color", "-input=false", "-out=plan.out"],
        cwd=str(workspace), capture_output=True, text=True, timeout=600,
    )

    plan_output = plan_result.stdout + ("\n" + plan_result.stderr if plan_result.stderr else "")
    _update_migrate_status(session, migration_id,
                           terraform_plan=plan_output,
                           log_line=f"terraform plan exit code: {plan_result.returncode}")

    if plan_result.returncode != 0:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line=f"terraform plan failed:\n{plan_result.stderr[:2000]}")
        return

    # ── Step 4: Wait for approval ─────────────────────────────────────
    _update_migrate_status(session, migration_id, status="review", step="review",
                           log_line="Terraform plan ready — waiting for user approval")

    # Poll for approval (check migrate_status changes from 'review' to 'approved')
    deadline = time.time() + 3600  # 1 hour timeout
    while time.time() < deadline:
        row = session.execute(
            text("SELECT migrate_status FROM migrations WHERE id = :id"),
            {"id": migration_id},
        ).fetchone()
        current_status = row[0] if row else None

        if current_status == "approved":
            _update_migrate_status(session, migration_id,
                                   log_line="User approved — proceeding with apply")
            break
        elif current_status == "rejected":
            _update_migrate_status(session, migration_id, status="rejected",
                                   log_line="User rejected the plan")
            return
        elif current_status not in ("review",):
            # Status changed externally (cancelled, etc.)
            return

        time.sleep(5)
    else:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line="Approval timed out after 1 hour")
        return

    # ── Step 5: terraform apply ───────────────────────────────────────
    _update_migrate_status(session, migration_id, status="applying", step="apply",
                           log_line="Running terraform apply")

    apply_result = subprocess.run(
        ["terraform", "apply", "-no-color", "-input=false", "plan.out"],
        cwd=str(workspace), capture_output=True, text=True, timeout=1800,
    )

    _update_migrate_status(session, migration_id,
                           log_line=f"terraform apply exit code: {apply_result.returncode}")

    # Capture terraform apply output in logs
    for line in apply_result.stdout.split("\n")[-20:]:
        if line.strip():
            _update_migrate_status(session, migration_id, log_line=line.strip())

    if apply_result.returncode != 0:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line=f"terraform apply failed:\n{apply_result.stderr[:2000]}")
        # Still try to save state
        _save_terraform_state(session, migration_id, workspace)
        return

    # ── Step 6: Save state + complete ─────────────────────────────────
    _save_terraform_state(session, migration_id, workspace)

    _update_migrate_status(session, migration_id, status="completed", step="complete",
                           log_line="Migration completed successfully")
    logger.info("Migration execution completed for %s", workload_name)


def _ensure_provider_block(workspace: Path, oci_conn) -> None:
    """Ensure there's an OCI provider configuration in the workspace."""
    provider_tf = workspace / "provider.tf"
    if provider_tf.exists():
        return

    provider_tf.write_text(f'''terraform {{
  required_providers {{
    oci = {{
      source = "oracle/oci"
    }}
  }}
}}

provider "oci" {{
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}}

variable "tenancy_ocid" {{}}
variable "user_ocid" {{}}
variable "fingerprint" {{}}
variable "private_key_path" {{}}
variable "region" {{}}
''')


def _save_terraform_state(session, migration_id: str, workspace: Path) -> None:
    """Read and store terraform.tfstate from workspace."""
    state_path = workspace / "terraform.tfstate"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            _update_migrate_status(session, migration_id, terraform_state=state,
                                   log_line="Terraform state saved")
        except Exception as exc:
            _update_migrate_status(session, migration_id,
                                   log_line=f"Failed to save terraform state: {exc}")


def approve_migration(migration_id: str) -> None:
    """Called from the API to approve a terraform plan."""
    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        session.execute(
            text("UPDATE migrations SET migrate_status = 'approved' WHERE id = :id AND migrate_status = 'review'"),
            {"id": migration_id},
        )
        session.commit()
    finally:
        session.close()


def reject_migration(migration_id: str) -> None:
    """Called from the API to reject a terraform plan."""
    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        session.execute(
            text("UPDATE migrations SET migrate_status = 'rejected' WHERE id = :id AND migrate_status = 'review'"),
            {"id": migration_id},
        )
        session.commit()
    finally:
        session.close()


def rollback_migration(migration_id: str) -> None:
    """Run terraform destroy to rollback a migration."""
    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        # Find workspace
        row = session.execute(
            text("SELECT migrate_workload_name FROM migrations WHERE id = :id"),
            {"id": migration_id},
        ).fetchone()
        if not row or not row[0]:
            return

        workload_name = row[0]
        workspace = WORKSPACE_ROOT / migration_id / workload_name.replace(" ", "_")

        # Check if there's anything to destroy
        tfstate_path = workspace / "terraform.tfstate"
        if not workspace.exists() or not tfstate_path.exists():
            _update_migrate_status(session, migration_id, status="rolled_back",
                                   log_line="Nothing to rollback — no terraform state exists")
            return

        _update_migrate_status(session, migration_id, status="rolling_back", step="destroy",
                               log_line="Running terraform destroy for rollback")

        destroy_result = subprocess.run(
            ["terraform", "destroy", "-no-color", "-input=false", "-auto-approve"],
            cwd=str(workspace), capture_output=True, text=True, timeout=1800,
        )

        if destroy_result.returncode == 0:
            _update_migrate_status(session, migration_id, status="rolled_back",
                                   log_line="Rollback completed — all resources destroyed")
            _save_terraform_state(session, migration_id, workspace)
        else:
            _update_migrate_status(session, migration_id, status="failed",
                                   log_line=f"Rollback failed:\n{destroy_result.stderr[:2000]}")
    finally:
        session.close()
