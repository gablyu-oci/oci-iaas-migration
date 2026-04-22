"""Enrichment layer that turns a raw ``Resource`` row into a UI-friendly detail view.

Given a ``Resource`` + its ``raw_config`` JSON, produce a dict that the
frontend can render without re-implementing the joins. For each resource
type we surface:

- Structural fields lifted directly from raw_config (instance_type, engine,
  size_gb, etc.).
- Derived fields joined from the YAML mapping tables:
  * EC2 instance_type → vCPU / memory / arch / GPU (instance_shapes.yaml)
  * Any aws_type → OCI target + confidence + notes (resources.yaml)
- Optional rightsizing preview (OCI shape recommendation + cost) when the
  source is an EC2 instance — same math the assessment pipeline runs,
  exposed for browse-time inspection.

Kept pure (no DB / network) so it can run inline on API responses.
"""

from __future__ import annotations

from typing import Any

from app import mappings


# ─── Public entry point ──────────────────────────────────────────────────────

def enrich(
    aws_type: str | None,
    raw_config: dict | None,
    include_rightsizing: bool = True,
) -> dict[str, Any]:
    """Return a dict of UI-ready fields for one resource.

    Shape:
        {
          "oci_mapping": {...} | None,       # from resources.yaml
          "summary": {label → value},        # per-type compact summary
          "sections": [                      # per-type detail sections
            {"title": "...", "rows": [{label, value, hint?}]}
          ],
          "rightsizing": {...} | None,       # only for EC2
          "metrics": {...} | None,           # CloudWatch data if present
          "software_inventory": {...} | None # SSM data if present
        }
    """
    rc = raw_config or {}
    out: dict[str, Any] = {
        "oci_mapping": _oci_mapping(aws_type),
        "summary": {},
        "sections": [],
        "rightsizing": None,
        "metrics": rc.get("metrics"),
        "software_inventory": rc.get("software_inventory"),
    }

    builder = _BUILDERS.get(aws_type or "", _build_generic)
    summary, sections = builder(rc)
    out["summary"] = summary
    out["sections"] = sections

    if include_rightsizing and aws_type == "AWS::EC2::Instance":
        out["rightsizing"] = _rightsizing_for_ec2(rc)

    return out


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _oci_mapping(aws_type: str | None) -> dict[str, Any] | None:
    if not aws_type:
        return None
    entry = mappings.resource_by_aws_type(aws_type)
    if not entry:
        return None
    return {
        "aws_type": aws_type,
        "oci_service": entry.get("oci_service"),
        "oci_resource_label": entry.get("oci_resource_label"),
        "oci_terraform": entry.get("oci_terraform"),
        "skill": entry.get("skill"),
        "confidence": entry.get("mapping_confidence"),
        "notes": entry.get("notes") or [],
        "gaps": entry.get("gaps") or [],
    }


def _shape_spec_for(instance_type: str) -> dict[str, Any] | None:
    """Join ``instance_type`` against the local shape catalog."""
    if not instance_type:
        return None
    specs = mappings.aws_instance_specs()
    spec = specs.get(instance_type)
    if not spec:
        return None
    return {
        "vcpus": spec.get("vcpus"),
        "memory_gb": spec.get("memory_gb"),
        "arch": spec.get("arch"),
        "family": spec.get("family"),
        "gpu": spec.get("gpu", False),
        "gpu_type": spec.get("gpu_type"),
        "gpu_count": spec.get("gpu_count"),
        "monthly_cost_usd_est": spec.get("monthly_cost_usd"),
        "local_nvme_gb": spec.get("local_nvme_gb"),
        "local_hdd_gb": spec.get("local_hdd_gb"),
    }


def _rightsizing_for_ec2(rc: dict) -> dict[str, Any] | None:
    """Best-effort OCI shape recommendation for one EC2 instance."""
    instance_type = rc.get("instance_type")
    if not instance_type:
        return None
    try:
        from app.services.rightsizing_engine import compute_rightsizing
    except ImportError:
        return None

    # If CloudWatch metrics were captured, feed their p95 into the rightsizer.
    metrics = rc.get("metrics") or {}
    cwargs: dict[str, float] = {}
    cpu = (metrics.get("CPUUtilization") or {}).get("p95")
    if cpu is not None:
        cwargs["cpu_p95"] = cpu
    mem = (metrics.get("mem_used_percent") or {}).get("p95")
    if mem is not None:
        cwargs["mem_p95"] = mem

    try:
        return compute_rightsizing(instance_type, metrics=cwargs or None)
    except Exception:  # noqa: BLE001 — never fail a detail render
        return None


