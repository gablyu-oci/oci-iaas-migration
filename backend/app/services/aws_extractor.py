"""AWS resource extraction helpers using boto3."""

import json
from typing import Any

import boto3
from botocore.exceptions import ClientError, BotoCoreError


def _build_session(credentials: dict, region: str) -> boto3.Session:
    """Build a boto3 Session from a credentials dict."""
    return boto3.Session(
        aws_access_key_id=credentials.get("aws_access_key_id"),
        aws_secret_access_key=credentials.get("aws_secret_access_key"),
        aws_session_token=credentials.get("aws_session_token"),
        region_name=region,
    )


def validate_credentials(credentials: dict, region: str) -> dict:
    """
    Validate AWS credentials using sts.get_caller_identity.

    Returns:
        dict with keys: valid (bool), account_id, arn, error (if any)
    """
    try:
        session = _build_session(credentials, region)
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        return {
            "valid": True,
            "account_id": identity["Account"],
            "arn": identity["Arn"],
            "error": None,
        }
    except (ClientError, BotoCoreError) as e:
        return {
            "valid": False,
            "account_id": None,
            "arn": None,
            "error": str(e),
        }


def extract_cfn_stacks(credentials: dict, region: str) -> list[dict[str, Any]]:
    """
    Extract CloudFormation stacks and their templates.

    Returns a list of dicts, each with:
        stack_name, stack_id, status, template (str)
    """
    session = _build_session(credentials, region)
    cfn = session.client("cloudformation")

    results = []
    paginator = cfn.get_paginator("list_stacks")
    active_statuses = [
        "CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE",
        "ROLLBACK_COMPLETE", "IMPORT_COMPLETE",
    ]

    for page in paginator.paginate(StackStatusFilter=active_statuses):
        for summary in page.get("StackSummaries", []):
            stack_name = summary["StackName"]
            try:
                tmpl_resp = cfn.get_template(StackName=stack_name, TemplateStage="Processed")
                template_body = tmpl_resp.get("TemplateBody", "")
                # TemplateBody can be a dict (JSON) or a string (YAML)
                if isinstance(template_body, dict):
                    template_body = json.dumps(template_body, indent=2)
            except ClientError:
                template_body = ""

            results.append({
                "stack_name": stack_name,
                "stack_id": summary.get("StackId", ""),
                "status": summary.get("StackStatus", ""),
                "template": template_body,
            })

    return results


def extract_cfn_stack_resources(credentials: dict, region: str) -> dict[str, str]:
    """Build a map of physical resource ARN/ID → CFN stack name.

    For every active CFN stack, lists its managed resources so that downstream
    discovery can tag individual resources (EC2, VPC, RDS, etc.) as CFN-managed
    and avoid translating them twice.

    Returns: { physical_resource_id_or_arn: stack_name }
    """
    session = _build_session(credentials, region)
    cfn = session.client("cloudformation")

    membership: dict[str, str] = {}
    active_statuses = [
        "CREATE_COMPLETE", "UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE",
        "ROLLBACK_COMPLETE", "IMPORT_COMPLETE",
    ]

    try:
        paginator = cfn.get_paginator("list_stacks")
        for page in paginator.paginate(StackStatusFilter=active_statuses):
            for summary in page.get("StackSummaries", []):
                stack_name = summary["StackName"]
                try:
                    res_paginator = cfn.get_paginator("list_stack_resources")
                    for res_page in res_paginator.paginate(StackName=stack_name):
                        for res in res_page.get("StackResourceSummaries", []):
                            phys_id = res.get("PhysicalResourceId", "")
                            if phys_id:
                                membership[phys_id] = stack_name
                except ClientError:
                    pass
    except ClientError:
        pass

    return membership


def extract_iam_policies(credentials: dict, region: str) -> list[dict[str, Any]]:
    """
    Extract customer-managed IAM policies and their latest version document.

    Returns a list of dicts, each with:
        policy_name, policy_arn, policy_document (dict)
    """
    session = _build_session(credentials, region)
    iam = session.client("iam")

    results = []
    paginator = iam.get_paginator("list_policies")

    for page in paginator.paginate(Scope="Local"):
        for policy in page.get("Policies", []):
            policy_arn = policy["Arn"]
            default_version = policy.get("DefaultVersionId", "v1")

            try:
                ver_resp = iam.get_policy_version(
                    PolicyArn=policy_arn,
                    VersionId=default_version,
                )
                doc = ver_resp["PolicyVersion"]["Document"]
                # The document may already be a dict or a URL-encoded JSON string
                if isinstance(doc, str):
                    import urllib.parse
                    doc = json.loads(urllib.parse.unquote(doc))
            except (ClientError, json.JSONDecodeError):
                doc = {}

            results.append({
                "policy_name": policy["PolicyName"],
                "policy_arn": policy_arn,
                "policy_document": doc,
            })

    return results


# ---------------------------------------------------------------------------
# Extended extraction helpers (instance-centric discovery)
# ---------------------------------------------------------------------------
# These functions discover resources connected to a specific EC2 instance.
# They are stubs that return empty lists until full boto3 logic is wired up.


