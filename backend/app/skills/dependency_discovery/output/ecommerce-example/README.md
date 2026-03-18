# ecommerce-example — AWS → OCI Migration Analysis

**Analysis Date:** 2026-03-12  
**Method:** Real AI Orchestration (Discovery → Runbook → Review → Fix)  
**Account:** ecommerce-example

---

## 📊 Analysis Summary

**Input Data:**
- CloudTrail events: 14
- VPC Flow Logs: 7 connections
- Services detected: 13 (ec2, lambda, dynamodb, rds, elasticache, sqs, sns, s3, secretsmanager, apigateway, sts, iam, vpc)

**Discovery Results:**
- Resources: 24
- Dependencies: 28
- Migration layers: 4
- Critical risks: 4 (HIGH severity)

**AI Agent Calls:**
- Discovery Agent (Opus): 100s, 17.0k tokens
- Runbook Generation Agent (Opus): 220s, 21.0k tokens
- Review Agent - Iteration 1 (Opus, 60s): 60s, 5.0k tokens
- Fix Agent - Iteration 2 (Opus, 482s): 8m2s (timeout), 51.0k tokens
- Review Agent - Iteration 2 (Opus, 70s): 70s, 5.0k tokens
- Fix Agent - Iteration 3 (Opus, 521s): 8m41s (timeout), 67.0k tokens
- Review Agent - Iteration 3 (Opus, 65s): 64s, 5.0k tokens
- Anomaly Agent (Opus, 141s): 141s, 11.0k tokens

**Total:** ~185.0k tokens, ~$9.08

---

## 📁 Files in This Directory

### Core Reports

| File | Description | Size |
|------|-------------|------|
| **migration-runbook.md** | Production-ready migration runbook (5 phases) | ~50 KB |
| **anomaly-analysis.md** | AI-detected risks and ghost dependencies | ~10 KB |
| **dependency-report.txt** | Top dependencies ranked by weight | ~5 KB |
| **ORCHESTRATION-SUMMARY.md** | Complete session summary with metrics | ~5 KB |

### Dependency Graphs

| File | Description | Use Case |
|------|-------------|----------|
| **dependency-graph.dot** | Graphviz DOT source | Regenerate with custom layout |
| **dependency-graph.mmd** | Mermaid diagram | GitHub, Confluence, Notion |

### Data

