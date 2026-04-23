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
    Migration,
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

    if skill_type == "ocm_handoff_translation":
        # Attach per-instance OCM compatibility metadata so the writer can
        # route correctly (full/with_prep/manual → OCM; unsupported already
        # filtered upstream in _partition_ec2_for_hybrid).
        try:
            from app.services.ocm_compatibility import check_ec2_compatibility
            from app import mappings as _m
        except ImportError:
            check_ec2_compatibility = None  # type: ignore
            _m = None  # type: ignore

        instances: list[dict] = []
        for r in resources:
            rc = dict(r.get("raw_config") or {})
            if check_ec2_compatibility is not None:
                inv = rc.get("software_inventory") or None
                try:
                    rc["ocm_compatibility"] = check_ec2_compatibility(rc, inv)
                except Exception:
                    pass
            instances.append(rc)
        prereqs = _m.ocm_handoff_prereqs() if _m else []
        whitelist = _m.ocm_target_shapes() if _m else []
        return json.dumps({
            "instances": instances,
            "ocm_prereqs": prereqs,
            "target_shape_whitelist": whitelist,
            "target_compartment_var": "compartment_ocid",
            "target_vcn_var": "target_vcn_ocid",
            "target_subnet_var": "target_subnet_ocid",
        }, indent=2)

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
    import os
    os.setpgrp()
    os.environ.pop("CLAUDECODE", None)  # Allow Agent SDK to spawn nested sessions

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
    assess_id = UUID(assessment_id)
    t_id = UUID(tenant_id)
    mig_id = UUID(migration_id)

    # Load the migration to check for a bound app group
    migration = session.execute(
        select(Migration).where(Migration.id == mig_id)
    ).scalar_one()

    # Determine the effective app group id: prefer migration.bound_app_group_id,
    # fall back to the explicitly passed app_group_id parameter.
    effective_ag_id = migration.bound_app_group_id or (UUID(app_group_id) if app_group_id else None)

    if effective_ag_id:
        # Load resources via AppGroupMember -> Resource for the bound group
        ag = session.execute(
            select(AppGroup).where(AppGroup.id == effective_ag_id)
        ).scalar_one()

        members = session.execute(
            select(AppGroupMember).where(AppGroupMember.app_group_id == effective_ag_id)
        ).scalars().all()

        resource_ids = [m.resource_id for m in members]
        resources_orm = session.execute(
            select(Resource).where(Resource.id.in_(resource_ids), Resource.status != "stale")
        ).scalars().all()
    else:
        # Fallback: load resources from the migration's resources relationship
        resources_orm = session.execute(
            select(Resource).where(Resource.migration_id == mig_id)
        ).scalars().all()
        resource_ids = [r.id for r in resources_orm]

        # Create a synthetic app group name from the migration
        class _FakeAG:
            name: str
        ag = _FakeAG()
        ag.name = migration.name

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
        {"wid": str(effective_ag_id) if effective_ag_id else None, "wname": ag.name, "mid": migration_id, "iters": max_iterations},
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
    # CFN dedup: resources managed by a CloudFormation stack are tagged
    # with cfn_stack_name in raw_config during discovery. Skip them from
    # individual skill translation (ec2, network, etc.) since the stack
    # itself gets translated via cfn_terraform.
    skill_resources: dict[str, list[dict]] = {}
    cfn_skipped = 0
    for r in resources:
        skill = _skill_for_type(r.get("aws_type", ""))
        if not skill:
            continue
        raw = r.get("raw_config") or {}
        if skill != "cfn_terraform" and raw.get("cfn_stack_name"):
            cfn_skipped += 1
            continue  # Skip — already covered by CFN stack translation
        skill_resources.setdefault(skill, []).append(r)

    if cfn_skipped:
        logger.info("Skipped %d resources already covered by CloudFormation stack translation", cfn_skipped)
        _progress("resource_mapping", f"Skipped {cfn_skipped} CFN-managed resources (covered by stack translation)")

    # ── Hybrid EC2 routing: OCM vs native fallback ────────────────────
    # Every EC2 instance gets an OCM compatibility check. Those whose level
    # is full/with_prep/manual route through ocm_handoff_translation;
    # unsupported ones fall through to ec2_translation. This gives us the
    # OCM path for cases OCM can handle and keeps native HCL as the
    # fallback for Graviton, instance-store, etc.
    ec2_rows = skill_resources.get("ec2_translation", [])
    if ec2_rows:
        try:
            from app.services.ocm_compatibility import check_ec2_compatibility
        except ImportError:
            check_ec2_compatibility = None  # type: ignore

        ocm_eligible: list[dict] = []
        native_only: list[dict] = []
        for r in ec2_rows:
            if "AutoScaling" in r.get("aws_type", ""):
                # ASGs don't go through OCM today — OCM doesn't model scaling.
                native_only.append(r)
                continue
            if check_ec2_compatibility is None:
                native_only.append(r)
                continue
            rc = r.get("raw_config") or {}
            # Feed the rightsizer-picked shape in so the check rejects
            # instances whose target shape isn't on OCM's whitelist (e.g.
            # DenseIO.E5.Flex, A2.Flex) — they'd otherwise fail at OCM
            # plan-execute time instead of at routing time.
            rec_shape = (ra_map.get(str(r.get("id", ""))) or {}).get("recommended_oci_shape")
            compat = check_ec2_compatibility(
                rc, rc.get("software_inventory"), recommended_shape=rec_shape,
            )
            if compat.get("level") in ("full", "with_prep", "manual"):
                ocm_eligible.append(r)
            else:
                native_only.append(r)

        if ocm_eligible:
            skill_resources["ocm_handoff_translation"] = ocm_eligible
        if native_only:
            skill_resources["ec2_translation"] = native_only
        else:
            skill_resources.pop("ec2_translation", None)
        logger.info(
            "Hybrid EC2 routing: %d → OCM handoff, %d → native ec2_translation",
            len(ocm_eligible), len(native_only),
        )
        _progress(
            "resource_mapping",
            f"Hybrid EC2: {len(ocm_eligible)} via OCM, {len(native_only)} via native Terraform",
        )
        _hybrid_ocm_count = len(ocm_eligible)
        _hybrid_native_count = len(native_only)
    else:
        _hybrid_ocm_count = 0
        _hybrid_native_count = 0

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

    # Defer cfn_terraform until after the per-resource skills have run —
    # the chunked CFN writer reuses their already-generated HCL so it only
    # has to translate what isn't already covered.
    cfn_stacks = skill_resources.pop("cfn_terraform", None)

    # Accumulates reviewer-flagged gaps across every skill so the
    # bundle_builder can aggregate them into reports/gaps.md at the end.
    all_gaps: list[dict] = []

    def _collect_gaps(skill_type: str, result: dict | None) -> None:
        if not result:
            return
        review = result.get("review") or {}
        # Standard shape: review.issues = [{severity, description, recommendation}]
        for issue in (review.get("issues") or []):
            if not isinstance(issue, dict):
                continue
            all_gaps.append({
                "skill": skill_type,
                "severity": issue.get("severity", ""),
                "description": issue.get("description", ""),
                "recommendation": issue.get("recommendation", ""),
            })
        # Some skills also drop gaps as a separate array on draft
        draft = result.get("draft") or {}
        for g in (draft.get("gaps") or []):
            if isinstance(g, str):
                all_gaps.append({"skill": skill_type, "severity": "INFO", "description": g, "recommendation": ""})
            elif isinstance(g, dict):
                all_gaps.append({
                    "skill": skill_type,
                    "severity": g.get("severity", "INFO"),
                    "description": g.get("description", g.get("issue", "")),
                    "recommendation": g.get("recommendation", g.get("fix", "")),
                })

    for skill_type in skill_resources:
        skill_label = skill_type.replace("_", " ").title()
        _progress(skill_type, f"Running {skill_label} (max {max_iterations} rounds)")
        try:
            # network_translation gets the chunked path — big networks
            # (lots of SGs / rules / ENIs) blow past the LLM gateway's
            # upstream-read timeout as one call.
            if skill_type == "network_translation":
                _run_network_chunked(
                    skill_resources[skill_type], completed_artifacts,
                    _progress, _progress_cb, anthropic_client, max_iterations,
                    _collect_gaps,
                )
                continue
            skill_input = _build_skill_input(skill_type, skill_resources[skill_type])
            result = _run_skill(skill_type, skill_input, _progress_cb, anthropic_client, max_iterations)
            if result:
                for name, content in result.get("artifacts", {}).items():
                    completed_artifacts[f"{skill_type}/{name}"] = content
                _collect_gaps(skill_type, result)
                _progress(skill_type, f"{skill_label} complete — confidence {result.get('confidence', 0):.0%}, {result.get('iterations', 1)} round(s)")
        except Exception as exc:
            _progress(skill_type, f"{skill_label} failed: {exc}")
            logger.warning("Skill %s failed: %s", skill_type, exc)

    # ── Step 3b: CFN stacks — chunked translation with prior-skill reuse ─
    if cfn_stacks:
        _run_cfn_chunked(
            cfn_stacks=cfn_stacks,
            completed_artifacts=completed_artifacts,
            _progress=_progress,
            _progress_cb=_progress_cb,
            anthropic_client=anthropic_client,
            max_iterations=max_iterations,
        )

    # ── Step 4: Data migration planning (if needed) ────────────────────
    if needs_data_migration:
        _progress("data_migration", f"Running Data Migration Planning (max {max_iterations} rounds)")
        try:
            dm_input = _build_data_migration_input(ag.name, resources, software_inventory)
            from app.agents.job_result import run_skill_sync
            result = run_skill_sync(
                "data_migration_planning", dm_input,
                max_iterations=max_iterations,
                migration_id=str(ag.assessment_id) if ag.assessment_id else None,
            )
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
        from app.agents.job_result import run_skill_sync
        result = run_skill_sync(
            "workload_planning", wp_input,
            max_iterations=3,
            migration_id=str(ag.assessment_id) if ag.assessment_id else None,
        )
        if result:
            for name, content in result.get("artifacts", {}).items():
                completed_artifacts[f"workload_planning/{name}"] = content
    except Exception as exc:
        logger.warning("Workload planning failed: %s", exc)

    # ── Step 6: Synthesis ──────────────────────────────────────────────
    # Aggregate artifacts by skill type (not one job per file)
    skill_artifacts: dict[str, dict[str, str]] = {}
    for key, content in completed_artifacts.items():
        if "/" not in key:
            continue
        skill = key.split("/")[0]
        if skill in ("workload_planning", "data_migration", "resource-mapping"):
            continue
        fname = key.split("/", 1)[-1]
        # .tf files in full, .md reports truncated to first 1000 chars for context
        if fname.endswith(".tf"):
            skill_artifacts.setdefault(skill, {})[fname] = content
        elif fname.endswith(".md"):
            skill_artifacts.setdefault(skill, {})[fname] = content[:1000] + "\n\n[... truncated for synthesis ...]" if len(content) > 1000 else content
            skill_artifacts.setdefault(skill, {})[fname] = content

    translation_jobs = [
        {"skill_type": skill, "artifacts": arts}
        for skill, arts in skill_artifacts.items()
    ]

    if translation_jobs:
        _progress("synthesis", f"Merging Terraform (combining {len(translation_jobs)} skill outputs into one stack)")
        try:
            synthesis_input = json.dumps({
                "migration_name": ag.name,
                "jobs": translation_jobs,
            }, indent=2)

            from app.agents.job_result import run_skill_sync
            result = run_skill_sync(
                "synthesis", synthesis_input,
                max_iterations=max_iterations,
                migration_id=str(ag.assessment_id) if ag.assessment_id else None,
            )
            if result:
                for name, content in result.get("artifacts", {}).items():
                    completed_artifacts[f"synthesis/{name}"] = content
                _progress("synthesis", "Synthesis complete")
        except Exception as exc:
            _progress("synthesis", f"Synthesis failed: {exc!r}")
            logger.warning("Synthesis failed: %s\n%s", exc, traceback.format_exc())
    else:
        _progress("synthesis", "No translation artifacts to synthesize — skipping")

    # ── Step 7: Build the hybrid bundle ────────────────────────────────
    # Reorganize per-skill artifacts into terraform/ + runbooks/ +
    # reports/ + debug/ with a top-level README.md + manifest.json.
    import time
    elapsed = round(time.time() - pipeline_start, 1)

    synthesis_ok = any(k.startswith("synthesis/") for k in completed_artifacts)
    skills_ran_list = (
        list(skill_resources.keys())
        + (["data_migration_planning"] if needs_data_migration else [])
        + ["workload_planning"]
        + (["synthesis"] if synthesis_ok else [])
    )

    # Stash aggregated gaps for bundle_builder (consumed + deleted inside).
    completed_artifacts["_review_gaps_sentinel"] = json.dumps(all_gaps)

    try:
        from app.services.bundle_builder import build_hybrid_bundle
        bundle = build_hybrid_bundle(
            completed_artifacts,
            migration_name=ag.name,
            resource_count=len(resources),
            skills_ran=skills_ran_list,
            elapsed_seconds=elapsed,
            synthesis_ok=synthesis_ok,
            ocm_instance_count=_hybrid_ocm_count,
            native_instance_count=_hybrid_native_count,
        )
        _progress(
            "complete",
            f"Hybrid bundle built: {sum(1 for p in bundle if p.startswith('terraform/'))} terraform files, "
            f"{sum(1 for p in bundle if p.startswith('runbooks/'))} runbook files, "
            f"{sum(1 for p in bundle if p.startswith('reports/'))} report files, "
            f"{sum(1 for p in bundle if p.startswith('debug/'))} debug files",
        )
        # Replace flat dict with hybrid layout for downstream consumers
        completed_artifacts = bundle
    except Exception as exc:
        logger.warning("bundle rebuild failed: %s\n%s", exc, traceback.format_exc())
        completed_artifacts.pop("_review_gaps_sentinel", None)

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
            "skills_ran": skills_ran_list,
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
    progress_callback,      # kept for signature compatibility; unused below
    anthropic_client,       # kept for signature compatibility; unused below
    max_iterations: int = 3,
    migration_id: str | None = None,
) -> dict | None:
    """Run a single translation skill via the agent runtime.

    Thin wrapper over ``app.agents.job_result.run_skill_sync`` so this
    module's original sync call site keeps working. The ``progress_callback``
    / ``anthropic_client`` args are accepted but ignored — the agent runtime
    has its own logging and its own client.
    """
    try:
        from app.agents.job_result import run_skill_sync
        from app.agents.skill_group import SKILL_SPECS
    except ImportError as exc:  # pragma: no cover — indicates a bad deployment
        logger.error("Agent runtime not importable: %s", exc)
        return None

    if skill_type not in SKILL_SPECS:
        logger.warning("Unknown skill type: %s (not in SKILL_SPECS)", skill_type)
        return None

    return run_skill_sync(
        skill_type, input_content,
        max_iterations=max_iterations,
        migration_id=migration_id,
    )


