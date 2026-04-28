# Phase 1 Architecture: Templates + Structured Output Refactor

**Status:** Proposed
**Date:** 2026-04-28
**Scope:** 3 skills (network_translation, loadbalancer_translation, ocm_handoff_translation)


## 1. System Overview

Today, every skill writer agent produces raw HCL strings via an LLM. The LLM
must simultaneously reason about AWS-to-OCI mapping semantics *and* emit
syntactically correct HCL -- two orthogonal concerns tangled in one prompt. This
causes:

- Frequent `terraform validate` failures (missing braces, wrong attribute names)
- Non-deterministic formatting across runs
- Reviewer iterations wasted on syntax, not semantics
- Output tokens dominated by boilerplate HCL that is identical across runs

Phase 1 splits these concerns. Writers for the 3 in-scope skills emit a
**structured JSON spec** (which resource, which template, what parameters).
A deterministic **template renderer** converts specs to correct HCL via Jinja2
templates validated by Pydantic schemas. The rest of the pipeline
(synthesis_composer, bundle_builder, reviewer) sees rendered HCL and is
unchanged.


## 2. Component Diagram

```
                    +------------------------------------------+
                    |            plan_orchestrator              |
                    +------------------------------------------+
                                      |
                         +------------+------------+
                         |                         |
                  (in-scope skills)         (all other skills)
                         |                         |
                         v                         v
              +---------------------+    +---------------------+
              |   skill_group.py    |    |   skill_group.py    |
              |  (STRUCTURED path)  |    |    (LEGACY path)    |
              +---------------------+    +---------------------+
              | writer prompt asks  |    | writer prompt asks  |
              | for JSON specs      |    | for raw HCL (as-is) |
              | reviewer reviews    |    | reviewer reviews    |
              | semantic accuracy   |    | HCL correctness     |
              +----------+----------+    +----------+----------+
                         |                         |
                         v                         |
              +---------------------+              |
              | template_renderer   |              |
              |  (Layer 1.5)        |              |
              +---------------------+              |
              | 1. Pydantic validate|              |
              | 2. Jinja2 render    |              |
              | 3. Group by domain  |              |
              +----------+----------+              |
                         |                         |
                         v                         v
                    dict[str, str]           dict[str, str]
                    {"main.tf": "...",       {"main.tf": "...",
                     "variables.tf": "..."}   "variables.tf": "..."}
                         |                         |
                         +------------+------------+
                                      |
                                      v
                    +------------------------------------------+
                    |         synthesis_composer.py             |
                    |  (UNCHANGED -- receives rendered HCL)    |
                    +------------------------------------------+
                                      |
                                      v
                    +------------------------------------------+
                    |          bundle_builder.py                |
                    |            (UNCHANGED)                    |
                    +------------------------------------------+
```


## 3. Data Flow: Structured vs Legacy Path

### 3a. Structured Output Path (in-scope skills)

```
Input JSON (AWS resources)
    |
    v
Writer Agent (LLM)
    |  prompt: "emit a JSON array of specs, not HCL"
    |  tools: lookup_aws_mapping, list_resources_for_skill
    |         (terraform_validate is REMOVED from structured writers)
    v
Writer output (JSON):
    {
      "specs": [
        {"template": "vcn",           "label": "main",    "params": {...}},
        {"template": "subnet",        "label": "public",  "params": {...}},
        {"template": "nsg",           "label": "web_sg",  "params": {...}},
        ...
      ],
      "resource_mappings": [...],
      "gaps": [...],
      "migration_prerequisites": [...]
    }
    |
    v
_extract_json() --> parse "specs" key
    |
    v
Reviewer Agent (LLM)
    |  reviews: are the right templates used? are params semantically correct?
    |  does NOT review HCL syntax (there is none yet)
    v
Review verdict --> loop if NEEDS_FIXES
    |
    v  (after approval)
template_renderer.render_specs(specs)
    |
    |  For each spec:
    |    1. Look up Pydantic model from TEMPLATE_REGISTRY[spec["template"]]
    |    2. Validate spec["params"] against model (hard fail on error)
    |    3. Load Jinja2 template from backend/app/templates/oci/<domain>/
    |    4. Render template with validated params
    |
    v
Grouped HCL files:
    {
      "main.tf":      "<rendered resource blocks>",
      "variables.tf": "<rendered variable blocks>",
      "outputs.tf":   "<rendered output blocks>"
    }
    |
    v
SkillRunResult.draft  (same shape as legacy path)
```

### 3b. Legacy Path (all other skills -- UNCHANGED)

```
Input JSON (AWS resources)
    |
    v
Writer Agent (LLM)
    |  prompt: "emit HCL as JSON keys" (current behavior)
    |  tools: lookup_aws_mapping, list_resources_for_skill, terraform_validate
    v
Writer output (JSON):
    {
      "main.tf":       "<raw HCL>",
      "variables.tf":  "<raw HCL>",
      "outputs.tf":    "<raw HCL>",
      "resource_mappings": [...],
      ...
    }
    |
    v
Reviewer --> loop if NEEDS_FIXES
    |
    v
SkillRunResult.draft  (passed through to synthesis_composer as-is)
```


