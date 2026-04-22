# Agent Architecture

How the agent runtime is organized, what each layer does, and what the
agents can and cannot reach.

> **Single source of truth:** every claim in this doc is backed by the
> machine-readable registry at [`backend/app/agents/registry.py`](../backend/app/agents/registry.py).
> If you add a tool or change the orchestrator workflow, update the registry
> and regenerate this doc via `python3 scripts/render_agent_docs.py`.

---

## Runtime layers

```
                    ┌───────────────────────────────────────┐
                    │  MigrationOrchestrator (Python)        │
                    │  - Python code, no LLM call itself     │
                    │  - Reads DEPENDENCY_WAVES              │
                    │  - asyncio.gather within each wave     │
                    └──────────────┬────────────────────────┘
                                   │ spawns per applicable skill
         ┌─────────────────────────┼────────────────────────┐
         ▼                         ▼                        ▼
    ┌─────────┐              ┌─────────┐              ┌─────────┐
    │SkillGroup│              │SkillGroup│              │SkillGroup│
    │          │              │          │              │          │
    │ writer   │◄─┐         │ writer   │              │ writer   │
    │   +      │  │ loop    │   +      │              │   +      │
    │ reviewer │──┘ up to   │ reviewer │              │ reviewer │
    │          │  max_iter  │          │              │          │
    │ tools:   │            │ tools:   │              │ tools:   │
    │ lookup_  │            │ lookup_  │              │ lookup_  │
    │ mapping, │            │ mapping  │              │ mapping, │
    │ tf_val…  │            │          │              │ tf_val…  │
    └─────────┘              └─────────┘              └─────────┘
```

## Per-skill review-edit loop

Each `SkillGroup.run()` drives a bounded iteration loop:

1. **Writer turn** — runs on `settings.LLM_WRITER_MODEL`. Iteration 1 sees
   the input; later iterations see the previous draft + the reviewer's
   flagged issues.
2. **Reviewer turn** — runs on `settings.LLM_REVIEWER_MODEL`. Scores the
   draft with `{decision, confidence, issues[], review_summary}`.
3. **Early stop** — if `decision ∈ {APPROVED, APPROVED_WITH_NOTES}` **and**
   `confidence ≥ confidence_threshold` (default **0.90**), the loop returns.
4. **Otherwise** — repeat until `max_iterations` (user-configurable on the
   skill-run form, default 3).

## Parallel dispatch across dependency waves

The orchestrator runs **waves sequentially** but runs **skills within a wave
in parallel** via `asyncio.gather`. Dependencies between OCI resources
determine the waves — you can't create instances before the VCN they live
in, you can't fully synthesize before everything else has produced an
artifact.

<!-- BEGIN AUTO-GENERATED REGISTRY -->
## Tool registry

| Tool | Scope | Used by | Context-scoped | Read-only | Description |
|---|---|---|:---:|:---:|---|
| `lookup_aws_mapping` | skill | writer, reviewer | — | ✅ | Resolve an AWS CloudFormation type to its canonical OCI target from data/mappings/resources.yaml. |
| `list_resources_for_skill` | skill | writer | — | ✅ | Enumerate every AWS type a given skill is allowed to translate. |
| `terraform_validate` | skill | writer | — | ✅ | Run `terraform init -backend=false && terraform validate -json` on the supplied HCL inside a bubblewrap sandbox. The agent uses this to self-check correctness before returning. |
| `list_discovered_resources` | orchestrator | orchestrator | ✅ | ✅ | List AWS resources already discovered for the current migration. Reads ``migration_id`` from the trusted MigrationContext — the LLM cannot target a different migration. |
| `count_resources_by_type` | orchestrator | orchestrator | ✅ | ✅ | Count discovered AWS resources for the current migration, grouped by ``aws_type``. Also reads ``migration_id`` from MigrationContext. |

## Agent roles

### orchestrator
- **Model:** n/a (Python code)
- **Tools:** _(none)_
- Python-driven (not LLM-driven). Loads the discovered resource inventory, decides which skill groups are applicable, and dispatches them across ``DEPENDENCY_WAVES`` with parallel execution within each wave. Does not itself call the LLM — the LLM calls happen inside each SkillGroup.

### writer
- **Model:** settings.LLM_WRITER_MODEL
- **Tools:** lookup_aws_mapping, list_resources_for_skill, terraform_validate
- Per skill-group, runs on the user-selected writer model. Produces the initial draft and, on subsequent iterations, revises based on reviewer feedback. Calls mapping-lookup + (for HCL skills) terraform_validate tools.

