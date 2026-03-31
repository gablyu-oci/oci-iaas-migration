"""Application grouping engine -- groups resources into logical applications.

This module is purely algorithmic (no external API calls). It assigns
resources to application groups using a three-pass strategy:

  1. Tag-based grouping   -- resources that share a known application tag value
  2. Network-based grouping -- ungrouped resources that share VPC + subnet
  3. Traffic-based merging  -- merge groups with heavy cross-group traffic
"""
from __future__ import annotations

import logging
from collections import defaultdict
from itertools import combinations
from typing import Any

logger = logging.getLogger(__name__)

# Tags commonly used to identify the owning application
APP_TAG_KEYS = [
    "Application", "application", "app", "App",
    "project", "Project",
    "stack", "Stack",
    "service", "Service",
    "aws:cloudformation:stack-name",
    "aws:cloudformation:stack-id",
]


# ---------------------------------------------------------------------------
# Pass 1: Tag-based grouping
# ---------------------------------------------------------------------------

def _extract_resource_id(resource: dict) -> str:
    """Return a stable identifier for a resource dict.

    Checks common keys produced by the AWS extractor layer.
    """
    for key in ("id", "resource_id", "aws_arn", "arn", "instance_id"):
        val = resource.get(key)
        if val:
            return str(val)
    return str(id(resource))


def _get_tags(resource: dict) -> list[dict]:
    """Retrieve the tags list from a resource, tolerating different shapes."""
    raw_config = resource.get("raw_config") or resource
    tags = raw_config.get("Tags") or raw_config.get("tags") or []
    if isinstance(tags, dict):
        # Some resources store tags as {Key: Value, ...} instead of a list
        return [{"Key": k, "Value": v} for k, v in tags.items()]
    return tags


def _group_by_tags(resources: list[dict]) -> dict[str, list[str]]:
    """Pass 1: Group resources by application tags.

    Scan each resource's tags for keys in APP_TAG_KEYS.  The first matching
    tag value becomes that resource's group.  A resource can only appear in
    one tag-based group.

    Returns:
        Mapping of tag_value -> list of resource IDs.
    """
    groups: dict[str, list[str]] = defaultdict(list)

    for resource in resources:
        resource_id = _extract_resource_id(resource)
        tags = _get_tags(resource)

        tag_map: dict[str, str] = {}
        for tag in tags:
            if isinstance(tag, dict):
                tag_map[tag.get("Key", "")] = tag.get("Value", "")

        # First matching key wins
        for candidate_key in APP_TAG_KEYS:
            value = tag_map.get(candidate_key, "").strip()
            if value:
                groups[value].append(resource_id)
                break  # resource assigned -- move to the next one

    # Remove any group with empty name (shouldn't happen, but be safe)
    return {k: v for k, v in groups.items() if k}


# ---------------------------------------------------------------------------
# Pass 2: Network-based grouping
# ---------------------------------------------------------------------------

def _group_by_network(
    resources: list[dict],
    already_grouped: set[str],
) -> dict[str, list[str]]:
    """Pass 2: Group ungrouped resources by VPC + subnet locality.

    For each resource not in *already_grouped*, extract ``VpcId`` and
    ``SubnetId`` from the resource's ``raw_config`` (or top-level keys) and
    form a composite key ``vpc:{vpc_id}:subnet:{subnet_id}``.

    Only groups with 2 or more members are returned.
    """
    network_groups: dict[str, list[str]] = defaultdict(list)

    for resource in resources:
        resource_id = _extract_resource_id(resource)
        if resource_id in already_grouped:
            continue

        raw = resource.get("raw_config") or resource
        vpc_id = raw.get("VpcId") or raw.get("vpc_id") or ""
        subnet_id = raw.get("SubnetId") or raw.get("subnet_id") or ""

        if not vpc_id:
            continue

        if subnet_id:
            group_key = f"vpc:{vpc_id}:subnet:{subnet_id}"
        else:
            group_key = f"vpc:{vpc_id}"

        network_groups[group_key].append(resource_id)

    # Only keep groups with at least 2 members
    return {k: v for k, v in network_groups.items() if len(v) >= 2}


# ---------------------------------------------------------------------------
# Pass 3: Merge groups with heavy cross-traffic
# ---------------------------------------------------------------------------

def _build_resource_to_group(groups: dict[str, list[str]]) -> dict[str, str]:
    """Invert groups dict to resource_id -> group_name."""
    mapping: dict[str, str] = {}
    for group_name, resource_ids in groups.items():
        for rid in resource_ids:
            mapping[rid] = group_name
    return mapping


