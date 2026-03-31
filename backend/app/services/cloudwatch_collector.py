"""CloudWatch metrics collector for migration assessment."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)

METRIC_CONFIGS = [
    {"namespace": "AWS/EC2", "metric": "CPUUtilization", "stat": ["Average", "p95"]},
    {"namespace": "AWS/EC2", "metric": "NetworkIn", "stat": ["Average"]},
    {"namespace": "AWS/EC2", "metric": "NetworkOut", "stat": ["Average"]},
    {"namespace": "AWS/EC2", "metric": "DiskReadOps", "stat": ["Average"]},
    {"namespace": "AWS/EC2", "metric": "DiskWriteOps", "stat": ["Average"]},
]

# One-hour period for CloudWatch data points
_PERIOD_SECONDS = 3600


def _build_session(credentials: dict, region: str) -> boto3.Session:
    """Build a boto3 Session from a credentials dict."""
    return boto3.Session(
        aws_access_key_id=credentials.get("aws_access_key_id"),
        aws_secret_access_key=credentials.get("aws_secret_access_key"),
        aws_session_token=credentials.get("aws_session_token"),
        region_name=region,
    )


def _build_cw_client(credentials: dict, region: str):
    """Create CloudWatch client using the standard credential pattern."""
    session = _build_session(credentials, region)
    return session.client("cloudwatch")


def _compute_p95(datapoints: list[dict], stat_key: str = "Average") -> float:
    """Compute p95 from a list of CloudWatch datapoints.

    Sorts values in ascending order and returns the value at the 95th
    percentile index.  Returns 0.0 when no valid data is available.
    """
    values = sorted([d[stat_key] for d in datapoints if stat_key in d])
    if not values:
        return 0.0
    idx = int(len(values) * 0.95)
    return values[min(idx, len(values) - 1)]


def _average(datapoints: list[dict], stat_key: str = "Average") -> float:
    """Compute the simple mean from CloudWatch datapoints."""
    values = [d[stat_key] for d in datapoints if stat_key in d]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _fetch_metric(
    cw_client,
    namespace: str,
    metric_name: str,
    instance_id: str,
    start_time: datetime,
    end_time: datetime,
    statistics: list[str] | None = None,
    extended_statistics: list[str] | None = None,
) -> list[dict]:
    """Fetch metric statistics for a single instance.

    Returns the raw Datapoints list from get_metric_statistics.
    """
    kwargs: dict = {
        "Namespace": namespace,
        "MetricName": metric_name,
        "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
        "StartTime": start_time,
        "EndTime": end_time,
        "Period": _PERIOD_SECONDS,
    }
    if statistics:
        kwargs["Statistics"] = statistics
    if extended_statistics:
        kwargs["ExtendedStatistics"] = extended_statistics

    response = cw_client.get_metric_statistics(**kwargs)
    return response.get("Datapoints", [])


def collect_metrics(
    credentials: dict,
    region: str,
    instance_ids: list[str],
    window_days: int = 14,
) -> dict[str, dict]:
    """Collect CloudWatch metrics for a list of EC2 instances.

    Returns a dict mapping *instance_id* to a metrics summary::

        {
            "cpu_avg": float,
            "cpu_p95": float,
            "network_in_avg": float,
            "network_out_avg": float,
            "disk_read_ops_avg": float,
            "disk_write_ops_avg": float,
            "mem_p95": float | None,
        }

    Best-effort: errors for individual instances are logged and skipped so
    that partial results can still be returned.
    """
    cw_client = _build_cw_client(credentials, region)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=window_days)

    results: dict[str, dict] = {}

    for instance_id in instance_ids:
        try:
            metrics: dict[str, float | None] = {}

            for cfg in METRIC_CONFIGS:
                # Determine whether we need extended statistics (p95)
                needs_extended = "p95" in cfg["stat"]
                statistics = ["Average"]
                extended = ["p95"] if needs_extended else None

                datapoints = _fetch_metric(
                    cw_client,
                    namespace=cfg["namespace"],
                    metric_name=cfg["metric"],
                    instance_id=instance_id,
                    start_time=start_time,
                    end_time=end_time,
                    statistics=statistics,
                    extended_statistics=extended,
                )

                metric_lower = cfg["metric"]
                if metric_lower == "CPUUtilization":
                    metrics["cpu_avg"] = _average(datapoints, "Average")
                    # Use ExtendedStatistics p95 value if available, otherwise
                    # compute from the Average datapoints as a fallback.
                    p95_values = [
                        d["ExtendedStatistics"]["p95"]
                        for d in datapoints
                        if "ExtendedStatistics" in d and "p95" in d.get("ExtendedStatistics", {})
                    ]
                    if p95_values:
                        metrics["cpu_p95"] = sorted(p95_values)[
                            min(int(len(p95_values) * 0.95), len(p95_values) - 1)
                        ]
                    else:
                        metrics["cpu_p95"] = _compute_p95(datapoints, "Average")
                elif metric_lower == "NetworkIn":
                    metrics["network_in_avg"] = _average(datapoints, "Average")
                elif metric_lower == "NetworkOut":
                    metrics["network_out_avg"] = _average(datapoints, "Average")
                elif metric_lower == "DiskReadOps":
                    metrics["disk_read_ops_avg"] = _average(datapoints, "Average")
                elif metric_lower == "DiskWriteOps":
                    metrics["disk_write_ops_avg"] = _average(datapoints, "Average")

            # Best-effort: try CWAgent namespace for memory utilisation
            try:
                mem_datapoints = _fetch_metric(
                    cw_client,
                    namespace="CWAgent",
                    metric_name="mem_used_percent",
                    instance_id=instance_id,
                    start_time=start_time,
                    end_time=end_time,
                    statistics=["Average"],
                )
                metrics["mem_p95"] = _compute_p95(mem_datapoints, "Average") if mem_datapoints else None
            except (ClientError, BotoCoreError):
                # CWAgent metrics are not available for this instance
                metrics["mem_p95"] = None

            results[instance_id] = metrics

        except (ClientError, BotoCoreError) as exc:
            logger.error("Failed to collect CloudWatch metrics for %s: %s", instance_id, exc)
            continue
        except Exception:
            logger.exception("Unexpected error collecting metrics for %s", instance_id)
            continue

    logger.info(
        "Collected CloudWatch metrics for %d / %d instances",
        len(results),
        len(instance_ids),
    )
    return results
