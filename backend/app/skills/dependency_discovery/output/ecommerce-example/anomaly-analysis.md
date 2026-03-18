# Anomaly Analysis Report: ecommerce-example

## 1. Executive Summary

This analysis covers a multi-account e-commerce architecture spanning two AWS accounts — **555555555555 (ecommerce-core)** and **666666666666 (payments)** — with cross-account trust relationships and cross-VPC network connectivity. The architecture supports a classic order processing pipeline with synchronous and asynchronous components.

**Overall Risk Assessment: HIGH**

The dependency graph, constructed from only **14 CloudTrail events** and VPC Flow Logs, reveals a system with significant observability blind spots, a critical stateful bottleneck (RDS PostgreSQL), an unidentified ghost service, and a cross-account trust chain that introduces both migration coordination risk and security exposure. The actual dependency surface is conservatively estimated to be **10–50x larger** than what is currently visible, meaning the true blast radius of any single component failure or misconfiguration is substantially underestimated.

**Key Findings:**
- **1 critical** cross-account trust chain between payments and ecommerce-core
- **1 unidentified ghost dependency** (HTTPS service at 10.1.7.80) with zero attribution
- **3 single points of failure** (RDS PostgreSQL, ElastiCache Redis, DynamoDB Orders table)
- **Multiple self-referencing edges** suggesting collapsed graph resolution — the actual service-to-service topology is obscured
- **Severe observability gap**: data-plane operations for DynamoDB, ElastiCache, and RDS are not represented in CloudTrail

---

## 2. Unexpected Coupling Patterns

### 2.1 Self-Referencing Service Edges (Graph Collapse Anomaly)

The most prominent anomaly in this graph is the prevalence of **self-referencing edges** where both source and target resolve to the same service namespace:

| Edge | Type | Observation |
|------|------|-------------|
| `555555555555:dynamodb → 555555555555:dynamodb` | data_write (PutItem ×4) | Multiple distinct callers collapsed into one node |
| `555555555555:sqs → 555555555555:sqs` | async (SendMessage ×2) | Producer and consumer collapsed |
| `555555555555:s3 → 555555555555:s3` | data_write (PutObject ×2) | Writer identity obscured |
| `555555555555:sns → 555555555555:sns` | async (Publish ×1) | Publisher identity obscured |
| `555555555555:lambda → 555555555555:lambda` | sync_call (Invoke ×1) | Lambda-to-Lambda chaining hidden |
| `555555555555:secretsmanager → 555555555555:secretsmanager` | data_read (GetSecretValue ×2) | Secret consumers unknown |
| `666666666666:execute-api → 666666666666:execute-api` | sync_call (Invoke ×1) | API Gateway self-invocation or proxy |

**Analysis:** These are not true self-dependencies. They are artifacts of graph construction where the **calling principal** (e.g., a Lambda function, an EC2 instance role) was collapsed into the target service namespace. This means the actual caller–callee relationships are **invisible in the current graph**. For example, `dynamodb → dynamodb (PutItem ×4)` almost certainly represents 3–4 distinct services (order-api, fulfillment-worker, etc.) writing to the Orders and Inventory tables — but we cannot distinguish them.

**Risk:** Without resolving these collapsed edges, migration sequencing cannot determine which services must be moved together, and blast radius analysis is impossible.

### 2.2 Cross-Account Network Hop Anomaly

The edge `666666666666:10.2.1.10 → 666666666666:https@10.1.1.20` reveals a cross-VPC or cross-account network connection where the **target IP (10.1.1.20)** is in the `10.1.x.x` address space belonging to account **555555555555 (ecommerce-core)**, yet the edge is attributed entirely to account **666666666666 (payments)**.

This indicates one of:
- **VPC Peering or Transit Gateway** connecting the two accounts, with the payments account's service directly hitting the ecommerce-core API server
- **A misattributed flow log** where the ENI belongs to account 666666666666 but the target IP is in account 555555555555's CIDR block

