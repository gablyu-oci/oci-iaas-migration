# Product Feature Design: OCI IaaS Migration Platform v2

> Agent-assisted migration platform for AWS-to-OCI workload migration.
> Redesigned based on competitive analysis of Matilda Cloud, Azure Migrate, AWS Transform, and Oracle Cloud Migrations.

---

## Design Principles

1. **Agent-first architecture** — specialized AI agents per migration domain, orchestrated by a central planner
2. **Application-centric** — group, assess, and migrate by application/workload, not individual resources
3. **Optimize as you transition** — rightsizing and modernization recommendations baked into every phase
4. **IaC-native** — every output is Terraform; every action is reproducible and auditable
5. **Integrate, don't rebuild** — orchestrate OCI Cloud Migrations, ZDM, DMS, GoldenGate rather than reimplementing replication
6. **Progressive disclosure** — simple for lift-and-shift; deep for complex modernization

---

## Phase 1: Discovery & Assessment

### 1.1 Agentless Discovery Engine

**What:** Continuous, non-invasive discovery of AWS resources without storing long-lived credentials.

**How it works:**
- User deploys a cross-account IAM role in their AWS account (CloudFormation one-click template provided)
- Platform assumes the role via STS for time-limited sessions
- Scheduled discovery runs every 15 minutes (configurable)
- Discovers 20+ resource types: EC2, RDS, Aurora, DynamoDB, Lambda, ECS/EKS, S3, EBS, VPC, subnets, security groups, NAT gateways, load balancers, Route 53, CloudFront, IAM roles/policies, Auto Scaling groups, ElastiCache, SQS, SNS

**Enhancements over current state:**
- Replace stored AWS access keys with IAM role assumption (security improvement)
- Add scheduled discovery (currently one-shot extraction only)
- Expand resource coverage from 15+ to 20+ types
- Store discovery history for drift detection

### 1.2 Performance-Based Rightsizing

**What:** Collect actual utilization metrics to recommend optimal OCI compute shapes — not just match source instance types.

**How it works:**
- Pull CloudWatch metrics via the assumed IAM role: CPU utilization, memory (via CloudWatch agent), disk IOPS/throughput, network in/out
- Configurable collection window: 7, 14, or 30 days
- Configurable percentile: 50th, 75th, 90th, 95th, 99th (default: 95th)
- Comfort factor: adjustable buffer (default: 20%) for growth and seasonal spikes
- **Output per instance:**
  - Current AWS instance type and cost
  - Recommended OCI shape (Flex shapes preferred for right-fit)
  - Projected OCI monthly cost
  - Savings percentage
  - Confidence level (based on data completeness)

**OCI shape matching logic:**
1. Calculate effective vCPU and memory needs from utilization data + comfort factor
2. Filter eligible OCI shapes (VM.Standard.E5.Flex, VM.Standard3.Flex, VM.Optimized3.Flex, etc.)
3. Match disk IOPS/throughput to OCI Block Volume performance tiers
4. Rank by cost-efficiency, then select cheapest shape that meets all requirements
5. Flag cases where no direct match exists (e.g., GPU instances, high-memory)

### 1.3 Dependency Mapping

**What:** Automatically map application dependencies by analyzing network traffic and API call patterns.

**How it works:**
- **VPC Flow Logs analysis** — identify which instances communicate, on which ports, with what frequency
- **CloudTrail analysis** — identify cross-service dependencies (e.g., EC2 calling RDS, Lambda calling S3)
- **Live polling** (upgrade from current file upload): connect to CloudWatch Logs Insights to query flow logs and CloudTrail in real-time
- **Output:**
  - Interactive dependency graph (Mermaid + ReactFlow visualization)
  - Communication matrix (source → destination, ports, protocols, bandwidth)
  - Dependency clusters (tightly coupled groups that must migrate together)
  - External dependencies (third-party APIs, on-prem connections, cross-region)

### 1.4 Software Inventory Discovery

**What:** Discover installed software, frameworks, database versions, and OS details on each instance.

