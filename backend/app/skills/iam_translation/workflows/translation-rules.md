# AWS IAM to OCI IAM Policy Translation Rules

## Overview
This document defines the systematic rules for translating AWS IAM policies to OCI IAM policy language.

## Key Differences: AWS vs OCI IAM

### 1. Policy Structure
**AWS IAM:**
- JSON-based
- Effect: Allow/Deny
- Actions: `service:Action` (e.g., `s3:PutObject`)
- Resources: ARN-based (e.g., `arn:aws:s3:::bucket/*`)
- Conditions: Complex JSON conditions

**OCI IAM:**
- Plain-English statements
- Verb-based permissions: `inspect`, `read`, `use`, `manage`
- Resource types (not ARNs): `instances`, `buckets`, `databases`
- Compartment-scoped (hierarchical)
- Limited condition support (groups, tags, network sources)

### 2. Permission Verb Mapping (Detailed)

| OCI Verb | Access Level | Typical AWS Actions | Important Notes |
|----------|--------------|---------------------|-----------------|
| `inspect` | List metadata | Describe*, List*, Get* (metadata) | **WARNING:** Returns more than you think! See special cases below. |
| `read` | View + download | Get*, Download*, Describe* (with content) | Includes inspect + actual resource data |
| `use` | Limited modifications | Start*, Stop*, Reboot*, some Update* | Does NOT include Create/Delete for most resources |
| `manage` | Full control | All actions (*, Create*, Delete*, Update*) | Complete lifecycle management |

#### Special Cases & Verb Nuances

**CRITICAL: `inspect` is not always "safe"!**

These resources return sensitive data with `inspect`:

| Resource Type | What `inspect` Returns | Security Implication |
|---------------|------------------------|----------------------|
| `policies` | **Full policy content** | Not just metadata - entire policy statements visible |
| `security-lists` | **Complete security rules** | All ingress/egress rules exposed |
| `route-tables` | **All route entries** | Network topology visible |
| `load-balancers` | **Full LB configuration** | Backend sets, health checks, certificates info |
| `vcns` | **Network configuration** | CIDR blocks, DNS settings |

**Users Resource:**
- `manage users` + `manage groups` → Full user lifecycle + group management
- `use users` + `use groups` → Add/remove users from groups ONLY (no create/delete users)

**Policies Resource:**
- `update policy` requires `manage policies` (not `use`)
- Reason: Updating = effectively creating new policy (security-sensitive)

**Object Storage:**
- `inspect objects` → List objects + HEAD operation (metadata)
- `read objects` → Download actual object content
- Separate statements required for buckets vs objects!

**Networking:**
- Update security-lists → Requires `manage` (not `use`)
- Update route-tables → Requires `manage` (not `use`)
- Update DHCP options → Requires `manage` (not `use`)
- Enable/disable internet-gateways → Requires `manage` (not `use`)
- Attach DRG to VCN → Requires `manage` (not `use`)

**Key principle:** When creating a component that attaches to VCN (security-list, route-table, etc.), you need permission to both create the component AND `manage` the VCN. However, updating that component later does NOT require `manage vcns`.

### 2b. Verb Selection Algorithm

```
Start
  │
  ├─ Need Create or Delete? ──YES──> manage
  │         │
  │         NO
  │         │
  ├─ Need Update (policy, security-list, route-table)? ──YES──> manage
  │         │
  │         NO
  │         │
  ├─ Need Start/Stop/Reboot/limited updates? ──YES──> use
  │         │
  │         NO
  │         │
  ├─ Need to download data (objects, backups)? ──YES──> read
  │         │
  │         NO
  │         │
  └─ Only listing/viewing metadata? ──YES──> inspect
                                              (but check special cases above!)
```

### 3. Core Translation Rules

#### Rule 1: Service Name Mapping
```
AWS Service → OCI Service
ec2 → compute (instances, images, vnics)
s3 → object-storage (buckets, objects)
rds → database (db-systems, db-homes)
dynamodb → nosql (tables, streams)
lambda → fn (functions, applications)
iam → identity (users, groups, policies)
kms → kms (keys, vaults)
vpc → networking (vcns, subnets, security-lists)
```

#### Rule 2: Resource Hierarchy
AWS uses flat ARN paths; OCI uses compartment hierarchy.

**AWS:**
```
Resource: arn:aws:s3:::my-bucket/*
```

**OCI:**
```
in compartment project-a where target.bucket.name = 'my-bucket'
```

#### Rule 3: Condition Translation
Limited OCI condition support. Many AWS conditions become group-based policies.

**AWS MFA Condition:**
```json
"Condition": {
  "BoolIfExists": {
    "aws:MultiFactorAuthPresent": false
  }
}
```

