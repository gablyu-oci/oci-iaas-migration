# OCI Serverless and Event-Driven Services — IAM Permissions Reference

## Overview

OCI provides serverless and event-driven services that map to AWS Lambda, API Gateway, SQS, SNS, EventBridge, Step Functions, and Kinesis.

## Service Mapping (AWS → OCI)

| AWS Service | OCI Equivalent | Resource Type |
|---|---|---|
| Lambda | Functions (Oracle Functions) | `fn-function`, `fn-app`, `fn-invocation` |
| API Gateway | API Gateway | `api-gateway-family` |
| SQS | Queue (OCI Queue) | `queues` |
| SNS | Notifications (ONS) | `ons-family` |
| EventBridge | Events | `cloudevents-rules` |
| Step Functions | Service Connector Hub | `serviceconnector` |
| Kinesis | Streaming (OCI Streaming) | `stream-family` |
| SES | Email Delivery | `email-family` |

## Oracle Functions (fn-function)

Maps to AWS Lambda.

### Resource Types
- `fn-app` — Application (logical container for functions)
- `fn-function` — Individual function
- `fn-invocation` — Function invocations (used for invoke-only access)

### Verbs
| Verb | Allowed Operations |
|---|---|
| `inspect` | List applications and functions |
| `read` | Get function details, view logs |
| `use` | Invoke functions |
| `manage` | Create, update, delete applications and functions |

### Example Policies
```
Allow group FunctionDevelopers to manage fn-app in compartment ServerlessApps
Allow group FunctionDevelopers to manage fn-function in compartment ServerlessApps
Allow group AppServers to use fn-invocation in compartment ServerlessApps
Allow service faas to use virtual-network-family in compartment ServerlessApps
Allow service faas to read repos in tenancy
```

### Note on Service Policies for Functions
Functions require the OCI Functions service (faas) to access other resources:
```
Allow service faas to manage objects in compartment Production
Allow service faas to use secrets in compartment Production
```

## API Gateway

Maps to AWS API Gateway.

### Resource Types
- `api-gateway-family` — All API Gateway resources
- `api-gateways` — Gateway instances
- `api-deployments` — Deployed APIs

### Example Policies
```
Allow group APIGatewayAdmins to manage api-gateway-family in compartment Production
Allow service apigateway to use functions-family in compartment Production
```

## OCI Streaming (Kinesis equivalent)

Maps to AWS Kinesis Data Streams and Firehose.

### Resource Types
- `stream-family` — Group covering all streaming resources
- `streams` — Individual stream instances
- `connect-harness` — Kafka-compatible harness
- `stream-pools` — Stream pool configurations

### Verbs
| Verb | Allowed Operations |
|---|---|
| `inspect` | List streams |
| `read` | Get stream metadata |
| `use` | Produce to and consume from streams |
| `manage` | Create, update, delete streams and pools |

### Example Policies
```
Allow group StreamAdmins to manage stream-family in compartment DataPipeline
Allow group DataProducers to use streams in compartment DataPipeline
Allow group DataConsumers to use streams in compartment DataPipeline
```

## OCI Queue (SQS equivalent)

Maps to AWS SQS.

### Resource Types
- `queues` — Queue instances

### Example Policies
```
Allow group QueueAdmins to manage queues in compartment Messaging
Allow group AppServers to use queues in compartment Messaging
```

## OCI Notifications (ONS, SNS equivalent)

Maps to AWS SNS.

### Resource Types
- `ons-family` — All notification resources
- `ons-topics` — Notification topics
- `ons-subscriptions` — Topic subscriptions

### Example Policies
```
Allow group NotifAdmins to manage ons-family in compartment Messaging
Allow group AppServers to use ons-topics in compartment Messaging
```

## OCI Events (EventBridge equivalent)

Maps to AWS EventBridge.

### Resource Types
- `cloudevents-rules` — Event rules

### Example Policies
```
Allow group EventAdmins to manage cloudevents-rules in compartment Automation
Allow service cloudEvents to use fn-invocation in compartment Automation
Allow service cloudEvents to use stream-push in compartment Automation
```

## Service Connector Hub (Step Functions orchestration)

### Resource Types
- `serviceconnector` — Connector instances

### Example Policies
```
Allow group ConnectorAdmins to manage serviceconnector in compartment DataPipeline
Allow resource serviceconnector to manage objects in compartment DataPipeline
```

## AWS → OCI IAM Action Mapping

| AWS Action | OCI Equivalent Policy |
|---|---|
| `lambda:CreateFunction` | `manage fn-function` |
| `lambda:InvokeFunction` | `use fn-invocation` |
| `lambda:DeleteFunction` | `manage fn-function` |
| `lambda:GetFunction` | `read fn-function` |
| `lambda:ListFunctions` | `inspect fn-function` |
| `lambda:UpdateFunctionCode` | `manage fn-function` |
| `sqs:CreateQueue` | `manage queues` |
| `sqs:DeleteQueue` | `manage queues` |
| `sqs:SendMessage` | `use queues` |
| `sqs:ReceiveMessage` | `use queues` |
| `sns:CreateTopic` | `manage ons-topics` |
| `sns:Publish` | `use ons-topics` |
| `sns:Subscribe` | `manage ons-subscriptions` |
| `kinesis:PutRecord` | `use streams` |
| `kinesis:GetRecords` | `use streams` |
| `kinesis:CreateStream` | `manage streams` |
| `events:PutRule` | `manage cloudevents-rules` |
| `execute-api:Invoke` | `use api-deployments` |
