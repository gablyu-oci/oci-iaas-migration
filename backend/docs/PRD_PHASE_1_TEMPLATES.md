# PRD: Phase 1 -- Structured Templates for HCL Generation

**Author:** Product Management
**Status:** Draft
**Date:** 2026-04-28
**Stakeholders:** Backend Engineering, QA, DevOps

---

## 1. Problem Statement

The OCI IaaS Migration pipeline translates AWS infrastructure into OCI Terraform
via per-skill writer Agents (see `backend/app/agents/skill_group.py`). Today each
writer Agent generates raw HCL from scratch on every run. This design has three
compounding problems:

1. **Schema bugs are endemic.** The LLM routinely produces wrong field names
   (e.g. `ip_address` instead of `ip_addresses`), incorrect nesting (flat
   attribute where a sub-block is required), and missing required fields. These
   bugs only surface at `terraform validate` or `terraform apply` time, after
   the operator has already reviewed and approved the plan.

2. **Output tokens are wasted on boilerplate.** A typical `oci_core_vcn` block
   is 15-25 lines of HCL, but only 3-5 values actually vary per migration. The
   writer spends tokens reproducing static scaffolding that is identical across
   every run, inflating cost and latency.

3. **Review iterations are spent on syntax, not semantics.** The reviewer Agent
   catches many schema errors, but each fix triggers a full re-generation
   cycle. On average 1.5 of the 3 default iterations are consumed by structural
   corrections rather than domain-level improvements.

The structural root cause is that the LLM is responsible for both **deciding
what to create** (semantic) and **rendering valid HCL** (syntactic). These
concerns should be separated.

---

## 2. Goals and Non-Goals

### Goals

| # | Goal | Measurable target |
|---|------|-------------------|
| G1 | Eliminate schema bugs in the 3 in-scope skills | 0 `terraform validate` failures caused by wrong field names, nesting, or missing required fields in network, load balancer, and OCM translation output |
| G2 | Reduce writer output tokens by 5-10x | Measured via token-usage telemetry on the same input corpus before/after |
| G3 | Make Terraform structure testable without an LLM | 100% of Jinja2 templates have unit tests that run in < 1 second with no LLM calls |
| G4 | Preserve full backward compatibility | All existing skills not in scope (ec2, storage, iam, database, security, serverless, observability, cfn_terraform, synthesis, data_migration_planning, workload_planning, dependency_discovery) continue to work with zero changes |
| G5 | Ship behind a feature flag | Operators can toggle `USE_TEMPLATE_RENDERER` per skill; default OFF at merge, flipped ON after soak |

### Non-Goals

- Migrating skills outside the 3 in scope (ec2_translation, storage_translation,
  database_translation, iam_translation, security_translation,
  serverless_translation, observability_translation, cfn_terraform, synthesis,
  workload_planning, dependency_discovery, data_migration_planning).
- Changing the reviewer Agent logic. Reviewers will continue to evaluate the
  final rendered HCL the same way they do today.
- Modifying the plan_orchestrator routing, synthesis merge, or the UI.
- Supporting user-authored custom templates (future phase).
- Replacing `terraform_validate` as a safety net. It stays as a backstop even
  after templates guarantee structure.

---

## 3. User Stories

### US-1: Migration operator gets valid Terraform on first pass

> As a **migration operator**, I want the generated Terraform for networking,
> load balancers, and OCM handoff resources to pass `terraform validate`
> without manual fixes, so that I can proceed to `terraform plan` immediately
> after reviewing the migration plan.

**Acceptance Criteria:**

- AC-1.1: Running `terraform validate` on the rendered output for any
  combination of in-scope resources produces zero errors caused by field names,
  nesting, or missing required fields.
- AC-1.2: The rendered `.tf` files are human-readable, properly formatted, and
  include the same `# aws_source_id` traceability comments and `freeform_tags`
  that the current raw-HCL path produces.
- AC-1.3: Variable declarations in `variables.tf` and output declarations in
  `outputs.tf` are consistent with references in `main.tf`.

