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
