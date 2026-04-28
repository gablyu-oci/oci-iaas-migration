"""Tests for reasoning-model-aware chunking thresholds."""
import json
import pytest

from app.services.network_chunker import (
    chunk_network_input,
    DEFAULT_SIZE_THRESHOLD,
    REASONING_SIZE_THRESHOLD,
)
from app.services.cfn_chunker import (
    chunk_cfn_template,
    DEFAULT_CHUNK_SIZE,
    REASONING_CHUNK_SIZE,
)


class TestNetworkChunkerReasoningThreshold:
    """Verify that reasoning models get a lower size threshold."""

    def _make_network_input(self, char_count: int, num_vpcs: int = 3) -> dict:
        """Build a synthetic network input of approximately char_count chars.

        Spreads security groups across num_vpcs VPCs so the chunker
        (which groups by VPC) actually produces multiple chunks.
        """
        # Each security group rule is ~200 chars of JSON
        rules = []
        subnets = []
        for i in range(char_count // 200 + 1):
            vpc_id = f"vpc-{i % num_vpcs}"
            rules.append({
                "group_id": f"sg-{i:06d}",
                "protocol": "tcp",
                "from_port": 443,
                "to_port": 443,
                "cidr": f"10.{i % 256}.0.0/16",
                "description": f"Rule {i} for testing chunking thresholds",
                "vpc_id": vpc_id,
            })
        # One subnet per VPC
        for v in range(num_vpcs):
            subnets.append({
                "subnet_id": f"sub-{v}",
                "vpc_id": f"vpc-{v}",
                "cidr_block": f"10.{v}.1.0/24",
            })
        return {
            "subnets": subnets,
            "security_groups": rules,
        }

    def test_reasoning_model_chunks_medium_input(self):
        """Input between REASONING threshold and DEFAULT threshold is chunked for reasoning, single-pass for non-reasoning."""
        # Make input that's > REASONING_SIZE_THRESHOLD chars but < DEFAULT_SIZE_THRESHOLD chars
        inp = self._make_network_input(10_000, num_vpcs=3)
        serialized = json.dumps(inp)
        assert REASONING_SIZE_THRESHOLD < len(serialized) < DEFAULT_SIZE_THRESHOLD, (
            f"Input size {len(serialized)} not between {REASONING_SIZE_THRESHOLD} and {DEFAULT_SIZE_THRESHOLD}"
        )

        # Reasoning model should produce multiple chunks (one per VPC + global)
        chunks_reasoning = chunk_network_input(inp, model="oci/openai.gpt-5.4")
        assert len(chunks_reasoning) > 1, "Reasoning model should chunk medium input"

        # Non-reasoning model should produce a single chunk (under DEFAULT threshold)
        chunks_normal = chunk_network_input(inp, model="oci/meta-llama-3.1-70b")
        assert len(chunks_normal) == 1, "Non-reasoning model should single-pass medium input"

    def test_explicit_threshold_overrides_model(self):
        """When size_threshold is explicitly passed, it overrides the model-based default."""
        inp = self._make_network_input(10_000)
        # Even with reasoning model, if explicit threshold is high, no chunking
        chunks = chunk_network_input(inp, size_threshold=50_000, model="oci/openai.gpt-5.4")
        assert len(chunks) == 1

    def test_no_model_uses_default_threshold(self):
        """When model is not provided, DEFAULT_SIZE_THRESHOLD is used."""
        inp = self._make_network_input(10_000)
        chunks = chunk_network_input(inp)
        assert len(chunks) == 1  # under 20_000 default

    def test_small_input_never_chunked(self):
        """Input under both thresholds is never chunked regardless of model."""
        inp = {"vpc_id": "vpc-1", "cidr_block": "10.0.0.0/16", "subnets": []}
        chunks_reasoning = chunk_network_input(inp, model="oci/openai.gpt-5.4")
        chunks_normal = chunk_network_input(inp, model="oci/meta-llama-3.1-70b")
        assert len(chunks_reasoning) == 1
        assert len(chunks_normal) == 1

    def test_empty_input_returns_empty(self):
        """Empty or non-dict inputs return an empty list."""
        assert chunk_network_input({}) == []
        assert chunk_network_input(None) == []

    def test_threshold_constants_are_ordered(self):
        """REASONING_SIZE_THRESHOLD must be strictly less than DEFAULT_SIZE_THRESHOLD."""
        assert REASONING_SIZE_THRESHOLD < DEFAULT_SIZE_THRESHOLD


class TestCfnChunkerReasoningThreshold:
    """Verify that reasoning models get a lower per-chunk resource cap."""

    def _make_cfn_template(self, resource_count: int) -> dict:
        """Build a synthetic CFN template with N resources."""
        resources = {}
        for i in range(resource_count):
            resources[f"Resource{i}"] = {
                "Type": "AWS::EC2::Instance",
                "Properties": {"InstanceType": "t3.medium", "ImageId": f"ami-{i:08d}"},
            }
        return {
            "AWSTemplateFormatVersion": "2010-09-09",
            "Resources": resources,
        }

    def test_reasoning_model_smaller_chunks(self):
        """With 12 resources: reasoning model splits into >1 chunk, non-reasoning does 1 chunk."""
        template = self._make_cfn_template(12)

        chunks_reasoning = chunk_cfn_template(template, model="oci/openai.o3-mini")
        # 12 resources / REASONING_CHUNK_SIZE(6) per chunk = 2 chunks
        assert len(chunks_reasoning) == 2, f"Expected 2 chunks for reasoning model, got {len(chunks_reasoning)}"

        chunks_normal = chunk_cfn_template(template, model="oci/meta-llama-3.1-70b")
        # 12 resources / DEFAULT_CHUNK_SIZE(20) per chunk = 1 chunk
        assert len(chunks_normal) == 1, f"Expected 1 chunk for non-reasoning model, got {len(chunks_normal)}"

    def test_explicit_chunk_size_overrides_model(self):
        """Explicit chunk_size takes precedence over model-based default."""
        template = self._make_cfn_template(12)
        chunks = chunk_cfn_template(template, chunk_size=4, model="oci/meta-llama-3.1-70b")
        assert len(chunks) == 3  # 12/4 = 3

    def test_no_model_uses_default_chunk_size(self):
        """Without model parameter, DEFAULT_CHUNK_SIZE (20) is used."""
        template = self._make_cfn_template(12)
        chunks = chunk_cfn_template(template)
        assert len(chunks) == 1  # 12 < 20

    def test_chunk_size_constants_are_ordered(self):
        """REASONING_CHUNK_SIZE must be strictly less than DEFAULT_CHUNK_SIZE."""
        assert REASONING_CHUNK_SIZE < DEFAULT_CHUNK_SIZE

    def test_empty_template_returns_empty(self):
        """A template with no Resources returns an empty list."""
        assert chunk_cfn_template({}) == []
        assert chunk_cfn_template(None) == []

    def test_all_logical_ids_present_in_every_chunk(self):
        """Each chunk carries the full list of logical IDs for cross-chunk references."""
        template = self._make_cfn_template(12)
        chunks = chunk_cfn_template(template, chunk_size=4)
        all_ids = [f"Resource{i}" for i in range(12)]
        for chunk in chunks:
            assert sorted(chunk.all_logical_ids) == sorted(all_ids)