### US-2: Migration operator sees no behavior change on out-of-scope skills

> As a **migration operator**, I want all skills outside Phase 1 scope to
> behave identically to today, so that ongoing migrations are not disrupted.

**Acceptance Criteria:**

- AC-2.1: The existing `SkillGroup.run()` code path is untouched for any
  `skill_type` not in `{network_translation, loadbalancer_translation,
  ocm_handoff_translation}`.
- AC-2.2: No changes to prompt text, tool lists, or model routing for
  out-of-scope skills.
- AC-2.3: Existing integration tests for out-of-scope skills pass without
  modification.

### US-3: Developer adds a new OCI resource template in under 30 minutes

> As a **developer maintaining the pipeline**, I want each OCI resource type
> to be a self-contained Jinja2 template with a paired Pydantic schema, so
> that adding support for a new resource requires only a template file, a
> schema class, and a test -- not prompt engineering.

**Acceptance Criteria:**

- AC-3.1: Each template lives in a dedicated file under
  `backend/app/templates/terraform/<category>/<template_name>.tf.j2`.
- AC-3.2: Each template has a corresponding Pydantic v2 model under
  `backend/app/templates/schemas/<category>.py` that validates every parameter
  the template expects.
- AC-3.3: A template registry (`backend/app/templates/registry.py`) maps
  `template_name` to `(schema_class, template_path)` and raises a clear error
  on unknown names.
- AC-3.4: A developer can add a new resource by creating one `.tf.j2` file,
  one Pydantic model, one registry entry, and one test file. No changes to
  `skill_group.py` or prompt text are needed.

### US-4: Writer Agent emits structured JSON instead of raw HCL

> As a **developer maintaining the pipeline**, I want the writer Agent for
> in-scope skills to return a list of `{template_name, params}` objects
> instead of raw HCL strings, so that the LLM's job is reduced to semantic
> mapping decisions and the renderer handles syntax.

**Acceptance Criteria:**

- AC-4.1: The writer prompt for in-scope skills instructs the LLM to return
  JSON in the shape:
  ```json
  {
    "resources": [
      {
        "template_name": "oci_core_vcn",
        "params": { "name": "...", "cidr_blocks": ["..."], ... },
        "aws_source_id": "vpc-0abc123"
      }
    ],
    "resource_mappings": [...],
    "gaps": [...],
    "migration_prerequisites": [...]
  }
  ```
- AC-4.2: Each `params` object is validated against the corresponding Pydantic
  schema before rendering. Validation failures are logged with the resource
  index and field path.
- AC-4.3: If the feature flag `USE_TEMPLATE_RENDERER` is OFF for a skill, the
  existing raw-HCL code path is used with no changes.

### US-5: Deterministic renderer produces .tf files from structured JSON

> As a **developer maintaining the pipeline**, I want a `TemplateRenderer`
> service that takes the validated structured output and produces `main.tf`,
> `variables.tf`, and `outputs.tf` deterministically, so that the same input
> always produces the same output.

**Acceptance Criteria:**

- AC-5.1: `TemplateRenderer.render(resources: list[RenderedResource]) -> dict`
  returns `{"main.tf": str, "variables.tf": str, "outputs.tf": str}`.
- AC-5.2: Output is deterministic: same input list in same order produces
  byte-identical output.
- AC-5.3: The renderer injects `# aws_source_id = <id>` comments and
  `freeform_tags` blocks automatically so templates do not need to handle
  traceability boilerplate.
- AC-5.4: A fallback template (`_fallback.tf.j2`) handles any
  `template_name` not in the registry, rendering a `# TODO: manually
  configure` comment block with the raw params as HCL comments, so that no
  resource is silently dropped.

### US-6: Feature flag controls per-skill rollout

> As a **developer or operator**, I want a feature flag
> `USE_TEMPLATE_RENDERER` that can be toggled per skill, so that I can
> gradually migrate skills without an all-or-nothing deployment.

**Acceptance Criteria:**