### reviewer
- **Model:** settings.LLM_REVIEWER_MODEL
- **Tools:** lookup_aws_mapping
- Per skill-group, runs on the user-selected reviewer model. Scores drafts against the skill's contract and the canonical YAML + workflow prose. Returns decision + confidence + issues, never HCL.

## Orchestrator workflow

- **Type:** dependency-wave parallel dispatch
- **Concurrency:** Within a wave every applicable skill runs via asyncio.gather; waves themselves are sequential.
- **Loop policy:**
  - per_skill_loop: writer → reviewer → (revise) → review, bounded
  - max_iterations: user-configurable (default 3)
  - early_stop: reviewer returns APPROVED/APPROVED_WITH_NOTES and confidence >= confidence_threshold (default 0.90)

### Dependency waves

| Wave | Skills | Purpose |
|---:|---|---|
| 0 | `iam_translation`, `security_translation` | IAM + Security (KMS/Vault) — no infra dependencies; consumed by later waves |
| 1 | `network_translation` | Networking foundation (VCN + subnets + NSGs + TGW/DRG + peering) |
| 2 | `storage_translation`, `database_translation`, `data_migration_planning` | Storage / database / data-migration (parallel once network + security exist) |
| 3 | `ec2_translation` | Compute (needs network + storage) |
| 4 | `loadbalancer_translation` | Load balancers (need compute backends) |
| 5 | `serverless_translation` | Serverless + containers (Lambda/Functions, API Gateway, ECS/EKS) |
| 6 | `observability_translation` | Observability + messaging (CloudWatch → Monitoring/Logging, SNS/SQS) |
| 7 | `cfn_terraform` | Full CFN stack translation (when input is a CFN template) |
| 8 | `workload_planning`, `dependency_discovery` | Per-workload runbooks and dependency-graph analysis |
| 9 | `synthesis` | Synthesis — compose every prior artifact |

### Skill → AWS resource-type routing

Single source of truth: `SKILL_TO_AWS_TYPES` in [`skill_group.py`](../backend/app/agents/skill_group.py). Any AWS type NOT on this list shows up in `OrchestratorResult.unknown_resource_types` so the user sees exactly what didn't get translated.

| Skill | AWS types claimed |
|---|---|
| `iam_translation` | `AWS::IAM::AccessKey`, `AWS::IAM::Group`, `AWS::IAM::InstanceProfile`, `AWS::IAM::Policy`, `AWS::IAM::Role`, `AWS::IAM::User` |
| `network_translation` | `AWS::DirectConnect::Connection`, `AWS::EC2::CustomerGateway`, `AWS::EC2::EIP`, `AWS::EC2::InternetGateway`, `AWS::EC2::NatGateway`, `AWS::EC2::NetworkAcl`, `AWS::EC2::NetworkInterface`, `AWS::EC2::RouteTable`, `AWS::EC2::SecurityGroup`, `AWS::EC2::Subnet`, `AWS::EC2::TransitGateway`, `AWS::EC2::TransitGatewayAttachment`, `AWS::EC2::TransitGatewayRouteTable`, `AWS::EC2::VPC`, `AWS::EC2::VPCEndpoint`, `AWS::EC2::VPCPeeringConnection`, `AWS::EC2::VPNConnection`, `AWS::EC2::VPNGateway`, `AWS::Route53::HostedZone`, `AWS::Route53::RecordSet` |
| `ec2_translation` | `AWS::AutoScaling::AutoScalingGroup`, `AWS::AutoScaling::LaunchConfiguration`, `AWS::EC2::Image`, `AWS::EC2::Instance`, `AWS::EC2::KeyPair`, `AWS::EC2::LaunchTemplate`, `AWS::EC2::SpotFleet` |
| `storage_translation` | `AWS::EC2::Snapshot`, `AWS::EC2::Volume`, `AWS::EC2::VolumeAttachment`, `AWS::EFS::AccessPoint`, `AWS::EFS::FileSystem`, `AWS::EFS::MountTarget`, `AWS::FSx::FileSystem`, `AWS::S3::Bucket`, `AWS::S3::BucketPolicy` |
| `database_translation` | `AWS::DAX::Cluster`, `AWS::DocDB::DBCluster`, `AWS::DynamoDB::Table`, `AWS::ElastiCache::CacheCluster`, `AWS::ElastiCache::ReplicationGroup`, `AWS::MSK::Cluster`, `AWS::Neptune::DBCluster`, `AWS::OpenSearchService::Domain`, `AWS::RDS::DBCluster`, `AWS::RDS::DBInstance`, `AWS::RDS::DBParameterGroup`, `AWS::RDS::DBSubnetGroup`, `AWS::Redshift::Cluster`, `AWS::Timestream::Database` |
| `loadbalancer_translation` | `AWS::ElasticLoadBalancing::LoadBalancer`, `AWS::ElasticLoadBalancingV2::Listener`, `AWS::ElasticLoadBalancingV2::LoadBalancer`, `AWS::ElasticLoadBalancingV2::TargetGroup` |
| `security_translation` | `AWS::CertificateManager::Certificate`, `AWS::KMS::Alias`, `AWS::KMS::Key`, `AWS::SSM::Parameter`, `AWS::SecretsManager::RotationSchedule`, `AWS::SecretsManager::Secret`, `AWS::WAFv2::IPSet`, `AWS::WAFv2::WebACL` |
| `serverless_translation` | `AWS::ApiGateway::RestApi`, `AWS::ApiGateway::Stage`, `AWS::ApiGatewayV2::Api`, `AWS::ECR::Repository`, `AWS::ECS::Cluster`, `AWS::ECS::Service`, `AWS::ECS::TaskDefinition`, `AWS::EKS::Cluster`, `AWS::EKS::Nodegroup`, `AWS::Events::EventBus`, `AWS::Events::Rule`, `AWS::Kinesis::Stream`, `AWS::KinesisFirehose::DeliveryStream`, `AWS::Lambda::EventSourceMapping`, `AWS::Lambda::Function`, `AWS::Lambda::LayerVersion`, `AWS::StepFunctions::StateMachine` |
| `observability_translation` | `AWS::CloudTrail::Trail`, `AWS::CloudWatch::Alarm`, `AWS::CloudWatch::Dashboard`, `AWS::Logs::LogGroup`, `AWS::Logs::LogStream`, `AWS::Logs::SubscriptionFilter`, `AWS::SNS::Subscription`, `AWS::SNS::Topic`, `AWS::SQS::Queue`, `AWS::SQS::QueuePolicy` |
| `cfn_terraform` | `AWS::CloudFormation::Stack`, `AWS::CloudFront::Distribution` |
| `data_migration_planning` | _(consumes skill outputs / assessment context)_ |
| `synthesis` | _(consumes skill outputs / assessment context)_ |
| `workload_planning` | _(consumes skill outputs / assessment context)_ |
| `dependency_discovery` | _(consumes skill outputs / assessment context)_ |

