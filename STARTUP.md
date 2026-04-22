# OCI Migration Tool — Startup Guide

## Prerequisites

- Ubuntu 20.04+ (tested on 22.04)
- Python 3.10+
- Node.js 18+ (20 recommended — Vite 8 requires it)
- PostgreSQL 14+
- Redis 6+ *(optional — jobs run in-process without it)*
- `terraform` CLI on `$PATH` — agents use it to self-validate generated HCL
- `bwrap` (bubblewrap) — *optional but recommended*; sandboxes `terraform_validate`
- Network access to an **OpenAI-compatible chat-completions endpoint**. Default is the Oracle-internal Llama Stack (anonymous, in-network).

## 1. System dependencies

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib redis-server bubblewrap terraform
sudo systemctl enable --now postgresql
sudo systemctl enable --now redis-server    # optional
```

## 2. Database

```bash
sudo -u postgres createdb oci_migration
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

Tables are auto-created on backend startup.

## 3. Backend

```bash
cd backend
pip3 install -r requirements.txt
cp .env.example .env     # then edit — at minimum set JWT_SECRET
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | no | `postgresql+asyncpg://postgres:postgres@localhost:5432/oci_migration` | Postgres connection |
| `REDIS_URL` | no | `redis://localhost:6379` | Redis connection (ARQ job queue) |
| `LLM_BASE_URL` | no | `https://llama-stack.ai-apps-ord.oci-incubations.com/v1` | OpenAI-compatible chat-completions URL |
| `LLM_API_KEY` | no | *(empty)* | API key — leave blank for anonymous endpoints (e.g., the internal Llama Stack) |
| `LLM_WRITER_MODEL` | no | `oci/openai.gpt-5.4` | Writer model used by agent runtime |
| `LLM_REVIEWER_MODEL` | no | `oci/openai.gpt-5.4-mini` | Reviewer model used by agent runtime |
| `LLM_ORCHESTRATOR_MODEL` | no | `oci/openai.gpt-5.4` | *(reserved — orchestrator is Python today; no LLM call)* |
| `JWT_SECRET` | **yes** | `change-me-in-production` | Secret for JWT signing — `openssl rand -hex 32` |
| `JWT_EXPIRE_MINUTES` | no | `1440` | JWT TTL (24h) |

Every `LLM_*` var is also editable at runtime through the Settings page — the
chosen values are persisted to the `system_settings` DB table and take effect
on the next LLM call without a backend restart.

The writer + reviewer models are user-picked from a dropdown populated by a
live probe of `/v1/models` on the configured endpoint. See
[`docs/llm-models.md`](docs/llm-models.md) for the catalog of models that
actually work.

## 4. Frontend

```bash
cd frontend
npm install          # first time only
npm run dev
```

## 5. *(Optional)* ARQ worker

For background job processing via Redis:

```bash
cd backend
arq app.services.job_runner.WorkerSettings
```

Without the ARQ worker, jobs run in child processes per request — fine for dev.

## 6. Access

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8001 |
| Swagger | http://localhost:8001/docs |
| Health | http://localhost:8001/health |

## First-time usage

1. **Register** an account at the login page.
2. **Settings → LLM Endpoint** — the default points at the Oracle Llama Stack; swap if you need a different backend.
3. **Settings → LLM Models** — pick writer + reviewer models (defaults to `gpt-5.4` / `gpt-5.4-mini`).
4. Add an **AWS connection** (IAM access key or an existing local AWS profile).
5. **Create a migration**, extract resources, run the assessment.
6. **Generate plan** — the Migration Orchestrator dispatches writer+reviewer agent pairs across dependency waves, self-validating Terraform as it goes. See [`docs/agent-architecture.md`](docs/agent-architecture.md) for the full flow.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Port already in use | `kill $(lsof -t -i:8001)` (or `:5173`) |
| `DB connection refused` | `sudo systemctl status postgresql` |
| LLM calls 504 on large prompts | Upstream gateway timeout. Client retry is configured (5 tries, 300s read timeout). If it still fails, switch to a smaller writer (e.g., `gpt-4.1` instead of reasoning `gpt-5.4`). |
| `terraform: command not found` in agent logs | Install terraform, or accept that `terraform_validate` will skip-with-warning (the agent handles this gracefully). |
| Dropdown shows "— unknown —" model | Run `python3 scripts/probe_llm_models.py` to refresh the catalog from the live endpoint. |
| Frontend can't reach backend | Check `VITE_API_URL` in `frontend/.env`; defaults to `http://localhost:8001`. Behind nginx, use the vhost URL. |

## Re-probing the model catalog

```bash
python3 scripts/probe_llm_models.py
```

Writes `docs/llm-models.md` + `docs/llm-models.json` with the current
availability of every model on the endpoint. The Settings dropdown reads
from the JSON sidecar.

## Regenerating agent architecture docs

```bash
python3 scripts/render_agent_docs.py
```

Rebuilds `docs/agent-architecture.md` from the machine-readable registry
at `backend/app/agents/registry.py`. Run this whenever a tool, skill, or
dependency wave changes.