## 4. Layer 0 -- Template Schema Design

### 4a. Directory Layout

```
backend/app/templates/
    oci/
        core/                          # 11 templates
            vcn.tf.j2
            subnet.tf.j2
            internet_gateway.tf.j2
            nat_gateway.tf.j2
            service_gateway.tf.j2
            route_table.tf.j2
            network_security_group.tf.j2
            nsg_rule.tf.j2
            drg.tf.j2
            local_peering_gateway.tf.j2
            vnic_attachment.tf.j2
        load_balancer/                 # 7 templates
            load_balancer.tf.j2
            backend_set.tf.j2
            backend.tf.j2
            listener.tf.j2
            network_load_balancer.tf.j2
            nlb_backend_set.tf.j2
            nlb_listener.tf.j2
        cloud_migrations/              # 4 templates
            migration.tf.j2
            migration_plan.tf.j2
            target_asset.tf.j2
            replication_schedule.tf.j2
        _fallback.tf.j2               # 1 escape hatch for unmapped resources
    schemas/
        __init__.py                    # TEMPLATE_REGISTRY + re-exports
        core.py                        # Pydantic models for core/ templates
        load_balancer.py               # Pydantic models for load_balancer/ templates
        cloud_migrations.py            # Pydantic models for cloud_migrations/ templates
        _base.py                       # Shared base classes + field types
```

### 4b. Pydantic Model Example: VCN

```python
# backend/app/templates/schemas/_base.py

from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Any
import re

# Reusable field types
class CidrBlock(BaseModel):
    """Validates a CIDR string like 10.0.0.0/16."""
    cidr: str

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/\d{1,2}$"
        if not re.match(pattern, v):
            raise ValueError(f"Invalid CIDR: {v}")
        return v

class FreeformTags(BaseModel):
    aws_source_id: str = Field(..., description="Original AWS resource ID for traceability")
    managed_by: str = Field(default="oci-iaas-migration")
    extra: dict[str, str] = Field(default_factory=dict)

class TemplateSpec(BaseModel):
    """Base class for all template parameter models."""
    label: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$",
                       description="Terraform resource label (snake_case)")
    aws_source_id: str = Field(..., description="Source AWS resource ID for traceability comment")

    class Config:
        extra = "forbid"  # Hard fail on unknown fields
```

```python
# backend/app/templates/schemas/core.py

from __future__ import annotations
from pydantic import Field
from typing import Literal
from ._base import TemplateSpec

class VcnSpec(TemplateSpec):
    """Parameters for the vcn.tf.j2 template."""
    display_name: str = Field(..., description="OCI display name for the VCN")
    cidr_blocks: list[str] = Field(..., min_length=1, max_length=5,
                                    description="List of CIDR blocks (e.g. ['10.0.0.0/16'])")
    compartment_id_expr: str = Field(default="var.compartment_id",
                                      description="Terraform expression for compartment OCID")
    dns_label: str | None = Field(default=None, max_length=15,
                                   description="VCN DNS label (max 15 chars, alphanumeric)")
    freeform_tags: dict[str, str] = Field(default_factory=dict)

class SubnetSpec(TemplateSpec):
    display_name: str
    cidr_block: str
    vcn_ref: str = Field(..., description="Terraform reference to VCN, e.g. oci_core_vcn.main.id")
    compartment_id_expr: str = Field(default="var.compartment_id")
    route_table_ref: str | None = None
    security_list_refs: list[str] = Field(default_factory=list)
    prohibit_public_ip: bool = True
    dns_label: str | None = None
    availability_domain: str | None = None
    freeform_tags: dict[str, str] = Field(default_factory=dict)

class InternetGatewaySpec(TemplateSpec):
    display_name: str
    vcn_ref: str
    compartment_id_expr: str = Field(default="var.compartment_id")
    enabled: bool = True
    freeform_tags: dict[str, str] = Field(default_factory=dict)

class NatGatewaySpec(TemplateSpec):
    display_name: str
    vcn_ref: str
    compartment_id_expr: str = Field(default="var.compartment_id")
    block_traffic: bool = False
    freeform_tags: dict[str, str] = Field(default_factory=dict)

class ServiceGatewaySpec(TemplateSpec):
    display_name: str
    vcn_ref: str
    compartment_id_expr: str = Field(default="var.compartment_id")
    service_id_expr: str = Field(default='data.oci_core_services.all.services[0].id')
    freeform_tags: dict[str, str] = Field(default_factory=dict)

class RouteTableSpec(TemplateSpec):
    display_name: str
    vcn_ref: str
    compartment_id_expr: str = Field(default="var.compartment_id")
    routes: list[RouteRuleSpec] = Field(default_factory=list)
    freeform_tags: dict[str, str] = Field(default_factory=dict)

class RouteRuleSpec(BaseModel):
    destination: str
    destination_type: Literal["CIDR_BLOCK", "SERVICE_CIDR_BLOCK"] = "CIDR_BLOCK"
    network_entity_ref: str  # e.g. oci_core_internet_gateway.main.id

class NsgSpec(TemplateSpec):
    display_name: str
    vcn_ref: str
    compartment_id_expr: str = Field(default="var.compartment_id")
    freeform_tags: dict[str, str] = Field(default_factory=dict)

class NsgRuleSpec(TemplateSpec):
    nsg_ref: str
    direction: Literal["INGRESS", "EGRESS"]
    protocol: str  # "6", "17", "1", "all"
    source: str | None = None
    source_type: Literal["CIDR_BLOCK", "NETWORK_SECURITY_GROUP", "SERVICE_CIDR_BLOCK"] | None = None
    destination: str | None = None
    destination_type: Literal["CIDR_BLOCK", "NETWORK_SECURITY_GROUP", "SERVICE_CIDR_BLOCK"] | None = None
    stateless: bool = False
    description: str | None = None
    tcp_options_dest_min: int | None = None
    tcp_options_dest_max: int | None = None
    udp_options_dest_min: int | None = None
    udp_options_dest_max: int | None = None

# ... (DrgSpec, LocalPeeringGatewaySpec, VnicAttachmentSpec follow the same pattern)
```

