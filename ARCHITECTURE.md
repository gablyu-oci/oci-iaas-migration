# Architecture

This document describes how the codebase is structured and how the components interact.

---

## System diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Browser                                                                    │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │  REST / SSE (HTTP)
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Frontend  (React + Vite, port 5173)                                        │
│                                                                             │
│  Pages: Login · Dashboard · Migrations · MigrationDetail · MigrationPlan   │
│          Resources · TranslationJobNew · TranslationJobProgress             │
│          TranslationJobResults · WorkloadDetail                             │
│                                                                             │
│  Components: ResourceTable · SkillProgressTracker · ArtifactViewer         │
│              DependencyGraph                                                │
│                                                                             │
│  API layer: Axios client (JWT interceptor) + TanStack Query hooks           │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │  REST + SSE
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Backend API  (FastAPI + Uvicorn, port 8001)                                │
│                                                                             │
│  api/auth.py      POST /api/auth/register · /login                         │
│  api/aws.py       AWS connections · migrations · resource extraction        │
│  api/jobs.py      Translation jobs · SSE stream · artifacts                 │
│  api/plans.py     Migration plan generation · phase/workload CRUD           │
│  api/rag.py       Service & IAM mapping lookups                             │
│  api/deps.py      JWT auth dependency (get_current_tenant)                  │
└──────┬──────────────────────┬────────────────────────┬───────────────────────┘
       │                      │                        │
       ▼                      ▼                        ▼
┌─────────────┐   ┌───────────────────────┐   ┌──────────────────────────────┐
│ PostgreSQL  │   │  services/            │   │  Redis  (optional)           │
│  port 5432  │   │                       │   │  port 6379                   │
│             │   │  auth_service.py      │   │                              │
│  13 tables  │   │  aws_extractor.py     │   │  ARQ job queue               │
│  (see data  │   │  migration_           │   │  (fallback: child process)   │
│   model)    │   │    orchestrator.py    │   └──────────────┬───────────────┘
└─────────────┘   │  job_runner.py        │                  │
                  └──────────┬────────────┘                  │
                             │  routes job to skill          │
                             ▼                               ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  skills/  (Translation Orchestrators)                        │
              │                                                              │
              │  network_translation    VPC/Subnet/SG/ENI → OCI VCN         │
              │  ec2_translation        EC2/ASG → OCI Compute                │
              │  storage_translation    EBS → OCI Block Volume               │
              │  database_translation   RDS → OCI Database                   │
              │  loadbalancer_trans.    ALB/NLB → OCI LB                     │
              │  cfn_terraform          CloudFormation → Terraform            │
              │  iam_translation        IAM → OCI IAM                        │
              │  dependency_discovery   Flow logs → dependency graph          │
              │                                                              │
              │  shared/base_orchestrator.py   ← Enhancement→Review→Fix loop│
              │  shared/agent_logger.py        ← session & cost tracking     │
              │  shared/rag.py                 ← RAG lookup helper           │
              └──────────────────────────┬───────────────────────────────────┘
                                         │  LLM calls
                                         ▼
              ┌──────────────────────────────────────────────────────────────┐
              │  gateway/                                                    │
              │                                                              │
              │  model_gateway.py                                            │
              │    get_anthropic_client()  API key → OAuth fallback          │
              │    get_model()             skill + agent type → model name   │
              │    guard_input()           calls guardrails.check_input()    │
              │    guard_output()          calls guardrails.check_output()   │
              │                                                              │
              │  guardrails.py                                               │
              │    check_input()   token budget · prompt injection · secret  │
              │                   scrubbing (AKIA*, account IDs, OCIDs) ·   │
              │                   PII detection (email, phone, SSN)          │
              │    check_output()  OCI type validation · compliance flags    │
              │                   (overly broad IAM, public ports,           │
              │                   unencrypted storage) · AWS leak detection  │
              │                                                              │
              │  agent_adapter.py                                            │
              │    AgentSDKClient  wraps claude_agent_sdk (OAuth) in the     │
              │    same interface as anthropic.Anthropic() so orchestrators  │
              │    need no auth-specific branching                           │
              └──────────────────────────┬───────────────────────────────────┘
                                         │
                              ┌──────────┴──────────┐
                              ▼                     ▼
                   ┌─────────────────┐   ┌─────────────────────┐
                   │  Anthropic API  │   │  Claude Code OAuth  │
                   │  (API key)      │   │  (agent_adapter)    │
                   └─────────────────┘   └─────────────────────┘
