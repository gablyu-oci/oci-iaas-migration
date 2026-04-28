"""Golden-file tests for Phase 4 templates: input params -> expected HCL fragments.

Each test feeds valid params (conforming to the Pydantic schema) into
render_specs and asserts the rendered HCL contains the expected resource
blocks, field values, and aws_source_id traceability comments.
"""

import pytest
from app.services.template_renderer import render_specs
from app.templates.schemas import TEMPLATE_REGISTRY


# -----------------------------------------------------------------------
# Phase 4 template keys -- 19 total (7 compute + 4 identity + 3 vault
#                                     + 2 functions + 3 observability)
# -----------------------------------------------------------------------
PHASE4_TEMPLATES = [
    # Compute / Storage (7)
    "core/instance",
    "core/instance_configuration",
    "core/instance_pool",
    "core/autoscaling_configuration",
    "core/boot_volume",
    "core/block_volume",
    "core/block_volume_attachment",
    # Identity / IAM (4)
    "identity/dynamic_group",
    "identity/policy",
    "identity/group",
    "identity/user",
    # Vault / KMS (3)
    "vault/vault",
    "vault/key",
    "vault/secret",
    # Functions / Serverless (2)
    "functions/application",
    "functions/function",
    # Observability (3)
    "observability/log_group",
    "observability/log",
    "observability/metric_alarm",
]


class TestAllPhase4TemplatesRegistered:
    """Verify every Phase 4 template is present in the central registry."""

    def test_all_phase4_templates_registered(self):
        for tmpl in PHASE4_TEMPLATES:
            assert tmpl in TEMPLATE_REGISTRY, (
                f"Template '{tmpl}' missing from TEMPLATE_REGISTRY"
            )

    def test_phase4_template_count(self):
        """There are exactly 19 Phase 4 template entries."""
        assert len(PHASE4_TEMPLATES) == 19


# ===================================================================
# Compute / EC2 templates  (core/* -> network.tf)
# ===================================================================


