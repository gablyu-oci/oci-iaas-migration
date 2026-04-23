"""Chunk a large network_translation input so the writer LLM stays within
nginx's upstream timeout.

Same failure mode as the CFN translator: a single VPC with 30+ security
groups, each carrying 10+ ingress / egress rules, blows the network_
translation input past the LLM's comfort window. The writer takes long
enough producing the merged HCL that the Llama Stack nginx proxy returns
504 before the response streams back, and retries just hit the same wall.

Strategy mirrors cfn_chunker:

1. If the input is small (< SIZE_THRESHOLD chars of JSON), pass it to
   the writer as one chunk — no chunking overhead for simple networks.
2. Otherwise group resources by VPC so each chunk is self-contained
   (subnets + SGs + ENIs + route tables + IGW/NAT/NACL/EIP all scoped
   to one VPC). Global-ish resources (DNS zones, customer gateways,
   direct-connect, transit gateways, VPC peerings) go in a final
   "global" chunk so they're only emitted once.
3. Each ChunkSpec carries the full list of all VPC IDs + all subnet IDs
   so the writer can emit cross-chunk Terraform references (the planner
   resolves them at apply time regardless of declaration order).
4. Each chunk runs as a separate skill call; outputs merge with
   cfn_chunker.merge_chunk_outputs (shared helper; dedupes variables
   and outputs by name, concatenates main.tf with chunk headers).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# If the full network input serializes under this many chars, we skip
# chunking entirely. Empirically tuned so sub-threshold inputs fit in a
# single gpt-5.4 response within nginx's upstream timeout.
DEFAULT_SIZE_THRESHOLD = 20_000


@dataclass
class NetworkChunkSpec:
    """One chunk of the network input — all VPC-scoped resources for a
    single VPC plus a slice of global metadata, or a global-only chunk
    covering DNS / peering / transit-gateway / direct-connect.
    """
    index: int
    total: int
    scope: str                    # "vpc:<id>" or "global"
    payload: dict[str, Any]       # the skill input for this chunk
    all_vpc_ids: list[str]        # every VPC ID (for cross-chunk refs)
    all_subnet_ids: list[str]

    def to_input(self) -> str:
        envelope = {
            "_chunked": True,
            "chunk_index": self.index,
            "chunk_total": self.total,
            "scope": self.scope,
            "all_vpc_ids": self.all_vpc_ids,
            "all_subnet_ids": self.all_subnet_ids,
            **self.payload,
        }
        return json.dumps(envelope, indent=2, default=str)


# ─── Helpers ──────────────────────────────────────────────────────────────

_VPC_SCOPED_KEYS = (
    "subnets", "security_groups", "network_interfaces",
    "route_tables", "internet_gateways", "nat_gateways",
    "elastic_ips", "network_acls",
)

# Resources that aren't naturally bound to a single VPC. Emitted once
# in the final "global" chunk to avoid duplication.
_GLOBAL_KEYS = (
    "vpc_peerings", "transit_gateways", "transit_gateway_attachments",
    "transit_gateway_route_tables", "vpc_endpoints",
    "vpn_connections", "vpn_gateways", "customer_gateways",
    "direct_connects", "dns_zones", "dns_records",
)


def _vpc_of(item: dict) -> str:
    """Best-effort VPC ID extraction from a sub-resource."""
    if not isinstance(item, dict):
        return ""
    for k in ("vpc_id", "VpcId"):
        v = item.get(k)
        if isinstance(v, str) and v:
            return v
    # IGW stores attachments[{ vpc_id }]
    atts = item.get("attachments") or []
    if isinstance(atts, list):
        for a in atts:
            if isinstance(a, dict):
                v = a.get("vpc_id") or a.get("VpcId")
                if isinstance(v, str) and v:
                    return v
    return ""


def chunk_network_input(
    network_input: dict,
    size_threshold: int = DEFAULT_SIZE_THRESHOLD,
) -> list[NetworkChunkSpec]:
    """Return a list of chunks, each small enough for one writer turn.

    When the input is under the threshold, returns a single chunk
    containing the whole thing (``scope="global"``). For large inputs,
    returns one chunk per unique VPC id + one trailing global chunk
    covering cross-VPC resources.
    """
    if not isinstance(network_input, dict) or not network_input:
        return []

    serialized = json.dumps(network_input, default=str)
    if len(serialized) < size_threshold:
        # Fast path — single chunk, writer handles as usual.
        return [NetworkChunkSpec(
            index=0, total=1, scope="whole",
            payload=dict(network_input),
            all_vpc_ids=_collect_vpc_ids(network_input),
            all_subnet_ids=_collect_subnet_ids(network_input),
        )]

    all_vpc_ids = _collect_vpc_ids(network_input)
    all_subnet_ids = _collect_subnet_ids(network_input)

    # Bucket per-VPC
    per_vpc: dict[str, dict[str, list]] = {vpc: {k: [] for k in _VPC_SCOPED_KEYS} for vpc in all_vpc_ids}
    orphans: dict[str, list] = {k: [] for k in _VPC_SCOPED_KEYS}

    for key in _VPC_SCOPED_KEYS:
        items = network_input.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            vpc = _vpc_of(item)
            if vpc and vpc in per_vpc:
                per_vpc[vpc][key].append(item)
            else:
                orphans[key].append(item)

    # Build per-VPC chunks
    chunks: list[NetworkChunkSpec] = []
    # Preserve top-level VPC metadata (if the input carried a single-VPC
    # shape with cidr_block at the top)
    top_vpc_id = network_input.get("vpc_id")
    top_vpc_cidr = network_input.get("cidr_block")

    for vpc_id, buckets in per_vpc.items():
        payload: dict[str, Any] = {"vpc_id": vpc_id}
        if top_vpc_id == vpc_id and top_vpc_cidr:
            payload["cidr_block"] = top_vpc_cidr
        payload.update(buckets)
        chunks.append(NetworkChunkSpec(
            index=0, total=0, scope=f"vpc:{vpc_id}",
            payload=payload,
            all_vpc_ids=all_vpc_ids,
            all_subnet_ids=all_subnet_ids,
        ))

    # Global chunk: cross-VPC + orphan VPC-scoped resources (whose vpc_id
    # didn't match any known VPC — usually legacy data).
    global_payload: dict[str, Any] = {}
    for key in _GLOBAL_KEYS:
        v = network_input.get(key)
        if v:
            global_payload[key] = v
    # Orphans folded in so they don't silently disappear.
    for key, items in orphans.items():
        if items:
            global_payload.setdefault("orphans", {})[key] = items
    if global_payload:
        chunks.append(NetworkChunkSpec(
            index=0, total=0, scope="global",
            payload=global_payload,
            all_vpc_ids=all_vpc_ids,
            all_subnet_ids=all_subnet_ids,
        ))

    # Finalize index/total
    total = len(chunks)
    for i, c in enumerate(chunks):
        c.index = i
        c.total = total
    return chunks


def _collect_vpc_ids(network_input: dict) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    def _add(v: str | None) -> None:
        if v and v not in seen:
            seen.add(v)
            ids.append(v)

    _add(network_input.get("vpc_id"))
    for key in _VPC_SCOPED_KEYS:
        for item in (network_input.get(key) or []):
            if isinstance(item, dict):
                _add(_vpc_of(item))
    for vpc in (network_input.get("vpcs") or []):
        if isinstance(vpc, dict):
            _add(vpc.get("vpc_id") or vpc.get("VpcId"))
    return ids


def _collect_subnet_ids(network_input: dict) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for s in (network_input.get("subnets") or []):
        if isinstance(s, dict):
            sid = s.get("subnet_id") or s.get("SubnetId")
            if sid and sid not in seen:
                seen.add(sid)
                ids.append(sid)
    return ids
