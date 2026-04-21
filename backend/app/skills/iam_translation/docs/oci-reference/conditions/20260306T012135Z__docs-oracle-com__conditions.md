# OCI Advanced Policy Features — Conditions & Condition Keys

Source: https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policyadvancedfeatures.htm
Captured: 2026-03-06

## Conditions

A policy statement can include one or more _conditions_ that must be met for access to be granted.

Each condition consists of one or more predefined variables. When a request is evaluated, if all conditions in the policy evaluate _true_, the request is allowed; if any condition evaluates _false_ (or is not applicable), the request is not allowed.

Variables fall into two categories:

- **Request variables** — properties of the request itself. Prefixed with `request.` (e.g. `request.operation`, `request.region`, `request.permission`, `request.principal.type`, `request.networkSource.name`, `request.utc-timestamp`).
- **Target variables** — properties of the resource being acted on (the _target_). Prefixed with `target.` (e.g. `target.bucket.name`, `target.group.name`, `target.compartment.id`, `target.user.id`, `target.policy.id`, `target.tag-namespace.name`).

**Important:** Condition matching is **case insensitive**. This matters for resource types that allow case-sensitive names (e.g. Object Storage buckets `BucketA` and `bucketA` both match `target.bucket.name='BucketA'`).

### Variables That Aren't Applicable to a Request Result in a Declined Request

If a variable referenced in a condition is _not applicable_ to the incoming request, the condition evaluates to _false_ and the request is declined.

Example — these statements let someone add/remove users from any group except Administrators:

```
Allow group GroupAdmins to use users in tenancy
 where target.group.name != 'Administrators'

Allow group GroupAdmins to use groups in tenancy
 where target.group.name != 'Administrators'
```

