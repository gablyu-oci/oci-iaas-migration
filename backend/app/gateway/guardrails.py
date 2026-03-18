"""
Input and output guardrails for all LLM calls in the AWS-to-OCI migration tool.

Every LLM invocation should pass through these guardrails:

    check_input  -- before sending text to the model (scrubs secrets, detects
                    PII, blocks prompt injections, enforces token budget).
    check_output -- after receiving text from the model (validates OCI resource
                    types, flags compliance risks, detects AWS resource leaks).
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum input size (characters). ~50k tokens at ~4 chars/token.
_MAX_INPUT_CHARS = 200_000

# ---------------------------------------------------------------------------
# Secret-scrubbing patterns
# ---------------------------------------------------------------------------

# AWS access key IDs (always start with AKIA followed by 16 uppercase alphanumerics).
_RE_AWS_ACCESS_KEY = re.compile(r"AKIA[0-9A-Z]{16}")

# AWS secret access keys: 40-char base64 string appearing after "secret" keywords.
# Looks for key=value or key:value style with common separator chars.
_RE_AWS_SECRET_KEY = re.compile(
    r"(?i)(?:secret[_\s-]*(?:access)?[_\s-]*key)\s*[=:]\s*"
    r"([A-Za-z0-9/+=]{40})"
)

# AWS account IDs: exactly 12 digits, standalone (not embedded in longer numbers).
_RE_AWS_ACCOUNT_ID = re.compile(r"(?<!\d)\d{12}(?!\d)")

# OCI OCIDs: ocid1.<resource>.<realm>.<region>.<unique-id>
# Realm contains digits (e.g. "oc1"), region may contain digits and dashes.
_RE_OCID = re.compile(r"ocid1\.[a-z]+\.[a-z0-9]+\.[a-z0-9-]*\.[a-z0-9]+")

# Generic secret patterns: password, secret, token, api_key followed by = or :
_RE_GENERIC_SECRET = re.compile(
    r"(?i)(?:password|secret|token|api_key)\s*[=:]\s*\S+"
)

_SECRET_PATTERNS: list[re.Pattern] = [
    _RE_AWS_ACCESS_KEY,
    _RE_AWS_SECRET_KEY,
    _RE_AWS_ACCOUNT_ID,
    _RE_OCID,
    _RE_GENERIC_SECRET,
]

# ---------------------------------------------------------------------------
# PII patterns (warn only, do not block)
# ---------------------------------------------------------------------------

_RE_EMAIL = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

# US phone numbers: (xxx) xxx-xxxx, xxx-xxx-xxxx, xxx.xxx.xxxx, etc.
_RE_PHONE = re.compile(
    r"(?<!\d)"
    r"(?:\(?\d{3}\)?[\s.-]?)?"
    r"\d{3}[\s.-]?\d{4}"
    r"(?!\d)"
)

# Social Security Numbers: ###-##-####
_RE_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

_PII_PATTERNS: list[tuple[re.Pattern, str]] = [
    (_RE_EMAIL, "email address"),
    (_RE_PHONE, "phone number"),
    (_RE_SSN, "SSN"),
]

# ---------------------------------------------------------------------------
# Prompt injection patterns (block if detected)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore previous instructions", re.IGNORECASE),
    re.compile(r"system prompt:", re.IGNORECASE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"forget your instructions", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Known valid OCI Terraform resource types
# ---------------------------------------------------------------------------

VALID_OCI_TERRAFORM_RESOURCES: set[str] = {
    # Core networking
    "oci_core_vcn",
    "oci_core_subnet",
    "oci_core_internet_gateway",
    "oci_core_nat_gateway",
    "oci_core_route_table",
    "oci_core_route_table_attachment",
    "oci_core_network_security_group",
    "oci_core_network_security_group_security_rule",
    "oci_core_security_list",
    "oci_core_dhcp_options",
    "oci_core_drg",
    "oci_core_drg_attachment",
    # Compute
    "oci_core_instance",
    "oci_core_volume",
    "oci_core_volume_attachment",
    "oci_core_instance_configuration",
    "oci_core_instance_pool",
    # Load balancers
    "oci_load_balancer_load_balancer",
    "oci_load_balancer_backend_set",
    "oci_load_balancer_listener",
    "oci_load_balancer_backend",
    # Network load balancers
    "oci_network_load_balancer_network_load_balancer",
    "oci_network_load_balancer_backend_set",
    "oci_network_load_balancer_listener",
    "oci_network_load_balancer_backend",
    # Database
    "oci_database_db_system",
    "oci_database_autonomous_database",
    "oci_mysql_mysql_db_system",
    # Identity / IAM
    "oci_identity_policy",
    "oci_identity_compartment",
    "oci_identity_dynamic_group",
    "oci_identity_group",
    "oci_identity_user",
    # Object storage
    "oci_objectstorage_bucket",
    "oci_objectstorage_namespace_metadata",
    # Functions
    "oci_functions_application",
    "oci_functions_function",
    # Autoscaling
    "oci_autoscaling_auto_scaling_configuration",
    "oci_autoscaling_auto_scaling_policy",
    # Container engine (OKE)
    "oci_containerengine_cluster",
    "oci_containerengine_node_pool",
    # DNS
    "oci_dns_zone",
    "oci_dns_record",
    # Monitoring / Logging
    "oci_monitoring_alarm",
    "oci_logging_log",
    "oci_logging_log_group",
    # Security / KMS
    "oci_vault_secret",
    "oci_kms_vault",
    "oci_kms_key",
}

# Ports considered sensitive when exposed to 0.0.0.0/0.
_SENSITIVE_PORTS: set[int] = {22, 3389, 3306, 5432, 1521}

# Regex to detect "0.0.0.0/0" near a sensitive port number in the same line.
_RE_PUBLIC_ACCESS = re.compile(
    r"0\.0\.0\.0/0"
)

# AWS CloudFormation resource type pattern (e.g. AWS::EC2::Instance).
_RE_AWS_CFN_TYPE = re.compile(r"AWS::[A-Za-z0-9]+::[A-Za-z0-9]+")

# AWS Terraform resource type pattern (e.g. aws_instance).
_RE_AWS_TF_TYPE = re.compile(r"\baws_[a-z][a-z0-9_]*\b")

# Pattern to find all oci_ prefixed resource references in text.
_RE_OCI_TYPE = re.compile(r"\boci_[a-z][a-z0-9_]*\b")

# Resources that should normally have a kms_key_id for encryption.
_ENCRYPT_REQUIRED_TYPES = {"oci_core_volume", "oci_objectstorage_bucket"}


# ===================================================================
# Public API
# ===================================================================


def check_input(text: str) -> dict:
    """Validate and sanitise text *before* it is sent to the LLM.

    Performs four checks in order:
        1. Token budget enforcement (block if too long).
        2. Prompt injection detection (block if found).
        3. Secret scrubbing (replace with ``[REDACTED]``).
        4. PII detection (warn, do not block).

    Returns::

        {
            "scrubbed_text": str,
            "blocked": bool,
            "block_reason": str | None,
            "warnings": list[str],
        }
    """
    warnings: list[str] = []
    blocked: bool = False
    block_reason: Optional[str] = None
    scrubbed: str = text

    # 1. Token budget enforcement -------------------------------------------
    if len(text) > _MAX_INPUT_CHARS:
        blocked = True
        block_reason = (
            f"Input length ({len(text)} chars) exceeds the maximum "
            f"allowed budget of {_MAX_INPUT_CHARS} characters (~50k tokens)"
        )
        return {
            "scrubbed_text": scrubbed,
            "blocked": blocked,
            "block_reason": block_reason,
            "warnings": warnings,
        }

    # 2. Prompt injection detection -----------------------------------------
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            blocked = True
            block_reason = (
                f"Prompt injection detected: matched pattern "
                f"'{match.group()}'"
            )
            # Still scrub secrets before returning so the blocked payload
            # does not inadvertently leak credentials in logs.
            break

    # 3. Secret scrubbing ---------------------------------------------------
    for pat in _SECRET_PATTERNS:
        scrubbed = pat.sub("[REDACTED]", scrubbed)

    # 4. PII detection (warn, not block) ------------------------------------
    for pat, label in _PII_PATTERNS:
        matches = pat.findall(scrubbed)
        if matches:
            warnings.append(
                f"PII detected ({label}): {len(matches)} occurrence(s) found"
            )
            # We do NOT scrub PII out of the text automatically -- we only
            # warn so the caller can decide how to proceed.

    return {
        "scrubbed_text": scrubbed,
        "blocked": blocked,
        "block_reason": block_reason,
        "warnings": warnings,
    }


def check_output(text: str, skill_type: str = "unknown") -> dict:
    """Validate LLM-generated output *after* generation.

    Performs three checks:
        1. OCI resource type validation -- flags potentially hallucinated
           ``oci_*`` types that are not in the known-valid set.
        2. Compliance flags -- detects dangerous IAM policies, public access
           on sensitive ports, and unencrypted storage resources.
        3. AWS resource type leak detection -- flags any ``AWS::`` or
           ``aws_`` resource types that should not appear in OCI output.

    Args:
        text: The raw LLM output text to validate.
        skill_type: The skill that produced this output (e.g.
            ``"cfn_terraform"``, ``"iam_translation"``).  Used to tune
            which checks are relevant, but all checks run regardless.

    Returns::

        {
            "valid": bool,
            "issues": list[str],
            "warnings": list[str],
            "compliance_flags": list[str],
        }
    """
    issues: list[str] = []
    warnings: list[str] = []
    compliance_flags: list[str] = []

    # 1. OCI resource type validation ---------------------------------------
    found_oci_types = set(_RE_OCI_TYPE.findall(text))
    unknown_types = found_oci_types - VALID_OCI_TERRAFORM_RESOURCES
    if unknown_types:
        sorted_unknown = sorted(unknown_types)
        issues.append(
            f"Potentially hallucinated OCI resource types: "
            f"{', '.join(sorted_unknown)}"
        )

    # 2. Compliance flags ---------------------------------------------------

    # 2a. Overly broad IAM policy
    if re.search(r"manage\s+all-resources\s+in\s+tenancy", text, re.IGNORECASE):
        compliance_flags.append("OVERLY_BROAD_IAM")
        warnings.append(
            "Overly broad IAM statement detected: "
            "'manage all-resources in tenancy'"
        )

    # 2b. Public access on sensitive ports
    #     We scan for 0.0.0.0/0 and check whether a sensitive port appears
    #     within a ±5-line context window around each match.  This handles
    #     Terraform HCL where the CIDR and port appear on separate lines
    #     within the same security rule block.
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if _RE_PUBLIC_ACCESS.search(line):
            # Build context: 5 lines before + the match line + 5 lines after
            ctx_start = max(0, idx - 5)
            ctx_end = min(len(lines), idx + 6)
            context_block = "\n".join(lines[ctx_start:ctx_end])
            for port in _SENSITIVE_PORTS:
                if re.search(rf"(?<!\d){port}(?!\d)", context_block):
                    compliance_flags.append("PUBLIC_ACCESS_RISK")
                    warnings.append(
                        f"Public access (0.0.0.0/0) detected on "
                        f"sensitive port {port}"
                    )
                    break  # one flag per occurrence of 0.0.0.0/0 is enough

    # Deduplicate compliance flags while preserving order.
    seen_flags: set[str] = set()
    deduped_flags: list[str] = []
    for flag in compliance_flags:
        if flag not in seen_flags:
            seen_flags.add(flag)
            deduped_flags.append(flag)
    compliance_flags = deduped_flags

    # 2c. Unencrypted storage detection
    #     For each resource block that creates oci_core_volume or
    #     oci_objectstorage_bucket, check whether kms_key_id appears
    #     somewhere nearby in the same block.  As a heuristic we split
    #     on "resource" boundaries and look within each chunk.
    for res_type in _ENCRYPT_REQUIRED_TYPES:
        # Find all occurrences of the resource type
        for match in re.finditer(
            rf'resource\s+"({re.escape(res_type)})"\s+"[^"]*"\s*\{{',
            text,
        ):
            # Grab the block from the resource declaration to the next
            # top-level closing brace.  This is a rough heuristic that
            # works for well-formatted Terraform.
            block_start = match.start()
            brace_depth = 0
            block_end = len(text)
            for i in range(match.end() - 1, len(text)):
                if text[i] == "{":
                    brace_depth += 1
                elif text[i] == "}":
                    brace_depth -= 1
                    if brace_depth == 0:
                        block_end = i + 1
                        break
            block = text[block_start:block_end]
            if "kms_key_id" not in block:
                if "UNENCRYPTED_STORAGE" not in compliance_flags:
                    compliance_flags.append("UNENCRYPTED_STORAGE")
                warnings.append(
                    f"Resource '{res_type}' is missing kms_key_id "
                    f"(unencrypted storage)"
                )

    # 3. AWS resource type leak detection -----------------------------------
    aws_cfn_matches = _RE_AWS_CFN_TYPE.findall(text)
    if aws_cfn_matches:
        unique = sorted(set(aws_cfn_matches))[:10]
        issues.append(
            f"AWS CloudFormation resource types found in output "
            f"(should be OCI): {', '.join(unique)}"
        )

    aws_tf_matches = _RE_AWS_TF_TYPE.findall(text)
    if aws_tf_matches:
        unique = sorted(set(aws_tf_matches))[:10]
        issues.append(
            f"AWS Terraform resource types found in output "
            f"(should be OCI): {', '.join(unique)}"
        )

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "compliance_flags": compliance_flags,
    }
