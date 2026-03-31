"""Deterministic AWS-to-OCI resource mapping service.

Computes a clear mapping table for a set of AWS resources to their OCI
equivalents, pulling from existing rightsizing, OS compat, and skill
mapping data.  No LLM calls -- purely algorithmic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any

logger = logging.getLogger(__name__)

# ── Volume type mapping (from storage_translation skill) ──────────────────────
_VOLUME_TYPE_MAP = {
    "gp3": ("OCI Block Volume — Balanced", 10),
    "gp2": ("OCI Block Volume — Balanced", 10),
    "io1": ("OCI Block Volume — High Performance", 20),
    "io2": ("OCI Block Volume — High Performance", 20),
    "st1": ("OCI Block Volume — Low Cost", 0),
    "sc1": ("OCI Block Volume — Low Cost", 0),
}

# ── Database engine mapping (from database_translation skill) ─────────────────
_DB_ENGINE_MAP = {
    "postgres":  ("OCI Database — PostgreSQL", "oci_database_db_system"),
    "mysql":     ("OCI MySQL HeatWave", "oci_mysql_mysql_db_system"),
    "mariadb":   ("OCI MySQL HeatWave", "oci_mysql_mysql_db_system"),
    "oracle-ee": ("OCI Database — Oracle", "oci_database_db_system"),
    "oracle-se2":("OCI Database — Oracle", "oci_database_db_system"),
    "sqlserver": ("OCI Compute (self-managed)", "oci_core_instance"),
    "aurora-postgresql": ("OCI Autonomous Database (ATP)", "oci_database_autonomous_database"),
    "aurora-mysql": ("OCI MySQL HeatWave", "oci_mysql_mysql_db_system"),
}

# ── Network resource mapping ─────────────────────────────────────────────────
_NETWORK_MAP = {
    "AWS::EC2::VPC":              ("OCI VCN", "oci_core_vcn"),
    "AWS::EC2::Subnet":           ("OCI Subnet", "oci_core_subnet"),
    "AWS::EC2::SecurityGroup":    ("OCI Network Security Group", "oci_core_network_security_group"),
    "AWS::EC2::NetworkInterface": ("OCI VNIC Attachment", "oci_core_vnic_attachment"),
    "AWS::EC2::InternetGateway":  ("OCI Internet Gateway", "oci_core_internet_gateway"),
    "AWS::EC2::NatGateway":       ("OCI NAT Gateway", "oci_core_nat_gateway"),
}

# ── Local database detection keywords ────────────────────────────────────────
_LOCAL_DB_KEYWORDS = {
    "mariadb": ("MariaDB", "OCI MySQL HeatWave"),
    "mysql":   ("MySQL", "OCI MySQL HeatWave"),
    "postgres": ("PostgreSQL", "OCI Database — PostgreSQL"),
    "postgresql": ("PostgreSQL", "OCI Database — PostgreSQL"),
    "mongodb": ("MongoDB", "OCI NoSQL / self-managed"),
    "redis":   ("Redis", "OCI Cache with Redis"),
    "sqlite":  ("SQLite", "OCI MySQL HeatWave (upgrade)"),
}


@dataclass
class ResourceMappingEntry:
    aws_resource_id: str
    aws_type: str
    aws_name: str
    aws_config_summary: str
    oci_resource_type: str
    oci_shape: str
    oci_config_summary: str
    mapping_confidence: str  # high, medium, low
    notes: list[str]
    gaps: list[str]
    aws_monthly_cost: float | None = None
    oci_monthly_cost: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def compute_resource_mapping(
    resources: list[dict[str, Any]],
    resource_assessments: dict[str, dict[str, Any]] | None = None,
    software_inventory: dict[str, dict[str, Any]] | None = None,
) -> list[ResourceMappingEntry]:
    """Compute AWS → OCI mapping for a list of resources.

    Args:
        resources: Resource dicts with id, name, aws_type, raw_config.
        resource_assessments: Optional mapping of resource_id -> ResourceAssessment
            fields (recommended_oci_shape, recommended_oci_ocpus, etc.)
        software_inventory: Optional mapping of resource_id -> software inventory
            from SSM (applications list, etc.)

    Returns:
        List of ResourceMappingEntry, one per resource + detected local DBs.
    """
    from app.services.rightsizing_engine import AWS_INSTANCE_SPECS

    assessments = resource_assessments or {}
    inventory = software_inventory or {}
    entries: list[ResourceMappingEntry] = []
    seen_local_dbs: set[str] = set()

    for r in resources:
        rid = str(r.get("id", ""))
        aws_type = r.get("aws_type", "")
        name = r.get("name", "") or rid[:12]
        raw = r.get("raw_config") or {}
        ra = assessments.get(rid, {})

        if "EC2::Instance" in aws_type:
            entries.append(_map_ec2(rid, name, raw, ra))
            # Check for local databases in software inventory
            inv = inventory.get(rid, {})
            apps = inv.get("applications", [])
            for app in apps:
                app_name = (app.get("Name") or app.get("name") or "").lower()
                for keyword, (db_name, oci_target) in _LOCAL_DB_KEYWORDS.items():
                    if keyword in app_name and keyword not in seen_local_dbs:
                        seen_local_dbs.add(keyword)
                        version = app.get("Version") or app.get("version") or "unknown"
                        entries.append(ResourceMappingEntry(
                            aws_resource_id=rid,
                            aws_type=f"Local DB ({db_name})",
                            aws_name=f"{db_name} {version} on {name}",
                            aws_config_summary=f"Detected via SSM inventory on instance {name}",
                            oci_resource_type=oci_target,
                            oci_shape="",
                            oci_config_summary=f"Migrate data via mysqldump/pg_dump → import to {oci_target}",
                            mapping_confidence="medium",
                            notes=[
                                f"Local {db_name} detected on EC2 instance",
                                "Requires data migration — not just infrastructure lift-and-shift",
                                "Consider using OCI Database Migration Service or manual dump/restore",
                            ],
                            gaps=[
                                "Database size unknown — run disk usage check before migration",
                                "Application connection strings must be updated post-migration",
                            ],
                        ))

        elif "EC2::Volume" in aws_type:
            entries.append(_map_ebs(rid, name, raw))

        elif "RDS" in aws_type or "Aurora" in aws_type:
            entries.append(_map_rds(rid, name, raw, ra))

        elif "CloudFormation::Stack" in aws_type:
            entries.append(ResourceMappingEntry(
                aws_resource_id=rid,
                aws_type=aws_type,
                aws_name=name,
                aws_config_summary=f"Stack: {name}",
                oci_resource_type="Terraform Configuration",
                oci_shape="",
                oci_config_summary="Convert CloudFormation template to Terraform HCL for OCI provider",
                mapping_confidence="high",
                notes=["CFN → Terraform translation available via cfn_terraform skill"],
                gaps=[],
            ))

        elif "Lambda" in aws_type:
            entries.append(ResourceMappingEntry(
                aws_resource_id=rid,
                aws_type=aws_type,
                aws_name=name,
                aws_config_summary=f"Function: {name}",
                oci_resource_type="OCI Functions",
                oci_shape="",
                oci_config_summary="Repackage as OCI Functions (Fn Project compatible)",
                mapping_confidence="medium",
                notes=["OCI Functions uses Fn Project runtime", "May need code changes for SDK/API calls"],
                gaps=["Lambda layers not supported in OCI Functions", "Event source mappings need manual reconfiguration"],
            ))

        elif "ElasticLoadBalancing" in aws_type or "LoadBalancer" in aws_type:
            lb_type = raw.get("Type", "application")
            oci_type = "OCI Load Balancer" if lb_type == "application" else "OCI Network Load Balancer"
            entries.append(ResourceMappingEntry(
                aws_resource_id=rid,
                aws_type=aws_type,
                aws_name=name,
                aws_config_summary=f"{lb_type} load balancer",
                oci_resource_type=oci_type,
                oci_shape="Flexible (10-100 Mbps)",
                oci_config_summary=f"Migrate to {oci_type} with flexible shape",
                mapping_confidence="high",
                notes=[],
                gaps=["SSL certificates must be imported to OCI Certificate Service"],
            ))

        elif "IAM" in aws_type:
            entries.append(ResourceMappingEntry(
                aws_resource_id=rid,
                aws_type=aws_type,
                aws_name=name,
                aws_config_summary=f"IAM: {name}",
                oci_resource_type="OCI IAM Policy",
                oci_shape="",
                oci_config_summary="Translate IAM actions to OCI policy verbs (inspect/read/use/manage)",
                mapping_confidence="medium",
                notes=["OCI uses verb-based permissions, not action-based"],
                gaps=["Cross-account IAM roles → use OCI tenancy federation"],
            ))

        elif aws_type in _NETWORK_MAP:
            oci_name, oci_tf = _NETWORK_MAP[aws_type]
            entries.append(_map_network(rid, name, aws_type, raw, oci_name, oci_tf))

        else:
            entries.append(ResourceMappingEntry(
                aws_resource_id=rid,
                aws_type=aws_type,
                aws_name=name,
                aws_config_summary="",
                oci_resource_type="Manual mapping required",
                oci_shape="",
                oci_config_summary="No automated mapping available for this resource type",
                mapping_confidence="low",
                notes=[],
                gaps=[f"No OCI equivalent mapping defined for {aws_type}"],
            ))

    return entries


def _map_ec2(rid: str, name: str, raw: dict, ra: dict) -> ResourceMappingEntry:
    from app.services.rightsizing_engine import AWS_INSTANCE_SPECS

    instance_type = raw.get("instance_type") or raw.get("InstanceType") or ""
    aws_spec = AWS_INSTANCE_SPECS.get(instance_type, {})
    vcpus = aws_spec.get("vcpus", "?")
    mem = aws_spec.get("memory_gb", "?")
    aws_cost = aws_spec.get("monthly_cost_usd")

    oci_shape = ra.get("recommended_oci_shape", "VM.Standard.E5.Flex")
    oci_ocpus = ra.get("recommended_oci_ocpus", 1)
    oci_mem = ra.get("recommended_oci_memory_gb", 2)
    oci_cost = ra.get("projected_oci_monthly_cost_usd")

    os_status = ra.get("os_compat_status", "unknown")
    notes = []
    gaps = []
    if os_status == "compatible":
        notes.append("OS is compatible with OCI")
    elif os_status == "needs_conversion":
        notes.append("OS needs conversion (e.g., CentOS → Oracle Linux)")
    elif os_status == "unknown":
        gaps.append("OS compatibility not determined — run SSM inventory")

    confidence = "high" if oci_shape and aws_spec else "medium" if oci_shape else "low"

    return ResourceMappingEntry(
        aws_resource_id=rid,
        aws_type="AWS::EC2::Instance",
        aws_name=name or instance_type,
        aws_config_summary=f"{instance_type} ({vcpus} vCPU, {mem} GB RAM)",
        oci_resource_type="OCI Compute Instance",
        oci_shape=oci_shape,
        oci_config_summary=f"{oci_shape} ({oci_ocpus} OCPU, {oci_mem} GB RAM)",
        mapping_confidence=confidence,
        notes=notes,
        gaps=gaps,
        aws_monthly_cost=aws_cost,
        oci_monthly_cost=oci_cost,
    )


def _map_ebs(rid: str, name: str, raw: dict) -> ResourceMappingEntry:
    vol_type = raw.get("volume_type") or raw.get("VolumeType") or "gp2"
    size_gb = raw.get("size_gb") or raw.get("Size") or 0
    encrypted = raw.get("encrypted") or raw.get("Encrypted") or False

    oci_desc, vpus = _VOLUME_TYPE_MAP.get(vol_type, ("OCI Block Volume — Balanced", 10))

    return ResourceMappingEntry(
        aws_resource_id=rid,
        aws_type="AWS::EC2::Volume",
        aws_name=name or f"vol-{rid[:8]}",
        aws_config_summary=f"{vol_type} {size_gb} GB" + (" (encrypted)" if encrypted else ""),
        oci_resource_type="OCI Block Volume",
        oci_shape="",
        oci_config_summary=f"{size_gb} GB, vpus_per_gb={vpus} ({oci_desc})",
        mapping_confidence="high",
        notes=[
            "OCI encrypts all block volumes by default",
            f"Attachment type: paravirtualized (standard for VM shapes)",
        ],
        gaps=[],
    )


def _map_rds(rid: str, name: str, raw: dict, ra: dict) -> ResourceMappingEntry:
    engine = raw.get("engine") or raw.get("Engine") or ""
    engine_key = engine.lower().replace(" ", "-")
    instance_class = raw.get("db_instance_class") or raw.get("DBInstanceClass") or ""
    storage_gb = raw.get("allocated_storage") or raw.get("AllocatedStorage") or 0
    multi_az = raw.get("multi_az") or raw.get("MultiAZ") or False

    oci_name, oci_tf = _DB_ENGINE_MAP.get(engine_key, ("Manual mapping required", ""))

    notes = []
    gaps = []
    if multi_az:
        notes.append("Multi-AZ → 2-node OCI DB System for HA")
    if "sqlserver" in engine_key:
        gaps.append("No managed SQL Server on OCI — requires self-hosted on Compute")

    return ResourceMappingEntry(
        aws_resource_id=rid,
        aws_type="AWS::RDS::DBInstance",
        aws_name=name,
        aws_config_summary=f"{engine} ({instance_class}), {storage_gb} GB" + (", Multi-AZ" if multi_az else ""),
        oci_resource_type=oci_name,
        oci_shape=oci_tf,
        oci_config_summary=f"Migrate to {oci_name}, {storage_gb} GB storage",
        mapping_confidence="high" if oci_tf else "low",
        notes=notes,
        gaps=gaps,
    )


def _map_network(
    rid: str, name: str, aws_type: str, raw: dict,
    oci_name: str, oci_tf: str,
) -> ResourceMappingEntry:
    notes = []
    config_summary = ""

    if "VPC" in aws_type:
        cidr = raw.get("cidr_block") or raw.get("CidrBlock") or ""
        config_summary = f"CIDR: {cidr}" if cidr else ""
        notes.append("OCI VCN is regional (spans all ADs)")

    elif "Subnet" in aws_type:
        cidr = raw.get("cidr_block") or raw.get("CidrBlock") or ""
        config_summary = f"CIDR: {cidr}" if cidr else ""
        notes.append("OCI subnets are regional, not per-AZ")

    elif "SecurityGroup" in aws_type:
        notes.append("OCI uses NSGs (preferred) or Security Lists")

    return ResourceMappingEntry(
        aws_resource_id=rid,
        aws_type=aws_type,
        aws_name=name,
        aws_config_summary=config_summary,
        oci_resource_type=oci_name,
        oci_shape=oci_tf,
        oci_config_summary=f"Migrate to {oci_name}",
        mapping_confidence="high",
        notes=notes,
        gaps=[],
    )


# ── LLM Review of Resource Mapping ──────────────────────────────────────────

_REVIEW_SYSTEM = """\
You are an expert AWS-to-OCI migration architect. Review and improve this \
resource mapping table produced by an automated mapper.

