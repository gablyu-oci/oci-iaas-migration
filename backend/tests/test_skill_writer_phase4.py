"""Phase 4 integration: structured output -> template rendering -> resource graph.

Tests the full round-trip for all 6 Phase 4 skills:
  1. Verify skill membership in STRUCTURED_OUTPUT_SKILLS
  2. Build SkillGroup, feed valid spec JSON to _process_structured_output
  3. Assert rendered HCL lands in the correct output file with expected resource types
  4. Assert specs_to_graph produces correctly typed ResourceNode entries
  5. Validate multi-skill graph merge with ResourceGraph
"""

import pytest

from app.agents.skill_group import (
    SKILL_SPECS,
    STRUCTURED_OUTPUT_SKILLS,
    SkillGroup,
)
from app.services.resource_graph import specs_to_graph, ResourceGraph


class TestPhase4StructuredOutputSkills:
    """All 6 Phase 4 skills are in STRUCTURED_OUTPUT_SKILLS."""

    PHASE_4_SKILLS = [
        "ec2_translation",
        "storage_translation",
        "iam_translation",
        "security_translation",
        "serverless_translation",
        "observability_translation",
    ]

    def test_all_phase4_skills_are_structured(self):
        for skill in self.PHASE_4_SKILLS:
            assert skill in STRUCTURED_OUTPUT_SKILLS, (
                f"{skill} should be in STRUCTURED_OUTPUT_SKILLS"
            )

    def test_structured_output_skills_total_count(self):
        """Phase 1 (3) + Phase 4 (6) = 9 total."""
        assert len(STRUCTURED_OUTPUT_SKILLS) == 9

    def test_cfn_terraform_not_structured(self):
        assert "cfn_terraform" not in STRUCTURED_OUTPUT_SKILLS

    def test_data_migration_not_structured(self):
        assert "data_migration_planning" not in STRUCTURED_OUTPUT_SKILLS


class TestEc2TranslationRoundTrip:
    """ec2_translation spec -> render -> graph."""

    def test_instance_spec_renders_and_graphs(self):
        group = SkillGroup(SKILL_SPECS["ec2_translation"])
        draft = {"specs": [{
            "template": "core/instance",
            "label": "web_prod",
            "params": {
                "compartment_id": "var.compartment_id",
                "availability_domain": "Uocm:PHX-AD-1",
                "display_name": "web-prod",
                "shape": "VM.Standard.E5.Flex",
                "shape_config": {"ocpus": 4, "memory_in_gbs": 64},
                "source_details": {
                    "source_type": "image",
                    "source_id": "ocid1.image.oc1..xxx",
                },
                "aws_source_id": "i-0abc123",
            },
        }]}
        result = group._process_structured_output(draft)
        assert "network.tf" in result
        assert "oci_core_instance" in result["network.tf"]

        # Graph round-trip
        specs = group._extract_specs_from_draft(draft)
        nodes, ids = specs_to_graph(specs, "ec2_translation")
        assert len(nodes) == 1
        assert nodes[0].domain == "network"  # core prefix maps to network
        assert nodes[0].aws_source_id == "i-0abc123"

    def test_autoscaling_multi_resource_spec(self):
        """ASG translation produces instance_configuration + pool."""
        group = SkillGroup(SKILL_SPECS["ec2_translation"])
        draft = {"specs": [
            {
                "template": "core/instance_configuration",
                "label": "asg_config",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "display_name": "asg-config",
                    "instance_details": {
                        "instance_type": "compute",
                        "launch_details": {
                            "shape": "VM.Standard.E5.Flex",
                            "source_details": {
                                "source_type": "image",
                                "source_id": "ocid1.image.oc1..xxx",
                            },
                        },
                    },
                    "aws_source_id": "lt-0abc",
                },
            },
            {
                "template": "core/instance_pool",
                "label": "asg_pool",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "display_name": "asg-pool",
                    "instance_configuration_id": (
                        "oci_core_instance_configuration.asg_config.id"
                    ),
                    "size": 3,
                    "placement_configurations": [
                        {
                            "availability_domain": "Uocm:PHX-AD-1",
                            "primary_subnet_id": "oci_core_subnet.app.id",
                        },
                    ],
                    "aws_source_id": "asg-0abc",
                },
            },
        ]}
        result = group._process_structured_output(draft)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert "oci_core_instance_configuration" in hcl
        assert "oci_core_instance_pool" in hcl

    def test_instance_with_vnic_details(self):
        """Instance with create_vnic_details renders correctly."""
        group = SkillGroup(SKILL_SPECS["ec2_translation"])
        draft = {"specs": [{
            "template": "core/instance",
            "label": "app_server",
            "params": {
                "compartment_id": "var.compartment_id",
                "availability_domain": "Uocm:PHX-AD-1",
                "display_name": "app-server",
                "shape": "VM.Standard.E5.Flex",
                "shape_config": {"ocpus": 2, "memory_in_gbs": 32},
                "source_details": {
                    "source_type": "image",
                    "source_id": "ocid1.image.oc1..xxx",
                },
                "create_vnic_details": {
                    "subnet_id": "oci_core_subnet.private.id",
                    "assign_public_ip": False,
                },
                "aws_source_id": "i-0def456",
            },
        }]}
        result = group._process_structured_output(draft)
        assert "network.tf" in result
        assert "oci_core_instance" in result["network.tf"]


