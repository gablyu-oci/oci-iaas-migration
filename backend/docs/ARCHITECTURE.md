# Migration Pipeline Architecture

## Overview

The OCI IaaS Migration pipeline converts AWS infrastructure into OCI-native Terraform configurations through a 5-layer processing pipeline.

## Pipeline Layers

```
 Input Resources (AWS CloudFormation / discovery)
           |
           v
 ┌─────────────────────────────────┐
 │  Layer 1: Skill Writers         │  Per-domain LLM agents produce structured
 │  (per_skill structured JSON)    │  JSON specs (9 templated skills) or
 │                                 │  free-form HCL (cfn_terraform).
 └──────────────┬──────────────────┘
                |
                v
 ┌─────────────────────────────────┐
 │  Layer 2: Resource Graph        │  specs_to_graph() builds typed nodes +
 │  (ResourceGraph + validation)   │  explicit edges. Phase 3 per-skill
 │                                 │  validation catches errors early.
 └──────────────┬──────────────────┘
                |
                v
 ┌─────────────────────────────────┐
 │  Layer 3: Template Renderer     │  Jinja2 templates + Pydantic schemas
 │  (Jinja2 HCL generation)       │  produce schema-correct HCL from graph
 │                                 │  nodes. Deterministic, no LLM needed.
 └──────────────┬──────────────────┘
                |
                v
 ┌─────────────────────────────────┐
 │  Layer 4: Synthesis Composer    │  Merges per-skill HCL into one Terraform
 │  (merge + dedup + providers.tf) │  module. Deduplicates variables, outputs.
 │                                 │  Generates canonical providers.tf.
 └──────────────┬──────────────────┘
                |
                v
 ┌─────────────────────────────────┐
 │  Layer 5: Bundle Builder        │  Reorganizes into deployable bundle:
 │  + Polish + Validator           │  terraform/, runbooks/, reports/, debug/.
 │                                 │  Optional polish agent + terraform validate.
 └─────────────────────────────────┘
                |
                v
         Final Bundle (ZIP)
```

## Key Components

| Component | Location | Role |
|-----------|----------|------|
| Skill Writers | `app/agents/skill_group.py` | LLM agents per AWS domain |
| Resource Graph | `app/services/resource_graph.py` | Typed node/edge graph |
| Template Renderer | `app/services/template_renderer.py` | Jinja2 HCL generation |
| Synthesis Composer | `app/services/synthesis_composer.py` | Multi-file merge + dedup |
| Bundle Builder | `app/services/bundle_builder.py` | Final layout + manifest |
| Per-Skill Validator | `app/services/per_skill_validator.py` | `terraform validate` checkpoint |
| Synthesis Validator | `app/services/synthesis_validator.py` | Post-merge validation |
| Model Gateway | `app/gateway/model_gateway.py` | Model selection + routing |

## Structured Output Skills

9 of the 10 translation skill writers emit structured JSON specs that flow through the graph + template path:
- network_translation, ec2_translation, storage_translation, loadbalancer_translation
- iam_translation, security_translation, serverless_translation, observability_translation
- ocm_handoff_translation

The remaining skill (`cfn_terraform`) generates free-form HCL and bypasses the template layer.

## Model Routing

Models are selected per agent role in `app/gateway/model_gateway.py`. Defaults
and env-var overrides are documented in [STARTUP.md](../../STARTUP.md#environment-variables)
and `app/config.py`.

- Templated skill writers -> fast non-reasoning model (configurable via `LLM_TEMPLATED_WRITER_MODEL`)
- Free-form writers (cfn_terraform) -> reasoning model (configurable via `LLM_FREEFORM_WRITER_MODEL`)
- Reviewers -> smaller reasoning model (`LLM_REVIEWER_MODEL`)
- Orchestrator -> reasoning model (`LLM_ORCHESTRATOR_MODEL`)

## Reference

- AWS→OCI type mappings: single source of truth is `backend/data/mappings/resources.yaml`.
- Live agent/tool/wave reference: [`docs/agent-architecture.md`](../../docs/agent-architecture.md),
  auto-generated from `app/agents/registry.py` via `scripts/render_agent_docs.py`.
