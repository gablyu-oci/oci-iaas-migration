# EBS → OCI Block Volume Conversion Rules

Prose guidance that doesn't fit in the mapping table.

## Ordering

1. `oci_core_volume` (one per EBS volume)
2. `oci_core_volume_attachment` (one per attachment; references volume + instance)

Unattached EBS volumes → emit only `oci_core_volume`, no attachment.

## Volume type → `vpus_per_gb`

The canonical table (`resources.yaml → storage.ebs_to_block_volume`) is the source of truth for `vpus_per_gb`. Quick reference:

| EBS type | `vpus_per_gb` | Use case |
|---|---|---|
| `gp3` / `gp2` | 10 | Balanced (default) |
| `io1` / `io2` | 20 | Higher perf, latency-sensitive |
| `st1` / `sc1` | 0 | Low cost, throughput-oriented |

For `unknown` or unmapped, default to `10` and flag as MEDIUM.

## Attachment type

- Default to `attachment_type = "paravirtualized"` — this is what every standard `VM.*` shape uses.
- Only use `"iscsi"` when source evidence indicates the workload needs iSCSI semantics (multi-attach, SAN-style management). Most migrations don't.

## Root volumes vs data volumes

- **The root EBS volume is part of the instance**, not a separate `oci_core_volume` — `ec2_translation` handles it via `source_details`. Don't emit a volume here for the root.
- Only data volumes (the ones with `device_name != /dev/sda1` and similar) get `oci_core_volume` resources.

## Encryption

- OCI encrypts every block volume by default using Oracle-managed keys. If the source AWS volume has `Encrypted: true` with the default KMS CMK, emit nothing extra — just a NOTE: "OCI block volumes encrypted by default."
- If the source uses a customer-managed CMK, set `kms_key_id` on the volume and flag as MEDIUM ("customer key must be imported into OCI Vault before apply").

## Sizing

- `size_in_gbs` must come from the source `Size` field. OCI minimum is 50 GB — if source is smaller, round up to 50 and add an INFO note.
- `is_auto_tune_enabled = true` for gp3/io1/io2 volumes (lets OCI auto-adjust performance).

## Snapshots / AMIs

- Snapshots are out of scope for this skill — `data_migration` handles snapshot → boot-volume-backup mapping.
- If a snapshot ID appears in the input, emit a NOTE pointing at `data_migration`, don't try to model it here.

## Tags

- Copy every AWS tag to `freeform_tags`.
