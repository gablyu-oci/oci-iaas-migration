# Gap Analysis: EC2 → Full Migration Plan
_Last updated: 2026-03-18_

## Goal

Given an EC2 instance, auto-discover all connected underlying resources, translate each to its OCI equivalent, and produce a structured migration plan with phases and workloads — all without actually provisioning anything on OCI yet (plan + review output only).

---

## Where We Are vs. Where We Want to Be

### Current State (MVP)
The system works for **single-resource, manually-triggered skills**:
- **Extract** → CloudFormation stacks and IAM policies only
- **Translate** → CFN template or IAM policy JSON, one at a time, user-selected
- **Discover** → CloudTrail file upload, produces a dependency graph + runbook

### Target State
Given one EC2 instance → auto-discover everything connected → translate all of it → structured migration plan with phases and workloads.

---

## Gap Analysis by Layer

### 1. Resource Discovery — Biggest Gap

`ec2.describe_instances()` is not called anywhere. The extractor only does `cfn.list_stacks()` + `iam.list_policies()`.

**Needed — a full AWS resource inventory via boto3:**

| Resource | boto3 call | Why needed |
|---|---|---|
| EC2 instances | `ec2.describe_instances()` | Starting point of the whole flow |
| VPC / Subnets | `ec2.describe_vpcs()`, `describe_subnets()` | Network topology |
| Security Groups | `ec2.describe_security_groups()` | Firewall rules → OCI NSGs |
| ELB / ALB / NLB | `elbv2.describe_load_balancers()` | Traffic routing |
| Auto Scaling Groups | `autoscaling.describe_auto_scaling_groups()` | Compute scaling |
| RDS instances | `rds.describe_db_instances()` | Databases |
| EKS clusters | `eks.list_clusters()` | Containers |
| Lambda functions | `lambda.list_functions()` | Serverless |
| Target Groups | `elbv2.describe_target_groups()` | Links ELB → EC2 |
| Route Tables | `ec2.describe_route_tables()` | Network routing |
| Internet / NAT Gateways | `ec2.describe_internet_gateways()` | Egress/ingress |
| Secrets Manager | `secretsmanager.list_secrets()` | Credentials management |
| CloudWatch Alarms | `cloudwatch.describe_alarms()` | Observability |

This is the foundation everything else depends on. Without it the system is blind to what actually runs on the instance.

---

### 2. Connected Resource Tracing — Medium Gap

Once you have an EC2 instance's VPC, subnet, security groups, and IAM role, you can follow the graph:
- Security group → find other instances that share it → same tier
- IAM role → find what APIs it calls → dependencies
- Target group → find which ELB it's behind
- Subnet → find what RDS instances share the same subnet

**Currently:** Only CloudTrail upload traces this.
**Needed:** An active graph-building step that calls the SDK in-flight, starting from one EC2 instance and following edges outward to produce a complete connected-resource inventory.

---

### 3. Translation Skills — Major Gap

**Implemented:**
- CloudFormation template → Terraform HCL ✅
- IAM policy → OCI IAM statements ✅

**Missing — each needs a new orchestrator following the Enhancement → Review → Fix pattern:**

| AWS Resource | Target OCI Resource | Skill Needed |
|---|---|---|
| EC2 Instance + EBS | `oci_core_instance` + `oci_core_volume` | `ec2_translation` |
| VPC + Subnets + Route Tables | `oci_core_vcn` + `oci_core_subnet` | `network_translation` |
| Security Groups | `oci_core_network_security_group` | part of `network_translation` |
| RDS PostgreSQL | `oci_database_db_system` / `oci_mysql_mysql_db_system` | `database_translation` |
| ALB / NLB | `oci_load_balancer_load_balancer` | `loadbalancer_translation` |
| Auto Scaling Group | `oci_autoscaling_auto_scaling_configuration` | part of `ec2_translation` |
| Lambda | `oci_functions_function` | `serverless_translation` |
| EKS | `oci_containerengine_cluster` | `kubernetes_translation` |
| CloudWatch | OCI Monitoring / Logging Analytics | `observability_translation` |
| Route 53 | OCI DNS | part of `network_translation` |

