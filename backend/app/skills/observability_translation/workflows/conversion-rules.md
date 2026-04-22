# AWS Observability / Messaging → OCI Monitoring / Logging / Notifications / Queue Conversion Rules

Prose guidance that doesn't fit in the mapping table.

## Service-level mapping

| AWS service | OCI target | Terraform resources |
|---|---|---|
| CloudWatch Alarm | Monitoring Alarm | `oci_monitoring_alarm` |
| CloudWatch Dashboard | Management Dashboards | `oci_management_dashboard_management_dashboard` |
| CloudWatch Logs (Log Group) | Logging (Log Group) | `oci_logging_log_group` |
| CloudWatch Logs (Log Stream) | Logging (Log) | `oci_logging_log` |
| Logs Subscription Filter | Service Connector Hub | `oci_sch_service_connector` |
| SNS Topic | Notifications | `oci_ons_notification_topic` |
| SNS Subscription | Notifications Subscription | `oci_ons_subscription` |
| SQS Queue | Queue | `oci_queue_queue` |
| SQS Queue Policy | IAM policy on compartment | `oci_identity_policy` |
| CloudTrail Trail | Audit (always-on, no HCL) | — (emit Service Connector for retention) |

## Metric namespace mapping

CloudWatch metrics are fetched from `AWS/<Service>` namespaces. OCI Monitoring uses `oci_<service>` namespaces with different metric names. When translating alarm queries, rewrite both the namespace and the metric name.

| AWS namespace | OCI namespace | Common metric rename |
|---|---|---|
| `AWS/EC2` | `oci_computeagent` | `CPUUtilization` → `CpuUtilization` |
| `AWS/RDS` | `oci_database` | `CPUUtilization` → `CpuUtilization`, `DatabaseConnections` → `CurrentConnections` |
| `AWS/Lambda` | `oci_faas` | `Invocations` → `FunctionInvocations`, `Errors` → `FunctionExecutionError` |
| `AWS/ApplicationELB` | `oci_lbaas` | `TargetResponseTime` → `ResponseTime` |
| `AWS/NetworkELB` | `oci_nlb` | Same-name for most |
| `AWS/S3` | `oci_objectstorage` | `NumberOfObjects` → `StoredObjects`, different unit |
| `AWS/Logs` | `oci_logging` | `IncomingBytes` → `LogSize` |
| `AWS/ApiGateway` | `oci_apigateway` | `Count` → `HttpRequests` |
| `CWAgent` (custom EC2 agent) | `oci_computeagent` | Map per-metric; verify Compute Agent plugin enabled |

When unsure, emit the alarm with a TODO comment and the original AWS namespace/metric preserved in a `description` field.

## CloudWatch Alarm translation

```hcl
resource "oci_monitoring_alarm" "cpu_high" {
  compartment_id          = var.compartment_ocid
  destinations            = [oci_ons_notification_topic.alerts.id]
  display_name            = "cpu-high"
  is_enabled              = true
  metric_compartment_id   = var.compartment_ocid
  namespace               = "oci_computeagent"
  query                   = "CpuUtilization[1m].mean() > 80"
  severity                = "CRITICAL"
  body                    = "CPU > 80% for 5 minutes"
  pending_duration        = "PT5M"
}
```

### AWS → OCI field mapping

| AWS `Alarm` property | OCI `oci_monitoring_alarm` field |
|---|---|
| `AlarmName` | `display_name` |
| `Namespace` + `MetricName` | Reference in `query` (`<Metric>[<interval>].<agg>() <op> <threshold>`) |
| `Statistic` (`Average`, `Sum`, etc.) | `.mean()`, `.sum()`, `.max()`, etc. on the metric |
| `Period` (seconds) | Interval inside `query` — `[60s]`, `[1m]`, `[5m]`, `[1h]` |
| `EvaluationPeriods` × `Period` | `pending_duration` (ISO-8601 duration; e.g., 3 × 60s → `PT3M`) |
| `Threshold` + `ComparisonOperator` | Inside `query` (`> 80`, `<= 10`, etc.) |
| `AlarmActions` (SNS ARNs) | `destinations` (list of `oci_ons_notification_topic.*.id`) |
| `TreatMissingData` | `is_notifications_per_metric_dimension_enabled` + `suppression` block (best-effort) |
| `Dimensions` | Filter inside `query`: `CpuUtilization[1m]{resourceId="..."}.mean()` |

### Severity mapping

AWS alarms have no built-in severity. Infer from the name:
- Name contains `critical`, `page`, `error` → `severity = "CRITICAL"`
- Contains `warn`, `warning` → `severity = "WARNING"`
- Contains `info` → `severity = "INFO"`
- Otherwise → `severity = "ERROR"` (safe default).

## CloudWatch Logs

### Log Group → OCI Log Group + Logs

OCI's model: **Log Group** is a container, **Log** is the queryable stream inside it. One AWS log group typically maps to one OCI log group + one OCI log.

```hcl
resource "oci_logging_log_group" "app" {
  compartment_id = var.compartment_ocid
  display_name   = "app-logs"
}

resource "oci_logging_log" "app_access" {
  log_group_id = oci_logging_log_group.app.id
  display_name = "access"
  log_type     = "CUSTOM"                  # or "SERVICE" for OCI-produced logs
  is_enabled   = true
  retention_duration = 30                  # days
}
```

