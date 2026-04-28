# Phase 1 Documentation: OCI IaaS Migration -- Template Layer

## 1. Decision Log

- **Template source**: all templates adapted from real working OCI HCL in the reference projects (`ai-accelerator-tf/network.tf`, `cfn_terraform/output/web-app-stack-terraform/main.tf`, `ocm_handoff_translation/conversion-rules.md`).
- **VCN template** uses `cidr_blocks` (list) instead of `cidr_block` (string) -- aligns with OCI provider v6+ which deprecated the singular form.
- **NSG security rules** use separate `oci_core_network_security_group_security_rule` resources (not inline) -- matches the reference CFN output and is more flexible for per-rule management.
- **Security lists** modeled with inline rules (matching ai-accelerator-tf pattern) since that is the typical migration use case.
- **Load balancer** always uses flexible shape (`shape_details` with `min/max bandwidth`) -- this is the current OCI best practice.
- **OCM target_asset**: `preferred_shape_type` at top level (VM/BM bucket), actual shape in `user_spec.shape` -- this was a frequent source of bugs when LLM generated from scratch.
- **Route table attachment** modeled as a separate resource even though in practice it is done via the subnet's `route_table_id` attribute -- the template exists for cases where the attachment needs to be managed independently.
- **Security list attachment** is a no-op template (comment only) -- in OCI, security lists are attached via `security_list_ids` on the subnet resource.

---

## 2. Coverage Report

### network_translation skill

| AWS Input Type | OCI Template | Notes |
|---|---|---|
| AWS::EC2::VPC | core/vcn | 1:1 mapping, CIDR constraint checked |
| AWS::EC2::Subnet | core/subnet | Regional by default (no AZ pin unless explicitly needed) |
| AWS::EC2::InternetGateway | core/internet_gateway | |
| AWS::EC2::NatGateway | core/nat_gateway | Regional (collapses per-AZ NATs) |
| AWS::EC2::RouteTable | core/route_table | Inline route_rules |
| AWS::EC2::RouteTable (association) | core/route_table_attachment | |
| AWS::EC2::SecurityGroup (SL mode) | core/security_list | When subnet-level SGs preferred |
| AWS::EC2::SecurityGroup (NSG mode) | core/network_security_group + core/network_security_group_security_rule | Preferred approach |
| AWS::EC2::EIP | core/public_ip | RESERVED lifetime |
| AWS::EC2::NetworkInterface | free_form_hcl | Secondary ENIs only; primary ENI auto-created |
| AWS::EC2::NetworkAcl | core/security_list | NACLs map to security lists |

### loadbalancer_translation skill

| AWS Input Type | OCI Template | Notes |
|---|---|---|
| AWS::ElasticLoadBalancingV2::LoadBalancer (ALB) | load_balancer/load_balancer | L7, flexible shape |
| AWS::ElasticLoadBalancingV2::LoadBalancer (NLB) | free_form_hcl | Uses oci_network_load_balancer_* family (different provider) |
| AWS::ElasticLoadBalancingV2::TargetGroup | load_balancer/backend_set | 1:1 mapping |
| AWS::ElasticLoadBalancingV2::Listener | load_balancer/listener | HTTP/HTTPS/TCP |
| AWS::ElasticLoadBalancing::LoadBalancer (Classic) | load_balancer/load_balancer + load_balancer/backend_set + load_balancer/listener | Decomposed into 3 resources |
| HTTPS cert reference | load_balancer/certificate | Placeholder; manual import needed |
| Host-based routing | load_balancer/hostname | Per-hostname resource |
| Path-based routing | load_balancer/path_route_set | Per-route-set resource |
| Header manipulation rules | load_balancer/rule_set | ADD/REMOVE header actions |

### ocm_handoff_translation skill

| AWS Input Type | OCI Template | Notes |
|---|---|---|
| AWS::EC2::Instance (OCM-eligible) | cloud_migrations/migration + cloud_migrations/migration_plan + cloud_migrations/target_asset | One migration wrapper, one plan, one target_asset per instance |
| Replication schedule | cloud_migrations/replication_schedule | Optional; one per migration |

---

## 3. Known Gaps (use free_form_hcl fallback)

| AWS Input Type | Gap Reason | Fallback |
|---|---|---|
| VPC Peering | oci_core_local_peering_gateway not yet templated | free_form_hcl |
| Transit Gateway | oci_core_drg family not yet templated | free_form_hcl |
| VPN Connection | oci_core_ipsec not yet templated | free_form_hcl |
| Direct Connect | oci_core_drg + oci_core_drg_attachment not yet templated | free_form_hcl |
| Route53 HostedZone/RecordSet | DNS not yet templated | free_form_hcl |
| VPC Endpoint | oci_core_service_gateway partial coverage | free_form_hcl |
| NLB (Network Load Balancer) | Uses oci_network_load_balancer_* (different resource family) | free_form_hcl |
| Gateway Load Balancer | No OCI equivalent | CRITICAL gap, flag only |
| Lambda target on LB | No OCI equivalent on LB | CRITICAL gap |

---

## 4. Architecture Summary

Brief text-diagram of the data flow:

```
Writer Agent -> JSON specs [{template, label, params}]
    |
    v
Pydantic validation (TEMPLATE_REGISTRY schemas)
    |
    v
Jinja2 rendering (templates/oci/**/*.tf.j2)
    |
    v
Grouped HCL files {network.tf, loadbalancer.tf, ocm/main.tf}
    |
    v
synthesis_composer.py (unchanged -- receives HCL as before)
```

---

## 5. Template Count

- **Core networking**: 11 (vcn, subnet, internet_gateway, nat_gateway, route_table, route_table_attachment, security_list, security_list_attachment, network_security_group, network_security_group_security_rule, public_ip)
- **Load balancer**: 7 (load_balancer, backend_set, listener, certificate, hostname, path_route_set, rule_set)
- **Cloud migrations**: 4 (migration, migration_plan, target_asset, replication_schedule)
- **Fallback**: 1 (free_form_hcl)
- **Total**: 23

---

## 6. Test Coverage

- `test_templates_render.py`: Golden-file tests for all 23 templates
- `test_template_renderer.py`: Renderer routing, grouping, error handling
- `test_skill_writer_structured_output.py`: Integration with SkillGroup
- `test_writer_invalid_specs.py`: Malformed spec handling