- AC-6.1: Flag is configurable via environment variable
  (`TEMPLATE_RENDERER_SKILLS=network_translation,loadbalancer_translation`)
  and defaults to empty (all skills use the legacy path).
- AC-6.2: `SkillGroup.__init__` reads the flag and selects the writer prompt
  variant (structured JSON vs. raw HCL) accordingly.
- AC-6.3: Toggling the flag requires only a process restart, not a code
  change or redeployment.

### US-7: Comprehensive test suite covers templates, schemas, and renderer

> As a **developer maintaining the pipeline**, I want a test suite that
> validates every template renders valid HCL for representative inputs, so
> that template regressions are caught in CI before they reach production.

**Acceptance Criteria:**

- AC-7.1: Every Pydantic schema has at least one positive and one negative
  validation test.
- AC-7.2: Every Jinja2 template has a render test that feeds valid params and
  asserts the output contains expected resource type, required fields, and no
  Jinja2 syntax errors.
- AC-7.3: An integration test renders a full multi-resource network stack
  (VCN + 3 subnets + 2 NSGs + IGW + NAT GW + route tables) and runs
  `terraform validate` on the output.
- AC-7.4: An integration test renders a full load balancer stack (LB +
  backend set + listener + health check) and runs `terraform validate`.
- AC-7.5: An integration test renders a full OCM stack (migration +
  migration plan + target asset + replication schedule) and runs
  `terraform validate`.
- AC-7.6: Test coverage for `backend/app/templates/` is >= 95% line coverage.

---

## 4. Detailed Scope

### 4.1 Jinja2 Templates (23 total)

**Core Networking (11):**

| # | template_name | OCI Terraform resource | Notes |
|---|---------------|------------------------|-------|
| 1 | `oci_core_vcn` | `oci_core_vcn` | Regional VCN with DNS label |
| 2 | `oci_core_subnet` | `oci_core_subnet` | Regional or AD-pinned |
| 3 | `oci_core_network_security_group` | `oci_core_network_security_group` | NSG container |
| 4 | `oci_core_network_security_group_security_rule` | `oci_core_network_security_group_security_rule` | Ingress/egress rules |
| 5 | `oci_core_internet_gateway` | `oci_core_internet_gateway` | One per VCN |
| 6 | `oci_core_nat_gateway` | `oci_core_nat_gateway` | One per VCN |
| 7 | `oci_core_route_table` | `oci_core_route_table` | Route rules as nested blocks |
| 8 | `oci_core_security_list` | `oci_core_security_list` | Legacy SL for edge cases |
| 9 | `oci_core_drg` | `oci_core_drg` | Dynamic routing gateway (VPN/peering) |
| 10 | `oci_core_drg_attachment` | `oci_core_drg_attachment` | DRG-to-VCN attachment |
| 11 | `oci_core_local_peering_gateway` | `oci_core_local_peering_gateway` | VCN peering |

**Load Balancer (7):**

| # | template_name | OCI Terraform resource | Notes |
|---|---------------|------------------------|-------|
| 12 | `oci_load_balancer_load_balancer` | `oci_load_balancer_load_balancer` | L7 LB |
| 13 | `oci_load_balancer_backend_set` | `oci_load_balancer_backend_set` | Backend set with health check |
| 14 | `oci_load_balancer_backend` | `oci_load_balancer_backend` | Individual backend |
| 15 | `oci_load_balancer_listener` | `oci_load_balancer_listener` | L7 listener |
| 16 | `oci_network_load_balancer_network_load_balancer` | `oci_network_load_balancer_network_load_balancer` | L4 NLB |
| 17 | `oci_network_load_balancer_backend_set` | `oci_network_load_balancer_backend_set` | NLB backend set |
| 18 | `oci_network_load_balancer_listener` | `oci_network_load_balancer_listener` | L4 listener |

**Cloud Migrations / OCM (4):**

