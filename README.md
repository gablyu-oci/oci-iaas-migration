# OCI Migration Tool

AI-powered platform for migrating AWS workloads to Oracle Cloud Infrastructure.
Connects to an AWS account, discovers resources, assesses readiness, groups
them into workloads, and generates OCI Terraform — driven by an **agent runtime**
that spawns writer + reviewer agents per resource type and self-validates output
with `terraform validate`.

- **LLM endpoint:** any OpenAI-compatible chat-completions URL. Default is
  the Oracle-internal Llama Stack gateway
  (`https://llama-stack.ai-apps-ord.oci-incubations.com/v1`); switchable at
  runtime from the Settings page.
- **Agent framework:** [`openai-agents`](https://github.com/openai/openai-agents-python)
  SDK, tracing disabled (no data leaves the network).
- **Orchestrator:** Python-driven dependency-wave dispatcher that runs
  applicable skills in parallel within each wave. See
  [`docs/agent-architecture.md`](docs/agent-architecture.md) for the full
  runtime reference.

---

## What it does

1. **Discover** — extract AWS resources region-wide or scoped to a specific EC2 instance (picks up only that instance's subnet, security group, EBS volumes, and ENIs — not the entire VPC).
2. **Assess** — classify resources with 6R, group into workloads, right-size, compare AWS vs OCI cost.
3. **Generate plan** — the [Migration Orchestrator](docs/agent-architecture.md) dispatches writer+reviewer agents per resource type across dependency waves; each writer calls tools (`terraform_validate`, `lookup_aws_mapping`) to self-check output before returning.
4. **Download** — `.tf` files, migration guides, and runbooks as artifacts.

### Translation skills (agent-runtime)

| Skill | Covers |
|---|---|
| `network_translation` | VPC, subnets, SGs, ENIs, IGW, NAT, route tables, EIPs, NACLs → OCI VCN family |
| `ec2_translation` | EC2 instances, ASGs, launch templates → OCI Compute + Instance Pools |
| `storage_translation` | EBS volumes → OCI Block Volumes |
| `database_translation` | RDS instances/clusters → OCI DB Systems / MySQL HeatWave / Autonomous DB |
| `loadbalancer_translation` | ALB/NLB + target groups + listeners → OCI LB + backend sets |
| `iam_translation` | IAM policies/roles → OCI verb-based policy statements |
| `cfn_terraform` | CloudFormation templates → OCI Terraform (self-validated with `terraform validate`) |
| `data_migration_planning` | DB cutover runbook (ZDM / DMS / dump-load) |
| `synthesis` | Compose per-skill artifacts into a final workload Terraform package |
| `workload_planning` · `dependency_discovery` | Per-workload runbook + CloudTrail / flow-log dependency analysis |

See [`backend/data/mappings/resources.yaml`](backend/data/mappings/resources.yaml)
for the single source of truth of AWS→OCI type mappings, and
[`docs/llm-models.md`](docs/llm-models.md) for the working-model catalog.

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis (optional — jobs run in-process without it)
- `terraform` CLI on PATH (agents use it to self-validate HCL)
- `bwrap` (bubblewrap) on PATH, optional but recommended — sandboxes `terraform_validate` subprocess calls
- An OpenAI-compatible chat-completions endpoint. For Oracle employees the
  internal Llama Stack at `https://llama-stack.ai-apps-ord.oci-incubations.com/v1`
  is anonymous; external deployments point at OCI GenAI or OpenAI directly.

---

## Setup

### 1. Database

```bash
sudo -u postgres createdb oci_migration
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # then edit
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Minimum `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/oci_migration
LLM_BASE_URL=https://llama-stack.ai-apps-ord.oci-incubations.com/v1
LLM_API_KEY=                     # empty for anonymous endpoints
LLM_WRITER_MODEL=oci/openai.gpt-5.4
LLM_REVIEWER_MODEL=oci/openai.gpt-5.4-mini
JWT_SECRET=                      # openssl rand -hex 32
```

Writer/reviewer models are also editable at runtime via the Settings page.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Access

- **UI:** http://localhost:5173
- **API docs:** http://localhost:8001/docs
- **Health:** http://localhost:8001/health

If you're running behind the nginx vhost at `migration.oci-incubations.com`,
both are proxied under that host.

---

## AWS credentials

The tool is read-only — it never writes to your AWS account. Supply credentials per-migration in the UI.

**IAM User access keys** (Console → IAM → Users → Security credentials → Create access key, use case **Other**) or an existing profile (`cat ~/.aws/credentials`).

### Minimum IAM policy

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "ec2:Describe*",
      "rds:Describe*",
      "elasticloadbalancing:Describe*",
      "autoscaling:Describe*",
      "lambda:List*", "lambda:Get*",
      "cloudformation:ListStacks", "cloudformation:GetTemplate", "cloudformation:DescribeStacks",
      "iam:ListPolicies", "iam:GetPolicy", "iam:GetPolicyVersion",
      "iam:ListRoles", "iam:GetRole", "iam:ListAttachedRolePolicies"
    ],
    "Resource": "*"
  }]
}
```

AWS managed `ReadOnlyAccess` also works.

---

## Remote access

If the backend is on a remote VM, forward the ports:

```bash
ssh -L 5173:localhost:5173 -L 8001:localhost:8001 user@your-vm-ip
```

Then open http://localhost:5173 locally.

---

## Project layout

```
oci-iaas-migration/
├── backend/
│   ├── app/
│   │   ├── agents/           ← openai-agents SDK runtime (orchestrator, skill groups, tools)
│   │   ├── api/              ← FastAPI route handlers
│   │   ├── db/               ← SQLAlchemy models + async engine
│   │   ├── gateway/          ← LLM client (OpenAI SDK → any OpenAI-compat endpoint)
│   │   ├── mappings/         ← typed accessors over data/mappings/*.yaml
│   │   ├── services/         ← AWS extractor, assessment runner, job runner, grouper
│   │   └── skills/           ← per-skill workflow prompts + reference docs
│   └── data/
│       └── mappings/         ← single source of truth for AWS→OCI mappings (YAML)
├── frontend/                 ← React + Vite + Tailwind UI
├── docs/                     ← live architecture + model-catalog reference
│   ├── agent-architecture.md   (auto-generated from app/agents/registry.py)
│   └── llm-models.md           (auto-generated by scripts/probe_llm_models.py)
├── design-docs/              ← historical planning + gap analyses
├── reference/                ← product requirements / market analysis
└── scripts/
    ├── probe_llm_models.py   ← re-probes every model on the endpoint
    └── render_agent_docs.py  ← regenerates docs/agent-architecture.md
```

---

## Where to read next

- [**docs/agent-architecture.md**](docs/agent-architecture.md) — how the agent runtime is organized, which tools exist, security posture, extension checklists.
- [**docs/llm-models.md**](docs/llm-models.md) — every model on the configured endpoint, status + failure category.
- [**ARCHITECTURE.md**](ARCHITECTURE.md) — higher-level component diagram and API surface.
- [**design-docs/**](design-docs/) — original planning docs (architecture v2, gap analysis, UX spec).

---

## Health check

```bash
cd backend
python3 -c "
import sys; sys.path.insert(0, '.')
from app.agents.orchestrator import MigrationOrchestrator, DEPENDENCY_WAVES
from app.agents.skill_group import SKILL_SPECS, SKILL_TO_AWS_TYPES, KNOWN_AWS_TYPES
print(f'waves: {len(DEPENDENCY_WAVES)}, skills: {len(SKILL_SPECS)}, known types: {len(KNOWN_AWS_TYPES)}')
"
```

Should print `waves: 8, skills: 11, known types: 21` (or higher as the routing table grows).
