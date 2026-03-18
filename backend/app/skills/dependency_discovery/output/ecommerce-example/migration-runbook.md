# AWS → OCI Migration Runbook: ecommerce-example

## Document Control

| Field | Value |
|-------|-------|
| **Account** | ecommerce-example |
| **AWS Accounts** | 555555555555 (ecommerce-core), 666666666666 (payments) |
| **Target OCI Tenancy** | `ocid1.tenancy.oc1..aaaaaaaaexample` |
| **Target OCI Region** | us-ashburn-1 (IAD) |
| **Author** | Cloud Migration Architecture Team |
| **Version** | 2.1 |
| **Classification** | CONFIDENTIAL |
| **Planned Maintenance Window** | Saturday 02:00 UTC → Sunday 18:00 UTC (40h) |
| **Estimated Total Downtime** | 90–180 minutes (database cutover + application repointing window — see §3.0 for per-component breakdown) |
| **Total Resources** | 24 AWS resources → OCI equivalents |

---

## 1. Executive Summary

This runbook details the migration of a multi-account e-commerce platform from AWS (2 accounts, 24 resources) to Oracle Cloud Infrastructure. The platform processes orders through a synchronous critical path (Order API → PostgreSQL + Redis + DynamoDB + SQS) with asynchronous fanout (SQS → Fulfillment Worker → SNS → Lambda email notifications). A cross-account payment service in account 666666666666 makes cross-VPC calls to the order API and uses an API Gateway for payment charging.

**Migration Strategy**: Lift-and-shift with service re-platforming where native OCI equivalents exist. The migration follows a 5-phase approach executed over a single extended maintenance window, preceded by 7 days of preparation and followed by 7 days of hypercare.

### 1.1 Dependency Ordering

The migration must follow this strict dependency sequence. Each layer must be validated before the next begins.

```
Layer 1 — Foundation (Phase 1)
  ├── VCN: vcn-ecommerce-main, vcn-payments
  ├── Subnets, Route Tables, Gateways (IGW, NAT, SGW)
  ├── Local Peering Gateway (LPG) main ↔ payments
  ├── Network Security Groups (NSGs)
  ├── IAM: Compartments, Dynamic Groups, Policies
  ├── OCI Vault + Secrets (database-creds, smtp-creds)
  ├── OCI Load Balancer provisioned (without active backends — TLS cert, 
  │     backend set, health checks configured with placeholder/no backends)
  ├── OCI Monitoring: Alarms (CPU, memory, queue depth, DB connections,
  │     API latency, error rates), Logging (compute, functions),
  │     and Notifications for alarm routing
  └── OCI DNS Zone (pre-provisioned, not yet serving traffic)

Layer 2 — Data (Phase 2)
  ├── OCI Database with PostgreSQL (pgsql-ecommerce-orders) — DMS replication from AWS RDS
  ├── OCI NoSQL (nosql-orders, nosql-inventory) — export/import from DynamoDB
  ├── OCI Cache with Redis (redis-ecommerce-cache) — cold migration + warm-up
  └── OCI Object Storage (bucket-order-invoices) — rclone sync from S3

Layer 3 — Messaging (Phase 3)
  ├── OCI Queue (queue-order-fulfillment)
  ├── OCI Notifications (topic-order-notifications)
  ├── OCI Functions (fn-send-order-email) — subscribed to Notifications
  └── OCI API Gateway (apigw-payments)

Layer 4 — Compute / Applications (Phase 4)  ← DOWNTIME BEGINS
  ├── Stop AWS producers (order-api) → drain SQS → verify empty
  ├── Stop DMS CDC, promote OCI PostgreSQL to standalone
  ├── Deploy inst-order-api (points to OCI PostgreSQL, Redis, NoSQL, Queue)
  ├── Deploy inst-fulfillment-worker (consumes OCI Queue, publishes to OCI Notifications)
  ├── Deploy inst-payment-svc (points to OCI API Gateway + order-api via LPG)
  ├── Deploy inst-reporting-svc (reads OCI NoSQL + Object Storage)
  ├── Deploy inst-internal-https-svc (identified service — see §2.1 Item #1)
  ├── Execute Redis warm-up procedure (see §3 Phase 4 for detailed steps)
  └── Attach compute backends to pre-provisioned OCI Load Balancer + validate health checks

Layer 5 — Integration / Entry Point (Phase 5)  ← DOWNTIME ENDS
  ├── DNS weighted routing cutover (Route53 → OCI DNS or weighted CNAME)
  ├── End-to-end smoke tests
  └── Traffic validation → declare migration complete
```

### 1.2 AWS → OCI Service Mapping

