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

        # Build set of existing ARNs for this connection to avoid duplicates
        existing_result = session.execute(
            select(Resource.aws_arn).where(
                Resource.tenant_id == migration.tenant_id,
                Resource.aws_connection_id == conn.id,
                Resource.aws_arn.isnot(None),
            )
        )
        existing_arns = {row[0] for row in existing_result.all()}

        extracted_count = 0

        def _normalize_arn(arn: str) -> str:
            """Normalize ARN to consistent format for dedup.

            AWS ARNs can have the account ID present or absent:
              arn:aws:ec2:us-west-1:569445999862:subnet/subnet-xxx
              arn:aws:ec2:us-west-1::subnet/subnet-xxx
            Normalize by removing the account ID field so both match.
            """
            if not arn or not arn.startswith("arn:"):
                return arn
            parts = arn.split(":")
            if len(parts) >= 5:
                parts[4] = ""  # Clear account ID field
                return ":".join(parts)
            return arn

        # Normalize existing ARNs for consistent dedup
        existing_arns = {_normalize_arn(a) for a in existing_arns}

        freshly_seen_arns: set[str] = set()  # ARNs discovered in this run (for stale detection)

        def add_resource(aws_type: str, aws_arn: str | None, name: str | None, raw_config: dict) -> Resource | None:
            """Insert a Resource row (unless duplicate). Returns the row (or None if duped)
            so callers can attach post-processing enrichments (metrics, SSM) later in
            the same session."""
            nonlocal extracted_count
            norm_arn = _normalize_arn(aws_arn) if aws_arn else None
            if norm_arn:
                freshly_seen_arns.add(norm_arn)
            if norm_arn and norm_arn in existing_arns:
                return None
            if norm_arn:
                existing_arns.add(norm_arn)
            # Resources are connection-scoped, not migration-scoped
            resource = Resource(
                tenant_id=migration.tenant_id,
                migration_id=None,
                aws_connection_id=conn.id,
                aws_type=aws_type,
                aws_arn=aws_arn,
                name=name,
                raw_config=raw_config,
                status="discovered",
            )
            session.add(resource)
            extracted_count += 1
            return resource

        # Import extractors
        from app.services.aws_extractor import (
            extract_cfn_stacks,
            extract_cfn_stack_resources,
            extract_iam_policies,
            extract_ec2_instances,
            extract_vpcs,
            extract_subnets,
            extract_security_groups,
            extract_ebs_volumes,
            extract_network_interfaces,
            extract_rds_instances,
            extract_load_balancers,
            extract_target_groups,
            extract_listeners,
            extract_auto_scaling_groups,
            extract_launch_templates,
            extract_lambda_functions,
            extract_internet_gateways,
            extract_nat_gateways,
            extract_route_tables,
            extract_network_acls,
            extract_elastic_ips,
            extract_s3_buckets,
            extract_ec2_metrics,
            extract_ssm_inventory,
        )

        # Build CFN membership map: physical_resource_id → stack_name
        # Used to tag discovered resources as CFN-managed for deduplication
        try:
            cfn_membership = extract_cfn_stack_resources(creds, region)
            if cfn_membership:
                logger.info("Found %d CFN-managed resources across stacks", len(cfn_membership))
        except Exception as exc:
            logger.warning("Failed to extract CFN stack resources: %s", exc)
            cfn_membership = {}

        # Extract all resource types
        extractors = [
            ("CFN Stacks", lambda: extract_cfn_stacks(creds, region)),
            ("EC2 Instances", lambda: extract_ec2_instances(creds, region)),
            ("VPCs", lambda: extract_vpcs(creds, region)),
            ("Subnets", lambda: extract_subnets(creds, region)),
            ("Security Groups", lambda: extract_security_groups(creds, region)),
            ("EBS Volumes", lambda: extract_ebs_volumes(creds, region)),
            ("Network Interfaces", lambda: extract_network_interfaces(creds, region)),
            ("RDS Instances", lambda: extract_rds_instances(creds, region)),
            ("Load Balancers", lambda: extract_load_balancers(creds, region)),
            ("Target Groups", lambda: extract_target_groups(creds, region)),
            ("Listeners", lambda: extract_listeners(creds, region)),
            ("Auto Scaling Groups", lambda: extract_auto_scaling_groups(creds, region)),
            ("Launch Templates", lambda: extract_launch_templates(creds, region)),
            ("Lambda Functions", lambda: extract_lambda_functions(creds, region)),
            ("IAM Policies", lambda: extract_iam_policies(creds, region)),
            ("Internet Gateways", lambda: extract_internet_gateways(creds, region)),
            ("NAT Gateways", lambda: extract_nat_gateways(creds, region)),
            ("Route Tables", lambda: extract_route_tables(creds, region)),
            ("Network ACLs", lambda: extract_network_acls(creds, region)),
            ("Elastic IPs", lambda: extract_elastic_ips(creds, region)),
            ("S3 Buckets", lambda: extract_s3_buckets(creds, region)),
        ]

        # Cache of discovered EC2 rows so we can enrich them after the main
        # loop without re-querying the DB. Keyed by instance_id → Resource obj.
        ec2_instances_for_enrich: dict[str, Resource] = {}

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
                                "Subnets": "AWS::EC2::Subnet",
                                "Security Groups": "AWS::EC2::SecurityGroup",
                                "EBS Volumes": "AWS::EC2::Volume",
                                "Network Interfaces": "AWS::EC2::NetworkInterface",
                                "RDS Instances": "AWS::RDS::DBInstance",
                                "Load Balancers": "AWS::ElasticLoadBalancingV2::LoadBalancer",
                                "Target Groups": "AWS::ElasticLoadBalancingV2::TargetGroup",
                                "Listeners": "AWS::ElasticLoadBalancingV2::Listener",
                                "Auto Scaling Groups": "AWS::AutoScaling::AutoScalingGroup",
                                "Launch Templates": "AWS::EC2::LaunchTemplate",
                                "Lambda Functions": "AWS::Lambda::Function",
                                "IAM Policies": "AWS::IAM::Policy",
                                "Internet Gateways": "AWS::EC2::InternetGateway",
                                "NAT Gateways": "AWS::EC2::NatGateway",
                                "Route Tables": "AWS::EC2::RouteTable",
                                "Network ACLs": "AWS::EC2::NetworkAcl",
                                "Elastic IPs": "AWS::EC2::EIP",
                                "S3 Buckets": "AWS::S3::Bucket",
                            }
                            aws_type = type_map.get(label, "")

                        rc = raw_config if isinstance(raw_config, dict) else {}
                        # Tag CFN-managed resources for deduplication
                        if aws_arn and aws_arn in cfn_membership:
                            rc["cfn_stack_name"] = cfn_membership[aws_arn]
                        elif name and name in cfn_membership:
                            rc["cfn_stack_name"] = cfn_membership[name]
                        res_row = add_resource(aws_type, aws_arn, name, rc)
                        # Remember EC2 rows so we can attach CloudWatch / SSM
                        # enrichments after the main loop.
                        if res_row is not None and aws_type == "AWS::EC2::Instance":
                            iid = rc.get("instance_id")
                            if iid:
                                ec2_instances_for_enrich[iid] = res_row
                logger.info("Extracted %s: %d items", label, len(items))
            except Exception as exc:
                logger.warning("Failed to extract %s: %s", label, exc)

        # ── Per-instance enrichment (best-effort, never fails discovery) ──
        # CloudWatch metrics + SSM inventory are pulled once per discovery
        # run and folded into the existing EC2 rows' raw_config.
        if ec2_instances_for_enrich:
            instance_ids = list(ec2_instances_for_enrich.keys())
            try:
                metrics_map = extract_ec2_metrics(creds, region, instance_ids)
                logger.info("CloudWatch metrics collected for %d/%d instances",
                            len(metrics_map), len(instance_ids))
            except Exception as exc:
                logger.warning("CloudWatch metric enrichment failed: %s", exc)
                metrics_map = {}

            try:
                inventory_map = extract_ssm_inventory(creds, region, instance_ids)
                logger.info("SSM inventory collected for %d/%d instances",
                            len(inventory_map), len(instance_ids))
            except Exception as exc:
                logger.warning("SSM inventory enrichment failed: %s", exc)
                inventory_map = {}

            for iid, row in ec2_instances_for_enrich.items():
                rc = dict(row.raw_config or {})
                if iid in metrics_map:
                    rc["metrics"] = metrics_map[iid]
                if iid in inventory_map:
                    rc["software_inventory"] = inventory_map[iid]
                row.raw_config = rc

        session.commit()

        # Mark resources not seen in this run as stale
        if freshly_seen_arns:
            all_conn_resources = session.execute(
                select(Resource.id, Resource.aws_arn).where(
                    Resource.tenant_id == migration.tenant_id,
                    Resource.aws_connection_id == conn.id,
                    Resource.aws_arn.isnot(None),
                    Resource.status != "stale",
                )
            ).all()
            stale_ids = [
                row[0] for row in all_conn_resources
                if _normalize_arn(row[1]) not in freshly_seen_arns
            ]
            if stale_ids:
                session.execute(
                    update(Resource)
                    .where(Resource.id.in_(stale_ids))
                    .values(status="stale")
                )
                session.commit()
                logger.info("Marked %d resources as stale (no longer found in AWS)", len(stale_ids))

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
