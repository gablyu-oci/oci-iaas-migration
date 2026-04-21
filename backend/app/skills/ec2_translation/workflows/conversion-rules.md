# EC2 → OCI Compute Conversion Rules

Prose guidance that doesn't fit in `data/mappings/resources.yaml`.
The canonical table is injected into the system prompt alongside this file;
read it first for the AWS type → OCI terraform resource map.

## Ordering

Create in this order — each later step depends on IDs from earlier steps:

1. Compartment (prerequisite, typically already exists — use `var.compartment_id`)
2. VCN + subnet + NSG (handled by `network_translation`; reference via variables)
3. Instance Configuration (for ASG'd fleets) or Instance (for standalone)
4. Block Volumes (`oci_core_volume`) for data volumes
5. Volume Attachments (`oci_core_volume_attachment`)
6. Instance Pool (for ASG'd fleets) — references the Instance Configuration

## Root volume vs data volumes

- **Root volume is NOT a separate resource in OCI** — unlike AWS where the root EBS volume is its own resource. In OCI, the boot volume is created inline via `source_details { source_type = "image" }` on `oci_core_instance` and sized via `boot_volume_size_in_gbs`.
- Data volumes map 1:1 to `oci_core_volume` + `oci_core_volume_attachment`.
- **Don't generate a `oci_core_volume` resource for the root volume.** That's a common mistake — it would create a detached volume that duplicates the boot volume.

## Instance type selection

Shape recommendations come from `app.services.rightsizing_engine` (which reads
`data/mappings/instance_shapes.yaml`). The LLM should:

- Trust the recommended shape when present in the input. Don't second-guess it.
- For unmapped AWS types, fall back to `VM.Standard.E5.Flex` and flag as a MEDIUM gap.
- **ARM-based Ampere (`VM.Standard.A2.Flex`)** is cheapest but only works for AMD64-compatible workloads that have ARM builds. If source AMI's architecture is `x86_64`, don't recommend A2.Flex.

## SSH keys and instance principal

- OCI has no concept of AWS key pairs as a standalone resource. The public key is passed directly to `oci_core_instance` via `metadata.ssh_authorized_keys`. Use `var.ssh_public_key`.
- AWS IAM instance profiles → OCI dynamic groups + instance principal. This is NOT a Terraform resource on the instance itself — just a COMMENT noting that a dynamic group statement must be created in IAM. Point the LLM at the `iam_translation` skill's output.

## Auto Scaling Groups

- ASG → `oci_autoscaling_auto_scaling_configuration` + `oci_core_instance_configuration` + `oci_core_instance_pool`. Three resources, not one.
- Launch Configuration / Launch Template contents become the `oci_core_instance_configuration.instance_details`.
- `min_size` / `max_size` / `desired_capacity` go on the `oci_core_instance_pool`, not the autoscaling config.
- Health check grace period → `oci_autoscaling_auto_scaling_configuration.cool_down_in_seconds`.

## Tags

- Always set `freeform_tags` to the full AWS tag map.
- Don't use `defined_tags` unless the user has a tag namespace configured — that's a MEDIUM-severity gap otherwise.

## Gaps to always flag

- **Spot instances:** no direct OCI equivalent. Flag as HIGH severity; recommend preemptible capacity (different semantics) or normal instances.
- **Dedicated hosts:** require `oci_core_dedicated_vm_host` — separate resource. Usually HIGH.
- **Placement groups:** no direct equivalent; OCI uses `fault_domain` for availability, not performance locality.
- **EBS-optimized flag:** irrelevant in OCI (all block volume I/O is network-backed); don't emit a gap, just drop the field silently.
