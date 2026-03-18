# AWS Action to OCI Verb Mappings

## Overview
This document provides detailed mappings from AWS IAM actions to OCI IAM verbs for major services.

## OCI Verb Hierarchy (Least → Most Permissive)

| OCI Verb | Access Level | Typical AWS Actions |
|----------|--------------|---------------------|
| `inspect` | List metadata only | Describe*, List*, Get* (metadata only) |
| `read` | View + download content | Describe*, List*, Get*, Download* |
| `use` | Limited modifications | Start*, Stop*, Reboot*, limited Create/Update |
| `manage` | Full control | All actions (Create*, Update*, Delete*, *) |

## Service-by-Service Mappings

### EC2 (Compute Instances)

#### OCI Resource Types
- `instances` - Compute instances
- `instance-images` - Custom images
- `instance-configurations` - Launch templates
- `instance-pools` - Auto-scaling groups
- `compute-clusters` - Cluster placements

#### Action Mappings

| AWS Action | OCI Verb | OCI Resource Type | Notes |
|------------|----------|-------------------|-------|
| `ec2:DescribeInstances` | `inspect` | `instances` | Metadata only |
| `ec2:DescribeInstanceTypes` | `inspect` | `instances` | Public info |
| `ec2:GetConsoleOutput` | `read` | `instances` | Requires read access |
| `ec2:GetConsoleScreenshot` | `read` | `instances` | Console access |
| `ec2:StartInstances` | `use` | `instances` | Instance lifecycle |
| `ec2:StopInstances` | `use` | `instances` | Instance lifecycle |
| `ec2:RebootInstances` | `use` | `instances` | Instance lifecycle |
| `ec2:TerminateInstances` | `manage` | `instances` | Destructive - requires manage |
| `ec2:RunInstances` | `manage` | `instances` | Create requires manage |
| `ec2:ModifyInstanceAttribute` | `manage` | `instances` | Most updates require manage |
| `ec2:CreateImage` | `manage` | `instance-images` | Image creation |
| `ec2:DeregisterImage` | `manage` | `instance-images` | Image deletion |
| `ec2:DescribeImages` | `inspect` | `instance-images` | List images |

**Example Policy Translation:**

AWS:
```json
{
  "Effect": "Allow",
  "Action": ["ec2:StartInstances", "ec2:StopInstances"],
  "Resource": "*"
}
```

OCI:
```
Allow group ops-team to use instances in compartment production
```

### S3 (Object Storage)

#### OCI Resource Types
- `buckets` - Object Storage buckets
- `objects` - Objects within buckets

#### Action Mappings

| AWS Action | OCI Verb | OCI Resource Type | Notes |
|------------|----------|-------------------|-------|
| `s3:ListBucket` | `inspect` | `buckets` | List bucket contents |
| `s3:ListAllMyBuckets` | `inspect` | `buckets` | List all buckets |
| `s3:GetBucketLocation` | `inspect` | `buckets` | Metadata |
| `s3:GetObject` | `read` | `objects` | Download objects |
| `s3:GetObjectVersion` | `read` | `objects` | Version access |
| `s3:PutObject` | `manage` | `objects` | Upload requires manage |
| `s3:DeleteObject` | `manage` | `objects` | Delete requires manage |
| `s3:CreateBucket` | `manage` | `buckets` | Bucket creation |
| `s3:DeleteBucket` | `manage` | `buckets` | Bucket deletion |
| `s3:PutBucketPolicy` | `manage` | `buckets` | Policy changes |
| `s3:GetBucketPolicy` | `read` | `buckets` | Read bucket policy |

**Important Note:** OCI requires separate statements for buckets vs objects.

**Example Policy Translation:**

AWS:
```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::my-bucket",
    "arn:aws:s3:::my-bucket/*"
  ]
}
```

OCI:
```
Allow group data-readers to inspect buckets in compartment storage where target.bucket.name = 'my-bucket'
Allow group data-readers to read objects in compartment storage where target.bucket.name = 'my-bucket'
```

### RDS (Database)

#### OCI Resource Types
- `db-systems` - Database instances
- `db-homes` - Database homes (Oracle concept)
- `databases` - Individual databases
- `db-backups` - Database backups
- `database-family` - All database resources

#### Action Mappings

| AWS Action | OCI Verb | OCI Resource Type | Notes |
|------------|----------|-------------------|-------|
| `rds:DescribeDBInstances` | `inspect` | `db-systems` | List databases |
| `rds:DescribeDBSnapshots` | `inspect` | `db-backups` | List backups |
| `rds:CreateDBSnapshot` | `manage` | `db-backups` | Create backup |
| `rds:RestoreDBInstanceFromSnapshot` | `manage` | `db-systems` | Restore requires manage |
| `rds:StartDBInstance` | `use` | `db-systems` | Start/stop |
| `rds:StopDBInstance` | `use` | `db-systems` | Start/stop |
| `rds:RebootDBInstance` | `use` | `db-systems` | Reboot |
| `rds:CreateDBInstance` | `manage` | `db-systems` | Create database |
| `rds:DeleteDBInstance` | `manage` | `db-systems` | Delete database |
| `rds:ModifyDBInstance` | `manage` | `db-systems` | Most modifications |