class TestStorageTranslationRoundTrip:
    """storage_translation spec -> render -> graph."""

    def test_block_volume_and_attachment(self):
        group = SkillGroup(SKILL_SPECS["storage_translation"])
        draft = {"specs": [
            {
                "template": "core/block_volume",
                "label": "data_vol",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "availability_domain": "Uocm:PHX-AD-1",
                    "display_name": "data-volume",
                    "size_in_gbs": 500,
                    "aws_source_id": "vol-0abc",
                },
            },
            {
                "template": "core/block_volume_attachment",
                "label": "data_attach",
                "params": {
                    "instance_id": "oci_core_instance.web.id",
                    "volume_id": "oci_core_volume.data_vol.id",
                    "attachment_type": "paravirtualized",
                    "aws_source_id": "vol-attach-0abc",
                },
            },
        ]}
        result = group._process_structured_output(draft)
        assert "network.tf" in result
        hcl = result["network.tf"]
        assert "oci_core_volume" in hcl
        assert "oci_core_volume_attachment" in hcl

    def test_block_volume_graph_domain(self):
        """Block volume specs map to 'network' domain (core prefix)."""
        specs = [{
            "template": "core/block_volume",
            "label": "vol1",
            "params": {
                "compartment_id": "var.c",
                "availability_domain": "AD-1",
                "display_name": "v1",
                "size_in_gbs": 100,
                "aws_source_id": "vol-1",
            },
        }]
        nodes, ids = specs_to_graph(specs, "storage_translation")
        assert len(nodes) == 1
        assert nodes[0].domain == "network"
        assert nodes[0].aws_source_id == "vol-1"


class TestIamTranslationRoundTrip:
    """iam_translation spec -> render -> graph."""

    def test_dynamic_group_and_policy(self):
        group = SkillGroup(SKILL_SPECS["iam_translation"])
        draft = {"specs": [
            {
                "template": "identity/dynamic_group",
                "label": "compute_dg",
                "params": {
                    "compartment_id": "var.tenancy_ocid",
                    "name": "compute-dg",
                    "description": "Dynamic group for compute instances",
                    "matching_rule": (
                        "ALL {instance.compartment.id = "
                        "'ocid1.compartment.oc1..xxx'}"
                    ),
                    "aws_source_id": "role-compute",
                },
            },
            {
                "template": "identity/policy",
                "label": "compute_policy",
                "params": {
                    "compartment_id": "var.tenancy_ocid",
                    "name": "compute-policy",
                    "description": "Policy for compute dynamic group",
                    "statements": [
                        "Allow dynamic-group compute-dg to manage instances "
                        "in compartment id ocid1.compartment.oc1..xxx",
                    ],
                    "aws_source_id": "policy-compute",
                },
            },
        ]}
        result = group._process_structured_output(draft)
        assert "iam.tf" in result
        hcl = result["iam.tf"]
        assert "oci_identity_dynamic_group" in hcl
        assert "oci_identity_policy" in hcl

        # Graph round-trip
        specs = group._extract_specs_from_draft(draft)
        nodes, ids = specs_to_graph(specs, "iam_translation")
        assert len(nodes) == 2
        assert nodes[0].domain == "iam"
        assert nodes[1].domain == "iam"


