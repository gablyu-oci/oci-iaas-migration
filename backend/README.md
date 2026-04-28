# OCI IaaS Migration -- Backend

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env  # configure LLM endpoint + DB
uvicorn app.main:app --reload
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the 5-layer pipeline overview.

## Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline overview and component map |
| [PHASE_1_TEMPLATES.md](docs/PHASE_1_TEMPLATES.md) | Structured output + template rendering |
| [PHASE_2_GRAPH.md](docs/PHASE_2_GRAPH.md) | ResourceGraph typed nodes + edges |
| [PHASE_3_VALIDATION.md](docs/PHASE_3_VALIDATION.md) | Per-skill + post-merge validation |
| [PHASE_4_REMAINING_SKILLS.md](docs/PHASE_4_REMAINING_SKILLS.md) | Remaining skills migration |
| [PHASE_5_MODEL_ROUTING.md](docs/PHASE_5_MODEL_ROUTING.md) | Model routing + provider pinning |

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

## Project Structure

```
app/
  agents/          -- LLM skill agents (skill_group.py)
  gateway/         -- LLM client, model routing, guardrails
  services/        -- Core pipeline services
  templates/       -- Jinja2 HCL templates + Pydantic schemas
  db/              -- SQLAlchemy models + migrations
tests/             -- pytest test suite
  fixtures/        -- Captured regression test data
docs/              -- Architecture deep-dives
```