**OCI Equivalent:**
Create separate policy for MFA-verified users (not natively supported):
```
Allow group mfa-verified-admins to manage instances in compartment production
```

#### Rule 4: Tag-Based Access Control
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

#### Rule 5: Network Source Restrictions
**AWS IP restriction:**
```json
"Condition": {
  "NotIpAddress": {
    "aws:SourceIp": ["192.0.2.0/24"]
  }
}
```

**OCI:**
```
Allow group admins to manage all-resources in tenancy where request.networkSource.name = 'corporate-network'
```

## Translation Workflow

### Step 1: Parse AWS Policy
Extract:
- Service (e.g., `ec2`, `s3`)
- Actions (e.g., `StartInstances`, `PutObject`)
- Resources (ARNs)
- Conditions
- Effect (Allow/Deny)

### Step 2: Map Service → OCI Resource Type
Use service mapping table (Rule 1)

### Step 3: Determine OCI Verb
Analyze action granularity:
- Only `Describe*/List*/Get*` → `inspect`
- Read + limited write → `use`
- Full CRUD → `manage`

### Step 4: Extract Compartment Scope
From AWS resource ARN, infer compartment structure:
- Account ID → Tenancy
- Resource path segments → Compartment hierarchy

Example:
```
arn:aws:ec2:us-west-2:123456789012:instance/i-*
→ compartment us-west-2 (or infer from tags/metadata)
```

### Step 5: Handle Conditions
- **MFA**: Recommend separate group for MFA-verified users
- **IP restrictions**: Convert to OCI network sources (pre-create via API)
- **Tag-based**: Direct translation using `target.resource.tag.*`
- **Time-based**: OCI does not support time conditions (recommend external enforcement)

### Step 6: Generate OCI Policy Statement
Template:
```
Allow group <group-name> to <verb> <resource-type> in compartment <compartment> where <conditions>
```

### Step 7: Handle Deny Statements
OCI has limited Deny support (mostly for tenancy-level policies).
- Convert AWS `Deny` to inverted `Allow` when possible
- Flag for manual review if complex

## Example Translations

### Example 1: EC2 Start/Stop with MFA
**AWS:**
```json
{
  "Effect": "Allow",
  "Action": ["ec2:StartInstances", "ec2:StopInstances"],
  "Resource": "arn:aws:ec2:*:*:instance/*",
  "Condition": {
    "BoolIfExists": {"aws:MultiFactorAuthPresent": true}
  }
}
```

**OCI:**
```
Allow group mfa-verified-ops to use instances in compartment production
```
*(Note: Requires pre-creating `mfa-verified-ops` group with MFA enforcement at IdP level)*

### Example 2: S3 Read Access to Specific Bucket
**AWS:**
```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:ListBucket"],
  "Resource": [
    "arn:aws:s3:::my-data-bucket",
    "arn:aws:s3:::my-data-bucket/*"
  ]
}
```

**OCI:**
```
Allow group data-readers to read buckets in compartment data-storage where target.bucket.name = 'my-data-bucket'
Allow group data-readers to read objects in compartment data-storage where target.bucket.name = 'my-data-bucket'
```

### Example 3: Lambda DynamoDB Access
**AWS:**
```json
{
  "Effect": "Allow",
  "Action": [
    "dynamodb:PutItem",
    "dynamodb:GetItem",
    "dynamodb:Query"
  ],
  "Resource": "arn:aws:dynamodb:us-west-2:123456789012:table/MyTable"
}
```

**OCI:** (Functions accessing NoSQL)
```
Allow dynamic-group lambda-functions to use nosql-tables in compartment application where target.nosql-table.name = 'MyTable'
```
*(Dynamic group defined as: matching-rule = "ALL {resource.type = 'fnfunc'}")*

### Example 4: Tag-Based EC2 Access
**AWS:**
```json
{
  "Effect": "Allow",
  "Action": ["ec2:StartInstances", "ec2:StopInstances"],
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "aws:ResourceTag/Owner": "${aws:username}"
    }
  }
}
```

**OCI:**
```
Allow group developers to use instances in compartment dev where target.resource.tag.Owner = request.user.name
```

### Example 5: Regional Restriction
**AWS:**
```json
{
  "Effect": "Allow",
  "Action": "rds:*",
  "Resource": "*",
  "Condition": {
    "StringEquals": {"aws:RequestedRegion": "us-west-2"}
  }
}
```

**OCI:**
```
Allow group db-admins to manage database-family in compartment production where request.region = 'us-phoenix-1'
```
*(Note: OCI regions have different naming; us-west-2 → us-phoenix-1 mapping required)*

## Edge Cases & Limitations

