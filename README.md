# OCI Migration Tool — Oracle GenAI edition

An AI-powered platform for migrating AWS workloads to Oracle Cloud Infrastructure (OCI). It connects to your AWS account, discovers resources, builds a dependency-ordered migration plan, and uses **Oracle Generative AI** to generate Terraform configurations for OCI.

This is a fork of the original Claude-powered tool; all LLM calls are now routed through OCI Generative AI's OpenAI-compatible inference endpoint.

---

## What changed in this fork

- **Provider:** Claude (Anthropic) → Oracle Generative AI
- **Client library:** `anthropic` → `openai` (pointed at the OCI inference endpoint)
- **Auth:** `ANTHROPIC_API_KEY` / Claude Code OAuth → `OCI_GENAI_API_KEY` + project OCID
- **Models:** `claude-opus-4-6` / `claude-sonnet-4-6` → `google.gemini-2.5-pro` (configurable — any OCI GenAI chat model works)
- **Gateway:** `app.gateway.oci_genai_client.OCIGenAIClient` exposes the same `messages.create()` / `messages.stream()` surface the orchestrators were written against, so skill orchestrators did not need rewriting

---

## What it does

1. **Discover** — extract AWS resources region-wide or scoped to a specific EC2 instance
2. **Plan** — auto-generate a phased migration plan that groups resources by type and dependency order
3. **Translate** — run AI translation jobs per workload; each job runs an Enhancement → Review → Fix loop and produces ready-to-apply Terraform
4. **Download** — get `.tf` files, migration guides, and runbooks as artifacts

### Translation skills

| Skill | Translates |
|---|---|
| `network_translation` | VPC, subnets, security groups, ENIs → OCI VCN, subnets, NSGs, VNIC attachments |
| `ec2_translation` | EC2 instances, Auto Scaling groups → OCI Compute, instance pools |
| `storage_translation` | EBS volumes → OCI Block Volumes |
| `database_translation` | RDS instances/clusters → OCI Database services |
| `loadbalancer_translation` | ALB/NLB → OCI Load Balancer |
| `cfn_terraform` | CloudFormation templates → Terraform for OCI |
| `iam_translation` | IAM policies/roles → OCI IAM policy statements |
| `dependency_discovery` | VPC flow logs → service dependency graph + runbook |

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis (optional — jobs run in-process without it)
- **OCI Generative AI API key and project OCID** (Ashburn region by default; change `OCI_GENAI_BASE_URL` for other regions)

---

## Setup

### 1. Database

```bash
createdb oci_migration
# If using the postgres system user:
sudo -u postgres createdb oci_migration
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env   # then edit .env
```

Or create `backend/.env` directly:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/oci_migration
REDIS_URL=redis://localhost:6379

OCI_GENAI_API_KEY=sk-...
OCI_GENAI_BASE_URL=https://inference.generativeai.us-ashburn-1.oci.oraclecloud.com/openai/v1
OCI_GENAI_PROJECT=ocid1.generativeaiproject.oc1.iad...
OCI_GENAI_WRITER_MODEL=google.gemini-2.5-pro
OCI_GENAI_REVIEWER_MODEL=google.gemini-2.5-pro

JWT_SECRET=                     # generate with: openssl rand -hex 32
JWT_EXPIRE_MINUTES=1440
```

Getting your OCI GenAI API key:

1. OCI Console → Generative AI → **Create project**
2. Copy the project OCID (starts with `ocid1.generativeaiproject.oc1...`) into `OCI_GENAI_PROJECT`
3. Generative AI → **API keys** → Create — the value starts with `sk-` and goes into `OCI_GENAI_API_KEY`

See the [OCI Generative AI documentation](https://docs.oracle.com/en-us/iaas/Content/generative-ai/home.htm) for supported regions, models, and quotas.

Run database migrations:

```bash
alembic upgrade head
```

Seed the RAG knowledge base (AWS→OCI service mappings, IAM mappings):

```bash
cd ..
python3 scripts/seed_rag.py
cd backend
```

Start the API server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

For a production build:

```bash
npm run build
npx serve dist -p 5173 -s
```

### 4. ARQ worker (optional, requires Redis)

```bash
cd backend
arq app.services.job_runner.WorkerSettings
```

Without this, jobs still run — they just use child processes spawned by the API server.

### 5. Access

- **UI:** http://localhost:5173
- **API docs:** http://localhost:8001/docs

---

## AWS credentials

The tool is read-only — it never writes to your AWS account. Supply credentials per-migration in the UI.

**Option A — IAM User access keys**

1. AWS Console → IAM → Users → Security credentials → Create access key
2. Use case: **Other**
3. Copy the Access Key ID and Secret Access Key

**Option B — Use existing AWS CLI credentials**

```bash
cat ~/.aws/credentials
```

### Minimum required permissions

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

The AWS managed policy `ReadOnlyAccess` also works.

---

## Remote access

If the backend is on a remote VM, forward ports with SSH:

```bash
ssh -L 5173:localhost:5173 -L 8001:localhost:8001 user@your-vm-ip
```

Then open http://localhost:5173 locally.

---

## Project layout

```
oci-iaas-migration-genai/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── db/           # SQLAlchemy models and migrations
│   │   ├── gateway/      # OCI GenAI client + model routing
│   │   │   ├── model_gateway.py     # get_anthropic_client() now returns OCIGenAIClient
│   │   │   └── oci_genai_client.py  # OpenAI SDK wrapper with Anthropic-shaped surface
│   │   ├── services/     # AWS extractor, migration orchestrator, job runner
│   │   └── skills/       # Translation skill orchestrators (one dir per skill)
│   └── alembic/          # DB migration scripts
├── frontend/
│   └── src/
│       ├── pages/        # Route-level components
│       └── components/   # Shared UI components
├── scripts/              # DB seeding utilities
└── design-docs/          # Architecture diagrams and planning notes
```

---

## How the Oracle GenAI adapter works

`OCIGenAIClient` keeps the Anthropic SDK surface the orchestrators were written against:

```python
client = get_anthropic_client()  # now returns OCIGenAIClient under the hood

response = client.messages.create(
    model="google.gemini-2.5-pro",
    max_tokens=32768,
    system=[{"type": "text", "text": "..."}],
    messages=[{"role": "user", "content": "..."}],
)

response.content[0].text       # same attribute path
response.usage.input_tokens    # mapped from OpenAI prompt_tokens
response.stop_reason           # "max_tokens" / "end_turn" — mapped from finish_reason
```

Internally the adapter uses the OpenAI Python SDK pointed at the OCI inference endpoint:

```python
from openai import OpenAI
OpenAI(
    api_key=OCI_GENAI_API_KEY,
    base_url="https://inference.generativeai.us-ashburn-1.oci.oraclecloud.com/openai/v1",
    project=OCI_GENAI_PROJECT,
).chat.completions.create(model="google.gemini-2.5-pro", messages=...)
```

Notes / limitations:
- OCI GenAI does not expose prompt caching via the OpenAI-compatible endpoint, so `cache_read_input_tokens` / `cache_creation_input_tokens` always report 0.
- `cache_control` annotations on system blocks are accepted but ignored.
- Streaming is aggregated server-side before return (orchestrators only read `stream.get_final_message()`, so this is invisible).
