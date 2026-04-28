"""Deterministic HCL patcher — swap shape/size attributes on resource
blocks without re-running any LLM writer.

Use case: the Plan UI lets users pick between "direct 1:1" and
"rightsized" per compute/database resource. When they hit *Apply*, this
module walks the already-generated .tf files, finds each block by its
``aws_source_id`` marker, and rewrites its sizing attributes in place.
The bundle is otherwise unchanged; no skill re-runs, no model calls.

Block identification: writers are prompted to include a
``# aws_source_id = <id>`` trailing comment and ``freeform_tags =
{ aws_source_id = "<id>" }`` on every resource block. The patcher
locates blocks by either marker (comment preferred; tag as fallback).

Per-resource-type attribute swap table lives in ``_SHAPE_PATCHERS``.
Compute and database-system shapes are the common case. EBS volume
sizing is covered too. Anything not in the table is reported as a
warning — the patcher never silently leaves a selection unapplied.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from app.services.synthesis_composer import HclBlock, _extract_blocks

logger = logging.getLogger(__name__)


# ─── Result type ─────────────────────────────────────────────────────────

@dataclass
class PatchResult:
    files: dict[str, str] = field(default_factory=dict)          # updated bundle
    applied: list[dict] = field(default_factory=list)            # {aws_source_id, file, old, new}
    warnings: list[str] = field(default_factory=list)            # what we couldn't patch


# ─── Public entry point ──────────────────────────────────────────────────

def apply_overrides(
    bundle: dict[str, str],
    overrides: dict[str, dict[str, Any]],
) -> PatchResult:
    """Patch the bundle's .tf files to reflect user shape selections.

    Args:
        bundle: ``{filename: content}`` as produced by the plan orchestrator.
            Only entries ending in ``.tf`` are considered. Non-tf entries
            are passed through unchanged.
        overrides: ``{aws_source_id: {"shape": "VM.Standard.E5.Flex",
            "ocpus": 4, "memory_gb": 16, "size_gb": 200}}``. Only the keys
            present are patched; missing keys are left alone. Extra keys
            are ignored so compute/volume overrides can share a schema.

    Returns:
        PatchResult with the new bundle, a list of applied patches, and a
        list of warnings for anything the patcher couldn't locate or
        didn't know how to rewrite.
    """
    result = PatchResult(files=dict(bundle))
    if not overrides:
        return result

    # First pass — index every .tf block by its aws_source_id.
    # ``block_index[source_id] = (filename, block)``.
    block_index: dict[str, tuple[str, HclBlock]] = {}
    for filename, content in bundle.items():
        if not filename.endswith(".tf") or not isinstance(content, str):
            continue
        for blk in _extract_blocks(content):
            if blk.kind not in ("resource", "module"):
                continue
            sid = _source_id_of(blk)
            if sid:
                block_index.setdefault(sid, (filename, blk))

    # Second pass — for each override, find the block and rewrite.
    # We group by filename so we only rebuild each file once.
    per_file_edits: dict[str, list[tuple[HclBlock, str]]] = {}
    for sid, override in overrides.items():
        hit = block_index.get(sid)
        if hit is None:
            result.warnings.append(
                f"aws_source_id '{sid}' not found in any .tf file — "
                "override skipped. Writer may have missed the tagging "
                "instruction; re-run plan generation."
            )
            continue
        filename, blk = hit
        patcher = _SHAPE_PATCHERS.get(blk.labels[0]) if blk.labels else None
        if patcher is None:
            result.warnings.append(
                f"No shape patcher registered for resource type "
                f"'{blk.labels[0] if blk.labels else '?'}' "
                f"(aws_source_id={sid}) — override skipped."
            )
            continue
        new_body, changes = patcher(blk.body, override)
        if not changes:
            # Patcher ran but didn't find attributes to change. Usually
            # means the override carried keys the type doesn't support
            # (e.g. ocpus on an EBS volume). Silent skip is fine.
            continue
        per_file_edits.setdefault(filename, []).append((blk, new_body))
        for attr, old_val, new_val in changes:
            result.applied.append({
                "aws_source_id": sid,
                "file": filename,
                "resource_type": blk.labels[0],
                "attribute": attr,
                "old": old_val,
                "new": new_val,
            })

    # Third pass — rebuild each file by splicing the new block bodies
    # back in. We swap by exact-body match against the original content,
    # so the only requirement is that two blocks don't share identical
    # bodies in the same file (they won't — the writer's labels differ).
    for filename, edits in per_file_edits.items():
        content = result.files[filename]
        for blk, new_body in edits:
            if blk.body in content:
                content = content.replace(blk.body, new_body, 1)
            else:
                result.warnings.append(
                    f"Could not splice patched block '{'.'.join(blk.labels)}' "
                    f"into {filename} — body didn't match. "
                    "File left unchanged."
                )
        result.files[filename] = content

    return result


# ─── Finding a block's aws_source_id ─────────────────────────────────────

_COMMENT_RE = re.compile(r"#\s*aws_source_id\s*=\s*([^\s\n#]+)")
_TAG_RE = re.compile(r'aws_source_id\s*=\s*"([^"]+)"')


def _source_id_of(blk: HclBlock) -> str | None:
    """Extract aws_source_id from a block's body. Checks the trailing
    comment form first (``# aws_source_id = i-abc``), then the
    ``freeform_tags.aws_source_id`` attribute form."""
    m = _COMMENT_RE.search(blk.body)
    if m:
        return m.group(1).strip()
    m = _TAG_RE.search(blk.body)
    if m:
        return m.group(1).strip()
    return None


# ─── Per-resource-type patchers ──────────────────────────────────────────
#
# Each patcher takes ``(body, override)`` and returns
# ``(new_body, list[(attribute_name, old_value, new_value)])``.
# Keep the changes list truthy-when-something-actually-changed so the
# caller can skip no-ops without relying on string equality.

def _patch_oci_core_instance(
    body: str, override: dict[str, Any]
) -> tuple[str, list[tuple[str, str, str]]]:
    """Patch compute instance: shape, shape_config.ocpus, shape_config.memory_in_gbs."""
    changes: list[tuple[str, str, str]] = []
    new_body = body

    if "shape" in override:
        new_body, old_val = _replace_scalar_attr(new_body, "shape", f'"{override["shape"]}"')
        if old_val is not None and old_val.strip('"') != override["shape"]:
            changes.append(("shape", old_val, f'"{override["shape"]}"'))

    # shape_config { ocpus = N, memory_in_gbs = N }
    if "ocpus" in override:
        new_body, old_val = _replace_nested_scalar(new_body, "shape_config", "ocpus", str(override["ocpus"]))
        if old_val is not None and old_val != str(override["ocpus"]):
            changes.append(("shape_config.ocpus", old_val, str(override["ocpus"])))
    if "memory_gb" in override:
        new_body, old_val = _replace_nested_scalar(new_body, "shape_config", "memory_in_gbs", str(override["memory_gb"]))
        if old_val is not None and old_val != str(override["memory_gb"]):
            changes.append(("shape_config.memory_in_gbs", old_val, str(override["memory_gb"])))

    return new_body, changes


def _patch_oci_database_db_system(
    body: str, override: dict[str, Any]
) -> tuple[str, list[tuple[str, str, str]]]:
    """DB system: shape + cpu_core_count."""
    changes: list[tuple[str, str, str]] = []
    new_body = body
    if "shape" in override:
        new_body, old_val = _replace_scalar_attr(new_body, "shape", f'"{override["shape"]}"')
        if old_val is not None and old_val.strip('"') != override["shape"]:
            changes.append(("shape", old_val, f'"{override["shape"]}"'))
    if "ocpus" in override:
        new_body, old_val = _replace_scalar_attr(new_body, "cpu_core_count", str(override["ocpus"]))
        if old_val is not None and old_val != str(override["ocpus"]):
            changes.append(("cpu_core_count", old_val, str(override["ocpus"])))
    return new_body, changes


def _patch_oci_core_volume(
    body: str, override: dict[str, Any]
) -> tuple[str, list[tuple[str, str, str]]]:
    """Block volume: size_in_gbs, vpus_per_gb."""
    changes: list[tuple[str, str, str]] = []
    new_body = body
    if "size_gb" in override:
        new_body, old_val = _replace_scalar_attr(new_body, "size_in_gbs", str(override["size_gb"]))
        if old_val is not None and old_val != str(override["size_gb"]):
            changes.append(("size_in_gbs", old_val, str(override["size_gb"])))
    if "vpus_per_gb" in override:
        new_body, old_val = _replace_scalar_attr(new_body, "vpus_per_gb", str(override["vpus_per_gb"]))
        if old_val is not None and old_val != str(override["vpus_per_gb"]):
            changes.append(("vpus_per_gb", old_val, str(override["vpus_per_gb"])))
    return new_body, changes


_SHAPE_PATCHERS: dict[str, Callable[[str, dict], tuple[str, list[tuple[str, str, str]]]]] = {
    "oci_core_instance":           _patch_oci_core_instance,
    "oci_database_db_system":      _patch_oci_database_db_system,
    "oci_core_volume":             _patch_oci_core_volume,
}


# ─── Attribute-rewrite primitives ────────────────────────────────────────

def _replace_scalar_attr(body: str, attr: str, new_value: str) -> tuple[str, str | None]:
    """Replace the top-level ``<attr> = <value>`` line in ``body``. Returns
    the new body and the previous raw value string (or None if the attr
    wasn't found). Only matches attributes at the top level of the block
    (not nested inside sub-blocks).
    """
    # Match ``<attr> = <value>`` where value is everything to end of line
    # (up to an inline comment or newline). Anchored at start-of-line
    # with optional leading whitespace; requires at least one indent level
    # (2+ spaces / a tab) so we skip ``resource "oci_core_instance" ...``
    # header-level tokens like ``shape`` inside string labels are impossible
    # at BOL anyway.
    pattern = re.compile(
        rf'(^\s+{re.escape(attr)}\s*=\s*)([^\n#]+?)(\s*(?:#.*)?$)',
        re.MULTILINE,
    )
    m = pattern.search(body)
    if not m:
        return body, None
    old_raw = m.group(2).rstrip()
    new_body = pattern.sub(lambda mo: f"{mo.group(1)}{new_value}{mo.group(3)}", body, count=1)
    return new_body, old_raw


def _replace_nested_scalar(
    body: str, block_name: str, attr: str, new_value: str
) -> tuple[str, str | None]:
    """Replace ``<attr> = <value>`` inside a nested ``<block_name> { ... }``.
    Used for ``shape_config { ocpus = N }``. If the nested block isn't
    found, returns body unchanged.
    """
    # Find ``shape_config {`` and balance-match its closing brace.
    header = re.search(rf'^\s+{re.escape(block_name)}\s*\{{', body, re.MULTILINE)
    if not header:
        return body, None
    brace_open = body.find("{", header.end() - 1)
    depth = 0
    in_str = False
    esc = False
    end = -1
    for i in range(brace_open, len(body)):
        ch = body[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
    if end < 0:
        return body, None
    nested_body = body[brace_open:end]
    pattern = re.compile(
        rf'(^\s+{re.escape(attr)}\s*=\s*)([^\n#]+?)(\s*(?:#.*)?$)',
        re.MULTILINE,
    )
    m = pattern.search(nested_body)
    if not m:
        return body, None
    old_raw = m.group(2).rstrip()
    new_nested = pattern.sub(lambda mo: f"{mo.group(1)}{new_value}{mo.group(3)}", nested_body, count=1)
    return body[:brace_open] + new_nested + body[end:], old_raw
