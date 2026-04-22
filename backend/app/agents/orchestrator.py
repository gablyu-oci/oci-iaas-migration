"""Python-driven migration orchestrator.

Unlike the LLM-handoff pattern, this orchestrator is Python code that:

1. Reads the discovered AWS resource inventory for a migration.
2. Groups resources into **dependency waves** — skills that must finish
   before later waves can start (network before compute, storage before DB, …).
3. Within a wave, runs every applicable skill group **in parallel** via
   ``asyncio.gather``. Each skill group is itself a writer+reviewer agent
   pair that runs a bounded iteration loop (see ``skill_group.py``).
4. Collects all skill outputs and returns them as a single structured
   result, plus an overall summary.

Why Python instead of an LLM orchestrator: our dispatch is prescriptive
(dependency-ordered), not adaptive. An LLM deciding "should I run the
network skill first or compute first?" adds latency + a failure mode
without adding value. LLMs shine inside the skill groups (write/review/
validate) where judgement matters.

Callers:
- ``/api/migrations/{id}/generate-plan`` API route (future wiring).
- ``app.services.job_runner`` via ``run_skill()`` for single-skill jobs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

from app.agents.context import MigrationContext
from app.agents.skill_group import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_MAX_ITERATIONS,
    KNOWN_AWS_TYPES,
    SKILL_SPECS,
    SKILL_TO_AWS_TYPES,
    SkillGroup,
    SkillRunResult,
    get_skill_group,
)

_log = logging.getLogger(__name__)


# ─── Dependency waves ─────────────────────────────────────────────────────────
# Skills within a wave run in parallel; waves run sequentially.
# Order is determined by OCI resource dependencies (VCN before subnets before
# instances, etc.). A skill appears in exactly one wave.
DEPENDENCY_WAVES: list[tuple[str, ...]] = (
    # Wave 0 — no infrastructure dependencies. Security (KMS/Vault) runs here
    # because compute + DB + storage references KMS keys.
    ("iam_translation", "security_translation"),
    # Wave 1 — networking foundation (other waves depend on it)
    ("network_translation",),
    # Wave 2 — storage + DB + data-migration planning (need network + security)
    ("storage_translation", "database_translation", "data_migration_planning"),
    # Wave 3 — compute depends on network + (optionally) storage/db
    ("ec2_translation",),
    # Wave 4 — load balancers depend on backends (instances)
    ("loadbalancer_translation",),
    # Wave 5 — serverless + containers (may reference earlier resources)
    ("serverless_translation",),
    # Wave 6 — observability + messaging (targets everything above)
    ("observability_translation",),
    # Wave 7 — full CFN stack translation (if input was a CFN template)
    ("cfn_terraform",),
    # Wave 8 — per-workload planning (needs everything above)
    ("workload_planning", "dependency_discovery"),
    # Wave 9 — final synthesis composes every prior artifact
    ("synthesis",),
)


# ─── Orchestrator result ──────────────────────────────────────────────────────

@dataclass
class OrchestratorResult:
    """Structured return shape for one full migration orchestration run.

    Gap-tracking fields (``unknown_resource_types``, ``unmatched_resource_count``,
    ``skipped_skills``) surface what we did *not* translate so callers never
    see a silent drop. These are populated from the resource inventory —
    they're inputs to the UI's "what still needs manual work" list.
    """
    migration_id: str
    max_iterations: int
    confidence_threshold: float
    elapsed_seconds: float
    total_resources: int                         # input inventory size
    matched_resources: int                       # resources claimed by at least one skill
    unmatched_resource_count: int                # resources with no skill
    unknown_resource_types: list[str]            # AWS types in inventory not in KNOWN_AWS_TYPES
    skipped_skills: list[str]                    # skills registered but with zero resources
    waves: list[dict]                            # one entry per wave
    skills: dict[str, dict]                      # skill_type → SkillRunResult.as_dict()
    total_writer_tool_calls: int
    total_reviewer_tool_calls: int
    failed_skills: list[str]
    summary: str                                 # short human line

    def as_dict(self) -> dict:
        return asdict(self)


# ─── Input builders ───────────────────────────────────────────────────────────
# Each skill expects a slightly different input shape. These helpers turn
# a flat list of AWS resources into the per-skill payload. They mirror the
# ``_build_*_input`` functions in ``app.services.job_runner`` — that module's
# logic is the authoritative source; we delegate to it to avoid drift.


def _select_resources_for(skill: str, resources: list[dict]) -> list[dict]:
    """Return raw resource dicts relevant to a given skill.

    Routing table lives in ``skill_group.SKILL_TO_AWS_TYPES`` — the single
    source of truth also consumed by the registry. A skill whose entry is
    ``None`` doesn't route off raw resources (synthesis, workload_planning,
    …) and always returns empty here.
    """
    types = SKILL_TO_AWS_TYPES.get(skill)
    if not types:
        return []
    return [r for r in resources if r.get("aws_type") in types]


def _classify_inventory(resources: list[dict]) -> tuple[list[str], list[str], int]:
    """Split the inventory into (matched_aws_types, unknown_aws_types, unmatched_count).

    - ``matched``: types present in inventory AND claimed by some skill
    - ``unknown``: types present in inventory but not claimed by any skill
    - ``unmatched_count``: individual resources with an unknown type
    """
    types_in_inventory: set[str] = set()
    unmatched = 0
    for r in resources:
        t = r.get("aws_type")
        if not t:
            continue
        types_in_inventory.add(t)
        if t not in KNOWN_AWS_TYPES:
            unmatched += 1
    matched = sorted(types_in_inventory & KNOWN_AWS_TYPES)
    unknown = sorted(types_in_inventory - KNOWN_AWS_TYPES)
    return matched, unknown, unmatched


def _build_input_for(skill: str, resources: list[dict], prior_results: dict) -> str | None:
    """Build the JSON input string the skill expects. Returns None to skip."""
    selected = _select_resources_for(skill, resources)

    if skill == "iam_translation":
        if not selected:
            return None
        # Keep the legacy single-policy shape when the inventory is exactly one
        # IAM::Policy document (lets the existing writer prompt match). For
        # anything else, fan out into per-object buckets.
        only_policies = all(
            r.get("aws_type") == "AWS::IAM::Policy" for r in selected
        )
        if only_policies and len(selected) == 1:
            rc = selected[0].get("raw_config") or {}
            return json.dumps(rc) if rc else None
        return json.dumps({
            "policies": [r.get("raw_config", {}) for r in selected
                          if r.get("aws_type") == "AWS::IAM::Policy"],
            "roles": [r.get("raw_config", {}) for r in selected
                       if r.get("aws_type") == "AWS::IAM::Role"],
            "users": [r.get("raw_config", {}) for r in selected
                       if r.get("aws_type") == "AWS::IAM::User"],
            "groups": [r.get("raw_config", {}) for r in selected
                        if r.get("aws_type") == "AWS::IAM::Group"],
            "instance_profiles": [r.get("raw_config", {}) for r in selected
                                   if r.get("aws_type") == "AWS::IAM::InstanceProfile"],
            "access_keys": [r.get("raw_config", {}) for r in selected
                             if r.get("aws_type") == "AWS::IAM::AccessKey"],
        })

    if skill == "network_translation":
        if not selected:
            return None
        from collections import defaultdict
        agg: dict[str, list] = defaultdict(list)
        bucket_by_type = {
            "AWS::EC2::VPC":                     "vpcs",
            "AWS::EC2::Subnet":                  "subnets",
            "AWS::EC2::SecurityGroup":           "security_groups",
            "AWS::EC2::NetworkInterface":        "network_interfaces",
            "AWS::EC2::InternetGateway":         "internet_gateways",
            "AWS::EC2::NatGateway":              "nat_gateways",
            "AWS::EC2::RouteTable":              "route_tables",
            "AWS::EC2::EIP":                     "elastic_ips",
            "AWS::EC2::NetworkAcl":              "network_acls",
            "AWS::EC2::VPCPeeringConnection":    "vpc_peerings",
            "AWS::EC2::TransitGateway":          "transit_gateways",
            "AWS::EC2::TransitGatewayAttachment":"transit_gateway_attachments",
            "AWS::EC2::TransitGatewayRouteTable":"transit_gateway_route_tables",
            "AWS::EC2::VPCEndpoint":             "vpc_endpoints",
            "AWS::EC2::VPNConnection":           "vpn_connections",
            "AWS::EC2::VPNGateway":              "vpn_gateways",
            "AWS::EC2::CustomerGateway":         "customer_gateways",
            "AWS::DirectConnect::Connection":    "direct_connects",
            "AWS::Route53::HostedZone":          "dns_zones",
            "AWS::Route53::RecordSet":           "dns_records",
        }
        for r in selected:
            rc = r.get("raw_config", {}) or {}
            bucket = bucket_by_type.get(r.get("aws_type", ""))
            if bucket:
                agg[bucket].append(rc)
        return json.dumps(agg) if any(agg.values()) else None

    if skill == "ec2_translation":
        if not selected:
            return None
        return json.dumps({
            "instances": [r.get("raw_config", {}) for r in selected
                          if r.get("aws_type") == "AWS::EC2::Instance"],
            "auto_scaling_groups": [r.get("raw_config", {}) for r in selected
                                     if r.get("aws_type") == "AWS::AutoScaling::AutoScalingGroup"],
            "launch_configurations": [r.get("raw_config", {}) for r in selected
                                       if r.get("aws_type") == "AWS::AutoScaling::LaunchConfiguration"],
            "launch_templates": [r.get("raw_config", {}) for r in selected
                                  if r.get("aws_type") == "AWS::EC2::LaunchTemplate"],
            "images": [r.get("raw_config", {}) for r in selected
                        if r.get("aws_type") == "AWS::EC2::Image"],
            "key_pairs": [r.get("raw_config", {}) for r in selected
                           if r.get("aws_type") == "AWS::EC2::KeyPair"],
            "spot_fleets": [r.get("raw_config", {}) for r in selected
                             if r.get("aws_type") == "AWS::EC2::SpotFleet"],
        })

    if skill == "storage_translation":
        if not selected:
            return None
        return json.dumps({
            "volumes": [r.get("raw_config", {}) for r in selected
                         if r.get("aws_type") in ("AWS::EC2::Volume", "AWS::EC2::VolumeAttachment")],
            "snapshots": [r.get("raw_config", {}) for r in selected
                           if r.get("aws_type") == "AWS::EC2::Snapshot"],
            "s3_buckets": [r.get("raw_config", {}) for r in selected
                            if r.get("aws_type") in ("AWS::S3::Bucket", "AWS::S3::BucketPolicy")],
            "efs_filesystems": [r.get("raw_config", {}) for r in selected
                                 if r.get("aws_type") in (
                                     "AWS::EFS::FileSystem", "AWS::EFS::MountTarget", "AWS::EFS::AccessPoint",
                                 )],
            "fsx_filesystems": [r.get("raw_config", {}) for r in selected
                                 if r.get("aws_type") == "AWS::FSx::FileSystem"],
        })

    if skill == "database_translation":
        if not selected:
            return None
        return json.dumps({
            "db_instances": [r.get("raw_config", {}) for r in selected
                              if r.get("aws_type") == "AWS::RDS::DBInstance"],
            "db_clusters": [r.get("raw_config", {}) for r in selected
                             if r.get("aws_type") == "AWS::RDS::DBCluster"],
            "db_subnet_groups": [r.get("raw_config", {}) for r in selected
                                  if r.get("aws_type") == "AWS::RDS::DBSubnetGroup"],
            "db_parameter_groups": [r.get("raw_config", {}) for r in selected
                                     if r.get("aws_type") == "AWS::RDS::DBParameterGroup"],
            "dynamodb_tables": [r.get("raw_config", {}) for r in selected
                                 if r.get("aws_type") == "AWS::DynamoDB::Table"],
            "elasticache_clusters": [r.get("raw_config", {}) for r in selected
                                      if r.get("aws_type") in (
                                          "AWS::ElastiCache::CacheCluster",
                                          "AWS::ElastiCache::ReplicationGroup",
                                      )],
            "documentdb_clusters": [r.get("raw_config", {}) for r in selected
                                     if r.get("aws_type") == "AWS::DocDB::DBCluster"],
            "neptune_clusters": [r.get("raw_config", {}) for r in selected
                                  if r.get("aws_type") == "AWS::Neptune::DBCluster"],
            "opensearch_domains": [r.get("raw_config", {}) for r in selected
                                    if r.get("aws_type") == "AWS::OpenSearchService::Domain"],
            "redshift_clusters": [r.get("raw_config", {}) for r in selected
                                   if r.get("aws_type") == "AWS::Redshift::Cluster"],
            "dax_clusters": [r.get("raw_config", {}) for r in selected
                              if r.get("aws_type") == "AWS::DAX::Cluster"],
            "msk_clusters": [r.get("raw_config", {}) for r in selected
                              if r.get("aws_type") == "AWS::MSK::Cluster"],
            "timestream_databases": [r.get("raw_config", {}) for r in selected
                                      if r.get("aws_type") == "AWS::Timestream::Database"],
        })

    if skill == "loadbalancer_translation":
        if not selected:
            return None
        return json.dumps({
            "load_balancers":  [r.get("raw_config", {}) for r in selected
                                if r.get("aws_type") == "AWS::ElasticLoadBalancingV2::LoadBalancer"],
            "target_groups":   [r.get("raw_config", {}) for r in selected
                                if r.get("aws_type") == "AWS::ElasticLoadBalancingV2::TargetGroup"],
            "listeners":       [r.get("raw_config", {}) for r in selected
                                if r.get("aws_type") == "AWS::ElasticLoadBalancingV2::Listener"],
            "classic_load_balancers": [r.get("raw_config", {}) for r in selected
                                        if r.get("aws_type") == "AWS::ElasticLoadBalancing::LoadBalancer"],
        })

    if skill == "security_translation":
        if not selected:
            return None
        return json.dumps({
            "kms_keys": [r.get("raw_config", {}) for r in selected
                          if r.get("aws_type") in ("AWS::KMS::Key", "AWS::KMS::Alias")],
            "secrets": [r.get("raw_config", {}) for r in selected
                         if r.get("aws_type") in (
                             "AWS::SecretsManager::Secret",
                             "AWS::SecretsManager::RotationSchedule",
                         )],
            "ssm_parameters": [r.get("raw_config", {}) for r in selected
                                if r.get("aws_type") == "AWS::SSM::Parameter"],
            "certificates": [r.get("raw_config", {}) for r in selected
                              if r.get("aws_type") == "AWS::CertificateManager::Certificate"],
            "waf_acls": [r.get("raw_config", {}) for r in selected
                          if r.get("aws_type") == "AWS::WAFv2::WebACL"],
            "waf_ip_sets": [r.get("raw_config", {}) for r in selected
                             if r.get("aws_type") == "AWS::WAFv2::IPSet"],
        })

    if skill == "serverless_translation":
        if not selected:
            return None
        return json.dumps({
            "functions": [r.get("raw_config", {}) for r in selected
                           if r.get("aws_type") in (
                               "AWS::Lambda::Function",
                               "AWS::Lambda::LayerVersion",
                               "AWS::Lambda::EventSourceMapping",
                           )],
            "apis": [r.get("raw_config", {}) for r in selected
                      if r.get("aws_type") in (
                          "AWS::ApiGateway::RestApi",
                          "AWS::ApiGatewayV2::Api",
                          "AWS::ApiGateway::Stage",
                      )],
            "state_machines": [r.get("raw_config", {}) for r in selected
                                if r.get("aws_type") == "AWS::StepFunctions::StateMachine"],
            "event_rules": [r.get("raw_config", {}) for r in selected
                             if r.get("aws_type") in ("AWS::Events::Rule", "AWS::Events::EventBus")],
            "streams": [r.get("raw_config", {}) for r in selected
                         if r.get("aws_type") in (
                             "AWS::Kinesis::Stream",
                             "AWS::KinesisFirehose::DeliveryStream",
                         )],
            "ecs_services": [r.get("raw_config", {}) for r in selected
                              if r.get("aws_type") in (
                                  "AWS::ECS::Service",
                                  "AWS::ECS::TaskDefinition",
                                  "AWS::ECS::Cluster",
                              )],
            "eks_clusters": [r.get("raw_config", {}) for r in selected
                              if r.get("aws_type") in ("AWS::EKS::Cluster", "AWS::EKS::Nodegroup")],
            "container_repos": [r.get("raw_config", {}) for r in selected
                                 if r.get("aws_type") == "AWS::ECR::Repository"],
        })

    if skill == "observability_translation":
        if not selected:
            return None
        return json.dumps({
            "alarms": [r.get("raw_config", {}) for r in selected
                        if r.get("aws_type") == "AWS::CloudWatch::Alarm"],
            "dashboards": [r.get("raw_config", {}) for r in selected
                            if r.get("aws_type") == "AWS::CloudWatch::Dashboard"],
            "log_groups": [r.get("raw_config", {}) for r in selected
                            if r.get("aws_type") == "AWS::Logs::LogGroup"],
            "log_streams": [r.get("raw_config", {}) for r in selected
                             if r.get("aws_type") == "AWS::Logs::LogStream"],
            "log_subscriptions": [r.get("raw_config", {}) for r in selected
                                   if r.get("aws_type") == "AWS::Logs::SubscriptionFilter"],
            "sns_topics": [r.get("raw_config", {}) for r in selected
                            if r.get("aws_type") == "AWS::SNS::Topic"],
            "sns_subscriptions": [r.get("raw_config", {}) for r in selected
                                   if r.get("aws_type") == "AWS::SNS::Subscription"],
            "sqs_queues": [r.get("raw_config", {}) for r in selected
                            if r.get("aws_type") in ("AWS::SQS::Queue", "AWS::SQS::QueuePolicy")],
            "trails": [r.get("raw_config", {}) for r in selected
                        if r.get("aws_type") == "AWS::CloudTrail::Trail"],
        })

    if skill == "cfn_terraform":
        if not selected:
            return None
        # Pass the first stack's template; orchestration for multi-stack is
        # a follow-up.
        rc = selected[0].get("raw_config") or {}
        return rc.get("template") or json.dumps(rc)

    if skill == "synthesis":
        # Synthesis takes all prior skill outputs.
        if not prior_results:
            return None
        return json.dumps({k: v.get("draft") for k, v in prior_results.items() if v.get("draft")})

    if skill == "data_migration_planning":
        db = [r for r in resources if r.get("aws_type") in ("AWS::RDS::DBInstance", "AWS::RDS::DBCluster")]
        return json.dumps({"db_resources": [r.get("raw_config", {}) for r in db]}) if db else None

    if skill in ("workload_planning", "dependency_discovery"):
        # These need more context than this orchestrator has today; skip
        # them from the migration-wide loop and run them only if the caller
        # invokes them directly.
        return None

    return None


# ─── The orchestrator ─────────────────────────────────────────────────────────

class MigrationOrchestrator:
    """Drives a full migration: parallel waves of skill groups with iteration loops.

    Single instance per migration run. Not thread-safe; create a new one
    per migration.

    Args:
        max_iterations: Upper bound on writer↔reviewer rounds per skill.
            Passed through to every ``SkillGroup``.
        confidence_threshold: Early-stop threshold inside each skill group.
    """

    def __init__(
        self,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ):
        self.max_iterations = max(1, int(max_iterations))
        self.confidence_threshold = float(confidence_threshold)

    async def run(
        self,
        migration_id: str,
        resources: list[dict],
        tenant_id: str | None = None,
        aws_connection_id: str | None = None,
    ) -> OrchestratorResult:
        """Run every applicable skill group across ``DEPENDENCY_WAVES``.

        Args:
            migration_id: UUID string for the migration.
            resources: List of discovered resource dicts. Minimum fields:
                ``aws_type``, ``raw_config``. Optional: ``id``, ``name``.
            tenant_id / aws_connection_id: Threaded into ``MigrationContext``
                for tools that need them.

        Returns:
            ``OrchestratorResult`` with per-skill results + wave timing.
        """
        t_start = time.perf_counter()
        ctx = MigrationContext(
            migration_id=migration_id,
            tenant_id=tenant_id,
            aws_connection_id=aws_connection_id,
        )

        # Classify the inventory UP FRONT so we can report gaps even if a
        # skill run fails later.
        matched_types, unknown_types, unmatched_count = _classify_inventory(resources)
        matched_count = len(resources) - unmatched_count
        if unknown_types:
            _log.warning(
                "migration %s: %d unknown AWS resource types will not be translated: %s",
                migration_id, len(unknown_types), unknown_types,
            )

        results: dict[str, dict] = {}
        waves_report: list[dict] = []
        failed: list[str] = []
        # Skills that *could* apply to this inventory but produced no input
        # (e.g., synthesis with no prior results, workload_planning today).
        # We populate this as we walk the waves.
        skipped: list[str] = []
        total_w, total_r = 0, 0

        for wave_idx, wave in enumerate(DEPENDENCY_WAVES):
            wave_t0 = time.perf_counter()
            # Build inputs now so we know which skills are applicable
            planned = []
            for skill in wave:
                inp = _build_input_for(skill, resources, results)
                if inp is None:
                    skipped.append(skill)
                    continue
                planned.append((skill, inp))

            if not planned:
                waves_report.append({
                    "wave": wave_idx, "skills": list(wave),
                    "executed": [], "skipped": list(wave), "duration_s": 0.0,
                })
                continue

            # Parallel dispatch within the wave
            async def _run_one(skill: str, inp: str) -> tuple[str, SkillRunResult | BaseException]:
                try:
                    group = SkillGroup(
                        SKILL_SPECS[skill],
                        max_iterations=self.max_iterations,
                        confidence_threshold=self.confidence_threshold,
                    )
                    res = await group.run(inp, ctx)
                    return skill, res
                except BaseException as exc:  # noqa: BLE001 — surface the failure
                    _log.exception("skill %s failed", skill)
                    return skill, exc

            gathered = await asyncio.gather(*(_run_one(s, i) for s, i in planned))

            executed: list[dict] = []
            for skill, res in gathered:
                if isinstance(res, BaseException):
                    failed.append(skill)
                    results[skill] = {"error": str(res)}
                    executed.append({"skill": skill, "error": str(res)})
                else:
                    results[skill] = res.as_dict()
                    total_w += res.writer_tool_calls
                    total_r += res.reviewer_tool_calls
                    executed.append({
                        "skill": skill,
                        "iterations": res.iterations,
                        "approved": res.approved,
                        "stopped_early": res.stopped_early,
                    })

            waves_report.append({
                "wave": wave_idx, "skills": list(wave),
                "executed": executed,
                "skipped": [s for s in wave if s not in {e["skill"] for e in executed}],
                "duration_s": round(time.perf_counter() - wave_t0, 2),
            })

        elapsed = time.perf_counter() - t_start
        approved = sum(1 for v in results.values() if v.get("approved"))

        summary_parts = [
            f"Ran {len(results)} skills in {elapsed:.1f}s across "
            f"{len([w for w in waves_report if w['executed']])} waves; "
            f"{approved} approved, {len(failed)} failed."
        ]
        if unknown_types:
            summary_parts.append(
                f"⚠ {unmatched_count} resources with {len(unknown_types)} unhandled "
                f"AWS types: {', '.join(unknown_types[:5])}"
                + (" …" if len(unknown_types) > 5 else "")
            )
        if skipped:
            # De-dup while preserving order
            dedup_skipped = list(dict.fromkeys(skipped))
            summary_parts.append(
                f"skipped {len(dedup_skipped)} skills w/ no input: {', '.join(dedup_skipped)}"
            )

        return OrchestratorResult(
            migration_id=migration_id,
            max_iterations=self.max_iterations,
            confidence_threshold=self.confidence_threshold,
            elapsed_seconds=round(elapsed, 2),
            total_resources=len(resources),
            matched_resources=matched_count,
            unmatched_resource_count=unmatched_count,
            unknown_resource_types=unknown_types,
            skipped_skills=list(dict.fromkeys(skipped)),
            waves=waves_report,
            skills=results,
            total_writer_tool_calls=total_w,
            total_reviewer_tool_calls=total_r,
            failed_skills=failed,
            summary=" · ".join(summary_parts),
        )


# ─── Entry points used by the API + job_runner ────────────────────────────────

async def run_migration(
    migration_id: str,
    resources: list[dict] | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    tenant_id: str | None = None,
    aws_connection_id: str | None = None,
) -> dict:
    """Run the full orchestrator for one migration.

    If ``resources`` isn't supplied, load them from the ``resources`` table
    for this migration's AWS connection.
    """
    if resources is None:
        resources = _load_resources_sync(migration_id)

    orchestrator = MigrationOrchestrator(
        max_iterations=max_iterations,
        confidence_threshold=confidence_threshold,
    )
    result = await orchestrator.run(
        migration_id=migration_id,
        resources=resources,
        tenant_id=tenant_id,
        aws_connection_id=aws_connection_id,
    )
    return result.as_dict()


async def run_skill(
    skill_type: str,
    input_content: str,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    migration_id: str | None = None,
) -> dict:
    """Run a single skill group standalone (bypasses the orchestrator)."""
    group = get_skill_group(
        skill_type,
        max_iterations=max_iterations,
        confidence_threshold=confidence_threshold,
    )
    ctx = MigrationContext(migration_id=migration_id) if migration_id else MigrationContext()
    res = await group.run(input_content, ctx)
    return res.as_dict()


def _load_resources_sync(migration_id: str) -> list[dict]:
    """Fetch discovered resources for a migration via a sync engine (called
    from async code, but does its own session — short-lived, fine)."""
    import uuid as _uuid
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from app.config import settings
    from app.db.models import Migration, Resource

    engine = create_engine(settings.DATABASE_URL.replace("+asyncpg", ""), echo=False)
    Session = sessionmaker(bind=engine)
    try:
        with Session() as s:
            mig = s.execute(
                select(Migration).where(Migration.id == _uuid.UUID(migration_id))
            ).scalar_one_or_none()
            if not mig:
                return []
            rows = s.execute(
                select(Resource).where(
                    Resource.aws_connection_id == mig.aws_connection_id
                )
            ).scalars().all()
            return [{
                "id": str(r.id),
                "aws_type": r.aws_type,
                "name": r.name,
                "raw_config": r.raw_config or {},
            } for r in rows]
    finally:
        engine.dispose()