**Concern:** The IP 10.1.1.20 is the **same host** that connects to RDS PostgreSQL, ElastiCache Redis, and the ghost HTTPS service at 10.1.7.80 — making it a central hub. The payments service in account 666666666666 is reaching directly into the core application tier, bypassing any API Gateway or load balancer abstraction. This is **tight network coupling across account boundaries**.

### 2.3 API Gateway Self-Invocation

The `execute-api → execute-api` synchronous call in account 666666666666 suggests either:
- An API Gateway endpoint invoking another API Gateway stage/resource (unusual and likely a proxy pattern)
- An API Gateway route that fans out to itself via a Lambda integration that calls back into the same API

Either pattern creates a **recursive invocation risk** and increases latency unpredictably.

---

## 3. Tight Coupling Hotspots

### 3.1 Host 10.1.1.20 — The Order API Hub

This single IP address is the most connected node in the entire graph:

```
10.1.1.20 → postgres/rds@10.1.5.100    (5432/TCP, 2 connections, 210 KB)
10.1.1.20 → redis/elasticache@10.1.6.50 (6379/TCP, 1 connection, 195 KB)
10.1.1.20 → https@10.1.7.80             (443/TCP, 1 connection, 24 KB)
666666666666:10.2.1.10 → https@10.1.1.20 (443/TCP, inbound from payments)
```

**Fan-out degree: 3 outbound + 1 inbound = 4 direct dependencies**

This host exhibits the classic **"God Service" anti-pattern** — a single compute instance that holds synchronous connections to every stateful backend. If this instance fails, the entire order processing pipeline halts. The synchronous critical path is:

```
[Payments API (666)] → [Order API @ 10.1.1.20] → [RDS + Redis + Ghost Service]
                                                 ↓
                                              [DynamoDB]
                                                 ↓
                                              [SQS Queue]
```

**Coupling Score: CRITICAL** — Any latency spike in RDS, Redis, or the ghost service at 10.1.7.80 will cascade upstream through the order API to the payments account.

### 3.2 RDS PostgreSQL @ 10.1.5.100 — Shared Stateful Bottleneck

Three distinct sources connect to this single database:

| Source | Bytes Transferred | Connections |
|--------|------------------|-------------|
| 10.1.1.20 (order-api) | 210 KB | 2 |
| 10.1.4.50 (unknown service) | 146.5 KB | 1 |
| 10.1.2.30 (unknown service) | 58.6 KB | 1 |

**Total: 3 services, 4 connections, ~415 KB observed**

This is a **shared mutable state bottleneck**. All three services presumably read and write to overlapping tables, creating:
- Schema coupling (all must agree on table structures)
- Transaction contention (row-level locks under concurrent writes)
- Migration atomicity requirements (all three must cut over simultaneously)

### 3.3 DynamoDB Orders Table — Dual-Purpose System of Record

The DynamoDB `PutItem` frequency of 4 against the "Orders" table, combined with the discovery notes stating it is accessed by **all services**, makes this the second major tight coupling point. DynamoDB's Global Tables could ease migration, but the dual-role nature (Orders + Inventory) means **transactional consistency across both tables** must be maintained during cutover.

---

## 4. Ghost Dependencies (Estimated Missing)

### 4.1 Confirmed Ghost: HTTPS Service @ 10.1.7.80

| Attribute | Value |
|-----------|-------|
| **Source** | 10.1.1.20 (order-api) |
| **Target** | 10.1.7.80:443 |
| **Bytes** | 24.4 KB |
| **CloudTrail Attribution** | **NONE** |
| **Probable Identity** | Internal ALB, microservice, or external proxy |

**Risk:** This service has **zero observability**. It could be:
- An internal payment tokenization service
- A third-party webhook relay or fraud detection proxy
- A legacy service not yet onboarded to CloudTrail/X-Ray
- An ALB fronting another service tier

**If this is a stateful service that participates in the order transaction**, its absence from the dependency graph means the migration plan has a **blind spot in the critical path**. The relatively small data transfer (24 KB) suggests either a lightweight API call (auth token validation, configuration fetch) or a health check — but this cannot be confirmed without investigation.

