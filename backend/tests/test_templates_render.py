"""Golden-file tests: each template renders valid HCL with known params.

Covers all 23 registered templates -- validates schema acceptance, Jinja2
rendering, and output-file routing.  Also verifies that schemas correctly
reject invalid input.

BUG NOTE: The NsgSecurityRuleParams schema defines tcp_options as
TcpUdpOptions(min, max) but the Jinja2 template at
core/network_security_group_security_rule.tf.j2 expects
tcp_options.destination_port_range.min/max.  This mismatch means a
schema-valid NsgSecurityRuleParams with tcp_options will always fail
rendering.  The test for that template currently omits tcp_options to
avoid the crash; a separate test documents the schema/template mismatch.
"""

import pytest

from app.templates.schemas import TEMPLATE_REGISTRY
from app.services.template_renderer import render_specs, TemplateRenderError


# -- Valid params fixtures for every template --------------------------------

VALID_PARAMS = {
    "core/vcn": {
        "compartment_id": "var.compartment_id",
        "cidr_blocks": ["10.0.0.0/16"],
        "display_name": "test-vcn",
        "dns_label": "testvcn",
        "aws_source_id": "vpc-12345",
        "freeform_tags": {"aws_source_id": "vpc-12345", "managed_by": "oci-iaas-migration"},
    },
    "core/subnet": {
        "compartment_id": "var.compartment_id",
        "vcn_id": "oci_core_vcn.main.id",
        "cidr_block": "10.0.1.0/24",
        "display_name": "test-subnet",
        "dns_label": "testsub",
        "prohibit_public_ip_on_vnic": False,
        "aws_source_id": "subnet-abc123",
        "freeform_tags": {"aws_source_id": "subnet-abc123", "managed_by": "oci-iaas-migration"},
    },
    "core/internet_gateway": {
        "compartment_id": "var.compartment_id",
        "vcn_id": "oci_core_vcn.main.id",
        "display_name": "test-igw",
        "enabled": True,
        "aws_source_id": "igw-12345",
    },
    "core/nat_gateway": {
        "compartment_id": "var.compartment_id",
        "vcn_id": "oci_core_vcn.main.id",
        "display_name": "test-nat",
        "block_traffic": False,
        "aws_source_id": "nat-12345",
    },
    "core/route_table": {
        "compartment_id": "var.compartment_id",
        "vcn_id": "oci_core_vcn.main.id",
        "display_name": "test-rt",
        "route_rules": [
            {
                "destination": "0.0.0.0/0",
                "destination_type": "CIDR_BLOCK",
                "network_entity_id": "oci_core_internet_gateway.main.id",
                "description": "Route to internet",
            }
        ],
        "aws_source_id": "rtb-12345",
    },
    "core/route_table_attachment": {
        "subnet_id": "oci_core_subnet.main.id",
        "route_table_id": "oci_core_route_table.main.id",
    },
    "core/security_list": {
        "compartment_id": "var.compartment_id",
        "vcn_id": "oci_core_vcn.main.id",
        "display_name": "test-sl",
        "ingress_security_rules": [
            {
                "source": "0.0.0.0/0",
                "protocol": "6",
                "stateless": False,
                "tcp_options": {"min": 443, "max": 443},
            }
        ],
        "egress_security_rules": [
            {"destination": "0.0.0.0/0", "protocol": "all", "stateless": False}
        ],
        "aws_source_id": "sg-12345",
    },
    "core/security_list_attachment": {
        "subnet_id": "oci_core_subnet.main.id",
        "security_list_id": "oci_core_security_list.main.id",
    },
    "core/network_security_group": {
        "compartment_id": "var.compartment_id",
        "vcn_id": "oci_core_vcn.main.id",
        "display_name": "test-nsg",
        "aws_source_id": "sg-12345",
    },
    # NOTE: tcp_options omitted here because the schema (TcpUdpOptions with
    # flat min/max) does not match the template (expects
    # tcp_options.destination_port_range.min/max).  See the mismatch test
    # in TestSchemaTemplateMismatch below.
    "core/network_security_group_security_rule": {
        "network_security_group_id": "oci_core_network_security_group.main.id",
        "direction": "INGRESS",
        "protocol": "6",
        "source": '"0.0.0.0/0"',
        "source_type": "CIDR_BLOCK",
        "stateless": False,
        "description": "Allow HTTPS",
        "aws_source_id": "sgr-12345",
    },
    "core/public_ip": {
        "compartment_id": "var.compartment_id",
        "lifetime": "RESERVED",
        "display_name": "test-eip",
        "aws_source_id": "eipalloc-12345",
    },
    "load_balancer/load_balancer": {
        "compartment_id": "var.compartment_id",
        "display_name": "test-lb",
        "shape": "flexible",
        "is_private": False,
        "shape_details": {"minimum_bandwidth_in_mbps": 10, "maximum_bandwidth_in_mbps": 100},
        "subnet_ids": ["oci_core_subnet.public.id"],
        "aws_source_id": "arn:aws:elasticloadbalancing:us-east-1:123:loadbalancer/app/test",
    },
    "load_balancer/backend_set": {
        "load_balancer_id": "oci_load_balancer_load_balancer.main.id",
        "name": "app-backend-set",
        "policy": "ROUND_ROBIN",
        "health_checker": {
            "protocol": "HTTP",
            "port": 8080,
            "url_path": "/health",
            "interval_ms": 30000,
            "timeout_in_millis": 3000,
            "retries": 3,
            "return_code": 200,
        },
        "aws_source_id": "arn:aws:elasticloadbalancing:us-east-1:123:targetgroup/tg",
    },
    "load_balancer/listener": {
        "load_balancer_id": "oci_load_balancer_load_balancer.main.id",
        "name": "http-listener",
        "default_backend_set_name": "oci_load_balancer_backend_set.main.name",
        "port": 80,
        "protocol": "HTTP",
        "aws_source_id": "arn:aws:elasticloadbalancing:us-east-1:123:listener/test",
    },
    "load_balancer/certificate": {
        "load_balancer_id": "oci_load_balancer_load_balancer.main.id",
        "certificate_name": "test-cert",
        "aws_source_id": "arn:aws:acm:us-east-1:123:certificate/test",
    },
    "load_balancer/hostname": {
        "load_balancer_id": "oci_load_balancer_load_balancer.main.id",
        "hostname": "app.example.com",
        "name": "app-hostname",
        "aws_source_id": "listener-rule-host",
    },
    "load_balancer/path_route_set": {
        "load_balancer_id": "oci_load_balancer_load_balancer.main.id",
        "name": "api-routes",
        "path_routes": [
            {
                "path_string": "/api/*",
                "backend_set_name": "oci_load_balancer_backend_set.api.name",
                "match_type": "PREFIX_MATCH",
            }
        ],
        "aws_source_id": "listener-rule-path",
    },
    "load_balancer/rule_set": {
        "load_balancer_id": "oci_load_balancer_load_balancer.main.id",
        "name": "header-rules",
        "items": [
            {"action": "ADD_HTTP_REQUEST_HEADER", "header": "X-Forwarded-Proto", "value": "https"}
        ],
        "aws_source_id": "listener-rule-action",
    },
    "cloud_migrations/migration": {
        "compartment_id": "var.compartment_id",
        "display_name": "aws-to-oci-test",
        "freeform_tags": {"source": "aws", "strategy": "ocm-hybrid"},
    },
    "cloud_migrations/migration_plan": {
        "compartment_id": "var.compartment_id",
        "migration_id": "oci_cloud_migrations_migration.main.id",
        "display_name": "plan-test",
    },
    "cloud_migrations/target_asset": {
        "migration_plan_id": "oci_cloud_migrations_migration_plan.plan.id",
        "preferred_shape_type": "VM",
        "shape": "VM.Standard.E5.Flex",
        "ocpus": 4,
        "memory_in_gbs": 64,
        "block_volumes_performance": 10,
        "aws_source_id": "i-0abc1234567890abc",
    },
    "cloud_migrations/replication_schedule": {
        "compartment_id": "var.compartment_id",
        "display_name": "weekly-sync",
        "execution_recurrences": "FREQ=WEEKLY;BYDAY=SU;BYHOUR=2",
    },
    "free_form_hcl": {
        "hcl": (
            'resource "null_resource" "placeholder" {\n'
            "  triggers = {\n"
            "    always_run = timestamp()\n"
            "  }\n"
            "}"
        ),
    },
    # ── Phase 4 templates: compute, storage, identity, vault, functions, observability ──
    "core/instance": {
        "compartment_id": "var.compartment_id",
        "availability_domain": "Uocm:US-ASHBURN-AD-1",
        "display_name": "web-server-1",
        "shape": "VM.Standard.E5.Flex",
        "shape_config": {"ocpus": 2.0, "memory_in_gbs": 16.0},
        "source_details": {
            "source_type": "image",
            "source_id": "ocid1.image.oc1..example",
            "boot_volume_size_in_gbs": 50,
        },
        "create_vnic_details": {
            "subnet_id": "oci_core_subnet.private.id",
            "assign_public_ip": False,
        },
        "metadata": {"ssh_authorized_keys": "ssh-rsa AAAA..."},
        "aws_source_id": "i-0abc123def456",
    },
    "core/instance_configuration": {
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
    },
    "core/instance_pool": {
        "compartment_id": "var.compartment_id",
        "display_name": "web-pool",
        "instance_configuration_id": "oci_core_instance_configuration.web.id",
        "size": 2,
        "placement_configurations": [
            {
                "availability_domain": "Uocm:US-ASHBURN-AD-1",
                "primary_subnet_id": "oci_core_subnet.private.id",
            }
        ],
        "aws_source_id": "asg-0abc123def456",
    },
    "core/autoscaling_configuration": {
        "compartment_id": "var.compartment_id",
        "display_name": "web-autoscaling",
        "auto_scaling_resources": {
            "id": "oci_core_instance_pool.web.id",
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
    },
    "core/boot_volume": {
        "compartment_id": "var.compartment_id",
        "availability_domain": "Uocm:US-ASHBURN-AD-1",
        "display_name": "bv-web-server-1",
        "size_in_gbs": 100,
        "vpus_per_gb": 10,
        "aws_source_id": "vol-0abc123def456",
    },
    "core/block_volume": {
        "compartment_id": "var.compartment_id",
        "availability_domain": "Uocm:US-ASHBURN-AD-1",
        "display_name": "data-vol-1",
        "size_in_gbs": 200,
        "vpus_per_gb": 20,
        "aws_source_id": "vol-0abc123def456",
    },
    "core/block_volume_attachment": {
        "instance_id": "oci_core_instance.web.id",
        "volume_id": "oci_core_volume.data.id",
        "attachment_type": "paravirtualized",
        "display_name": "data-attach",
        "is_read_only": False,
        "is_shareable": False,
        "device": "/dev/oracleoci/oraclevdb",
        "aws_source_id": "vol-attach-0abc123",
    },
    "identity/dynamic_group": {
        "compartment_id": "var.tenancy_ocid",
        "name": "migration-instance-dg",
        "description": "Dynamic group for migrated instances",
        "matching_rule": "ALL {instance.compartment.id = 'ocid1.compartment.oc1..example'}",
        "aws_source_id": "arn:aws:iam::123456789012:role/my-role",
    },
    "identity/group": {
        "compartment_id": "var.tenancy_ocid",
        "name": "migration-admins",
        "description": "Group for migration administrators",
        "aws_source_id": "arn:aws:iam::123456789012:group/admins",
    },
    "identity/policy": {
        "compartment_id": "var.tenancy_ocid",
        "name": "migration-admin-policy",
        "description": "Policy granting admin access to migrated resources",
        "statements": [
            "Allow group admins to manage all-resources in compartment migration"
        ],
        "aws_source_id": "arn:aws:iam::123456789012:policy/my-policy",
    },
    "identity/user": {
        "compartment_id": "var.tenancy_ocid",
        "name": "migration-svc-user",
        "description": "Service user for migration workloads",
        "email": "svc-user@example.com",
        "aws_source_id": "arn:aws:iam::123456789012:user/svc-user",
    },
    "vault/vault": {
        "compartment_id": "var.compartment_id",
        "display_name": "migration-vault",
        "vault_type": "DEFAULT",
        "aws_source_id": "arn:aws:kms:us-east-1:123456789012:key/abc-def",
    },
    "vault/key": {
        "compartment_id": "var.compartment_id",
        "display_name": "migration-key",
        "key_shape": {"algorithm": "AES", "length": 32},
        "management_endpoint": "oci_kms_vault.main.management_endpoint",
        "protection_mode": "SOFTWARE",
        "aws_source_id": "arn:aws:kms:us-east-1:123456789012:key/abc-def",
    },
    "vault/secret": {
        "compartment_id": "var.compartment_id",
        "vault_id": "oci_kms_vault.main.id",
        "key_id": "oci_kms_key.main.id",
        "secret_name": "db-password",
        "description": "Database password migrated from AWS Secrets Manager",
        "secret_content": {"content": "cGxhY2Vob2xkZXI=", "content_type": "BASE64"},
        "aws_source_id": "arn:aws:secretsmanager:us-east-1:123456789012:secret:db-password",
    },
    "functions/application": {
        "compartment_id": "var.compartment_id",
        "display_name": "migration-fn-app",
        "subnet_ids": ["oci_core_subnet.private.id"],
        "config": {"ENV": "production"},
        "aws_source_id": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
    },
    "functions/function": {
        "application_id": "oci_functions_application.main.id",
        "display_name": "my-function",
        "image": "iad.ocir.io/namespace/repo:latest",
        "memory_in_mbs": 256,
        "timeout_in_seconds": 30,
        "aws_source_id": "arn:aws:lambda:us-east-1:123456789012:function:my-function",
    },
    "observability/log_group": {
        "compartment_id": "var.compartment_id",
        "display_name": "migration-log-group",
        "description": "Log group for migrated workloads",
        "aws_source_id": "arn:aws:logs:us-east-1:123456789012:log-group:/aws/my-app",
    },
    "observability/log": {
        "log_group_id": "oci_logging_log_group.main.id",
        "display_name": "migration-app-log",
        "log_type": "CUSTOM",
        "is_enabled": True,
        "retention_duration": 30,
        "aws_source_id": "arn:aws:logs:us-east-1:123456789012:log-group:/aws/my-app:log-stream:stream1",
    },
    "observability/metric_alarm": {
        "compartment_id": "var.compartment_id",
        "display_name": "high-cpu-alarm",
        "metric_compartment_id": "var.compartment_id",
        "namespace": "oci_computeagent",
        "query": "CpuUtilization[5m].mean() > 80",
        "severity": "WARNING",
        "body": "CPU utilization exceeded 80%",
        "destinations": ["oci_ons_notification_topic.ops.id"],
        "is_enabled": True,
        "pending_duration": "PT5M",
        "aws_source_id": "arn:aws:cloudwatch:us-east-1:123456789012:alarm:high-cpu",
    },
}


class TestTemplateRegistry:
    """Verify all templates are registered and have valid schemas."""

    def test_registry_has_all_templates(self):
        # Phase 1 added 23, Phase 4 added 19 more. Use >= so adding more
        # templates later doesn't break this count check.
        assert len(TEMPLATE_REGISTRY) >= 42, (
            f"Expected at least 42 templates, got {len(TEMPLATE_REGISTRY)}. "
            f"Keys: {sorted(TEMPLATE_REGISTRY.keys())}"
        )

    def test_valid_params_covers_all_templates(self):
        """Every registered template has a VALID_PARAMS entry."""
        missing = set(TEMPLATE_REGISTRY.keys()) - set(VALID_PARAMS.keys())
        assert not missing, f"VALID_PARAMS missing entries for: {missing}"

    @pytest.mark.parametrize("template_name", sorted(TEMPLATE_REGISTRY.keys()))
    def test_schema_produces_json_schema(self, template_name):
        schema_cls = TEMPLATE_REGISTRY[template_name]
        json_schema = schema_cls.model_json_schema()
        assert "properties" in json_schema or "type" in json_schema

    @pytest.mark.parametrize("template_name", sorted(TEMPLATE_REGISTRY.keys()))
    def test_schema_validates_valid_params(self, template_name):
        """Each schema accepts its VALID_PARAMS without error."""
        schema_cls = TEMPLATE_REGISTRY[template_name]
        params = VALID_PARAMS[template_name]
        validated = schema_cls.model_validate(params)
        assert validated is not None


class TestTemplateRendering:
    """Golden-file tests: each template renders with valid params."""

    @pytest.mark.parametrize(
        "template_name,params",
        sorted(VALID_PARAMS.items()),
    )
    def test_valid_render(self, template_name, params):
        """Each template renders without error with valid params."""
        label = "test_resource"
        specs = [{"template": template_name, "label": label, "params": params}]
        result = render_specs(specs)
        assert len(result) >= 1
        for filename, content in result.items():
            assert len(content) > 10, f"{filename} rendered too short"

    @pytest.mark.parametrize(
        "template_name",
        [
            "core/vcn",
            "core/subnet",
            "core/internet_gateway",
            "core/nat_gateway",
            "core/network_security_group",
            "load_balancer/load_balancer",
            "load_balancer/backend_set",
            "cloud_migrations/migration",
            "cloud_migrations/target_asset",
        ],
    )
    def test_rendered_has_resource_block(self, template_name):
        """Rendered HCL contains the expected resource block."""
        params = VALID_PARAMS[template_name]
        specs = [{"template": template_name, "label": "golden", "params": params}]
        result = render_specs(specs)
        content = next(iter(result.values()))
        assert 'resource "' in content

    def test_vcn_golden_output(self):
        """VCN renders with correct structure."""
        specs = [
            {"template": "core/vcn", "label": "main", "params": VALID_PARAMS["core/vcn"]}
        ]
        result = render_specs(specs)
        hcl = result["network.tf"]
        assert 'resource "oci_core_vcn" "main"' in hcl
        assert "cidr_blocks" in hcl
        assert "10.0.0.0/16" in hcl
        assert "aws_source_id" in hcl
        assert "managed_by" in hcl

    def test_target_asset_golden_output(self):
        """OCM target_asset renders with user_spec and preferred_shape_type."""
        specs = [
            {
                "template": "cloud_migrations/target_asset",
                "label": "asset_i_0abc",
                "params": VALID_PARAMS["cloud_migrations/target_asset"],
            }
        ]
        result = render_specs(specs)
        hcl = result["ocm/main.tf"]
        assert 'resource "oci_cloud_migrations_target_asset" "asset_i_0abc"' in hcl
        assert "preferred_shape_type" in hcl
        assert '"VM"' in hcl
        assert "user_spec" in hcl
        assert "shape_config" in hcl
        assert "ocpus" in hcl
        assert "memory_in_gbs" in hcl
        assert "block_volumes_performance" in hcl

    def test_load_balancer_golden_output(self):
        """Load balancer renders with shape_details."""
        specs = [
            {
                "template": "load_balancer/load_balancer",
                "label": "web_lb",
                "params": VALID_PARAMS["load_balancer/load_balancer"],
            }
        ]
        result = render_specs(specs)
        hcl = result["loadbalancer.tf"]
        assert 'resource "oci_load_balancer_load_balancer" "web_lb"' in hcl
        assert "shape_details" in hcl
        assert "minimum_bandwidth_in_mbps" in hcl

    def test_nsg_rule_golden_output_no_tcp(self):
        """NSG rule renders direction, protocol, source without tcp_options."""
        specs = [
            {
                "template": "core/network_security_group_security_rule",
                "label": "https_ingress",
                "params": VALID_PARAMS["core/network_security_group_security_rule"],
            }
        ]
        result = render_specs(specs)
        hcl = result["network.tf"]
        assert "direction" in hcl
        assert '"INGRESS"' in hcl
        assert '"6"' in hcl

    def test_free_form_hcl_passthrough(self):
        """Free-form HCL passes through as-is."""
        specs = [
            {"template": "free_form_hcl", "label": "custom", "params": VALID_PARAMS["free_form_hcl"]}
        ]
        result = render_specs(specs)
        content = next(iter(result.values()))
        assert "null_resource" in content

    def test_free_form_hcl_routes_to_main_tf(self):
        """free_form_hcl content lands in main.tf."""
        specs = [
            {"template": "free_form_hcl", "label": "custom", "params": VALID_PARAMS["free_form_hcl"]}
        ]
        result = render_specs(specs)
        assert "main.tf" in result

    def test_subnet_includes_cidr_block(self):
        """Subnet renders the CIDR block value."""
        specs = [
            {"template": "core/subnet", "label": "web", "params": VALID_PARAMS["core/subnet"]}
        ]
        result = render_specs(specs)
        hcl = result["network.tf"]
        assert "10.0.1.0/24" in hcl

    def test_route_table_includes_route_rules(self):
        """Route table renders route_rules with destination."""
        specs = [
            {"template": "core/route_table", "label": "pub", "params": VALID_PARAMS["core/route_table"]}
        ]
        result = render_specs(specs)
        hcl = result["network.tf"]
        assert "0.0.0.0/0" in hcl
        assert "CIDR_BLOCK" in hcl


class TestSchemaValidation:
    """Schema rejects invalid params via Pydantic validation."""

    def test_vcn_missing_required_compartment_id(self):
        """VCN rejects params without compartment_id."""
        specs = [
            {"template": "core/vcn", "label": "bad", "params": {"display_name": "no-compartment"}}
        ]
        with pytest.raises(TemplateRenderError) as exc_info:
            render_specs(specs)
        assert "validation failed" in str(exc_info.value).lower() or "validation" in str(exc_info.value).lower()

    def test_vcn_missing_required_aws_source_id(self):
        """VCN rejects params without aws_source_id."""
        specs = [
            {
                "template": "core/vcn",
                "label": "bad",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["10.0.0.0/16"],
                    "display_name": "vcn",
                    # aws_source_id missing
                },
            }
        ]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_vcn_invalid_cidr(self):
        """VCN rejects invalid CIDR notation."""
        specs = [
            {
                "template": "core/vcn",
                "label": "bad",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": ["not-a-cidr"],
                    "display_name": "vcn",
                    "aws_source_id": "vpc-1",
                },
            }
        ]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_vcn_empty_cidr_blocks(self):
        """VCN rejects empty cidr_blocks list."""
        specs = [
            {
                "template": "core/vcn",
                "label": "bad",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "cidr_blocks": [],
                    "display_name": "vcn",
                    "aws_source_id": "vpc-1",
                },
            }
        ]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_target_asset_missing_shape(self):
        """target_asset rejects params without required shape."""
        specs = [
            {
                "template": "cloud_migrations/target_asset",
                "label": "bad",
                "params": {
                    "migration_plan_id": "ref",
                    "aws_source_id": "i-123",
                    # missing: shape, ocpus, memory_in_gbs
                },
            }
        ]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_target_asset_zero_ocpus_rejected(self):
        """target_asset rejects ocpus < 1."""
        specs = [
            {
                "template": "cloud_migrations/target_asset",
                "label": "bad",
                "params": {
                    "migration_plan_id": "ref",
                    "shape": "VM.Standard.E5.Flex",
                    "ocpus": 0,
                    "memory_in_gbs": 16,
                    "aws_source_id": "i-123",
                },
            }
        ]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_listener_invalid_protocol(self):
        """Listener rejects protocol not in HTTP/HTTPS/TCP."""
        specs = [
            {
                "template": "load_balancer/listener",
                "label": "bad",
                "params": {
                    "load_balancer_id": "ref",
                    "name": "listener",
                    "default_backend_set_name": "bs",
                    "port": 80,
                    "protocol": "UDP",  # not allowed
                    "aws_source_id": "arn:test",
                },
            }
        ]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_listener_port_out_of_range(self):
        """Listener rejects port > 65535."""
        specs = [
            {
                "template": "load_balancer/listener",
                "label": "bad",
                "params": {
                    "load_balancer_id": "ref",
                    "name": "listener",
                    "default_backend_set_name": "bs",
                    "port": 70000,
                    "protocol": "HTTP",
                    "aws_source_id": "arn:test",
                },
            }
        ]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_unknown_template_rejected(self):
        """Unknown template name raises TemplateRenderError."""
        specs = [{"template": "nonexistent/widget", "label": "bad", "params": {}}]
        with pytest.raises(TemplateRenderError, match="No schema"):
            render_specs(specs)

    def test_empty_template_name_rejected(self):
        """Empty template name raises error."""
        specs = [{"template": "", "label": "bad", "params": {}}]
        with pytest.raises(TemplateRenderError, match="Missing"):
            render_specs(specs)

    def test_free_form_hcl_empty_body_rejected(self):
        """free_form_hcl with empty hcl string is rejected."""
        specs = [{"template": "free_form_hcl", "label": "bad", "params": {"hcl": ""}}]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_subnet_invalid_cidr(self):
        """Subnet rejects malformed CIDR."""
        params = dict(VALID_PARAMS["core/subnet"])
        params["cidr_block"] = "999.999.999.999/99"
        specs = [{"template": "core/subnet", "label": "bad", "params": params}]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_security_rule_invalid_protocol(self):
        """SecurityList rejects invalid protocol in ingress rules."""
        params = dict(VALID_PARAMS["core/security_list"])
        params["ingress_security_rules"] = [
            {"source": "0.0.0.0/0", "protocol": "999", "stateless": False}
        ]
        specs = [{"template": "core/security_list", "label": "bad", "params": params}]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_public_ip_invalid_lifetime(self):
        """PublicIp rejects lifetime not in RESERVED/EPHEMERAL."""
        params = dict(VALID_PARAMS["core/public_ip"])
        params["lifetime"] = "PERMANENT"
        specs = [{"template": "core/public_ip", "label": "bad", "params": params}]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)

    def test_lb_shape_details_bandwidth_too_low(self):
        """Load balancer rejects shape_details with bandwidth < 10."""
        params = dict(VALID_PARAMS["load_balancer/load_balancer"])
        params["shape_details"] = {
            "minimum_bandwidth_in_mbps": 1,
            "maximum_bandwidth_in_mbps": 5,
        }
        specs = [{"template": "load_balancer/load_balancer", "label": "bad", "params": params}]
        with pytest.raises(TemplateRenderError):
            render_specs(specs)


