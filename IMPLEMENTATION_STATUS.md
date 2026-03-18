# OCI Migration Tool — Implementation Status

## Overview

Full-stack implementation of the OCI Migration Tool — a FastAPI + React web platform wrapping three Claude-powered AWS-to-OCI migration skills (CFN->Terraform, IAM Translation, Dependency Discovery).

---

## Files Created

### Backend (`backend/`)

| File | Description |
|---|---|
| `app/__init__.py` | Package init |
| `app/config.py` | Pydantic BaseSettings (DATABASE_URL, REDIS_URL, ANTHROPIC_API_KEY, JWT) |
| `app/main.py` | FastAPI app with CORS, lifespan (init_db), health endpoint |
| `app/api/__init__.py` | Package init |
| `app/api/auth.py` | POST /api/auth/register, POST /api/auth/login |
| `app/api/aws.py` | AWS connections CRUD, migrations CRUD, extraction, upload, resources |
| `app/api/deps.py` | HTTPBearer auth dependency, get_current_tenant |
| `app/api/skills.py` | Skill runs CRUD, SSE stream, artifact download |
| `app/db/__init__.py` | Package init |
| `app/db/base.py` | Async engine, session factory, get_db(), init_db() |
| `app/db/models.py` | 9 SQLAlchemy 2.0 ORM models (Tenant, AWSConnection, Migration, Resource, SkillRun, SkillRunInteraction, Artifact, ServiceMapping, IAMMapping) |
| `app/gateway/__init__.py` | Package init |
| `app/gateway/model_gateway.py` | MODEL_ROUTING, scrub_secrets(), get_anthropic_client(), get_model() |
| `app/services/__init__.py` | Package init |
| `app/services/auth_service.py` | hash_password, verify_password, create_access_token, decode_token |
| `app/services/aws_extractor.py` | validate_credentials, extract_cfn_stacks, extract_iam_policies (boto3) |
| `app/services/skill_runner.py` | ARQ worker task run_skill_job + WorkerSettings |
| `app/rag/__init__.py` | Package init |
| `app/rag/search.py` | search_service_mappings, lookup_iam_mapping (keyword ILIKE) |
| `app/skills/__init__.py` | Package init |
| `app/skills/shared/agent_logger.py` | **ADAPTED**: Removed file I/O, end_session() returns (json_str, md_str) |
| `app/skills/shared/doc_loader.py` | **ADAPTED**: SKILLS_ROOT path fix, underscore dirs |
| `app/skills/cfn_terraform/orchestrator.py` | **ADAPTED**: Flipped models (Opus=writer, Sonnet=reviewer), removed FS, new run() signature |
| `app/skills/iam_translation/orchestrator.py` | **ADAPTED**: Same model flip, removed FS, new run() signature |
| `app/skills/dependency_discovery/orchestrator.py` | **REWRITTEN**: Thin wrapper over src/ package |
| `requirements.txt` | All Python dependencies |
| `.env.example` | Environment variable template |
| `data/seeds/service_mappings.json` | 15+ AWS-to-OCI service mappings |
| `data/seeds/iam_mappings.json` | 15+ AWS-to-OCI IAM action mappings |
| `alembic.ini` | Alembic configuration |
| `alembic/env.py` | Async-aware Alembic env with model imports |

### Frontend (`frontend/`)