| # | AWS Resource | AWS Service | OCI Target Service | OCI Resource Name | Migration Strategy |
|---|-------------|-------------|-------------------|-------------------|-------------------|
| 1 | `vpc-main` (10.1.0.0/16) | VPC | **VCN** | `vcn-ecommerce-main` | Recreate with matching CIDR |
| 2 | `vpc-payments` (10.2.0.0/16) | VPC | **VCN** | `vcn-payments` | Recreate with matching CIDR |
| 3 | VPC Peering (main↔payments) | VPC Peering | **Local Peering Gateway (LPG)** | `lpg-ecommerce-to-payments` | Recreate |
| 4 | `ec2-order-api` | EC2 | **OCI Compute (VM.Standard.E4.Flex)** | `inst-order-api` | Rehost (image migration) |
| 5 | `ec2-fulfillment-worker` | EC2 | **OCI Compute (VM.Standard.E4.Flex)** | `inst-fulfillment-worker` | Rehost (image migration) |
| 6 | `ec2-reporting-svc` | EC2 | **OCI Compute (VM.Standard.E4.Flex)** | `inst-reporting-svc` | Rehost (image migration) |
| 7 | `ec2-payment-svc` | EC2 | **OCI Compute (VM.Standard.E4.Flex)** | `inst-payment-svc` | Rehost (image migration) |
| 8 | `internal-https-svc` | EC2/ALB | **OCI Compute or OCI Load Balancer (LBaaS) — determined by §2.1 Item #1** | `inst-internal-https-svc` | Rehost or recreate — see §2.1 Item #1 resolution and note below |
| 9 | `lambda-send-order-email` | Lambda | **OCI Functions** | `fn-send-order-email` | Replatform (see §2.1 Item #14-FN for details) |
| 10 | `rds-postgres` | RDS PostgreSQL | **OCI Database with PostgreSQL** | `pgsql-ecommerce-orders` | DMS + Blue-Green cutover |
| 11 | `elasticache-redis` | ElastiCache Redis | **OCI Cache with Redis** | `redis-ecommerce-cache` | Cold migration with warm-up (see §2.1 Item #5 and §3 Phase 4 warm-up procedure) |
| 12 | `dynamodb-orders` | DynamoDB | **OCI NoSQL Database** | `nosql-orders` | Full table export/import with schema mapping (see §2.1 Item #7 and Phase 2) |
| 13 | `dynamodb-inventory` | DynamoDB | **OCI NoSQL Database** | `nosql-inventory` | Full table export/import with schema mapping (see §2.1 Item #7 and Phase 2) |
| 14 | `s3-order-invoices` | S3 | **OCI Object Storage** | `bucket-order-invoices` | rclone sync + S3-compatible API (including lifecycle/versioning — see Phase 2) |
| 15 | `sqs-order-fulfillment` | SQS | **OCI Queue** | `queue-order-fulfillment` | Recreate + ordered drain (see Phase 4 cutover) |
| 16 | `sns-order-notifications` | SNS | **OCI Notifications** | `topic-order-notifications` | Recreate + resubscribe |
| 17 | `secretsmanager-db-creds` | Secrets Manager | **OCI Vault** | `secret-database-creds` | Generate new credentials on OCI PostgreSQL (see §2.1 Item #17-SEC) |
| 18 | `secretsmanager-smtp-creds` | Secrets Manager | **OCI Vault** | `secret-email-smtp-creds` | Re-create secret; rotate SMTP credentials post-migration (see §2.1 Item #17-SEC) |
| 19 | `apigateway-payments` | API Gateway | **OCI API Gateway** | `apigw-payments` | Recreate deployment (with auth mapping — see Phase 3) |
| 20 | `iam-order-api-role` | IAM Role | **OCI Dynamic Group + Policy** | `dg-order-api` + `policy-order-api` | Recreate as Dynamic Group matching instance tags + IAM policy granting access to NoSQL, Queue, Object Storage, Vault, Cache |
| 21 | `iam-fulfillment-worker-role` | IAM Role | **OCI Dynamic Group + Policy** | `dg-fulfillment-worker` + `policy-fulfillment-worker` | Recreate as Dynamic Group matching instance tags + IAM policy granting access to Queue, NoSQL, Notifications, Cache |
| 22 | `iam-notification-lambda-role` | IAM Role | **OCI Dynamic Group + Policy** | `dg-notification-functions` + `policy-notification-functions` | Recreate as Dynamic Group matching OCI Functions resources + IAM policy granting access to Vault secrets |
| 23 | `iam-reporting-service-role` | IAM Role | **OCI Dynamic Group + Policy** | `dg-reporting-svc` + `policy-reporting-svc` | Recreate as Dynamic Group matching instance tags + IAM policy granting read access to NoSQL, Object Storage |
| 24 | `iam-payment-service-role` + `iam-payment-gateway-access` | IAM Roles (cross-account) | **OCI Cross-Compartment Policy** | `policy-payment-cross-compartment` + `dg-payment-svc` | Consolidate into OCI tenancy-level cross-compartment policies granting payment service access to API Gateway and network in ecommerce-core |
| — | ALB/NLB (external ingress) | Elastic Load Balancing | **OCI Load Balancer (LBaaS)** | `lb-ecommerce-public` | Recreate — provisioned in Layer 1 (Foundation) with TLS certificate, backend set, and health checks pre-configured; backends attached in Layer 4 during cutover |
| — | Route 53 hosted zone + records | Route 53 | **OCI DNS** | `dns-zone-ecommerce` | Pre-provision OCI DNS zone in Layer 1; DNS cutover via weighted routing in Phase 5 |
| — | CloudWatch metrics, logs, alarms | CloudWatch | **OCI Monitoring + OCI Logging + OCI Notifications (Alarms)** | `alarm-*`, `log-group-*`, `topic-ops-alerts` | Recreate alarms (CPU, memory, queue depth, DB connections, API latency, error rates), configure logging agents on compute instances, configure OCI Notifications for alarm routing — deployed in Layer 1 before traffic cutover |
| — | ACM certificates | ACM | **OCI Certificates Service** | `cert-ecommerce`, `cert-apigw-payments` | Import or issue new TLS certificates during pre-migration (T-4d); associate with Load Balancer and API Gateway |

> **⚠ Resource #8 — `internal-https-svc` Resolution Requirements**: This resource at 10.1.7.80:443 **must** be fully identified before migration execution begins. Pre-migration checklist Item #1 (§2.1) gates this. The following must be documented:
>
> 1. **Identity**: Is this an internal load balancer, a standalone microservice, a reverse proxy (e.g., nginx/envoy), or an ECS/EKS service?
> 2. **Function**: What business function does it serve? (e.g., internal API aggregation, TLS termination, health checking)
> 3. **Upstream callers**: Which services call 10.1.7.80:443? (order-api? payment-svc? fulfillment-worker?)
> 4. **Downstream dependencies**: What does this service call? (PostgreSQL? external APIs? other internal services?)
> 5. **Port/protocol details**: HTTP/HTTPS, TLS certificate requirements, health check path
> 6. **Data contract**: Request/response format, API schema
> 7. **Layer placement**: If this service has no data dependencies (e.g., it is a proxy), it may be moved to Layer 3 or Layer 4. If it is a dependency for payment-svc or order-api in the critical order path, it must be deployed before those consumers. Current Layer 2 placement assumes it has data-tier characteristics — adjust once identity is confirmed.
>
> **OCI target mapping**:
> - If discovery reveals it is an **internal load balancer** → map to **OCI Load Balancer (LBaaS)** (private, internal)
> - If it is a **standalone application** → map to **OCI Compute** (rehost)
> - If it is a **reverse proxy/envoy** → map to **OCI Compute** or **OCI API Gateway** (internal)
>
> The final OCI target will be recorded in this table once discovery is complete. **⛔ DO NOT PROCEED to Phase 4 without a definitive answer.**

### 1.3 Architecture Diagram (Conceptual)

```
                            ┌─── External Traffic ───┐
                            │  DNS (Route53 → OCI)   │
                            │  TLS Certificate (OCI)  │
                            └──────────┬─────────────┘
                                       │
                            ┌──────────▼─────────────┐
                            │  OCI Load Balancer      │
                            │  (Public, HTTPS:443)    │
                            └──────────┬─────────────┘
                                       │
┌─────────────────────────────── OCI Tenancy ───────────────────────────────────┐
│                                                                                │
│  ┌── Compartment: ecommerce-core ──────────────────────────────────────────┐  │
│  │                                                                          │  │
│  │  VCN: vcn-ecommerce-main (10.1.0.0/16)                                 │  │
│  │  ┌─────────────┐  ┌──────────────────┐  ┌──────────────────┐           │  │
│  │  │ inst-order- │→ │ pgsql-ecommerce  │  │ redis-ecommerce  │           │  │
│  │  │ api (10.1.  │→ │ (10.1.5.100)     │  │ (10.1.6.50)      │           │  │
│  │  │ 1.20)       │→ │                  │  │                  │           │  │
│  │  └──────┬──────┘  └──────────────────┘  └──────────────────┘           │  │
│  │         │  ↓ OCI Queue                                                  │  │
│  │  ┌──────┴──────────┐  ┌──────────────────┐  ┌─────────────────┐        │  │
│  │  │ queue-order-    │→ │ inst-fulfillment │→ │ topic-order-    │        │  │
│  │  │ fulfillment     │  │ worker (10.1.2.30)│ │ notifications   │        │  │
│  │  └─────────────────┘  └──────────────────┘  └───────┬─────────┘        │  │
│  │                                                       ↓                  │  │
│  │  ┌─────────────────┐  ┌──────────────────┐  ┌───────┴─────────┐        │  │
│  │  │ inst-reporting  │  │ bucket-order-    │  │ fn-send-order-  │        │  │
│  │  │ svc (10.1.4.50) │  │ invoices         │  │ email           │        │  │
│  │  └─────────────────┘  └──────────────────┘  └─────────────────┘        │  │
│  │                                                                          │  │
│  │  NoSQL: nosql-orders, nosql-inventory                                   │  │
│  │  Vault: secret-database-creds, secret-email-smtp-creds                  │  │
│  │  Internal: inst-internal-https-svc (10.1.7.80)                          │  │
│  │  Monitoring: OCI Monitoring alarms, OCI Logging, ops-alerts topic       │  │
│  └──────────────────────────────┬───────────────────────────────────────────┘  │
│                                 │ LPG                                          │
│  ┌── Compartment: payments ─────┴──────────────────────────────────────────┐  │
│  │  VCN: vcn-payments (10.2.0.0/16)                                       │  │
│  │  ┌─────────────────┐  ┌──────────────────┐                              │  │
│  │  │ inst-payment-   │→ │ apigw-payments   │                              │  │
│  │  │ svc (10.2.1.10) │  │ /v1/payments/    │                              │  │
│  │  └─────────────────┘  └──────────────────┘                              │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Pre-Migration Checklist (T-7 Days)

All items must be completed and signed off **before** the migration window opens.

### 2.1 Discovery & Dependency Resolution

| # | Item | Owner | Status | Due |
|---|------|-------|--------|-----|
| 1 | **Identify ghost dependency at 10.1.7.80:443** — Run `aws ec2 describe-network-interfaces --filters Name=addresses.private-ip-address,Values=10.1.7.80` and cross-reference with Route53 records, ALB target groups, and ECS/EKS services. Document: (a) service name; (b) function (microservice, proxy, internal LB, etc.); (c) port, protocol, health check path; (d) TLS certificate requirements; (e) all upstream callers (who calls this service?); (f) all downstream dependencies (what does it call?); (g) data contract (request/response format); (h) correct layer placement in dependency ordering (update §1.1 if Layer 2 is incorrect). Assign a **definitive** OCI target service (Compute, LBaaS, or API Gateway) and update §1.2 Resource #8 accordingly. If it is a dependency for payment-svc or order-api, ensure it is deployed before those consumers in Layer 4. | Infra Lead | ☐ | T-7d |
| 2 | **Inventory all DynamoDB access patterns** — Enable DynamoDB CloudWatch Contributor Insights on `Orders` and `Inventory` tables for 7 days. Document all partition keys, sort keys, GSI/LSI usage, throughput patterns, consistency model usage (eventually consistent vs strongly consistent reads), and on-demand vs provisioned capacity mode. Capture table sizes in GB to estimate NoSQL import time. (Only 14 events sampled; real load is 10-50x higher). | Data Lead | ☐ | T-7d |
| 3 | **Audit RDS PostgreSQL schema and extensions** — Run `SELECT * FROM pg_extension;` and `SELECT * FROM pg_stat_user_tables;`. Document table sizes, row counts, custom extensions (PostGIS, pg_cron, etc.), replication slots, and logical replication compatibility. | DBA | ☐ | T-7d |
| 4 | **Document all hardcoded IPs** — grep application config, environment variables, and container images for `10.1.*` and `10.2.*` patterns. Catalog every instance. Verify whether payment service uses IP `10.1.1.20` directly or a DNS name. | App Lead | ☐ | T-6d |
| 5 | **Validate ElastiCache Redis serialization and document warm-up strategy** — Confirm Redis version (engine version), data structures used (strings, hashes, sorted sets), max memory policy, and whether RDB snapshots are compatible with OCI Cache with Redis target version. **Document what data is cached** (sessions, product catalog, order lookups), determine if cache-aside pattern is used (auto-populates on miss), or if pre-warming scripts are needed. If session data is stored in Redis, document the impact of session invalidation on active users. **Specifically document**: (a) Which keys must be pre-populated before traffic cutover (product catalog, rate-limiting counters, etc.); (b) Expected cache miss rate during warm-up and estimated duration until cache hit ratio stabilizes; (c) PostgreSQL capacity to handle cache-miss thundering herd load (run load test against OCI PostgreSQL with cold cache); (d) Whether a gradual traffic ramp (canary/weighted DNS at 10%→25%→50%→100%) will be used to limit cold-cache impact; (e) Whether RDB snapshot export from ElastiCache and import to OCI Cache is supported for the target Redis version — if so, prefer this over cold migration to preserve session data. | App Lead | ☐ | T-6d |
| 6 | **Catalog SQS message formats and DLQ config** — Document message schema, visibility timeout, max receive count, dead-letter queue configuration, and current approximate message count. Verify idempotency of fulfillment-worker message processing. | App Lead | ☐ | T-6d |
| 7 | **DynamoDB → OCI NoSQL schema mapping** — Document the full data model mapping: (a) Partition key and sort key translation for both tables; (b) All Global Secondary Indexes (GSIs) and Local Secondary Indexes (LSIs) — map to OCI NoSQL secondary indexes or child tables; (c) Capacity mode decision (on-demand → ON_DEMAND, provisioned → PROVISIONED with specific RU/WU values based on CloudWatch metrics); (d) Consistency model mapping (DynamoDB eventual/strong consistent reads → OCI NoSQL EVENTUAL/ABSOLUTE consistency); (e) TTL attribute mapping if used; (f) Stream/CDC mapping — if DynamoDB Streams are enabled, document the OCI equivalent (OCI NoSQL change data capture, or an alternative pattern using OCI Events + Functions to replicate stream-triggered logic). | Data Lead | ☐ | T-6d |
| 8 | **S3 bucket configuration audit** — Document `s3-order-invoices` bucket configuration: versioning status, lifecycle policies (transition to IA/Glacier, expiration rules), event notifications (S3 → Lambda/SNS/SQS triggers), bucket policy, CORS configuration, server-side encryption settings, and replication rules. Map each to OCI Object Storage equivalents: object lifecycle rules, OCI Events + Rules, IAM policies, CORS, SSE with Vault keys. | Data Lead | ☐ | T-6d |
| 9 | **Document current external ingress path** — Audit and document: (a) ALB/NLB configuration (listeners, target groups, health checks, stickiness, WAF rules); (b) Route53 hosted zones, record types, TTL values, and health checks; (c) ACM certificate ARNs, domains covered (wildcard vs specific), and expiration dates; (d) Any CloudFront distributions in front of the ALB. Map to OCI equivalents: OCI Load Balancer, OCI DNS Zone, OCI Certificates Service. | Infra Lead | ☐ | T-6d |
| 10 | **Document API Gateway authentication mechanism** — Audit `apigateway-payments` in AWS: (a) Authentication type (IAM auth, API keys, Lambda authorizers, Cognito/OAuth2); (b) Authorization policies and resource policies; (c) Rate limiting / throttling configuration; (d) Request/response mapping templates; (e) Custom domain and TLS certificate. Map to OCI API Gateway equivalents: OCI Identity-based authentication, custom authorizer functions (OCI Functions), mTLS, or API key validation. Document all cross-compartment network security list rules needed for payment-svc → order-api traffic over LPG. | Security | ☐ | T-6d |

### 2.2 Application Code Refactoring (Pre-Migration)

> **⚠ CRITICAL**: Moving from AWS SDK-dependent services to OCI equivalents requires significant code modifications. All code changes **must** be completed, tested, and ready to deploy before the maintenance window opens.

| # | Item | Owner | Status | Due |
|---|------|-------|--------|-----|
| 11 | **order-api: Replace AWS SDK calls with OCI SDK** — Refactor the following integrations: (a) `boto3` DynamoDB client → OCI NoSQL SDK (`borneo` for Python or `nosqldriver` for Java) for Orders/Inventory table access; (b) `boto3` SQS client → OCI Queue SDK for message publishing; (c) `boto3` S3 client → OCI Object Storage SDK (or retain S3-compatible API if using rclone-style access); (d) `boto3` Secrets Manager client → OCI Vault SDK for secret retrieval; (e) ElastiCache Redis connection string → OCI Cache Redis endpoint. Build OCI-compatible application artifact. | App Lead | ☐ | T-5d |
| 12 | **fulfillment-worker: Replace AWS SDK calls with OCI SDK** — Refactor: (a) `boto3` SQS consumer → OCI Queue SDK for message consumption (note: OCI Queue uses long-polling with different API); (b) `boto3` DynamoDB client → OCI NoSQL SDK for Orders/Inventory updates; (c) `boto3` SNS client → OCI Notifications SDK for publishing to topic-order-notifications; (d) Any Secrets Manager calls → OCI Vault SDK. Build OCI-compatible application artifact. | App Lead | ☐ | T-5d |
| 13 | **payment-svc: Update API endpoint configuration** — Update payment service to call OCI API Gateway endpoint instead of AWS API Gateway. Verify TLS certificate validation. Update any IAM SigV4 signing logic to OCI request signing or token-based auth as determined by Item #10. | App Lead | ☐ | T-5d |
| 14 | **lambda-send-order-email → fn-send-order-email: Replatform** — Rewrite Lambda handler to OCI Functions SDK. Specific changes required: (a) **Target runtime**: Confirm runtime version compatibility (e.g., Python 3.9+ or Node.js 18+ — must match OCI Functions supported runtimes); (b) **Trigger mechanism change**: Replace AWS SNS subscription trigger with OCI Notifications subscription — the incoming event payload format differs (SNS `Records[].Sns.Message` → OCI Notifications JSON body); update event parsing logic accordingly; (c) **Secrets access pattern change**: Replace `boto3` Secrets Manager `get_secret_value()` calls with OCI Vault SDK `get_secret_bundle()` — requires OCI config or instance principal authentication instead of AWS IAM role; (d) **SMTP credential access**: If Lambda accessed SMTP credentials via environment variables sourced from Secrets Manager, update to retrieve from OCI Vault at function invocation time (or use OCI Functions config for non-sensitive values); (e) **Function entry point**: Update handler signature from Lambda `handler(event, context)` to OCI Functions `handler(ctx, data)` format; (f) **Container image**: Build and push container image to OCI Container Registry (OCIR) — OCI Functions uses Docker images, not ZIP packages; (g) **Pre-migration testing**: Test locally using `fn invoke --local` and in OCI staging environment — validate: secret retrieval from Vault, email sending via SMTP, correct parsing of OCI Notifications event format, and error handling/retry behavior. | App Lead | ☐ | T-4d |
| 15 | **reporting-svc: Replace AWS SDK calls with OCI SDK** — Refactor: (a) DynamoDB read calls → OCI NoSQL SDK; (b) S3 read calls → OCI Object Storage SDK (or S3-compatible API). | App Lead | ☐ | T-5d |
| 16 | **Test all modified code in OCI staging environment** — Deploy all refactored services to a staging OCI compartment. Execute functional tests covering: database CRUD, queue publish/consume, object storage read/write, vault secret retrieval, notification publish, and cross-compartment API call. Document test results and any issues. | QA Lead | ☐ | T-3d |

### 2.3 OCI Tenancy Preparation

| # | Item | Owner | Status | Due |
|---|------|-------|--------|-----|
| 17 | **OCI tenancy provisioned** — Confirm tenancy `ocid1.tenancy.oc1..aaaaaaaaexample` is active with service limits raised for: Compute (VM.Standard.E4.Flex ×5), OCI Database with PostgreSQL (×1), OCI Cache with Redis (×1), NoSQL tables (×2), Object Storage (5TB), OCI Queue (×1), Notifications topics (×2 — one for order notifications, one for ops alerts), Functions applications (×1), API Gateway (×1), Vault (×1), Load Balancer (×1), DNS Zone (×1), Certificates (×2), Monitoring alarms (×20), Log Groups (×5). | Cloud Ops | ☐ | T-6d |
| 18 | **Create OCI compartment hierarchy** — Create `ecommerce-core` and `payments` compartments under root. | Cloud Ops | ☐ | T-6d |
| 19 | **Configure OCI IAM Identity Domains** — Create service user accounts for automation. Configure federation if using centralized IdP. | Security | ☐ | T-5d |
| 20 | **Generate OCI API signing keys** — Create API keys for all service accounts and OCI CLI profiles. Test `oci os ns get` from migration workstation. | Cloud Ops | ☐ | T-5d |
| 21 | **Provision OCI Vault** — Create master encryption key for secrets and database TDE. Vault must be ACTIVE before migration window. | Security | ☐ | T-5d |
| 22 | **Set up OCI CLI and Terraform** — Install OCI CLI v3.x, configure `~/.oci/config` profiles for both compartments. Validate with `oci iam region list`. | Cloud Ops | ☐ | T-5d |
| 23 | **Provision OCI TLS certificates** — Request or import TLS certificates via OCI Certificates Service for: (a) external-facing load balancer (matching current ACM certificate domains); (b) OCI API Gateway (apigw-payments). If using Let's Encrypt or public CA, initiate certificate issuance. If importing existing certificates, export private key from ACM (if possible) or generate new CSR. | Security | ☐ | T-4d |

### 2.4 Data Migration Preparation

| # | Item | Owner | Status | Due |
|---|------|-------|--------|-----|
| 24 | **Begin S3 → Object Storage pre-sync** — Start initial rclone sync of `acme-order-invoices` bucket. This can run continuously through T-0 to minimize final delta. Document S3 bucket versioning status and configure OCI bucket versioning to match. Replicate lifecycle rules to OCI Object Storage lifecycle policies. Configure OCI Events rules to match any S3 event notifications. | Data Lead | ☐ | T-5d |
| 25 | **Export DynamoDB tables to S3** — Perform PITR export of both `Orders` and `Inventory` tables to S3 in DynamoDB JSON format. Validate export completeness. **Record table sizes**: if either table exceeds 10GB, flag for extended downtime estimate and consider DynamoDB Streams-based CDC for incremental sync instead of full export during cutover. | Data Lead | ☐ | T-4d |
| 26 | **Set up AWS DMS for PostgreSQL** — Configure DMS replication instance, source endpoint (RDS), test connectivity. Do NOT start replication yet. Document replication instance ARN. | DBA | ☐ | T-4d |
| 27 | **Create RDS read replica for migration** — Create a read replica to use as DMS source, minimizing impact on production RDS. | DBA | ☐ | T-4d |
| 28 | **Package Lambda function for OCI Functions** — Rewrite `send-order-email` Lambda handler to OCI Functions SDK (Python/Java). Replace `boto3` Secrets Manager calls with OCI Vault SDK calls. Replace SNS trigger with OCI Notifications subscription. Build and test container image locally. | App Lead | ☐ | T-3d |
| 29 | **Prepare DynamoDB → OCI NoSQL conversion scripts** — Based on schema mapping from Item #7, build and test `dynamodb_to_nosql_converter.py` that handles: (a) DynamoDB type descriptors (S, N, M, L, BOOL, NULL) → OCI NoSQL native types; (b) GSI data into separate OCI NoSQL indexes or denormalized child tables; (c) TTL attribute conversion if applicable. Validate with sample data export. | Data Lead | ☐ | T-3d |
| 30 | **Prepare Redis warm-up scripts** — Based on discovery from Item #5: (a) If cache-aside pattern is used and all cache entries are populated on-miss, document expected cache miss rate and latency impact during warm-up period; (b) If pre-warming is required (e.g., product catalog, rate limits), write scripts to seed OCI Redis from source data (PostgreSQL queries or DynamoDB scans); (c) If session data is critical, plan for user re-authentication communication; (d) **If RDB snapshot import is feasible** (confirmed in Item #5), prepare export script: `aws elasticache create-snapshot` → download RDB file → test import to OCI Cache; (e) Run load test against OCI PostgreSQL with simulated cold-cache traffic (cache-miss thundering herd scenario) to validate database can handle the additional load during warm-up. | App Lead | ☐ | T-3d |

### 2.5 Application & Network Preparation

| # | Item | Owner | Status | Due |
|---|------|-------|--------|-----|
| 31 | **Create AMI snapshots of all EC2 instances** — Create golden AMIs of `ec2-order-api`, `ec2-fulfillment-worker`, `ec2-reporting-svc`, `ec2-payment-svc`, `internal-https-svc`. Export as VMDK/QCOW2 for OCI custom image import. | Infra Lead | ☐ | T-3d |
| 32 | **Export EC2 images to OCI-compatible format** — Use `aws ec2 export-image` to export to QCOW2. Upload to OCI Object Storage for custom image creation. | Infra Lead | ☐ | T-3d |
| 33 | **Prepare application configuration overlays** — Create OCI-specific config files for each service: new database connection strings (OCI PostgreSQL), Redis endpoint (OCI Cache), NoSQL connection info, Queue OCID, Object Storage namespace/bucket. **All config files must point to OCI SDK endpoints and use OCI authentication (instance principal).** | App Lead | ☐ | T-2d |
| 34 | **DNS TTL reduction** — Reduce TTL on all external DNS records pointing to the ecommerce platform to **60 seconds** (from typical 300-3600s). Verify propagation with `dig` from multiple resolvers. Record all current DNS records, types, and TTL values for rollback reference. | Infra Lead | ☐ | T-2d |
| 35 | **Notify payment service stakeholders** — Coordinate with account 666666666666 owners. Confirm maintenance window. Provide new OCI endpoint details for payment API gateway. | Project Lead | ☐ | T-2d |
| 36 | **Freeze all deployments** — Code freeze on all repositories. No infrastructure changes in AWS accounts 555555555555 or 666666666666 from T-2d onward. | Project Lead | ☐ | T-2d |
| 37 | **Establish VPN or FastConnect between AWS and OCI** — Set up Site-to-Site VPN between AWS VPC and OCI VCN for hybrid connectivity during migration (DMS replication, validation). Verify bidirectional routing for 10.1.0.0/16 and 10.2.0.0/16. | Network Lead | ☐ | T-3d |
| 38 | **Runbook dry run on staging** — Execute complete runbook against staging/dev environment. **Record actual elapsed time for each phase and each critical step** (especially DynamoDB export/import, DMS full-load, Redis warm-up, LB health check stabilization, and DNS propagation). Update downtime estimates in §3.0 based on actual measurements. Identify gaps and update runbook. | Migration Lead | ☐ | T-1d |
| 39 | **Stakeholder sign-off** — Obtain written approval from Engineering VP, Security Lead, and Product Owner. Confirm rollback authority and escalation contacts. | Project Lead | ☐ | T-1d |

### 2.6 Secrets Migration Procedure

> **⚠ SECURITY**: Secrets must never be stored in runbook documents, migration scripts, or logs in plaintext.

| # | Item | Owner | Status | Due |
|---|------|-------|--------|-----|
| 17-SEC-1 | **Generate new database credentials on OCI PostgreSQL** — Do NOT copy AWS database credentials. Create a new `pgadmin` password on the OCI PostgreSQL instance. Store the new credentials in OCI Vault as `secret-database-creds`. Update application configuration overlays (Item #33) to reference the OCI Vault secret OCID. | DBA + Security | ☐ | T-3d |
| 17-SEC-2 | **Migrate SMTP credentials to OCI Vault** — Retrieve SMTP credentials from AWS Secrets Manager (via secure workstation, not scripts that log output). Store in OCI Vault as `secret-email-smtp-creds`. Verify the OCI Functions application (fn-send-order-email) can retrieve the secret using OCI Vault SDK with instance principal auth. | Security | ☐ | T-3d |
| 17-SEC-3 | **Document application code changes for OCI Vault SDK** — For each service that accesses secrets, document the specific code change: (a) order-api: replace `boto3 secretsmanager get_secret_value(SecretId='prod/database-creds')` with `oci.secrets.SecretsClient.get_secret_bundle(secret_id=<OCID>)`; (b) fn-send-order-email: same pattern for SMTP creds; (c) Ensure all services use instance principal authentication (`oci.auth.signers.get_resource_principals_signer()`) — no API keys embedded in application code. | App Lead | ☐ | T-4d |
| 17-SEC-4 | **Post-migration: Rotate SMTP credentials** — After migration is validated and hypercare begins, rotate SMTP credentials (generate new credentials from SMTP provider, update OCI Vault secret version, verify email delivery). | Security | ☐ | T+7d (Hypercare) |
| 17-SEC-5 | **Post-migration: Revoke AWS credentials** — After hypercare sign-off, disable/delete all AWS Secrets Manager secrets and IAM access keys. | Security | ☐ | T+14d (Post-Hypercare) |

### 2.7 Pre-Migration Validation Gates

| Gate | Criteria | Verified |
|------|----------|----------|
| G1 | Ghost service at 10.1.7.80 fully identified, OCI target assigned, dependencies/dependents documented, layer placement confirmed, and migration plan documented | ☐ |
| G2 | OCI tenancy service limits confirmed sufficient (including LB, DNS, Certificates, Monitoring alarms, Log Groups) | ☐ |
| G3 | VPN/FastConnect tunnel UP and routing verified (ping test) | ☐ |
| G4 | S3 pre-sync >95% complete | ☐ |
| G5 | DynamoDB export validated (row counts match) and table sizes recorded for timing estimate | ☐ |
| G6 | All EC2 images exported and uploaded to OCI Object Storage | ☐ |
| G7 | OCI Functions container image tested locally and pushed to OCIR | ☐ |
| G8 | All application code refactored and tested in OCI staging environment (Items #11–16) | ☐ |
| G9 | DynamoDB → OCI NoSQL schema mapping completed with GSI/LSI equivalents documented | ☐ |
| G10 | Redis warm-up strategy documented, scripts prepared, and PostgreSQL cold-cache load test passed | ☐ |
| G11 | API Gateway authentication mapping documented and tested | ☐ |
| G12 | DNS TTLs reduced to 60s and verified propagation | ☐ |
| G13 | OCI TLS certificates provisioned and ACTIVE | ☐ |
| G14 | Staging dry-run completed successfully with timing data recorded and §3.0 downtime estimates updated | ☐ |
| G15 | Stakeholders signed off and rollback authority confirmed | ☐ |
| G16 | S3 bucket lifecycle rules, event notifications, versioning, and CORS mapped to OCI equivalents | ☐ |
| G17 | New database credentials generated on OCI PostgreSQL and stored in OCI Vault (not copied from AWS) | ☐ |
| G18 | SMTP credentials stored in OCI Vault and accessible from OCI Functions | ☐ |
| G19 | OCI Functions replatform validated: event parsing, Vault secret retrieval, SMTP sending, and error handling all tested in staging | ☐ |
| G20 | Rollback procedures reviewed and understood by all team members (§6 Rollback Plan) | ☐ |
| G21 | OCI Monitoring alarms, Logging, and Notifications for ops alerts configured and tested | ☐ |

**⛔ DO NOT PROCEED if any gate is FAIL.**

---

## 3. Migration Phases

### 3.0 Downtime Estimate Breakdown

> **⚠ IMPORTANT**: These estimates must be validated during the dry-run (Item #38). DynamoDB import time scales with table size. Update the table below with actual dry-run timings.

| Component | Step | Estimated Duration | Dry-Run Actual | Notes |
|-----------|------|-------------------|----------------|-------|
| SQS → OCI Queue | Stop producers, drain SQS, verify empty | 5–15 min | ___ min | Depends on queue depth at cutover time |
| PostgreSQL | Stop DMS CDC + promote OCI PG | 5–10 min | ___ min | CDC lag must be < 5s before stop |
| DynamoDB Orders | Final delta export + convert + import | 15–60 min | ___ min | **Highly dependent on table size**. If >10GB, consider pre-cutover CDC approach |
| DynamoDB Inventory | Final delta export + convert + import | 10–30 min | ___ min | Typically smaller than Orders |
| Object Storage | Final rclone delta sync | 2–5 min | ___ min | Delta should be small if pre-sync ran continuously |
| Redis | Cold start (no data migration) | 0 min | ___ min | Warm-up runs post-cutover in background |
| Application repointing | Deploy 5 compute instances with OCI config | 15–30 min | ___ min | Parallel launches, serial health checks |
| Redis warm-up | Pre-warm critical keys + cache-aside stabilization | 5–15 min | ___ min | Pre-warm scripts for product catalog/rate limits; cache-aside fills organically |
| Load Balancer | Attach backends to pre-provisioned LB, health check pass | 5–10 min | ___ min | LB already provisioned in Phase 1; only backend attachment needed |
| DNS propagation | Weighted routing cutover + propagation wait | 2–5 min | ___ min | TTL pre-reduced to 60s; most resolvers update within 60-120s |
| End-to-end validation | Smoke tests before declaring downtime end | 15–20 min | ___ min | Must pass before declaring downtime end |
| **Total estimated downtime** | | **90–180 min** | **___ min** | **Validate with dry-run; update before go/no-go** |

### Timeline Overview

```
T+0h        T+2h        T+6h        T+10h       T+14h    T+16h    T+40h
 │           │           │            │            │        │        │
 ▼           ▼           ▼            ▼            ▼        ▼        ▼
┌───────────┬───────────┬────────────┬────────────┬────────┬────────┐
│  Phase 1  │  Phase 2  │  Phase 3   │  Phase 4   │Phase 5 │Post-   │
│Foundation │Data Layer │ Messaging  │Application │Entry   │Migrate │
│  (2h)     │  (4h)     │  (4h)      │  (4h)      │Point   │Valid.  │
│           │           │            │            │ (2h)   │        │
└───────────┴───────────┴──────┬─────┴────────────┴────────┴────────┘
                               │
                    ═══════════╪════════════════
                     POINT OF NO RETURN (T+8h)
                    ═══════════╪════════════════
                               │

  ◄──── No downtime ────►◄──── No downtime ────►◄─ DOWNTIME ─►◄── UP ──►
  (AWS still serving)     (AWS still serving)    (Phase 4-5)
```

> **Note**: Phases 1–3 are non-impacting — AWS continues serving production traffic. Downtime begins at Phase 4 when AWS producers are stopped for cutover.

---

### Phase 1: Foundation (T+0h → T+2h)

**Objective**: Provision OCI networking (VCNs, subnets, gateways, peering), IAM (compartments, dynamic groups, policies), Vault with secrets, Load Balancer (pre-provisioned without active backends), Monitoring/Logging infrastructure, and DNS zone.

**Entry Criteria**: All pre-migration gates passed. Migration team assembled. AWS console and OCI console access verified.

#### T+0h:00 — Create Compartments

```bash
# Create ecommerce-core compartment
oci iam compartment create \
  --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample \
  --name "ecommerce-core" \
  --description "Ecommerce core services migrated from AWS 555555555555" \
  --wait-for-state ACTIVE

# Capture compartment OCID
export COMPARTMENT_CORE=$(oci iam compartment list \
  --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample \
  --name "ecommerce-core" \
  --query 'data[0].id' --raw-output)

# Create payments compartment
oci iam compartment create \
  --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample \
  --name "payments" \
  --description "Payment services migrated from AWS 666666666666" \
  --wait-for-state ACTIVE

export COMPARTMENT_PAYMENTS=$(oci iam compartment list \
  --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample \
  --name "payments" \
  --query 'data[0].id' --raw-output)

echo "Core Compartment: $COMPARTMENT_CORE"
echo "Payments Compartment: $COMPARTMENT_PAYMENTS"
```

#### T+0h:10 — Create VCNs and Subnets

```bash
# Create main VCN (mirrors vpc-main 10.1.0.0/16)
oci network vcn create \
  --compartment-id $COMPARTMENT_CORE \
  --cidr-blocks '["10.1.0.0/16"]' \
  --display-name "vcn-ecommerce-main" \
  --dns-label "ecommain" \
  --wait-for-state AVAILABLE

export VCN_MAIN=$(oci network vcn list \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "vcn-ecommerce-main" \
  --query 'data[0].id' --raw-output)

# Create subnets matching AWS topology
# Compute subnet - Order API (10.1.1.0/24)
oci network subnet create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --cidr-block "10.1.1.0/24" \
  --display-name "subnet-compute-order-api" \
  --dns-label "orderapi" \
  --prohibit-public-ip-assignment true \
  --wait-for-state AVAILABLE

# Compute subnet - Fulfillment Worker (10.1.2.0/24)
oci network subnet create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --cidr-block "10.1.2.0/24" \
  --display-name "subnet-compute-fulfillment" \
  --dns-label "fulfill" \
  --prohibit-public-ip-assignment true \
  --wait-for-state AVAILABLE

# Compute subnet - Functions/Lambda (10.1.3.0/24)
oci network subnet create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --cidr-block "10.1.3.0/24" \
  --display-name "subnet-compute-functions" \
  --dns-label "functions" \
  --prohibit-public-ip-assignment true \
  --wait-for-state AVAILABLE

# Compute subnet - Reporting (10.1.4.0/24)
oci network subnet create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --cidr-block "10.1.4.0/24" \
  --display-name "subnet-compute-reporting" \
  --dns-label "reporting" \
  --prohibit-public-ip-assignment true \
  --wait-for-state AVAILABLE

# Database subnet (10.1.5.0/24)
oci network subnet create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --cidr-block "10.1.5.0/24" \
  --display-name "subnet-database" \
  --dns-label "database" \
  --prohibit-public-ip-assignment true \
  --wait-for-state AVAILABLE

# Cache subnet (10.1.6.0/24)
oci network subnet create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --cidr-block "10.1.6.0/24" \
  --display-name "subnet-cache" \
  --dns-label "cache" \
  --prohibit-public-ip-assignment true \
  --wait-for-state AVAILABLE

# Internal services subnet (10.1.7.0/24)
oci network subnet create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --cidr-block "10.1.7.0/24" \
  --display-name "subnet-internal-svc" \
  --dns-label "internalsvc" \
  --prohibit-public-ip-assignment true \
  --wait-for-state AVAILABLE

# Public subnet for Load Balancer (10.1.8.0/24)
oci network subnet create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --cidr-block "10.1.8.0/24" \
  --display-name "subnet-public-lb" \
  --dns-label "publiclb" \
  --prohibit-public-ip-assignment false \
  --wait-for-state AVAILABLE

# Create payments VCN (mirrors vpc-payments 10.2.0.0/16)
oci network vcn create \
  --compartment-id $COMPARTMENT_PAYMENTS \
  --cidr-blocks '["10.2.0.0/16"]' \
  --display-name "vcn-payments" \
  --dns-label "payments" \
  --wait-for-state AVAILABLE

export VCN_PAYMENTS=$(oci network vcn list \
  --compartment-id $COMPARTMENT_PAYMENTS \
  --display-name "vcn-payments" \
  --query 'data[0].id' --raw-output)

# Payments compute subnet (10.2.1.0/24)
oci network subnet create \
  --compartment-id $COMPARTMENT_PAYMENTS \
  --vcn-id $VCN_PAYMENTS \
  --cidr-block "10.2.1.0/24" \
  --display-name "subnet-payments-compute" \
  --dns-label "paycompute" \
  --prohibit-public-ip-assignment true \
  --wait-for-state AVAILABLE
```

#### T+0h:25 — Create Gateways and Route Tables

```bash
# Internet Gateway for main VCN (for public-facing load balancer)
oci network internet-gateway create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "igw-ecommerce-main" \
  --is-enabled true \
  --wait-for-state AVAILABLE

export IGW_MAIN=$(oci network internet-gateway list \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "igw-ecommerce-main" \
  --query 'data[0].id' --raw-output)

# NAT Gateway for private subnets outbound (SMTP, external APIs)
oci network nat-gateway create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "natgw-ecommerce-main" \
  --wait-for-state AVAILABLE

export NATGW_MAIN=$(oci network nat-gateway list \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "natgw-ecommerce-main" \
  --query 'data[0].id' --raw-output)

# Service Gateway for OCI services (Object Storage, etc.)
oci network service-gateway create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "sgw-ecommerce-main" \
  --services "[{\"serviceId\": \"$(oci network service list \
    --query 'data[?contains(name, `All IAD`)].id | [0]' --raw-output)\"}]" \
  --wait-for-state AVAILABLE

# NAT Gateway for payments VCN
oci network nat-gateway create \
  --compartment-id $COMPARTMENT_PAYMENTS \
  --vcn-id $VCN_PAYMENTS \
  --display-name "natgw-payments" \
  --wait-for-state AVAILABLE

# Update route table for public LB subnet → IGW
export RT_PUBLIC=$(oci network subnet get \
  --subnet-id $(oci network subnet list \
    --compartment-id $COMPARTMENT_CORE \
    --vcn-id $VCN_MAIN \
    --display-name "subnet-public-lb" \
    --query 'data[0].id' --raw-output) \
  --query 'data."route-table-id"' --raw-output)

oci network route-table update \
  --rt-id $RT_PUBLIC \
  --route-rules "[{
    \"cidrBlock\": \"0.0.0.0/0\",
    \"networkEntityId\": \"$IGW_MAIN\"
  }]" --force
```

#### T+0h:35 — Create Local Peering Gateway (Replaces VPC Peering)

```bash
# LPG on main VCN
oci network local-peering-gateway create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "lpg-main-to-payments" \
  --wait-for-state AVAILABLE

export LPG_MAIN=$(oci network local-peering-gateway list \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "lpg-main-to-payments" \
  --query 'data[0].id' --raw-output)

# LPG on payments VCN
oci network local-peering-gateway create \
  --compartment-id $COMPARTMENT_PAYMENTS \
  --vcn-id $VCN_PAYMENTS \
  --display-name "lpg-payments-to-main" \
  --wait-for-state AVAILABLE

export LPG_PAYMENTS=$(oci network local-peering-gateway list \
  --compartment-id $COMPARTMENT_PAYMENTS \
  --vcn-id $VCN_PAYMENTS \
  --display-name "lpg-payments-to-main" \
  --query 'data[0].id' --raw-output)

# Establish peering connection
oci network local-peering-gateway connect \
  --local-peering-gateway-id $LPG_MAIN \
  --peer-id $LPG_PAYMENTS

# Verify peering status
oci network local-peering-gateway get \
  --local-peering-gateway-id $LPG_MAIN \
  --query 'data."peering-status"' --raw-output
# Expected: PEERED
```

#### T+0h:45 — Create Network Security Groups

```bash
# NSG for compute instances
oci network nsg create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "nsg-compute" \
  --wait-for-state AVAILABLE

export NSG_COMPUTE=$(oci network nsg list \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "nsg-compute" \
  --query 'data[0].id' --raw-output)

# NSG for database
oci network nsg create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "nsg-database" \
  --wait-for-state AVAILABLE

export NSG_DB=$(oci network nsg list \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "nsg-database" \
  --query 'data[0].id' --raw-output)

# NSG for cache
oci network nsg create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "nsg-cache" \
  --wait-for-state AVAILABLE

export NSG_CACHE=$(oci network nsg list \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "nsg-cache" \
  --query 'data[0].id' --raw-output)

# NSG for load balancer
oci network nsg create \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "nsg-lb" \
  --wait-for-state AVAILABLE

export NSG_LB=$(oci network nsg list \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "nsg-lb" \
  --query 'data[0].id' --raw-output)

# NSG for payments
oci network nsg create \
  --compartment-id $COMPARTMENT_PAYMENTS \
  --vcn-id $VCN_PAYMENTS \
  --display-name "nsg-payments" \
  --wait-for-state AVAILABLE

export NSG_PAYMENTS=$(oci network nsg list \
  --compartment-id $COMPARTMENT_PAYMENTS \
  --vcn-id $VCN_PAYMENTS \
  --display-name "nsg-payments" \
  --query 'data[0].id' --raw-output)

# Add rules: Allow compute → database (PostgreSQL 5432)
oci network nsg rules add \
  --nsg-id $NSG_DB \
  --security-rules "[{
    \"direction\": \"INGRESS\",
    \"protocol\": \"6\",
    \"source\": \"$NSG_COMPUTE\",
    \"sourceType\": \"NETWORK_SECURITY_GROUP\",
    \"tcpOptions\": {\"destinationPortRange\": {\"min\": 5432, \"max\": 5432}},
    \"description\": \"Allow compute to PostgreSQL\"
  }]"

# Allow compute → cache (Redis 6379)
oci network nsg rules add \
  --nsg-id $NSG_CACHE \
  --security-rules "[{
    \"direction\": \"INGRESS\",
    \"protocol\": \"6\",
    \"source\": \"$NSG_COMPUTE\",
    \"sourceType\": \"NETWORK_SECURITY_GROUP\",
    \"tcpOptions\": {\"destinationPortRange\": {\"min\": 6379, \"max\": 6379}},
    \"description\": \"Allow compute to Redis\"
  }]"

