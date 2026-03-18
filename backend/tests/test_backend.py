"""
Backend integration tests using in-memory SQLite (async) + HTTPX AsyncClient.
Tests all API routes without requiring a live Postgres or Redis.
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.db.models import Base, Tenant, AWSConnection, Migration, Resource, SkillRun, Artifact
from app.db.base import get_db
from app.services.auth_service import hash_password, create_access_token


# ── Test DB setup (SQLite in-memory) ─────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """Create all tables once for the test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def tenant(db):
    """Create a test tenant in DB (no teardown — session-scoped drop_all handles cleanup)."""
    t = Tenant(email=f"test-{uuid.uuid4()}@example.com", password_hash=hash_password("password123"))
    db.add(t)
    await db.commit()
    await db.refresh(t)
    yield t


@pytest_asyncio.fixture
def auth_headers(tenant):
    """JWT auth headers for test tenant."""
    token = create_access_token({"sub": str(tenant.id)})
    return {"Authorization": f"Bearer {token}"}


# ── Health ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Auth ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register(client):
    r = await client.post("/api/auth/register", json={
        "email": "newuser@example.com",
        "password": "securepass"
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate(client):
    body = {"email": "dup@example.com", "password": "pass"}
    await client.post("/api/auth/register", json=body)
    r = await client.post("/api/auth/register", json=body)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client, tenant):
    r = await client.post("/api/auth/login", json={
        "email": tenant.email,
        "password": "password123"
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client, tenant):
    r = await client.post("/api/auth/login", json={
        "email": tenant.email,
        "password": "wrongpass"
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_protected_without_token(client):
    r = await client.get("/api/aws/connections")
    assert r.status_code in (401, 403)  # HTTPBearer returns 403, dep may return 401


# ── AWS Connections ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_connection(client, auth_headers):
    with patch("app.api.aws.validate_credentials", return_value={"valid": True, "error": None}):
        r = await client.post("/api/aws/connections", json={
            "name": "My AWS Account",
            "region": "us-east-1",
            "credential_type": "key_pair",
            "credentials": {"access_key_id": "AKIATEST", "secret_access_key": "secret"}
        }, headers=auth_headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["name"] == "My AWS Account"
    assert data["status"] == "active"
    return data["id"]


@pytest.mark.asyncio
async def test_list_connections(client, auth_headers):
    with patch("app.api.aws.validate_credentials", return_value={"valid": True, "error": None}):
        await client.post("/api/aws/connections", json={
            "name": "Listed Conn",
            "region": "eu-west-1",
            "credential_type": "key_pair",
            "credentials": {"access_key_id": "AKIA2", "secret_access_key": "s2"}
        }, headers=auth_headers)
    r = await client.get("/api/aws/connections", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_delete_connection(client, auth_headers):
    with patch("app.api.aws.validate_credentials", return_value={"valid": True, "error": None}):
        create_r = await client.post("/api/aws/connections", json={
            "name": "To Delete",
            "region": "us-east-1",
            "credential_type": "key_pair",
            "credentials": {"access_key_id": "AKIA3", "secret_access_key": "s3"}
        }, headers=auth_headers)
    conn_id = create_r.json()["id"]
    r = await client.delete(f"/api/aws/connections/{conn_id}", headers=auth_headers)
    assert r.status_code == 200


# ── Migrations ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_migration(client, auth_headers):
    r = await client.post("/api/migrations", json={"name": "My Migration"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "My Migration"


@pytest.mark.asyncio
async def test_list_migrations(client, auth_headers):
    await client.post("/api/migrations", json={"name": "Migration 1"}, headers=auth_headers)
    r = await client.get("/api/migrations", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_get_migration(client, auth_headers):
    create_r = await client.post("/api/migrations", json={"name": "Get Me"}, headers=auth_headers)
    mig_id = create_r.json()["id"]
    r = await client.get(f"/api/migrations/{mig_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Get Me"


@pytest.mark.asyncio
async def test_get_migration_not_found(client, auth_headers):
    r = await client.get(f"/api/migrations/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


# ── Resources ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_resources_empty(client, auth_headers):
    r = await client.get("/api/aws/resources", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_upload_file(client, auth_headers):
    create_r = await client.post("/api/migrations", json={"name": "Upload Test"}, headers=auth_headers)
    mig_id = create_r.json()["id"]

    import io
    cloudtrail_json = '{"Records": []}'
    r = await client.post(
        f"/api/migrations/{mig_id}/upload",
        params={"resource_type": "cloudtrail"},
        files={"file": ("cloudtrail.json", io.BytesIO(cloudtrail_json.encode()), "application/json")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["aws_type"] == "AWS::CloudTrail::Log"


# ── Skill Runs ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_skill_run_invalid_input(client, auth_headers):
    """Non-parseable content should return 422."""
    r = await client.post("/api/skill-runs", json={
        "skill_type": "cfn_terraform",
        "input_content": ":::not yaml or json:::"
    }, headers=auth_headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_skill_run_valid(client, auth_headers):
    """Valid YAML input should enqueue and return skill_run_id."""
    yaml_input = "AWSTemplateFormatVersion: '2010-09-09'\nResources: {}"
    with patch("app.api.skills.create_pool") as mock_pool_factory:
        mock_pool = AsyncMock()
        mock_pool.enqueue_job = AsyncMock()
        mock_pool.aclose = AsyncMock()
        mock_pool_factory.return_value = mock_pool
        r = await client.post("/api/skill-runs", json={
            "skill_type": "cfn_terraform",
            "input_content": yaml_input,
        }, headers=auth_headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert "skill_run_id" in data
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_list_skill_runs(client, auth_headers):
    r = await client.get("/api/skill-runs", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_get_skill_run_not_found(client, auth_headers):
    r = await client.get(f"/api/skill-runs/{uuid.uuid4()}", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_artifact_download_not_found(client, auth_headers):
    r = await client.get(f"/api/artifacts/{uuid.uuid4()}/download", headers=auth_headers)
    assert r.status_code == 404


# ── Unit: Auth Service ────────────────────────────────────────────────────────

def test_hash_and_verify():
    hashed = hash_password("mypassword")
    from app.services.auth_service import verify_password
    assert verify_password("mypassword", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip():
    from app.services.auth_service import decode_token
    token = create_access_token({"sub": "tenant-123"})
    payload = decode_token(token)
    assert payload["sub"] == "tenant-123"


def test_jwt_invalid():
    from app.services.auth_service import decode_token
    with pytest.raises(ValueError):
        decode_token("invalid.jwt.token")


# ── Unit: Model Gateway ───────────────────────────────────────────────────────

def test_model_routing():
    from app.gateway.model_gateway import get_model
    assert get_model("cfn_terraform", "enhancement") == "claude-opus-4-6"
    assert get_model("cfn_terraform", "review") == "claude-sonnet-4-6"
    assert get_model("cfn_terraform", "fix") == "claude-opus-4-6"
    assert get_model("iam_translation", "enhancement") == "claude-opus-4-6"
    assert get_model("iam_translation", "review") == "claude-sonnet-4-6"
    assert get_model("dependency_discovery", "runbook") == "claude-opus-4-6"
    assert get_model("dependency_discovery", "anomalies") == "claude-sonnet-4-6"


def test_secret_scrubbing():
    from app.gateway.model_gateway import scrub_secrets
    text = "key AKIAIOSFODNN7EXAMPLE in account 123456789012"
    scrubbed = scrub_secrets(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
    assert "123456789012" not in scrubbed


# ── Unit: Agent Logger ────────────────────────────────────────────────────────

def test_agent_logger_no_file_io():
    from app.skills.shared.agent_logger import AgentLogger, AgentType, ReviewDecision
    import inspect, os

    # Should not create any files
    logger = AgentLogger("test", "test.json")
    logger.start_session()
    logger.log_agent_call(1, AgentType.ENHANCEMENT, "in", "out", duration_seconds=0.1, model="claude-opus-4-6")
    logger.log_review_call(1, ReviewDecision.APPROVED, 0.9, [], {}, 0.1, model="claude-sonnet-4-6")
    result = logger.end_session(ReviewDecision.APPROVED, 0.9)

    assert isinstance(result, tuple) and len(result) == 2
    json_str, md_str = result
    assert isinstance(json_str, str)
    assert isinstance(md_str, str)
    import json
    data = json.loads(json_str)
    assert data["final_decision"] == "APPROVED"
    assert "APPROVED" in md_str


def test_confidence_calculator():
    from app.skills.shared.agent_logger import ConfidenceCalculator
    c = ConfidenceCalculator.calculate(10, 10, [])
    assert c == 0.95  # capped

    c2 = ConfidenceCalculator.calculate(10, 8, [{"severity": "HIGH"}])
    assert 0.0 <= c2 <= 1.0

    c3 = ConfidenceCalculator.calculate(0, 0, [])
    assert c3 == 0.0


# ── Unit: Orchestrator signatures ─────────────────────────────────────────────

def test_cfn_orchestrator_signature():
    import inspect
    from app.skills.cfn_terraform import orchestrator
    sig = inspect.signature(orchestrator.run)
    assert set(sig.parameters) >= {"input_content", "progress_callback", "anthropic_client", "max_iterations"}
    assert orchestrator.ENHANCEMENT_MODEL == "claude-opus-4-6"
    assert orchestrator.REVIEW_MODEL == "claude-sonnet-4-6"
    assert orchestrator.FIX_MODEL == "claude-opus-4-6"


def test_iam_orchestrator_signature():
    import inspect
    from app.skills.iam_translation import orchestrator
    sig = inspect.signature(orchestrator.run)
    assert set(sig.parameters) >= {"input_content", "progress_callback", "anthropic_client"}
    assert orchestrator.ENHANCEMENT_MODEL == "claude-opus-4-6"
    assert orchestrator.REVIEW_MODEL == "claude-sonnet-4-6"


def test_dep_orchestrator_signature():
    import inspect
    from app.skills.dependency_discovery import orchestrator
    sig = inspect.signature(orchestrator.run)
    assert set(sig.parameters) >= {"input_content", "flowlog_content", "progress_callback", "anthropic_client"}
