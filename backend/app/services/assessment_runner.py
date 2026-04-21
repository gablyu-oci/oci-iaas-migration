"""Assessment runner -- executes full assessment pipeline in a child process.

This module is invoked via multiprocessing.Process from the assessments API.
It creates its own synchronous DB engine (not shared with the FastAPI async
engine) following the same isolation pattern as job_runner.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.models import (
    Assessment,
    AppGroup,
    AppGroupMember,
    AWSConnection,
    DependencyEdge,
    Migration,
    Resource,
    ResourceAssessment,
    TCOReport,
)
from app.services.cloudwatch_collector import collect_metrics
from app.services.ssm_inventory import collect_inventory
from app.services.rightsizing_engine import compute_rightsizing
from app.services.os_compat_checker import check_os_compatibility
from app.services.readiness_scorer import compute_readiness_score
from app.services.tco_calculator import compute_tco
from app.services.dependency_mapper import (
    discover_dependencies,
    extract_cloudtrail_json,
    extract_flowlog_text,
)
from app.services.app_grouper import compute_app_groups
from app.services.sixr_classifier import classify_workloads

logger = logging.getLogger(__name__)

STEPS = [
    "collecting_metrics",
    "collecting_inventory",
    "rightsizing",
    "os_compatibility",
    "dependency_mapping",
    "grouping",
    "classifying",
    "scoring",
    "tco",
]


def _sync_database_url() -> str:
    """Convert the async DATABASE_URL to a synchronous one for psycopg2."""
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def _update_step(session: Session, assessment_id: str, step: str) -> None:
    """Update assessment current_step in the DB."""
    session.execute(
        update(Assessment)
        .where(Assessment.id == UUID(assessment_id))
        .values(current_step=step)
    )
    session.commit()


def _get_aws_credentials(session: Session, connection_id: UUID) -> tuple[dict, str]:
    """Load AWS credentials and region from an AWSConnection record.

    Returns (credentials_dict, region).
    """
    conn = session.execute(
        select(AWSConnection).where(AWSConnection.id == connection_id)
    ).scalar_one_or_none()

    if not conn:
        raise ValueError(f"AWSConnection {connection_id} not found")

    # credentials is stored as JSON text
    creds = conn.credentials
    if isinstance(creds, str):
        creds = json.loads(creds)

    return creds, conn.region


def _extract_instance_id(resource: Resource) -> str | None:
    """Extract the EC2 instance ID from a resource's raw_config."""
    raw = resource.raw_config or {}
    for key in ("InstanceId", "instance_id"):
        val = raw.get(key)
        if val:
            return val
    return None


def _extract_instance_type(resource: Resource) -> str:
    """Extract the EC2 instance type from a resource's raw_config."""
    raw = resource.raw_config or {}
    return raw.get("InstanceType") or raw.get("instance_type") or "t3.medium"


def _extract_vpc_ids(resources: list[Resource]) -> list[str]:
    """Extract unique VPC IDs from a list of resources."""
    vpc_ids: set[str] = set()
    for r in resources:
        raw = r.raw_config or {}
        vpc_id = raw.get("VpcId") or raw.get("vpc_id")
        if vpc_id:
            vpc_ids.add(vpc_id)
    return list(vpc_ids)


def _resource_to_dict(resource: Resource) -> dict:
    """Convert a Resource ORM object to a plain dict for service functions."""
    return {
        "id": str(resource.id),
        "resource_id": str(resource.id),
        "name": resource.name,
        "aws_type": resource.aws_type,
        "raw_config": resource.raw_config or {},
    }


