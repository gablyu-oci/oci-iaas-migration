# Migration Synthesis Rules

## Your role

You are the **final composer** of the migration. Every per-resource
skill (`network_translation`, `ec2_translation`, `storage_translation`,
`database_translation`, `loadbalancer_translation`, `iam_translation`,
`security_translation`, `serverless_translation`,
`observability_translation`, `ocm_handoff_translation`,
`cfn_terraform`) has already produced its own HCL bundle. Your job is to
**merge them into one deployable Terraform package** that the operator
runs via `terraform apply`.

## Input shape

```json
{
  "migration_name": "multi-tier-vpc",
  "jobs": [
    {
      "skill_type": "network_translation",
      "artifacts": {
        "main.tf": "<HCL with every VCN, subnet, NSG, route table, …>",
        "variables.tf": "<...>",
        "outputs.tf": "<...>"
      }
    },
    { "skill_type": "ec2_translation",    "artifacts": { ... } },
    { "skill_type": "database_translation", "artifacts": { ... } },
    … possibly 5-10 more skill jobs …
  ]
}
```

## Output contract

Return a single JSON object with **dotted filename keys** — use real
Terraform file names, not underscore aliases. The plan pipeline writes
them to disk verbatim; `main_tf` would land as `main_tf.txt` on the
operator's machine and lose syntax highlighting.

```json
{
  "main.tf":       "<merged resource + data + module blocks>",
  "variables.tf":  "<merged variable declarations, deduplicated by name>",
  "outputs.tf":    "<merged outputs, deduplicated by name>",
  "providers.tf":  "<single oci provider block + required_providers>",
  "terraform.tfvars.example": "<example var values — optional>"
}
```

## **Completeness is the whole job**

This is the #1 rule. The operator will `terraform apply` your output
and expects every AWS resource the discovery pass found to have a
corresponding OCI resource in the final stack.

- **Include every single `resource` / `data` / `module` block from every
  input job.** Do not pick representatives. Do not write `# ... and 20
  more similar resources ...`. If the input has 34 resources spread
  across 8 skills, the output has ≥ 34 resources.
- **Do not summarize, condense, or "consolidate for brevity".** A plan
  bundle with 5 resources when 34 were expected is a failure — the
  missing 29 resources simply won't get created in OCI.
- **Counting check**: before you finish, mentally grep your `main.tf`
  for `^resource "` and confirm the count matches (or exceeds, because
  some skills emit multiple TF resources per AWS source) the number of
  AWS resources in the input jobs. If the count is off by more than a
  handful, your output is wrong — return to completeness.
- **If your output is getting long, that's fine.** Terraform files of
  2000+ lines are normal for enterprise stacks. Prefer long over
  truncated. Do not emit placeholders like `# TODO: add more subnets`.

## Merging rules (the how)

### Resources
- Concatenate. Every job's resource blocks appear in the output.
- **Resolve name collisions** by renaming one copy with the source
  skill as a suffix — e.g. two `oci_core_vcn "main"` blocks become
  `oci_core_vcn "main"` and `oci_core_vcn "main_from_ec2"` (or fold
  them if truly the same VCN, but only if you verify every attribute
  matches).

### Variables
- Dedupe by name: if two jobs both declare `variable "compartment_ocid"
  {}`, keep one. If they declare the same variable with *different*
  types or defaults, keep the stricter one (e.g. `sensitive = true`
  wins over `sensitive = false`) and add a comment noting the conflict.

### Outputs
- Dedupe by name. If two outputs expose the same name with different
  values, prefer the one from the more-downstream skill (synthesis >
  ec2 > network).

### Provider configuration
- Emit **exactly one** `provider "oci" {}` block and exactly one
  `terraform { required_providers { ... } }` block in `providers.tf`.
  Do not duplicate across files. The per-skill outputs may each carry
  one — merge into a single authoritative provider file.

### Data sources
- Concatenate like resources. Dedupe `data "oci_identity_compartment"
  "this"` and similar lookup-only blocks.

### Modules
- If any input job used `module { source = "..." }`, preserve it. Do
  NOT inline the module's contents.

### Cross-skill references
- A `variables.tf` from `ec2_translation` may reference a VCN OCID that
  came out of `network_translation` via a variable. In the merged
  stack, rewrite these as direct resource references (e.g.
  `oci_core_vcn.main.id`) instead of variables where possible. This
  shrinks the required `terraform.tfvars` and makes the plan
  self-contained.

## What to call out

After merging, emit two optional companion files that the bundle
surfaces as reports:

- `prerequisites.md`: OCI Vault + compartment + IAM + FastConnect
  prerequisites the operator must satisfy before `terraform apply`.
- `special-attention.md`: any cross-skill conflicts you resolved (name
  collisions, variable-default mismatches, etc.) so the operator knows
  what to verify.

These are shorter and can be 200-400 words each. They go in the
`reports/` section of the bundle, not alongside the HCL.

## Validation

Call `terraform_validate(main_tf, variables_tf, outputs_tf)` on your
output before returning. If it fails with undeclared-variable or
missing-resource errors, fix and re-validate. Do **not** return an
output that fails `terraform validate`.

## Gaps to always flag

- **Provider version mismatch**: if input jobs targeted different
  `hashicorp/oci` versions, pick the newest and warn in
  special-attention.md.
- **Credential conflicts**: if two jobs expect `var.compartment_ocid`
  and one expects `var.compartment_id`, pick one name, rewrite the
  references, and flag.
- **Any skill input that was empty or trivially wrong**: surface as
  `gaps` so the operator sees why a resource type is missing.
