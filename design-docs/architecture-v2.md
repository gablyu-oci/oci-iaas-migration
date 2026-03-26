# OCI IaaS Migration Platform — Architecture v2

> **Status:** DRAFT
> **Author:** Platform Architecture Team
> **Date:** 2026-03-26
> **Supersedes:** ARCHITECTURE.md (v1 — monolithic execution model)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview & Architecture Diagram](#2-system-overview--architecture-diagram)
3. [Plane A: Platform / Control Plane](#3-plane-a-platform--control-plane)
4. [Plane B: Execution Plane](#4-plane-b-execution-plane)
5. [Plane C: Model / Knowledge Plane](#5-plane-c-model--knowledge-plane)
6. [Component & Responsibilities Table](#6-component--responsibilities-table)
7. [Interface Definitions](#7-interface-definitions)
8. [Data Flow Diagrams](#8-data-flow-diagrams)
9. [Security Architecture](#9-security-architecture)
10. [Data Models](#10-data-models)
11. [API Contracts](#11-api-contracts)
12. [Tech Stack Decisions](#12-tech-stack-decisions)
13. [Architecture Decision Records](#13-architecture-decision-records)
14. [What Changes vs What Stays](#14-what-changes-vs-what-stays)
15. [Phased Implementation Plan](#15-phased-implementation-plan)
16. [Deployment Architecture](#16-deployment-architecture)
17. [Risks & Mitigations](#17-risks--mitigations)
18. [Anti-Patterns to Avoid](#18-anti-patterns-to-avoid)

---

## 1. Executive Summary

The OCI IaaS Migration Platform helps enterprise customers migrate AWS workloads to Oracle Cloud Infrastructure. The platform uses AI-powered translation skills to convert AWS resources (CloudFormation, IAM, VPC, EC2, RDS, EBS, ALB/NLB) into OCI Terraform configurations via an Enhancement → Review → Fix orchestration loop.

**Architecture v2** introduces a **3-Plane separation** to achieve:

| Goal | Mechanism |
|------|-----------|
| **Security isolation** | Credentials never leave their designated plane boundary |
| **Execution flexibility** | Pluggable backends: in-process → Docker → NemoClaw sandbox |
| **Model portability** | Swap Anthropic API for OCI GenAI, vLLM, or proxied endpoints |
| **Enterprise readiness** | Encrypted credentials, mandatory guardrails, locked-down CORS, audit trail |
| **Zero skill rewrites** | All 8 existing orchestrators remain unchanged |

**Key invariant:** The browser ONLY talks to Plane A. Plane B never has direct DB or tenant access. Plane C never sees tenant PII.

---

## 2. System Overview & Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                    BROWSER                                          │
│  React 19 + Vite + TanStack Query + Tailwind                                       │
│  Pages: Dashboard · Migrations · Plan · Jobs · Progress · Results · Settings        │
└──────────────────────────────────────┬──────────────────────────────────────────────┘
                                       │ HTTPS (REST + SSE)
                                       │ JWT Bearer token
                              ═════════╪═════════════════════════
                              ║  PLANE A: CONTROL PLANE         ║
                              ═════════╪═════════════════════════
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  FastAPI Platform API  (port 8001)                                                  │
│                                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  api/auth   │  │  api/aws    │  │  api/jobs    │  │  api/plans   │              │
│  │  register   │  │  connections│  │  CRUD + SSE  │  │  generate    │              │
│  │  login      │  │  extract    │  │  artifacts   │  │  workloads   │              │
│  └─────────────┘  └─────────────┘  └──────┬───────┘  └──────────────┘              │
│                                            │                                        │
│  ┌─────────────────────────────────────────▼───────────────────────────────────┐    │
│  │                        JobDispatcher (NEW)                                  │    │
│  │                                                                             │    │
│  │  1. Load TranslationJob from DB                                             │    │
│  │  2. Resolve SkillDefinition from SkillRegistry                              │    │
│  │  3. Mint ScopedCredentials (model token + STS session)                      │    │
│  │  4. Build JobContext (immutable dataclass)                                  │    │
│  │  5. Dispatch to ExecutionBackend.execute_job()                              │    │
│  │  6. Receive JobResult → persist artifacts + interactions                    │    │
│  └─────────────────────────────────────────┬───────────────────────────────────┘    │
│                                            │                                        │
│  ┌──────────────┐  ┌──────────────────┐    │    ┌──────────────────────────────┐    │
│  │  PostgreSQL  │  │  Redis / ARQ     │    │    │  SkillRegistry (NEW)         │    │
│  │  15 tables   │  │  Job queue       │    │    │  skill_type → SkillDefinition│    │
│  │  (see §10)   │  │  (optional)      │    │    │  Dynamic import via importlib│    │
│  └──────────────┘  └──────────────────┘    │    └──────────────────────────────┘    │
│                                            │                                        │
└────────────────────────────────────────────┼────────────────────────────────────────┘
                              ═══════════════╪══════════════════
                              ║  BOUNDARY 1: JobContext only   ║
                              ║  No DB strings, no JWT secrets ║
                              ║  No full AWS creds, no PII     ║
                              ═══════════════╪══════════════════
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                       PLANE B: EXECUTION PLANE (PLUGGABLE)                          │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                    ExecutionBackend (ABC)                                    │    │
│  │  initialize() · execute_job(ctx) → JobResult · cancel_job() · health_check()│    │
│  └──────────┬──────────────────────┬──────────────────────┬────────────────────┘    │
│             │                      │                      │                          │
│     ┌───────▼───────┐    ┌────────▼────────┐    ┌────────▼──────────┐               │
│     │ LocalExecutor │    │ContainerExecutor│    │ SandboxExecutor   │               │
│     │   (v1)        │    │   (v1.5)        │    │   (v2+)           │               │
│     │               │    │                 │    │                   │               │
│     │ In-process or │    │ Docker container│    │ NemoClaw/OpenShell│               │
│     │ subprocess    │    │ tmpfs mount     │    │ Landlock + seccomp│               │
│     │ Wraps existing│    │ Network:model   │    │ Creds host-side   │               │
│     │ orchestrators │    │ endpoint only   │    │ only (proxied)    │               │
│     │ via Adapter   │    │ STS creds       │    │                   │               │
│     └───────────────┘    └─────────────────┘    └───────────────────┘               │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  SkillExecutor (wraps BaseTranslationOrchestrator)                          │    │
│  │                                                                             │    │
│  │  8 Skills:  cfn_terraform · iam_translation · dependency_discovery          │    │
│  │             network_translation · ec2_translation · database_translation     │    │
│  │             loadbalancer_translation · storage_translation                   │    │
│  │  + synthesis orchestrator                                                    │    │
│  │                                                                             │    │
│  │  Enhancement → Review → Fix loop (max 3 iterations)                         │    │
│  │  Each skill: gap_analysis → enhance → review → fix → artifacts              │    │
│  └──────────────────────────────────────────┬──────────────────────────────────┘    │
│                                             │                                       │
└─────────────────────────────────────────────┼───────────────────────────────────────┘
                              ════════════════╪══════════════════
                              ║  BOUNDARY 2: Model API only    ║
                              ║  Scoped token + scrubbed prompt║
                              ║  No DB contents, no tenant PII ║
                              ════════════════╪══════════════════
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                       PLANE C: MODEL / KNOWLEDGE PLANE                              │
│                                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────┐       │
│  │                     ModelRouter (NEW)                                     │       │
│  │  Unified ModelClient protocol → route to backend by config               │       │
│  │  Guardrails enforced HERE (input scrub + output validation)              │       │
│  └────────┬──────────────────┬──────────────────┬───────────────────────────┘       │
│           │                  │                  │                                    │
│  ┌────────▼──────┐  ┌───────▼────────┐  ┌─────▼──────────┐  ┌──────────────┐      │
│  │ Anthropic API │  │ OCI GenAI      │  │ Self-hosted    │  │ NemoClaw     │      │
│  │ claude-opus   │  │ (future)       │  │ vLLM (future)  │  │ Proxy        │      │
│  │ claude-sonnet │  │                │  │                │  │ (future)     │      │
│  └───────────────┘  └────────────────┘  └────────────────┘  └──────────────┘      │
│                                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────┐       │
│  │                   Knowledge Store                                        │       │
│  │  service_mappings (161 OCI TF resource types)                            │       │
│  │  iam_mappings (AWS action → OCI permission)                              │       │
│  │  Future: pgvector embeddings for RAG                                     │       │
│  └──────────────────────────────────────────────────────────────────────────┘       │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Plane A: Platform / Control Plane

### 3.1 Responsibilities

| Responsibility | Component | Current File |
|---------------|-----------|-------------|
| User authentication (JWT) | `api/auth.py` + `services/auth_service.py` | Unchanged |
| AWS connection management | `api/aws.py` | Unchanged |
| Migration lifecycle | `api/aws.py` + `api/plans.py` | Unchanged |
| Resource discovery | `services/aws_extractor.py` | Unchanged |
| Job creation & queuing | `api/jobs.py` → `JobDispatcher` | **Refactored** |
| Job status / SSE streaming | `api/jobs.py` | Unchanged (reads DB) |
| Artifact storage & download | `api/jobs.py` | Unchanged |
| Credential minting | `JobDispatcher` → `CredentialMinter` | **New** |
| Execution backend selection | `JobDispatcher` → `ExecutionBackend` | **New** |
| Skill registry | `SkillRegistry` | **New** |
| Audit trail | DB writes (interactions, artifacts) | Unchanged |

### 3.2 JobDispatcher (New — replaces job routing logic in job_runner.py)

The `JobDispatcher` is the **sole entry point** from Plane A into Plane B. It replaces the 540-line `job_runner.py` monolith with a clean pipeline:

```
TranslationJob (DB)
    │
    ▼
┌─────────────────────────────────────────────────┐
│ JobDispatcher.dispatch(job_id)                  │
│                                                 │
│ 1. Load TranslationJob from DB                  │
│ 2. skill_def = SkillRegistry.get(skill_type)    │
│ 3. input_content = InputBuilder.build(          │
│        job, skill_def, db_session)              │
│ 4. credentials = CredentialMinter.mint(         │
│        tenant_id, skill_def)                    │
│ 5. context = JobContext(                        │
│        job_id, tenant_id, skill_def,            │
│        input_content, config, credentials,      │
│        progress_callback)                       │
│ 6. result = execution_backend.execute_job(ctx)  │
│ 7. Persist: artifacts, interactions, status     │
│ 8. Update: confidence, cost, completion time    │
└─────────────────────────────────────────────────┘
```

### 3.3 SkillRegistry (New)

Replaces the `if/elif` chain in `job_runner.py` with a declarative registry:

```python
# Loaded once at startup from skill definitions
SKILL_REGISTRY = {
    "cfn_terraform": SkillDefinition(
        skill_type="cfn_terraform",
        display_name="CloudFormation → Terraform",
        orchestrator_module="backend.app.skills.cfn_terraform.orchestrator",
        orchestrator_class="CfnTerraformOrchestrator",
        model_requirements=ModelRequirements(
            enhancement="claude-opus-4-6",
            review="claude-opus-4-6",
            fix="claude-opus-4-6",
        ),
        max_iterations=3,
        timeout_seconds=300,
        requires_aws_credentials=False,
        input_mode="single_resource",  # or "aggregated" or "synthesis"
    ),
    "network_translation": SkillDefinition(
        skill_type="network_translation",
        display_name="Network → OCI VCN",
        orchestrator_module="backend.app.skills.network_translation.orchestrator",
        orchestrator_class="NetworkTranslationOrchestrator",
        model_requirements=ModelRequirements(
            enhancement="claude-opus-4-6",
            review="claude-sonnet-4-6",
            fix="claude-sonnet-4-6",
        ),
        max_iterations=3,
        timeout_seconds=300,
        requires_aws_credentials=False,
        input_mode="aggregated",
        aggregation_types=["AWS::EC2::VPC", "AWS::EC2::Subnet",
                           "AWS::EC2::SecurityGroup", "AWS::EC2::RouteTable",
                           "AWS::EC2::InternetGateway", "AWS::EC2::NatGateway",
                           "AWS::EC2::NetworkInterface"],
    ),
    # ... remaining 7 skills follow same pattern
}
```

### 3.4 CredentialMinter (New)

Produces time-boxed, least-privilege credentials for Plane B:

```
CredentialMinter.mint(tenant_id, skill_def) → ScopedCredentials
    │
    ├─ model_api_token: Rotate per-job from ANTHROPIC_API_KEY
    │                   (or issue scoped token for OCI GenAI)
    │
    ├─ model_api_base_url: From config (MODEL_API_BASE_URL)
    │
    ├─ aws_session_token: (only if skill_def.requires_aws_credentials)
    │   └─ STS AssumeRole with 15-min TTL, scoped to read-only
    │
    └─ expires_at: min(model_token_expiry, aws_session_expiry)
```

### 3.5 InputBuilder (New — extracts from job_runner.py)

Moves the `_build_*_input()` functions out of `job_runner.py` into a dedicated module. The aggregation logic (combining VPCs + subnets + SGs for network_translation, instances + ASGs for ec2_translation, etc.) is preserved exactly but driven by `SkillDefinition.input_mode` and `aggregation_types`.

---

## 4. Plane B: Execution Plane

### 4.1 ExecutionBackend Interface

All three backends implement the same ABC:

```python
class ExecutionBackend(ABC):
    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def execute_job(self, context: JobContext) -> JobResult: ...

    @abstractmethod
    async def cancel_job(self, job_id: str) -> bool: ...

    @abstractmethod
    async def health_check(self) -> dict[str, Any]: ...

    @abstractmethod
    async def shutdown(self) -> None: ...
```

### 4.2 Backend 1: LocalExecutor (Phase 1)

**Goal:** Zero behavior change — wraps existing orchestrators exactly as `job_runner.py` does today.

```
LocalExecutor.execute_job(context):
    1. Import orchestrator class from context.skill_definition
    2. Build anthropic client from context.credentials.model_api_token
    3. Call orchestrator.run(
           input_content=context.input_content,
           progress_callback=context.progress_callback,
           client=client,
       )
    4. Return JobResult(artifacts, confidence, cost, interactions, ...)
```

**Isolation:** None (same process). This is the v1 default — functionally identical to current behavior but behind the `ExecutionBackend` interface.

**What moves from job_runner.py:**
- Skill routing → `SkillRegistry` (Plane A)
- Input aggregation → `InputBuilder` (Plane A)
- Artifact/interaction persistence → `JobDispatcher` (Plane A)
- Orchestrator invocation → `LocalExecutor` (Plane B)

### 4.3 Backend 2: ContainerExecutor (Phase 2)

**Goal:** Process isolation via Docker with restricted capabilities.

```
ContainerExecutor.execute_job(context):
    1. Serialize JobContext to JSON → mount as /input/context.json
    2. docker run \
         --rm \
         --network=model-only \        # Only MODEL_API_BASE_URL reachable
         --tmpfs /sandbox:size=512m \   # Ephemeral workspace
         --read-only \                  # Root FS immutable
         --memory=2g --cpus=2 \         # Resource limits
         --env MODEL_API_TOKEN=<scoped> \
         --env MODEL_API_BASE_URL=<url> \
         oci-migration-worker:latest \
         python -m backend.app.execution.worker_entrypoint
    3. Read /output/result.json from container
    4. Return deserialized JobResult
```

**Network policy:** Docker network `model-only` allows egress only to `MODEL_API_BASE_URL` (iptables or Docker network plugin). All other egress blocked.

**Credential handling:** STS session token (15-min TTL) passed as env var. Model API token scoped per-job. Both expire before container can be reused.

### 4.4 Backend 3: SandboxExecutor (Phase 3)

**Goal:** Maximum isolation via NemoClaw/OpenShell sandbox.

```
SandboxExecutor.execute_job(context):
    1. Upload input bundle to OpenShell sandbox
    2. Sandbox runs: python -m backend.app.execution.worker_entrypoint
    3. Sandbox kernel enforcements:
       - Landlock: read-only /usr,/lib; read-write /sandbox,/tmp ONLY
       - Network namespace: model endpoint only (via OpenShell gateway)
       - Non-root UID with seccomp profile (no mount/ptrace/network admin)
       - Model API calls proxied through OpenShell gateway
       - Credentials injected HOST-SIDE by gateway (never enter sandbox)
    4. Download output bundle from sandbox
    5. Return deserialized JobResult
```

**Critical security property:** The sandbox NEVER sees `model_api_token` or `aws_session_token`. The OpenShell gateway intercepts outbound HTTPS to the model endpoint and injects the Authorization header host-side. The sandbox only knows the gateway's local endpoint URL.

### 4.5 Worker Entrypoint (New)

A single entry point script used by both ContainerExecutor and SandboxExecutor:

```python
# backend/app/execution/worker_entrypoint.py
"""
Reads /input/context.json, runs the skill, writes /output/result.json.
Used inside Docker containers and NemoClaw sandboxes.
"""
def main():
    context = JobContext.from_json(Path("/input/context.json").read_text())
    client = create_model_client(
        token=os.environ["MODEL_API_TOKEN"],
        base_url=os.environ.get("MODEL_API_BASE_URL"),
    )
    orchestrator = import_orchestrator(context.skill_definition)
    result = orchestrator.run(
        input_content=context.input_content,
        progress_callback=context.progress_callback,
        client=client,
    )
    Path("/output/result.json").write_text(JobResult.from_orchestrator(result).to_json())
```

### 4.6 OrchestratorAdapter (New)

Bridges `JobContext` → existing orchestrator `run()` signatures. This is a thin wrapper ensuring the 8 existing orchestrators receive exactly the arguments they expect:

```python
class OrchestratorAdapter:
    """Adapts JobContext into orchestrator.run() call signature."""

    def execute(self, context: JobContext) -> JobResult:
        orchestrator = self._load_orchestrator(context.skill_definition)
        client = self._build_client(context.credentials)

        raw_result = orchestrator.run(
            input_content=context.input_content,
            progress_callback=context.progress_callback,
            client=client,
        )

        return JobResult(
            success=True,
            artifacts=raw_result.get("artifacts", {}),
            confidence=raw_result.get("confidence", 0.0),
            decision=raw_result.get("decision", "UNKNOWN"),
            iterations=raw_result.get("iterations", 0),
            cost=raw_result.get("total_cost_usd", 0.0),
            interactions=raw_result.get("interactions", []),
        )
```

---

## 5. Plane C: Model / Knowledge Plane

### 5.1 ModelRouter (New)

Replaces the model routing logic currently scattered across `model_gateway.py` and `base_orchestrator.py`:

```python
class ModelRouter:
    """Routes model requests to the configured backend."""

    def __init__(self, config: ModelConfig):
        self.backends: dict[str, ModelClient] = {}
        # Register backends based on config
        if config.anthropic_api_key:
            self.backends["anthropic"] = AnthropicModelClient(config)
        if config.oci_genai_endpoint:
            self.backends["oci_genai"] = OCIGenAIClient(config)
        if config.vllm_endpoint:
            self.backends["vllm"] = VLLMClient(config)

    def get_client(self, model_name: str) -> ModelClient:
        """Resolve model name to appropriate backend client."""
        if model_name.startswith("claude-"):
            return self.backends["anthropic"]
        elif model_name.startswith("oci-"):
            return self.backends["oci_genai"]
        else:
            return self.backends.get("vllm", self.backends["anthropic"])
```

### 5.2 ModelClient Protocol

```python
class ModelClient(Protocol):
    def create_message(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        temperature: float = 0.0,
    ) -> ModelResponse: ...

    def stream_message(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict],
        temperature: float = 0.0,
    ) -> Iterator[StreamEvent]: ...
```

### 5.3 Guardrails Enforcement

In v2, guardrails are enforced at the **ModelRouter level** (Plane C boundary), not inside individual orchestrators. This ensures ALL model calls — regardless of which skill or execution backend — pass through guardrails.

```
Skill Orchestrator
    │
    ▼ messages.create(...)
ModelClient (wrapper)
    │
    ├─ guard_input(prompt)     ← check_input(): token budget, injection, secrets, PII
    │    └─ BLOCK if violation (raise GuardrailViolation)
    │    └─ SCRUB secrets from prompt text
    │
    ├─ Forward to model backend (Anthropic API / OCI GenAI / vLLM)
    │
    ├─ guard_output(response)  ← check_output(): OCI validation, compliance, AWS leaks
    │    └─ WARN / FLAG (never block output — let reviewer handle)
    │
    └─ Return response with guardrail_flags attached
```

### 5.4 Knowledge Store

| Store | Current | v2 |
|-------|---------|-----|
| `service_mappings` | 161 OCI TF resource types in PostgreSQL | Unchanged, add pgvector column (future) |
| `iam_mappings` | AWS action → OCI permission in PostgreSQL | Unchanged, add pgvector column (future) |
| RAG search | Keyword ILIKE via `rag/search.py` | Unchanged (Phase 1); pgvector semantic search (Phase 3+) |
| OCI reference docs | `backend/docs/core/` + `backend/docs/services/` | Unchanged; future: index into pgvector |

---

## 6. Component & Responsibilities Table

| Component | Plane | File(s) | Responsibility | Status |
|-----------|-------|---------|---------------|--------|
| React Frontend | A | `frontend/src/` | UI, user interactions, SSE consumption | **Unchanged** |
| FastAPI Platform API | A | `backend/app/api/*.py` | REST endpoints, auth, CORS, SSE | **Unchanged** (CORS tightened) |
| PostgreSQL | A | `backend/app/db/` | Persistence: tenants, migrations, jobs, artifacts | **2 new tables** |
| Redis / ARQ | A | `backend/app/services/` | Job queue (optional, fallback to subprocess) | **Unchanged** |
| JobDispatcher | A | `backend/app/execution/job_dispatcher.py` | **NEW** — orchestrates job lifecycle | **New** |
| SkillRegistry | A | `backend/app/execution/skill_registry.py` | **NEW** — declarative skill→orchestrator map | **New** |
| CredentialMinter | A | `backend/app/execution/credential_minter.py` | **NEW** — scoped credential issuance | **New** |
| InputBuilder | A | `backend/app/execution/input_builder.py` | **NEW** — extracted from job_runner.py | **New** (logic preserved) |
| ExecutionBackend | B | `backend/app/execution/interfaces.py` | **NEW** — ABC for execution backends | **New** |
| LocalExecutor | B | `backend/app/execution/local_executor.py` | **NEW** — wraps current in-process execution | **New** (behavior preserved) |
| ContainerExecutor | B | `backend/app/execution/container_executor.py` | **NEW** — Docker-isolated execution | **New** (Phase 2) |
| SandboxExecutor | B | `backend/app/execution/sandbox_executor.py` | **NEW** — NemoClaw/OpenShell execution | **New** (Phase 3) |
| WorkerEntrypoint | B | `backend/app/execution/worker_entrypoint.py` | **NEW** — container/sandbox entry point | **New** (Phase 2) |
| OrchestratorAdapter | B | `backend/app/execution/orchestrator_adapter.py` | **NEW** — JobContext → orchestrator.run() | **New** |
| BaseTranslationOrchestrator | B | `backend/app/skills/shared/base_orchestrator.py` | Enhancement→Review→Fix loop | **Unchanged** |
| 8 Skill Orchestrators | B | `backend/app/skills/*/orchestrator.py` | AWS→OCI translation logic | **Unchanged** |
| Synthesis Orchestrator | B | `backend/app/skills/synthesis/orchestrator.py` | Cross-skill artifact synthesis | **Unchanged** |
| AgentLogger | B | `backend/app/skills/shared/agent_logger.py` | Session & cost tracking | **Unchanged** |
| ModelRouter | C | `backend/app/gateway/model_router.py` | **NEW** — unified model backend routing | **New** |
| ModelClient Protocol | C | `backend/app/gateway/model_client.py` | **NEW** — abstract model interface | **New** |
| Guardrails | C | `backend/app/gateway/guardrails.py` | Input/output validation | **Hardened** (mandatory) |
| model_gateway.py | C | `backend/app/gateway/model_gateway.py` | Client factory, secret scrubbing | **Refactored** |
| agent_adapter.py | C | `backend/app/gateway/agent_adapter.py` | Claude Code OAuth adapter | **Gated** by config flag |
| Knowledge Store | C | `backend/app/db/models.py` + `backend/app/rag/` | Service/IAM mappings, RAG search | **Unchanged** |

---

## 7. Interface Definitions

### 7.1 SkillDefinition

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class ModelRequirements:
    """Model assignments for each agent role in the orchestration loop."""
    enhancement: str = "claude-opus-4-6"
    review: str = "claude-sonnet-4-6"
    fix: str = "claude-sonnet-4-6"

@dataclass(frozen=True)
class SkillDefinition:
    """Immutable declaration of a translation skill's properties."""
    skill_type: str                          # e.g., "network_translation"
    display_name: str                        # e.g., "Network → OCI VCN"
    orchestrator_module: str                 # e.g., "backend.app.skills.network_translation.orchestrator"
    orchestrator_class: str                  # e.g., "NetworkTranslationOrchestrator"
    model_requirements: ModelRequirements = field(default_factory=ModelRequirements)
    max_iterations: int = 3
    timeout_seconds: int = 300
    requires_aws_credentials: bool = False
    input_mode: str = "single_resource"      # "single_resource" | "aggregated" | "synthesis"
    aggregation_types: tuple[str, ...] = ()  # AWS resource types to aggregate
    description: str = ""
```

### 7.2 ScopedCredentials

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class ScopedCredentials:
    """Time-boxed, least-privilege credentials for a single job execution.

    These credentials cross Boundary 1 (Control → Execution) and are the ONLY
    secrets that enter Plane B. They are:
    - Scoped: only the permissions needed for this specific job
    - Time-limited: expires_at enforced; 15-min TTL for AWS STS
    - Rotatable: new credentials minted per job execution
    """
    # Model API access
    model_api_token: str                     # Anthropic API key or scoped token
    model_api_base_url: str = "https://api.anthropic.com"

    # AWS access (optional — only for skills that need live AWS reads)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None  # STS temporary session, 15-min TTL
    aws_region: Optional[str] = None

    # Expiration
    expires_at: datetime = None              # Earliest expiry of any credential component

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.utcnow() >= self.expires_at

    def to_env_dict(self) -> dict[str, str]:
        """Serialize for container/sandbox env injection."""
        env = {
            "MODEL_API_TOKEN": self.model_api_token,
            "MODEL_API_BASE_URL": self.model_api_base_url,
        }
        if self.aws_session_token:
            env["AWS_ACCESS_KEY_ID"] = self.aws_access_key_id
            env["AWS_SECRET_ACCESS_KEY"] = self.aws_secret_access_key
            env["AWS_SESSION_TOKEN"] = self.aws_session_token
            env["AWS_DEFAULT_REGION"] = self.aws_region
        return env
```

### 7.3 JobContext

```python
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import json

@dataclass
class JobContext:
    """Immutable context passed across Boundary 1 into the Execution Plane.

    This is the ONLY data structure that crosses from Plane A → Plane B.
    It contains everything the execution backend needs and nothing more.
    """
    # Identity
    job_id: str                              # UUID of TranslationJob
    tenant_id: str                           # UUID of owning tenant (for audit only)

    # Skill definition
    skill_definition: SkillDefinition

    # Input
    input_content: str                       # Pre-built JSON/YAML for the skill
    config: dict[str, Any] = field(default_factory=dict)  # Skill-specific config

    # Credentials (scoped, time-limited)
    credentials: ScopedCredentials = None

    # Callbacks (only used by LocalExecutor — serialized contexts use message queue)
    progress_callback: Optional[Callable] = field(default=None, repr=False)

    def to_json(self) -> str:
        """Serialize for container/sandbox transport. Excludes callbacks."""
        return json.dumps({
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "skill_definition": {
                "skill_type": self.skill_definition.skill_type,
                "orchestrator_module": self.skill_definition.orchestrator_module,
                "orchestrator_class": self.skill_definition.orchestrator_class,
                "max_iterations": self.skill_definition.max_iterations,
                "timeout_seconds": self.skill_definition.timeout_seconds,
            },
            "input_content": self.input_content,
            "config": self.config,
        })

    @classmethod
    def from_json(cls, data: str) -> "JobContext":
        """Deserialize inside container/sandbox."""
        d = json.loads(data)
        return cls(
            job_id=d["job_id"],
            tenant_id=d["tenant_id"],
            skill_definition=SkillDefinition(**d["skill_definition"]),
            input_content=d["input_content"],
            config=d.get("config", {}),
            # credentials come from env vars, not JSON
            # progress_callback set up by worker_entrypoint
        )
```

### 7.4 JobResult

```python
from dataclasses import dataclass, field
from typing import Any, Optional
import json

@dataclass
class JobResult:
    """Result returned from Plane B → Plane A after skill execution.

    This is the ONLY data structure that crosses back from Plane B → Plane A.
    """
    success: bool
    artifacts: dict[str, str] = field(default_factory=dict)  # filename → content
    confidence: float = 0.0                  # 0.0–1.0
    decision: str = "UNKNOWN"                # APPROVED | APPROVED_WITH_NOTES | NEEDS_FIXES | ERROR
    iterations: int = 0
    cost: float = 0.0                        # Total USD
    interactions: list[dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None              # Error message if success=False
    guardrail_flags: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps({
            "success": self.success,
            "artifacts": self.artifacts,
            "confidence": self.confidence,
            "decision": self.decision,
            "iterations": self.iterations,
            "cost": self.cost,
            "interactions": self.interactions,
            "error": self.error,
            "guardrail_flags": self.guardrail_flags,
        })

    @classmethod
    def from_json(cls, data: str) -> "JobResult":
        d = json.loads(data)
        return cls(**d)

    @classmethod
    def from_error(cls, error: str) -> "JobResult":
        return cls(success=False, error=error, decision="ERROR")
```

### 7.5 SkillExecutor

```python
from abc import ABC, abstractmethod

class SkillExecutor(ABC):
    """Wraps a single skill orchestrator to execute within a JobContext."""

    @abstractmethod
    def execute(self, context: JobContext) -> JobResult:
        """Run the skill and return results.

        This method is called inside the execution backend (in-process,
        container, or sandbox). It receives a fully-formed JobContext and
        must return a JobResult.
        """
        ...
```

### 7.6 ExecutionBackend

```python
from abc import ABC, abstractmethod
from typing import Any

class ExecutionBackend(ABC):
    """Abstract base for pluggable execution environments.

    Selected via EXECUTION_BACKEND config:
      "local"     → LocalExecutor (v1, default)
      "container" → ContainerExecutor (v1.5)
      "sandbox"   → SandboxExecutor (v2+)
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Start up the backend (e.g., connect to Docker, verify sandbox)."""
        ...

    @abstractmethod
    async def execute_job(self, context: JobContext) -> JobResult:
        """Execute a translation job and return results."""
        ...

    @abstractmethod
    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job. Returns True if successfully cancelled."""
        ...

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Return backend health status.

        Returns:
            {
                "healthy": bool,
                "backend": str,        # "local" | "container" | "sandbox"
                "active_jobs": int,
                "details": dict,       # Backend-specific details
            }
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Gracefully shut down the backend."""
        ...
```

### 7.7 ModelClient Protocol

```python
from typing import Protocol, Iterator, Any, Optional
from dataclasses import dataclass

@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

@dataclass
class ModelResponse:
    content: str
    usage: TokenUsage
    stop_reason: str = "end_turn"
    model: str = ""
    guardrail_flags: list[dict] = None

class ModelClient(Protocol):
    """Protocol for model backend clients.

    All model interactions in the platform go through this interface,
    enabling backend swapping (Anthropic → OCI GenAI → vLLM) without
    changing any orchestrator code.

    Implementations:
    - AnthropicModelClient: wraps anthropic.Anthropic
    - AgentSDKModelClient: wraps AgentSDKClient (Claude Code OAuth)
    - OCIGenAIModelClient: wraps OCI GenAI SDK (future)
    - VLLMModelClient: wraps vLLM OpenAI-compatible API (future)
    """

    def create_message(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
    ) -> ModelResponse: ...

    def stream_message(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
    ) -> Iterator[Any]: ...
```

---

## 8. Data Flow Diagrams

### 8.1 Job Lifecycle (Happy Path)

```
User                    Plane A (Control)              Plane B (Execution)         Plane C (Model)
 │                           │                              │                          │
 │  POST /api/translation-   │                              │                          │
 │  jobs {skill_type,        │                              │                          │
 │       input_content}      │                              │                          │
 │ ─────────────────────────>│                              │                          │
 │                           │                              │                          │
 │                    ┌──────┤  Create TranslationJob       │                          │
 │                    │  DB  │  status='queued'             │                          │
 │                    └──────┤                              │                          │
 │                           │                              │                          │
 │  201 {job_id, status}     │                              │                          │
 │ <─────────────────────────│                              │                          │
 │                           │                              │                          │
 │  GET /stream?token=...    │                              │                          │
 │ ─────────────────────────>│                              │                          │
 │  SSE: status=queued       │                              │                          │
 │ <─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│                              │                          │
 │                           │                              │                          │
 │                    ┌──────────────────────────┐          │                          │
 │                    │ JobDispatcher.dispatch()  │          │                          │
 │                    │                          │          │                          │
 │                    │ 1. Load job from DB       │          │                          │
 │                    │ 2. SkillRegistry.get()    │          │                          │
 │                    │ 3. InputBuilder.build()   │          │                          │
 │                    │ 4. CredentialMinter.mint() │          │                          │
 │                    │ 5. Build JobContext        │          │                          │
 │                    └──────────┬───────────────┘          │                          │
 │                               │                          │                          │
 │                               │  execute_job(context)    │                          │
 │                               │ ────────────────────────>│                          │
 │                               │                          │                          │
 │                               │                    ┌─────┤  OrchestratorAdapter     │
 │                               │                    │     │  loads orchestrator      │
 │  SSE: phase=gap_analysis      │                    │     │                          │
 │ <─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│                    │     │  Gap analysis            │
 │                               │                    │     │                          │
 │  SSE: phase=enhancement,i=1   │                    │     │  Enhancement agent       │
 │ <─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│                    │     │ ─────────────────────────>│
 │                               │                    │     │                          │
 │                               │                    │     │  guard_input(prompt)     │
 │                               │                    │     │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─>│
 │                               │                    │     │                          │
 │                               │                    │     │  Anthropic API / OCI     │
 │                               │                    │     │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─>│
 │                               │                    │     │                          │
 │                               │                    │     │  guard_output(response)  │
 │                               │                    │     │  <─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
 │                               │                    │     │                          │
 │  SSE: phase=review,i=1        │                    │     │  Review agent            │
 │ <─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│                    │     │ ─────────────────────────>│
 │                               │                    │     │                          │
 │  SSE: phase=fix,i=1           │                    │     │  Fix agent (if needed)   │
 │ <─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│                    │     │ ─────────────────────────>│
 │                               │                    │     │                          │
 │                               │                    │     │  ... iterations 2-3      │
 │                               │                    └─────┤                          │
 │                               │                          │                          │
 │                               │  JobResult               │                          │
 │                               │ <────────────────────────│                          │
 │                               │                          │                          │
 │                    ┌──────────┤  Persist:                │                          │
 │                    │  DB      │  - artifacts             │                          │
 │                    │          │  - interactions          │                          │
 │                    │          │  - status='complete'     │                          │
 │                    └──────────┤  - confidence, cost      │                          │
 │                               │                          │                          │
 │  SSE: status=complete         │                          │                          │
 │ <─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│                          │                          │
 │                               │                          │                          │
 │  GET /artifacts/{id}/download │                          │                          │
 │ ─────────────────────────────>│                          │                          │
 │  terraform files              │                          │                          │
 │ <─────────────────────────────│                          │                          │
```

### 8.2 Credential Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│                    CREDENTIAL LIFECYCLE                                   │
└──────────────────────────────────────────────────────────────────────────┘

1. STORAGE (at rest)
   ┌──────────────┐
   │  PostgreSQL   │
   │               │
   │  aws_connections.credentials  ──── Fernet-encrypted (NEW)
   │  Key source: OCI Vault / KMS     (currently: plaintext — FIXED in Phase 1)
   │               │
   │  ANTHROPIC_API_KEY ──── Environment variable (never in DB)
   └──────────────┘

2. MINTING (per job)
   ┌──────────────────────────────────────────────────────┐
   │  CredentialMinter.mint(tenant_id, skill_definition)  │
   │                                                      │
   │  Input:                                              │
   │    - tenant_id → lookup AWSConnection (decrypt)      │
   │    - skill_def.requires_aws_credentials → bool       │
   │                                                      │
   │  If requires_aws_credentials:                        │
   │    sts.assume_role(                                  │
   │      RoleArn=<migration-reader-role>,                │
   │      DurationSeconds=900,  # 15 minutes              │
   │      Policy=<inline-scoped-to-skill>,                │
   │    )                                                 │
   │                                                      │
   │  Output: ScopedCredentials(                          │
   │    model_api_token=ANTHROPIC_API_KEY,                │
   │    model_api_base_url=settings.MODEL_API_BASE_URL,   │
   │    aws_session_token=<STS temporary>,                │
   │    expires_at=now + 15min,                           │
   │  )                                                   │
   └──────────────────────────────────────────────────────┘

3. TRANSPORT (Boundary 1: Control → Execution)
   ┌──────────────────────────────────────────────┐
   │  LocalExecutor:   In-memory (same process)   │
   │  ContainerExecutor: env vars in docker run   │
   │  SandboxExecutor:  HOST-SIDE proxy injection │
   └──────────────────────────────────────────────┘

4. USAGE (Execution Plane)
   ┌──────────────────────────────────────────────────┐
   │  Orchestrator calls client.messages.create()     │
   │  Client uses model_api_token in Authorization    │
   │  Token checked for expiry before each call       │
   └──────────────────────────────────────────────────┘

5. EXPIRY
   ┌──────────────────────────────────────────────────┐
   │  ScopedCredentials.expires_at checked by:        │
   │  - ModelClient before each API call              │
   │  - ContainerExecutor watchdog (kills container)  │
   │  - SandboxExecutor gateway (rejects proxy req)   │
   │                                                  │
   │  On expiry: job fails with CREDENTIAL_EXPIRED    │
   │  (no silent renewal — fail safe)                 │
   └──────────────────────────────────────────────────┘
```

### 8.3 Execution Backend Selection

```
settings.EXECUTION_BACKEND
          │
          ├── "local"     ──→ LocalExecutor
          │                     └─ In-process, same event loop
          │                     └─ progress_callback: direct DB write
          │                     └─ Isolation: NONE (same as v1)
          │
          ├── "container" ──→ ContainerExecutor
          │                     └─ Docker container per job
          │                     └─ progress_callback: stdout JSON lines → reader thread
          │                     └─ Isolation: process, filesystem, network
          │
          └── "sandbox"   ──→ SandboxExecutor
                                └─ NemoClaw/OpenShell sandbox per job
                                └─ progress_callback: sandbox stdout → OpenShell API
                                └─ Isolation: Landlock, seccomp, network namespace
                                └─ Credentials: HOST-SIDE only (proxied)
```

---

## 9. Security Architecture

### 9.1 Security Boundaries

```
┌──────────────────────────────────────────────────────────────────┐
│ BOUNDARY 1: Control Plane → Execution Plane                      │
│                                                                  │
│ ALLOWED to cross:                                                │
│   ✓ JobContext (scrubbed input, scoped credentials, metadata)    │
│   ✓ ScopedCredentials (time-limited, least-privilege)            │
│   ✓ Progress callbacks (phase, iteration — no data content)      │
│                                                                  │
│ NEVER crosses:                                                   │
│   ✗ Database connection strings                                  │
│   ✗ JWT_SECRET                                                   │
│   ✗ Full AWS long-lived credentials                              │
│   ✗ Other tenants' data                                          │
│   ✗ Tenant passwords / password hashes                           │
│   ✗ Redis connection URL                                         │
│   ✗ OCI Vault encryption keys                                    │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ BOUNDARY 2: Execution Plane → Model Plane                        │
│                                                                  │
│ ALLOWED to cross:                                                │
│   ✓ Model API requests (Authorization: Bearer <scoped_token>)    │
│   ✓ Scrubbed prompts (secrets removed by guardrails)             │
│   ✓ Model name and parameters (temperature, max_tokens)          │
│                                                                  │
│ NEVER crosses:                                                   │
│   ✗ Database contents                                            │
│   ✗ Tenant PII (emails, phone numbers — scrubbed)                │
│   ✗ Raw AWS API keys (only STS temporary tokens)                 │
│   ✗ Internal metadata (job IDs, tenant IDs)                      │
└──────────────────────────────────────────────────────────────────┘
```

### 9.2 Isolation Per Execution Backend

| Property | LocalExecutor | ContainerExecutor | SandboxExecutor |
|----------|--------------|-------------------|-----------------|
| **Process isolation** | None (same process) | Full (container) | Full (sandbox) |
| **Filesystem isolation** | None | Read-only root + tmpfs /sandbox | Landlock: r/o /usr,/lib; r/w /sandbox,/tmp only |
| **Network isolation** | None | Docker network: model endpoint only | Network namespace: model endpoint only |
| **Credential access** | In-memory | Env vars (cleared on exit) | **Never enters sandbox** (host-side proxy) |
| **User context** | Application user | Non-root (UID 1000) | Non-root + seccomp |
| **Resource limits** | None | --memory=2g --cpus=2 | Sandbox resource quotas |
| **Audit** | Application logs | Container logs + exit code | Sandbox execution log |
| **Kill mechanism** | In-process cancellation | docker stop + docker rm | Sandbox termination API |

### 9.3 Security Hardening (Phase 1 — Immediate)

#### 9.3.1 Encrypt AWS Credentials at Rest

**Current state:** `aws_connections.credentials` stored as plaintext `Text` column in `models.py:57`.

**Fix:**

```python
# backend/app/services/credential_encryption.py (NEW)
from cryptography.fernet import Fernet
import os

_FERNET_KEY = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
# In production: loaded from OCI Vault KMS

def encrypt_credentials(plaintext: str) -> str:
    """Encrypt credentials before DB storage."""
    if not _FERNET_KEY:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY not configured")
    f = Fernet(_FERNET_KEY.encode())
    return f.encrypt(plaintext.encode()).decode()

def decrypt_credentials(ciphertext: str) -> str:
    """Decrypt credentials from DB storage."""
    if not _FERNET_KEY:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY not configured")
    f = Fernet(_FERNET_KEY.encode())
    return f.decrypt(ciphertext.encode()).decode()
```

**Migration:** Alembic migration to re-encrypt existing plaintext credentials.

#### 9.3.2 Make Guardrails Mandatory

**Current state:** `base_orchestrator.py:170-175` wraps guardrails in `try/except ImportError`, making them silently optional.

**Fix:** Remove the try/except. Guardrails are a required dependency. If the import fails, the skill fails — this is the correct behavior for production.

```python
# BEFORE (base_orchestrator.py:170-175)
try:
    from backend.app.gateway.guardrails import check_input, check_output
except ImportError:
    check_input = lambda text, skill_type: {"action": "allow", "scrubbed_text": text}
    check_output = lambda text, skill_type: {"flags": []}

# AFTER
from backend.app.gateway.guardrails import check_input, check_output
# No fallback. If guardrails can't load, skill execution fails.
```

#### 9.3.3 Lock Down CORS

**Current state:** `main.py:23` allows all origins with credentials:

```python
allow_origins=["*"], allow_credentials=True  # DANGEROUS
```

**Fix:**

```python
# Read allowed origins from config
ALLOWED_ORIGINS = settings.CORS_ALLOWED_ORIGINS.split(",") if settings.CORS_ALLOWED_ORIGINS else [
    "http://localhost:5173",   # Vite dev server
    "http://localhost:3000",   # Alternative dev port
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
```

#### 9.3.4 Gate Agent SDK Fallback

**Current state:** `model_gateway.py` automatically falls back to `AgentSDKClient` (Claude Code OAuth) when no `ANTHROPIC_API_KEY` is set. This is appropriate for development but should be explicitly opt-in for production.

**Fix:** New config flag `ALLOW_AGENT_SDK_FALLBACK` (default: `false`).

```python
# model_gateway.py
def get_anthropic_client(api_key: str | None = None) -> Anthropic:
    key = api_key or settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_AUTH_TOKEN
    if key:
        return Anthropic(api_key=key)

    if settings.ALLOW_AGENT_SDK_FALLBACK:
        from backend.app.gateway.agent_adapter import AgentSDKClient
        return AgentSDKClient()

    raise RuntimeError(
        "No ANTHROPIC_API_KEY configured and ALLOW_AGENT_SDK_FALLBACK=false. "
        "Set ANTHROPIC_API_KEY or enable ALLOW_AGENT_SDK_FALLBACK for development."
    )
```

#### 9.3.5 PII Blocking in Enterprise Mode

**Current state:** `guardrails.py` detects PII (emails, phone numbers, SSNs) but only warns.

**Fix:** New config flag `ENTERPRISE_MODE` (default: `false`). When enabled, PII detection blocks the request instead of warning.

```python
# guardrails.py check_input()
if pii_found:
    if settings.ENTERPRISE_MODE:
        return {"action": "block", "reason": f"PII detected: {pii_types}"}
    else:
        return {"action": "allow", "warnings": [f"PII detected: {pii_types}"], ...}
```

### 9.4 Tenant Isolation

All database queries are scoped to `tenant_id` (existing pattern — unchanged). The `JobContext` carries `tenant_id` for audit logging only; execution backends cannot use it to access other tenants' data because they have no database access.

```
Tenant A ──→ JobContext(tenant_id=A) ──→ Execution ──→ JobResult
Tenant B ──→ JobContext(tenant_id=B) ──→ Execution ──→ JobResult

Execution Plane has NO database access.
Execution Plane has NO knowledge of other tenants.
tenant_id in JobContext is for audit trail only.
```

---

## 10. Data Models

### 10.1 Existing Models (Unchanged)

| Model | Table | Columns | Notes |
|-------|-------|---------|-------|
| `Tenant` | `tenants` | id, email, password_hash, created_at | |
| `AWSConnection` | `aws_connections` | id, tenant_id, name, region, credential_type, credentials, status, created_at | **credentials column: encrypted (Phase 1)** |
| `Migration` | `migrations` | id, tenant_id, aws_connection_id, name, status, created_at | |
| `Resource` | `resources` | id, tenant_id, migration_id, aws_connection_id, aws_type, aws_arn, name, raw_config, status, created_at | |
| `TranslationJob` | `translation_jobs` | id, tenant_id, migration_id, skill_type, input_resource_id, input_content, config, status, current_phase, current_iteration, confidence, total_cost_usd, output, errors, started_at, completed_at, created_at | |
| `TranslationJobInteraction` | `translation_job_interactions` | id, translation_job_id, agent_type, model, iteration, tokens_*, cost_usd, decision, confidence, issues, duration_seconds, created_at | |
| `Artifact` | `artifacts` | id, translation_job_id, tenant_id, file_type, file_name, content_type, data, created_at | |
| `ServiceMapping` | `service_mappings` | id, aws_service, aws_resource_type, oci_service, oci_resource_type, terraform_resource, notes | |
| `IAMMapping` | `iam_mappings` | id, aws_action, aws_service, oci_permission, oci_service, notes | |
| `MigrationPlan` | `migration_plans` | id, migration_id, tenant_id, status, generated_at, summary | |
| `PlanPhase` | `plan_phases` | id, plan_id, tenant_id, name, description, order_index, status | |
| `Workload` | `workloads` | id, phase_id, tenant_id, name, description, skill_type, status, translation_job_id | |
| `WorkloadResource` | `workload_resources` | id, workload_id, resource_id | |

### 10.2 New Models

#### ExecutionLog (New)

Tracks execution backend activity for audit and debugging.

```python
class ExecutionLog(Base):
    """Audit log for execution backend activity."""
    __tablename__ = "execution_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    translation_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("translation_jobs.id"))
    backend_type: Mapped[str]         # "local" | "container" | "sandbox"
    container_id: Mapped[Optional[str]]  # Docker container ID (container backend)
    sandbox_id: Mapped[Optional[str]]    # NemoClaw sandbox ID (sandbox backend)
    started_at: Mapped[datetime]
    completed_at: Mapped[Optional[datetime]]
    exit_code: Mapped[Optional[int]]
    resource_usage: Mapped[Optional[dict]] = mapped_column(JSONB)  # CPU, memory, duration
    credential_expires_at: Mapped[Optional[datetime]]  # When scoped creds expire
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

#### GuardrailEvent (New)

Records guardrail violations and flags for compliance auditing.

```python
class GuardrailEvent(Base):
    """Audit log for guardrail activations."""
    __tablename__ = "guardrail_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    translation_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("translation_jobs.id"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"))
    event_type: Mapped[str]           # "input_block" | "input_scrub" | "output_flag" | "pii_detect"
    severity: Mapped[str]             # "info" | "warning" | "critical"
    details: Mapped[dict] = mapped_column(JSONB)  # Pattern matched, action taken
    agent_type: Mapped[Optional[str]] # Which agent triggered it
    iteration: Mapped[Optional[int]]
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

### 10.3 Modified Models

#### TranslationJob — New Columns

```python
# Add to existing TranslationJob model
execution_backend: Mapped[Optional[str]]   # "local" | "container" | "sandbox"
execution_log_id: Mapped[Optional[uuid.UUID]] = mapped_column(
    ForeignKey("execution_logs.id")
)
```

#### AWSConnection — Column Modification

```python
# credentials column: no schema change, but value is now Fernet-encrypted
# Application-level encrypt/decrypt via credential_encryption.py
credentials: Mapped[Optional[str]] = mapped_column(Text)  # Fernet-encrypted JSON
```

---

## 11. API Contracts

### 11.1 Existing Endpoints (Unchanged)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/auth/register` | Create tenant |
| `POST` | `/api/auth/login` | Authenticate, return JWT |
| `POST` | `/api/aws/connections` | Add AWS connection |
| `GET` | `/api/aws/connections` | List connections |
| `POST` | `/api/migrations` | Create migration |
| `GET` | `/api/migrations` | List migrations |
| `POST` | `/api/migrations/{id}/extract` | Extract all resources |
| `POST` | `/api/migrations/{id}/extract/instance` | Extract single instance |
| `GET` | `/api/aws/resources` | List resources |
| `POST` | `/api/translation-jobs` | Create translation job |
| `GET` | `/api/translation-jobs` | List jobs |
| `GET` | `/api/translation-jobs/{id}` | Get job details |
| `DELETE` | `/api/translation-jobs/{id}` | Cancel/delete job |
| `GET` | `/api/translation-jobs/{id}/stream` | SSE progress stream |
| `GET` | `/api/translation-jobs/{id}/interactions` | List interactions |
| `GET` | `/api/translation-jobs/{id}/artifacts` | List artifact metadata |
| `GET` | `/artifacts/{id}/download` | Download artifact |
| `POST` | `/api/artifacts/download-zip` | Download multiple as ZIP |
| `POST` | `/api/migrations/{id}/plan` | Generate migration plan |
| `GET` | `/api/migrations/{id}/plan` | Get migration plan |
| `POST` | `/api/workloads/{id}/run` | Execute workload job |
| `GET` | `/api/rag/service-mappings` | Search service mappings |
| `GET` | `/api/rag/iam-mappings` | Search IAM mappings |
| `GET` | `/health` | Health check |

### 11.2 New Endpoints

#### GET /api/admin/execution/health

Returns health status of the configured execution backend.

```json
// Request
GET /api/admin/execution/health
Authorization: Bearer <admin_jwt>

// Response 200
{
    "healthy": true,
    "backend": "container",
    "active_jobs": 3,
    "details": {
        "docker_version": "24.0.7",
        "available_memory_gb": 12.5,
        "container_count": 3,
        "network": "model-only"
    }
}
```

#### GET /api/admin/execution/logs

List execution logs for debugging and audit.

```json
// Request
GET /api/admin/execution/logs?job_id=<uuid>&backend_type=container&limit=50
Authorization: Bearer <admin_jwt>

// Response 200
{
    "logs": [
        {
            "id": "uuid",
            "translation_job_id": "uuid",
            "backend_type": "container",
            "container_id": "abc123",
            "started_at": "2026-03-26T10:00:00Z",
            "completed_at": "2026-03-26T10:03:45Z",
            "exit_code": 0,
            "resource_usage": {
                "cpu_seconds": 42.3,
                "peak_memory_mb": 512,
                "duration_seconds": 225
            }
        }
    ]
}
```

#### GET /api/admin/guardrail-events

List guardrail events for compliance audit.

```json
// Request
GET /api/admin/guardrail-events?tenant_id=<uuid>&severity=critical&limit=100
Authorization: Bearer <admin_jwt>

// Response 200
{
    "events": [
        {
            "id": "uuid",
            "translation_job_id": "uuid",
            "tenant_id": "uuid",
            "event_type": "input_block",
            "severity": "critical",
            "details": {
                "pattern": "prompt_injection",
                "matched": "ignore previous instructions",
                "action": "blocked"
            },
            "created_at": "2026-03-26T10:00:00Z"
        }
    ]
}
```

#### GET /api/translation-jobs/{id}/execution-log

Get execution metadata for a specific job.

```json
// Request
GET /api/translation-jobs/{id}/execution-log
Authorization: Bearer <jwt>

// Response 200
{
    "backend_type": "container",
    "container_id": "abc123def456",
    "started_at": "2026-03-26T10:00:00Z",
    "completed_at": "2026-03-26T10:03:45Z",
    "exit_code": 0,
    "credential_expires_at": "2026-03-26T10:15:00Z",
    "resource_usage": {
        "cpu_seconds": 42.3,
        "peak_memory_mb": 512
    }
}
```

### 11.3 Modified Endpoints

#### POST /api/translation-jobs — Response Addition

The response now includes `execution_backend`:

```json
{
    "id": "uuid",
    "skill_type": "network_translation",
    "status": "queued",
    "execution_backend": "container",
    // ... existing fields unchanged
}
```

---

## 12. Tech Stack Decisions

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Frontend** | React 19 + Vite 8 + TypeScript 5.9 | Existing; React 19 concurrent features for SSE; Vite for fast builds |
| **State Management** | TanStack Query 5 | Existing; excellent for server-state + SSE integration |
| **Styling** | Tailwind 4 | Existing; utility-first CSS, no component library lock-in |
| **API Framework** | FastAPI 0.115+ | Existing; async-native, automatic OpenAPI, dependency injection |
| **ORM** | SQLAlchemy 2.0 (async) | Existing; mature, type-safe with mapped_column |
| **Database** | PostgreSQL 15+ | Existing; JSONB for configs, future pgvector for RAG |
| **Job Queue** | Redis + ARQ | Existing; lightweight, async-native; fallback to subprocess |
| **AI SDK** | anthropic >= 0.40.0 | Existing; direct Anthropic API client |
| **Agent SDK** | claude_agent_sdk | Existing (optional); Claude Code OAuth fallback |
| **AWS SDK** | boto3 | Existing; resource discovery + STS credential minting |
| **Container Runtime** | Docker 24+ | **New (Phase 2)**; industry standard, OCI-compatible |
| **Credential Encryption** | cryptography (Fernet) | **New (Phase 1)**; symmetric encryption, key from OCI Vault |
| **Sandbox** | NemoClaw/OpenShell | **New (Phase 3)**; enterprise-grade sandbox with Landlock + seccomp |
| **Migrations** | Alembic | Existing; handles new tables + column modifications |
| **Testing** | pytest + pytest-asyncio + httpx | Existing; async test support |

### Why NOT These Alternatives

| Alternative | Rejected Because |
|-------------|-----------------|
| Celery (instead of ARQ) | Heavier, requires separate broker; ARQ is async-native and already integrated |
| Kubernetes Jobs (instead of Docker) | Too much infrastructure for Phase 2; Helm chart already planned for Phase 3+ |
| HashiCorp Vault (instead of OCI Vault + Fernet) | Additional infrastructure dependency; Fernet + OCI Vault KMS is simpler for single-key rotation |
| gVisor (instead of NemoClaw) | NemoClaw provides OpenShell gateway for credential proxy; gVisor would need custom proxy work |
| LangChain/LlamaIndex | Over-abstraction for our use case; direct anthropic SDK gives full control |
| Server Components (React) | Not needed; TanStack Query handles server-state well; SSE is already working |

---

## 13. Architecture Decision Records

### ADR-001: Execution Plane Abstraction

**Status:** Accepted
**Date:** 2026-03-26
**Context:** The current `job_runner.py` (540 lines) directly invokes skill orchestrators in-process with no isolation boundary. Enterprise customers require process isolation, credential scoping, and eventual sandbox execution for compliance. However, changing all 8 skill orchestrators is high-risk and unnecessary.

**Decision:** Introduce an `ExecutionBackend` ABC with three implementations (Local, Container, Sandbox) selected by config. The orchestrators remain unchanged — they already accept an injected `client` and `progress_callback`.

**Consequences:**
- (+) Zero changes to any of the 8 skill orchestrators
- (+) `job_runner.py` decomposed into focused components (JobDispatcher, InputBuilder, CredentialMinter)
- (+) Each execution backend can be tested independently
- (+) Backend selection via single env var (`EXECUTION_BACKEND=local|container|sandbox`)
- (-) Slight increase in abstraction layers (3 new interfaces)
- (-) ContainerExecutor and SandboxExecutor add operational complexity

**Alternatives Considered:**
1. **Refactor all orchestrators to be sandbox-aware:** Rejected. High risk, 8 files to modify, violates open/closed principle.
2. **Use Kubernetes Jobs directly:** Rejected. Requires K8s even in dev; too heavy for Phase 1.
3. **Single container model (no local option):** Rejected. Must work on developer laptops without Docker.

---

### ADR-002: Credential Scoping

**Status:** Accepted
**Date:** 2026-03-26
**Context:** Currently, the ANTHROPIC_API_KEY is a long-lived environment variable accessible to the entire application. AWS credentials are stored in plaintext in the database. Any code path can access any credential at any time.

**Decision:** Introduce `CredentialMinter` that produces `ScopedCredentials` per-job with:
- Model API token: passed through (future: per-job rotation via API key management)
- AWS credentials: STS AssumeRole with 15-minute TTL and inline policy scoped to read-only for the skill's required services
- Explicit `expires_at` checked before each model API call

**Consequences:**
- (+) Credential blast radius limited to 15 minutes for AWS
- (+) Even if execution environment is compromised, credentials expire quickly
- (+) Audit trail of credential issuance via ExecutionLog
- (+) SandboxExecutor can proxy model credentials host-side (never enter sandbox)
- (-) STS AssumeRole adds ~200ms latency per job start
- (-) Requires IAM role setup in customer AWS accounts (documented in deployment guide)
- (-) Model API token is still long-lived in Phase 1 (scoped rotation in Phase 3)

**Alternatives Considered:**
1. **No credential scoping (pass env vars):** Rejected. Fails enterprise security requirements.
2. **OAuth per-request tokens:** Rejected. Anthropic API doesn't currently support per-request token issuance.
3. **AWS IAM Roles Anywhere (X.509):** Considered for Phase 3+. More complex but eliminates long-lived AWS keys entirely.

---

### ADR-003: NemoClaw Integration Approach

**Status:** Proposed (Phase 3)
**Date:** 2026-03-26
**Context:** Maximum isolation requires the skill execution to run in a sandbox where it cannot exfiltrate credentials, access the network freely, or modify the host filesystem. NemoClaw (via OpenShell) provides Landlock filesystem isolation, network namespacing, seccomp, and — critically — an inference proxy that can inject credentials host-side.

**Decision:** SandboxExecutor uses OpenShell API to:
1. Create a sandbox with Landlock policy (read-only /usr,/lib; read-write /sandbox,/tmp)
2. Upload the input bundle (context JSON + worker entrypoint)
3. Execute `python -m backend.app.execution.worker_entrypoint` inside the sandbox
4. The sandbox's outbound HTTPS to MODEL_API_BASE_URL is intercepted by the OpenShell gateway
5. The gateway injects the model API token into the Authorization header **host-side**
6. The sandbox process only sees a local proxy URL — it never has the real token
7. Download the output bundle (result JSON) when execution completes

**Consequences:**
- (+) Model API credentials never enter the sandbox
- (+) Filesystem isolation prevents reading host secrets
- (+) Network isolation prevents data exfiltration
- (+) Same worker entrypoint as ContainerExecutor (code reuse)
- (-) Requires NemoClaw/OpenShell infrastructure (not available in all environments)
- (-) Host-side proxy adds ~5ms latency per model API call
- (-) Debugging is harder inside sandboxed execution

**Alternatives Considered:**
1. **AWS Lambda / OCI Functions:** Rejected. Cold start latency (5-10s) unacceptable for interactive translation; 15-min max execution limit may be insufficient.
2. **Firecracker microVMs:** Rejected. More overhead than Landlock, and NemoClaw already provides equivalent isolation.
3. **WebAssembly sandbox (Wasmtime):** Rejected. Python ecosystem not mature enough in Wasm.

---

### ADR-004: Model Plane Separation

**Status:** Accepted
**Date:** 2026-03-26
**Context:** The platform currently hardcodes Anthropic Claude as the only model backend, with model names (`claude-opus-4-6`, `claude-sonnet-4-6`) embedded in orchestrator class constants. Enterprise customers may need to use OCI GenAI Service, self-hosted vLLM, or NemoClaw-proxied endpoints for data sovereignty or cost reasons.

**Decision:** Introduce a `ModelClient` protocol and `ModelRouter` that:
1. Abstract the model API behind a protocol (create_message, stream_message)
2. Route model names to appropriate backends (claude-* → Anthropic, oci-* → OCI GenAI, etc.)
3. Enforce guardrails at the ModelClient wrapper level (not in individual orchestrators)
4. Configure via `MODEL_API_BASE_URL` for private endpoints

**Consequences:**
- (+) Orchestrators don't change — they call `client.messages.create()` as before
- (+) New model backends added without touching skill code
- (+) Guardrails enforced uniformly at one choke point
- (+) Private endpoints for data sovereignty (no data leaves customer network)
- (-) Different models have different capabilities — skills may need model-specific prompts
- (-) ModelClient protocol must be a lowest-common-denominator API
- (-) Testing requires mocks for each backend

**Alternatives Considered:**
1. **LiteLLM proxy:** Considered. Provides OpenAI-compatible proxy for 100+ models. Rejected because it adds an external dependency and we only need 3-4 backends.
2. **Keep Anthropic-only, configure base_url:** Partial solution. Works for Anthropic-compatible endpoints but not for OCI GenAI (different API format).
3. **Abstract at orchestrator level:** Rejected. Would require changing all 8 orchestrators.

---

## 14. What Changes vs What Stays

### Files That STAY (Unchanged)

| File | Lines | Reason |
|------|-------|--------|
| `backend/app/skills/shared/base_orchestrator.py` | ~650 | Core loop works correctly; interface already accepts injected client |
| `backend/app/skills/cfn_terraform/orchestrator.py` | ~811 | Standalone orchestrator; client-injected |
| `backend/app/skills/network_translation/orchestrator.py` | ~505 | BaseTranslationOrchestrator subclass; client-injected |
| `backend/app/skills/ec2_translation/orchestrator.py` | ~400 | BaseTranslationOrchestrator subclass |
| `backend/app/skills/database_translation/orchestrator.py` | ~400 | BaseTranslationOrchestrator subclass |
| `backend/app/skills/storage_translation/orchestrator.py` | ~350 | BaseTranslationOrchestrator subclass |
| `backend/app/skills/loadbalancer_translation/orchestrator.py` | ~400 | BaseTranslationOrchestrator subclass |
| `backend/app/skills/iam_translation/orchestrator.py` | ~500 | BaseTranslationOrchestrator subclass |
| `backend/app/skills/dependency_discovery/orchestrator.py` | ~300 | Standalone orchestrator |
| `backend/app/skills/synthesis/orchestrator.py` | ~350 | Standalone orchestrator |
| `backend/app/skills/shared/agent_logger.py` | ~200 | Session tracking (no coupling to execution) |
| `backend/app/skills/shared/rag.py` | ~100 | RAG search helper |
| `backend/app/skills/shared/session_tracker.py` | ~80 | Token accumulator |
| `backend/app/api/auth.py` | ~60 | JWT registration/login |
| `backend/app/api/aws.py` | ~200 | AWS connection management |
| `backend/app/api/plans.py` | ~150 | Migration plan endpoints |
| `backend/app/api/rag.py` | ~40 | Service/IAM mapping search |
| `backend/app/api/deps.py` | ~30 | JWT auth dependency |
| `backend/app/services/auth_service.py` | ~40 | bcrypt + JWT helpers |
| `backend/app/services/aws_extractor.py` | ~300 | boto3 resource discovery |
| `backend/app/services/migration_orchestrator.py` | ~200 | Plan generation |
| `backend/app/db/base.py` | ~30 | Engine + session factory |
| `backend/app/rag/search.py` | ~50 | Keyword search |
| `frontend/src/**/*` | ~5000+ | All frontend code unchanged |

### Files That CHANGE

| File | Change | Detail |
|------|--------|--------|
| `backend/app/services/job_runner.py` | **Decomposed** | Input aggregation → `InputBuilder`; skill routing → `SkillRegistry`; orchestrator call → `LocalExecutor`; persistence stays in `JobDispatcher`. Old file becomes thin ARQ wrapper calling `JobDispatcher.dispatch()` |
| `backend/app/api/jobs.py` | **Simplified** | Remove `_enqueue_or_run()`, `_run_job_in_process()`, and process management code. Job creation calls `JobDispatcher.dispatch()` (via ARQ or directly). ~100 lines removed |
| `backend/app/gateway/model_gateway.py` | **Refactored** | Add `ModelClient` Protocol; `get_anthropic_client()` becomes `get_model_client()`; add `ALLOW_AGENT_SDK_FALLBACK` gate; move guardrail calls to `ModelClientWrapper` |
| `backend/app/gateway/guardrails.py` | **Hardened** | PII blocking in ENTERPRISE_MODE; guardrail events recorded to DB; no functional changes to existing rules |
| `backend/app/db/models.py` | **Extended** | Add `ExecutionLog`, `GuardrailEvent` models; add `execution_backend`, `execution_log_id` columns to `TranslationJob` |
| `backend/app/config.py` | **Extended** | Add: `EXECUTION_BACKEND`, `MODEL_API_BASE_URL`, `ALLOW_AGENT_SDK_FALLBACK`, `ENTERPRISE_MODE`, `CORS_ALLOWED_ORIGINS`, `CREDENTIAL_ENCRYPTION_KEY` |
| `backend/app/main.py` | **Hardened** | Lock down CORS with `CORS_ALLOWED_ORIGINS`; initialize execution backend in lifespan |
| `backend/app/skills/shared/base_orchestrator.py` | **Tiny fix** | Remove `try/except ImportError` around guardrails import (make mandatory) |

### Files That Are NEW

| File | Purpose |
|------|---------|
| `backend/app/execution/__init__.py` | Package init |
| `backend/app/execution/interfaces.py` | `SkillDefinition`, `ScopedCredentials`, `JobContext`, `JobResult`, `SkillExecutor`, `ExecutionBackend` |
| `backend/app/execution/skill_registry.py` | Declarative skill→orchestrator mapping |
| `backend/app/execution/job_dispatcher.py` | Job lifecycle management (load → mint → dispatch → persist) |
| `backend/app/execution/input_builder.py` | Input aggregation logic (extracted from job_runner.py) |
| `backend/app/execution/credential_minter.py` | Scoped credential issuance |
| `backend/app/execution/local_executor.py` | In-process execution (v1 default) |
| `backend/app/execution/container_executor.py` | Docker-isolated execution (v1.5) |
| `backend/app/execution/sandbox_executor.py` | NemoClaw sandbox execution (v2+) |
| `backend/app/execution/orchestrator_adapter.py` | JobContext → orchestrator.run() bridge |
| `backend/app/execution/worker_entrypoint.py` | Container/sandbox entry point script |
| `backend/app/gateway/model_client.py` | `ModelClient` protocol + `AnthropicModelClient` |
| `backend/app/gateway/model_router.py` | `ModelRouter` for backend selection |
| `backend/app/services/credential_encryption.py` | Fernet encrypt/decrypt for DB credentials |
| `backend/app/api/admin.py` | Admin endpoints (execution health, logs, guardrail events) |
| `docker/Dockerfile.worker` | Worker image for ContainerExecutor |
| `docker/docker-compose.yml` | Development docker-compose |
| `helm/` | Helm chart for Kubernetes deployment |

---

## 15. Phased Implementation Plan

### Phase 1: Abstractions + Security Hardening (v1.0)

**Goal:** Introduce all new interfaces and security fixes. Zero behavior change. LocalExecutor wraps current execution model.

**Duration:** 2-3 weeks

| Step | Task | Files | Verification |
|------|------|-------|-------------|
| 1.1 | Create `backend/app/execution/` package with all interfaces | `interfaces.py` | `python -c "from backend.app.execution.interfaces import *"` |
| 1.2 | Implement `SkillRegistry` | `skill_registry.py` | Unit test: registry resolves all 9 skill types correctly |
| 1.3 | Extract `InputBuilder` from `job_runner.py` | `input_builder.py` | Unit test: identical output for all 5 aggregation modes |
| 1.4 | Implement `CredentialMinter` (pass-through in Phase 1) | `credential_minter.py` | Unit test: returns ScopedCredentials with correct fields |
| 1.5 | Implement `OrchestratorAdapter` | `orchestrator_adapter.py` | Unit test: wraps mock orchestrator correctly |
| 1.6 | Implement `LocalExecutor` | `local_executor.py` | Integration test: run cfn_terraform skill end-to-end |
| 1.7 | Implement `JobDispatcher` | `job_dispatcher.py` | Integration test: full job lifecycle through dispatcher |
| 1.8 | Refactor `job_runner.py` to delegate to `JobDispatcher` | `job_runner.py` | All existing tests pass with zero behavior change |
| 1.9 | Simplify `api/jobs.py` (remove process management) | `api/jobs.py` | SSE streaming still works; job creation still works |
| 1.10 | Implement `ModelClient` protocol + `AnthropicModelClient` | `model_client.py` | Unit test: wraps anthropic.Anthropic correctly |
| 1.11 | Implement `ModelRouter` | `model_router.py` | Unit test: routes claude-* to Anthropic backend |
| 1.12 | Encrypt AWS credentials at rest (Fernet) | `credential_encryption.py`, `models.py` | Migration test: encrypt → store → decrypt roundtrip |
| 1.13 | Make guardrails mandatory | `base_orchestrator.py` | Remove try/except; verify import works |
| 1.14 | Lock down CORS | `main.py`, `config.py` | Browser test: requests from unauthorized origin rejected |
| 1.15 | Gate agent SDK fallback | `model_gateway.py`, `config.py` | Config test: fails without API key when flag=false |
| 1.16 | PII blocking in enterprise mode | `guardrails.py`, `config.py` | Unit test: PII blocked when ENTERPRISE_MODE=true |
| 1.17 | Add `ExecutionLog` + `GuardrailEvent` models | `models.py` | Alembic migration runs successfully |
| 1.18 | Add admin endpoints | `api/admin.py` | API test: health, logs, guardrail events return correctly |
| 1.19 | Add `EXECUTION_BACKEND` + new config flags | `config.py` | Config test: all new flags have sensible defaults |
| 1.20 | Create `docker-compose.yml` for development | `docker/docker-compose.yml` | `docker-compose up` starts all services |

**Phase 1 Exit Criteria:**
- [ ] All existing tests pass (`pytest backend/tests/`)
- [ ] New unit tests for all new components (>90% coverage of `execution/` package)
- [ ] LocalExecutor produces identical output to old job_runner for all 9 skill types
- [ ] AWS credentials encrypted in DB (verified with migration)
- [ ] CORS restricted (verified with browser test)
- [ ] Guardrails mandatory (verified: skill fails if guardrails.py missing)
- [ ] Agent SDK fallback gated (verified: RuntimeError when disabled)
- [ ] ENTERPRISE_MODE PII blocking works (verified: request blocked)

---

### Phase 2: Container Isolation (v1.5)

**Goal:** Docker-based execution with process isolation, restricted networking, and STS credential minting.

**Duration:** 3-4 weeks

| Step | Task | Files | Verification |
|------|------|-------|-------------|
| 2.1 | Create worker Docker image | `docker/Dockerfile.worker` | `docker build -t oci-migration-worker .` succeeds |
| 2.2 | Implement `worker_entrypoint.py` | `execution/worker_entrypoint.py` | Run manually: reads context JSON, produces result JSON |
| 2.3 | Create Docker network `model-only` | Docker network config | `docker network inspect model-only` shows restricted egress |
| 2.4 | Implement `ContainerExecutor` | `execution/container_executor.py` | Integration test: run skill in container, get result |
| 2.5 | Implement STS credential minting | `credential_minter.py` | Test: STS session token issued with 15-min TTL |
| 2.6 | Implement progress streaming from container | Container stdout → parent reader | SSE stream shows real-time progress from container |
| 2.7 | Implement container cancellation | `cancel_job()` via `docker stop` | Cancel test: container stopped within 10s |
| 2.8 | Implement credential expiry watchdog | Timer thread in executor | Expiry test: container killed when creds expire |
| 2.9 | Update docker-compose for container backend | `docker/docker-compose.yml` | `EXECUTION_BACKEND=container docker-compose up` works |
| 2.10 | Resource limit tuning | Docker run flags | Load test: 10 concurrent jobs don't OOM |

**Phase 2 Exit Criteria:**
- [ ] All 9 skills run successfully in container backend
- [ ] Network isolation verified: container cannot reach anything except model endpoint
- [ ] STS credentials expire correctly (15-min TTL)
- [ ] Container killed on credential expiry
- [ ] Progress streaming works through container stdout
- [ ] Job cancellation works (docker stop)
- [ ] 10 concurrent jobs without OOM or deadlock

---

### Phase 3: Sandbox Execution + Model Portability (v2.0+)

**Goal:** NemoClaw/OpenShell sandbox for maximum isolation; model plane supports multiple backends.

**Duration:** 4-6 weeks

| Step | Task | Verification |
|------|------|-------------|
| 3.1 | Implement `SandboxExecutor` | Integration test: skill runs in NemoClaw sandbox |
| 3.2 | Configure OpenShell gateway credential proxy | Proxy test: model API call succeeds; sandbox never sees token |
| 3.3 | Implement Landlock policy | Filesystem test: sandbox can't read /etc/shadow |
| 3.4 | Implement seccomp profile | Syscall test: mount/ptrace blocked |
| 3.5 | Implement `OCIGenAIModelClient` | Route `oci-*` models to OCI GenAI |
| 3.6 | Implement `VLLMModelClient` | Route custom models to vLLM endpoint |
| 3.7 | Update ModelRouter for multi-backend | Config test: MODEL_API_BASE_URL routes correctly |
| 3.8 | Create Helm chart | `helm install` deploys full stack on K8s |
| 3.9 | pgvector integration for RAG | Semantic search returns relevant service mappings |
| 3.10 | Per-job model API token rotation | Each job gets unique, revocable token |

**Phase 3 Exit Criteria:**
- [ ] Sandbox execution: credentials never visible inside sandbox
- [ ] Landlock + seccomp verified with penetration test
- [ ] OCI GenAI backend works for at least 1 skill
- [ ] Helm chart deploys successfully on OKE
- [ ] RAG semantic search returns better results than keyword ILIKE

---

## 16. Deployment Architecture

### 16.1 Development (docker-compose)

```yaml
# docker/docker-compose.yml
version: "3.9"

services:
  api:
    build:
      context: ../backend
      dockerfile: Dockerfile
    ports:
      - "8001:8001"
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/oci_migration
      REDIS_URL: redis://redis:6379
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      JWT_SECRET: ${JWT_SECRET:-dev-secret-change-in-prod}
      EXECUTION_BACKEND: local
      CORS_ALLOWED_ORIGINS: http://localhost:5173
      ALLOW_AGENT_SDK_FALLBACK: "true"
      ENTERPRISE_MODE: "false"
      CREDENTIAL_ENCRYPTION_KEY: ${CREDENTIAL_ENCRYPTION_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ../backend:/app  # Hot reload in dev

  frontend:
    build:
      context: ../frontend
      dockerfile: Dockerfile
    ports:
      - "5173:5173"
    environment:
      VITE_API_URL: http://localhost:8001

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: oci_migration
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  worker:
    build:
      context: ../backend
      dockerfile: Dockerfile
    command: arq backend.app.services.job_runner.WorkerSettings
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/oci_migration
      REDIS_URL: redis://redis:6379
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      EXECUTION_BACKEND: local
      CREDENTIAL_ENCRYPTION_KEY: ${CREDENTIAL_ENCRYPTION_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

volumes:
  pgdata:
```

### 16.2 Production (Helm Chart — Simplified)

```
helm/oci-migration/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── api-deployment.yaml
│   ├── api-service.yaml
│   ├── frontend-deployment.yaml
│   ├── frontend-service.yaml
│   ├── worker-deployment.yaml
│   ├── postgres-statefulset.yaml
│   ├── postgres-service.yaml
│   ├── redis-deployment.yaml
│   ├── redis-service.yaml
│   ├── ingress.yaml
│   ├── secrets.yaml
│   ├── configmap.yaml
│   └── networkpolicy.yaml
```

**Key Helm values:**

```yaml
# helm/oci-migration/values.yaml
replicaCount:
  api: 2
  frontend: 2
  worker: 3

executionBackend: container  # "local" | "container" | "sandbox"

api:
  image: ghcr.io/org/oci-migration-api:latest
  resources:
    requests: { cpu: 500m, memory: 1Gi }
    limits: { cpu: 2000m, memory: 4Gi }

worker:
  image: ghcr.io/org/oci-migration-worker:latest
  resources:
    requests: { cpu: 1000m, memory: 2Gi }
    limits: { cpu: 4000m, memory: 8Gi }
  # For container backend: worker needs Docker socket access
  # For sandbox backend: worker needs OpenShell API access
  dockerSocket: /var/run/docker.sock  # Only for container backend

postgres:
  storageClass: oci-bv
  storageSize: 50Gi
  resources:
    requests: { cpu: 500m, memory: 2Gi }

redis:
  resources:
    requests: { cpu: 250m, memory: 512Mi }

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: migration.example.com
      paths:
        - path: /api
          service: api
        - path: /
          service: frontend

secrets:
  anthropicApiKey: ""          # From OCI Vault
  jwtSecret: ""                # Generated
  credentialEncryptionKey: ""  # From OCI Vault KMS
  databaseUrl: ""              # From OCI DB secret

networkPolicy:
  enabled: true
  # Workers can only reach: postgres, redis, model API endpoint
  # Frontend can only reach: api
  # API can reach: postgres, redis
```

### 16.3 Deployment Topology

```
                    ┌─────────────────────────────────────────┐
                    │            OCI Load Balancer              │
                    └────────────┬────────────┬───────────────┘
                                 │            │
                    ┌────────────▼──┐  ┌──────▼──────────────┐
                    │  Frontend     │  │  API                 │
                    │  (Nginx +     │  │  (FastAPI + Uvicorn) │
                    │   React SPA)  │  │  × 2 replicas        │
                    │  × 2 replicas │  │                      │
                    └───────────────┘  └──────┬───────────────┘
                                              │
                           ┌──────────────────┼──────────────────┐
                           │                  │                  │
                    ┌──────▼──────┐   ┌───────▼──────┐  ┌───────▼──────┐
                    │  PostgreSQL │   │    Redis     │  │   Workers    │
                    │  StatefulSet│   │  Deployment  │  │  × 3 replicas│
                    │  (OCI Block │   │  (in-memory) │  │              │
                    │   Volume)   │   │              │  │  EXECUTION_  │
                    │             │   │              │  │  BACKEND=    │
                    └─────────────┘   └──────────────┘  │  container   │
                                                        │              │
                                                        │  ┌────────┐  │
                                                        │  │Docker  │  │
                                                        │  │Socket  │  │
                                                        │  │(DinD)  │  │
                                                        │  └────────┘  │
                                                        └──────────────┘
                                                               │
                                                               │ Model API
                                                               ▼
                                                    ┌──────────────────┐
                                                    │  Anthropic API   │
                                                    │  (or OCI GenAI / │
                                                    │   private vLLM)  │
                                                    └──────────────────┘
```

---

## 17. Risks & Mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Phase 1 refactor breaks existing skills | Medium | High | LocalExecutor must produce byte-identical output. Run all 9 skills through both old and new code paths; compare artifacts. |
| R2 | ContainerExecutor Docker socket access is a security risk on shared K8s | High | High | Use Docker-in-Docker (DinD) sidecar or Kaniko. Never mount host Docker socket in production. Alternatively, use Podman rootless. |
| R3 | STS 15-min TTL too short for complex translations | Medium | Medium | Monitor job durations. If >12 min, extend TTL to 30 min or implement STS refresh (with audit log). Current max job timeout is 300s (5 min). |
| R4 | NemoClaw/OpenShell not available in all environments | High | Low | SandboxExecutor is Phase 3+ and optional. ContainerExecutor provides sufficient isolation for most enterprise requirements. |
| R5 | Model API rate limits with concurrent container jobs | Medium | Medium | Implement rate limiting in ModelRouter. Queue model API calls with exponential backoff. Monitor 429 responses. |
| R6 | Fernet key rotation requires re-encryption of all credentials | Low | Medium | Implement key rotation script: decrypt with old key → re-encrypt with new key. Schedule during maintenance window. |
| R7 | Progress callback doesn't work across container boundary | Medium | Medium | Container writes JSON-line progress to stdout; parent process reads and updates DB. Tested in Phase 2 step 2.6. |
| R8 | Config drift between LocalExecutor and ContainerExecutor | Medium | Medium | Worker Docker image built from same codebase. CI pipeline runs tests in both backends. |
| R9 | OCI GenAI model quality insufficient for translation tasks | Medium | High | ModelRouter supports per-skill model override. Fall back to Anthropic for critical skills while tuning OCI GenAI prompts. |
| R10 | Database migration fails on large production databases | Low | High | Test Alembic migration on production-size dataset snapshot. Add `execution_backend` column as nullable. Encrypt credentials in batch with progress tracking. |

---

## 18. Anti-Patterns to Avoid

### 18.1 Don't Let Execution Plane Access the Database

```python
# ❌ WRONG: Executor queries DB directly
class BadExecutor(ExecutionBackend):
    async def execute_job(self, context):
        async with get_session() as db:  # NO! DB access in execution plane
            resources = await db.query(Resource).filter(...)
            ...

# ✅ RIGHT: All DB data pre-loaded into JobContext by Plane A
class GoodExecutor(ExecutionBackend):
    async def execute_job(self, context):
        # context.input_content already contains everything the skill needs
        result = orchestrator.run(input_content=context.input_content, ...)
```

### 18.2 Don't Pass Full Credentials Across Boundaries

```python
# ❌ WRONG: Passing long-lived AWS keys to execution
credentials = ScopedCredentials(
    aws_access_key_id=connection.access_key,      # Long-lived!
    aws_secret_access_key=connection.secret_key,   # Long-lived!
)

# ✅ RIGHT: Mint STS temporary credentials
sts_response = sts.assume_role(
    RoleArn=role_arn,
    DurationSeconds=900,  # 15 minutes
)
credentials = ScopedCredentials(
    aws_access_key_id=sts_response["AccessKeyId"],
    aws_secret_access_key=sts_response["SecretAccessKey"],
    aws_session_token=sts_response["SessionToken"],  # Temporary!
    expires_at=sts_response["Expiration"],
)
```

### 18.3 Don't Modify Orchestrator Signatures

```python
# ❌ WRONG: Changing orchestrator to accept JobContext
class NetworkOrchestrator(BaseTranslationOrchestrator):
    def run(self, context: JobContext):  # Changed signature!
        ...

# ✅ RIGHT: Adapter translates JobContext → existing signature
class OrchestratorAdapter:
    def execute(self, context: JobContext) -> JobResult:
        return orchestrator.run(
            input_content=context.input_content,
            progress_callback=context.progress_callback,
            client=self._build_client(context.credentials),
        )
```

### 18.4 Don't Make Guardrails Optional

```python
# ❌ WRONG: Graceful degradation when guardrails fail
try:
    from backend.app.gateway.guardrails import check_input
except ImportError:
    check_input = lambda text, skill_type: {"action": "allow", "scrubbed_text": text}

# ✅ RIGHT: Guardrails are mandatory — fail if unavailable
from backend.app.gateway.guardrails import check_input, check_output
# ImportError means deployment is broken — fix it, don't work around it
```

### 18.5 Don't Hardcode Model Names in Skills

```python
# ❌ WRONG: Model name hardcoded in orchestrator
class MyOrchestrator(BaseTranslationOrchestrator):
    ENHANCEMENT_MODEL = "claude-opus-4-6"  # Hardcoded!

# ✅ RIGHT (future): Model name comes from SkillDefinition
# For Phase 1, the hardcoded names are acceptable because they're
# class constants that can be overridden. In Phase 3, ModelRouter
# handles all routing and skills don't reference model names.
```

### 18.6 Don't Use Catch-All Exception Handlers for Security Logic

```python
# ❌ WRONG: Swallowing security-relevant errors
try:
    credentials = credential_minter.mint(tenant_id, skill_def)
except Exception:
    credentials = ScopedCredentials(model_api_token=os.environ["ANTHROPIC_API_KEY"])

# ✅ RIGHT: Security failures must propagate
credentials = credential_minter.mint(tenant_id, skill_def)
# If this fails, the job fails. That's correct.
```

### 18.7 Don't Share Execution Contexts Between Jobs

```python
# ❌ WRONG: Reusing container/credentials between jobs
container = docker.create(image="worker")
for job in jobs:
    container.exec(job)  # Credential leakage between jobs!

# ✅ RIGHT: One container per job, fresh credentials each time
for job in jobs:
    credentials = credential_minter.mint(job.tenant_id, job.skill_def)
    container = docker.run(image="worker", env=credentials.to_env_dict())
    result = container.wait()
    container.remove()
```

### 18.8 Don't Put Business Logic in the Execution Backend

```python
# ❌ WRONG: Backend decides how to aggregate input
class ContainerExecutor(ExecutionBackend):
    async def execute_job(self, context):
        if context.skill_definition.skill_type == "network_translation":
            # Aggregation logic in executor!
            resources = self._load_network_resources(context)

# ✅ RIGHT: Input fully prepared by Plane A (InputBuilder)
class ContainerExecutor(ExecutionBackend):
    async def execute_job(self, context):
        # context.input_content is already aggregated by InputBuilder
        # Executor just runs the skill
        ...
```

---

## Appendix A: Directory Structure (Post-v2)

```
backend/app/
├── __init__.py
├── config.py                          # MODIFIED: new config flags
├── main.py                            # MODIFIED: CORS, execution backend init
│
├── api/
│   ├── __init__.py
│   ├── admin.py                       # NEW: execution health, logs, guardrails
│   ├── auth.py
│   ├── aws.py
│   ├── deps.py
│   ├── jobs.py                        # MODIFIED: delegates to JobDispatcher
│   ├── plans.py
│   └── rag.py
│
├── db/
│   ├── __init__.py
│   ├── base.py
│   └── models.py                      # MODIFIED: 2 new models, 2 new columns
│
├── execution/                         # NEW PACKAGE
│   ├── __init__.py
│   ├── interfaces.py                  # SkillDefinition, ScopedCredentials,
│   │                                  # JobContext, JobResult, SkillExecutor,
│   │                                  # ExecutionBackend
│   ├── skill_registry.py             # Declarative skill registry
│   ├── job_dispatcher.py             # Job lifecycle orchestration
│   ├── input_builder.py              # Input aggregation (from job_runner.py)
│   ├── credential_minter.py          # Scoped credential issuance
│   ├── orchestrator_adapter.py       # JobContext → orchestrator.run() bridge
│   ├── local_executor.py             # In-process execution (v1)
│   ├── container_executor.py         # Docker execution (v1.5)
│   ├── sandbox_executor.py           # NemoClaw execution (v2+)
│   └── worker_entrypoint.py          # Container/sandbox entry point
│
├── gateway/
│   ├── __init__.py
│   ├── agent_adapter.py              # GATED: requires ALLOW_AGENT_SDK_FALLBACK
│   ├── guardrails.py                 # HARDENED: mandatory, PII blocking
│   ├── model_client.py               # NEW: ModelClient protocol
│   ├── model_gateway.py              # REFACTORED: uses ModelClient
│   └── model_router.py               # NEW: multi-backend routing
│
├── rag/
│   ├── __init__.py
│   └── search.py
│
├── services/
│   ├── __init__.py
│   ├── auth_service.py
│   ├── aws_extractor.py
│   ├── credential_encryption.py      # NEW: Fernet encrypt/decrypt
│   ├── job_runner.py                  # SIMPLIFIED: thin ARQ wrapper
│   └── migration_orchestrator.py
│
└── skills/                            # UNCHANGED (all orchestrators)
    ├── __init__.py
    ├── shared/
    │   ├── agent_logger.py
    │   ├── base_orchestrator.py       # TINY FIX: mandatory guardrails
    │   ├── doc_loader.py
    │   ├── index_docs.py
    │   ├── rag.py
    │   └── session_tracker.py
    ├── cfn_terraform/
    ├── database_translation/
    ├── dependency_discovery/
    ├── ec2_translation/
    ├── iam_translation/
    ├── loadbalancer_translation/
    ├── network_translation/
    ├── storage_translation/
    └── synthesis/
```

---

## Appendix B: Configuration Reference

```ini
# ── Existing (unchanged) ──
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/oci_migration
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_AUTH_TOKEN=           # Claude Code OAuth token (optional)
JWT_SECRET=<random-256-bit>
JWT_EXPIRE_MINUTES=1440

# ── New in v2 ──
EXECUTION_BACKEND=local                        # "local" | "container" | "sandbox"
MODEL_API_BASE_URL=https://api.anthropic.com   # Override for private endpoints
ALLOW_AGENT_SDK_FALLBACK=false                 # Gate Claude Code OAuth fallback
ENTERPRISE_MODE=false                          # PII blocking, stricter guardrails
CORS_ALLOWED_ORIGINS=http://localhost:5173     # Comma-separated allowed origins
CREDENTIAL_ENCRYPTION_KEY=<fernet-key>         # Fernet key for AWS cred encryption

# ── Container backend (Phase 2) ──
WORKER_IMAGE=oci-migration-worker:latest
WORKER_MEMORY_LIMIT=2g
WORKER_CPU_LIMIT=2
DOCKER_NETWORK=model-only

# ── Sandbox backend (Phase 3) ──
OPENSHELL_API_URL=http://localhost:9090
OPENSHELL_API_TOKEN=<token>
SANDBOX_MEMORY_LIMIT=2g
SANDBOX_TIMEOUT_SECONDS=600
```

---

## Appendix C: Glossary

| Term | Definition |
|------|-----------|
| **Plane A** | Control Plane — UI, API, database, job queue, credential management |
| **Plane B** | Execution Plane — where skills run and call LLMs; pluggable backends |
| **Plane C** | Model/Knowledge Plane — LLM endpoints, guardrails, RAG knowledge store |
| **Boundary 1** | Security boundary between Control and Execution planes |
| **Boundary 2** | Security boundary between Execution and Model planes |
| **SkillDefinition** | Immutable declaration of a skill's properties (module, model, timeout) |
| **ScopedCredentials** | Time-limited, least-privilege credentials for a single job |
| **JobContext** | Everything an execution backend needs to run a job (and nothing more) |
| **JobResult** | Everything returned from execution (artifacts, cost, interactions) |
| **ExecutionBackend** | ABC for pluggable execution environments |
| **LocalExecutor** | In-process execution (Phase 1, development default) |
| **ContainerExecutor** | Docker-isolated execution (Phase 2) |
| **SandboxExecutor** | NemoClaw/OpenShell sandboxed execution (Phase 3) |
| **ModelClient** | Protocol for model backend abstraction |
| **ModelRouter** | Routes model requests to appropriate backend |
| **CredentialMinter** | Issues scoped credentials per job execution |
| **InputBuilder** | Prepares skill input from DB resources (aggregation logic) |
| **OrchestratorAdapter** | Bridges JobContext to existing orchestrator.run() signature |
| **NemoClaw** | Sandbox runtime with Landlock, seccomp, and network namespace isolation |
| **OpenShell** | API gateway for NemoClaw; proxies model API calls with host-side credentials |
| **ARQ** | Async Redis Queue — lightweight Python job queue |
| **STS** | AWS Security Token Service — issues temporary credentials |
| **Fernet** | Symmetric encryption scheme from the `cryptography` library |
