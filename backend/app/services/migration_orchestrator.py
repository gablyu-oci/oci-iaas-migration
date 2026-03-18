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
    Migration,
    MigrationPlan,
    PlanPhase,
    Resource,
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

    # -- VPCs: one workload per VPC resource ---------------------------------
    if skill == "network_translation":
        groups: list[tuple[str, str, list[Resource]]] = []
        for r in matched_resources:
            vpc_id = _safe_raw(r).get("vpc_id", r.name or "unknown")
            name = f"VPC {vpc_id} workload"
            desc = f"Migrate VPC {vpc_id}"
            groups.append((name, desc, [r]))
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
        description="Translate VPCs, subnets, and security groups to OCI VCNs.",
        aws_types=("AWS::EC2::VPC",),
        skill_type="network_translation",
    ),
    _PhaseDef(
        name="Data Layer",
        description="Translate RDS instances to OCI database services.",
        aws_types=("AWS::RDS::DBInstance",),
        skill_type="database_translation",
    ),
    _PhaseDef(
        name="Application Layer",
        description="Translate EC2 instances and Auto Scaling groups to OCI Compute.",
        aws_types=("AWS::EC2::Instance", "AWS::AutoScaling::AutoScalingGroup"),
        skill_type="ec2_translation",
    ),
    _PhaseDef(
        name="Traffic Management",
        description="Translate ALB / NLB load balancers to OCI Load Balancer.",
        aws_types=("AWS::ElasticLoadBalancingV2::LoadBalancer",),
        skill_type="loadbalancer_translation",
    ),
    _PhaseDef(
        name="Serverless",
        description="Lambda function translation (Phase 3 -- future).",
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
        description="Translate IAM policies to OCI IAM policy statements.",
        aws_types=("AWS::IAM::Policy",),
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

    if skill_type == "network_translation":
        # The network skill expects a single VPC JSON object.  When multiple
        # VPCs exist we take the first -- multi-VPC support can be added later.
        return json.dumps(raw_configs[0], indent=2)

    if skill_type == "ec2_translation":
        instances = [
            cfg
            for cfg, r in zip(raw_configs, resources)
            if r.aws_type == "AWS::EC2::Instance"
        ]
        asgs = [
            cfg
            for cfg, r in zip(raw_configs, resources)
            if r.aws_type == "AWS::AutoScaling::AutoScalingGroup"
        ]
        return json.dumps(
            {"instances": instances, "auto_scaling_groups": asgs},
            indent=2,
        )

    if skill_type == "database_translation":
        return json.dumps({"db_instances": raw_configs}, indent=2)

    if skill_type == "loadbalancer_translation":
        return json.dumps({"load_balancers": raw_configs}, indent=2)

    if skill_type == "cfn_terraform":
        # CloudFormation template stored as the raw_config dict.
        return json.dumps(raw_configs[0], indent=2)

    if skill_type == "iam_translation":
        # IAM policy document JSON.
        return json.dumps(raw_configs[0], indent=2)

    logger.warning("Unknown skill_type '%s' -- returning None", skill_type)
    return None