### Retention

AWS supports retention in days (1, 3, 5, ..., 3653). OCI Logging retention is 30/60/90/180/365 days. Map to the **nearest supported** value and log a note if rounding changes the policy materially.

### Subscription filters

AWS `SubscriptionFilter` → OCI Service Connector Hub flow. Do NOT attempt to codify Lambda subscriptions directly — emit `oci_sch_service_connector` with source = Logging, target = Functions / Streaming / Object Storage as appropriate.

```hcl
resource "oci_sch_service_connector" "logs_to_stream" {
  display_name   = "app-logs-to-kafka"
  compartment_id = var.compartment_ocid
  source {
    kind = "logging"
    log_sources { compartment_id = var.compartment_ocid
                   log_group_id   = oci_logging_log_group.app.id
                   log_id         = oci_logging_log.app_access.id }
  }
  target {
    kind       = "streaming"
    stream_id  = oci_streaming_stream.log_sink.id
  }
}
```

### Log Insights queries

CloudWatch Logs Insights syntax differs from OCI Logging Search. If the source alarm or dashboard references a Logs Insights query, emit the OCI-Logging query inside a `description` comment — the operator will port it manually. Flag LOW.

## SNS → Notifications

- `AWS::SNS::Topic` → `oci_ons_notification_topic` 1:1.
- `AWS::SNS::Subscription` protocols:

  | AWS protocol | OCI protocol |
  |---|---|
  | `email` | `EMAIL` |
  | `email-json` | `EMAIL` (note: JSON payload) |
  | `https` | `HTTPS` |
  | `http` | Flag CRITICAL — OCI requires HTTPS |
  | `lambda` | `ORACLE_FUNCTIONS` |
  | `sqs` | Custom — use Service Connector Hub instead |
  | `sms` | `SMS` |
  | `application` (mobile push) | Not supported — flag CRITICAL |
  | PagerDuty / Slack (custom) | `PAGERDUTY` or `SLACK` (native OCI support) |

- **Topic policies** (resource-based) → IAM policies on the compartment referencing the topic OCID. Flag MEDIUM for cross-account topic access.

## SQS → Queue

- `AWS::SQS::Queue` → `oci_queue_queue` 1:1.
- Properties:
  - `VisibilityTimeout` (seconds) → `visibility_in_seconds`
  - `MessageRetentionPeriod` → `retention_in_seconds` (note: OCI max is 7 days)
  - `MaximumMessageSize` → `channel_consumption_limit` / not 1:1, flag LOW
  - `DelaySeconds` → not natively supported; enforce in consumer code. Flag MEDIUM.
  - FIFO (`FifoQueue: true`) → OCI Queue does not support strict FIFO ordering. Flag CRITICAL.
- Dead-letter queue (DLQ): OCI supports a per-queue DLQ via `dead_letter_queue_delivery_count`. Map from `RedrivePolicy.deadLetterTargetArn`.

## CloudTrail

OCI **Audit is always on** for every tenancy — do NOT emit a resource for the "trail" itself. Instead, if the AWS trail has log-forwarding (to S3 / CloudWatch Logs), emit a Service Connector:

```hcl
resource "oci_sch_service_connector" "audit_archive" {
  display_name = "audit-to-object-storage"
  source {
    kind = "audit"
  }
  target {
    kind      = "objectStorage"
    bucket    = oci_objectstorage_bucket.audit.name
    namespace = data.oci_objectstorage_namespace.ns.namespace
  }
}
```

Flag LOW for trails that only capture management events (the default) since that's redundant with OCI Audit. Flag MEDIUM for data-event trails (bucket-level S3 events, Lambda data events) that need explicit additional capture.

## CloudWatch Dashboards

Dashboard JSON widgets don't translate cleanly to OCI Management Dashboards. Recommendation: emit a placeholder `oci_management_dashboard_management_dashboard` with a TODO + the original AWS widgets dumped in the `dashboard` string (as a comment) so the operator can rebuild.

## Ordering within this skill

1. Log groups first (alarms + subscriptions reference them).
2. SNS topics next (alarms reference them as destinations).
3. Alarms (reference topics + metric namespaces).
4. SQS queues (independent).
5. Dashboards last.
6. Service Connectors last (reference everything).

## Gaps to always flag

- **FIFO SQS queues:** CRITICAL — OCI has no strict-FIFO guarantee.
- **SNS HTTP (non-TLS):** CRITICAL — OCI requires HTTPS.
- **SNS application/mobile-push:** CRITICAL — no OCI equivalent.
- **Logs Insights queries:** LOW — query dialect differs; operator must port.
- **Custom metric namespaces** (`CWAgent`, app-emitted): HIGH — Compute Agent must be enabled on the target instance and the metric name must be re-published.
- **CloudWatch Contributor Insights:** CRITICAL — no OCI equivalent.
- **X-Ray tracing**: if any alarm references X-Ray metrics, flag CRITICAL (no OCI equivalent today).
