# OCI Policy Syntax

Source: https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm
Captured: 2026-03-06

## Policy Syntax

The overall syntax of a policy statement is:

```
Allow <subject> to <verb> <resource-type> in <location> where <conditions>
```

Spare spaces or line breaks in the statement have no effect.

### EBNF-style grammar

```
statement    ::= "Allow" subject "to" verb resource-type location [ "where" conditions ]

subject      ::= "group" group_name
               | "group" "id" group_ocid
               | "dynamic-group" dynamic-group_name
               | "dynamic-group" "id" dynamic-group_ocid
               | "any-group"
               | "any-user"
               | subject "," subject     (* multiple comma-separated subjects *)

verb         ::= "inspect" | "read" | "use" | "manage"

resource-type ::= individual_resource_type
                | family_resource_type
                | "all-resources"

location     ::= "tenancy"
               | "compartment" compartment_name
               | "compartment" "id" compartment_ocid
               | "compartment" compartment_path    (* e.g. A:B:C *)

conditions   ::= condition
               | ( "any" | "all" ) "{" condition ( "," condition )* "}"

condition    ::= variable ( "=" | "!=" ) value
               | variable time_operator value       (* before, after, between, in *)

value        ::= "'" string_value "'"
               | "/" pattern "/"                    (* supports * wildcard *)
```

For limits on the number of policies and statements, see "Limits by Service".

## Subject

Specify one or more comma-separated groups by name or OCID. Or specify `any-group` to cover all users, instance principals, and resource principals in the tenancy.

**Syntax:** `group <group_name> | group id <group_ocid> | dynamic-group <dynamic-group_name> | dynamic-group id <dynamic-group_ocid> | any-group | any-user`

**Note:** `any-user` grants access to all users, resource principals, instance principals, and service principals in your tenancy. We recommend **against** using `any-user`; use `any-group` or scope by principal type via a condition (e.g. `{request.principal.type='disworkspace'}`).

**Examples:**

- Single group by name:
  ```
  Allow group A-Admins to manage all-resources in compartment Project-A
  ```

- Multiple groups by name (space after the comma optional):
  ```
  Allow group A-Admins, B-Admins to manage all-resources in compartment Projects-A-and-B
  ```

- Single group by OCID (shortened):
  ```
  Allow group id ocid1.group.oc1..aaaaaaaaqjihfhvxmum...awuc7i5xwe6s7qmnsbc6a to manage all-resources in compartment Project-A
  ```

- Multiple groups by OCID:
  ```
  Allow group id ocid1.group.oc1..aaaaaaaaqjihfhvxmumrl...wuc7i5xwe6s7qmnsbc6a,
   id ocid1.group.oc1..aaaaaaaavhea5mellwzb...66yfxvl462tdgx2oecyq to manage all-resources in compartment Projects-A-and-B
  ```

- Any group or instance principal in the tenancy (to let anyone inspect users):
  ```
  Allow any-group to inspect users in tenancy
  ```

## Verb

Specify a single verb: `inspect`, `read`, `use`, or `manage`.

```
Allow group A-Admins to manage all-resources in compartment Project-A
```

## Resource-Type

Specify a single resource-type:

- An **individual** resource-type (e.g. `vcns`, `subnets`, `instances`, `volumes`).
- A **family** resource-type (e.g. `virtual-network-family`, `instance-family`, `volume-family`).
- `all-resources` — covers all resources in the compartment (or tenancy).

**Syntax:** `<resource_type> | all-resources`

**Examples:**

- Single resource-type:
  ```
  Allow group HelpDesk to manage users in tenancy
  ```

- Multiple resource-types — use separate statements:
  ```
  Allow group A-Users to manage instance-family in compartment Project-A

  Allow group A-Users to manage volume-family in compartment Project-A
  ```

- All resources in the compartment (or tenancy):
  ```
  Allow group A-Admins to manage all-resources in compartment Project-A
  ```

## Location

Specify a single compartment (or compartment path) by name or OCID, or `tenancy` to cover the entire tenancy. Users, groups, and compartments themselves reside in the tenancy. Policies may be attached to the tenancy or to a child compartment.

**Note:** To scope access to a specific region or availability domain, use the `request.region` or `request.ad` variable in a condition.

The location is required. To attach a policy to a compartment, you must be in that compartment when you create the policy.

To specify a compartment that is not a direct child of the compartment you are attaching the policy to, specify the path to the compartment, using the colon (`:`) as a separator.

**Syntax:** `tenancy | compartment <compartment_name> | compartment id <compartment_ocid>`

**Examples:**

- Compartment by name:
  ```
  Allow group A-Admins to manage all-resources in compartment Project-A
  ```

- Compartment by OCID:
  ```
  Allow group id ocid1.group.oc1..aaaaaaaaexampleocid to manage all-resources in compartment id ocid1.compartment.oc1..aaaaaaaaexampleocid
  ```

- Multiple compartments — use separate statements:
  ```
  Allow group InstanceAdmins to manage instance-family in compartment Project-A

  Allow group InstanceAdmins to manage instance-family in compartment Project-B
  ```

- A compartment that is not a direct child of the compartment where the policy is attached (specify the path):
  ```
  Allow group InstanceAdmins to manage instance-family in compartment Project-A:Project-A2
  ```

## Conditions

Specify one or more conditions. Use `any` or `all` with multiple conditions for logical OR / AND.

**Syntax for a single condition:** `variable =|!= value`

**Syntax for multiple conditions:** `any|all {<condition>,<condition>,...}`

Additional operators can be used with time-based variables.

**Important:** Condition matching is **case insensitive**. A condition `target.bucket.name='BucketA'` matches both `BucketA` and `bucketA`.

| Type | Examples |
|------|----------|
| String | `'johnsmith@example.com'`, `'ocid1.compartment.oc1..aaaaaaaaph...ctehnqg756a'` (single quotation marks required) |
| Pattern | `/HR*/` (starts with "HR"), `/*HR/` (ends with "HR"), `/*HR*/` (contains "HR") |

**Examples:**

> **Note:** The statements that specify the condition do not, by themselves, let GroupAdmins actually list all the users and groups. Statements including the `inspect` verb are added for completeness.

- Single condition — create/update/delete only groups whose names start with "A-Users-":
  ```
  Allow group GroupAdmins to manage groups in tenancy where target.group.name = /A-Users-*/
  Allow group GroupAdmins to inspect groups in tenancy
  ```

- Manage cloud networks in any compartment except the one specified:
  ```
  Allow group NetworkAdmins to manage virtual-network-family in tenancy where target.compartment.id != 'ocid1.compartment.oc1..aaaaaaaaexampleocid'
  ```

- Multiple conditions — create/update/delete only groups whose names start with "A-", except the A-Admins group itself:
  ```
  Allow group GroupAdmins to manage groups in tenancy where all {target.group.name=/A-*/,target.group.name!='A-Admins'}

  Allow group GroupAdmins to inspect groups in tenancy
  ```

## Three to Five Full-Sentence Example Policy Statements

1. `Allow group A-Admins to manage all-resources in compartment Project-A`
2. `Allow group HelpDesk to manage users in tenancy`
3. `Allow group NetworkAdmins to manage virtual-network-family in tenancy where target.compartment.id != 'ocid1.compartment.oc1..aaaaaaaaexampleocid'`
4. `Allow dynamic-group BackupRunners to use volume-family in compartment Backups where request.operation='CreateVolumeBackup'`
5. `Allow group Contractors to manage instance-family in tenancy where request.utc-timestamp before '2026-12-31T00:00Z'`