```

---

## Component reference

### Frontend (`frontend/src/`)

| Path | Purpose |
|---|---|
| `App.tsx` | React Router layout, protected route wrapper |
| `api/client.ts` | Axios instance with JWT auth interceptor |
| `api/hooks/` | TanStack Query hooks — `useMigrations`, `useResources`, `useTranslationJobs`, `usePlans` |
| `pages/Dashboard.tsx` | Overview: migration count, recent jobs, cost summary |
| `pages/Migrations.tsx` | Migration list |
| `pages/MigrationDetail.tsx` | Resources, extraction controls, run translation jobs |
| `pages/MigrationPlan.tsx` | Phased plan viewer, per-workload job launcher |
| `pages/Resources.tsx` | Resource browser across all migrations |
| `pages/TranslationJobNew.tsx` | Manual job creation (pick skill, paste input) |
| `pages/TranslationJobProgress.tsx` | Live SSE progress view |
| `pages/TranslationJobResults.tsx` | Final results, artifacts, dependency graph |
| `pages/WorkloadDetail.tsx` | Single workload: resources, linked job, artifacts |
| `components/ResourceTable.tsx` | Sortable/filterable resource list with bulk job actions |
| `components/SkillProgressTracker.tsx` | SSE-driven live phase/iteration/confidence display |
| `components/ArtifactViewer.tsx` | Artifact list with inline Markdown/Terraform preview |
| `components/DependencyGraph.tsx` | ReactFlow canvas for `.mmd`/`.dot` dependency graphs |

### Backend API (`backend/app/api/`)

| File | Routes |
|---|---|
| `auth.py` | `POST /api/auth/register`, `POST /api/auth/login` |
| `aws.py` | `POST/GET /api/aws/connections`, `POST/GET /api/migrations`, `POST /api/migrations/{id}/extract`, `POST /api/migrations/{id}/extract/instance`, `GET /api/aws/resources` |
| `jobs.py` | `POST/GET /api/translation-jobs`, `GET /api/translation-jobs/{id}`, `GET /api/translation-jobs/{id}/stream` (SSE), `GET /api/translation-jobs/{id}/artifacts`, `GET /api/artifacts/{id}/download`, `DELETE /api/translation-jobs/{id}` |
| `plans.py` | `POST /api/migrations/{id}/plan`, `GET /api/migrations/{id}/plan`, `POST /api/workloads/{id}/run` |
| `rag.py` | `GET /api/rag/service-mappings`, `GET /api/rag/iam-mappings` |
| `deps.py` | `get_current_tenant()` — JWT decode + tenant lookup |

### Services (`backend/app/services/`)

| File | Purpose |
|---|---|
| `auth_service.py` | bcrypt password hashing, JWT creation and decode |
| `aws_extractor.py` | boto3: extract EC2, VPC, subnets, SGs, ENIs, EBS volumes, RDS, ALB/NLB, ASG, Lambda, CloudFormation, IAM. Validates credentials via `sts.get_caller_identity()`. |
| `migration_orchestrator.py` | Generates `MigrationPlan` by grouping `Resource` rows into dependency-ordered phases and workloads |
| `job_runner.py` | ARQ worker task `run_translation_job()`: loads job from DB, builds composite input JSON for aggregated skills, routes to skill orchestrator, stores artifacts, updates status |

### Skills (`backend/app/skills/`)

Each skill is a directory with an `orchestrator.py` that subclasses `BaseTranslationOrchestrator`.

| Skill | Input shape | Output |
|---|---|---|
| `network_translation` | `{vpc_id, subnets, security_groups, network_interfaces, ...}` | `main.tf`, `variables.tf`, `outputs.tf`, migration guide |
| `ec2_translation` | `{instances, auto_scaling_groups}` | Terraform Compute resources |
| `storage_translation` | `{volumes}` | `oci_core_volume` + `oci_core_volume_attachment` |
| `database_translation` | `{db_instances}` | OCI DB system Terraform |
| `loadbalancer_translation` | `{load_balancers}` | OCI LB Terraform |
| `cfn_terraform` | CloudFormation YAML/JSON string | OCI Terraform modules |
| `iam_translation` | IAM policy document JSON | OCI IAM policy statements |
| `dependency_discovery` | CloudTrail + VPC flow log content | Dependency graph (`.mmd`, `.dot`) + runbook |

**`shared/base_orchestrator.py`** — common Enhancement → Review → Fix loop used by all skills above:
- Calls `guard_input()` before every LLM call
- Calls `guard_output()` after every LLM response (log only, non-blocking)
- Retries JSON parse failures up to 3 times per agent call
- Runs `terraform validate` on output artifacts if `terraform` is installed
- Returns `{artifacts, confidence, decision, iterations, cost, interactions}`

**`shared/agent_logger.py`** — records every agent call (type, model, tokens, cost, decision) into a session log; produces `ORCHESTRATION-SUMMARY.md` artifact.

**`shared/rag.py`** — queries `service_mappings` and `iam_mappings` tables via ILIKE for orchestrator prompts.

### Gateway (`backend/app/gateway/`)

| File | Purpose |
|---|---|
| `model_gateway.py` | `get_anthropic_client()`: returns `anthropic.Anthropic(api_key=...)` or `AgentSDKClient()`. `get_model(skill, agent)`: looks up model from routing table. `guard_input()` / `guard_output()`: thin wrappers over guardrails. |
| `guardrails.py` | `check_input()`: token budget (200k char limit), prompt injection detection, secret scrubbing (AWS keys, account IDs, OCIDs, generic `password=` patterns), PII warnings. `check_output()`: OCI resource type validation against known-valid set, compliance flags (overly-broad IAM, public port exposure, unencrypted storage), AWS resource leak detection. |
| `agent_adapter.py` | `AgentSDKClient`: wraps `claude_agent_sdk.query()` (Claude Code OAuth) in an `anthropic.Anthropic`-compatible interface. Runs each call in an isolated thread with its own event loop. |

**Model routing:**

| Skill | Enhancement | Review | Fix |
|---|---|---|---|
| `cfn_terraform` | Opus 4.6 | Opus 4.6 | Opus 4.6 |
| `iam_translation` | Opus 4.6 | Opus 4.6 | Opus 4.6 |
| `network_translation` | Opus 4.6 | Sonnet 4.6 | Sonnet 4.6 |
| `ec2_translation` | Opus 4.6 | Sonnet 4.6 | Sonnet 4.6 |
| `storage_translation` | Opus 4.6 | Sonnet 4.6 | Sonnet 4.6 |
| `database_translation` | Opus 4.6 | Sonnet 4.6 | Sonnet 4.6 |
| `loadbalancer_translation` | Opus 4.6 | Sonnet 4.6 | Sonnet 4.6 |
| `dependency_discovery` | Opus 4.6 (runbook) | Sonnet 4.6 (anomalies) | — |

### RAG (`backend/app/rag/`)

`search.py` — ILIKE keyword queries against two reference tables:

- `service_mappings`: AWS resource type → OCI Terraform resource type + notes
- `iam_mappings`: AWS IAM action → OCI permission verb

Seeded by `scripts/seed_rag.py` from `backend/data/seeds/`.

---

## Data model

```
Tenant ──< AWSConnection
Tenant ──< Migration ──< Resource
                    └──  MigrationPlan ──< PlanPhase ──< Workload ──< WorkloadResource
                                                                           │
                                                                           └──> Resource
