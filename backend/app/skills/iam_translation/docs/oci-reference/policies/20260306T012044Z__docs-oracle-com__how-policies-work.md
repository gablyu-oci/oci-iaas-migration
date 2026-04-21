# How OCI Policies Work

Source: https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policies.htm
Captured: 2026-03-06

## Overview of Policies

A _policy_ is a document that specifies who can access which Oracle Cloud Infrastructure resources that your company has, and how. A policy simply allows a **group** to work in certain ways with specific types of **resources** in a particular **compartment**.

### General Process

In general, here's the process an IAM administrator in your organization needs to follow:

1. Define users, groups, and one or more compartments to hold the cloud resources for your organization.
2. Create one or more policies, each written in the policy language.
3. Place users into the appropriate groups depending on the compartments and resources they need to work with.
4. Provide the users with the one-time passwords that they need in order to access the Console and work with the compartments.

After the administrator completes these steps, the users can access the Console, change their one-time passwords, and work with specific cloud resources as stated in the policies.

## Policy Basics

Each policy consists of one or more policy _statements_ that follow this basic syntax:

```
Allow group <group_name> to <verb> <resource-type> in compartment <compartment_name>
```

Statements always begin with `Allow`. Policies only _allow_ access; they cannot deny it. There is an implicit deny — by default users can do nothing and must be granted access through policies.

An administrator in your organization defines the groups and compartments in your tenancy. Oracle defines the possible verbs and resource-types you can use in policies.

When a policy applies to the tenancy itself (not a compartment), the statement ends with `in tenancy`:

```
Allow group <group_name> to <verb> <resource-type> in tenancy
```

### Examples

Example — manage users and their credentials (users reside in the tenancy, which is the root compartment):

```
Allow group HelpDesk to manage users in tenancy
```

Example — manage all resources in a compartment:

```
Allow group A-Admins to manage all-resources in compartment Project-A
```

This also includes the ability to write policies _for that compartment_, which means A-Admins can control access to the compartment's resources.

Example — limit A-Admins to launching and managing compute instances and block storage volumes (both volumes and backups) in Project-A, while the network itself lives in the Networks compartment:

```
Allow group A-Admins to manage instance-family in compartment Project-A

Allow group A-Admins to manage volume-family in compartment Project-A

Allow group A-Admins to use virtual-network-family in compartment Networks
```

The third statement (with the `virtual-network-family` resource-type) enables the instance launch process, because the cloud network is involved (launch creates a new VNIC and attaches it to a subnet).

### Specifying Groups and Compartments

Specify a group or compartment by name — or by OCID, preceded by `id`:

```
Allow group id ocid1.group.oc1..aaaaaaaaqjihfhvxmumrl3isyrjw3n6c4rzwskaawuc7i5xwe6s7qmnsbc6a to manage instance-family in compartment Project-A
```

Multiple groups are comma-separated:

```
Allow group A-Admins, B-Admins to manage instance-family in compartment Projects-A-and-B
```

## Verbs

Oracle defines four possible verbs, from least to most access:

| Verb | Target User | Types of Access Covered |
|------|-------------|------------------------|
| `inspect` | Third-party auditors | List resources, without access to confidential information or user-specified metadata. **Important:** Listing policies includes the contents of the policies themselves. Listing Networking resource-types returns all the information (e.g. the contents of security lists and route tables). |
| `read` | Internal auditors | Includes `inspect` plus the ability to get user-specified metadata and the actual resource itself. |
| `use` | Day-to-day end users | Includes `read` plus the ability to work with existing resources. Includes update except where an "update" is effectively a "create" (e.g. `UpdatePolicy`, `UpdateSecurityList`), in which case update requires `manage`. Generally does not include create or delete. |
| `manage` | Administrators | Includes all permissions for the resource. |

The verb gives a general type of access. Joining the verb with a particular resource-type (for example, `Allow group XYZ to inspect compartments in the tenancy`) grants a specific set of permissions and API operations (e.g. `ListCompartments`, `GetCompartment`).

### Special Exceptions for Certain Resource-Types

- **Users:** `manage users` + `manage groups` lets you do anything with users and groups (including add/remove membership). To add/remove users from groups without also letting callers create/delete users and groups, grant `use users` + `use groups`.
- **Policies:** Updating a policy requires `manage policies`, not `use policies`, because update is effectively create. Also, `inspect policies` returns the full contents of policies.
- **Object Storage objects:** `inspect objects` lets you list all objects and do HEAD. `read objects` lets you download the object.
- **Load Balancer resources:** `inspect load-balancers` returns all information about load balancers and related components.
- **Networking:** `inspect` returns contents of components (e.g. the actual rules in a security list). Updating `internet-gateways`, `security-lists`, `route-tables`, `dhcp-options`; attaching a DRG to a VCN; creating an IPSec connection between DRG and CPE; and peering VCNs all require `manage`.

