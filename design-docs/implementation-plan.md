# OCI Migration Tool — Implementation Plan

## Context

Integrating three working CLI-based migration skills (CFN→TF, IAM Translation, Dependency Discovery)
into a multi-tenant FastAPI web platform. Skills already have working writer/reviewer loops,
confidence scoring, and token tracking. The platform wraps them with async job execution, SSE
progress streaming, DB-backed state, and artifact storage.

**Model roles:** Opus = implementer (writer + fix agents), Sonnet = reviewer.

---

## Proposed MVP Requirement Modifications

The following changes from `requirements/mvp.md` are proposed to reduce scope without removing user-visible value:

| Original | Proposed Change | Rationale |
|---|---|---|
| pandas for CloudTrail preprocessing | **Remove** — use existing Python ingestion code | `aws-dependency-discovery/ingestion/` already handles grouping, dedup, relationship extraction with pure Python + NetworkX. No pandas needed. |
| Live CloudTrail via `CloudTrail.lookup_events` | **File upload only** for CloudTrail + Flow Logs | Live CloudWatch Logs Insights/Athena requires customer log group setup, Athena tables, and complex IAM. CFN + IAM live SDK extraction stays. |
| RAG with pgvector + semantic search + sentence-transformers | **Keyword-only lookup** for MVP | Skills already produce quality output with built-in doc loading. Embeddings add infra complexity (model download, pgvector) for marginal MVP gain. Phase 2 upgrade. |
| `terraform init`-able gate | **Remove gate, mark as unvalidated** | Requires a sandboxed Terraform binary container — infra work, not skill work. Label artifacts as "unvalidated" and document local `terraform init` steps. |

---

## Directory Structure

```
oci-migration-tool/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI app, CORS, lifespan
│   │   ├── config.py                   # Pydantic BaseSettings
│   │   ├── api/
│   │   │   ├── deps.py                 # get_db, get_current_tenant
│   │   │   ├── auth.py                 # register, login
│   │   │   ├── aws.py                  # connections, migrations, extraction, resources
│   │   │   └── skills.py              # skill runs, SSE stream, artifact download
│   │   ├── db/
│   │   │   ├── base.py                 # async engine + session factory
│   │   │   └── models.py               # all ORM models
│   │   ├── services/
│   │   │   ├── auth_service.py         # JWT + bcrypt
│   │   │   ├── aws_extractor.py        # boto3 CFN + IAM extraction
│   │   │   └── skill_runner.py         # ARQ worker task
│   │   ├── gateway/
│   │   │   └── model_gateway.py        # model routing + secret scrubbing
│   │   ├── skills/                     # copied + adapted from migration-claude-skills
│   │   │   ├── shared/
│   │   │   │   ├── agent_logger.py     # ADAPTED: no file I/O
│   │   │   │   └── doc_loader.py       # ADAPTED: fix path root
│   │   │   ├── cfn_terraform/
│   │   │   │   ├── orchestrator.py     # ADAPTED: flip models, remove FS, add callback
│   │   │   │   ├── translator.py       # copied as-is
│   │   │   │   ├── workflows/          # copied as-is
│   │   │   │   └── docs/               # copied as-is
│   │   │   ├── iam_translation/
│   │   │   │   ├── orchestrator.py     # ADAPTED: same as CFN
│   │   │   │   ├── translator.py       # copied as-is
│   │   │   │   ├── workflows/          # copied as-is
│   │   │   │   └── docs/               # copied as-is
│   │   │   └── dependency_discovery/
│   │   │       ├── orchestrator.py     # NEW: thin wrapper over src/ package
│   │   │       └── src/                # copied as-is
│   │   └── rag/
│   │       └── search.py               # keyword lookup for service/IAM mappings
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── data/seeds/                     # service_mappings.json, iam_mappings.json
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   ├── client.ts
│   │   │   └── hooks/
│   │   ├── components/
│   │   │   ├── ui/                     # shadcn/ui components
│   │   │   ├── SkillProgressTracker.tsx
│   │   │   ├── DependencyGraph.tsx
│   │   │   └── ArtifactViewer.tsx
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Settings.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Resources.tsx
│   │   │   ├── SkillRunNew.tsx
│   │   │   ├── SkillRunProgress.tsx
│   │   │   └── SkillRunResults.tsx
│   │   └── lib/utils.ts
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
├── scripts/
│   └── seed_rag.py                     # one-time seed for service/IAM mappings
└── docker-compose.yml
```

