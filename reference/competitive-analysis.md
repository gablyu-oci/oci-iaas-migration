# Competitive Analysis: Cloud Migration Platforms

## 1. Matilda Cloud

**Overview:** AI-powered, application-centric cloud transformation platform. End-to-end migration from discovery through post-migration optimization. Supports AWS, Azure, GCP, and OCI as targets.

### Strengths
- **Application-centric approach** — groups and analyzes by application, not just infrastructure
- **5 integrated products** in a single platform: RAPID Assessment, Discover, Migrate, Orchestrate, Optimize
- **5R classification** per workload (Rehost, Replatform, Refactor, Rearchitect, Retire) using generative AI
- **Dual discovery modes** — agentless (SNMP/WMI) and login-based (SSH/RDP), zero-disruption
- **Real-time continuous dependency mapping** (not static snapshots)
- **IaC generation** — auto-generates Terraform, Ansible, PowerShell for landing zones
- **CI/CD integration** — GitHub, GitLab, Bitbucket, Azure Repos, Jenkins
- **"Optimize as you transition"** — rightsizing and cost optimization during migration, not deferred
- **.NET modernization** — .NET Legacy to .NET Core 6/8 conversion
- **Broad OS support** — includes IBM AIX, HP-UX, Solaris alongside Linux/Windows
- **Multi-cloud and cross-cloud** migration support

### Weaknesses
- No public pricing (subscription-based, opaque)
- No serverless conversion (Lambda/API Gateway)
- No licensing mechanism conversion
- Not available on AWS Marketplace
- Smaller partner ecosystem compared to hyperscalers

---

## 2. Microsoft Azure Migrate

**Overview:** Free, unified migration hub for servers, databases, web apps, and data. Strongest in structured workflow and enterprise tooling integration.

### Strengths
- **Unified hub** — single platform for VMs, databases, web apps, VDI, and data migration
- **Azure Migrate Appliance** — lightweight VM deployed on-premises for continuous discovery (OVA/VHD/script)
  - Discovers up to 10,000 VMware servers, 5,000 Hyper-V servers, 1,000 physical servers per appliance
  - Collects config every 15-30 min, performance every 5-50 min, software inventory daily
- **Agentless dependency analysis** — TCP connection monitoring without installing agents on targets
- **Performance-based sizing** — recommendations based on actual CPU/memory/disk/IOPS utilization (1-30 day collection)
- **Business case engine** — 5-year TCO projections, ROI calculation, payback period, CAPEX-to-OPEX modeling, sustainability/carbon emissions comparison
- **Test migration** — non-destructive test VMs in isolated network before cutover (unique differentiator)
- **Multi-cloud source support** — VMware, Hyper-V, physical servers, AWS EC2, GCP, Xen, KVM
- **Assessment groups** — group by application, department, or migration wave; run separate assessments per group
- **SQL/PostgreSQL/MySQL discovery** built into the same appliance
- **ISV partner ecosystem** — Carbonite, Cloudamize, Zerto, Turbonomic, Device42, and more pre-integrated
- **Completely free** — no charge for the migration service itself; only pay for Azure resources created
- **Private Link support** — end-to-end private connectivity for sensitive environments

### Weaknesses
- Migration is still somewhat manual despite structured workflow
- Relies heavily on Microsoft partner ecosystem for complex migrations
- Agent-based migration required for AWS EC2 and physical servers (no agentless option)
- Replication appliance needs Windows Server 2022 with 32GB RAM / 8 vCPUs
- Dependency visualization limited to 1-hour window (agent-based) or 30-day window (agentless)

---

## 3. AWS Transform

**Overview:** Amazon's agentic AI-powered migration and modernization platform (launched May 2025). First-of-its-kind agentic approach. Positioned around modernization, not just lift-and-shift.

### Strengths
- **Agentic AI architecture** — specialized AI agents for each domain (assessment, Windows, mainframe, VMware, custom code)
- **Modernization-first** — doesn't just rehost; transforms and optimizes full-stack applications
- **Full-stack Windows modernization:**
  - .NET Framework → Linux-compatible apps
  - ASP.NET Web Forms → Blazor
  - SQL Server → Aurora PostgreSQL
  - Coordinated across application, UI, database, and deployment layers
