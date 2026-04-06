# OCI IaaS Migration Platform — Startup Guide

## Prerequisites

- Ubuntu 20.04+ (tested on 22.04)
- Python 3.10+
- Node.js 18+ (20 recommended — Vite 8 requires it)
- PostgreSQL 14+
- Redis 6+ (optional — jobs run in-process without it)

## 1. Install System Dependencies

```bash
# PostgreSQL
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib

# Redis (optional but recommended for background job queue)
sudo apt-get install -y redis-server

# Start services
sudo systemctl start postgresql
sudo systemctl enable postgresql
sudo systemctl start redis-server   # if installed
sudo systemctl enable redis-server  # if installed
```

## 2. Create Database

```bash
sudo -u postgres psql -c "CREATE DATABASE oci_migration;"
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
```

## 3. Backend Setup

```bash
cd /home/ubuntu/oci-iaas-migration/backend

# Install Python dependencies
pip3 install -r requirements.txt

# Create environment config
cp .env.example .env
# Edit .env and set JWT_SECRET (generate with: openssl rand -hex 32)
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | `postgresql+asyncpg://postgres:postgres@localhost:5432/oci_migration` | PostgreSQL connection |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis connection (for ARQ job queue) |
| `ANTHROPIC_API_KEY` | No | — | Anthropic API key. Leave **empty** to use Claude Code agent (OAuth) instead |
| `JWT_SECRET` | Yes | `change-me-in-production` | Secret for JWT token signing |
| `JWT_EXPIRE_MINUTES` | No | `1440` | JWT token expiry (24 hours) |

### AI Backend: Claude Code Agent vs API Key

The app supports two modes for AI features (6R classification, etc.):

1. **Claude Code Agent (default)** — Leave `ANTHROPIC_API_KEY` empty. The app uses the `AgentSDKClient` adapter which authenticates via Claude Code OAuth. No API key needed.
2. **Anthropic API** — Set `ANTHROPIC_API_KEY=sk-ant-...` to use the Anthropic API directly.

## 4. Start Backend

```bash
cd /home/ubuntu/oci-iaas-migration/backend
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

The backend will:
- Auto-create all database tables on startup
- Seed reference data (service mappings, IAM mappings)
- Serve API at http://localhost:8001
- Swagger docs at http://localhost:8001/docs

## 5. Start Frontend

```bash
cd /home/ubuntu/oci-iaas-migration/frontend
npm install   # first time only
npm run dev
```

Frontend runs at http://localhost:5173

## 6. (Optional) Start ARQ Worker

For background job processing via Redis:

```bash
cd /home/ubuntu/oci-iaas-migration/backend
arq app.services.job_runner.WorkerSettings
```

Without the ARQ worker, jobs run in child processes (works fine for development).

## Access Points

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8001 |
| Swagger Docs | http://localhost:8001/docs |
| Health Check | http://localhost:8001/health |

## First-Time Usage

1. **Register** — Create an account at the login page
2. **Settings** — Add an AWS connection (access key or IAM role)
3. **Create Migration** — Name your migration project, link AWS connection
4. **Extract Resources** — Click "Extract" to discover AWS resources via boto3
5. **Run Assessment** — Click "Run Assessment" on the migration detail page
   - Collects CloudWatch metrics
   - Rightsizes to OCI shapes
   - Checks OS compatibility
   - Maps dependencies
   - Groups into applications
   - Classifies 6R strategy (via Claude)
   - Scores migration readiness
   - Calculates TCO comparison
6. **View Results** — Assessment detail page with 5 tabs: Overview, Resources, Applications, Dependencies, OS Compatibility

## Troubleshooting

- **Port in use**: `lsof -i :8001` or `lsof -i :5173` to find and kill conflicting processes
- **DB connection refused**: Ensure PostgreSQL is running: `sudo systemctl status postgresql`
- **Missing tables**: Tables auto-create on backend startup via `Base.metadata.create_all()`
- **Frontend can't reach backend**: Check VITE_API_URL in frontend (defaults to http://localhost:8001)
