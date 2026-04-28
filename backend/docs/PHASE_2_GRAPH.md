# Phase 2: Resource Graph

## Overview

Phase 2 replaces the implicit string-based contract between skills and
downstream code with an explicit, validated graph. Every OCI resource becomes
a typed `ResourceNode`; every cross-resource reference becomes a `ResourceRef`
edge. Downstream consumers (synthesis_composer, bundle_builder) read the graph
instead of parsing raw HCL strings.

Source: `backend/app/services/resource_graph.py`

---

## 1. Data Model

### ResourceNode

A single OCI resource in the migration graph.

| Field           | Type                  | Description |
|-----------------|-----------------------|-------------|
| `template`      | `str`                 | Jinja2 template name (e.g. `core/vcn`, `load_balancer/listener`). |
| `label`         | `str`                 | Terraform resource label. Must be unique within its template type. |
| `params`        | `dict[str, Any]`      | Template parameters, validated against the template's Pydantic schema at render time. |
| `source_skill`  | `str`                 | Which skill produced this node (e.g. `network_translation`). |
| `aws_source_id` | `str | None`          | AWS resource ID that this node was translated from. |
| `domain`        | `Literal[...]`        | Determines output file routing: `network`, `compute`, `storage`, `database`, `loadbalancer`, `iam`, `security`, `serverless`, `observability`, `ocm`, `cfn`. |

Validators enforce that `template` and `label` are non-empty strings.

### ResourceRef

A directed edge: one node's parameter references another node's attribute.

| Field            | Type   | Description |
|------------------|--------|-------------|
| `src_node_id`    | `str`  | SHA-256 hash (first 16 hex chars) of `template::label` for the source node. |
| `src_param_path` | `str`  | Dotted path inside `params` (e.g. `create_vnic_details.subnet_id`). |
| `dst_node_id`    | `str`  | Hash of `template::label` for the target node. |
| `dst_attr`       | `str`  | Target attribute; defaults to `id`. Can be `ip_address`, `name`, etc. |

### ResourceGraph

Container that owns all nodes and edges.

| Member             | Type                        | Description |
|--------------------|-----------------------------|-------------|
| `nodes`            | `dict[str, ResourceNode]`   | Keyed by deterministic `node_id`. |
| `refs`             | `list[ResourceRef]`         | All cross-resource reference edges. |
| `free_form_files`  | `dict[str, str]`            | HCL from non-Phase-1 skills, keyed by `skill/filename`. |

Key methods:

- `add_node(node)` -- inserts a node; raises `ValueError` on duplicate `(template, label)`.
- `add_ref(src_node_id, src_param_path, dst_node_id, dst_attr)` -- creates an edge.
- `find_by_aws_id(aws_id)` -- lookup a node by its AWS source resource ID.
- `find_by_template(template)` -- return all nodes using a given template.
- `node_id_for(template, label)` -- return the node_id or `None`.
- `validate()` -- run all validation rules (see Section 6).
- `render()` -- produce `{filename: HCL}` output (see Section 4).

Node IDs are computed as `sha256(f"{template}::{label}")[:16]`, making them
deterministic and collision-resistant.

---

## 2. Skill-to-Node Mapping

Each Phase 1 skill produces a list of template specs (`{template, label, params}`).
The helper function `specs_to_graph()` converts these into `ResourceNode` objects
and infers the `domain` from the template name prefix.

| Template prefix     | Domain           | Output file        |
|---------------------|------------------|--------------------|
| `core`              | `network`        | `network.tf`       |
| `load_balancer`     | `loadbalancer`   | `loadbalancer.tf`  |
| `cloud_migrations`  | `ocm`            | `ocm/main.tf`      |
| (other)             | `cfn`            | `main.tf`          |

### network_translation

Maps AWS VPC networking primitives to OCI core networking resources.

| AWS Resource                    | OCI Template                                      |
|---------------------------------|---------------------------------------------------|
| VPC                             | `core/vcn`                                        |
| Subnet                          | `core/subnet`                                     |
| InternetGateway                 | `core/internet_gateway`                           |
| NatGateway                      | `core/nat_gateway`                                |
| RouteTable                      | `core/route_table`                                |
| RouteTable association          | `core/route_table_attachment`                     |
| SecurityGroup (SL mode)         | `core/security_list`                              |
| SecurityGroup (NSG mode)        | `core/network_security_group` + `core/network_security_group_security_rule` |
| EIP                             | `core/public_ip`                                  |

All nodes land in the `network` domain and render into `network.tf`.