---

### 4. Migration Plan Data Model — Not Implemented

**Current schema is flat:** `Migration → Resources → SkillRuns`

**Needed:**
```
Migration
└── MigrationPlan
    ├── Phase 1: "Networking Foundation"
    │   ├── Workload: VPC + Subnets + Security Groups
    │   └── SkillRuns (network_translation) → Artifacts
    ├── Phase 2: "Data Layer"
    │   ├── Workload: RDS PostgreSQL cluster (3 instances)
    │   └── SkillRuns (database_translation) → Artifacts
    └── Phase 3: "Application Layer"
        ├── Workload: Web App (3 EC2s + ALB + ASG)
        └── SkillRuns (ec2_translation + loadbalancer_translation) → Artifacts
```

**New DB tables needed:** `migration_plans`, `plan_phases`, `workloads`, `workload_resources`

---

### 5. App-Level Orchestration Layer — Not Implemented

**Currently:** Each skill has its own internal Enhancement → Review → Fix loop, but there is no app-level orchestrator that decides: _"given these resources, run network_translation first, then database_translation, then ec2_translation."_

**Needed:** A top-level orchestrator that:
1. Takes a workload's resources as input
2. Determines the right skill(s) to run in the right order based on resource types
3. Feeds outputs from one skill as context to the next (e.g., VCN OCID from `network_translation` → input to `ec2_translation`)
4. Tracks plan-level progress and confidence

---

### 6. Guardrails — Not Implemented

The architecture diagram shows input + output guardrails around every LLM call. Currently:
- **Input:** Only `scrub_secrets()` regex in `model_gateway.py` (masks AWS key IDs, account IDs, OCIDs)
- **Output:** Nothing — raw LLM response goes straight to the parser

**What guardrails should cover:**