def _run_network_chunked(
    network_resources: list[dict],
    completed_artifacts: dict[str, str],
    _progress,
    _progress_cb,
    anthropic_client,
    max_iterations: int,
    _collect_gaps,
    migration_id: str | None = None,
) -> None:
    """Translate the network via chunked writer calls.

    For small networks (under the chunker's size threshold) this runs
    exactly one skill call — same as before. For large networks (many
    VPCs / security groups / ENIs), each VPC becomes its own chunk plus
    a trailing 'global' chunk for DNS / peering / transit gateways.
    Outputs merge via the shared cfn_chunker helpers (dedupe variables
    + outputs by name, concatenate main.tf with headers).
    """
    from app.services.cfn_chunker import merge_chunk_outputs
    from app.services.network_chunker import chunk_network_input

    # Reuse the existing _build_skill_input to aggregate the raw network
    # input shape, then hand that dict to the chunker.
    raw_input_str = _build_skill_input("network_translation", network_resources)
    try:
        network_input = json.loads(raw_input_str)
    except (ValueError, TypeError):
        logger.warning("network input not parseable; falling back to single call")
        network_input = {}

    chunks = chunk_network_input(network_input)
    if not chunks:
        _progress("network_translation", "Network input is empty; nothing to translate")
        return

    total = len(chunks)
    _progress(
        "network_translation",
        f"Running Network Translation — {total} chunk(s)"
        + (" (single-pass, input small enough)" if total == 1 else " (per-VPC chunking)"),
    )

    chunk_outputs: list[dict] = []
    for chunk in chunks:
        label = chunk.scope
        # Single small network gets the full iteration budget; multi-chunk
        # runs use 1 iteration each since each chunk is self-contained and
        # a review loop per chunk would multiply LLM traffic without
        # catching much the reviewer on the aggregate couldn't catch at
        # merge time.
        iters = max_iterations if total == 1 else 1
        try:
            result = _run_skill(
                "network_translation", chunk.to_input(),
                _progress_cb, anthropic_client,
                max_iterations=iters,
                migration_id=migration_id,
            )
            if result:
                chunk_outputs.append(result.get("artifacts") or {})
                conf = result.get("confidence", 0)
                _collect_gaps("network_translation", result)
                _progress(
                    "network_translation",
                    f"Network chunk {chunk.index + 1}/{total} [{label}] — "
                    f"confidence {conf:.0%}",
                )
        except Exception as exc:
            logger.warning("Network chunk %d/%d [%s] failed: %s",
                           chunk.index + 1, total, label, exc)
            _progress(
                "network_translation",
                f"Network chunk {chunk.index + 1}/{total} [{label}] failed: {str(exc)[:200]}",
            )

    if not chunk_outputs:
        _progress("network_translation", "Network translation produced no output")
        return

    # Small-network fast path: one chunk → no merge overhead, just lift
    # the single bundle as-is.
    if total == 1:
        for name, content in chunk_outputs[0].items():
            completed_artifacts[f"network_translation/{name}"] = content
    else:
        merged = merge_chunk_outputs(chunk_outputs)
        for name, content in merged.items():
            completed_artifacts[f"network_translation/{name}"] = content
    _progress(
        "network_translation",
        f"Network Translation merged: {len(chunk_outputs)}/{total} chunk(s) translated",
    )


