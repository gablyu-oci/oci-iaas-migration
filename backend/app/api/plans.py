"""Migration plan CRUD and workload execution endpoints."""

import asyncio
import json
import multiprocessing
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import cast, or_, select, Text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import get_db
from app.db.models import (
    Migration,
    MigrationPlan,
    PlanPhase,
    Resource,
    TranslationJob,
    Tenant,
    Workload,
    WorkloadResource,
)
from app.api.deps import get_current_tenant
from app.services.migration_orchestrator import generate_plan, build_workload_input

router = APIRouter(prefix="/api", tags=["plans"])

# ---------------------------------------------------------------------------
# Helper: convert UUID (or None) to str (or None)
# ---------------------------------------------------------------------------
_s = lambda v: str(v) if v else None


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------
class ResourceOut(BaseModel):
    id: str
    aws_type: Optional[str] = None
    aws_arn: Optional[str] = None
    name: Optional[str] = None
    status: str = "discovered"
    model_config = {"from_attributes": True}


class WorkloadDetailOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    skill_type: Optional[str] = None
    status: str
    translation_job_id: Optional[str] = None
    phase_id: str
    phase_name: str
    resource_count: int = 0
    resources: list[ResourceOut] = []
    model_config = {"from_attributes": True}


class WorkloadOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    skill_type: Optional[str] = None
    status: str
    translation_job_id: Optional[str] = None
    resource_count: int = 0

    model_config = {"from_attributes": True}


class PhaseOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    order_index: int
    status: str
    workloads: list[WorkloadOut] = []

    model_config = {"from_attributes": True}


class PlanOut(BaseModel):
    id: str
    migration_id: str
    status: str
    generated_at: Optional[str] = None
    summary: Optional[dict] = None
    phases: list[PhaseOut] = []

    model_config = {"from_attributes": True}


class ExecuteOut(BaseModel):
    translation_job_id: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _workload_to_out(w: Workload) -> WorkloadOut:
    return WorkloadOut(
        id=str(w.id),
        name=w.name,
        description=w.description,
        skill_type=w.skill_type,
        status=w.status,
        translation_job_id=_s(w.translation_job_id),
        resource_count=len(w.resources) if w.resources else 0,
    )


def _phase_to_out(p: PlanPhase) -> PhaseOut:
    return PhaseOut(
        id=str(p.id),
        name=p.name,
        description=p.description,
        order_index=p.order_index,
        status=p.status,
        workloads=[_workload_to_out(w) for w in (p.workloads or [])],
    )


def _plan_to_out(plan: MigrationPlan) -> PlanOut:
    return PlanOut(
        id=str(plan.id),
        migration_id=str(plan.migration_id),
        status=plan.status,
        generated_at=str(plan.generated_at) if plan.generated_at else None,
        summary=plan.summary,
        phases=[_phase_to_out(p) for p in (plan.phases or [])],
    )


def _run_job_in_process(translation_job_id: str) -> None:
    """Entry point for child process that executes a translation job.

    Creates a new process group so all descendants (e.g. claude CLI) can be
    cleaned up together if the job is cancelled.
    """
    import os
    import asyncio as _asyncio

    os.setpgrp()
    # Unset CLAUDECODE so the Agent SDK can launch inside this process
    os.environ.pop("CLAUDECODE", None)
    from app.services.job_runner import run_translation_job

    _asyncio.run(run_translation_job({}, translation_job_id))


async def _enqueue_or_run(translation_job_id: str) -> None:
    """Run a translation job in a spawned child process.

    Child processes unset CLAUDECODE so the Agent SDK can launch cleanly,
    and run without a job-level timeout that would conflict with long-running
    synthesis or translation jobs.
    """
    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(
        target=_run_job_in_process, args=(translation_job_id,), daemon=True
    )
    p.start()