---

## Phase 1: Database Models

**File:** `backend/app/db/models.py`
All tables carry `tenant_id UUID NOT NULL`. SQLAlchemy 2.0 async + asyncpg. Alembic migrations.

```
tenants
  id UUID PK
  email TEXT UNIQUE NOT NULL
  password_hash TEXT NOT NULL
  created_at TIMESTAMPTZ

aws_connections
  id UUID PK
  tenant_id UUID FK→tenants NOT NULL
  name TEXT
  region TEXT NOT NULL
  credential_type TEXT          -- "key_pair" | "assume_role"
  credentials TEXT NOT NULL     -- plaintext JSON for MVP (encrypt in production)
  status TEXT                   -- "active" | "invalid"
  created_at TIMESTAMPTZ

migrations
  id UUID PK
  tenant_id UUID FK→tenants NOT NULL
  aws_connection_id UUID FK→aws_connections
  name TEXT NOT NULL
  status TEXT                   -- "active" | "completed"
  created_at TIMESTAMPTZ

resources
  id UUID PK
  tenant_id UUID FK→tenants NOT NULL
  migration_id UUID FK→migrations
  aws_connection_id UUID FK→aws_connections
  aws_type TEXT                 -- "AWS::CloudFormation::Stack" | "AWS::IAM::Policy" | "cloudtrail_upload"
  aws_arn TEXT
  name TEXT
  raw_config JSONB
  status TEXT                   -- "discovered" | "migrated"
  created_at TIMESTAMPTZ

skill_runs
  id UUID PK
  tenant_id UUID FK→tenants NOT NULL
  migration_id UUID FK→migrations
  skill_type TEXT               -- "cfn_terraform" | "iam_translation" | "dependency_discovery"
  input_resource_id UUID FK→resources (nullable)
  input_content TEXT            -- raw YAML/JSON or CloudTrail JSON
  config JSONB                  -- {max_iterations, ...}
  status TEXT                   -- "queued" | "running" | "complete" | "failed"
  current_phase TEXT            -- "enhancement" | "review" | "fix"
  current_iteration INT
  confidence FLOAT
  total_cost_usd FLOAT
  output JSONB                  -- final structured result
  errors JSONB
  started_at TIMESTAMPTZ
  completed_at TIMESTAMPTZ
  created_at TIMESTAMPTZ

skill_run_interactions          -- replaces /tmp session_tracker.py
  id UUID PK
  skill_run_id UUID FK→skill_runs NOT NULL
  agent_type TEXT               -- "enhancement" | "review" | "fix"
  model TEXT
  iteration INT
  tokens_input INT
  tokens_output INT
  tokens_cache_read INT
  tokens_cache_write INT
  cost_usd FLOAT
  decision TEXT                 -- "APPROVED" | "APPROVED_WITH_NOTES" | "NEEDS_FIXES"
  confidence FLOAT
  issues JSONB
  duration_seconds FLOAT
  created_at TIMESTAMPTZ

artifacts                       -- bytea storage, MVP
  id UUID PK
  skill_run_id UUID FK→skill_runs NOT NULL
  tenant_id UUID FK→tenants NOT NULL
  file_type TEXT
    -- "terraform_zip" | "terraform_tf" | "iam_json" | "iam_md"
    -- "cfn_md" | "dependency_json" | "dependency_graph_mmd"
    -- "dependency_graph_dot" | "run_report_md"
  file_name TEXT
  content_type TEXT             -- MIME type
  data BYTEA NOT NULL
  created_at TIMESTAMPTZ

service_mappings                -- keyword lookup, no embeddings for MVP
  id SERIAL PK
  aws_service TEXT
  aws_resource_type TEXT
  oci_service TEXT
  oci_resource_type TEXT
  terraform_resource TEXT
  notes TEXT

iam_mappings
  id SERIAL PK
  aws_action TEXT
  aws_service TEXT
  oci_permission TEXT
  oci_service TEXT
  notes TEXT
```

---

## Phase 2: Adapt Skills