class TestCoreComputeTemplates:
    """core/ templates for ec2_translation and storage_translation."""

    # ---- core/instance ------------------------------------------------

    def test_instance_basic(self):
        specs = [{"template": "core/instance", "label": "web", "params": {
            "compartment_id": "var.compartment_id",
            "availability_domain": "Uocm:PHX-AD-1",
            "display_name": "web-server",
            "shape": "VM.Standard.E5.Flex",
            "source_details": {
                "source_type": "image",
                "source_id": "ocid1.image.oc1..xxx",
            },
            "aws_source_id": "i-0abc123",
        }}]
        result = render_specs(specs)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert 'resource "oci_core_instance" "web"' in hcl
        assert "VM.Standard.E5.Flex" in hcl
        assert "web-server" in hcl
        assert "Uocm:PHX-AD-1" in hcl
        assert "i-0abc123" in hcl

    def test_instance_with_flex_shape_config(self):
        specs = [{"template": "core/instance", "label": "app", "params": {
            "compartment_id": "var.compartment_id",
            "availability_domain": "Uocm:US-ASHBURN-AD-1",
            "display_name": "app-server",
            "shape": "VM.Standard.E5.Flex",
            "shape_config": {"ocpus": 4.0, "memory_in_gbs": 32.0},
            "source_details": {
                "source_type": "image",
                "source_id": "ocid1.image.oc1..abc",
                "boot_volume_size_in_gbs": 100,
            },
            "create_vnic_details": {
                "subnet_id": "oci_core_subnet.private.id",
                "assign_public_ip": False,
                "nsg_ids": ["oci_core_network_security_group.app.id"],
                "display_name": "app-vnic",
            },
            "metadata": {"ssh_authorized_keys": "ssh-rsa AAAA..."},
            "aws_source_id": "i-0def456",
        }}]
        result = render_specs(specs)
        hcl = result["network.tf"]
        assert 'resource "oci_core_instance" "app"' in hcl
        assert "shape_config" in hcl
        assert "4.0" in hcl or "4" in hcl
        assert "32.0" in hcl or "32" in hcl
        assert "create_vnic_details" in hcl
        assert "assign_public_ip" in hcl
        assert "nsg_ids" in hcl
        assert "app-vnic" in hcl
        assert "ssh_authorized_keys" in hcl
        assert "i-0def456" in hcl

    # ---- core/instance_configuration ----------------------------------

    def test_instance_configuration(self):
        specs = [{"template": "core/instance_configuration", "label": "web_lt", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "web-launch-config",
            "instance_details": {
                "instance_type": "compute",
                "launch_details": {
                    "shape": "VM.Standard.E5.Flex",
                    "shape_config": {"ocpus": 2.0, "memory_in_gbs": 16.0},
                    "source_details": {
                        "source_type": "image",
                        "source_id": "ocid1.image.oc1..example",
                    },
                },
            },
            "aws_source_id": "lt-0abc123def456",
        }}]
        result = render_specs(specs)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert 'resource "oci_core_instance_configuration" "web_lt"' in hcl
        assert "web-launch-config" in hcl
        assert "instance_details" in hcl
        assert "launch_details" in hcl
        assert "VM.Standard.E5.Flex" in hcl
        assert "lt-0abc123def456" in hcl

    # ---- core/instance_pool -------------------------------------------

    def test_instance_pool(self):
        specs = [{"template": "core/instance_pool", "label": "web_pool", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "web-pool",
            "instance_configuration_id": "oci_core_instance_configuration.web_lt.id",
            "size": 3,
            "placement_configurations": [
                {
                    "availability_domain": "Uocm:US-ASHBURN-AD-1",
                    "primary_subnet_id": "oci_core_subnet.private.id",
                },
            ],
            "aws_source_id": "asg-0abc123def456",
        }}]
        result = render_specs(specs)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert 'resource "oci_core_instance_pool" "web_pool"' in hcl
        assert "web-pool" in hcl
        assert "size" in hcl
        assert "placement_configurations" in hcl
        assert "Uocm:US-ASHBURN-AD-1" in hcl
        assert "asg-0abc123def456" in hcl

    # ---- core/autoscaling_configuration -------------------------------

    def test_autoscaling_configuration(self):
        specs = [{"template": "core/autoscaling_configuration", "label": "web_as", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "web-autoscaling",
            "auto_scaling_resources": {
                "id": "oci_core_instance_pool.web_pool.id",
                "type": "instancePool",
            },
            "cool_down_in_seconds": 300,
            "is_enabled": True,
            "policies": [
                {
                    "display_name": "scale-out-policy",
                    "policy_type": "threshold",
                    "capacity": {"max": 4, "min": 1, "initial": 2},
                    "rules": [
                        {
                            "display_name": "scale-out-rule",
                            "action": {"type": "CHANGE_COUNT_BY", "value": 1},
                            "metric": {
                                "metric_type": "CPU_UTILIZATION",
                                "threshold": {"operator": "GT", "value": 80},
                            },
                        }
                    ],
                }
            ],
            "aws_source_id": "asg-policy-0abc123",
        }}]
        result = render_specs(specs)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert 'resource "oci_autoscaling_auto_scaling_configuration" "web_as"' in hcl
        assert "web-autoscaling" in hcl
        assert "auto_scaling_resources" in hcl
        assert "instancePool" in hcl
        assert "cool_down_in_seconds" in hcl
        assert "policies" in hcl
        assert "scale-out-policy" in hcl
        assert "capacity" in hcl
        assert "CPU_UTILIZATION" in hcl
        assert "asg-policy-0abc123" in hcl

    # ---- core/boot_volume ---------------------------------------------

    def test_boot_volume(self):
        specs = [{"template": "core/boot_volume", "label": "web_bv", "params": {
            "compartment_id": "var.compartment_id",
            "availability_domain": "Uocm:US-ASHBURN-AD-1",
            "display_name": "bv-web-server-1",
            "size_in_gbs": 100,
            "vpus_per_gb": 10,
            "aws_source_id": "vol-0abc123root",
        }}]
        result = render_specs(specs)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert 'resource "oci_core_boot_volume" "web_bv"' in hcl
        assert "bv-web-server-1" in hcl
        assert "size_in_gbs" in hcl
        assert "100" in hcl
        assert "vpus_per_gb" in hcl
        assert "vol-0abc123root" in hcl

    def test_boot_volume_with_source_details(self):
        specs = [{"template": "core/boot_volume", "label": "cloned_bv", "params": {
            "compartment_id": "var.compartment_id",
            "availability_domain": "Uocm:PHX-AD-1",
            "display_name": "cloned-boot-vol",
            "size_in_gbs": 200,
            "source_details": {
                "id": "ocid1.bootvolumebackup.oc1..xyz",
                "type": "bootVolumeBackup",
            },
            "aws_source_id": "vol-clone-abc",
        }}]
        result = render_specs(specs)
        hcl = result["network.tf"]
        assert "source_details" in hcl
        assert "bootVolumeBackup" in hcl
        assert "vol-clone-abc" in hcl

    # ---- core/block_volume --------------------------------------------

    def test_block_volume(self):
        specs = [{"template": "core/block_volume", "label": "data_vol", "params": {
            "compartment_id": "var.compartment_id",
            "availability_domain": "Uocm:US-ASHBURN-AD-1",
            "display_name": "data-vol-1",
            "size_in_gbs": 200,
            "vpus_per_gb": 20,
            "aws_source_id": "vol-0abc123data",
        }}]
        result = render_specs(specs)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert 'resource "oci_core_volume" "data_vol"' in hcl
        assert "data-vol-1" in hcl
        assert "200" in hcl
        assert "vpus_per_gb" in hcl
        assert "vol-0abc123data" in hcl

    # ---- core/block_volume_attachment ---------------------------------

    def test_block_volume_attachment(self):
        specs = [{"template": "core/block_volume_attachment", "label": "data_attach", "params": {
            "instance_id": "oci_core_instance.web.id",
            "volume_id": "oci_core_volume.data_vol.id",
            "attachment_type": "paravirtualized",
            "display_name": "data-attach",
            "is_read_only": False,
            "is_shareable": False,
            "device": "/dev/oracleoci/oraclevdb",
            "aws_source_id": "vol-attach-0abc123",
        }}]
        result = render_specs(specs)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert 'resource "oci_core_volume_attachment" "data_attach"' in hcl
        assert "paravirtualized" in hcl
        assert "data-attach" in hcl
        assert "/dev/oracleoci/oraclevdb" in hcl
        assert "vol-attach-0abc123" in hcl

    def test_block_volume_attachment_iscsi(self):
        specs = [{"template": "core/block_volume_attachment", "label": "iscsi_attach", "params": {
            "instance_id": "oci_core_instance.db.id",
            "volume_id": "oci_core_volume.iscsi_vol.id",
            "attachment_type": "iscsi",
            "aws_source_id": "vol-attach-iscsi-001",
        }}]
        result = render_specs(specs)
        hcl = result["network.tf"]
        assert 'resource "oci_core_volume_attachment" "iscsi_attach"' in hcl
        assert "iscsi" in hcl
        assert "vol-attach-iscsi-001" in hcl