**How it works:**
- Use AWS Systems Manager (SSM) inventory data if available
- Fallback: SSM Run Command to execute lightweight inventory scripts (requires SSM agent)
- Collects: OS type/version, installed packages, running services, language runtimes, database versions, web server configs
- **Purpose:** Feed into OS compatibility checking and 6R classification

### 1.5 OS Compatibility Checking

**What:** Validate that each source OS can run on OCI and identify required remediation.

**Checks:**
- Source OS vs OCI supported image catalog (Oracle Linux, RHEL, Ubuntu, CentOS, Windows Server, SUSE, Debian)
- Kernel version compatibility
- Boot mode (BIOS vs UEFI) → OCI support
- VirtIO driver availability (required for OCI)
- File system compatibility (ext4, xfs, NTFS)
- **Output:** Per-instance compatibility status (Compatible, Compatible with remediation, Incompatible) with specific remediation steps

### 1.6 Application-Centric Grouping

**What:** Automatically group resources into logical applications/workloads for migration planning.

**Grouping strategies (layered):**
1. **Tag-based** — group by AWS tags (e.g., `Application`, `Environment`, `Team`, `CostCenter`)
2. **Network-based** — group by VPC, subnet, or security group membership
3. **Dependency-based** — group by communication patterns from dependency mapping
4. **AI-assisted** — Claude agent analyzes resource names, tags, and dependencies to suggest logical groupings

**Output per application group:**
- Member resources (compute, database, storage, networking, serverless)
- Internal dependencies (within group)
- External dependencies (cross-group and external)
- Total current AWS cost
- Migration complexity score

### 1.7 6R Classification

**What:** AI-powered recommendation for the optimal migration strategy per workload.

**Categories:**
| Strategy | Description | When recommended |
|---|---|---|
| **Rehost** | Lift-and-shift to OCI with minimal changes | Standard workloads with direct OCI equivalents |
| **Replatform** | Migrate with optimization (e.g., self-managed DB → OCI Database Service) | Workloads that benefit from managed services |
| **Refactor** | Rearchitect for cloud-native OCI | Monolithic apps, .NET Legacy, performance-critical |
| **Rearchitect** | Rebuild using OCI-native services | Legacy apps with no direct migration path |
| **Repurchase** | Replace with SaaS/OCI equivalent | Commercial software with OCI marketplace alternatives |
| **Retire** | Decommission | Unused, redundant, or end-of-life workloads |

**How it works:**
- AI agent analyzes: resource types, utilization patterns, software inventory, dependencies, OS compatibility, age/version of software
- Considers: OCI service catalog, pricing, and feature parity
- **Output per workload:** Recommended strategy, confidence score, rationale, and estimated effort

### 1.8 Migration Readiness Score

**What:** A single score (0-100) per workload indicating how ready it is to migrate.

**Scoring factors:**
| Factor | Weight | Scoring |
|---|---|---|
| OS compatibility | 20% | Compatible=100, Remediation needed=60, Incompatible=0 |
| Resource mapping coverage | 20% | % of resources with direct OCI equivalents |
| Dependency complexity | 15% | Simple (few deps)=100, Complex (many cross-group)=30 |
| Data volume | 15% | Small (<100GB)=100, Large (>10TB)=40 |
| Performance data availability | 10% | 30-day data=100, 7-day=70, None=20 |
| Software inventory completeness | 10% | Full inventory=100, Partial=50, None=20 |
| Compliance requirements | 10% | No special reqs=100, Encryption needed=70, Regulated=40 |

**Display:** Color-coded score with drill-down into each factor.

### 1.9 Business Case & TCO Engine

**What:** Side-by-side cost comparison of current AWS spend vs projected OCI cost, with ROI analysis.

**AWS cost sources:**
- AWS Cost Explorer API (with user authorization)
- Fallback: calculated from discovered instance types and current pricing
- Includes: compute, storage, networking, database, licensing, support

**OCI cost projection:**
- Based on rightsized OCI shapes from Section 1.2
- Includes: compute (Flex shapes), block storage, networking, database services, licensing (BYOL vs included)
- Applies OCI pricing advantages (50% less compute, 70% less block storage, 80% less networking)
- Models: Pay-as-you-go, Annual Flex, Monthly Flex

