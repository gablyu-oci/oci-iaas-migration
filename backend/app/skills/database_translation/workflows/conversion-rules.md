# RDS → OCI Database Conversion Rules

Prose guidance that doesn't fit in the mapping table.

## Engine → target service

| RDS engine | OCI target | Why |
|---|---|---|
| `postgres` | `oci_database_db_system` (OLTP workload) | Managed Postgres under the DB Systems family |
| `aurora-postgresql` | `oci_database_autonomous_database` (ATP) | Aurora → Autonomous is the natural managed-to-managed path |
| `mysql` / `mariadb` | `oci_mysql_mysql_db_system` | MySQL HeatWave covers MySQL and MariaDB wire-compat |
| `aurora-mysql` | `oci_mysql_mysql_db_system` | |
| `oracle-ee` / `oracle-se2` | `oci_database_db_system` | `database_edition` distinguishes EE vs SE2 |
| `sqlserver` | `oci_core_instance` with self-hosted SQL Server | **No managed SQL Server on OCI.** Always flag as HIGH gap. |

The `rds_engine` subsection of `resources.yaml` carries this same table — do not diverge.

## DB instance class → shape sizing

- OCI DB Systems use shapes (`VM.Standard.E4.Flex` etc.), not instance classes.
- Don't invent shape mappings — reuse the `instance_shapes.yaml` table as if `db.*` were prefix-stripped (`db.r6g.xlarge` ≈ `r6g.xlarge` sizing).
- Set `cpu_core_count` (`oci_database_db_system`) or `shape_name` (`oci_mysql_mysql_db_system`) accordingly.

## Multi-AZ

- `multi_az: true` → `node_count = 2` on `oci_database_db_system`.
- OCI DB Systems in 2-node mode provide Data Guard (sync or async) across ADs.
- For MySQL, multi-AZ → `oci_mysql_mysql_db_system` with `is_highly_available = true`.

## Storage

- `allocated_storage` → `data_storage_size_in_gb`.
- `iops` (RDS provisioned IOPS) has no direct equivalent; OCI sizes IO with the compute shape — flag LOW.

## Credentials

- **`admin_password` MUST be a sensitive variable.** Emit `variable "db_admin_password" { sensitive = true }`. Never hardcode.
- `ssh_public_key` (required by `oci_database_db_system`) → `var.db_ssh_public_key`.

## Parameter groups / option groups

- AWS parameter groups → OCI does NOT have a parameter group equivalent. Common values (e.g., `max_connections`) are set on the DB System itself or via `alter system`. Flag as MEDIUM for each non-default parameter.

## Security

- RDS security groups → `oci_core_network_security_group` attached to the DB System's subnet.
- DB subnet group → regional subnet (OCI DB Systems use a regional subnet, not per-AZ like RDS).

## Backups

- Automated backups → `oci_database_db_system.db_home.database.db_backup_config`. Retention maps directly.
- Cross-region replicas → Data Guard across regions; requires a second DB System in the target region. Flag HIGH.

## Licensing

- For Oracle DB: `license_model = "BRING_YOUR_OWN_LICENSE"` or `"LICENSE_INCLUDED"`. Default to `BRING_YOUR_OWN_LICENSE` and flag MEDIUM for the customer to confirm.

## Gaps to always flag

- **SQL Server:** CRITICAL → use OCI Compute + self-managed.
- **RDS Proxy:** no direct equivalent. Flag HIGH.
- **Performance Insights:** no direct equivalent; OCI Ops Insights covers similar ground. Flag MEDIUM.
- **IAM DB auth:** OCI supports IAM DB auth for MySQL HeatWave but not (yet) for DB Systems Postgres. Check engine-specific support.
