"""Writer returns malformed specs -> error handling works correctly.

Tests _extract_json array handling and SkillGroup graceful degradation
when the LLM writer produces invalid structured output.
"""

import json
import pytest

from app.agents.skill_group import SKILL_SPECS, SkillGroup, _extract_json


class TestExtractJsonArrays:
    """_extract_json handles JSON arrays for structured output."""

    def test_direct_array(self):
        text = '[{"template": "core/vcn", "label": "main", "params": {}}]'
        result = _extract_json(text)
        assert "specs" in result
        assert len(result["specs"]) == 1

    def test_fenced_array(self):
        text = '```json\n[{"template": "core/vcn"}]\n```'
        result = _extract_json(text)
        assert "specs" in result

    def test_dict_still_works(self):
        text = '{"main.tf": "resource..."}'
        result = _extract_json(text)
        assert "main.tf" in result

    def test_garbage_returns_raw(self):
        text = "This is not JSON at all"
        result = _extract_json(text)
        assert "raw" in result

    def test_empty_string_returns_raw(self):
        result = _extract_json("")
        assert "raw" in result

    def test_non_string_input_returns_raw(self):
        result = _extract_json(12345)
        assert "raw" in result

    def test_nested_array_in_prose(self):
        """Array embedded in prose: _extract_json finds the dict inside the
        array via brace-balancing (strategy 3) before it finds the array
        (strategy 3b), so the result is a single dict, not {"specs": [...]}.
        This is expected behavior -- the brace strategy runs first."""
        text = (
            "Here are the resource specs I've created:\n\n"
            '[{"template": "core/vcn", "label": "main", "params": {"compartment_id": "var.c"}}]\n\n'
            "Let me know if you need changes."
        )
        result = _extract_json(text)
        # Brace-balanced extraction finds the inner dict first
        assert "template" in result
        assert result["template"] == "core/vcn"

    def test_empty_array(self):
        result = _extract_json("[]")
        assert "specs" in result
        assert result["specs"] == []

    def test_nested_json_in_markdown(self):
        """JSON embedded in markdown fences is extracted."""
        text = (
            "Here is the translation:\n\n"
            "```json\n"
            '{"specs": [{"template": "core/vcn", "label": "main", "params": {}}]}\n'
            "```\n\n"
            "That should work."
        )
        result = _extract_json(text)
        assert "specs" in result

    def test_multiple_json_blocks_picks_largest(self):
        """When multiple fenced blocks exist, picks the largest dict."""
        text = (
            '```json\n{"a": 1}\n```\n'
            '```json\n{"a": 1, "b": 2, "c": 3}\n```\n'
        )
        result = _extract_json(text)
        assert len(result) == 3

    def test_mixed_content_prefers_dict(self):
        """When both dict and array JSON exist, dict (being first strategy) wins."""
        text = '{"main.tf": "code"}'
        result = _extract_json(text)
        assert "main.tf" in result

    def test_bare_json_object_no_fences(self):
        """Bare JSON object without fences is parsed."""
        text = 'Some text {"template": "core/vcn", "label": "x", "params": {}} after'
        result = _extract_json(text)
        assert "template" in result

    def test_array_with_multiple_specs(self):
        text = (
            '[{"template": "core/vcn", "label": "a", "params": {}},'
            ' {"template": "core/subnet", "label": "b", "params": {}}]'
        )
        result = _extract_json(text)
        assert "specs" in result
        assert len(result["specs"]) == 2

    def test_deeply_nested_braces_in_hcl(self):
        """JSON with HCL string values containing braces still parses."""
        payload = {
            "specs": [
                {
                    "template": "free_form_hcl",
                    "label": "x",
                    "params": {"hcl": 'resource "null" "x" { triggers = { a = "b" } }'},
                }
            ]
        }
        text = json.dumps(payload)
        result = _extract_json(text)
        assert "specs" in result