**Important VCN caveat:** Creating a component of a VCN (route tables, security lists, DHCP options, Internet Gateway, etc.) requires policy to both create the component and manage the VCN. However, _updating_ that component does **not** require `manage vcns`, even though updating can directly affect network behavior. This is deliberate, to allow least-privilege grants.

## Resource-Types

Oracle defines two categories:

- **Individual** types — e.g. `vcns`, `volumes`, `instances`, `buckets`.
- **Family** types — bundles of individual types that are typically managed together. Examples:
  - `virtual-network-family` (VCNs, subnets, route-tables, security-lists, etc.)
  - `volume-family` (volumes, volume-attachments, volume-backups)
  - `instance-family`, `compute-management-family`, `object-family`, etc.

**Important:** If a service adds a new individual resource-type, it is typically added to the family automatically. But if a service adds new permissions to an existing resource type, you must update the policy statement for that existing resource type for the new permissions to take effect.

## Access that Requires Multiple Resource-Types

Some API operations require access to multiple resource-types. For example, `LaunchInstance` requires access to create instances and to work with a cloud network. `CreateVolumeBackup` requires access to both the volume and the volume backup. Separate statements are written for each resource-type. These statements don't have to be in the same policy, and a user can gain the required access from being in different groups. The sum of the individual statements, regardless of location, gives the user access.

## Policy Inheritance

A basic feature of OCI policies is **inheritance**: compartments inherit any policies from their parent compartment. The built-in policy:

```
Allow group Administrators to manage all-resources in tenancy
```

...means Administrators can do anything in _any_ compartment in the tenancy.

Example — a tenancy with three levels (CompartmentA → CompartmentB → CompartmentC):

```
Allow group NetworkAdmins to manage virtual-network-family in compartment CompartmentA
```

This allows NetworkAdmins to manage VCNs in CompartmentA, CompartmentB, **and** CompartmentC.

## Policy Attachment

When you create a policy you must attach it to a compartment (or to the tenancy, which is the root compartment). **Where you attach it controls who can modify or delete it.**

- Attach to the **tenancy** (root): anyone with access to manage policies in the tenancy (typically Administrators) can modify or delete it. Anyone with access only to a child compartment cannot.
- Attach to a **child compartment**: anyone with access to manage the policies _in that compartment_ can change or delete it. This lets compartment admins manage their own compartment's policies without being granted broader access to tenancy-level policies.

Mechanics:

- Console: navigate to the desired compartment before creating the policy.
- API: specify the OCID of the compartment (tenancy or child) as part of `CreatePolicy`.
- A policy can be attached to exactly one compartment.
- You must be in the compartment you are attaching the policy to, and the statement must indicate the compartment that access is granted in.

## Policies and Compartment Hierarchies

The statement must specify the compartment (or tenancy) that access is granted in. If the policy is attached to the compartment or its direct parent, you can just use the compartment name. If it's attached further up the hierarchy, specify the compartment **path** using `:` as separator:

```
<compartment_level_1>:<compartment_level_2>: . . . <compartment_level_n>
```

Example with three levels (A parent, B child of A, C child of B):

- Attach to CompartmentC or to CompartmentB:
  ```
  Allow group NetworkAdmins to manage virtual-network-family in compartment CompartmentC
  ```
- Attach to CompartmentA:
  ```
  Allow group NetworkAdmins to manage virtual-network-family in compartment CompartmentB:CompartmentC
  ```
- Attach to the tenancy:
  ```
  Allow group NetworkAdmins to manage virtual-network-family in compartment CompartmentA:CompartmentB:CompartmentC
  ```

## Policies and Service Updates

Verb / resource-type definitions can change. By default, policies stay current with service changes — for example, if `virtual-network-family` later adds a new sub-type, existing `virtual-network-family` grants automatically include it.

**Important:** If a service introduces new permissions for an existing resource type, you must update the policy statement for the existing resource type to make the new permissions take effect.

## Evaluation Model (summary)

- **Default deny.** Nothing is allowed until a policy statement grants it.
- **No explicit deny.** Policies are additive only; there is no `Deny` statement.
- **Union of statements.** A user gains the union of all permissions granted by every statement applicable to every group the user is a member of (directly or via dynamic-groups).
- **Inheritance from parent compartments.** A statement attached higher in the compartment tree applies to all descendant compartments.
- **Conditions narrow.** `where` conditions further scope a grant; if a condition is not applicable to the request, it evaluates to false and the request is declined.
