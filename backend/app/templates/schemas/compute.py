"""
Pydantic v2 schemas for OCI Compute and Storage resources.

Maps to ``oci_core_instance``, ``oci_core_instance_configuration``,
``oci_core_instance_pool``, ``oci_autoscaling_auto_scaling_configuration``,
``oci_core_boot_volume``, ``oci_core_volume``, and
``oci_core_volume_attachment`` Terraform resources.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Shared defaults
# ---------------------------------------------------------------------------
def _default_tags() -> dict[str, str]:
    return {"managed_by": "oci-iaas-migration", "aws_source_id": "PLACEHOLDER"}


# ---------------------------------------------------------------------------
# Sub-models: Instance
# ---------------------------------------------------------------------------

class ShapeConfig(BaseModel):
    """Flex shape OCPU / memory configuration for compute instances."""
    model_config = ConfigDict(populate_by_name=True)

    ocpus: Annotated[float, Field(gt=0, description="Number of OCPUs")]
    memory_in_gbs: Annotated[float, Field(gt=0, description="Memory in GBs")]


class SourceDetails(BaseModel):
    """Boot source for a compute instance (image or boot volume)."""
    model_config = ConfigDict(populate_by_name=True)

    source_type: Annotated[
        Literal["image", "bootVolume"],
        Field(description="Source type: 'image' or 'bootVolume'"),
    ]
    source_id: Annotated[
        str, Field(description="OCID of the image or boot volume")
    ]
    boot_volume_size_in_gbs: Annotated[
        Optional[int],
        Field(default=None, ge=50, description="Boot volume size in GBs (min 50)"),
    ]


class CreateVnicDetails(BaseModel):
    """VNIC configuration attached to a compute instance at launch."""
    model_config = ConfigDict(populate_by_name=True)

    subnet_id: Annotated[str, Field(description="Terraform reference to the subnet")]
    assign_public_ip: Annotated[
        Optional[bool],
        Field(default=None, description="Whether to assign a public IP"),
    ]
    nsg_ids: Annotated[
        Optional[list[str]],
        Field(default=None, description="Terraform references to NSGs"),
    ]
    display_name: Annotated[
        Optional[str],
        Field(default=None, description="Display name for the VNIC"),
    ]


# ---------------------------------------------------------------------------
# Sub-models: Instance Configuration / Pool
# ---------------------------------------------------------------------------

class LaunchDetails(BaseModel):
    """Launch configuration embedded in an instance configuration."""
    model_config = ConfigDict(populate_by_name=True)

    shape: Annotated[str, Field(description="Compute shape (e.g. 'VM.Standard.E5.Flex')")]
    shape_config: Annotated[
        Optional[ShapeConfig],
        Field(default=None, description="Flex shape OCPU / memory config"),
    ]
    source_details: Annotated[
        Optional[SourceDetails],
        Field(default=None, description="Boot source details"),
    ]
    create_vnic_details: Annotated[
        Optional[CreateVnicDetails],
        Field(default=None, description="Primary VNIC details"),
    ]
    metadata: Annotated[
        Optional[dict[str, str]],
        Field(default=None, description="Instance metadata (e.g. ssh_authorized_keys)"),
    ]


class InstanceConfigDetails(BaseModel):
    """Instance details block inside an instance configuration."""
    model_config = ConfigDict(populate_by_name=True)

    instance_type: Annotated[
        str, Field(default="compute", description="Instance type (typically 'compute')")
    ]
    launch_details: Annotated[
        LaunchDetails, Field(description="Launch configuration for instances")
    ]


class PlacementConfig(BaseModel):
    """Placement configuration for an instance pool."""
    model_config = ConfigDict(populate_by_name=True)

    availability_domain: Annotated[
        str, Field(description="Availability domain name")
    ]
    primary_subnet_id: Annotated[
        str, Field(description="Terraform reference to the primary subnet")
    ]


# ---------------------------------------------------------------------------
# Sub-models: Auto Scaling
# ---------------------------------------------------------------------------

class AutoScalingResource(BaseModel):
    """Resource target for an auto-scaling configuration."""
    model_config = ConfigDict(populate_by_name=True)

    id: Annotated[
        str, Field(description="Terraform reference to the instance pool")
    ]
    type: Annotated[
        Literal["instancePool"],
        Field(description="Resource type (must be 'instancePool')"),
    ]


class ScalingCapacity(BaseModel):
    """Capacity limits for a scaling policy."""
    model_config = ConfigDict(populate_by_name=True)

    max: Annotated[int, Field(ge=0, description="Maximum instance count")]
    min: Annotated[int, Field(ge=0, description="Minimum instance count")]
    initial: Annotated[int, Field(ge=0, description="Initial (desired) instance count")]


class ScalingRule(BaseModel):
    """A single threshold-based scaling rule."""
    model_config = ConfigDict(populate_by_name=True)

    display_name: Annotated[str, Field(description="Rule display name")]
    action: Annotated[
        Optional[dict[str, object]],
        Field(default=None, description="Action block (type, value)"),
    ]
    metric: Annotated[
        Optional[dict[str, object]],
        Field(default=None, description="Metric block (metric_type, threshold)"),
    ]


class ScalingPolicy(BaseModel):
    """A scaling policy with capacity and threshold rules."""
    model_config = ConfigDict(populate_by_name=True)

    display_name: Annotated[str, Field(description="Policy display name")]
    policy_type: Annotated[
        str, Field(default="threshold", description="Policy type (e.g. 'threshold')")
    ]
    capacity: Annotated[
        ScalingCapacity, Field(description="Capacity limits")
    ]
    rules: Annotated[
        list[ScalingRule], Field(min_length=1, description="Scaling rules")
    ]


# ---------------------------------------------------------------------------
# Sub-models: Boot Volume
# ---------------------------------------------------------------------------

class BootVolumeSourceDetails(BaseModel):
    """Source details for creating a boot volume from another source."""
    model_config = ConfigDict(populate_by_name=True)

    id: Annotated[str, Field(description="OCID of the source boot volume or backup")]
    type: Annotated[
        str, Field(description="Source type (e.g. 'bootVolume', 'bootVolumeBackup')")
    ]


# ===================================================================
# Top-level resource schemas (7 models)
# ===================================================================

class InstanceParams(BaseModel):
    """Parameters for ``oci_core_instance``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
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
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    availability_domain: Annotated[str, Field(description="Availability domain name")]
    display_name: Annotated[str, Field(description="Display name for the instance")]
    shape: Annotated[str, Field(description="Compute shape (e.g. 'VM.Standard.E5.Flex')")]
    shape_config: Annotated[
        Optional[ShapeConfig],
        Field(default=None, description="Flex shape OCPU / memory config (required for Flex shapes)"),
    ]
    source_details: Annotated[
        SourceDetails, Field(description="Boot source (image or boot volume)")
    ]
    create_vnic_details: Annotated[
        Optional[CreateVnicDetails],
        Field(default=None, description="Primary VNIC details"),
    ]
    metadata: Annotated[
        Optional[dict[str, str]],
        Field(default=None, description="Instance metadata (e.g. ssh_authorized_keys)"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS EC2 instance ID for traceability")]


class InstanceConfigurationParams(BaseModel):
    """Parameters for ``oci_core_instance_configuration``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
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
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name for the instance configuration")]
    instance_details: Annotated[
        InstanceConfigDetails,
        Field(description="Instance details with launch configuration"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Launch Template / Launch Configuration ID")]


class InstancePoolParams(BaseModel):
    """Parameters for ``oci_core_instance_pool``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
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
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name for the instance pool")]
    instance_configuration_id: Annotated[
        str, Field(description="Terraform reference to the instance configuration")
    ]
    size: Annotated[int, Field(ge=0, description="Desired number of instances in the pool")]
    placement_configurations: Annotated[
        list[PlacementConfig],
        Field(min_length=1, description="Placement configurations per AD"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Auto Scaling Group ID")]


class AutoScalingConfigurationParams(BaseModel):
    """Parameters for ``oci_autoscaling_auto_scaling_configuration``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
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
                    "aws_source_id": "asg-0abc123def456",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    display_name: Annotated[str, Field(description="Display name")]
    auto_scaling_resources: Annotated[
        AutoScalingResource,
        Field(description="Target resource for auto scaling (instance pool)"),
    ]
    cool_down_in_seconds: Annotated[
        Optional[int],
        Field(default=300, ge=0, description="Cool-down period between scaling actions in seconds"),
    ]
    is_enabled: Annotated[
        Optional[bool],
        Field(default=True, description="Whether the auto-scaling configuration is enabled"),
    ]
    policies: Annotated[
        list[ScalingPolicy],
        Field(min_length=1, description="Scaling policies"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS Auto Scaling Group or Policy ARN")]


class BootVolumeParams(BaseModel):
    """Parameters for ``oci_core_boot_volume``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "availability_domain": "Uocm:US-ASHBURN-AD-1",
                    "display_name": "bv-web-server-1",
                    "size_in_gbs": 100,
                    "vpus_per_gb": 10,
                    "aws_source_id": "vol-0abc123def456",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    availability_domain: Annotated[str, Field(description="Availability domain name")]
    display_name: Annotated[str, Field(description="Display name for the boot volume")]
    size_in_gbs: Annotated[
        int, Field(default=50, ge=50, description="Boot volume size in GBs (min 50)")
    ]
    vpus_per_gb: Annotated[
        Optional[int],
        Field(default=10, ge=0, description="Volume performance units per GB (0=Lower Cost, 10=Balanced, 20=Higher Perf)"),
    ]
    source_details: Annotated[
        Optional[BootVolumeSourceDetails],
        Field(default=None, description="Source for cloning from another boot volume or backup"),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS EBS volume ID (root device)")]


class BlockVolumeParams(BaseModel):
    """Parameters for ``oci_core_volume``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "compartment_id": "var.compartment_id",
                    "availability_domain": "Uocm:US-ASHBURN-AD-1",
                    "display_name": "data-vol-1",
                    "size_in_gbs": 200,
                    "vpus_per_gb": 20,
                    "aws_source_id": "vol-0abc123def456",
                }
            ]
        }
    )

    compartment_id: Annotated[str, Field(description="OCI compartment OCID or TF variable reference")]
    availability_domain: Annotated[str, Field(description="Availability domain name")]
    display_name: Annotated[str, Field(description="Display name for the block volume")]
    size_in_gbs: Annotated[
        int, Field(ge=50, description="Volume size in GBs (min 50)")
    ]
    vpus_per_gb: Annotated[
        Optional[int],
        Field(
            default=10, ge=0,
            description="Volume performance units per GB "
                        "(0=Lower Cost, 10=Balanced, 20=Higher Perf, 30+=Ultra High Perf)",
        ),
    ]
    freeform_tags: Annotated[
        Optional[dict[str, str]],
        Field(default_factory=_default_tags, description="OCI freeform tags"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS EBS volume ID")]


class BlockVolumeAttachmentParams(BaseModel):
    """Parameters for ``oci_core_volume_attachment``."""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "instance_id": "oci_core_instance.web.id",
                    "volume_id": "oci_core_volume.data.id",
                    "attachment_type": "paravirtualized",
                    "display_name": "data-attach",
                    "is_read_only": False,
                    "is_shareable": False,
                    "device": "/dev/oracleoci/oraclevdb",
                    "aws_source_id": "vol-attach-0abc123",
                }
            ]
        }
    )

    instance_id: Annotated[
        str, Field(description="Terraform reference to the compute instance")
    ]
    volume_id: Annotated[
        str, Field(description="Terraform reference to the block volume")
    ]
    attachment_type: Annotated[
        Literal["paravirtualized", "iscsi"],
        Field(default="paravirtualized", description="Attachment type"),
    ]
    display_name: Annotated[
        Optional[str],
        Field(default=None, description="Display name for the attachment"),
    ]
    is_read_only: Annotated[
        Optional[bool],
        Field(default=False, description="Whether the volume is attached read-only"),
    ]
    is_shareable: Annotated[
        Optional[bool],
        Field(default=False, description="Whether the volume can be shared across instances"),
    ]
    device: Annotated[
        Optional[str],
        Field(default=None, description="Device path (e.g. '/dev/oracleoci/oraclevdb')"),
    ]
    aws_source_id: Annotated[str, Field(description="AWS volume attachment identifier")]