Tenant ──< TranslationJob ──< TranslationJobInteraction
                          ──< Artifact
ServiceMapping  (RAG)
IAMMapping      (RAG)
```

Every table has a `tenant_id` — all queries are scoped to the authenticated tenant.

| Table | Purpose |
|---|---|
| `tenants` | One row per registered account |
| `aws_connections` | AWS credentials + region (plaintext — encrypt for production) |
| `migrations` | Migration project grouping resources under one AWS connection |
| `resources` | Individual AWS resources; `raw_config` JSONB stores full resource details |
| `migration_plans` | One plan per migration; `summary` JSONB with total resource counts |
| `plan_phases` | Ordered phases within a plan (Networking → Data → Application → ...) |
| `workloads` | Resource group within a phase; carries `skill_type` and optional `translation_job_id` |
| `workload_resources` | Join table: workload ↔ resource (many-to-many) |
| `translation_jobs` | One job per skill execution: status, phase, confidence, cost, config |
| `translation_job_interactions` | Per-agent-call log: model, tokens, cost, decision, confidence |
| `artifacts` | Output files as `bytea` blobs (`.tf`, `.md`, `.json`, `.mmd`) |
| `service_mappings` | RAG: AWS resource type → OCI Terraform resource |
| `iam_mappings` | RAG: AWS IAM action → OCI permission verb |

---

## Request flow: running a translation job

```
1. POST /api/translation-jobs
   ├── Validates skill_type is in allowed set
   ├── Creates TranslationJob row (status = "queued")
   └── Calls _enqueue_or_run(job_id)
         ├── Try: enqueue via ARQ → Redis
         └── Fallback: spawn child process (os.setpgrp() for clean kill)

