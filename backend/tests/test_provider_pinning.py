"""Provider version pinning tests (Phase 5)."""
import pytest
from app.services.synthesis_composer import (
    CANONICAL_PROVIDERS,
    _render_providers_tf,
    compose_terraform,
    compose_from_graph,
)


class TestCanonicalProviders:
    """CANONICAL_PROVIDERS dict has correct structure."""

    def test_oci_provider_exists(self):
        assert "oci" in CANONICAL_PROVIDERS

    def test_oci_provider_has_source(self):
        assert CANONICAL_PROVIDERS["oci"]["source"] == "oracle/oci"

    def test_oci_provider_has_lower_bound(self):
        version = CANONICAL_PROVIDERS["oci"]["version"]
        assert ">= 6.0.0" in version

    def test_oci_provider_has_upper_bound(self):
        version = CANONICAL_PROVIDERS["oci"]["version"]
        assert "< 7.0.0" in version


class TestRenderProvidersTf:
    """_render_providers_tf emits pinned version constraints."""

    def test_contains_lower_bound(self):
        tf = _render_providers_tf("test")
        assert ">= 6.0.0" in tf

    def test_contains_upper_bound(self):
        tf = _render_providers_tf("test")
        assert "< 7.0.0" in tf

    def test_contains_source(self):
        tf = _render_providers_tf("test")
        assert "oracle/oci" in tf

    def test_contains_required_version(self):
        tf = _render_providers_tf("test")
        assert ">= 1.5" in tf

    def test_contains_provider_block(self):
        tf = _render_providers_tf("test")
        assert 'provider "oci"' in tf
        assert "var.tenancy_ocid" in tf

    def test_migration_name_in_comment(self):
        tf = _render_providers_tf("my-migration")
        assert "my-migration" in tf


class TestComposeTerraformProviderPinning:
    """compose_terraform output includes pinned providers.tf."""

    def test_providers_tf_in_empty_compose(self):
        result = compose_terraform({}, migration_name="test")
        assert "providers.tf" in result.files
        tf = result.files["providers.tf"]
        assert ">= 6.0.0" in tf
        assert "< 7.0.0" in tf