async def _load_plan_eager(
    db: AsyncSession, plan_id: uuid.UUID, tenant_id: uuid.UUID
) -> Optional[MigrationPlan]:
    """Load a MigrationPlan with phases -> workloads -> resources eagerly."""
    result = await db.execute(
        select(MigrationPlan)
        .where(
            MigrationPlan.id == plan_id,
            MigrationPlan.tenant_id == tenant_id,
        )
        .options(
            selectinload(MigrationPlan.phases)
            .selectinload(PlanPhase.workloads)
            .selectinload(Workload.resources)
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/migrations/{mig_id}/plan", response_model=PlanOut, status_code=201)
async def generate_migration_plan(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate (or regenerate) a migration plan for the given migration.

    Analyses the migration's discovered resources and creates phases and
    workloads following dependency order:
    networking -> IAM -> data -> compute -> serverless -> CloudFormation.
    """
    # Verify the migration exists and belongs to this tenant
    try:
        mig_uuid = uuid.UUID(mig_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid migration ID format")

    result = await db.execute(
        select(Migration).where(
            Migration.id == mig_uuid,
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    try:
        plan = await generate_plan(mig.id, tenant.id, db)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    # Reload with eager relationships for the response
    loaded = await _load_plan_eager(db, plan.id, tenant.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Failed to load generated plan")

    return _plan_to_out(loaded)


class PlanFromAssessmentRequest(BaseModel):
    assessment_id: str
    app_group_ids: list[str] | None = None
    max_iterations: int = 3  # LLM debate rounds (1-5)


@router.post("/migrations/{mig_id}/plan-from-assessment", status_code=202)
async def generate_plan_from_assessment(
    mig_id: str,
    body: PlanFromAssessmentRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate a migration plan for a workload (app group).

    Spawns a child process that runs the full pipeline:
    resource mapping → translation skills → data migration → runbook → synthesis.
    """
    import multiprocessing

    try:
        mig_uuid = uuid.UUID(mig_id)
        assessment_uuid = uuid.UUID(body.assessment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    if not body.app_group_ids or len(body.app_group_ids) != 1:
        raise HTTPException(status_code=400, detail="Exactly one app_group_id required")

    app_group_id = body.app_group_ids[0]
    try:
        uuid.UUID(app_group_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid app_group_id format")

    result = await db.execute(
        select(Migration).where(Migration.id == mig_uuid, Migration.tenant_id == tenant.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Migration not found")

    max_iters = max(1, min(5, body.max_iterations))

    # Spawn child process for the plan orchestrator
    from app.services.plan_orchestrator import run_workload_plan

    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(
        target=run_workload_plan,
        args=(str(mig_uuid), str(assessment_uuid), app_group_id, str(tenant.id), max_iters),
        daemon=True,
    )
    p.start()

    return {
        "status": "started",
        "migration_id": str(mig_uuid),
        "app_group_id": app_group_id,
        "message": "Plan generation started. Results will appear on the workload.",
    }


@router.post("/app-groups/{app_group_id}/cancel-plan", status_code=200)
async def cancel_workload_plan(
    app_group_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running plan and reset status so it can be re-run."""
    from sqlalchemy import text

    ag_result = await db.execute(
        select(AppGroup).where(
            AppGroup.id == uuid.UUID(app_group_id),
            AppGroup.tenant_id == tenant.id,
        )
    )
    ag = ag_result.scalar_one_or_none()
    if not ag:
        raise HTTPException(status_code=404, detail="App group not found")

    asmt_result = await db.execute(
        select(Assessment).where(Assessment.id == ag.assessment_id)
    )
    asmt = asmt_result.scalar_one_or_none()
    if not asmt:
        raise HTTPException(status_code=404, detail="Assessment not found")

    arts = asmt.dependency_artifacts or {}
    wp = arts.get("workload_plans", {})
    if ag.name in wp:
        del wp[ag.name]
        arts["workload_plans"] = wp
        # Use raw SQL to avoid JSONB mutation issues
        await db.execute(
            text("UPDATE assessments SET dependency_artifacts = :arts WHERE id = :id"),
            {"arts": json.dumps(arts), "id": str(asmt.id)},
        )
        await db.commit()

    return {"status": "cancelled", "app_group_id": app_group_id}


@router.post("/migrations/{mig_id}/synthesize", status_code=202)
async def synthesize_migration(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a migration_synthesis job that reads all completed translation
    job artifacts for the migration and produces a unified Terraform plan."""
    try:
        mig_uuid = uuid.UUID(mig_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid migration ID format")

    result = await db.execute(
        select(Migration).where(
            Migration.id == mig_uuid,
            Migration.tenant_id == tenant.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Migration not found")

    completed_result = await db.execute(
        select(TranslationJob).where(
            TranslationJob.migration_id == mig_uuid,
            TranslationJob.status == "complete",
            TranslationJob.skill_type != "migration_synthesis",
        )
    )
    completed_jobs = list(completed_result.scalars().all())
    if not completed_jobs:
        raise HTTPException(
            status_code=400,
            detail="No completed translation jobs found. Run translation jobs on workloads first.",
        )

    job = TranslationJob(
        tenant_id=tenant.id,
        migration_id=mig_uuid,
        skill_type="migration_synthesis",
        status="queued",
        config={"job_count": len(completed_jobs)},
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await _enqueue_or_run(str(job.id))

    return {"translation_job_id": str(job.id), "job_count": len(completed_jobs)}


@router.get("/migrations/{mig_id}/synthesize/latest")
async def get_latest_synthesis(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return the most recent migration_synthesis job for a migration, or null."""
    try:
        mig_uuid = uuid.UUID(mig_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid migration ID format")

    result = await db.execute(
        select(TranslationJob)
        .where(
            TranslationJob.migration_id == mig_uuid,
            TranslationJob.tenant_id == tenant.id,
            TranslationJob.skill_type == "migration_synthesis",
        )
        .order_by(TranslationJob.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None
    return {
        "id": str(job.id),
        "status": job.status,
        "confidence": job.confidence,
        "current_phase": job.current_phase,
        "created_at": str(job.created_at),
        "completed_at": str(job.completed_at) if job.completed_at else None,
        "errors": job.errors,
    }


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    migration_id: Optional[str] = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List plans, optionally filtered by migration_id."""
    query = (
        select(MigrationPlan)
        .where(MigrationPlan.tenant_id == tenant.id)
        .options(
            selectinload(MigrationPlan.phases)
            .selectinload(PlanPhase.workloads)
            .selectinload(Workload.resources)
        )
    )
    if migration_id:
        query = query.where(MigrationPlan.migration_id == uuid.UUID(migration_id))
    result = await db.execute(query)
    plans = result.scalars().all()
    return [_plan_to_out(p) for p in plans]


@router.get("/plans/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return a plan with its phases and workloads."""
    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid plan ID format")
    plan = await _load_plan_eager(db, plan_uuid, tenant.id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return _plan_to_out(plan)


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_plan(
    plan_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete a plan and cascade-delete its phases, workloads, and workload
    resources."""
    try:
        plan_uuid_parsed = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid plan ID format")
    plan = await _load_plan_eager(db, plan_uuid_parsed, tenant.id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    from sqlalchemy import delete as _delete

    plan_uuid = uuid.UUID(plan_id)

    # Cancel any running or queued translation jobs linked to workloads in this plan
    for phase in plan.phases:
        for workload in phase.workloads:
            if workload.translation_job_id and workload.status in ("running", "queued"):
                job_result = await db.execute(
                    select(TranslationJob).where(TranslationJob.id == workload.translation_job_id)
                )
                job = job_result.scalar_one_or_none()
                if job and job.status in ("running", "queued"):
                    job.status = "failed"
                    job.errors = {"error": "Plan deleted — job cancelled"}

                    # Attempt to cancel the ARQ job in Redis
                    try:
                        import arq
                        from app.config import settings

                        redis = await arq.create_pool(
                            arq.connections.RedisSettings.from_dsn(
                                settings.REDIS_URL
                            )
                        )
                        try:
                            await redis.abort_job(str(workload.translation_job_id))
                        except AttributeError:
                            pass  # abort_job may not exist on this arq version
                        finally:
                            await redis.close()
                    except Exception:
                        pass  # Redis unavailable or other error — continue

    # Delete in FK-safe order: workload_resources -> workloads -> phases -> plan
    for phase in plan.phases:
        for workload in phase.workloads:
            await db.execute(
                _delete(WorkloadResource).where(
                    WorkloadResource.workload_id == workload.id
                )
            )
        await db.execute(
            _delete(Workload).where(Workload.phase_id == phase.id)
        )
    await db.execute(
        _delete(PlanPhase).where(PlanPhase.plan_id == plan_uuid)
    )
    await db.delete(plan)
    await db.commit()


@router.post("/workloads/{workload_id}/execute", response_model=ExecuteOut, status_code=202)
async def execute_workload(
    workload_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create and queue a TranslationJob for the workload.

    Prepares input content from the workload's linked resources, creates a
    TranslationJob record, links it to the workload, and enqueues the job via
    ARQ (Redis) or falls back to a child-process execution.
    """
    # Load workload with its linked resources
    try:
        workload_uuid = uuid.UUID(workload_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workload ID format")

    result = await db.execute(
        select(Workload)
        .where(
            Workload.id == workload_uuid,
            Workload.tenant_id == tenant.id,
        )
        .options(selectinload(Workload.resources))
    )
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="Workload not found")

    if not workload.skill_type:
        raise HTTPException(
            status_code=400,
            detail="Workload has no skill_type assigned and cannot be executed",
        )

    if workload.status == "running":
        raise HTTPException(
            status_code=409,
            detail="Workload is already running",
        )

    # Walk up to the plan to find migration_id and enforce phase dependencies
    phase_result = await db.execute(
        select(PlanPhase).where(PlanPhase.id == workload.phase_id)
    )
    phase = phase_result.scalar_one_or_none()
    migration_id = None
    if phase:
        plan_result = await db.execute(
            select(MigrationPlan)
            .where(MigrationPlan.id == phase.plan_id)
            .options(
                selectinload(MigrationPlan.phases)
                .selectinload(PlanPhase.workloads)
            )
        )
        plan_obj = plan_result.scalar_one_or_none()
        if plan_obj:
            migration_id = plan_obj.migration_id

            # [I7] Phase dependency enforcement: all workloads in preceding
            # phases (lower order_index) must be "complete" before executing
            # a workload in the current phase.
            for prior_phase in plan_obj.phases:
                if prior_phase.order_index < phase.order_index:
                    for pw in prior_phase.workloads:
                        if pw.status != "complete":
                            raise HTTPException(
                                status_code=409,
                                detail=(
                                    f"Cannot execute workload: preceding phase "
                                    f"'{prior_phase.name}' has incomplete workloads. "
                                    f"All workloads in earlier phases must be completed first."
                                ),
                            )

    # Prepare input content from linked resources
    input_content = await build_workload_input(workload.id, db)

    # Resolve the actual resource IDs for this workload (for name lookup)
    resource_ids = [str(wr.resource_id) for wr in (workload.resources or [])]
    first_resource_id = (
        uuid.UUID(resource_ids[0]) if resource_ids else None
    )

    # Create a TranslationJob record
    job = TranslationJob(
        tenant_id=tenant.id,
        skill_type=workload.skill_type,
        input_content=input_content,
        migration_id=migration_id,
        input_resource_id=first_resource_id,
        config={
            "workload_id": str(workload.id),
            "workload_name": workload.name,
            "resource_ids": resource_ids,
        },
        status="queued",
    )
    db.add(job)
    await db.flush()

    # Link workload to this translation job and mark it as running
    workload.translation_job_id = job.id
    workload.status = "running"

    await db.commit()
    await db.refresh(job)

    # Enqueue the job (ARQ or child-process fallback)
    await _enqueue_or_run(str(job.id))

    return ExecuteOut(translation_job_id=str(job.id))


@router.get("/plans/{plan_id}/status", response_model=PlanOut)
async def get_plan_status(
    plan_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return plan status with per-phase and per-workload progress.

    Reconciles workload statuses with their linked TranslationJobs and derives
    phase and plan statuses before returning.
    """
    try:
        plan_uuid_status = uuid.UUID(plan_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid plan ID format")
    plan = await _load_plan_eager(db, plan_uuid_status, tenant.id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # Batch-load all translation jobs for this migration to reconcile workload statuses
    # (handles both workloads linked via translation_job_id AND those linked via resource overlap)
    all_jobs_result = await db.execute(
        select(TranslationJob)
        .where(
            TranslationJob.tenant_id == tenant.id,
            TranslationJob.migration_id == plan.migration_id,
        )
        .order_by(TranslationJob.created_at.desc())
    )
    all_runs: list[TranslationJob] = list(all_jobs_result.scalars().all())

    # Build resource_id -> latest TranslationJob index
    resource_run_index: dict[uuid.UUID, TranslationJob] = {}
    for sr in reversed(all_runs):  # reversed so latest wins
        if sr.input_resource_id:
            resource_run_index[sr.input_resource_id] = sr
        if isinstance(sr.config, dict):
            for rid_str in sr.config.get("resource_ids", []):
                try:
                    resource_run_index[uuid.UUID(rid_str)] = sr
                except (ValueError, AttributeError):
                    pass

    # Build id -> TranslationJob for direct lookup by translation_job_id
    run_by_id: dict[uuid.UUID, TranslationJob] = {sr.id: sr for sr in all_runs}

    # Reconcile workload statuses with their linked TranslationJobs
    dirty = False
    for phase in plan.phases:
        phase_statuses: list[str] = []
        for workload in phase.workloads:
            sr: TranslationJob | None = None
            if workload.translation_job_id:
                sr = run_by_id.get(workload.translation_job_id)
            else:
                # Try to find a matching job via resource overlap
                for wr in (workload.resources or []):
                    candidate = resource_run_index.get(wr.resource_id)
                    if candidate:
                        sr = candidate
                        # Persist the link so future polls are fast
                        workload.translation_job_id = sr.id
                        dirty = True
                        break

            if sr:
                new_status = workload.status
                if sr.status == "complete":
                    new_status = "complete"
                elif sr.status == "failed":
                    new_status = "failed"
                elif sr.status in ("running", "queued"):
                    new_status = "running"

                if new_status != workload.status:
                    workload.status = new_status
                    dirty = True

            phase_statuses.append(workload.status)

        # Derive phase status from its workload statuses
        if phase_statuses and all(s == "complete" for s in phase_statuses):
            new_phase_status = "complete"
        elif any(s == "failed" for s in phase_statuses):
            new_phase_status = "failed"
        elif any(s == "running" for s in phase_statuses):
            new_phase_status = "running"
        else:
            new_phase_status = "pending"

        if new_phase_status != phase.status:
            phase.status = new_phase_status
            dirty = True

    # Derive overall plan status from phases
    all_phase_statuses = [p.status for p in plan.phases]
    if all_phase_statuses and all(s == "complete" for s in all_phase_statuses):
        new_plan_status = "complete"
    elif any(s == "failed" for s in all_phase_statuses):
        new_plan_status = "failed"
    elif any(s == "running" for s in all_phase_statuses):
        new_plan_status = "running"
    else:
        new_plan_status = "draft"

    if new_plan_status != plan.status:
        plan.status = new_plan_status
        dirty = True

    if dirty:
        await db.commit()

    return _plan_to_out(plan)


# ---------------------------------------------------------------------------
# Workload detail & resource endpoints
# ---------------------------------------------------------------------------


@router.get("/workloads/{workload_id}", response_model=WorkloadDetailOut)
async def get_workload_detail(
    workload_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return detailed information about a single workload, including its
    phase name and linked resources."""
    try:
        workload_uuid = uuid.UUID(workload_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workload ID format")

    # Load workload with its WorkloadResource join records
    result = await db.execute(
        select(Workload)
        .where(
            Workload.id == workload_uuid,
            Workload.tenant_id == tenant.id,
        )
        .options(selectinload(Workload.resources))
    )
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="Workload not found")

    # Load the parent phase for the phase_name
    phase_result = await db.execute(
        select(PlanPhase).where(PlanPhase.id == workload.phase_id)
    )
    phase = phase_result.scalar_one_or_none()
    phase_name = phase.name if phase else "Unknown"

    # Resolve actual Resource objects from the WorkloadResource join table
    resource_ids = [wr.resource_id for wr in (workload.resources or [])]
    resources: list[Resource] = []
    if resource_ids:
        res_result = await db.execute(
            select(Resource).where(Resource.id.in_(resource_ids))
        )
        resources = list(res_result.scalars().all())

    return WorkloadDetailOut(
        id=str(workload.id),
        name=workload.name,
        description=workload.description,
        skill_type=workload.skill_type,
        status=workload.status,
        translation_job_id=_s(workload.translation_job_id),
        phase_id=str(workload.phase_id),
        phase_name=phase_name,
        resource_count=len(resources),
        resources=[
            ResourceOut(
                id=str(r.id),
                aws_type=r.aws_type,
                aws_arn=r.aws_arn,
                name=r.name,
                status=r.status,
            )
            for r in resources
        ],
    )


@router.get("/workloads/{workload_id}/resources", response_model=list[ResourceOut])
async def get_workload_resources(
    workload_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return the list of resources attached to a workload."""
    try:
        workload_uuid = uuid.UUID(workload_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workload ID format")

    # Verify workload exists and belongs to this tenant
    result = await db.execute(
        select(Workload).where(
            Workload.id == workload_uuid,
            Workload.tenant_id == tenant.id,
        )
    )
    workload = result.scalar_one_or_none()
    if not workload:
        raise HTTPException(status_code=404, detail="Workload not found")

    # Get resource IDs from the join table
    wr_result = await db.execute(
        select(WorkloadResource.resource_id).where(
            WorkloadResource.workload_id == workload_uuid
        )
    )
    resource_ids = [row[0] for row in wr_result.all()]

    if not resource_ids:
        return []

    # Load the actual Resource rows
    res_result = await db.execute(
        select(Resource).where(Resource.id.in_(resource_ids))
    )
    resources = res_result.scalars().all()

    return [
        ResourceOut(
            id=str(r.id),
            aws_type=r.aws_type,
            aws_arn=r.aws_arn,
            name=r.name,
            status=r.status,
        )
        for r in resources
    ]


@router.get("/phases/{phase_id}/workloads", response_model=list[WorkloadOut])
async def get_phase_workloads(
    phase_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return all workloads belonging to a plan phase."""
    try:
        phase_uuid = uuid.UUID(phase_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid phase ID format")

    # Load phase with workloads eagerly (including their resources for count)
    result = await db.execute(
        select(PlanPhase)
        .where(
            PlanPhase.id == phase_uuid,
            PlanPhase.tenant_id == tenant.id,
        )
        .options(
            selectinload(PlanPhase.workloads)
            .selectinload(Workload.resources)
        )
    )
    phase = result.scalar_one_or_none()
    if not phase:
        raise HTTPException(status_code=404, detail="Phase not found")

    return [_workload_to_out(w) for w in (phase.workloads or [])]
