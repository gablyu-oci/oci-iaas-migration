"""ARQ worker task for running translation jobs asynchronously."""

import asyncio
import json
import re
import threading
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import settings
from app.db.models import TranslationJob, Resource, Artifact, TranslationJobInteraction, Migration
from app.gateway.model_gateway import get_anthropic_client


def _extract_input_content(raw_config: dict | list, skill_type: str) -> str:
    """
    Convert a resource's raw_config into the string the skill orchestrator expects.

    CloudFormation stacks are stored as {"template": "<yaml/json>", "status": "..."}
    because the extractor wraps the template body. For cfn_terraform we unwrap and
    pass the template body directly so the orchestrator sees a proper Resources section.
    """
    if skill_type == "cfn_terraform" and isinstance(raw_config, dict):
        template = raw_config.get("template")
        if template and isinstance(template, str) and template.strip():
            return template
    if isinstance(raw_config, dict):
        return json.dumps(raw_config)
    return json.dumps(raw_config)


def _build_network_input(resources: list) -> str:
    """
    Aggregate multiple network resources (VPC, subnets, security groups, etc.)
    into the VPC-level JSON structure the network_translation orchestrator expects:
    { vpc_id, cidr_block, subnets: [...], security_groups: [...], route_tables: [...],
      internet_gateways: [...], nat_gateways: [...] }
    """
    aggregated: dict = {
        "subnets": [],
        "security_groups": [],
        "network_interfaces": [],
        "route_tables": [],
        "internet_gateways": [],
        "nat_gateways": [],
    }
    seen_subnets: set = set()

    for res in resources:
        rc = res.raw_config if hasattr(res, "raw_config") else res
        if not isinstance(rc, dict):
            continue
        aws_type = getattr(res, "aws_type", "") if hasattr(res, "aws_type") else ""

        if aws_type == "AWS::EC2::VPC":
            if not aggregated.get("vpc_id") and rc.get("vpc_id"):
                aggregated["vpc_id"] = rc["vpc_id"]
            if not aggregated.get("cidr_block") and rc.get("cidr_block"):
                aggregated["cidr_block"] = rc["cidr_block"]
            if not aggregated.get("name") and rc.get("name"):
                aggregated["name"] = rc["name"]
            # Merge embedded subnets
            for s in rc.get("subnets", []):
                sid = s.get("subnet_id")
                if sid and sid not in seen_subnets:
                    seen_subnets.add(sid)
                    aggregated["subnets"].append(s)
            for rt in rc.get("route_tables", []):
                aggregated["route_tables"].append(rt)
            for igw in rc.get("internet_gateways", []):
                aggregated["internet_gateways"].append(igw)
            for nat in rc.get("nat_gateways", []):
                aggregated["nat_gateways"].append(nat)

        elif aws_type == "AWS::EC2::Subnet":
            sid = rc.get("subnet_id")
            if sid and sid not in seen_subnets:
                seen_subnets.add(sid)
                aggregated["subnets"].append(rc)
            # Extract vpc_id if not yet set
            if not aggregated.get("vpc_id") and rc.get("vpc_id"):
                aggregated["vpc_id"] = rc["vpc_id"]

        elif aws_type == "AWS::EC2::SecurityGroup":
            aggregated["security_groups"].append(rc)
            if not aggregated.get("vpc_id") and rc.get("vpc_id"):
                aggregated["vpc_id"] = rc["vpc_id"]

        elif aws_type == "AWS::EC2::NetworkInterface":
            aggregated.setdefault("network_interfaces", []).append(rc)

        elif aws_type == "AWS::EC2::RouteTable":
            aggregated["route_tables"].append(rc)

        elif aws_type in ("AWS::EC2::InternetGateway", "AWS::EC2::VPCGatewayAttachment"):
            aggregated["internet_gateways"].append(rc)

        elif aws_type == "AWS::EC2::NatGateway":
            aggregated["nat_gateways"].append(rc)

    return json.dumps(aggregated)


def _build_ec2_input(resources: list) -> str:
    """
    Aggregate EC2 instance (and optional ASG) resources into the format
    the ec2_translation orchestrator expects:
    { "instances": [...], "auto_scaling_groups": [...] }
    """
    instances = []
    asgs = []
    for res in resources:
        rc = res.raw_config if hasattr(res, "raw_config") else res
        if not isinstance(rc, dict):
            continue
        aws_type = getattr(res, "aws_type", "") if hasattr(res, "aws_type") else ""
        if aws_type == "AWS::AutoScaling::AutoScalingGroup":
            asgs.append(rc)
        else:
            instances.append(rc)
    return json.dumps({"instances": instances, "auto_scaling_groups": asgs})