# ===================================================================
# Identity / IAM templates  (identity/* -> iam.tf)
# ===================================================================


class TestIdentityTemplates:
    """identity/ templates for iam_translation."""

    def test_dynamic_group(self):
        specs = [{"template": "identity/dynamic_group", "label": "migration_dg", "params": {
            "compartment_id": "var.tenancy_ocid",
            "name": "migration-instance-dg",
            "description": "Dynamic group for migrated instances",
            "matching_rule": "ALL {instance.compartment.id = 'ocid1.compartment.oc1..example'}",
            "aws_source_id": "arn:aws:iam::123456789012:role/my-role",
        }}]
        result = render_specs(specs)
        assert "iam.tf" in result
        hcl = result["iam.tf"]
        assert 'resource "oci_identity_dynamic_group" "migration_dg"' in hcl
        assert "migration-instance-dg" in hcl
        assert "Dynamic group for migrated instances" in hcl
        assert "matching_rule" in hcl
        assert "arn:aws:iam::123456789012:role/my-role" in hcl

    def test_policy(self):
        specs = [{"template": "identity/policy", "label": "admin_pol", "params": {
            "compartment_id": "var.tenancy_ocid",
            "name": "migration-admin-policy",
            "description": "Policy granting admin access",
            "statements": [
                "Allow group admins to manage all-resources in compartment migration",
                "Allow dynamic-group migration-dg to use instances in compartment migration",
            ],
            "aws_source_id": "arn:aws:iam::123456789012:policy/my-policy",
        }}]
        result = render_specs(specs)
        assert "iam.tf" in result
        hcl = result["iam.tf"]
        assert 'resource "oci_identity_policy" "admin_pol"' in hcl
        assert "migration-admin-policy" in hcl
        assert "statements" in hcl
        assert "Allow group admins" in hcl
        assert "arn:aws:iam::123456789012:policy/my-policy" in hcl

    def test_group(self):
        specs = [{"template": "identity/group", "label": "admins", "params": {
            "compartment_id": "var.tenancy_ocid",
            "name": "migration-admins",
            "description": "Group for migration administrators",
            "aws_source_id": "arn:aws:iam::123456789012:group/admins",
        }}]
        result = render_specs(specs)
        assert "iam.tf" in result
        hcl = result["iam.tf"]
        assert 'resource "oci_identity_group" "admins"' in hcl
        assert "migration-admins" in hcl
        assert "Group for migration administrators" in hcl
        assert "arn:aws:iam::123456789012:group/admins" in hcl

    def test_user(self):
        specs = [{"template": "identity/user", "label": "svc_user", "params": {
            "compartment_id": "var.tenancy_ocid",
            "name": "migration-svc-user",
            "description": "Service user for migration workloads",
            "email": "svc-user@example.com",
            "aws_source_id": "arn:aws:iam::123456789012:user/svc-user",
        }}]
        result = render_specs(specs)
        assert "iam.tf" in result
        hcl = result["iam.tf"]
        assert 'resource "oci_identity_user" "svc_user"' in hcl
        assert "migration-svc-user" in hcl
        assert "svc-user@example.com" in hcl
        assert "arn:aws:iam::123456789012:user/svc-user" in hcl

    def test_user_without_email(self):
        specs = [{"template": "identity/user", "label": "basic_user", "params": {
            "compartment_id": "var.tenancy_ocid",
            "name": "basic-user",
            "description": "Basic user without email",
            "aws_source_id": "arn:aws:iam::123456789012:user/basic",
        }}]
        result = render_specs(specs)
        hcl = result["iam.tf"]
        assert 'resource "oci_identity_user" "basic_user"' in hcl
        assert "basic-user" in hcl
        # email field should NOT appear since it was not supplied
        lines = [l.strip() for l in hcl.splitlines()]
        email_lines = [l for l in lines if l.startswith("email")]
        assert len(email_lines) == 0