| # | template_name | OCI Terraform resource | Notes |
|---|---------------|------------------------|-------|
| 19 | `oci_cloud_migrations_migration` | `oci_cloud_migrations_migration` | Migration project |
| 20 | `oci_cloud_migrations_migration_plan` | `oci_cloud_migrations_migration_plan` | Plan within migration |
| 21 | `oci_cloud_migrations_target_asset` | `oci_cloud_migrations_target_asset` | Per-instance target |
| 22 | `oci_cloud_migrations_replication_schedule` | `oci_cloud_migrations_replication_schedule` | Replication cadence |

**Fallback (1):**

| # | template_name | Purpose |
|---|---------------|---------|
| 23 | `_fallback` | Catch-all for unknown template_name; renders a commented TODO block |

### 4.2 Pydantic v2 Schemas

One Pydantic `BaseModel` per template. Grouped into modules:

- `backend/app/templates/schemas/networking.py` (11 models)
- `backend/app/templates/schemas/loadbalancer.py` (7 models)
- `backend/app/templates/schemas/cloud_migrations.py` (4 models)

Each model enforces:
- Required fields (e.g. `compartment_id_var: str`)
- Field types and constraints (e.g. `cidr_blocks: list[str]`, each matching CIDR regex)
- Optional fields with OCI-correct defaults
- `model_config = ConfigDict(extra="forbid")` to reject unknown params

### 4.3 Template Renderer Service

New module: `backend/app/templates/renderer.py`

```
class TemplateRenderer:
    def __init__(self, registry: TemplateRegistry)
    def render(self, resources: list[ResourceDirective]) -> dict[str, str]
    def render_single(self, directive: ResourceDirective) -> str
```

Where `ResourceDirective` is:

```
class ResourceDirective(BaseModel):
    template_name: str
    params: dict[str, Any]
    aws_source_id: str
    resource_label: str  # Terraform resource label (e.g. "web_vcn")
```

### 4.4 Modifications to skill_group.py

The changes to `SkillGroup` are minimal and gated behind the feature flag:

1. In `__init__`, check if `self.spec.skill_type` is in
   `TEMPLATE_RENDERER_SKILLS` from settings.
2. If yes, swap the writer prompt to the structured-JSON variant (different
   output format section; same context/mapping/workflow sections).
3. After the writer-reviewer loop completes, if template mode is active,
   pass the `draft["resources"]` list through `TemplateRenderer.render()`
   to produce `{"main.tf": ..., "variables.tf": ..., "outputs.tf": ...}`.
4. Replace the corresponding keys in `draft` with the rendered output before
   returning `SkillRunResult`.

This means the reviewer still sees rendered HCL (the reviewer runs after the
renderer in iteration 1+). The synthesis layer and downstream consumers see
the same `draft` shape they see today.

### 4.5 File Layout

```
backend/app/templates/
    __init__.py
    registry.py              # TemplateRegistry: name -> (schema, template_path)
    renderer.py              # TemplateRenderer: list[ResourceDirective] -> .tf files
    schemas/
        __init__.py
        networking.py        # 11 Pydantic models
        loadbalancer.py      # 7 Pydantic models
        cloud_migrations.py  # 4 Pydantic models
    terraform/
        networking/
            oci_core_vcn.tf.j2
            oci_core_subnet.tf.j2
            ... (11 files)
        loadbalancer/
            oci_load_balancer_load_balancer.tf.j2
            ... (7 files)
        cloud_migrations/
            oci_cloud_migrations_migration.tf.j2
            ... (4 files)
        _fallback.tf.j2

backend/tests/templates/
    __init__.py
    test_schemas_networking.py
    test_schemas_loadbalancer.py
    test_schemas_cloud_migrations.py
    test_renderer.py
    test_registry.py
    test_integration_network_stack.py
    test_integration_lb_stack.py
    test_integration_ocm_stack.py
    conftest.py              # shared fixtures (sample params dicts)
```

---

## 5. Success Metrics