### 4.2 Estimated Missing: DynamoDB Read Operations

CloudTrail captured 4× `PutItem` but **zero** `GetItem`, `Query`, or `Scan` operations. In an e-commerce system, read:write ratios are typically **10:1 to 100:1**. The actual DynamoDB dependency weight is estimated at:

| Operation | Observed | Estimated Actual |
|-----------|----------|-----------------|
| PutItem | 4 | 40–200 (writes are periodic) |
| GetItem/Query | 0 | 400–2,000+ |
| UpdateItem | 0 | 20–100 (inventory decrements) |

### 4.3 Estimated Missing: ElastiCache Redis Data-Plane

Redis connections are visible in VPC Flow Logs (195 KB + 39 KB from two hosts) but **zero Redis commands** appear in CloudTrail because ElastiCache data-plane operations are not logged there. Estimated missing operations:

- `GET`/`SET` for session caching or order state: **hundreds to thousands per minute**
- `INCR`/`DECR` for inventory counters: **tens per minute**
- `PUBLISH`/`SUBSCRIBE` for real-time notifications: **unknown**

### 4.4 Estimated Missing: RDS SQL Queries

415 KB of PostgreSQL traffic across 3 services and 4 connections is visible, but individual SQL operations are invisible. Estimated:

- `SELECT` queries (order lookup, inventory check): **hundreds per minute**
- `INSERT`/`UPDATE` (order creation, status updates): **tens per minute**
- Transaction coordination (`BEGIN`/`COMMIT`): **equal to write frequency**

### 4.5 Estimated Missing: SQS ReceiveMessage / DeleteMessage

Only `SendMessage ×2` is observed. The consumer side (`ReceiveMessage`, `DeleteMessage`) is entirely absent, suggesting the fulfillment-worker's polling activity was not captured. Estimated missing:

| Operation | Observed | Estimated |
|-----------|----------|-----------|
| SendMessage | 2 | 20–100 |
| ReceiveMessage | 0 | 200–1,000 (long-polling) |
| DeleteMessage | 0 | 20–100 |

### 4.6 Estimated Missing: SNS Subscriptions and Deliveries

Only `Publish ×1` to `order-notifications` is visible. Missing:
- SNS → SQS subscription delivery
- SNS → Lambda subscription delivery  
- SNS → Email/SMS delivery (if configured)
- Subscription confirmation events

### 4.7 Probable Missing: CloudWatch, X-Ray, KMS

No edges exist for:
- **CloudWatch** (Logs, Metrics, Alarms) — every Lambda and EC2 instance should be emitting logs
- **KMS** — if DynamoDB encryption at rest or S3 SSE-KMS is enabled, `Decrypt`/`GenerateDataKey` calls should appear
- **X-Ray** — if tracing is enabled, trace segment submission dependencies are missing
- **IAM/STS within account 555555555555** — Lambda execution role assumptions are not visible

---

## 5. Single Points of Failure

### 5.1 RDS PostgreSQL @ 10.1.5.100 — **CRITICAL SPOF**

| Attribute | Assessment |
|-----------|-----------|
| **Consumers** | 3 services across 3 subnets |
| **Redundancy Visible** | None (single IP observed) |
| **Failure Impact** | Complete order processing halt |
| **Recovery** | Depends on Multi-AZ config (not confirmed in graph) |

If this is a single-AZ RDS instance, a failure takes down all three consuming services simultaneously. Even with Multi-AZ, failover takes 60–120 seconds during which all synchronous queries will timeout.

### 5.2 ElastiCache Redis @ 10.1.6.50 — **HIGH SPOF**

| Attribute | Assessment |
|-----------|-----------|
| **Consumers** | 2 services (10.1.1.20, 10.1.2.30) |
| **Redundancy Visible** | None (single node IP) |
| **Failure Impact** | Cache miss storm → RDS overload → cascade failure |

A single Redis node failure will cause a **thundering herd** against RDS as all cached reads fall through. If Redis is used for session state (likely in e-commerce), active user sessions will be lost.