### 4c. Example Jinja2 Template: vcn.tf.j2

```hcl
{# backend/app/templates/oci/core/vcn.tf.j2 #}
resource "oci_core_vcn" "{{ label }}" {
  # aws_source_id = {{ aws_source_id }}
  compartment_id = {{ compartment_id_expr }}
  display_name   = "{{ display_name }}"
{% for cidr in cidr_blocks %}
{% if loop.first %}
  cidr_blocks    = [
{% endif %}
    "{{ cidr }}",
{% if loop.last %}
  ]
{% endif %}
{% endfor %}
{% if dns_label %}
  dns_label      = "{{ dns_label }}"
{% endif %}

  freeform_tags = {
    aws_source_id  = "{{ aws_source_id }}"
    managed_by     = "oci-iaas-migration"
{% for k, v in freeform_tags.items() %}
    {{ k }} = "{{ v }}"
{% endfor %}
  }
}
```


## 5. Template Registry Design

```python
# backend/app/templates/schemas/__init__.py

"""Template registry: maps template name -> (Pydantic model, Jinja2 path, output domain).

The registry is the single source of truth that the renderer uses to:
  1. Validate writer-emitted specs
  2. Locate the Jinja2 template file
  3. Route rendered HCL into the correct output file
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Type
from pydantic import BaseModel

from .core import (
    VcnSpec, SubnetSpec, InternetGatewaySpec, NatGatewaySpec,
    ServiceGatewaySpec, RouteTableSpec, NsgSpec, NsgRuleSpec,
    DrgSpec, LocalPeeringGatewaySpec, VnicAttachmentSpec,
)
from .load_balancer import (
    LoadBalancerSpec, BackendSetSpec, BackendSpec, ListenerSpec,
    NetworkLoadBalancerSpec, NlbBackendSetSpec, NlbListenerSpec,
)
from .cloud_migrations import (
    MigrationSpec, MigrationPlanSpec, TargetAssetSpec,
    ReplicationScheduleSpec,
)


@dataclass(frozen=True)
class TemplateEntry:
    schema: Type[BaseModel]       # Pydantic model for validation
    template_path: str            # Relative to backend/app/templates/oci/
    output_domain: str            # "network" | "loadbalancer" | "ocm"
    output_kind: str              # "resource" | "variable" | "data"


TEMPLATE_REGISTRY: dict[str, TemplateEntry] = {
    # --- Core network (11) ---
    "vcn":                   TemplateEntry(VcnSpec,                "core/vcn.tf.j2",                        "network", "resource"),
    "subnet":                TemplateEntry(SubnetSpec,             "core/subnet.tf.j2",                     "network", "resource"),
    "internet_gateway":      TemplateEntry(InternetGatewaySpec,    "core/internet_gateway.tf.j2",           "network", "resource"),
    "nat_gateway":           TemplateEntry(NatGatewaySpec,         "core/nat_gateway.tf.j2",                "network", "resource"),
    "service_gateway":       TemplateEntry(ServiceGatewaySpec,     "core/service_gateway.tf.j2",            "network", "resource"),
    "route_table":           TemplateEntry(RouteTableSpec,         "core/route_table.tf.j2",                "network", "resource"),
    "nsg":                   TemplateEntry(NsgSpec,                "core/network_security_group.tf.j2",     "network", "resource"),
    "nsg_rule":              TemplateEntry(NsgRuleSpec,            "core/nsg_rule.tf.j2",                   "network", "resource"),
    "drg":                   TemplateEntry(DrgSpec,                "core/drg.tf.j2",                        "network", "resource"),
    "local_peering_gateway": TemplateEntry(LocalPeeringGatewaySpec,"core/local_peering_gateway.tf.j2",      "network", "resource"),
    "vnic_attachment":       TemplateEntry(VnicAttachmentSpec,     "core/vnic_attachment.tf.j2",            "network", "resource"),

    # --- Load balancer (7) ---
    "load_balancer":         TemplateEntry(LoadBalancerSpec,       "load_balancer/load_balancer.tf.j2",     "loadbalancer", "resource"),
    "backend_set":           TemplateEntry(BackendSetSpec,         "load_balancer/backend_set.tf.j2",       "loadbalancer", "resource"),
    "backend":               TemplateEntry(BackendSpec,            "load_balancer/backend.tf.j2",           "loadbalancer", "resource"),
    "listener":              TemplateEntry(ListenerSpec,           "load_balancer/listener.tf.j2",          "loadbalancer", "resource"),
    "network_load_balancer": TemplateEntry(NetworkLoadBalancerSpec,"load_balancer/network_load_balancer.tf.j2","loadbalancer", "resource"),
    "nlb_backend_set":       TemplateEntry(NlbBackendSetSpec,     "load_balancer/nlb_backend_set.tf.j2",   "loadbalancer", "resource"),
    "nlb_listener":          TemplateEntry(NlbListenerSpec,       "load_balancer/nlb_listener.tf.j2",      "loadbalancer", "resource"),

    # --- Cloud Migrations / OCM (4) ---
    "migration":             TemplateEntry(MigrationSpec,          "cloud_migrations/migration.tf.j2",      "ocm", "resource"),
    "migration_plan":        TemplateEntry(MigrationPlanSpec,      "cloud_migrations/migration_plan.tf.j2", "ocm", "resource"),
    "target_asset":          TemplateEntry(TargetAssetSpec,        "cloud_migrations/target_asset.tf.j2",   "ocm", "resource"),
    "replication_schedule":  TemplateEntry(ReplicationScheduleSpec,"cloud_migrations/replication_schedule.tf.j2","ocm", "resource"),
}


# Reverse lookup: which templates belong to which skill?
# Used by skill_group.py to validate writer output.
SKILL_TO_TEMPLATES: dict[str, frozenset[str]] = {
    "network_translation": frozenset({
        "vcn", "subnet", "internet_gateway", "nat_gateway", "service_gateway",
        "route_table", "nsg", "nsg_rule", "drg", "local_peering_gateway",
        "vnic_attachment",
    }),
    "loadbalancer_translation": frozenset({
        "load_balancer", "backend_set", "backend", "listener",
        "network_load_balancer", "nlb_backend_set", "nlb_listener",
    }),
    "ocm_handoff_translation": frozenset({
        "migration", "migration_plan", "target_asset", "replication_schedule",
    }),
}
```