def _run_cfn_chunked(
    cfn_stacks: list[dict],
    completed_artifacts: dict[str, str],
    _progress,
    _progress_cb,
    anthropic_client,
    max_iterations: int,
    migration_id: str | None = None,
) -> None:
    """Translate each CFN stack via chunked writer calls + prior-skill reuse.

    Instead of handing the whole template to one writer call (which 504s on
    the nginx gateway for templates with 20+ resources), split it into
    chunks of ~8 resources, reuse already-translated HCL from earlier
    skills as context, translate each chunk with ``max_iterations=1``
    (small inputs don't need a review loop), and merge the outputs.

    Failures are per-chunk, not per-stack — one 504 no longer wipes out
    the whole CFN translation.
    """
    from app.services.cfn_chunker import (
        DEFAULT_CHUNK_SIZE,
        build_reference_library,
        chunk_cfn_template,
        merge_chunk_outputs,
    )

    for stack_idx, stack in enumerate(cfn_stacks):
        raw = stack.get("raw_config") or {}
        template = raw.get("template") or raw
        stack_name = (
            raw.get("stack_name")
            or stack.get("name")
            or f"stack-{stack_idx}"
        )

        chunks = chunk_cfn_template(template, chunk_size=DEFAULT_CHUNK_SIZE)
        if not chunks:
            _progress("cfn_terraform", f"CFN '{stack_name}': no Resources to translate; skipping")
            continue

        reference_hcl = build_reference_library(completed_artifacts)
        total = len(chunks)
        _progress(
            "cfn_terraform",
            f"CFN '{stack_name}': translating {total} chunk(s) of up to {DEFAULT_CHUNK_SIZE} resources "
            f"(reusing HCL from {len(reference_hcl)} prior skills)",
        )

        chunk_outputs: list[dict] = []
        for chunk in chunks:
            chunk_input = chunk.to_input(reference_hcl=reference_hcl)
            try:
                # max_iterations=1: chunks are small, a full review/revise loop
                # per chunk would 3x the LLM traffic for marginal gain.
                result = _run_skill(
                    "cfn_terraform",
                    chunk_input,
                    _progress_cb,
                    anthropic_client,
                    max_iterations=1,
                    migration_id=migration_id,
                )
                if result:
                    chunk_outputs.append(result.get("artifacts") or {})
                    conf = result.get("confidence", 0)
                    _progress(
                        "cfn_terraform",
                        f"CFN '{stack_name}' chunk {chunk.index + 1}/{total} — confidence {conf:.0%}",
                    )
            except Exception as exc:
                logger.warning("CFN chunk %d/%d for '%s' failed: %s",
                               chunk.index + 1, total, stack_name, exc)
                _progress(
                    "cfn_terraform",
                    f"CFN '{stack_name}' chunk {chunk.index + 1}/{total} failed: {str(exc)[:200]}",
                )

        if not chunk_outputs:
            _progress("cfn_terraform", f"CFN '{stack_name}' produced no output; moving on")
            continue

        merged = merge_chunk_outputs(chunk_outputs)
        for name, content in merged.items():
            completed_artifacts[f"cfn_terraform/{stack_name}/{name}"] = content
        _progress(
            "cfn_terraform",
            f"CFN '{stack_name}' merged: {len(chunk_outputs)}/{total} chunks translated, "
            f"{len(merged)} file(s) in final bundle",
        )
