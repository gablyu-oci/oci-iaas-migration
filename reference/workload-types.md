# Workload Types: AWS to OCI Migration

> A **workload** is the top-level migration entity — a logical unit the user cares about.
> The platform auto-detects workload type based on the resources discovered inside it.

---

## Workload Type Definitions

### 1. Web / API Application
**Detection signals:** EC2 + ALB/NLB + RDS/Aurora + S3 (static assets)
| AWS Resources | OCI Target | Migration Strategy |
|---------------|------------|-------------------|
| EC2 instances | OCI Compute (Flex shapes) | Rehost or Replatform |
| Application Load Balancer | OCI Flexible Load Balancer | Rehost |
| RDS / Aurora | Autonomous DB / MySQL / PostgreSQL | Replatform |
| S3 (static assets) | Object Storage | Rehost |
| Route 53 | OCI DNS | Rehost |
| CloudFront | OCI CDN (Akamai partner) | Replatform |
| Auto Scaling Group | OCI Instance Pool + Autoscaling | Rehost |
| ElastiCache | OCI Cache with Redis | Replatform |

**Assessment focus:** Load balancer config translation, auto-scaling rules, session management, SSL/TLS certificates, health check configuration.

---

### 2. Database
**Detection signals:** Standalone RDS/Aurora (no associated EC2 app tier), or DynamoDB tables
| AWS Resources | OCI Target | Migration Strategy |
|---------------|------------|-------------------|
| RDS MySQL | MySQL DB System or Autonomous DB | Replatform |
| RDS PostgreSQL | PostgreSQL DB System or Autonomous DB | Replatform |
| RDS Oracle | Autonomous DB / Exadata | Replatform |
| RDS SQL Server | Autonomous DB (via migration) | Replatform or Refactor |
| Aurora MySQL/PostgreSQL | Autonomous DB or DB System | Replatform |
| DynamoDB | OCI NoSQL Database | Replatform |
| Redshift | Autonomous Data Warehouse | Replatform |
| ElastiCache Redis | OCI Cache with Redis | Rehost |

**Assessment focus:** Data volume, replication lag tolerance, downtime window, Oracle licensing (BYOL vs included), encryption at rest/transit, backup retention, read replicas.

**Migration tools:** Oracle ZDM, OCI Database Migration Service (DMS), GoldenGate.

---

### 3. AI / ML
**Detection signals:** SageMaker endpoints/notebooks, GPU EC2 instances (p3/p4/g4/g5), S3 training data buckets, ECR with ML framework images
| AWS Resources | OCI Target | Migration Strategy |
|---------------|------------|-------------------|
| SageMaker Notebooks | OCI Data Science Notebooks | Replatform |
| SageMaker Endpoints | OCI Data Science Model Deployment | Replatform |
| GPU EC2 (p3/p4/g4/g5) | OCI GPU shapes (A10, A100, H100) | Rehost or Replatform |
| S3 (training data) | Object Storage | Rehost |
| ECR (ML images) | OCI Container Registry (OCIR) | Rehost |
| Step Functions (ML pipeline) | OCI Data Science Pipelines | Replatform |
| Bedrock / custom models | OCI GenAI Service | Replatform |

**Assessment focus:** GPU shape matching (NVIDIA generation, VRAM), training data volume, model artifact size, inference latency requirements, framework compatibility (PyTorch/TensorFlow/JAX).

---

### 4. Container
**Detection signals:** ECS services/tasks, EKS clusters, ECR repositories, Fargate tasks
| AWS Resources | OCI Target | Migration Strategy |
|---------------|------------|-------------------|
| EKS Cluster | OKE (Container Engine for Kubernetes) | Rehost |
| ECS Services | OKE or OCI Container Instances | Replatform |
| Fargate Tasks | OCI Container Instances | Replatform |
| ECR Repositories | OCIR (Container Registry) | Rehost |
| App Mesh / Service Connect | OCI Service Mesh | Replatform |
| ECS Service Discovery | OKE + CoreDNS | Replatform |

**Assessment focus:** Kubernetes version compatibility, container image registry migration, service mesh config, persistent volume claims, ingress/egress rules, Helm charts, namespace structure.

---

### 5. Data & Analytics
**Detection signals:** Redshift clusters, Glue jobs, EMR clusters, Athena workgroups, Kinesis streams, QuickSight
| AWS Resources | OCI Target | Migration Strategy |
|---------------|------------|-------------------|
| Redshift | Autonomous Data Warehouse | Replatform |
| Glue ETL Jobs | OCI Data Integration | Replatform |
| EMR (Spark/Hadoop) | OCI Data Flow (managed Spark) | Replatform |
| Athena | Autonomous DB (SQL analytics) | Replatform |
| Kinesis Data Streams | OCI Streaming (Kafka-compatible) | Replatform |
| Kinesis Firehose | OCI Service Connector Hub | Replatform |
| QuickSight | OCI Analytics Cloud | Repurchase |
| Lake Formation | OCI Data Catalog | Replatform |

**Assessment focus:** Data volume (TB/PB), query patterns, ETL job complexity, real-time vs batch, data freshness requirements, existing Spark/SQL code compatibility.

