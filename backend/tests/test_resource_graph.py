"""Tests for the ResourceGraph core module: nodes, edges, validation, conversion."""

import hashlib

import pytest
from pydantic import ValidationError

from app.services.resource_graph import (
    GraphValidationError,
    ResourceGraph,
    ResourceNode,
    ResourceRef,
    _node_id,
    specs_to_graph,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_node(
    template: str = "core/vcn",
    label: str = "main",
    domain: str = "network",
    source_skill: str = "network_translation",
    **extra_params,
) -> ResourceNode:
    """Convenience factory for a ResourceNode with sensible defaults."""
    params = {"compartment_id": "var.compartment_id", **extra_params}
    return ResourceNode(
        template=template,
        label=label,
        params=params,
        source_skill=source_skill,
        domain=domain,
    )


# ── ResourceNode validation ───────────────────────────────────────────────

class TestResourceNodeValidation:
    """Pydantic field validators on ResourceNode."""

    def test_valid_construction(self):
        node = _make_node()
        assert node.template == "core/vcn"
        assert node.label == "main"
        assert node.domain == "network"

    def test_empty_label_rejected(self):
        with pytest.raises(ValidationError, match="label must not be empty"):
            _make_node(label="")

    def test_whitespace_only_label_rejected(self):
        with pytest.raises(ValidationError, match="label must not be empty"):
            _make_node(label="   ")

    def test_empty_template_rejected(self):
        with pytest.raises(ValidationError, match="template must not be empty"):
            _make_node(template="")

    def test_whitespace_only_template_rejected(self):
        with pytest.raises(ValidationError, match="template must not be empty"):
            _make_node(template="  ")

    def test_aws_source_id_optional(self):
        node = _make_node()
        assert node.aws_source_id is None

    def test_aws_source_id_set(self):
        node = ResourceNode(
            template="core/vcn",
            label="main",
            params={"compartment_id": "var.compartment_id"},
            source_skill="network_translation",
            aws_source_id="vpc-abc123",
            domain="network",
        )
        assert node.aws_source_id == "vpc-abc123"


# ── add_node ──────────────────────────────────────────────────────────────

class TestAddNode:
    """ResourceGraph.add_node behavior."""

    def test_returns_deterministic_node_id(self):
        graph = ResourceGraph()
        nid = graph.add_node(_make_node(template="core/vcn", label="main"))
        expected = _node_id("core/vcn", "main")
        assert nid == expected

    def test_node_id_is_sha256_prefix(self):
        """node_id is the first 16 hex chars of sha256('template::label')."""
        raw = "core/vcn::main"
        expected = hashlib.sha256(raw.encode()).hexdigest()[:16]
        assert _node_id("core/vcn", "main") == expected

    def test_same_inputs_produce_same_id(self):
        assert _node_id("core/vcn", "main") == _node_id("core/vcn", "main")

    def test_different_inputs_produce_different_ids(self):
        assert _node_id("core/vcn", "a") != _node_id("core/vcn", "b")

    def test_rejects_duplicate_template_label(self):
        graph = ResourceGraph()
        graph.add_node(_make_node(template="core/vcn", label="main"))
        with pytest.raises(ValueError, match="Duplicate node"):
            graph.add_node(_make_node(template="core/vcn", label="main"))

    def test_allows_same_template_different_labels(self):
        graph = ResourceGraph()
        id_a = graph.add_node(_make_node(template="core/vcn", label="a"))
        id_b = graph.add_node(_make_node(template="core/vcn", label="b"))
        assert id_a != id_b
        assert len(graph.nodes) == 2

    def test_allows_same_label_different_templates(self):
        graph = ResourceGraph()
        graph.add_node(_make_node(template="core/vcn", label="main"))
        graph.add_node(_make_node(template="core/subnet", label="main"))
        assert len(graph.nodes) == 2


# ── add_ref ───────────────────────────────────────────────────────────────

class TestAddRef:
    """ResourceGraph.add_ref behavior."""

    def test_creates_resource_ref(self):
        graph = ResourceGraph()
        vcn_id = graph.add_node(_make_node(template="core/vcn", label="main"))
        sub_id = graph.add_node(_make_node(template="core/subnet", label="web"))
        ref = graph.add_ref(sub_id, "vcn_id", vcn_id)
        assert isinstance(ref, ResourceRef)
        assert ref.src_node_id == sub_id
        assert ref.dst_node_id == vcn_id
        assert ref.src_param_path == "vcn_id"
        assert ref.dst_attr == "id"

    def test_custom_dst_attr(self):
        graph = ResourceGraph()
        a_id = graph.add_node(_make_node(template="core/vcn", label="a"))
        b_id = graph.add_node(_make_node(template="core/subnet", label="b"))
        ref = graph.add_ref(b_id, "some_field", a_id, dst_attr="ip_address")
        assert ref.dst_attr == "ip_address"

    def test_ref_appended_to_refs_list(self):
        graph = ResourceGraph()
        a_id = graph.add_node(_make_node(template="core/vcn", label="a"))
        b_id = graph.add_node(_make_node(template="core/subnet", label="b"))
        graph.add_ref(b_id, "vcn_id", a_id)
        assert len(graph.refs) == 1


# ── find_by_aws_id ────────────────────────────────────────────────────────

class TestFindByAwsId:
    """ResourceGraph.find_by_aws_id behavior."""

    def test_returns_correct_node(self):
        graph = ResourceGraph()
        node = _make_node(template="core/vcn", label="main")
        node.aws_source_id = "vpc-12345"
        graph.add_node(node)
        found = graph.find_by_aws_id("vpc-12345")
        assert found is not None
        assert found.label == "main"
        assert found.aws_source_id == "vpc-12345"

    def test_returns_none_when_not_found(self):
        graph = ResourceGraph()
        graph.add_node(_make_node(template="core/vcn", label="main"))
        assert graph.find_by_aws_id("nonexistent") is None

    def test_returns_none_on_empty_graph(self):
        graph = ResourceGraph()
        assert graph.find_by_aws_id("vpc-1") is None


# ── find_by_template ──────────────────────────────────────────────────────

class TestFindByTemplate:
    """ResourceGraph.find_by_template behavior."""

    def test_returns_matching_nodes(self):
        graph = ResourceGraph()
        graph.add_node(_make_node(template="core/vcn", label="a"))
        graph.add_node(_make_node(template="core/vcn", label="b"))
        graph.add_node(_make_node(template="core/subnet", label="c"))
        results = graph.find_by_template("core/vcn")
        assert len(results) == 2
        labels = {n.label for n in results}
        assert labels == {"a", "b"}

    def test_returns_empty_for_no_match(self):
        graph = ResourceGraph()
        graph.add_node(_make_node(template="core/vcn", label="a"))
        assert graph.find_by_template("core/subnet") == []


# ── validate ──────────────────────────────────────────────────────────────

class TestValidate:
    """ResourceGraph.validate() error detection."""

    def test_valid_graph_returns_empty(self):
        graph = ResourceGraph()
        vcn_id = graph.add_node(_make_node(template="core/vcn", label="main"))
        sub_id = graph.add_node(_make_node(template="core/subnet", label="web"))
        graph.add_ref(sub_id, "vcn_id", vcn_id)
        errors = graph.validate()
        assert errors == []

    def test_empty_graph_is_valid(self):
        graph = ResourceGraph()
        assert graph.validate() == []

    def test_catches_ref_to_nonexistent_dst(self):
        graph = ResourceGraph()
        nid = graph.add_node(_make_node(template="core/vcn", label="main"))
        graph.add_ref(nid, "some_field", "nonexistent_node_id")
        errors = graph.validate()
        assert any("nonexistent_node_id" in e for e in errors)

    def test_catches_ref_from_nonexistent_src(self):
        graph = ResourceGraph()
        nid = graph.add_node(_make_node(template="core/vcn", label="main"))
        graph.add_ref("ghost_src", "some_field", nid)
        errors = graph.validate()
        assert any("ghost_src" in e for e in errors)

    def test_catches_duplicate_template_label_if_injected(self):
        """Manually injecting a duplicate (template, label) bypasses add_node
        but validate() still catches it."""
        graph = ResourceGraph()
        node_a = _make_node(template="core/vcn", label="main")
        graph.add_node(node_a)
        # Manually inject a duplicate under a different key
        node_b = _make_node(template="core/vcn", label="main")
        graph.nodes["fake_id_999"] = node_b
        errors = graph.validate()
        assert any("Duplicate" in e for e in errors)

    def test_catches_cycle_3_node_ring(self):
        """A -> B -> C -> A is a cycle and must be detected."""
        graph = ResourceGraph()
        a_id = graph.add_node(_make_node(template="core/vcn", label="a"))
        b_id = graph.add_node(_make_node(template="core/vcn", label="b"))
        c_id = graph.add_node(_make_node(template="core/vcn", label="c"))
        graph.add_ref(a_id, "ref_b", b_id)
        graph.add_ref(b_id, "ref_c", c_id)
        graph.add_ref(c_id, "ref_a", a_id)
        errors = graph.validate()
        assert any("Cycle" in e for e in errors)

    def test_catches_self_loop(self):
        """A node referencing itself is a degenerate cycle."""
        graph = ResourceGraph()
        nid = graph.add_node(_make_node(template="core/vcn", label="self_ref"))
        graph.add_ref(nid, "some_field", nid)
        errors = graph.validate()
        assert any("Cycle" in e for e in errors)

    def test_acyclic_graph_no_cycle_error(self):
        """A chain A -> B -> C (no back-edge) is valid."""
        graph = ResourceGraph()
        a_id = graph.add_node(_make_node(template="core/vcn", label="a"))
        b_id = graph.add_node(_make_node(template="core/vcn", label="b"))
        c_id = graph.add_node(_make_node(template="core/vcn", label="c"))
        graph.add_ref(a_id, "ref_b", b_id)
        graph.add_ref(b_id, "ref_c", c_id)
        errors = graph.validate()
        assert errors == []


# ── specs_to_graph ────────────────────────────────────────────────────────

class TestSpecsToGraph:
    """specs_to_graph conversion from Phase 1 spec list."""

    def test_converts_core_specs_to_network_domain(self):
        specs = [
            {"template": "core/vcn", "label": "main", "params": {"compartment_id": "x"}},
            {"template": "core/subnet", "label": "web", "params": {"compartment_id": "x"}},
        ]
        nodes, node_ids = specs_to_graph(specs, source_skill="network_translation")
        assert len(nodes) == 2
        assert len(node_ids) == 2
        assert all(n.domain == "network" for n in nodes)
        assert all(n.source_skill == "network_translation" for n in nodes)

    def test_converts_lb_specs_to_loadbalancer_domain(self):
        specs = [
            {"template": "load_balancer/load_balancer", "label": "lb", "params": {}},
        ]
        nodes, _ = specs_to_graph(specs, source_skill="lb_translation")
        assert nodes[0].domain == "loadbalancer"

    def test_converts_ocm_specs_to_ocm_domain(self):
        specs = [
            {"template": "cloud_migrations/migration", "label": "m", "params": {}},
        ]
        nodes, _ = specs_to_graph(specs, source_skill="ocm")
        assert nodes[0].domain == "ocm"

    def test_unknown_prefix_gets_cfn_domain(self):
        specs = [
            {"template": "exotic/widget", "label": "w", "params": {}},
        ]
        nodes, _ = specs_to_graph(specs, source_skill="cfn")
        assert nodes[0].domain == "cfn"

    def test_skips_free_form_hcl(self):
        specs = [
            {"template": "free_form_hcl", "label": "custom", "params": {"hcl": "resource ..."}},
            {"template": "core/vcn", "label": "main", "params": {"compartment_id": "x"}},
        ]
        nodes, node_ids = specs_to_graph(specs, source_skill="test")
        assert len(nodes) == 1
        assert nodes[0].template == "core/vcn"

    def test_preserves_aws_source_id_from_params(self):
        specs = [
            {
                "template": "core/vcn",
                "label": "main",
                "params": {"compartment_id": "x", "aws_source_id": "vpc-999"},
            },
        ]
        nodes, _ = specs_to_graph(specs, source_skill="net")
        assert nodes[0].aws_source_id == "vpc-999"

    def test_empty_specs_list(self):
        nodes, node_ids = specs_to_graph([], source_skill="test")
        assert nodes == []
        assert node_ids == []

    def test_node_ids_match_node_id_function(self):
        specs = [
            {"template": "core/vcn", "label": "main", "params": {}},
        ]
        nodes, node_ids = specs_to_graph(specs, source_skill="test")
        expected_id = _node_id("core/vcn", "main")
        assert node_ids[0] == expected_id


# ── node_id_for ───────────────────────────────────────────────────────────

class TestNodeIdFor:
    """ResourceGraph.node_id_for lookup."""

    def test_returns_id_for_existing_node(self):
        graph = ResourceGraph()
        expected = graph.add_node(_make_node(template="core/vcn", label="main"))
        result = graph.node_id_for("core/vcn", "main")
        assert result == expected

    def test_returns_none_for_missing_node(self):
        graph = ResourceGraph()
        assert graph.node_id_for("core/vcn", "nonexistent") is None
