# AWS → OCI Data Migration — Rulebook

Prose guidance for the `data_migration_planning` skill. Unlike the
infra-translation skills, this one doesn't produce Terraform — it produces
a runbook. The rules below are about tool selection and cutover sequencing,
not resource mapping.

## Tool selection matrix

| Source | Primary tool | Fallback | Notes |
|---|---|---|---|
| **Oracle DB (RDS or self-hosted)** | Zero Downtime Migration (ZDM) | OCI DMS | ZDM is Oracle-to-Oracle only; use DMS for cross-engine |
| **MySQL / MariaDB (RDS)** | OCI Database Migration Service | MySQL Shell dump/load | DMS supports MySQL-to-MySQL HeatWave; Shell is simpler for small DBs |
| **MySQL / MariaDB (on EC2)** | MySQL Shell `util.dumpInstance` + `util.loadDump` | `mysqldump` + `mysql` import | Shell is 10-20x faster |
| **Aurora PostgreSQL** | OCI DMS | `pg_dump` + `pg_restore` | DMS handles schema conversion |
| **PostgreSQL (RDS / EC2)** | OCI DMS or logical replication | `pg_dump` + `pg_restore` | Logical replication for near-zero downtime |
| **SQL Server** | Backup/restore to self-hosted on OCI Compute | Azure Data Migration Assistant | No managed SQL Server on OCI |
| **DynamoDB** | Export to S3 → ETL → OCI NoSQL | Manual scripting | Schema differences require validation |
| **S3** | `rclone sync` or OCI CLI `bulk-upload` | `oci os object put` | rclone for cross-cloud verification |
| **Redis / ElastiCache** | RDB dump + restore | Cold migration | No warm replication path |

## Cutover pattern (generic)

Every migration runbook MUST include these phases:

1. **Pre-cutover (T-7 to T-1 days)**
   - Schema audit + capacity planning on OCI target
   - Network connectivity test (VPN / IPsec / FastConnect) — NEVER skip this
   - Test dry-run with a trimmed dataset (last 24h of changes)
   - Rollback plan dry-run
   - Stakeholder sign-off on downtime window

2. **Cutover (T-0)**
   - Application freeze on source (stop writes at the application, not the DB)
   - Final incremental sync (`pg_dump` diff / binlog replay / DMS CDC drain)
   - Validation: row counts + checksum on a sample of N large tables
   - DNS / connection string swap
   - Smoke tests on target
   - Declare success or abort to rollback

3. **Post-cutover (T+1 hour to T+7 days)**
   - Monitor replication lag (if any) — should be zero after cutover
   - Backup verification on the new target
   - Retention of source for configurable cool-off period before decommission

## Downtime budget

- `ZDM / logical replication`: near-zero (< 1 min)
- `DMS online mode`: minutes (< 10)
- `dump + load`: proportional to data size. Rough rule: 100 GB/hour on a 10 Gbit link for MySQL/Postgres.
- **Always estimate conservatively** — customers remember the worst run, not the average.

## Risk classification

- `low`: read-only workload, < 10 GB, well-known engine
- `medium`: read/write workload, < 500 GB, standard engine
- `high`: > 500 GB OR customer extensions OR SQL Server OR cross-region

Always include a specific rollback trigger per phase.

## Common traps

- **Connection-string changes are the #1 cause of post-cutover incidents.** Always list every application that references the DB and plan the config push.
- **IAM DB auth:** if source uses IAM DB auth, target OCI may not — validate early.
- **Extensions / plugins:** `pg_stat_statements`, `pgcrypto`, etc. Not all ship on OCI. Flag HIGH during pre-cutover.
- **Triggers / stored procs referencing cloud-specific functions** (AWS Lambda invocation from Aurora, etc.) — flag as CRITICAL; requires app-side rewrite.
