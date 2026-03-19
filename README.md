# OCI Migration Tool

An AI-powered platform for migrating AWS workloads to Oracle Cloud Infrastructure (OCI). It connects to your AWS account, discovers resources, builds a dependency-ordered migration plan, and uses Claude to generate Terraform configurations for OCI.

---

## What it does

1. **Discover** — extract AWS resources region-wide or scoped to a specific EC2 instance (picks up only the instance's subnet, security group, EBS volumes, and ENIs — not the entire VPC)
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

### Migration plan phases

Resources are grouped into phases in dependency order:

1. Networking Foundation (VPC, subnets, security groups, ENIs)
2. Data Layer (RDS)
3. Application Layer (EC2, Auto Scaling)
4. Storage (EBS volumes)
5. Traffic Management (ALB/NLB)
6. Serverless (Lambda)
7. Infrastructure as Code (CloudFormation stacks)
8. Identity & Access (IAM policies/roles)

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Redis (optional — jobs run in-process without it)
- Anthropic API key **or** Claude Code CLI authenticated with your account

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
ANTHROPIC_API_KEY=              # set this, OR use ANTHROPIC_AUTH_TOKEN below
ANTHROPIC_AUTH_TOKEN=           # Claude Code OAuth token (fallback if API key is blank)
JWT_SECRET=                     # generate with: openssl rand -hex 32
JWT_EXPIRE_MINUTES=1440
```

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

> **Note:** If using Claude Code OAuth (no `ANTHROPIC_API_KEY`), start the server from a regular terminal — not from inside a Claude Code session.

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
oci-migration-tool/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── db/           # SQLAlchemy models and migrations
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
