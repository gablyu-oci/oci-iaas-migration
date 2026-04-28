# multi_tier_vpc fixture

Regression fixture representing a multi-tier VPC migration:
- 1 VCN (from AWS VPC)
- 2 subnets (public + private)
- 1 internet gateway
- 1 NAT gateway
- 2 route tables (public + private)
- 2 security lists (web + app)
- 2 compute instances (web + app)
- 1 load balancer + backend set + HTTP listener

## How to add a new fixture

1. Create a new directory under `backend/tests/fixtures/<name>/`.
2. Capture the input `resource_mapping.json` from the resource-mapping stage.
3. Run the pipeline with a mocked LLM (or capture real LLM output) and save
   the per-skill structured specs as `skill_specs.json`.  This dict is keyed
   by skill type (`network_translation`, `ec2_translation`, etc.) and each
   value is a list of `{template, label, params}` dicts.
4. Feed the specs through `specs_to_graph` and record the sorted node IDs
   in `expected_graph_nodes.json`.
5. Run `compose_from_graph` and record the output filenames in
   `expected_bundle_files.json`.
6. Write an E2E test class in `backend/tests/test_e2e_<name>.py` that loads
   the fixture and asserts graph nodes, rendered HCL, bundle files, and
   provider version pins.