### ocm_handoff_translation

Maps EC2 instances to OCI Cloud Migrations (OCM) resources for lift-and-shift.

| AWS Resource   | OCI Template                            |
|----------------|-----------------------------------------|
| EC2 Instance   | `cloud_migrations/migration`            |
|                | `cloud_migrations/migration_plan`       |
|                | `cloud_migrations/target_asset`         |
|                | `cloud_migrations/replication_schedule` |

A single EC2 instance fans out to four OCM resources. All land in the `ocm`
domain and render into `ocm/main.tf`.

### loadbalancer_translation

Maps AWS ALB/NLB resources to OCI Load Balancer resources.

| AWS Resource                          | OCI Template                          |
|---------------------------------------|---------------------------------------|
| ALB (Application Load Balancer)       | `load_balancer/load_balancer`         |
| NLB (Network Load Balancer)           | `free_form_hcl` (different OCI provider family) |
| TargetGroup                           | `load_balancer/backend_set`           |
| Listener                              | `load_balancer/listener`              |
| Certificate                           | `load_balancer/certificate`           |
| Hostname                              | `load_balancer/hostname`              |
| ListenerRule (path-based)             | `load_balancer/path_route_set`        |
| ListenerRule (header/method-based)    | `load_balancer/rule_set`              |

All typed nodes land in the `loadbalancer` domain and render into `loadbalancer.tf`.

---

## 3. Node ID Computation

Every node receives a deterministic ID derived from its `(template, label)` pair:

```python
node_id = sha256(f"{template}::{label}".encode()).hexdigest()[:16]
```

This ID is used as the key in `graph.nodes` and as the source/destination in
`ResourceRef` edges. The first 16 hex characters of a SHA-256 hash provide
sufficient collision resistance for migration-scale graphs (hundreds to low
thousands of resources).

---

## 4. Rendering Pipeline

`graph.render()` transforms the graph into a `dict[str, str]` mapping filenames
to HCL content.

### Steps

1. **Build ref lookup table.** For each `ResourceRef`, resolve the destination
   node's template to an OCI Terraform resource type using the
   `_TEMPLATE_TO_TF_TYPE` mapping (e.g. `core/vcn` -> `oci_core_vcn`), then
   construct the Terraform expression: `oci_core_vcn.main.id`.

2. **Inject refs into params.** Walk each node's `params` dict recursively.
   When a `(node_id, dotted_path)` key matches a ref, replace the parameter
   value with the Terraform expression string. The `_inject_refs()` helper
   handles nested dicts (e.g. `create_vnic_details.subnet_id`).

3. **Group nodes by domain.** Build a list of `{template, label, params}` spec
   dicts per domain.

4. **Render via template_renderer.** Call `render_specs(all_specs)` which
   validates each spec against its Pydantic schema and renders the Jinja2
   template. Output is grouped by domain into filenames (`network.tf`,
   `loadbalancer.tf`, `ocm/main.tf`, etc.).

5. **Merge free-form files.** Append `free_form_files` entries to the rendered
   output. If a free-form file targets the same filename as a graph-rendered
   file, the content is appended.

### Template-to-Terraform-Type Mapping

The `_TEMPLATE_TO_TF_TYPE` dict maps every known template to its
`oci_*` Terraform resource type. This mapping is authoritative for generating
cross-reference expressions. Examples:

```
core/vcn                                -> oci_core_vcn
core/subnet                             -> oci_core_subnet
load_balancer/load_balancer             -> oci_load_balancer_load_balancer
cloud_migrations/migration_plan         -> oci_cloud_migrations_migration_plan
```

---

## 5. Cross-References

Cross-references between resources are modeled as `ResourceRef` edges rather
than embedded strings. This ensures references are validated before rendering
and can be updated if a node is renamed or removed.

### Creating a Reference

```python
vcn_id = graph.add_node(ResourceNode(
    template="core/vcn", label="main", params={...},
    source_skill="network_translation", domain="network",
))
subnet_id = graph.add_node(ResourceNode(
    template="core/subnet", label="web", params={"vcn_id": "PLACEHOLDER", ...},
    source_skill="network_translation", domain="network",
))
graph.add_ref(
    src_node_id=subnet_id,
    src_param_path="vcn_id",
    dst_node_id=vcn_id,
    dst_attr="id",
)
```

### Rendered Output

At render time, the placeholder value in `params["vcn_id"]` is replaced with:

```hcl
oci_core_vcn.main.id
```