# Allow payments → main VCN (HTTPS to order-api on 443) via LPG
oci network nsg rules add \
  --nsg-id $NSG_COMPUTE \
  --security-rules "[{
    \"direction\": \"INGRESS\",
    \"protocol\": \"6\",
    \"source\": \"10.2.0.0/16\",
    \"sourceType\": \"CIDR_BLOCK\",
    \"tcpOptions\": {\"destinationPortRange\": {\"min\": 443, \"max\": 443}},
    \"description\": \"Allow payments VCN to order-api HTTPS via LPG\"
  }]"

# Allow LB → compute (HTTPS 443)
oci network nsg rules add \
  --nsg-id $NSG_COMPUTE \
  --security-rules "[{
    \"direction\": \"INGRESS\",
    \"protocol\": \"6\",
    \"source\": \"$NSG_LB\",
    \"sourceType\": \"NETWORK_SECURITY_GROUP\",
    \"tcpOptions\": {\"destinationPortRange\": {\"min\": 443, \"max\": 443}},
    \"description\": \"Allow LB to order-api\"
  }]"

# Allow internet → LB (HTTPS 443)
oci network nsg rules add \
  --nsg-id $NSG_LB \
  --security-rules "[{
    \"direction\": \"INGRESS\",
    \"protocol\": \"6\",
    \"source\": \"0.0.0.0/0\",
    \"sourceType\": \"CIDR_BLOCK\",
    \"tcpOptions\": {\"destinationPortRange\": {\"min\": 443, \"max\": 443}},
    \"description\": \"Allow internet HTTPS to LB\"
  }]"