def _build_database_input(resources: list) -> str:
    """
    Aggregate RDS instance resources into the format the database_translation
    orchestrator expects: { "db_instances": [...] }
    """
    db_instances = [
        (res.raw_config if hasattr(res, "raw_config") else res)
        for res in resources
        if isinstance(res.raw_config if hasattr(res, "raw_config") else res, dict)
    ]
    return json.dumps({"db_instances": db_instances})


def _build_storage_input(resources: list) -> str:
    """
    Aggregate EBS volume resources into the format the storage_translation
    orchestrator expects: { "volumes": [...] }
    """
    volumes = [
        (res.raw_config if hasattr(res, "raw_config") else res)
        for res in resources
        if isinstance(res.raw_config if hasattr(res, "raw_config") else res, dict)
    ]
    return json.dumps({"volumes": volumes})


def _build_loadbalancer_input(resources: list) -> str:
    """
    Aggregate ELB resources into the format the loadbalancer_translation
    orchestrator expects: { "load_balancers": [...] }
    """
    lbs = [
        (res.raw_config if hasattr(res, "raw_config") else res)
        for res in resources
        if isinstance(res.raw_config if hasattr(res, "raw_config") else res, dict)
    ]
    return json.dumps({"load_balancers": lbs})


async def _build_synthesis_input_async(
    db: AsyncSession, migration_id: UUID
) -> str | None:
    """Load all completed translation job artifacts for a migration and build
    the JSON input the synthesis orchestrator expects."""
    from app.db.models import Artifact, Migration as MigModel

    mig_result = await db.execute(
        select(MigModel).where(MigModel.id == migration_id)
    )
    migration = mig_result.scalar_one_or_none()
    migration_name = migration.name if migration else "Unknown"

    jobs_result = await db.execute(
        select(TranslationJob).where(
            TranslationJob.migration_id == migration_id,
            TranslationJob.status == "complete",
            TranslationJob.skill_type != "migration_synthesis",
        ).order_by(TranslationJob.created_at.asc())
    )
    jobs = list(jobs_result.scalars().all())
    if not jobs:
        return None

    job_data = []
    for job in jobs:
        art_result = await db.execute(
            select(Artifact).where(Artifact.translation_job_id == job.id)
        )
        artifacts = list(art_result.scalars().all())
        artifact_dict: dict[str, str] = {}
        for art in artifacts:
            if not art.file_name or not art.data:
                continue
            fname = art.file_name
            # Include .tf files and migration-guide .md files; skip internal logs
            if fname.endswith(".tf") or (
                fname.endswith(".md")
                and fname not in ("ORCHESTRATION-SUMMARY.md",)
                and not fname.startswith("terraform-validate")
            ):
                content = art.data.decode("utf-8", errors="replace").strip()
                if content and content not in (
                    "# main.tf", "# variables.tf", "# outputs.tf",
                    "# terraform.tfvars.example",
                ):
                    artifact_dict[fname] = content
        if artifact_dict:
            job_data.append({"skill_type": job.skill_type, "artifacts": artifact_dict})

    if not job_data:
        return None

    return json.dumps({
        "migration_id":   str(migration_id),
        "migration_name": migration_name,
        "jobs":           job_data,
    })


async def _load_all_job_resources(db: AsyncSession, job: TranslationJob) -> list:
    """Load all Resource objects referenced by a job (deduped)."""
    all_ids: list[UUID] = []
    if job.input_resource_id:
        all_ids.append(job.input_resource_id)
    if job.config and job.config.get("resource_ids"):
        for rid_str in job.config["resource_ids"]:
            try:
                rid = UUID(rid_str)
                if rid not in all_ids:
                    all_ids.append(rid)
            except (ValueError, TypeError):
                pass
    resources = []
    for rid in all_ids:
        r_result = await db.execute(select(Resource).where(Resource.id == rid))
        r = r_result.scalar_one_or_none()
        if r and r.raw_config:
            resources.append(r)
    return resources


async def _update_batch_resource_statuses(db: AsyncSession, job: TranslationJob, new_status: str) -> None:
    """Update status of all resources referenced by this translation job."""
    resource_ids: list[UUID] = []
    if job.input_resource_id:
        resource_ids.append(job.input_resource_id)
    if job.config and job.config.get("resource_ids"):
        for rid_str in job.config["resource_ids"]:
            try:
                rid = UUID(rid_str)
                if rid not in resource_ids:
                    resource_ids.append(rid)
            except (ValueError, TypeError):
                pass
    if resource_ids:
        await db.execute(
            update(Resource).where(Resource.id.in_(resource_ids)).values(status=new_status)
        )


