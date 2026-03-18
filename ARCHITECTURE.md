# Architecture

This document explains how the codebase is structured and how the main components interact.

---

## High-level overview

```
Browser
  │
  │  HTTP / SSE
  ▼
Frontend (React + Vite)          port 5173
  │
  │  REST API calls
  ▼
Backend API (FastAPI)            port 8001
  ├── Auth (JWT)
  ├── AWS connections + extraction (boto3)
  ├── Skill run management
  └── Artifact storage
       │
       ├── PostgreSQL            (all state, artifacts as blobs)
       │
       └── Orchestration layer
            ├── IAM Translation orchestrator
            ├── CFN → Terraform orchestrator
            └── Dependency Discovery orchestrator
                 │
                 ▼
            Model Gateway
            ├── scrub_secrets()  (input guardrail)
            ├── Model routing    (Opus for writing, Sonnet for review)
            └── LLM client       (Anthropic API key or Claude Code OAuth)
```

---

## Directory structure

```
backend/
├── app/
│   ├── main.py               # FastAPI app, CORS, lifespan hook
│   ├── config.py             # Settings from .env (pydantic-settings)
│   ├── api/
│   │   ├── auth.py           # POST /api/auth/register, /login
│   │   ├── aws.py            # AWS connections, migrations, extraction, resources
│   │   ├── skills.py         # Skill runs, SSE stream, artifact download
│   │   └── deps.py           # JWT auth dependency (get_current_tenant)
│   ├── db/
│   │   ├── base.py           # Async SQLAlchemy engine, session factory, init_db()
│   │   └── models.py         # All ORM models (9 tables)
│   ├── gateway/
│   │   ├── model_gateway.py  # LLM client factory + model routing + scrub_secrets
│   │   └── agent_adapter.py  # Claude Code OAuth adapter (no API key needed)
│   ├── services/
│   │   ├── auth_service.py   # bcrypt hashing, JWT creation/decode
│   │   ├── aws_extractor.py  # boto3: list CFN stacks, get IAM policies
│   │   └── skill_runner.py   # ARQ worker task: runs a skill job end-to-end
│   ├── skills/
│   │   ├── shared/
│   │   │   ├── agent_logger.py   # Session logger (returns JSON + MD strings)
│   │   │   └── doc_loader.py     # Resolves paths to reference docs
│   │   ├── iam_translation/
│   │   │   ├── orchestrator.py   # Enhancement → Review → Fix loop for IAM
│   │   │   ├── translator.py     # Deterministic gap analysis
│   │   │   ├── workflows/        # Translation rules (markdown)
│   │   │   └── docs/             # 82 crawled OCI reference docs
│   │   ├── cfn_terraform/
│   │   │   ├── orchestrator.py   # Enhancement → Review → Fix loop for CFN
│   │   │   ├── translator.py     # CFN parser + resource detection
│   │   │   ├── workflows/        # Conversion rules (markdown)
│   │   │   └── docs/             # OCI Terraform provider reference docs
│   │   └── dependency_discovery/
│   │       ├── orchestrator.py   # Thin wrapper over src/ package
│   │       └── src/              # CloudTrail parser, graph builder (NetworkX)
│   └── rag/
│       └── search.py         # Keyword ILIKE lookup in service_mappings + iam_mappings
├── data/seeds/
│   ├── service_mappings.json # AWS resource type → OCI Terraform resource
│   └── iam_mappings.json     # AWS IAM action → OCI permission verb
└── scripts/
    └── seed_rag.py           # Loads seed files into DB

frontend/
├── src/
│   ├── App.tsx               # React Router layout + protected routes
│   ├── api/
│   │   ├── client.ts         # Axios instance with JWT interceptor
│   │   └── hooks/            # React Query hooks (useAuth, useConnections, etc.)
│   ├── components/
│   │   ├── SkillProgressTracker.tsx  # SSE-driven live progress display
│   │   ├── ArtifactViewer.tsx        # Artifact list with inline preview + download
│   │   └── DependencyGraph.tsx       # ReactFlow canvas for dependency graphs
│   └── pages/
│       ├── Login.tsx / Register.tsx
│       ├── Dashboard.tsx     # Overview: run counts, recent skill runs
│       ├── Settings.tsx      # AWS connection management
│       ├── Resources.tsx     # Resource browser + "Run Skill" action
│       ├── SkillRunNew.tsx   # Pick skill, paste or select input
│       ├── SkillRunProgress.tsx  # Live SSE view
│       └── SkillRunResults.tsx   # Final results, artifacts, dependency graph
```

---

## Data model

```
Tenant ──< AWSConnection
Tenant ──< Migration ──< Resource
Tenant ──< SkillRun ──< Artifact
                    ──< SkillRunInteraction
ServiceMapping (RAG)
IAMMapping     (RAG)
```

Every table has a `tenant_id` foreign key — all queries are scoped to the authenticated tenant. There is no cross-tenant data access.

**Key tables:**

| Table | Purpose |
|---|---|
| `tenants` | One row per registered user/account |
| `aws_connections` | Stored AWS credentials + region (plaintext — encrypt for production) |
| `migrations` | A migration project grouping multiple resources |
| `resources` | Individual AWS resources extracted from a migration (CFN stacks, IAM policies) |
| `skill_runs` | One row per skill execution: status, phase, confidence, cost |
| `artifacts` | Output files stored as bytea blobs (TF files, JSON policies, markdown guides) |
| `skill_run_interactions` | Per-agent-call log: model, tokens, cost, decision, confidence |
| `service_mappings` | RAG: AWS resource type → OCI Terraform resource type |
| `iam_mappings` | RAG: AWS IAM action → OCI permission verb |