class TestSchemaTemplateMismatch:
    """Document known mismatches between Pydantic schemas and Jinja2 templates.

    These tests verify the bug exists so it gets tracked; they should be
    updated when the mismatch is fixed.
    """

    def test_nsg_rule_tcp_options_schema_vs_template_mismatch(self):
        """NsgSecurityRuleParams.tcp_options uses TcpUdpOptions(min, max) but
        the Jinja2 template expects tcp_options.destination_port_range.min/max.

        Schema validation passes but rendering fails because the template
        accesses a nested 'destination_port_range' key that doesn't exist
        in the model_dump output.
        """
        # Schema validation succeeds with flat min/max
        from app.templates.schemas.core import NsgSecurityRuleParams

        params = {
            "network_security_group_id": "oci_core_network_security_group.main.id",
            "direction": "INGRESS",
            "protocol": "6",
            "source": '"0.0.0.0/0"',
            "source_type": "CIDR_BLOCK",
            "stateless": False,
            "tcp_options": {"min": 443, "max": 443},
            "aws_source_id": "sgr-12345",
        }
        validated = NsgSecurityRuleParams.model_validate(params)
        assert validated.tcp_options is not None
        assert validated.tcp_options.min == 443

        # But rendering fails because the template expects
        # tcp_options.destination_port_range.min
        specs = [
            {
                "template": "core/network_security_group_security_rule",
                "label": "test",
                "params": params,
            }
        ]
        with pytest.raises(TemplateRenderError, match="Jinja2 rendering failed"):
            render_specs(specs)