def extract_ec2_instances(
    credentials: dict, region: str, instance_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract EC2 instance details. If *instance_id* is given, return only
    that instance; otherwise return all instances in the region.

    Each dict contains everything we can pull from DescribeInstances in a
    single call: identity, type, sizing, networking, OS/arch, root device,
    all block-device mappings, IAM profile, tags. vCPU + memory are not in
    DescribeInstances — they're looked up from ``instance_shapes.yaml``
    downstream (see ``enrich_resource_detail``) so we don't pay the
    ``DescribeInstanceTypes`` call per resource.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        instance_ids: list[str] = []
        if instance_id:
            instance_ids = [instance_id]

        kwargs: dict[str, Any] = {}
        if instance_ids:
            kwargs["InstanceIds"] = instance_ids
        else:
            # Exclude terminated instances from bulk discovery
            kwargs["Filters"] = [
                {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}
            ]

        results: list[dict[str, Any]] = []
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate(**kwargs):
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    name = ""
                    for tag in inst.get("Tags", []):
                        if tag["Key"] == "Name":
                            name = tag["Value"]
                            break
                    sg_ids = [sg["GroupId"] for sg in inst.get("SecurityGroups", [])]
                    profile = inst.get("IamInstanceProfile", {})
                    placement = inst.get("Placement", {}) or {}
                    monitoring = inst.get("Monitoring", {}) or {}
                    # Block-device mappings: volume id + device name + delete-on-term
                    bdms = [
                        {
                            "device_name": b.get("DeviceName", ""),
                            "volume_id": (b.get("Ebs") or {}).get("VolumeId", ""),
                            "status": (b.get("Ebs") or {}).get("Status", ""),
                            "delete_on_termination": (b.get("Ebs") or {}).get("DeleteOnTermination", False),
                            "attach_time": (
                                (b.get("Ebs") or {}).get("AttachTime").isoformat()
                                if (b.get("Ebs") or {}).get("AttachTime") else ""
                            ),
                        }
                        for b in inst.get("BlockDeviceMappings", [])
                    ]
                    launch_time = inst.get("LaunchTime")
                    results.append({
                        # Identity
                        "instance_id": inst["InstanceId"],
                        "name": name,
                        "arn": f"arn:aws:ec2:{region}::instance/{inst['InstanceId']}",
                        # Type + state
                        "instance_type": inst.get("InstanceType", ""),
                        "state": inst.get("State", {}).get("Name", ""),
                        "state_reason": (inst.get("StateReason") or {}).get("Message", ""),
                        "launch_time": launch_time.isoformat() if launch_time else "",
                        # OS / arch
                        "architecture": inst.get("Architecture", ""),
                        "platform": inst.get("Platform", "") or "linux",  # AWS returns "windows" or absent
                        "platform_details": inst.get("PlatformDetails", ""),
                        "hypervisor": inst.get("Hypervisor", ""),
                        "virtualization_type": inst.get("VirtualizationType", ""),
                        "image_id": inst.get("ImageId", ""),
                        "key_name": inst.get("KeyName", ""),
                        # Networking
                        "vpc_id": inst.get("VpcId", ""),
                        "subnet_id": inst.get("SubnetId", ""),
                        "security_groups": sg_ids,
                        "private_ip_address": inst.get("PrivateIpAddress", ""),
                        "public_ip_address": inst.get("PublicIpAddress", ""),
                        "private_dns_name": inst.get("PrivateDnsName", ""),
                        "public_dns_name": inst.get("PublicDnsName", ""),
                        # Placement
                        "availability_zone": placement.get("AvailabilityZone", ""),
                        "tenancy": placement.get("Tenancy", ""),
                        # Storage
                        "root_device_type": inst.get("RootDeviceType", ""),
                        "root_device_name": inst.get("RootDeviceName", ""),
                        "block_device_mappings": bdms,
                        "ebs_optimized": inst.get("EbsOptimized", False),
                        # Monitoring / IAM
                        "monitoring_state": monitoring.get("State", ""),
                        "iam_instance_profile_arn": profile.get("Arn", ""),
                        "Tags": inst.get("Tags", []),
                    })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"EC2 extraction error: {e}")
        return []


def extract_vpcs(
    credentials: dict, region: str, vpc_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract VPC details. If *vpc_id* is given, return only that VPC.

    Each dict contains: vpc_id, cidr_block, name, arn, subnets (list).
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        kwargs: dict[str, Any] = {}
        if vpc_id:
            kwargs["VpcIds"] = [vpc_id]

        vpcs_resp = ec2.describe_vpcs(**kwargs)
        results: list[dict[str, Any]] = []
        for vpc in vpcs_resp.get("Vpcs", []):
            name = ""
            for tag in vpc.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break

            # Fetch subnets for this VPC
            sub_resp = ec2.describe_subnets(
                Filters=[{"Name": "vpc-id", "Values": [vpc["VpcId"]]}]
            )
            subnets = [
                {
                    "subnet_id": s["SubnetId"],
                    "cidr_block": s.get("CidrBlock", ""),
                    "availability_zone": s.get("AvailabilityZone", ""),
                }
                for s in sub_resp.get("Subnets", [])
            ]

            results.append({
                "vpc_id": vpc["VpcId"],
                "cidr_block": vpc.get("CidrBlock", ""),
                "name": name,
                "arn": f"arn:aws:ec2:{region}::vpc/{vpc['VpcId']}",
                "subnets": subnets,
                "Tags": vpc.get("Tags", []),
            })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"VPC extraction error: {e}")
        return []


def extract_security_groups(
    credentials: dict, region: str, group_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Extract security group details.

    Each dict contains: group_id, group_name, vpc_id, description,
    ingress_rules, egress_rules, arn.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        kwargs: dict[str, Any] = {}
        if group_ids:
            kwargs["GroupIds"] = group_ids

        sg_resp = ec2.describe_security_groups(**kwargs)
        results: list[dict[str, Any]] = []
        for sg in sg_resp.get("SecurityGroups", []):
            results.append({
                "group_id": sg["GroupId"],
                "group_name": sg.get("GroupName", ""),
                "vpc_id": sg.get("VpcId", ""),
                "description": sg.get("Description", ""),
                "ingress_rules": sg.get("IpPermissions", []),
                "egress_rules": sg.get("IpPermissionsEgress", []),
                "arn": f"arn:aws:ec2:{region}::security-group/{sg['GroupId']}",
                "Tags": sg.get("Tags", []),
            })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Security group extraction error: {e}")
        return []


def extract_iam_policies_for_instance_profile(
    credentials: dict, profile_arn: str
) -> list[dict[str, Any]]:
    """Given an IAM instance profile ARN, return all IAM policy documents attached
    to the profile's role (both managed and inline).

    Each dict contains: policy_arn, policy_name, policy_document.
    """
    if not profile_arn:
        return []
    try:
        session = _build_session(credentials, "us-east-1")  # IAM is global
        iam = session.client("iam")

        # Profile ARN format: arn:aws:iam::ACCOUNT:instance-profile/NAME
        profile_name = profile_arn.split("/")[-1]
        profile = iam.get_instance_profile(InstanceProfileName=profile_name)
        roles = profile.get("InstanceProfile", {}).get("Roles", [])
        if not roles:
            return []
        role_name = roles[0]["RoleName"]

        results: list[dict[str, Any]] = []

        # Managed policies attached to the role
        paginator = iam.get_paginator("list_attached_role_policies")
        for page in paginator.paginate(RoleName=role_name):
            for pol in page.get("AttachedPolicies", []):
                arn = pol["PolicyArn"]
                name = pol["PolicyName"]
                try:
                    pol_detail = iam.get_policy(PolicyArn=arn)
                    version_id = pol_detail["Policy"]["DefaultVersionId"]
                    version = iam.get_policy_version(PolicyArn=arn, VersionId=version_id)
                    doc = version["PolicyVersion"]["Document"]
                except Exception:
                    doc = {}
                results.append({"policy_arn": arn, "policy_name": name, "policy_document": doc})

        # Inline policies on the role
        inline_paginator = iam.get_paginator("list_role_policies")
        for page in inline_paginator.paginate(RoleName=role_name):
            for policy_name in page.get("PolicyNames", []):
                try:
                    inline = iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)
                    doc = inline.get("PolicyDocument", {})
                except Exception:
                    doc = {}
                results.append({
                    "policy_arn": f"arn:aws:iam::inline:{role_name}/{policy_name}",
                    "policy_name": policy_name,
                    "policy_document": doc,
                })

        return results
    except (ClientError, BotoCoreError) as e:
        print(f"IAM role policy extraction error: {e}")
        return []