| File | Description |
|---|---|
| `src/main.tsx` | Entry point with QueryClientProvider |
| `src/App.tsx` | React Router v6 with protected routes and sidebar nav |
| `src/index.css` | Tailwind CSS base imports |
| `src/api/client.ts` | Axios instance with auth interceptor |
| `src/api/hooks/useAuth.ts` | Register and login mutations |
| `src/api/hooks/useConnections.ts` | AWS connection CRUD hooks |
| `src/api/hooks/useMigrations.ts` | Migration CRUD + extract + upload hooks |
| `src/api/hooks/useResources.ts` | Resource list query hook |
| `src/api/hooks/useSkillRuns.ts` | Skill run CRUD + SSE stream + artifacts hooks |
| `src/lib/utils.ts` | cn(), formatDate(), formatCost() helpers |
| `src/components/SkillProgressTracker.tsx` | SSE-driven progress display (round/phase/confidence/elapsed) |
| `src/components/ArtifactViewer.tsx` | Artifact list with inline preview (ReactMarkdown) and download |
| `src/components/DependencyGraph.tsx` | ReactFlow canvas for dependency visualization |
| `src/components/ResourceTable.tsx` | Filterable resource table with row selection |
| `src/pages/Login.tsx` | Email + password login form |
| `src/pages/Register.tsx` | Registration form |
| `src/pages/Dashboard.tsx` | Overview with count cards and recent skill runs |
| `src/pages/Settings.tsx` | AWS connection management (add/list/delete) |
| `src/pages/Resources.tsx` | Resource browser with filter + "Run Skill" action |
| `src/pages/SkillRunNew.tsx` | Skill run creation (pick skill, resource/paste content, max iterations) |
| `src/pages/SkillRunProgress.tsx` | Live SSE progress view |
| `src/pages/SkillRunResults.tsx` | Results with summary, artifacts, dependency graph |
| `tailwind.config.ts` | Tailwind CSS configuration |
| `postcss.config.js` | PostCSS configuration |
| `index.html` | HTML entry point with "OCI Migration Tool" title |
| `package.json` | All npm dependencies |

### Scripts

| File | Description |
|---|---|
| `scripts/seed_rag.py` | Seeds service_mappings and iam_mappings tables from JSON |

---

## Verification Results

- **TypeScript compilation**: `npx tsc --noEmit` passes with zero errors
- **npm install**: All dependencies installed successfully (0 vulnerabilities)
- **pip install**: All Python dependencies installed successfully
- **Python imports**: Models, config, auth service, gateway all import correctly
- **Model routing**: `get_model('cfn_terraform', 'enhancement')` returns `claude-opus-4-6` (confirmed flip)
- **Skill adaptations**: All three orchestrators have new `run()` signatures, agent_logger returns strings instead of writing files, doc_loader paths use underscores

---

## How to Run Locally

### Prerequisites
- PostgreSQL 16+ running on localhost:5432
- Redis running on localhost:6379
- Python 3.10+
- Node.js 18+

### 1. Database Setup
```bash
createdb oci_migration
```

### 2. Backend
```bash
cd backend
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY and database credentials

pip install -r requirements.txt

# Create tables
python3 -c "import asyncio; from app.db.base import init_db; asyncio.run(init_db())"

# Seed reference data
cd .. && python3 scripts/seed_rag.py

# Start API server
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# In a separate terminal, start the ARQ worker
cd backend && arq app.services.skill_runner.WorkerSettings
```

### 3. Frontend
```bash
cd frontend
echo "VITE_API_URL=http://localhost:8000" > .env
npm install
npm run dev
```

### 4. Access
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

---

## Architecture Summary

```
Frontend (React + Vite)          Backend (FastAPI)              Workers
    |                                |                             |
    |-- REST API calls -----------> Auth, AWS, Skills routers     |
    |                                |                             |
    |-- SSE stream ----------------> /skill-runs/{id}/stream      |
    |                                |                             |
    |                           DB (PostgreSQL)                    |
    |                                |                             |
    |                           Redis queue                        |
    |                                |                             |
    |                                +-----> ARQ Worker            |
    |                                        |                     |
    |                                        +-> cfn_terraform     |
    |                                        +-> iam_translation   |
    |                                        +-> dependency_discovery
```

**Model Routing (Opus = writer, Sonnet = reviewer)**:
- CFN/IAM Enhancement: `claude-opus-4-6`
- CFN/IAM Review: `claude-sonnet-4-6`
- CFN/IAM Fix: `claude-opus-4-6`
- Dependency Runbook: `claude-opus-4-6`
- Dependency Anomalies: `claude-sonnet-4-6`

---

## Known Limitations (MVP)

- Credentials stored as plaintext (encrypt with Fernet for production)
- CloudTrail/Flow Logs are file upload only (no live SDK)
- RAG uses keyword ILIKE search (no pgvector semantic search)
- No `terraform init` validation gate
- ARQ worker requires Redis (falls back to direct execution if unavailable)
