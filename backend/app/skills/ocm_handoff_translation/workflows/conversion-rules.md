# EC2 → OCM Hybrid Translation Rules

## Overview

Unlike `ec2_translation` which emits `oci_core_instance` HCL directly,
this skill produces **Oracle Cloud Migrations (OCM)** resources. OCM is
Oracle's managed migration service: it replicates EC2 volumes block-level
into OCI Block Volumes, then launches replacement instances from them.

**Your output bundle**:
- `main.tf` — the `oci_cloud_migrations_*` resources
- `variables.tf` — OCM + source + target variables
- `outputs.tf` — migration OCID, plan OCID, work-request references
- `handoff.md` — a step-by-step runbook the operator follows before + after `terraform apply`

## Input shape

```json
{
  "instances": [
    {
      "instance_id": "i-abc", "instance_type": "m5.large",
      "architecture": "x86_64", "platform": "", "root_device_type": "ebs",
      "vpc_id": "vpc-1", "subnet_id": "sub-1",
      "availability_zone": "us-east-1a",
      "ocm_compatibility": {
        "level": "full" | "with_prep" | "manual" | "unsupported",
        "matched_rule": "...", "prep_steps": [...], "notes": [...]
      }
    }
  ],
  "ocm_prereqs": [ /* from ocm_support.yaml handoff_prereqs */ ],
  "target_shape_whitelist": [ "VM.Standard.E5.Flex", ... ],
  "target_compartment_var": "compartment_ocid",
  "target_vcn_var": "target_vcn_ocid",
  "target_subnet_var": "target_subnet_ocid"
}
```

**Crucial**: only translate instances whose `ocm_compatibility.level` is
`full`, `with_prep`, or `manual`. Skip `unsupported` entries entirely —
they belong to the native `ec2_translation` fallback path; this skill must
NOT emit HCL for them (emit a `resource_mappings.skipped` entry instead).

## HCL to emit

### 1. Exactly one wrapper `oci_cloud_migrations_migration` per run

```hcl
resource "oci_cloud_migrations_migration" "main" {
  compartment_id = var.compartment_ocid
  display_name   = "aws-to-oci-${var.migration_name}"
  freeform_tags  = { source = "aws", strategy = "ocm-hybrid" }
}
```

### 2. Exactly one `oci_cloud_migrations_migration_plan`

```hcl
resource "oci_cloud_migrations_migration_plan" "plan" {
  compartment_id = var.compartment_ocid
  migration_id   = oci_cloud_migrations_migration.main.id
  display_name   = "plan-${var.migration_name}"
  strategies {
    strategy_type = "AS_IS"
    resource_type = "VM"
  }
}
```

### 3. One `oci_cloud_migrations_target_asset` per eligible EC2 instance

```hcl
resource "oci_cloud_migrations_target_asset" "asset_<instance_id_sanitized>" {
  compartment_id     = var.compartment_ocid
  migration_plan_id  = oci_cloud_migrations_migration_plan.plan.id
  type               = "INSTANCE"
  is_excluded_from_execution = false
  # Source linkage — filled in by the operator after running OCM discovery:
  compatibility_messages {
    # OCM returns these; left here for documentation
  }
  # Target shape — from our whitelist, picked to match source CPU/mem:
  preferred_shape_type = "<VM.Standard.E5.Flex or similar>"
  # Target networking — MUST reference variables the operator supplies:
  block_volumes_performance = 10    # Balanced (vpus=10); use 20 for io1/io2 sources
}
```

Rules for the target asset:
- `preferred_shape_type` **must** be on `target_shape_whitelist`. If the
  source doesn't map to a whitelisted shape, flag it as `manual` in the
  mapping output (the operator picks the shape in OCM).
- `block_volumes_performance` reflects the source EBS volume's tier:
  - `gp3` / `gp2` / `st1` / `sc1` → `10` (Balanced)
  - `io1` / `io2` → `20` (High Performance)
- Sanitize `instance_id` for the Terraform label: replace `-` with `_`.

### 4. Optional `oci_cloud_migrations_replication_schedule`

Emit ONE schedule covering all target assets if the user wants periodic
sync before cutover:

```hcl
resource "oci_cloud_migrations_replication_schedule" "weekly" {
  compartment_id = var.compartment_ocid
  display_name   = "weekly-sync"
  execution_recurrences = "FREQ=WEEKLY;BYDAY=SU;BYHOUR=2"
}
```

## Variables (variables.tf)

Emit at minimum:
- `var.compartment_ocid` — sensitive = false, description pointing at
  the migration compartment
- `var.migration_name` — short label for display_name
- `var.target_vcn_ocid` — OCID of the pre-provisioned target VCN
- `var.target_subnet_ocid` — OCID of the pre-provisioned target subnet
- `var.aws_credentials_secret_ocid` — the Vault secret holding AWS creds
  (OCM needs this to discover + replicate)

## Outputs (outputs.tf)

- `migration_id` → `oci_cloud_migrations_migration.main.id`
- `migration_plan_id` → `oci_cloud_migrations_migration_plan.plan.id`
- `target_asset_ids` → map of instance_id → target_asset.id

## handoff.md (the runbook)

Structure:
1. **Before `terraform apply`** — the handoff_prereqs checklist (Vault
   + secret, dynamic groups + policies, staging bucket, target VCN/subnet,
   AWS IAM user with required permissions). List each with a ✅ checkbox.
2. **Trigger OCM discovery** — `oci cloud-migrations source add-aws-source`
   with the secret OCID; then `oci cloud-migrations migration-asset
   add-aws-assets --migration-id $(terraform output migration_id)` to link
   the discovered assets.
3. **Per-instance preparation** — for each instance with
   `ocm_compatibility.level == "with_prep"`, expand its `prep_steps`
   verbatim as a sub-checklist.
4. **Execute the plan** — `oci cloud-migrations migration-plan execute
   --migration-plan-id ...` or click "Execute" in the OCM console.
5. **Monitor** — `oci work-requests work-request get` or the Migrate
   panel in our UI (Phase 3 integration).
6. **Post-launch verification** — smoke tests the operator should run
   against each migrated instance.

## Resource mappings output (for our synthesis stage)

```json
{
  "ocm_target_assets": [
    {"source_instance_id": "i-abc", "target_asset_name": "asset_i_abc",
     "preferred_shape": "VM.Standard.E5.Flex", "ocm_level": "full"}
  ],
  "skipped_for_native_fallback": [
    {"source_instance_id": "i-xyz", "aws_type": "AWS::EC2::Instance",
     "reason": "arm-architecture", "fall_back_to": "ec2_translation"}
  ]
}
```

## Gaps to always flag

- **Cross-account AWS**: if the source account is different from the
  discovery credentials' account, flag HIGH.
- **Encrypted EBS with customer-managed KMS key**: OCM re-encrypts in OCI
  Vault; note that the AWS KMS key metadata is lost. MEDIUM.
- **Instance in a non-public AWS region** (GovCloud, China): not
  documented as OCM-supported. CRITICAL.
- **Source with >20 attached EBS volumes**: OCM replication time scales
  with volume count; warn the operator on the runbook. LOW.
- **Outdated source OS** (RHEL 5/6, Ubuntu 12.04 LTS): not in the support
  matrix. CRITICAL — operator must upgrade before migrating.