def _row(label: str, value: Any, hint: str | None = None) -> dict[str, Any] | None:
    """Skip rows where the value is empty so the UI stays compact."""
    if value is None or value == "" or value == []:
        return None
    entry = {"label": label, "value": value}
    if hint:
        entry["hint"] = hint
    return entry


def _non_empty_rows(pairs: list[tuple]) -> list[dict]:
    rows: list[dict] = []
    for tup in pairs:
        if len(tup) == 2:
            label, value = tup
            r = _row(label, value)
        else:
            label, value, hint = tup
            r = _row(label, value, hint)
        if r is not None:
            rows.append(r)
    return rows


# ─── Per-type builders ───────────────────────────────────────────────────────
# Each returns (summary: dict, sections: list[{title, rows}]).


def _build_ec2(rc: dict) -> tuple[dict, list[dict]]:
    inst_type = rc.get("instance_type", "")
    spec = _shape_spec_for(inst_type)
    summary = {
        "Instance ID": rc.get("instance_id", ""),
        "Type": inst_type,
        "State": rc.get("state", ""),
        "AZ": rc.get("availability_zone", ""),
    }
    if spec:
        summary["vCPU"] = spec["vcpus"]
        summary["Memory (GB)"] = spec["memory_gb"]
        summary["Arch"] = spec["arch"]
        if spec.get("gpu"):
            summary["GPU"] = f"{spec.get('gpu_count', 1)}× {spec.get('gpu_type') or '?'}"

    sections: list[dict] = []
    sections.append({
        "title": "Compute",
        "rows": _non_empty_rows([
            ("Instance type", inst_type),
            ("vCPU", spec["vcpus"] if spec else None),
            ("Memory (GB)", spec["memory_gb"] if spec else None),
            ("Architecture", rc.get("architecture", "") or (spec and spec.get("arch"))),
            ("Family", spec and spec.get("family")),
            ("GPU", (spec and spec.get("gpu") and
                     f"{spec.get('gpu_count', 1)}× {spec.get('gpu_type')}") or None),
            ("Hypervisor", rc.get("hypervisor", "")),
            ("Virtualization", rc.get("virtualization_type", "")),
            ("Image ID", rc.get("image_id", "")),
            ("Key pair", rc.get("key_name", "")),
            ("Platform", rc.get("platform_details", "") or rc.get("platform", "")),
        ]),
    })
    sections.append({
        "title": "State",
        "rows": _non_empty_rows([
            ("Status", rc.get("state", "")),
            ("Reason", rc.get("state_reason", "")),
            ("Launched", rc.get("launch_time", "")),
            ("Monitoring", rc.get("monitoring_state", "")),
            ("EBS optimized", rc.get("ebs_optimized", False)),
        ]),
    })
    sections.append({
        "title": "Networking",
        "rows": _non_empty_rows([
            ("VPC", rc.get("vpc_id", "")),
            ("Subnet", rc.get("subnet_id", "")),
            ("Availability zone", rc.get("availability_zone", "")),
            ("Tenancy", rc.get("tenancy", "")),
            ("Private IP", rc.get("private_ip_address", "")),
            ("Public IP", rc.get("public_ip_address", "")),
            ("Private DNS", rc.get("private_dns_name", "")),
            ("Public DNS", rc.get("public_dns_name", "")),
            ("Security groups", ", ".join(rc.get("security_groups", []) or []) or None),
        ]),
    })
    bdms = rc.get("block_device_mappings", []) or []
    if bdms:
        sections.append({
            "title": f"Block devices ({len(bdms)})",
            "rows": [
                {"label": b.get("device_name", "?"),
                 "value": b.get("volume_id", "?"),
                 "hint": ("delete-on-term" if b.get("delete_on_termination") else "persistent")}
                for b in bdms
            ],
        })
    profile_arn = rc.get("iam_instance_profile_arn", "")
    if profile_arn:
        sections.append({
            "title": "IAM",
            "rows": _non_empty_rows([
                ("Instance profile", profile_arn),
                ("Root device type", rc.get("root_device_type", "")),
                ("Root device name", rc.get("root_device_name", "")),
            ]),
        })
    return summary, sections