def _merge_heavy_traffic_groups(
    groups: dict[str, list[str]],
    dependency_edges: list[dict],
    threshold_bytes: int = 100_000_000,  # 100 MB
) -> dict[str, list[str]]:
    """Pass 3: Merge groups connected by heavy network traffic.

    For every pair of groups, sum the ``byte_count`` of dependency edges whose
    source and target belong to different groups.  If the total exceeds
    *threshold_bytes*, the smaller group is merged into the larger one.

    The process repeats until no further merges are needed.
    """
    if not dependency_edges:
        return groups

    merged = True
    while merged:
        merged = False
        r2g = _build_resource_to_group(groups)

        # Accumulate cross-group traffic
        cross_traffic: dict[tuple[str, str], float] = defaultdict(float)
        for edge in dependency_edges:
            src = str(edge.get("source_resource_id", ""))
            tgt = str(edge.get("target_resource_id", ""))
            byte_count = edge.get("byte_count") or 0

            src_group = r2g.get(src)
            tgt_group = r2g.get(tgt)

            if not src_group or not tgt_group or src_group == tgt_group:
                continue

            # Normalise the pair so (A, B) == (B, A)
            pair = tuple(sorted([src_group, tgt_group]))
            cross_traffic[pair] += byte_count

        # Find and execute the heaviest merge that exceeds the threshold
        for (g1, g2), total_bytes in sorted(
            cross_traffic.items(), key=lambda x: x[1], reverse=True
        ):
            if total_bytes < threshold_bytes:
                break  # sorted descending, so no more pairs will qualify

            # Merge smaller into larger
            if len(groups.get(g1, [])) >= len(groups.get(g2, [])):
                target, source = g1, g2
            else:
                target, source = g2, g1

            groups[target].extend(groups.pop(source))
            logger.info(
                "Merged group '%s' into '%s' (cross-traffic %.1f MB)",
                source, target, total_bytes / 1_000_000,
            )
            merged = True
            break  # restart the while loop with updated mappings

    return groups


# ---------------------------------------------------------------------------
# Pass 4: Workload type classification
# ---------------------------------------------------------------------------

# AWS resource type patterns for workload classification
_GPU_INSTANCE_PREFIXES = ("p3", "p4", "p5", "g4", "g5", "g6")


def _has_type(resources: list[dict], *patterns: str) -> bool:
    """Check if any resource's aws_type contains one of the given patterns."""
    for r in resources:
        aws_type = (r.get("aws_type") or "").lower()
        for pattern in patterns:
            if pattern.lower() in aws_type:
                return True
    return False


def _has_gpu_instances(resources: list[dict]) -> bool:
    """Check for GPU EC2 instances (p3/p4/p5/g4/g5/g6 families)."""
    for r in resources:
        aws_type = r.get("aws_type") or ""
        if "EC2::Instance" not in aws_type:
            continue
        raw = r.get("raw_config") or {}
        instance_type = raw.get("InstanceType") or raw.get("instance_type") or ""
        for prefix in _GPU_INSTANCE_PREFIXES:
            if instance_type.startswith(prefix):
                return True
    return False


def _has_large_s3(resources: list[dict], threshold_bytes: int = 1_099_511_627_776) -> bool:
    """Check for S3 buckets exceeding threshold (default 1 TB)."""
    for r in resources:
        aws_type = r.get("aws_type") or ""
        if "S3" not in aws_type:
            continue
        raw = r.get("raw_config") or {}
        size = raw.get("SizeBytes") or raw.get("size_bytes") or 0
        if size > threshold_bytes:
            return True
    return False


def _has_spot_instances(resources: list[dict]) -> bool:
    """Check for EC2 Spot instances."""
    for r in resources:
        aws_type = r.get("aws_type") or ""
        if "EC2::Instance" not in aws_type:
            continue
        raw = r.get("raw_config") or {}
        lifecycle = raw.get("InstanceLifecycle") or raw.get("instance_lifecycle") or ""
        if lifecycle.lower() == "spot":
            return True
    return False


