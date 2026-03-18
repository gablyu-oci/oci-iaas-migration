# OCI Database Services — IAM Permissions Reference

## Overview

OCI offers several managed database services that map to AWS RDS, DynamoDB, ElastiCache, and Redshift.

## Database Service Mapping (AWS → OCI)

| AWS Service | OCI Equivalent | Resource Type |
|---|---|---|
| RDS (MySQL, PostgreSQL, Oracle) | MySQL HeatWave / Base Database | `database-family`, `db-systems` |
| RDS (Oracle) | Oracle Base Database Service | `db-systems`, `db-homes`, `databases` |
| Aurora | MySQL HeatWave | `mysql-db-systems` |
| DynamoDB | NoSQL Database | `nosql-tables` |
| ElastiCache (Redis) | OCI Cache (Redis-compatible) | `redis-clusters` |
| Redshift | Autonomous Data Warehouse | `autonomous-databases` |
| DMS | Database Migration Service | `migrations` |

## Base Database Service (db-systems)

### Resource Types
- `db-systems` — DB System (VM, BM, or Exadata)
- `db-nodes` — Compute nodes in a DB system
- `db-homes` — Oracle Database homes
- `databases` — Individual databases within a home
- `backups` — Database backups
- `db-system-shapes` — Available shapes (read-only)
- `db-versions` — Available DB versions (read-only)

### Verbs
| Verb | Allowed Operations |
|---|---|
| `inspect` | List DB systems, nodes, homes, databases |
| `read` | Get details, read backups |
| `use` | Connect to databases |
| `manage` | Create, update, delete DB systems, create backups, patch |

### Example Policies
```
Allow group DBAdmins to manage db-systems in compartment Production
Allow group DBAdmins to manage databases in compartment Production
Allow group DBReadOnly to read db-systems in compartment Production
Allow group AppServers to use databases in compartment Production
```

## MySQL HeatWave (mysql-db-systems)

### Resource Types
- `mysql-db-systems` — MySQL DB System
- `mysql-backups` — MySQL backups
- `mysql-configurations` — Configuration profiles
- `mysql-shapes` — Available shapes (read-only)
- `mysql-versions` — Available versions (read-only)

### Example Policies
```
Allow group MySQLAdmins to manage mysql-db-systems in compartment Production
Allow group MySQLAdmins to manage mysql-backups in compartment Production
Allow group AppServers to use mysql-db-systems in compartment Production
```

## NoSQL Database (nosql-tables)

Maps to AWS DynamoDB.

### Resource Types
- `nosql-tables` — NoSQL tables
- `nosql-rows` — Individual rows within a table

### Verbs
| Verb | Allowed Operations |
|---|---|
| `inspect` | List tables |
| `read` | Get table metadata, read rows |
| `use` | Read and write rows |
| `manage` | Create, update, delete tables |

### Example Policies
```
Allow group NoSQLAdmins to manage nosql-tables in compartment Production
Allow group AppServers to use nosql-tables in compartment Production
Allow group ReadOnlyApps to read nosql-tables in compartment Production
```

## Autonomous Database (autonomous-databases)

Maps to AWS RDS Aurora Serverless or Redshift.

### Resource Types
- `autonomous-databases` — Autonomous Database instances (ATP, ADW)
- `autonomous-backups` — Automated and manual backups
- `autonomous-container-databases` — Container DBs (Exadata only)
- `autonomous-database-family` — Group resource covering all autonomous DB resources

### Verbs
| Verb | Allowed Operations |
|---|---|
| `inspect` | List autonomous databases |
| `read` | Get details, view backups |
| `use` | Scale, start/stop, download wallet/credentials |
| `manage` | Create, update, delete, restore from backup |

### Example Policies
```
Allow group ADBAdmins to manage autonomous-databases in compartment Production
Allow group ADBReadOnly to read autonomous-database-family in compartment Production
Allow group AppServers to use autonomous-databases in compartment Production
```

## AWS → OCI IAM Action Mapping

| AWS Action | OCI Equivalent Policy |
|---|---|
| `rds:CreateDBInstance` | `manage db-systems` |
| `rds:DeleteDBInstance` | `manage db-systems` |
| `rds:DescribeDBInstances` | `read db-systems` |
| `rds:CreateDBSnapshot` | `manage backups` |
| `rds:RestoreDBInstanceFromDBSnapshot` | `manage db-systems` |
| `dynamodb:CreateTable` | `manage nosql-tables` |
| `dynamodb:DeleteTable` | `manage nosql-tables` |
| `dynamodb:DescribeTable` | `read nosql-tables` |
| `dynamodb:PutItem` | `use nosql-tables` |
| `dynamodb:GetItem` | `use nosql-tables` |
| `dynamodb:Query` | `use nosql-tables` |
| `dynamodb:Scan` | `use nosql-tables` |
| `rds:DescribeDBClusters` | `read db-systems` |
| `redshift:CreateCluster` | `manage autonomous-databases` |

## Conditions Available for Database Policies

- `target.db-system.id` — Specific DB system OCID
- `target.database.id` — Specific database OCID
- `target.nosql-table.id` — Specific NoSQL table OCID
- `target.autonomous-database.id` — Specific Autonomous DB OCID
- `request.permission` — Fine-grained permission check