- **Mainframe modernization:** COBOL → Java, JCL → Groovy (compresses years to months)
- **VMware migration:** 80x faster network configuration conversion; automated VPC/subnet/SG/NAT/transit gateway translation
- **Custom code transformations:** Java/Python/Node.js version upgrades at $0.035/agent minute
- **Wave planning** — dependency-aware sequencing with automated server grouping
- **Discovery tool** — self-contained on-premises deployment, no external dependencies
- **IaC output** — generates CDK, Terraform, or Landing Zone Accelerator configurations
- **Composability initiative** — partners (Accenture, Capgemini, IBM, Infosys, Deloitte, TCS) can embed proprietary agents
- **Free for enterprise workloads** (Windows, mainframe, VMware); only custom transformations are paid
- **Reforge feature** — LLM enhancement of refactored code for readability and best practices
- **Quantified results:** 1.35M hours saved, 85% productivity boost, 70% cost reduction

### Weaknesses
- New product (May 2025) — less battle-tested than Azure Migrate
- Assessment and discovery are narrower than Azure Migrate's appliance approach
- Relies on AWS MGN for actual VM replication (Transform handles planning/modernization only)
- Primarily designed for migrating TO AWS, not FROM AWS
- Partner ecosystem still forming

---

## 4. Oracle Cloud Migrations (Current OCI Offering)

**Overview:** Free, managed VM migration service for VMware and AWS EC2 to OCI. Part of a broader but fragmented ecosystem.

### Strengths
- **Free service** — no charge for migration; only temporary resources billed
- **VMware and AWS EC2 support** with automated discovery and replication
- **Configuration Recommendation Engine** — maps source assets to OCI shapes based on utilization
- **Terraform/Resource Manager integration** — auto-generates OCI Resource Manager stacks for deployment
- **Multi-plan comparison** — create and compare migration plans with different sizing strategies
- **Cloud Lift Services** — free, dedicated Oracle engineers for migration support (strong GTM differentiator)
- **Database ecosystem is mature** — ZDM, DMS (free 6 months), GoldenGate for Oracle DB migrations
- **Competitive OCI pricing** — 50% less compute, 70% less block storage, 80% less networking vs competitors

### Weaknesses
- **Fragmented tooling** — VMs, databases, and apps use separate tools with no unified dashboard
- **No dependency mapping** — no native application dependency visualization
- **No Hyper-V or physical server support** (requires partner tools)
- **No Azure/GCP VM source support**
- **x86 only** — no ARM/AARCH64 support
- **No application-aware migration** — VM-level only
- **No built-in post-migration validation**
- **Network migration is manual** — no automated network topology translation
- **No software inventory discovery**
- **No business case / TCO engine**
- **No test migration capability**

---

## Feature Comparison Matrix