# Allow payment-svc → apigw-payments (within payments VCN)
oci network nsg rules add \
  --nsg-id $NSG_PAYMENTS \
  --security-rules "[{
    \"direction\": \"INGRESS\",
    \"protocol\": \"6\",
    \"source\": \"10.2.1.0/24\",
    \"sourceType\": \"CIDR_BLOCK\",
    \"tcpOptions\": {\"destinationPortRange\": {\"min\": 443, \"max\": 443}},
    \"description\": \"Allow payment-svc to API Gateway\"
  }]"
```

#### T+1h:00 — Create IAM Dynamic Groups and Policies

```bash
# Dynamic Group: Order API instances
oci iam dynamic-group create \
  --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample \
  --name "dg-order-api" \
  --description "Order API compute instances" \
  --matching-rule "Any {instance.compartment.id = '$COMPARTMENT_CORE', tag.role.value = 'order-api'}"

# Dynamic Group: Fulfillment Worker instances
oci iam dynamic-group create \
  --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample \
  --name "dg-fulfillment-worker" \
  --description "Fulfillment worker compute instances" \
  --matching-rule "Any {instance.compartment.id = '$COMPARTMENT_CORE', tag.role.value = 'fulfillment-worker'}"

# Dynamic Group: Reporting Service instances
oci iam dynamic-group create \
  --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample \
  --name "dg-reporting-svc" \
  --description "Reporting service compute instances" \
  --matching-rule "Any {instance.compartment.id = '$COMPARTMENT_CORE', tag.role.value = 'reporting-svc'}"