# ===================================================================
# Vault / KMS templates  (vault/* -> security.tf)
# ===================================================================


class TestVaultTemplates:
    """vault/ templates for security_translation."""

    def test_vault(self):
        specs = [{"template": "vault/vault", "label": "main", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "migration-vault",
            "vault_type": "DEFAULT",
            "aws_source_id": "arn:aws:kms:us-east-1:123456789012:key/abc-def",
        }}]
        result = render_specs(specs)
        assert "security.tf" in result
        hcl = result["security.tf"]
        assert 'resource "oci_kms_vault" "main"' in hcl
        assert "migration-vault" in hcl
        assert "DEFAULT" in hcl
        assert "arn:aws:kms:us-east-1:123456789012:key/abc-def" in hcl

    def test_vault_virtual_private(self):
        specs = [{"template": "vault/vault", "label": "private_vault", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "private-vault",
            "vault_type": "VIRTUAL_PRIVATE",
            "aws_source_id": "arn:aws:kms:us-east-1:123456789012:key/priv-001",
        }}]
        result = render_specs(specs)
        hcl = result["security.tf"]
        assert "VIRTUAL_PRIVATE" in hcl

    def test_key(self):
        specs = [{"template": "vault/key", "label": "enc_key", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "migration-key",
            "management_endpoint": "oci_kms_vault.main.management_endpoint",
            "protection_mode": "SOFTWARE",
            "key_shape": {"algorithm": "AES", "length": 32},
            "aws_source_id": "arn:aws:kms:us-east-1:123456789012:key/abc-def",
        }}]
        result = render_specs(specs)
        assert "security.tf" in result
        hcl = result["security.tf"]
        assert 'resource "oci_kms_key" "enc_key"' in hcl
        assert "migration-key" in hcl
        assert "management_endpoint" in hcl
        assert "SOFTWARE" in hcl
        assert "key_shape" in hcl
        assert "AES" in hcl
        assert "32" in hcl
        assert "arn:aws:kms:us-east-1:123456789012:key/abc-def" in hcl

    def test_key_hsm_protection(self):
        specs = [{"template": "vault/key", "label": "hsm_key", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "hsm-key",
            "management_endpoint": "oci_kms_vault.main.management_endpoint",
            "protection_mode": "HSM",
            "key_shape": {"algorithm": "RSA", "length": 256},
            "aws_source_id": "arn:aws:kms:us-east-1:123456789012:key/hsm-001",
        }}]
        result = render_specs(specs)
        hcl = result["security.tf"]
        assert "HSM" in hcl
        assert "RSA" in hcl

    def test_secret(self):
        specs = [{"template": "vault/secret", "label": "db_pw", "params": {
            "compartment_id": "var.compartment_id",
            "vault_id": "oci_kms_vault.main.id",
            "key_id": "oci_kms_key.enc_key.id",
            "secret_name": "db-password",
            "description": "Database password migrated from AWS Secrets Manager",
            "secret_content": {
                "content_type": "BASE64",
                "content": "cGxhY2Vob2xkZXI=",
            },
            "aws_source_id": "arn:aws:secretsmanager:us-east-1:123456789012:secret:db-password",
        }}]
        result = render_specs(specs)
        assert "security.tf" in result
        hcl = result["security.tf"]
        assert 'resource "oci_vault_secret" "db_pw"' in hcl
        assert "db-password" in hcl
        assert "secret_content" in hcl
        assert "BASE64" in hcl
        assert "cGxhY2Vob2xkZXI=" in hcl
        assert "arn:aws:secretsmanager:us-east-1:123456789012:secret:db-password" in hcl

    def test_secret_without_description(self):
        specs = [{"template": "vault/secret", "label": "api_key", "params": {
            "compartment_id": "var.compartment_id",
            "vault_id": "oci_kms_vault.main.id",
            "key_id": "oci_kms_key.enc_key.id",
            "secret_name": "api-key",
            "secret_content": {
                "content_type": "BASE64",
                "content": "c2VjcmV0",
            },
            "aws_source_id": "arn:aws:secretsmanager:us-east-1:123456789012:secret:api-key",
        }}]
        result = render_specs(specs)
        hcl = result["security.tf"]
        assert 'resource "oci_vault_secret" "api_key"' in hcl
        # description line should not appear since it was not supplied
        lines = [l.strip() for l in hcl.splitlines()]
        desc_lines = [l for l in lines if l.startswith("description")]
        assert len(desc_lines) == 0