| Capability | Matilda Cloud | Azure Migrate | AWS Transform | OCI Cloud Migrations | **Our Product (Current)** |
|---|---|---|---|---|---|
| **Discovery** | | | | | |
| Agentless discovery | Yes (SNMP/WMI) | Yes (appliance) | Yes (on-prem tool) | Yes (appliance/agentless) | Partial (API-based) |
| Software inventory | Yes | Yes (apps, SQL, web) | Yes (code analysis) | No | No |
| OS compatibility check | Partial | Yes | Yes | Partial | No |
| Performance data collection | Yes (continuous) | Yes (5-50 min intervals) | Yes | Yes | No (static config only) |
| **Assessment** | | | | | |
| Dependency mapping | Yes (real-time) | Yes (agentless TCP) | Yes (network mapping) | No | Partial (file upload) |
| Resource mapping to target | Yes (multi-cloud) | Yes (Azure only) | Yes (AWS only) | Yes (OCI shapes) | Yes (AWS→OCI) |
| Performance-based rightsizing | Yes | Yes (1-30 day) | Yes | Yes (utilization-based) | No |
| 5R/6R classification | Yes (5R + AI) | Yes (6R business case) | Yes (modernization focus) | No | No |
| Migration readiness score | Yes | Yes (confidence rating) | Yes | No | No |
| Business case / TCO | Yes (cost projections) | Yes (5-year, sustainability) | Yes (Migration Evaluator) | No | No |
| **Planning** | | | | | |
| Wave planning | Yes (wave groups) | Yes (assessment groups) | Yes (dependency-aware) | No | Yes (7 phases) |
| Multi-plan comparison | No | Yes (per group) | No | Yes | No |
| Landing zone IaC | Yes (Terraform/Ansible) | No (manual) | Yes (CDK/Terraform/LZA) | Yes (Resource Manager) | Partial (skill output) |
| Network topology translation | Partial | No | Yes (80x faster) | No | Yes (skill) |
| Golden image recommendation | No | No | No | No | No |
| **Migration Execution** | | | | | |
| VM migration (disk replication) | Yes (async replication) | Yes (agent/agentless) | Via MGN (replication) | Yes (snapshot + hydration) | No |
| Database migration | Partial | Yes (DMA, DMS) | Yes (DMS, SCT) | Yes (ZDM, DMS, GoldenGate) | No (translation only) |
| Storage migration | Partial | Yes (Data Box) | Yes (DataSync, S3) | Partial (block volumes) | No |
| IAM migration | No | Partial | No | No | Yes (translation only) |
| Network migration | Partial | Partial | Yes (automated) | No | Yes (translation only) |
| Serverless migration | No | Yes (App Service) | Yes (Lambda) | No | No |
| Live progress dashboard | Yes | Yes (portal) | Yes (chat-based) | Yes (console) | Yes (SSE streaming) |
| **Validation** | | | | | |
| Test migration | No | Yes (non-destructive) | Via MGN | No | No |
| Post-migration validation | Yes (monitoring) | Yes (checklist) | Via MGN | No | No |
| Rollback plan | No | Partial | No | No | No |
| Compliance validation | Yes (real-time) | Yes (Defender) | Partial | No | Partial (guardrails) |
| Performance comparison | Yes (optimize) | Partial | Partial | No | No |
| **AI / Agent Features** | | | | | |
| AI-powered recommendations | Yes (GenAI 5R) | No (rule-based) | Yes (agentic AI) | No | Yes (Claude AI) |
| Specialized domain agents | No | No | Yes (5 agent types) | No | Yes (8 skills) |
| Natural language interface | No | No | Yes (chat) | No | No |
| Code modernization | Yes (.NET) | No | Yes (full-stack) | No | No |
| **Ecosystem** | | | | | |
| Partner integrations | Limited | Strong (8+ ISVs) | Growing (6+ SIs) | Moderate (5+ tools) | None |
| Free service | No (subscription) | Yes | Mostly free | Yes | N/A |

---

## Key Takeaways for Our Product

### 1. Biggest competitive gaps to close
- **No performance-based rightsizing** — every competitor does this; we only use static config
- **No dependency mapping** — Azure and Matilda lead here; we only support file upload
- **No test migration** — Azure's non-destructive test migration is a major risk-reduction feature
- **No business case / TCO engine** — Azure's 5-year projections and sustainability metrics set the bar
- **No VM disk migration** — we translate configs but don't move actual workloads

### 2. Differentiation opportunities
- **Agentic AI is our strongest asset** — AWS Transform validates this approach; we should lean in harder with specialized agents per migration domain
- **Application-centric grouping** (like Matilda) + **AI-powered 6R classification** would be unique in the OCI ecosystem
- **End-to-end single platform** — OCI's current offering is fragmented; we can be the unified hub
- **Network topology translation** — we already do this; AWS Transform's 80x speed claim shows this is high-value
- **IaC-first approach** — our Terraform generation is strong; extending to landing zones and CI/CD pipelines (like Matilda) would differentiate

### 3. Design patterns to adopt
- **Azure's appliance model** — lightweight discovery agent deployed in source environment for continuous monitoring
- **Azure's test migration** — non-destructive validation before cutover
- **AWS Transform's wave planning** — dependency-aware migration sequencing
- **Matilda's "optimize as you transition"** — rightsizing during migration, not after
- **AWS Transform's composability** — allow partners to plug in specialized agents

### 4. What NOT to build
- Don't build our own VM replication engine — integrate with OCI Cloud Migrations for actual disk movement
- Don't build database replication — orchestrate ZDM/DMS/GoldenGate instead
- Don't build a generic monitoring tool — integrate with OCI Monitoring post-migration
