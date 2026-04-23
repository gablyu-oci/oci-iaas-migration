"""Assessment API routes -- create, query, and delete migration assessments."""
from __future__ import annotations

import logging
import multiprocessing
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import (
    AppGroup,
    AppGroupMember,
    Assessment,
    DependencyEdge,
    Migration,
    Resource,
    ResourceAssessment,
    TCOReport,
    Tenant,
)
from app.api.deps import get_current_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["assessments"])

# Registry of running assessment processes keyed by assessment_id (str).
_running_assessment_processes: dict[str, multiprocessing.Process] = {}


# ---------------------------------------------------------------------------
# Pydantic response schemas
# ---------------------------------------------------------------------------
class AssessmentOut(BaseModel):
    id: str
    migration_id: str
    status: str
    current_step: Optional[str] = None
    summary: Optional[dict] = None
    dependency_artifacts: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ResourceAssessmentOut(BaseModel):
    id: str
    resource_id: str
    resource_name: Optional[str] = None
    resource_type: Optional[str] = None
    readiness_score: Optional[float] = None
    readiness_factors: Optional[dict] = None
    recommended_oci_shape: Optional[str] = None
    recommended_oci_ocpus: Optional[float] = None
    recommended_oci_memory_gb: Optional[float] = None
    os_compat_status: Optional[str] = None
    os_type: Optional[str] = None
    os_version: Optional[str] = None
    current_instance_type: Optional[str] = None
    current_monthly_cost_usd: Optional[float] = None
    projected_oci_monthly_cost_usd: Optional[float] = None
    rightsizing_confidence: Optional[float] = None
    ssm_available: Optional[bool] = None
    sixr_strategy: Optional[str] = None
    sixr_confidence: Optional[float] = None
    # OCM hybrid: per-EC2 badge surfaced in the assessment resources table.
    # Populated from the instance's raw_config + software_inventory at read
    # time (no DB column — the matrix lives in ocm_support.yaml).
    ocm_level: Optional[str] = None                 # full | with_prep | manual | unsupported
    ocm_matched_rule: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AppGroupMemberOut(BaseModel):
    resource_id: str
    resource_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AppGroupOut(BaseModel):
    id: str
    name: str
    workload_type: Optional[str] = None
    grouping_method: Optional[str] = None
    sixr_strategy: Optional[str] = None
    readiness_score: Optional[float] = None
    total_aws_cost_usd: Optional[float] = None
    total_oci_cost_usd: Optional[float] = None
    members: list[AppGroupMemberOut] = []

    model_config = ConfigDict(from_attributes=True)


class TCOReportOut(BaseModel):
    id: str
    aws_monthly_total_usd: float
    oci_monthly_total_usd: float
    annual_savings_usd: float
    savings_percentage: float
    breakdown: Optional[dict] = None
    three_year_tco: Optional[dict] = None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class DependencyEdgeOut(BaseModel):
    id: str
    source_resource_id: Optional[str] = None
    target_resource_id: Optional[str] = None
    source_ip: Optional[str] = None
    target_ip: Optional[str] = None
    port: Optional[int] = None
    protocol: Optional[str] = None
    edge_type: Optional[str] = None
    byte_count: Optional[float] = None
    packet_count: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_str(val) -> Optional[str]:
    if val is None:
        return None
    return str(val)


def _assessment_to_out(a: Assessment) -> AssessmentOut:
    return AssessmentOut(
        id=str(a.id),
        migration_id=str(a.migration_id),
        status=a.status,
        current_step=a.current_step,
        summary=a.summary,
        dependency_artifacts=a.dependency_artifacts,
        error_message=a.error_message,
        created_at=str(a.created_at),
        started_at=_to_str(a.started_at),
        completed_at=_to_str(a.completed_at),
    )


