"""Migration plan generator -- groups discovered AWS resources into phased workloads.

The generator queries all Resources for a given migration and organises them
into an ordered set of phases based on AWS resource type.  The phase ordering
reflects a safe dependency sequence for cloud migrations:

    Phase 1  Networking Foundation   (VPCs, subnets, security groups)
    Phase 2  Data Layer              (RDS databases)
    Phase 3  Application Layer       (EC2 instances, Auto Scaling groups)
    Phase 4  Traffic Management      (Load balancers)
    Phase 5  Serverless              (Lambda functions -- future)
    Phase 6  Infrastructure as Code  (CloudFormation stacks)
    Phase 7  Identity & Access       (IAM policies)

Each phase contains one or more workloads grouped by logical affinity (e.g.
one workload per VPC, EC2 instances grouped by VPC, RDS instances grouped
by DB subnet group).  Every workload is tagged with the ``skill_type`` that
will later drive the AI translation agent.
A helper function (``build_workload_input``) serialises the workload's
resources into the JSON shape expected by the corresponding skill orchestrator.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workload grouping helper
# ---------------------------------------------------------------------------

def _group_resources(
    phase_def: "_PhaseDef",
    matched_resources: list[Resource],
) -> list[tuple[str, str, list[Resource]]]:
    """Return a list of ``(workload_name, workload_description, resources)`` tuples.

    Each tuple represents one workload to create inside the phase.  The
    grouping strategy depends on the skill type so that logically related
    resources (e.g. all EC2 instances inside the same VPC) stay together.
    """

    def _safe_raw(r: Resource) -> dict:
        return r.raw_config if r.raw_config else {}

    skill = phase_def.skill_type

    # -- Network resources: one workload per VPC (all types aggregated) ------
    if skill == "network_translation":
        buckets: dict[str, list[Resource]] = {}
        for r in matched_resources:
            raw = _safe_raw(r)
            # VPC resources carry their own vpc_id; subnets/SGs/ENIs carry it too
            vpc_id = raw.get("vpc_id", r.name or "unknown")
            buckets.setdefault(vpc_id, []).append(r)
        groups: list[tuple[str, str, list[Resource]]] = []
        for vpc_id, resources in buckets.items():
            name = f"VPC {vpc_id} workload"
            desc = f"Migrate VPC {vpc_id} networking ({len(resources)} resource(s))"
            groups.append((name, desc, resources))
        return groups

    # -- EC2 instances: group by VPC ID --------------------------------------
    if skill == "ec2_translation":
        buckets: dict[str | None, list[Resource]] = {}
        for r in matched_resources:
            vpc_id = _safe_raw(r).get("vpc_id")
            buckets.setdefault(vpc_id, []).append(r)
        groups = []
        for vpc_id, resources in buckets.items():
            if vpc_id is not None:
                name = f"EC2 VPC {vpc_id} workload"
                desc = f"Migrate {len(resources)} EC2/ASG resource(s) in VPC {vpc_id}"
            else:
                name = "EC2 workload"
                desc = f"Migrate {len(resources)} EC2/ASG resource(s)"
            groups.append((name, desc, resources))
        return groups

    # -- RDS instances: group by DB subnet group -----------------------------
    if skill == "database_translation":
        buckets = {}
        for r in matched_resources:
            raw = _safe_raw(r)
            sg = raw.get("db_subnet_group", {})
            # sg may be a dict with a "name" key, or the value may be stored
            # at the top-level key "db_subnet_group_name".
            if isinstance(sg, dict):
                group_name = sg.get("name")
            else:
                group_name = None
            if group_name is None:
                group_name = raw.get("db_subnet_group_name")
            buckets.setdefault(group_name, []).append(r)
        groups = []
        for sg_name, resources in buckets.items():
            if sg_name is not None:
                name = f"RDS {sg_name} workload"
                desc = f"Migrate {len(resources)} RDS instance(s) in subnet group {sg_name}"
            else:
                name = "RDS workload"
                desc = f"Migrate {len(resources)} RDS instance(s)"
            groups.append((name, desc, resources))
        return groups

    # -- Load balancers: single workload ------------------------------------
    if skill == "loadbalancer_translation":
        name = "Load Balancer workload"
        desc = f"Migrate {len(matched_resources)} load balancer(s)"
        return [(name, desc, matched_resources)]

    # -- CloudFormation stacks: one workload per stack ----------------------
    if skill == "cfn_terraform":
        groups = []
        for r in matched_resources:
            stack_name = _safe_raw(r).get("stack_name", r.name or "unknown")
            name = f"CFN {stack_name} workload"
            desc = f"Convert CloudFormation stack {stack_name} to Terraform"
            groups.append((name, desc, [r]))
        return groups

    # -- IAM policies: one workload per policy ------------------------------
    if skill == "iam_translation":
        groups = []
        for r in matched_resources:
            policy_name = _safe_raw(r).get("PolicyName", r.name or "unknown")
            name = f"IAM {policy_name} workload"
            desc = f"Translate IAM policy {policy_name} to OCI"
            groups.append((name, desc, [r]))
        return groups

    # -- EBS volumes: single workload with all volumes -----------------------
    if skill == "storage_translation":
        name = "Storage workload"
        desc = f"Migrate {len(matched_resources)} EBS volume(s) to OCI Block Volume"
        return [(name, desc, matched_resources)]

    # -- Lambda / future: single workload -----------------------------------
    name = "Lambda workload"
    desc = f"Migrate {len(matched_resources)} Lambda function(s)"
    return [(name, desc, matched_resources)]


# ---------------------------------------------------------------------------
# Phase definitions -- order matters (it becomes the migration sequence).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _PhaseDef:
    """Internal definition for a migration phase."""

    name: str
    description: str
    aws_types: tuple[str, ...]
    skill_type: Optional[str]


PHASE_DEFINITIONS: list[_PhaseDef] = [
    _PhaseDef(
        name="Networking Foundation",
        description="Translate VPCs, subnets, security groups, and network interfaces to OCI VCNs.",
        aws_types=(
            "AWS::EC2::VPC",
            "AWS::EC2::Subnet",
            "AWS::EC2::SecurityGroup",
            "AWS::EC2::NetworkInterface",
        ),
        skill_type="network_translation",
    ),
    _PhaseDef(
        name="Data Layer",
        description="Translate RDS instances and clusters to OCI database services.",
        aws_types=("AWS::RDS::DBInstance", "AWS::RDS::DBCluster"),
        skill_type="database_translation",
    ),
    _PhaseDef(
        name="Application Layer",
        description="Translate EC2 instances and Auto Scaling groups to OCI Compute.",
        aws_types=("AWS::EC2::Instance", "AWS::AutoScaling::AutoScalingGroup"),
        skill_type="ec2_translation",
    ),
    _PhaseDef(
        name="Storage",
        description="Translate EBS volumes to OCI Block Volumes.",
        aws_types=("AWS::EC2::Volume",),
        skill_type="storage_translation",
    ),
    _PhaseDef(
        name="Traffic Management",
        description="Translate ALB / NLB load balancers to OCI Load Balancer.",
        aws_types=("AWS::ElasticLoadBalancingV2::LoadBalancer",),
        skill_type="loadbalancer_translation",
    ),
    _PhaseDef(
        name="Serverless",
        description="Lambda function translation.",
        aws_types=("AWS::Lambda::Function",),
        skill_type=None,
    ),
    _PhaseDef(
        name="Infrastructure as Code",
        description="Convert CloudFormation templates to Terraform for OCI.",
        aws_types=("AWS::CloudFormation::Stack",),
        skill_type="cfn_terraform",
    ),
    _PhaseDef(
        name="Identity & Access",
        description="Translate IAM policies and roles to OCI IAM policy statements.",
        aws_types=("AWS::IAM::Policy", "AWS::IAM::Role"),
        skill_type="iam_translation",
    ),
]


# ---------------------------------------------------------------------------
# Plan generator
# ---------------------------------------------------------------------------

async def generate_plan(
    migration_id: uuid.UUID,
    tenant_id: uuid.UUID,
    db: AsyncSession,
) -> MigrationPlan:
    """Build a :class:`MigrationPlan` for *migration_id*.

    The plan groups every discovered :class:`Resource` into dependency-ordered
    phases and workloads.  Only phases that contain at least one matching
    resource are created -- empty phases are omitted to keep the plan concise.

    If a plan already exists for this migration it is deleted first so the
    caller can safely regenerate.

    Parameters
    ----------
    migration_id:
        Primary key of the :class:`Migration` to plan.
    tenant_id:
        Owning tenant -- propagated to every child record for row-level security.
    db:
        An active SQLAlchemy ``AsyncSession``.

    Returns
    -------
    MigrationPlan
        The newly created plan with its ``phases`` relationship populated.

    Raises
    ------
    ValueError
        If the migration does not exist or does not belong to the tenant.
    """

    # -- 0. Verify migration ownership ----------------------------------------
    mig_result = await db.execute(
        select(Migration).where(
            Migration.id == migration_id,
            Migration.tenant_id == tenant_id,
        )
    )
    if mig_result.scalar_one_or_none() is None:
        raise ValueError(
            f"Migration {migration_id} not found for tenant {tenant_id}"
        )

    # -- 1. Delete any previous plan for this migration -----------------------
    await _delete_existing_plan(migration_id, db)

    # -- 2. Fetch all resources belonging to this migration -------------------
    result = await db.execute(
        select(Resource).where(
            Resource.migration_id == migration_id,
            Resource.tenant_id == tenant_id,
        )
    )
    resources: list[Resource] = list(result.scalars().all())

    # -- 3. Index resources by AWS type for fast lookup -----------------------
    resources_by_type: dict[str, list[Resource]] = {}
    for r in resources:
        key = r.aws_type or "__unknown__"
        resources_by_type.setdefault(key, []).append(r)

    # -- 4. Build plan-level summary ------------------------------------------
    type_counts = {t: len(rs) for t, rs in resources_by_type.items()}

    plan = MigrationPlan(
        migration_id=migration_id,
        tenant_id=tenant_id,
        status="draft",
        summary={
            "total_resources": len(resources),
            "resource_types": type_counts,
        },
    )
    db.add(plan)
    await db.flush()  # materialise plan.id

    # -- 5. Create phases and workloads ---------------------------------------
    phase_order = 0
    for phase_def in PHASE_DEFINITIONS:
        matched: list[Resource] = []
        for aws_type in phase_def.aws_types:
            matched.extend(resources_by_type.get(aws_type, []))

        if not matched:
            continue

        phase_order += 1
        phase = PlanPhase(
            plan_id=plan.id,
            tenant_id=tenant_id,
            name=phase_def.name,
            description=phase_def.description,
            order_index=phase_order,
            status="pending",
        )
        db.add(phase)
        await db.flush()  # materialise phase.id

        # Create one or more workloads per phase depending on resource grouping.
        groups = _group_resources(phase_def, matched)
        for wl_name, wl_desc, wl_resources in groups:
            workload = Workload(
                phase_id=phase.id,
                tenant_id=tenant_id,
                name=wl_name,
                description=wl_desc,
                skill_type=phase_def.skill_type,
                status="pending",
            )
            db.add(workload)
            await db.flush()  # materialise workload.id

            for resource in wl_resources:
                db.add(
                    WorkloadResource(
                        workload_id=workload.id,
                        resource_id=resource.id,
                    )
                )

    await db.flush()

    # -- 6. Reload with eagerly populated relationships -----------------------
    result = await db.execute(
        select(MigrationPlan)
        .where(MigrationPlan.id == plan.id)
        .options(
            selectinload(MigrationPlan.phases)
            .selectinload(PlanPhase.workloads)
            .selectinload(Workload.resources)
        )
    )
    plan = result.scalar_one()

    logger.info(
        "Generated migration plan %s with %d phase(s) for migration %s",
        plan.id,
        len(plan.phases),
        migration_id,
    )
    return plan


async def _delete_existing_plan(
    migration_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Remove a previous plan and all its children for *migration_id*.

    Deletes are done bottom-up (workload_resources -> workloads -> phases ->
    plan) so foreign-key constraints are satisfied regardless of whether
    cascading deletes are configured on the database.
    """

    plan_result = await db.execute(
        select(MigrationPlan)
        .where(MigrationPlan.migration_id == migration_id)
        .options(
            selectinload(MigrationPlan.phases)
            .selectinload(PlanPhase.workloads)
        )
    )
    existing_plan = plan_result.scalar_one_or_none()
    if existing_plan is None:
        return

    for phase in existing_plan.phases:
        for workload in phase.workloads:
            await db.execute(
                delete(WorkloadResource).where(
                    WorkloadResource.workload_id == workload.id
                )
            )
        await db.execute(
            delete(Workload).where(Workload.phase_id == phase.id)
        )
    await db.execute(
        delete(PlanPhase).where(PlanPhase.plan_id == existing_plan.id)
    )
    await db.execute(
        delete(MigrationPlan).where(MigrationPlan.id == existing_plan.id)
    )
    await db.flush()