def _build_ebs(rc: dict) -> tuple[dict, list[dict]]:
    summary = {
        "Volume ID": rc.get("volume_id", ""),
        "Size (GB)": rc.get("size_gb", 0),
        "Type": rc.get("volume_type", ""),
        "State": rc.get("state", ""),
    }
    sections = [{
        "title": "Volume",
        "rows": _non_empty_rows([
            ("Volume ID", rc.get("volume_id", "")),
            ("Size (GB)", rc.get("size_gb", 0)),
            ("Type", rc.get("volume_type", "")),
            ("IOPS", rc.get("iops", 0)),
            ("Throughput (MB/s)", rc.get("throughput_mbps", 0)),
            ("State", rc.get("state", "")),
            ("Encrypted", rc.get("encrypted", False)),
            ("KMS key", rc.get("kms_key_id", "")),
            ("Availability zone", rc.get("availability_zone", "")),
            ("Multi-attach", rc.get("multi_attach_enabled", False)),
            ("Created", rc.get("create_time", "")),
        ]),
    }]
    attachments = rc.get("attachments", []) or []
    if attachments:
        sections.append({
            "title": f"Attachments ({len(attachments)})",
            "rows": [
                {"label": a.get("device", "?"),
                 "value": a.get("instance_id", "?"),
                 "hint": a.get("state", "") + (" · delete-on-term"
                                                 if a.get("delete_on_termination") else "")}
                for a in attachments
            ],
        })
    return summary, sections


def _build_rds(rc: dict) -> tuple[dict, list[dict]]:
    engine = rc.get("engine", "")
    engine_version = rc.get("engine_version", "")
    summary = {
        "DB instance": rc.get("db_instance_id", ""),
        "Engine": f"{engine} {engine_version}".strip(),
        "Class": rc.get("db_instance_class", ""),
        "Storage (GB)": rc.get("allocated_storage_gb", 0),
        "Multi-AZ": rc.get("multi_az", False),
    }
    sections = [
        {
            "title": "Engine",
            "rows": _non_empty_rows([
                ("Engine", engine),
                ("Version", engine_version),
                ("License", rc.get("license_model", "")),
                ("DB name", rc.get("db_name", "")),
                ("Master user", rc.get("master_username", "")),
            ]),
        },
        {
            "title": "Compute + HA",
            "rows": _non_empty_rows([
                ("Instance class", rc.get("db_instance_class", "")),
                ("Availability zone", rc.get("availability_zone", "")),
                ("Secondary AZ", rc.get("secondary_availability_zone", "")),
                ("Multi-AZ", rc.get("multi_az", False)),
                ("Read replicas",
                 ", ".join(rc.get("read_replica_db_instance_identifiers", []) or []) or None),
                ("Replica of", rc.get("read_replica_source", "")),
            ]),
        },
        {
            "title": "Storage",
            "rows": _non_empty_rows([
                ("Allocated (GB)", rc.get("allocated_storage_gb", 0)),
                ("Max allocated (GB)", rc.get("max_allocated_storage_gb", 0)),
                ("Storage type", rc.get("storage_type", "")),
                ("IOPS", rc.get("iops", 0)),
                ("Throughput (MB/s)", rc.get("storage_throughput_mbps", 0)),
                ("Encrypted", rc.get("storage_encrypted", False)),
                ("KMS key", rc.get("kms_key_id", "")),
            ]),
        },
        {
            "title": "Backup + lifecycle",
            "rows": _non_empty_rows([
                ("Retention (days)", rc.get("backup_retention_period_days", 0)),
                ("Backup window", rc.get("preferred_backup_window", "")),
                ("Maintenance window", rc.get("preferred_maintenance_window", "")),
                ("Auto minor upgrade", rc.get("auto_minor_version_upgrade", False)),
                ("Deletion protection", rc.get("deletion_protection", False)),
                ("Performance Insights", rc.get("performance_insights_enabled", False)),
            ]),
        },
        {
            "title": "Networking",
            "rows": _non_empty_rows([
                ("VPC", rc.get("vpc_id", "")),
                ("Subnet group", rc.get("db_subnet_group_name", "")),
                ("Publicly accessible", rc.get("publicly_accessible", False)),
                ("Endpoint", rc.get("endpoint_address", "")),
                ("Port", rc.get("endpoint_port", 0)),
                ("Security groups",
                 ", ".join(rc.get("vpc_security_group_ids", []) or []) or None),
            ]),
        },
    ]
    return summary, sections