def run_assessment(assessment_id: str) -> None:
    """Main entry point -- called in a child process.

    Creates its own synchronous DB engine, loads assessment data, and runs
    the full assessment pipeline step by step.
    """
    logging.basicConfig(level=logging.INFO)

    sync_url = _sync_database_url()
    engine = create_engine(sync_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)

    session = SessionLocal()
    try:
        # ---- Load assessment and related data ----
        assessment = session.execute(
            select(Assessment).where(Assessment.id == UUID(assessment_id))
        ).scalar_one_or_none()

        if not assessment:
            logger.error("Assessment %s not found", assessment_id)
            return

        migration = session.execute(
            select(Migration).where(Migration.id == assessment.migration_id)
        ).scalar_one_or_none()

        if not migration:
            logger.error("Migration %s not found", str(assessment.migration_id))
            return

        # Load resources scoped to the AWS connection (not migration), excluding stale
        if migration.aws_connection_id:
            resources = list(
                session.execute(
                    select(Resource).where(
                        Resource.aws_connection_id == migration.aws_connection_id,
                        Resource.tenant_id == assessment.tenant_id,
                        Resource.status != "stale",
                    )
                ).scalars().all()
            )
        else:
            # Fallback: legacy migration-scoped resources
            resources = list(
                session.execute(
                    select(Resource).where(Resource.migration_id == migration.id)
                ).scalars().all()
            )

        tenant_id = assessment.tenant_id

        # Store connection_id on assessment for future reference
        if migration.aws_connection_id and not assessment.aws_connection_id:
            assessment.aws_connection_id = migration.aws_connection_id

        # Mark running
        assessment.status = "running"
        assessment.started_at = datetime.now(timezone.utc)
        session.commit()

        # ---- Resolve AWS credentials ----
        credentials: dict = {}
        region: str = "us-east-1"
        if migration.aws_connection_id:
            try:
                credentials, region = _get_aws_credentials(
                    session, migration.aws_connection_id
                )
            except Exception as exc:
                logger.warning("Could not load AWS credentials: %s", exc)

        # Filter to EC2 instances for compute-specific steps
        ec2_resources = [
            r for r in resources
            if r.aws_type and "EC2::Instance" in r.aws_type
        ]
        instance_ids = [
            _extract_instance_id(r) for r in ec2_resources
        ]
        instance_ids = [iid for iid in instance_ids if iid]

        # Map instance_id -> resource for quick lookup
        iid_to_resource: dict[str, Resource] = {}
        for r in ec2_resources:
            iid = _extract_instance_id(r)
            if iid:
                iid_to_resource[iid] = r

        # Intermediate results stored across steps
        metrics_by_instance: dict[str, dict] = {}
        inventory_by_instance: dict[str, dict] = {}
        rightsizing_by_resource_id: dict[str, dict] = {}
        os_compat_by_resource_id: dict[str, dict] = {}
        dependency_edges: list[dict] = []
        app_groups_result: list[dict] = []
        sixr_classifications: dict[str, dict] = {}

        # ================================================================
        # Step 1: Collect CloudWatch metrics
        # ================================================================
        _update_step(session, assessment_id, "collecting_metrics")
        if credentials and instance_ids:
            try:
                metrics_by_instance = collect_metrics(
                    credentials, region, instance_ids
                )
            except Exception as exc:
                logger.warning("CloudWatch collection failed: %s", exc)

        # ================================================================
        # Step 2: Collect SSM inventory
        # ================================================================
        _update_step(session, assessment_id, "collecting_inventory")
        if credentials and instance_ids:
            try:
                inventory_by_instance = collect_inventory(
                    credentials, region, instance_ids
                )
            except Exception as exc:
                logger.warning("SSM inventory collection failed: %s", exc)

        # ================================================================
        # Step 3: Rightsizing
        # ================================================================
        _update_step(session, assessment_id, "rightsizing")
        for r in ec2_resources:
            iid = _extract_instance_id(r)
            instance_type = _extract_instance_type(r)
            metrics = metrics_by_instance.get(iid, {}) if iid else {}
            try:
                result = compute_rightsizing(instance_type, metrics)
                rightsizing_by_resource_id[str(r.id)] = result
            except Exception as exc:
                logger.warning("Rightsizing failed for %s: %s", r.name, exc)

        # ================================================================
        # Step 4: OS compatibility
        # ================================================================
        _update_step(session, assessment_id, "os_compatibility")
        for r in ec2_resources:
            raw_config = r.raw_config or {}
            try:
                result = check_os_compatibility(raw_config)
                os_compat_by_resource_id[str(r.id)] = result
            except Exception as exc:
                logger.warning("OS compat check failed for %s: %s", r.name, exc)

        # ================================================================
        # Step 5: Dependency discovery (full pipeline)
        # ================================================================
        _update_step(session, assessment_id, "dependency_mapping")
        vpc_ids = _extract_vpc_ids(resources)
        resource_dicts = [_resource_to_dict(r) for r in resources]

        # 5a: Pull network-level edges (VPC Flow Logs + CloudTrail lookup)
        if credentials and vpc_ids:
            try:
                dependency_edges = discover_dependencies(
                    credentials, region, vpc_ids, resource_dicts
                )
            except Exception as exc:
                logger.warning("Network dependency mapping failed: %s", exc)

        # 5b: Run dependency discovery pipeline (CloudTrail + graph + LLM review)
        cloudtrail_json: str = ""
        flowlog_text: str | None = None
        discovery_graph_data: dict = {}  # parsed dependency.json from pipeline

        if credentials:
            try:
                cloudtrail_json = extract_cloudtrail_json(
                    credentials, region, lookback_days=30
                )
                if vpc_ids:
                    flowlog_text = extract_flowlog_text(
                        credentials, region, vpc_ids, lookback_days=14
                    )

                ct_data = json.loads(cloudtrail_json) if cloudtrail_json else {}
                ct_count = len(ct_data.get("Records", []))
                logger.info(
                    "Extracted %d CloudTrail events, flow logs=%s",
                    ct_count, "yes" if flowlog_text else "no",
                )

                if ct_count > 0 or flowlog_text:
                    from app.skills.dependency_discovery.orchestrator import (
                        run_graph_only as run_discovery_graph,
                    )
                    from app.gateway.model_gateway import get_anthropic_client

                    anthropic_client = get_anthropic_client()

                    dd_result = run_discovery_graph(
                        input_content=cloudtrail_json,
                        flowlog_content=flowlog_text,
                        anthropic_client=anthropic_client,
                    )

                    # Parse the dependency graph JSON for per-workload rendering
                    dep_json_str = dd_result.get("artifacts", {}).get("dependency.json", "")
                    if dep_json_str:
                        discovery_graph_data = json.loads(dep_json_str)

                    logger.info(
                        "Dependency discovery graph: %d nodes, %d edges, confidence=%.2f",
                        len(discovery_graph_data.get("nodes", [])),
                        len(discovery_graph_data.get("edges", [])),
                        dd_result.get("confidence", 0),
                    )

            except Exception as exc:
                logger.warning("Dependency discovery failed: %s\n%s", exc, traceback.format_exc())

        # Store dependency edges in DB
        for edge in dependency_edges:
            src_id = edge.get("source_resource_id")
            tgt_id = edge.get("target_resource_id")
            dep_edge = DependencyEdge(
                assessment_id=UUID(assessment_id),
                tenant_id=tenant_id,
                source_resource_id=UUID(src_id) if src_id else None,
                target_resource_id=UUID(tgt_id) if tgt_id else None,
                source_ip=edge.get("source_ip"),
                target_ip=edge.get("target_ip"),
                port=edge.get("port"),
                protocol=str(edge.get("protocol", "")),
                edge_type="network",
                byte_count=edge.get("byte_count"),
                packet_count=float(edge.get("flow_count", 0)),
            )
            session.add(dep_edge)

        session.commit()

        # ================================================================
        # Step 6: Application grouping
        # ================================================================
        _update_step(session, assessment_id, "grouping")
        try:
            # Get anthropic client for LLM grouping review
            grouping_client = None
            try:
                from app.gateway.model_gateway import get_anthropic_client
                grouping_client = get_anthropic_client()
            except Exception:
                logger.info("No anthropic client available, skipping LLM grouping review")
            app_groups_result = compute_app_groups(
                resource_dicts, dependency_edges, anthropic_client=grouping_client,
            )
        except Exception as exc:
            logger.warning("App grouping failed: %s", exc)

        # Store app groups in DB
        group_name_to_id: dict[str, UUID] = {}
        for group_data in app_groups_result:
            ag_id = uuid4()
            group_name_to_id[group_data["name"]] = ag_id
            ag = AppGroup(
                id=ag_id,
                assessment_id=UUID(assessment_id),
                tenant_id=tenant_id,
                name=group_data["name"],
                grouping_method=group_data.get("strategy"),
                workload_type=group_data.get("workload_type"),
            )
            session.add(ag)
            for rid_str in group_data.get("resource_ids", []):
                try:
                    rid_uuid = UUID(rid_str)
                except (ValueError, TypeError):
                    logger.warning(
                        "Skipping app group member with bad resource_id %r in group %s",
                        rid_str, group_data.get("name"),
                    )
                    continue
                member = AppGroupMember(
                    app_group_id=ag_id,
                    resource_id=rid_uuid,
                )
                session.add(member)
        session.commit()

        # ================================================================
        # Step 6b: Generate per-workload dependency graphs
        # ================================================================
        try:
            from app.services.workload_graph import build_workload_graphs
            rd_by_id = {str(r.get("id", "")): r for r in resource_dicts}
            workload_graphs = build_workload_graphs(
                app_groups=app_groups_result,
                resource_by_id=rd_by_id,
                dependency_edges=dependency_edges,
                discovery_graph=discovery_graph_data,
            )
            if workload_graphs:
                assessment.dependency_artifacts = {
                    "workload_graphs": workload_graphs,
                    "cloudtrail_event_count": len(
                        json.loads(cloudtrail_json).get("Records", [])
                    ) if cloudtrail_json else 0,
                    "has_flowlogs": bool(flowlog_text),
                }
                session.commit()
                logger.info("Generated %d workload dependency graphs", len(workload_graphs))
        except Exception as exc:
            logger.warning("Workload graph generation failed: %s\n%s", exc, traceback.format_exc())

        # ================================================================
        # Step 7: 6R classification (async call via asyncio.run)
        # ================================================================
        _update_step(session, assessment_id, "classifying")
        try:
            from app.gateway.model_gateway import get_anthropic_client
            client = get_anthropic_client()

            # Build data for the classifier
            groups_for_classification = []
            for group_data in app_groups_result:
                group_resource_ids = set(group_data.get("resource_ids", []))
                group_types: list[str] = []
                group_os_statuses: list[str] = []
                cpu_values: list[float] = []
                mem_values: list[float] = []

                for r in resources:
                    rid = str(r.id)
                    if rid in group_resource_ids:
                        if r.aws_type:
                            group_types.append(r.aws_type)
                        os_info = os_compat_by_resource_id.get(rid, {})
                        if os_info.get("status"):
                            group_os_statuses.append(os_info["status"])
                        iid = _extract_instance_id(r)
                        if iid and iid in metrics_by_instance:
                            m = metrics_by_instance[iid]
                            if m.get("cpu_p95"):
                                cpu_values.append(m["cpu_p95"])
                            if m.get("mem_p95"):
                                mem_values.append(m["mem_p95"])

                groups_for_classification.append({
                    "name": group_data["name"],
                    "resource_types": list(set(group_types)),
                    "resource_count": group_data.get("resource_count", 0),
                    "avg_cpu": round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else None,
                    "avg_memory": round(sum(mem_values) / len(mem_values), 1) if mem_values else None,
                    "os_compat_summary": list(set(group_os_statuses)),
                })

            sixr_classifications = asyncio.run(
                classify_workloads(groups_for_classification, client)
            )

            # Update app group records with 6R results
            for group_data in app_groups_result:
                gname = group_data["name"]
                classification = sixr_classifications.get(gname, {})
                ag_id = group_name_to_id.get(gname)
                if ag_id and classification:
                    session.execute(
                        update(AppGroup)
                        .where(AppGroup.id == ag_id)
                        .values(
                            sixr_strategy=classification.get("strategy"),
                        )
                    )
            session.commit()

        except Exception as exc:
            logger.warning("6R classification failed: %s", exc)

        # ================================================================
        # Step 8: Readiness scoring + ResourceAssessment records
        # ================================================================
        _update_step(session, assessment_id, "scoring")
        resource_assessment_data: list[dict] = []

        for r in ec2_resources:
            rid = str(r.id)
            iid = _extract_instance_id(r)

            rightsizing = rightsizing_by_resource_id.get(rid, {})
            os_compat = os_compat_by_resource_id.get(rid, {})
            inventory = inventory_by_instance.get(iid, {}) if iid else {}
            metrics = metrics_by_instance.get(iid, {}) if iid else {}

            # Count dependencies for this resource
            dep_count = sum(
                1 for e in dependency_edges
                if e.get("source_resource_id") == rid
                or e.get("target_resource_id") == rid
            )

            # Estimate storage from raw_config
            raw = r.raw_config or {}
            storage_gb = 0.0
            for bdm in raw.get("BlockDeviceMappings", []):
                ebs = bdm.get("Ebs", {})
                storage_gb += ebs.get("VolumeSize", 0)

            # Software inventory percentage
            apps = inventory.get("applications", [])
            sw_pct = 100.0 if inventory.get("ssm_managed") and apps else 0.0

            try:
                score, factors = compute_readiness_score(
                    os_compat_status=os_compat.get("status", "unknown"),
                    has_oci_shape=bool(rightsizing.get("recommended_oci_shape")),
                    dependency_count=dep_count,
                    data_volume_gb=storage_gb,
                    has_metrics=bool(metrics),
                    sw_inventory_pct=sw_pct,
                )
            except Exception as exc:
                logger.warning("Readiness scoring failed for %s: %s", r.name, exc)
                score, factors = 0, {}

            aws_cost = rightsizing.get("aws_monthly_cost", 0.0)
            oci_cost = rightsizing.get("monthly_cost", 0.0)

            ra = ResourceAssessment(
                assessment_id=UUID(assessment_id),
                resource_id=r.id,
                tenant_id=tenant_id,
                metrics=metrics if metrics else None,
                current_instance_type=_extract_instance_type(r),
                current_monthly_cost_usd=aws_cost,
                recommended_oci_shape=rightsizing.get("recommended_oci_shape", "VM.Standard.E5.Flex"),
                recommended_oci_ocpus=float(rightsizing.get("ocpus", 2)),
                recommended_oci_memory_gb=float(rightsizing.get("memory_gb", 8)),
                projected_oci_monthly_cost_usd=oci_cost,
                rightsizing_confidence=_confidence_to_float(
                    rightsizing.get("confidence", "low")
                ),
                rightsizing_notes="\n".join(rightsizing.get("notes", [])),
                os_type=os_compat.get("os_type"),
                os_version=os_compat.get("os_version"),
                os_compat_status=os_compat.get("status"),
                os_compat_details=os_compat,
                software_inventory=inventory if inventory else None,
                ssm_available=inventory.get("ssm_managed", False),
                readiness_score=float(score),
                readiness_factors=factors,
            )
            session.add(ra)

            resource_assessment_data.append({
                "aws_monthly_cost": aws_cost,
                "oci_monthly_cost": oci_cost,
                "resource_type": r.aws_type or "compute",
                "storage_gb": storage_gb,
            })

        session.commit()

        # ================================================================
        # Step 9: TCO calculation
        # ================================================================
        _update_step(session, assessment_id, "tco")
        tco_result: dict = {}
        try:
            tco_result = compute_tco(resource_assessment_data)
        except Exception as exc:
            logger.warning("TCO calculation failed: %s", exc)

        if tco_result:
            tco_report = TCOReport(
                assessment_id=UUID(assessment_id),
                tenant_id=tenant_id,
                aws_monthly_total_usd=tco_result.get("aws_monthly", 0.0),
                oci_monthly_total_usd=tco_result.get("oci_monthly", 0.0),
                annual_savings_usd=tco_result.get("annual_savings", 0.0),
                savings_percentage=tco_result.get("savings_pct", 0.0),
                breakdown=tco_result.get("breakdown"),
                three_year_tco=tco_result.get("three_year_tco"),
            )
            session.add(tco_report)
            session.commit()

        # ================================================================
        # Build summary and mark completed
        # ================================================================
        all_scores = [
            ra.readiness_score
            for ra in session.execute(
                select(ResourceAssessment).where(
                    ResourceAssessment.assessment_id == UUID(assessment_id)
                )
            ).scalars().all()
            if ra.readiness_score is not None
        ]

        avg_score = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0.0

        high_count = sum(1 for s in all_scores if s >= 70)
        medium_count = sum(1 for s in all_scores if 40 <= s < 70)
        low_count = sum(1 for s in all_scores if s < 40)

        summary = {
            "total_resources": len(resources),
            "assessed_resources": len(ec2_resources),
            "avg_readiness_score": avg_score,
            "aws_monthly_cost": tco_result.get("aws_monthly", 0.0),
            "oci_monthly_cost": tco_result.get("oci_monthly", 0.0),
            "savings_pct": tco_result.get("savings_pct", 0.0),
            "resources_by_readiness": {
                "high": high_count,
                "medium": medium_count,
                "low": low_count,
            },
            "app_group_count": len(app_groups_result),
            "dependency_edge_count": len(dependency_edges),
        }

        assessment.status = "completed"
        assessment.summary = summary
        assessment.current_step = None
        assessment.completed_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(
            "Assessment %s completed: %d resources, avg score %.1f",
            assessment_id, len(resources), avg_score,
        )

    except Exception:
        logger.exception("Assessment %s failed", assessment_id)
        try:
            session.rollback()
            session.execute(
                update(Assessment)
                .where(Assessment.id == UUID(assessment_id))
                .values(
                    status="failed",
                    error_message=traceback.format_exc()[-2000:],
                    current_step=None,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
        except Exception:
            logger.exception("Failed to update assessment status to 'failed'")
    finally:
        session.close()
        engine.dispose()


def _confidence_to_float(confidence: str) -> float:
    """Convert a textual confidence level to a numeric value."""
    mapping = {"high": 0.9, "medium": 0.6, "low": 0.3}
    return mapping.get(confidence, 0.3)