class TestSecurityTranslationRoundTrip:
    """security_translation spec -> render -> graph."""

    def test_vault_key_secret(self):
        group = SkillGroup(SKILL_SPECS["security_translation"])
        draft = {"specs": [
            {
                "template": "vault/vault",
                "label": "main_vault",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "display_name": "migration-vault",
                    "vault_type": "DEFAULT",
                    "aws_source_id": "kms-key-id",
                },
            },
            {
                "template": "vault/key",
                "label": "main_key",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "display_name": "migration-key",
                    "management_endpoint": (
                        "oci_kms_vault.main_vault.management_endpoint"
                    ),
                    "key_shape": {"algorithm": "AES", "length": 32},
                    "aws_source_id": "kms-key-0abc",
                },
            },
            {
                "template": "vault/secret",
                "label": "db_secret",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "vault_id": "oci_kms_vault.main_vault.id",
                    "key_id": "oci_kms_key.main_key.id",
                    "secret_name": "db-password",
                    "secret_content": {
                        "content_type": "BASE64",
                        "content": "cGxhY2Vob2xkZXI=",
                    },
                    "aws_source_id": "secret-0abc",
                },
            },
        ]}
        result = group._process_structured_output(draft)
        assert "security.tf" in result
        hcl = result["security.tf"]
        assert "oci_kms_vault" in hcl
        assert "oci_kms_key" in hcl
        assert "oci_vault_secret" in hcl

    def test_vault_virtual_private_type(self):
        """VIRTUAL_PRIVATE vault type is accepted."""
        group = SkillGroup(SKILL_SPECS["security_translation"])
        draft = {"specs": [{
            "template": "vault/vault",
            "label": "private_vault",
            "params": {
                "compartment_id": "var.compartment_id",
                "display_name": "private-vault",
                "vault_type": "VIRTUAL_PRIVATE",
                "aws_source_id": "kms-private",
            },
        }]}
        result = group._process_structured_output(draft)
        assert "security.tf" in result
        assert "oci_kms_vault" in result["security.tf"]


class TestServerlessTranslationRoundTrip:
    """serverless_translation spec -> render -> graph."""

    def test_application_and_function(self):
        group = SkillGroup(SKILL_SPECS["serverless_translation"])
        draft = {"specs": [
            {
                "template": "functions/application",
                "label": "my_app",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "display_name": "my-functions-app",
                    "subnet_ids": ["oci_core_subnet.app.id"],
                    "aws_source_id": "lambda-app",
                },
            },
            {
                "template": "functions/function",
                "label": "handler",
                "params": {
                    "application_id": (
                        "oci_functions_application.my_app.id"
                    ),
                    "display_name": "request-handler",
                    "image": "iad.ocir.io/namespace/repo:latest",
                    "memory_in_mbs": 256,
                    "aws_source_id": "lambda-handler",
                },
            },
        ]}
        result = group._process_structured_output(draft)
        assert "serverless.tf" in result
        hcl = result["serverless.tf"]
        assert "oci_functions_application" in hcl
        assert "oci_functions_function" in hcl

    def test_serverless_graph_domain(self):
        """Functions specs map to 'serverless' domain."""
        specs = [{
            "template": "functions/application",
            "label": "app1",
            "params": {
                "compartment_id": "var.c",
                "display_name": "app1",
                "subnet_ids": ["oci_core_subnet.a.id"],
                "aws_source_id": "lambda-1",
            },
        }]
        nodes, ids = specs_to_graph(specs, "serverless_translation")
        assert len(nodes) == 1
        assert nodes[0].domain == "serverless"


