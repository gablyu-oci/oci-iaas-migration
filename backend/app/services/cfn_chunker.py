"""CloudFormation template chunking + cross-skill HCL reuse.

The ``cfn_terraform`` skill used to receive the entire CloudFormation
template in a single call. For real-world stacks (20+ resources), the
writer agent had to reason about + generate enough HCL that the LLM
gateway's nginx layer would 504 before the response completed.

This module breaks that pattern into three pieces:

1. **Chunking** — split the template's ``Resources`` map into groups of
   ≤ ``chunk_size`` resources. Each chunk gets the chunk's resources plus
   the template-level context (``Parameters``, ``Mappings``, ``Conditions``,
   ``Outputs``) so the writer can still resolve ``!Ref``/``!FindInMap``/
   ``Fn::If``. The full list of logical IDs is included so the writer
   knows which names will exist in other chunks and can emit the correct
   Terraform references.

2. **Reference library** — per-resource skills
   (``network_translation``, ``ec2_translation``, …) have usually
   already produced HCL for the resources that live inside the CFN
   stack. Instead of re-translating those, we pass their ``main.tf`` /
   ``variables.tf`` fragments into each chunk as a reference. The writer's
   prompt instructs it to reuse verbatim when coverage exists; this
   shrinks both the input reasoning burden and the output generation.

3. **Merge** — concatenate per-chunk HCL with variable/output
   deduplication. Resource definitions don't collide (each logical ID is
   unique in the source template); variables and outputs do collide across
   chunks and are deduped by name.

Downstream caller: ``plan_orchestrator._run_cfn_chunked()``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Chunk size: number of CFN Resources per writer call.
#
# Strategy: start LARGE (fewer chunks = shorter wall-clock when successful).
# If a chunk fails (504 / timeout / generic exception), the runner in
# plan_orchestrator bisects it recursively down to single-resource chunks.
# So the effective chunk size adapts to what the LLM gateway will
# actually accept on a given day, and we only pay the bisect cost when
# a chunk is genuinely too big.
DEFAULT_CHUNK_SIZE = 20


# ─── Parsing ─────────────────────────────────────────────────────────────────

def parse_cfn_template(template: str | dict | None) -> dict:
    """Parse a CloudFormation template into a normalized dict.

    Accepts JSON strings, YAML strings (including short-form intrinsics
    like ``!Ref``), and pre-parsed dicts. Returns an empty dict on failure
    so callers don't need defensive try/excepts.
    """
    if not template:
        return {}
    if isinstance(template, dict):
        return template

    # Try JSON first (cheap + common)
    try:
        return json.loads(template)
    except (ValueError, TypeError):
        pass

    # Fall back to YAML with CFN-style short-form intrinsics
    try:
        import yaml  # pyyaml — already a dep via other mapping code
    except ImportError:
        logger.warning("PyYAML unavailable; cannot parse non-JSON CFN template")
        return {}

    class _CFNLoader(yaml.SafeLoader):
        pass

    def _intrinsic(tag: str):
        """Build a yaml constructor for one short-form intrinsic.

        ``!Ref Foo`` → ``{"Ref": "Foo"}``
        ``!GetAtt Foo.Bar`` → ``{"Fn::GetAtt": ["Foo", "Bar"]}``
        ``!Sub foo`` → ``{"Fn::Sub": "foo"}`` (scalar) or list
        """
        key = tag if tag.startswith("Fn::") else f"Fn::{tag.lstrip('Fn::')}"
        if tag == "Ref":
            key = "Ref"

        def _ctor(loader, node):
            if isinstance(node, yaml.ScalarNode):
                value = loader.construct_scalar(node)
                # GetAtt's shorthand ``!GetAtt Foo.Bar`` must become a list
                if tag == "GetAtt" and isinstance(value, str) and "." in value:
                    value = value.split(".", 1)
                return {key: value}
            if isinstance(node, yaml.SequenceNode):
                return {key: loader.construct_sequence(node, deep=True)}
            if isinstance(node, yaml.MappingNode):
                return {key: loader.construct_mapping(node, deep=True)}
            return {key: None}

        return _ctor

    for t in ("Ref", "GetAtt", "Sub", "Join", "Select", "Split", "FindInMap",
              "If", "And", "Or", "Not", "Equals", "ImportValue", "Base64",
              "Cidr", "Condition", "Transform", "GetAZs"):
        _CFNLoader.add_constructor(f"!{t}", _intrinsic(t))

    try:
        result = yaml.load(template, Loader=_CFNLoader)
        return result if isinstance(result, dict) else {}
    except yaml.YAMLError as exc:
        logger.warning("Failed to parse CFN template as YAML: %s", exc)
        return {}


# ─── Chunking ────────────────────────────────────────────────────────────────

@dataclass
class ChunkSpec:
    """One chunk of a CFN template, ready to hand to the writer agent."""
    index: int
    total: int
    resources: dict[str, dict]            # this chunk's resources
    all_logical_ids: list[str]            # every logical ID in the full template
    parameters: dict = field(default_factory=dict)
    mappings: dict = field(default_factory=dict)
    conditions: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)  # attached to the last chunk only
    transform: Any = None
    description: str = ""

    def to_input(self, reference_hcl: dict[str, dict] | None = None) -> str:
        """Serialize this chunk as the JSON input the writer agent expects."""
        payload: dict[str, Any] = {
            "_chunked": True,
            "chunk_index": self.index,
            "chunk_total": self.total,
            "description": self.description or "",
            "resources": self.resources,
            "all_logical_ids": self.all_logical_ids,
            "parameters": self.parameters,
            "mappings": self.mappings,
            "conditions": self.conditions,
        }
        if self.transform is not None:
            payload["transform"] = self.transform
        # Outputs + reference HCL only on last chunk (nothing to merge before that)
        if self.outputs:
            payload["outputs"] = self.outputs
        if reference_hcl:
            payload["reference_hcl"] = reference_hcl
        return json.dumps(payload, indent=2, default=str)


def chunk_cfn_template(
    template: str | dict | None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[ChunkSpec]:
    """Split a CFN template's ``Resources`` map into chunks of ``chunk_size``.

    Dependencies between resources (via ``!Ref`` / ``!GetAtt``) don't
    force a strict ordering here — Terraform's planner resolves the
    graph regardless of declaration order, and each chunk carries the
    full logical-ID list so the writer can emit cross-chunk references
    correctly. Outputs are attached to the last chunk only.
    """
    parsed = parse_cfn_template(template)
    resources = parsed.get("Resources") or {}
    if not isinstance(resources, dict) or not resources:
        return []

    # Preserve template order (dict insertion order) for predictability
    items = list(resources.items())
    all_ids = [lid for lid, _ in items]

    chunks: list[ChunkSpec] = []
    total = max(1, (len(items) + chunk_size - 1) // chunk_size)
    for i in range(0, len(items), chunk_size):
        slice_items = items[i : i + chunk_size]
        chunks.append(ChunkSpec(
            index=len(chunks),
            total=total,
            resources=dict(slice_items),
            all_logical_ids=all_ids,
            parameters=parsed.get("Parameters") or {},
            mappings=parsed.get("Mappings") or {},
            conditions=parsed.get("Conditions") or {},
            transform=parsed.get("Transform"),
            description=str(parsed.get("Description") or ""),
        ))
    if chunks:
        chunks[-1].outputs = parsed.get("Outputs") or {}
    return chunks


# ─── Reference-library assembly ──────────────────────────────────────────────

def build_reference_library(
    completed_artifacts: dict[str, str],
    skills_of_interest: tuple[str, ...] = (
        "network_translation", "ec2_translation", "storage_translation",
        "database_translation", "loadbalancer_translation", "iam_translation",
        "security_translation",
    ),
) -> dict[str, dict[str, str]]:
    """Assemble per-skill HCL fragments from already-completed translations.

    ``completed_artifacts`` is keyed like ``"{skill}/{filename}"`` (the
    same shape ``plan_orchestrator`` already stores). We pivot that into
    ``{skill: {filename: content}}`` so the writer can see each prior
    skill's HCL as a coherent unit.

    Contents are not modified, so the writer can lift fragments verbatim
    when a CFN resource matches one of our already-translated ones.
    """
    out: dict[str, dict[str, str]] = {}
    for path, content in completed_artifacts.items():
        if "/" not in path:
            continue
        skill, filename = path.split("/", 1)
        if skill not in skills_of_interest:
            continue
        # Only surface the core HCL files
        if not filename.endswith((".tf", ".tfvars")):
            continue
        out.setdefault(skill, {})[filename] = content
    return out


# ─── Merging chunk outputs ───────────────────────────────────────────────────

_RESOURCE_BLOCK_RE = re.compile(
    r'^\s*(resource|data|module)\s+"[^"]+"\s+"[^"]+"\s*\{',
    re.MULTILINE,
)

_VARIABLE_BLOCK_RE = re.compile(
    r'variable\s+"(?P<name>[^"]+)"\s*\{',
    re.MULTILINE,
)

_OUTPUT_BLOCK_RE = re.compile(
    r'output\s+"(?P<name>[^"]+)"\s*\{',
    re.MULTILINE,
)


def _extract_top_level_blocks(hcl: str, block_re: re.Pattern[str]) -> list[tuple[str, str]]:
    """Return ``[(name, block_text)]`` for every top-level ``variable`` /
    ``output`` block in ``hcl``. Brace-balanced, not a full HCL parser."""
    results: list[tuple[str, str]] = []
    for m in block_re.finditer(hcl):
        start = m.start()
        # Walk forward counting braces to find the matching close
        depth = 0
        i = hcl.find("{", m.end() - 1)
        if i < 0:
            continue
        end = i
        while i < len(hcl):
            ch = hcl[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            i += 1
        results.append((m.group("name"), hcl[start:end]))
    return results


def merge_chunk_outputs(chunk_outputs: list[dict[str, str]]) -> dict[str, str]:
    """Merge per-chunk ``{main.tf, variables.tf, outputs.tf}`` maps.

    - ``main.tf``: concatenate in chunk order, with ``# --- chunk N ---``
      headers so the resulting file stays readable.
    - ``variables.tf`` / ``outputs.tf``: dedupe by block name. First
      definition wins; a duplicate with a different body logs a warning
      but is silently dropped (the writer is expected to produce
      consistent variable/output definitions across chunks).
    """
    main_parts: list[str] = []
    seen_vars: dict[str, str] = {}
    seen_outs: dict[str, str] = {}
    extra_files: dict[str, str] = {}

    for i, chunk in enumerate(chunk_outputs):
        if not isinstance(chunk, dict):
            continue
        for filename, content in chunk.items():
            if not isinstance(content, str):
                continue
            if filename.endswith("main.tf") or filename == "main.tf":
                main_parts.append(f"# --- chunk {i} ---\n{content.strip()}\n")
            elif filename.endswith("variables.tf") or filename == "variables.tf":
                for name, block in _extract_top_level_blocks(content, _VARIABLE_BLOCK_RE):
                    if name in seen_vars and seen_vars[name].strip() != block.strip():
                        logger.warning("variable '%s' redefined across chunks; keeping first", name)
                        continue
                    seen_vars.setdefault(name, block)
            elif filename.endswith("outputs.tf") or filename == "outputs.tf":
                for name, block in _extract_top_level_blocks(content, _OUTPUT_BLOCK_RE):
                    if name in seen_outs and seen_outs[name].strip() != block.strip():
                        logger.warning("output '%s' redefined across chunks; keeping first", name)
                        continue
                    seen_outs.setdefault(name, block)
            else:
                # Anything else (README.md, per-chunk scratch) — namespace by chunk
                extra_files[f"chunk{i}_{filename}"] = content

    merged: dict[str, str] = {}
    if main_parts:
        merged["main.tf"] = "\n".join(main_parts).strip() + "\n"
    if seen_vars:
        merged["variables.tf"] = "\n\n".join(seen_vars.values()).strip() + "\n"
    if seen_outs:
        merged["outputs.tf"] = "\n\n".join(seen_outs.values()).strip() + "\n"
    merged.update(extra_files)
    return merged