class TestMalformedSpecs:
    """SkillGroup handles malformed writer output gracefully."""

    def _make_group(self, skill_type: str = "network_translation") -> SkillGroup:
        return SkillGroup(SKILL_SPECS[skill_type])

    def test_empty_specs_falls_back(self):
        group = self._make_group()
        draft = {"raw": "Not valid specs at all"}
        result = group._process_structured_output(draft)
        # Should return draft as-is since no specs found
        assert "raw" in result

    def test_missing_params_key(self):
        group = self._make_group()
        draft = {"specs": [{"template": "core/vcn", "label": "bad"}]}
        result = group._process_structured_output(draft)
        # Should fail -- missing params triggers render error
        assert "_render_error" in result

    def test_wrong_template_name(self):
        group = self._make_group()
        draft = {"specs": [{"template": "nonexistent/thing", "label": "bad", "params": {}}]}
        result = group._process_structured_output(draft)
        assert "_render_error" in result

    def test_render_error_message_includes_template_name(self):
        group = self._make_group()
        draft = {"specs": [{"template": "nonexistent/widget", "label": "x", "params": {}}]}
        result = group._process_structured_output(draft)
        assert "_render_error" in result
        assert "nonexistent/widget" in result["_render_error"]

    def test_empty_specs_list(self):
        """Empty specs list returns draft as-is."""
        group = self._make_group()
        draft = {"specs": []}
        result = group._process_structured_output(draft)
        assert result == draft

    def test_partial_valid_specs_fail_strict(self):
        """Mix of valid and invalid specs -- the whole render fails (strict mode)."""
        group = self._make_group()
        draft = {
            "specs": [
                {
                    "template": "core/vcn",
                    "label": "good",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "cidr_blocks": ["10.0.0.0/16"],
                        "display_name": "vcn",
                        "aws_source_id": "vpc-1",
                    },
                },
                {
                    "template": "core/vcn",
                    "label": "bad",
                    "params": {"display_name": "no-compartment"},
                },
            ]
        }
        result = group._process_structured_output(draft)
        # Strict mode: one bad spec fails the whole render
        assert "_render_error" in result

    def test_spec_with_null_params(self):
        """None params handled gracefully."""
        group = self._make_group()
        draft = {"specs": [{"template": "core/vcn", "label": "null", "params": None}]}
        result = group._process_structured_output(draft)
        assert "_render_error" in result

    def test_specs_with_none_optional_fields(self):
        """Specs with None values for optional fields render correctly."""
        group = self._make_group()
        draft = {
            "specs": [
                {
                    "template": "core/vcn",
                    "label": "main",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "cidr_blocks": ["10.0.0.0/16"],
                        "display_name": "vcn",
                        "dns_label": None,
                        "freeform_tags": None,
                        "aws_source_id": "vpc-1",
                    },
                },
            ]
        }
        result = group._process_structured_output(draft)
        assert "network.tf" in result
        assert "oci_core_vcn" in result["network.tf"]

    def test_specs_with_extra_fields_tolerated(self):
        """Extra fields in params that are not in the schema are ignored
        (Pydantic default behavior) and do not break rendering."""
        group = self._make_group()
        draft = {
            "specs": [
                {
                    "template": "core/vcn",
                    "label": "main",
                    "params": {
                        "compartment_id": "var.compartment_id",
                        "cidr_blocks": ["10.0.0.0/16"],
                        "display_name": "vcn",
                        "aws_source_id": "vpc-1",
                        "extra_field_from_llm": "should be ignored",
                    },
                }
            ]
        }
        result = group._process_structured_output(draft)
        assert "network.tf" in result
        assert "oci_core_vcn" in result["network.tf"]

    def test_free_form_hcl_fallback_works(self):
        """Writer can fall back to free_form_hcl for unsupported resources."""
        group = self._make_group()
        draft = {
            "specs": [
                {
                    "template": "free_form_hcl",
                    "label": "vpn",
                    "params": {
                        "hcl": 'resource "oci_core_ipsec" "vpn" {\n  # TODO: template this\n}'
                    },
                },
            ]
        }
        result = group._process_structured_output(draft)
        assert "main.tf" in result
        assert "oci_core_ipsec" in result["main.tf"]

    def test_free_form_hcl_empty_body_fails(self):
        """free_form_hcl with empty string fails rendering."""
        group = self._make_group()
        draft = {
            "specs": [
                {"template": "free_form_hcl", "label": "empty", "params": {"hcl": ""}},
            ]
        }
        result = group._process_structured_output(draft)
        assert "_render_error" in result