## 6. Renderer Design (Layer 1.5)

```python
# backend/app/services/template_renderer.py

"""Deterministic template renderer: JSON specs -> validated HCL.

Entry point: render_specs(specs, skill_type) -> dict[str, str]

Error strategy: HARD FAIL. If a spec fails Pydantic validation, the
entire render raises TemplateRenderError. The caller (skill_group.py)
catches this and feeds the validation errors back to the writer for
one retry before surfacing the failure.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import ValidationError

from app.templates.schemas import TEMPLATE_REGISTRY, SKILL_TO_TEMPLATES, TemplateEntry

_log = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "oci"

# Jinja2 environment: StrictUndefined ensures missing variables cause an
# error rather than rendering as empty string -- fail-fast on bad specs.
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    undefined=StrictUndefined,
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


class TemplateRenderError(Exception):
    """Raised when spec validation or template rendering fails."""
    def __init__(self, errors: list[dict[str, Any]]):
        self.errors = errors
        super().__init__(f"{len(errors)} spec(s) failed validation/rendering")


# Domain -> output filename mapping
_DOMAIN_TO_FILE: dict[str, str] = {
    "network":      "main.tf",
    "loadbalancer": "main.tf",
    "ocm":          "main.tf",
}

# Variables and outputs are rendered into separate files.
# The templates themselves only produce resource blocks; variables/outputs
# are assembled from a fixed set per domain.
_DOMAIN_VARIABLE_TEMPLATES: dict[str, str] = {
    "network":      "core/_variables.tf.j2",
    "loadbalancer": "load_balancer/_variables.tf.j2",
    "ocm":          "cloud_migrations/_variables.tf.j2",
}


def render_specs(
    specs: list[dict[str, Any]],
    skill_type: str,
) -> dict[str, str]:
    """Validate and render a list of template specs into HCL files.

    Args:
        specs: List of {"template": str, "label": str, "params": dict}.
        skill_type: The skill that produced these specs (for guardrail checks).

    Returns:
        {"main.tf": "...", "variables.tf": "...", "outputs.tf": "..."}

    Raises:
        TemplateRenderError: If any spec fails Pydantic validation or
            Jinja2 rendering. The .errors list contains per-spec diagnostics
            the writer can use to self-correct.
    """
    allowed = SKILL_TO_TEMPLATES.get(skill_type)
    errors: list[dict[str, Any]] = []
    rendered_blocks: dict[str, list[str]] = {}  # domain -> [rendered HCL blocks]

    for i, spec in enumerate(specs):
        template_name = spec.get("template", "")
        label = spec.get("label", "")
        params = spec.get("params", {})

        # --- Guard: template must exist in registry ---
        entry = TEMPLATE_REGISTRY.get(template_name)
        if entry is None:
            errors.append({
                "spec_index": i,
                "template": template_name,
                "error": f"Unknown template '{template_name}'. "
                         f"Valid templates: {sorted(TEMPLATE_REGISTRY.keys())}",
            })
            continue

        # --- Guard: template must belong to this skill ---
        if allowed is not None and template_name not in allowed:
            errors.append({
                "spec_index": i,
                "template": template_name,
                "error": f"Template '{template_name}' is not allowed for "
                         f"skill '{skill_type}'. Allowed: {sorted(allowed)}",
            })
            continue

        # --- Pydantic validation ---
        full_params = {"label": label, **params}
        try:
            validated = entry.schema(**full_params)
        except ValidationError as exc:
            errors.append({
                "spec_index": i,
                "template": template_name,
                "label": label,
                "error": f"Pydantic validation failed: {exc.error_count()} error(s)",
                "details": exc.errors(),
            })
            continue

        # --- Jinja2 rendering ---
        try:
            tmpl = _jinja_env.get_template(entry.template_path)
            hcl_block = tmpl.render(**validated.model_dump())
        except Exception as exc:
            errors.append({
                "spec_index": i,
                "template": template_name,
                "label": label,
                "error": f"Jinja2 render failed: {exc}",
            })
            continue

        domain = entry.output_domain
        rendered_blocks.setdefault(domain, []).append(hcl_block)

    # --- Hard fail on any errors ---
    if errors:
        raise TemplateRenderError(errors)

    # --- Assemble output files ---
    result: dict[str, str] = {}

    # Merge all resource blocks into main.tf
    all_blocks: list[str] = []
    for domain_blocks in rendered_blocks.values():
        all_blocks.extend(domain_blocks)

    if all_blocks:
        result["main.tf"] = "\n\n".join(all_blocks) + "\n"

    # Render domain-specific variables.tf if template exists
    variables_parts: list[str] = []
    for domain in rendered_blocks:
        var_template_path = _DOMAIN_VARIABLE_TEMPLATES.get(domain)
        if var_template_path:
            try:
                var_tmpl = _jinja_env.get_template(var_template_path)
                variables_parts.append(var_tmpl.render())
            except Exception:
                _log.warning("No variables template at %s", var_template_path)

    if variables_parts:
        result["variables.tf"] = "\n\n".join(variables_parts) + "\n"

    # outputs.tf -- similarly rendered from domain templates
    # (omitted for brevity; same pattern as variables)

    return result
```