**Output:**
- Monthly cost comparison (AWS vs OCI)
- Annual savings projection
- 3-year TCO comparison
- Break-even timeline
- Cost breakdown by service category
- Exportable executive summary (PDF)

---

## Phase 2: Planning

### 2.1 Wave Planning with Dependency-Aware Sequencing

**What:** Organize workloads into migration waves based on dependencies, complexity, and business priority.

**How it works:**
- **Input:** Application groups (Section 1.6), dependency map (Section 1.3), readiness scores (Section 1.8), user-defined priorities
- **Algorithm:**
  1. Build directed acyclic graph (DAG) of application dependencies
  2. Topological sort to determine migration order
  3. Group into waves based on: dependency ordering, parallel capacity, business priority, risk tolerance
  4. Validate: no wave breaks a critical dependency; shared services migrate before consumers
- **Wave templates:**
  - **Pilot wave:** 1-2 low-risk, low-dependency workloads for proving the process
  - **Foundation wave:** Networking, IAM, shared services
  - **Application waves:** Business workloads in dependency order
  - **Cleanup wave:** Decommission source resources, DNS cutover

**Output per wave:**
- Workloads included
- Estimated duration
- Prerequisites (what must complete before this wave starts)
- Risk assessment
- Rollback strategy

### 2.2 Multi-Plan Comparison

**What:** Create and compare multiple migration plans with different strategies and sizing.

**Use cases:**
- Compare lift-and-shift vs replatform costs
- Compare aggressive rightsizing (95th percentile) vs conservative (75th percentile)
- Compare different OCI regions
- Compare Pay-as-you-go vs Annual Flex pricing

**Output:** Side-by-side comparison table with total cost, timeline, risk score, and effort estimate per plan.

### 2.3 Landing Zone Generation

**What:** Auto-generate the OCI foundation infrastructure (compartments, VCN, IAM, policies) as Terraform.

**Generated resources:**
- **Compartment structure:** Mirrors application groupings (e.g., `network`, `compute`, `database`, `security`)
- **VCN architecture:** Hub-and-spoke or flat, based on source AWS VPC topology
  - VCN, subnets (public/private), route tables, internet gateway, NAT gateway, service gateway, DRG
  - Security lists and NSGs mapped from AWS security groups
- **IAM baseline:**
  - Groups and policies mapped from AWS IAM roles
  - Dynamic groups for instance-level permissions
  - Compartment-level policies following least-privilege
- **Monitoring foundation:** Alarms, notifications, log groups
- **Tagging:** Namespace and tag keys matching source AWS tags

**Output:** Complete Terraform module with `main.tf`, `variables.tf`, `outputs.tf`, `terraform.tfvars.example`, and a README with deployment instructions.

### 2.4 Golden Image Recommendation

**What:** Recommend OCI base images and document required customizations per workload.

**How it works:**
- Match source OS (from software inventory) to closest OCI platform image
- Identify required customizations: packages, agents, configurations, drivers
- Generate a build script (cloud-init or Packer template) for the golden image
- **Output per workload:** Recommended base image OCID, customization script, validation checklist

### 2.5 Network Topology Translation

**What:** Visual side-by-side comparison of AWS network topology and proposed OCI network topology.

**Enhancements over current skill:**
- **Visual diff:** React-based interactive diagram showing AWS (left) and OCI (right) with mapped connections
- **Automated translation rules:**
  - AWS VPC → OCI VCN
  - AWS Subnet → OCI Subnet (with CIDR remapping if needed)
  - AWS Security Group → OCI Network Security Group
  - AWS NAT Gateway → OCI NAT Gateway
  - AWS Internet Gateway → OCI Internet Gateway
  - AWS Transit Gateway → OCI DRG (Dynamic Routing Gateway)
  - AWS Route 53 → OCI DNS
  - AWS CloudFront → OCI CDN (or keep CloudFront with OCI origin)
  - AWS Direct Connect → OCI FastConnect
  - AWS VPN → OCI Site-to-Site VPN
