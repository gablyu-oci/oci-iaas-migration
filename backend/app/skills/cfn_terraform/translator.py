#!/usr/bin/env python3
"""
AWS CloudFormation to OCI Terraform Translator
Automatically converts AWS CloudFormation templates to OCI-compatible Terraform configurations.

Two-phase approach:
1. Use cf2tf to convert CloudFormation → AWS Terraform
2. Transform AWS Terraform → OCI Terraform with resource mapping
"""

import json
import yaml
import argparse
import re
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Set, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class TranslationResult:
    """Result of translating a CloudFormation template to OCI Terraform."""
    resources: Dict[str, str] = field(default_factory=dict)  # resource.tf content by type
    variables: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # variables.tf
    outputs: Dict[str, Dict[str, str]] = field(default_factory=dict)  # outputs.tf
    provider_config: str = ""  # provider.tf
    migration_notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    gaps: List[Dict[str, str]] = field(default_factory=list)
    unsupported: List[Dict[str, str]] = field(default_factory=list)
    success_count: int = 0
    total_count: int = 0


class ContainerTargetSelector:
    """Selects the appropriate OCI container platform based on CloudFormation resource analysis."""

    # AWS resource types that indicate container workloads needing orchestration
    MESH_TYPES = {'AWS::AppMesh::Mesh', 'AWS::AppMesh::VirtualService',
                  'AWS::AppMesh::VirtualNode', 'AWS::AppMesh::VirtualRouter',
                  'AWS::AppMesh::Route', 'AWS::AppMesh::GatewayRoute',
                  'AWS::AppMesh::VirtualGateway'}
    DISCOVERY_TYPES = {'AWS::ServiceDiscovery::PrivateDnsNamespace',
                       'AWS::ServiceDiscovery::PublicDnsNamespace',
                       'AWS::ServiceDiscovery::Service'}
    ECS_TYPES = {'AWS::ECS::Cluster', 'AWS::ECS::Service',
                 'AWS::ECS::TaskDefinition'}
    SCALING_TYPES = {'AWS::ApplicationAutoScaling::ScalableTarget',
                     'AWS::ApplicationAutoScaling::ScalingPolicy'}

    @classmethod
    def select_target(cls, cfn_resource_types: Set[str]) -> str:
        """
        Decide between 'OKE' and 'CONTAINER_INSTANCES' based on resource types present.

        Returns:
            'OKE' - When service mesh, multi-service discovery, or autoscaling is needed
            'CONTAINER_INSTANCES' - For simple single-container workloads
        """
        has_mesh = bool(cfn_resource_types & cls.MESH_TYPES)
        has_discovery = bool(cfn_resource_types & cls.DISCOVERY_TYPES)
        has_scaling = bool(cfn_resource_types & cls.SCALING_TYPES)
        ecs_service_count = sum(1 for t in cfn_resource_types if t == 'AWS::ECS::Service')
        has_ecs = bool(cfn_resource_types & cls.ECS_TYPES)

        # OKE is required when:
        # 1. Service mesh is used (no Container Instances equivalent)
        # 2. Multiple services with discovery (K8s DNS is native)
        # 3. Autoscaling with ECS (HPA is native in OKE)
        if has_mesh:
            return 'OKE'
        if has_discovery and has_ecs:
            return 'OKE'
        if has_scaling and has_ecs:
            return 'OKE'
        if ecs_service_count > 1:
            return 'OKE'
        if has_ecs:
            return 'CONTAINER_INSTANCES'
        return 'NONE'

    @classmethod
    def get_target_rationale(cls, cfn_resource_types: Set[str], target: str) -> str:
        """Return human-readable rationale for the target selection."""
        reasons = []
        if cfn_resource_types & cls.MESH_TYPES:
            reasons.append("App Mesh requires OCI Service Mesh (OKE only)")
        if cfn_resource_types & cls.DISCOVERY_TYPES:
            reasons.append("Service discovery maps to native K8s DNS in OKE")
        if cfn_resource_types & cls.SCALING_TYPES:
            reasons.append("ECS autoscaling maps to HPA in OKE")
        svc_count = sum(1 for t in cfn_resource_types if t == 'AWS::ECS::Service')
        if svc_count > 1:
            reasons.append(f"{svc_count} ECS services benefit from K8s orchestration")
        if not reasons and target == 'CONTAINER_INSTANCES':
            reasons.append("Simple single-container workload suitable for Container Instances")
        return "; ".join(reasons) if reasons else "No container workload detected"


