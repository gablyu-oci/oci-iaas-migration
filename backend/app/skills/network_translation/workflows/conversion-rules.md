# VPC → OCI VCN Conversion Rules

Prose guidance that doesn't fit in `data/mappings/resources.yaml`.
The canonical mapping table is injected alongside this file.

## Ordering

OCI networking resources must be created in this order:

1. VCN
2. Internet Gateway (if any public subnet exists)
3. NAT Gateway (if any private subnet needs outbound)
4. Service Gateway (if workloads reach `oci_core_services`, i.e. Object Storage over private link)
5. Route Tables (referencing the gateways from #2–#4)
6. Subnets (referencing VCN + route table + optionally NSGs)
7. Network Security Groups
8. Security rules within each NSG

Attempting to create subnets before their route table causes terraform apply failures.

## Regional vs AZ scope — biggest source of bugs

- **AWS subnets are AZ-pinned. OCI subnets are regional by default.** An AWS stack with one subnet per AZ typically collapses to a single regional OCI subnet.
- If the customer truly needs AZ-pinning (legacy compliance, latency-sensitive pairing with a specific AD), set `availability_domain` on the subnet. Do **not** do this by default.
- `prohibit_public_ip_on_vnic` is OCI's public/private flag — it's on the subnet, not the route. A public subnet in AWS becomes `prohibit_public_ip_on_vnic = false` in OCI.

## CIDR constraints

- VCN CIDR must be between /16 and /30. If the input AWS VPC has a /12, FAIL with a CRITICAL gap ("cannot map /12 VPC; split into multiple /16 VCNs").
- Subnet CIDRs must fit entirely within the VCN CIDR.
- Subnets across ADs in OCI share the same VCN-level CIDR pool — no separate per-AZ allocation like AWS.

## NSG vs Security List

- Prefer NSGs (`oci_core_network_security_group`) over Security Lists for everything new.
- NSGs attach to VNICs (fine-grained); Security Lists attach to subnets (coarse).
- Don't mix — choose one model per translation to keep the output legible.

## Protocol numbers (NSG rules)

| AWS protocol | OCI protocol field |
|---|---|
| `tcp` | `6` |
| `udp` | `17` |
| `icmp` | `1` |
| `-1` (all) | `all` |

For protocol `-1`, omit `tcp_options` / `udp_options` entirely and set `source_type`/`destination_type` to `CIDR_BLOCK`.

## Security Group rules

- `ingress` / `egress` distinction → `direction = "INGRESS"` / `"EGRESS"` in OCI.
- Stateless vs stateful: AWS SGs are always stateful. OCI NSGs can be stateless; default to `stateless = false` for parity.
- Source/destination CIDR on AWS → `source = "0.0.0.0/0"` + `source_type = "CIDR_BLOCK"` on OCI.

## Network Interfaces (ENIs)

- **Primary ENI** (`device_index = 0`) has no OCI Terraform resource — it's auto-created with the instance. Don't emit anything for it.
- **Secondary ENIs** (`device_index > 0`) → `oci_core_vnic_attachment`.
- ENI-to-instance association in AWS becomes the `instance_id` argument on the VNIC attachment.

## NAT Gateway

- OCI NAT is **regional, not per-AZ**. An AWS stack with one NAT per AZ collapses to a single OCI NAT gateway — flag that as INFO, not a gap.
- NAT's `block_traffic = false` by default — don't change without reason.

## Gaps to always flag

- **VPC peering** / Transit Gateway → OCI equivalents are `oci_core_local_peering_gateway` (same region), `oci_core_remote_peering_connection` (cross-region), and DRG for hub-and-spoke. Flag as HIGH.
- **VPN / Direct Connect** → `oci_core_ipsec` / `oci_core_drg` + `oci_core_drg_attachment`. Flag as HIGH with a prerequisite.
- **VPC Flow Logs** → OCI VCN Flow Logs is a separate service; not translated here. Flag as MEDIUM.