async def run_translation_job(ctx, translation_job_id: str):
    """
    ARQ task: execute a translation job.

    Loads the TranslationJob from DB, routes to the appropriate skill orchestrator,
    stores artifacts, and updates the job status.

    Creates its own engine so this function is safe to call from a background
    thread with a fresh event loop (no shared connection pool with FastAPI).
    """
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db:
            # 1. Load TranslationJob
            result = await db.execute(
                select(TranslationJob).where(TranslationJob.id == UUID(translation_job_id))
            )
            job = result.scalar_one_or_none()
            if not job:
                return

            # 2. Set status running; mirror to all batched resources
            job.status = "running"
            job.started_at = datetime.utcnow()
            await _update_batch_resource_statuses(db, job, "running")
            await db.commit()

            try:
                # 3. Get input content
                input_content = job.input_content

                # Skills with multi-resource aggregation: always collect all referenced
                # resources and build a skill-specific composite input JSON.
                _AGGREGATED_SKILLS = {
                    "network_translation":     _build_network_input,
                    "ec2_translation":         _build_ec2_input,
                    "database_translation":    _build_database_input,
                    "loadbalancer_translation": _build_loadbalancer_input,
                    "storage_translation":     _build_storage_input,
                }
                if not input_content and job.skill_type in _AGGREGATED_SKILLS:
                    all_resources = await _load_all_job_resources(db, job)
                    if all_resources:
                        builder = _AGGREGATED_SKILLS[job.skill_type]
                        input_content = builder(all_resources)

                # Try single resource via input_resource_id
                if not input_content and job.input_resource_id:
                    res_result = await db.execute(
                        select(Resource).where(Resource.id == job.input_resource_id)
                    )
                    resource = res_result.scalar_one_or_none()
                    if resource and resource.raw_config:
                        input_content = _extract_input_content(resource.raw_config, job.skill_type)

                # Fallback: load content from config.resource_ids (multi-resource groups)
                if not input_content and job.config and job.config.get("resource_ids"):
                    configs = []
                    for rid_str in job.config["resource_ids"]:
                        res_result = await db.execute(
                            select(Resource).where(Resource.id == UUID(rid_str))
                        )
                        res = res_result.scalar_one_or_none()
                        if res and res.raw_config:
                            configs.append(res.raw_config)
                    if configs:
                        raw = configs[0] if len(configs) == 1 else configs
                        input_content = _extract_input_content(raw, job.skill_type)

                if not input_content and job.skill_type != "migration_synthesis":
                    raise ValueError("No input content available")

                # 4. Build a sync progress callback that updates current_phase in the DB
                # Uses asyncpg directly in a fire-and-forget thread so the orchestrator
                # isn't blocked, but the SSE stream shows live phase updates.
                _db_url = settings.DATABASE_URL
                _job_id = translation_job_id

                def _write_phase(phase, iteration, confidence):
                    """Fire-and-forget DB phase update via asyncpg."""
                    m = re.match(
                        r'postgresql\+asyncpg://([^:]+):([^@]+)@([^:/]+):(\d+)/(.+)',
                        _db_url,
                    )
                    if not m:
                        return
                    user, password, host, port, db_name = m.groups()

                    async def _do():
                        import asyncpg
                        conn = await asyncpg.connect(
                            user=user, password=password,
                            host=host, port=int(port), database=db_name,
                        )
                        try:
                            if confidence is not None:
                                await conn.execute(
                                    "UPDATE translation_jobs SET current_phase=$1, "
                                    "current_iteration=$2, confidence=$3 WHERE id=$4",
                                    phase, iteration, float(confidence), UUID(_job_id),
                                )
                            else:
                                await conn.execute(
                                    "UPDATE translation_jobs SET current_phase=$1, "
                                    "current_iteration=$2 WHERE id=$3",
                                    phase, iteration, UUID(_job_id),
                                )
                        finally:
                            await conn.close()

                    def _thread():
                        loop = asyncio.new_event_loop()
                        try:
                            loop.run_until_complete(_do())
                        except Exception:
                            pass
                        finally:
                            loop.close()

                    t = threading.Thread(target=_thread, daemon=True)
                    t.start()

                def progress_callback(phase, iteration, confidence, decision):
                    _write_phase(phase, iteration, confidence)

                # 5. Get client
                client = get_anthropic_client()
                config = job.config or {}
                max_iterations = config.get("max_iterations", 3)

                # 6. Route to skill
                if job.skill_type == "cfn_terraform":
                    from app.skills.cfn_terraform.orchestrator import run as run_cfn
                    result_data = run_cfn(
                        input_content, progress_callback, client, max_iterations
                    )
                elif job.skill_type == "iam_translation":
                    from app.skills.iam_translation.orchestrator import run as run_iam
                    result_data = run_iam(
                        input_content, progress_callback, client, max_iterations
                    )
                elif job.skill_type == "dependency_discovery":
                    from app.skills.dependency_discovery.orchestrator import run as run_dd
                    flowlog = config.get("flowlog_content")
                    result_data = run_dd(
                        input_content, flowlog, progress_callback, client, max_iterations
                    )
                elif job.skill_type == "network_translation":
                    from app.skills.network_translation.orchestrator import run as run_net
                    result_data = run_net(
                        input_content, progress_callback, client, max_iterations
                    )
                elif job.skill_type == "ec2_translation":
                    from app.skills.ec2_translation.orchestrator import run as run_ec2
                    result_data = run_ec2(
                        input_content, progress_callback, client, max_iterations
                    )
                elif job.skill_type == "database_translation":
                    from app.skills.database_translation.orchestrator import run as run_db
                    result_data = run_db(
                        input_content, progress_callback, client, max_iterations
                    )
                elif job.skill_type == "loadbalancer_translation":
                    from app.skills.loadbalancer_translation.orchestrator import run as run_lb
                    result_data = run_lb(
                        input_content, progress_callback, client, max_iterations
                    )
                elif job.skill_type == "storage_translation":
                    from app.skills.storage_translation.orchestrator import run as run_storage
                    result_data = run_storage(
                        input_content, progress_callback, client, max_iterations
                    )
                elif job.skill_type == "data_migration_planning":
                    from app.skills.data_migration.orchestrator import run as run_data_mig
                    result_data = run_data_mig(
                        input_content, progress_callback, client, max_iterations
                    )
                elif job.skill_type == "workload_planning":
                    from app.skills.workload_planning.orchestrator import run as run_wp
                    result_data = run_wp(
                        input_content, progress_callback, client, max_iterations
                    )
                elif job.skill_type == "migration_synthesis":
                    if not input_content and job.migration_id:
                        input_content = await _build_synthesis_input_async(db, job.migration_id)
                    if not input_content:
                        raise ValueError("No completed translation job artifacts found to synthesize")
                    from app.skills.synthesis.orchestrator import run as run_synthesis
                    result_data = run_synthesis(
                        input_content, progress_callback, client, max_iterations
                    )
                else:
                    raise ValueError(f"Unknown skill type: {job.skill_type}")

                # 7. Store interaction records
                interaction_records = result_data.get("interactions", [])
                for rec in interaction_records:
                    interaction = TranslationJobInteraction(
                        translation_job_id=job.id,
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
                    elif filename in ("report.md", "migration-guide.md"):
                        file_type, ct = "run_report_md", "text/markdown"
                    elif filename in ("translation_log.md", "ORCHESTRATION-SUMMARY.md"):
                        file_type, ct = "translation_log_md", "text/markdown"
                    elif filename == "migration-runbook.md":
                        file_type, ct = "migration_runbook_md", "text/markdown"
                    elif filename == "anomaly-analysis.md":
                        file_type, ct = "anomaly_analysis_md", "text/markdown"
                    elif filename == "README.md":
                        file_type, ct = "readme_md", "text/markdown"
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
                        translation_job_id=job.id,
                        tenant_id=job.tenant_id,
                        file_type=file_type,
                        file_name=filename,
                        content_type=ct,
                        data=content_bytes,
                    )
                    db.add(artifact)

                # 9. Update job
                job.status = "complete"
                job.confidence = result_data.get("confidence", 0.0)
                job.total_cost_usd = result_data.get("cost", 0.0)
                job.current_iteration = result_data.get("iterations", 0)
                job.output = {
                    "decision": result_data.get("decision"),
                    "iterations": result_data.get("iterations"),
                }
                job.completed_at = datetime.utcnow()
                await _update_batch_resource_statuses(db, job, "migrated")
                await db.commit()

            except Exception as e:
                job.status = "failed"
                job.errors = {"error": str(e)}
                job.completed_at = datetime.utcnow()
                await _update_batch_resource_statuses(db, job, "failed")
                await db.commit()
                raise
    finally:
        await engine.dispose()


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [run_translation_job]
    redis_settings = None  # Configured from env at import time
    job_timeout = 300
    max_jobs = 10
