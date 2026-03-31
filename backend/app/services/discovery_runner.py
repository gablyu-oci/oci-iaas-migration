"""Discovery runner -- executes resource extraction + auto-grouping in a child process.

This module is invoked via multiprocessing.Process from the aws API.
It creates its own synchronous DB engine (not shared with the FastAPI async
engine) following the same isolation pattern as assessment_runner.py.
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.models import AWSConnection, Migration, Resource

logger = logging.getLogger(__name__)


def _sync_database_url() -> str:
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def run_discovery(migration_id: str) -> None:
    """Main entry point -- called in a child process.

    Extracts all AWS resources for the migration's connection and
    assigns them to the migration.
    """
    logging.basicConfig(level=logging.INFO)

    sync_url = _sync_database_url()
    engine = create_engine(sync_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)

    session = SessionLocal()
    try:
        # Load migration
        migration = session.execute(
            select(Migration).where(Migration.id == UUID(migration_id))
        ).scalar_one_or_none()

        if not migration:
            logger.error("Migration %s not found", migration_id)
            return

        if not migration.aws_connection_id:
            logger.error("Migration %s has no AWS connection", migration_id)
            session.execute(
                update(Migration)
                .where(Migration.id == UUID(migration_id))
                .values(
                    discovery_status="failed",
                    discovery_error="No AWS connection linked",
                )
            )
            session.commit()
            return

        # Load AWS connection
        conn = session.execute(
            select(AWSConnection).where(AWSConnection.id == migration.aws_connection_id)
        ).scalar_one_or_none()

        if not conn:
            logger.error("AWSConnection %s not found", str(migration.aws_connection_id))
            session.execute(
                update(Migration)
                .where(Migration.id == UUID(migration_id))
                .values(
                    discovery_status="failed",
                    discovery_error="AWS connection not found",
                )
            )
            session.commit()
            return

        creds = conn.credentials
        if isinstance(creds, str):
            creds = json.loads(creds)
        region = conn.region

        # Mark as discovering
        session.execute(
            update(Migration)
            .where(Migration.id == UUID(migration_id))
            .values(discovery_status="discovering")
        )
        session.commit()

        # Build set of existing ARNs to avoid duplicates
        existing_result = session.execute(
            select(Resource.aws_arn).where(
                Resource.tenant_id == migration.tenant_id,
                Resource.aws_arn.isnot(None),
            )
        )
        existing_arns = {row[0] for row in existing_result.all()}

        extracted_count = 0

        def add_resource(aws_type: str, aws_arn: str | None, name: str | None, raw_config: dict) -> bool:
            nonlocal extracted_count
            if aws_arn and aws_arn in existing_arns:
                return False
            if aws_arn:
                existing_arns.add(aws_arn)
            resource = Resource(
                tenant_id=migration.tenant_id,
                migration_id=migration.id,
                aws_connection_id=conn.id,
                aws_type=aws_type,
                aws_arn=aws_arn,
                name=name,
                raw_config=raw_config,
                status="discovered",
            )
            session.add(resource)
            extracted_count += 1
            return True

        # Import extractors
        from app.services.aws_extractor import (
            extract_cfn_stacks,
            extract_iam_policies,
            extract_ec2_instances,
            extract_vpcs,
            extract_security_groups,
            extract_ebs_volumes,
            extract_network_interfaces,
            extract_rds_instances,
            extract_load_balancers,
            extract_auto_scaling_groups,
            extract_lambda_functions,
        )

        # Extract all resource types
        extractors = [
            ("CFN Stacks", lambda: extract_cfn_stacks(creds, region)),
            ("EC2 Instances", lambda: extract_ec2_instances(creds, region)),
            ("VPCs", lambda: extract_vpcs(creds, region)),
            ("Security Groups", lambda: extract_security_groups(creds, region)),
            ("EBS Volumes", lambda: extract_ebs_volumes(creds, region)),
            ("Network Interfaces", lambda: extract_network_interfaces(creds, region)),
            ("RDS Instances", lambda: extract_rds_instances(creds, region)),
            ("Load Balancers", lambda: extract_load_balancers(creds, region)),
            ("Auto Scaling Groups", lambda: extract_auto_scaling_groups(creds, region)),
            ("Lambda Functions", lambda: extract_lambda_functions(creds, region)),
            ("IAM Policies", lambda: extract_iam_policies(creds, region)),
        ]

        for label, extractor_fn in extractors:
            try:
                items = extractor_fn()
                for item in items:
                    # Normalize item shape -- extractors return varied formats
                    if isinstance(item, dict):
                        aws_type = item.get("aws_type") or item.get("resource_type") or ""
                        aws_arn = item.get("aws_arn") or item.get("arn") or item.get("stack_id") or item.get("policy_arn") or ""
                        name = item.get("name") or item.get("stack_name") or item.get("policy_name") or ""
                        raw_config = item.get("raw_config") or item.get("template") or item.get("policy_document") or item

                        # Infer aws_type from label if not set
                        if not aws_type:
                            type_map = {
                                "CFN Stacks": "AWS::CloudFormation::Stack",
                                "EC2 Instances": "AWS::EC2::Instance",
                                "VPCs": "AWS::EC2::VPC",
                                "Security Groups": "AWS::EC2::SecurityGroup",
                                "EBS Volumes": "AWS::EC2::Volume",
                                "Network Interfaces": "AWS::EC2::NetworkInterface",
                                "RDS Instances": "AWS::RDS::DBInstance",
                                "Load Balancers": "AWS::ElasticLoadBalancingV2::LoadBalancer",
                                "Auto Scaling Groups": "AWS::AutoScaling::AutoScalingGroup",
                                "Lambda Functions": "AWS::Lambda::Function",
                                "IAM Policies": "AWS::IAM::Policy",
                            }
                            aws_type = type_map.get(label, "")

                        add_resource(aws_type, aws_arn, name, raw_config if isinstance(raw_config, dict) else {})
                logger.info("Extracted %s: %d items", label, len(items))
            except Exception as exc:
                logger.warning("Failed to extract %s: %s", label, exc)

        session.commit()

        # Mark as discovered
        session.execute(
            update(Migration)
            .where(Migration.id == UUID(migration_id))
            .values(
                discovery_status="discovered",
                discovered_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        logger.info(
            "Discovery completed for migration %s: %d resources extracted",
            migration_id, extracted_count,
        )

    except Exception:
        logger.exception("Discovery failed for migration %s", migration_id)
        try:
            session.rollback()
            session.execute(
                update(Migration)
                .where(Migration.id == UUID(migration_id))
                .values(
                    discovery_status="failed",
                    discovery_error=traceback.format_exc()[-2000:],
                )
            )
            session.commit()
        except Exception:
            logger.exception("Failed to update discovery status to 'failed'")
    finally:
        session.close()
        engine.dispose()
