# ALB / NLB → OCI Load Balancer Conversion Rules

Prose guidance that doesn't fit in the mapping table.

## Type mapping

| AWS LB type | OCI target | Terraform resources |
|---|---|---|
| `application` (ALB) | OCI Load Balancer (Layer 7) | `oci_load_balancer_*` family |
| `network` (NLB) | OCI Network Load Balancer (Layer 4) | `oci_network_load_balancer_*` family |
| `gateway` (GLB) | **No OCI equivalent** — flag as CRITICAL |

The two families have **different resource names and property names** — don't mix them within one LB.

## Ordering (per LB)

1. LB itself (`oci_load_balancer_load_balancer` or `oci_network_load_balancer_network_load_balancer`)
2. Backend sets (one per AWS target group)
3. Backends (one per registered target within a target group) — optional, can be managed separately
4. Listeners (one per AWS listener)
5. (ALB only) Path route sets and hostnames if AWS used advanced routing

## Scheme

- `internet-facing` → `is_private = false`
- `internal` → `is_private = true`

## Shape (ALB)

Always use flexible shape with explicit min/max:
```
shape = "flexible"
shape_details {
  minimum_bandwidth_in_mbps = 10
  maximum_bandwidth_in_mbps = 100
}
```
10–100 Mbps is the right starting point; tune later via runbook.

## Target group → backend set

- 1 AWS target group = 1 `oci_load_balancer_backend_set`.
- `health_check` → `health_checker`:
  - `path` → `url_path` (HTTP/HTTPS only; omit for TCP)
  - `interval` (seconds) → `interval_ms` (×1000)
  - `timeout` (seconds) → `timeout_in_millis` (×1000)
  - `healthy_threshold` → `retries`
- Policy: `ROUND_ROBIN` by default. If AWS used `least_outstanding_requests`, emit `LEAST_CONNECTIONS`.

## Listener mapping

| AWS listener | OCI listener |
|---|---|
| HTTP | `HTTP` |
| HTTPS | `HTTPS` — requires a cert (see below) |
| TCP | `TCP` (NLB) |
| TCP_UDP | Split into two listeners — no combined variant on OCI |

## HTTPS / TLS

- AWS ACM certs → OCI Certificate Service. OCI does **not** auto-import ACM certs; the cert must be imported manually or requested via `oci_certificates_certificate`.
- Reference via `var.certificate_ids` (list of OCIDs); emit a placeholder variable with a comment explaining the prerequisite.
- Flag as HIGH for every HTTPS listener.

## Backends (target registration)

- AWS registers targets by instance ID or IP. OCI backends take an IP + port.
- If the input has target IDs rather than IPs, emit the backend with `var.backend_instance_ids[n]` and a comment — the IP lookup is deferred until apply time.

## Path-based / host-based routing (ALB only)

- AWS listener rules with host or path conditions → `oci_load_balancer_path_route_set` + `oci_load_balancer_hostname` on the listener.
- Each unique path pattern becomes one `path_route` entry.

## Tags

- `freeform_tags` on the LB itself and on every backend set.

## Gaps to always flag

- **Gateway Load Balancer:** no equivalent. CRITICAL.
- **AWS WAF integration:** WAF on OCI is a separate service (`oci_waf_*`). Flag HIGH with prerequisite.
- **Target type `lambda`:** CRITICAL; function backends use `oci_functions_function` + API Gateway integration, not LB.
- **Cross-zone load balancing:** OCI LB is always cross-AD within a region; silently drop the field if it's `true`, flag INFO if `false` ("OCI LB is always cross-AD — setting ignored").
