# Phase 5: Model Routing & Operational Hardening

## Model Routing Strategy

### Problem

Reasoning models (GPT-5.x, o-series) are slow and expensive. Templated skill writers don't need reasoning capability — they produce small JSON specs that get validated by Pydantic schemas. Sending these through a reasoning model wastes tokens and adds latency.

### Solution

Phase 5 introduces tiered model routing:

| Skill Category | Model Tier | Rationale |
|----------------|-----------|-----------|
| Templated writers (9 skills) | Fast non-reasoning (e.g., gpt-4o-mini, claude-haiku) | Output is small structured JSON; schema validation catches errors |
| cfn_terraform writer | Reasoning (e.g., gpt-5.4) | Generates free-form HCL; benefits from chain-of-thought |
| data_migration_planning | Fast non-reasoning | Produces structured plans, not complex HCL |
| Review agents | Smaller reasoning (e.g., gpt-5.4-mini) | Needs to analyze and score, but output is small |
| Orchestrator | Reasoning | Multi-step planning + tool coordination |

### Configuration

Environment variables (all optional — defaults to existing `LLM_WRITER_MODEL` if unset):

```
LLM_TEMPLATED_WRITER_MODEL=oci/openai.gpt-4o-mini   # fast model for structured skills
LLM_FREEFORM_WRITER_MODEL=oci/openai.gpt-5.4         # reasoning model for cfn_terraform
LLM_WRITER_MODEL=oci/openai.gpt-5.4                   # fallback for all writers
LLM_REVIEWER_MODEL=oci/openai.gpt-5.4-mini            # review/scoring agents
LLM_ORCHESTRATOR_MODEL=oci/openai.gpt-5.4             # top-level orchestrator
```

### Implementation

Model routing lives in `app/gateway/model_gateway.py`. The `MODEL_ROUTING` dict maps `(skill_type, agent_type)` pairs to resolver functions. Each resolver reads the appropriate setting at call time, so changing an env var takes effect immediately.

```python
get_model("network_translation", "enhancement")  # -> LLM_TEMPLATED_WRITER_MODEL
get_model("cfn_terraform", "enhancement")         # -> LLM_FREEFORM_WRITER_MODEL
get_model("network_translation", "review")        # -> LLM_REVIEWER_MODEL
```

## Provider Version Pinning

### Problem

Using `>= 6.0.0` without an upper bound means a provider update on Friday can break Terraform plans that worked on Tuesday.

### Solution

`CANONICAL_PROVIDERS` in `synthesis_composer.py` pins the OCI provider to `>= 6.0.0, < 7.0.0`:

```hcl
required_providers {
  oci = {
    source  = "oracle/oci"
    version = ">= 6.0.0, < 7.0.0"
  }
}
```

Update the pin when upgrading to a new major version.

## Regression Test Fixtures

Captured pipeline outputs are stored in `tests/fixtures/<scenario>/`:
- `resource_mapping.json` — input AWS resources
- `skill_specs.json` — per-skill structured output (what the LLM would produce)
- `expected_graph_nodes.json` — expected ResourceGraph node IDs
- `expected_bundle_files.json` — expected files in the composed output

### Adding a New Fixture

1. Run a successful plan on a workload
2. Capture the resource mapping from the discovery phase
3. Capture each skill's structured JSON output (from the TranslationJob results)
4. Run the captured specs through `specs_to_graph()` and record the node IDs
5. Run through `compose_from_graph()` and record the output filenames
6. Save all files in `tests/fixtures/<scenario_name>/`
7. Add a test class in `tests/test_e2e_<scenario_name>.py` following the pattern in `test_e2e_multi_tier_vpc.py`
