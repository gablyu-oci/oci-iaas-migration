"""Deterministic synthesis merger — splits per-skill HCL into per-concern
``.tf`` files in one Terraform module.

Replaces the earlier LLM synthesis call that was prone to timing out on
big stacks (30+ resources → 20k+ output tokens → more than nginx's
5-min upstream window allows). This module walks the per-skill HCL the
writers already produced and re-homes each ``resource`` / ``data`` /
``module`` block into the file whose name matches its concern:

    terraform/network.tf        <- network_translation
    terraform/compute.tf        <- ec2_translation
    terraform/storage.tf        <- storage_translation
    terraform/database.tf       <- database_translation
    terraform/loadbalancer.tf   <- loadbalancer_translation
    terraform/iam.tf            <- iam_translation
    terraform/security.tf       <- security_translation
    terraform/serverless.tf     <- serverless_translation
    terraform/observability.tf  <- observability_translation
    terraform/cfn-<stack>.tf    <- cfn_terraform per-stack

All files live in the same directory so cross-file references resolve
naturally — ``oci_core_subnet.primary.id`` in ``compute.tf`` hits the
block declared in ``network.tf`` without any wiring.

Dedup rules:
- **Resource / data / module blocks**: labels must be unique across all
  output files. If two skills emit the same ``(type, label)`` pair, the
  composer renames the second one by appending ``_from_<skill>`` and
  records the collision in the returned warnings list. The writer
  prompts discourage collisions in the first place, but they happen
  (both ``network_translation`` and a CFN stack can each declare
  ``oci_core_vcn.main``).
- **Variables**: deduped by name. First definition wins; a later
  definition with different body is logged as a collision.
- **Outputs**: deduped by name, same rule.
- **Provider / terraform blocks**: dropped from every input and replaced
  with a single generated ``providers.tf`` so there's exactly one
  canonical provider config + required_providers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Skill → output concern file. Skills whose HCL lands in a sub-module
# (ocm_handoff_translation → terraform/ocm/) are handled separately and
# not listed here.
_SKILL_TO_CONCERN: dict[str, str] = {
    "network_translation":     "network.tf",
    "ec2_translation":         "compute.tf",
    "storage_translation":     "storage.tf",
    "database_translation":    "database.tf",
    "loadbalancer_translation":"loadbalancer.tf",
    "iam_translation":         "iam.tf",
    "security_translation":    "security.tf",
    "serverless_translation":  "serverless.tf",
    "observability_translation":"observability.tf",
}

# Top-level HCL block regexes. Not a full HCL parser — brace-balanced
# scanner finds the block body. Works for well-formed LLM output.
_BLOCK_TYPES = ("resource", "data", "module", "variable", "output",
                "provider", "terraform", "locals")


@dataclass
class HclBlock:
    """One top-level HCL block extracted from a file."""
    kind: str                          # "resource", "variable", …
    labels: tuple[str, ...]            # ("oci_core_vcn", "main") for resources
    body: str                          # full text including leading kind + labels

    @property
    def identity(self) -> tuple:
        """What makes this block unique for dedup purposes."""
        return (self.kind, self.labels)


@dataclass
class SynthesisResult:
    """What the composer returns to the orchestrator."""
    files: dict[str, str] = field(default_factory=dict)     # "network.tf" → content
    warnings: list[str] = field(default_factory=list)       # collision notes etc.
    skills_included: list[str] = field(default_factory=list)


# ─── HCL parsing ──────────────────────────────────────────────────────────

def _extract_blocks(hcl: str) -> list[HclBlock]:
    """Find every top-level block in ``hcl``. Brace-balanced, not perfect
    for every HCL edge case but sufficient for LLM-generated Terraform."""
    blocks: list[HclBlock] = []
    if not hcl:
        return blocks

    # Match: ``resource "type" "name" {`` / ``variable "name" {`` / etc.
    # Labels are quoted strings (typical LLM output). We capture the prefix
    # (kind + labels) up to the opening brace; brace-scan to find the match.
    header_re = re.compile(
        r'(?P<kind>' + "|".join(_BLOCK_TYPES) + r')\b'
        r'(?P<labels>(?:\s+"(?:[^"\\]|\\.)*")*)'
        r'\s*\{',
        re.MULTILINE,
    )
    label_re = re.compile(r'"((?:[^"\\]|\\.)*)"')

    pos = 0
    while True:
        m = header_re.search(hcl, pos)
        if not m:
            break
        start = m.start()
        brace_open = hcl.find("{", m.end() - 1)
        if brace_open < 0:
            pos = m.end()
            continue
        # Walk the body tracking brace depth, ignoring ones inside strings.
        i = brace_open
        depth = 0
        in_str = False
        esc = False
        end = -1
        while i < len(hcl):
            ch = hcl[i]
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
            i += 1
        if end < 0:
            pos = m.end()
            continue
        kind = m.group("kind")
        labels = tuple(label_re.findall(m.group("labels") or ""))
        blocks.append(HclBlock(kind=kind, labels=labels, body=hcl[start:end]))
        pos = end
    return blocks


# ─── Composer entry points ───────────────────────────────────────────────

def compose_terraform(
    per_skill_artifacts: dict[str, dict[str, str]],
    migration_name: str = "migration",
) -> SynthesisResult:
    """Merge per-skill HCL into a single Terraform module.

    Args:
        per_skill_artifacts: ``{skill_name: {filename: content}}`` as
            produced by plan_orchestrator. Typically keyed like
            ``{"network_translation": {"main.tf": "...", "variables.tf": "..."}, ...}``.
        migration_name: short label embedded in the generated providers.tf
            comment header.

    Returns:
        SynthesisResult with files keyed by concern filename and a list
        of warnings the orchestrator can surface in the gaps report.
    """
    result = SynthesisResult()

    # Track {(kind, labels): origin_skill} to detect collisions across skills.
    seen_block: dict[tuple, str] = {}

    # Per-file block lists (in concern order). We build and serialize at
    # the end so renames can happen before serialization.
    per_concern_blocks: dict[str, list[HclBlock]] = {f: [] for f in _SKILL_TO_CONCERN.values()}
    variable_blocks: dict[str, HclBlock] = {}   # dedup by variable name
    output_blocks: dict[str, HclBlock] = {}     # dedup by output name

    for skill, files in per_skill_artifacts.items():
        if not files:
            continue
        concern_file = _SKILL_TO_CONCERN.get(skill)
        if not concern_file:
            # Unmapped skill (ocm_handoff_translation, cfn_terraform, etc.) —
            # handled separately by the orchestrator, not folded in here.
            continue
        result.skills_included.append(skill)

        for filename, content in files.items():
            if not isinstance(content, str):
                continue
            blocks = _extract_blocks(content)
            for blk in blocks:
                # provider / terraform blocks replaced with a clean one
                # in providers.tf later — drop them here.
                if blk.kind in ("provider", "terraform"):
                    continue
                if blk.kind == "variable":
                    name = blk.labels[0] if blk.labels else ""
                    if not name:
                        continue
                    if name in variable_blocks:
                        if variable_blocks[name].body.strip() != blk.body.strip():
                            result.warnings.append(
                                f"variable '{name}' defined differently in "
                                f"{skill} and an earlier skill — kept first definition"
                            )
                        continue
                    variable_blocks[name] = blk
                    continue
                if blk.kind == "output":
                    name = blk.labels[0] if blk.labels else ""
                    if not name:
                        continue
                    if name in output_blocks:
                        if output_blocks[name].body.strip() != blk.body.strip():
                            result.warnings.append(
                                f"output '{name}' redefined in {skill} — kept first"
                            )
                        continue
                    output_blocks[name] = blk
                    continue
                # resource / data / module / locals — route into the concern file.
                # Collision detection + renaming only applies to labelled
                # blocks (resource/data/module); locals don't have labels.
                if blk.kind in ("resource", "data", "module") and blk.labels:
                    if blk.identity in seen_block:
                        # Rename the second occurrence to avoid an HCL
                        # duplicate-label error at validate time.
                        original_label = blk.labels[-1]
                        new_label = f"{original_label}_from_{skill.replace('_translation','')}"
                        prev = seen_block[blk.identity]
                        result.warnings.append(
                            f"{blk.kind} \"{blk.labels[0]}\" \"{original_label}\" defined "
                            f"by both {prev} and {skill} — renamed {skill}'s copy to "
                            f'"{new_label}"'
                        )
                        renamed_body = _rename_last_label(blk, new_label)
                        blk = HclBlock(
                            kind=blk.kind,
                            labels=blk.labels[:-1] + (new_label,),
                            body=renamed_body,
                        )
                        # Don't overwrite seen_block — we want to keep catching
                        # further collisions against the original.
                    else:
                        seen_block[blk.identity] = skill
                per_concern_blocks[concern_file].append(blk)

    # Serialize
    for filename, blocks in per_concern_blocks.items():
        if not blocks:
            continue
        result.files[filename] = _render_file(
            header_comment=f"# Generated for '{migration_name}' by synthesis_composer\n"
                           f"# Contents of this file came from the skill(s) that produced "
                           f"{filename.replace('.tf','')} resources.\n",
            blocks=blocks,
        )

    if variable_blocks:
        result.files["variables.tf"] = _render_file(
            header_comment=f"# Variables consolidated across every skill that ran.\n"
                           f"# Populate terraform.tfvars or pass with -var.\n",
            blocks=list(variable_blocks.values()),
        )
    if output_blocks:
        result.files["outputs.tf"] = _render_file(
            header_comment=f"# Outputs consolidated across every skill.\n",
            blocks=list(output_blocks.values()),
        )

    # Canonical providers.tf — exactly one provider block + required_providers.
    result.files["providers.tf"] = _render_providers_tf(migration_name)

    return result


def _rename_last_label(blk: HclBlock, new_label: str) -> str:
    """Rewrite the trailing ``"old"`` in a block header with ``"new_label"``."""
    # Locate the opening brace
    brace = blk.body.find("{")
    if brace < 0:
        return blk.body
    header, tail = blk.body[:brace], blk.body[brace:]
    # Replace the last quoted label before the brace
    i = len(header) - 1
    # skip trailing whitespace
    while i >= 0 and header[i].isspace():
        i -= 1
    if i < 0 or header[i] != '"':
        return blk.body
    end_quote = i
    i -= 1
    while i >= 0 and header[i] != '"':
        i -= 1
    if i < 0:
        return blk.body
    start_quote = i
    return header[:start_quote] + f'"{new_label}"' + header[end_quote + 1:] + tail


def _render_file(header_comment: str, blocks: list[HclBlock]) -> str:
    parts = [header_comment, ""]
    for b in blocks:
        parts.append(b.body.strip())
        parts.append("")
    return "\n".join(parts)


def _render_providers_tf(migration_name: str) -> str:
    """One clean provider block + required_providers. Individual skills'
    provider blocks were dropped in the merge; this replaces them."""
    return (
        f'# Generated for "{migration_name}".\n'
        "# Single canonical oci provider + required_providers block for the module.\n"
        "\n"
        "terraform {\n"
        "  required_version = \">= 1.5\"\n"
        "  required_providers {\n"
        "    oci = {\n"
        "      source  = \"oracle/oci\"\n"
        "      version = \">= 6.0.0\"\n"
        "    }\n"
        "  }\n"
        "}\n"
        "\n"
        "provider \"oci\" {\n"
        "  tenancy_ocid     = var.tenancy_ocid\n"
        "  user_ocid        = var.user_ocid\n"
        "  fingerprint      = var.fingerprint\n"
        "  private_key_path = var.private_key_path\n"
        "  region           = var.region\n"
        "}\n"
    )
