"""Tests for the robust _extract_json parser in skill_group."""
import json
import pytest
from app.agents.skill_group import _extract_json


class TestExtractJson:
    """Verify _extract_json handles various writer output formats."""

    def test_clean_json(self):
        result = _extract_json('{"main.tf": "resource...", "variables.tf": "var..."}')
        assert result.get("main.tf") == "resource..."

    def test_json_in_markdown_fence(self):
        text = 'Here is the output:\n```json\n{"main.tf": "code"}\n```\nDone.'
        result = _extract_json(text)
        assert result.get("main.tf") == "code"

    def test_json_with_prose_around(self):
        text = 'I have translated the resources.\n\n{"main.tf": "hcl content", "gaps": []}\n\nLet me know if you need changes.'
        result = _extract_json(text)
        assert "main.tf" in result

    def test_multiple_json_blocks_picks_largest(self):
        text = '{"small": 1}\nMore text\n{"main.tf": "code", "variables.tf": "vars", "outputs.tf": "outs"}'
        result = _extract_json(text)
        assert "main.tf" in result
        assert len(result) >= 3

    def test_empty_json_object(self):
        result = _extract_json('{}')
        assert result == {}

    def test_json_array_wrapped_as_specs(self):
        """JSON arrays are wrapped in {"specs": [...]} for structured output support."""
        result = _extract_json('[1, 2, 3]')
        assert "specs" in result
        assert result["specs"] == [1, 2, 3]

    def test_non_string_input(self):
        result = _extract_json(None)
        assert "raw" in result

    def test_completely_unparseable(self):
        result = _extract_json("This is just plain text with no JSON at all.")
        assert "raw" in result

    def test_nested_braces_in_hcl(self):
        """HCL content with nested braces should not break the parser."""
        inner = 'resource "oci_core_vcn" "main" {\n  compartment_id = var.cid\n  cidr_blocks = ["10.0.0.0/16"]\n}'
        text = json.dumps({"main.tf": inner, "variables.tf": 'variable "cid" { type = string }'})
        result = _extract_json(text)
        assert "main.tf" in result

    def test_json_fence_without_json_label(self):
        """A markdown fence without the 'json' label still works via brace scanning."""
        text = 'Output:\n```\n{"main.tf": "code"}\n```'
        result = _extract_json(text)
        assert "main.tf" in result

    def test_whitespace_only_returns_raw(self):
        result = _extract_json("   \n  \t  ")
        assert "raw" in result

    def test_integer_input_returns_raw(self):
        result = _extract_json(42)
        assert "raw" in result