2. job_runner.run_translation_job(ctx, job_id)
   ├── Load TranslationJob from DB, set status = "running"
   ├── Build input_content:
   │     ├── Aggregated skills (network/ec2/storage/database/lb): load all
   │     │   resource IDs from job.config["resource_ids"] + input_resource_id,
   │     │   call skill-specific builder (_build_network_input, etc.)
   │     └── Single-resource skills (cfn/iam): use resource.raw_config
   ├── Route to skill orchestrator
   ├── Store artifacts + interaction records in DB
   └── Set status = "complete" / "failed"

3. GET /api/translation-jobs/{id}/stream  (SSE)
   └── Polls translation_job row every 1s
       └── Yields {status, phase, iteration, confidence, new_interactions}
           until status = "complete" or "failed"
```

---

## Skill orchestration loop

```
Input JSON (AWS resource config)
        │
        ▼
  guard_input()          ← token budget, injection check, secret scrub
        │
        ▼
  run_gap_analysis()     ← deterministic count of resources, types, complexity
        │
        ▼
  ┌─────────────────────────────────────────────┐
  │  for iteration in 1 .. max_iterations (3)   │
  │                                             │
  │  Enhancement agent (Opus 4.6)               │
  │    ← translate / improve current output     │
  │    → guard_output() (log only)              │
  │                                             │
  │  Review agent (Sonnet 4.6)                  │
  │    ← score issues by severity               │
  │    → APPROVED / APPROVED_WITH_NOTES /       │
  │      NEEDS_FIXES + confidence score         │
  │    → guard_output() (log only)              │
  │                                             │
  │  if APPROVED* → exit loop                   │
  │                                             │
  │  Fix agent (Opus 4.6)                       │
  │    ← target CRITICAL + HIGH issues only     │
  │    → guard_output() (log only)              │
  └─────────────────────────────────────────────┘
        │
        ▼
  Confidence thresholds:
    APPROVED            ≥ 0.85, no CRITICAL/HIGH
    APPROVED_WITH_NOTES  0.65–0.85, no CRITICAL
    NEEDS_FIXES         < 0.65 or any CRITICAL/HIGH
        │
        ▼
  terraform validate (if terraform is installed)
        │
        ▼
  Artifacts: main.tf · variables.tf · outputs.tf · tfvars.example
             summary.json · <skill>-translation.md · ORCHESTRATION-SUMMARY.md
