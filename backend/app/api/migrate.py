"""Migration execution API — Phase 2 Migrate."""

import json
import multiprocessing
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db
from app.db.models import Migration, Tenant

router = APIRouter(prefix="/api", tags=["migrate"])


class ExecuteRequest(BaseModel):
    workload_name: str
    oci_connection_id: str
    variable_overrides: dict | None = None


class ExecutionStatusOut(BaseModel):
    status: Optional[str] = None
    current_step: Optional[str] = None
    started_at: Optional[str] = None
    workload_name: Optional[str] = None
    terraform_plan: Optional[str] = None
    logs: list[str] = []


@router.post("/migrations/{mig_id}/execute", status_code=202)
async def start_execution(
    mig_id: str,
    body: ExecuteRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Start migration execution for a workload.

    Runs terraform init → plan → (wait for approval) → apply in a child process.
    """
    from app.services.migration_executor import execute_migration

    mig_result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = mig_result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    if mig.migrate_status in ("running", "review", "applying"):
        raise HTTPException(status_code=409, detail="Migration is already running")

    # Update migration with execution info
    await db.execute(
        text("""UPDATE migrations SET
            migrate_status = 'running',
            migrate_workload_name = :wname,
            migrate_oci_connection_id = :oci_id,
            migrate_started_at = NOW(),
            migrate_current_step = 'preflight',
            migrate_terraform_plan = NULL,
            migrate_terraform_state = NULL,
            migrate_logs = '[]'::jsonb
        WHERE id = :id"""),
        {
            "id": str(mig.id),
            "wname": body.workload_name,
            "oci_id": body.oci_connection_id,
        },
    )
    await db.commit()

    # Spawn child process
    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(
        target=execute_migration,
        args=(str(mig.id), body.workload_name, body.oci_connection_id, body.variable_overrides),
        daemon=True,
    )
    p.start()

    return {"status": "started", "migration_id": str(mig.id)}


@router.get("/migrations/{mig_id}/execution-status", response_model=ExecutionStatusOut)
async def get_execution_status(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get the current execution status."""
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    return ExecutionStatusOut(
        status=mig.migrate_status,
        current_step=mig.migrate_current_step,
        started_at=str(mig.migrate_started_at) + "Z" if mig.migrate_started_at else None,
        workload_name=mig.migrate_workload_name,
        terraform_plan=mig.migrate_terraform_plan,
        logs=mig.migrate_logs or [],
    )


@router.get("/migrations/{mig_id}/ocm-handoff")
async def get_ocm_handoff(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return what the UI needs to drive the OCM step.

    Bundle:
      prereqs[]                — from ocm_support.yaml handoff_prereqs
      ocm_instance_ids[]       — AWS instance IDs this migration routed
                                  to OCM (from the plan artifacts)
      ocm_migration_ocid       — from terraform state, if apply ran
      ocm_plan_ocid            — same
      aws_secret_ocid          — from the saved OCI connection metadata
                                  if the operator has stored it
      status                   — aggregate: not_ready | ready_to_add_assets
                                  | ready_to_execute | running | succeeded |
                                  failed
    """
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    from app import mappings as _m
    prereqs = _m.ocm_handoff_prereqs()

    # Pull OCM OCIDs out of saved terraform state. terraform_state is
    # persisted as raw JSON (output -json), so parse defensively.
    ocm_migration_ocid = None
    ocm_plan_ocid = None
    tf_state = mig.migrate_terraform_state
    if isinstance(tf_state, dict) and tf_state.get("outputs"):
        outs = tf_state["outputs"]
        mig_out = outs.get("migration_id") or outs.get("migration_ocid") or {}
        plan_out = outs.get("migration_plan_id") or outs.get("migration_plan_ocid") or {}
        if isinstance(mig_out, dict):
            ocm_migration_ocid = mig_out.get("value")
        if isinstance(plan_out, dict):
            ocm_plan_ocid = plan_out.get("value")

    # Scan migrate_logs for the latest [OCM] status line
    last_status_level = None
    for line in reversed(mig.migrate_logs or []):
        if not isinstance(line, str):
            continue
        idx = line.find("[OCM]")
        if idx < 0:
            continue
        payload = line[idx + len("[OCM]"):].strip()
        try:
            last_status_level = json.loads(payload).get("level")
            break
        except (ValueError, TypeError):
            continue

    # Derive an aggregate status for the UI
    if not ocm_migration_ocid:
        agg = "not_ready"       # no OCM resources in this migration
    elif last_status_level in ("running", "succeeded", "failed", "timeout"):
        agg = last_status_level
    elif ocm_plan_ocid:
        # Plan exists but nothing OCM-side has run yet
        agg = "ready_to_add_assets"
    else:
        agg = "not_ready"

    return {
        "status": agg,
        "prereqs": prereqs,
        "ocm_migration_ocid": ocm_migration_ocid,
        "ocm_plan_ocid": ocm_plan_ocid,
        "last_status_level": last_status_level,
    }


class OCMAddAssetsRequest(BaseModel):
    aws_instance_ids: list[str]
    aws_credentials_secret_ocid: str


@router.post("/migrations/{mig_id}/ocm-actions/add-aws-assets")
async def ocm_add_aws_assets(
    mig_id: str,
    body: OCMAddAssetsRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Call OCM's add-aws-assets action for this migration.

    Operator provides the Vault secret OCID that OCM can read to auth
    against AWS (separate from our own AWS connection — OCM discovers on
    its own side). Returns the work-request ID so the UI can poll.
    """
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    from app.services.migration_executor import _oci_config_from_conn
    from app.services.ocm_watcher import add_aws_assets_to_plan
    from app.db.models import OCIConnection

    conn_row = None
    if mig.migrate_oci_connection_id:
        conn_result = await db.execute(
            select(OCIConnection).where(OCIConnection.id == mig.migrate_oci_connection_id)
        )
        conn_row = conn_result.scalar_one_or_none()
    if not conn_row:
        raise HTTPException(status_code=400, detail="Migration has no OCI connection yet; run the Migrate step first.")

    # Resolve the OCM migration OCID from terraform state
    ocm_migration_ocid = None
    tf_state = mig.migrate_terraform_state
    if isinstance(tf_state, dict) and tf_state.get("outputs"):
        mig_out = tf_state["outputs"].get("migration_id") or tf_state["outputs"].get("migration_ocid") or {}
        if isinstance(mig_out, dict):
            ocm_migration_ocid = mig_out.get("value")
    if not ocm_migration_ocid:
        raise HTTPException(status_code=400, detail="No OCM migration OCID in Terraform state. Run terraform apply first.")

    oci_config = _oci_config_from_conn(conn_row)
    result = add_aws_assets_to_plan(
        oci_config=oci_config,
        ocm_migration_ocid=ocm_migration_ocid,
        aws_instance_ids=body.aws_instance_ids,
        aws_credentials_secret_ocid=body.aws_credentials_secret_ocid,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("message", "OCM add-aws-assets failed."))
    return result


@router.post("/migrations/{mig_id}/ocm-actions/execute")
async def ocm_execute_plan(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Trigger OCM to execute the migration plan.

    Kicks off replication + launch inside OCM. Returns the work-request
    ID. The OCMProgressCard polls separately via /ocm-status.
    """
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    from app.services.migration_executor import _oci_config_from_conn
    from app.services.ocm_watcher import execute_migration_plan
    from app.db.models import OCIConnection

    conn_row = None
    if mig.migrate_oci_connection_id:
        conn_result = await db.execute(
            select(OCIConnection).where(OCIConnection.id == mig.migrate_oci_connection_id)
        )
        conn_row = conn_result.scalar_one_or_none()
    if not conn_row:
        raise HTTPException(status_code=400, detail="Migration has no OCI connection yet.")

    ocm_plan_ocid = None
    tf_state = mig.migrate_terraform_state
    if isinstance(tf_state, dict) and tf_state.get("outputs"):
        plan_out = tf_state["outputs"].get("migration_plan_id") or tf_state["outputs"].get("migration_plan_ocid") or {}
        if isinstance(plan_out, dict):
            ocm_plan_ocid = plan_out.get("value")
    if not ocm_plan_ocid:
        raise HTTPException(status_code=400, detail="No OCM migration plan OCID in Terraform state.")

    oci_config = _oci_config_from_conn(conn_row)
    result = execute_migration_plan(oci_config=oci_config, ocm_migration_plan_ocid=ocm_plan_ocid)
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("message", "OCM execute failed."))
    return result


@router.get("/migrations/{mig_id}/ocm-status")
async def get_ocm_status(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return the latest OCM work-request status parsed from migrate_logs.

    The migration_executor writes ``[OCM] <json>`` entries as the watcher
    reports progress; we scan from the end for the most recent one and
    return its parsed contents. Shape mirrors
    ``ocm_watcher.WorkRequestStatus.as_dict()``:

        {
          "migration_ocid": "...",
          "level": "running" | "succeeded" | "failed" | "timeout" | "sdk_unavailable",
          "message": "...",
          "percent_complete": 0.0,
          "work_requests": [...],
          "started_at": "...",
          "updated_at": "..."
        }

    Returns ``{"level": "none"}`` when the migration isn't using OCM or
    hasn't reached the OCM phase yet — the UI hides the progress card in
    that case.
    """
    import json as _json

    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    logs = mig.migrate_logs or []
    for line in reversed(logs):
        if not isinstance(line, str):
            continue
        # Lines are stored as "HH:MM:SS [OCM] <json>" or similar; find the marker.
        idx = line.find("[OCM]")
        if idx < 0:
            continue
        payload = line[idx + len("[OCM]"):].strip()
        try:
            return _json.loads(payload)
        except (ValueError, TypeError):
            continue

    return {"level": "none", "message": "No OCM activity recorded for this migration."}


@router.post("/migrations/{mig_id}/approve-plan")
async def approve_plan(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Approve the terraform plan and proceed to apply."""
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")
    if mig.migrate_status != "review":
        raise HTTPException(status_code=409, detail=f"Cannot approve: status is '{mig.migrate_status}', expected 'review'")

    await db.execute(
        text("UPDATE migrations SET migrate_status = 'approved' WHERE id = :id"),
        {"id": str(mig.id)},
    )
    await db.commit()
    return {"status": "approved"}


@router.post("/migrations/{mig_id}/reject-plan")
async def reject_plan(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Reject the terraform plan and go back to configure."""
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    await db.execute(
        text("UPDATE migrations SET migrate_status = 'rejected' WHERE id = :id"),
        {"id": str(mig.id)},
    )
    await db.commit()
    return {"status": "rejected"}


@router.post("/migrations/{mig_id}/rollback")
async def rollback_migration(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Run terraform destroy to rollback the migration."""
    from app.services.migration_executor import rollback_migration as do_rollback

    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(target=do_rollback, args=(str(mig.id),), daemon=True)
    p.start()

    return {"status": "rolling_back"}


@router.post("/migrations/{mig_id}/test-plan", status_code=202)
async def test_terraform_plan(
    mig_id: str,
    body: ExecuteRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Run terraform init + plan only (no apply). For testing before migration."""
    import multiprocessing
    from app.services.migration_executor import test_plan

    mig_result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = mig_result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    # Fall back to previously stored values for re-tests after fix
    oci_id = body.oci_connection_id or str(mig.migrate_oci_connection_id or "")
    wname = body.workload_name or (mig.migrate_workload_name or "")
    if not oci_id:
        raise HTTPException(status_code=400, detail="No OCI connection selected")
    if not wname:
        raise HTTPException(status_code=400, detail="No workload name")

    await db.execute(
        text("""UPDATE migrations SET
            migrate_status = 'testing',
            migrate_workload_name = :wname,
            migrate_oci_connection_id = :oci_id,
            migrate_started_at = NOW(),
            migrate_current_step = 'init',
            migrate_terraform_plan = NULL,
            migrate_logs = '[]'::jsonb
        WHERE id = :id"""),
        {"id": str(mig.id), "wname": wname, "oci_id": oci_id},
    )
    await db.commit()

    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(
        target=test_plan,
        args=(str(mig.id), wname, oci_id, body.variable_overrides),
        daemon=True,
    )
    p.start()

    return {"status": "testing", "migration_id": str(mig.id)}


@router.post("/migrations/{mig_id}/fix-terraform", status_code=202)
async def fix_terraform_files(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Send terraform errors to LLM to fix .tf files. User-triggered after test failure."""
    import multiprocessing
    from app.services.migration_executor import fix_terraform

    mig_result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = mig_result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    if mig.migrate_status != "test_failed":
        raise HTTPException(status_code=400, detail="Can only fix after a failed test")

    workload_name = mig.migrate_workload_name
    if not workload_name:
        raise HTTPException(status_code=400, detail="No workload name on migration")

    await db.execute(
        text("""UPDATE migrations SET
            migrate_status = 'fixing',
            migrate_current_step = 'llm_fix'
        WHERE id = :id"""),
        {"id": str(mig.id)},
    )
    await db.commit()

    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(
        target=fix_terraform,
        args=(str(mig.id), workload_name),
        daemon=True,
    )
    p.start()

    return {"status": "fixing", "migration_id": str(mig.id)}


@router.get("/migrations/{mig_id}/terraform-state")
async def get_terraform_state(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get the current terraform state."""
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")
    return mig.migrate_terraform_state or {}
