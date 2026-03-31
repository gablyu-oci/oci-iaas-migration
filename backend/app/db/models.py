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
# OCIConnection
# ---------------------------------------------------------------------------
class OCIConnection(Base):
    __tablename__ = "oci_connections"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tenancy_ocid: Mapped[str] = mapped_column(String(255), nullable=False)
    user_ocid: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    private_key: Mapped[str] = mapped_column(Text, nullable=False)  # PEM key content
    compartment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    tenant: Mapped["Tenant"] = relationship()


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
    discovery_status: Mapped[str] = mapped_column(String(32), default="pending")
    discovery_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    discovered_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    plan_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    plan_workload_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    plan_workload_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    plan_started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    plan_max_iterations: Mapped[Optional[int]] = mapped_column(nullable=True)
    # Phase 2: Migrate
    migrate_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    migrate_workload_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    migrate_oci_connection_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("oci_connections.id"), nullable=True
    )
    migrate_started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    migrate_current_step: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    migrate_terraform_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    migrate_terraform_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    migrate_logs: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="migrations")
    resources: Mapped[list["Resource"]] = relationship(back_populates="migration")
    plan: Mapped[Optional["MigrationPlan"]] = relationship(
        back_populates="migration", uselist=False
    )
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="migration")


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
# TranslationJob
# ---------------------------------------------------------------------------
class TranslationJob(Base):
    __tablename__ = "translation_jobs"

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

    interactions: Mapped[list["TranslationJobInteraction"]] = relationship(back_populates="translation_job")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="translation_job")


# ---------------------------------------------------------------------------
# TranslationJobInteraction
# ---------------------------------------------------------------------------
class TranslationJobInteraction(Base):
    __tablename__ = "translation_job_interactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    translation_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("translation_jobs.id"), nullable=False
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

    translation_job: Mapped["TranslationJob"] = relationship(back_populates="interactions")


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------
class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    translation_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("translation_jobs.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    file_type: Mapped[Optional[str]] = mapped_column(String(64))
    file_name: Mapped[Optional[str]] = mapped_column(String(255))
    content_type: Mapped[Optional[str]] = mapped_column(String(128))
    data: Mapped[Optional[bytes]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    translation_job: Mapped["TranslationJob"] = relationship(back_populates="artifacts")


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


# ---------------------------------------------------------------------------
# MigrationPlan
# ---------------------------------------------------------------------------
class MigrationPlan(Base):
    __tablename__ = "migration_plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    migration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("migrations.id"), nullable=False, unique=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="draft")
    generated_at: Mapped[datetime] = mapped_column(default=_utcnow)
    summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    migration: Mapped["Migration"] = relationship(back_populates="plan")
    phases: Mapped[list["PlanPhase"]] = relationship(
        back_populates="plan",
        order_by="PlanPhase.order_index",
    )


# ---------------------------------------------------------------------------
# PlanPhase
# ---------------------------------------------------------------------------
class PlanPhase(Base):
    __tablename__ = "plan_phases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("migration_plans.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")

    plan: Mapped["MigrationPlan"] = relationship(back_populates="phases")
    workloads: Mapped[list["Workload"]] = relationship(back_populates="phase")


# ---------------------------------------------------------------------------
# Workload
# ---------------------------------------------------------------------------
class Workload(Base):
    __tablename__ = "workloads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    phase_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plan_phases.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    skill_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    translation_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("translation_jobs.id"), nullable=True
    )
    app_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("app_groups.id"), nullable=True
    )

    phase: Mapped["PlanPhase"] = relationship(back_populates="workloads")
    resources: Mapped[list["WorkloadResource"]] = relationship(back_populates="workload")


# ---------------------------------------------------------------------------
# WorkloadResource
# ---------------------------------------------------------------------------
class WorkloadResource(Base):
    __tablename__ = "workload_resources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    workload_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workloads.id"), nullable=False
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resources.id"), nullable=False
    )

    __table_args__ = (UniqueConstraint("workload_id", "resource_id"),)

    workload: Mapped["Workload"] = relationship(back_populates="resources")


# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------
class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    migration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("migrations.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    current_step: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    dependency_artifacts: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=None)

    migration: Mapped["Migration"] = relationship(back_populates="assessments")
    resource_assessments: Mapped[list["ResourceAssessment"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    app_groups: Mapped[list["AppGroup"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )
    tco_report: Mapped[Optional["TCOReport"]] = relationship(
        back_populates="assessment", uselist=False, cascade="all, delete-orphan"
    )
    dependency_edges: Mapped[list["DependencyEdge"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# ResourceAssessment
# ---------------------------------------------------------------------------
class ResourceAssessment(Base):
    __tablename__ = "resource_assessments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id"), nullable=False
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resources.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )

    # Rightsizing
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    current_instance_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    current_monthly_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_oci_shape: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    recommended_oci_ocpus: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    recommended_oci_memory_gb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    projected_oci_monthly_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rightsizing_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rightsizing_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # OS Compatibility
    os_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    os_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    os_compat_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    os_compat_details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Software Inventory
    software_inventory: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ssm_available: Mapped[Optional[bool]] = mapped_column(nullable=True)

    # 6R Classification
    sixr_strategy: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sixr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sixr_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Readiness Score
    readiness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    readiness_factors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    assessment: Mapped["Assessment"] = relationship(back_populates="resource_assessments")

    __table_args__ = (UniqueConstraint("assessment_id", "resource_id"),)


# ---------------------------------------------------------------------------
# AppGroup
# ---------------------------------------------------------------------------
class AppGroup(Base):
    __tablename__ = "app_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    grouping_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    workload_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sixr_strategy: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    readiness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_aws_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_oci_cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    assessment: Mapped["Assessment"] = relationship(back_populates="app_groups")
    members: Mapped[list["AppGroupMember"]] = relationship(
        back_populates="app_group", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# AppGroupMember
# ---------------------------------------------------------------------------
class AppGroupMember(Base):
    __tablename__ = "app_group_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    app_group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_groups.id"), nullable=False
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("resources.id"), nullable=False
    )

    __table_args__ = (UniqueConstraint("app_group_id", "resource_id"),)

    app_group: Mapped["AppGroup"] = relationship(back_populates="members")


# ---------------------------------------------------------------------------
# TCOReport
# ---------------------------------------------------------------------------
class TCOReport(Base):
    __tablename__ = "tco_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id"), nullable=False, unique=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    aws_monthly_total_usd: Mapped[float] = mapped_column(Float, default=0.0)
    oci_monthly_total_usd: Mapped[float] = mapped_column(Float, default=0.0)
    annual_savings_usd: Mapped[float] = mapped_column(Float, default=0.0)
    savings_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    breakdown: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    three_year_tco: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    assessment: Mapped["Assessment"] = relationship(back_populates="tco_report")


# ---------------------------------------------------------------------------
# DependencyEdge
# ---------------------------------------------------------------------------
class DependencyEdge(Base):
    __tablename__ = "dependency_edges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_new_uuid)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessments.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id"), nullable=False
    )
    source_resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("resources.id"), nullable=True
    )
    target_resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("resources.id"), nullable=True
    )
    source_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    protocol: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    edge_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    byte_count: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    packet_count: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    assessment: Mapped["Assessment"] = relationship(back_populates="dependency_edges")