### `skills/shared/agent_logger.py`
- Remove all `Path` / file I/O
- `end_session()` → returns `(json_str: str, markdown_str: str)` instead of writing files
- `_write_json_log()` → `_build_json_report()` returns `str`
- `_write_markdown_report()` → `_build_markdown_report()` returns `str`
- Keep unchanged: `AgentType`, `ReviewDecision`, `AgentInteraction`, `OrchestrationSession`, `calculate_cost()`, `ConfidenceCalculator`

### `skills/shared/doc_loader.py`
Single change — fix path root so all relative doc paths still work after the directory moves:
```python
# Before:
PROJECT_ROOT = Path(__file__).parent.parent.resolve()  # → migration-claude-skills/
# After:
SKILLS_ROOT = Path(__file__).parent.parent.resolve()   # → backend/app/skills/
```

### `skills/cfn_terraform/orchestrator.py`
| Change | Detail |
|---|---|
| Model flip | `ENHANCEMENT_MODEL = "claude-opus-4-6"` (was sonnet) |
| | `REVIEW_MODEL = "claude-sonnet-4-6"` (was opus) |
| | `FIX_MODEL = "claude-opus-4-6"` (was sonnet) |
| Remove FS constants | Delete `INPUT_DIR`, `OUTPUT_DIR`, `LOGS_DIR` |
| Remove `write_outputs()` | New `build_artifact_dict()` returns `{"main_tf", "variables_tf", "outputs_tf", "tfvars_example", "summary_json", "report_md"}` |
| Replace subprocess | `from .translator import run_analysis` — direct import |
| New `run()` signature | `run(input_content: str, progress_callback: Callable, anthropic_client, max_iterations=3) → dict` |
| Progress callback | Called on every phase transition: `callback(phase, iteration, confidence, decision)` |
| Remove `sys.exit()` | Raise `ValueError` / `RuntimeError` |
| Remove `main()` | Not needed in API context |

### `skills/iam_translation/orchestrator.py`
Same changes as CFN, plus `load_core_oci_docs()` and `load_service_docs()` resolve paths via updated `doc_loader.py`.

### `skills/dependency_discovery/orchestrator.py` (new file)
Thin wrapper calling existing `src/` modules directly (no Click, no subprocess):
```python
def run(
    input_content: str,          # CloudTrail JSON
    flowlog_content: str | None,
    progress_callback: Callable,
    anthropic_client: anthropic.Anthropic,
) -> dict:
    # 1. Write to tempfile
    # 2. ingest → graph build → classify → report → runbook
    # 3. Return {dependency_json, graph_mmd, graph_dot, runbook_md, report_md}
    # 4. Cleanup tempfile
```
Models: `claude-opus-4-6` for runbook generation, `claude-sonnet-4-6` for anomaly review.

---

## Phase 3: Model Gateway

**File:** `backend/app/gateway/model_gateway.py`

```python
MODEL_ROUTING = {
    "cfn_terraform":         {"enhancement": "claude-opus-4-6", "review": "claude-sonnet-4-6", "fix": "claude-opus-4-6"},
    "iam_translation":       {"enhancement": "claude-opus-4-6", "review": "claude-sonnet-4-6", "fix": "claude-opus-4-6"},
    "dependency_discovery":  {"runbook": "claude-opus-4-6", "anomalies": "claude-sonnet-4-6"},
}

SECRET_PATTERNS = [
    r'AKIA[0-9A-Z]{16}',               # AWS access key ID
    r'(?i)secret.{0,20}[=:]\s*\S+',   # generic secret=
    r'\d{12}',                          # AWS 12-digit account ID
    r'ocid1\.[a-z]+\.[a-z]+\.[a-z-]+\.[a-z0-9]+',  # OCI OCID
]
```

Public API: `scrub_secrets(text) → str`, `get_anthropic_client(api_key) → Anthropic`, `get_model(skill_type, agent_type) → str`

---

## Phase 4: ARQ Worker

**File:** `backend/app/services/skill_runner.py`

```python
async def run_skill_job(ctx, skill_run_id: str):
    # 1. Load SkillRun → set status="running", started_at=now()
    # 2. Load credentials from AWSConnection
    # 3. Build progress_callback:
    #      - UPDATE skill_runs SET current_phase, current_iteration, confidence
    #      - INSERT skill_run_interactions row per LLM call
    # 4. Route to skill orchestrator by skill_type
    # 5. Store artifacts as Artifact rows (bytea)
    # 6. SET status="complete" | "failed"

class WorkerSettings:
    functions = [run_skill_job]
    job_timeout = 300      # hard 5-minute cap
    max_jobs = 10
```

