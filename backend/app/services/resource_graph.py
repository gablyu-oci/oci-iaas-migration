"""Resource graph — typed nodes + explicit edges for every OCI resource.

Phase 2 replaces the implicit string-based contract between skills and
downstream code (synthesis_composer, bundle_builder) with an explicit,
validated graph.  Every OCI resource becomes a typed ``ResourceNode``;
every cross-resource reference becomes a ``ResourceRef`` edge.

Composer and bundle_builder consume the graph — never raw strings.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Literal

import networkx as nx
from pydantic import BaseModel, field_validator

_log = logging.getLogger(__name__)


# ── Node + Edge models ─────────────────────────────────────────────────────

class ResourceNode(BaseModel):
    """One OCI resource in the migration graph."""
    template: str                     # Jinja2 template name (e.g. 'core/vcn')
    label: str                        # terraform resource label (must be unique within type)
    params: dict[str, Any]            # validated against template's Pydantic schema
    source_skill: str                 # which skill produced this
    aws_source_id: str | None = None  # AWS source resource id when applicable
    domain: Literal[
        'network', 'compute', 'storage', 'database', 'loadbalancer',
        'iam', 'security', 'serverless', 'observability',
        'ocm', 'cfn',
    ]                                 # which output file it lands in

    @field_validator('label')
    @classmethod
    def _label_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('label must not be empty')
        return v

    @field_validator('template')
    @classmethod
    def _template_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('template must not be empty')
        return v


class ResourceRef(BaseModel):
    """An edge: this node's params[field] references another node's attribute."""
    src_node_id: str       # hash of (template, label) for source
    src_param_path: str    # dotted path inside params (e.g. 'create_vnic_details.subnet_id')
    dst_node_id: str       # hash of (template, label) for target
    dst_attr: str = 'id'   # 'id' default; can be 'ip_address', 'name', etc.


# ── Template → OCI resource type mapping ──────────────────────────────────
# Used by render() to produce terraform expressions like
# oci_core_vcn.main.id

_TEMPLATE_TO_TF_TYPE: dict[str, str] = {
    'core/vcn': 'oci_core_vcn',
    'core/subnet': 'oci_core_subnet',
    'core/internet_gateway': 'oci_core_internet_gateway',
    'core/nat_gateway': 'oci_core_nat_gateway',
    'core/route_table': 'oci_core_route_table',
    'core/route_table_attachment': 'oci_core_route_table_attachment',
    'core/security_list': 'oci_core_security_list',
    'core/security_list_attachment': 'oci_core_security_list_attachment',
    'core/network_security_group': 'oci_core_network_security_group',
    'core/network_security_group_security_rule': 'oci_core_network_security_group_security_rule',
    'core/public_ip': 'oci_core_public_ip',
    'load_balancer/load_balancer': 'oci_load_balancer_load_balancer',
    'load_balancer/backend_set': 'oci_load_balancer_backend_set',
    'load_balancer/listener': 'oci_load_balancer_listener',
    'load_balancer/certificate': 'oci_load_balancer_certificate',
    'load_balancer/hostname': 'oci_load_balancer_hostname',
    'load_balancer/path_route_set': 'oci_load_balancer_path_route_set',
    'load_balancer/rule_set': 'oci_load_balancer_rule_set',
    'cloud_migrations/migration': 'oci_cloud_migrations_migration',
    'cloud_migrations/migration_plan': 'oci_cloud_migrations_migration_plan',
    'cloud_migrations/target_asset': 'oci_cloud_migrations_target_asset',
    'cloud_migrations/replication_schedule': 'oci_cloud_migrations_replication_schedule',
}

# Domain → output filename
_DOMAIN_TO_FILE: dict[str, str] = {
    'network': 'network.tf',
    'compute': 'compute.tf',
    'storage': 'storage.tf',
    'database': 'database.tf',
    'loadbalancer': 'loadbalancer.tf',
    'iam': 'iam.tf',
    'security': 'security.tf',
    'serverless': 'serverless.tf',
    'observability': 'observability.tf',
    'ocm': 'ocm/main.tf',
    'cfn': 'main.tf',
}


def _node_id(template: str, label: str) -> str:
    """Deterministic node ID from (template, label)."""
    raw = f"{template}::{label}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── The Graph ──────────────────────────────────────────────────────────────

class GraphValidationError(Exception):
    """Raised when graph.validate() finds problems."""
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"{len(errors)} validation error(s): {'; '.join(errors[:5])}")


class ResourceGraph:
    """Central data structure for Phase 2: typed nodes + explicit edges."""

    def __init__(self) -> None:
        self.nodes: dict[str, ResourceNode] = {}       # keyed by node_id
        self.refs: list[ResourceRef] = []
        self.free_form_files: dict[str, str] = {}      # for skills not yet migrated

    def add_node(self, node: ResourceNode) -> str:
        """Insert a node. Returns its deterministic node_id.

        Raises ValueError if a node with the same (template, label) already exists.
        """
        nid = _node_id(node.template, node.label)
        if nid in self.nodes:
            existing = self.nodes[nid]
            raise ValueError(
                f"Duplicate node: ({node.template}, {node.label}) already exists "
                f"from skill '{existing.source_skill}'"
            )
        self.nodes[nid] = node
        return nid

    def add_ref(
        self,
        src_node_id: str,
        src_param_path: str,
        dst_node_id: str,
        dst_attr: str = 'id',
    ) -> ResourceRef:
        """Add an edge between two nodes. Returns the created ResourceRef."""
        ref = ResourceRef(
            src_node_id=src_node_id,
            src_param_path=src_param_path,
            dst_node_id=dst_node_id,
            dst_attr=dst_attr,
        )
        self.refs.append(ref)
        return ref

    def find_by_aws_id(self, aws_id: str) -> ResourceNode | None:
        """Find a node by its AWS source resource ID."""
        for node in self.nodes.values():
            if node.aws_source_id == aws_id:
                return node
        return None

    def find_by_template(self, template: str) -> list[ResourceNode]:
        """Find all nodes using a given template name."""
        return [n for n in self.nodes.values() if n.template == template]

    def node_id_for(self, template: str, label: str) -> str | None:
        """Look up the node_id for a (template, label) pair, or None."""
        nid = _node_id(template, label)
        return nid if nid in self.nodes else None

    def validate(self) -> list[str]:
        """Validate the graph. Returns a list of error strings (empty = valid).

        Checks:
        1. Refs point to existing nodes (both src and dst).
        2. No duplicate (template, label) pairs (enforced by add_node, but double-check).
        3. No cycles in the reference graph.
        """
        errors: list[str] = []

        # 1. Check refs resolve
        for ref in self.refs:
            if ref.src_node_id not in self.nodes:
                errors.append(
                    f"Ref src_node_id '{ref.src_node_id}' not found in graph"
                )
            if ref.dst_node_id not in self.nodes:
                errors.append(
                    f"Ref dst_node_id '{ref.dst_node_id}' not found in graph"
                )

        # 2. Check for duplicate (template, label) — should not happen if
        #    add_node is the only insertion path, but belt-and-suspenders.
        seen: dict[tuple[str, str], str] = {}
        for nid, node in self.nodes.items():
            key = (node.template, node.label)
            if key in seen:
                errors.append(
                    f"Duplicate (template, label) = {key}: "
                    f"node_ids {seen[key]} and {nid}"
                )
            seen[key] = nid

        # 3. Cycle detection via NetworkX
        if self.refs:
            dg = nx.DiGraph()
            for ref in self.refs:
                dg.add_edge(ref.src_node_id, ref.dst_node_id)
            try:
                cycles = list(nx.simple_cycles(dg))
                for cycle in cycles:
                    labels = []
                    for nid in cycle:
                        n = self.nodes.get(nid)
                        labels.append(f"{n.template}/{n.label}" if n else nid)
                    errors.append(f"Cycle detected: {' -> '.join(labels)}")
            except Exception as exc:
                errors.append(f"Cycle detection failed: {exc}")

        return errors

    def render(self) -> dict[str, str]:
        """Render the graph into {filename: HCL content}.

        - Each node is rendered via its Jinja2 template (Phase 1 templates).
        - Cross-refs in params are resolved to terraform expression syntax
          (e.g. oci_core_vcn.main.id).
        - Free-form files pass through unchanged.
        """
        from app.services.template_renderer import render_specs

        # Build a ref lookup: (src_node_id, param_path) -> terraform expression
        ref_expressions: dict[tuple[str, str], str] = {}
        for ref in self.refs:
            dst_node = self.nodes.get(ref.dst_node_id)
            if dst_node:
                tf_type = _TEMPLATE_TO_TF_TYPE.get(dst_node.template, dst_node.template)
                expr = f"{tf_type}.{dst_node.label}.{ref.dst_attr}"
                ref_expressions[(ref.src_node_id, ref.src_param_path)] = expr

        # Group nodes by domain -> filename
        domain_specs: dict[str, list[dict]] = {}  # domain -> list of spec dicts
        for nid, node in self.nodes.items():
            # Deep copy params and inject ref expressions
            params = _inject_refs(nid, node.params, ref_expressions)
            spec = {
                'template': node.template,
                'label': node.label,
                'params': params,
            }
            domain_specs.setdefault(node.domain, []).append(spec)

        # Render each domain's specs via the template renderer
        result: dict[str, str] = {}
        all_specs: list[dict] = []
        for domain, specs in domain_specs.items():
            all_specs.extend(specs)

        if all_specs:
            rendered = render_specs(all_specs)
            result.update(rendered)

        # Merge in free-form files
        for path, content in self.free_form_files.items():
            if path in result:
                # Append free-form content to existing file
                result[path] += "\n" + content
            else:
                result[path] = content

        return result


def _inject_refs(
    node_id: str,
    params: dict[str, Any],
    ref_expressions: dict[tuple[str, str], str],
    prefix: str = '',
) -> dict[str, Any]:
    """Recursively walk params and replace values that have a matching ref."""
    result = {}
    for key, value in params.items():
        path = f"{prefix}.{key}" if prefix else key
        lookup = (node_id, path)
        if lookup in ref_expressions:
            result[key] = ref_expressions[lookup]
        elif isinstance(value, dict):
            result[key] = _inject_refs(node_id, value, ref_expressions, path)
        else:
            result[key] = value
    return result


def specs_to_graph(
    specs: list[dict[str, Any]],
    source_skill: str,
) -> tuple[list[ResourceNode], list[str]]:
    """Convert a list of template specs (Phase 1 format) to ResourceNode list.

    Returns (nodes, node_ids) — caller adds them to the graph.
    Determines domain from the template name prefix.
    """
    _TEMPLATE_PREFIX_TO_DOMAIN: dict[str, str] = {
        'core': 'network',
        'load_balancer': 'loadbalancer',
        'cloud_migrations': 'ocm',
    }

    nodes: list[ResourceNode] = []
    node_ids: list[str] = []

    for spec in specs:
        template = spec.get('template', '')
        label = spec.get('label', '')
        params = spec.get('params', {})

        if template == 'free_form_hcl':
            # Free-form HCL can't become a typed node
            continue

        # Determine domain from template prefix
        prefix = template.split('/')[0] if '/' in template else template
        domain = _TEMPLATE_PREFIX_TO_DOMAIN.get(prefix, 'cfn')

        node = ResourceNode(
            template=template,
            label=label,
            params=params,
            source_skill=source_skill,
            aws_source_id=params.get('aws_source_id'),
            domain=domain,
        )
        nodes.append(node)
        node_ids.append(_node_id(template, label))

    return nodes, node_ids
