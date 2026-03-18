"""ARQ worker task for running skill jobs asynchronously."""

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.db.models import SkillRun, Resource, Artifact, SkillRunInteraction
from app.gateway.model_gateway import get_anthropic_client


async def run_skill_job(ctx, skill_run_id: str):
    """
    ARQ task: execute a skill run.

    Loads the SkillRun from DB, routes to the appropriate skill orchestrator,
    stores artifacts, and updates the run status.

    Creates its own engine so this function is safe to call from a background
    thread with a fresh event loop (no shared connection pool with FastAPI).
    """
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db:
            # 1. Load SkillRun
            result = await db.execute(
                select(SkillRun).where(SkillRun.id == UUID(skill_run_id))
            )
            run = result.scalar_one_or_none()
            if not run:
                return

            # 2. Set status running
            run.status = "running"
            run.started_at = datetime.utcnow()
            await db.commit()

            try:
                # 3. Get input content
                input_content = run.input_content
                if not input_content and run.input_resource_id:
                    res_result = await db.execute(
                        select(Resource).where(Resource.id == run.input_resource_id)
                    )
                    resource = res_result.scalar_one_or_none()
                    if resource and resource.raw_config:
                        input_content = (
                            json.dumps(resource.raw_config)
                            if isinstance(resource.raw_config, dict)
                            else str(resource.raw_config)
                        )

                if not input_content:
                    raise ValueError("No input content available")

                # 4. Build a sync progress callback
                # The skills run synchronously; DB updates happen after the run.
                def progress_callback(phase, iteration, confidence, decision):
                    pass

                # 5. Get client
                client = get_anthropic_client()
                config = run.config or {}
                max_iterations = config.get("max_iterations", 3)

                # 6. Route to skill
                if run.skill_type == "cfn_terraform":
                    from app.skills.cfn_terraform.orchestrator import run as run_cfn
                    result_data = run_cfn(
                        input_content, progress_callback, client, max_iterations
                    )
                elif run.skill_type == "iam_translation":
                    from app.skills.iam_translation.orchestrator import run as run_iam
                    result_data = run_iam(
                        input_content, progress_callback, client, max_iterations
                    )
                elif run.skill_type == "dependency_discovery":
                    from app.skills.dependency_discovery.orchestrator import run as run_dd
                    flowlog = config.get("flowlog_content")
                    result_data = run_dd(
                        input_content, flowlog, progress_callback, client, max_iterations
                    )
                else:
                    raise ValueError(f"Unknown skill type: {run.skill_type}")

                # 7. Store interaction records
                interaction_records = result_data.get("interactions", [])
                for rec in interaction_records:
                    interaction = SkillRunInteraction(
                        skill_run_id=run.id,
                        agent_type=rec.get("agent_type"),
                        model=rec.get("model"),
                        iteration=rec.get("iteration"),
                        tokens_input=rec.get("tokens_input"),
                        tokens_output=rec.get("tokens_output"),
                        tokens_cache_read=rec.get("tokens_cache_read"),
                        tokens_cache_write=rec.get("tokens_cache_write"),
                        cost_usd=rec.get("cost_usd"),
                        decision=rec.get("decision"),
                        confidence=rec.get("confidence"),
                        issues=rec.get("issues"),
                        duration_seconds=rec.get("duration_seconds"),
                    )
                    db.add(interaction)

                # 8. Store artifacts
                artifacts = result_data.get("artifacts", {})
                for filename, content in artifacts.items():
                    content_bytes = (
                        content.encode("utf-8") if isinstance(content, str) else content
                    )
                    if filename.endswith(".tf"):
                        file_type, ct = "terraform_tf", "text/plain"
                    elif filename.endswith(".json"):
                        if "summary" in filename:
                            file_type = "terraform_json"
                        elif "dependency" in filename or "oci_policies" in filename:
                            file_type = "dependency_json"
                        else:
                            file_type = "dependency_json"
                        ct = "application/json"
                    elif filename == "report.md":
                        file_type, ct = "run_report_md", "text/markdown"
                    elif filename == "translation_log.md":
                        file_type, ct = "translation_log_md", "text/markdown"
                    elif filename.endswith(".md"):
                        file_type, ct = "run_report_md", "text/markdown"
                    elif filename.endswith(".mmd"):
                        file_type, ct = "dependency_graph_mmd", "text/plain"
                    elif filename.endswith(".dot"):
                        file_type, ct = "dependency_graph_dot", "text/plain"
                    elif filename.endswith(".tfvars.example") or filename.endswith(".tfvars"):
                        file_type, ct = "terraform_tf", "text/plain"
                    elif filename.endswith(".txt"):
                        file_type, ct = "oci_policies_txt", "text/plain"
                    else:
                        file_type, ct = "other", "application/octet-stream"

                    artifact = Artifact(
                        skill_run_id=run.id,
                        tenant_id=run.tenant_id,
                        file_type=file_type,
                        file_name=filename,
                        content_type=ct,
                        data=content_bytes,
                    )
                    db.add(artifact)

                # 9. Update run
                run.status = "complete"
                run.confidence = result_data.get("confidence", 0.0)
                run.total_cost_usd = result_data.get("cost", 0.0)
                run.current_iteration = result_data.get("iterations", 0)
                run.output = {
                    "decision": result_data.get("decision"),
                    "iterations": result_data.get("iterations"),
                }
                run.completed_at = datetime.utcnow()
                await db.commit()

            except Exception as e:
                run.status = "failed"
                run.errors = {"error": str(e)}
                run.completed_at = datetime.utcnow()
                await db.commit()
                raise
    finally:
        await engine.dispose()


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [run_skill_job]
    redis_settings = None  # Configured from env at import time
    job_timeout = 300
    max_jobs = 10