---

### 6. Serverless
**Detection signals:** Lambda functions, API Gateway APIs, DynamoDB (as backend), SQS/SNS, Step Functions
| AWS Resources | OCI Target | Migration Strategy |
|---------------|------------|-------------------|
| Lambda Functions | OCI Functions | Replatform |
| API Gateway | OCI API Gateway | Replatform |
| DynamoDB | OCI NoSQL Database | Replatform |
| SQS | OCI Queue | Replatform |
| SNS | OCI Notifications | Replatform |
| Step Functions | OCI Data Integration / custom | Refactor |
| EventBridge | OCI Events Service | Replatform |
| CloudWatch Events | OCI Events + Alarms | Replatform |

**Assessment focus:** Runtime compatibility (Node.js/Python/Java/Go), cold start sensitivity, invocation frequency, memory/timeout limits, VPC connectivity, event source mappings, IAM execution roles.

---

### 7. Storage
**Detection signals:** S3 buckets (large, standalone — not attached to an app), EFS file systems, FSx, Glacier
| AWS Resources | OCI Target | Migration Strategy |
|---------------|------------|-------------------|
| S3 Buckets | OCI Object Storage | Rehost |
| S3 Glacier | OCI Archive Storage | Rehost |
| EFS | OCI File Storage (NFS) | Rehost |
| FSx for Lustre | OCI File Storage (HPC) | Replatform |
| FSx for Windows | OCI File Storage + SMB | Replatform |
| EBS Snapshots | OCI Block Volume backups | Rehost |

**Assessment focus:** Total data volume, object count, access patterns (hot/warm/cold), lifecycle policies, cross-region replication, encryption, bucket policies to OCI IAM policies.

**Migration tools:** OCI Object Storage Transfer (rclone, oci-cli bulk), OCI Data Transfer Appliance (for PB-scale).

---

### 8. Batch / HPC
**Detection signals:** EC2 Spot instances + SQS, AWS Batch, ParallelCluster, large compute-optimized instances
| AWS Resources | OCI Target | Migration Strategy |
|---------------|------------|-------------------|
| AWS Batch | OCI Container Instances / OKE Jobs | Replatform |
| EC2 Spot Instances | OCI Preemptible Instances | Rehost |
| ParallelCluster | OCI HPC cluster networking (RDMA) | Replatform |
| SQS (job queue) | OCI Queue | Rehost |
| Step Functions (orchestration) | OCI Data Integration | Replatform |

**Assessment focus:** Spot/preemptible pricing comparison, job queue depth, compute shape matching (bare metal for HPC), RDMA/cluster networking needs, burst capacity requirements.

---

## Workload Detection Logic

The auto-grouper classifies workloads using this priority:

### Pass 1: Tag-based detection
Resources with matching `Application`, `app`, `project`, `workload`, `stack`, or `environment` tags are grouped together.

### Pass 2: Network topology
Ungrouped resources sharing VPC + subnet + security group communication paths are grouped together.

### Pass 3: Dependency traffic
Groups with heavy cross-group network traffic (from VPC Flow Logs) are merged.

### Pass 4: Type classification
Each group is classified by its dominant resource composition:

```
if has(SageMaker) or has(GPU EC2):           → AI/ML
if has(EKS) or has(ECS) or has(Fargate):     → Container
if has(Lambda) and not has(EC2):              → Serverless
if has(Redshift) or has(EMR) or has(Glue):   → Data & Analytics
if has(RDS/Aurora) and not has(EC2):          → Database
if has(Batch) or has(Spot) and is_compute_heavy: → Batch/HPC
if has(S3) and data_volume > 1TB and not has(EC2): → Storage
if has(EC2) and has(ALB/NLB or RDS):         → Web/API App
else:                                         → Web/API App (default)
```

### Pass 5: AI refinement (optional)
Claude reviews the auto-grouping and suggests:
- Better group names (e.g., "Payment Service" instead of "vpc-0abc-subnet-web")
- Splits for groups that contain multiple logical apps
- Merges for groups that are fragments of one app

---

## Workload-Specific Assessment Criteria

| Criteria | Web/API | Database | AI/ML | Container | Data | Serverless | Storage | Batch |
|----------|---------|----------|-------|-----------|------|------------|---------|-------|
| Compute rightsizing | Yes | N/A | GPU match | Pod sizing | Spark sizing | Memory/timeout | N/A | Spot pricing |
| OS compatibility | Yes | N/A | Yes | Image compat | N/A | Runtime compat | N/A | Yes |
| Data volume | Low priority | Critical | Training data | PV claims | Critical | N/A | Critical | N/A |
| Downtime tolerance | Medium | Low | Medium | Low | Medium | N/A | High | High |
| Network dependencies | Critical | Important | Medium | Critical | Medium | Event sources | N/A | Low |
| Licensing | OS only | DB engine | Framework | K8s version | Tool licenses | N/A | N/A | N/A |
| Cost comparison | Compute+LB | DB pricing | GPU pricing | OKE vs ECS | DW pricing | Invocation pricing | Storage tiers | Spot pricing |
