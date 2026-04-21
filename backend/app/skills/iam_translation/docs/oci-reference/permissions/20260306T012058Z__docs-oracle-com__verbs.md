# OCI IAM Policy Reference — Verbs

Source: https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/policyreference.htm
Section: Verbs
Captured: 2026-03-06

## Verbs

The verbs are listed in order of least amount of ability to most. The exact meaning of each verb depends on which resource-type it's paired with. The tables later in this section show the API operations covered by each combination of verb and resource-type.

| Verb | Target User | Types of Access Covered |
|------|-------------|------------------------|
| `inspect` | Third-party auditors | Ability to list resources, without access to any confidential information or user-specified metadata that might be part of that resource. **Important:** The operation to list policies includes the contents of the policies themselves. The list operations for the Networking resource-types return all the information (for example, the contents of security lists and route tables). |
| `read` | Internal auditors | Includes `inspect` plus the ability to get user-specified metadata and the actual resource itself. |
| `use` | Day-to-day end users of resources | Includes `read` plus the ability to work with existing resources (the actions vary by resource type). Includes the ability to update the resource, except for resource-types where the "update" operation has the same effective impact as the "create" operation (for example, `UpdatePolicy`, `UpdateSecurityList`, and more), in which case the "update" ability is available only with the `manage` verb. In general, this verb doesn't include the ability to create or delete that type of resource. |
| `manage` | Administrators | Includes all permissions for the resource. |

## Permission Hierarchy / Subsumption

Access is **cumulative** going from least-privileged to most-privileged:

```
inspect  ⊂  read  ⊂  use  ⊂  manage
```

- `manage` subsumes `use` subsumes `read` subsumes `inspect`.
- A group granted `manage` gets every permission that `use`, `read`, and `inspect` grant for that resource-type, plus extra create/delete permissions.
- In per-resource-type tables, a "+" in a cell indicates incremental permissions compared to the cell directly above; "no extra" means the verb does not add anything beyond what the weaker verb already grants.

## Special Exceptions for Certain Resource-Types

**Users:** Access to both `manage users` and `manage groups` lets you do anything with users and groups, including creating and deleting users and groups, and adding/removing users from groups. To add/remove users from groups without access to creating and deleting users and groups, only both `use users` and `use groups` are required.

**Policies:** The ability to update a policy is available only with `manage policies`, not `use policies`, because updating a policy is similar in effect to creating a new policy (you can overwrite the existing policy statements). In addition, `inspect policies` lets you get the full contents of the policies.

**Object Storage objects:** `inspect objects` lets you list all the objects in a bucket and do a HEAD operation for a particular object. In comparison, `read objects` lets you download the object itself.

**Load Balancer resources:** Be aware that `inspect load-balancers` lets you get _all_ information about your load balancers and related components (backend sets, and more).

**Networking resources:**

- The `inspect` verb not only returns general information about the cloud network's components (for example, the name and OCID of a security list, or of a route table). It also includes the contents of the component (for example, the actual rules in the security list, the routes in the route table, and so on).
- The following abilities are available only with the `manage` verb, not the `use` verb:
  - Update (enable/disable) `internet-gateways`
  - Update `security-lists`
  - Update `route-tables`
  - Update `dhcp-options`
  - Attach a Dynamic Routing Gateway (DRG) to a Virtual Cloud Network (VCN)
  - Create an IPSec connection between a DRG and customer-premises equipment (CPE)
  - Peer VCNs

**Important:** Each VCN has various components that directly affect the behavior of the network (route tables, security lists, DHCP options, Internet Gateway, and so on). When you create one of these components, you establish a relationship between that component and the VCN, which means you must be allowed in a policy to both create the component and manage the VCN itself. However, the ability to _update_ that component (to change the route rules, security list rules, and so on) **doesn't** require permission to manage the VCN itself, even though changing that component can directly affect the behavior of the network. This discrepancy is designed to give you flexibility in granting least privilege.

## Relation to Permissions

_Permissions_ are the atomic units of authorization. When a policy grants a group access to a verb + resource-type, it is actually granting one or more predefined permissions. Going from `inspect` → `read` → `use` → `manage`, the level of access generally increases and the permissions granted are cumulative.

Example — the `volumes` resource-type:

| Inspect Volumes | Read Volumes | Use Volumes | Manage Volumes |
|---|---|---|---|
| VOLUME_INSPECT | VOLUME_INSPECT | VOLUME_INSPECT | VOLUME_INSPECT |
| | | VOLUME_UPDATE | VOLUME_UPDATE |
| | | VOLUME_WRITE | VOLUME_WRITE |
| | | | VOLUME_CREATE |
| | | | VOLUME_DELETE |

(Note: no additional permissions are granted going from `inspect` to `read` for the `volumes` resource-type.)