---

## Phase 5: API Endpoints

### Auth — `api/auth.py`
```
POST  /api/auth/register    {email, password}   → {access_token}
POST  /api/auth/login       {email, password}   → {access_token}
```

### AWS + Migrations — `api/aws.py`
```
POST   /api/aws/connections           {name, region, credential_type, credentials}
GET    /api/aws/connections
DELETE /api/aws/connections/{id}

POST   /api/migrations                {name, aws_connection_id}
GET    /api/migrations
GET    /api/migrations/{id}

POST   /api/migrations/{id}/extract   → ARQ job: pull CFN stacks + IAM policies via SDK
POST   /api/migrations/{id}/upload    → accept CloudTrail JSON / Flow Log file upload
GET    /api/aws/resources             ?type=&migration_id=&status=
```

**AWS SDK extraction** (`services/aws_extractor.py`):
- `cfn.list_stacks()` + `cfn.get_template()` per stack → `Resource` rows
- `iam.list_policies(Scope='Local')` + `iam.get_policy_version()` → `Resource` rows
- `sts.get_caller_identity()` → validate credentials on connection creation
- CloudTrail + Flow Logs: file upload only (no live SDK)

### Skill Runs — `api/skills.py`
```
POST  /api/skill-runs                 {skill_type, input_content | input_resource_id, config}
GET   /api/skill-runs                 → list for tenant
GET   /api/skill-runs/{id}           → status + interactions
GET   /api/skill-runs/{id}/stream    → SSE (EventSourceResponse, polls DB every 1s)
GET   /api/skill-runs/{id}/artifacts → list artifacts
GET   /api/artifacts/{id}/download   → stream file as attachment
```

**SSE event payload:**
```json
{
  "phase":        "enhancement | review | fix",
  "iteration":    2,
  "confidence":   0.72,
  "status":       "running | complete | failed",
  "elapsed_secs": 47
}
```

**Input validation:** Before enqueuing, attempt `yaml.safe_load()` or `json.loads()` on `input_content` — return HTTP 422 if not parseable.

---

## Phase 6: Infrastructure

### `backend/app/config.py`
```python
class Settings(BaseSettings):
    DATABASE_URL: str        # postgresql+asyncpg://...
    REDIS_URL: str           # redis://redis:6379
    ANTHROPIC_API_KEY: str
    JWT_SECRET: str
    JWT_EXPIRE_MINUTES: int = 1440
```

### `docker-compose.yml`
```yaml
services:
  postgres:
    image: postgres:16-alpine    # standard postgres, no pgvector needed for MVP
  redis:
    image: redis:7-alpine
  backend:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [postgres, redis]
  arq-worker:
    build: ./backend
    command: arq app.services.skill_runner.WorkerSettings
    env_file: .env
    depends_on: [postgres, redis]
  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    environment:
      VITE_API_URL: http://localhost:8000
```

### `backend/requirements.txt`
```
fastapi>=0.115
uvicorn[standard]
sqlalchemy[asyncio]>=2.0
asyncpg
alembic
arq
redis
sse-starlette
python-jose[cryptography]
passlib[bcrypt]
boto3
anthropic>=0.40.0
networkx>=3.0
pyyaml
python-dotenv
pydantic-settings
# Phase 2: pandas, sentence-transformers, pgvector
```

---

## Phase 7: RAG / Lookup

**File:** `backend/app/rag/search.py` — keyword-only for MVP.

Seed script `scripts/seed_rag.py` loads `data/seeds/service_mappings.json` and `iam_mappings.json` once.

```python
async def search_service_mappings(aws_service: str, aws_resource_type: str, db) → list[ServiceMapping]:
    # ILIKE match on aws_service + aws_resource_type

async def lookup_iam_mapping(aws_action: str, db) → IAMMapping | None:
    # exact match on aws_action
```

Phase 2: add `embedding vector(768)` column + pgvector HNSW index + `bge-base-en-v1.5` for hybrid search.