# ---------------------------------------------------------------------------
# Workload input builder -- prepares the content blob for a skill run.
# ---------------------------------------------------------------------------

async def build_workload_input(
    workload_id: uuid.UUID,
    db: AsyncSession,
) -> Optional[str]:
    """Prepare the ``input_content`` string for a skill run tied to *workload_id*.

    Each skill type expects a different JSON shape.  This function loads the
    workload's linked :class:`Resource` records (with their ``raw_config``)
    and serialises them into the format the corresponding skill orchestrator
    expects.

    Returns ``None`` when the workload has no ``skill_type`` (e.g. the
    Serverless phase whose skill is not yet implemented) or when there are no
    resources to process.
    """

    # Load workload with its join-table rows.
    result = await db.execute(
        select(Workload)
        .where(Workload.id == workload_id)
        .options(selectinload(Workload.resources))
    )
    workload: Optional[Workload] = result.scalar_one_or_none()
    if workload is None or workload.skill_type is None:
        return None

    # Resolve full Resource rows via the WorkloadResource join table.
    resource_ids = [wr.resource_id for wr in workload.resources]
    if not resource_ids:
        return None

    res_result = await db.execute(
        select(Resource).where(Resource.id.in_(resource_ids))
    )
    resources: list[Resource] = list(res_result.scalars().all())
    if not resources:
        return None

    return _format_input(workload.skill_type, resources)