### Error Handling Strategy

```
Writer emits specs
        |
        v
  render_specs()
        |
   +----+----+
   |         |
 success   TemplateRenderError
   |         |
   v         v
HCL files  Catch in skill_group.py
           Format .errors as reviewer-style feedback
           Feed back to writer: "Fix ONLY these spec errors"
           Writer retries (counts against max_iterations)
           |
      +----+----+
      |         |
   success    still fails
      |         |
      v         v
  HCL files   SkillRunResult with
              draft={"error": ..., "spec_errors": [...]}
              review={"decision": "NEEDS_FIXES", ...}
```

Key properties:

- **Fail-fast**: One bad spec fails the entire batch. Partial renders risk
  dangling references (e.g. subnet referencing a VCN that failed validation).
- **Actionable errors**: Each error includes `spec_index`, `template`, `label`,
  and the Pydantic `details` array so the writer knows exactly what to fix.
- **Bounded retries**: Template render errors consume writer iterations (the
  same `max_iterations` cap). If the writer cannot produce valid specs after
  `max_iterations` rounds, the skill run fails rather than looping forever.
- **StrictUndefined**: Jinja2 raises on any variable the template references
  but the spec did not provide. This catches schema/template drift.


## 7. skill_group.py Integration Points

### 7a. What Changes

Six precise changes to `skill_group.py`, marked by where they occur:

**Change 1 -- New constant: set of structured-output skills**

```python
# After SKILL_SPECS dict (line ~362)

STRUCTURED_OUTPUT_SKILLS: frozenset[str] = frozenset({
    "network_translation",
    "loadbalancer_translation",
    "ocm_handoff_translation",
})
```

**Change 2 -- Feature flag check**

```python
# New import at top of file
from app.config import settings

# Helper predicate used in _build_writer, _writer_instructions, and SkillGroup.run
def _use_structured_output(skill_type: str) -> bool:
    """True when this skill should use the template-based structured output path."""
    if not getattr(settings, "STRUCTURED_OUTPUT_ENABLED", False):
        return False
    return skill_type in STRUCTURED_OUTPUT_SKILLS
```

**Change 3 -- Writer instructions fork**

