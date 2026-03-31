# Translation Skill Coverage

## Implemented Skills

| Resource Type | Skill | OCI Target | Output |
|---|---|---|---|
| EC2 Instance / ASG | `ec2_translation` | OCI Compute (Flex shapes) | Terraform HCL |
| VPC / Subnet / SG / ENI | `network_translation` | OCI VCN / Subnet / NSG / VNIC | Terraform HCL |
| EBS Volume | `storage_translation` | OCI Block Volume | Terraform HCL |
| RDS / Aurora | `database_translation` | OCI DB System / MySQL HeatWave / Autonomous DB | Terraform HCL |
| ALB / NLB | `loadbalancer_translation` | OCI Load Balancer / Network LB | Terraform HCL |
| CloudFormation Stack | `cfn_terraform` | Terraform for OCI provider | Terraform HCL |
| IAM Policy / Role | `iam_translation` | OCI IAM Policy (verb-based) | OCI policy JSON |
| Database data (RDS or local) | `data_migration_planning` | Migration procedures | Markdown |
| Per-workload runbook | `workload_planning` | Runbook + anomaly analysis | Markdown |
| Cross-skill synthesis | `migration_synthesis` | Unified Terraform + runbook | Combined artifacts |

## Missing Skills (Future)

| Resource Type | Extracted? | OCI Target | Priority |
|---|---|---|---|
| Lambda Function | Yes (no skill) | OCI Functions (Fn Project) | High |
| S3 Bucket | No | OCI Object Storage | High |
| ECS / EKS / Fargate | No | OCI Container Engine (OKE) | High |
| DynamoDB | No | OCI NoSQL Database | Medium |
| ElastiCache / Redis | No | OCI Cache with Redis | Medium |
| SageMaker | No | OCI Data Science | Medium |
| SNS / SQS | No | OCI Notifications / Queue | Medium |
| Redshift | No | OCI Autonomous Data Warehouse | Low |
| EMR | No | OCI Data Flow (Spark) | Low |
| Glue | No | OCI Data Integration | Low |
| Batch | No | OCI Container Instances | Low |

## Known Gaps in Existing Skills

- **SQL Server on RDS**: No managed OCI equivalent; recommend self-hosted on Compute
- **Lambda layers**: Not supported in OCI Functions
- **Lambda event source mappings**: Require manual reconfiguration for OCI
- **SSL certificates on ALB/NLB**: Must be imported to OCI Certificate Service manually
- **IAM cross-account roles**: Map to OCI tenancy federation (not automated)
- **Local databases on EC2**: Detected via SSM inventory; data_migration_planning handles procedure but database size unknown until disk check