| Metric | Baseline (current) | Target (Phase 1) | Measurement method |
|--------|-------------------|-------------------|-------------------|
| Schema bug rate (wrong field, nesting, missing required) on in-scope skills | ~15-20% of runs produce at least one `terraform validate` error | 0% for template-rendered resources | Automated test suite + production telemetry on validate results |
| Writer output tokens per skill run (network_translation) | ~4,000-8,000 tokens | ~400-1,500 tokens (structured JSON) | Token usage logged in `SkillRunResult` metadata |
| Writer output tokens per skill run (loadbalancer_translation) | ~3,000-6,000 tokens | ~300-1,200 tokens | Same |
| Writer output tokens per skill run (ocm_handoff_translation) | ~2,500-5,000 tokens | ~250-800 tokens | Same |
| Average review iterations to APPROVED | ~2.1 iterations | ~1.2 iterations (fewer structural fixes) | Logged `iterations` field in `SkillRunResult` |
| Template unit test coverage | 0% (no templates exist) | >= 95% line coverage | `pytest --cov` |
| Time to add a new resource template | N/A (requires prompt changes) | < 30 minutes (template + schema + test) | Developer self-report |

---

## 6. Rollout Plan

### Phase 1a: Build and Test (Week 1-2)

1. Create `backend/app/templates/` directory structure.
2. Implement Pydantic schemas for all 22 resource types.
3. Author 23 Jinja2 templates (11 + 7 + 4 + 1 fallback).
4. Implement `TemplateRegistry` and `TemplateRenderer`.
5. Write unit tests for all schemas and templates.
6. Write integration tests that run `terraform validate` on rendered stacks.

### Phase 1b: Wire into Pipeline (Week 2-3)

1. Add `TEMPLATE_RENDERER_SKILLS` setting to `app/config.py` (default: empty string).
2. Create structured-JSON writer prompt variant.
3. Modify `SkillGroup.__init__` and post-loop rendering path (gated by flag).
4. Run existing integration tests with flag OFF to confirm zero regression.
5. Run new integration tests with flag ON for in-scope skills.

### Phase 1c: Soak and Validate (Week 3-4)

1. Deploy with flag OFF. Confirm production behavior is unchanged.
2. Enable for `network_translation` only (`TEMPLATE_RENDERER_SKILLS=network_translation`).
3. Run 10+ real migrations. Compare `terraform validate` error rates and token
   usage against baseline.
4. If soak passes, enable `loadbalancer_translation`.
5. If soak passes, enable `ocm_handoff_translation`.
6. After all 3 skills soak for 1 week with zero regressions, make the flag
   default to all 3 skills ON and remove the legacy prompt variant for those
   skills in Phase 2.

### Rollback

At any point, setting `TEMPLATE_RENDERER_SKILLS=""` (empty) reverts all skills
to the legacy raw-HCL code path. No code deployment is needed -- only a
process restart.

---

## 7. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM does not reliably produce the structured JSON output format | Medium | High -- pipeline breaks | Constrained output format via `response_format` (structured outputs) if the model supports it; robust JSON extraction fallback in `_extract_json`; validation errors trigger a retry with explicit error feedback |
| Templates miss edge cases present in LLM free-form output (e.g. conditional blocks for optional features) | Medium | Medium -- gaps in coverage | Each template supports optional params with sensible defaults; the fallback template catches any resource the registry does not cover; soak period surfaces gaps before full rollout |
| Pydantic validation is too strict, rejecting valid LLM output | Medium | Medium -- false rejections increase iterations | Use `model_config = ConfigDict(extra="ignore")` during soak, switch to `extra="forbid"` after field coverage is confirmed; log all validation errors for review |
| Reviewer Agent confused by new output format | Low | Low -- reviewer still sees rendered HCL | Reviewer prompt and tools are unchanged; it reviews the final rendered `.tf` files, not the intermediate JSON |
| Performance regression from Jinja2 rendering step | Low | Low | Jinja2 rendering is < 10ms for 30 resources; negligible vs. LLM round-trip |

---

## 8. Open Questions

1. **Synthesis pass-through:** The `synthesis` skill merges outputs from all
   prior skills into a unified Terraform package. Should synthesis also consume
   structured JSON, or does it continue to merge raw HCL strings? (Recommendation:
   defer to Phase 2; synthesis sees rendered HCL from Phase 1 skills.)