```python
# In _writer_instructions(), after the existing output format section:

def _writer_instructions(spec: SkillSpec) -> str:
    if _use_structured_output(spec.skill_type):
        return _structured_writer_instructions(spec)
    return _legacy_writer_instructions(spec)  # current implementation, renamed
```

The new `_structured_writer_instructions()` replaces the "Output format" section
with:

```
## Output format (STRUCTURED)

Return a single JSON object with this shape:

{
  "specs": [
    {
      "template": "<template name from the allowed set>",
      "label":    "<terraform resource label, snake_case>",
      "params":   { <template-specific parameters> }
    },
    ...
  ],
  "resource_mappings": [...],
  "gaps": [...],
  "migration_prerequisites": [...]
}

Allowed templates for this skill: <list from SKILL_TO_TEMPLATES>
```

It also embeds a condensed schema reference (field names + types + required/optional)
for each allowed template, generated from the Pydantic models at prompt-build time.

**Change 4 -- Remove terraform_validate from structured writers**

```python
# In _build_writer():

def _build_writer(spec: SkillSpec) -> Agent:
    tools = [lookup_aws_mapping, list_resources_for_skill]
    if spec.needs_terraform_validate and not _use_structured_output(spec.skill_type):
        tools.append(terraform_validate)
    # ...
```

Rationale: structured-output writers never see HCL, so `terraform_validate` is
meaningless. Removing it saves tool-call tokens and avoids confusing the writer.

**Change 5 -- Post-approval rendering in SkillGroup.run()**

```python
# In SkillGroup.run(), after the review loop ends with approval:

async def run(self, input_content, ctx=None):
    # ... existing loop ...

    # NEW: render structured specs into HCL
    if _use_structured_output(self.spec.skill_type):
        draft = self._render_structured_draft(draft)

    return SkillRunResult(...)


def _render_structured_draft(self, draft: dict) -> dict:
    """Convert {"specs": [...], ...} into {"main.tf": "...", ...}.

    On TemplateRenderError, returns the draft with error metadata
    so the caller sees it as a failed run.
    """
    from app.services.template_renderer import render_specs, TemplateRenderError

    specs = draft.get("specs", [])
    if not specs:
        _log.warning("%s: no specs in structured draft", self.spec.skill_type)
        return draft

    try:
        rendered = render_specs(specs, self.spec.skill_type)
    except TemplateRenderError as exc:
        _log.error("%s: template render failed: %s", self.spec.skill_type, exc)
        draft["_render_errors"] = exc.errors
        return draft

    # Merge rendered HCL into the draft dict, preserving non-HCL keys
    # (resource_mappings, gaps, migration_prerequisites)
    for key, content in rendered.items():
        draft[key] = content

    # Remove the specs key -- downstream only needs the HCL files
    draft.pop("specs", None)
    return draft
```

**Change 6 -- Render-error retry inside the loop (optional enhancement)**

Instead of rendering only after the loop, render inside the loop so that
template validation errors can be fed back to the writer as pseudo-reviewer
issues. This is an optional enhancement for Phase 1; the simpler post-loop
approach in Change 5 is the minimum viable integration.

```python
# Inside the review loop, after writer turn, before reviewer turn:

if _use_structured_output(self.spec.skill_type):
    try:
        render_specs(draft.get("specs", []), self.spec.skill_type)
    except TemplateRenderError as exc:
        # Synthesize reviewer-like issues from render errors
        issues = [
            {"severity": "CRITICAL",
             "description": f"Spec {e['spec_index']} ({e.get('template','?')}): {e['error']}",
             "recommendation": "Fix the params for this spec."}
            for e in exc.errors
        ]
        review = {"decision": "NEEDS_FIXES", "confidence": 0.0, "issues": issues}
        # Skip the real reviewer -- go straight to next writer iteration
        continue
```

### 7b. What Does NOT Change

- `_extract_json()` -- works as-is; the structured output is still a JSON object
- `_build_reviewer_turn()` -- reviewer sees the JSON draft (with specs) and
  reviews semantic correctness, not HCL syntax
- `SkillRunResult` -- the `.draft` dict gains HCL keys after rendering, same
  shape downstream consumers expect
- `SKILL_SPECS` / `SKILL_TO_AWS_TYPES` -- unchanged
- `synthesis_composer.py` -- receives `{"main.tf": "...", ...}` as before
- `bundle_builder.py` -- unchanged
- All other skills -- unchanged


## 8. File Layout (Complete)