# Dynamic Group: OCI Functions (replaces notification-lambda-role)
oci iam dynamic-group create \
  --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample \
  --name "dg-notification-functions" \
  --description "Notification OCI Functions" \
  --matching-rule "All {resource.type = 'fnfunc', resource.compartment.id = '$COMPARTMENT_CORE'}"

# Dynamic Group: Payment Service instances
oci iam dynamic-group create \
  --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample \
  --name "dg-payment-svc" \
  --description "Payment service compute instances" \
  --matching-rule "Any {instance.compartment.id = '$COMPARTMENT_PAYMENTS', tag.role.value = 'payment-svc'}"

# Policy: Order API role (replaces iam-order-api-role)
oci iam policy create \
  --compartment-id $COMPARTMENT_CORE \
  --name "policy-order-api" \
  --description "Order API access to NoSQL, Queue, Object Storage, Vault" \
  --statements "[
    \"Allow dynamic-group dg-order-api to manage nosql-tables in compartment ecommerce-core\",
    \"Allow dynamic-group dg-order-api to use queues in compartment ecommerce-core\",
    \"Allow dynamic-group dg-order-api to manage objects in compartment ecommerce-core where target.bucket.name='bucket-order-invoices'\",
    \"Allow dynamic-group dg-order-api to read secret-bundles in compartment ecommerce-core where target.secret.name='secret-database-creds'\",
    \"Allow dynamic-group dg-order-api to use oci-cache-clusters in compartment ecommerce-core\"
  ]"

# Policy: Fulfillment Worker role (replaces iam-fulfillment-worker-role)
oci iam policy create \
  --compartment-id $COMPARTMENT_CORE \
  --name "policy-fulfillment-worker" \
  --description "Fulfillment worker access to Queue, NoSQL, Notifications" \
  --statements "[
    \"Allow dynamic-group dg-fulfillment-worker to use queues in compartment ecommerce-core\",
    \"Allow dynamic-group dg-fulfillment-worker to manage nosql-tables in compartment ecommerce-core\",
    \"Allow dynamic-group dg-fulfillment-worker to use ons-topics in compartment ecommerce-core\",
    \"Allow dynamic-group dg-fulfillment-worker to use oci-cache-clusters in compartment ecommerce-core\"
  ]"

# Policy: Reporting Service role (replaces iam-reporting-service-role)
oci iam policy create \
  --compartment-id $COMPARTMENT_CORE \
  --name "policy-reporting-svc" \
  --description "Reporting service access to NoSQL, Object Storage" \
  --statements "[
    \"Allow dynamic-group dg-reporting-svc to read nosql-tables in compartment ecommerce-core\",
    \"Allow dynamic-group dg-reporting-svc to read objects in compartment ecommerce-core where target.bucket.name='bucket-order-invoices'\"
  ]"

# Policy: Notification Functions (replaces iam-notification-lambda-role)
oci iam policy create \
  --compartment-id $COMPARTMENT_CORE \
  --name "policy-notification-functions" \
  --description "Notification functions access to Vault secrets" \
  --statements "[
    \"Allow dynamic-group dg-notification-functions to read secret-bundles in compartment ecommerce-core where target.secret.name='secret-email-smtp-creds'\",
    \"Allow dynamic-group dg-notification-functions to use fn-invocation in compartment ecommerce-core\"
  ]"

# Policy: Cross-compartment payment access (replaces cross-account IAM trust)
# This grants payment-svc instances in the payments compartment access to:
# 1. API Gateway in ecommerce-core (for routing payment API calls)
# 2. Network connectivity across LPG to order-api
oci iam policy create \
  --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample \
  --name "policy-payment-cross-compartment" \
  --description "Payment service cross-compartment access to ecommerce-core API Gateway and network" \
  --statements "[
    \"Allow dynamic-group dg-payment-svc to use api-gateway-family in compartment ecommerce-core\",
    \"Allow dynamic-group dg-payment-svc to read virtual-network-family in compartment ecommerce-core\",
    \"Allow dynamic-group dg-payment-svc to use fn-invocation in compartment ecommerce-core\"
  ]"
```

#### T+1h:15 — Create OCI Vault and Secrets

> **⚠ SECURITY NOTE**: Database credentials are generated fresh on OCI — NOT copied from AWS. SMTP credentials are transferred securely and will be rotated post-migration.

```bash
# Get existing Vault (provisioned at T-5d)
export VAULT_OCID=$(oci kms management vault list \
  --compartment-id $COMPARTMENT_CORE \
  --query 'data[?contains("display-name", `vault-ecommerce`)].id | [0]' --raw-output)

export VAULT_MGMT_ENDPOINT=$(oci kms management vault get \
  --vault-id $VAULT_OCID \
  --query 'data."management-endpoint"' --raw-output)

export VAULT_CRYPTO_ENDPOINT=$(oci kms management vault get \
  --vault-id $VAULT_OCID \
  --query 'data."crypto-endpoint"' --raw-output)

# Get master key OCID
export MASTER_KEY=$(oci kms management key list \
  --compartment-id $COMPARTMENT_CORE \
  --endpoint $VAULT_MGMT_ENDPOINT \
  --query 'data[0].id' --raw-output)

# Generate new database credentials for OCI PostgreSQL
# DO NOT copy AWS credentials — generate fresh ones
DB_NEW_PASS=$(openssl rand -base64 32)
DB_CREDS_JSON=$(printf '{"username":"pgadmin","password":"%s","host":"<PGSQL_IP_SET_IN_PHASE2>","port":5432,"dbname":"ecommerce"}' "$DB_NEW_PASS")

# Create database credentials secret in OCI Vault (with new credentials)
oci vault secret create-base64 \
  --compartment-id $COMPARTMENT_CORE \
  --vault-id $VAULT_OCID \
  --key-id $MASTER_KEY \
  --secret-name "secret-database-creds" \
  --description "PostgreSQL database credentials — NEW credentials generated for OCI PostgreSQL" \
  --secret-content-content "$(echo -n "$DB_CREDS_JSON" | base64)" \
  --secret-content-content-type BASE64 \
  --secret-content-name "secret-database-creds"

# Retrieve SMTP credentials from AWS securely (from authenticated, secure workstation)
# WARNING: Do not pipe to log files or echo to terminal
SMTP_CREDS=$(aws secretsmanager get-secret-value \
  --secret-id prod/email-smtp-creds \
  --query 'SecretString' --output text)

# Create SMTP credentials secret in OCI Vault
oci vault secret create-base64 \
  --compartment-id $COMPARTMENT_CORE \
  --vault-id $VAULT_OCID \
  --key-id $MASTER_KEY \
  --secret-name "secret-email-smtp-creds" \
  --description "SMTP credentials — to be rotated post-migration (see §2.6 Item 17-SEC-4)" \
  --secret-content-content "$(echo -n "$SMTP_CREDS" | base64)" \
  --secret-content-content-type BASE64 \
  --secret-content-name "secret-email-smtp-creds"

# Clear ALL sensitive variables immediately
unset DB_NEW_PASS DB_CREDS_JSON SMTP_CREDS

echo "Vault secrets created. Database credentials are NEW (not copied from AWS)."
echo "SMTP credentials will be rotated during hypercare (T+7d)."
```

#### T+1h:25 — Provision OCI Load Balancer (Pre-provisioned — No Active Backends)

> **Note**: The load balancer is provisioned in Phase 1 (Foundation) to avoid provisioning delays during the critical cutover window. TLS certificates are associated now. Backend sets and health checks are configured with no backends. During Phase 4, only backend membership updates and health check validation are needed.

```bash
export SUBNET_LB=$(oci network subnet list \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "subnet-public-lb" \
  --query 'data[0].id' --raw-output)

# Create public load balancer
oci lb load-balancer create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "lb-ecommerce-public" \
  --shape-name "flexible" \
  --shape-details '{"minimumBandwidthInMbps": 100, "maximumBandwidthInMbps": 400}' \
  --subnet-ids "[\"$SUBNET_LB\"]" \
  --nsg-ids "[\"$NSG_LB\"]" \
  --is-private false \
  --wait-for-state ACTIVE \
  --max-wait-seconds 600

export LB_OCID=$(oci lb load-balancer list \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "lb-ecommerce-public" \
  --query 'data[0].id' --raw-output)

export LB_PUBLIC_IP=$(oci lb load-balancer get \
  --load-balancer-id $LB_OCID \
  --query 'data."ip-addresses"[?."is-public"==`true`]."ip-address" | [0]' --raw-output)

echo "Load Balancer Public IP: $LB_PUBLIC_IP"

# Import TLS certificate (provisioned at T-4d, Item #23)
export CERT_OCID=$(oci certificates-management certificate list \
  --compartment-id $COMPARTMENT_CORE \
  --name "cert-ecommerce" \
  --query 'data.items[0].id' --raw-output)

# Create backend set with health check (no backends yet — will be attached in Phase 4)
oci lb backend-set create \
  --load-balancer-id $LB_OCID \
  --name "bs-order-api" \
  --policy "ROUND_ROBIN" \
  --health-checker-protocol "HTTPS" \
  --health-checker-port 443 \
  --health-checker-url-path "/health" \
  --health-checker-return-code 200 \
  --health-checker-interval-in-millis 10000 \
  --health-checker-timeout-in-millis 3000 \
  --wait-for-state SUCCEEDED

# Create HTTPS listener
oci lb listener create \
  --load-balancer-id $LB_OCID \
  --name "listener-https" \
  --default-backend-set-name "bs-order-api" \
  --port 443 \
  --protocol "HTTP" \
  --ssl-certificate-ids "[\"$CERT_OCID\"]" \
  --wait-for-state SUCCEEDED

echo "Load Balancer provisioned with TLS and backend set (no backends attached yet)"
echo "Backends will be attached in Phase 4 after compute instances are running"
```

#### T+1h:35 — Configure OCI Monitoring, Logging, and Alerting

> **Note**: Monitoring infrastructure must be active before traffic cutover. Operating blind during hypercare is unacceptable.

```bash
# Create Notifications topic for ops alerts
oci ons topic create \
  --compartment-id $COMPARTMENT_CORE \
  --name "topic-ops-alerts" \
  --description "Operational alerts for ecommerce platform — replaces CloudWatch Alarms + SNS"

export OPS_TOPIC_OCID=$(oci ons topic list \
  --compartment-id $COMPARTMENT_CORE \
  --name "topic-ops-alerts" \
  --query 'data[0]."topic-id"' --raw-output)

# Subscribe on-call email to ops alerts topic
oci ons subscription create \
  --compartment-id $COMPARTMENT_CORE \
  --topic-id $OPS_TOPIC_OCID \
  --protocol "EMAIL" \
  --endpoint "oncall-ecommerce@example.com"

# Subscribe PagerDuty/Slack webhook if applicable
# oci ons subscription create \
#   --compartment-id $COMPARTMENT_CORE \
#   --topic-id $OPS_TOPIC_OCID \
#   --protocol "HTTPS" \
#   --endpoint "https://events.pagerduty.com/integration/<KEY>/enqueue"

# Create Log Group for all ecommerce services
oci logging log-group create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "log-group-ecommerce" \
  --description "Centralized log group for ecommerce platform"

export LOG_GROUP_OCID=$(oci logging log-group list \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "log-group-ecommerce" \
  --query 'data[0].id' --raw-output)

# Create custom log for compute instances (agent-based)
oci logging log create \
  --log-group-id $LOG_GROUP_OCID \
  --display-name "log-compute-application" \
  --log-type "CUSTOM" \
  --is-enabled true

# Create service log for Load Balancer access logs
oci logging log create \
  --log-group-id $LOG_GROUP_OCID \
  --display-name "log-lb-access" \
  --log-type "SERVICE" \
  --is-enabled true \
  --configuration "{
    \"source\": {
      \"category\": \"access\",
      \"resource\": \"$LB_OCID\",
      \"service\": \"loadbalancer\",
      \"sourceType\": \"OCISERVICE\"
    },
    \"compartmentId\": \"$COMPARTMENT_CORE\"
  }"

