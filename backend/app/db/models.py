"""SQLAlchemy 2.0 async ORM models for the OCI Migration Tool."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    ForeignKey,
    Integer,
    Float,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------
class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    aws_connections: Mapped[list["AWSConnection"]] = relationship(back_populates="tenant")
    migrations: Mapped[list["Migration"]] = relationship(back_populates="tenant")


# ---------------------------------------------------------------------------
# AWSConnection
# ---------------------------------------------------------------------------
class AWSConnection(Base):
    __tablename__ = "aws_connections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_type: Mapped[str] = mapped_column(String(64), nullable=False)
    credentials: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    tenant: Mapped["Tenant"] = relationship(back_populates="aws_connections")


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------
class Migration(Base):
    __tablename__ = "migrations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    aws_connection_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("aws_connections.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    tenant: Mapped["Tenant"] = relationship(back_populates="migrations")
    resources: Mapped[list["Resource"]] = relationship(back_populates="migration")


# ---------------------------------------------------------------------------
# Resource
# ---------------------------------------------------------------------------
class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    migration_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("migrations.id"), nullable=True
    )
    aws_connection_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("aws_connections.id"), nullable=True
    )
    aws_type: Mapped[Optional[str]] = mapped_column(String(128))
    aws_arn: Mapped[Optional[str]] = mapped_column(String(512))
    name: Mapped[Optional[str]] = mapped_column(String(255))
    raw_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="discovered")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    migration: Mapped[Optional["Migration"]] = relationship(back_populates="resources")


# ---------------------------------------------------------------------------
# SkillRun
# ---------------------------------------------------------------------------
class SkillRun(Base):
    __tablename__ = "skill_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    migration_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("migrations.id"), nullable=True
    )
    skill_type: Mapped[str] = mapped_column(String(64), nullable=False)
    input_resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("resources.id"), nullable=True
    )
    input_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    current_phase: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    current_iteration: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    errors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    interactions: Mapped[list["SkillRunInteraction"]] = relationship(back_populates="skill_run")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="skill_run")


# ---------------------------------------------------------------------------
# SkillRunInteraction
# ---------------------------------------------------------------------------
class SkillRunInteraction(Base):
    __tablename__ = "skill_run_interactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    skill_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skill_runs.id"), nullable=False
    )
    agent_type: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(128))
    iteration: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_input: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_cache_read: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_cache_write: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float)
    decision: Mapped[Optional[str]] = mapped_column(String(64))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    issues: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    skill_run: Mapped["SkillRun"] = relationship(back_populates="interactions")


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------
class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    skill_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("skill_runs.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(64))
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    content_type: Mapped[Optional[str]] = mapped_column(String(128))
    data: Mapped[Optional[bytes]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    skill_run: Mapped["SkillRun"] = relationship(back_populates="artifacts")


# ---------------------------------------------------------------------------
# ServiceMapping (RAG reference data)
# ---------------------------------------------------------------------------
class ServiceMapping(Base):
    __tablename__ = "service_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    aws_service: Mapped[Optional[str]] = mapped_column(String(128))
    aws_resource_type: Mapped[Optional[str]] = mapped_column(String(255))
    oci_service: Mapped[Optional[str]] = mapped_column(String(128))
    oci_resource_type: Mapped[Optional[str]] = mapped_column(String(255))
    terraform_resource: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)


# ---------------------------------------------------------------------------
# IAMMapping (RAG reference data)
# ---------------------------------------------------------------------------
class IAMMapping(Base):
    __tablename__ = "iam_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    aws_action: Mapped[Optional[str]] = mapped_column(String(255))
    aws_service: Mapped[Optional[str]] = mapped_column(String(128))
    oci_permission: Mapped[Optional[str]] = mapped_column(String(255))
    oci_service: Mapped[Optional[str]] = mapped_column(String(128))
    notes: Mapped[Optional[str]] = mapped_column(Text)
