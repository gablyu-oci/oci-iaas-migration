"""OCM compatibility check for EC2 instances.

Given an EC2 instance's ``raw_config`` (plus, if captured, its SSM software
inventory), decide whether Oracle Cloud Migrations can migrate it — and
surface any prep steps the operator needs to do before replication runs.

Output contract (dict):

    {
      "supported":    bool,          # OCM can migrate this, possibly w/ prep
      "level":        "full" | "with_prep" | "manual" | "unsupported",
      "matched_rule": "<rule id>",   # which ocm_support.yaml entry matched
      "reason":       str,           # present when level == manual/unsupported
      "alternative":  str,           # what to do if OCM can't handle it
      "prep_steps":   [str, ...],    # operator checklist
      "notes":        [str, ...],    # advisory notes
      "detected_os":  str,           # best-effort guess of source OS
    }

Levels:
- ``full``        — OCM handles it out of the box. Route via ocm_handoff.
- ``with_prep``   — OCM handles it once the operator runs prep_steps (e.g.
                    rebuild initramfs with virtio for Amazon Linux).
- ``manual``      — OCM may work but needs human decisions (GPU shape
                    selection, BYOL verification). Flag but don't block.
- ``unsupported`` — OCM refuses this source (Graviton, instance-store root).
                    Caller should fall back to native ec2_translation.

Pure function — no DB, no network. Tests cover every rule path.
"""

from __future__ import annotations

from typing import Any

from app import mappings


_DEFAULT_RESULT_FIELDS = {
    "supported": False,
    "level": "manual",
    "matched_rule": None,
    "reason": "",
    "alternative": "",
    "prep_steps": [],
    "notes": [],
    "detected_os": "",
}


def _detected_os(raw_config: dict, software_inventory: dict | None) -> str:
    """Best-effort source-OS label for rule matching + UI display.

    Priority order: SSM inventory (most accurate, names the distro) → EC2
    PlatformDetails (e.g. "Linux/UNIX", "Windows"/"Windows Server 2022
    Datacenter") → EC2 Platform field ("windows" or missing).
    """
    inv = software_inventory or {}
    name = (inv.get("os_name") or "").strip()
    version = (inv.get("os_version") or "").strip()
    if name:
        return f"{name} {version}".strip()

    details = (raw_config.get("platform_details") or "").strip()
    if details and details.lower() != "linux/unix":
        return details

    platform = (raw_config.get("platform") or "").strip().lower()
    if platform == "windows":
        return "Windows"
    return "Linux (unspecified distribution)"


def _check_disqualifiers(raw_config: dict) -> dict[str, Any] | None:
    """Return a result dict if a hard disqualifier matches, else None."""
    for rule in mappings.ocm_disqualifiers():
        condition = rule.get("condition")
        values = set(rule.get("values") or [])
        field_val = raw_config.get(condition)
        if condition == "gpu":
            # 'gpu' in shape_spec is a bool; raw_config doesn't carry it
            # directly but the shape_spec lookup can. For now, inspect the
            # instance_type family as a heuristic.
            inst_type = (raw_config.get("instance_type") or "").lower()
            is_gpu = any(inst_type.startswith(f) for f in ("p3.", "p4", "p5", "g4", "g5", "g6"))
            field_val = is_gpu
        if field_val is None:
            continue
        # Normalize — values list stores lowercased strings / booleans
        if isinstance(field_val, str):
            field_val = field_val.lower()
        if field_val in values:
            return {
                **_DEFAULT_RESULT_FIELDS,
                "supported": rule.get("level") == "manual",
                "level": rule.get("level", "unsupported"),
                "matched_rule": rule.get("id"),
                "reason": rule.get("reason", ""),
                "alternative": rule.get("alternative", ""),
            }
    return None


def _match_os_rule(os_label: str, raw_config: dict) -> dict[str, Any] | None:
    """Walk os_support rules in declared order, first match wins."""
    platform = (raw_config.get("platform") or "").strip().lower()
    haystack = " ".join([
        os_label.lower(),
        (raw_config.get("platform_details") or "").lower(),
        platform,
    ])
    for rule in mappings.ocm_os_support_rules():
        required_platform = (rule.get("match_platform") or "").strip().lower()
        if required_platform and platform != required_platform:
            continue
        keywords = rule.get("match_keywords") or []
        # Keywords are alternatives — the rule matches if ANY of them is
        # present in the detected-OS haystack (e.g. "red hat" OR "rhel").
        if keywords and not any(kw.lower() in haystack for kw in keywords):
            continue
        # Passed the filters
        return {
            **_DEFAULT_RESULT_FIELDS,
            "supported": rule.get("level") in ("full", "with_prep"),
            "level": rule.get("level", "manual"),
            "matched_rule": rule.get("id"),
            "prep_steps": list(rule.get("prep_steps") or []),
            "notes": list(rule.get("notes") or []),
        }
    return None