For nested params (e.g. `create_vnic_details.subnet_id`), the `src_param_path`
uses dot notation and `_inject_refs` walks the dict tree to find and replace
the correct value.

---

## 6. Validation Rules

`graph.validate()` returns a list of error strings. An empty list means the
graph is valid.

### Rule 1: Dangling References

Every `ResourceRef` must point to nodes that exist in the graph. Both
`src_node_id` and `dst_node_id` are checked. A missing node produces an error
like:

```
Ref dst_node_id 'a1b2c3d4e5f67890' not found in graph
```

### Rule 2: Duplicate Detection

No two nodes may share the same `(template, label)` pair. This is enforced at
insertion time by `add_node()` (raises `ValueError`), and double-checked by
`validate()` as a belt-and-suspenders guard against direct dict manipulation.

### Rule 3: Cycle Detection

Uses NetworkX `simple_cycles()` on a directed graph built from all refs. If a
cycle is found, the error includes the human-readable path:

```
Cycle detected: core/subnet/web -> core/route_table/rt1 -> core/subnet/web
```

Cycles would cause Terraform to reject the plan, so they are flagged as
validation errors and surfaced as HIGH severity gaps.

---

## 7. Free-Form File Bridge

Skills that have not yet been migrated to the Phase 1 template system produce
raw HCL strings. These are routed into `graph.free_form_files` keyed by
`skill_name/filename.tf`.

In `plan_orchestrator`, the routing logic is:

1. Iterate over `completed_artifacts`.
2. Skip artifacts from Phase 1 skills (already in the graph as typed nodes).
3. For remaining `.tf` artifacts, store in `graph.free_form_files`.

At render time, free-form content merges with graph-rendered content:
- If the filename already exists (from graph nodes), the free-form HCL is
  appended.
- Otherwise a new file entry is created.

In `synthesis_composer.compose_from_graph()`, free-form files are additionally
parsed through the legacy string-based HCL merge path for variable/output
deduplication.

---

## 8. Integration Points

### plan_orchestrator (producer)

The orchestrator builds the graph in Step 5b:

1. Import `ResourceGraph`, `ResourceNode`, `specs_to_graph`.
2. Instantiate `ResourceGraph()`.
3. For each Phase 1 skill (`network_translation`, `ocm_handoff_translation`,
   `loadbalancer_translation`), call `specs_to_graph(specs, skill_name)` to
   convert the skill's structured output into `ResourceNode` objects.
4. Call `graph.add_node()` for each node (duplicates logged and skipped).
5. Route non-Phase-1 skill `.tf` artifacts to `graph.free_form_files`.
6. Run `graph.validate()`. Errors become HIGH severity entries in `all_gaps`.
7. Pass the graph to synthesis.

### synthesis_composer (consumer)

`compose_from_graph(graph, migration_name)` is the graph-aware entry point:

1. Call `graph.render()` to get `{filename: HCL}`.
2. Store each rendered file in the `SynthesisResult`.
3. Parse `graph.free_form_files` through the legacy string-based merge path
   for variable/output deduplication and providers.tf generation.
4. Return the merged result.

The graph path is chosen over the legacy `compose_terraform()` path when
`graph.nodes` is non-empty.

### bundle_builder (downstream consumer)

bundle_builder receives the final `completed_artifacts` dict, which includes
synthesis output derived from the graph. It does not directly import the graph
module, but its behavior is shaped by graph outputs:

- Graph validation errors are aggregated into `all_gaps` and rendered into
  `reports/gaps.md` by bundle_builder.
- The domain-based file routing (`network.tf`, `loadbalancer.tf`, `ocm/main.tf`)
  is determined by the graph's domain mapping, ensuring consistent file layout
  in the output bundle.

---

## 9. Adding a New Skill to the Graph

To migrate a new skill from free-form HCL to the typed graph:

1. Create Jinja2 templates under `backend/app/templates/oci/<service>/`.
2. Create Pydantic schemas for each template's params.
3. Add entries to `_TEMPLATE_TO_TF_TYPE` in `resource_graph.py`.
4. Add the template prefix to `_TEMPLATE_PREFIX_TO_DOMAIN` in `specs_to_graph()`.
5. Update the domain routing in `_DOMAIN_TO_FILE` if a new output file is needed.
6. In `plan_orchestrator`, add the skill name to the Phase 1 skill list so its
   specs are routed through `specs_to_graph()` instead of `free_form_files`.
7. Add cross-skill `ResourceRef` edges where the new resources reference
   existing graph nodes (e.g. a compute instance referencing a subnet).