class ResourceMapper:
    """Maps AWS resources to OCI resources with property translation."""

    # AWS → OCI resource type mapping
    RESOURCE_MAP = {
        # Networking
        'aws_vpc': {
            'oci_type': 'oci_core_vcn',
            'properties': {
                'cidr_block': 'cidr_blocks',
                'enable_dns_support': None,      # OCI dns_label is a string, not boolean
                'enable_dns_hostnames': None,    # OCI dns_label is a string, not boolean
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id'],
            'notes': 'VCN is regional in OCI, not AZ-specific'
        },
        'aws_subnet': {
            'oci_type': 'oci_core_subnet',
            'properties': {
                'vpc_id': 'vcn_id',
                'cidr_block': 'cidr_block',
                'availability_zone': 'availability_domain',  # Requires lookup
                'map_public_ip_on_launch': 'prohibit_public_ip_on_vnic',  # Inverted
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'vcn_id'],
            'notes': 'OCI subnets can be regional or AD-specific'
        },
        'aws_internet_gateway': {
            'oci_type': 'oci_core_internet_gateway',
            'properties': {
                'vpc_id': 'vcn_id',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'vcn_id'],
            'notes': 'Direct mapping'
        },
        'aws_nat_gateway': {
            'oci_type': 'oci_core_nat_gateway',
            'properties': {
                'subnet_id': 'vcn_id',  # NAT gateway is VCN-level, not subnet-level
                'allocation_id': None,  # No EIP concept in OCI
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'vcn_id'],
            'notes': 'OCI NAT gateway is VCN-scoped, no EIP needed'
        },
        'aws_route_table': {
            'oci_type': 'oci_core_route_table',
            'properties': {
                'vpc_id': 'vcn_id',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'vcn_id'],
            'notes': 'Routes defined in route_rules blocks'
        },
        'aws_route': {
            'oci_type': None,  # Not a separate resource in OCI; routes are route_rules in route_table
            'properties': {},
            'required': [],
            'notes': 'Routes must be consolidated into parent route_table route_rules as route_rules blocks'
        },
        'aws_security_group': {
            'oci_type': 'oci_core_network_security_group',
            'properties': {
                'vpc_id': 'vcn_id',
                'description': 'display_name',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'vcn_id'],
            'notes': 'Security rules must be created as separate resources'
        },
        'aws_eip': {
            'oci_type': 'oci_core_public_ip',
            'properties': {
                'domain': None,  # Not applicable in OCI
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'lifetime'],
            'notes': 'OCI public IPs are RESERVED (persistent) or EPHEMERAL; set lifetime="RESERVED"'
        },
        'aws_vpc_gateway_attachment': {
            'oci_type': None,  # Not a separate resource in OCI
            'properties': {},
            'required': [],
            'notes': 'Internet gateway is automatically attached to VCN in OCI'
        },
        'aws_subnet_route_table_association': {
            'oci_type': None,  # Not a separate resource in OCI
            'properties': {},
            'required': [],
            'notes': 'Route tables are associated via subnet route_table_id property'
        },
        
        # Compute
        'aws_instance': {
            'oci_type': 'oci_core_instance',
            'properties': {
                'ami': 'source_details.source_id',
                'instance_type': 'shape',  # Requires mapping
                'subnet_id': 'create_vnic_details.subnet_id',
                'key_name': 'metadata.ssh_authorized_keys',
                'vpc_security_group_ids': 'create_vnic_details.nsg_ids',
                'user_data': 'metadata.user_data',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'availability_domain', 'shape'],
            'notes': 'Instance type requires manual mapping, requires SSH key'
        },
        'aws_launch_template': {
            'oci_type': 'oci_core_instance_configuration',
            'properties': {
                'image_id': 'instance_details.launch_details.source_details.source_id',
                'instance_type': 'instance_details.launch_details.shape',
                'user_data': 'instance_details.launch_details.metadata.user_data',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id'],
            'notes': 'Used for instance pools and auto-scaling'
        },
        'aws_autoscaling_group': {
            'oci_type': 'oci_core_instance_pool',
            'properties': {
                'launch_template': 'instance_configuration_id',
                'min_size': 'size',  # Initial size
                'max_size': None,  # Set in autoscaling_configuration
                'desired_capacity': 'size',
                'vpc_zone_identifier': 'placement_configurations',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'instance_configuration_id'],
            'notes': 'Requires separate oci_autoscaling_auto_scaling_configuration'
        },
        'aws_ebs_volume': {
            'oci_type': 'oci_core_volume',
            'properties': {
                'availability_zone': 'availability_domain',
                'size': 'size_in_gbs',
                'volume_type': 'vpus_per_gb',  # gp3→auto, io1→higher VPU
                'encrypted': 'is_auto_tune_enabled',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'availability_domain'],
            'notes': 'OCI uses VPUs for performance tuning'
        },
        'aws_volume_attachment': {
            'oci_type': 'oci_core_volume_attachment',
            'properties': {
                'device_name': 'device',
                'instance_id': 'instance_id',
                'volume_id': 'volume_id'
            },
            'required': ['attachment_type'],
            'notes': 'OCI requires attachment_type (iscsi or paravirtualized)'
        },
        
        # Load Balancers
        'aws_lb': {
            'oci_type': 'oci_load_balancer_load_balancer',
            'properties': {
                'subnets': 'subnet_ids',
                'internal': 'is_private',
                'load_balancer_type': 'shape',  # application→flexible, network→unsupported
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'shape'],
            'notes': 'OCI supports flexible shape (application LB only)'
        },
        'aws_lb_target_group': {
            'oci_type': 'oci_load_balancer_backend_set',
            'name_attr': 'name',
            'properties': {
                'port': 'health_checker.port',
                'protocol': 'health_checker.protocol',
                'vpc_id': None,
                'health_check': 'health_checker',
                'tags': None
            },
            'required': ['load_balancer_id', 'name', 'policy'],
            'notes': 'Health checker configuration different in OCI'
        },
        'aws_lb_listener': {
            'oci_type': 'oci_load_balancer_listener',
            'name_attr': 'name',
            'properties': {
                'load_balancer_arn': 'load_balancer_id',
                'port': 'port',
                'protocol': 'protocol',
                'default_action': 'default_backend_set_name',
                'certificate_arn': 'ssl_configuration'
            },
            'required': ['load_balancer_id', 'name', 'port', 'protocol'],
            'notes': 'SSL configuration structure different'
        },
        
        # Database
        'aws_db_instance': {
            'oci_type': 'oci_database_autonomous_database',  # Or db_system for Oracle
            'properties': {
                'allocated_storage': 'data_storage_size_in_tbs',
                'engine': 'db_workload',  # postgres→OLTP, mysql→DW
                'engine_version': 'db_version',
                'instance_class': 'cpu_core_count',
                'db_name': 'db_name',
                'username': 'admin_password',  # admin user is always ADMIN
                'password': 'admin_password',
                'db_subnet_group_name': 'subnet_id',
                'vpc_security_group_ids': 'nsg_ids',
                'multi_az': 'is_auto_scaling_enabled',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'db_name', 'admin_password'],
            'notes': 'PostgreSQL/MySQL require Autonomous DB; Oracle can use DB System'
        },
        
        # Storage
        'aws_s3_bucket': {
            'oci_type': 'oci_objectstorage_bucket',
            'name_attr': 'name',  # Uses 'name' not 'display_name'
            'properties': {
                'bucket': 'name',
                'acl': 'access_type',  # private→NoPublicAccess, public-read→ObjectRead
                'versioning': 'versioning',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'namespace', 'name'],
            'notes': 'Requires namespace (tenancy-specific)'
        },
        'aws_s3_bucket_policy': {
            'oci_type': 'oci_identity_policy',  # Bucket-level policies become IAM policies
            'name_attr': 'name',
            'properties': {
                'bucket': None,
                'policy': 'statements'
            },
            'required': ['compartment_id', 'description', 'name', 'statements'],
            'notes': 'S3 bucket policies map to OCI IAM policies'
        },
        
        # Serverless
        'aws_lambda_function': {
            'oci_type': 'oci_functions_function',
            'properties': {
                'function_name': 'display_name',
                'runtime': None,        # OCI Functions use Docker images, not runtimes
                'handler': None,        # OCI uses image entrypoint
                'role': None,           # OCI uses dynamic groups instead
                'code': None,           # ZipFile inline code not supported in OCI Functions
                'environment': None,    # Handled separately via config map
                'memory_size': 'memory_in_mbs',
                'timeout': 'timeout_in_seconds',
                'tags': 'freeform_tags'
            },
            'required': ['application_id', 'display_name', 'image', 'memory_in_mbs'],
            'notes': 'OCI Functions require Docker images and application context'
        },
        
        # IAM
        'aws_iam_role': {
            'oci_type': 'oci_identity_dynamic_group',
            'name_attr': 'name',  # Uses 'name' not 'display_name'
            'properties': {
                'assume_role_policy_document': None,  # Complex JSON - use placeholder matching_rule
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'description', 'matching_rule', 'name'],
            'notes': 'IAM roles map to dynamic groups for instance principals'
        },
        'aws_iam_policy': {
            'oci_type': 'oci_identity_policy',
            'name_attr': 'name',  # Uses 'name' not 'display_name'
            'properties': {
                'policy': 'statements',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'description', 'name', 'statements'],
            'notes': 'Policy syntax completely different in OCI'
        },

        # --- Container / Kubernetes (OKE target) ---
        'aws_ecs_cluster': {
            'oci_type': 'oci_containerengine_cluster',
            'properties': {
                'cluster_name': 'name',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'vcn_id', 'kubernetes_version'],
            'notes': 'ECS Cluster maps to OKE cluster. Fargate → virtual node pool or managed nodes.'
        },
        'aws_ecs_service': {
            'oci_type': 'kubernetes_deployment',
            'properties': {
                'service_name': 'metadata.name',
                'desired_count': 'spec.replicas',
                'task_definition': 'spec.template.spec.containers',
                'tags': None
            },
            'required': [],
            'notes': 'ECS Service maps to K8s Deployment + Service. Load balancer config becomes K8s Service type LoadBalancer or Ingress.'
        },
        'aws_ecs_task_definition': {
            'oci_type': 'kubernetes_deployment',
            'properties': {
                'family': 'metadata.name',
                'cpu': 'spec.template.spec.containers[0].resources.requests.cpu',
                'memory': 'spec.template.spec.containers[0].resources.requests.memory',
                'container_definitions': 'spec.template.spec.containers',
                'tags': None
            },
            'required': [],
            'notes': 'ECS Task Definition maps to K8s Pod spec within Deployment. Secrets from Secrets Manager become K8s Secrets + Vault references.'
        },

        # --- Container / Kubernetes (OKE) - App Mesh ---
        'aws_appmesh_mesh': {
            'oci_type': 'oci_service_mesh_mesh',
            'properties': {
                'mesh_name': 'display_name',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'certificate_authorities'],
            'notes': 'App Mesh maps to OCI Service Mesh. Requires OKE cluster.'
        },
        'aws_appmesh_virtual_service': {
            'oci_type': 'oci_service_mesh_virtual_service',
            'properties': {
                'mesh_name': 'mesh_id',
                'virtual_service_name': 'name',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'mesh_id', 'name'],
            'notes': 'Maps to OCI Virtual Service within Service Mesh.'
        },
        'aws_appmesh_virtual_node': {
            'oci_type': 'oci_service_mesh_virtual_deployment',
            'properties': {
                'mesh_name': 'mesh_id',
                'virtual_node_name': 'name',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'mesh_id', 'virtual_service_id', 'name'],
            'notes': 'App Mesh Virtual Node maps to OCI Virtual Deployment.'
        },

        # --- Service Discovery ---
        'aws_service_discovery_private_dns_namespace': {
            'oci_type': None,
            'properties': {},
            'required': [],
            'notes': 'Cloud Map namespace maps to native K8s DNS in OKE (built-in, no resource needed). For Container Instances, use oci_dns_zone.'
        },
        'aws_service_discovery_service': {
            'oci_type': 'kubernetes_service',
            'properties': {
                'name': 'metadata.name',
                'dns_config': None
            },
            'required': [],
            'notes': 'Cloud Map service maps to K8s Service (ClusterIP) with native DNS. service.namespace.svc.cluster.local'
        },

        # --- ECR ---
        'aws_ecr_repository': {
            'oci_type': 'oci_artifacts_container_repository',
            'properties': {
                'name': 'display_name',
                'image_scanning_configuration': None,
                'encryption_configuration': None,
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id'],
            'notes': 'ECR maps to OCIR. Vulnerability scanning requires separate Security Center setup.'
        },

        # --- SQS ---
        'aws_sqs_queue': {
            'oci_type': 'oci_queue_queue',
            'properties': {
                'name': 'display_name',
                'visibility_timeout_in_seconds': 'visibility_in_seconds',
                'message_retention_seconds': 'retention_in_seconds',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id'],
            'notes': 'SQS maps to OCI Queue. DLQ requires separate queue + dead_letter_queue_delivery_count.'
        },

        # --- Secrets Manager ---
        'aws_secretsmanager_secret': {
            'oci_type': 'oci_vault_secret',
            'properties': {
                'name': 'secret_name',
                'description': 'description',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'vault_id', 'key_id'],
            'notes': 'Secrets Manager maps to OCI Vault. Requires KMS vault and master key. Auto-rotation not supported (manual or Functions-based).'
        },

        # --- CloudWatch ---
        'aws_cloudwatch_log_group': {
            'oci_type': 'oci_logging_log_group',
            'properties': {
                'name': 'display_name',
                'retention_in_days': None,
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id'],
            'notes': 'CloudWatch Log Group maps to OCI Log Group. Retention via oci_logging_log retention_duration.'
        },
        'aws_cloudwatch_metric_alarm': {
            'oci_type': 'oci_monitoring_alarm',
            'properties': {
                'alarm_name': 'display_name',
                'metric_name': 'query',
                'threshold': 'query',
                'comparison_operator': 'query',
                'tags': 'freeform_tags'
            },
            'required': ['compartment_id', 'destinations', 'is_enabled', 'severity', 'query'],
            'notes': 'CloudWatch Alarm maps to OCI Monitoring Alarm. Requires ONS topic for destinations.'
        },

        # --- Application Auto Scaling (OKE HPA) ---
        'aws_appautoscaling_target': {
            'oci_type': 'kubernetes_horizontal_pod_autoscaler',
            'properties': {
                'min_capacity': 'spec.min_replicas',
                'max_capacity': 'spec.max_replicas',
                'resource_id': 'spec.scale_target_ref',
                'tags': None
            },
            'required': [],
            'notes': 'ECS autoscaling target maps to K8s HPA. Requires metrics-server in OKE.'
        },
        'aws_appautoscaling_policy': {
            'oci_type': 'kubernetes_horizontal_pod_autoscaler',
            'properties': {
                'target_value': 'spec.metrics[0].resource.target.average_utilization',
                'predefined_metric_type': 'spec.metrics[0].resource.name',
                'tags': None
            },
            'required': [],
            'notes': 'ECS scaling policy merges into HPA spec. CPU/Memory targets map to K8s resource metrics.'
        }
    }
    
    # Instance type mapping (AWS → OCI)
    INSTANCE_TYPE_MAP = {
        # General purpose
        't2.micro': 'VM.Standard.E2.1.Micro',
        't2.small': 'VM.Standard.E3.Flex',  # 1 OCPU, 1-16GB
        't2.medium': 'VM.Standard.E3.Flex',  # 2 OCPU, 2-32GB
        't3.micro': 'VM.Standard.E4.Flex',
        't3.small': 'VM.Standard.E4.Flex',
        't3.medium': 'VM.Standard.E4.Flex',
        't3.large': 'VM.Standard.E4.Flex',
        'm5.large': 'VM.Standard3.Flex',
        'm5.xlarge': 'VM.Standard3.Flex',
        'm5.2xlarge': 'VM.Standard3.Flex',
        # Compute optimized
        'c5.large': 'VM.Standard3.Flex',
        'c5.xlarge': 'VM.Standard3.Flex',
        'c5.2xlarge': 'VM.Standard3.Flex',
        # Memory optimized
        'r5.large': 'VM.Standard.E4.Flex',
        'r5.xlarge': 'VM.Standard.E4.Flex',
        'r5.2xlarge': 'VM.Standard.E4.Flex',
    }
    
    # Database instance class mapping
    DB_INSTANCE_MAP = {
        'db.t3.micro': {'cpu': 1, 'storage_tb': 1},
        'db.t3.small': {'cpu': 1, 'storage_tb': 1},
        'db.t3.medium': {'cpu': 2, 'storage_tb': 1},
        'db.m5.large': {'cpu': 2, 'storage_tb': 1},
        'db.m5.xlarge': {'cpu': 4, 'storage_tb': 2},
        'db.m5.2xlarge': {'cpu': 8, 'storage_tb': 2},
    }
    
    @classmethod
    def get_oci_resource_type(cls, aws_type: str) -> Optional[Dict[str, Any]]:
        """Get OCI resource mapping for AWS type."""
        return cls.RESOURCE_MAP.get(aws_type)
    
    @classmethod
    def map_instance_type(cls, aws_type: str) -> Tuple[str, Dict[str, Any]]:
        """Map AWS instance type to OCI shape with configuration."""
        oci_shape = cls.INSTANCE_TYPE_MAP.get(aws_type, 'VM.Standard.E4.Flex')
        
        # Determine OCPU and memory based on AWS type
        if 't2.micro' in aws_type or 't3.micro' in aws_type:
            config = {'ocpus': 1, 'memory_in_gbs': 1}
        elif 't2.small' in aws_type or 't3.small' in aws_type:
            config = {'ocpus': 1, 'memory_in_gbs': 2}
        elif 't2.medium' in aws_type or 't3.medium' in aws_type:
            config = {'ocpus': 2, 'memory_in_gbs': 4}
        elif 't3.large' in aws_type:
            config = {'ocpus': 2, 'memory_in_gbs': 8}
        elif 'm5.large' in aws_type or 'c5.large' in aws_type:
            config = {'ocpus': 2, 'memory_in_gbs': 8}
        elif 'm5.xlarge' in aws_type or 'c5.xlarge' in aws_type:
            config = {'ocpus': 4, 'memory_in_gbs': 16}
        elif 'm5.2xlarge' in aws_type or 'c5.2xlarge' in aws_type:
            config = {'ocpus': 8, 'memory_in_gbs': 32}
        else:
            config = {'ocpus': 2, 'memory_in_gbs': 8}
        
        return oci_shape, config


class CFNParser:
    """Parse CloudFormation templates (YAML or JSON)."""
    
    def __init__(self):
        """Initialize parser with CloudFormation YAML constructors."""
        # Add custom YAML constructors for CloudFormation intrinsic functions
        self._setup_yaml_constructors()
    
    def _setup_yaml_constructors(self):
        """Setup YAML constructors for CloudFormation intrinsic functions."""
        def ref_constructor(loader, node):
            return {'Ref': loader.construct_scalar(node)}
        
        def getatt_constructor(loader, node):
            if isinstance(node, yaml.ScalarNode):
                return {'Fn::GetAtt': loader.construct_scalar(node).split('.')}
            return {'Fn::GetAtt': loader.construct_sequence(node)}
        
        def sub_constructor(loader, node):
            if isinstance(node, yaml.ScalarNode):
                return {'Fn::Sub': loader.construct_scalar(node)}
            return {'Fn::Sub': loader.construct_sequence(node)}
        
        def join_constructor(loader, node):
            return {'Fn::Join': loader.construct_sequence(node)}
        
        def select_constructor(loader, node):
            return {'Fn::Select': loader.construct_sequence(node)}
        
        def getazs_constructor(loader, node):
            value = loader.construct_scalar(node) if isinstance(node, yaml.ScalarNode) else ''
            return {'Fn::GetAZs': value}
        
        def if_constructor(loader, node):
            return {'Fn::If': loader.construct_sequence(node)}
        
        def equals_constructor(loader, node):
            return {'Fn::Equals': loader.construct_sequence(node)}
        
        def base64_constructor(loader, node):
            return {'Fn::Base64': loader.construct_scalar(node)}
        
        def cidr_constructor(loader, node):
            return {'Fn::Cidr': loader.construct_sequence(node)}
        
        # Register constructors
        yaml.SafeLoader.add_constructor('!Ref', ref_constructor)
        yaml.SafeLoader.add_constructor('!GetAtt', getatt_constructor)
        yaml.SafeLoader.add_constructor('!Sub', sub_constructor)
        yaml.SafeLoader.add_constructor('!Join', join_constructor)
        yaml.SafeLoader.add_constructor('!Select', select_constructor)
        yaml.SafeLoader.add_constructor('!GetAZs', getazs_constructor)
        yaml.SafeLoader.add_constructor('!If', if_constructor)
        yaml.SafeLoader.add_constructor('!Equals', equals_constructor)
        yaml.SafeLoader.add_constructor('!Base64', base64_constructor)
        yaml.SafeLoader.add_constructor('!Cidr', cidr_constructor)
    
    @staticmethod
    def parse_file(file_path: Path) -> Dict[str, Any]:
        """Parse CloudFormation template file."""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                
            # Try YAML first (supports JSON too)
            try:
                return yaml.safe_load(content)
            except yaml.YAMLError:
                # Fall back to JSON
                return json.loads(content)
        except Exception as e:
            raise ValueError(f"Failed to parse CloudFormation template: {e}")
    
    @staticmethod
    def extract_resources(cfn_template: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract resources section from CloudFormation template."""
        return cfn_template.get('Resources', {})
    
    @staticmethod
    def extract_parameters(cfn_template: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract parameters section."""
        return cfn_template.get('Parameters', {})
    
    @staticmethod
    def extract_outputs(cfn_template: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract outputs section."""
        return cfn_template.get('Outputs', {})


class TerraformGenerator:
    """Generate OCI Terraform code from parsed and mapped resources."""
    
    def __init__(self):
        self.indent = "  "
    
    def generate_provider(self) -> str:
        """Generate OCI provider configuration."""
        return """terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

provider "oci" {
  # Authentication via ~/.oci/config or environment variables
  # tenancy_ocid     = var.tenancy_ocid
  # user_ocid        = var.user_ocid
  # fingerprint      = var.fingerprint
  # private_key_path = var.private_key_path
  # region           = var.region
}

# Data sources for availability domains
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_identity_availability_domain" "ad1" {
  compartment_id = var.tenancy_ocid
  ad_number      = 1
}

data "oci_identity_availability_domain" "ad2" {
  compartment_id = var.tenancy_ocid
  ad_number      = 2
}

data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.compartment_id
}
"""
    
    def generate_variable(self, name: str, var_def: Dict[str, Any]) -> str:
        """Generate a Terraform variable block."""
        lines = [f'variable "{name}" {{']
        
        if 'description' in var_def:
            lines.append(f'{self.indent}description = "{var_def["description"]}"')
        
        if 'type' in var_def:
            lines.append(f'{self.indent}type = {var_def["type"]}')
        
        if 'default' in var_def:
            default_val = var_def['default']
            if isinstance(default_val, str):
                lines.append(f'{self.indent}default = "{default_val}"')
            else:
                lines.append(f'{self.indent}default = {json.dumps(default_val)}')
        
        lines.append('}')
        return '\n'.join(lines)
    
    def generate_resource(self, resource_type: str, resource_name: str, 
                         properties: Dict[str, Any]) -> str:
        """Generate a Terraform resource block."""
        lines = [f'resource "{resource_type}" "{resource_name}" {{']
        
        for key, value in properties.items():
            if isinstance(value, dict):
                lines.append(f'{self.indent}{key} {{')
                for sub_key, sub_value in value.items():
                    lines.append(f'{self.indent}{self.indent}{sub_key} = {self._format_value(sub_value)}')
                lines.append(f'{self.indent}}}')
            elif isinstance(value, list):
                if value and isinstance(value[0], dict):
                    for item in value:
                        lines.append(f'{self.indent}{key} {{')
                        for sub_key, sub_value in item.items():
                            lines.append(f'{self.indent}{self.indent}{sub_key} = {self._format_value(sub_value)}')
                        lines.append(f'{self.indent}}}')
                else:
                    lines.append(f'{self.indent}{key} = {self._format_value(value)}')
            else:
                lines.append(f'{self.indent}{key} = {self._format_value(value)}')
        
        lines.append('}')
        return '\n'.join(lines)
    
    # HCL expressions that should not be quoted
    HCL_EXPRESSION_PREFIXES = (
        'var.', 'data.', 'oci_', 'local.', 'module.',
        'join(', 'element(', 'toset(', 'tolist(', 'tomap(',
        'format(', 'lookup(', 'coalesce(', 'concat(', 'flatten(',
        'merge(', 'jsonencode(', 'yamlencode(', 'base64encode(',
        'null', 'true', 'false',
    )

    def _format_value(self, value: Any) -> str:
        """Format a value for Terraform HCL."""
        if isinstance(value, str):
            # Check if it's a reference or HCL expression (must not be quoted)
            if any(value.startswith(p) for p in self.HCL_EXPRESSION_PREFIXES):
                return value
            else:
                # Escape any embedded quotes and newlines for HCL strings
                escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '')
                return f'"{escaped}"'
        elif isinstance(value, bool):
            return 'true' if value else 'false'
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, list):
            items = [self._format_value(v) for v in value]
            return f'[{", ".join(items)}]'
        elif value is None:
            return 'null'
        else:
            return f'"{value}"'
    
    def generate_output(self, name: str, output_def: Dict[str, Any]) -> str:
        """Generate a Terraform output block."""
        lines = [f'output "{name}" {{']
        
        if 'description' in output_def:
            lines.append(f'{self.indent}description = "{output_def["description"]}"')
        
        if 'value' in output_def:
            lines.append(f'{self.indent}value = {output_def["value"]}')
        
        lines.append('}')
        return '\n'.join(lines)


class CloudFormationTranslator:
    """Main translator orchestrating the conversion process."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.parser = CFNParser()
        self.mapper = ResourceMapper()
        self.generator = TerraformGenerator()
        self.result = TranslationResult()
        # Registry: CF logical name → (oci_type, tf_name) for reference resolution
        self.resource_registry: Dict[str, tuple] = {}
        # Set of logical names that were NOT translated (unsupported resources)
        self.unsupported_logical_names: Set[str] = set()
        # Container platform target (OKE, CONTAINER_INSTANCES, or NONE)
        self.container_target: str = 'NONE'
    
    def log(self, message: str):
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"[INFO] {message}")
    
    def warn(self, message: str):
        """Log warning."""
        print(f"[WARN] {message}", file=sys.stderr)
        self.result.warnings.append(message)
    
    def translate_file(self, cfn_file: Path) -> TranslationResult:
        """Translate a CloudFormation template file to OCI Terraform."""
        self.log(f"Starting translation of {cfn_file}")
        
        # Phase 1: Parse CloudFormation template
        self.log("Phase 1: Parsing CloudFormation template...")
        try:
            cfn_template = self.parser.parse_file(cfn_file)
        except Exception as e:
            self.result.warnings.append(f"Failed to parse CloudFormation: {e}")
            return self.result
        
        resources = self.parser.extract_resources(cfn_template)
        parameters = self.parser.extract_parameters(cfn_template)
        outputs = self.parser.extract_outputs(cfn_template)
        
        self.log(f"Found {len(resources)} resources, {len(parameters)} parameters, {len(outputs)} outputs")
        self.result.total_count = len(resources)

        # Phase 1b: Detect container workloads and select OCI target platform
        cfn_types = {r.get('Type', '') for r in resources.values()}
        self.container_target = ContainerTargetSelector.select_target(cfn_types)
        target_rationale = ContainerTargetSelector.get_target_rationale(cfn_types, self.container_target)
        if self.container_target != 'NONE':
            self.log(f"Container target: {self.container_target} ({target_rationale})")
            self.result.migration_notes.append(
                f"🎯 Container platform selected: {self.container_target} — {target_rationale}"
            )

        # Phase 2: Use cf2tf for initial AWS Terraform conversion
        self.log("Phase 2: Converting to AWS Terraform using cf2tf...")
        aws_tf_content = self._run_cf2tf(cfn_file)
        
        if not aws_tf_content:
            self.warn("cf2tf conversion failed, proceeding with direct translation")
        
        # Phase 3: Convert parameters to variables
        self.log("Phase 3: Converting parameters to variables...")
        self._convert_parameters(parameters)
        
        # Add standard OCI variables
        self._add_standard_variables()
        
        # Phase 4: Translate resources
        self.log("Phase 4: Translating resources to OCI...")
        self._translate_resources(resources, aws_tf_content)
        
        # Phase 5: Convert outputs
        self.log("Phase 5: Converting outputs...")
        self._convert_outputs(outputs)
        
        # Phase 6: Generate provider configuration
        self.log("Phase 6: Generating provider configuration...")
        self.result.provider_config = self.generator.generate_provider()
        
        # Generate summary
        success_rate = (self.result.success_count / self.result.total_count * 100) if self.result.total_count > 0 else 0
        self.log(f"Translation complete: {self.result.success_count}/{self.result.total_count} resources ({success_rate:.1f}%)")
        
        return self.result
    
    def _build_resource_registry(self, resources: Dict[str, Dict[str, Any]]):
        """Pre-pass: build registry of CF logical name → (oci_type, tf_name).
        Used to resolve !Ref and !GetAtt to correct OCI resource references."""
        self.resource_registry = {}
        for logical_name, resource_def in resources.items():
            cfn_type = resource_def.get('Type', '')
            aws_type = self._cfn_type_to_aws_tf_type(cfn_type)
            oci_mapping = self.mapper.get_oci_resource_type(aws_type)
            if oci_mapping and oci_mapping.get('oci_type'):
                oci_type = oci_mapping['oci_type']
                tf_name = self._to_snake_case(logical_name)
                self.resource_registry[logical_name] = (oci_type, tf_name)

    def _find_vcn_reference(self) -> Optional[str]:
        """Find the first VCN in the registry and return its Terraform reference."""
        for logical_name, (oci_type, tf_name) in self.resource_registry.items():
            if oci_type == 'oci_core_vcn':
                return f'oci_core_vcn.{tf_name}.id'
        return None

    def _run_cf2tf(self, cfn_file: Path) -> Optional[str]:
        """Run cf2tf tool to convert CloudFormation to AWS Terraform."""
        try:
            result = subprocess.run(
                ['cf2tf', str(cfn_file)],  # cf2tf takes file path directly
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                self.warn(f"cf2tf failed: {result.stderr}")
                return None
        except subprocess.TimeoutExpired:
            self.warn("cf2tf timeout")
            return None
        except FileNotFoundError:
            self.warn("cf2tf not found in PATH")
            return None
        except Exception as e:
            self.warn(f"cf2tf error: {e}")
            return None
    
    def _convert_parameters(self, parameters: Dict[str, Dict[str, Any]]):
        """Convert CloudFormation parameters to Terraform variables."""
        for param_name, param_def in parameters.items():
            var_name = self._to_snake_case(param_name)
            
            # Map CloudFormation parameter types to Terraform types
            cfn_type = param_def.get('Type', 'String')
            tf_type = 'string'
            
            if cfn_type == 'Number':
                tf_type = 'number'
            elif cfn_type.startswith('List'):
                tf_type = 'list(string)'
            elif cfn_type.startswith('CommaDelimitedList'):
                tf_type = 'list(string)'
            
            var_config = {
                'description': param_def.get('Description', f'Converted from CloudFormation parameter {param_name}'),
                'type': tf_type
            }
            
            if 'Default' in param_def:
                var_config['default'] = param_def['Default']
            
            self.result.variables[var_name] = var_config
    
    def _add_standard_variables(self):
        """Add standard OCI variables required for all resources."""
        standard_vars = {
            'tenancy_ocid': {
                'description': 'OCID of the tenancy',
                'type': 'string'
            },
            'compartment_id': {
                'description': 'OCID of the compartment where resources will be created',
                'type': 'string'
            },
            'region': {
                'description': 'OCI region',
                'type': 'string',
                'default': 'us-ashburn-1'
            },
            'stack_name': {
                'description': 'Stack name (maps from CloudFormation AWS::StackName)',
                'type': 'string',
                'default': 'my-stack'
            },
            'ssh_public_key': {
                'description': 'SSH public key for instance access',
                'type': 'string'
            },
            'db_admin_password': {
                'description': 'Admin password for database instances',
                'type': 'string'
            }
        }

        for var_name, var_def in standard_vars.items():
            if var_name not in self.result.variables:
                self.result.variables[var_name] = var_def
    
    def _translate_resources(self, resources: Dict[str, Dict[str, Any]], aws_tf: Optional[str]):
        """Translate CloudFormation resources to OCI Terraform resources."""
        # Pre-pass: build resource registry for reference resolution
        self._build_resource_registry(resources)

        # Group resources by type for better organization
        resource_groups = defaultdict(list)

        for resource_name, resource_def in resources.items():
            cfn_type = resource_def.get('Type', '')
            properties = resource_def.get('Properties', {})

            self.log(f"Translating {resource_name} ({cfn_type})...")

            # Convert CFN type to AWS TF type (e.g., AWS::EC2::Instance → aws_instance)
            aws_type = self._cfn_type_to_aws_tf_type(cfn_type)

            # Get OCI mapping
            oci_mapping = self.mapper.get_oci_resource_type(aws_type)

            if not oci_mapping:
                self.warn(f"No OCI mapping for {cfn_type} ({aws_type})")
                self.result.unsupported.append({
                    'resource': resource_name,
                    'type': cfn_type,
                    'reason': 'No OCI equivalent found',
                    'workaround': 'Manual implementation required'
                })
                self.unsupported_logical_names.add(resource_name)
                continue

            # Check if OCI type is None (resource not needed in OCI)
            oci_type = oci_mapping.get('oci_type')
            if not oci_type:
                self.log(f"Resource {resource_name} not needed in OCI: {oci_mapping.get('notes', '')}")
                self.result.migration_notes.append(
                    f"ℹ {resource_name} ({cfn_type}): {oci_mapping.get('notes', 'Not needed in OCI')}"
                )
                self.result.success_count += 1
                continue

            # Translate properties
            oci_properties = self._translate_properties(
                properties,
                oci_mapping,
                resource_name,
                cfn_type,
                aws_type
            )

            # Add display_name or name (resource type-specific) if not set
            name_attr = oci_mapping.get('name_attr', 'display_name')
            if name_attr == 'name':
                # Resource uses 'name' not 'display_name' - move display_name → name
                if 'display_name' in oci_properties:
                    oci_properties['name'] = oci_properties.pop('display_name')
                elif 'name' not in oci_properties:
                    oci_properties['name'] = resource_name
            else:
                if 'display_name' not in oci_properties:
                    oci_properties['display_name'] = resource_name

            # Add required OCI-specific properties
            for required_prop in oci_mapping.get('required', []):
                if required_prop not in oci_properties:
                    if required_prop == 'compartment_id':
                        oci_properties['compartment_id'] = 'var.compartment_id'
                    elif required_prop == 'availability_domain':
                        oci_properties['availability_domain'] = 'data.oci_identity_availability_domain.ad1.name'
                    elif required_prop == 'namespace':
                        oci_properties['namespace'] = 'data.oci_objectstorage_namespace.ns.namespace'
                    elif required_prop == 'vcn_id':
                        vcn_ref = self._find_vcn_reference()
                        if vcn_ref:
                            oci_properties['vcn_id'] = vcn_ref
                        else:
                            self.warn(f"Cannot auto-populate vcn_id for {resource_name}")
                            self.result.migration_notes.append(
                                f"⚠ {resource_name}: Set 'vcn_id' manually"
                            )
                    elif required_prop == 'lifetime':
                        oci_properties['lifetime'] = 'RESERVED'
                    elif required_prop == 'name':
                        oci_properties['name'] = resource_name
                    elif required_prop == 'policy':
                        oci_properties['policy'] = 'ROUND_ROBIN'
                    elif required_prop == 'description':
                        oci_properties['description'] = resource_name
                    elif required_prop == 'matching_rule':
                        oci_properties['matching_rule'] = 'Any {instance.compartment.id = var.compartment_id}'
                    elif required_prop == 'statements':
                        oci_properties['statements'] = ['Allow group Administrators to manage all-resources in tenancy']
                    elif required_prop == 'db_name':
                        oci_properties['db_name'] = properties.get('DBName', resource_name.lower()[:14])
                    elif required_prop == 'admin_password':
                        oci_properties['admin_password'] = 'var.db_admin_password'
                    elif required_prop == 'shape':
                        oci_properties['shape'] = 'flexible'
                    elif required_prop == 'application_id':
                        oci_properties['application_id'] = 'var.function_application_id'
                        if 'function_application_id' not in self.result.variables:
                            self.result.variables['function_application_id'] = {
                                'description': 'OCID of the OCI Functions application',
                                'type': 'string'
                            }
                    elif required_prop == 'image':
                        oci_properties['image'] = 'var.function_image'
                        if 'function_image' not in self.result.variables:
                            self.result.variables['function_image'] = {
                                'description': 'Docker image for the OCI Function (e.g. container-registry.oracle.com/namespace/image:tag)',
                                'type': 'string'
                            }
                    elif required_prop == 'load_balancer_id':
                        oci_properties['load_balancer_id'] = 'var.load_balancer_id'
                        if 'load_balancer_id' not in self.result.variables:
                            self.result.variables['load_balancer_id'] = {
                                'description': 'OCID of the OCI load balancer',
                                'type': 'string'
                            }
                    elif required_prop == 'instance_configuration_id':
                        oci_properties['instance_configuration_id'] = 'var.instance_configuration_id'
                        if 'instance_configuration_id' not in self.result.variables:
                            self.result.variables['instance_configuration_id'] = {
                                'description': 'OCID of the OCI instance configuration',
                                'type': 'string'
                            }
                    elif required_prop == 'memory_in_mbs':
                        oci_properties['memory_in_mbs'] = 128
                    else:
                        self.warn(f"Missing required property '{required_prop}' for {resource_name}")
                        self.result.migration_notes.append(
                            f"⚠ {resource_name}: Set '{required_prop}' manually"
                        )

            # Generate resource code
            tf_name = self._to_snake_case(resource_name)
            resource_code = self.generator.generate_resource(
                oci_type,
                tf_name,
                oci_properties
            )

            resource_groups[oci_type].append(resource_code)

            # Add migration notes if any
            if oci_mapping.get('notes'):
                self.result.migration_notes.append(
                    f"ℹ {resource_name}: {oci_mapping['notes']}"
                )

            self.result.success_count += 1

        # Organize resources by type
        for resource_type, resource_codes in resource_groups.items():
            type_comment = f"# {resource_type} resources"
            all_code = type_comment + "\n\n" + "\n\n".join(resource_codes)
            self.result.resources[resource_type] = all_code
    
    def _translate_properties(self, cfn_properties: Dict[str, Any],
                            oci_mapping: Dict[str, Any],
                            resource_name: str,
                            cfn_type: str,
                            aws_type: str = '') -> Dict[str, Any]:
        """Translate CloudFormation properties to OCI properties."""
        oci_properties = {}
        property_map = oci_mapping.get('properties', {})

        for cfn_prop, cfn_value in cfn_properties.items():
            # CF uses PascalCase (CidrBlock), property_map keys are snake_case (cidr_block)
            aws_prop = self._to_snake_case(cfn_prop)

            # Handle Tags specially: extract Name tag → display_name
            if aws_prop == 'tags':
                display = self._extract_name_tag(cfn_value)
                if display:
                    oci_properties['display_name'] = display
                continue

            if aws_prop not in property_map:
                # Property has no mapping - skip silently
                self.log(f"Skipping unmapped property '{cfn_prop}' for {resource_name}")
                continue

            oci_prop = property_map[aws_prop]

            if oci_prop is None:
                # Explicitly not applicable in OCI
                self.result.migration_notes.append(
                    f"⚠ {resource_name}: Property '{cfn_prop}' not applicable in OCI"
                )
                continue

            translated = self._translate_value(cfn_value)

            # Special: cidr_blocks must be a list in OCI
            if oci_prop == 'cidr_blocks' and isinstance(translated, str):
                translated = [translated]

            # Handle nested properties (e.g., "source_details.source_id")
            if '.' in oci_prop:
                parts = oci_prop.split('.')
                self._set_nested_property(oci_properties, parts, translated)
            else:
                oci_properties[oci_prop] = translated

        # Handle special cases based on the AWS resource type
        if aws_type == 'aws_instance':
            self._enhance_instance_properties(oci_properties, cfn_properties)
        elif aws_type == 'aws_db_instance':
            self._enhance_database_properties(oci_properties, cfn_properties)

        return oci_properties

    def _extract_name_tag(self, tags_value: Any) -> Optional[str]:
        """Extract the Name tag value from CloudFormation Tags list."""
        if isinstance(tags_value, list):
            for tag in tags_value:
                if isinstance(tag, dict):
                    key = tag.get('Key', '')
                    if key == 'Name':
                        val = tag.get('Value', '')
                        return self._translate_value(val)
        return None
    
    def _translate_value(self, cfn_value: Any) -> Any:
        """Translate CloudFormation value (including intrinsic functions) to Terraform."""
        if isinstance(cfn_value, dict):
            # Handle CloudFormation intrinsic functions
            if 'Ref' in cfn_value:
                ref_target = cfn_value['Ref']
                if ref_target.startswith('AWS::'):
                    # Pseudo parameters
                    AWS_PSEUDO_VARS = {
                        'AWS::Region': 'var.region',
                        'AWS::AccountId': 'var.tenancy_ocid',
                        'AWS::StackName': 'var.stack_name',
                        'AWS::StackId': 'var.stack_name',
                        'AWS::URLSuffix': '"oracle.com"',
                        'AWS::Partition': '"oci"',
                        'AWS::NoValue': 'null',
                    }
                    return AWS_PSEUDO_VARS.get(ref_target, 'var.region')
                elif ref_target in self.resource_registry:
                    # It's a resource reference → resolve to OCI resource
                    oci_type, tf_name = self.resource_registry[ref_target]
                    return f'{oci_type}.{tf_name}.id'
                elif ref_target in self.unsupported_logical_names:
                    # References an unsupported/untranslated resource - skip
                    return None
                else:
                    # It's a parameter reference → Terraform variable
                    snake_name = self._to_snake_case(ref_target)
                    return f'var.{snake_name}'

            elif 'Fn::GetAtt' in cfn_value:
                get_att = cfn_value['Fn::GetAtt']
                if isinstance(get_att, list) and len(get_att) >= 2:
                    logical_name = get_att[0]
                    cf_attribute = get_att[1] if len(get_att) == 2 else '.'.join(get_att[1:])
                    if logical_name in self.resource_registry:
                        oci_type, tf_name = self.resource_registry[logical_name]
                        attribute = self._translate_attribute(cf_attribute)
                        if attribute is None:
                            return None  # No OCI equivalent for this attribute
                        return f'{oci_type}.{tf_name}.{attribute}'
                    else:
                        # Resource not translated (unsupported or unknown)
                        return None

            elif 'Fn::Sub' in cfn_value:
                sub_string = cfn_value['Fn::Sub']
                if isinstance(sub_string, str):
                    return self._translate_sub_string(sub_string)
                elif isinstance(sub_string, list):
                    return self._translate_sub_string(sub_string[0])

            elif 'Fn::Join' in cfn_value:
                join_params = cfn_value['Fn::Join']
                if len(join_params) == 2:
                    delimiter = join_params[0]
                    values = join_params[1]
                    translated_values = [self._translate_value(v) for v in values]
                    # Filter out non-string items for join
                    str_values = []
                    for v in translated_values:
                        if isinstance(v, str):
                            if v.startswith('var.') or v.startswith('oci_') or v.startswith('data.'):
                                str_values.append(v)
                            else:
                                str_values.append(f'"{v}"')
                        else:
                            str_values.append(str(v))
                    return f'join("{delimiter}", [{", ".join(str_values)}])'

            elif 'Fn::Select' in cfn_value:
                select_params = cfn_value['Fn::Select']
                if len(select_params) == 2:
                    index = select_params[0]
                    list_val = self._translate_value(select_params[1])
                    return f'element({list_val}, {index})'

            elif 'Fn::GetAZs' in cfn_value:
                return 'data.oci_identity_availability_domains.ads.availability_domains[*].name'

            elif 'Fn::If' in cfn_value:
                # Conditional - use first branch as default
                if_params = cfn_value['Fn::If']
                if len(if_params) >= 2:
                    return self._translate_value(if_params[1])

            # If no intrinsic function matched, recurse
            return {k: self._translate_value(v) for k, v in cfn_value.items()}

        elif isinstance(cfn_value, list):
            return [self._translate_value(v) for v in cfn_value]

        else:
            return cfn_value
    
    # Mapping of AWS pseudo-parameters to Terraform variable references
    AWS_SUB_PSEUDO = {
        'AWS::Region': 'var.region',
        'AWS::AccountId': 'var.tenancy_ocid',
        'AWS::StackName': 'var.stack_name',
        'AWS::StackId': 'var.stack_name',
        'AWS::URLSuffix': 'oracle.com',
        'AWS::Partition': 'oci',
        'AWS::NoValue': '',
    }

    def _translate_sub_string(self, sub_string: str) -> str:
        """Translate CloudFormation !Sub string to Terraform interpolation."""
        pattern = r'\$\{([^}]+)\}'

        def replace_ref(match):
            ref = match.group(1)
            if ref in self.AWS_SUB_PSEUDO:
                val = self.AWS_SUB_PSEUDO[ref]
                return '${' + val + '}' if val else ''
            elif ref.startswith('AWS::'):
                # Unknown AWS pseudo-param - use generic var
                param_name = ref.split('::')[1].lower()
                return '${var.aws_' + param_name + '}'
            elif ref in self.resource_registry:
                oci_type, tf_name = self.resource_registry[ref]
                return '${' + oci_type + '.' + tf_name + '.id}'
            elif ref in self.unsupported_logical_names:
                return ''
            elif '.' in ref:
                # GetAtt-style ${Resource.Attribute} inside Sub string
                parts = ref.split('.', 1)
                logical_name, attr_name = parts[0], parts[1]
                if logical_name in self.resource_registry:
                    oci_type, tf_name = self.resource_registry[logical_name]
                    attribute = self._translate_attribute(attr_name)
                    if attribute:
                        return '${' + oci_type + '.' + tf_name + '.' + attribute + '}'
                return ''
            else:
                snake_ref = self._to_snake_case(ref)
                return f'${{var.{snake_ref}}}'

        return re.sub(pattern, replace_ref, sub_string)
    
    def _translate_attribute(self, cfn_attribute: str) -> Optional[str]:
        """Translate CloudFormation attribute name to OCI attribute.
        Returns None for attributes with no OCI equivalent (output will be skipped)."""
        attr_map = {
            'PrivateIp': 'private_ip',
            'PublicIp': 'public_ip',
            'PrivateDnsName': 'hostname_label',
            'PublicDnsName': 'public_ip',
            'Arn': 'id',
            'Id': 'id',
            'Ref': 'id',
            'AllocationId': 'id',
            'GroupId': 'id',
            'SubnetId': 'id',
            'VpcId': 'id',
            # RDS endpoint - no direct OCI equivalent
            'Endpoint.Address': None,
            'Endpoint.Port': None,
            # DNS names / domain names - no direct OCI equivalent
            'DNSName': 'ip_addresses[0]',
            'DomainName': None,
            'WebsiteURL': None,
            'BucketDomainName': None,
            'BucketRegionalDomainName': None,
        }
        if cfn_attribute in attr_map:
            return attr_map[cfn_attribute]
        # Skip multi-level attributes that aren't explicitly mapped
        if '.' in cfn_attribute:
            return None
        return cfn_attribute.lower()
    
    def _set_nested_property(self, target: Dict, path: List[str], value: Any):
        """Set a nested property in a dictionary."""
        for i, key in enumerate(path[:-1]):
            if key not in target:
                target[key] = {}
            target = target[key]
        target[path[-1]] = value
    
    def _enhance_instance_properties(self, oci_props: Dict, cfn_props: Dict):
        """Enhance OCI instance properties with additional required fields."""
        # Ensure source_details structure
        if 'source_details' not in oci_props:
            oci_props['source_details'] = {}
        if 'source_type' not in oci_props['source_details']:
            oci_props['source_details']['source_type'] = 'image'
        
        # Map instance type if present
        if 'InstanceType' in cfn_props:
            instance_type = cfn_props['InstanceType']
            if isinstance(instance_type, str):
                shape, config = self.mapper.map_instance_type(instance_type)
                oci_props['shape'] = shape
                if 'Flex' in shape:
                    oci_props['shape_config'] = config
        
        # Ensure create_vnic_details structure
        if 'SubnetId' in cfn_props or 'SecurityGroupIds' in cfn_props:
            if 'create_vnic_details' not in oci_props:
                oci_props['create_vnic_details'] = {}
        
        # Handle SSH key
        if 'KeyName' in cfn_props:
            if 'metadata' not in oci_props:
                oci_props['metadata'] = {}
            oci_props['metadata']['ssh_authorized_keys'] = 'var.ssh_public_key'
    
    def _enhance_database_properties(self, oci_props: Dict, cfn_props: Dict):
        """Enhance OCI database properties."""
        # Map database instance class
        if 'DBInstanceClass' in cfn_props:
            db_class = cfn_props['DBInstanceClass']
            if isinstance(db_class, str):
                db_config = self.mapper.DB_INSTANCE_MAP.get(db_class, {'cpu': 2, 'storage_tb': 1})
                oci_props['cpu_core_count'] = db_config['cpu']
                oci_props['data_storage_size_in_tbs'] = db_config['storage_tb']
        
        # Set workload type based on engine
        if 'Engine' in cfn_props:
            engine = cfn_props['Engine']
            if isinstance(engine, str):
                if 'postgres' in engine.lower() or 'mysql' in engine.lower():
                    oci_props['db_workload'] = 'OLTP'
                    self.result.migration_notes.append(
                        f"ℹ Database engine {engine} requires OCI Autonomous Database"
                    )
    
    def _convert_outputs(self, outputs: Dict[str, Dict[str, Any]]):
        """Convert CloudFormation outputs to Terraform outputs."""
        for output_name, output_def in outputs.items():
            output_snake = self._to_snake_case(output_name)

            value = output_def.get('Value', '')
            translated_value = self._translate_value(value)

            # Sanitize output value to ensure valid Terraform HCL
            sanitized = self._sanitize_output_value(translated_value)
            if sanitized is None:
                # Skip outputs that can't be translated
                self.result.migration_notes.append(
                    f"⚠ Output '{output_name}' skipped - cannot translate to OCI"
                )
                continue

            self.result.outputs[output_snake] = {
                'description': output_def.get('Description', f'Converted from {output_name}'),
                'value': sanitized
            }

    def _sanitize_output_value(self, value: Any) -> Optional[str]:
        """Sanitize an output value to ensure it's valid Terraform HCL.
        Returns the value string or None if it should be skipped."""
        if value is None:
            return None
        if isinstance(value, str):
            # Skip values that reference non-existent oci_core_resource placeholder
            if 'oci_core_resource.' in value:
                return None
            # Skip null comments (untranslated GetAtt)
            if value.startswith('null  #'):
                return None
            # Skip AWS-specific URLs
            if '.amazonaws.com' in value or '.aws.amazon.com' in value or 'arn:aws:' in value:
                return None
            # Quote raw URL strings (they're not valid HCL references)
            if value.startswith('http://') or value.startswith('https://'):
                escaped = value.replace('"', '\\"')
                return f'"{escaped}"'
            # Don't quote HCL expressions (references, function calls, literals)
            if any(value.startswith(p) for p in TerraformGenerator.HCL_EXPRESSION_PREFIXES):
                return value
            if value.startswith('"') or value[0:1].isdigit():
                return value
            # Quote plain strings
            escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return f'"{escaped}"'
        elif isinstance(value, bool):
            return 'true' if value else 'false'
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, list):
            # Render as tuple
            items = [self._sanitize_output_value(v) for v in value]
            items = [i for i in items if i is not None]
            return f'[{", ".join(items)}]'
        elif value is None:
            return 'null'
        else:
            return f'"{value}"'
    
    def _cfn_type_to_aws_tf_type(self, cfn_type: str) -> str:
        """Convert CloudFormation type to AWS Terraform type."""
        # Mapping for special cases
        special_mappings = {
            'AWS::EC2::VPC': 'aws_vpc',
            'AWS::EC2::EIP': 'aws_eip',
            'AWS::EC2::VPCGatewayAttachment': 'aws_vpc_gateway_attachment',
            'AWS::EC2::SubnetRouteTableAssociation': 'aws_subnet_route_table_association',
            'AWS::RDS::DBInstance': 'aws_db_instance',
            'AWS::RDS::DBSubnetGroup': 'aws_db_subnet_group',
            'AWS::RDS::DBParameterGroup': 'aws_db_parameter_group',
            'AWS::S3::Bucket': 'aws_s3_bucket',
            'AWS::S3::BucketPolicy': 'aws_s3_bucket_policy',
            'AWS::IAM::Role': 'aws_iam_role',
            'AWS::IAM::Policy': 'aws_iam_policy',
            'AWS::IAM::InstanceProfile': 'aws_iam_instance_profile',
            'AWS::Lambda::Function': 'aws_lambda_function',
            'AWS::ECS::Cluster': 'aws_ecs_cluster',
            'AWS::ECS::Service': 'aws_ecs_service',
            'AWS::ECS::TaskDefinition': 'aws_ecs_task_definition',
            # ECR
            'AWS::ECR::Repository': 'aws_ecr_repository',
            # App Mesh
            'AWS::AppMesh::Mesh': 'aws_appmesh_mesh',
            'AWS::AppMesh::VirtualService': 'aws_appmesh_virtual_service',
            'AWS::AppMesh::VirtualNode': 'aws_appmesh_virtual_node',
            'AWS::AppMesh::VirtualRouter': 'aws_appmesh_virtual_node',
            'AWS::AppMesh::Route': 'aws_appmesh_virtual_node',
            'AWS::AppMesh::VirtualGateway': 'aws_appmesh_virtual_node',
            # Service Discovery / Cloud Map
            'AWS::ServiceDiscovery::PrivateDnsNamespace': 'aws_service_discovery_private_dns_namespace',
            'AWS::ServiceDiscovery::PublicDnsNamespace': 'aws_service_discovery_private_dns_namespace',
            'AWS::ServiceDiscovery::Service': 'aws_service_discovery_service',
            # SQS
            'AWS::SQS::Queue': 'aws_sqs_queue',
            # Secrets Manager
            'AWS::SecretsManager::Secret': 'aws_secretsmanager_secret',
            # CloudWatch
            'AWS::Logs::LogGroup': 'aws_cloudwatch_log_group',
            'AWS::CloudWatch::Alarm': 'aws_cloudwatch_metric_alarm',
            # Application Auto Scaling
            'AWS::ApplicationAutoScaling::ScalableTarget': 'aws_appautoscaling_target',
            'AWS::ApplicationAutoScaling::ScalingPolicy': 'aws_appautoscaling_policy'
        }
        
        if cfn_type in special_mappings:
            return special_mappings[cfn_type]
        
        # General conversion: AWS::EC2::Instance → aws_instance
        if cfn_type.startswith('AWS::'):
            parts = cfn_type.split('::')
            if len(parts) >= 3:
                service = parts[1].lower()
                resource = parts[2]
                # Convert to snake_case properly
                resource_snake = re.sub(r'(?<!^)(?=[A-Z])', '_', resource).lower()
                return f'aws_{resource_snake}'
        return cfn_type.lower()
    
    @staticmethod
    def _to_snake_case(name: str) -> str:
        """Convert PascalCase/camelCase to snake_case."""
        # Insert underscore before uppercase letters
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        # Insert underscore before uppercase letters followed by lowercase
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def write_terraform_files(output_dir: Path, result: TranslationResult):
    """Write Terraform files to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Write provider.tf
    provider_file = output_dir / 'provider.tf'
    with open(provider_file, 'w') as f:
        f.write(result.provider_config)
    print(f"✓ Written: {provider_file}")
    
    # Write variables.tf
    variables_file = output_dir / 'variables.tf'
    with open(variables_file, 'w') as f:
        f.write("# Variables\n\n")
        generator = TerraformGenerator()
        for var_name, var_def in result.variables.items():
            f.write(generator.generate_variable(var_name, var_def))
            f.write("\n\n")
    print(f"✓ Written: {variables_file}")
    
    # Write resource.tf (all resources)
    resource_file = output_dir / 'resource.tf'
    with open(resource_file, 'w') as f:
        f.write("# OCI Resources\n\n")
        for resource_type, resource_code in result.resources.items():
            f.write(resource_code)
            f.write("\n\n")
    print(f"✓ Written: {resource_file}")
    
    # Write outputs.tf
    outputs_file = output_dir / 'outputs.tf'
    with open(outputs_file, 'w') as f:
        f.write("# Outputs\n\n")
        generator = TerraformGenerator()
        for output_name, output_def in result.outputs.items():
            f.write(generator.generate_output(output_name, output_def))
            f.write("\n\n")
    print(f"✓ Written: {outputs_file}")
    
    # Write migration-notes.txt
    notes_file = output_dir / 'migration-notes.txt'
    with open(notes_file, 'w') as f:
        f.write("MIGRATION NOTES\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("MANUAL STEPS REQUIRED:\n")
        f.write("-" * 80 + "\n")
        for note in result.migration_notes:
            f.write(f"{note}\n")
        f.write("\n")
        
        if result.warnings:
            f.write("WARNINGS:\n")
            f.write("-" * 80 + "\n")
            for warning in result.warnings:
                f.write(f"⚠ {warning}\n")
            f.write("\n")
        
        if result.unsupported:
            f.write("UNSUPPORTED RESOURCES:\n")
            f.write("-" * 80 + "\n")
            for item in result.unsupported:
                f.write(f"Resource: {item['resource']}\n")
                f.write(f"  Type: {item['type']}\n")
                f.write(f"  Reason: {item['reason']}\n")
                f.write(f"  Workaround: {item['workaround']}\n\n")
        
        if result.gaps:
            f.write("TRANSLATION GAPS:\n")
            f.write("-" * 80 + "\n")
            for gap in result.gaps:
                f.write(f"[{gap['severity']}] {gap['feature']}\n")
                f.write(f"  Impact: {gap['impact']}\n")
                f.write(f"  Workaround: {gap['workaround']}\n\n")
        
        # Summary
        success_rate = (result.success_count / result.total_count * 100) if result.total_count > 0 else 0
        f.write("TRANSLATION SUMMARY:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total resources: {result.total_count}\n")
        f.write(f"Translated: {result.success_count}\n")
        f.write(f"Success rate: {success_rate:.1f}%\n")
        f.write(f"Unsupported: {len(result.unsupported)}\n")
    
    print(f"✓ Written: {notes_file}")

    # Auto-format all generated .tf files
    try:
        fmt_result = subprocess.run(
            ['terraform', 'fmt', '-write=true', str(output_dir)],
            capture_output=True,
            text=True,
            timeout=30
        )
        if fmt_result.returncode == 0:
            print(f"✓ terraform fmt: formatted successfully")
        else:
            print(f"⚠ terraform fmt: {fmt_result.stderr.strip()[:200]}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # terraform not available, skip


def main():
    parser = argparse.ArgumentParser(
        description='AWS CloudFormation to OCI Terraform Translator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Translate a single CloudFormation template
  %(prog)s samples/01-vpc-multi-az-networking.yaml
  
  # Specify output directory
  %(prog)s samples/01-vpc-multi-az-networking.yaml -o output/vpc-translation
  
  # Verbose mode
  %(prog)s samples/02-rds-postgres-multi-az.yaml -v
        """
    )
    
    parser.add_argument('template', type=Path, help='CloudFormation template file (YAML or JSON)')
    parser.add_argument('-o', '--output', type=Path, help='Output directory (default: output/automated-translations/<template-name>)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Validate input file
    if not args.template.exists():
        print(f"Error: Template file not found: {args.template}", file=sys.stderr)
        sys.exit(1)
    
    # Determine output directory
    if args.output:
        output_dir = args.output
    else:
        template_name = args.template.stem
        output_dir = Path('output/automated-translations') / template_name
    
    print(f"\n{'='*80}")
    print(f"CloudFormation → OCI Terraform Translation")
    print(f"{'='*80}")
    print(f"Input:  {args.template}")
    print(f"Output: {output_dir}")
    print(f"{'='*80}\n")
    
    # Run translation
    translator = CloudFormationTranslator(verbose=args.verbose)
    result = translator.translate_file(args.template)
    
    # Write output files
    write_terraform_files(output_dir, result)
    
    # Print summary
    print(f"\n{'='*80}")
    print("TRANSLATION SUMMARY")
    print(f"{'='*80}")
    success_rate = (result.success_count / result.total_count * 100) if result.total_count > 0 else 0
    print(f"Total resources:    {result.total_count}")
    print(f"Translated:         {result.success_count}")
    print(f"Success rate:       {success_rate:.1f}%")
    print(f"Unsupported:        {len(result.unsupported)}")
    print(f"Warnings:           {len(result.warnings)}")
    print(f"Migration notes:    {len(result.migration_notes)}")
    print(f"{'='*80}\n")
    
    if result.unsupported:
        print("⚠ Unsupported resources:")
        for item in result.unsupported:
            print(f"  - {item['resource']} ({item['type']})")
        print()
    
    print(f"✓ Translation complete! Review {output_dir}/migration-notes.txt for manual steps.\n")


if __name__ == '__main__':
    main()