def check_ec2_compatibility(
    raw_config: dict,
    software_inventory: dict | None = None,
    recommended_shape: str | None = None,
) -> dict[str, Any]:
    """Decide OCM compatibility for one EC2 instance.

    Factor in three tiers of checks:
      1. Hard source disqualifiers (ARM arch, instance-store root, GPU family).
      2. OS-rule match against ``ocm_support.yaml`` (full / with_prep / manual).
      3. Target-shape check — if ``recommended_shape`` is supplied (from
         the assessment's rightsizing), verify it's on OCM's published
         target whitelist. A source that passes 1-2 but whose recommended
         target shape isn't OCM-supported gets downgraded to ``manual``,
         surfacing an otherwise-silent incompatibility the operator would
         only discover at `oci cloud-migrations migration-plan execute` time.

    Args:
        raw_config: The EC2 row's raw_config dict (post-enrichment — must
            carry at least instance_type, architecture, platform,
            root_device_type).
        software_inventory: Optional SSM inventory payload captured at
            discovery time ({os_name, os_version, kernel, ...}).
        recommended_shape: Optional OCI shape name the rightsizer picked
            for this instance (e.g. ``VM.Standard.E5.Flex``). When None,
            only source-side checks run — matches the old behaviour.

    Returns:
        A dict matching the module docstring's contract.
    """
    raw_config = raw_config or {}
    detected = _detected_os(raw_config, software_inventory)

    # 1) Hard disqualifiers first (arch, instance-store, gpu → manual)
    hit = _check_disqualifiers(raw_config)
    if hit is not None:
        hit["detected_os"] = detected
        return hit

    # 2) OS rule match
    base = _match_os_rule(detected, raw_config)
    if base is None:
        # No OS rule matched — conservative default: manual review
        base = {
            **_DEFAULT_RESULT_FIELDS,
            "supported": False,
            "level": "manual",
            "reason": f"Could not classify source OS '{detected}'; no OCM support rule matched.",
            "alternative": "Verify the instance OS manually. Fall back to native ec2_translation if OCM doesn't cover it.",
        }
    base["detected_os"] = detected

    # 3) Target-shape check. The rightsizer may have picked a perfectly
    # reasonable OCI shape (e.g. VM.DenseIO.E5.Flex, VM.Standard.A2.Flex)
    # that OCM doesn't accept as a target — and the operator would only
    # find out when `migration-plan execute` throws. Catch it here so the
    # compatibility badge reflects the full end-to-end verdict.
    if recommended_shape and not is_shape_supported_by_ocm(recommended_shape):
        already_bad = base.get("level") in ("unsupported", "manual")
        base["supported"] = False
        base["level"] = "manual" if not already_bad else base["level"]
        shape_reason = (
            f"Recommended OCI shape '{recommended_shape}' is not on OCM's "
            f"target whitelist. OCM will refuse to provision the migration "
            f"plan on execute."
        )
        # Preserve any earlier reason; prepend the shape-specific one so it
        # reads first in the UI.
        base["reason"] = (
            shape_reason + (f" (also: {base['reason']})" if base.get("reason") else "")
        )
        base["alternative"] = (
            "Either (a) route this instance through native ec2_translation "
            "(emits oci_core_instance HCL directly), or (b) downshift the "
            "rightsizer to a whitelisted shape such as VM.Standard.E5.Flex "
            "/ VM.Standard3.Flex / VM.Optimized3.Flex / VM.Standard2.*."
        )

    return base


def is_shape_supported_by_ocm(shape: str | None) -> bool:
    """Check whether an OCI shape is in OCM's published target-shape whitelist."""
    if not shape:
        return False
    return shape in set(mappings.ocm_target_shapes())


def handoff_prereqs() -> list[dict[str, Any]]:
    """Return the handoff checklist the UI shows on the Plan results page."""
    return mappings.ocm_handoff_prereqs()
