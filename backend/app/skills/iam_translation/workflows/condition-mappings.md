# AWS Condition to OCI Condition Translation

## Overview
AWS IAM conditions are significantly more expressive than OCI IAM conditions. This document maps AWS condition operators and context keys to OCI equivalents where possible, and documents workarounds for unsupported conditions.

## Condition Operator Mappings

### String Operators

| AWS Operator | OCI Equivalent | Notes |
|--------------|----------------|-------|
| `StringEquals` | `=` | Direct mapping |
| `StringNotEquals` | `!=` | Direct mapping |
| `StringLike` | Pattern matching limited | OCI supports basic wildcards in some contexts |
| `StringNotLike` | `!=` with pattern | Limited support |
| `StringEqualsIgnoreCase` | **NOT SUPPORTED** | Workaround: normalize at application layer |
| `StringNotEqualsIgnoreCase` | **NOT SUPPORTED** | Workaround: normalize at application layer |

### Numeric Operators

| AWS Operator | OCI Equivalent | Notes |
|--------------|----------------|-------|
| `NumericEquals` | `=` | Supported for numeric comparisons |
| `NumericNotEquals` | `!=` | Supported |
| `NumericLessThan` | `<` | **NOT SUPPORTED** in most OCI contexts |
| `NumericLessThanEquals` | `<=` | **NOT SUPPORTED** in most OCI contexts |
| `NumericGreaterThan` | `>` | **NOT SUPPORTED** in most OCI contexts |
| `NumericGreaterThanEquals` | `>=` | **NOT SUPPORTED** in most OCI contexts |

**Workaround:** For numeric range checks, use group-based policies or external enforcement.

### Date/Time Operators

| AWS Operator | OCI Equivalent | Notes |
|--------------|----------------|-------|
| `DateEquals` | Time-based conditions | Limited support via `request.utc-timestamp` |
| `DateNotEquals` | **NOT SUPPORTED** | |
| `DateLessThan` | **NOT SUPPORTED** | |
| `DateGreaterThan` | **NOT SUPPORTED** | |

**OCI Time Support:**
- `request.utc-timestamp` - Full timestamp
- `request.utc-timestamp.month-of-year` - Month only
- `request.utc-timestamp.day-of-month` - Day only
- `request.utc-timestamp.day-of-week` - Day of week
- `request.utc-timestamp.time-of-day` - Time range

**Example:**
```
Allow group developers to use instances in compartment dev where request.utc-timestamp.day-of-week = 'Monday'
```

### Boolean Operators

| AWS Operator | OCI Equivalent | Notes |
|--------------|----------------|-------|
| `Bool` | `= true` or `= false` | Limited boolean context keys |
| `BoolIfExists` | **NOT SUPPORTED** | OCI has no `IfExists` operator |

### IP Address Operators

| AWS Operator | OCI Equivalent | Notes |
|--------------|----------------|-------|
| `IpAddress` | Network sources | Must pre-create network source |
| `NotIpAddress` | **NOT SUPPORTED** | Can't negate network sources |

**OCI Network Sources:**
Must be pre-created via API/Console, then referenced by name.

**Example:**
```
# First create network source via API:
oci network-firewall network-source create --name corporate-network --cidr-blocks '["10.0.0.0/8"]'

# Then use in policy:
Allow group admins to manage all-resources in tenancy where request.networkSource.name = 'corporate-network'
```

### ARN Operators

| AWS Operator | OCI Equivalent | Notes |
|--------------|----------------|-------|
| `ArnEquals` | OCID comparison | Use `target.resource.id` or name-based |
| `ArnLike` | **NOT SUPPORTED** | OCI uses OCIDs, not ARNs |
| `ArnNotEquals` | `!=` with OCID | |
| `ArnNotLike` | **NOT SUPPORTED** | |

### Null Check

| AWS Operator | OCI Equivalent | Notes |
|--------------|----------------|-------|
| `Null` | **NO DIRECT EQUIVALENT** | OCI evaluates missing keys as `false` |

### IfExists Variants

| AWS Operator | OCI Equivalent | Notes |
|--------------|----------------|-------|
| `*IfExists` | **NOT SUPPORTED** | All OCI conditions require key presence |

**Workaround:** Create separate policy statements for different scenarios.

## Context Key Mappings

### AWS Global Keys → OCI Variables

