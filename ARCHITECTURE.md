# OCI IaaS Migration Tool -- Architecture Document

**Generated:** 2026-03-30
**Scope:** Complete codebase analysis covering backend, frontend, AI/LLM pipeline, database schema, and migration readiness.

---

## Table of Contents

1. [System Overview](#section-1-system-overview)
2. [Backend Architecture](#section-2-backend-architecture)
3. [AI/LLM Architecture](#section-3-aillm-architecture)
4. [Frontend Architecture](#section-4-frontend-architecture)
5. [What Is Implemented (fully working)](#section-5-what-is-implemented)
6. [What Is NOT Implemented (gaps)](#section-6-what-is-not-implemented)
7. [API Reference](#section-7-api-reference)
8. [NemoKlaw Migration Guide](#section-8-nemoklaw-migration-guide)

---

## Section 1: System Overview

### What Is This Tool?

The OCI IaaS Migration Tool is an AI-powered web application that assists enterprises in migrating their AWS infrastructure to Oracle Cloud Infrastructure (OCI). It automates the entire migration lifecycle from discovery through planning:

1. **Discover** -- Connect to an AWS account and automatically extract all infrastructure resources (EC2, VPC, RDS, Lambda, IAM, CloudFormation, EBS, etc.)
2. **Assess** -- Analyze each resource for migration readiness: rightsizing to OCI shapes, OS compatibility, dependency mapping, cost comparison (TCO), 6R classification, and readiness scoring
3. **Plan** -- Generate phased migration plans with AI-powered translation of AWS resources to OCI Terraform HCL, including network, compute, database, storage, load balancer, IAM, and CloudFormation translations
4. **Synthesize** -- Combine all translation artifacts into a unified, apply-ready Terraform plan with runbooks

### High-Level Architecture

```
                     +------------------+
                     |   React Frontend |
                     |  (Vite + TS)     |
                     +--------+---------+
                              |
                         REST API (JSON)
                         SSE (streaming)
                              |
                     +--------+---------+
                     |   FastAPI Backend |
                     |   (Python 3.10+) |
                     +--------+---------+
                              |
            +---------+-------+-------+---------+
            |         |               |         |
     +------+---+ +---+----+  +------+---+ +---+------+
     |PostgreSQL | |  AWS   |  | Anthropic| |  Redis   |
     | (asyncpg) | | (boto3)|  |  Claude  | | (arq)    |
     +-----------+ +--------+  | API/SDK  | | optional |
                               +----------+ +----------+

    Process Architecture:
    +--FastAPI (uvicorn)--+       +--Child Process (spawn)--+
    |  API handlers       |  -->  |  assessment_runner       |
    |  Auth middleware     |       |  discovery_runner        |
    |  SSE streaming      |       |  job_runner              |
    +---------------------+       |  plan_orchestrator       |
                                  |    (each creates own     |
                                  |     DB engine)           |
                                  +-------------------------+
```

### Tech Stack

| Layer       | Technology                                                  |
|-------------|-------------------------------------------------------------|
| **Frontend**| React 19, TypeScript, Vite 8, TailwindCSS 4, React Router 7, TanStack React Query 5 |
| **Backend** | Python 3.10+, FastAPI, Uvicorn, SQLAlchemy 2.0 (async), Pydantic |
| **Database**| PostgreSQL (via asyncpg for FastAPI, psycopg2 for child processes) |
| **Queue**   | ARQ + Redis (optional; falls back to multiprocessing.Process) |
| **AI/LLM**  | Anthropic Claude (claude-opus-4-6, claude-sonnet-4-6) via API or Agent SDK |
| **AWS**     | boto3 (STS, EC2, VPC, RDS, Lambda, IAM, CloudFormation, CloudWatch, SSM, ELBv2, ASG, EBS) |
| **Graphing**| Graphviz (SVG dependency graphs), Mermaid (frontend rendering) |
| **IaC**     | Terraform (validation of generated HCL)                     |

---

## Section 2: Backend Architecture

### FastAPI App Structure

**Entry point:** `/home/ubuntu/oci-iaas-migration/backend/app/main.py`

The app is initialized with a lifespan handler that runs `init_db()` on startup (creates all tables via SQLAlchemy `create_all`). CORS is configured to allow all origins.

**Router modules** (all mounted under `/api`):

| Module | Prefix | Purpose |
|--------|--------|---------|
| `app/api/auth.py` | `/api/auth` | Registration, login, JWT issuance |
| `app/api/aws.py` | `/api` | AWS connections, migrations, resource CRUD, discovery |
| `app/api/assessments.py` | `/api` | Assessment lifecycle, resource assessments, app groups, TCO, dependencies |
| `app/api/jobs.py` | `/api` | Translation job CRUD, SSE streaming, artifact download |
| `app/api/plans.py` | `/api` | Migration plan generation, workload execution, synthesis |
| `app/api/rag.py` | (not mounted in main.py) | RAG indexing and search (exists but not wired into the router) |

**Service modules** (`app/services/`):

| Module | Purpose |
|--------|---------|
| `auth_service.py` | bcrypt password hashing, JWT encode/decode (python-jose, HS256) |
| `aws_extractor.py` | boto3-based extraction of 11 resource types from AWS |
| `discovery_runner.py` | Runs full AWS resource extraction in a child process |
| `assessment_runner.py` | 9-step assessment pipeline in a child process |
| `cloudwatch_collector.py` | Collects CPU, network, disk metrics from CloudWatch |
| `ssm_inventory.py` | Collects software inventory via SSM |
| `rightsizing_engine.py` | Maps AWS instance types to optimal OCI Flex shapes with cost comparison |
| `os_compat_checker.py` | Checks OS compatibility with OCI (Linux distro mapping) |
| `dependency_mapper.py` | VPC Flow Logs + CloudTrail dependency discovery |
| `app_grouper.py` | 3-pass resource grouping: tag-based, network-based, traffic-based |
| `sixr_classifier.py` | LLM-based 6R strategy classification (Rehost/Replatform/Refactor/Repurchase/Retire/Retain) |
| `readiness_scorer.py` | Weighted readiness score computation |
| `tco_calculator.py` | TCO comparison with 3-year projections and OCI commitment discounts |
| `resource_mapper.py` | Deterministic AWS-to-OCI resource mapping + LLM review |
| `workload_graph.py` | Graphviz SVG rendering of per-workload dependency graphs |
| `job_runner.py` | ARQ task that routes translation jobs to skill orchestrators |
| `plan_orchestrator.py` | Full pipeline: resource mapping -> skills -> data migration -> runbook -> synthesis |
| `migration_orchestrator.py` | Phase-based plan generation grouping resources by type |

### Database Schema

**Engine:** PostgreSQL via asyncpg (async) and psycopg2 (sync in child processes).

**ORM:** SQLAlchemy 2.0 declarative with `Mapped` type annotations.

**Models file:** `/home/ubuntu/oci-iaas-migration/backend/app/db/models.py`

#### Tables and Relationships

```
tenants
  |-- id (UUID PK)
  |-- email (unique)
  |-- password_hash
  |-- created_at
  |
  +--< aws_connections (tenant_id FK)
  |     |-- id, name, region, credential_type
  |     |-- credentials (Text, stored as JSON)
  |     |-- status (active/invalid)
  |
  +--< migrations (tenant_id FK)
        |-- id, name, status, created_at
        |-- aws_connection_id FK -> aws_connections
        |-- discovery_status, discovery_error, discovered_at
        |-- plan_status, plan_workload_id, plan_workload_name
        |
        +--< resources (migration_id FK)
        |     |-- id, aws_type, aws_arn, name
        |     |-- raw_config (JSONB -- full AWS resource config)
        |     |-- status (discovered/running/migrated/failed)
        |
        +--< assessments (migration_id FK)
        |     |-- id, status, config (JSONB), summary (JSONB)
        |     |-- current_step, error_message
        |     |-- dependency_artifacts (JSONB -- workload graphs, plans)
        |     |
        |     +--< resource_assessments (assessment_id FK, resource_id FK)
        |     |     |-- metrics (JSONB), rightsizing fields
        |     |     |-- OS compat fields, software_inventory (JSONB)
        |     |     |-- sixr_strategy, readiness_score, readiness_factors (JSONB)
        |     |
        |     +--< app_groups (assessment_id FK)
        |     |     |-- name, grouping_method, workload_type
        |     |     |-- sixr_strategy, readiness_score, costs
        |     |     |-- metadata (JSONB)
        |     |     +--< app_group_members (app_group_id FK, resource_id FK)
        |     |
        |     +--1 tco_reports (assessment_id FK, unique)
        |     |     |-- aws_monthly, oci_monthly, savings
        |     |     |-- breakdown (JSONB), three_year_tco (JSONB)
        |     |
        |     +--< dependency_edges (assessment_id FK)
        |           |-- source/target resource_id FKs
        |           |-- source_ip, target_ip, port, protocol
        |           |-- edge_type, byte_count, packet_count
        |
        +--1 migration_plans (migration_id FK, unique)
              |-- status, summary (JSONB)
              +--< plan_phases (plan_id FK)
                    |-- name, description, order_index, status
                    +--< workloads (phase_id FK)
                          |-- name, description, skill_type, status
                          |-- translation_job_id FK -> translation_jobs
                          |-- app_group_id FK -> app_groups
                          +--< workload_resources (workload_id FK, resource_id FK)

translation_jobs (tenant_id FK)
  |-- id, skill_type, status, current_phase, current_iteration
  |-- input_resource_id FK -> resources
  |-- input_content (Text), config (JSONB)
  |-- confidence (Float), total_cost_usd (Float)
  |-- output (JSONB), errors (JSONB)
  |
  +--< translation_job_interactions
  |     |-- agent_type, model, iteration
  |     |-- tokens_input, tokens_output, tokens_cache_read/write
  |     |-- cost_usd, decision, confidence, issues (JSONB)
  |
  +--< artifacts
        |-- file_type, file_name, content_type
        |-- data (bytes -- actual file content)

service_mappings (RAG reference data)
  |-- aws_service, aws_resource_type -> oci_service, oci_resource_type, terraform_resource

iam_mappings (RAG reference data)
  |-- aws_action, aws_service -> oci_permission, oci_service
```

### Authentication Flow

1. **Register** (`POST /api/auth/register`): Creates `Tenant` with bcrypt-hashed password, returns JWT.
2. **Login** (`POST /api/auth/login`): Verifies credentials, returns JWT.
3. **JWT**: HS256 signed with `JWT_SECRET`, contains `{"sub": "<tenant_id>"}`, expires in 1440 minutes (24h).
4. **Protected routes**: Use `get_current_tenant` dependency (HTTPBearer scheme), which decodes the JWT and loads the Tenant from the DB.
5. **SSE/Download**: Since EventSource and `<a download>` cannot send headers, JWT is passed as `?token=` query parameter.

### How Multiprocessing Is Used

All long-running operations spawn child processes via `multiprocessing.get_context("spawn").Process` with `daemon=True`:

| Runner | Spawned From | Entry Point | Purpose |
|--------|-------------|-------------|---------|
| **Discovery** | `POST /api/migrations` (when aws_connection_id given) | `discovery_runner.run_discovery()` | Extracts all AWS resources |
| **Assessment** | `POST /api/migrations/{id}/assess` | `assessment_runner.run_assessment()` | 9-step assessment pipeline |
| **Translation Job** | `POST /api/translation-jobs` or workload execute | `job_runner.run_translation_job()` | Runs skill orchestrator |
| **Plan Orchestrator** | `POST /api/migrations/{id}/plan-from-assessment` | `plan_orchestrator.run_workload_plan()` | Full plan pipeline |

**Key patterns:**
- Each child calls `os.setpgrp()` to create a new process group, enabling clean kill of the entire process tree (including `claude` CLI subprocesses).
- Each child creates its **own DB engine** (sync for assessment/discovery, async for job_runner) to avoid sharing connection pools across process boundaries.
- Child processes unset `CLAUDECODE` env var so the Agent SDK can launch nested sessions.
- On job/assessment delete, the parent sends `SIGTERM` to the process group, then `SIGKILL` after 5s timeout.

---

## Section 3: AI/LLM Architecture

### How Claude Is Called

**File:** `/home/ubuntu/oci-iaas-migration/backend/app/gateway/model_gateway.py`

Two client modes, selected by `get_anthropic_client()`:

1. **Direct Anthropic API** (`anthropic.Anthropic`): Used when `ANTHROPIC_API_KEY` is configured. Makes standard API calls with `client.messages.create()` or `client.messages.stream()`.

2. **Agent SDK Client** (`AgentSDKClient` in `app/gateway/agent_adapter.py`): Used when no API key is set. Wraps `claude_agent_sdk.query()` with an `anthropic.Anthropic`-compatible interface. Runs in a separate thread with its own event loop to avoid conflicts with the caller's async context. 5-minute timeout per call.

**Model routing** (`MODEL_ROUTING` dict in `model_gateway.py`):
- **Enhancement agent**: `claude-opus-4-6` (all skills)
- **Review agent**: `claude-sonnet-4-6` (most skills) or `claude-opus-4-6` (cfn_terraform, iam_translation)
- **Fix agent**: `claude-sonnet-4-6` (most skills) or `claude-opus-4-6` (cfn_terraform, iam_translation)

### The Enhancement -> Review -> Fix Loop (BaseTranslationOrchestrator)

**File:** `/home/ubuntu/oci-iaas-migration/backend/app/skills/shared/base_orchestrator.py`

This is the core AI pattern used by 7 translation skills. The loop:

```
1. Parse input JSON
2. Run gap analysis (deterministic, per-skill)
3. For iteration = 1..max_iterations:
   a. ENHANCEMENT agent: Generate/improve OCI Terraform translation
      - Model: claude-opus-4-6, max_tokens: 32768
      - Input: AWS resource JSON + previous translation + issues to fix
      - Output: Complete OCI Terraform translation as JSON
      - Retries: up to 3 attempts on JSON parse failure
   b. REVIEW agent: Evaluate the translation
      - Model: claude-sonnet-4-6, max_tokens: 4096
      - Input: AWS resource JSON + translation to review
      - Output: JSON with decision, confidence, issues[]
      - Decision types: APPROVED, APPROVED_WITH_NOTES, NEEDS_FIXES, FAILED
   c. If APPROVED or APPROVED_WITH_NOTES -> break
   d. If last iteration -> break
   e. FIX agent: Apply targeted fixes
      - Model: claude-sonnet-4-6, max_tokens: 32768
      - Input: AWS resource JSON + translation + high-severity issues
      - Output: Fixed translation JSON
4. Build artifacts (main.tf, variables.tf, outputs.tf, tfvars, summary.json, report.md)
5. Run terraform validate (if terraform binary available)
6. Return result dict with artifacts, confidence, cost, interactions
```

**Confidence calculation** (in `make_decision_from_review`):
- Based on gap analysis counts + reviewer issues
- `ConfidenceCalculator` computes score from total_items, mapped_count, issues severity, architectural mismatch
- Decision thresholds: APPROVED (>= 0.85), APPROVED_WITH_NOTES (>= 0.65), NEEDS_FIXES (< 0.65)

**Guardrails** (`app/gateway/guardrails.py`):
- **Input**: Scrubs AWS access keys, secret keys, account IDs, OCIDs, generic secrets. Detects PII (warns). Blocks prompt injection attempts. Enforces 200k char budget.
- **Output**: Validates OCI resource types, flags AWS resource leaks, checks compliance.

### All Skills and What Each Produces

| Skill | File | Input | Output Artifacts |
|-------|------|-------|-----------------|
| `network_translation` | `skills/network_translation/orchestrator.py` | VPC JSON (vpc_id, subnets, SGs, route tables, IGWs, NAT GWs, ENIs) | `main.tf` (VCN, subnets, NSGs, routes), `variables.tf`, `outputs.tf`, `tfvars`, `network-translation.md` |
| `ec2_translation` | `skills/ec2_translation/orchestrator.py` | `{instances: [...], auto_scaling_groups: [...]}` | `main.tf` (oci_core_instance, oci_core_volume, ASG config), `variables.tf`, `outputs.tf`, `tfvars`, report |
| `storage_translation` | `skills/storage_translation/orchestrator.py` | `{volumes: [...]}` | `main.tf` (oci_core_volume), `variables.tf`, `outputs.tf`, `tfvars`, report |
| `database_translation` | `skills/database_translation/orchestrator.py` | `{db_instances: [...]}` | `main.tf` (oci_database_db_system, oci_mysql_mysql_db_system), `variables.tf`, `outputs.tf`, `tfvars`, report |
| `loadbalancer_translation` | `skills/loadbalancer_translation/orchestrator.py` | `{load_balancers: [...]}` | `main.tf` (oci_load_balancer), `variables.tf`, `outputs.tf`, `tfvars`, report |
| `iam_translation` | `skills/iam_translation/orchestrator.py` | IAM policy document JSON | `main.tf` (OCI IAM policies), `variables.tf`, `outputs.tf`, `tfvars`, `iam-translation.md` |
| `cfn_terraform` | `skills/cfn_terraform/orchestrator.py` | CloudFormation template (YAML/JSON) | `main.tf`, `variables.tf`, `outputs.tf`, `tfvars`, conversion report |
| `data_migration_planning` | `skills/data_migration/orchestrator.py` | `{workload_name, database_resources, local_databases, storage_resources}` | `migration-guide.md` (data migration procedure), `summary.json` |
| `workload_planning` | `skills/workload_planning/orchestrator.py` | `{workload_name, resources, resource_mapping, dependency_edges, completed_translations}` | `migration-runbook.md`, `anomaly-analysis.md` |
| `migration_synthesis` | `skills/synthesis/orchestrator.py` | All completed job artifacts for a migration | `01-networking.tf`, `02-database.tf`, `03-compute.tf`, `04-storage.tf`, `05-loadbalancer.tf`, `variables.tf`, `outputs.tf`, `iam-setup.md`, `migration-runbook.md`, `special-attention.md` |
| `dependency_discovery` | `skills/dependency_discovery/orchestrator.py` | CloudTrail JSON + optional Flow Log text | `dependency.json`, `dependency-graph.dot`, `dependency-graph.mmd`, `dependency-report.txt`, `migration-runbook.md`, `anomaly-analysis.md` |

### The Plan Orchestrator Pipeline

**File:** `/home/ubuntu/oci-iaas-migration/backend/app/services/plan_orchestrator.py`

When "Generate Plan" is clicked for a workload (app group):

```
Step 1: Resource Mapping
  - Deterministic mapping (resource_mapper.compute_resource_mapping)
  - LLM review pass (resource_mapper.review_mapping_with_llm using claude-sonnet-4-6)

Step 2: Determine Skills to Run
  - Maps AWS resource types to skills via _TYPE_TO_SKILL patterns
  - e.g., EC2::Instance -> ec2_translation, EC2::VPC -> network_translation

Step 3: Run Translation Skills
  - For each skill: build input JSON, run Enhancement->Review->Fix loop
  - Collect artifacts from each skill

Step 4: Data Migration Planning (if databases or storage detected)
  - Runs data_migration_planning skill

Step 5: Workload Planning
  - Runs runbook + anomaly analysis agents

Step 6: Synthesis
  - Combines all artifacts into unified Terraform plan

Step 7: Store Results
  - Writes to assessment.dependency_artifacts.workload_plans JSONB
  - Updates migration.plan_status
```

Progress is stored in the assessment's `dependency_artifacts` JSONB field and polled by the frontend.

### Token Usage and Cost Tracking

Every LLM call records:
- `tokens_input`, `tokens_output`, `tokens_cache_read`, `tokens_cache_write`
- `cost_usd` calculated from model-specific pricing in `agent_logger.calculate_cost()`
- `duration_seconds`

These are stored as `TranslationJobInteraction` records and surfaced via the SSE stream and the interactions API endpoint. The `TranslationJob.total_cost_usd` field accumulates total cost across all interactions.

---

## Section 4: Frontend Architecture

### React App Structure

**Entry point:** `/home/ubuntu/oci-iaas-migration/frontend/src/main.tsx`
**Root component:** `/home/ubuntu/oci-iaas-migration/frontend/src/App.tsx`

**Tech stack:** React 19, TypeScript, Vite 8, TailwindCSS 4, React Router 7, TanStack React Query 5, Axios, ReactFlow, Mermaid, react-markdown.

### Pages

| Page | File | Purpose |
|------|------|---------|
| `Login` | `pages/Login.tsx` | Email/password login form |
| `Register` | `pages/Register.tsx` | Account registration form |
| `Dashboard` | `pages/Dashboard.tsx` | Overview: migrations list with create/discover actions |
| `Connections` | `pages/Connections.tsx` | AWS connection management (add/list/delete) |
| `Resources` | `pages/Resources.tsx` | All discovered resources table |
| `Migrations` | `pages/Migrations.tsx` | Migration list (redirects to detail) |
| `MigrationDetail` | `pages/MigrationDetail.tsx` | Single migration: resources, assessments, plans |
| `AssessmentDetail` | `pages/AssessmentDetail.tsx` | Assessment results: resource assessments, app groups, TCO, dependencies, workload graphs |
| `MigrationPlan` | `pages/MigrationPlan.tsx` | Phase/workload tree view, execute workloads |
| `WorkloadDetail` | `pages/WorkloadDetail.tsx` | Workload resources, plan results, artifacts |
| `MigrationSynthesisResults` | `pages/MigrationSynthesisResults.tsx` | Unified synthesis output viewer |
| `TranslationJobList` | `pages/TranslationJobList.tsx` | All translation jobs |
| `TranslationJobNew` | `pages/TranslationJobNew.tsx` | Create standalone translation job (paste YAML/JSON) |
| `TranslationJobProgress` | `pages/TranslationJobProgress.tsx` | SSE-powered live progress view |
| `TranslationJobResults` | `pages/TranslationJobResults.tsx` | View/download job artifacts |
| `Settings` | `pages/Settings.tsx` | App settings |

### Components

| Component | File | Purpose |
|-----------|------|---------|
| `ResourceTable` | `components/ResourceTable.tsx` | Filterable resource data table |
| `ResourceMappingTable` | `components/ResourceMappingTable.tsx` | AWS-to-OCI mapping display |
| `DependencyGraph` | `components/DependencyGraph.tsx` | ReactFlow-based dependency visualization |
| `MermaidDiagram` | `components/MermaidDiagram.tsx` | Mermaid diagram renderer |
| `ArtifactViewer` | `components/ArtifactViewer.tsx` | Tabbed artifact content viewer with syntax highlighting |
| `CostComparisonChart` | `components/CostComparisonChart.tsx` | AWS vs OCI cost bar chart |
| `SixRBadge` | `components/SixRBadge.tsx` | Colored badge for 6R strategy |
| `ReadinessScoreBadge` | `components/ReadinessScoreBadge.tsx` | Colored readiness score indicator |
| `OSCompatBadge` | `components/OSCompatBadge.tsx` | OS compatibility status badge |
| `SkillProgressTracker` | `components/SkillProgressTracker.tsx` | Real-time skill execution progress |
| `WorkloadCard` | `components/WorkloadCard.tsx` | Workload summary card in plan view |

### Routing and Navigation Flow

```
/login         -> Login
/register      -> Register
/               -> Redirect to /dashboard
/dashboard      -> Dashboard (main entry after login)
/connections    -> Connections
/resources      -> Resources
/migrations     -> Migrations
/migrations/:id -> MigrationDetail
/migrations/:id/plan -> MigrationSynthesisResults
/assessments/:id -> AssessmentDetail
/plans/:planId  -> MigrationPlan
/workloads/:id  -> WorkloadDetail
/translation-jobs      -> TranslationJobList
/translation-jobs/new  -> TranslationJobNew
/translation-jobs/:id  -> TranslationJobProgress
/translation-jobs/:id/results -> TranslationJobResults
/migrate/execution -> Coming Soon placeholder
/migrate/waves     -> Coming Soon placeholder
/validation        -> Coming Soon placeholder
/settings          -> Settings
```

All routes except `/login` and `/register` are wrapped in `ProtectedRoute` which checks for `localStorage.token`.

### State Management

- **Server state**: TanStack React Query v5 with automatic cache invalidation on mutations
- **Auth state**: JWT stored in `localStorage.token`, injected via Axios interceptor
- **URL state**: React Router params (`:id`, `:assessmentId`, etc.) and query params
- **Local state**: React `useState` for forms, modals, tab selection
- **Polling**: React Query `refetchInterval` for plan status (4s), synthesis job (3s), translation job progress (1s via SSE)

### Key UI Flows

**Discovery -> Assessment -> Plan:**

1. User creates AWS Connection (enter credentials, validated via STS)
2. User creates Migration linked to connection -> auto-triggers discovery (child process)
3. User views MigrationDetail -> sees discovered resources appear
4. User clicks "Run Assessment" -> spawns assessment child process
5. User views AssessmentDetail -> sees 9-step progress, then results:
   - Per-resource readiness scores, rightsizing, OS compatibility
   - Application groups with 6R classification
   - TCO comparison chart
   - Per-workload dependency graphs (SVG)
6. User clicks "Generate Plan" on a workload -> spawns plan orchestrator
7. User monitors plan progress (resource mapping, skill execution, synthesis)
8. User views generated artifacts (Terraform files, runbooks, migration guides)

---

## Section 5: What Is Implemented

### AWS Connection Management
- **Endpoint:** `POST/GET/DELETE /api/aws/connections`
- **Frontend:** `Connections` page
- **Status:** Fully working. Validates credentials via STS `get_caller_identity`.

### Resource Discovery
- **Endpoint:** `POST /api/migrations` (auto-triggers), `POST /api/migrations/{id}/discover`
- **Frontend:** `MigrationDetail` page
- **Status:** Fully working for 11 resource types.

| Resource Type | Extractor Function | Status |
|---------------|-------------------|--------|
| EC2 Instances | `extract_ec2_instances` | Working |
| VPCs + Subnets | `extract_vpcs` | Working |
| Security Groups | `extract_security_groups` | Working |
| EBS Volumes | `extract_ebs_volumes` | Working |
| Network Interfaces | `extract_network_interfaces` | Working |
| RDS Instances | `extract_rds_instances` | Working |
| Load Balancers (ELBv2) | `extract_load_balancers` | Working |
| Auto Scaling Groups | `extract_auto_scaling_groups` | Working |
| Lambda Functions | `extract_lambda_functions` | Working |
| CloudFormation Stacks | `extract_cfn_stacks` | Working |
| IAM Policies | `extract_iam_policies` | Working |

### Assessment Pipeline
- **Endpoint:** `POST /api/migrations/{id}/assess`
- **Frontend:** `AssessmentDetail` page
- **Status:** Fully working. 9-step pipeline.

| Step | Service | Status |
|------|---------|--------|
| 1. CloudWatch metrics | `cloudwatch_collector.collect_metrics` | Working (requires AWS creds) |
| 2. SSM inventory | `ssm_inventory.collect_inventory` | Working (requires SSM agent) |
| 3. Rightsizing | `rightsizing_engine.compute_rightsizing` | Working (30+ AWS instance types mapped) |
| 4. OS compatibility | `os_compat_checker.check_os_compatibility` | Working |
| 5. Dependency mapping | `dependency_mapper.discover_dependencies` + `dependency_discovery.orchestrator` | Working (VPC Flow Logs + CloudTrail + LLM) |
| 6. App grouping | `app_grouper.compute_app_groups` | Working (tag + network + traffic grouping) |
| 6b. Workload graphs | `workload_graph.build_workload_graphs` | Working (Graphviz SVG) |
| 7. 6R classification | `sixr_classifier.classify_workloads` | Working (LLM-based) |
| 8. Readiness scoring | `readiness_scorer.compute_readiness_score` | Working |
| 9. TCO calculation | `tco_calculator.compute_tco` | Working (3-year projections, OCI discounts) |

### Workload Dependency Graphs
- **Endpoint:** `GET /api/assessments/{id}/workload-graph/{name}` (returns SVG)
- **Frontend:** Rendered inline in `AssessmentDetail` page
- **Status:** Fully working. Color-coded by service type, edge styles by dependency type.

### Plan Generation (Phase-Based)
- **Endpoint:** `POST /api/migrations/{id}/plan`
- **Frontend:** `MigrationPlan` page
- **Status:** Fully working. Groups resources into 7 phases by dependency order.

### Plan Generation (AI-Powered Per-Workload)
- **Endpoint:** `POST /api/migrations/{id}/plan-from-assessment`
- **Frontend:** Triggered from `AssessmentDetail` "Generate Plan" button
- **Status:** Fully working. Full pipeline: mapping -> skills -> data migration -> runbook -> synthesis.

### Translation Skills
All 7 translation skills use the Enhancement->Review->Fix loop:

| Skill | Status | Notes |
|-------|--------|-------|
| `network_translation` | Working | VPC -> VCN, Subnet, NSG, route tables, IGW, NAT GW, ENI mapping |
| `ec2_translation` | Working | EC2 -> oci_core_instance, ASG -> oci_autoscaling |
| `storage_translation` | Working | EBS -> oci_core_volume (gp2/gp3/io1/io2/st1/sc1 mapped) |
| `database_translation` | Working | RDS -> OCI DB System/MySQL HeatWave/Autonomous DB |
| `loadbalancer_translation` | Working | ALB/NLB -> OCI Load Balancer/Network LB |
| `iam_translation` | Working | IAM policies -> OCI IAM policies (verb-based) |
| `cfn_terraform` | Working | CloudFormation -> OCI Terraform HCL |

### Additional Skills

| Skill | Status | Notes |
|-------|--------|-------|
| `data_migration_planning` | Working | Generates data migration procedure (markdown) |
| `workload_planning` | Working | Generates runbook + anomaly analysis |
| `migration_synthesis` | Working | Combines all artifacts into unified Terraform plan |
| `dependency_discovery` | Working | CloudTrail + Flow Log graph analysis |

### Migration Synthesis
- **Endpoint:** `POST /api/migrations/{id}/synthesize`
- **Frontend:** `MigrationSynthesisResults` page
- **Status:** Fully working. Produces numbered .tf files, IAM setup guide, runbook, special attention items.

---

## Section 6: What Is NOT Implemented

### Missing Translation Skills

These AWS services are discovered but have no dedicated translation skill:

| AWS Service | Discovery | Translation Skill | Status |
|-------------|-----------|-------------------|--------|
| Lambda Functions | Extracted | None | Resource mapper outputs "OCI Functions" with gaps noted |
| S3 Buckets | **Not extracted** | None | No extractor or skill |
| ECS/EKS Clusters | **Not extracted** | None | No extractor or skill |
| SageMaker | **Not extracted** | None | No extractor or skill |
| DynamoDB | **Not extracted** | None | No extractor or skill |
| ElastiCache/Redis | **Not extracted** | None | No extractor or skill |
| SQS/SNS | **Not extracted** | None | No extractor or skill |
| API Gateway | **Not extracted** | None | No extractor or skill |
| CloudWatch Alarms | **Not extracted** | None | No extractor or skill |
| Route 53 DNS | **Not extracted** | None | No extractor or skill |
| Secrets Manager | **Not extracted** | None | No extractor or skill |
| EFS | **Not extracted** | None | No extractor or skill |

### Missing Extractors

The `aws_extractor.py` module only covers 11 resource types. Missing:
- S3 buckets and policies
- ECS services, task definitions, clusters
- EKS clusters and node groups
- DynamoDB tables
- ElastiCache clusters
- SQS queues
- SNS topics
- API Gateway REST/HTTP APIs
- Route 53 hosted zones and records
- CloudWatch alarms and dashboards
- Secrets Manager secrets
- EFS file systems
- Step Functions state machines
- Kinesis streams

### Migrate Phase (Actual Execution)
- **Status:** NOT IMPLEMENTED
- Frontend has placeholder pages at `/migrate/execution` and `/migrate/waves` with "Coming soon" messages
- No actual OCI API integration for creating resources
- No Terraform apply automation
- No wave-based execution engine

### Validate Phase (Post-Migration Testing)
- **Status:** NOT IMPLEMENTED
- Frontend has placeholder at `/validation` with "Coming soon" message
- No post-migration validation logic
- No smoke test automation
- No data integrity verification

### Multi-Region Support
- **Status:** NOT IMPLEMENTED
- Each AWS connection has a single `region` field
- Discovery only scans one region per connection
- No cross-region dependency tracking

### RAG System
- **Status:** Partially implemented but not wired
- `app/api/rag.py` exists with index/search endpoints but is NOT included in `app/main.py` router registration
- `app/skills/shared/rag.py` and `app/skills/shared/index_docs.py` exist for vector-based doc search
- `backend/docs/` has OCI reference docs (IAM, networking, database, etc.)
- Vector store (doc_chunks table) is referenced but may not be created by `init_db()`

### Other Gaps
- No audit logging of user actions
- No role-based access control (single tenant model, no org/team support)
- No webhook/notification integration
- No Terraform state management
- No cost estimation for the migration process itself
- No export to PDF/Excel for reports
- Redis/ARQ queue is optional and untested (always falls back to multiprocessing)
- Alembic migration `001_rename_skill_runs_to_translation_jobs.py` exists but schema management relies primarily on `create_all`

---

## Section 7: API Reference

### Authentication

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `POST` | `/api/auth/register` | Create account, return JWT | Register |
| `POST` | `/api/auth/login` | Authenticate, return JWT | Login |

### AWS Connections

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `POST` | `/api/aws/connections` | Create AWS connection (validates via STS) | Connections |
| `GET` | `/api/aws/connections` | List connections for tenant | Connections |
| `DELETE` | `/api/aws/connections/{conn_id}` | Delete a connection | Connections |

### Migrations

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `POST` | `/api/migrations` | Create migration (auto-triggers discovery if connection linked) | Dashboard |
| `GET` | `/api/migrations` | List migrations with resource counts | Dashboard, Migrations |
| `GET` | `/api/migrations/{mig_id}` | Get single migration | MigrationDetail |
| `DELETE` | `/api/migrations/{mig_id}` | Delete migration and all child data | MigrationDetail |
| `POST` | `/api/migrations/{mig_id}/discover` | Trigger resource discovery | MigrationDetail |

### Resources

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `GET` | `/api/resources` | List all resources (filterable by migration_id) | Resources |
| `GET` | `/api/resources/{resource_id}` | Get single resource with raw_config | Resources |
| `POST` | `/api/migrations/{mig_id}/resources/assign` | Assign resources to migration | MigrationDetail |
| `POST` | `/api/resources/{resource_id}/upload` | Upload resource config (file) | TranslationJobNew |

### Assessments

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `POST` | `/api/migrations/{mig_id}/assess` | Create assessment, spawn runner | MigrationDetail |
| `GET` | `/api/migrations/{mig_id}/assessments` | List assessments | MigrationDetail |
| `GET` | `/api/assessments/{id}` | Get assessment status/summary | AssessmentDetail |
| `GET` | `/api/assessments/{id}/resources` | List resource assessments | AssessmentDetail |
| `GET` | `/api/assessments/{id}/app-groups` | List application groups | AssessmentDetail |
| `GET` | `/api/assessments/{id}/tco` | Get TCO report | AssessmentDetail |
| `GET` | `/api/assessments/{id}/dependencies` | List dependency edges | AssessmentDetail |
| `GET` | `/api/assessments/{id}/dependency-artifacts` | Get raw dependency artifacts JSON | AssessmentDetail |
| `GET` | `/api/assessments/{id}/workload-graph/{name}` | Get SVG dependency graph for workload | AssessmentDetail |
| `DELETE` | `/api/assessments/{id}` | Delete assessment and all child records | AssessmentDetail |

### App Groups / Resource Mapping

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `GET` | `/api/app-groups/{id}/resource-mapping` | Compute AWS->OCI resource mapping | AssessmentDetail |
| `GET` | `/api/app-groups/{id}/plan-results` | Get plan results for workload | AssessmentDetail, WorkloadDetail |
| `POST` | `/api/app-groups/{id}/cancel-plan` | Cancel running plan | AssessmentDetail |

### Translation Jobs

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `POST` | `/api/translation-jobs` | Create and enqueue a translation job | TranslationJobNew |
| `GET` | `/api/translation-jobs` | List jobs (filterable by migration_id, resource_id) | TranslationJobList |
| `GET` | `/api/translation-jobs/{id}` | Get job status/output | TranslationJobProgress |
| `DELETE` | `/api/translation-jobs/{id}` | Delete job (kills child process) | TranslationJobList |
| `GET` | `/api/translation-jobs/{id}/stream` | SSE stream of job progress | TranslationJobProgress |
| `GET` | `/api/translation-jobs/{id}/interactions` | List LLM interaction records | TranslationJobResults |
| `GET` | `/api/translation-jobs/{id}/artifacts` | List artifact metadata | TranslationJobResults |

### Artifacts

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `GET` | `/api/artifacts/{id}/download` | Download single artifact (JWT via ?token=) | TranslationJobResults |
| `POST` | `/api/artifacts/download-zip` | Download multiple artifacts as ZIP | TranslationJobResults |

### Plans

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `POST` | `/api/migrations/{id}/plan` | Generate phase-based plan from resources | MigrationPlan |
| `POST` | `/api/migrations/{id}/plan-from-assessment` | Generate AI plan for workload | AssessmentDetail |
| `GET` | `/api/plans` | List plans (filterable by migration_id) | MigrationPlan |
| `GET` | `/api/plans/{id}` | Get plan with phases and workloads | MigrationPlan |
| `GET` | `/api/plans/{id}/status` | Get plan status (reconciles with translation jobs) | MigrationPlan |
| `DELETE` | `/api/plans/{id}` | Delete plan and cancel running jobs | MigrationPlan |
| `POST` | `/api/workloads/{id}/execute` | Execute workload (create and run translation job) | MigrationPlan |
| `GET` | `/api/workloads/{id}` | Get workload detail with resources | WorkloadDetail |
| `GET` | `/api/workloads/{id}/resources` | List workload resources | WorkloadDetail |
| `GET` | `/api/phases/{id}/workloads` | List workloads in a phase | MigrationPlan |

### Synthesis

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `POST` | `/api/migrations/{id}/synthesize` | Create synthesis job | MigrationSynthesisResults |
| `GET` | `/api/migrations/{id}/synthesize/latest` | Get latest synthesis job status | MigrationSynthesisResults |

### Health

| Method | Path | Description | Frontend Page |
|--------|------|-------------|---------------|
| `GET` | `/health` | Health check | N/A |

---

## Section 8: NemoKlaw Migration Guide

This section provides a migration guide assuming NemoKlaw is an AI agent orchestration platform (similar to LangChain, CrewAI, AutoGen, or a custom multi-agent framework).

### Components That Are Platform-Agnostic (Reuse As-Is)

These modules have no dependency on the current AI orchestration pattern and can be extracted directly:

| Component | File(s) | Why Reusable |
|-----------|---------|-------------|
| **Database models** | `app/db/models.py`, `app/db/base.py` | Pure SQLAlchemy ORM; framework-independent |
| **AWS extractors** | `app/services/aws_extractor.py` | Pure boto3; no AI dependency |
| **Discovery runner** | `app/services/discovery_runner.py` | DB + boto3 only |
| **Rightsizing engine** | `app/services/rightsizing_engine.py` | Pure lookup tables + math |
| **OS compatibility checker** | `app/services/os_compat_checker.py` | Pure logic |
| **Readiness scorer** | `app/services/readiness_scorer.py` | Pure weighted scoring |
| **TCO calculator** | `app/services/tco_calculator.py` | Pure math |
| **App grouper** | `app/services/app_grouper.py` | Pure algorithmic grouping |
| **Resource mapper** (deterministic part) | `app/services/resource_mapper.py` (except `review_mapping_with_llm`) | Pure lookup tables |
| **Workload graph renderer** | `app/services/workload_graph.py` | Pure Graphviz; no AI |
| **CloudWatch collector** | `app/services/cloudwatch_collector.py` | Pure boto3 |
| **SSM inventory** | `app/services/ssm_inventory.py` | Pure boto3 |
| **Dependency mapper** (VPC Flow Log query) | `app/services/dependency_mapper.py` | Pure boto3 |
| **Auth service** | `app/services/auth_service.py` | Pure JWT/bcrypt |
| **Guardrails** | `app/gateway/guardrails.py` | Pure regex, can wrap any LLM |
| **Seed data** | `backend/data/seeds/*.json` | Static mapping reference |
| **OCI reference docs** | `backend/docs/core/`, `backend/docs/services/` | RAG corpus |
| **Frontend** | `frontend/` (entire directory) | Communicates only via REST API |

### Components Tightly Coupled to Current Architecture (Need Rewriting)

| Component | File | Coupling Point | Migration Effort |
|-----------|------|----------------|-----------------|
| **BaseTranslationOrchestrator** | `app/skills/shared/base_orchestrator.py` | Direct `anthropic.Anthropic` calls, custom Enhancement->Review->Fix loop | **High** -- core AI pattern |
| **All 7 skill orchestrators** | `app/skills/*/orchestrator.py` | Subclass BaseTranslationOrchestrator | **Medium** -- system prompts reusable, loop logic needs rewrite |
| **Synthesis orchestrator** | `app/skills/synthesis/orchestrator.py` | Direct Anthropic API calls (not using base class) | **Medium** |
| **Workload planning orchestrator** | `app/skills/workload_planning/orchestrator.py` | Direct Anthropic API calls | **Medium** |
| **AgentSDKClient** | `app/gateway/agent_adapter.py` | Claude Code Agent SDK specific | **Discard** if NemoKlaw has its own LLM gateway |
| **Model gateway** | `app/gateway/model_gateway.py` | Anthropic client factory + model routing | **Rewrite** to use NemoKlaw's model abstraction |
| **Job runner** | `app/services/job_runner.py` | Multiprocessing + direct skill routing | **Rewrite** to use NemoKlaw's job/task system |
| **Assessment runner** (6R classifier call) | `app/services/assessment_runner.py` | Direct Anthropic call via sixr_classifier | **Rewrite** the LLM call portion |
| **Plan orchestrator** | `app/services/plan_orchestrator.py` | Orchestrates multiple skill runs + LLM calls | **High** -- rewrite as NemoKlaw agent graph |
| **6R classifier** | `app/services/sixr_classifier.py` | Direct Anthropic API call | **Low** -- single prompt, easy to port |
| **Agent logger** | `app/skills/shared/agent_logger.py` | Custom logging; may conflict with NemoKlaw's tracing | **Replace** with NemoKlaw's observability |

### AI Agent Patterns and NemoKlaw Mapping

The current system uses a 3-agent loop pattern that maps naturally to multi-agent frameworks:

| Current Agent | Role | NemoKlaw Equivalent |
|---------------|------|-------------------|
| **Enhancement Agent** | Generates/improves translations (high capability, opus model) | **Builder Agent** -- creative/generative role, needs strong model |
| **Review Agent** | Evaluates quality, finds issues (faster model, structured output) | **Critic Agent** -- evaluative role, can use smaller/faster model |
| **Fix Agent** | Applies targeted fixes based on review feedback | **Refiner Agent** -- targeted improvement role |
| **Plan Orchestrator** | Routes work to skills, aggregates results | **Supervisor/Router Agent** -- orchestration layer |
| **6R Classifier** | Classifies workloads (single-shot) | **Classifier Agent** -- stateless, single-turn |
| **Resource Mapper (LLM review)** | Reviews and enriches mapping table | **Reviewer Agent** -- stateless enrichment |
| **Runbook Generator** | Generates migration runbooks | **Document Agent** -- long-form generation |
| **Anomaly Analyzer** | Identifies migration risks | **Analyst Agent** -- risk assessment |

**Agent graph structure for NemoKlaw:**

```
Supervisor Agent (plan_orchestrator equivalent)
  |
  +-- For each resource type:
  |     Builder Agent (enhancement)
  |       |-> Critic Agent (review)
  |       |-> Refiner Agent (fix) [if needed]
  |       |-> Loop back to Critic [up to max_iterations]
  |
  +-- Data Migration Agent (if databases present)
  +-- Runbook Agent (per workload)
  +-- Anomaly Agent (per workload)
  +-- Synthesis Agent (combines all outputs)
```

### Data Flow That Must Be Preserved

```
AWS Credentials (AWSConnection)
  -> Resource Extraction (boto3 extractors)
    -> Resource Storage (PostgreSQL resources table)
      -> Assessment Pipeline:
         CloudWatch Metrics + SSM Inventory
           -> Rightsizing (instance type -> OCI shape)
           -> OS Compatibility Check
           -> Dependency Discovery (Flow Logs + CloudTrail + LLM)
           -> App Grouping (tag/network/traffic)
           -> 6R Classification (LLM)
           -> Readiness Scoring
           -> TCO Calculation
             -> Planning Pipeline:
                Resource Mapping (deterministic + LLM review)
                  -> Translation Skills (per resource type)
                    -> Data Migration Planning (if DBs present)
                      -> Workload Planning (runbook + anomaly)
                        -> Synthesis (unified Terraform plan)
```

This pipeline is sequential with some parallelizable branches (translation skills could run concurrently).

### Frontend Considerations

The React frontend communicates exclusively via REST API and SSE. It has **zero coupling** to the backend's AI implementation. As long as the new NemoKlaw backend exposes the same API endpoints with the same request/response shapes, the frontend can remain completely unchanged.

Key integration points to preserve:
- All `/api/*` endpoints (same method, path, request/response JSON shapes)
- SSE stream at `/api/translation-jobs/{id}/stream` with `status` and `done` event types
- JWT authentication via `Authorization: Bearer <token>` header
- `?token=` query param for SSE and artifact download endpoints
- JSONB fields in responses (summary, dependency_artifacts, raw_config)

### Step-by-Step Migration Plan

#### Phase 1: Foundation (1-2 weeks)

**Goal:** Set up NemoKlaw project with existing platform-agnostic components.

1. Create NemoKlaw project structure
2. Copy all platform-agnostic components (DB models, extractors, calculators, frontend)
3. Set up PostgreSQL with the same schema
4. Implement the REST API layer (same endpoints) using NemoKlaw's preferred web framework
5. Verify: frontend connects and auth/CRUD operations work

**Effort:** Low. Mostly copy and wire.

#### Phase 2: Single-Agent Skills (2-3 weeks)

**Goal:** Port each translation skill as a NemoKlaw agent.

1. Extract system prompts from each skill orchestrator (these are the most valuable assets)
2. Create NemoKlaw agent definitions for each skill type:
   - Define the Enhancement/Review/Fix agent chain
   - Port gap analysis logic (deterministic, per-skill)
   - Port prompt builders (skill-specific input formatting)
   - Port report generators (skill-specific markdown output)
3. Implement the Enhancement->Review->Fix loop as a NemoKlaw agent workflow
4. Port the artifact builder (Terraform file generation)
5. Port terraform validate integration
6. Verify: each skill produces the same output quality

**Effort:** Medium. System prompts are directly reusable; loop logic needs adaptation to NemoKlaw's agent patterns.

#### Phase 3: Assessment Pipeline (1-2 weeks)

**Goal:** Port the assessment runner.

1. Port steps 1-5 (metrics, inventory, rightsizing, OS compat, dependency) as-is (no AI)
2. Port step 6 (grouping) as-is (no AI)
3. Port step 7 (6R classification) as a NemoKlaw single-turn agent
4. Port steps 8-9 (scoring, TCO) as-is (no AI)
5. Replace multiprocessing with NemoKlaw's task/job system
6. Verify: assessment produces same results

**Effort:** Low-Medium. Most steps are pure Python; only 6R classification needs agent adaptation.

#### Phase 4: Plan Orchestrator (2-3 weeks)

**Goal:** Port the plan orchestrator as a NemoKlaw supervisor agent.

1. Implement the supervisor agent that:
   - Analyzes workload resources
   - Determines which skills to run
   - Routes to appropriate translation agents
   - Aggregates results
2. Port resource mapping (deterministic + LLM review as a NemoKlaw agent)
3. Port data migration planning agent
4. Port workload planning agents (runbook + anomaly)
5. Port synthesis agent
6. Implement progress tracking (replace JSONB polling with NemoKlaw's native state)
7. Verify: full pipeline produces same output

**Effort:** High. This is the most complex orchestration logic.

#### Phase 5: Polish and Deploy (1-2 weeks)

1. Port SSE streaming to match frontend expectations
2. Implement cost/token tracking using NemoKlaw's observability
3. Load test with real AWS environments
4. Verify frontend works end-to-end without changes
5. Document NemoKlaw-specific configuration

**Effort:** Low-Medium.

**Total estimated effort: 7-12 weeks** for a team familiar with NemoKlaw's platform.

### What to Keep vs Rewrite vs Discard

| Action | Components |
|--------|-----------|
| **KEEP (as-is)** | Frontend (entire React app), DB models + schema, AWS extractors (all 11), rightsizing engine, OS compat checker, readiness scorer, TCO calculator, app grouper, resource mapper (deterministic), workload graph renderer, CloudWatch collector, SSM inventory, dependency mapper (boto3 parts), auth service, seed data, OCI reference docs |
| **KEEP (extract and adapt)** | All system prompts from skill orchestrators, gap analysis logic, prompt builders, report generators, Terraform validation logic |
| **REWRITE** | BaseTranslationOrchestrator (core agent loop), plan_orchestrator (supervisor logic), job_runner (task routing), assessment_runner (multiprocessing portions), model_gateway (client factory), 6R classifier (LLM call), resource_mapper.review_mapping_with_llm, agent_logger (observability) |
| **DISCARD** | AgentSDKClient (Claude Code specific), ARQ worker config, multiprocessing spawn/setpgrp patterns (replaced by NemoKlaw's task system) |
