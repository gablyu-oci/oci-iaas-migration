# OCI Migration Tool — Architecture

High-level map of the system. For the agent-runtime internals (tool registry,
writer/reviewer loop, dependency waves, security posture) see
[`docs/agent-architecture.md`](docs/agent-architecture.md) — that doc is
auto-generated from the code and is the authoritative reference.

For historical design context (pre-agent-runtime, pre-Llama-Stack) see
[`design-docs/`](design-docs/) — those are kept as reference but don't
describe the current system.

---

## Component map

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Frontend  (React + Vite + Tailwind)                                     │
│  - Login / Register                                                      │
│  - Dashboard                                                             │
│  - Migration detail → resources, assessments, workloads                  │
│  - Settings → LLM endpoint + writer / reviewer model picker              │
└───────────────────────────┬──────────────────────────────────────────────┘
                            │ REST + SSE
┌───────────────────────────▼──────────────────────────────────────────────┐
│  Backend  (FastAPI, SQLAlchemy 2.0 async, Postgres, optional ARQ)        │
│                                                                          │
│  app/api/         ← HTTP routes (auth, aws, migrations, plans, settings) │
│  app/db/          ← ORM models + async engine                            │
│  app/services/    ← AWS extractor, assessment runner, job runner,        │
│                     plan orchestrator, grouper, rightsizer, TCO          │
│  app/gateway/     ← LLM client (OpenAI SDK → any chat-completions URL)   │
│  app/mappings/    ← typed accessors over data/mappings/*.yaml            │
│  app/agents/      ← openai-agents SDK runtime                            │
│  app/skills/      ← per-skill workflow prompts + OCI reference docs      │
└───────────────────────────┬──────────────────────────────────────────────┘
                            │ /v1/chat/completions
┌───────────────────────────▼──────────────────────────────────────────────┐
│  LLM endpoint  (OpenAI-compatible)                                       │
│  Default: Llama Stack @ llama-stack.ai-apps-ord.oci-incubations.com/v1   │
│  Swappable to OCI GenAI / OpenAI / vLLM via the Settings UI              │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Runtime data flow

1. **Discovery** — `app/services/aws_extractor.py` calls AWS `Describe*` APIs and writes rows to the `resources` table. Scope is either region-wide or a single EC2 instance (only touches that instance's subnet / SG / volumes / ENIs).
2. **Assessment** — `app/services/assessment_runner.py` runs a deterministic pipeline (dependency mapping, rightsizing, OS compat, TCO) plus one LLM-driven step per resource type (6R classification, app grouping). Results land in the `assessments` / `app_groups` / `resource_assessments` tables.
3. **Plan generation** — the [Migration Orchestrator](docs/agent-architecture.md) dispatches per-skill writer+reviewer agent pairs across dependency waves. Each skill group loops enhance → review → (revise) up to a user-configurable `max_iterations`, early-stopping on high reviewer confidence. Tool calls (`terraform_validate`, `lookup_aws_mapping`) happen inside the loop.
4. **Artifacts** — approved drafts land in the `artifacts` table as `{filename → content}` maps, rendered as a downloadable bundle in the UI.

---

## Single sources of truth

| What | Where | Consumed by |
|---|---|---|
| AWS → OCI resource mapping | [`backend/data/mappings/resources.yaml`](backend/data/mappings/resources.yaml) | Python services + LLM prompts (injected as a table) |
| Instance specs + OCI flex shapes | [`backend/data/mappings/instance_shapes.yaml`](backend/data/mappings/instance_shapes.yaml) | `rightsizing_engine.py` |
| IAM action → OCI verb | [`backend/data/mappings/iam.yaml`](backend/data/mappings/iam.yaml) | `iam_translation` agents |
| Storage / network pricing | [`backend/data/mappings/pricing.yaml`](backend/data/mappings/pricing.yaml) | `tco_calculator.py` |
| Skill → AWS types routing | `SKILL_TO_AWS_TYPES` in [`app/agents/skill_group.py`](backend/app/agents/skill_group.py) | Orchestrator + registry |
| Tool catalog + agent roles | [`app/agents/registry.py`](backend/app/agents/registry.py) | Runtime + [`docs/agent-architecture.md`](docs/agent-architecture.md) |
| Working-model catalog | [`docs/llm-models.json`](docs/llm-models.json) (probe sidecar) | `app/api/settings.py` dropdown |

---

## API surface

Top-level routes under `/api/`:

| Path | Notes |
|---|---|
| `auth/register`, `auth/login` | JWT-based |
| `aws/connections`, `aws/resources`, `migrations/{id}/extract` | AWS discovery |
| `migrations`, `migrations/{id}/assess`, `migrations/{id}/workloads` | Assessment |
| `migrations/{id}/plans`, `app-groups/{id}/plan-results` | Plan generation |
| `migrate/*` | Terraform apply / state management (Phase 2) |
| `settings/models`, `settings/credentials`, `settings/credentials/test` | LLM endpoint + model picker |
| `skill-runs`, `skill-runs/{id}/stream` | Single-skill runs + SSE progress |

Full OpenAPI spec at `GET /openapi.json` and interactive docs at `GET /docs`.

---

## Security posture

- **Agent tool scope** — every tool the LLM can call is listed in [`app/agents/registry.py`](backend/app/agents/registry.py). All are **read-only**; no `terraform apply`, no AWS writes, no arbitrary code execution.
- **Trusted migration context** — orchestrator-level tools (`list_discovered_resources`, `count_resources_by_type`) read `migration_id` from `RunContextWrapper[MigrationContext]`, not from LLM-supplied arguments. The model cannot target a different migration.
- **`terraform_validate` sandbox** — wrapped in `bwrap --unshare-all --cap-drop ALL --clearenv`, read-only binds of system dirs, writable tmpdir only, dies with parent.
- **No external telemetry** — `openai-agents` SDK tracing is hard-disabled via `set_tracing_disabled(True)` in [`app/agents/config.py`](backend/app/agents/config.py). Nothing leaves the internal network.
- **Scrubbed logs** — `app/gateway/model_gateway.py` has a `scrub_secrets` helper that redacts AKIA keys, 12-digit account IDs, and OCIDs before logging or sending to the LLM.
- **Credentials at rest** — AWS keys supplied per-migration are stored in the `aws_connections` table (plaintext today; Fernet encryption is a known follow-up).

See [`docs/agent-architecture.md#security-posture`](docs/agent-architecture.md)
for the agent-runtime-specific threat model.

---

## Where to look for specifics

- **How the agents work, end-to-end** → [`docs/agent-architecture.md`](docs/agent-architecture.md)
- **Which LLM models actually work** → [`docs/llm-models.md`](docs/llm-models.md)
- **How to run locally** → [`STARTUP.md`](STARTUP.md)
- **Historical planning** → [`design-docs/`](design-docs/) (pre-agent architecture; kept for context, not current)
- **Product requirements** → [`reference/`](reference/)