- **Conflict detection:** Flag overlapping CIDRs, unsupported configurations, missing routes

### 2.6 IaC Generation with CI/CD Integration

**What:** Generate deployment-ready Terraform with optional CI/CD pipeline configuration.

**Enhancements over current skill output:**
- **Module structure:** Separate Terraform modules per workload/wave (not one monolithic file)
- **State management:** Pre-configured OCI Object Storage backend for Terraform state
- **CI/CD templates:**
  - OCI DevOps pipeline YAML
  - GitHub Actions workflow
  - GitLab CI configuration
- **Drift detection:** Post-deployment Terraform plan to detect configuration drift

---

## Phase 3: Migration Execution

### 3.1 VM Migration Orchestration

**What:** Orchestrate the actual movement of VM workloads from AWS to OCI.

**Approach: Integrate with OCI Cloud Migrations service** (don't rebuild replication)

**Workflow:**
1. **Pre-flight checks** — OS compatibility verified, VirtIO drivers available, OCI landing zone deployed
2. **Initiate replication** — API call to OCI Cloud Migrations to start snapshot + replication
3. **Monitor progress** — Poll replication status, display in migration dashboard
4. **Test launch** — Trigger test instance launch in OCI (non-destructive)
5. **Validate** — Run automated validation checks (Section 4)
6. **Cutover** — Final sync, DNS update, source shutdown
7. **Cleanup** — Remove replication artifacts, update status

**For workloads not supported by OCI Cloud Migrations:**
- Generate manual migration runbook with step-by-step instructions
- Recommend partner tools (RackWare, ZConverter) for physical/Hyper-V sources

### 3.2 Database Migration Orchestration

**What:** Recommend and orchestrate the right database migration tool based on source database type.

**Decision tree:**

```
Source Database
├── Oracle DB (any version)
│   ├── Target: OCI Base DB / Exadata → Use ZDM (physical migration)
│   ├── Target: Autonomous DB → Use ZDM (logical migration)
│   └── Large DB (>1TB) with zero downtime → Use ZDM + GoldenGate
├── MySQL / Aurora MySQL
│   ├── Target: OCI MySQL HeatWave → Use OCI DMS
│   └── Alt: mysqldump + import for small DBs
├── PostgreSQL / Aurora PostgreSQL
│   ├── Target: OCI PostgreSQL → Use pg_dump/pg_restore + logical replication
│   └── Alt: DMS with PostgreSQL connector
├── SQL Server
│   ├── Target: OCI Compute (self-managed) → Backup/restore + log shipping
│   └── Alt: Third-party tools (Commvault, etc.)
├── DynamoDB
│   └── Target: OCI NoSQL → Custom ETL (export to S3 → import to OCI)
└── Other
    └── Generate manual migration runbook with recommended approach
```

**Output per database:** Recommended tool, estimated migration time, downtime window, rollback strategy, and step-by-step runbook.

### 3.3 Storage Migration

**What:** Migrate AWS storage to OCI equivalents.

**Mappings:**
| AWS Source | OCI Target | Migration Method |
|---|---|---|
| S3 buckets | OCI Object Storage | rclone sync or OCI CLI bulk upload |
| EBS volumes | OCI Block Volumes | Migrated with VM (OCI Cloud Migrations) |
| EFS | OCI File Storage | rsync over VPN/FastConnect |
| FSx | OCI File Storage | robocopy/rsync |
| Glacier | OCI Archive Storage | S3 restore → rclone to OCI |

**Output:** Migration script per storage resource, estimated transfer time (based on data volume and bandwidth), and cost estimate.

### 3.4 IAM Migration Agent

**What:** Translate and deploy AWS IAM policies to OCI IAM.

**Enhancements over current skill:**
- Go beyond translation to **actual deployment** — apply OCI IAM policies via Terraform
- **Mapping logic:**
  - AWS IAM Users → OCI IDCS Users or federated identity
  - AWS IAM Groups → OCI Groups
  - AWS IAM Roles → OCI Dynamic Groups + Policies
  - AWS IAM Policies → OCI Policy Statements (HCL format)
  - AWS Service-linked Roles → OCI service-specific policies
- **Gap detection:** Flag AWS permissions with no OCI equivalent; suggest alternatives
- **Least-privilege analysis:** Identify over-broad AWS policies and recommend tighter OCI equivalents

### 3.5 Network Migration Agent

**What:** Deploy the translated network topology to OCI.

**Enhancements over current skill:**
- Go beyond translation to **Terraform apply** — deploy the VCN, subnets, NSGs, gateways
- **Pre-deployment validation:** Check for CIDR conflicts with existing OCI networks, quota limits, region availability
- **Connectivity testing:** After deployment, verify routing between subnets, internet access, and VPN/FastConnect connectivity
- **DNS migration:** Import AWS Route 53 zones to OCI DNS (BIND format export/import)

### 3.6 Serverless Migration Recommendations

**What:** Map AWS serverless services to OCI equivalents with migration guidance.

**Mappings:**
| AWS Service | OCI Equivalent | Migration complexity |
|---|---|---|
| Lambda | OCI Functions | Medium — rewrite triggers, use OCI Events |
| API Gateway | OCI API Gateway | Medium — rewrite OpenAPI specs |
| Step Functions | OCI Resource Scheduler + Functions | High — no direct equivalent |
| EventBridge | OCI Events Service | Medium — rewrite event rules |
| SQS | OCI Queue Service | Low — similar API patterns |
| SNS | OCI Notifications | Low — similar pub/sub model |
| DynamoDB | OCI NoSQL Database | High — different data model |

**Output:** Per-service migration guide with code samples, estimated effort, and recommended approach (rehost vs rewrite).

### 3.7 Migration Progress Dashboard

**What:** Real-time dashboard showing migration status across all waves and workloads.

**Features:**
- **Wave-level view:** Progress bar per wave (% of workloads completed)
- **Workload-level view:** Status per workload (Pending, Replicating, Testing, Cutover, Complete, Failed)
- **Resource-level view:** Individual resource migration status with logs
- **Timeline view:** Gantt chart showing planned vs actual migration timeline
- **Alerts:** Notifications for failures, long-running replications, validation errors
- **Metrics:** Total resources migrated, data transferred, estimated time remaining

---

## Phase 4: Validation

### 4.1 Test Migration

**What:** Non-destructive test deployment to validate migrated workloads before cutover. Inspired by Azure Migrate's test migration feature.

**How it works:**
1. Deploy migrated resources to an isolated OCI test compartment and VCN
2. Launch test instances from replicated block volumes
3. Run automated validation checks (Section 4.2)
4. User performs manual acceptance testing
5. Clean up test resources without affecting replication state
6. Generate test report with pass/fail results

**Isolation guarantees:**
- Test VCN has no connectivity to production
- Test instances use separate IP ranges
- DNS not updated — test uses IP-based access
- No impact on ongoing replication

### 4.2 Post-Migration Validation Checklist

**What:** Automated and manual validation checks run after migration (test or production).

**Automated checks:**
| Check | Method | Pass criteria |
|---|---|---|
| Instance reachable | OCI Health Check / ping | Response within 5s |
| SSH/RDP accessible | Port check (22/3389) | Connection established |
| OS boots correctly | Instance console connection | Login prompt visible |
| Disk mounted | OS-level check via cloud-init | All expected volumes present |
| Network connectivity | Ping between dependent instances | All dependencies reachable |
| DNS resolution | nslookup for key hostnames | Correct IP returned |
| Application port open | TCP port check | Service listening |
| Database connectivity | Connection test from app tier | Query returns results |
| Load balancer health | OCI Health Check | Backend servers healthy |
| Outbound internet | curl to known endpoint | HTTP 200 |

**Manual checks (generated checklist):**
- Application login works
- Key business transactions succeed
- Performance is acceptable (response times within SLA)
- Logs are flowing to OCI Logging
- Monitoring alerts are configured
- Backup is scheduled

### 4.3 Rollback Plan Generation

**What:** Pre-generated rollback procedures for every migration wave.

**Content per wave:**
- DNS revert instructions (restore original A/CNAME records)
- Source instance restart procedure
- Data sync-back strategy (if writes occurred on OCI during cutover window)
- OCI resource cleanup Terraform destroy
- Communication template for stakeholders
- Decision criteria for when to trigger rollback (e.g., >30 min application downtime)

### 4.4 Compliance Validation

**What:** Verify migrated infrastructure meets security and compliance standards.

**Checks:**
- **CIS OCI Benchmark** compliance (automated scan)
- **Encryption:** Block volumes encrypted at rest, data in transit over TLS
- **Public exposure:** No unintended public IPs, open security list rules, or public buckets
- **IAM:** No overly broad policies (e.g., `manage all-resources in tenancy`)
- **Logging:** Audit logging enabled, VCN flow logs active
- **Backup:** Backup policies attached to all block volumes and databases
- **Tagging:** All resources tagged per governance policy

**Output:** Compliance report with pass/fail per check, remediation steps for failures, and Terraform patches to fix issues.

### 4.5 Performance Comparison

**What:** Compare pre-migration AWS performance with post-migration OCI performance.

**Metrics compared:**
- CPU utilization (average, peak)
- Memory utilization
- Disk IOPS and latency
- Network throughput
- Application response time (if instrumented)
- Database query performance

**How it works:**
- Pre-migration: CloudWatch metrics collected during assessment (Section 1.2)
- Post-migration: OCI Monitoring metrics collected over configurable window (24h, 7d)
- Side-by-side comparison with delta and percentage change
- Flag any metrics where OCI performance is >20% worse than AWS baseline

---

## Cross-Cutting: AI/Agent Enhancements

### C.1 Agentic Workflow Orchestration

**What:** Upgrade from skill-based translation to full agentic orchestration where specialized agents collaborate on migration tasks.

**Agent types:**
| Agent | Domain | Capabilities |
|---|---|---|
| **Discovery Agent** | Assessment | Resource scanning, inventory, performance collection |
| **Assessment Agent** | Analysis | Rightsizing, 6R classification, readiness scoring, TCO |
| **Network Agent** | Networking | Topology translation, CIDR planning, connectivity validation |
| **Compute Agent** | VMs | Shape mapping, OS compatibility, golden image, VM migration |
| **Data Agent** | Databases & Storage | DB tool selection, schema analysis, storage migration planning |
| **Security Agent** | IAM & Compliance | IAM translation, compliance checking, policy generation |
| **Validation Agent** | Testing | Test migration, health checks, performance comparison |
| **Planning Agent** | Orchestration | Wave planning, dependency resolution, plan generation, progress tracking |

**Orchestration model:**
- Planning Agent is the coordinator — decomposes migration into tasks, assigns to domain agents
- Domain agents work in parallel where possible (e.g., Network Agent + Security Agent)
- Each agent uses the Enhancement → Review → Fix loop (existing pattern)
- Agents share context via a migration knowledge base (resource inventory, dependency graph, plan state)

### C.2 Natural Language Migration Assistant

**What:** Chat-based interface where users can interact with the migration platform using natural language.

**Example interactions:**
- "Show me all workloads that are ready to migrate"
- "What's blocking the payment-service migration?"
- "Compare the cost of rehosting vs replatforming the analytics database"
- "Generate a migration runbook for wave 3"
- "Why did the test migration for web-frontend fail?"

**Implementation:** Claude-powered chat with access to all migration data (resources, plans, jobs, validation results) via tool use.

### C.3 Recommendation Engine for Non-1:1 Mappings

**What:** Intelligent recommendations when AWS services have no direct OCI equivalent.

**Examples:**
| AWS Service | Recommendation | Rationale |
|---|---|---|
| Aurora MySQL | OCI MySQL HeatWave | Managed MySQL with analytics acceleration |
| Aurora PostgreSQL | OCI PostgreSQL or OCI Base DB | Managed PostgreSQL; Base DB for Oracle features |
| DynamoDB | OCI NoSQL Database | Key-value/document store; different API but similar patterns |
| ElastiCache Redis | OCI Cache with Redis | Managed Redis-compatible cache |
| Kinesis | OCI Streaming (Kafka-compatible) | Event streaming with Kafka API compatibility |
| CloudWatch | OCI Monitoring + Logging + Events | Split across 3 services |
| AWS Glue | OCI Data Integration | ETL/data pipeline service |
| SageMaker | OCI Data Science | ML platform with notebook environments |
| EKS | OCI Container Engine (OKE) | Managed Kubernetes |
| Fargate | OCI Container Instances | Serverless containers |

**Output:** For each non-1:1 mapping, provide: recommended OCI service, feature comparison table, migration effort estimate, code/config changes required, and alternative options.

### C.4 Automated Remediation Suggestions

**What:** When validation fails, automatically suggest and optionally apply fixes.

**Examples:**
- Validation: "Security list allows 0.0.0.0/0 on port 22" → Fix: "Restrict to VPN CIDR 10.0.0.0/8" → Generate Terraform patch
- Validation: "Block volume not encrypted" → Fix: "Add encryption with OCI-managed key" → Generate Terraform patch
- Validation: "Instance unreachable on port 443" → Fix: "Add ingress rule to NSG for port 443/TCP" → Generate Terraform patch

### C.5 Cost Optimization Agent

**What:** Continuous post-migration agent that monitors OCI resource utilization and recommends optimizations.

**Recommendations:**
- Downsize underutilized instances (CPU <10% average over 7 days)
- Convert to preemptible instances for fault-tolerant workloads
- Enable autoscaling for variable workloads
- Archive infrequently accessed object storage data
- Right-size block volumes based on actual IOPS usage
- Recommend reserved capacity for stable workloads

---

## Architecture Impact

### New Backend Services
- `services/discovery_scheduler.py` — Scheduled AWS discovery via IAM role assumption
- `services/cloudwatch_collector.py` — Performance metrics collection
- `services/dependency_mapper.py` — Live VPC Flow Log + CloudTrail analysis
- `services/tco_engine.py` — Cost comparison and business case generation
- `services/wave_planner.py` — Dependency-aware wave planning algorithm
- `services/validation_runner.py` — Automated post-migration checks
- `services/migration_orchestrator.py` — (enhanced) Orchestrate OCI Cloud Migrations API

### New Skills (Agents)
- `skills/assessment/` — 6R classification, readiness scoring
- `skills/landing_zone/` — Compartment + VCN + IAM baseline generation
- `skills/golden_image/` — Image recommendation and build script generation
- `skills/serverless_translation/` — Lambda → OCI Functions mapping
- `skills/validation/` — Automated health checks and compliance scanning
- `skills/remediation/` — Auto-fix generation for validation failures

### New Frontend Pages
- Discovery Dashboard — continuous discovery status, resource trends
- Assessment Report — per-workload readiness scores, 6R recommendations
- TCO Comparison — interactive cost comparison with charts
- Wave Planner — drag-and-drop wave organization with dependency visualization
- Migration Control Center — live status across all waves
- Validation Report — test migration results, compliance status
- Chat Assistant — natural language interface

### New Database Models
- `DiscoverySchedule` — scheduled discovery configurations
- `PerformanceMetric` — CloudWatch metric snapshots
- `DependencyEdge` — resource-to-resource dependency with metadata
- `ApplicationGroup` — logical workload grouping
- `MigrationWave` — wave definition with ordering
- `ValidationResult` — per-check pass/fail with evidence
- `CostEstimate` — per-workload AWS vs OCI cost projection

### External Integrations
- AWS STS (AssumeRole for secure credential handling)
- AWS CloudWatch (metrics collection)
- AWS CloudWatch Logs Insights (flow log + CloudTrail queries)
- AWS Cost Explorer (actual cost data)
- AWS Systems Manager (software inventory)
- OCI Cloud Migrations API (VM replication orchestration)
- OCI Monitoring API (post-migration metrics)
- OCI Resource Manager API (Terraform stack deployment)