**Example Policy Translation:**

AWS:
```json
{
  "Effect": "Allow",
  "Action": "rds:*",
  "Resource": "*"
}
```

OCI:
```
Allow group db-admins to manage database-family in compartment production
```

### Lambda (Functions)

#### OCI Resource Types
- `fn-function` - Individual functions
- `fn-app` - Function applications
- `fn-invocation` - Function invocations

#### Action Mappings

| AWS Action | OCI Verb | OCI Resource Type | Notes |
|------------|----------|-------------------|-------|
| `lambda:ListFunctions` | `inspect` | `fn-function` | List functions |
| `lambda:GetFunction` | `read` | `fn-function` | View function details |
| `lambda:InvokeFunction` | `use` | `fn-function` | Execute function |
| `lambda:CreateFunction` | `manage` | `fn-function` | Create function |
| `lambda:UpdateFunctionCode` | `manage` | `fn-function` | Update code |
| `lambda:UpdateFunctionConfiguration` | `manage` | `fn-function` | Update config |
| `lambda:DeleteFunction` | `manage` | `fn-function` | Delete function |
| `lambda:PublishVersion` | `manage` | `fn-function` | Versioning |

### DynamoDB (NoSQL)

#### OCI Resource Types
- `nosql-tables` - NoSQL tables
- `nosql-rows` - Table rows
- `nosql-indexes` - Table indexes
- `nosql-family` - All NoSQL resources

#### Action Mappings

| AWS Action | OCI Verb | OCI Resource Type | Notes |
|------------|----------|-------------------|-------|
| `dynamodb:DescribeTable` | `inspect` | `nosql-tables` | Table metadata |
| `dynamodb:ListTables` | `inspect` | `nosql-tables` | List tables |
| `dynamodb:GetItem` | `read` | `nosql-rows` | Read data |
| `dynamodb:Query` | `read` | `nosql-rows` | Query data |
| `dynamodb:Scan` | `read` | `nosql-rows` | Scan table |
| `dynamodb:PutItem` | `use` | `nosql-rows` | Write data |
| `dynamodb:UpdateItem` | `use` | `nosql-rows` | Update data |
| `dynamodb:DeleteItem` | `use` | `nosql-rows` | Delete rows |
| `dynamodb:CreateTable` | `manage` | `nosql-tables` | Create table |
| `dynamodb:DeleteTable` | `manage` | `nosql-tables` | Delete table |
| `dynamodb:UpdateTable` | `manage` | `nosql-tables` | Modify table structure |

### IAM (Identity)

#### OCI Resource Types
- `users` - IAM users
- `groups` - IAM groups
- `policies` - IAM policies
- `dynamic-groups` - Dynamic groups (role-like)
- `identity-providers` - Federated identity providers

#### Action Mappings

| AWS Action | OCI Verb | OCI Resource Type | Notes |
|------------|----------|-------------------|-------|
| `iam:ListUsers` | `inspect` | `users` | List users |
| `iam:GetUser` | `read` | `users` | Get user details |
| `iam:CreateUser` | `manage` | `users` | Create user |
| `iam:DeleteUser` | `manage` | `users` | Delete user |
| `iam:UpdateUser` | `use` | `users` | Update description only |
| `iam:ListGroups` | `inspect` | `groups` | List groups |
| `iam:AddUserToGroup` | `use` | `users` + `groups` | Add to group (requires both) |
| `iam:RemoveUserFromGroup` | `use` | `users` + `groups` | Remove from group |
| `iam:CreateGroup` | `manage` | `groups` | Create group |
| `iam:DeleteGroup` | `manage` | `groups` | Delete group |
| `iam:GetPolicy` | `inspect` | `policies` | View policy (includes content!) |
| `iam:CreatePolicy` | `manage` | `policies` | Create policy |
| `iam:DeletePolicy` | `manage` | `policies` | Delete policy |

**Important:** In OCI, `inspect policies` returns the full policy content, not just metadata.

### VPC (Networking)

#### OCI Resource Types
- `vcns` - Virtual Cloud Networks
- `subnets` - Subnets
- `security-lists` - Security groups equivalent
- `route-tables` - Route tables
- `internet-gateways` - Internet gateways
- `nat-gateways` - NAT gateways
- `virtual-network-family` - All networking resources

#### Action Mappings

