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

    Each dict contains: instance_id, instance_type, state, vpc_id,
    subnet_id, security_groups (list of group-ids), name, arn.
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
                    results.append({
                        "instance_id": inst["InstanceId"],
                        "instance_type": inst.get("InstanceType", ""),
                        "state": inst.get("State", {}).get("Name", ""),
                        "vpc_id": inst.get("VpcId", ""),
                        "subnet_id": inst.get("SubnetId", ""),
                        "security_groups": sg_ids,
                        "iam_instance_profile_arn": profile.get("Arn", ""),
                        "name": name,
                        "arn": (
                            f"arn:aws:ec2:{region}::instance/{inst['InstanceId']}"
                        ),
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
    """Extract RDS instances, optionally filtered to those in *vpc_id*.

    Each dict contains: db_instance_id, engine, status, vpc_id, arn.
    """
    try:
        session = _build_session(credentials, region)
        rds = session.client("rds")

        results: list[dict[str, Any]] = []
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db_inst in page.get("DBInstances", []):
                inst_vpc = db_inst.get("DBSubnetGroup", {}).get("VpcId", "")
                if vpc_id and inst_vpc != vpc_id:
                    continue
                results.append({
                    "db_instance_id": db_inst["DBInstanceIdentifier"],
                    "engine": db_inst.get("Engine", ""),
                    "status": db_inst.get("DBInstanceStatus", ""),
                    "vpc_id": inst_vpc,
                    "arn": db_inst.get("DBInstanceArn", ""),
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
                results.append({
                    "name": lb.get("LoadBalancerName", ""),
                    "dns_name": lb.get("DNSName", ""),
                    "type": lb.get("Type", ""),
                    "vpc_id": lb_vpc,
                    "arn": lb.get("LoadBalancerArn", ""),
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
                results.append({
                    "asg_name": asg["AutoScalingGroupName"],
                    "min_size": asg.get("MinSize", 0),
                    "max_size": asg.get("MaxSize", 0),
                    "desired_capacity": asg.get("DesiredCapacity", 0),
                    "instance_ids": ids,
                    "arn": asg.get("AutoScalingGroupARN", ""),
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
                results.append({
                    "volume_id": vol["VolumeId"],
                    "size_gb": vol.get("Size", 0),
                    "volume_type": vol.get("VolumeType", ""),
                    "state": vol.get("State", ""),
                    "encrypted": vol.get("Encrypted", False),
                    "availability_zone": vol.get("AvailabilityZone", ""),
                    "attachments": attachments,
                    "name": name,
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
    """Extract Lambda functions, optionally filtered to those attached to
    *vpc_id*.

    Each dict contains: function_name, runtime, vpc_id, arn.
    """
    try:
        session = _build_session(credentials, region)
        lam = session.client("lambda")

        results: list[dict[str, Any]] = []
        paginator = lam.get_paginator("list_functions")
        for page in paginator.paginate():
            for fn in page.get("Functions", []):
                fn_vpc = fn.get("VpcConfig", {}).get("VpcId", "")
                if vpc_id and fn_vpc != vpc_id:
                    continue
                results.append({
                    "function_name": fn["FunctionName"],
                    "runtime": fn.get("Runtime", ""),
                    "vpc_id": fn_vpc,
                    "arn": fn.get("FunctionArn", ""),
                })
        return results
    except (ClientError, BotoCoreError) as e:
        print(f"Lambda extraction error: {e}")
        return []