### 5.3 Host 10.1.1.20 (Order API) — **HIGH SPOF**

This single IP suggests either a single EC2 instance or a single ENI. No evidence of an Auto Scaling Group, ALB, or multiple IPs serving this role. If this host terminates:
- Payments account loses its only path into ecommerce-core
- All downstream writes to DynamoDB, SQS, S3 stop
- The ghost service at 10.1.7.80 loses its only known caller

### 5.4 Cross-Account Trust: payment-gateway-access Role — **HIGH SPOF**

The single IAM role `arn:aws:iam::555555555555:role/payment-gateway-access` is the **only observed bridge** between accounts 666666666666 and 555555555555. If this role is deleted, modified, or its trust policy is tightened, the entire payment integration breaks.

---

## 6. Data Consistency Risks

### 6.1 Dual-Write to DynamoDB + RDS PostgreSQL

The order-api (10.1.1.20) writes to **both** DynamoDB (PutItem to Orders table) and RDS PostgreSQL simultaneously. This creates a **dual-write consistency problem**:

```
Order API
  ├── PutItem → DynamoDB:Orders     (success)
  └── INSERT  → RDS:PostgreSQL      (failure?)
```

If the RDS write fails after the DynamoDB write succeeds (or vice versa), the system enters an **inconsistent state** where the order exists in one store but not the other. There is no evidence of:
- A distributed transaction coordinator (Saga pattern)
- An outbox pattern with CDC
- An idempotency mechanism for retry reconciliation

**Estimated Probability of Inconsistency During Migration:** HIGH — during database cutover, the window where one store is writable and the other is read-only will guarantee split-brain writes.

### 6.2 DynamoDB Orders + Inventory Atomicity

The discovery notes indicate both the Orders and Inventory tables are critical. In a typical e-commerce flow:

```
1. Check Inventory (GetItem → Inventory table)
2. Decrement Stock (UpdateItem → Inventory table)  
3. Create Order   (PutItem → Orders table)
```

If steps 2 and 3 are not in a DynamoDB transaction (`TransactWriteItems`), a failure between them creates either:
- **Overselling**: order created but inventory not decremented
- **Phantom stock reduction**: inventory decremented but order not created

No `TransactWriteItems` events are observed (though the sample is small).

### 6.3 SQS Message Ordering and At-Least-Once Delivery

The order-fulfillment-queue processes order completion events. SQS Standard queues provide **at-least-once delivery** with **best-effort ordering**. If the fulfillment pipeline is not idempotent:
- Duplicate message delivery could trigger double-fulfillment
- Out-of-order delivery could process cancellations before confirmations

No evidence of FIFO queue usage (the queue URL does not end in `.fifo`).

### 6.4 Redis Cache Invalidation

With two services (10.1.1.20 and 10.1.2.30) sharing the same Redis instance, cache invalidation becomes critical. If service A writes to RDS but service B reads stale data from Redis:
- Inventory counts may be stale (selling items already out of stock)
- Order status may lag behind actual state

No evidence of cache invalidation strategy (pub/sub, TTL policies, write-through caching).

---

## 7. Security Concerns

### 7.1 Cross-Account Role Trust — Overly Broad?

```
666666666666:sts → AssumeRole → arn:aws:iam::555555555555:role/payment-gateway-access
```

**Concerns:**
- The role name `payment-gateway-access` suggests it grants access to payment-related resources, but the graph shows the payments account (666666666666) can reach **into** the ecommerce-core account. The scope of permissions attached to this role is unknown.
- If the trust policy uses `"Principal": {"AWS": "arn:aws:iam::666666666666:root"}`, then **any principal** in account 666666666666 can assume this role — not just the payment service.
- No evidence of `ExternalId` condition, which is a best practice for cross-account trust.
- No evidence of session duration limits or MFA requirements.
- If account 666666666666 is compromised, the attacker gains access to whatever `payment-gateway-access` permits in the core account.

