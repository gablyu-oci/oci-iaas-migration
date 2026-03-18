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