```
backend/
    app/
        templates/
            __init__.py                          # empty, makes it a package
            oci/
                core/
                    vcn.tf.j2
                    subnet.tf.j2
                    internet_gateway.tf.j2
                    nat_gateway.tf.j2
                    service_gateway.tf.j2
                    route_table.tf.j2
                    network_security_group.tf.j2
                    nsg_rule.tf.j2
                    drg.tf.j2
                    local_peering_gateway.tf.j2
                    vnic_attachment.tf.j2
                    _variables.tf.j2
                load_balancer/
                    load_balancer.tf.j2
                    backend_set.tf.j2
                    backend.tf.j2
                    listener.tf.j2
                    network_load_balancer.tf.j2
                    nlb_backend_set.tf.j2
                    nlb_listener.tf.j2
                    _variables.tf.j2
                cloud_migrations/
                    migration.tf.j2
                    migration_plan.tf.j2
                    target_asset.tf.j2
                    replication_schedule.tf.j2
                    _variables.tf.j2
                _fallback.tf.j2
            schemas/
                __init__.py                      # TEMPLATE_REGISTRY
                _base.py                         # TemplateSpec, shared types
                core.py                          # VcnSpec, SubnetSpec, ...
                load_balancer.py                 # LoadBalancerSpec, ...
                cloud_migrations.py              # MigrationSpec, ...
        services/
            template_renderer.py                 # render_specs()
            synthesis_composer.py                 # UNCHANGED
            bundle_builder.py                    # UNCHANGED
        agents/
            skill_group.py                       # 6 targeted changes (Section 7a)
            tools.py                             # UNCHANGED
        config.py                                # +STRUCTURED_OUTPUT_ENABLED flag
    requirements.txt                             # +Jinja2>=3.1
    docs/
        ARCHITECTURE_PHASE_1.md                  # this document
```


## 9. Migration Strategy: Feature Flag Approach

### 9a. The Flag

Add to `backend/app/config.py`:

```python
class Settings(BaseSettings):
    # ... existing fields ...

    # Phase 1: structured output for template-backed skills.
    # Set to True to enable; False falls back to legacy LLM-generated HCL.
    STRUCTURED_OUTPUT_ENABLED: bool = False
```

Default is `False` -- the feature is off until explicitly enabled. This means:

- **Existing tests (235 backend + 18 frontend) are unaffected** -- they run
  against the legacy path by default.
- **CI pipeline** -- add a second test matrix entry that sets
  `STRUCTURED_OUTPUT_ENABLED=True` and runs the new template-specific tests.
- **Staging** -- flip the flag in the staging `.env` first, run the full
  migration pipeline on reference stacks, compare output to baseline.
- **Production** -- flip after staging validation.

### 9b. Rollout Phases

```
Phase 1a: Templates + Schemas + Renderer (Layer 0 + 1.5)
    - Ship all templates, schemas, renderer, and tests
    - Flag = False (off by default)
    - No behavioral change to any user-facing flow
    - Test: unit tests for every template + schema + renderer

Phase 1b: skill_group.py integration (Layer 1)
    - Ship the 6 changes to skill_group.py
    - Flag = False still
    - Test: integration tests that mock LLM responses as structured specs,
      verify rendered HCL matches golden files

Phase 1c: Staging validation
    - Set STRUCTURED_OUTPUT_ENABLED=True in staging .env
    - Run 3 reference migrations (small/medium/large)
    - Diff rendered HCL against legacy LLM-generated HCL
    - Measure: token usage reduction, terraform validate pass rate, latency

Phase 1d: Production rollout
    - Set STRUCTURED_OUTPUT_ENABLED=True in production .env
    - Monitor for 1 week
    - If issues: set back to False (instant rollback, no code change)
```

### 9c. Rollback

Setting `STRUCTURED_OUTPUT_ENABLED=False` immediately reverts all 3 skills to
the legacy LLM-generates-HCL path. No code deployment required. The templates,
schemas, and renderer remain deployed but inert.


## 10. ADRs (Architecture Decision Records)

### ADR-001: Structured JSON specs over direct HCL generation

**Context:** LLM writers produce raw HCL strings. This tangles semantic
reasoning with syntax production, causing ~30% of reviewer iterations to fix
syntax errors rather than mapping mistakes.

**Decision:** For template-backed skills, writers emit structured JSON specs
(`{template, label, params}`). A deterministic renderer produces HCL from
Jinja2 templates + Pydantic-validated parameters.

**Consequences:**
- (+) Syntax errors eliminated -- templates are pre-validated against real
  `terraform validate` during development.
- (+) Token usage drops ~40% -- no HCL boilerplate in writer output.
- (+) Reviewer can focus on semantic correctness (did the writer pick the
  right template? are the CIDR blocks correct?) rather than brace-matching.
- (-) Templates must be maintained in lockstep with OCI provider schema changes.
- (-) Writer prompts are more constrained -- less flexibility for edge cases.
  The `_fallback.tf.j2` template is the escape hatch.

---

### ADR-002: Hard fail on validation error

**Context:** Should the renderer skip invalid specs and render the rest, or
fail the entire batch?

**Decision:** Hard fail. One `TemplateRenderError` aborts the entire render.

**Rationale:** Partial renders risk dangling Terraform references. A subnet
spec that passes validation might reference a VCN that failed validation. If
we render the subnet but not the VCN, `terraform plan` will produce a
confusing error about an undeclared resource. Fail-fast gives the writer clear
feedback and avoids broken partial output.

---

### ADR-003: Feature flag gating over branch-based rollout

**Context:** How do we ship the structured output path without breaking
existing users?

**Decision:** A single boolean `STRUCTURED_OUTPUT_ENABLED` in Settings,
defaulting to `False`. The `_use_structured_output()` predicate gates every
code path divergence.

