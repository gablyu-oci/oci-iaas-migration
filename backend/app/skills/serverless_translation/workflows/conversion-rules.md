# AWS Serverless / Containers → OCI Functions / API Gateway / OKE Conversion Rules

Prose guidance that doesn't fit in the mapping table.

## Service-level mapping

| AWS service | OCI target | Terraform resources |
|---|---|---|
| Lambda | Functions | `oci_functions_application`, `oci_functions_function` |
| Lambda Layer | **No equivalent** — bake into function's container image |
| Lambda EventSourceMapping | Service Connector Hub | `oci_sch_service_connector` |
| API Gateway v1 (REST) | API Gateway | `oci_apigateway_gateway`, `oci_apigateway_deployment` |
| API Gateway v2 (HTTP) | API Gateway | Same as v1 |
| API Gateway v2 (WebSocket) | **No equivalent** — flag CRITICAL, route to Streaming |
| Step Functions | **No equivalent** — flag CRITICAL |
| EventBridge Rule | Events Service | `oci_events_rule` |
| EventBridge custom bus | **No equivalent** — OCI has one per-tenancy stream |
| Kinesis Data Stream | Streaming | `oci_streaming_stream` |
| Kinesis Firehose | Service Connector Hub | `oci_sch_service_connector` |
| ECS Service (+ task def) | Container Instances | `oci_container_instances_container_instance` |
| ECS with EC2 launch type | OKE | `oci_containerengine_cluster` + `oci_containerengine_node_pool` |
| EKS Cluster | OKE | `oci_containerengine_cluster` |
| EKS Nodegroup | OKE Node Pool | `oci_containerengine_node_pool` |
| ECR Repository | OCIR | `oci_artifacts_container_repository` |

## Lambda → OCI Functions

### Application first

OCI Functions requires an **Application** scope before any function. Emit exactly one `oci_functions_application` per migration target, referenced by every function:

```hcl
resource "oci_functions_application" "main" {
  compartment_id = var.compartment_ocid
  display_name   = "migration-app"
  subnet_ids     = [var.functions_subnet_ocid]
}
```

### Function translation

| Lambda property | OCI Function property | Notes |
|---|---|---|
| `Runtime: nodejs20.x` | `image = "<region>.ocir.io/<tenancy>/node20-func:latest"` | OCIR path expected |
| `Runtime: python3.12` | `image = "python312-func:latest"` | |
| `Runtime: java17` | `image = "java17-func:latest"` | |
| `Runtime: provided.al2` (custom) | Build custom Docker image | CRITICAL — not automatic |
| `Handler` | Baked into image's entrypoint | Not a separate HCL field |
| `MemorySize` | `memory_in_mbs` | Must be 128/256/512/1024/2048 (OCI only allows these) |
| `Timeout` | `timeout_in_seconds` | Max 300 s (AWS allows 900 s — flag if > 300) |
| `Environment.Variables` | `config` | Same shape (string→string map) |
| `VpcConfig` | Inherited from application's `subnet_ids` | No per-function VPC override |
| `DeadLetterConfig` | **No equivalent** — emit as OCI Notifications topic with manual dispatch |
| `Layers` | **NOT supported** — CRITICAL. Bundle layer contents into the image |
| `ReservedConcurrentExecutions` | `provisioned_concurrency_config` | Approximate — OCI model differs |

### Code / image pipeline

OCI Functions requires a Docker image in OCIR before deployment. For the HCL output:

1. Emit the `oci_artifacts_container_repository` first.
2. Emit a `# TODO:` comment near each function explaining the image-build step (user must run `fn build` + `docker push` before `terraform apply` succeeds).
3. Reference the image as `var.<function_name>_image_tag` so the user can override per environment.

### Triggers

Lambda's `EventSourceMapping` becomes OCI Service Connector Hub flows (Streaming → Function, Queue → Function, Object Storage → Function). Don't emit one-to-one — aggregate and comment.

## API Gateway

### v1 REST → OCI API Gateway

| AWS concept | OCI equivalent |
|---|---|
| REST API | `oci_apigateway_gateway` + `oci_apigateway_deployment` |
| Resource (`/users/{id}`) | Route in `deployment.specification.routes` |
| Method (GET/POST/…) | `methods` array per route |
| Integration type `AWS_PROXY` (Lambda) | `type = "ORACLE_FUNCTIONS_BACKEND"` |
| Integration type `HTTP_PROXY` | `type = "HTTP_BACKEND"` |
| Integration type `MOCK` | `type = "STOCK_RESPONSE_BACKEND"` |
| Stage | Deployment `path_prefix` (e.g., `/v1`, `/prod`) |
| Custom domain | `oci_apigateway_gateway` with `certificate_id` |

### v2 HTTP API → OCI API Gateway (same target)

Simpler translation: HTTP APIs have fewer features, so the mapping is 1:1.

### v2 WebSocket API