For each resource, verify the OCI target is correct and improve:
- Better OCI configuration recommendations (shape sizing, performance tier)
- Migration-specific notes (data migration needs, application changes required)
- Gaps the automated mapper missed (dependencies, licensing, feature parity)
- Cost optimization suggestions

IMPORTANT RULES:
- Do NOT add new resources that are not in the original mapping.
- Do NOT invent recommended services, networking, load balancers, or storage \
  that don't exist in the source AWS environment.
- Only improve the existing entries — fix incorrect mappings, add better notes, \
  refine OCI configuration details.
- Return EXACTLY the same number of entries as the input.

Return ONLY a JSON array of objects with this schema:
{
  "aws_resource_id": "original ID",
  "aws_type": "type",
  "aws_name": "name",
  "aws_config_summary": "summary",
  "oci_resource_type": "OCI target",
  "oci_shape": "shape or empty",
  "oci_config_summary": "detailed OCI config",
  "mapping_confidence": "high|medium|low",
  "notes": ["note1", "note2"],
  "gaps": ["gap1"],
  "aws_monthly_cost": null,
  "oci_monthly_cost": null
}

Include ALL original entries (improved) plus any NEW entries you want to add.
"""


def review_mapping_with_llm(
    entries: list[ResourceMappingEntry],
    workload_name: str,
    anthropic_client,
) -> list[ResourceMappingEntry]:
    """LLM review pass over the deterministic mapping.

    Takes the draft mapping entries, sends them to Claude for review
    and enrichment, and returns the improved list.
    """
    import json
    import time

    draft_json = json.dumps([e.to_dict() for e in entries], indent=2)

    prompt = (
        f"## Workload: {workload_name}\n\n"
        f"## Draft Resource Mapping ({len(entries)} entries)\n\n"
        f"```json\n{draft_json}\n```\n\n"
        "Review this mapping. Improve notes, gaps, and OCI recommendations. "
        "Add missing entries for any detected local databases or services. "
        "Return the complete improved JSON array."
    )

    try:
        start = time.perf_counter()
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=_REVIEW_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        duration = time.perf_counter() - start
        logger.info("Resource mapping LLM review took %.1fs", duration)

        raw = response.content[0].text.strip()
        # Extract JSON from possible markdown code block
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                if stripped.startswith("["):
                    raw = stripped
                    break

        reviewed = json.loads(raw)
        if not isinstance(reviewed, list):
            logger.warning("LLM review returned non-list, keeping draft")
            return entries

        result = []
        for item in reviewed:
            result.append(ResourceMappingEntry(
                aws_resource_id=item.get("aws_resource_id", ""),
                aws_type=item.get("aws_type", ""),
                aws_name=item.get("aws_name", ""),
                aws_config_summary=item.get("aws_config_summary", ""),
                oci_resource_type=item.get("oci_resource_type", ""),
                oci_shape=item.get("oci_shape", ""),
                oci_config_summary=item.get("oci_config_summary", ""),
                mapping_confidence=item.get("mapping_confidence", "medium"),
                notes=item.get("notes", []),
                gaps=item.get("gaps", []),
                aws_monthly_cost=item.get("aws_monthly_cost"),
                oci_monthly_cost=item.get("oci_monthly_cost"),
            ))

        # Filter out any hallucinated entries not in the original set
        original_ids = {e.aws_resource_id for e in entries}
        filtered = [r for r in result if r.aws_resource_id in original_ids]

        logger.info(
            "LLM review: %d entries in, %d returned, %d after filtering",
            len(entries), len(result), len(filtered),
        )
        return filtered if filtered else entries  # Fall back to original if all filtered out

    except Exception as exc:
        logger.warning("LLM resource mapping review failed: %s — using draft", exc)
        return entries