# ===================================================================
# Functions / Serverless templates  (functions/* -> serverless.tf)
# ===================================================================


class TestFunctionsTemplates:
    """functions/ templates for serverless_translation."""

    def test_application(self):
        specs = [{"template": "functions/application", "label": "fn_app", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "migration-fn-app",
            "subnet_ids": ["oci_core_subnet.private.id"],
            "config": {"ENV": "production"},
            "aws_source_id": "arn:aws:lambda:us-east-1:123456789012:function:my-fn",
        }}]
        result = render_specs(specs)
        assert "serverless.tf" in result
        hcl = result["serverless.tf"]
        assert 'resource "oci_functions_application" "fn_app"' in hcl
        assert "migration-fn-app" in hcl
        assert "subnet_ids" in hcl
        assert "oci_core_subnet.private.id" in hcl
        assert "ENV" in hcl
        assert "production" in hcl
        assert "arn:aws:lambda:us-east-1:123456789012:function:my-fn" in hcl

    def test_application_multiple_subnets(self):
        specs = [{"template": "functions/application", "label": "multi_sub", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "multi-subnet-app",
            "subnet_ids": [
                "oci_core_subnet.a.id",
                "oci_core_subnet.b.id",
            ],
            "aws_source_id": "arn:aws:lambda:us-east-1:123456789012:function:multi",
        }}]
        result = render_specs(specs)
        hcl = result["serverless.tf"]
        assert "oci_core_subnet.a.id" in hcl
        assert "oci_core_subnet.b.id" in hcl

    def test_function(self):
        specs = [{"template": "functions/function", "label": "my_fn", "params": {
            "application_id": "oci_functions_application.fn_app.id",
            "display_name": "my-function",
            "image": "iad.ocir.io/namespace/repo:latest",
            "memory_in_mbs": 512,
            "timeout_in_seconds": 60,
            "config": {"DEBUG": "true"},
            "aws_source_id": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
        }}]
        result = render_specs(specs)
        assert "serverless.tf" in result
        hcl = result["serverless.tf"]
        assert 'resource "oci_functions_function" "my_fn"' in hcl
        assert "my-function" in hcl
        assert "iad.ocir.io/namespace/repo:latest" in hcl
        assert "512" in hcl
        assert "timeout_in_seconds" in hcl
        assert "60" in hcl
        assert "DEBUG" in hcl
        assert "arn:aws:lambda:us-east-1:123456789012:function:my-function" in hcl

    def test_function_defaults(self):
        """Function with only required fields uses schema defaults."""
        specs = [{"template": "functions/function", "label": "minimal_fn", "params": {
            "application_id": "oci_functions_application.fn_app.id",
            "display_name": "minimal",
            "image": "iad.ocir.io/ns/img:v1",
            "aws_source_id": "arn:aws:lambda:us-east-1:123456789012:function:min",
        }}]
        result = render_specs(specs)
        hcl = result["serverless.tf"]
        assert 'resource "oci_functions_function" "minimal_fn"' in hcl
        # default memory_in_mbs = 256
        assert "256" in hcl