**Known AWS types** (97 total): `AWS::ApiGateway::RestApi`, `AWS::ApiGateway::Stage`, `AWS::ApiGatewayV2::Api`, `AWS::AutoScaling::AutoScalingGroup`, `AWS::AutoScaling::LaunchConfiguration`, `AWS::CertificateManager::Certificate`, `AWS::CloudFormation::Stack`, `AWS::CloudFront::Distribution`, `AWS::CloudTrail::Trail`, `AWS::CloudWatch::Alarm`, `AWS::CloudWatch::Dashboard`, `AWS::DAX::Cluster`, `AWS::DirectConnect::Connection`, `AWS::DocDB::DBCluster`, `AWS::DynamoDB::Table`, `AWS::EC2::CustomerGateway`, `AWS::EC2::EIP`, `AWS::EC2::Image`, `AWS::EC2::Instance`, `AWS::EC2::InternetGateway`, `AWS::EC2::KeyPair`, `AWS::EC2::LaunchTemplate`, `AWS::EC2::NatGateway`, `AWS::EC2::NetworkAcl`, `AWS::EC2::NetworkInterface`, `AWS::EC2::RouteTable`, `AWS::EC2::SecurityGroup`, `AWS::EC2::Snapshot`, `AWS::EC2::SpotFleet`, `AWS::EC2::Subnet`, `AWS::EC2::TransitGateway`, `AWS::EC2::TransitGatewayAttachment`, `AWS::EC2::TransitGatewayRouteTable`, `AWS::EC2::VPC`, `AWS::EC2::VPCEndpoint`, `AWS::EC2::VPCPeeringConnection`, `AWS::EC2::VPNConnection`, `AWS::EC2::VPNGateway`, `AWS::EC2::Volume`, `AWS::EC2::VolumeAttachment`, `AWS::ECR::Repository`, `AWS::ECS::Cluster`, `AWS::ECS::Service`, `AWS::ECS::TaskDefinition`, `AWS::EFS::AccessPoint`, `AWS::EFS::FileSystem`, `AWS::EFS::MountTarget`, `AWS::EKS::Cluster`, `AWS::EKS::Nodegroup`, `AWS::ElastiCache::CacheCluster`, `AWS::ElastiCache::ReplicationGroup`, `AWS::ElasticLoadBalancing::LoadBalancer`, `AWS::ElasticLoadBalancingV2::Listener`, `AWS::ElasticLoadBalancingV2::LoadBalancer`, `AWS::ElasticLoadBalancingV2::TargetGroup`, `AWS::Events::EventBus`, `AWS::Events::Rule`, `AWS::FSx::FileSystem`, `AWS::IAM::AccessKey`, `AWS::IAM::Group`, `AWS::IAM::InstanceProfile`, `AWS::IAM::Policy`, `AWS::IAM::Role`, `AWS::IAM::User`, `AWS::KMS::Alias`, `AWS::KMS::Key`, `AWS::Kinesis::Stream`, `AWS::KinesisFirehose::DeliveryStream`, `AWS::Lambda::EventSourceMapping`, `AWS::Lambda::Function`, `AWS::Lambda::LayerVersion`, `AWS::Logs::LogGroup`, `AWS::Logs::LogStream`, `AWS::Logs::SubscriptionFilter`, `AWS::MSK::Cluster`, `AWS::Neptune::DBCluster`, `AWS::OpenSearchService::Domain`, `AWS::RDS::DBCluster`, `AWS::RDS::DBInstance`, `AWS::RDS::DBParameterGroup`, `AWS::RDS::DBSubnetGroup`, `AWS::Redshift::Cluster`, `AWS::Route53::HostedZone`, `AWS::Route53::RecordSet`, `AWS::S3::Bucket`, `AWS::S3::BucketPolicy`, `AWS::SNS::Subscription`, `AWS::SNS::Topic`, `AWS::SQS::Queue`, `AWS::SQS::QueuePolicy`, `AWS::SSM::Parameter`, `AWS::SecretsManager::RotationSchedule`, `AWS::SecretsManager::Secret`, `AWS::StepFunctions::StateMachine`, `AWS::Timestream::Database`, `AWS::WAFv2::IPSet`, `AWS::WAFv2::WebACL`

