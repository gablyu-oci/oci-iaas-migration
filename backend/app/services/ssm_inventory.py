"""SSM inventory collector for software discovery."""
from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)

# SSM describe_instance_information accepts at most 50 instance IDs per call
_CHUNK_SIZE = 50


def _build_session(credentials: dict, region: str) -> boto3.Session:
    """Build a boto3 Session from a credentials dict."""
    return boto3.Session(
        aws_access_key_id=credentials.get("aws_access_key_id"),
        aws_secret_access_key=credentials.get("aws_secret_access_key"),
        aws_session_token=credentials.get("aws_session_token"),
        region_name=region,
    )


def _build_ssm_client(credentials: dict, region: str):
    """Create SSM client using the standard credential pattern."""
    session = _build_session(credentials, region)
    return session.client("ssm")


def _chunks(lst: list, size: int):
    """Yield successive chunks of *size* from *lst*."""
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def collect_inventory(
    credentials: dict,
    region: str,
    instance_ids: list[str],
) -> dict[str, dict]:
    """Collect SSM inventory for the given EC2 instances.

    Returns a dict mapping *instance_id* to an inventory summary::

        {
            "ssm_managed": bool,
            "os_name": str | None,
            "os_version": str | None,
            "computer_name": str | None,
            "applications": [{"name": str, "version": str, "publisher": str}, ...],
        }

    Instances that are not SSM-managed get a skeleton entry with
    ``ssm_managed=False`` and empty fields.  Errors are logged and
    partial results are returned.
    """
    ssm = _build_ssm_client(credentials, region)

    # Pre-populate every instance with a default "not managed" entry
    results: dict[str, dict[str, Any]] = {
        iid: {
            "ssm_managed": False,
            "os_name": None,
            "os_version": None,
            "computer_name": None,
            "applications": [],
        }
        for iid in instance_ids
    }

    # --- Step 1: Identify SSM-managed instances ---------------------------
    managed_ids: set[str] = set()
    try:
        for chunk in _chunks(instance_ids, _CHUNK_SIZE):
            paginator = ssm.get_paginator("describe_instance_information")
            for page in paginator.paginate(
                Filters=[{"Key": "InstanceIds", "Values": chunk}],
            ):
                for info in page.get("InstanceInformationList", []):
                    iid = info.get("InstanceId", "")
                    if iid not in results:
                        continue
                    managed_ids.add(iid)
                    results[iid]["ssm_managed"] = True
                    results[iid]["os_name"] = info.get("PlatformName")
                    results[iid]["os_version"] = info.get("PlatformVersion")
                    results[iid]["computer_name"] = info.get("ComputerName")
    except (ClientError, BotoCoreError) as exc:
        logger.error("SSM describe_instance_information failed: %s", exc)
        # Return what we have so far -- all entries default to unmanaged
        return results

    # --- Step 2: Collect application inventory for managed instances -------
    for iid in managed_ids:
        try:
            apps: list[dict[str, str]] = []
            next_token: str | None = None

            while True:
                kwargs: dict[str, Any] = {
                    "InstanceId": iid,
                    "TypeName": "AWS:Application",
                    "MaxResults": 50,
                }
                if next_token:
                    kwargs["NextToken"] = next_token

                resp = ssm.list_inventory_entries(**kwargs)

                for entry in resp.get("Entries", []):
                    apps.append({
                        "name": entry.get("Name", ""),
                        "version": entry.get("Version", ""),
                        "publisher": entry.get("Publisher", ""),
                    })

                next_token = resp.get("NextToken")
                if not next_token:
                    break

            results[iid]["applications"] = apps

        except (ClientError, BotoCoreError) as exc:
            logger.warning(
                "Failed to retrieve SSM inventory for %s: %s", iid, exc
            )
            # Leave applications as empty list
            continue
        except Exception:
            logger.exception("Unexpected error fetching inventory for %s", iid)
            continue

    logger.info(
        "SSM inventory collected: %d managed / %d total instances",
        len(managed_ids),
        len(instance_ids),
    )
    return results