def classify_workload_type(resources: list[dict]) -> str:
    """Classify a group of resources into a workload type.

    Priority order (from workload-types.md):
    1. AI/ML: SageMaker or GPU EC2
    2. Container: EKS/ECS/Fargate
    3. Serverless: Lambda without EC2
    4. Data & Analytics: Redshift/EMR/Glue
    5. Database: RDS/Aurora without EC2
    6. Batch/HPC: Batch or Spot compute
    7. Storage: S3 > 1TB without EC2
    8. Web/API App: EC2 + ALB/RDS
    9. Default: Web/API App
    """
    has_ec2 = _has_type(resources, "EC2::Instance")

    # 1. AI/ML
    if _has_type(resources, "SageMaker") or _has_gpu_instances(resources):
        return "ai_ml"

    # 2. Container
    if _has_type(resources, "EKS", "ECS", "Fargate"):
        return "container"

    # 3. Serverless
    if _has_type(resources, "Lambda") and not has_ec2:
        return "serverless"

    # 4. Data & Analytics
    if _has_type(resources, "Redshift", "EMR", "Glue"):
        return "data_analytics"

    # 5. Database
    if _has_type(resources, "RDS", "Aurora") and not has_ec2:
        return "database"

    # 6. Batch/HPC
    if _has_type(resources, "Batch") or (_has_spot_instances(resources) and has_ec2):
        return "batch_hpc"

    # 7. Storage
    if _has_large_s3(resources) and not has_ec2:
        return "storage"

    # 8. Web/API App (explicit match)
    if has_ec2 and (_has_type(resources, "LoadBalancer", "ALB", "NLB") or _has_type(resources, "RDS")):
        return "web_api"

    # 9. Default
    return "web_api"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_app_groups(
    resources: list[dict],
    dependency_edges: list[dict],
) -> list[dict]:
    """Compute application groups from a flat list of resources.

    Returns a list of dicts, each with:
        - name (str): tag value, network key, or ``ungrouped-N``
        - strategy (str): ``tag-based``, ``network-based``, or ``singleton``
        - resource_ids (list[str])
        - resource_count (int)

    Steps:
        1. Tag-based grouping
        2. Network-based grouping for remaining resources
        3. Merge groups with heavy cross-traffic
        4. Remaining resources become singleton groups
        5. Sort descending by resource_count
    """
    if not resources:
        return []

    # Build resource lookup for workload classification
    resource_by_id = {_extract_resource_id(r): r for r in resources}

    # --- 1. Tag-based grouping ---
    tag_groups = _group_by_tags(resources)
    already_grouped: set[str] = set()
    for ids in tag_groups.values():
        already_grouped.update(ids)

    logger.info(
        "Tag-based grouping: %d groups covering %d resources",
        len(tag_groups), len(already_grouped),
    )

    # --- 2. Network-based grouping ---
    net_groups = _group_by_network(resources, already_grouped)
    for ids in net_groups.values():
        already_grouped.update(ids)

    logger.info(
        "Network-based grouping: %d groups covering %d additional resources",
        len(net_groups),
        sum(len(v) for v in net_groups.values()),
    )

    # --- 3. Merge all groups, then apply traffic-based merging ---
    # Track strategy origin before merging
    strategy_map: dict[str, str] = {}
    all_groups: dict[str, list[str]] = {}

    for name, ids in tag_groups.items():
        all_groups[name] = ids
        strategy_map[name] = "tag-based"

    for name, ids in net_groups.items():
        all_groups[name] = ids
        strategy_map[name] = "network-based"

    all_groups = _merge_heavy_traffic_groups(all_groups, dependency_edges)

    # --- 3b. Attachment-based grouping for EBS volumes ---
    # Pull ungrouped EBS volumes into the same group as their attached EC2 instance.
    grouped_ids_now: set[str] = {rid for ids in all_groups.values() for rid in ids}
    instance_id_to_group: dict[str, str] = {}
    for group_name, ids in all_groups.items():
        for rid in ids:
            r = resource_by_id.get(rid, {})
            raw = r.get("raw_config") or r
            iid = raw.get("instance_id") or raw.get("InstanceId")
            if iid:
                instance_id_to_group[iid] = group_name

    for resource in resources:
        rid = _extract_resource_id(resource)
        if rid in grouped_ids_now:
            continue
        raw = resource.get("raw_config") or resource
        aws_type = resource.get("aws_type", "")
        # EBS volume: check attachments list
        if "Volume" in aws_type:
            for att in raw.get("attachments", raw.get("Attachments", [])):
                iid = att.get("instance_id") or att.get("InstanceId")
                if iid and iid in instance_id_to_group:
                    target_group = instance_id_to_group[iid]
                    all_groups[target_group].append(rid)
                    grouped_ids_now.add(rid)
                    logger.info("Attached EBS %s to group '%s' via instance %s", rid, target_group, iid)
                    break

    # --- 3c. CloudFormation stack name matching ---
    # A CFN stack whose name matches an existing group name belongs to that group.
    grouped_ids_now = {rid for ids in all_groups.values() for rid in ids}
    for resource in resources:
        rid = _extract_resource_id(resource)
        if rid in grouped_ids_now:
            continue
        aws_type = resource.get("aws_type", "")
        if "CloudFormation::Stack" not in aws_type:
            continue
        stack_name = resource.get("name") or (resource.get("raw_config") or {}).get("stack_name", "")
        if stack_name and stack_name in all_groups:
            all_groups[stack_name].append(rid)
            grouped_ids_now.add(rid)
            logger.info("Added CFN stack '%s' to its matching group", stack_name)

    # --- 4. Singleton groups for anything still ungrouped ---
    all_resource_ids = {_extract_resource_id(r) for r in resources}
    grouped_ids: set[str] = set()
    for ids in all_groups.values():
        grouped_ids.update(ids)

    ungrouped_counter = 0
    for resource_id in sorted(all_resource_ids - grouped_ids):
        ungrouped_counter += 1
        name = f"ungrouped-{ungrouped_counter}"
        all_groups[name] = [resource_id]
        strategy_map[name] = "singleton"

    if ungrouped_counter:
        logger.info("Created %d singleton groups for ungrouped resources", ungrouped_counter)

    # --- 5. Build result list, sorted by resource_count descending ---
    results: list[dict] = []
    for name, resource_ids in all_groups.items():
        group_resources = [resource_by_id[rid] for rid in resource_ids if rid in resource_by_id]
        results.append({
            "name": name,
            "strategy": strategy_map.get(name, "tag-based"),
            "resource_ids": resource_ids,
            "resource_count": len(resource_ids),
            "workload_type": classify_workload_type(group_resources),
        })

    results.sort(key=lambda g: g["resource_count"], reverse=True)
    return results
