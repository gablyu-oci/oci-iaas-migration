# OCI IaaS Migration -- Backend

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env  # configure LLM endpoint + DB
uvicorn app.main:app --reload
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The plan-generation pipeline (skill writers → graph → templates → synthesis → bundle) + component map |
| [docs/skill-coverage.md](docs/skill-coverage.md) | Which AWS resource types each skill covers, and known gaps |
| [../docs/agent-architecture.md](../docs/agent-architecture.md) | Authoritative agent-runtime reference (tools, roles, dependency waves) — auto-generated from `app/agents/registry.py` |
| [../ARCHITECTURE.md](../ARCHITECTURE.md) | Whole-system component map, runtime data flow, API surface, security posture |
| [../STARTUP.md](../STARTUP.md) | Local setup, environment variables, troubleshooting |

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

## Project Structure

```
app/
  agents/          -- openai-agents runtime: orchestrator agent, skill groups, tools, registry
  api/             -- FastAPI route handlers (auth, aws, assessments, plans, migrate, settings)
  gateway/         -- LLM client, model routing, guardrails
  services/        -- Core pipeline services (extractor, assessment, plan orchestrator, synthesis)
  templates/       -- Jinja2 HCL templates + Pydantic schemas
  skills/          -- Per-skill workflow prompts + OCI reference docs
  mappings/        -- Typed accessors over data/mappings/*.yaml
  db/              -- SQLAlchemy models + async engine
data/mappings/     -- Single source of truth for AWS→OCI mappings (YAML)
tests/             -- pytest test suite (fixtures/ holds captured regression data)
docs/              -- Architecture + skill-coverage reference
```