### 1. No Direct OCI Equivalent
**Scenarios:**
- Time-based access (`aws:CurrentTime` conditions)
- MFA age checks (`aws:MultiFactorAuthAge`)
- Service Control Policies (SCPs) → Use OCI tenancy-level policies
- Resource-based policies (S3 bucket policies) → OCI bucket-level policies (limited)

**Recommendation:** Flag for manual review + document workaround

### 2. Complex Condition Logic
AWS supports nested `AND`/`OR`/`NOT` in conditions. OCI supports single-level `where` clauses.

**Solution:** Split into multiple OCI policy statements

### 3. Cross-Account Access
AWS uses resource-based policies + trust relationships. OCI uses federation + cross-tenancy policies.

**Workflow:**
1. Identify cross-account ARNs
2. Convert to OCI federation setup (SAML/SCIM)
3. Generate cross-tenancy policy statements

## Enhanced Translation Workflow

### Step 1: Policy Analysis
**Input:** AWS IAM policy JSON  
**Actions:**
- Identify all services referenced (ec2, s3, rds, etc.)
- Extract unique actions per service
- List all condition operators used
- Identify resource patterns (ARNs)
- Note Effect types (Allow vs Deny)

**Output:** Structured analysis document

### Step 2: Service & Resource Mapping
**Process:**
- Map AWS service → OCI service (see `action-verb-mappings.md`)
- Map AWS resources (ARNs) → OCI resource types + compartments
- Extract resource identifiers (names, tags) from ARNs

**Example:**
```
arn:aws:s3:::my-data-bucket/* 
  → Resource type: objects
  → Compartment: data-storage
  → Condition: where target.bucket.name = 'my-data-bucket'
```

### Step 3: Action → Verb Translation
**Decision tree:**
1. Group actions by AWS service
2. For each action group:
   - All actions are Describe*/List*/Get* (metadata only)? → `inspect`
   - Includes Get* (data download)? → `read`  
   - Includes Start/Stop/limited updates? → `use`
   - Includes Create*/Delete*/full updates? → `manage`
3. If mixed permissions → Split into multiple OCI statements or use highest verb

**Reference:** `action-verb-mappings.md`

### Step 4: Condition Translation
**Process:**
- For each condition in AWS policy:
  - Check if OCI supports the operator (see `condition-mappings.md`)
  - Map AWS context key → OCI variable
  - If unsupported → Document gap + workaround

**Special cases:**
- MFA conditions → IdP enforcement + group segregation
- IP restrictions → Pre-create network sources
- Tag conditions → Direct translation (good parity!)
- Time conditions → Use OCI time variables (limited)
- VPC/encryption → Infrastructure-level controls

**Reference:** `condition-mappings.md`

### Step 5: Compartment Design
**Strategy:**
- Map AWS account structure → OCI compartments
- Use compartments for:
  - Environment separation (dev/staging/prod)
  - Project/team isolation
  - Cost tracking boundaries
  - Blast radius limitation

**Example hierarchy:**
```
Tenancy (root)
├── production
│   ├── compute
│   ├── storage
│   └── database
├── development
│   ├── compute
│   └── storage
└── shared-services
    ├── networking
    └── security
```

### Step 6: Group Strategy
**When to create groups:**
- Different permission levels (read-only, operators, admins)
- MFA enforcement requirements
- Tag-based access patterns
- Cross-functional teams

**Naming convention:**
```
<service>-<permission-level>[-qualifier]

Examples:
- ec2-operators
- ec2-admins-mfa
- s3-data-readers
- rds-backup-operators
```

### Step 7: Handle Deny Statements
**AWS Deny → OCI conversion:**

**Option A:** Group segregation (preferred)
```
AWS: Allow all EC2, Deny Terminate without MFA
OCI: Create two groups:
  - ec2-operators (use instances)
  - ec2-admins-mfa (manage instances)
```

**Option B:** Split into positive allow statements
```
AWS: Allow S3 except bucket policy changes
OCI: Explicitly list allowed verbs (read, use) without manage
```

**Option C:** Tenancy-level deny (limited use)
```
# Only for broad tenancy-wide restrictions
Deny group contractors to manage policies in tenancy
```

### Step 8: Generate OCI Policy Statements
**Template:**
```
Allow <group|dynamic-group> <group-name> to <verb> <resource-type> in <location> [where <conditions>]
```

**Components:**
- **Subject:** group or dynamic-group
- **Verb:** inspect, read, use, manage
- **Resource:** individual type or family
- **Location:** tenancy, compartment <name>, compartment <ocid>
- **Conditions:** Optional where clause

**Examples:**
```
Allow group developers to use instances in compartment dev
Allow group data-analysts to read objects in compartment analytics where target.bucket.name = 'reports'
Allow dynamic-group lambda-functions to use nosql-tables in compartment production
```

