"""Workload Plan Orchestrator.

When "Generate Plan" is clicked for a workload, this orchestrator:
1. Inspects the workload's resources
2. Picks which skills to run based on resource types
3. Runs resource mapping (deterministic + LLM review)
4. Runs all translation skills (Enhancement → Review → Fix each)
5. Runs data migration planning if databases detected
6. Runs workload planning (runbook + anomaly analysis)
7. Synthesizes everything into a unified plan

Runs in a child process (like assessment_runner) to avoid blocking the API.
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.models import (
    AppGroup,
    AppGroupMember,
    Assessment,
    MigrationPlan,
    PlanPhase,
    Resource,
    ResourceAssessment,
    Workload,
    WorkloadResource,
    TranslationJob,
)

logger = logging.getLogger(__name__)

# Skill routing: AWS type pattern → skill_type
_TYPE_TO_SKILL: list[tuple[str, str]] = [
    ("EC2::VPC", "network_translation"),
    ("EC2::Subnet", "network_translation"),
    ("EC2::SecurityGroup", "network_translation"),
    ("EC2::NetworkInterface", "network_translation"),
    ("EC2::Instance", "ec2_translation"),
    ("AutoScaling", "ec2_translation"),
    ("EC2::Volume", "storage_translation"),
    ("RDS", "database_translation"),
    ("Aurora", "database_translation"),
    ("ElasticLoadBalancing", "loadbalancer_translation"),
    ("LoadBalancer", "loadbalancer_translation"),
    ("CloudFormation::Stack", "cfn_terraform"),
    ("IAM::Policy", "iam_translation"),
    ("IAM::Role", "iam_translation"),
]

# Skills that take aggregated resource input (multiple resources as JSON array)
_AGGREGATED_SKILLS = {
    "network_translation", "ec2_translation", "database_translation",
    "loadbalancer_translation", "storage_translation",
}


def _sync_database_url() -> str:
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def _skill_for_type(aws_type: str) -> str | None:
    for pattern, skill in _TYPE_TO_SKILL:
        if pattern in (aws_type or ""):
            return skill
    return None


def _build_skill_input(skill_type: str, resources: list[dict]) -> str:
    """Build the JSON input string for a skill from resource raw_configs.

    Each skill expects a specific wrapper format matching what the
    job_runner builders produce.
    """
    raw_configs = [r.get("raw_config") or {} for r in resources]

    if skill_type == "network_translation":
        # { vpc_id, cidr_block, subnets: [...], security_groups: [...], ... }
        agg: dict = {"subnets": [], "security_groups": [], "network_interfaces": [],
                     "route_tables": [], "internet_gateways": [], "nat_gateways": []}
        for r in resources:
            rc = r.get("raw_config") or {}
            at = r.get("aws_type", "")
            if "VPC" in at and "Subnet" not in at:
                agg.update({k: rc.get(k, v) for k, v in [("vpc_id", ""), ("cidr_block", ""), ("name", "")] if rc.get(k)})
                for s in rc.get("subnets", []): agg["subnets"].append(s)
            elif "Subnet" in at: agg["subnets"].append(rc)
            elif "SecurityGroup" in at: agg["security_groups"].append(rc)
            elif "NetworkInterface" in at: agg["network_interfaces"].append(rc)
        return json.dumps(agg, indent=2)

    if skill_type == "ec2_translation":
        instances, asgs = [], []
        for r in resources:
            if "AutoScaling" in r.get("aws_type", ""): asgs.append(r.get("raw_config") or {})
            else: instances.append(r.get("raw_config") or {})
        return json.dumps({"instances": instances, "auto_scaling_groups": asgs}, indent=2)

    if skill_type == "database_translation":
        return json.dumps({"db_instances": raw_configs}, indent=2)

    if skill_type == "storage_translation":
        return json.dumps({"volumes": raw_configs}, indent=2)

    if skill_type == "loadbalancer_translation":
        return json.dumps({"load_balancers": raw_configs}, indent=2)

    if skill_type == "cfn_terraform":
        return json.dumps(raw_configs[0] if raw_configs else {}, indent=2)

    if skill_type == "iam_translation":
        return json.dumps(raw_configs[0] if raw_configs else {}, indent=2)

    return json.dumps(raw_configs, indent=2)


def _build_data_migration_input(
    workload_name: str,
    resources: list[dict],
    software_inventory: dict,
) -> str:
    """Build input for the data_migration_planning skill."""
    db_resources = []
    for r in resources:
        aws_type = r.get("aws_type", "")
        raw = r.get("raw_config") or {}
        if "RDS" in aws_type or "Aurora" in aws_type:
            db_resources.append({
                "engine": raw.get("engine", ""),
                "source": "rds",
                "instance_class": raw.get("db_instance_class", ""),
                "allocated_storage": raw.get("allocated_storage", 0),
                "multi_az": raw.get("multi_az", False),
                "name": r.get("name", ""),
            })

    # Check for local databases in software inventory
    local_dbs = []
    for rid, inv in software_inventory.items():
        for app in inv.get("applications", []):
            app_name = (app.get("Name") or app.get("name") or "").lower()
            for kw in ("mysql", "mariadb", "postgres", "mongodb", "redis"):
                if kw in app_name:
                    local_dbs.append({
                        "engine": kw,
                        "source": "local",
                        "host_instance": rid,
                        "version": app.get("Version") or app.get("version") or "unknown",
                        "name": app.get("Name") or app.get("name") or kw,
                    })

    storage_resources = []
    for r in resources:
        if "Volume" in r.get("aws_type", "") or "S3" in r.get("aws_type", ""):
            raw = r.get("raw_config") or {}
            storage_resources.append({
                "type": r.get("aws_type", ""),
                "size_gb": raw.get("size_gb") or raw.get("Size") or 0,
                "name": r.get("name", ""),
            })

    return json.dumps({
        "workload_name": workload_name,
        "database_resources": db_resources,
        "local_databases": local_dbs,
        "storage_resources": storage_resources,
    }, indent=2)


def _build_workload_planning_input(
    workload_name: str,
    resources: list[dict],
    resource_mapping: list[dict],
    dependency_edges: list[dict],
    completed_artifacts: dict[str, str],
) -> str:
    """Build input for the workload_planning skill (runbook + anomaly)."""
    return json.dumps({
        "workload_name": workload_name,
        "resources": [
            {"id": r.get("id", ""), "name": r.get("name", ""), "aws_type": r.get("aws_type", "")}
            for r in resources
        ],
        "resource_mapping": resource_mapping,
        "dependency_edges": dependency_edges[:50],
        "completed_translations": {k: v[:2000] for k, v in completed_artifacts.items()},
    }, indent=2)


def run_workload_plan(
    migration_id: str,
    assessment_id: str,
    app_group_id: str,
    tenant_id: str,
    max_iterations: int = 3,
) -> None:
    """Main entry point — runs in a child process.

    Orchestrates the full plan generation pipeline for a single workload.
    """
    logging.basicConfig(level=logging.INFO)

    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        _run_pipeline(session, migration_id, assessment_id, app_group_id, tenant_id, max_iterations)
    except Exception as exc:
        logger.error("Workload plan failed: %s\n%s", exc, traceback.format_exc())
        # Mark as failed on migration + artifacts
        try:
            from sqlalchemy import text as _text
            session.execute(
                _text("UPDATE migrations SET plan_status = 'failed' WHERE id = :mid"),
                {"mid": migration_id},
            )
            session.commit()
        except Exception:
            pass
        try:
            from sqlalchemy import text as _text
            row = session.execute(
                _text("SELECT dependency_artifacts FROM assessments WHERE id = :id"),
                {"id": assessment_id},
            ).fetchone()
            if row:
                arts = row[0] or {}
                wp = arts.get("workload_plans", {})
                wp[app_group_id] = {"status": "failed", "error": str(exc)}
                arts["workload_plans"] = wp
                session.execute(
                    _text("UPDATE assessments SET dependency_artifacts = :arts WHERE id = :id"),
                    {"arts": json.dumps(arts), "id": assessment_id},
                )
                session.commit()
        except Exception:
            pass
    finally:
        session.close()


def _update_plan_progress(
    session: Session,
    assessment_id: str,
    app_group_name: str,
    step: str,
    log_line: str,
    started_at: float,
) -> None:
    """Write progress to the assessment's dependency_artifacts so the frontend can poll it."""
    import time
    from sqlalchemy import text

    # Use raw SQL to avoid SQLAlchemy JSONB mutation detection issues
    # First read current value
    row = session.execute(
        text("SELECT dependency_artifacts FROM assessments WHERE id = :id"),
        {"id": assessment_id},
    ).fetchone()
    if not row:
        return

    arts = row[0] or {}
    wp = arts.get("workload_plans", {})
    plan = wp.get(app_group_name, {})
    plan["status"] = "running"
    plan["current_step"] = step
    plan["elapsed_seconds"] = round(time.time() - started_at, 1)
    logs = plan.get("logs", [])
    logs.append(f"[{round(time.time() - started_at, 1)}s] {log_line}")
    plan["logs"] = logs[-50:]
    wp[app_group_name] = plan
    arts["workload_plans"] = wp

    session.execute(
        text("UPDATE assessments SET dependency_artifacts = :arts WHERE id = :id"),
        {"arts": json.dumps(arts), "id": assessment_id},
    )
    session.commit()