Anything else in a migration inventory (e.g., `AWS::Lambda::Function`, `AWS::DynamoDB::Table`, `AWS::SNS::Topic`) is flagged as **unknown / gap** — the run completes but those resources need manual migration or a new skill to handle them.
<!-- END AUTO-GENERATED REGISTRY -->

---

## Security posture

### What agents can do
- Call the tools registered below — nothing else.
- Read from the mapping YAML, the `resources` table, and a tmpdir during
  `terraform_validate`.

### What agents explicitly cannot do
- **Spoof migration scope.** Orchestrator tools read `migration_id` from
  `RunContextWrapper[MigrationContext]`, not from LLM-supplied arguments.
- **Break out of the terraform sandbox.** `terraform_validate` wraps every
  subprocess in `bwrap --unshare-all --cap-drop ALL --clearenv`, with
  read-only binds for `/usr /lib /bin /etc/ssl` and a writable scope of
  the temp dir only. All capabilities are dropped. The sandbox dies with
  the parent.
- **Exfiltrate via observability.** The openai-agents SDK's tracing is
  disabled (`set_tracing_disabled(True)` in `app.agents.config`); no data
  leaves the internal network to `platform.openai.com`.
- **Mutate AWS or OCI state.** No `write` / `apply` / `delete` tools are
  registered. Adding one requires a human-in-loop confirmation step —
  don't ship it without that.

### What the gateway egress still allows
- `terraform init` downloads the `hashicorp/oci` provider — the sandbox
  re-shares the net namespace for that one call. In production, restrict
  egress at the host / sidecar firewall to allowlist only
  `registry.terraform.io`, `*.oci.oraclecloud.com`, `*.amazonaws.com`, and
  the Llama Stack host.

---

## Extension checklist — adding a new tool

1. Define the `@function_tool` function in
   [`backend/app/agents/tools.py`](../backend/app/agents/tools.py).
2. Register its metadata in `TOOL_REGISTRY` in
   [`backend/app/agents/registry.py`](../backend/app/agents/registry.py).
3. Attach it to the writer / reviewer agent(s) that should have it in
   [`backend/app/agents/skill_group.py`](../backend/app/agents/skill_group.py) `_build_writer` / `_build_reviewer`.
4. Re-run `python3 scripts/render_agent_docs.py` to update this file.

## Extension checklist — adding a new skill group

1. Add a `SkillSpec` entry to `SKILL_SPECS` in `skill_group.py`.
2. Place it in the correct wave in `DEPENDENCY_WAVES` in `orchestrator.py`.
3. Teach `_build_input_for()` how to turn resources into the skill's
   expected input shape.
4. Add an entry to `ORCHESTRATOR_WORKFLOW["resource_routing"]` in
   `registry.py` so the docs reflect which AWS types the skill handles.
5. Create `backend/app/skills/<skill_type>/workflows/*.md` for the
   domain-specific prose rules the writer and reviewer will read.