```

---

## Directory structure

```
oci-migration-tool/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app factory, CORS, lifespan
│   │   ├── config.py                  # Settings loaded from .env (pydantic-settings)
│   │   ├── api/
│   │   │   ├── auth.py                # Register / login
│   │   │   ├── aws.py                 # AWS connections, migrations, extraction
│   │   │   ├── jobs.py                # Translation jobs, SSE, artifacts
│   │   │   ├── plans.py               # Migration plan generation and retrieval
│   │   │   ├── rag.py                 # Service/IAM mapping search
│   │   │   └── deps.py                # JWT auth dependency
│   │   ├── db/
│   │   │   ├── base.py                # Async SQLAlchemy engine + session factory
│   │   │   └── models.py              # All ORM models (13 tables)
│   │   ├── gateway/
│   │   │   ├── model_gateway.py       # Client factory, model routing, guardrail wrappers
│   │   │   ├── guardrails.py          # Input + output guardrails
│   │   │   └── agent_adapter.py       # Claude Code OAuth adapter
│   │   ├── services/
│   │   │   ├── auth_service.py        # bcrypt + JWT
│   │   │   ├── aws_extractor.py       # boto3 resource extraction (all types)
│   │   │   ├── migration_orchestrator.py  # Plan generation logic
│   │   │   └── job_runner.py          # ARQ worker task
│   │   ├── skills/
│   │   │   ├── shared/
│   │   │   │   ├── base_orchestrator.py   # Enhancement→Review→Fix base class
│   │   │   │   ├── agent_logger.py        # Session + cost logger
│   │   │   │   ├── rag.py                 # RAG lookup helper
│   │   │   │   ├── session_tracker.py     # Token/cost accumulator
│   │   │   │   └── doc_loader.py          # Reference doc path resolver
│   │   │   ├── network_translation/
│   │   │   ├── ec2_translation/
│   │   │   ├── storage_translation/
│   │   │   ├── database_translation/
│   │   │   ├── loadbalancer_translation/
│   │   │   ├── cfn_terraform/
│   │   │   ├── iam_translation/
│   │   │   └── dependency_discovery/
│   │   └── rag/
│   │       └── search.py              # ILIKE keyword search over reference tables
│   ├── alembic/                       # DB migration scripts
│   └── data/seeds/
│       ├── service_mappings.json      # AWS → OCI service/resource mappings
│       └── iam_mappings.json          # AWS IAM action → OCI permission verb
├── frontend/
│   └── src/
│       ├── App.tsx                    # Router + layout + auth guard
│       ├── api/
│       │   ├── client.ts              # Axios + JWT interceptor
│       │   └── hooks/                 # TanStack Query hooks
│       ├── components/                # Shared UI components
│       └── pages/                     # Route-level page components
├── scripts/
│   └── seed_rag.py                    # Loads seed files into DB
└── design-docs/                       # Architecture diagrams + planning notes
```

---

## Known limitations (MVP)

| Area | Current state | Production fix |
|---|---|---|
| AWS credentials | Stored as plaintext in DB | Encrypt with Fernet / use AWS Secrets Manager |
| Artifact storage | `bytea` blobs in PostgreSQL | Move to object storage (OCI Object Storage / S3) |
| RAG search | Keyword ILIKE | pgvector + sentence-transformers for semantic search |
| Output guardrail | Logs only, non-blocking | Block or quarantine non-compliant output |
| CloudTrail/flow logs | File upload only | Live polling via CloudWatch Logs Insights / Athena |
| Terraform validation | Best-effort local `terraform validate` | Sandbox container with OCI provider initialized |
| Redis | Optional | Required for production job queue isolation and retry |