def _build_lambda(rc: dict) -> tuple[dict, list[dict]]:
    summary = {
        "Function": rc.get("function_name", ""),
        "Runtime": rc.get("runtime", "") or rc.get("package_type", ""),
        "Memory (MB)": rc.get("memory_size_mb", 0),
        "Timeout (s)": rc.get("timeout_seconds", 0),
    }
    sections = [
        {
            "title": "Runtime",
            "rows": _non_empty_rows([
                ("Runtime", rc.get("runtime", "")),
                ("Handler", rc.get("handler", "")),
                ("Architectures", ", ".join(rc.get("architectures", []) or []) or None),
                ("Package type", rc.get("package_type", "")),
                ("Memory (MB)", rc.get("memory_size_mb", 0)),
                ("Timeout (s)", rc.get("timeout_seconds", 0)),
                ("Ephemeral storage (MB)", rc.get("ephemeral_storage_mb", 0)),
            ]),
        },
        {
            "title": "Code",
            "rows": _non_empty_rows([
                ("Code size (bytes)", rc.get("code_size_bytes", 0)),
                ("SHA256", rc.get("code_sha256", "")),
                ("Last modified", rc.get("last_modified", "")),
                ("Layer count", rc.get("layer_count", 0)),
                ("Environment vars", rc.get("environment_variable_count", 0)),
                ("State", rc.get("state", "")),
                ("Tracing mode", rc.get("tracing_mode", "")),
                ("DLQ", rc.get("dead_letter_target_arn", "")),
            ]),
        },
        {
            "title": "Networking + IAM",
            "rows": _non_empty_rows([
                ("Role", rc.get("role_arn", "")),
                ("VPC", rc.get("vpc_id", "")),
                ("Subnets", ", ".join(rc.get("subnet_ids", []) or []) or None),
                ("Security groups", ", ".join(rc.get("security_group_ids", []) or []) or None),
                ("Reserved concurrency", rc.get("reserved_concurrent_executions", 0)),
            ]),
        },
    ]
    env_keys = rc.get("environment_variable_keys", []) or []
    if env_keys:
        sections.append({
            "title": f"Environment variable keys ({len(env_keys)})",
            "rows": [{"label": k, "value": "•"} for k in sorted(env_keys)],
        })
    return summary, sections


def _build_s3(rc: dict) -> tuple[dict, list[dict]]:
    pab = rc.get("public_access_block", {}) or {}
    any_public_blocked = any(pab.values()) if pab else False
    summary = {
        "Bucket": rc.get("bucket_name", ""),
        "Region": rc.get("region", ""),
        "Versioning": rc.get("versioning_status", "Disabled"),
        "Encryption": rc.get("encryption_type", "none"),
    }
    sections = [{
        "title": "Bucket",
        "rows": _non_empty_rows([
            ("Name", rc.get("bucket_name", "")),
            ("Region", rc.get("region", "")),
            ("Created", rc.get("creation_date", "")),
            ("Versioning", rc.get("versioning_status", "Disabled")),
            ("Encryption type", rc.get("encryption_type", "none")),
            ("KMS key", rc.get("encryption_kms_key", "")),
            ("Public access blocks",
             "all blocked" if all(pab.values()) else
             ("partial" if any_public_blocked else "none"),
             "aggregates the four block_public_* flags"),
        ]),
    }]
    return summary, sections