| AWS Context Key | OCI Variable | Translation Notes |
|-----------------|--------------|-------------------|
| `aws:username` | `request.user.name` | User name |
| `aws:userid` | `request.user.id` | User OCID |
| `aws:PrincipalArn` | `request.user.id` | OCI uses OCID not ARN |
| `aws:PrincipalAccount` | N/A | OCI is tenancy-scoped |
| `aws:PrincipalOrgID` | N/A | OCI has no org concept at policy level |
| `aws:PrincipalTag/key` | `request.principal.group.tag.key` | Tag on user's groups |
| `aws:PrincipalType` | `request.principal.type` | user, cluster, etc. |
| `aws:SourceIp` | `request.networkSource.name` | Must pre-create network source |
| `aws:SourceVpc` | **NOT SUPPORTED** | No VPC-based conditions |
| `aws:SourceVpce` | **NOT SUPPORTED** | |
| `aws:RequestedRegion` | `request.region` | Region code (3-letter in OCI) |
| `aws:CurrentTime` | `request.utc-timestamp` | ISO 8601 timestamp |
| `aws:EpochTime` | **NOT SUPPORTED** | Use `request.utc-timestamp` |
| `aws:MultiFactorAuthPresent` | **NOT SUPPORTED** | Enforce at IdP level |
| `aws:MultiFactorAuthAge` | **NOT SUPPORTED** | No MFA age tracking |
| `aws:SecureTransport` | **NOT SUPPORTED** | HTTPS enforced by default |
| `aws:UserAgent` | **NOT SUPPORTED** | |
| `aws:Referer` | **NOT SUPPORTED** | |
| `aws:ResourceTag/key` | `target.resource.tag.key` | Tag on target resource |

### AWS Service-Specific → OCI

| AWS Key | OCI Equivalent | Notes |
|---------|----------------|-------|
| `s3:x-amz-server-side-encryption` | **NOT SUPPORTED** | Use bucket-level encryption policy |
| `s3:x-amz-acl` | **NOT SUPPORTED** | OCI uses different bucket policy model |
| `ec2:ResourceTag/key` | `target.resource.tag.key` | Resource tagging |
| `ec2:InstanceType` | **NOT SUPPORTED** | No shape-based policy conditions |
| `ec2:Region` | `request.region` | Region restriction |
| `dynamodb:LeadingKeys` | **NOT SUPPORTED** | No fine-grained NoSQL conditions |
| `lambda:FunctionArn` | `target.function.id` | Function OCID |

## Common Translation Patterns

### Pattern 1: MFA Requirement

**AWS:**
```json
"Condition": {
  "BoolIfExists": {
    "aws:MultiFactorAuthPresent": true
  }
}
```

**OCI Workaround:**
1. Enforce MFA at identity provider (SAML/SCIM) level
2. Create separate group for MFA-verified users
3. Grant permissions to that group only

```
# Assume IdP enforces MFA for group 'mfa-verified-admins'
Allow group mfa-verified-admins to manage instances in compartment production
```

### Pattern 2: MFA Age Check

**AWS:**
```json
"Condition": {
  "NumericLessThan": {
    "aws:MultiFactorAuthAge": "3600"
  }
}
```

**OCI:**
**NOT SUPPORTED** - Recommend external session management or IdP-level controls.

### Pattern 3: IP Address Restriction

**AWS:**
```json
"Condition": {
  "IpAddress": {
    "aws:SourceIp": ["203.0.113.0/24", "198.51.100.0/24"]
  }
}
```

**OCI:**
```bash
# First create network source
oci network-firewall network-source create \
  --name allowed-office-ips \
  --public-source-list '["203.0.113.0/24","198.51.100.0/24"]'

# Then use in policy
Allow group employees to manage instances in compartment dev where request.networkSource.name = 'allowed-office-ips'
```

### Pattern 4: Tag-Based Access (Owner Match)

**AWS:**
```json
"Condition": {
  "StringEquals": {
    "aws:ResourceTag/Owner": "${aws:username}"
  }
}
```

**OCI:**
```
Allow group developers to use instances in compartment dev where target.resource.tag.Owner = request.user.name
```

**Direct translation!** This is one case where OCI has excellent parity.

### Pattern 5: Tag-Based Access (Environment Match)

**AWS:**
```json
"Condition": {
  "StringEquals": {
    "ec2:ResourceTag/Environment": "production"
  }
}
```

**OCI:**
```
Allow group ops-team to manage instances in compartment prod where target.resource.tag.Environment = 'production'
```

### Pattern 6: Regional Restriction

**AWS:**
```json
"Condition": {
  "StringEquals": {
    "aws:RequestedRegion": ["us-west-2", "us-east-1"]
  }
}
```

**OCI:**
```
Allow group global-admins to manage all-resources in tenancy where any {request.region = 'PHX', request.region = 'IAD'}
```

**Note:** OCI uses 3-letter region codes:
- us-west-2 → PHX (Phoenix)
- us-east-1 → IAD (Ashburn)

### Pattern 7: Time-of-Day Restriction

**AWS:**
```json
"Condition": {
  "StringLike": {
    "aws:CurrentTime": "2024-*-*T09:00:00Z"
  }
}
```