Given the above, if GroupAdmins calls a general user API like `ListUsers` or `UpdateUser` (which doesn't reference a group), the request is declined. There is no `target.group.name` for those calls, so the condition fails.

To also grant general user API operations, add a separate statement _without_ the condition:

```
Allow group GroupAdmins to inspect users in tenancy
```

Or, to grant `UpdateUser` too (which also includes `ListUsers` because `use` covers `inspect`):

```
Allow group GroupAdmins to use users in tenancy
```

## Syntax

Single condition:

```
variable =|!= value
```

Multiple conditions — logical OR / AND with `any` / `all`:

```
any|all {<condition>, <condition>, ...}
```

Time-based variables support additional operators (`before`, `after`, `between`, `in`).

Value types:

| Type | Examples |
|------|----------|
| String | `'johnsmith@example.com'`, `'ocid1.compartment.oc1..aaaaaaaa...'` (single quotes required) |
| Pattern | `/HR*/`, `/*HR/`, `/*HR*/` |

## Tag-Based Access Control

Conditions plus a set of tag variables let you scope access by tags applied to a resource. Tags can exist on the requesting principal (group or dynamic-group) or on the target (resource or compartment). See "Using Tags to Manage Access" for details.

## Permissions

_Permissions_ are the atomic units of authorization. When a policy grants `<verb> <resource-type>`, the group is actually granted one or more predefined permissions. Verbs exist to simplify granting multiple related permissions.

### Relation to Verbs

Example — `inspect volumes` grants the `VOLUME_INSPECT` permission. Going from `inspect` → `read` → `use` → `manage`, permissions are cumulative.

| Inspect Volumes | Read Volumes | Use Volumes | Manage Volumes |
|---|---|---|---|
| VOLUME_INSPECT | VOLUME_INSPECT | VOLUME_INSPECT | VOLUME_INSPECT |
| | | VOLUME_UPDATE | VOLUME_UPDATE |
| | | VOLUME_WRITE | VOLUME_WRITE |
| | | | VOLUME_CREATE |
| | | | VOLUME_DELETE |

### Relation to API Operations

Each API operation requires one or more permissions.

- `ListVolumes` and `GetVolume` require `VOLUME_INSPECT`.
- Attaching a volume to an instance requires `VOLUME_WRITE`, `VOLUME_ATTACHMENT_CREATE`, `INSTANCE_ATTACH_VOLUME`.

### Understanding a User's Access

You can audit a user's effective access by enumerating groups, policies applicable to those groups, and the permissions those verbs grant. But conditions in the policy can further scope access, so the full picture requires reading the policy conditions as well.

## Scoping Access with `request.permission` or `request.operation`

Conditions combined with `request.permission` or `request.operation` can narrow the scope of a verb.

Example — allow XYZ to list, get, create, and update groups, but not delete them. `manage groups` normally covers `GROUP_INSPECT`, `GROUP_UPDATE`, `GROUP_CREATE`, `GROUP_DELETE`. Restrict via permissions:

```
Allow group XYZ to manage groups in tenancy
 where any {request.permission='GROUP_INSPECT',
            request.permission='GROUP_CREATE',
            request.permission='GROUP_UPDATE'}
```

Alternatively — allow all permissions except `GROUP_DELETE` (be aware: future new permissions would also be granted):

```
Allow group XYZ to manage groups in tenancy where request.permission != 'GROUP_DELETE'
```

Or — scope by specific API operation:

```
Allow group XYZ to manage groups in tenancy
 where any {request.operation='ListGroups',
            request.operation='GetGroup',
            request.operation='CreateGroup',
            request.operation='UpdateGroup'}
```

Permissions-based conditions are generally preferable to operation-based conditions, because if a new API operation is added that requires one of the named permissions, the existing policy will already cover it.

You can combine both — grant a permission, but only for a specific API operation:

```
Allow group XYZ to manage groups in tenancy
 where all {request.permission='GROUP_INSPECT',
            request.operation='ListGroups'}
```

## Scoping Policy by the IP Address of the Requestor

Scope access to a set of allowed IP addresses (or VCNs) using a **network source**:

1. Create a network source object listing the allowed IPs / VCNs.
2. Reference it in a condition with `request.networkSource.name`.

```
request.networkSource.name='<network_source_name>'
```

Example:

```
allow group GroupA to manage object-family in tenancy where request.networkSource.name='corpnet'
```

## Restricting Access to Resources Based on Time Frame

Use time-based variables to restrict when a grant applies.

| Variable | Purpose |
|---|---|
| `request.utc-timestamp` | The full timestamp when the request is authorized. Operators: `before`, `after`. |
| `request.utc-timestamp.month-of-year` | Numeric month (1–12). Operators: `=`, `!=`, `in`. |
| `request.utc-timestamp.day-of-month` | Numeric day (1–31). Operators: `=`, `!=`, `in`. |
| `request.utc-timestamp.day-of-week` | English day name. Operators: `=`, `!=`, `in`. |
| `request.utc-timestamp.time-of-day` | UTC time interval. Operator: `between`. |

### ISO 8601 Format

`YYYY-MM-DDThh:mm:ssZ` — examples:

- Date and time with seconds: `'2020-04-01T15:00:00Z'`
- Date and time with minutes: `'2020-04-01T05:00Z'`
- Date only: `'2020-04-01Z'`
- Time only: `'05:00:00'`

Allow for a ~5 minute clock skew between the request and evaluation.

All times are evaluated as UTC. Daylight savings changes require updating policies that reference a specific local hour.

### Examples

**`request.utc-timestamp`** — contractor access expires on a date:

```
Allow group Contractors to manage instance-family in tenancy where request.utc-timestamp before '2022-01-01T00:00Z'
```

**`request.utc-timestamp.month-of-year`** — summer interns only during June, July, and August:

```
Allow group SummerInterns to manage instance-family in tenancy where ANY {request.utc-timestamp.month-of-year in ('6', '7', '8')}
```

**`request.utc-timestamp.day-of-month`** — compliance auditors only on the first day of each month:

```
Allow group ComplianceAuditors to read all-resources in tenancy where request.utc-timestamp.day-of-month = '1'
```

**`request.utc-timestamp.day-of-week`** — work-week access:

```
Allow group WorkWeek to manage instance-family where ANY {request.utc-timestamp.day-of-week in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday')}
```

**`request.utc-timestamp.time-of-day`** — day-shift between 9 AM and 5 PM PST (converted to UTC):

```
Allow group DayShift to manage instance-family where request.utc-timestamp.time-of-day between '17:00:00Z' and '01:00:00Z'
```

Night-shift between 5 PM and 9 AM PST:

```
Allow group NightShift to manage instance-family where request.utc-timestamp.time-of-day between '01:00:00Z' and '17:00:00Z'
```

In each time-of-day example, the current UTC time is tested against the range (day-of-week is ignored).