def _build_vpc(rc: dict) -> tuple[dict, list[dict]]:
    subnets = rc.get("subnets", []) or []
    summary = {
        "VPC": rc.get("vpc_id", ""),
        "CIDR": rc.get("cidr_block", ""),
        "Subnets": len(subnets),
    }
    sections = [
        {
            "title": "VPC",
            "rows": _non_empty_rows([
                ("VPC ID", rc.get("vpc_id", "")),
                ("CIDR", rc.get("cidr_block", "")),
            ]),
        }
    ]
    if subnets:
        sections.append({
            "title": f"Subnets ({len(subnets)})",
            "rows": [
                {"label": s.get("subnet_id", "?"),
                 "value": f"{s.get('cidr_block', '?')}  ·  {s.get('availability_zone', '?')}"}
                for s in subnets
            ],
        })
    return summary, sections


def _build_subnet(rc: dict) -> tuple[dict, list[dict]]:
    summary = {
        "Subnet": rc.get("subnet_id", ""),
        "VPC": rc.get("vpc_id", ""),
        "CIDR": rc.get("cidr_block", ""),
        "AZ": rc.get("availability_zone", ""),
    }
    sections = [{
        "title": "Subnet",
        "rows": _non_empty_rows([
            ("Subnet ID", rc.get("subnet_id", "")),
            ("VPC", rc.get("vpc_id", "")),
            ("CIDR", rc.get("cidr_block", "")),
            ("Availability zone", rc.get("availability_zone", "")),
            ("Map public IP on launch", rc.get("map_public_ip_on_launch", False)),
            ("Available IPs", rc.get("available_ip_count", 0)),
        ]),
    }]
    return summary, sections


def _build_security_group(rc: dict) -> tuple[dict, list[dict]]:
    ingress = rc.get("ingress_rules", []) or []
    egress = rc.get("egress_rules", []) or []
    summary = {
        "Group": rc.get("group_name", "") or rc.get("group_id", ""),
        "VPC": rc.get("vpc_id", ""),
        "Ingress rules": len(ingress),
        "Egress rules": len(egress),
    }
    sections = [{
        "title": "Group",
        "rows": _non_empty_rows([
            ("Group ID", rc.get("group_id", "")),
            ("Name", rc.get("group_name", "")),
            ("VPC", rc.get("vpc_id", "")),
            ("Description", rc.get("description", "")),
        ]),
    }]
    # Short-form rule rendering: protocol + port + source/dest
    def _rule_summary(r: dict) -> str:
        proto = r.get("IpProtocol", "?")
        if proto == "-1":
            proto = "all"
        from_p = r.get("FromPort")
        to_p = r.get("ToPort")
        port = (f"{from_p}-{to_p}" if from_p != to_p else str(from_p)) if from_p is not None else "-"
        cidrs = [p.get("CidrIp", "") for p in r.get("IpRanges", [])]
        cidrs += [p.get("CidrIpv6", "") for p in r.get("Ipv6Ranges", [])]
        sg_refs = [p.get("GroupId", "") for p in r.get("UserIdGroupPairs", [])]
        srcs = [s for s in cidrs + sg_refs if s]
        return f"{proto}:{port} ← {', '.join(srcs) or 'any'}"
    if ingress:
        sections.append({
            "title": f"Ingress ({len(ingress)})",
            "rows": [{"label": f"rule #{i+1}", "value": _rule_summary(r)}
                     for i, r in enumerate(ingress)],
        })
    if egress:
        sections.append({
            "title": f"Egress ({len(egress)})",
            "rows": [{"label": f"rule #{i+1}", "value": _rule_summary(r)}
                     for i, r in enumerate(egress)],
        })
    return summary, sections


def _build_asg(rc: dict) -> tuple[dict, list[dict]]:
    summary = {
        "ASG": rc.get("asg_name", ""),
        "Min": rc.get("min_size", 0),
        "Max": rc.get("max_size", 0),
        "Desired": rc.get("desired_capacity", 0),
    }
    sections = [{
        "title": "Auto scaling",
        "rows": _non_empty_rows([
            ("Name", rc.get("asg_name", "")),
            ("Min", rc.get("min_size", 0)),
            ("Max", rc.get("max_size", 0)),
            ("Desired", rc.get("desired_capacity", 0)),
            ("Instances", len(rc.get("instance_ids", []) or [])),
        ]),
    }]
    return summary, sections