2. **`terraform_validate` tool for template skills:** If templates guarantee
   structural correctness, should we remove the `terraform_validate` tool from
   in-scope writer Agents to save a tool-call round-trip? (Recommendation: keep
   it as a safety net during soak; revisit removal in Phase 2.)

3. **Variable naming conventions:** Templates need a convention for variable
   names (e.g. `var.compartment_id`, `var.vcn_id`). Should variable names be
   deterministic from the AWS source ID, or should the LLM choose them?
   (Recommendation: deterministic -- derive from `aws_source_id` with a
   sanitization function, e.g. `vpc-0abc123` becomes `vcn_vpc_0abc123`.)

4. **Multi-resource cross-references:** A subnet template references a VCN via
   `oci_core_vcn.<label>.id`. The renderer needs to resolve these
   cross-references. Should cross-ref resolution be in the renderer or in the
   schema (as explicit `vcn_resource_label` params)? (Recommendation: explicit
   params -- the LLM specifies `vcn_ref: "web_vcn"` and the template renders
   `oci_core_vcn.web_vcn.id`.)

5. **Jinja2 vs. string templates:** Jinja2 adds a dependency but supports
   conditionals and loops natively. Is the team comfortable with the Jinja2
   dependency? (Note: Jinja2 is already a transitive dependency of FastAPI.)

---

## Appendix A: Example End-to-End Flow

**Input** (from plan_orchestrator, network_translation skill):
```json
{
  "vpc_id": "vpc-0abc123",
  "cidr_block": "10.0.0.0/16",
  "subnets": [
    {"subnet_id": "subnet-001", "cidr_block": "10.0.1.0/24", "name": "web"},
    {"subnet_id": "subnet-002", "cidr_block": "10.0.2.0/24", "name": "app"}
  ],
  "security_groups": [
    {"group_id": "sg-001", "name": "web-sg", "rules": [...]}
  ]
}
```

**Writer Agent output** (new structured format):
```json
{
  "resources": [
    {
      "template_name": "oci_core_vcn",
      "resource_label": "web_vcn",
      "aws_source_id": "vpc-0abc123",
      "params": {
        "compartment_id_var": "compartment_id",
        "display_name": "web-vcn",
        "cidr_blocks": ["10.0.0.0/16"],
        "dns_label": "webvcn"
      }
    },
    {
      "template_name": "oci_core_subnet",
      "resource_label": "web_subnet",
      "aws_source_id": "subnet-001",
      "params": {
        "compartment_id_var": "compartment_id",
        "vcn_ref": "web_vcn",
        "display_name": "web",
        "cidr_block": "10.0.1.0/24",
        "dns_label": "web"
      }
    }
  ],
  "resource_mappings": [
    {"aws_type": "AWS::EC2::VPC", "aws_id": "vpc-0abc123", "oci_type": "oci_core_vcn"}
  ],
  "gaps": [],
  "migration_prerequisites": []
}
```

**Renderer output** (`main.tf` excerpt):
```hcl
resource "oci_core_vcn" "web_vcn" {
  # aws_source_id = vpc-0abc123
  compartment_id = var.compartment_id
  display_name   = "web-vcn"
  cidr_blocks    = ["10.0.0.0/16"]
  dns_label      = "webvcn"

  freeform_tags = {
    aws_source_id = "vpc-0abc123"
    managed_by    = "oci-iaas-migration"
  }
}

resource "oci_core_subnet" "web_subnet" {
  # aws_source_id = subnet-001
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.web_vcn.id
  display_name   = "web"
  cidr_block     = "10.0.1.0/24"
  dns_label      = "web"

  freeform_tags = {
    aws_source_id = "subnet-001"
    managed_by    = "oci-iaas-migration"
  }
}
```

Token comparison: the writer output JSON is ~350 tokens. The equivalent raw HCL
for a VCN + 2 subnets + 1 NSG with rules is ~1,800 tokens. That is a ~5x
reduction even for this small example; larger stacks see 8-10x.
