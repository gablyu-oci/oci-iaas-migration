# AWS Security Services → OCI Vault / Certificates / WAF Conversion Rules

Prose guidance that doesn't fit in the mapping table.

## Service-level mapping

| AWS service | OCI target | Terraform resources |
|---|---|---|
| KMS | Vault + Keys | `oci_kms_vault`, `oci_kms_key` |
| Secrets Manager | Vault Secret | `oci_vault_secret` |
| SSM Parameter Store (`SecureString`) | Vault Secret | `oci_vault_secret` |
| SSM Parameter Store (`String`, `StringList`) | App Config / Vault Secret | `oci_vault_secret` (if sensitive) or inline `locals` |
| ACM (private + imported) | Certificate Service | `oci_certificates_management_certificate` |
| ACM (public auto-renewed) | Certificate Service (import) | `oci_certificates_management_certificate` + manual DNS validation |
| WAFv2 Web ACL | Web Application Firewall | `oci_waf_web_app_firewall`, `oci_waf_web_app_firewall_policy` |
| WAFv2 IP Set | WAF Network Address List | `oci_waf_network_address_list` |

## The vault-first rule

**Every key and secret in OCI lives inside a Vault.** You MUST emit exactly one `oci_kms_vault` at the top of the output, then attach every key and secret to its `id`. Do NOT emit standalone keys without a parent vault.

```hcl
resource "oci_kms_vault" "main" {
  compartment_id = var.compartment_ocid
  display_name   = "migration-vault"
  vault_type     = "DEFAULT"     # or "VIRTUAL_PRIVATE" for dedicated HSM
}

resource "oci_kms_key" "app" {
  compartment_id      = var.compartment_ocid
  display_name        = "app-key"
  management_endpoint = oci_kms_vault.main.management_endpoint
  key_shape {
    algorithm = "AES"
    length    = 32
  }
  protection_mode = "SOFTWARE"   # or "HSM" for HSM-protected
}
```

## KMS key translation

- `KeyUsage: ENCRYPT_DECRYPT` → `algorithm = "AES"`, `length = 32` (256-bit).
- `KeyUsage: SIGN_VERIFY` → `algorithm = "RSA"` or `"ECDSA"`, matching key length.
- `Origin: AWS_KMS` → `protection_mode = "SOFTWARE"`.
- `Origin: AWS_CLOUDHSM` → `protection_mode = "HSM"` (requires `vault_type = "VIRTUAL_PRIVATE"`).
- `MultiRegion: true` → **NOT directly supported.** Flag HIGH; OCI cross-region-replicated keys are a paid add-on configured out-of-band.
- `PendingWindowInDays` (key deletion) → `time_of_deletion` on OCI; default 30 days.

**Aliases** (`AWS::KMS::Alias`) do NOT get their own HCL resource. OCI identifies keys by OCID + `display_name`; fold the alias name into the key's `display_name`.

## Secret translation

### SecretsManager → Vault Secret

- `SecretString` → `secret_content.content` (base64-encode plaintext via `base64encode(...)` in the TF `base64` function).
- `SecretBinary` → `secret_content.content` (already base64).
- `KmsKeyId` → `key_id` (must reference an `oci_kms_key.*.id` in the same compartment).
- `RotationRules` → Flag HIGH: OCI rotation is either manual or driven by an `oci_functions_function` — there is no built-in Lambda rotator. Emit a TODO comment in the HCL.
- `ReplicaRegions` → Emit a `# TODO: regional replication is manual in OCI` comment; do not attempt to codify.

### SSM Parameter Store

- `SecureString` → `oci_vault_secret` (always).
- `String` / `StringList` — decide per value:
  - If value is sensitive (API keys, URLs with credentials) → `oci_vault_secret`.
  - If value is non-sensitive config → emit as Terraform `locals { ... }` or a `var` default.
- `Tier: Advanced` → OCI has no secret-tier concept; drop silently.

## Certificate translation

- **Managed public ACM certs** (DNS-validated auto-renewal):
  - OCI can't auto-renew certs from AWS-managed CAs. Flag HIGH.
  - Emit `oci_certificates_management_certificate` in `IMPORTED` config_type with `# TODO: import PEM` placeholder.
- **Private CA ACM certs** (PCA-issued):
  - Map to OCI Certificate Service's internal CA.
  - Emit `oci_certificates_management_ca_bundle` first if multiple certs share a CA.
- **Imported certs**:
  - Straightforward — `config_type = "IMPORTED"` + placeholder for PEM chain.

All certs referenced by load balancers (HTTPS listeners) must be provisioned before the LB. The synthesis stage will enforce ordering; for this skill, just emit the cert resources.

## WAF translation

### WAFv2 Web ACL

- `Scope: REGIONAL` (ALB/API Gateway) → OCI WAF attached to an LB.
- `Scope: CLOUDFRONT` → OCI WAA (Web Application Acceleration) instead of OCI WAF. Flag MEDIUM and route to cfn_terraform.
- `DefaultAction` → `oci_waf_web_app_firewall_policy.actions[0]` (`ALLOW` or `CHECK`).

### Rule translation

| AWS managed rule group | OCI WAF capability |
|---|---|
| `AWSManagedRulesCommonRuleSet` | OWASP Core Rule Set (enabled by default) |
| `AWSManagedRulesSQLiRuleSet` | SQL injection protection |
| `AWSManagedRulesKnownBadInputsRuleSet` | Malicious user-agent / bad bot rules |
| `AWSManagedRulesAmazonIpReputationList` | Threat intelligence feeds |
| Custom rules (IP block, rate-limit) | `oci_waf_web_app_firewall_policy.request_access_control.rules` |

- Rate-based rules → `action_name = "THROTTLE"` on the WAF policy.
- CAPTCHA rules → **no equivalent in OCI WAF.** Flag HIGH.
- Bot control → partial equivalent; flag MEDIUM.

### IP Sets

- `WAFv2::IPSet` (CIDR list) → `oci_waf_network_address_list` with the same list.
- Reference via `oci_waf_web_app_firewall_policy.request_access_control.rules[].condition.address_lists`.

## Cross-resource references

Write a `variables.tf` that exposes:
- `var.compartment_ocid` (always required).
- One `var.<name>_secret_value` per secret, marked `sensitive = true`.
- `var.kms_master_key_id` (optional — defaults to the vault's first key if omitted).

Never hardcode secret values in the HCL output. If the AWS source contains a plaintext `SecretString`, emit the secret **with a placeholder** + a note that the operator must populate it at apply time.

## IAM policy impact

This skill owns the resource HCL, but KMS/Secrets/SSM access requires IAM policies. Emit a `resource_mappings.iam_policies_needed` list that the iam_translation skill will pick up in synthesis:

```json
"iam_policies_needed": [
  "Allow dynamic-group app-servers to use keys in compartment app",
  "Allow dynamic-group app-servers to read secret-bundles in compartment app"
]
```

## Gaps to always flag

- **Multi-region KMS keys:** OCI cross-region key replication is paid/manual. CRITICAL if the AWS key is actively multi-region.
- **External key (BYOK / XKS):** OCI supports BYOK import but not all algorithms; flag HIGH with manual review.
- **Secrets Manager rotation Lambdas:** must be rewritten as OCI Functions. CRITICAL for rotation-enabled secrets.
- **CloudHSM clusters:** use `vault_type = "VIRTUAL_PRIVATE"`. Flag MEDIUM — capacity planning is required.
- **WAFv2 CAPTCHA:** no equivalent. CRITICAL for public-facing apps that rely on it.
- **Certificate auto-renewal** for public ACM certs: manual on OCI. HIGH.