---

## Phase 8: Frontend

**Stack:** React 18 + Vite + TypeScript + React Router + TanStack Query + shadcn/ui + Tailwind + reactflow

### Routes
| Route | Page | Key requirement |
|---|---|---|
| `/login` | Login | Email + password form |
| `/register` | Register | |
| `/settings` | AWS Connections | Add/list/delete credentials; validate connection |
| `/dashboard` | Dashboard | Resource counts by type; recent skill runs |
| `/resources` | Resource Browser | Filter by type, migration; select for skill run |
| `/skill-runs/new` | Skill Runner | Pick skill; pick resource OR upload file; trigger |
| `/skill-runs/:id` | Progress | Live SSE: round N of M · phase · confidence · elapsed time |
| `/skill-runs/:id/results` | Results | Artifact list + inline MD viewer + downloads |

### Key Components
- **`SkillProgressTracker`** — `EventSource` on `/api/skill-runs/{id}/stream`; renders "Round 2 of 3 · Reviewer · 0.72 confidence · 47s"
- **`DependencyGraph`** — reactflow canvas from `dependency_graph_mmd` artifact data
- **`ArtifactViewer`** — react-markdown renderer + download button per artifact
- **`ResourceTable`** — shadcn DataTable (TanStack Table); sortable/filterable

### `frontend/package.json` key dependencies
```json
{
  "react": "^18",
  "react-router-dom": "^6",
  "@tanstack/react-query": "^5",
  "reactflow": "^11",
  "react-markdown": "^9",
  "axios": "^1",
  "tailwindcss": "^3",
  "shadcn/ui": "latest"
}
```

---

## Deferred (Post-MVP)

| Feature | When |
|---|---|
| Credential encryption (Fernet) | Before any production deployment |
| Live CloudTrail/Flow Log via SDK | Phase 2 |
| pgvector semantic search | Phase 2 |
| `terraform init` validation container | Phase 2 |
| pandas preprocessing | Not needed (existing code handles it) |

---

## Files Summary

| File | Action | Key Notes |
|---|---|---|
| `skills/shared/agent_logger.py` | Adapt | Remove file I/O; `end_session()` returns `(json_str, md_str)` |
| `skills/shared/doc_loader.py` | Adapt | `SKILLS_ROOT` path fix |
| `skills/cfn_terraform/orchestrator.py` | Adapt | Flip models; remove FS; `progress_callback`; direct translator import |
| `skills/iam_translation/orchestrator.py` | Adapt | Same as CFN |
| `skills/dependency_discovery/orchestrator.py` | New | Thin async wrapper over `src/` modules |
| `skills/*/translator.py`, `workflows/`, `docs/`, `src/` | Copy as-is | No changes |
| `db/models.py` | New | 8 ORM models |
| `gateway/model_gateway.py` | New | Routing table + secret scrubbing |
| `services/skill_runner.py` | New | ARQ task + `WorkerSettings` |
| `services/aws_extractor.py` | New | boto3 CFN + IAM extraction |
| `services/auth_service.py` | New | JWT + bcrypt |
| `api/auth.py` | New | Register + login |
| `api/aws.py` | New | Connections, migrations, extraction, file upload, resources |
| `api/skills.py` | New | Skill runs, SSE, artifact download |
| `api/deps.py` | New | `get_db`, `get_current_tenant` |
| `rag/search.py` | New | Keyword lookup |
| `main.py`, `config.py`, `db/base.py` | New | App bootstrap |
| `docker-compose.yml` | New | 4 services |
| `Dockerfile`, `requirements.txt` | New | |
| `frontend/` | New | Full React app (8 pages) |

---

## Verification

1. `docker compose up` — all 4 services healthy
2. Register → login → receive JWT
3. Add AWS connection → status `"active"`
4. Create migration → trigger extraction → resources appear in `/resources`
5. Upload CFN YAML → trigger `cfn_terraform` skill run
6. Watch `/skill-runs/:id` SSE stream: round/phase/confidence/elapsed update live
7. Download terraform zip from results page; run `terraform init -backend=false` locally
8. Check DB: `skill_run_interactions` shows `claude-opus-4-6` for enhancement/fix, `claude-sonnet-4-6` for review
9. Run IAM + dependency discovery skill runs end-to-end