def _format_input(skill_type: str, resources: list[Resource]) -> Optional[str]:
    """Serialise *resources* into the JSON shape expected by *skill_type*.

    This is a pure function (no I/O) so it can be unit-tested in isolation.
    """

    raw_configs = [r.raw_config for r in resources if r.raw_config]
    if not raw_configs:
        return None

    # For aggregated skills, return None so the job_runner builds the proper
    # composite input from config["resource_ids"] via its _AGGREGATED_SKILLS map.
    # This ensures VPC/subnet/SG/ENI are all passed together, EC2+EBS together, etc.
    if skill_type in (
        "network_translation",
        "ec2_translation",
        "database_translation",
        "loadbalancer_translation",
        "storage_translation",
    ):
        return None

    if skill_type == "cfn_terraform":
        # CloudFormation template stored as the raw_config dict.
        return json.dumps(raw_configs[0], indent=2)

    if skill_type == "iam_translation":
        # IAM policy document JSON.
        return json.dumps(raw_configs[0], indent=2)

    logger.warning("Unknown skill_type '%s' -- returning None", skill_type)
    return None


# ---------------------------------------------------------------------------
# App-group-based plan generator
# ---------------------------------------------------------------------------

# Map AWS type patterns to skill_type
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
    ("Lambda", None),  # Future
]