**Rationale:** Branch-based rollout would require maintaining two code paths
in separate branches and risk merge conflicts. A runtime flag lets us ship
all the code to main, test both paths in CI, and toggle in production without
deployment. The flag is environment-scoped (`.env`), not per-user -- this is
an infrastructure concern, not a user preference.

---

### ADR-004: Jinja2 with StrictUndefined over string concatenation

**Context:** The renderer needs to produce HCL from validated params. Options:
(a) Python string formatting, (b) Jinja2 templates, (c) HCL AST builder.

**Decision:** Jinja2 with `StrictUndefined`.

**Rationale:**
- (a) String formatting is fragile for multi-line HCL with conditionals.
- (c) No mature Python HCL AST library exists; `python-hcl2` parses but
  does not generate.
- (b) Jinja2 is widely understood, supports conditionals/loops/includes,
  and `StrictUndefined` ensures schema/template drift is caught immediately.
  The templates are readable by anyone who knows HCL + Jinja2.

---

### ADR-005: Pydantic v2 `extra = "forbid"` on all specs

**Context:** Should schema models allow extra fields the template does not use?

**Decision:** `extra = "forbid"` on the `TemplateSpec` base class.

**Rationale:** Extra fields signal a bug -- the writer is emitting params the
template will silently ignore. Forbidding them surfaces the mismatch as a
validation error the writer can correct. If a legitimate use case for extra
fields emerges (e.g. metadata passthrough), we add an explicit `metadata:
dict` field rather than opening `extra = "allow"`.


## 11. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM struggles to emit valid JSON specs (wrong template names, bad param types) | Medium | Medium | Embed condensed schema reference in writer prompt; render-error retry loop (Change 6) feeds Pydantic errors back as issues; `_fallback.tf.j2` as escape hatch |
| Template drift: OCI provider adds/renames attributes | Low | High | Pin `oracle/oci` provider version in templates; add CI job that runs `terraform validate` on rendered golden-file HCL against latest provider |
| Token regression: structured prompt + schema reference is *longer* than legacy prompt | Low | Low | Measure token usage in Phase 1c staging; schema reference is ~200 tokens per template, but output tokens drop by ~40% (no HCL in writer response) |
| Partial render masking: hard-fail hides valid specs behind one bad one | Medium | Low | Error message includes all per-spec diagnostics, not just the first; writer can fix the one bad spec without re-generating valid ones (iteration 2+ prompt says "fix ONLY these") |
| Feature flag left off indefinitely | Low | Low | Add structured-output coverage to the CI smoke test matrix so it runs on every PR regardless of the flag |
| Jinja2 dependency adds attack surface | Very Low | Medium | Jinja2 sandboxing is not needed -- templates are developer-authored, not user-supplied; pin version in requirements.txt |
| Fallback template overuse: writer emits `_fallback` for everything instead of learning the real templates | Medium | Medium | Reviewer prompt includes a guard: "if more than 20% of specs use _fallback, set decision=NEEDS_FIXES with a CRITICAL issue" |


## 12. Dependency Changes

**requirements.txt** -- add one line:

```
Jinja2>=3.1
```

Jinja2 pulls in `MarkupSafe` as a transitive dependency. Both are
well-maintained, widely used, and have no known CVEs at current versions.

**No other dependency changes.** Pydantic v2 is already available via
`pydantic-settings`. The `json-repair` package (already in requirements) is
still used by `_extract_json()` for the legacy path.


## 13. Testing Strategy

### Unit Tests (new)

| Test file | What it covers |
|-----------|---------------|
| `tests/templates/test_schemas.py` | Every Pydantic model: valid params pass, missing required fields fail, extra fields fail, edge cases (empty CIDR list, label with uppercase) |
| `tests/templates/test_registry.py` | Every TEMPLATE_REGISTRY entry has a matching `.j2` file on disk; SKILL_TO_TEMPLATES covers every registry key |
| `tests/templates/test_render_*.py` | Per-domain render tests: feed valid specs, assert rendered HCL matches golden files; feed invalid specs, assert TemplateRenderError with correct diagnostics |
| `tests/services/test_template_renderer.py` | Integration: render_specs() with mixed valid specs, skill guardrails (wrong skill -> error), empty specs list |

### Integration Tests (new)

| Test file | What it covers |
|-----------|---------------|
| `tests/agents/test_skill_group_structured.py` | Mock LLM returning structured specs; verify SkillRunResult.draft contains rendered HCL; verify render errors trigger retry |

### Existing Tests (must still pass)

| Test suite | Count | Expected impact |
|-----------|-------|----------------|
| Backend unit + integration | 235 | None (flag defaults to False) |
| Frontend | 18 | None (no API contract changes) |

### Golden File Validation

For each of the 23 templates, maintain a golden `.tf` file in
`tests/templates/golden/`. The CI test renders the template with fixed params
and asserts byte-exact match. When a template changes intentionally, the
developer updates the golden file (explicit opt-in to output changes).