**OCI:**
```
Allow group business-hours-users to use instances in compartment dev where request.utc-timestamp.time-of-day >= '09:00:00Z' AND request.utc-timestamp.time-of-day <= '17:00:00Z'
```

**Note:** OCI supports time-of-day ranges but NOT full date ranges.

### Pattern 8: VPC Endpoint Restriction

**AWS:**
```json
"Condition": {
  "StringEquals": {
    "aws:SourceVpce": "vpce-1a2b3c4d"
  }
}
```

**OCI:**
**NOT SUPPORTED** - OCI has no VPC endpoint-based policy conditions.

**Workaround:** Use service gateway + route table restrictions (infrastructure-level, not IAM).

### Pattern 9: Encryption Requirement (S3)

**AWS:**
```json
"Condition": {
  "StringNotEquals": {
    "s3:x-amz-server-side-encryption": "AES256"
  }
}
```

**OCI:**
**NOT SUPPORTED in IAM policy** - Set encryption at bucket level:

```bash
# Configure bucket-level encryption (not IAM policy)
oci os bucket create --name my-bucket --kms-key-id <key-ocid>
```

### Pattern 10: Cross-Account Access

**AWS:**
```json
{
  "Principal": {
    "AWS": "arn:aws:iam::123456789012:root"
  },
  "Condition": {
    "StringEquals": {
      "sts:ExternalId": "unique-external-id"
    }
  }
}
```

**OCI:**
Cross-tenancy policies use different mechanism:

```
# In the target tenancy, create policy allowing external tenancy
Define tenancy PartnerTenancy as ocid1.tenancy.oc1..aaaaaa...
Endorse group GroupInPartnerTenancy to manage buckets in compartment shared-data

# In the partner tenancy
Admit group MyGroup to manage buckets in tenancy TargetTenancy:compartment:shared-data
```

## Unsupported Conditions & Workarounds

### Category: MFA & Session Security

| AWS Feature | OCI Workaround |
|-------------|----------------|
| MFA presence check | Enforce at IdP, create MFA-verified group |
| MFA age check | Use IdP session timeout |
| Secure transport (HTTPS) | Always enforced by OCI |

### Category: Network

| AWS Feature | OCI Workaround |
|-------------|----------------|
| VPC endpoint restriction | Use service gateway + network routing |
| VPC source restriction | Not applicable (OCI network model differs) |
| Source VPN check | Use network source with VPN IPs |

### Category: Service-Specific

| AWS Feature | OCI Workaround |
|-------------|----------------|
| S3 encryption header | Set bucket-level encryption policy |
| S3 ACL restrictions | Use OCI bucket policies (different model) |
| EC2 instance type | Not supported; use compartments to separate workloads |
| Lambda runtime restriction | Not supported in OCI Functions |

### Category: Time & Access Patterns

| AWS Feature | OCI Workaround |
|-------------|----------------|
| Full date/time ranges | Use time-of-day + day-of-week |
| Date-based expiration | External automation (e.g., cron job to update policies) |
| Session duration | Configure at IdP level |

### Category: Complex Logic

| AWS Feature | OCI Workaround |
|-------------|----------------|
| Nested AND/OR/NOT | Split into multiple policy statements |
| IfExists conditions | Create separate policies for different scenarios |
| Null checks | Handle at application layer |

## Translation Decision Tree

```
AWS Condition
    │
    ├─ Is it tag-based? → YES → Direct translation (target.resource.tag.*)
    │
    ├─ Is it IP-based? → YES → Create network source first, then use request.networkSource.name
    │
    ├─ Is it time-based? → YES → Check if time-of-day/day-of-week sufficient
    │                              NO → External enforcement
    │
    ├─ Is it MFA-related? → YES → Enforce at IdP level + group-based policy
    │
    ├─ Is it region-based? → YES → Use request.region (map AWS region to OCI)
    │
    ├─ Is it encryption/VPC? → YES → NOT SUPPORTED - use infrastructure controls
    │
    └─ Other? → Check condition-mappings table → If NOT SUPPORTED, document gap
```

## Validation Checklist

When translating AWS conditions to OCI:

- [ ] Check if OCI supports the condition operator
- [ ] Verify context key is available in OCI
- [ ] Pre-create network sources if using IP restrictions
- [ ] Map AWS region names to OCI 3-letter codes
- [ ] Document any unsupported conditions in gaps report
- [ ] Test with `oci iam policy validate` command
- [ ] For unsupported conditions, provide workaround or flag for manual review

## References

- OCI General Variables: `docs/oci-reference/conditions/general-variables-for-all-requests.md`
- AWS Condition Operators: `docs/aws-reference/user-guide/iam-json-policy-elements-condition-operators.md`
- Network Sources: Pre-create via `oci network-firewall network-source create`
