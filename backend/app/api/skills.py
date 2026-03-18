"""Skill run CRUD, SSE streaming, and artifact download endpoints."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.db.base import get_db
from app.db.models import (
    Artifact,
    SkillRun,
    SkillRunInteraction,
    Tenant,
)
from app.api.deps import get_current_tenant

router = APIRouter(prefix="/api", tags=["skills"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SkillRunCreate(BaseModel):
    skill_type: str  # cfn_terraform | iam_translation | dependency_discovery
    input_content: Optional[str] = None
    input_resource_id: Optional[str] = None
    migration_id: Optional[str] = None
    config: Optional[dict] = None


class SkillRunOut(BaseModel):
    id: str
    skill_type: str
    status: str
    current_phase: Optional[str]
    current_iteration: int
    confidence: float
    total_cost_usd: float
    output: Optional[dict]
    errors: Optional[dict]
    started_at: Optional[str]
    completed_at: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


class ArtifactOut(BaseModel):
    id: str
    file_type: Optional[str]
    file_name: Optional[str]
    content_type: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


class InteractionOut(BaseModel):
    id: str
    agent_type: Optional[str]
    model: Optional[str]
    iteration: Optional[int]
    tokens_input: Optional[int]
    tokens_output: Optional[int]
    cost_usd: Optional[float]
    decision: Optional[str]
    confidence: Optional[float]
    duration_seconds: Optional[float]
    created_at: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_str(val):
    if val is None:
        return None
    return str(val)


def _run_to_out(r: SkillRun) -> SkillRunOut:
    return SkillRunOut(
        id=str(r.id),
        skill_type=r.skill_type,
        status=r.status,
        current_phase=r.current_phase,
        current_iteration=r.current_iteration,
        confidence=r.confidence,
        total_cost_usd=r.total_cost_usd,
        output=r.output,
        errors=r.errors,
        started_at=_to_str(r.started_at),
        completed_at=_to_str(r.completed_at),
        created_at=str(r.created_at),
    )


def _validate_input(content: str) -> str:
    """Validate that input_content is valid YAML or JSON."""
    # Try JSON first
    try:
        json.loads(content)
        return content
    except (json.JSONDecodeError, TypeError):
        pass
    # Try YAML
    try:
        yaml.safe_load(content)
        return content
    except yaml.YAMLError:
        pass
    raise ValueError("input_content must be valid JSON or YAML")


async def _enqueue_or_run(skill_run_id: str):
    """
    Try to enqueue via ARQ/Redis. If Redis is unavailable, run the job
    directly in a background task (for development without Redis).
    """
    try:
        import arq
        from app.config import settings

        redis = await arq.create_pool(
            arq.connections.RedisSettings.from_dsn(settings.REDIS_URL)
        )
        await redis.enqueue_job("run_skill_job", skill_run_id)
        await redis.close()
    except Exception:
        # Redis not available -- run directly in a background thread
        import threading

        def _run_in_thread():
            import asyncio as _asyncio

            async def _inner():
                from app.services.skill_runner import run_skill_job
                await run_skill_job({}, skill_run_id)

            _asyncio.run(_inner())

        t = threading.Thread(target=_run_in_thread, daemon=True)
        t.start()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/skill-runs", response_model=SkillRunOut, status_code=201)
async def create_skill_run(
    body: SkillRunCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new skill run and enqueue it for processing."""
    # Validate skill_type
    valid_types = {"cfn_terraform", "iam_translation", "dependency_discovery"}
    if body.skill_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid skill_type. Must be one of: {', '.join(sorted(valid_types))}",
        )

    # Validate input
    if body.input_content:
        try:
            _validate_input(body.input_content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    run = SkillRun(
        tenant_id=tenant.id,
        skill_type=body.skill_type,
        input_content=body.input_content,
        input_resource_id=(
            uuid.UUID(body.input_resource_id) if body.input_resource_id else None
        ),
        migration_id=(
            uuid.UUID(body.migration_id) if body.migration_id else None
        ),
        config=body.config,
        status="queued",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Enqueue the job
    await _enqueue_or_run(str(run.id))

    return _run_to_out(run)


@router.get("/skill-runs", response_model=list[SkillRunOut])
async def list_skill_runs(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SkillRun)
        .where(SkillRun.tenant_id == tenant.id)
        .order_by(SkillRun.created_at.desc())
    )
    rows = result.scalars().all()
    return [_run_to_out(r) for r in rows]


@router.get("/skill-runs/{run_id}", response_model=SkillRunOut)
async def get_skill_run(
    run_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SkillRun).where(
            SkillRun.id == uuid.UUID(run_id),
            SkillRun.tenant_id == tenant.id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Skill run not found")
    return _run_to_out(run)


@router.get("/skill-runs/{run_id}/stream")
async def stream_skill_run(
    run_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """SSE stream that polls the DB every second and yields status updates."""

    # Verify ownership
    result = await db.execute(
        select(SkillRun).where(
            SkillRun.id == uuid.UUID(run_id),
            SkillRun.tenant_id == tenant.id,
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Skill run not found")

    run_uuid = uuid.UUID(run_id)
    started = datetime.now(timezone.utc)

    async def event_generator():
        """Yield SSE events by polling the skill_run row."""
        from app.db.base import async_session as session_factory

        while True:
            async with session_factory() as poll_db:
                res = await poll_db.execute(
                    select(SkillRun).where(SkillRun.id == run_uuid)
                )
                current = res.scalar_one_or_none()
                if not current:
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": "Run not found"}),
                    }
                    return

                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                payload = {
                    "status": current.status,
                    "phase": current.current_phase,
                    "iteration": current.current_iteration,
                    "confidence": current.confidence,
                    "elapsed_secs": round(elapsed, 1),
                }

                yield {
                    "event": "status",
                    "data": json.dumps(payload),
                }

                if current.status in ("complete", "failed"):
                    # Send final event with output/errors
                    final = {
                        "status": current.status,
                        "output": current.output,
                        "errors": current.errors,
                        "confidence": current.confidence,
                        "cost": current.total_cost_usd,
                    }
                    yield {
                        "event": "done",
                        "data": json.dumps(final),
                    }
                    return

            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/skill-runs/{run_id}/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(
    run_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    # Verify ownership
    run_result = await db.execute(
        select(SkillRun).where(
            SkillRun.id == uuid.UUID(run_id),
            SkillRun.tenant_id == tenant.id,
        )
    )
    if not run_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Skill run not found")

    result = await db.execute(
        select(Artifact).where(Artifact.skill_run_id == uuid.UUID(run_id))
    )
    rows = result.scalars().all()
    return [
        ArtifactOut(
            id=str(a.id),
            file_type=a.file_type,
            file_name=a.file_name,
            content_type=a.content_type,
            created_at=str(a.created_at),
        )
        for a in rows
    ]


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Download an artifact as a file attachment."""
    result = await db.execute(
        select(Artifact).where(
            Artifact.id == uuid.UUID(artifact_id),
            Artifact.tenant_id == tenant.id,
        )
    )
    artifact = result.scalar_one_or_none()
    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    from io import BytesIO

    content = artifact.data or b""
    filename = artifact.file_name or f"artifact-{artifact_id}"

    return StreamingResponse(
        BytesIO(content),
        media_type=artifact.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
