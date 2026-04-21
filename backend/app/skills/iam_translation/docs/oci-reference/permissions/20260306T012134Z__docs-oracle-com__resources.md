# OCI IAM Policy Reference — Resource-Types

Source: https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/policyreference.htm
Section: Resource-Types
Captured: 2026-03-06

## Resource-Types

Oracle defines two kinds of resource-types you can use in OCI policies:

- **Individual resource-types** — a single, specific resource (e.g. `vcns`, `subnets`, `instances`, `volumes`, `buckets`, `users`, `groups`, `dynamic-groups`, `policies`).
- **Aggregate (family) resource-types** — a bundle of related individual resource-types managed together (e.g. `virtual-network-family` covers `vcns`, `subnets`, `route-tables`, `security-lists`, `dhcp-options`, etc.).

A policy that uses `<verb> <family>` is equivalent to writing one statement with `<verb> <individual-resource-type>` for each individual resource-type in the family.

Special wildcard:

- `all-resources` — covers **every** Oracle Cloud Infrastructure resource-type in the compartment (or tenancy).

## Common Family Resource-Types

A few common family resource-types are listed below. For the individual resource-types that make up each family, follow the links.

* `all-resources` — All Oracle Cloud Infrastructure resource-types
* `cluster-family` — See Details for Kubernetes Engine
* `compute-management-family` — See Details for the Core Services
* `data-catalog-family` — See Data Catalog Policies
* `data-science-family` — See Data Science Policies
* `database-family` — See Details for the Database Service
* `datasafe-family-resources` — See OCI Resources for Oracle Data Safe
* `dns` — See Details for the DNS Service
* `email-family` — See Details for the Email Delivery Service
* `file-family` — See Details for the File Storage Service
* `instance-agent-command-family` — See Details for the Core Services
* `instance-agent-family` — See Details for the Core Services
* `instance-family` — See Details for the Core Services
* `object-family` — See Details for Object Storage and Archive Storage
* `optimizer-api-family` — See Creating Cloud Advisor Policies
* `appmgmt-family` — See Details for Stack Monitoring
* `stack-monitoring-family` — See Details for Stack Monitoring
* `virtual-network-family` — See Details for the Core Services
* `volume-family` — See Details for the Core Services

IAM has no family resource-type, only individual ones. See IAM Policies Overview or Details for IAM without Identity Domains, depending on whether your tenancy has identity domains or not.

## How Aggregates Map to Individual Resource-Types

### `virtual-network-family` (Core Services — Networking)

Individual resource-types included:

`vcns`, `subnets`, `route-tables`, `network-security-groups`, `security-lists`, `dhcp-options`, `private-ips`, `public-ips`, `ipv6s`, `internet-gateways`, `nat-gateways`, `service-gateways`, `local-peering-gateways` (includes `local-peering-from` and `local-peering-to`), `remote-peering-connections` (includes `remote-peering-from` and `remote-peering-to`), `drg-object`, `drg-attachments`, `drg-route-tables`, `drg-route-distributions`, `cpes`, `ipsec-connections`, `cross-connects`, `cross-connect-groups`, `virtual-circuits`, `vnics`, `vtaps`, `vnic-attachments`, `vlans`, `byoiprange`, `publicippool`, `ipam`.

A policy that uses `<verb> virtual-network-family` is equivalent to writing a separate `<verb> <individual resource-type>` statement for each of these.

### `instance-family` (Core Services — Compute)

Individual resource-types included:

`app-catalog-listing`, `console-histories`, `instances`, `instance-console-connection`, `instance-images`, `volume-attachments` (only the permissions required for attaching volumes to instances).

`instance-family` also includes **extra** permissions beyond the sum of its members so that a single statement covers common "instance with attached volume" use cases:

- For `inspect instance-family`: `VNIC_READ`, `VNIC_ATTACHMENT_READ`, `VOLUME_ATTACHMENT_INSPECT`
- For `read instance-family`: `VOLUME_ATTACHMENT_READ`
- For `use instance-family`: `VNIC_ATTACH`, `VNIC_DETACH`, `VOLUME_ATTACHMENT_UPDATE`
- For `manage instance-family`: `VOLUME_ATTACHMENT_CREATE`, `VOLUME_ATTACHMENT_DELETE`

### `compute-management-family` (Core Services — Compute management)

Individual resource-types included:

`instance-configurations`, `instance-pools`, `cluster-networks`.

### `instance-agent-family`

Individual resource-type included:

`instance-agent-plugins`.

### `instance-agent-command-family`

Individual resource-type included:

`instance-agent-commands`.

### `volume-family` (Core Services — Block Volume)

Individual resource-types included:

`volumes`, `volume-attachments`, `volume-backups`, `boot-volume-backups`, `backup-policies`, `backup-policy-assignments`, `volume-groups`, `volume-group-backups`.

### `object-family` (Object Storage & Archive Storage)

Individual resource-types included:

`objectstorage-namespaces`, `buckets`, `objects`.

A policy that uses `<verb> object-family` is equivalent to writing a separate `<verb> <individual resource-type>` statement for each of `objectstorage-namespaces`, `buckets`, and `objects`.

## Additional Core Individual Resource-Types Not in Any Family

Compute individual resource-types not included in any aggregate:

`auto-scaling-configurations`, `compute-bare-metal-hosts`, `compute-capacity-reports`, `compute-capacity-reservations`, `compute-clusters`, `compute-global-image-capability-schema`, `compute-gpu-memory-clusters`, `compute-gpu-memory-fabrics`, `compute-host-groups`, `compute-image-capability-schema`, `dedicated-vm-hosts`, `instance-agent-commands`, `work-requests`.

## Important Notes on Aggregate Behavior

- If a service introduces new individual resource-types, they are typically included automatically in the family for that service. Policies that grant access to the family pick up the new type without edits.
- If a service introduces **new permissions for an existing resource type**, you must update the policy statement for the existing resource type to make the new permissions take effect.