# ===================================================================
# Observability templates  (observability/* -> observability.tf)
# ===================================================================


class TestObservabilityTemplates:
    """observability/ templates for observability_translation."""

    def test_log_group(self):
        specs = [{"template": "observability/log_group", "label": "app_logs", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "migration-log-group",
            "description": "Log group for migrated workloads",
            "aws_source_id": "arn:aws:logs:us-east-1:123456789012:log-group:/aws/my-app",
        }}]
        result = render_specs(specs)
        assert "observability.tf" in result
        hcl = result["observability.tf"]
        assert 'resource "oci_logging_log_group" "app_logs"' in hcl
        assert "migration-log-group" in hcl
        assert "Log group for migrated workloads" in hcl
        assert "arn:aws:logs:us-east-1:123456789012:log-group:/aws/my-app" in hcl

    def test_log_group_without_description(self):
        specs = [{"template": "observability/log_group", "label": "bare_lg", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "bare-log-group",
            "aws_source_id": "arn:aws:logs:us-east-1:123456789012:log-group:bare",
        }}]
        result = render_specs(specs)
        hcl = result["observability.tf"]
        assert 'resource "oci_logging_log_group" "bare_lg"' in hcl
        lines = [l.strip() for l in hcl.splitlines()]
        desc_lines = [l for l in lines if l.startswith("description")]
        assert len(desc_lines) == 0

    def test_log_custom(self):
        specs = [{"template": "observability/log", "label": "app_log", "params": {
            "log_group_id": "oci_logging_log_group.app_logs.id",
            "display_name": "migration-app-log",
            "log_type": "CUSTOM",
            "is_enabled": True,
            "retention_duration": 30,
            "aws_source_id": "arn:aws:logs:us-east-1:123456789012:log-group:/aws/my-app:stream",
        }}]
        result = render_specs(specs)
        assert "observability.tf" in result
        hcl = result["observability.tf"]
        assert 'resource "oci_logging_log" "app_log"' in hcl
        assert "migration-app-log" in hcl
        assert "CUSTOM" in hcl
        assert "retention_duration" in hcl

    def test_log_service_with_configuration(self):
        specs = [{"template": "observability/log", "label": "svc_log", "params": {
            "log_group_id": "oci_logging_log_group.app_logs.id",
            "display_name": "flowlog",
            "log_type": "SERVICE",
            "is_enabled": True,
            "configuration": {
                "source": {
                    "service": "flowlogs",
                    "resource": "oci_core_subnet.private.id",
                    "category": "all",
                },
                "compartment_id": "var.compartment_id",
            },
            "aws_source_id": "arn:aws:logs:us-east-1:123456789012:log-group:flow",
        }}]
        result = render_specs(specs)
        hcl = result["observability.tf"]
        assert 'resource "oci_logging_log" "svc_log"' in hcl
        assert "SERVICE" in hcl
        assert "configuration" in hcl
        assert "flowlogs" in hcl
        assert "oci_core_subnet.private.id" in hcl

    def test_metric_alarm(self):
        specs = [{"template": "observability/metric_alarm", "label": "high_cpu", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "high-cpu-alarm",
            "metric_compartment_id": "var.compartment_id",
            "namespace": "oci_computeagent",
            "query": "CpuUtilization[5m].mean() > 80",
            "severity": "WARNING",
            "destinations": ["oci_ons_notification_topic.ops.id"],
            "is_enabled": True,
            "body": "CPU utilization exceeded 80%",
            "pending_duration": "PT5M",
            "aws_source_id": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:high-cpu",
        }}]
        result = render_specs(specs)
        assert "observability.tf" in result
        hcl = result["observability.tf"]
        assert 'resource "oci_monitoring_alarm" "high_cpu"' in hcl
        assert "high-cpu-alarm" in hcl
        assert "oci_computeagent" in hcl
        assert "CpuUtilization[5m].mean() > 80" in hcl
        assert "WARNING" in hcl
        assert "oci_ons_notification_topic.ops.id" in hcl
        assert "CPU utilization exceeded 80%" in hcl
        assert "PT5M" in hcl
        assert "arn:aws:cloudwatch:us-east-1:123456789012:alarm:high-cpu" in hcl

    def test_metric_alarm_critical(self):
        specs = [{"template": "observability/metric_alarm", "label": "disk_full", "params": {
            "compartment_id": "var.compartment_id",
            "display_name": "disk-full-alarm",
            "metric_compartment_id": "var.compartment_id",
            "namespace": "oci_computeagent",
            "query": "DiskBytesUsed[5m].max() > 90",
            "severity": "CRITICAL",
            "destinations": ["oci_ons_notification_topic.critical.id"],
            "is_enabled": True,
            "repeat_notification_duration": "PT15M",
            "aws_source_id": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:disk-full",
        }}]
        result = render_specs(specs)
        hcl = result["observability.tf"]
        assert "CRITICAL" in hcl
        assert "repeat_notification_duration" in hcl
        assert "PT15M" in hcl


