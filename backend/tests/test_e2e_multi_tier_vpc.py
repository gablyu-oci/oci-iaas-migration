"""End-to-end regression test: multi-tier VPC fixture through the full pipeline.

Mocks only the LLM skill writers (replaces them with captured fixture outputs).
Validates:
  1. specs_to_graph produces the expected graph nodes
  2. Template renderer produces valid HCL
  3. synthesis_composer merges into expected bundle files
  4. providers.tf has pinned version constraints
"""
import json
import pytest
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "multi_tier_vpc"


def _load_fixture(name: str):
    with open(FIXTURE_DIR / name) as f:
        return json.load(f)


def _build_graph(skill_specs: dict):
    """Build a ResourceGraph from per-skill specs using specs_to_graph.

    specs_to_graph returns (nodes, node_ids) per skill call.  We add every
    node to a shared ResourceGraph so downstream tests can exercise
    compose_from_graph.
    """
    from app.services.resource_graph import ResourceGraph, specs_to_graph

    graph = ResourceGraph()
    for skill, specs in skill_specs.items():
        nodes, node_ids = specs_to_graph(specs, source_skill=skill)
        for node in nodes:
            graph.add_node(node)
    return graph


class TestMultiTierVpcE2E:
    """Full pipeline regression from captured fixtures."""

    @pytest.fixture(autouse=True)
    def load_fixtures(self):
        self.resource_mapping = _load_fixture("resource_mapping.json")
        self.skill_specs = _load_fixture("skill_specs.json")
        self.expected_graph_nodes = _load_fixture("expected_graph_nodes.json")
        self.expected_bundle_files = _load_fixture("expected_bundle_files.json")

    # ── 1. Graph construction ────────────────────────────────────────────

    def test_specs_to_graph_nodes(self):
        """All expected graph nodes are created from fixture specs."""
        graph = _build_graph(self.skill_specs)
        node_ids = sorted(graph.nodes.keys())
        expected_ids = sorted(self.expected_graph_nodes)
        assert node_ids == expected_ids, (
            f"Graph node mismatch.\nGot:      {node_ids}\nExpected: {expected_ids}"
        )

    def test_graph_validation_passes(self):
        """The fixture graph passes validation with no errors."""
        graph = _build_graph(self.skill_specs)
        errors = graph.validate()
        assert errors == [], f"Graph validation errors: {errors}"

    # ── 2. Template rendering ────────────────────────────────────────────

    def test_template_renderer_produces_hcl(self):
        """Template renderer produces non-empty HCL for each skill's specs."""
        from app.services.template_renderer import render_specs

        for skill, specs in self.skill_specs.items():
            rendered = render_specs(specs)
            assert rendered, f"No HCL rendered for {skill}"
            for fname, content in rendered.items():
                assert fname.endswith(".tf"), (
                    f"Unexpected file extension: {fname}"
                )
                assert (
                    "resource" in content
                    or "data" in content
                    or "module" in content
                ), f"No HCL blocks found in {fname} for {skill}"

    def test_network_hcl_contains_vcn_and_subnets(self):
        """Rendered network HCL contains VCN and both subnets."""
        from app.services.template_renderer import render_specs

        rendered = render_specs(self.skill_specs["network_translation"])
        hcl = rendered.get("network.tf", "")
        assert "oci_core_vcn" in hcl, "VCN resource missing from network.tf"
        assert "public-subnet" in hcl, "public subnet missing from network.tf"
        assert "private-subnet" in hcl, "private subnet missing from network.tf"

    def test_loadbalancer_hcl_contains_lb_resources(self):
        """Rendered loadbalancer HCL has the LB, backend set, and listener."""
        from app.services.template_renderer import render_specs

        rendered = render_specs(self.skill_specs["loadbalancer_translation"])
        hcl = rendered.get("loadbalancer.tf", "")
        assert "oci_load_balancer_load_balancer" in hcl, (
            "LB resource missing from loadbalancer.tf"
        )
        assert "bs-web" in hcl, "Backend set missing from loadbalancer.tf"
        assert "listener-http" in hcl, "Listener missing from loadbalancer.tf"

    # ── 3. Full composition via graph ────────────────────────────────────

    def test_compose_from_graph_produces_expected_files(self):
        """Composed output contains all expected bundle files."""
        from app.services.synthesis_composer import compose_from_graph

        graph = _build_graph(self.skill_specs)
        result = compose_from_graph(graph, migration_name="multi-tier-vpc")
        actual_files = sorted(result.files.keys())
        expected_files = sorted(self.expected_bundle_files)
        for ef in expected_files:
            assert ef in actual_files, f"Missing expected file: {ef}"

    def test_providers_tf_has_version_pin(self):
        """providers.tf has a lower version bound for the OCI provider."""
        from app.services.synthesis_composer import compose_from_graph

        graph = _build_graph(self.skill_specs)
        result = compose_from_graph(graph, migration_name="multi-tier-vpc")
        providers_tf = result.files.get("providers.tf", "")
        assert ">= 6.0.0" in providers_tf, (
            "Missing lower bound in providers.tf"
        )
        assert "oracle/oci" in providers_tf, (
            "Missing OCI provider source in providers.tf"
        )

    def test_providers_tf_has_required_version(self):
        """providers.tf requires Terraform >= 1.5."""
        from app.services.synthesis_composer import compose_from_graph

        graph = _build_graph(self.skill_specs)
        result = compose_from_graph(graph, migration_name="multi-tier-vpc")
        providers_tf = result.files.get("providers.tf", "")
        assert ">= 1.5" in providers_tf, (
            "Missing Terraform required_version in providers.tf"
        )

    # ── 4. Collision-free fixture ────────────────────────────────────────

    def test_no_warnings_on_clean_fixture(self):
        """A clean fixture should produce no collision warnings."""
        from app.services.synthesis_composer import compose_from_graph

        graph = _build_graph(self.skill_specs)
        result = compose_from_graph(graph, migration_name="multi-tier-vpc")
        assert result.warnings == [], f"Unexpected warnings: {result.warnings}"

    # ── 5. Skills tracked ────────────────────────────────────────────────

    def test_skills_included_in_result(self):
        """All three source skills are tracked in the composition result."""
        from app.services.synthesis_composer import compose_from_graph

        graph = _build_graph(self.skill_specs)
        result = compose_from_graph(graph, migration_name="multi-tier-vpc")
        for skill in ("network_translation", "ec2_translation",
                       "loadbalancer_translation"):
            assert skill in result.skills_included, (
                f"Skill {skill} not tracked in result.skills_included"
            )

    # ── 6. Variables file ────────────────────────────────────────────────

    def test_variables_tf_contains_canonical_vars(self):
        """variables.tf includes canonical root variables needed by the provider."""
        from app.services.synthesis_composer import compose_from_graph

        graph = _build_graph(self.skill_specs)
        result = compose_from_graph(graph, migration_name="multi-tier-vpc")
        variables_tf = result.files.get("variables.tf", "")
        for var_name in ("tenancy_ocid", "user_ocid", "fingerprint",
                         "private_key_path", "region", "compartment_id"):
            assert var_name in variables_tf, (
                f"Canonical variable '{var_name}' missing from variables.tf"
            )