def _run_assessment_in_process(assessment_id: str) -> None:
    """Entry point for the child process -- must be a module-level function."""
    import os
    os.setpgrp()
    os.environ.pop("CLAUDECODE", None)  # Allow Agent SDK nested sessions
    from app.services.assessment_runner import run_assessment
    run_assessment(assessment_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/migrations/{migration_id}/assess", response_model=AssessmentOut, status_code=201)
async def create_assessment(
    migration_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new assessment and spawn a child process to execute it."""
    # Verify migration belongs to tenant
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(migration_id),
            Migration.tenant_id == tenant.id,
        )
    )
    migration = result.scalar_one_or_none()
    if not migration:
        raise HTTPException(status_code=404, detail="Migration not found")

    # Create assessment record
    assessment = Assessment(
        migration_id=migration.id,
        tenant_id=tenant.id,
        status="pending",
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)

    assessment_id = str(assessment.id)

    # Spawn child process
    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(
        target=_run_assessment_in_process,
        args=(assessment_id,),
        daemon=True,
    )
    _running_assessment_processes[assessment_id] = p
    p.start()

    return _assessment_to_out(assessment)


@router.get("/migrations/{migration_id}/assessments", response_model=list[AssessmentOut])
async def list_assessments(
    migration_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all assessments for a migration."""
    # Verify migration belongs to tenant
    mig_result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(migration_id),
            Migration.tenant_id == tenant.id,
        )
    )
    if not mig_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Migration not found")

    result = await db.execute(
        select(Assessment)
        .where(
            Assessment.migration_id == uuid.UUID(migration_id),
            Assessment.tenant_id == tenant.id,
        )
        .order_by(Assessment.created_at.desc())
    )
    rows = result.scalars().all()
    return [_assessment_to_out(a) for a in rows]