| AWS Action | OCI Verb | OCI Resource Type | Notes |
|------------|----------|-------------------|-------|
| `ec2:DescribeVpcs` | `inspect` | `vcns` | Includes security rules! |
| `ec2:DescribeSubnets` | `inspect` | `subnets` | List subnets |
| `ec2:DescribeSecurityGroups` | `inspect` | `security-lists` | Includes rules |
| `ec2:CreateVpc` | `manage` | `vcns` | Create VCN |
| `ec2:DeleteVpc` | `manage` | `vcns` | Delete VCN |
| `ec2:CreateSubnet` | `manage` | `subnets` | Requires VCN manage |
| `ec2:AuthorizeSecurityGroupIngress` | `manage` | `security-lists` | Update rules |
| `ec2:AuthorizeSecurityGroupEgress` | `manage` | `security-lists` | Update rules |
| `ec2:CreateInternetGateway` | `manage` | `internet-gateways` | Create IGW |
| `ec2:AttachInternetGateway` | `manage` | `vcns` + `internet-gateways` | Attachment |

**Important:** OCI `inspect` on networking returns full configuration including security rules!

### KMS (Key Management)

#### OCI Resource Types
- `vaults` - Key vaults
- `keys` - Encryption keys
- `key-delegates` - Key delegation

#### Action Mappings

| AWS Action | OCI Verb | OCI Resource Type | Notes |
|------------|----------|-------------------|-------|
| `kms:ListKeys` | `inspect` | `keys` | List keys |
| `kms:DescribeKey` | `read` | `keys` | Key metadata |
| `kms:Encrypt` | `use` | `keys` | Encrypt data |
| `kms:Decrypt` | `use` | `keys` | Decrypt data |
| `kms:CreateKey` | `manage` | `keys` | Create key |
| `kms:ScheduleKeyDeletion` | `manage` | `keys` | Delete key |
| `kms:CreateAlias` | `manage` | `keys` | Manage aliases |

## Special Cases & Translation Patterns

### Wildcard Actions (`service:*`)

AWS policies often use wildcards for all actions. Map based on intent:

**AWS:**
```json
{"Action": "ec2:*"}
```

**OCI:**
```
Allow group admins to manage instances in compartment production
```

Or use family resource type for broader access:
```
Allow group admins to manage compute-family in compartment production
```

### PassRole Pattern

AWS `iam:PassRole` allows passing roles to services. In OCI, use **dynamic groups** instead.

**AWS:**
```json
{
  "Effect": "Allow",
  "Action": "iam:PassRole",
  "Resource": "arn:aws:iam::*:role/LambdaExecutionRole"
}
```

**OCI Equivalent:**
Create a dynamic group matching the service:
```
# Define dynamic group
ALL {resource.type = 'fnfunc', resource.compartment.id = 'ocid1.compartment...'}

# Grant permissions to the dynamic group
Allow dynamic-group lambda-functions to use nosql-tables in compartment production
```

### Multi-Resource Operations

Some AWS operations require multiple resource types. Create separate OCI statements.

**AWS (Launch EC2 instance):**
```json
{
  "Effect": "Allow",
  "Action": "ec2:RunInstances",
  "Resource": "*"
}
```

**OCI (requires instance + VCN access):**
```
Allow group dev-team to manage instances in compartment dev
Allow group dev-team to use vcns in compartment dev
Allow group dev-team to use subnets in compartment dev
```

## Action Determination Algorithm

To determine OCI verb from AWS actions:

1. **Check action pattern:**
   - Only `Describe*`, `List*`, `Get*` (metadata) → `inspect`
   - `Get*` + data download → `read`
   - Start/Stop/Reboot + limited updates → `use`
   - Create/Delete/full updates → `manage`

2. **Check action granularity:**
   - Need fine-grained control → Use specific verbs
   - Need broad access → Use `manage`

3. **Consider security:**
   - Principle of least privilege → Start with lower verb
   - Administrative tasks → Use `manage`

4. **Multiple actions in policy:**
   - If ANY action requires `manage` → Use `manage`
   - If mixed read/write → Use `use` or split into multiple statements

## Common Translation Errors to Avoid

1. **Using `inspect` when data access is needed**
   - `s3:GetObject` needs `read objects`, not `inspect`

2. **Forgetting separate bucket/object statements**
   - S3 requires separate OCI statements for buckets vs objects

3. **Over-permissioning with `manage`**
   - Start/Stop doesn't need `manage`, use `use`

4. **Missing resource dependencies**
   - Creating subnets requires VCN access too

5. **Assuming `inspect` is harmless**
   - In OCI networking, `inspect` returns security rules!
   - `inspect policies` returns full policy content!

## Next Steps

- See `condition-mappings.md` for condition translation
- See `translation-rules.md` for complete workflow
- See `output/manual-examples/` for translation examples