| Layer | Checks |
|---|---|
| Input guardrail | PII detection, credential scrubbing, injection prevention, max token budget enforcement |
| Output guardrail | Schema validation (is the JSON valid Terraform?), hallucination detection (did the LLM invent OCI resource types that don't exist?), compliance flags (e.g., output grants `manage all-resources in tenancy`) |

---

### 7. Infrastructure Tooling Gaps

| Tool | Current State | Recommendation |
|---|---|---|
| **Redis** | Optional, falls back to threads | Make required. Fallback is fragile — FastAPI restart loses in-flight jobs |
| **Embeddings / pgvector** | In place, used for IAM translation | Keep and expand. Useful for cross-skill semantic retrieval as more skills are added |
| **Input guardrails** | Thin regex scrub only | Build proper middleware: PII detection + token budget enforcement |
| **Output guardrails** | None | Validate against OCI resource schemas; catch hallucinated Terraform resource types |
| **Terraform validation** | Artifacts labeled "unvalidated" | Add `terraform validate` gate on cfn_terraform artifacts |
| **Alembic migrations** | Unused (schema auto-created by SQLAlchemy) | Run Alembic so there is a migration history before schema changes |
| **Object storage for artifacts** | DB BYTEA blobs | Replace with S3/OCI Object Storage for large Terraform + graph files |
| **Credential encryption** | Plaintext JSONB | Fernet encryption before production |
| **Model routing** | All hardcoded to Opus 4.6 | Use Sonnet for review/fix passes; Opus for enhancement only |

---

## Tooling Decisions

| Tool | Decision | Reason |
|---|---|---|
| Redis | Required | Reliable async job queue, job persistence across restarts |
| pgvector + fastembed | Keep | Marginal for IAM alone, valuable once multiple skills use it for cross-resource context retrieval |
| Guardrails | Build custom middleware | Input: scrubbing + budget; Output: schema + compliance |
| Terraform validate | Add as post-processing gate | Users need confidence artifacts will actually apply |
| Object storage | Phase 3 | Not blocking MVP but needed at scale |

---

## Priority Order

### Phase 1 — Foundation (enables the EC2 scenario end-to-end)
1. Full AWS resource extractor (EC2, VPC, SG, RDS, ELB) via boto3
2. `MigrationPlan` data model — plans → phases → workloads
3. `network_translation` skill (VPC → VCN is a prerequisite for compute)
4. `ec2_translation` skill (highest impact single new skill)
5. App-level skill orchestrator (auto-sequence skills by resource type)

### Phase 2 — Completeness
6. `database_translation` skill (RDS → OCI DB System)
7. `loadbalancer_translation` skill
8. Input/output guardrails as middleware layer
9. Redis required + ARQ worker in separate process
10. Terraform validate gate on cfn_terraform artifacts

### Phase 3 — Production-grade
11. Object storage for artifacts (replace DB BYTEA)
12. Credential encryption (Fernet)
13. `observability_translation` (CloudWatch → OCI Monitoring)
14. `serverless_translation` (Lambda → Oracle Functions)
15. Dynamic model routing (Sonnet for review/fix, Opus for enhancement only)

---

## Example Target Flow (EC2 Scenario)

**Input:** EC2 instance `i-0abc123` in `us-east-1`

**Step 1 — Discovery:**
```
EC2: i-0abc123 (t3.large, us-east-1a)
  ├── VPC: vpc-0def456
  │   ├── Subnet: subnet-0ghi789 (10.0.1.0/24, us-east-1a)
  │   └── Route Table: rtb-0jkl012 → IGW igw-0mno345
  ├── Security Groups: sg-0pqr678 (inbound 443, 22)
  ├── IAM Role: arn:aws:iam::123456789:role/WebAppRole
  │   └── Policy: allows s3:GetObject, rds:DescribeDBInstances
  ├── EBS Volume: vol-0stu901 (100GB gp3)
  └── Connected via subnet:
      └── RDS: db-web-postgres (PostgreSQL 15, db.r6g.large)
            ├── Multi-AZ: yes
            └── Security Group: sg-0vwx234 (inbound 5432 from sg-0pqr678)
```

**Step 2 — Plan Generation:**
```
Phase 1: Networking
  Workload: VPC + Subnets + Security Groups + Route Tables
  Skill: network_translation
  Output: oci_core_vcn.tf, oci_core_subnet.tf, oci_core_nsg.tf

Phase 2: Data Layer
  Workload: RDS PostgreSQL (+ IAM role)
  Skills: database_translation + iam_translation
  Output: oci_database_db_system.tf, oci_iam_policy.tf

Phase 3: Application Layer
  Workload: EC2 + EBS + Security Group rules
  Skill: ec2_translation
  Output: oci_core_instance.tf, oci_core_volume.tf
```

**Step 3 — User Review:**
- View plan in UI with phase breakdown and confidence scores per phase
- Download all Terraform artifacts as a zip
- Review migration runbook with ordered steps
- Identify gaps and manual steps flagged by the skills

---

## Current Architecture vs. Target Architecture

### What Works Well Today
- Multi-tenant JWT auth with per-tenant data isolation
- Real-time SSE streaming of skill progress
- Iterative LLM Enhancement → Review → Fix loop with confidence scoring
- CloudTrail → dependency graph (deterministic + LLM enriched)
- Wave-based migration planning from dependency discovery
- Token tracking per interaction for cost reporting

### What the Architecture Diagram Calls For That Isn't Built Yet
- **Skill Selection layer** (orchestration decides which skills to run and in what order)
- **Model Gateway** with dynamic routing (currently all hardcoded to Opus 4.6)
- **Guardrails wrapper** (input + output validation around every LLM call)
- **Plan/Phase/Workload** data model and UI
- **Object storage** for TF files and IAM policies (currently DB BYTEA)
