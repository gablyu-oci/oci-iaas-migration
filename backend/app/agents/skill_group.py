"""Per-skill writer + reviewer pair with a bounded review-edit loop.

Each ``SkillGroup`` pairs two agents:

- **Writer** runs on ``settings.LLM_WRITER_MODEL`` and has tools to look up
  canonical mappings and (for CFN) self-validate HCL.
- **Reviewer** runs on ``settings.LLM_REVIEWER_MODEL`` and has the same
  lookup tools so it can verify claims independently.

``SkillGroup.run(input, ctx)`` drives the enhance → review → (revise) loop:

1. Writer produces an initial draft.
2. Reviewer scores it (APPROVED / APPROVED_WITH_NOTES / NEEDS_FIXES + confidence + issues).
3. If APPROVED **and** confidence ≥ ``confidence_threshold`` → stop.
4. Otherwise writer revises with the reviewer's issues, reviewer re-scores.
5. Repeat until max_iterations or early-stop.

max_iterations and confidence_threshold come from the caller — typically
the user's "Max iterations" picker on the skill-run form.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from agents import Agent, ModelSettings, Runner

from app import mappings
from app.agents.config import build_model
from app.agents.context import MigrationContext
from app.agents.tools import (
    list_resources_for_skill,
    lookup_aws_mapping,
    terraform_validate,
)
from app.gateway.model_gateway import get_model

_log = logging.getLogger(__name__)

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"

DEFAULT_MAX_ITERATIONS = 3
DEFAULT_CONFIDENCE_THRESHOLD = 0.90


# ─── Skill specs ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SkillSpec:
    """Configuration for one skill group.

    Attributes:
        skill_type: Internal key (matches a ``MODEL_ROUTING`` entry and the
            on-disk ``app/skills/<skill_type>/`` directory).
        display_name: Human label for logs + UI.
        description: Shown to the orchestrator so it can route.
        input_shape_hint: Free-form hint about the expected input shape.
        needs_terraform_validate: Whether the writer gets the
            ``terraform_validate`` tool. True for skills that emit HCL.
    """
    skill_type: str
    display_name: str
    description: str
    input_shape_hint: str
    needs_terraform_validate: bool = False


# Routing from skill → the AWS CFN types it's responsible for translating.
# Single source of truth used by both the orchestrator (to decide which
# resources feed which skill) and the registry (to render the docs).
#
# If an AWS type is NOT in any set here, the orchestrator flags it as an
# **unknown type** — a gap the user needs to address manually. We never
# silently drop resources.
#
# Entries marked with ``None`` are skills that operate on inputs other than
# raw AWS resources (synthesis consumes prior-skill outputs; workload_planning
# and dependency_discovery need assessment context, not a flat resource list).

SKILL_TO_AWS_TYPES: dict[str, frozenset[str] | None] = {
    "iam_translation":         frozenset({
        "AWS::IAM::Policy", "AWS::IAM::Role", "AWS::IAM::User",
        "AWS::IAM::Group", "AWS::IAM::InstanceProfile", "AWS::IAM::AccessKey",
    }),
    "network_translation":     frozenset({
        # Core VPC
        "AWS::EC2::VPC", "AWS::EC2::Subnet", "AWS::EC2::SecurityGroup",
        "AWS::EC2::NetworkInterface", "AWS::EC2::InternetGateway",
        "AWS::EC2::NatGateway", "AWS::EC2::RouteTable",
        "AWS::EC2::EIP", "AWS::EC2::NetworkAcl",
        # Peering + transit + private link
        "AWS::EC2::VPCPeeringConnection", "AWS::EC2::TransitGateway",
        "AWS::EC2::TransitGatewayAttachment", "AWS::EC2::TransitGatewayRouteTable",
        "AWS::EC2::VPCEndpoint",
        # VPN / Direct Connect
        "AWS::EC2::VPNConnection", "AWS::EC2::VPNGateway",
        "AWS::EC2::CustomerGateway", "AWS::DirectConnect::Connection",
        # DNS
        "AWS::Route53::HostedZone", "AWS::Route53::RecordSet",
    }),
    "ec2_translation":         frozenset({
        "AWS::EC2::Instance", "AWS::AutoScaling::AutoScalingGroup",
        "AWS::AutoScaling::LaunchConfiguration",
        "AWS::EC2::LaunchTemplate", "AWS::EC2::Image",
        "AWS::EC2::KeyPair", "AWS::EC2::SpotFleet",
    }),
    "storage_translation":     frozenset({
        "AWS::EC2::Volume", "AWS::EC2::VolumeAttachment", "AWS::EC2::Snapshot",
        "AWS::S3::Bucket", "AWS::S3::BucketPolicy",
        "AWS::EFS::FileSystem", "AWS::EFS::MountTarget", "AWS::EFS::AccessPoint",
        "AWS::FSx::FileSystem",
    }),
    "database_translation":    frozenset({
        "AWS::RDS::DBInstance", "AWS::RDS::DBCluster",
        "AWS::RDS::DBSubnetGroup", "AWS::RDS::DBParameterGroup",
        "AWS::DynamoDB::Table",
        "AWS::ElastiCache::CacheCluster", "AWS::ElastiCache::ReplicationGroup",
        "AWS::DocDB::DBCluster", "AWS::Neptune::DBCluster",
        "AWS::OpenSearchService::Domain", "AWS::Redshift::Cluster",
        "AWS::DAX::Cluster", "AWS::MSK::Cluster", "AWS::Timestream::Database",
    }),
    "loadbalancer_translation":frozenset({
        "AWS::ElasticLoadBalancingV2::LoadBalancer",
        "AWS::ElasticLoadBalancingV2::TargetGroup",
        "AWS::ElasticLoadBalancingV2::Listener",
        "AWS::ElasticLoadBalancing::LoadBalancer",   # Classic ELB
    }),
    "security_translation":    frozenset({
        "AWS::KMS::Key", "AWS::KMS::Alias",
        "AWS::SecretsManager::Secret", "AWS::SecretsManager::RotationSchedule",
        "AWS::SSM::Parameter",
        "AWS::CertificateManager::Certificate",
        "AWS::WAFv2::WebACL", "AWS::WAFv2::IPSet",
    }),
    "serverless_translation":  frozenset({
        "AWS::Lambda::Function", "AWS::Lambda::LayerVersion",
        "AWS::Lambda::EventSourceMapping",
        "AWS::ApiGateway::RestApi", "AWS::ApiGatewayV2::Api", "AWS::ApiGateway::Stage",
        "AWS::StepFunctions::StateMachine",
        "AWS::Events::Rule", "AWS::Events::EventBus",
        "AWS::Kinesis::Stream", "AWS::KinesisFirehose::DeliveryStream",
        "AWS::ECS::Service", "AWS::ECS::TaskDefinition", "AWS::ECS::Cluster",
        "AWS::EKS::Cluster", "AWS::EKS::Nodegroup", "AWS::ECR::Repository",
    }),
    "observability_translation":frozenset({
        "AWS::CloudWatch::Alarm", "AWS::CloudWatch::Dashboard",
        "AWS::Logs::LogGroup", "AWS::Logs::LogStream",
        "AWS::Logs::SubscriptionFilter",
        "AWS::SNS::Topic", "AWS::SNS::Subscription",
        "AWS::SQS::Queue", "AWS::SQS::QueuePolicy",
        "AWS::CloudTrail::Trail",
    }),
    "cfn_terraform":           frozenset({
        "AWS::CloudFormation::Stack", "AWS::CloudFront::Distribution",
    }),
    # OCM handoff runs in parallel with ec2_translation on EC2 instances.
    # The plan_orchestrator picks between the two outputs based on each
    # instance's ocm_compatibility level: OCM-ready → OCM path;
    # unsupported → native ec2_translation fallback.
    "ocm_handoff_translation": frozenset({
        "AWS::EC2::Instance",
    }),
    "data_migration_planning": None,  # routes off DB resources but consumed differently
    "synthesis":               None,  # consumes prior skill outputs, not raw resources
    "workload_planning":       None,  # needs assessment output
    "dependency_discovery":    None,  # needs CloudTrail / flow-log input
}

# Every AWS type covered by some skill. Used to flag "unknown" types — those
# present in an inventory but not claimed by any skill.
KNOWN_AWS_TYPES: frozenset[str] = frozenset().union(*(
    s for s in SKILL_TO_AWS_TYPES.values() if s is not None
))


SKILL_SPECS: dict[str, SkillSpec] = {
    "cfn_terraform": SkillSpec(
        skill_type="cfn_terraform",
        display_name="CFN Terraform Translator",
        description=(
            "Converts AWS CloudFormation templates (YAML or JSON) to "
            "production-ready OCI Terraform HCL. Uses terraform_validate "
            "to self-check HCL correctness before returning."
        ),
        input_shape_hint="A CloudFormation template (string, YAML or JSON).",
        needs_terraform_validate=True,
    ),
    "iam_translation": SkillSpec(
        skill_type="iam_translation",
        display_name="IAM Policy Translator",
        description=(
            "Translates AWS IAM JSON policies to OCI IAM policy statements "
            "(verb-based: inspect/read/use/manage)."
        ),
        input_shape_hint="An AWS IAM policy JSON document (string).",
    ),
    "network_translation": SkillSpec(
        skill_type="network_translation",
        display_name="Network Translator",
        description=(
            "AWS VPC + subnets + SGs + gateways + route tables + ENIs → "
            "OCI VCN + subnets + NSGs + route tables. Must run before any "
            "compute/DB/LB skill that references subnet or NSG OCIDs."
        ),
        input_shape_hint=(
            "Dict with `vpcs`, `subnets`, `security_groups`, "
            "`internet_gateways`, `nat_gateways`, `route_tables`, `enis`."
        ),
        needs_terraform_validate=True,
    ),
    "ec2_translation": SkillSpec(
        skill_type="ec2_translation",
        display_name="EC2 Translator",
        description=(
            "EC2 instances + data EBS volumes + ASGs → OCI Compute + Block "
            "Volume + Instance Pool Terraform. Root volumes are inlined on "
            "the instance, not separate resources."
        ),
        input_shape_hint="Dict with `instances` (+ optionally `auto_scaling_groups`).",
        needs_terraform_validate=True,
    ),
    "ocm_handoff_translation": SkillSpec(
        skill_type="ocm_handoff_translation",
        display_name="OCM Handoff Translator",
        description=(
            "Hybrid-mode EC2 replacement for ec2_translation. Emits "
            "oci_cloud_migrations_{migration,migration_plan,target_asset,"
            "replication_schedule} Terraform + a step-by-step handoff.md "
            "runbook the operator follows before and after apply. Only "
            "translates instances whose assessed ocm_compatibility.level "
            "is full / with_prep / manual — unsupported ones fall through "
            "to native ec2_translation."
        ),
        input_shape_hint=(
            "Dict with `instances` (each carrying ocm_compatibility from "
            "the assessment), `ocm_prereqs`, `target_shape_whitelist`, and "
            "target compartment / VCN / subnet variable names."
        ),
        needs_terraform_validate=True,
    ),
    "storage_translation": SkillSpec(
        skill_type="storage_translation",
        display_name="Storage Translator",
        description=(
            "Standalone / data EBS volumes → OCI Block Volumes with matching "
            "performance tiers. Skips root volumes (EC2 skill's job)."
        ),
        input_shape_hint="Dict with `volumes`: list of EBS volume configs.",
        needs_terraform_validate=True,
    ),
    "database_translation": SkillSpec(
        skill_type="database_translation",
        display_name="Database Translator",
        description=(
            "RDS instances / clusters → OCI Database Systems / MySQL HeatWave "
            "/ Autonomous Database. Flags SQL Server as needing self-hosted "
            "Compute."
        ),
        input_shape_hint="Dict with `db_instances` (+ optionally `db_clusters`).",
        needs_terraform_validate=True,
    ),
    "loadbalancer_translation": SkillSpec(
        skill_type="loadbalancer_translation",
        display_name="Load Balancer Translator",
        description=(
            "ALB / NLB → OCI Load Balancer (L7) / Network Load Balancer (L4). "
            "Maps backend sets, listeners, health checks. HTTPS listeners "
            "flagged as needing cert import."
        ),
        input_shape_hint=(
            "Dict with `load_balancers` + nested `target_groups`, `listeners`."
        ),
        needs_terraform_validate=True,
    ),
    "security_translation": SkillSpec(
        skill_type="security_translation",
        display_name="Security Translator",
        description=(
            "KMS keys / Secrets Manager / SSM Parameter Store / ACM / WAFv2 → "
            "OCI Vault (keys + secrets) / Certificate Service / Web Application "
            "Firewall. Writes HCL for every object and flags rotation/policy "
            "gaps."
        ),
        input_shape_hint=(
            "Dict with `kms_keys`, `secrets`, `ssm_parameters`, "
            "`certificates`, `waf_acls`, `waf_ip_sets`."
        ),
        needs_terraform_validate=True,
    ),
    "serverless_translation": SkillSpec(
        skill_type="serverless_translation",
        display_name="Serverless / Containers Translator",
        description=(
            "Lambda / API Gateway / Step Functions / EventBridge / Kinesis / "
            "ECS / EKS / ECR → OCI Functions / API Gateway / Events / "
            "Streaming / Container Instances / OKE / OCIR. Emits HCL for each "
            "and calls out patterns that can't translate 1:1 (Lambda layers, "
            "Step Functions state machines, WebSocket APIs)."
        ),
        input_shape_hint=(
            "Dict with `functions`, `apis`, `state_machines`, `event_rules`, "
            "`streams`, `ecs_services`, `eks_clusters`, `container_repos`."
        ),
        needs_terraform_validate=True,
    ),
    "observability_translation": SkillSpec(
        skill_type="observability_translation",
        display_name="Observability / Messaging Translator",
        description=(
            "CloudWatch alarms + dashboards + logs, SNS, SQS, CloudTrail → "
            "OCI Monitoring / Logging / Notifications / Queue / Audit. Emits "
            "HCL plus metric-namespace mapping notes."
        ),
        input_shape_hint=(
            "Dict with `alarms`, `dashboards`, `log_groups`, `log_streams`, "
            "`sns_topics`, `sns_subscriptions`, `sqs_queues`, `trails`."
        ),
        needs_terraform_validate=True,
    ),
    "data_migration_planning": SkillSpec(
        skill_type="data_migration_planning",
        display_name="Data Migration Planner",
        description=(
            "Cutover runbook (not Terraform) for moving DB data AWS → OCI: "
            "tool selection, phase plan, rollback, downtime estimate."
        ),
        input_shape_hint="Dict describing the source DB(s).",
    ),
    "workload_planning": SkillSpec(
        skill_type="workload_planning",
        display_name="Workload Planner",
        description=(
            "Per-workload runbook + anomaly analysis scoped to one "
            "discovered app group."
        ),
        input_shape_hint="Dict with the workload's resources + dependency edges.",
    ),
    "dependency_discovery": SkillSpec(
        skill_type="dependency_discovery",
        display_name="Dependency Discovery Analyst",
        description=(
            "Reviews CloudTrail / VPC-flow-log dependency graphs for anomalies "
            "(ghost deps, SPOFs, tight-coupling hotspots)."
        ),
        input_shape_hint="Dict: nodes, edges, optional flow-log deps, step ordering.",
    ),
    "synthesis": SkillSpec(
        skill_type="synthesis",
        display_name="Migration Synthesizer",
        description=(
            "Final-stage composer: takes every per-skill artifact and "
            "produces the workload's final Terraform package."
        ),
        input_shape_hint="Dict keyed by prior skill names, each a translation result.",
        needs_terraform_validate=True,
    ),
}


# ─── Prompt assembly ──────────────────────────────────────────────────────────

def _load_workflow_prose(skill_type: str) -> str:
    workflows = SKILLS_ROOT / skill_type / "workflows"
    if not workflows.exists():
        return ""
    chunks = []
    for md in sorted(workflows.glob("*.md")):
        body = md.read_text(encoding="utf-8").strip()
        if body:
            chunks.append(f"### `{md.name}`\n\n{body}")
    return "\n\n".join(chunks)


def _common_context_section(spec: SkillSpec) -> str:
    """Mapping table + prose rules — shown to both writer and reviewer."""
    table = mappings.render_resource_table_md(skill=spec.skill_type)
    prose = _load_workflow_prose(spec.skill_type)
    parts = [
        f"## Canonical AWS → OCI Resource Table (skill={spec.skill_type})",
        "",
        table or "_(no mapping rows for this skill)_",
    ]
    if prose:
        parts += ["", "## Prose rules (ordering, edge cases, examples)", "", prose]
    return "\n".join(parts)


def _writer_instructions(spec: SkillSpec) -> str:
    tool_tips = []
    tool_tips.append(
        "- `lookup_aws_mapping(aws_type)`: resolve an AWS type's canonical "
        "OCI target from the YAML. Prefer this over guessing."
    )
    tool_tips.append(
        "- `list_resources_for_skill(skill)`: list every AWS type this skill "
        "can translate."
    )
    if spec.needs_terraform_validate:
        tool_tips.append(
            "- `terraform_validate(main_tf, variables_tf, outputs_tf)`: run "
            "`terraform init -backend=false && terraform validate` on your "
            "HCL. Call this BEFORE returning — do not deliver HCL you "
            "haven't validated."
        )

    return "\n".join([
        f"You are the **{spec.display_name}** writer agent.",
        "",
        spec.description.strip(),
        "",
        f"Expected input shape: {spec.input_shape_hint}",
        "",
        "## Tools available to you",
        "",
        "\n".join(tool_tips),
        "",
        "## Workflow",
        "",
        "1. If reviewer feedback was included in the prompt, treat the listed "
        "issues as the ONLY work to do — do not regenerate from scratch.",
        "2. Otherwise produce a complete first draft.",
        "3. Call tools to verify your mappings / validate your HCL.",
        "4. Return the finished translation as a single JSON object.",
        "",
        "## Output format (important)",
        "",
        "**Use real filenames as JSON keys**, with the extension as a dot-suffix:",
        "",
        "```json",
        "{",
        '  "main.tf":       "<full HCL content>",',
        '  "variables.tf":  "<full HCL content>",',
        '  "outputs.tf":    "<full HCL content>",',
        '  "resource_mappings": [...],',
        '  "gaps": [...],',
        '  "migration_prerequisites": [...]',
        "}",
        "```",
        "",
        "Do NOT use underscore-suffix aliases like `main_tf` / `variables_tf` / "
        "`handoff_md` — those end up written to disk as `main_tf.txt` and lose "
        "editor syntax highlighting. Always use the real filename as the key.",
        "",
        "## Completeness",
        "",
        "Translate EVERY resource the input asks about. Do not emit placeholders "
        "like \"# ... and N more similar resources\". If the input has 30 "
        "resources, your output has ≥ 30 resource blocks. Long HCL is fine — "
        "truncated HCL is a failure that causes missing OCI resources at apply time.",
        "",
        _common_context_section(spec),
    ])


def _reviewer_instructions(spec: SkillSpec) -> str:
    return "\n".join([
        f"You are the **{spec.display_name}** reviewer agent.",
        "",
        "Your only job is to score a draft translation and return structured "
        "feedback. You do NOT produce new HCL or JSON — you critique.",
        "",
        "## Tools available to you",
        "",
        "- `lookup_aws_mapping(aws_type)`: verify the writer used the right "
        "OCI target. Call this for any mapping you're uncertain about.",
        "",
        "## Review output contract (STRICT)",
        "",
        "Return a SINGLE JSON object with exactly these fields:",
        "",
        "```json",
        "{",
        '  "decision": "APPROVED" | "APPROVED_WITH_NOTES" | "NEEDS_FIXES",',
        '  "confidence": 0.0 to 1.0,',
        '  "issues": [',
        '    {"severity": "CRITICAL"|"HIGH"|"MEDIUM"|"LOW",',
        '     "description": "...", "recommendation": "..."}',
        "  ],",
        '  "review_summary": "2-3 sentence overall assessment"',
        "}",
        "```",
        "",
        "Severity guide:",
        "- `CRITICAL`: wrong OCI resource type, invalid HCL, would fail `terraform validate`.",
        "- `HIGH`: missing required field, wrong protocol/engine mapping, dangling reference.",
        "- `MEDIUM`: suboptimal config, missing tag, best-practice gap.",
        "- `LOW`: style / naming / non-blocking.",
        "",
        "Decision rules:",
        "- Any CRITICAL → NEEDS_FIXES.",
        "- HIGH issues → NEEDS_FIXES unless the writer explicitly noted them as gaps.",
        "- Only MEDIUM/LOW → APPROVED_WITH_NOTES.",
        "- No issues → APPROVED.",
        "",
        "Confidence guidance: the fraction of the draft you're confident is "
        "correct. 0.95+ = strongly correct. 0.75 = correct but missing "
        "coverage. <0.5 = fundamentally wrong.",
        "",
        _common_context_section(spec),
    ])


# Max output tokens for writer agents. The openai-agents SDK + OpenAI's
# chat-completions default to a few thousand tokens — enough for small
# skill outputs (IAM policies, runbook markdown, single-instance HCL) but
# **too small for synthesis merging a 30-resource stack**: a complete
# main.tf for 30 resources is routinely 10k-20k tokens of HCL, so the
# response was being silently truncated at ~5 resources with no error.
# Set a high explicit cap so the writer can emit the full file. gpt-5.x
# supports up to 128k output; 32k is conservative headroom for any
# realistic enterprise stack.
_WRITER_MAX_OUTPUT_TOKENS = 32_000

# Reviewers emit a small structured JSON verdict, not HCL, so their cap
# stays at the model default (setting max_tokens=None leaves it alone).


def _build_writer(spec: SkillSpec) -> Agent:
    tools = [lookup_aws_mapping, list_resources_for_skill]
    if spec.needs_terraform_validate:
        tools.append(terraform_validate)
    return Agent(
        name=f"{spec.display_name} (writer)",
        instructions=_writer_instructions(spec),
        model=build_model(get_model(spec.skill_type, "enhancement")),
        model_settings=ModelSettings(max_tokens=_WRITER_MAX_OUTPUT_TOKENS),
        tools=tools,
    )


def _build_reviewer(spec: SkillSpec) -> Agent:
    return Agent(
        name=f"{spec.display_name} (reviewer)",
        instructions=_reviewer_instructions(spec),
        model=build_model(get_model(spec.skill_type, "review")),
        tools=[lookup_aws_mapping],
    )


# ─── The loop ─────────────────────────────────────────────────────────────────

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction from a writer or reviewer response."""
    if not isinstance(text, str):
        return {"raw": text}
    s = text.strip()
    m = _JSON_FENCE_RE.search(s)
    if m:
        s = m.group(1)
    else:
        a, b = s.find("{"), s.rfind("}") + 1
        if a != -1 and b > a:
            s = s[a:b]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return {"raw": text}