class TestObservabilityTranslationRoundTrip:
    """observability_translation spec -> render -> graph."""

    def test_log_group_log_alarm(self):
        group = SkillGroup(SKILL_SPECS["observability_translation"])
        draft = {"specs": [
            {
                "template": "observability/log_group",
                "label": "app_logs",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "display_name": "app-log-group",
                    "aws_source_id": "log-group-app",
                },
            },
            {
                "template": "observability/log",
                "label": "app_log",
                "params": {
                    "log_group_id": (
                        "oci_logging_log_group.app_logs.id"
                    ),
                    "display_name": "app-log",
                    "log_type": "CUSTOM",
                    "aws_source_id": "log-stream-app",
                },
            },
            {
                "template": "observability/metric_alarm",
                "label": "cpu_alarm",
                "params": {
                    "compartment_id": "var.compartment_id",
                    "display_name": "high-cpu-alarm",
                    "metric_compartment_id": "var.compartment_id",
                    "namespace": "oci_computeagent",
                    "query": "CpuUtilization[5m].mean() > 80",
                    "severity": "WARNING",
                    "destinations": [
                        "oci_ons_notification_topic.alerts.id",
                    ],
                    "aws_source_id": "alarm-cpu-high",
                },
            },
        ]}
        result = group._process_structured_output(draft)
        assert "observability.tf" in result
        hcl = result["observability.tf"]
        assert "oci_logging_log_group" in hcl
        assert "oci_logging_log" in hcl
        assert "oci_monitoring_alarm" in hcl

    def test_observability_graph_domain(self):
        """Observability specs map to 'observability' domain."""
        specs = [{
            "template": "observability/log_group",
            "label": "lg1",
            "params": {
                "compartment_id": "var.c",
                "display_name": "lg1",
                "aws_source_id": "lg-1",
            },
        }]
        nodes, ids = specs_to_graph(specs, "observability_translation")
        assert len(nodes) == 1
        assert nodes[0].domain == "observability"


class TestGraphIntegration:
    """Full ResourceGraph round-trip for Phase 4 skills."""

    def test_multi_skill_graph_merge(self):
        """Multiple Phase 4 skills can add nodes to the same graph."""
        graph = ResourceGraph()

        # IAM nodes
        iam_specs = [
            {
                "template": "identity/dynamic_group",
                "label": "dg1",
                "params": {
                    "compartment_id": "var.t",
                    "name": "dg1",
                    "description": "test",
                    "matching_rule": "ALL {instance.compartment.id = 'x'}",
                    "aws_source_id": "role-1",
                },
            },
        ]
        nodes, ids = specs_to_graph(iam_specs, "iam_translation")
        for node in nodes:
            graph.add_node(node)

        # Security nodes
        sec_specs = [
            {
                "template": "vault/vault",
                "label": "v1",
                "params": {
                    "compartment_id": "var.c",
                    "display_name": "v1",
                    "vault_type": "DEFAULT",
                    "aws_source_id": "kms-1",
                },
            },
        ]
        nodes, ids = specs_to_graph(sec_specs, "security_translation")
        for node in nodes:
            graph.add_node(node)

        assert len(graph.nodes) == 2
        errors = graph.validate()
        assert errors == []

    def test_graph_find_by_aws_id(self):
        """ResourceGraph.find_by_aws_id locates Phase 4 nodes."""
        graph = ResourceGraph()
        specs = [{
            "template": "functions/application",
            "label": "app1",
            "params": {
                "compartment_id": "var.c",
                "display_name": "app1",
                "subnet_ids": ["oci_core_subnet.a.id"],
                "aws_source_id": "lambda-fn-123",
            },
        }]
        nodes, ids = specs_to_graph(specs, "serverless_translation")
        for node in nodes:
            graph.add_node(node)

        found = graph.find_by_aws_id("lambda-fn-123")
        assert found is not None
        assert found.template == "functions/application"

    def test_graph_duplicate_node_raises(self):
        """Adding the same (template, label) twice raises ValueError."""
        graph = ResourceGraph()
        specs = [{
            "template": "vault/vault",
            "label": "dup",
            "params": {
                "compartment_id": "var.c",
                "display_name": "dup",
                "vault_type": "DEFAULT",
                "aws_source_id": "kms-dup",
            },
        }]
        nodes, _ = specs_to_graph(specs, "security_translation")
        graph.add_node(nodes[0])
        with pytest.raises(ValueError, match="Duplicate node"):
            graph.add_node(nodes[0])

    def test_template_specs_preserved_in_result(self):
        """_process_structured_output stores original specs under _template_specs."""
        group = SkillGroup(SKILL_SPECS["iam_translation"])
        original_specs = [{
            "template": "identity/policy",
            "label": "p1",
            "params": {
                "compartment_id": "var.t",
                "name": "p1",
                "description": "d",
                "statements": ["Allow group admins to manage all-resources in tenancy"],
                "aws_source_id": "pol-1",
            },
        }]
        draft = {"specs": original_specs}
        result = group._process_structured_output(draft)
        assert result["_template_specs"] == original_specs