---

## Request flow: running a skill

```
1. POST /api/skill-runs
   - Validates input (JSON or YAML)
   - Creates SkillRun row (status = "queued")
   - Calls _enqueue_or_run()

2. _enqueue_or_run()
   - Tries to push job to Redis (ARQ queue)
   - If Redis unavailable: spawns a background thread and runs directly

3. run_skill_job() [skill_runner.py]
   - Loads SkillRun from DB
   - Sets status = "running"
   - Gets LLM client from model_gateway
   - Routes to the correct orchestrator (cfn_terraform / iam_translation / dependency_discovery)
   - Stores returned artifacts in DB
   - Sets status = "complete" (or "failed")

4. GET /api/skill-runs/{id}/stream
   - SSE endpoint that polls the skill_run row every second
   - Yields status/phase/confidence events until status = "complete" or "failed"
   - Frontend SkillProgressTracker consumes this stream
```

---

## Skill orchestration loop

Each skill follows the same pattern (enhancement → review → fix, max 3 iterations):

```
Input content (policy JSON or CFN YAML)
       │
       ▼
Gap analysis / resource detection   ← deterministic, no LLM
       │
       ▼
┌─────────────────────────────────────┐
│  Iteration 1..3                     │
│                                     │
│  Enhancement agent (Opus)           │
│    └─ Translate / improve output    │
│                                     │
│  Review agent (Sonnet)              │
│    └─ Score issues by severity      │
│    └─ APPROVED / NOTES / NEEDS_FIXES│
│                                     │
│  if APPROVED → exit loop early      │
│  if NEEDS_FIXES → Fix agent (Opus)  │
│    └─ Target only HIGH/CRITICAL     │
└─────────────────────────────────────┘
       │
       ▼
Confidence score + decision
Artifacts (JSON policy / TF files / runbook)
Session log (JSON + Markdown)
```

**Confidence thresholds:**
- `APPROVED` ≥ 0.85, no CRITICAL/HIGH issues
- `APPROVED_WITH_NOTES` 0.65–0.85, no CRITICAL issues
- `NEEDS_FIXES` < 0.65 or any CRITICAL/HIGH issue

---

## Model gateway and auth

`model_gateway.py` is the single point of contact with the LLM. It:

1. **Selects auth method**: API key (from `.env`) → Claude Code OAuth (via `agent_adapter.py`)
2. **Routes models** per skill and agent role:

| Skill | Agent role | Model |
|---|---|---|
| CFN/IAM | Enhancement | `claude-opus-4-6` |
| CFN/IAM | Review | `claude-sonnet-4-6` |
| CFN/IAM | Fix | `claude-opus-4-6` |
| Dependency | Runbook | `claude-opus-4-6` |
| Dependency | Anomalies | `claude-sonnet-4-6` |

3. **Scrubs secrets** from input text before any LLM call: AWS access key patterns, 12-digit account IDs, OCIDs.

**`agent_adapter.py`** is used when no API key is configured. It wraps `claude_agent_sdk.query()` (which authenticates via Claude Code OAuth) in an interface identical to `anthropic.Anthropic()`. Each call runs in an isolated thread with its own event loop so it doesn't conflict with FastAPI's async event loop.

---

## RAG (Reference data lookup)

Two tables act as a lightweight lookup layer the orchestrators can query:

- **`service_mappings`**: Given an AWS resource type like `AWS::S3::Bucket`, returns the OCI Terraform resource (`oci_objectstorage_bucket`) and notes.
- **`iam_mappings`**: Given an AWS IAM action like `s3:GetObject`, returns the OCI permission verb (`read objects`).

Search is implemented as SQL `ILIKE` keyword matching (`rag/search.py`). It works well for exact and near-exact lookups. The design-docs note pgvector semantic search as a future upgrade for fuzzy matching.

---

## AWS extraction

`services/aws_extractor.py` uses boto3 to pull resources from a connected AWS account:

- **CloudFormation**: `list_stacks` → `get_template` for each stack body
- **IAM**: `list_policies` (customer-managed) → `get_policy_version` for the active version document

Credentials are stored in the `aws_connections` table. The extractor validates them with `sts.get_caller_identity()` before saving.

---

## Frontend data flow

```
React Query hooks (useSkillRuns, useConnections, etc.)
  │  axios + JWT header
  ▼
REST API (FastAPI)
  │
  ▼
SkillProgressTracker
  └─ EventSource → GET /api/skill-runs/{id}/stream (SSE)
     └─ polls DB every 1s, yields status events until complete

ArtifactViewer
  └─ GET /api/skill-runs/{id}/artifacts → list
  └─ GET /api/artifacts/{id}/download → file blob

DependencyGraph
  └─ Reads .mmd or .dot artifact, renders with ReactFlow
```

---

## Known limitations (MVP)

| Area | Current state | Production fix |
|---|---|---|
| AWS credentials | Stored as plaintext in DB | Encrypt with Fernet / use AWS Secrets Manager |
| Artifact storage | Bytea blobs in PostgreSQL | Move to object storage (OCI Object Storage / S3) |
| RAG search | Keyword ILIKE | pgvector + sentence-transformers for semantic search |
| Output guardrail | None | Validate/sanitize LLM output before returning to client |
| Skill selection | Manual (user picks) | Orchestration layer that plans skill order automatically |
| CloudTrail/Flow Logs | File upload only | Live SDK polling via CloudWatch Logs Insights / Athena |
| Terraform validation | None | Run `terraform init` + `terraform validate` in a sandbox container |
| Redis | Optional / bypassed | Required for production job queue isolation |