### Step 9: Prerequisites Creation
**Generate commands for:**

1. **Compartments:**
```bash
oci iam compartment create \
  --compartment-id <parent-ocid> \
  --name <compartment-name> \
  --description "Description"
```

2. **Groups:**
```bash
oci iam group create \
  --name <group-name> \
  --description "Description"
```

3. **Network Sources (if IP restrictions):**
```bash
oci network-firewall network-source create \
  --name <source-name> \
  --public-source-list '["CIDR1","CIDR2"]'
```

4. **Dynamic Groups (if service access):**
```bash
oci iam dynamic-group create \
  --name <group-name> \
  --matching-rule "ALL {resource.type = 'fnfunc', resource.compartment.id = '<ocid>'}"
```

### Step 10: Gaps Documentation
**For each unsupported feature:**
- **Feature:** AWS capability name
- **Severity:** LOW | MEDIUM | HIGH | CRITICAL
- **Impact:** What functionality is lost
- **Workaround:** Alternative approach
- **Residual risk:** Remaining security/compliance gap

**Severity criteria:**
- **CRITICAL:** No workaround; major security/compliance impact
- **HIGH:** Workaround exists but complex or incomplete
- **MEDIUM:** Reasonable workaround available
- **LOW:** Minor feature; easy alternative

## Validation Checklist

After translation, verify:

### Technical Validation
- [ ] All AWS actions mapped to OCI verbs (see action-verb-mappings.md)
- [ ] All conditions translated or documented as gaps
- [ ] OCI policy syntax validated: `oci iam policy validate --policy-document <file>`
- [ ] No syntax errors in generated statements
- [ ] Resource types are valid for target service
- [ ] Compartment OCIDs are correct
- [ ] Group names match actual OCI groups

### Infrastructure Prerequisites
- [ ] Compartment structure created in OCI (if not exists)
- [ ] All referenced compartments exist
- [ ] Network sources created (for IP restrictions)
- [ ] Network source names match policy references
- [ ] Dynamic groups defined (for service→service access)
- [ ] Dynamic group matching rules are correct
- [ ] Tags migrated to OCI resources (for tag-based conditions)
- [ ] Tag namespaces and keys defined

### Security Validation
- [ ] Group membership matches AWS IAM users/roles intent
- [ ] MFA enforcement configured at IdP level (if required)
- [ ] Least privilege maintained (not over-permissioning with `manage`)
- [ ] Deny policies converted appropriately or documented
- [ ] Cross-account access patterns reviewed
- [ ] Service-to-service access using dynamic groups (not user credentials)

### Documentation
- [ ] Gaps report created with severity ratings
- [ ] Workarounds documented for unsupported features
- [ ] Prerequisites list complete (groups, compartments, network sources)
- [ ] Deployment commands provided
- [ ] Testing plan created
- [ ] Risk assessment completed

## Automation Strategy

### Phase 1: Rule-Based Translation
- Python script parses AWS JSON
- Apply service mapping + verb selection
- Generate OCI policy text

### Phase 2: LLM-Assisted Refinement
- Feed AWS policy + translation rules to LLM (Claude Sonnet 4.5)
- LLM generates OCI policy + explains gaps
- Human reviews complex conditions

### Phase 3: Validation
- Attempt to create policy in OCI test compartment
- Catch syntax errors
- Test with sample resources

## Output Format

For each AWS policy, generate:
1. **OCI Policy Statements** (ready to apply)
2. **Prerequisites** (groups, compartments, network sources to create)
3. **Gaps Report** (features not translatable, workarounds needed)
4. **Risk Assessment** (over-permissive vs under-permissive risk)

Example output structure:
```yaml
aws_policy: "01-ec2-full-access-with-mfa.json"
oci_policies:
  - statement: "Allow group mfa-ops to manage instances in compartment production"
    compartment: "production"
    group: "mfa-ops"
prerequisites:
  groups:
    - name: "mfa-ops"
      description: "Operators with MFA enabled"
      members: ["user1@example.com", "user2@example.com"]
  compartments:
    - name: "production"
      description: "Production workloads"
      parent: "root"
gaps:
  - feature: "MFA age check (1 hour)"
    severity: "medium"
    workaround: "Enforce MFA at IdP level; OCI does not support time-based MFA age"
risk_level: "low"
notes: "OCI 'manage' verb is broader than AWS stop/terminate; consider using 'use' for tighter control"
```

---

**Next Steps:**
1. Implement Python parser for AWS IAM JSON
2. Build mapping engine using these rules
3. Integrate LLM for complex condition handling
4. Create validation framework