**Recommendation:** Audit the trust policy and attached permissions immediately. Apply least-privilege with specific principal ARNs, condition keys, and session policies.

### 7.2 Secrets Manager Access Without Rotation Evidence

```
secretsmanager → GetSecretValue → prod/database-creds (×2)
```

Two reads of database credentials were observed. Concerns:
- **No `RotateSecret` events observed** — if secrets are not being rotated, compromised credentials have an indefinite window of exposure
- The secret name `prod/database-creds` suggests it contains RDS PostgreSQL credentials for the production database, making it an extremely high-value target
- No evidence of which principals are authorized to read this secret (Lambda execution roles? EC2 instance profiles? All of them?)

### 7.3 Unidentified HTTPS Endpoint @ 10.1.7.80

A service with **no CloudTrail attribution** receiving HTTPS traffic from the order-api is a security blind spot:
- If this is an **external proxy** (e.g., forwarding to a third-party payment processor), sensitive order data may be leaving the VPC without logging
- If this is a **compromised host** or **shadow IT service**, it represents an unmonitored exfiltration path
- 24 KB of data over HTTPS is enough to transmit customer PII, payment tokens, or order details

### 7.4 Direct IP-Based Network Connectivity (No Service Mesh / Zero Trust)

All network dependencies are based on **direct IP-to-IP communication** without evidence of:
- Service mesh (e.g., AWS App Mesh, Istio) providing mTLS
- VPC endpoints for AWS service calls (DynamoDB, SQS, SNS, S3, Secrets Manager)
- Network ACLs or security groups restricting lateral movement

The payments account reaching the order-api via direct IP (10.2.1.10 → 10.1.1.20:443) suggests traffic traverses a VPC peering connection or Transit Gateway without an API Gateway or ALB intermediary, meaning:
- No WAF protection on the cross-account API call
- No request throttling or rate limiting
- No TLS termination with certificate validation at an ALB

### 7.5 S3 Invoice Bucket — Data Exfiltration Risk

```
s3 → PutObject → s3://acme-order-invoices/2026/02/10/invoice-12345.pdf
```

Invoices contain customer PII (names, addresses, order details). Concerns:
- No evidence of **S3 bucket policy** restricting access
- No evidence of **server-side encryption** (SSE-S3, SSE-KMS)
- No evidence of **S3 access logging** or **CloudTrail data events** for reads
- Predictable key structure (`/YYYY/MM/DD/invoice-NNNNN.pdf`) enables enumeration attacks if the bucket is misconfigured

### 7.6 Timestamp Anomaly in VPC Flow Logs

The VPC Flow Log timestamps (`1707553060`, `1707552960`, etc.) decode to **February 10, 2024**, while the CloudTrail events are dated **February 10, 2026**. This is either:
- A **data collection error** (flow logs from a different time period mixed with current CloudTrail data)
- **Stale flow log data** being analyzed alongside current events, which means the network topology may have changed significantly

This discrepancy undermines confidence in the network dependency graph.

---

## 8. Recommendations

### 8.1 Immediate Actions (Before Migration Planning)

| Priority | Action | Rationale |
|----------|--------|-----------|
| **P0** | **Identify the ghost service at 10.1.7.80** | Run `aws ec2 describe-network-interfaces` with IP filter; check ALB/NLB target groups; inspect reverse DNS. Cannot plan migration with an unknown dependency in the critical path. |
| **P0** | **Audit IAM role `payment-gateway-access`** | Review trust policy, attached policies, and CloudTrail `AssumeRole` event details. Restrict principal to specific role ARN in 666666666666. Add `ExternalId` condition. |
| **P0** | **Resolve VPC Flow Log timestamp discrepancy** | Determine if network topology data is current. Re-collect flow logs from the same time window as CloudTrail events. |
| **P1** | **Enable CloudTrail Data Events** for S3 and DynamoDB in account 555555555555 | Current graph misses ~95%+ of actual operations. Enable for at least 7 days to establish true dependency weights. |
| **P1** | **Enable Slow Query Log and Audit Log** for RDS PostgreSQL | Identify which services execute which SQL queries, and establish read/write ratios per service. |
| **P1** | **Resolve collapsed graph edges** | Re-process CloudTrail events to extract `userIdentity.arn` for each API call, producing caller → service edges instead of service → service self-loops. |