def _skill_for_type(aws_type: str) -> Optional[str]:
    """Return the skill_type that handles a given AWS resource type."""
    for pattern, skill in _TYPE_TO_SKILL:
        if pattern in (aws_type or ""):
            return skill
    return None


async def generate_plan_from_app_groups(
    migration_id: uuid.UUID,
    assessment_id: uuid.UUID,
    tenant_id: uuid.UUID,
    db: AsyncSession,
    app_group_ids: list[uuid.UUID] | None = None,
) -> MigrationPlan:
    """Generate a plan from Assessment app groups.

    Each non-singleton app group becomes a PlanPhase. Within each phase,
    workloads are created per skill_type needed, plus data_migration and
    workload_planning workloads if applicable.
    """
    from datetime import datetime, timezone

    # Verify migration
    mig_result = await db.execute(
        select(Migration).where(
            Migration.id == migration_id,
            Migration.tenant_id == tenant_id,
        )
    )
    if mig_result.scalar_one_or_none() is None:
        raise ValueError(f"Migration {migration_id} not found")

    # Delete existing plan
    await _delete_existing_plan(migration_id, db)

    # Load app groups from assessment
    ag_query = select(AppGroup).where(
        AppGroup.assessment_id == assessment_id,
        AppGroup.tenant_id == tenant_id,
    )
    if app_group_ids:
        ag_query = ag_query.where(AppGroup.id.in_(app_group_ids))

    ag_result = await db.execute(ag_query)
    app_groups = list(ag_result.scalars().all())

    # Filter out singletons
    non_singleton = []
    for ag in app_groups:
        mem_result = await db.execute(
            select(AppGroupMember).where(AppGroupMember.app_group_id == ag.id)
        )
        members = list(mem_result.scalars().all())
        if len(members) >= 2 or (app_group_ids and ag.id in app_group_ids):
            non_singleton.append((ag, members))

    if not non_singleton:
        raise ValueError("No eligible app groups found for plan generation")

    # Create plan
    plan = MigrationPlan(
        migration_id=migration_id,
        tenant_id=tenant_id,
        status="draft",
        generated_at=datetime.now(timezone.utc),
        summary={
            "source": "app_groups",
            "assessment_id": str(assessment_id),
            "app_group_count": len(non_singleton),
        },
    )
    db.add(plan)
    await db.flush()

    total_resources = 0

    for order_idx, (ag, members) in enumerate(non_singleton):
        # Create phase for this app group
        phase = PlanPhase(
            plan_id=plan.id,
            tenant_id=tenant_id,
            name=ag.name,
            description=f"Migrate workload: {ag.name} ({ag.workload_type or 'web_api'})",
            order_index=order_idx,
            status="pending",
        )
        db.add(phase)
        await db.flush()

        # Load resources for this group
        resource_ids = [m.resource_id for m in members]
        res_result = await db.execute(
            select(Resource).where(Resource.id.in_(resource_ids))
        )
        resources = list(res_result.scalars().all())
        total_resources += len(resources)

        # Group resources by skill_type
        skill_resources: dict[str, list[Resource]] = {}
        for r in resources:
            skill = _skill_for_type(r.aws_type or "")
            if skill:
                skill_resources.setdefault(skill, []).append(r)

        # Create translation workloads per skill
        for skill_type, skill_resources_list in skill_resources.items():
            skill_label = skill_type.replace("_", " ").title()
            workload = Workload(
                phase_id=phase.id,
                tenant_id=tenant_id,
                name=f"{ag.name} — {skill_label}",
                description=f"Translate {len(skill_resources_list)} resource(s) via {skill_type}",
                skill_type=skill_type,
                status="pending",
                app_group_id=ag.id,
            )
            db.add(workload)
            await db.flush()
            for r in skill_resources_list:
                db.add(WorkloadResource(workload_id=workload.id, resource_id=r.id))

        # Check if data migration planning is needed
        has_rds = any("RDS" in (r.aws_type or "") or "Aurora" in (r.aws_type or "") for r in resources)
        # Also check for local DBs via software inventory
        has_local_db = False
        ec2_ids = [r.id for r in resources if "EC2::Instance" in (r.aws_type or "")]
        if ec2_ids:
            ra_result = await db.execute(
                select(ResourceAssessment).where(
                    ResourceAssessment.resource_id.in_(ec2_ids),
                    ResourceAssessment.assessment_id == assessment_id,
                )
            )
            for ra in ra_result.scalars().all():
                inv = ra.software_inventory or {}
                for app in inv.get("applications", []):
                    app_name = (app.get("Name") or app.get("name") or "").lower()
                    if any(kw in app_name for kw in ("mysql", "mariadb", "postgres", "mongodb", "redis")):
                        has_local_db = True
                        break

        if has_rds or has_local_db:
            dm_workload = Workload(
                phase_id=phase.id,
                tenant_id=tenant_id,
                name=f"{ag.name} — Data Migration",
                description="Plan and execute database data migration",
                skill_type="data_migration_planning",
                status="pending",
                app_group_id=ag.id,
            )
            db.add(dm_workload)
            await db.flush()
            for r in resources:
                db.add(WorkloadResource(workload_id=dm_workload.id, resource_id=r.id))

        # Create workload planning workload (runbook + anomaly)
        wp_workload = Workload(
            phase_id=phase.id,
            tenant_id=tenant_id,
            name=f"{ag.name} — Migration Runbook",
            description="Generate migration runbook and anomaly analysis",
            skill_type="workload_planning",
            status="pending",
            app_group_id=ag.id,
        )
        db.add(wp_workload)
        await db.flush()
        for r in resources:
            db.add(WorkloadResource(workload_id=wp_workload.id, resource_id=r.id))

    plan.summary["total_resources"] = total_resources
    await db.commit()
    await db.refresh(plan)

    logger.info(
        "Generated plan from %d app groups with %d total resources",
        len(non_singleton), total_resources,
    )
    return plan