def extract_rds_instances(
    credentials: dict, region: str, vpc_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract RDS instances with full sizing + HA + security detail.

    Optionally filtered to those in *vpc_id*. The raw_config carries
    everything downstream consumers (UI, TCO, rightsizing) need:
    instance class, engine + version, storage (size/type/IOPS/throughput),
    multi-AZ, endpoint, backups, encryption, public accessibility.
    """
    try:
        session = _build_session(credentials, region)
        rds = session.client("rds")

        results: list[dict[str, Any]] = []
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db_inst in page.get("DBInstances", []):
                sub_group = db_inst.get("DBSubnetGroup", {}) or {}
                inst_vpc = sub_group.get("VpcId", "")
                if vpc_id and inst_vpc != vpc_id:
                    continue
                endpoint = db_inst.get("Endpoint", {}) or {}
                sg_ids = [
                    sg.get("VpcSecurityGroupId", "")
                    for sg in db_inst.get("VpcSecurityGroups", [])
                ]
                created = db_inst.get("InstanceCreateTime")
                results.append({
                    # Identity
                    "db_instance_id": db_inst["DBInstanceIdentifier"],
                    "arn": db_inst.get("DBInstanceArn", ""),
                    "status": db_inst.get("DBInstanceStatus", ""),
                    "created_at": created.isoformat() if created else "",
                    # Engine
                    "engine": db_inst.get("Engine", ""),
                    "engine_version": db_inst.get("EngineVersion", ""),
                    "license_model": db_inst.get("LicenseModel", ""),
                    # Compute + sizing
                    "db_instance_class": db_inst.get("DBInstanceClass", ""),
                    "availability_zone": db_inst.get("AvailabilityZone", ""),
                    "secondary_availability_zone": db_inst.get("SecondaryAvailabilityZone", ""),
                    "multi_az": db_inst.get("MultiAZ", False),
                    # Storage
                    "allocated_storage_gb": db_inst.get("AllocatedStorage", 0),
                    "max_allocated_storage_gb": db_inst.get("MaxAllocatedStorage", 0),
                    "storage_type": db_inst.get("StorageType", ""),
                    "iops": db_inst.get("Iops", 0),
                    "storage_throughput_mbps": db_inst.get("StorageThroughput", 0),
                    "storage_encrypted": db_inst.get("StorageEncrypted", False),
                    "kms_key_id": db_inst.get("KmsKeyId", ""),
                    # Networking
                    "vpc_id": inst_vpc,
                    "db_subnet_group_name": sub_group.get("DBSubnetGroupName", ""),
                    "vpc_security_group_ids": sg_ids,
                    "publicly_accessible": db_inst.get("PubliclyAccessible", False),
                    "endpoint_address": endpoint.get("Address", ""),
                    "endpoint_port": endpoint.get("Port", 0),
                    # Backup / HA
                    "backup_retention_period_days": db_inst.get("BackupRetentionPeriod", 0),
                    "preferred_backup_window": db_inst.get("PreferredBackupWindow", ""),
                    "preferred_maintenance_window": db_inst.get("PreferredMaintenanceWindow", ""),
                    "auto_minor_version_upgrade": db_inst.get("AutoMinorVersionUpgrade", False),
                    "deletion_protection": db_inst.get("DeletionProtection", False),
                    "performance_insights_enabled": db_inst.get("PerformanceInsightsEnabled", False),
                    "read_replica_source": db_inst.get("ReadReplicaSourceDBInstanceIdentifier", ""),
                    "read_replica_db_instance_identifiers": db_inst.get("ReadReplicaDBInstanceIdentifiers", []),
                    # Identity
                    "master_username": db_inst.get("MasterUsername", ""),
                    "db_name": db_inst.get("DBName", ""),
                    "Tags": db_inst.get("TagList", []),
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"RDS extraction error: {e}")
        return []


def extract_load_balancers(
    credentials: dict, region: str, vpc_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract ELBv2 load balancers, optionally filtered by *vpc_id*.

    Each dict contains: name, dns_name, type, vpc_id, arn.
    """
    try:
        session = _build_session(credentials, region)
        elbv2 = session.client("elbv2")

        results: list[dict[str, Any]] = []
        paginator = elbv2.get_paginator("describe_load_balancers")
        for page in paginator.paginate():
            for lb in page.get("LoadBalancers", []):
                lb_vpc = lb.get("VpcId", "")
                if vpc_id and lb_vpc != vpc_id:
                    continue
                # Fetch tags for this LB
                lb_tags: list[dict] = []
                try:
                    tag_resp = elbv2.describe_tags(ResourceArns=[lb["LoadBalancerArn"]])
                    for td in tag_resp.get("TagDescriptions", []):
                        lb_tags = td.get("Tags", [])
                except (ClientError, BotoCoreError):
                    pass
                results.append({
                    "name": lb.get("LoadBalancerName", ""),
                    "dns_name": lb.get("DNSName", ""),
                    "type": lb.get("Type", ""),
                    "vpc_id": lb_vpc,
                    "arn": lb.get("LoadBalancerArn", ""),
                    "Tags": lb_tags,
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"ELB extraction error: {e}")
        return []


def extract_auto_scaling_groups(
    credentials: dict, region: str, instance_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract Auto Scaling groups. If *instance_id* is given, return only
    groups that contain that instance.

    Each dict contains: asg_name, min_size, max_size, desired_capacity,
    instance_ids, arn.
    """
    try:
        session = _build_session(credentials, region)
        asg_client = session.client("autoscaling")

        results: list[dict[str, Any]] = []
        paginator = asg_client.get_paginator("describe_auto_scaling_groups")
        for page in paginator.paginate():
            for asg in page.get("AutoScalingGroups", []):
                ids = [i["InstanceId"] for i in asg.get("Instances", [])]
                if instance_id and instance_id not in ids:
                    continue
                tags = [
                    {"Key": t.get("Key", ""), "Value": t.get("Value", "")}
                    for t in asg.get("Tags", [])
                ]
                results.append({
                    "asg_name": asg["AutoScalingGroupName"],
                    "min_size": asg.get("MinSize", 0),
                    "max_size": asg.get("MaxSize", 0),
                    "desired_capacity": asg.get("DesiredCapacity", 0),
                    "instance_ids": ids,
                    "arn": asg.get("AutoScalingGroupARN", ""),
                    "Tags": tags,
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"ASG extraction error: {e}")
        return []


def extract_ebs_volumes(
    credentials: dict, region: str, instance_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract EBS volumes. If *instance_id* is given, return only volumes
    attached to that instance.

    Each dict contains: volume_id, size_gb, volume_type, state, encrypted,
    availability_zone, attachments (list), arn.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        kwargs: dict[str, Any] = {}
        if instance_id:
            kwargs["Filters"] = [{"Name": "attachment.instance-id", "Values": [instance_id]}]

        results: list[dict[str, Any]] = []
        paginator = ec2.get_paginator("describe_volumes")
        for page in paginator.paginate(**kwargs):
            for vol in page.get("Volumes", []):
                attachments = [
                    {
                        "instance_id": a.get("InstanceId", ""),
                        "device": a.get("Device", ""),
                        "state": a.get("State", ""),
                        "delete_on_termination": a.get("DeleteOnTermination", False),
                    }
                    for a in vol.get("Attachments", [])
                ]
                # Get name tag
                name = ""
                for tag in vol.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break
                account_id = vol.get("OwnerId", "")
                created = vol.get("CreateTime")
                results.append({
                    "volume_id": vol["VolumeId"],
                    "name": name,
                    "size_gb": vol.get("Size", 0),
                    "volume_type": vol.get("VolumeType", ""),
                    "iops": vol.get("Iops", 0),
                    "throughput_mbps": vol.get("Throughput", 0),
                    "state": vol.get("State", ""),
                    "encrypted": vol.get("Encrypted", False),
                    "kms_key_id": vol.get("KmsKeyId", ""),
                    "availability_zone": vol.get("AvailabilityZone", ""),
                    "multi_attach_enabled": vol.get("MultiAttachEnabled", False),
                    "create_time": created.isoformat() if created else "",
                    "attachments": attachments,
                    "arn": f"arn:aws:ec2:{region}:{account_id}:volume/{vol['VolumeId']}",
                    "Tags": vol.get("Tags", []),
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"EBS volume extraction error: {e}")
        return []


def extract_network_interfaces(
    credentials: dict, region: str, instance_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract Elastic Network Interfaces (ENIs). If *instance_id* is given,
    return only interfaces attached to that instance.

    Each dict contains: interface_id, subnet_id, vpc_id, private_ip,
    public_ip, mac_address, status, arn.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        kwargs: dict[str, Any] = {}
        if instance_id:
            kwargs["Filters"] = [{"Name": "attachment.instance-id", "Values": [instance_id]}]

        results: list[dict[str, Any]] = []
        paginator = ec2.get_paginator("describe_network_interfaces")
        for page in paginator.paginate(**kwargs):
            for eni in page.get("NetworkInterfaces", []):
                account_id = eni.get("OwnerId", "")
                results.append({
                    "interface_id": eni["NetworkInterfaceId"],
                    "subnet_id": eni.get("SubnetId", ""),
                    "vpc_id": eni.get("VpcId", ""),
                    "private_ip": eni.get("PrivateIpAddress", ""),
                    "public_ip": eni.get("Association", {}).get("PublicIp", ""),
                    "mac_address": eni.get("MacAddress", ""),
                    "status": eni.get("Status", ""),
                    "description": eni.get("Description", ""),
                    "arn": f"arn:aws:ec2:{region}:{account_id}:network-interface/{eni['NetworkInterfaceId']}",
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"ENI extraction error: {e}")
        return []


def extract_subnet_by_id(
    credentials: dict, region: str, subnet_id: str
) -> dict[str, Any] | None:
    """Extract a single subnet by its ID.

    Returns a dict with: subnet_id, cidr_block, availability_zone.
    Returns None if the subnet cannot be found or on error.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")
        resp = ec2.describe_subnets(SubnetIds=[subnet_id])
        subnets = resp.get("Subnets", [])
        if not subnets:
            return None
        s = subnets[0]
        return {
            "subnet_id": s["SubnetId"],
            "cidr_block": s.get("CidrBlock", ""),
            "availability_zone": s.get("AvailabilityZone", ""),
        }
    except (ClientError, BotoCoreError) as e:
        print(f"Subnet extraction error: {e}")
        return None


def extract_lambda_functions(
    credentials: dict, region: str, vpc_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract Lambda functions with full runtime + sizing + packaging detail.

    Captures runtime, memory, timeout, handler, arch, package type, code
    size, layers, environment variable keys (not values — secrets), DLQ,
    tracing config. Does NOT call GetFunction per function (which would
    also return signed download URLs); ListFunctions response already
    contains everything we need.
    """
    try:
        session = _build_session(credentials, region)
        lam = session.client("lambda")

        results: list[dict[str, Any]] = []
        paginator = lam.get_paginator("list_functions")
        for page in paginator.paginate():
            for fn in page.get("Functions", []):
                vpc_config = fn.get("VpcConfig", {}) or {}
                fn_vpc = vpc_config.get("VpcId", "")
                if vpc_id and fn_vpc != vpc_id:
                    continue
                env_keys = list((fn.get("Environment") or {}).get("Variables", {}).keys())
                layers = [
                    {"arn": lyr.get("Arn", ""), "code_size_bytes": lyr.get("CodeSize", 0)}
                    for lyr in fn.get("Layers", [])
                ]
                results.append({
                    # Identity
                    "function_name": fn["FunctionName"],
                    "arn": fn.get("FunctionArn", ""),
                    "last_modified": fn.get("LastModified", ""),
                    # Runtime + sizing
                    "runtime": fn.get("Runtime", ""),
                    "handler": fn.get("Handler", ""),
                    "memory_size_mb": fn.get("MemorySize", 0),
                    "timeout_seconds": fn.get("Timeout", 0),
                    "architectures": fn.get("Architectures", []),
                    "ephemeral_storage_mb": (fn.get("EphemeralStorage") or {}).get("Size", 0),
                    # Packaging
                    "package_type": fn.get("PackageType", ""),
                    "code_size_bytes": fn.get("CodeSize", 0),
                    "code_sha256": fn.get("CodeSha256", ""),
                    # Network + IAM
                    "vpc_id": fn_vpc,
                    "subnet_ids": vpc_config.get("SubnetIds", []),
                    "security_group_ids": vpc_config.get("SecurityGroupIds", []),
                    "role_arn": fn.get("Role", ""),
                    # Observability / routing
                    "tracing_mode": (fn.get("TracingConfig") or {}).get("Mode", ""),
                    "dead_letter_target_arn": (fn.get("DeadLetterConfig") or {}).get("TargetArn", ""),
                    # Environment — keys only (never values: secrets frequently here)
                    "environment_variable_keys": env_keys,
                    "environment_variable_count": len(env_keys),
                    # Layers
                    "layers": layers,
                    "layer_count": len(layers),
                    # Event-driven config
                    "reserved_concurrent_executions": fn.get("ReservedConcurrentExecutions", 0),
                    "state": fn.get("State", ""),
                    "state_reason": fn.get("StateReason", ""),
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Lambda extraction error: {e}")
        return []


# ---------------------------------------------------------------------------
# Additional networking & compute extractors
# ---------------------------------------------------------------------------


def extract_subnets(
    credentials: dict, region: str, vpc_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract subnets as standalone resources.

    Each dict contains: subnet_id, vpc_id, cidr_block, availability_zone,
    map_public_ip_on_launch, name, arn.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        kwargs: dict[str, Any] = {}
        if vpc_id:
            kwargs["Filters"] = [{"Name": "vpc-id", "Values": [vpc_id]}]

        results: list[dict[str, Any]] = []
        paginator = ec2.get_paginator("describe_subnets")
        for page in paginator.paginate(**kwargs):
            for s in page.get("Subnets", []):
                name = ""
                for tag in s.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break
                account_id = s.get("OwnerId", "")
                results.append({
                    "subnet_id": s["SubnetId"],
                    "vpc_id": s.get("VpcId", ""),
                    "cidr_block": s.get("CidrBlock", ""),
                    "availability_zone": s.get("AvailabilityZone", ""),
                    "map_public_ip_on_launch": s.get("MapPublicIpOnLaunch", False),
                    "available_ip_count": s.get("AvailableIpAddressCount", 0),
                    "name": name,
                    "arn": s.get("SubnetArn", f"arn:aws:ec2:{region}:{account_id}:subnet/{s['SubnetId']}"),
                    "Tags": s.get("Tags", []),
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Subnet extraction error: {e}")
        return []


def extract_internet_gateways(
    credentials: dict, region: str, vpc_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract Internet Gateways.

    Each dict contains: igw_id, attachments (list of vpc_ids), name, arn.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        kwargs: dict[str, Any] = {}
        if vpc_id:
            kwargs["Filters"] = [{"Name": "attachment.vpc-id", "Values": [vpc_id]}]

        resp = ec2.describe_internet_gateways(**kwargs)
        results: list[dict[str, Any]] = []
        for igw in resp.get("InternetGateways", []):
            name = ""
            for tag in igw.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break
            attachments = [
                {"vpc_id": a.get("VpcId", ""), "state": a.get("State", "")}
                for a in igw.get("Attachments", [])
            ]
            account_id = igw.get("OwnerId", "")
            results.append({
                "igw_id": igw["InternetGatewayId"],
                "attachments": attachments,
                "name": name,
                "arn": f"arn:aws:ec2:{region}:{account_id}:internet-gateway/{igw['InternetGatewayId']}",
                "Tags": igw.get("Tags", []),
            })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Internet Gateway extraction error: {e}")
        return []


def extract_nat_gateways(
    credentials: dict, region: str, vpc_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract NAT Gateways.

    Each dict contains: nat_gateway_id, vpc_id, subnet_id, state,
    public_ip, private_ip, name, arn.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        kwargs: dict[str, Any] = {}
        if vpc_id:
            kwargs["Filter"] = [{"Name": "vpc-id", "Values": [vpc_id]}]

        results: list[dict[str, Any]] = []
        paginator = ec2.get_paginator("describe_nat_gateways")
        for page in paginator.paginate(**kwargs):
            for ngw in page.get("NatGateways", []):
                if ngw.get("State", "") == "deleted":
                    continue
                name = ""
                for tag in ngw.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                        break
                addresses = ngw.get("NatGatewayAddresses", [])
                public_ip = addresses[0].get("PublicIp", "") if addresses else ""
                private_ip = addresses[0].get("PrivateIp", "") if addresses else ""
                allocation_id = addresses[0].get("AllocationId", "") if addresses else ""
                results.append({
                    "nat_gateway_id": ngw["NatGatewayId"],
                    "vpc_id": ngw.get("VpcId", ""),
                    "subnet_id": ngw.get("SubnetId", ""),
                    "state": ngw.get("State", ""),
                    "connectivity_type": ngw.get("ConnectivityType", "public"),
                    "public_ip": public_ip,
                    "private_ip": private_ip,
                    "allocation_id": allocation_id,
                    "name": name,
                    "arn": f"arn:aws:ec2:{region}::natgateway/{ngw['NatGatewayId']}",
                    "Tags": ngw.get("Tags", []),
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"NAT Gateway extraction error: {e}")
        return []


def extract_route_tables(
    credentials: dict, region: str, vpc_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract Route Tables with their routes and subnet associations.

    Each dict contains: route_table_id, vpc_id, routes (list),
    associations (list), name, arn.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        kwargs: dict[str, Any] = {}
        if vpc_id:
            kwargs["Filters"] = [{"Name": "vpc-id", "Values": [vpc_id]}]

        resp = ec2.describe_route_tables(**kwargs)
        results: list[dict[str, Any]] = []
        for rt in resp.get("RouteTables", []):
            name = ""
            for tag in rt.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break
            routes = [
                {
                    "destination": r.get("DestinationCidrBlock", r.get("DestinationIpv6CidrBlock", "")),
                    "target": (
                        r.get("GatewayId", "")
                        or r.get("NatGatewayId", "")
                        or r.get("InstanceId", "")
                        or r.get("TransitGatewayId", "")
                        or r.get("VpcPeeringConnectionId", "")
                        or "local"
                    ),
                    "state": r.get("State", ""),
                    "origin": r.get("Origin", ""),
                }
                for r in rt.get("Routes", [])
            ]
            associations = [
                {
                    "association_id": a.get("RouteTableAssociationId", ""),
                    "subnet_id": a.get("SubnetId", ""),
                    "main": a.get("Main", False),
                }
                for a in rt.get("Associations", [])
            ]
            account_id = rt.get("OwnerId", "")
            results.append({
                "route_table_id": rt["RouteTableId"],
                "vpc_id": rt.get("VpcId", ""),
                "routes": routes,
                "associations": associations,
                "name": name,
                "arn": f"arn:aws:ec2:{region}:{account_id}:route-table/{rt['RouteTableId']}",
                "Tags": rt.get("Tags", []),
            })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Route table extraction error: {e}")
        return []


def extract_network_acls(
    credentials: dict, region: str, vpc_id: str | None = None
) -> list[dict[str, Any]]:
    """Extract Network ACLs with their entries and subnet associations.

    Each dict contains: network_acl_id, vpc_id, is_default, entries (list),
    associations (list of subnet_ids), name, arn.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        kwargs: dict[str, Any] = {}
        if vpc_id:
            kwargs["Filters"] = [{"Name": "vpc-id", "Values": [vpc_id]}]

        resp = ec2.describe_network_acls(**kwargs)
        results: list[dict[str, Any]] = []
        for nacl in resp.get("NetworkAcls", []):
            name = ""
            for tag in nacl.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break
            entries = [
                {
                    "rule_number": e.get("RuleNumber", 0),
                    "protocol": e.get("Protocol", ""),
                    "rule_action": e.get("RuleAction", ""),
                    "egress": e.get("Egress", False),
                    "cidr_block": e.get("CidrBlock", ""),
                    "port_range_from": e.get("PortRange", {}).get("From"),
                    "port_range_to": e.get("PortRange", {}).get("To"),
                }
                for e in nacl.get("Entries", [])
            ]
            associations = [
                {
                    "association_id": a.get("NetworkAclAssociationId", ""),
                    "subnet_id": a.get("SubnetId", ""),
                }
                for a in nacl.get("Associations", [])
            ]
            account_id = nacl.get("OwnerId", "")
            results.append({
                "network_acl_id": nacl["NetworkAclId"],
                "vpc_id": nacl.get("VpcId", ""),
                "is_default": nacl.get("IsDefault", False),
                "entries": entries,
                "associations": associations,
                "name": name,
                "arn": f"arn:aws:ec2:{region}:{account_id}:network-acl/{nacl['NetworkAclId']}",
                "Tags": nacl.get("Tags", []),
            })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Network ACL extraction error: {e}")
        return []


def extract_elastic_ips(
    credentials: dict, region: str
) -> list[dict[str, Any]]:
    """Extract Elastic IP addresses.

    Each dict contains: allocation_id, public_ip, association_id,
    instance_id, network_interface_id, domain, name, arn.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        resp = ec2.describe_addresses()
        results: list[dict[str, Any]] = []
        for eip in resp.get("Addresses", []):
            name = ""
            for tag in eip.get("Tags", []):
                if tag["Key"] == "Name":
                    name = tag["Value"]
                    break
            allocation_id = eip.get("AllocationId", "")
            results.append({
                "allocation_id": allocation_id,
                "public_ip": eip.get("PublicIp", ""),
                "association_id": eip.get("AssociationId", ""),
                "instance_id": eip.get("InstanceId", ""),
                "network_interface_id": eip.get("NetworkInterfaceId", ""),
                "domain": eip.get("Domain", ""),
                "name": name,
                "arn": f"arn:aws:ec2:{region}::eip/{allocation_id}",
                "Tags": eip.get("Tags", []),
            })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Elastic IP extraction error: {e}")
        return []


def extract_target_groups(
    credentials: dict, region: str
) -> list[dict[str, Any]]:
    """Extract ELBv2 Target Groups.

    Each dict contains: target_group_name, target_group_arn, port, protocol,
    vpc_id, target_type, health_check, load_balancer_arns.
    """
    try:
        session = _build_session(credentials, region)
        elbv2 = session.client("elbv2")

        results: list[dict[str, Any]] = []
        paginator = elbv2.get_paginator("describe_target_groups")
        for page in paginator.paginate():
            for tg in page.get("TargetGroups", []):
                tg_tags: list[dict] = []
                try:
                    tag_resp = elbv2.describe_tags(ResourceArns=[tg["TargetGroupArn"]])
                    for td in tag_resp.get("TagDescriptions", []):
                        tg_tags = td.get("Tags", [])
                except (ClientError, BotoCoreError):
                    pass
                results.append({
                    "target_group_name": tg.get("TargetGroupName", ""),
                    "port": tg.get("Port"),
                    "protocol": tg.get("Protocol", ""),
                    "vpc_id": tg.get("VpcId", ""),
                    "target_type": tg.get("TargetType", ""),
                    "health_check": {
                        "protocol": tg.get("HealthCheckProtocol", ""),
                        "port": tg.get("HealthCheckPort", ""),
                        "path": tg.get("HealthCheckPath", ""),
                        "interval_seconds": tg.get("HealthCheckIntervalSeconds"),
                        "timeout_seconds": tg.get("HealthCheckTimeoutSeconds"),
                        "healthy_threshold": tg.get("HealthyThresholdCount"),
                        "unhealthy_threshold": tg.get("UnhealthyThresholdCount"),
                    },
                    "load_balancer_arns": tg.get("LoadBalancerArns", []),
                    "name": tg.get("TargetGroupName", ""),
                    "arn": tg.get("TargetGroupArn", ""),
                    "Tags": tg_tags,
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Target Group extraction error: {e}")
        return []


def extract_listeners(
    credentials: dict, region: str
) -> list[dict[str, Any]]:
    """Extract ELBv2 Listeners for all load balancers.

    Each dict contains: listener_arn, load_balancer_arn, port, protocol,
    default_actions.
    """
    try:
        session = _build_session(credentials, region)
        elbv2 = session.client("elbv2")

        # First get all load balancers, then their listeners
        lb_arns: list[str] = []
        lb_paginator = elbv2.get_paginator("describe_load_balancers")
        for page in lb_paginator.paginate():
            for lb in page.get("LoadBalancers", []):
                lb_arns.append(lb["LoadBalancerArn"])

        results: list[dict[str, Any]] = []
        for lb_arn in lb_arns:
            try:
                resp = elbv2.describe_listeners(LoadBalancerArn=lb_arn)
                for listener in resp.get("Listeners", []):
                    actions = [
                        {
                            "type": a.get("Type", ""),
                            "target_group_arn": a.get("TargetGroupArn", ""),
                        }
                        for a in listener.get("DefaultActions", [])
                    ]
                    lb_name = lb_arn.split("/")[-2] if "/" in lb_arn else lb_arn
                    results.append({
                        "load_balancer_arn": lb_arn,
                        "port": listener.get("Port"),
                        "protocol": listener.get("Protocol", ""),
                        "default_actions": actions,
                        "name": f"{lb_name}:{listener.get('Port', '')}",
                        "arn": listener.get("ListenerArn", ""),
                    })
            except (ClientError, BotoCoreError):
                continue
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Listener extraction error: {e}")
        return []


def extract_launch_templates(
    credentials: dict, region: str
) -> list[dict[str, Any]]:
    """Extract EC2 Launch Templates with their latest version data.

    Each dict contains: launch_template_id, launch_template_name,
    latest_version, image_id, instance_type, key_name,
    security_group_ids, user_data_present, arn.
    """
    try:
        session = _build_session(credentials, region)
        ec2 = session.client("ec2")

        results: list[dict[str, Any]] = []
        paginator = ec2.get_paginator("describe_launch_templates")
        for page in paginator.paginate():
            for lt in page.get("LaunchTemplates", []):
                lt_id = lt["LaunchTemplateId"]
                lt_name = lt.get("LaunchTemplateName", "")

                # Get latest version details
                lt_data: dict[str, Any] = {}
                try:
                    ver_resp = ec2.describe_launch_template_versions(
                        LaunchTemplateId=lt_id,
                        Versions=["$Latest"],
                    )
                    versions = ver_resp.get("LaunchTemplateVersions", [])
                    if versions:
                        lt_data = versions[0].get("LaunchTemplateData", {})
                except (ClientError, BotoCoreError):
                    pass

                sg_ids = lt_data.get("SecurityGroupIds", [])
                if not sg_ids:
                    sg_ids = [
                        sg.get("GroupId", "")
                        for sg in lt_data.get("SecurityGroups", [])
                        if isinstance(sg, dict)
                    ]

                account_id = lt.get("CreatedBy", "").split(":")[4] if ":" in lt.get("CreatedBy", "") else ""
                results.append({
                    "launch_template_id": lt_id,
                    "launch_template_name": lt_name,
                    "latest_version": lt.get("LatestVersionNumber", 1),
                    "image_id": lt_data.get("ImageId", ""),
                    "instance_type": lt_data.get("InstanceType", ""),
                    "key_name": lt_data.get("KeyName", ""),
                    "security_group_ids": sg_ids,
                    "user_data_present": bool(lt_data.get("UserData")),
                    "name": lt_name,
                    "arn": f"arn:aws:ec2:{region}:{account_id}:launch-template/{lt_id}",
                    "Tags": lt.get("Tags", []),
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Launch Template extraction error: {e}")
        return []


# ---------------------------------------------------------------------------
# Object storage
# ---------------------------------------------------------------------------


def extract_s3_buckets(credentials: dict, region: str) -> list[dict[str, Any]]:
    """Extract S3 buckets + their security/versioning posture.

    S3 buckets are global (not region-scoped) but each bucket lives in a
    home region. We list all buckets, then filter to those in *region*
    (leaves cross-region buckets for discovery in the matching region's
    run). For each bucket we pull versioning, encryption, public-access
    block, and tags — all small per-bucket calls.
    """
    try:
        session = _build_session(credentials, region)
        s3 = session.client("s3")
        all_buckets = s3.list_buckets().get("Buckets", [])

        results: list[dict[str, Any]] = []
        for b in all_buckets:
            name = b["Name"]
            # Locate the bucket's home region
            try:
                loc = s3.get_bucket_location(Bucket=name).get("LocationConstraint", "") or "us-east-1"
            except (ClientError, BotoCoreError):
                continue
            if loc != region:
                continue

            versioning = ""
            try:
                v = s3.get_bucket_versioning(Bucket=name)
                versioning = v.get("Status", "Disabled")
            except (ClientError, BotoCoreError):
                pass

            encryption_type = "none"
            encryption_kms_key = ""
            try:
                enc = s3.get_bucket_encryption(Bucket=name)
                rules = (enc.get("ServerSideEncryptionConfiguration") or {}).get("Rules", [])
                if rules:
                    sse = (rules[0].get("ApplyServerSideEncryptionByDefault") or {})
                    encryption_type = sse.get("SSEAlgorithm", "")
                    encryption_kms_key = sse.get("KMSMasterKeyID", "")
            except (ClientError, BotoCoreError):
                # NoSuchConfiguration is expected when no default encryption set
                pass

            pab: dict = {}
            try:
                pab_resp = s3.get_public_access_block(Bucket=name)
                pab = pab_resp.get("PublicAccessBlockConfiguration", {}) or {}
            except (ClientError, BotoCoreError):
                pass

            tags: list[dict] = []
            try:
                tag_resp = s3.get_bucket_tagging(Bucket=name)
                tags = tag_resp.get("TagSet", []) or []
            except (ClientError, BotoCoreError):
                pass

            created = b.get("CreationDate")
            results.append({
                "bucket_name": name,
                "name": name,
                "region": loc,
                "creation_date": created.isoformat() if created else "",
                "versioning_status": versioning,
                "encryption_type": encryption_type,
                "encryption_kms_key": encryption_kms_key,
                "public_access_block": {
                    "block_public_acls": pab.get("BlockPublicAcls", False),
                    "ignore_public_acls": pab.get("IgnorePublicAcls", False),
                    "block_public_policy": pab.get("BlockPublicPolicy", False),
                    "restrict_public_buckets": pab.get("RestrictPublicBuckets", False),
                },
                "arn": f"arn:aws:s3:::{name}",
                "Tags": tags,
            })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"S3 extraction error: {e}")
        return []


# ---------------------------------------------------------------------------
# Best-effort per-instance enrichment (CloudWatch + SSM)
# ---------------------------------------------------------------------------
# These are post-processing passes invoked after the main extractor loop
# so they don't block discovery when the underlying services aren't set up
# on the customer's AWS (CWAgent not installed, SSM agent absent, etc.).


def extract_ec2_metrics(
    credentials: dict, region: str, instance_ids: list[str],
    lookback_days: int = 14,
) -> dict[str, dict[str, float]]:
    """Fetch last-{lookback_days} CloudWatch stats per instance.

    Returns ``{instance_id: {metric: {avg, p95, max}}}`` — a compact
    summary the rightsizer + UI can show. Metrics pulled:

    - ``CPUUtilization`` (AWS/EC2, always available)
    - ``mem_used_percent`` (CWAgent — only populated if the CloudWatch
      Agent is installed on the instance; silently absent otherwise)
    - ``NetworkIn``, ``NetworkOut`` (AWS/EC2)
    - ``DiskReadOps``, ``DiskWriteOps`` (AWS/EC2, EBS-backed only)

    Never raises — returns ``{}`` on any failure. CloudWatch calls are
    rate-limited by boto3's retry policy and are cheap relative to per-
    instance Describe calls.
    """
    if not instance_ids:
        return {}

    from datetime import datetime, timedelta, timezone
    try:
        session = _build_session(credentials, region)
        cw = session.client("cloudwatch")
    except (ClientError, BotoCoreError):
        return {}

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    # 1-hour granularity — 14 days × 24 = 336 data points max, well under quota
    period = 3600

    def _one_metric(namespace: str, metric_name: str, instance_id: str) -> dict[str, float]:
        try:
            resp = cw.get_metric_statistics(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=start,
                EndTime=end,
                Period=period,
                Statistics=["Average", "Maximum"],
                ExtendedStatistics=["p95"],
            )
            points = resp.get("Datapoints", [])
            if not points:
                return {}
            avg = sum(p.get("Average", 0) for p in points) / max(len(points), 1)
            mx = max((p.get("Maximum", 0) for p in points), default=0)
            p95_vals = [p.get("ExtendedStatistics", {}).get("p95") for p in points
                         if p.get("ExtendedStatistics")]
            p95_vals = [v for v in p95_vals if v is not None]
            p95 = (sum(p95_vals) / len(p95_vals)) if p95_vals else 0
            return {"avg": round(avg, 2), "p95": round(p95, 2), "max": round(mx, 2)}
        except (ClientError, BotoCoreError):
            return {}

    wanted = [
        ("AWS/EC2", "CPUUtilization"),
        ("AWS/EC2", "NetworkIn"),
        ("AWS/EC2", "NetworkOut"),
        ("AWS/EC2", "DiskReadOps"),
        ("AWS/EC2", "DiskWriteOps"),
        ("CWAgent", "mem_used_percent"),
    ]
    out: dict[str, dict[str, float]] = {}
    for iid in instance_ids:
        inst_metrics: dict[str, Any] = {}
        for ns, name in wanted:
            vals = _one_metric(ns, name, iid)
            if vals:
                inst_metrics[name] = vals
        if inst_metrics:
            out[iid] = inst_metrics
    return out


def extract_ssm_inventory(
    credentials: dict, region: str, instance_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Pull SSM inventory (OS + installed software) per instance.

    Returns ``{instance_id: {os_name, os_version, installed_applications:
    [{name, version}, …]}}``. Only instances with the SSM Agent installed +
    ``AmazonSSMManagedInstanceCore`` attached show up — others are silently
    skipped.

    We filter ``installed_applications`` to common DB / web / runtime
    signatures so the UI can surface "MySQL 8.0" / "nginx 1.24" / "java 17"
    without dumping 800-entry package lists.
    """
    if not instance_ids:
        return {}

    try:
        session = _build_session(credentials, region)
        ssm = session.client("ssm")
    except (ClientError, BotoCoreError):
        return {}

    # Keywords we surface — mirrors data/mappings/resources.yaml's
    # local_db_keywords + a few common web-server / runtime names.
    INTERESTING_APP_KEYWORDS = {
        "mysql", "mariadb", "postgres", "postgresql", "mongodb", "redis",
        "memcached", "cassandra", "elasticsearch", "kafka", "sqlite",
        "nginx", "apache", "httpd", "tomcat", "iis",
        "python", "java", "jdk", "node", "nodejs", "ruby", "php", "go", "dotnet",
        "docker", "kubernetes", "kubelet",
    }

    out: dict[str, dict[str, Any]] = {}
    for iid in instance_ids:
        entry: dict[str, Any] = {
            "os_name": "",
            "os_version": "",
            "kernel": "",
            "installed_applications": [],
            "inventory_collected": False,
        }
        # OS
        try:
            os_resp = ssm.list_inventory_entries(
                InstanceId=iid,
                TypeName="AWS:InstanceInformation",
            )
            ents = os_resp.get("Entries", [])
            if ents:
                e = ents[0]
                entry["os_name"] = e.get("PlatformName", "") or e.get("Name", "")
                entry["os_version"] = e.get("PlatformVersion", "")
                entry["kernel"] = e.get("KernelVersion", "")
                entry["inventory_collected"] = True
        except (ClientError, BotoCoreError):
            pass
        # Apps
        try:
            # list_inventory_entries paginates; capture up to 500 entries to
            # avoid runaway on full package lists.
            app_resp = ssm.list_inventory_entries(
                InstanceId=iid,
                TypeName="AWS:Application",
                MaxResults=500,
            )
            apps = []
            for e in app_resp.get("Entries", []):
                name = (e.get("Name") or "").strip()
                if not name:
                    continue
                nlow = name.lower()
                if any(kw in nlow for kw in INTERESTING_APP_KEYWORDS):
                    apps.append({
                        "name": name,
                        "version": e.get("Version", ""),
                        "publisher": e.get("Publisher", ""),
                    })
            entry["installed_applications"] = apps
            if apps:
                entry["inventory_collected"] = True
        except (ClientError, BotoCoreError):
            pass

        if entry["inventory_collected"]:
            out[iid] = entry
    return out
