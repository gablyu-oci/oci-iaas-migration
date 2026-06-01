# Translation Skill Coverage

The authoritative skill registry is `app/agents/skill_group.py` (`SKILL_SPECS`)
and the auto-generated [`docs/agent-architecture.md`](../../docs/agent-architecture.md).
AWS→OCI type mappings live in `backend/data/mappings/resources.yaml`. This page
is a human-readable summary of what each skill covers.

## Translation skills (produce Terraform / artifacts)

| Skill | AWS source | OCI target | Output |
|---|---|---|---|
| `network_translation` | VPC, subnets, SGs, gateways, route tables, ENIs, EIPs, NACLs | OCI VCN family (VCN, subnets, NSGs, gateways, route tables, VNICs) | Terraform HCL |
| `ec2_translation` | EC2 instances, data EBS volumes, ASGs, launch templates | OCI Compute + Block Volumes + Instance Pools | Terraform HCL |
| `storage_translation` | Standalone / data EBS volumes | OCI Block Volumes | Terraform HCL |
| `database_translation` | RDS instances / clusters | OCI Database Systems / MySQL HeatWave / Autonomous DB | Terraform HCL |
| `loadbalancer_translation` | ALB (L7) / NLB (L4) + target groups + listeners | OCI Load Balancer / Network Load Balancer | Terraform HCL |
| `iam_translation` | IAM policies / roles | OCI verb-based policy statements | OCI policy HCL |
| `security_translation` | KMS, Secrets Manager, SSM Parameter Store, ACM, WAFv2 | OCI Vault (keys + secrets), Certificate Service, WAF | Terraform HCL |
| `serverless_translation` | Lambda, API Gateway, Step Functions, EventBridge, Kinesis, ECS, EKS, ECR | OCI Functions, API Gateway, Events, Streaming, Container Instances, OKE, OCIR | Terraform HCL |
| `observability_translation` | CloudWatch alarms/dashboards/logs, SNS, SQS, CloudTrail | OCI Monitoring, Logging, Notifications, Queue, Audit | Terraform HCL |
| `ocm_handoff_translation` | OCM-compatible EC2 instances (hybrid path, replaces `ec2_translation`) | Oracle Cloud Migrations (`oci_cloud_migrations_*`) | Terraform HCL + handoff runbook |
| `cfn_terraform` | CloudFormation templates | OCI Terraform (self-validated with `terraform validate`) | Terraform HCL |

## Planning & meta skills

| Skill | Role | Output |
|---|---|---|
| `data_migration_planning` | DB data cutover runbook (tool selection, phase plan, rollback, downtime estimate) | Markdown runbook |
| `workload_planning` | Per-workload migration runbook + anomaly analysis | Markdown runbook |
| `dependency_discovery` | CloudTrail / VPC flow-log dependency graph analysis | Dependency graph + report |
| `synthesis` | Compose per-skill artifacts into one unified workload Terraform package | Combined artifacts |

## Not yet covered

These AWS services have no dedicated skill and are not yet mapped:

| Resource Type | OCI Target | Priority |
|---|---|---|
| S3 Bucket | OCI Object Storage | High |
| DynamoDB | OCI NoSQL Database | Medium |
| ElastiCache / Redis | OCI Cache with Redis | Medium |
| SageMaker | OCI Data Science | Medium |
| Route 53 / CloudFront | OCI DNS / CDN | Medium |
| Redshift | OCI Autonomous Data Warehouse | Low |
| EMR | OCI Data Flow (Spark) | Low |
| Glue | OCI Data Integration | Low |
| Batch | OCI Container Instances | Low |

## Known gaps within existing skills

- **SQL Server on RDS**: no managed OCI equivalent; recommend self-hosted on Compute.
- **Lambda layers / Step Functions state machines / WebSocket APIs**: flagged by `serverless_translation` as not 1:1 translatable; require manual rework.
- **SSL certificates on ALB/NLB**: must be imported to OCI Certificate Service manually.
- **IAM cross-account roles**: map to OCI tenancy federation (not automated).
- **Local databases on EC2**: detected via SSM inventory; `data_migration_planning` produces the procedure, but database size is unknown until a disk check.
