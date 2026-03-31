"""OCI Connection management API."""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant, get_db
from app.db.models import OCIConnection, Tenant

router = APIRouter(prefix="/api", tags=["oci"])


class OCIConnectionCreate(BaseModel):
    name: str
    tenancy_ocid: str
    user_ocid: str
    region: str
    fingerprint: str
    private_key: str
    compartment_id: Optional[str] = None


class OCIConnectionOut(BaseModel):
    id: str
    name: str
    tenancy_ocid: str
    user_ocid: str
    region: str
    fingerprint: str
    compartment_id: Optional[str] = None
    status: str
    created_at: str

    model_config = {"from_attributes": True}


@router.post("/oci-connections", response_model=OCIConnectionOut, status_code=201)
async def create_oci_connection(
    body: OCIConnectionCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Create a new OCI connection."""
    conn = OCIConnection(
        tenant_id=tenant.id,
        name=body.name,
        tenancy_ocid=body.tenancy_ocid,
        user_ocid=body.user_ocid,
        region=body.region,
        fingerprint=body.fingerprint,
        private_key=body.private_key,
        compartment_id=body.compartment_id,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _to_out(conn)


@router.get("/oci-connections", response_model=list[OCIConnectionOut])
async def list_oci_connections(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all OCI connections for the tenant."""
    result = await db.execute(
        select(OCIConnection).where(OCIConnection.tenant_id == tenant.id)
    )
    return [_to_out(c) for c in result.scalars().all()]


@router.post("/oci-connections/{conn_id}/test")
async def test_oci_connection(
    conn_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Test an OCI connection by calling the Identity API."""
    result = await db.execute(
        select(OCIConnection).where(
            OCIConnection.id == uuid.UUID(conn_id),
            OCIConnection.tenant_id == tenant.id,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Test by running terraform with a minimal config
    import subprocess
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write a minimal provider config
        tf_content = f'''
terraform {{
  required_providers {{
    oci = {{
      source = "oracle/oci"
    }}
  }}
}}

provider "oci" {{
  tenancy_ocid = "{conn.tenancy_ocid}"
  user_ocid    = "{conn.user_ocid}"
  fingerprint  = "{conn.fingerprint}"
  private_key  = <<-EOT
{conn.private_key}
EOT
  region       = "{conn.region}"
}}

data "oci_identity_tenancy" "test" {{
  tenancy_id = "{conn.tenancy_ocid}"
}}
'''
        tf_path = os.path.join(tmpdir, "main.tf")
        with open(tf_path, "w") as f:
            f.write(tf_content)

        # terraform init
        init_result = subprocess.run(
            ["terraform", "init", "-no-color"],
            cwd=tmpdir, capture_output=True, text=True, timeout=120,
        )
        if init_result.returncode != 0:
            return {"valid": False, "error": f"terraform init failed: {init_result.stderr[:500]}"}

        # terraform plan (validates credentials)
        plan_result = subprocess.run(
            ["terraform", "plan", "-no-color"],
            cwd=tmpdir, capture_output=True, text=True, timeout=120,
        )
        if plan_result.returncode != 0:
            conn.status = "invalid"
            await db.commit()
            return {"valid": False, "error": f"Credential validation failed: {plan_result.stderr[:500]}"}

    conn.status = "active"
    await db.commit()
    return {"valid": True, "region": conn.region, "tenancy": conn.tenancy_ocid}


@router.delete("/oci-connections/{conn_id}", status_code=204)
async def delete_oci_connection(
    conn_id: str,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Delete an OCI connection."""
    result = await db.execute(
        select(OCIConnection).where(
            OCIConnection.id == uuid.UUID(conn_id),
            OCIConnection.tenant_id == tenant.id,
        )
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)
    await db.commit()


def _to_out(conn: OCIConnection) -> OCIConnectionOut:
    return OCIConnectionOut(
        id=str(conn.id),
        name=conn.name,
        tenancy_ocid=conn.tenancy_ocid,
        user_ocid=conn.user_ocid,
        region=conn.region,
        fingerprint=conn.fingerprint,
        compartment_id=conn.compartment_id,
        status=conn.status,
        created_at=str(conn.created_at),
    )
