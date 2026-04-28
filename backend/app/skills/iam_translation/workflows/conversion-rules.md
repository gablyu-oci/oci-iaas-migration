# AWS IAM → OCI Identity Conversion Rules

Prose guidance that doesn't fit in the mapping table.
The canonical mapping table is injected alongside this file.

## Ordering

Create in this order:

1. Dynamic Groups (referenced by policies)
2. Groups (referenced by policies and user memberships)
3. Users (if any direct user creation is required)
4. Policies (reference dynamic groups, groups, and compartments)

## Dynamic Groups

- AWS IAM instance profiles / roles → OCI dynamic groups with matching rules.
- The `matching_rule` uses OCI resource metadata, e.g.:
  `ALL {resource.type = 'instance', resource.compartment.id = '<compartment_ocid>'}`
- `compartment_id` for dynamic groups is typically the **tenancy OCID** (`var.tenancy_ocid`), not a sub-compartment.

## Policies

- AWS IAM policies (inline + managed) → `oci_identity_policy` with `statements` list.
- Each statement follows OCI syntax: `Allow <subject> to <verb> <resource-type> in <location> [where <conditions>]`.
- `compartment_id` for policies is typically the **tenancy OCID** for tenancy-wide policies, or a compartment OCID for scoped policies.
- Combine related AWS policy statements into a single OCI policy resource where they share the same scope.

## Groups and Users

- AWS IAM groups → `oci_identity_group` (use `name`, not `display_name`).
- AWS IAM users → `oci_identity_user` (use `name`, not `display_name`).
- Note: IAM resources use `name` not `display_name` for the primary identifier.

## Naming

- OCI IAM resource names must be unique within the tenancy.
- Use lowercase with hyphens for consistency.

## Gaps to always flag

- **AWS IAM Roles with assume-role trust policies:** OCI uses dynamic groups instead of role assumption. Flag HIGH.
- **Cross-account access:** OCI uses tenancy-level policies for cross-tenancy access. Flag CRITICAL.
- **Permission boundaries:** No OCI equivalent. Flag HIGH.
- **Service-linked roles:** Map to OCI service policies; may require manual setup. Flag MEDIUM.
- **SAML / OIDC federation:** OCI uses IDCS or OCI IAM domains. Flag HIGH and defer to identity domain migration.

## Structured Output Format (Phase 4)

This skill uses **structured JSON output** instead of free-form HCL.

Your output MUST be a JSON array of resource specs:

```json
[
  {
    "template": "<domain/resource_type>",
    "label": "<terraform_resource_label>",
    "params": { ... matches the template's Pydantic schema ... }
  }
]
```

### Available Templates

- `identity/dynamic_group` -- OCI dynamic group (replaces AWS IAM roles/instance profiles); `compartment_id` is typically the tenancy OCID
- `identity/policy` -- OCI IAM policy with statement list; `compartment_id` is typically the tenancy OCID
- `identity/group` -- OCI IAM group; uses `name` (not `display_name`)
- `identity/user` -- OCI IAM user; uses `name` (not `display_name`)

For resources not covered by any template, use the `free_form_hcl` fallback:
```json
{"template": "free_form_hcl", "label": "<label>", "params": {"hcl": "<raw HCL string>"}}
```

### Traceability

Every spec's `params` MUST include `aws_source_id` with the original AWS resource identifier. Include `freeform_tags` with `aws_source_id` and `managed_by = "oci-iaas-migration"` where the OCI resource supports tags.