def _build_lb(rc: dict) -> tuple[dict, list[dict]]:
    summary = {
        "Load balancer": rc.get("name", ""),
        "Type": rc.get("type", ""),
        "DNS": rc.get("dns_name", ""),
    }
    sections = [{
        "title": "Load balancer",
        "rows": _non_empty_rows([
            ("Name", rc.get("name", "")),
            ("Type", rc.get("type", "")),
            ("DNS name", rc.get("dns_name", "")),
            ("VPC", rc.get("vpc_id", "")),
        ]),
    }]
    return summary, sections


def _build_target_group(rc: dict) -> tuple[dict, list[dict]]:
    hc = rc.get("health_check", {}) or {}
    summary = {
        "Target group": rc.get("target_group_name", ""),
        "Protocol": rc.get("protocol", ""),
        "Port": rc.get("port", ""),
    }
    sections = [
        {
            "title": "Target group",
            "rows": _non_empty_rows([
                ("Name", rc.get("target_group_name", "")),
                ("Protocol", rc.get("protocol", "")),
                ("Port", rc.get("port", "")),
                ("Target type", rc.get("target_type", "")),
                ("VPC", rc.get("vpc_id", "")),
            ]),
        },
        {
            "title": "Health check",
            "rows": _non_empty_rows([
                ("Protocol", hc.get("protocol", "")),
                ("Port", hc.get("port", "")),
                ("Path", hc.get("path", "")),
                ("Interval (s)", hc.get("interval_seconds", "")),
                ("Timeout (s)", hc.get("timeout_seconds", "")),
                ("Healthy threshold", hc.get("healthy_threshold", "")),
                ("Unhealthy threshold", hc.get("unhealthy_threshold", "")),
            ]),
        },
    ]
    return summary, sections


def _build_eni(rc: dict) -> tuple[dict, list[dict]]:
    summary = {
        "ENI": rc.get("interface_id", ""),
        "Subnet": rc.get("subnet_id", ""),
        "Status": rc.get("status", ""),
    }
    sections = [{
        "title": "Network interface",
        "rows": _non_empty_rows([
            ("Interface ID", rc.get("interface_id", "")),
            ("Subnet", rc.get("subnet_id", "")),
            ("VPC", rc.get("vpc_id", "")),
            ("Private IP", rc.get("private_ip", "")),
            ("Public IP", rc.get("public_ip", "")),
            ("MAC", rc.get("mac_address", "")),
            ("Status", rc.get("status", "")),
            ("Description", rc.get("description", "")),
        ]),
    }]
    return summary, sections


def _build_generic(rc: dict) -> tuple[dict, list[dict]]:
    """Fallback for resource types without a dedicated builder.

    Lifts small-scalar fields to the summary + dumps the rest into one section.
    """
    scalar_bits: list[tuple] = []
    other_bits: list[tuple] = []
    for k, v in rc.items():
        if k in ("Tags", "raw_config"):
            continue
        if isinstance(v, (str, int, float, bool)) and k not in ("name",):
            scalar_bits.append((_humanize(k), v))
        elif isinstance(v, list) and all(isinstance(x, (str, int)) for x in v):
            if v:
                other_bits.append((_humanize(k), ", ".join(str(x) for x in v)))

    summary = {
        _humanize(k): v
        for k, v in list(rc.items())[:4]
        if isinstance(v, (str, int, float, bool))
    }
    sections = [
        {"title": "Properties", "rows": _non_empty_rows(scalar_bits + other_bits)},
    ]
    return summary, sections


def _humanize(key: str) -> str:
    return key.replace("_", " ").capitalize()


_BUILDERS: dict[str, Any] = {
    "AWS::EC2::Instance":                        _build_ec2,
    "AWS::EC2::Volume":                          _build_ebs,
    "AWS::RDS::DBInstance":                      _build_rds,
    "AWS::Lambda::Function":                     _build_lambda,
    "AWS::S3::Bucket":                           _build_s3,
    "AWS::EC2::VPC":                             _build_vpc,
    "AWS::EC2::Subnet":                          _build_subnet,
    "AWS::EC2::SecurityGroup":                   _build_security_group,
    "AWS::AutoScaling::AutoScalingGroup":        _build_asg,
    "AWS::ElasticLoadBalancingV2::LoadBalancer": _build_lb,
    "AWS::ElasticLoadBalancingV2::TargetGroup":  _build_target_group,
    "AWS::EC2::NetworkInterface":                _build_eni,
}