**No OCI API Gateway equivalent.** Flag CRITICAL. Suggest one of:
- OCI Streaming for pub/sub semantics (lose client-side WS protocol).
- Self-hosted WS server on OKE.

### Authorizers

- Lambda Authorizer → OCI function-based authorizer (`oci_apigateway_deployment.specification.request_policies.authentication.type = "CUSTOM_AUTHENTICATION"`).
- JWT Authorizer (Cognito) → `type = "JWT_AUTHENTICATION"` with issuer URL + audiences.
- IAM auth → OCI instance principal / resource principal auth; flag MEDIUM.
- API Key → OCI API Gateway usage plans. Flag LOW.

## Step Functions

**No equivalent in OCI.** Always flag CRITICAL. Options to present:
1. Rewrite state machine logic inside a single OCI Function (simple cases).
2. Chain OCI Functions via Events service (moderate cases).
3. Use OCI Data Integration for ETL-shaped workflows.
4. Self-host Temporal / Airflow on OKE for complex cases.

Do NOT attempt to emit HCL for a state machine — the translation is always manual.

## EventBridge

- `AWS::Events::Rule` with `EventPattern` → `oci_events_rule` with `condition` (JSON-schema).
- Targets:
  - Lambda → OCI Function (same rule, `actions.function_id`).
  - SQS → OCI Queue (`actions.topic_id` on a topic that fans out to the queue).
  - SNS → OCI Notifications topic (`actions.topic_id`).
  - Step Functions → Flag CRITICAL (see above).
- Custom event buses → OCI has only the default tenancy bus; emit a note.
- `ScheduleExpression` (cron rules) → OCI Events supports cron via rule `condition.type = "TIMER"`.

## Kinesis

- Shards → partitions (1:1).
- Retention (24h default) → `retention_in_hours` on `oci_streaming_stream` (1–168 hours).
- Kinesis Firehose → Service Connector Hub with:
  - source: Streaming / Logging / Monitoring
  - optional Function transform
  - target: Object Storage / Streaming / Logging

## Containers

### ECS → Container Instances OR OKE

Decision flow:
- ECS Service count = 1 or trivial, no autoscaling → **Container Instances** (single-container, simpler HCL).
- ECS Service with desired_count > 1 or autoscaling → **OKE** with a Kubernetes Deployment.
- ECS with EC2 launch type → **OKE** (the AWS EC2 layer is now unnecessary).

For Container Instances:
```hcl
resource "oci_container_instances_container_instance" "app" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  shape               = "CI.Standard.E4.Flex"
  shape_config {
    ocpus         = 1
    memory_in_gbs = 2
  }
  containers {
    image_url   = "<ocir-path>:<tag>"
    display_name = "app"
  }
  vnics {
    subnet_id = var.app_subnet_ocid
  }
}
```

For OKE, emit cluster + one node pool. A separate Kubernetes manifest (Deployment, Service) is required downstream — emit a `# TODO:` comment pointing to it.

### EKS → OKE

Straightforward. Propagate:
- `Version` → `kubernetes_version` (OCI supports up to one minor behind latest).
- `ResourcesVpcConfig.SubnetIds` → `endpoint_config.subnet_id` + `options.kubernetes_network_config`.
- Control-plane logging → OCI Logging log group (emit via observability_translation, not here).
- Nodegroups → `oci_containerengine_node_pool` with matching `size`, `node_shape`, and shape_config.

### ECR → OCIR

OCIR repo name convention: `<region>.ocir.io/<tenancy>/<repo-name>:<tag>`. Rewrite every `image = "<aws-acct>.dkr.ecr.<region>.amazonaws.com/..."` to the OCIR path. This is purely a string rewrite, no new HCL field.

**Auth differs:** OCIR requires an auth token on the user (not a role-based token like ECR). Emit a `# TODO: generate an auth token` comment.

## Cross-cutting

### Cold start + memory

Lambda tolerates 128 MB and sub-second cold starts. OCI Functions minimum is 128 MB but cold starts can be 1–3 s for large images. Flag MEDIUM for latency-sensitive functions.

### X-Ray / tracing

No OCI equivalent today (Application Performance Monitoring is close but requires separate HCL). Emit a TODO.

## Gaps to always flag

- **Lambda Layers:** CRITICAL on every function that uses them.
- **WebSocket APIs:** CRITICAL — no OCI equivalent.
- **Step Functions:** CRITICAL — always manual.
- **ECS EC2 launch type:** HIGH — recommend rewriting to OKE.
- **Cognito User Pools (if any API auth uses them):** CRITICAL — flag and defer to IDCS migration.
- **Lambda @ Edge:** CRITICAL — no OCI edge compute.
- **Kinesis Analytics SQL apps:** CRITICAL — must be rewritten as OCI Functions or Data Flow.
- **Custom runtimes** (`provided.al2`): HIGH — user must build a compatible Docker image.