# Create service log for OCI Functions invocations
oci logging log create \
  --log-group-id $LOG_GROUP_OCID \
  --display-name "log-functions-invoke" \
  --log-type "SERVICE" \
  --is-enabled true \
  --configuration "{
    \"source\": {
      \"category\": \"invoke\",
      \"resource\": \"<FN_APP_OCID_SET_IN_PHASE3>\",
      \"service\": \"functions\",
      \"sourceType\": \"OCISERVICE\"
    },
    \"compartmentId\": \"$COMPARTMENT_CORE\"
  }"

# Create monitoring alarms (replaces CloudWatch Alarms)

# Alarm: High CPU on compute instances (>85% for 5 min)
oci monitoring alarm create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "alarm-compute-high-cpu" \
  --namespace "oci_computeagent" \
  --query-text "CpuUtilization[5m]{resourceDisplayName =~ \"inst-*\"}.mean() > 85" \
  --severity "CRITICAL" \
  --destinations "[\"$OPS_TOPIC_OCID\"]" \
  --is-enabled true \
  --pending-duration "PT5M" \
  --body "High CPU utilization detected on ecommerce compute instance"

# Alarm: High memory on compute instances (>90% for 5 min)
oci monitoring alarm create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "alarm-compute-high-memory" \
  --namespace "oci_computeagent" \
  --query-text "MemoryUtilization[5m]{resourceDisplayName =~ \"inst-*\"}.mean() > 90" \
  --severity "CRITICAL" \
  --destinations "[\"$OPS_TOPIC_OCID\"]" \
  --is-enabled true \
  --pending-duration "PT5M" \
  --body "High memory utilization detected on ecommerce compute instance"

# Alarm: Database connections high (>80% of max)
oci monitoring alarm create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "alarm-pgsql-connections-high" \
  --namespace "oci_postgresql" \
  --query-text "ActiveConnections[5m].mean() > 80" \
  --severity "WARNING" \
  --destinations "[\"$OPS_TOPIC_OCID\"]" \
  --is-enabled true \
  --pending-duration "PT5M" \
  --body "PostgreSQL active connections approaching limit"

# Alarm: OCI Queue depth high (messages accumulating)
oci monitoring alarm create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "alarm-queue-depth-high" \
  --namespace "oci_queue" \
  --query-text "MessagesInQueue[5m].mean() > 1000" \
  --severity "WARNING" \
  --destinations "[\"$OPS_TOPIC_OCID\"]" \
  --is-enabled true \
  --pending-duration "PT10M" \
  --body "OCI Queue depth exceeding threshold — fulfillment worker may be falling behind"

# Alarm: Load Balancer 5xx error rate (>5% for 5 min)
oci monitoring alarm create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "alarm-lb-5xx-rate" \
  --namespace "oci_lbaas" \
  --query-text "HttpResponses5xx[5m]{resourceId = \"$LB_OCID\"}.sum() / HttpResponses[5m]{resourceId = \"$LB_OCID\"}.sum() * 100 > 5" \
  --severity "CRITICAL" \
  --destinations "[\"$OPS_TOPIC_OCID\"]" \
  --is-enabled true \
  --pending-duration "PT5M" \
  --body "Load Balancer 5xx error rate exceeding 5% — potential service degradation"

# Alarm: Load Balancer latency high (p95 > 2000ms for 5 min)
oci monitoring alarm create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "alarm-lb-latency-high" \
  --namespace "oci_lbaas" \
  --query-text "HttpResponseTime[5m]{resourceId = \"$LB_OCID\"}.percentile(0.95) > 2000" \
  --severity "WARNING" \
  --destinations "[\"$OPS_TOPIC_OCID\"]" \
  --is-enabled true \
  --pending-duration "PT5M" \
  --body "API latency p95 exceeding 2000ms — investigate Redis cache hit rate and PostgreSQL performance"

# Alarm: Load Balancer unhealthy backends
oci monitoring alarm create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "alarm-lb-unhealthy-backends" \
  --namespace "oci_lbaas" \
  --query-text "UnHealthyBackendCount[1m]{resourceId = \"$LB_OCID\"}.max() > 0" \
  --severity "CRITICAL" \
  --destinations "[\"$OPS_TOPIC_OCID\"]" \
  --is-enabled true \
  --pending-duration "PT2M" \
  --body "Load Balancer has unhealthy backends — order-api may be down"

# Alarm: OCI Functions invocation errors
oci monitoring alarm create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "alarm-functions-errors" \
  --namespace "oci_faas" \
  --query-text "FunctionInvocationErrors[5m].sum() > 10" \
  --severity "WARNING" \
  --destinations "[\"$OPS_TOPIC_OCID\"]" \
  --is-enabled true \
  --pending-duration "PT5M" \
  --body "OCI Functions invocation errors detected — email notifications may be failing"

echo "OCI Monitoring alarms, Logging, and Notifications configured"
echo "Ops alerts will route to oncall-ecommerce@example.com"
```

#### T+1h:50 — Phase 1 Validation

| # | Validation Step | Command | Expected Result |
|---|----------------|---------|-----------------|
| V1.1 | VCN main exists and is AVAILABLE | `oci network vcn get --vcn-id $VCN_MAIN --query 'data."lifecycle-state"'` | `"AVAILABLE"` |
| V1.2 | VCN payments exists and is AVAILABLE | `oci network vcn get --vcn-id $VCN_PAYMENTS --query 'data."lifecycle-state"'` | `"AVAILABLE"` |
| V1.3 | 8 subnets created in main VCN (including public LB subnet) | `oci network subnet list --compartment-id $COMPARTMENT_CORE --vcn-id $VCN_MAIN --query 'length(data)'` | `8` |
| V1.4 | LPG peering status | `oci network local-peering-gateway get --local-peering-gateway-id $LPG_MAIN --query 'data."peering-status"'` | `"PEERED"` |
| V1.5 | Dynamic groups created | `oci iam dynamic-group list --compartment-id ocid1.tenancy.oc1..aaaaaaaaexample --query 'length(data)'` | `≥ 5` |
| V1.6 | Policies created | `oci iam policy list --compartment-id $COMPARTMENT_CORE --query 'length(data)'` | `≥ 4` |
| V1.7 | Vault secrets accessible | `oci vault secret list --compartment-id $COMPARTMENT_CORE --query 'data[*]."secret-name"'` | Contains both secret names |
| V1.8 | Load Balancer ACTIVE with public IP | `oci lb load-balancer get --load-balancer-id $LB_OCID --query 'data."lifecycle-state"'` | `"ACTIVE"` |
| V1.9 | Load Balancer TLS certificate associated | `oci lb listener get --load-balancer-id $LB_OCID --listener-name listener-https` | SSL config present |
| V1.10 | Load Balancer backend set created (0 backends) | `oci lb backend list --load-balancer-id $LB_OCID --backend-set-name bs-order-api --query 'length(data)'` | `0` |
| V1.11 | OCI Monitoring alarms created and enabled | `oci monitoring alarm list --compartment-id $COMPARTMENT_CORE --query 'length(data)'` | `≥ 8` |
| V1.12 | Ops Notifications topic ACTIVE | `oci ons topic get --topic-id $OPS_TOPIC_OCID --query 'data."lifecycle-state"'` | `"ACTIVE"` |
| V1.13 | Log Group created | `oci logging log-group get --log-group-id $LOG_GROUP_OCID --query 'data."lifecycle-state"'` | `"ACTIVE"` |

**Phase 1 Rollback**: If VCN creation fails or LPG peering cannot be established → STOP. Delete all Phase 1 OCI resources (LB, alarms, logging, VCNs, NSGs in reverse order). Investigate OCI service limits or region availability. AWS environment remains unchanged — zero impact.

```bash
# Phase 1 rollback (if needed)
# Delete monitoring alarms
oci monitoring alarm list --compartment-id $COMPARTMENT_CORE --query 'data[*].id' --raw-output | \
  while read alarm_id; do oci monitoring alarm delete --alarm-id $alarm_id --force; done
# Delete load balancer
oci lb load-balancer delete --load-balancer-id $LB_OCID --force
# Delete LPGs
oci network local-peering-gateway delete --local-peering-gateway-id $LPG_MAIN --force
oci network local-peering-gateway delete --local-peering-gateway-id $LPG_PAYMENTS --force
# Delete subnets, VCNs, NSGs in reverse order
# AWS environment remains unchanged — zero impact
```

---

### Phase 2: Data Layer (T+2h → T+6h)

**Objective**: Provision and populate PostgreSQL, Redis, NoSQL tables, and Object Storage. This is the longest phase due to data transfer. AWS continues serving production traffic throughout.

> **Note**: `internal-https-svc` has been removed from Layer 2. It is deployed in Phase 4 (Layer 4 — Compute/Applications) alongside other compute instances, after its identity, dependencies, and layer placement were confirmed during pre-migration Item #1.

#### T+2h:00 — Provision OCI Database with PostgreSQL

```bash
# Get subnet OCID for database
export SUBNET_DB=$(oci network subnet list \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "subnet-database" \
  --query 'data[0].id' --raw-output)

# Create PostgreSQL database system
oci psql db-system create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "pgsql-ecommerce-orders" \
  --db-version "14" \
  --shape-id "PostgreSQL.VM.Standard.E4.Flex.4.64GB" \
  --instance-count 2 \
  --instance-memory-size-in-gbs 64 \
  --instance-ocpu-count 4 \
  --storage-details "{
    \"systemType\": \"OCI_OPTIMIZED_STORAGE\",
    \"isRegionallyDurable\": true,
    \"availabilityDomain\": \"$(oci iam availability-domain list --query 'data[0].name' --raw-output)\"
  }" \
  --network-details "{
    \"subnetId\": \"$SUBNET_DB\",
    \"nsgIds\": [\"$NSG_DB\"]
  }" \
  --credentials "{
    \"username\": \"pgadmin\",
    \"passwordDetails\": {
      \"passwordType\": \"PLAIN_TEXT\",
      \"password\": \"$(openssl rand -base64 32)\"
    }
  }" \
  --description "Ecommerce PostgreSQL - migrated from AWS RDS" \
  --wait-for-state ACTIVE \
  --max-wait-seconds 3600

export PGSQL_OCID=$(oci psql db-system list \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "pgsql-ecommerce-orders" \
  --query 'data.items[0].id' --raw-output)

# Get private IP of the PostgreSQL primary endpoint
export PGSQL_IP=$(oci psql db-system get \
  --db-system-id $PGSQL_OCID \
  --query 'data."network-details"."primary-db-endpoint-private-ip"' --raw-output)

echo "PostgreSQL Endpoint: $PGSQL_IP:5432"

# Update the Vault secret with the actual PostgreSQL IP
# (The secret was created with placeholder host in Phase 1)
# Retrieve current secret OCID
export DB_SECRET_OCID=$(oci vault secret list \
  --compartment-id $COMPARTMENT_CORE \
  --name "secret-database-creds" \
  --query 'data[0].id' --raw-output)

# Update secret with actual PostgreSQL endpoint
DB_NEW_PASS=$(oci vault secret get-secret-bundle \
  --secret-id $DB_SECRET_OCID \
  --stage CURRENT \
  --query 'data."secret-bundle-content".content' --raw-output | base64 -d | jq -r '.password')

DB_CREDS_UPDATED=$(printf '{"username":"pgadmin","password":"%s","host":"%s","port":5432,"dbname":"ecommerce"}' "$DB_NEW_PASS" "$PGSQL_IP")

oci vault secret update-secret-content \
  --secret-id $DB_SECRET_OCID \
  --content-content "$(echo -n "$DB_CREDS_UPDATED" | base64)" \
  --content-content-type BASE64

# Set the new password on OCI PostgreSQL
psql -h $PGSQL_IP -p 5432 -U pgadmin -c "ALTER USER pgadmin PASSWORD '$DB_NEW_PASS';"

# Clear sensitive variables
unset DB_NEW_PASS DB_CREDS_UPDATED
```

#### T+2h:05 — Start DMS Replication (AWS RDS → OCI PostgreSQL via VPN)

> **Note**: AWS DMS replication instance was pre-configured at T-4d. The VPN tunnel between AWS VPC and OCI VCN enables cross-cloud connectivity.

```bash
# On AWS side: Start DMS full-load + CDC replication
aws dms start-replication-task \
  --replication-task-arn arn:aws:dms:us-east-1:555555555555:task:XXXXXXXXXXXX \
  --start-replication-task-type start-replication \
  --region us-east-1

# Monitor replication progress
aws dms describe-replication-tasks \
  --filters Name=replication-task-arn,Values=arn:aws:dms:us-east-1:555555555555:task:XXXXXXXXXXXX \
  --query 'ReplicationTasks[0].{Status:Status,Progress:ReplicationTaskStats.FullLoadProgressPercent,CDCLatency:ReplicationTaskStats.CDCLatencySource}'
```

#### T+2h:15 — Provision OCI Cache with Redis

```bash
export SUBNET_CACHE=$(oci network subnet list \
  --compartment-id $COMPARTMENT_CORE \
  --vcn-id $VCN_MAIN \
  --display-name "subnet-cache" \
  --query 'data[0].id' --raw-output)