def _count_tool_calls(result) -> int:
    return sum(
        1 for item in result.new_items
        if getattr(item, "type", "") == "tool_call_item"
    )


@dataclass
class SkillRunResult:
    """Structured return shape for one skill-group run."""
    skill_type: str
    draft: dict                 # the writer's final output (parsed JSON)
    review: dict                # the reviewer's final verdict (parsed JSON)
    iterations: int             # rounds executed (1..max_iterations)
    stopped_early: bool         # True if we broke out on confidence, False if we hit max
    writer_tool_calls: int
    reviewer_tool_calls: int

    @property
    def approved(self) -> bool:
        return self.review.get("decision") in ("APPROVED", "APPROVED_WITH_NOTES")

    def as_dict(self) -> dict:
        return {
            "skill_type": self.skill_type,
            "draft": self.draft,
            "review": self.review,
            "iterations": self.iterations,
            "stopped_early": self.stopped_early,
            "approved": self.approved,
            "writer_tool_calls": self.writer_tool_calls,
            "reviewer_tool_calls": self.reviewer_tool_calls,
        }


class SkillGroup:
    """Writer + reviewer + bounded review-edit loop for one skill."""

    def __init__(
        self,
        spec: SkillSpec,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ):
        self.spec = spec
        self.max_iterations = max(1, int(max_iterations))
        self.confidence_threshold = float(confidence_threshold)
        self.writer = _build_writer(spec)
        self.reviewer = _build_reviewer(spec)

    async def run(
        self,
        input_content: str,
        ctx: MigrationContext | None = None,
    ) -> SkillRunResult:
        ctx = ctx or MigrationContext()
        draft: dict = {}
        review: dict = {}
        writer_tools = 0
        reviewer_tools = 0
        iterations = 0
        stopped_early = False
        issues: list = []

        for iteration in range(1, self.max_iterations + 1):
            iterations = iteration

            # ── Writer turn ────────────────────────────────────────────────
            writer_prompt = self._build_writer_turn(input_content, draft, issues, iteration)
            wr = await Runner.run(self.writer, input=writer_prompt, context=ctx)
            writer_tools += _count_tool_calls(wr)
            draft = _extract_json(wr.final_output)

            # ── Reviewer turn ──────────────────────────────────────────────
            review_prompt = self._build_reviewer_turn(input_content, draft)
            rr = await Runner.run(self.reviewer, input=review_prompt, context=ctx)
            reviewer_tools += _count_tool_calls(rr)
            review = _extract_json(rr.final_output)

            decision = review.get("decision", "")
            confidence = float(review.get("confidence", 0.0) or 0.0)
            issues = review.get("issues", []) or []

            _log.info(
                "%s iter %d/%d: %s (confidence=%.2f, %d issues)",
                self.spec.skill_type, iteration, self.max_iterations,
                decision, confidence, len(issues),
            )

            # Early stop: approved with confidence ≥ threshold
            if decision in ("APPROVED", "APPROVED_WITH_NOTES") and confidence >= self.confidence_threshold:
                stopped_early = iteration < self.max_iterations
                break

        return SkillRunResult(
            skill_type=self.spec.skill_type,
            draft=draft,
            review=review,
            iterations=iterations,
            stopped_early=stopped_early,
            writer_tool_calls=writer_tools,
            reviewer_tool_calls=reviewer_tools,
        )

    # ── Turn builders ──────────────────────────────────────────────────────

    def _build_writer_turn(
        self, input_content: str, draft: dict, issues: list, iteration: int,
    ) -> str:
        if iteration == 1 or not draft:
            return f"## Input\n\n{input_content}\n\nProduce the initial draft."
        prev = json.dumps(draft, indent=2) if draft else "{}"
        issues_text = json.dumps(issues, indent=2) if issues else "[]"
        return (
            f"## Original Input\n\n{input_content}\n\n"
            f"## Previous Draft (iteration {iteration - 1})\n```json\n{prev}\n```\n\n"
            f"## Reviewer Issues To Fix\n```json\n{issues_text}\n```\n\n"
            f"Fix ONLY the listed issues. Do not regenerate fields that weren't flagged."
        )

    def _build_reviewer_turn(self, input_content: str, draft: dict) -> str:
        draft_text = json.dumps(draft, indent=2) if draft else "{}"
        # Trim input_content for review (reviewer doesn't need the raw template again)
        inp = input_content[:2000]
        return (
            f"## Original Input (first 2000 chars)\n\n{inp}\n\n"
            f"## Draft To Review\n```json\n{draft_text}\n```\n\n"
            "Score this draft per your contract."
        )


# ─── Convenience ───────────────────────────────────────────────────────────────

def get_skill_group(
    skill_type: str,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> SkillGroup:
    spec = SKILL_SPECS.get(skill_type)
    if not spec:
        raise KeyError(
            f"Unknown skill {skill_type!r}. Registered: {sorted(SKILL_SPECS)}"
        )
    return SkillGroup(spec, max_iterations, confidence_threshold)