### 8.2 Architecture Improvements (Pre-Migration)

| Action | Addresses |
|--------|-----------|
| **Implement the Outbox Pattern** for DynamoDB + RDS dual-writes | Data consistency risk §6.1. Write to one store, use CDC/Streams to replicate to the other. |
| **Use DynamoDB Transactions** (`TransactWriteItems`) for Orders + Inventory | Data consistency risk §6.2. Ensure atomic stock decrement + order creation. |
| **Replace SQS Standard with FIFO queue** for order-fulfillment-queue | Data consistency risk §6.3. Guarantees exactly-once processing and ordering. |
| **Deploy ALB/NLB** in front of the order-api at 10.1.1.20 | SPOF §5.3. Add health checks, auto-scaling, and a stable DNS endpoint. |
| **Deploy ElastiCache Redis in cluster mode** with at least one replica | SPOF §5.2. Automatic failover prevents cache-miss storms. |
| **Confirm RDS Multi-AZ** is enabled; if not, enable immediately | SPOF §5.1. |
| **Add VPC endpoints** for DynamoDB, SQS, SNS, S3, Secrets Manager, STS | Security §7.4. Keeps AWS API traffic within the VPC. |
| **Enable Secrets Manager automatic rotation** for `prod/database-creds` | Security §7.2. Set 30-day rotation with Lambda rotator. |

### 8.3 Migration Sequencing Recommendation

Based on the dependency analysis, the migration **must** follow this order:

```
Phase 0: Observability (enable data events, resolve ghost dep, resolve graph)
         ↓
Phase 1: Stateless async tier (SNS topics, SQS queues, S3 buckets)
         — These can be dual-written during transition
         ↓
Phase 2: DynamoDB tables (use Global Tables for zero-downtime replication)
         — Enable Streams for cross-region sync
         ↓
Phase 3: RDS PostgreSQL (use DMS with CDC for continuous replication)
         — Blue-green cutover with <60s write freeze
         ↓
Phase 4: ElastiCache Redis (warm new cluster, switch DNS)
         — Accept cache cold-start; pre-warm if possible
         ↓
Phase 5: Compute tier (Lambda functions, EC2 instances)
         — Deploy to new environment, shift traffic via weighted DNS/ALB
         ↓
Phase 6: Cross-account trust (update IAM role trust policies)
         — This MUST be the last step; update 666666666666 to point to new account/role
         ↓
Phase 7: Decommission (drain old SQS queues, verify zero traffic, delete)
```

**Critical Constraint:** Phases 2–4 (DynamoDB + RDS + Redis) must have overlapping replication windows. The order-api cannot function if any one of these three is unavailable. Plan for a **coordinated cutover window** of ≤5 minutes where all three data stores switch simultaneously.

### 8.4 Monitoring During and After Migration

| Metric | Threshold | Action |
|--------|-----------|--------|
| DynamoDB `ThrottledRequests` | >0 | Increase provisioned capacity or switch to on-demand |
| RDS `DatabaseConnections` | >80% of max | Verify all old-path connections are terminated |
| SQS `ApproximateNumberOfMessagesNotVisible` | Increasing | Consumer in new environment not processing |
| Cross-account `AssumeRole` failures | >0 | Trust policy not updated |
| ElastiCache `CacheMisses` | >90% for >5min | Cache pre-warming failed |
| VPC Flow Logs to 10.1.7.80 | Any traffic from new environment | Ghost service dependency not migrated |

---

*Report generated from dependency graph analysis of ecommerce-example. Confidence level: **MODERATE** due to limited CloudTrail sample size (14 events) and unresolved timestamp discrepancy in VPC Flow Logs. Recommend re-analysis after enabling data events and resolving ghost dependencies.*