# Create OCI Cache with Redis cluster
oci redis cluster create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "redis-ecommerce-cache" \
  --node-count 3 \
  --node-memory-in-gbs 8 \
  --software-version "REDIS_7_0" \
  --subnet-id $SUBNET_CACHE \
  --nsg-ids "[\"$NSG_CACHE\"]" \
  --wait-for-state ACTIVE \
  --max-wait-seconds 1800

export REDIS_OCID=$(oci redis cluster list \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "redis-ecommerce-cache" \
  --query 'data.items[0].id' --raw-output)

export REDIS_ENDPOINT=$(oci redis cluster get \
  --cluster-id $REDIS_OCID \
  --query 'data."primary-endpoint"' --raw-output)

echo "Redis Endpoint: $REDIS_ENDPOINT:6379"
```

#### T+2h:30 — Create OCI NoSQL Tables

> **Note**: The DDL below must match the schema mapping completed in pre-migration Item #7. The examples below show the **base tables**. If GSIs were identified during discovery, create corresponding OCI NoSQL secondary indexes using `CREATE INDEX` statements. Capacity values below are placeholders — replace with values derived from CloudWatch metrics (Item #2) and schema mapping (Item #7).

```bash
# Create Orders table (mirrors DynamoDB Orders table)
# Schema mapping notes (from Item #7):
#   DynamoDB partition key: orderId (S) → OCI NoSQL PRIMARY KEY(orderId)
#   DynamoDB sort key: (none for this table)
#   GSI customerIndex (customerId, orderDate): → CREATE INDEX below
#   Consistency model: Map DynamoDB eventual consistent reads → OCI NoSQL EVENTUAL
#                       Map DynamoDB strongly consistent reads → OCI NoSQL ABSOLUTE
#   Capacity: Based on CloudWatch metrics from Item #2
#   TTL: If DynamoDB TTL attribute is used, add TTL(ttlAttribute) to DDL
oci nosql table create \
  --compartment-id $COMPARTMENT_CORE \
  --name "Orders" \
  --ddl-statement "CREATE TABLE Orders (
    orderId STRING,
    customerId STRING,
    orderStatus STRING,
    orderDate TIMESTAMP(3),
    totalAmount NUMBER,
    items JSON,
    shippingAddress JSON,
    paymentInfo JSON,
    createdAt TIMESTAMP(3),
    updatedAt TIMESTAMP(3),
    PRIMARY KEY(orderId)
  )" \
  --table-limits "{
    \"maxReadUnits\": 200,
    \"maxWriteUnits\": 100,
    \"maxStorageInGBs\": 50,
    \"capacityMode\": \"PROVISIONED\"
  }" \
  --wait-for-state ACTIVE \
  --max-wait-seconds 300

# Create secondary index matching DynamoDB GSI (customerIndex)
# Adjust based on actual GSIs discovered in Item #7
oci nosql query execute \
  --compartment-id $COMPARTMENT_CORE \
  --statement "CREATE INDEX idx_customer_orders ON Orders(customerId, orderDate)"

# Create Inventory table (mirrors DynamoDB Inventory table)
# Schema mapping notes (from Item #7):
#   DynamoDB partition key: productId (S) → OCI NoSQL PRIMARY KEY(SHARD(productId), warehouseId)
#   DynamoDB sort key: warehouseId (S) → composite primary key
#   Capacity: Based on CloudWatch metrics from Item #2
oci nosql table create \
  --compartment-id $COMPARTMENT_CORE \
  --name "Inventory" \
  --ddl-statement "CREATE TABLE Inventory (
    productId STRING,
    warehouseId STRING,
    stockCount INTEGER,
    reservedCount INTEGER,
    lastUpdated TIMESTAMP(3),
    PRIMARY KEY(SHARD(productId), warehouseId)
  )" \
  --table-limits "{
    \"maxReadUnits\": 100,
    \"maxWriteUnits\": 50,
    \"maxStorageInGBs\": 10,
    \"capacityMode\": \"PROVISIONED\"
  }" \
  --wait-for-state ACTIVE \
  --max-wait-seconds 300
```

#### T+2h:45 — Import DynamoDB Data into OCI NoSQL

> **⚠ TIMING NOTE**: This step's duration is highly dependent on table size. For the initial pre-cutover load, we import the T-4d export. A final delta import will occur during the cutover window (Phase 4). If tables exceed 10GB, consider using DynamoDB Streams-based CDC for incremental sync instead.

```bash
# The DynamoDB exports (created at T-4d) are in S3.
# First, download to migration workstation or use OCI Data Integration.

# Option A: Use the NoSQL Database migrator tool
# Download exports from S3
aws s3 sync s3://acme-dynamodb-exports/Orders/ ./dynamodb-exports/Orders/
aws s3 sync s3://acme-dynamodb-exports/Inventory/ ./dynamodb-exports/Inventory/

# Convert DynamoDB JSON to OCI NoSQL JSON format using migration script
# This script handles DynamoDB type descriptors (S, N, M, L, BOOL, NULL)
# → OCI NoSQL native types, as documented in Item #7 & #29
python3 scripts/dynamodb_to_nosql_converter.py \
  --input ./dynamodb-exports/Orders/ \
  --output ./nosql-imports/Orders/ \
  --table-name Orders \
  --key-mapping '{"orderId": {"dynamo_type": "S", "nosql_type": "STRING"}}' \
  --gsi-mapping '{"customerIndex": "idx_customer_orders"}'

python3 scripts/dynamodb_to_nosql_converter.py \
  --input ./dynamodb-exports/Inventory/ \
  --output ./nosql-imports/Inventory/ \
  --table-name Inventory \
  --key-mapping '{"productId": {"dynamo_type": "S", "nosql_type": "STRING"}, "warehouseId": {"dynamo_type": "S", "nosql_type": "STRING"}}'

# Import to OCI NoSQL using borneo SDK bulk import
python3 scripts/nosql_bulk_import.py \
  --compartment-id $COMPARTMENT_CORE \
  --table-name Orders \
  --input-dir ./nosql-imports/Orders/ \
  --batch-size 50 \
  --region us-ashburn-1

python3 scripts/nosql_bulk_import.py \
  --compartment-id $COMPARTMENT_CORE \
  --table-name Inventory \
  --input-dir ./nosql-imports/Inventory/ \
  --batch-size 50 \
  --region us-ashburn-1

# Validate row counts
NOSQL_ORDERS_COUNT=$(oci nosql query execute \
  --compartment-id $COMPARTMENT_CORE \
  --statement "SELECT count(*) AS cnt FROM Orders" \
  --query 'data.items[0].cnt' --raw-output)

echo "OCI NoSQL Orders row count: $NOSQL_ORDERS_COUNT"

# Compare with DynamoDB counts
DYNAMO_ORDERS_COUNT=$(aws dynamodb describe-table \
  --table-name Orders \
  --query 'Table.ItemCount' --output text)

echo "DynamoDB Orders row count: $DYNAMO_ORDERS_COUNT"
echo "Delta: $(($DYNAMO_ORDERS_COUNT - $NOSQL_ORDERS_COUNT)) rows (will be caught up in Phase 4 final delta)"
```

#### T+3h:00 — Create OCI Object Storage Bucket and Final Sync

```bash
# Get namespace
export OCI_NAMESPACE=$(oci os ns get --query 'data' --raw-output)

# Create bucket with configuration matching S3 (as documented in Item #8)
oci os bucket create \
  --compartment-id $COMPARTMENT_CORE \
  --namespace $OCI_NAMESPACE \
  --name "bucket-order-invoices" \
  --storage-tier "Standard" \
  --versioning "Enabled" \
  --object-events-enabled true

# Configure lifecycle rules matching S3 lifecycle policies (from Item #8)
# Example: Transition to Infrequent Access after 90 days, delete after 365 days
oci os object-lifecycle-policy put \
  --namespace $OCI_NAMESPACE \
  --bucket-name "bucket-order-invoices" \
  --items "[{
    \"name\": \"archive-old-invoices\",
    \"action\": \"INFREQUENT_ACCESS\",
    \"timeAmount\": 90,
    \"timeUnit\": \"DAYS\",
    \"isEnabled\": true,
    \"target\": \"objects\"
  }, {
    \"name\": \"delete-expired-invoices\",
    \"action\": \"DELETE\",
    \"timeAmount\": 365,
    \"timeUnit\": \"DAYS\",
    \"isEnabled\": true,
    \"target\": \"objects\"
  }]"

# Configure CORS if S3 bucket had CORS configuration (from Item #8)
# oci os bucket update --name "bucket-order-invoices" --namespace $OCI_NAMESPACE \
#   --cors-rules '<JSON matching S3 CORS>'

# Final delta sync using rclone (pre-sync started at T-5d)
rclone sync \
  aws-s3:acme-order-invoices \
  oci-os:bucket-order-invoices \
  --transfers 32 \
  --checkers 16 \
  --s3-provider AWS \
  --s3-region us-east-1 \
  --checksum \
  --verbose \
  --log-file /var/log/rclone-final-sync.log

# Validate object counts
AWS_OBJ_COUNT=$(aws s3api list-objects-v2 \
  --bucket acme-order-invoices \
  --query 'KeyCount' --output text)

OCI_OBJ_COUNT=$(oci os object list \
  --namespace $OCI_NAMESPACE \
  --bucket-name "bucket-order-invoices" \
  --query 'length(data)' --raw-output)

echo "AWS S3 objects: $AWS_OBJ_COUNT | OCI Object Storage objects: $OCI_OBJ_COUNT"

# Validate data integrity with checksums (spot check)
echo "Spot-checking 10 random objects for checksum integrity..."
aws s3api list-objects-v2 --bucket acme-order-invoices --max-items 10 --query 'Contents[*].Key' --output text | \
while read key; do
  AWS_ETAG=$(aws s3api head-object --bucket acme-order-invoices --key "$key" --query 'ETag' --output text)
  OCI_MD5=$(oci os object head --namespace $OCI_NAMESPACE --bucket-name "bucket-order-invoices" --name "$key" --query 'headers."content-md5"' --raw-output)
  echo "  $key: AWS=$AWS_ETAG OCI=$OCI_MD5"
done
```

#### T+4h:00 — Verify DMS Replication Status

```bash
# Check DMS full load completion
aws dms describe-replication-tasks \
  --filters Name=replication-task-arn,Values=arn:aws:dms:us-east-1:555555555555:task:XXXXXXXXXXXX \
  --query 'ReplicationTasks[0].{
    Status: Status,
    FullLoadProgress: ReplicationTaskStats.FullLoadProgressPercent,
    TablesLoaded: ReplicationTaskStats.TablesLoaded,
    TablesErrored: ReplicationTaskStats.TablesErrored,
    CDCLatencySource: ReplicationTaskStats.CDCLatencySource
  }'

# Expected: Status=running, FullLoadProgress=100, TablesErrored=0, CDCLatencySource < 5s
```

#### T+5h:30 — Phase 2 Validation

| # | Validation Step | Command | Expected Result |
|---|----------------|---------|-----------------|
| V2.1 | PostgreSQL ACTIVE and reachable | `oci psql db-system get --db-system-id $PGSQL_OCID --query 'data."lifecycle-state"'` | `"ACTIVE"` |
| V2.2 | DMS replication lag < 5 seconds | AWS DMS describe-replication-tasks | `CDCLatencySource < 5` |
| V2.3 | Redis cluster ACTIVE | `oci redis cluster get --cluster-id $REDIS_OCID --query 'data."lifecycle-state"'` | `"ACTIVE"` |
| V2.4 | NoSQL Orders table row count matches (pre-cutover baseline) | Compare AWS DynamoDB ItemCount vs OCI NoSQL count | Counts within expected delta (new writes during migration) |
| V2.5 | NoSQL Inventory table row count matches | Compare AWS DynamoDB ItemCount vs OCI NoSQL count | Counts within expected delta |
| V2.6 | Object Storage object count matches S3 | Compare counts from sync step | Counts match |
| V2.7 | Object Storage checksum spot check passed | Spot check from sync step | All checksums match |
| V2.8 | Vault secrets readable | `oci vault secret get-secret-bundle --secret-id <OCID> --stage CURRENT` | Returns secret content |
| V2.9 | PostgreSQL connectivity from compute subnet | `psql -h $PGSQL_IP -p 5432 -U pgadmin -c "SELECT 1;"` (from bastion in compute subnet) | Returns 1 |
| V2.10 | NoSQL secondary indexes created | `oci nosql index list --table-name-or-id Orders --compartment-id $COMPARTMENT_CORE` | Shows idx_customer_orders |

**Phase 2 Rollback**: If DMS replication fails with > 10 tables errored, or PostgreSQL provisioning fails → STOP. AWS environment unchanged. Delete OCI data resources. All data remains in AWS. DMS replication can be restarted or reconfigured for next attempt.

---

### Phase 3: Messaging & Event Infrastructure (T+6h → T+10h)

**Objective**: Provision OCI Queue (replaces SQS), OCI Notifications (replaces SNS), OCI Functions (replaces Lambda), and OCI API Gateway. All AWS services remain active and serving traffic.

> **Note**: Load Balancer was already provisioned in Phase 1. It is not provisioned here.

#### T+6h:00 — Create OCI Queue (replaces SQS)

```bash
# Create OCI Queue matching SQS configuration (from Item #6)
oci queue queue create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "queue-order-fulfillment" \
  --dead-letter-queue-delivery-count 5 \
  --visibility-in-seconds 30 \
  --timeout-in-seconds 300 \
  --retention-in-seconds 345600 \
  --wait-for-state ACTIVE \
  --max-wait-seconds 300