# ===================================================================
# Cross-domain: multiple Phase 4 templates rendered together
# ===================================================================


class TestMultiplePhase4TemplatesTogether:
    """Multiple Phase 4 templates from the same domain land in one file."""

    def test_compute_and_storage_in_network_tf(self):
        specs = [
            {"template": "core/instance", "label": "web", "params": {
                "compartment_id": "var.compartment_id",
                "availability_domain": "Uocm:PHX-AD-1",
                "display_name": "web-server",
                "shape": "VM.Standard.E5.Flex",
                "source_details": {"source_type": "image", "source_id": "ocid1.image.oc1..xxx"},
                "aws_source_id": "i-001",
            }},
            {"template": "core/block_volume", "label": "data", "params": {
                "compartment_id": "var.compartment_id",
                "availability_domain": "Uocm:PHX-AD-1",
                "display_name": "data-vol",
                "size_in_gbs": 100,
                "aws_source_id": "vol-001",
            }},
            {"template": "core/block_volume_attachment", "label": "data_att", "params": {
                "instance_id": "oci_core_instance.web.id",
                "volume_id": "oci_core_volume.data.id",
                "attachment_type": "paravirtualized",
                "aws_source_id": "vol-att-001",
            }},
        ]
        result = render_specs(specs)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert "oci_core_instance" in hcl
        assert "oci_core_volume" in hcl
        assert "oci_core_volume_attachment" in hcl
        # All three aws_source_ids present
        assert "i-001" in hcl
        assert "vol-001" in hcl
        assert "vol-att-001" in hcl

    def test_identity_resources_in_iam_tf(self):
        specs = [
            {"template": "identity/group", "label": "grp", "params": {
                "compartment_id": "var.tenancy_ocid",
                "name": "mig-admins",
                "description": "Admins",
                "aws_source_id": "arn:aws:iam::111:group/a",
            }},
            {"template": "identity/policy", "label": "pol", "params": {
                "compartment_id": "var.tenancy_ocid",
                "name": "mig-pol",
                "description": "Policy",
                "statements": ["Allow group mig-admins to manage all-resources in tenancy"],
                "aws_source_id": "arn:aws:iam::111:policy/a",
            }},
        ]
        result = render_specs(specs)
        assert "iam.tf" in result
        hcl = result["iam.tf"]
        assert "oci_identity_group" in hcl
        assert "oci_identity_policy" in hcl