def _run_pipeline(
    session: Session,
    migration_id: str,
    assessment_id: str,
    app_group_id: str,
    tenant_id: str,
    max_iterations: int = 3,
) -> None:
    import time
    from app.gateway.model_gateway import get_anthropic_client

    pipeline_start = time.time()
    ag_id = UUID(app_group_id)
    assess_id = UUID(assessment_id)
    t_id = UUID(tenant_id)

    # Load app group and members
    ag = session.execute(
        select(AppGroup).where(AppGroup.id == ag_id)
    ).scalar_one()

    members = session.execute(
        select(AppGroupMember).where(AppGroupMember.app_group_id == ag_id)
    ).scalars().all()

    resource_ids = [m.resource_id for m in members]
    resources_orm = session.execute(
        select(Resource).where(Resource.id.in_(resource_ids))
    ).scalars().all()

    resources = [
        {
            "id": str(r.id),
            "name": r.name,
            "aws_type": r.aws_type,
            "raw_config": r.raw_config or {},
        }
        for r in resources_orm
    ]

    # Load resource assessments for software inventory
    ra_rows = session.execute(
        select(ResourceAssessment).where(
            ResourceAssessment.resource_id.in_(resource_ids),
            ResourceAssessment.assessment_id == assess_id,
        )
    ).scalars().all()

    software_inventory = {}
    for ra in ra_rows:
        if ra.software_inventory:
            software_inventory[str(ra.resource_id)] = ra.software_inventory

    logger.info(
        "Plan orchestrator: workload '%s' with %d resources, max_iterations=%d",
        ag.name, len(resources), max_iterations,
    )

    def _progress(step: str, msg: str):
        _update_plan_progress(session, assessment_id, ag.name, step, msg, pipeline_start)

    # Mark migration as plan running
    from sqlalchemy import text as _t
    session.execute(
        _t("UPDATE migrations SET plan_status = 'running', plan_workload_id = :wid, plan_workload_name = :wname, plan_started_at = NOW(), plan_max_iterations = :iters WHERE id = :mid"),
        {"wid": str(ag_id), "wname": ag.name, "mid": migration_id, "iters": max_iterations},
    )
    session.commit()

    _progress("init", f"Starting plan for '{ag.name}' ({len(resources)} resources)")

    anthropic_client = get_anthropic_client()
    completed_artifacts: dict[str, str] = {}

    # ── Step 1: Resource Mapping (deterministic + LLM review) ──────────
    _progress("resource_mapping", "Computing AWS → OCI resource mapping")
    from app.services.resource_mapper import compute_resource_mapping, review_mapping_with_llm

    ra_map = {}
    for ra in ra_rows:
        ra_map[str(ra.resource_id)] = {
            "recommended_oci_shape": ra.recommended_oci_shape,
            "recommended_oci_ocpus": ra.recommended_oci_ocpus,
            "recommended_oci_memory_gb": ra.recommended_oci_memory_gb,
            "projected_oci_monthly_cost_usd": ra.projected_oci_monthly_cost_usd,
            "os_compat_status": ra.os_compat_status,
        }

    mapping_entries = compute_resource_mapping(resources, ra_map, software_inventory)
    try:
        mapping_entries = review_mapping_with_llm(mapping_entries, ag.name, anthropic_client)
    except Exception as exc:
        logger.warning("LLM mapping review failed: %s", exc)

    resource_mapping = [e.to_dict() for e in mapping_entries]
    completed_artifacts["resource-mapping.json"] = json.dumps(resource_mapping, indent=2)
    logger.info("Resource mapping: %d entries", len(resource_mapping))

    # ── Step 2: Determine which skills to run ──────────────────────────
    skill_resources: dict[str, list[dict]] = {}
    for r in resources:
        skill = _skill_for_type(r.get("aws_type", ""))
        if skill:
            skill_resources.setdefault(skill, []).append(r)

    has_databases = "database_translation" in skill_resources
    # Check if data migration planning is needed:
    # - RDS/Aurora databases
    # - Local databases detected in SSM inventory
    # - EBS volumes with data (need snapshot + transfer)
    has_local_db = False
    for inv in software_inventory.values():
        for app in inv.get("applications", []):
            app_name = (app.get("Name") or app.get("name") or "").lower()
            if any(kw in app_name for kw in ("mysql", "mariadb", "postgres", "mongodb", "redis")):
                has_local_db = True
                break
        if has_local_db:
            break
    has_storage = any("Volume" in r.get("aws_type", "") for r in resources)
    needs_data_migration = has_databases or has_local_db or has_storage

    skills_to_run = list(skill_resources.keys())
    if needs_data_migration:
        skills_to_run.append("data_migration_planning")
    skills_to_run.append("workload_planning")

    _progress("resource_mapping", f"Resource mapping complete: {len(resource_mapping)} entries")
    logger.info("Skills to run: %s", skills_to_run)

    # ── Step 3: Run translation skills ─────────────────────────────────
    def _progress_cb(phase, iteration, confidence, decision):
        logger.info("  %s: iter=%d conf=%.2f", phase, iteration, confidence or 0)

    for skill_type in skill_resources:
        skill_label = skill_type.replace("_", " ").title()
        _progress(skill_type, f"Running {skill_label} (max {max_iterations} rounds)")
        try:
            skill_input = _build_skill_input(skill_type, skill_resources[skill_type])
            result = _run_skill(skill_type, skill_input, _progress_cb, anthropic_client, max_iterations)
            if result:
                for name, content in result.get("artifacts", {}).items():
                    completed_artifacts[f"{skill_type}/{name}"] = content
                _progress(skill_type, f"{skill_label} complete — confidence {result.get('confidence', 0):.0%}, {result.get('iterations', 1)} round(s)")
        except Exception as exc:
            _progress(skill_type, f"{skill_label} failed: {exc}")
            logger.warning("Skill %s failed: %s", skill_type, exc)

    # ── Step 4: Data migration planning (if needed) ────────────────────
    if needs_data_migration:
        _progress("data_migration", f"Running Data Migration Planning (max {max_iterations} rounds)")
        try:
            dm_input = _build_data_migration_input(ag.name, resources, software_inventory)
            from app.skills.data_migration.orchestrator import run as run_dm
            result = run_dm(dm_input, _progress_cb, anthropic_client, max_iterations)
            if result:
                for name, content in result.get("artifacts", {}).items():
                    completed_artifacts[f"data_migration/{name}"] = content
                _progress("data_migration", f"Data migration plan complete — confidence {result.get('confidence', 0):.0%}")
        except Exception as exc:
            _progress("data_migration", f"Data migration planning failed: {exc!r}")
            logger.warning("Data migration planning failed: %s\n%s", exc, traceback.format_exc())

    # ── Step 5: Workload planning (runbook + anomaly) ──────────────────
    _progress("workload_planning", "Running Runbook & Anomaly Analysis agents")
    try:
        # Load dependency edges for this workload
        from app.db.models import DependencyEdge
        edge_rows = session.execute(
            select(DependencyEdge).where(
                DependencyEdge.assessment_id == assess_id,
            )
        ).scalars().all()
        dep_edges = [
            {
                "source_resource_id": str(e.source_resource_id) if e.source_resource_id else "",
                "target_resource_id": str(e.target_resource_id) if e.target_resource_id else "",
                "edge_type": e.edge_type or "network",
                "byte_count": e.byte_count,
            }
            for e in edge_rows
        ]
        # Filter to edges involving this workload's resources
        rid_set = {r["id"] for r in resources}
        dep_edges = [
            e for e in dep_edges
            if e["source_resource_id"] in rid_set or e["target_resource_id"] in rid_set
        ]

        wp_input = _build_workload_planning_input(
            ag.name, resources, resource_mapping, dep_edges, completed_artifacts,
        )
        from app.skills.workload_planning.orchestrator import run as run_wp
        result = run_wp(wp_input, _progress_cb, anthropic_client, 3)
        if result:
            for name, content in result.get("artifacts", {}).items():
                completed_artifacts[f"workload_planning/{name}"] = content
    except Exception as exc:
        logger.warning("Workload planning failed: %s", exc)

    # ── Step 6: Synthesis ──────────────────────────────────────────────
    _progress("synthesis", f"Running Synthesis (combining all artifacts, max {max_iterations} rounds)")
    try:
        # Build synthesis input from all completed artifacts
        synthesis_input = json.dumps({
            "migration_name": ag.name,
            "jobs": [
                {
                    "skill_type": key.split("/")[0],
                    "artifacts": {key.split("/", 1)[-1]: content},
                }
                for key, content in completed_artifacts.items()
                if "/" in key and key.split("/")[0] not in ("workload_planning", "data_migration")
            ],
        }, indent=2)

        from app.skills.synthesis.orchestrator import run as run_synthesis
        result = run_synthesis(synthesis_input, _progress_cb, anthropic_client, max_iterations)
        if result:
            for name, content in result.get("artifacts", {}).items():
                completed_artifacts[f"synthesis/{name}"] = content
    except Exception as exc:
        logger.warning("Synthesis failed: %s", exc)

    # ── Step 7: Store results ──────────────────────────────────────────
    import time
    elapsed = round(time.time() - pipeline_start, 1)
    _progress("complete", f"Plan generation complete in {elapsed}s")

    from sqlalchemy import text as _text

    row = session.execute(
        _text("SELECT dependency_artifacts FROM assessments WHERE id = :id"),
        {"id": str(assess_id)},
    ).fetchone()

    if row:
        arts = row[0] or {}
        wp = arts.get("workload_plans", {})
        existing_logs = wp.get(ag.name, {}).get("logs", [])
        wp[ag.name] = {
            "status": "completed",
            "resource_mapping": resource_mapping,
            "artifacts": {k: v for k, v in completed_artifacts.items()},
            "skills_ran": list(skill_resources.keys()) + (["data_migration_planning"] if needs_data_migration else []) + ["workload_planning", "synthesis"],
            "max_iterations": max_iterations,
            "elapsed_seconds": elapsed,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "logs": existing_logs,
        }
        arts["workload_plans"] = wp
        session.execute(
            _text("UPDATE assessments SET dependency_artifacts = :arts WHERE id = :id"),
            {"arts": json.dumps(arts), "id": str(assess_id)},
        )
        session.commit()

    # Mark migration plan as completed
    session.execute(
        _text("UPDATE migrations SET plan_status = 'completed' WHERE id = :mid"),
        {"mid": migration_id},
    )
    session.commit()

    logger.info("Plan orchestrator complete for '%s' in %.1fs", ag.name, elapsed)


def _run_skill(
    skill_type: str,
    input_content: str,
    progress_callback,
    anthropic_client,
    max_iterations: int = 3,
) -> dict | None:
    """Run a single translation skill and return its result dict."""
    if skill_type == "ec2_translation":
        from app.skills.ec2_translation.orchestrator import run
    elif skill_type == "network_translation":
        from app.skills.network_translation.orchestrator import run
    elif skill_type == "database_translation":
        from app.skills.database_translation.orchestrator import run
    elif skill_type == "storage_translation":
        from app.skills.storage_translation.orchestrator import run
    elif skill_type == "loadbalancer_translation":
        from app.skills.loadbalancer_translation.orchestrator import run
    elif skill_type == "cfn_terraform":
        from app.skills.cfn_terraform.orchestrator import run
    elif skill_type == "iam_translation":
        from app.skills.iam_translation.orchestrator import run
    else:
        logger.warning("Unknown skill type: %s", skill_type)
        return None

    return run(input_content, progress_callback, anthropic_client, max_iterations)