export QUEUE_OCID=$(oci queue queue list \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "queue-order-fulfillment" \
  --query 'data.items[0].id' --raw-output)

export QUEUE_ENDPOINT=$(oci queue queue get \
  --queue-id $QUEUE_OCID \
  --query 'data."messages-endpoint"' --raw-output)

echo "OCI Queue OCID: $QUEUE_OCID"
echo "OCI Queue Endpoint: $QUEUE_ENDPOINT"
```

#### T+6h:10 — Create OCI Notifications Topic (replaces SNS)

```bash
# Create Notifications topic
oci ons topic create \
  --compartment-id $COMPARTMENT_CORE \
  --name "topic-order-notifications" \
  --description "Order notification topic (migrated from AWS SNS sns-order-notifications)"

export TOPIC_OCID=$(oci ons topic list \
  --compartment-id $COMPARTMENT_CORE \
  --name "topic-order-notifications" \
  --query 'data[0]."topic-id"' --raw-output)

echo "OCI Notifications Topic OCID: $TOPIC_OCID"
```

#### T+6h:20 — Deploy OCI Functions (replaces Lambda)

> **Note**: The function code was replatformed during pre-migration (Item #14). Key changes from Lambda:
> - **Runtime**: OCI Functions uses container images (pushed to OCIR), not ZIP packages
> - **Entry point**: `handler(ctx, data)` instead of Lambda's `handler(event, context)`
> - **Trigger**: OCI Notifications subscription (not SNS) — event payload format differs
> - **Secrets**: OCI Vault SDK `get_secret_bundle()` instead of `boto3` Secrets Manager
> - **Authentication**: Instance principal (resource principal for Functions) — no IAM role assumption

```bash
# Create Functions application
oci fn application create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "app-order-notifications" \
  --subnet-ids "[\"$(oci network subnet list \
    --compartment-id $COMPARTMENT_CORE \
    --vcn-id $VCN_MAIN \
    --display-name "subnet-compute-functions" \
    --query 'data[0].id' --raw-output)\"]"

export FN_APP_OCID=$(oci fn application list \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "app-order-notifications" \
  --query 'data[0].id' --raw-output)

# Deploy function from OCIR (image pushed during pre-migration Item #14)
oci fn function create \
  --application-id $FN_APP_OCID \
  --display-name "fn-send-order-email" \
  --image "iad.ocir.io/$OCI_NAMESPACE/ecommerce/fn-send-order-email:latest" \
  --memory-in-mbs 256 \
  --timeout-in-seconds 120 \
  --config "{
    \"VAULT_SECRET_OCID_SMTP\": \"$(oci vault secret list \
      --compartment-id $COMPARTMENT_CORE \
      --name "secret-email-smtp-creds" \
      --query 'data[0].id' --raw-output)\",
    \"OCI_REGION\": \"us-ashburn-1\"
  }"

export FN_OCID=$(oci fn function list \
  --application-id $FN_APP_OCID \
  --display-name "fn-send-order-email" \
  --query 'data[0].id' --raw-output)

# Update Functions logging (service log created in Phase 1 with placeholder)
# Now that we have the FN_APP_OCID, update the log source
oci logging log update \
  --log-group-id $LOG_GROUP_OCID \
  --log-id $(oci logging log list \
    --log-group-id $LOG_GROUP_OCID \
    --display-name "log-functions-invoke" \
    --query 'data[0].id' --raw-output) \
  --configuration "{
    \"source\": {
      \"category\": \"invoke\",
      \"resource\": \"$FN_APP_OCID\",
      \"service\": \"functions\",
      \"sourceType\": \"OCISERVICE\"
    },
    \"compartmentId\": \"$COMPARTMENT_CORE\"
  }" --force

# Subscribe function to Notifications topic
oci ons subscription create \
  --compartment-id $COMPARTMENT_CORE \
  --topic-id $TOPIC_OCID \
  --protocol "ORACLE_FUNCTIONS" \
  --endpoint $FN_OCID

echo "Function subscribed to Notifications topic"

# Test function invocation
echo '{"orderId": "test-001", "email": "test@example.com", "type": "order_confirmation"}' | \
  oci fn function invoke \
    --function-id $FN_OCID \
    --body - \
    --query 'data'

echo "Function test invocation complete — verify no errors in logs"
```

#### T+6h:40 — Provision OCI API Gateway (replaces apigateway-payments)

> **Note**: The authentication configuration below must match the mapping completed in pre-migration Item #10. The example shows custom authorizer function-based auth. Adjust based on actual AWS API Gateway auth type discovered.

```bash
# Create API Gateway in the ecommerce-core compartment
# (The payments service calls through LPG to this gateway)
oci api-gateway gateway create \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "apigw-payments" \
  --endpoint-type "PRIVATE" \
  --subnet-id $(oci network subnet list \
    --compartment-id $COMPARTMENT_CORE \
    --vcn-id $VCN_MAIN \
    --display-name "subnet-compute-order-api" \
    --query 'data[0].id' --raw-output) \
  --nsg-ids "[\"$NSG_COMPUTE\"]" \
  --wait-for-state ACTIVE \
  --max-wait-seconds 600

export APIGW_OCID=$(oci api-gateway gateway list \
  --compartment-id $COMPARTMENT_CORE \
  --display-name "apigw-payments" \
  --query 'data.items[0].id' --raw-output)

# Create API deployment with /v1/payments/charge route
# Authentication: Custom authorizer function (mapped from AWS Lambda authorizer per Item #10)
# If AWS used IAM SigV4 auth, use OCI Identity-based auth instead
# If AWS used API keys, configure OCI API Gateway API key validation
oci api-gateway deployment create \
  --compartment-id $COMPARTMENT_CORE \
  --gateway-id $APIGW_OCID \
  --display-name "deployment-payments-v1" \
  --path-prefix "/v1" \
  --specification "{
    \"requestPolicies\": {
      \"authentication\": {
        \"type\": \"CUSTOM_AUTHENTICATION\",
        \"functionId\": \"<AUTHORIZER_FUNCTION_OCID>\",
        \"isAnonymousAccessAllowed\": false,
        \"tokenHeader\": \"Authorization\"
      },
      \"rateLimiting\": {
        \"rateInRequestsPerSecond\": 100,
        \"rateKey\": \"CLIENT_IP\"
      }
    },
    \"routes\": [{
      \"path\": \"/payments/charge\",
      \"methods\": [\"POST\"],
      \"backend\": {
        \"type\": \"HTTP_BACKEND\",
        \"url\": \"https://10.1.1.20:443/v1/payments/charge\",
        \"isSSLVerifyDisabled\": false
      }
    }]
  }" \
  --wait-for-state ACTIVE
```

#### T+7h:00 — Phase 3 Validation

| # | Validation Step | Command | Expected Result |
|---|----------------|---------|-----------------|
| V3.1 | OCI Queue ACTIVE | `oci queue queue get --queue-id $QUEUE_OCID --query 'data."lifecycle-state"'` | `"ACTIVE"` |
| V3.2 | Notifications topic ACTIVE | `oci ons topic get --topic-id $TOPIC_OCID --query 'data."lifecycle-state"'` | `"ACTIVE"` |
| V3.3 | Function deployed and invocable | `oci fn function get --function-id $FN_OCID --query 'data."lifecycle-state"'` | `"ACTIVE"` |
| V3.4 | Function → Vault secret access | Check function test invocation logs | No permission errors |
| V3.5 | Notifications → Function subscription active | `oci ons subscription list --compartment-id $COMPARTMENT_CORE --topic-id $TOPIC_OCID` | Subscription ACTIVE |
| V3.6 | OCI API Gateway ACTIVE | `oci api-gateway gateway get --gateway-id $APIGW_OCID --query 'data."lifecycle-state"'` | `"ACTIVE"` |
| V3.7 | DMS replication still healthy | AWS DMS describe-replication-tasks | CDC lag < 5s, no errors |

**Phase 3 Rollback**: If Queue or Notifications fail → delete and recreate. These are stateless resources. If Function fails → check OCIR image, redeploy. AWS remains serving traffic — no user impact.

---

### GO / NO-GO Decision Point (T+8h)

**⚠ POINT OF NO RETURN ASSESSMENT**

Before proceeding to Phase 4, the Migration Lead must convene the decision team.

| Decision Maker | Role |
|----------------|------|
| Migration Lead | Final go/no-go authority |
| Engineering VP | Business impact authority |
| DBA | Data integrity confirmation |
| App Lead | Application readiness confirmation |
| Security Lead | Security posture confirmation |

**GO Criteria** — ALL must be true:

| # | Criterion | Status |
|---|----------|--------|
| 1 | All Phase 1-3 validations passed | ☐ |
| 2 | DMS CDC replication lag consistently < 5 seconds for past 30 minutes | ☐ |
| 3 | All OCI resources ACTIVE/RUNNING (including pre-provisioned LB and monitoring) | ☐ |
| 4 | Refactored application artifacts available and tested | ☐ |
| 5 | VPN tunnel stable for past 6 hours | ☐ |
| 6 | On-call team assembled and available for next 12 hours | ☐ |
| 7 | Rollback procedure reviewed and understood by all team members (§6 Rollback Plan) | ☐ |
| 8 | Remaining maintenance window ≥ 24 hours | ☐ |
| 9 | OCI Monitoring alarms active and ops alert topic confirmed reachable | ☐ |

**If NO-GO**: Stop. AWS continues serving traffic. OCI resources remain provisioned (can be cleaned up later or used for next attempt). DMS continues replicating. Schedule next maintenance window.

**If GO**: Proceed to Phase 4. **Downtime begins.**

---

### Phase 4: Application Cutover (T+10h → T+14h) — ⚠ DOWNTIME BEGINS

**Objective**: Stop AWS producers, drain queues, perform final data sync, deploy OCI compute instances with refactored code, warm up Redis cache, and attach backends to pre-provisioned Load Balancer.

> **⚠ DOWNTIME STARTS NOW** — External users will experience service unavailability from this point until Phase 5 validation completes.

#### T+10h:00 — Enable Maintenance Page

```bash
# If using CloudFront or ALB: switch to maintenance page
# Option A: Update ALB default action to return maintenance page
aws elbv2 modify-rule \
  --rule-arn <DEFAULT_RULE_ARN> \
  --actions '[{"Type":"fixed-response","FixedResponseConfig":{"StatusCode":"503","ContentType":"text/html","MessageBody":"<html><body><h1>Scheduled Maintenance</h1><p>We are performing scheduled maintenance. Please try again in 2 hours.</p></body></html>"}}]'

echo "$(date -u) DOWNTIME STARTED — Maintenance page active"
```

#### T+10h:05 — Stop AWS Producers (Order API)

```bash
# Stop order-api from sending new messages to SQS and writing to DynamoDB
# Option A: Stop the EC2 instance
aws ec2 stop-instances --instance-ids i-XXXXXXXXXXXX  # ec2-order-api

# Option B: If graceful shutdown preferred, set application to drain mode:
# ssh ec2-user@ec2-order-api "sudo systemctl stop order-api"

echo "$(date -u) Order API stopped — no new orders being accepted"
```

#### T+10h:08 — Drain SQS Queue

```bash
# Allow fulfillment-worker to process all remaining SQS messages
echo "Waiting for SQS queue to drain..."

while true; do
  ATTRS=$(aws sqs get-queue-attributes \
    --queue-url https://sqs.us-east-1.amazonaws.com/555555555555/sqs-order-fulfillment \
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
    --query 'Attributes')
  
  VISIBLE=$(echo $ATTRS | jq -r '.ApproximateNumberOfMessages')
  IN_FLIGHT=$(echo $ATTRS | jq -r '.ApproximateNumberOfMessagesNotVisible')
  
  echo "  $(date -u) SQS: Visible=$VISIBLE, InFlight=$IN_FLIGHT"
  
  if [ "$VISIBLE" -eq "0" ] && [ "$IN_FLIGHT" -eq "0" ]; then
    echo "$(date -u) SQS queue fully drained"
    break
  fi
  
  sleep 10
done

# Now stop the fulfillment worker
aws ec2 stop-instances --instance-ids i-YYYYYYYYYYYY  # ec2-fulfillment-worker

echo "$(date -u) Fulfillment worker stopped"
```

#### T+10h:15 — Stop DMS and Promote OCI PostgreSQL

```bash
# Verify DMS CDC lag is minimal before stopping
DMS_LAG=$(aws dms describe-replication-tasks \
  --filters Name=replication-task-arn,Values=arn:aws:dms:us-east-1:555555555555:task:XXXXXXXXXXXX \
  --query 'ReplicationTasks[0].ReplicationTaskStats.CDCLatencySource' --output text)

echo "Final DMS CDC lag: ${DMS_LAG}s"

if [ "$DMS_LAG" -gt "10" ]; then
  echo "⚠ WARNING: DMS lag > 10s. Wait for lag to reduce before stopping."
  # Wait up to 5 minutes for lag to reduce
  sleep 300
fi

# Stop DMS replication task
aws dms stop-replication-task \
  --replication-task-