| File | Description |
|------|-------------|
| **discovery-result.json** | Raw discovery data (resources, dependencies, risks) |
| **logs/** | Agent interaction logs with token usage |

---

## 🔴 Critical Findings

### 1. Multi-account architecture: 2 AWS accounts (555555555555 ecommerce-core, 6666666
- **Risk:** See anomaly-analysis.md for details
- **Mitigation:** Addressed in migration runbook

### 2. RDS PostgreSQL (10.1.5.100) is a shared stateful bottleneck accessed by 3 servic
- **Risk:** See anomaly-analysis.md for details
- **Mitigation:** Addressed in migration runbook

### 3. DynamoDB serves dual roles: 'Orders' table is the system of record accessed by A
- **Risk:** See anomaly-analysis.md for details
- **Mitigation:** Addressed in migration runbook

### 4. Ghost dependency detected: internal HTTPS service at 10.1.7.80 called by ec2-ord
- **Risk:** See anomaly-analysis.md for details
- **Mitigation:** Addressed in migration runbook

---

## 🗺️ Migration Architecture

### Resources Discovered

**Compute:**
- EC2: ec2-order-api
- EC2: ec2-fulfillment-worker
- EC2: ec2-reporting-svc
- EC2: ec2-payment-svc
- EC2: internal-https-svc

**Data Layer:**
- DynamoDB: dynamodb-orders
- DynamoDB: dynamodb-inventory
- S3: s3-order-invoices
- RDS: rds-postgres
- ElastiCache: elasticache-redis

**Messaging:**
- SQS: sqs-order-fulfillment
- SNS: sns-order-notifications

**Security:**
- SecretsManager: secretsmanager-db-creds
- SecretsManager: secretsmanager-smtp-creds

**Entry Point:**
- APIGateway: apigateway-payments

**Other:**
- IAMRole: iam-order-api-role
- IAMRole: iam-fulfillment-worker-role
- IAMRole: iam-notification-lambda-role
- IAMRole: iam-reporting-service-role
- IAMRole: iam-payment-service-role

**Infrastructure:**
- VPC: vpc-main
- VPC: vpc-payments

### Migration Layers (Dependency Order)

```
Layer 1: Foundation
  - vpc-main, vpc-payments, iam-order-api-role, iam-fulfillment-worker-role, ... (+4 more)

Layer 2: Data Layer
  - rds-postgres, elasticache-redis, dynamodb-orders, dynamodb-inventory, ... (+7 more)

Layer 3: Messaging
  - ec2-order-api, ec2-fulfillment-worker, ec2-reporting-svc, lambda-send-order-email

Layer 4: Application
  - ec2-payment-svc

```

---

## 📝 Migration Runbook Highlights

### 5-Phase Migration (16-24 hours)

**Phase 1: Foundation** (T+0 to T+2h)
- VCN, subnets, security lists, route tables
- IAM dynamic groups/policies
- OCI Vault (secrets migration)

**Phase 2: Data Layer** (T+2h to T+8h) ⚠️ **Point of No Return**
- Database migration (DMS replication)
- Cache migration
- Object storage sync

**Phase 3: Messaging** (T+8h to T+10h)
- Queue migration
- Pub/Sub notification migration

**Phase 4: Application** (T+10h to T+14h)
- Compute instances
- Serverless functions

**Phase 5: Entry Point** (T+14h to T+16h)
- API Gateway deployment
- Gradual DNS cutover (10% → 25% → 50% → 100%)

---

## 🚀 How to Use These Files

### View Migration Runbook
```bash
cat migration-runbook.md
# or open in Markdown viewer
```

Sections: Executive Summary, Pre-Migration Checklist (T-7 days), 5 Phases, Post-Migration Validation, Rollback Plan, Risk Mitigation

### Review Anomaly Analysis
```bash
cat anomaly-analysis.md
```

Findings: Unexpected coupling, tight coupling hotspots, ghost dependencies, single points of failure, data consistency risks

### Check Dependency Report
```bash
cat dependency-report.txt
```

Top dependencies ranked by weight with migration recommendations

### Visualize Dependency Graph

**Generate Custom Graph:**
```bash
# Requires: sudo apt install graphviz
dot -Tpng dependency-graph.dot -o custom-graph.png
neato -Tpng dependency-graph.dot -o radial-graph.png
```

**View Mermaid:**
```
# Paste dependency-graph.mmd into:
# - GitHub README
# - https://mermaid.live/
# - Confluence
# - Notion
```

---

## ⚠️ Known Gaps & Next Steps

### Immediate Actions
1. ✅ Dependency analysis complete
2. **VPC Flow Logs deep dive** - confirm ghost dependencies
3. **X-Ray trace analysis** - map service-to-service call patterns
4. **Secrets inventory** - enumerate all secrets
5. **Storage analysis** - determine data volume and dependencies

### Before Migration
6. Review runbook with stakeholders
7. Test data migration scripts with sample data
8. Verify tool compatibility with OCI services
9. Schedule maintenance window (weekend recommended)

### During Migration
10. Follow 5-phase sequence (do not skip phases)
11. Monitor rollback triggers at each phase gate
12. Execute smoke tests before proceeding

---

## 📞 Support

**Questions?** See ORCHESTRATION-SUMMARY.md for complete session details.

**Re-run analysis?**
```bash
# Place updated CloudTrail/Flow Logs in input/ecommerce-example/
python3 aws-dependency-discovery/orchestrator.py ecommerce-example
```

---

**Generated:** 2026-03-12 by AWS Dependency Discovery + Real AI Orchestration  
**Analysis Time:** ~27 minutes (wall time)  
**Output:** 11 files