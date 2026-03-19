"""AWS connection, migration, and resource extraction endpoints."""

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import (
    AWSConnection, Artifact, Migration, MigrationPlan, PlanPhase,
    Resource, TranslationJob, TranslationJobInteraction, Tenant, Workload, WorkloadResource,
)
from app.api.deps import get_current_tenant
from app.services.aws_extractor import (
    validate_credentials,
    extract_cfn_stacks,
    extract_iam_policies,
    extract_iam_policies_for_instance_profile,
    extract_ec2_instances,
    extract_vpcs,
    extract_subnet_by_id,
    extract_security_groups,
    extract_ebs_volumes,
    extract_network_interfaces,
    extract_rds_instances,
    extract_load_balancers,
    extract_auto_scaling_groups,
    extract_lambda_functions,
)

router = APIRouter(prefix="/api", tags=["aws"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ConnectionCreate(BaseModel):
    name: str
    region: str
    credential_type: str = "key_pair"
    credentials: dict  # {access_key_id, secret_access_key} or {role_arn}


class ConnectionOut(BaseModel):
    id: str
    name: str
    region: str
    credential_type: str
    status: str
    created_at: str

    model_config = {"from_attributes": True}


class MigrationCreate(BaseModel):
    name: str
    aws_connection_id: Optional[str] = None


class MigrationOut(BaseModel):
    id: str
    name: str
    aws_connection_id: Optional[str]
    status: str
    created_at: str
    resource_count: Optional[int] = None

    model_config = {"from_attributes": True}


class LatestSkillRunSummary(BaseModel):
    id: str
    status: str
    skill_type: str
    confidence: float
    completed_at: Optional[str] = None


class ResourceOut(BaseModel):
    id: str
    migration_id: Optional[str]
    aws_type: Optional[str]
    aws_arn: Optional[str]
    name: Optional[str]
    status: str
    created_at: str
    raw_config: Optional[dict] = None
    migration_name: Optional[str] = None
    latest_skill_run: Optional[LatestSkillRunSummary] = None

    model_config = {"from_attributes": True}


class AssignResourcesBody(BaseModel):
    resource_ids: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_str(val):
    """Convert UUID or datetime to string for Pydantic output."""
    if val is None:
        return None
    return str(val)


# ---------------------------------------------------------------------------
# AWS Connections
# ---------------------------------------------------------------------------
@router.post("/aws/connections", response_model=ConnectionOut, status_code=201)
async def create_connection(
    body: ConnectionCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new AWS connection (credentials are validated via STS)."""
    validation = validate_credentials(body.credentials, body.region)
    conn_status = "active" if validation["valid"] else "invalid"

    conn = AWSConnection(
        tenant_id=tenant.id,
        name=body.name,
        region=body.region,
        credential_type=body.credential_type,
        credentials=json.dumps(body.credentials),
        status=conn_status,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return ConnectionOut(
        id=str(conn.id), name=conn.name, region=conn.region,
        credential_type=conn.credential_type, status=conn.status,
        created_at=str(conn.created_at),
    )


@router.get("/aws/connections", response_model=list[ConnectionOut])
async def list_connections(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AWSConnection).where(AWSConnection.tenant_id == tenant.id)
    )
    rows = result.scalars().all()
    return [
        ConnectionOut(
            id=str(c.id), name=c.name, region=c.region,
            credential_type=c.credential_type, status=c.status,
            created_at=str(c.created_at),
        )
        for c in rows
    ]


@router.delete("/aws/connections/{conn_id}", status_code=204)
async def delete_connection(
    conn_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AWSConnection).where(
            AWSConnection.id == uuid.UUID(conn_id),
            AWSConnection.tenant_id == tenant.id,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)
    await db.commit()


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
@router.post("/migrations", response_model=MigrationOut, status_code=201)
async def create_migration(
    body: MigrationCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    mig = Migration(
        tenant_id=tenant.id,
        name=body.name,
        aws_connection_id=uuid.UUID(body.aws_connection_id) if body.aws_connection_id else None,
    )
    db.add(mig)
    await db.commit()
    await db.refresh(mig)
    return MigrationOut(
        id=str(mig.id), name=mig.name,
        aws_connection_id=_to_str(mig.aws_connection_id),
        status=mig.status, created_at=str(mig.created_at),
    )


@router.get("/migrations", response_model=list[MigrationOut])
async def list_migrations(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Migration).where(Migration.tenant_id == tenant.id)
    )
    rows = result.scalars().all()
    out = []
    for m in rows:
        count_result = await db.execute(
            select(func.count()).where(Resource.migration_id == m.id)
        )
        resource_count = count_result.scalar()
        out.append(MigrationOut(
            id=str(m.id), name=m.name,
            aws_connection_id=_to_str(m.aws_connection_id),
            status=m.status, created_at=str(m.created_at),
            resource_count=resource_count,
        ))
    return out


@router.get("/migrations/{mig_id}", response_model=MigrationOut)
async def get_migration(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")
    return MigrationOut(
        id=str(mig.id), name=mig.name,
        aws_connection_id=_to_str(mig.aws_connection_id),
        status=mig.status, created_at=str(mig.created_at),
    )


@router.delete("/migrations/{mig_id}", status_code=204)
async def delete_migration(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete a migration and all associated data.

    Cascade order (respecting FK constraints, no DB-level cascade):
    1. WorkloadResource → 2. Workload → 3. PlanPhase → 4. MigrationPlan
    5. TranslationJobInteraction + Artifact → 6. TranslationJob
    7. Nullify Resource.migration_id (resources go back to global pool)
    8. Migration
    """
    mid = uuid.UUID(mig_id)
    result = await db.execute(
        select(Migration).where(Migration.id == mid, Migration.tenant_id == tenant.id)
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    # 1–4: Delete plan tree (WorkloadResource → Workload → PlanPhase → MigrationPlan)
    plan_result = await db.execute(
        select(MigrationPlan).where(MigrationPlan.migration_id == mid)
    )
    plan = plan_result.scalar_one_or_none()
    if plan:
        phase_result = await db.execute(
            select(PlanPhase.id).where(PlanPhase.plan_id == plan.id)
        )
        phase_ids = [r[0] for r in phase_result.all()]
        if phase_ids:
            workload_result = await db.execute(
                select(Workload.id).where(Workload.phase_id.in_(phase_ids))
            )
            workload_ids = [r[0] for r in workload_result.all()]
            if workload_ids:
                await db.execute(
                    delete(WorkloadResource).where(WorkloadResource.workload_id.in_(workload_ids))
                )
                await db.execute(
                    delete(Workload).where(Workload.id.in_(workload_ids))
                )
            await db.execute(delete(PlanPhase).where(PlanPhase.plan_id == plan.id))
        await db.execute(delete(MigrationPlan).where(MigrationPlan.id == plan.id))

    # 5–6: Delete translation jobs linked to this migration
    sr_result = await db.execute(
        select(TranslationJob.id).where(TranslationJob.migration_id == mid)
    )
    sr_ids = [r[0] for r in sr_result.all()]
    if sr_ids:
        await db.execute(
            delete(TranslationJobInteraction).where(TranslationJobInteraction.translation_job_id.in_(sr_ids))
        )
        await db.execute(
            delete(Artifact).where(Artifact.translation_job_id.in_(sr_ids))
        )
        await db.execute(delete(TranslationJob).where(TranslationJob.id.in_(sr_ids)))

    # 7: Nullify Resource.migration_id (return resources to global pool)
    res_result = await db.execute(
        select(Resource).where(Resource.migration_id == mid)
    )
    for res in res_result.scalars().all():
        res.migration_id = None

    # 8: Delete migration
    await db.delete(mig)
    await db.commit()


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------
async def _get_migration_and_conn(mig_id: str, tenant: Tenant, db: AsyncSession):
    """Fetch migration and its AWS connection. Raises HTTPException on failure."""
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")
    if not mig.aws_connection_id:
        raise HTTPException(status_code=400, detail="Migration has no linked AWS connection")

    conn_result = await db.execute(
        select(AWSConnection).where(AWSConnection.id == mig.aws_connection_id)
    )
    conn = conn_result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="AWS connection not found")

    return mig, conn


async def _build_existing_arns(tenant: Tenant, db: AsyncSession) -> set[str]:
    existing_result = await db.execute(
        select(Resource.aws_arn).where(
            Resource.tenant_id == tenant.id,
            Resource.aws_arn.isnot(None),
        )
    )
    return {row[0] for row in existing_result.all()}


# ---------------------------------------------------------------------------
# Extraction endpoints
# ---------------------------------------------------------------------------
@router.post("/migrations/{mig_id}/extract")
async def extract_resources(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Full region-wide extraction: EC2, VPCs, subnets, SGs, RDS, ELBs, ASGs,
    Lambda, CFN stacks, and IAM policies."""
    mig, conn = await _get_migration_and_conn(mig_id, tenant, db)
    creds = json.loads(conn.credentials)
    region = conn.region

    extracted_count = 0
    extracted_resources: list = []
    existing_arns = await _build_existing_arns(tenant, db)

    def _add_if_new(resource: Resource) -> bool:
        if resource.aws_arn and resource.aws_arn in existing_arns:
            return False
        if resource.aws_arn:
            existing_arns.add(resource.aws_arn)
        db.add(resource)
        extracted_resources.append(resource)
        return True

    # CFN stacks and IAM policies (global)
    try:
        stacks = extract_cfn_stacks(creds, region)
        for stack in stacks:
            resource = Resource(
                tenant_id=tenant.id, migration_id=None, aws_connection_id=conn.id,
                aws_type="AWS::CloudFormation::Stack", aws_arn=stack["stack_id"],
                name=stack["stack_name"],
                raw_config={"template": stack["template"], "status": stack["status"]},
                status="discovered",
            )
            if _add_if_new(resource):
                extracted_count += 1
    except Exception as e:
        print(f"CFN extraction error: {e}")

    try:
        policies = extract_iam_policies(creds, region)
        for pol in policies:
            resource = Resource(
                tenant_id=tenant.id, migration_id=None, aws_connection_id=conn.id,
                aws_type="AWS::IAM::Policy", aws_arn=pol["policy_arn"],
                name=pol["policy_name"], raw_config=pol["policy_document"],
                status="discovered",
            )
            if _add_if_new(resource):
                extracted_count += 1
    except Exception as e:
        print(f"IAM extraction error: {e}")

    extracted_count += await _extract_all_resources(
        creds=creds, region=region, tenant=tenant, mig=mig, conn=conn,
        db=db, collected=extracted_resources, existing_arns=existing_arns,
    )

    await db.commit()
    return {
        "extracted": extracted_count,
        "migration_id": str(mig.id),
        "resource_ids": [str(r.id) for r in extracted_resources],
    }


@router.post("/migrations/{mig_id}/extract/instance")
async def extract_instance_resources(
    mig_id: str,
    resource_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Instance-scoped extraction: discover resources connected to a specific
    EC2 instance (VPC, the instance's subnet only, security groups, RDS, ELBs,
    ASGs, Lambda, and IAM policies via instance profile).

    *resource_id* is the DB UUID of the EC2 instance Resource row.
    Returns *resource_ids* — IDs of ALL found resources (new and pre-existing).
    """
    mig, conn = await _get_migration_and_conn(mig_id, tenant, db)
    creds = json.loads(conn.credentials)
    region = conn.region

    # Resolve DB resource UUID → AWS instance ID
    aws_instance_id = resource_id
    try:
        res_result = await db.execute(
            select(Resource).where(
                Resource.id == uuid.UUID(resource_id),
                Resource.tenant_id == tenant.id,
            )
        )
        res_row = res_result.scalar_one_or_none()
        if res_row and res_row.raw_config and res_row.raw_config.get("instance_id"):
            aws_instance_id = res_row.raw_config["instance_id"]
    except (ValueError, TypeError):
        pass

    existing_arns = await _build_existing_arns(tenant, db)
    extracted_resources: list = []
    found_arns: set[str] = set()

    extracted_count = await _extract_instance_resources(
        instance_id=aws_instance_id,
        creds=creds,
        region=region,
        tenant=tenant,
        mig=mig,
        conn=conn,
        db=db,
        collected=extracted_resources,
        existing_arns=existing_arns,
        found_arns=found_arns,
    )
    await db.commit()

    # Return IDs of ALL found resources (new + pre-existing)
    all_found: list[Resource] = []
    if found_arns:
        all_found_result = await db.execute(
            select(Resource).where(
                Resource.tenant_id == tenant.id,
                Resource.aws_arn.in_(found_arns),
            )
        )
        all_found = list(all_found_result.scalars().all())
    else:
        all_found = extracted_resources

    return {
        "extracted": extracted_count,
        "migration_id": str(mig.id),
        "resource_ids": [str(r.id) for r in all_found],
    }


async def _extract_instance_resources(
    *,
    instance_id: str,
    creds: dict,
    region: str,
    tenant: Tenant,
    mig: Migration,
    conn: AWSConnection,
    db: AsyncSession,
    collected: list,
    existing_arns: set,
    found_arns: set,
) -> int:
    """Discover and persist resources connected to a specific EC2 instance.

    Returns the number of new resources persisted (duplicates skipped).
    found_arns is populated with every ARN encountered (new and pre-existing).
    """
    count = 0

    def _add(resource: Resource) -> bool:
        if resource.aws_arn:
            found_arns.add(resource.aws_arn)
        if resource.aws_arn and resource.aws_arn in existing_arns:
            return False
        if resource.aws_arn:
            existing_arns.add(resource.aws_arn)
        db.add(resource)
        collected.append(resource)
        return True


    # 1. EC2 instance itself
    vpc_id: str | None = None
    instance_subnet_id: str | None = None
    sg_ids: list[str] = []
    profile_arn: str = ""
    try:
        instances = extract_ec2_instances(creds, region, instance_id=instance_id)
        for inst in instances:
            vpc_id = inst.get("vpc_id") or vpc_id
            instance_subnet_id = inst.get("subnet_id") or instance_subnet_id
            sg_ids.extend(inst.get("security_groups", []))
            profile_arn = inst.get("iam_instance_profile_arn", "") or profile_arn
            resource = Resource(
                tenant_id=tenant.id,
                migration_id=None,
                aws_connection_id=conn.id,
                aws_type="AWS::EC2::Instance",
                aws_arn=inst.get("arn", ""),
                name=inst.get("name") or inst["instance_id"],
                raw_config=inst,
                status="discovered",
            )
            if _add(resource):
                count += 1
    except Exception as e:
        print(f"EC2 instance extraction error: {e}")

    # 2. VPC (metadata only) + the instance's specific subnet
    if vpc_id:
        try:
            vpcs = extract_vpcs(creds, region, vpc_id=vpc_id)
            for vpc in vpcs:
                # Store VPC without the full subnet list (we extract the right subnet separately)
                vpc_data = {k: v for k, v in vpc.items() if k != "subnets"}
                resource = Resource(
                    tenant_id=tenant.id,
                    migration_id=None,
                    aws_connection_id=conn.id,
                    aws_type="AWS::EC2::VPC",
                    aws_arn=vpc.get("arn", ""),
                    name=vpc.get("name") or vpc["vpc_id"],
                    raw_config=vpc_data,
                    status="discovered",
                )
                if _add(resource):
                    count += 1
        except Exception as e:
            print(f"VPC extraction error: {e}")

        # Only extract the instance's specific subnet (not all VPC subnets)
        if instance_subnet_id:
            try:
                subnet = extract_subnet_by_id(creds, region, instance_subnet_id)
                if subnet:
                    sub_resource = Resource(
                        tenant_id=tenant.id,
                        migration_id=None,
                        aws_connection_id=conn.id,
                        aws_type="AWS::EC2::Subnet",
                        aws_arn=f"arn:aws:ec2:{region}::subnet/{subnet['subnet_id']}",
                        name=subnet["subnet_id"],
                        raw_config=subnet,
                        status="discovered",
                    )
                    if _add(sub_resource):
                        count += 1
            except Exception as e:
                print(f"Subnet extraction error: {e}")

    # 3. Security groups
    if sg_ids:
        try:
            sgs = extract_security_groups(creds, region, group_ids=sg_ids)
            for sg in sgs:
                resource = Resource(
                    tenant_id=tenant.id,
                    migration_id=None,
                    aws_connection_id=conn.id,
                    aws_type="AWS::EC2::SecurityGroup",
                    aws_arn=sg.get("arn", ""),
                    name=sg.get("group_name") or sg["group_id"],
                    raw_config=sg,
                    status="discovered",
                )
                if _add(resource):
                    count += 1
        except Exception as e:
            print(f"Security group extraction error: {e}")

    # 4. RDS instances in the same VPC
    if vpc_id:
        try:
            rds_instances = extract_rds_instances(creds, region, vpc_id=vpc_id)
            for rds_inst in rds_instances:
                resource = Resource(
                    tenant_id=tenant.id,
                    migration_id=None,
                    aws_connection_id=conn.id,
                    aws_type="AWS::RDS::DBInstance",
                    aws_arn=rds_inst.get("arn", ""),
                    name=rds_inst["db_instance_id"],
                    raw_config=rds_inst,
                    status="discovered",
                )
                if _add(resource):
                    count += 1
        except Exception as e:
            print(f"RDS extraction error: {e}")

    # 5. Load balancers in the same VPC
    if vpc_id:
        try:
            lbs = extract_load_balancers(creds, region, vpc_id=vpc_id)
            for lb in lbs:
                resource = Resource(
                    tenant_id=tenant.id,
                    migration_id=None,
                    aws_connection_id=conn.id,
                    aws_type="AWS::ElasticLoadBalancingV2::LoadBalancer",
                    aws_arn=lb.get("arn", ""),
                    name=lb["name"],
                    raw_config=lb,
                    status="discovered",
                )
                if _add(resource):
                    count += 1
        except Exception as e:
            print(f"ELB extraction error: {e}")

    # 6. Auto Scaling groups that contain this instance
    try:
        asgs = extract_auto_scaling_groups(creds, region, instance_id=instance_id)
        for asg in asgs:
            resource = Resource(
                tenant_id=tenant.id,
                migration_id=None,
                aws_connection_id=conn.id,
                aws_type="AWS::AutoScaling::AutoScalingGroup",
                aws_arn=asg.get("arn", ""),
                name=asg["asg_name"],
                raw_config=asg,
                status="discovered",
            )
            if _add(resource):
                count += 1
    except Exception as e:
        print(f"ASG extraction error: {e}")

    # 7. Lambda functions in the same VPC
    if vpc_id:
        try:
            lambdas = extract_lambda_functions(creds, region, vpc_id=vpc_id)
            for fn in lambdas:
                resource = Resource(
                    tenant_id=tenant.id,
                    migration_id=None,
                    aws_connection_id=conn.id,
                    aws_type="AWS::Lambda::Function",
                    aws_arn=fn.get("arn", ""),
                    name=fn["function_name"],
                    raw_config=fn,
                    status="discovered",
                )
                if _add(resource):
                    count += 1
        except Exception as e:
            print(f"Lambda extraction error: {e}")

    # 8. EBS volumes attached to this instance
    try:
        volumes = extract_ebs_volumes(creds, region, instance_id=instance_id)
        for vol in volumes:
            resource = Resource(
                tenant_id=tenant.id,
                migration_id=None,
                aws_connection_id=conn.id,
                aws_type="AWS::EC2::Volume",
                aws_arn=vol.get("arn", ""),
                name=vol.get("name") or vol["volume_id"],
                raw_config=vol,
                status="discovered",
            )
            if _add(resource):
                count += 1
    except Exception as e:
        print(f"EBS volume extraction error: {e}")

    # 9. Network interfaces (ENIs) attached to this instance
    try:
        enis = extract_network_interfaces(creds, region, instance_id=instance_id)
        for eni in enis:
            resource = Resource(
                tenant_id=tenant.id,
                migration_id=None,
                aws_connection_id=conn.id,
                aws_type="AWS::EC2::NetworkInterface",
                aws_arn=eni.get("arn", ""),
                name=eni["interface_id"],
                raw_config=eni,
                status="discovered",
            )
            if _add(resource):
                count += 1
    except Exception as e:
        print(f"ENI extraction error: {e}")

    # 11. IAM policies attached to the instance's role (via instance profile)
    if profile_arn:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            policies = await loop.run_in_executor(
                None, extract_iam_policies_for_instance_profile, creds, profile_arn
            )
            for pol in policies:
                resource = Resource(
                    tenant_id=tenant.id,
                    migration_id=None,
                    aws_connection_id=conn.id,
                    aws_type="AWS::IAM::Policy",
                    aws_arn=pol["policy_arn"],
                    name=pol["policy_name"],
                    raw_config=pol["policy_document"],
                    status="discovered",
                )
                if _add(resource):
                    count += 1
        except Exception as e:
            print(f"IAM instance profile extraction error: {e}")

    return count


async def _extract_all_resources(
    *,
    creds: dict,
    region: str,
    tenant: Tenant,
    mig: Migration,
    conn: AWSConnection,
    db: AsyncSession,
    collected: list,
    existing_arns: set,
) -> int:
    """Region-wide extraction of all supported resource types. Skips duplicates by ARN."""
    count = 0

    def _add(resource: Resource) -> bool:
        if resource.aws_arn and resource.aws_arn in existing_arns:
            return False
        if resource.aws_arn:
            existing_arns.add(resource.aws_arn)
        db.add(resource)
        collected.append(resource)
        return True


    # EC2 instances (all in region)
    try:
        instances = extract_ec2_instances(creds, region)
        for inst in instances:
            resource = Resource(
                tenant_id=tenant.id, migration_id=None, aws_connection_id=conn.id,
                aws_type="AWS::EC2::Instance", aws_arn=inst.get("arn", ""),
                name=inst.get("name") or inst["instance_id"],
                raw_config=inst, status="discovered",
            )
            if _add(resource):
                count += 1
    except Exception as e:
        print(f"EC2 extraction error: {e}")

    # VPCs + subnets (all in region)
    try:
        vpcs = extract_vpcs(creds, region)
        for vpc in vpcs:
            resource = Resource(
                tenant_id=tenant.id, migration_id=None, aws_connection_id=conn.id,
                aws_type="AWS::EC2::VPC", aws_arn=vpc.get("arn", ""),
                name=vpc.get("name") or vpc["vpc_id"],
                raw_config=vpc, status="discovered",
            )
            if _add(resource):
                count += 1
            for subnet in vpc.get("subnets", []):
                resource = Resource(
                    tenant_id=tenant.id, migration_id=None, aws_connection_id=conn.id,
                    aws_type="AWS::EC2::Subnet",
                    aws_arn=f"arn:aws:ec2:{region}::subnet/{subnet['subnet_id']}",
                    name=subnet["subnet_id"], raw_config=subnet, status="discovered",
                )
                if _add(resource):
                    count += 1
    except Exception as e:
        print(f"VPC extraction error: {e}")

    # Security groups (all in region)
    try:
        sgs = extract_security_groups(creds, region)
        for sg in sgs:
            resource = Resource(
                tenant_id=tenant.id, migration_id=None, aws_connection_id=conn.id,
                aws_type="AWS::EC2::SecurityGroup", aws_arn=sg.get("arn", ""),
                name=sg.get("group_name") or sg["group_id"],
                raw_config=sg, status="discovered",
            )
            if _add(resource):
                count += 1
    except Exception as e:
        print(f"Security group extraction error: {e}")

    # RDS instances (all in region)
    try:
        rds_instances = extract_rds_instances(creds, region)
        for rds_inst in rds_instances:
            resource = Resource(
                tenant_id=tenant.id, migration_id=None, aws_connection_id=conn.id,
                aws_type="AWS::RDS::DBInstance", aws_arn=rds_inst.get("arn", ""),
                name=rds_inst["db_instance_id"],
                raw_config=rds_inst, status="discovered",
            )
            if _add(resource):
                count += 1
    except Exception as e:
        print(f"RDS extraction error: {e}")

    # Load balancers (all in region)
    try:
        lbs = extract_load_balancers(creds, region)
        for lb in lbs:
            resource = Resource(
                tenant_id=tenant.id, migration_id=None, aws_connection_id=conn.id,
                aws_type="AWS::ElasticLoadBalancingV2::LoadBalancer", aws_arn=lb.get("arn", ""),
                name=lb["name"], raw_config=lb, status="discovered",
            )
            if _add(resource):
                count += 1
    except Exception as e:
        print(f"ELB extraction error: {e}")

    # Auto Scaling groups (all in region)
    try:
        asgs = extract_auto_scaling_groups(creds, region)
        for asg in asgs:
            resource = Resource(
                tenant_id=tenant.id, migration_id=None, aws_connection_id=conn.id,
                aws_type="AWS::AutoScaling::AutoScalingGroup", aws_arn=asg.get("arn", ""),
                name=asg["asg_name"], raw_config=asg, status="discovered",
            )
            if _add(resource):
                count += 1
    except Exception as e:
        print(f"ASG extraction error: {e}")

    # Lambda functions (all in region)
    try:
        lambdas = extract_lambda_functions(creds, region)
        for fn in lambdas:
            resource = Resource(
                tenant_id=tenant.id, migration_id=None, aws_connection_id=conn.id,
                aws_type="AWS::Lambda::Function", aws_arn=fn.get("arn", ""),
                name=fn["function_name"], raw_config=fn, status="discovered",
            )
            if _add(resource):
                count += 1
    except Exception as e:
        print(f"Lambda extraction error: {e}")

    return count


# ---------------------------------------------------------------------------
# File upload (CloudTrail, FlowLog)
# ---------------------------------------------------------------------------
@router.post("/migrations/{mig_id}/upload")
async def upload_file(
    mig_id: str,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CloudTrail or FlowLog file as a Resource."""
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    content = await file.read()
    content_str = content.decode("utf-8", errors="replace")

    # Determine type from filename
    filename = file.filename or ""
    if "cloudtrail" in filename.lower() or filename.endswith(".json"):
        aws_type = "CloudTrail"
    elif "flow" in filename.lower() or filename.endswith(".log"):
        aws_type = "FlowLog"
    else:
        aws_type = "Upload"

    # Try to parse as JSON for raw_config
    try:
        raw_config = json.loads(content_str)
    except json.JSONDecodeError:
        raw_config = {"content": content_str[:50000]}  # Store text content, truncated

    resource = Resource(
        tenant_id=tenant.id,
        migration_id=mig.id,
        aws_type=aws_type,
        name=filename,
        raw_config=raw_config,
        status="uploaded",
    )
    db.add(resource)
    await db.commit()
    await db.refresh(resource)

    return {"id": str(resource.id), "name": filename, "aws_type": aws_type}


# ---------------------------------------------------------------------------
# Resources listing
# ---------------------------------------------------------------------------
@router.get("/aws/resources", response_model=list[ResourceOut])
async def list_resources(
    type: Optional[str] = None,
    migration_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List resources with optional filters."""
    query = select(Resource).where(Resource.tenant_id == tenant.id)
    if type:
        query = query.where(Resource.aws_type == type)
    if migration_id:
        query = query.where(Resource.migration_id == uuid.UUID(migration_id))
    if status_filter:
        query = query.where(Resource.status == status_filter)

    result = await db.execute(query)
    rows = result.scalars().all()

    # Batch-load migration names
    migration_ids = {r.migration_id for r in rows if r.migration_id is not None}
    migration_names: dict = {}
    if migration_ids:
        mig_result = await db.execute(
            select(Migration).where(Migration.id.in_(migration_ids))
        )
        for m in mig_result.scalars().all():
            migration_names[m.id] = m.name

    # Batch-load latest translation job per resource.
    # A resource may appear as input_resource_id OR inside config["resource_ids"] for batched runs.
    resource_ids = [r.id for r in rows]
    latest_runs: dict[uuid.UUID, TranslationJob] = {}
    if resource_ids:
        resource_id_set = set(resource_ids)
        # Load all candidate translation jobs: those referencing any of our resources as primary
        # plus (if migration_id is filtered) all runs for the migration
        candidate_query = (
            select(TranslationJob)
            .where(
                TranslationJob.tenant_id == tenant.id,
                TranslationJob.input_resource_id.in_(resource_ids),
            )
            .order_by(TranslationJob.created_at.desc())
        )
        sr_result = await db.execute(candidate_query)
        candidate_runs = list(sr_result.scalars().all())

        # Also load runs for the migration so batched runs (where input_resource_id is only
        # the first resource) are included for all resources in the batch
        if migration_id:
            mig_sr_result = await db.execute(
                select(TranslationJob)
                .where(
                    TranslationJob.tenant_id == tenant.id,
                    TranslationJob.migration_id == uuid.UUID(migration_id),
                )
                .order_by(TranslationJob.created_at.desc())
            )
            for sr in mig_sr_result.scalars().all():
                if sr not in candidate_runs:
                    candidate_runs.append(sr)

        # Sort newest-first and build latest_runs map, expanding config["resource_ids"]
        candidate_runs.sort(key=lambda x: x.created_at, reverse=True)
        for sr in candidate_runs:
            run_resource_ids: list[uuid.UUID] = []
            if sr.input_resource_id:
                run_resource_ids.append(sr.input_resource_id)
            if sr.config and sr.config.get("resource_ids"):
                for rid_str in sr.config["resource_ids"]:
                    try:
                        rid = uuid.UUID(rid_str)
                        if rid not in run_resource_ids:
                            run_resource_ids.append(rid)
                    except (ValueError, TypeError):
                        pass
            for rid in run_resource_ids:
                if rid in resource_id_set and rid not in latest_runs:
                    latest_runs[rid] = sr

    def _latest_run_summary(sr: Optional[TranslationJob]) -> Optional[LatestSkillRunSummary]:
        if sr is None:
            return None
        return LatestSkillRunSummary(
            id=str(sr.id),
            status=sr.status,
            skill_type=sr.skill_type,
            confidence=sr.confidence,
            completed_at=str(sr.completed_at) if sr.completed_at else None,
        )

    return [
        ResourceOut(
            id=str(r.id), migration_id=_to_str(r.migration_id),
            aws_type=r.aws_type, aws_arn=r.aws_arn, name=r.name,
            status=r.status, created_at=str(r.created_at),
            raw_config=r.raw_config,
            migration_name=migration_names.get(r.migration_id) if r.migration_id else None,
            latest_skill_run=_latest_run_summary(latest_runs.get(r.id)),
        )
        for r in rows
    ]


@router.get("/aws/instances", response_model=list[ResourceOut])
async def list_ec2_instances(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return EC2 instance resources for the current tenant."""
    result = await db.execute(
        select(Resource).where(
            Resource.tenant_id == tenant.id,
            Resource.aws_type == "AWS::EC2::Instance",
        )
    )
    rows = result.scalars().all()
    return [
        ResourceOut(
            id=str(r.id), migration_id=_to_str(r.migration_id),
            aws_type=r.aws_type, aws_arn=r.aws_arn, name=r.name,
            status=r.status, created_at=str(r.created_at),
            raw_config=r.raw_config,
        )
        for r in rows
    ]


@router.get("/resources/unassigned", response_model=list[ResourceOut])
async def list_unassigned_resources(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return resources where migration_id IS NULL for the current tenant."""
    result = await db.execute(
        select(Resource).where(
            Resource.tenant_id == tenant.id,
            Resource.migration_id.is_(None),
        )
    )
    rows = result.scalars().all()
    return [
        ResourceOut(
            id=str(r.id), migration_id=None,
            aws_type=r.aws_type, aws_arn=r.aws_arn, name=r.name,
            status=r.status, created_at=str(r.created_at),
            raw_config=r.raw_config,
        )
        for r in rows
    ]


@router.post("/migrations/{mig_id}/resources")
async def assign_resources_to_migration(
    mig_id: str,
    body: AssignResourcesBody,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Assign resources to a migration by setting their migration_id."""
    # Verify migration ownership
    result = await db.execute(
        select(Migration).where(
            Migration.id == uuid.UUID(mig_id),
            Migration.tenant_id == tenant.id,
        )
    )
    mig = result.scalar_one_or_none()
    if not mig:
        raise HTTPException(status_code=404, detail="Migration not found")

    assigned = 0
    for rid_str in body.resource_ids:
        try:
            rid = uuid.UUID(rid_str)
        except ValueError:
            continue
        res_result = await db.execute(
            select(Resource).where(
                Resource.id == rid,
                Resource.tenant_id == tenant.id,
            )
        )
        resource = res_result.scalar_one_or_none()
        if resource:
            resource.migration_id = mig.id
            assigned += 1

    await db.commit()
    return {"assigned": assigned}


@router.delete("/aws/resources/{resource_id}", status_code=204)
async def delete_resource(
    resource_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single resource."""
    try:
        rid = uuid.UUID(resource_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid resource ID")
    result = await db.execute(
        select(Resource).where(
            Resource.id == rid,
            Resource.tenant_id == tenant.id,
        )
    )
    resource = result.scalar_one_or_none()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    # Remove from workload_resources join table
    await db.execute(
        delete(WorkloadResource).where(WorkloadResource.resource_id == rid)
    )
    # Delete linked translation jobs
    await db.execute(
        delete(TranslationJob).where(TranslationJob.input_resource_id == rid)
    )
    await db.delete(resource)
    await db.commit()
