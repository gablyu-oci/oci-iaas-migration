# OCI Migration Tool

A web platform that automates migrating AWS infrastructure to Oracle Cloud Infrastructure (OCI). It connects to your AWS account, extracts resources, and uses AI-powered skills to translate CloudFormation templates to Terraform, convert IAM policies, and map service dependencies.

---

## What it does

| Skill | Input | Output |
|---|---|---|
| **IAM Policy Translation** | AWS IAM policy JSON | OCI IAM policy statements + migration guide |
| **CloudFormation → Terraform** | CloudFormation YAML/JSON template | OCI Terraform HCL modules |
| **Dependency Discovery** | CloudTrail logs + VPC Flow Logs | Service dependency graph + migration runbook |

Each skill runs an iterative enhancement → review → fix loop (up to 3 rounds) with confidence scoring. Results are stored as downloadable artifacts.

---

## Requirements

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+
- Claude Code CLI (authenticated with your Anthropic account — used for AI calls via OAuth)

Redis is optional. If unavailable, skill jobs run directly in background threads.

---

## Setup

### 1. Clone and navigate

```bash
cd oci-migration-tool
```

### 2. Database

```bash
# Create the database
createdb oci_migration

# Or if using the postgres system user:
sudo -u postgres createdb oci_migration
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

### 3. Backend

```bash
cd backend

# Copy and edit environment config
cp .env.example .env
```

Edit `.env` — the defaults work for a local PostgreSQL install. The only required change is `JWT_SECRET`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/oci_migration
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=          # leave blank if using Claude Code OAuth
JWT_SECRET=your-random-secret-here
JWT_EXPIRE_MINUTES=1440
```

```bash
# Install dependencies
pip install -r requirements.txt

# Create database tables
python3 -c "import asyncio; from app.db.base import init_db; asyncio.run(init_db())"

# Seed reference data (AWS→OCI service and IAM mappings)
cd .. && python3 scripts/seed_rag.py && cd backend

# Start the API server (must be outside a Claude Code session for AI calls to work)
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### 4. Frontend

```bash
cd frontend

# Point the frontend at the backend
echo "VITE_API_URL=http://localhost:8001" > .env

# Install and build
npm install
npm run build

# Serve the built frontend
npx serve dist -p 5173 -s
```

### 5. Access

- **UI:** http://localhost:5173
- **API docs:** http://localhost:8001/docs

---

## AWS Credentials

The tool connects to your AWS account to extract CloudFormation stacks and IAM policies. You supply credentials per-migration through the UI (Settings → Add AWS Connection).

### Where to get them

**Option A — IAM User (simplest)**

1. Go to [AWS Console → IAM → Users](https://console.aws.amazon.com/iam/home#/users)
2. Create a new user or select an existing one
3. Go to **Security credentials** → **Create access key**
4. Choose **Other** as the use case
5. Copy the **Access Key ID** and **Secret Access Key**

**Option B — Existing user**

If you already have AWS CLI configured locally:

```bash
cat ~/.aws/credentials
```

This shows your `aws_access_key_id` and `aws_secret_access_key`.

### Required IAM permissions

The tool only reads from AWS — it never writes or modifies anything. Minimum permissions needed:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:ListStacks",
        "cloudformation:GetTemplate",
        "cloudformation:DescribeStacks",
        "iam:ListPolicies",
        "iam:GetPolicy",
        "iam:GetPolicyVersion",
        "iam:ListAttachedRolePolicies",
        "iam:GetRolePolicy"
      ],
      "Resource": "*"
    }
  ]
}
```

The AWS managed policy `ReadOnlyAccess` also works if you prefer not to create a custom policy.

### Supported regions

Any standard AWS region (e.g. `us-east-1`, `eu-west-1`). Enter the region when adding the connection in the UI.

---

## AI authentication

The tool uses Claude for all AI calls. It supports two auth modes:

**Claude Code OAuth (default, no setup needed)**
If you have Claude Code installed and authenticated (`claude` CLI), the tool uses your existing OAuth session automatically. The backend server must be started from a regular terminal — not from inside a Claude Code session.

**Anthropic API key**
Set `ANTHROPIC_API_KEY` in `backend/.env`. Takes priority over OAuth if set.

---

## Remote access via SSH tunnel

If the server is on a remote VM, forward ports to your local machine:

```bash
ssh -L 5173:localhost:5173 -L 8001:localhost:8001 user@your-vm-ip
```

Then open http://localhost:5173 in your local browser.

---

## Project layout

```
oci-migration-tool/
├── backend/          # FastAPI application
├── frontend/         # React + Vite application
├── scripts/          # DB seeding utilities
├── design-docs/      # Architecture diagrams and planning docs
└── logs/             # Runtime logs
```

See `ARCHITECTURE.md` for a detailed breakdown of the codebase.