@router.get("/assessments/{assessment_id}", response_model=AssessmentOut)
async def get_assessment(
    assessment_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get a single assessment by ID."""
    result = await db.execute(
        select(Assessment).where(
            Assessment.id == uuid.UUID(assessment_id),
            Assessment.tenant_id == tenant.id,
        )
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return _assessment_to_out(assessment)


@router.get("/assessments/{assessment_id}/resources", response_model=list[ResourceAssessmentOut])
async def get_resource_assessments(
    assessment_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List resource assessments for an assessment."""
    # Verify ownership
    asmt_result = await db.execute(
        select(Assessment).where(
            Assessment.id == uuid.UUID(assessment_id),
            Assessment.tenant_id == tenant.id,
        )
    )
    if not asmt_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Assessment not found")

    result = await db.execute(
        select(ResourceAssessment).where(
            ResourceAssessment.assessment_id == uuid.UUID(assessment_id),
        )
    )
    rows = result.scalars().all()

    # Batch-load resource names, types, and raw_configs (latter used for OCM
    # compatibility check on EC2 rows).
    resource_ids = [ra.resource_id for ra in rows]
    resource_map: dict[uuid.UUID, tuple[str, str, dict]] = {}
    if resource_ids:
        res_result = await db.execute(
            select(Resource.id, Resource.name, Resource.aws_type, Resource.raw_config).where(
                Resource.id.in_(resource_ids)
            )
        )
        for rid, rname, rtype, rraw in res_result.all():
            resource_map[rid] = (rname or "", rtype or "", rraw or {})

    from app.services.ocm_compatibility import check_ec2_compatibility
    out = []
    for ra in rows:
        rname, rtype, rraw = resource_map.get(ra.resource_id, ("", "", {}))
        ocm_level: Optional[str] = None
        ocm_rule: Optional[str] = None
        if rtype == "AWS::EC2::Instance":
            try:
                compat = check_ec2_compatibility(
                    rraw,
                    rraw.get("software_inventory") if isinstance(rraw, dict) else None,
                    recommended_shape=ra.recommended_oci_shape,
                )
                ocm_level = compat.get("level")
                ocm_rule = compat.get("matched_rule")
            except Exception:
                pass
        out.append(ResourceAssessmentOut(
            id=str(ra.id),
            resource_id=str(ra.resource_id),
            resource_name=rname,
            resource_type=rtype,
            readiness_score=ra.readiness_score,
            readiness_factors=ra.readiness_factors,
            recommended_oci_shape=ra.recommended_oci_shape,
            recommended_oci_ocpus=ra.recommended_oci_ocpus,
            recommended_oci_memory_gb=ra.recommended_oci_memory_gb,
            os_compat_status=ra.os_compat_status,
            os_type=ra.os_type,
            os_version=ra.os_version,
            current_instance_type=ra.current_instance_type,
            current_monthly_cost_usd=ra.current_monthly_cost_usd,
            projected_oci_monthly_cost_usd=ra.projected_oci_monthly_cost_usd,
            rightsizing_confidence=ra.rightsizing_confidence,
            ssm_available=ra.ssm_available,
            sixr_strategy=ra.sixr_strategy,
            sixr_confidence=ra.sixr_confidence,
            ocm_level=ocm_level,
            ocm_matched_rule=ocm_rule,
        ))
    return out


@router.get("/assessments/{assessment_id}/app-groups", response_model=list[AppGroupOut])
async def get_app_groups(
    assessment_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List application groups for an assessment."""
    # Verify ownership
    asmt_result = await db.execute(
        select(Assessment).where(
            Assessment.id == uuid.UUID(assessment_id),
            Assessment.tenant_id == tenant.id,
        )
    )
    if not asmt_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Assessment not found")

    result = await db.execute(
        select(AppGroup).where(
            AppGroup.assessment_id == uuid.UUID(assessment_id),
        )
    )
    groups = result.scalars().all()

    # Load all members in bulk
    group_ids = [g.id for g in groups]
    members_by_group: dict[uuid.UUID, list[AppGroupMember]] = {gid: [] for gid in group_ids}
    if group_ids:
        mem_result = await db.execute(
            select(AppGroupMember).where(
                AppGroupMember.app_group_id.in_(group_ids)
            )
        )
        for m in mem_result.scalars().all():
            members_by_group[m.app_group_id].append(m)

    # Load resource names for all members
    all_resource_ids = set()
    for members in members_by_group.values():
        for m in members:
            all_resource_ids.add(m.resource_id)

    resource_name_map: dict[uuid.UUID, str] = {}
    if all_resource_ids:
        res_result = await db.execute(
            select(Resource.id, Resource.name).where(
                Resource.id.in_(list(all_resource_ids))
            )
        )
        for rid, rname in res_result.all():
            resource_name_map[rid] = rname or ""

    out = []
    for g in groups:
        members = members_by_group.get(g.id, [])
        member_out = [
            AppGroupMemberOut(
                resource_id=str(m.resource_id),
                resource_name=resource_name_map.get(m.resource_id, ""),
            )
            for m in members
        ]
        out.append(AppGroupOut(
            id=str(g.id),
            name=g.name,
            workload_type=g.workload_type,
            grouping_method=g.grouping_method,
            sixr_strategy=g.sixr_strategy,
            readiness_score=g.readiness_score,
            total_aws_cost_usd=g.total_aws_cost_usd,
            total_oci_cost_usd=g.total_oci_cost_usd,
            members=member_out,
        ))
    return out


@router.get("/app-groups/{app_group_id}/resource-details")
async def get_app_group_resource_details(
    app_group_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return per-resource enrichment for every member of an app group.

    Drives the "View Resources" modal on the Workloads tab — one row per
    resource with pre-formatted summary fields so the frontend doesn't
    have to reshape raw_config itself.

    Each row carries:
      - id, aws_type, aws_type_short, name, aws_arn
      - aws_config_summary   : one-line "m5.large · us-east-1a · Oracle Linux 9 · vpc-abc"
      - usage                : CloudWatch {CPUUtilization/mem_used_percent/NetworkIn} p95 summary
      - oci_mapping_raw      : {oci_terraform, oci_service, oci_resource_label, skill, confidence}
                              — NO rightsizing. Straight lookup from resources.yaml.
      - ocm_compatibility    : full OCM compat dict (EC2 only, null otherwise)
      - raw_config           : the full dict so the "View raw" button can render it
    """
    from app.services.resource_details import _oci_mapping
    from app.services.ocm_compatibility import check_ec2_compatibility

    ag_result = await db.execute(
        select(AppGroup).where(
            AppGroup.id == uuid.UUID(app_group_id),
            AppGroup.tenant_id == tenant.id,
        )
    )
    ag = ag_result.scalar_one_or_none()
    if not ag:
        raise HTTPException(status_code=404, detail="App group not found")

    mem_result = await db.execute(
        select(AppGroupMember).where(AppGroupMember.app_group_id == ag.id)
    )
    members = mem_result.scalars().all()
    resource_ids = [m.resource_id for m in members]
    if not resource_ids:
        return []

    res_result = await db.execute(
        select(Resource).where(Resource.id.in_(resource_ids))
    )

    # Load this app-group's ResourceAssessment rows so we can feed the
    # rightsizer-picked shape into the OCM compat check (catches
    # target-shape-not-on-whitelist cases that a source-only check misses).
    shape_by_resource: dict[uuid.UUID, str] = {}
    if ag.assessment_id:
        ra_rows = await db.execute(
            select(ResourceAssessment).where(
                ResourceAssessment.assessment_id == ag.assessment_id,
                ResourceAssessment.resource_id.in_(resource_ids),
            )
        )
        for ra in ra_rows.scalars().all():
            if ra.recommended_oci_shape:
                shape_by_resource[ra.resource_id] = ra.recommended_oci_shape

    out: list[dict] = []
    for r in res_result.scalars().all():
        rc = r.raw_config or {}
        row = {
            "id": str(r.id),
            "aws_type": r.aws_type,
            "aws_type_short": _short_aws_type(r.aws_type or ""),
            "name": r.name or "",
            "aws_arn": r.aws_arn or "",
            "aws_config_summary": _aws_config_summary(r.aws_type or "", rc),
            "usage": _usage_summary(rc),
            "oci_mapping_raw": _oci_mapping(r.aws_type),
            "ocm_compatibility": None,
            "raw_config": rc,
        }
        if r.aws_type == "AWS::EC2::Instance":
            try:
                row["ocm_compatibility"] = check_ec2_compatibility(
                    rc,
                    rc.get("software_inventory") if isinstance(rc, dict) else None,
                    recommended_shape=shape_by_resource.get(r.id),
                )
            except Exception:
                pass
        out.append(row)
    return out


def _short_aws_type(t: str) -> str:
    parts = t.split("::")
    return "::".join(parts[1:]) if len(parts) >= 3 else t


def _aws_config_summary(aws_type: str, rc: dict) -> str:
    """One-line human-readable summary of the resource's headline config.

    Picks 3-5 fields that matter per resource type. Formatted with
    middle-dot separators so the UI can render it as a compact line.
    """
    if not isinstance(rc, dict):
        return ""
    parts: list[str] = []

    def _add(val: object, fmt: str | None = None) -> None:
        if val in (None, "", 0, False):
            return
        parts.append(fmt.format(val) if fmt else str(val))

    if aws_type == "AWS::EC2::Instance":
        _add(rc.get("instance_type"))
        _add(rc.get("availability_zone"))
        inv = rc.get("software_inventory") or {}
        os_name = inv.get("os_name") or rc.get("platform_details") or rc.get("platform")
        if os_name:
            ver = inv.get("os_version") or ""
            parts.append(f"{os_name} {ver}".strip())
        _add(rc.get("private_ip_address"), "ip:{}")
        _add(rc.get("vpc_id"))
    elif aws_type == "AWS::EC2::Volume":
        _add(rc.get("size_gb"), "{}GB")
        _add(rc.get("volume_type"))
        _add(rc.get("iops"), "{}iops")
        _add(rc.get("throughput_mbps"), "{}MB/s")
        if rc.get("encrypted"):
            parts.append("encrypted")
    elif aws_type == "AWS::RDS::DBInstance":
        _add(rc.get("engine"))
        _add(rc.get("engine_version"))
        _add(rc.get("db_instance_class"))
        _add(rc.get("allocated_storage_gb"), "{}GB")
        if rc.get("multi_az"):
            parts.append("multi-AZ")
    elif aws_type == "AWS::Lambda::Function":
        _add(rc.get("runtime"))
        _add(rc.get("memory_size_mb"), "{}MB")
        _add(rc.get("timeout_seconds"), "{}s")
        archs = rc.get("architectures") or []
        if archs:
            parts.append(",".join(archs))
    elif aws_type == "AWS::S3::Bucket":
        _add(rc.get("region"))
        _add(rc.get("versioning_status"))
        _add(rc.get("encryption_type"))
    elif aws_type == "AWS::EC2::VPC":
        _add(rc.get("cidr_block"))
        subnets = rc.get("subnets") or []
        if subnets:
            parts.append(f"{len(subnets)} subnet(s)")
    elif aws_type == "AWS::EC2::Subnet":
        _add(rc.get("cidr_block"))
        _add(rc.get("availability_zone"))
    elif aws_type == "AWS::EC2::SecurityGroup":
        ingress = rc.get("ingress_rules") or []
        egress = rc.get("egress_rules") or []
        parts.append(f"{len(ingress)} ingress / {len(egress)} egress rule(s)")
        _add(rc.get("vpc_id"))
    elif aws_type == "AWS::ElasticLoadBalancingV2::LoadBalancer":
        _add(rc.get("type"))
        _add(rc.get("dns_name"))
    elif aws_type == "AWS::AutoScaling::AutoScalingGroup":
        _add(rc.get("min_size"), "min={}")
        _add(rc.get("max_size"), "max={}")
        _add(rc.get("desired_capacity"), "desired={}")
    else:
        # Generic fallback — lift any handful of scalar fields
        for k in ("region", "type", "engine", "state", "status", "size_gb"):
            _add(rc.get(k))
    return " · ".join(parts) if parts else "—"


def _usage_summary(rc: dict) -> dict | None:
    """CloudWatch p95 summary for the resource (EC2 only today).

    Returns ``{cpu_p95, mem_p95, net_in_p95_mbps, disk_read_p95, ...}`` when
    metrics were captured at discovery; None otherwise.
    """
    if not isinstance(rc, dict):
        return None
    metrics = rc.get("metrics") or {}
    if not metrics:
        return None
    def _p95(name: str) -> float | None:
        val = (metrics.get(name) or {}).get("p95")
        return round(val, 1) if isinstance(val, (int, float)) else None
    return {
        "cpu_p95":          _p95("CPUUtilization"),
        "mem_p95":          _p95("mem_used_percent"),
        "net_in_p95":       _p95("NetworkIn"),
        "net_out_p95":      _p95("NetworkOut"),
        "disk_read_p95":    _p95("DiskReadOps"),
        "disk_write_p95":   _p95("DiskWriteOps"),
    }


@router.get("/app-groups/{app_group_id}/resource-mapping")
async def get_resource_mapping(
    app_group_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Compute AWS → OCI resource mapping for an app group.

    Returns a deterministic mapping enriched by LLM review.
    """
    from app.services.resource_mapper import (
        compute_resource_mapping,
        review_mapping_with_llm,
    )

    # Load app group
    ag_result = await db.execute(
        select(AppGroup).where(
            AppGroup.id == uuid.UUID(app_group_id),
            AppGroup.tenant_id == tenant.id,
        )
    )
    ag = ag_result.scalar_one_or_none()
    if not ag:
        raise HTTPException(status_code=404, detail="App group not found")

    # Load member resources
    mem_result = await db.execute(
        select(AppGroupMember).where(AppGroupMember.app_group_id == ag.id)
    )
    members = mem_result.scalars().all()
    resource_ids = [m.resource_id for m in members]

    if not resource_ids:
        return []

    res_result = await db.execute(
        select(Resource).where(Resource.id.in_(resource_ids))
    )
    resources = res_result.scalars().all()
    resource_dicts = [
        {
            "id": str(r.id),
            "name": r.name,
            "aws_type": r.aws_type,
            "raw_config": r.raw_config or {},
        }
        for r in resources
    ]

    # Load resource assessments for these resources
    ra_result = await db.execute(
        select(ResourceAssessment).where(
            ResourceAssessment.resource_id.in_(resource_ids),
            ResourceAssessment.assessment_id == ag.assessment_id,
        )
    )
    ra_map = {}
    inv_map = {}
    for ra in ra_result.scalars().all():
        ra_map[str(ra.resource_id)] = {
            "recommended_oci_shape": ra.recommended_oci_shape,
            "recommended_oci_ocpus": ra.recommended_oci_ocpus,
            "recommended_oci_memory_gb": ra.recommended_oci_memory_gb,
            "projected_oci_monthly_cost_usd": ra.projected_oci_monthly_cost_usd,
            "os_compat_status": ra.os_compat_status,
        }
        if ra.software_inventory:
            inv_map[str(ra.resource_id)] = ra.software_inventory

    # Step 1: Deterministic mapping
    entries = compute_resource_mapping(resource_dicts, ra_map, inv_map)

    # Step 2: LLM review
    try:
        from app.gateway.model_gateway import get_anthropic_client
        client = get_anthropic_client()
        entries = review_mapping_with_llm(entries, ag.name, client)
    except Exception:
        pass  # Fall back to deterministic mapping

    return [e.to_dict() for e in entries]


@router.get("/assessments/{assessment_id}/tco", response_model=TCOReportOut)
async def get_tco_report(
    assessment_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get the TCO report for an assessment."""
    # Verify ownership
    asmt_result = await db.execute(
        select(Assessment).where(
            Assessment.id == uuid.UUID(assessment_id),
            Assessment.tenant_id == tenant.id,
        )
    )
    if not asmt_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Assessment not found")

    result = await db.execute(
        select(TCOReport).where(
            TCOReport.assessment_id == uuid.UUID(assessment_id),
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="TCO report not found")

    return TCOReportOut(
        id=str(report.id),
        aws_monthly_total_usd=report.aws_monthly_total_usd,
        oci_monthly_total_usd=report.oci_monthly_total_usd,
        annual_savings_usd=report.annual_savings_usd,
        savings_percentage=report.savings_percentage,
        breakdown=report.breakdown,
        three_year_tco=report.three_year_tco,
        created_at=str(report.created_at),
    )


@router.get("/assessments/{assessment_id}/dependencies", response_model=list[DependencyEdgeOut])
async def get_dependencies(
    assessment_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List dependency edges for an assessment."""
    # Verify ownership
    asmt_result = await db.execute(
        select(Assessment).where(
            Assessment.id == uuid.UUID(assessment_id),
            Assessment.tenant_id == tenant.id,
        )
    )
    if not asmt_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Assessment not found")

    result = await db.execute(
        select(DependencyEdge).where(
            DependencyEdge.assessment_id == uuid.UUID(assessment_id),
        )
    )
    rows = result.scalars().all()

    return [
        DependencyEdgeOut(
            id=str(e.id),
            source_resource_id=_to_str(e.source_resource_id),
            target_resource_id=_to_str(e.target_resource_id),
            source_ip=e.source_ip,
            target_ip=e.target_ip,
            port=e.port,
            protocol=e.protocol,
            edge_type=e.edge_type,
            byte_count=e.byte_count,
            packet_count=e.packet_count,
        )
        for e in rows
    ]


@router.get("/app-groups/{app_group_id}/plan-results")
async def get_workload_plan_results(
    app_group_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get the generated plan results for a workload (app group)."""
    ag_result = await db.execute(
        select(AppGroup).where(
            AppGroup.id == uuid.UUID(app_group_id),
            AppGroup.tenant_id == tenant.id,
        )
    )
    ag = ag_result.scalar_one_or_none()
    if not ag:
        raise HTTPException(status_code=404, detail="App group not found")

    # Load assessment's dependency_artifacts which stores workload plans
    asmt_result = await db.execute(
        select(Assessment).where(Assessment.id == ag.assessment_id)
    )
    asmt = asmt_result.scalar_one_or_none()
    if not asmt:
        raise HTTPException(status_code=404, detail="Assessment not found")

    arts = asmt.dependency_artifacts or {}
    workload_plans = arts.get("workload_plans", {})
    plan = workload_plans.get(ag.name)

    if not plan:
        return {"status": "not_started"}

    return {
        "status": plan.get("status", "not_started"),
        "current_step": plan.get("current_step"),
        "elapsed_seconds": plan.get("elapsed_seconds"),
        "logs": plan.get("logs", []),
        "resource_mapping": plan.get("resource_mapping", []),
        "artifacts": plan.get("artifacts", {}),
        "skills_ran": plan.get("skills_ran", []),
        "max_iterations": plan.get("max_iterations"),
        "completed_at": plan.get("completed_at"),
    }


@router.get("/assessments/{assessment_id}/dependency-artifacts")
async def get_dependency_artifacts(
    assessment_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return dependency discovery artifacts."""
    result = await db.execute(
        select(Assessment).where(
            Assessment.id == uuid.UUID(assessment_id),
            Assessment.tenant_id == tenant.id,
        )
    )
    asmt = result.scalar_one_or_none()
    if not asmt:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return asmt.dependency_artifacts or {}


@router.get("/assessments/{assessment_id}/workload-graph/{workload_name}")
async def get_workload_graph(
    assessment_id: str,
    workload_name: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return SVG dependency graph for a specific workload."""
    from fastapi.responses import Response

    result = await db.execute(
        select(Assessment).where(
            Assessment.id == uuid.UUID(assessment_id),
            Assessment.tenant_id == tenant.id,
        )
    )
    asmt = result.scalar_one_or_none()
    if not asmt:
        raise HTTPException(status_code=404, detail="Assessment not found")

    artifacts = asmt.dependency_artifacts or {}
    graphs = artifacts.get("workload_graphs", {})
    svg = graphs.get(workload_name)
    if not svg:
        raise HTTPException(status_code=404, detail="Graph not found for this workload")

    return Response(content=svg, media_type="image/svg+xml")


@router.delete("/assessments/{assessment_id}", status_code=204)
async def delete_assessment(
    assessment_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete an assessment and all associated records."""
    result = await db.execute(
        select(Assessment).where(
            Assessment.id == uuid.UUID(assessment_id),
            Assessment.tenant_id == tenant.id,
        )
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Terminate the child process if still running
    proc = _running_assessment_processes.pop(assessment_id, None)
    if proc is not None and proc.is_alive():
        import os
        import signal
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        proc.join(timeout=5)
        if proc.is_alive():
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    asmt_uuid = uuid.UUID(assessment_id)

    # Delete child records (AppGroupMember -> AppGroup, ResourceAssessment,
    # DependencyEdge, TCOReport are cascade="all, delete-orphan" on Assessment,
    # but AppGroupMember FK to AppGroup needs explicit handling)
    ag_result = await db.execute(
        select(AppGroup.id).where(AppGroup.assessment_id == asmt_uuid)
    )
    ag_ids = [row[0] for row in ag_result.all()]
    if ag_ids:
        await db.execute(
            sa_delete(AppGroupMember).where(AppGroupMember.app_group_id.in_(ag_ids))
        )

    # Delete the assessment (cascades to resource_assessments, app_groups,
    # tco_report, dependency_edges via ORM cascade)
    await db.delete(assessment)
    await db.commit()
