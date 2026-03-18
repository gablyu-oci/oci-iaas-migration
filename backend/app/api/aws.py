"""AWS connection, migration, and resource extraction endpoints."""

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import AWSConnection, Migration, Resource, Tenant
from app.api.deps import get_current_tenant
from app.services.aws_extractor import (
    validate_credentials,
    extract_cfn_stacks,
    extract_iam_policies,
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

    model_config = {"from_attributes": True}


class ResourceOut(BaseModel):
    id: str
    migration_id: Optional[str]
    aws_type: Optional[str]
    aws_arn: Optional[str]
    name: Optional[str]
    status: str
    created_at: str

    model_config = {"from_attributes": True}


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
    return [
        MigrationOut(
            id=str(m.id), name=m.name,
            aws_connection_id=_to_str(m.aws_connection_id),
            status=m.status, created_at=str(m.created_at),
        )
        for m in rows
    ]


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


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
@router.post("/migrations/{mig_id}/extract")
async def extract_resources(
    mig_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Trigger AWS resource extraction for the migration's linked connection."""
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

    creds = json.loads(conn.credentials)
    region = conn.region

    extracted_count = 0

    # Extract CFN stacks
    try:
        stacks = extract_cfn_stacks(creds, region)
        for stack in stacks:
            resource = Resource(
                tenant_id=tenant.id,
                migration_id=mig.id,
                aws_connection_id=conn.id,
                aws_type="AWS::CloudFormation::Stack",
                aws_arn=stack["stack_id"],
                name=stack["stack_name"],
                raw_config={"template": stack["template"], "status": stack["status"]},
                status="discovered",
            )
            db.add(resource)
            extracted_count += 1
    except Exception as e:
        # Log but continue with other extractions
        print(f"CFN extraction error: {e}")

    # Extract IAM policies
    try:
        policies = extract_iam_policies(creds, region)
        for pol in policies:
            resource = Resource(
                tenant_id=tenant.id,
                migration_id=mig.id,
                aws_connection_id=conn.id,
                aws_type="AWS::IAM::Policy",
                aws_arn=pol["policy_arn"],
                name=pol["policy_name"],
                raw_config=pol["policy_document"],
                status="discovered",
            )
            db.add(resource)
            extracted_count += 1
    except Exception as e:
        print(f"IAM extraction error: {e}")

    await db.commit()

    return {"extracted": extracted_count, "migration_id": str(mig.id)}


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
    return [
        ResourceOut(
            id=str(r.id), migration_id=_to_str(r.migration_id),
            aws_type=r.aws_type, aws_arn=r.aws_arn, name=r.name,
            status=r.status, created_at=str(r.created_at),
        )
        for r in rows
    ]
