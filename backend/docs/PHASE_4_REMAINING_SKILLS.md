# Phase 4: Remaining Skills Migration to Templates + Structured Output

## Overview

Phase 4 completes the migration of all remaining translation skills to the
templates + structured output architecture introduced in Phase 1. Where Phase 1
converted three skills (network, load balancer, OCM handoff), Phase 4 migrates
the remaining six: **ec2**, **storage**, **iam**, **security**, **serverless**,
and **observability**.

Each skill's writer now emits a JSON array of `{ template, label, params }`
specs instead of raw HCL. The rendering pipeline resolves those specs against
Jinja2 templates and produces validated Terraform files, giving us consistent
output, deterministic formatting, and built-in schema validation across the
entire translation layer.

---

## AWS Type to OCI Template Maps

### ec2_translation

| AWS Type | OCI Template | OCI Resource |
|---|---|---|
| AWS::EC2::Instance | core/instance | oci_core_instance |
| AWS::AutoScaling::AutoScalingGroup | core/instance_pool + core/autoscaling_configuration | oci_core_instance_pool + oci_autoscaling_auto_scaling_configuration |
| AWS::AutoScaling::LaunchConfiguration | core/instance_configuration | oci_core_instance_configuration |
| AWS::EC2::LaunchTemplate | core/instance_configuration | oci_core_instance_configuration |
| AWS::EC2::Image | (no template - boot volume source_id) | - |
| AWS::EC2::KeyPair | (metadata on instance) | - |
| Root EBS Volume | core/boot_volume | oci_core_boot_volume |

### storage_translation

| AWS Type | OCI Template | OCI Resource |
|---|---|---|
| AWS::EC2::Volume | core/block_volume | oci_core_volume |
| AWS::EC2::VolumeAttachment | core/block_volume_attachment | oci_core_volume_attachment |
| AWS::S3::Bucket | free_form_hcl | oci_objectstorage_bucket |
| AWS::EFS::FileSystem | free_form_hcl | oci_file_storage_file_system |

### iam_translation

| AWS Type | OCI Template | OCI Resource |
|---|---|---|
| AWS::IAM::Role | identity/dynamic_group + identity/policy | oci_identity_dynamic_group + oci_identity_policy |
| AWS::IAM::Policy | identity/policy | oci_identity_policy |
| AWS::IAM::User | identity/user | oci_identity_user |
| AWS::IAM::Group | identity/group | oci_identity_group |
| AWS::IAM::InstanceProfile | identity/dynamic_group | oci_identity_dynamic_group |

### security_translation

| AWS Type | OCI Template | OCI Resource |
|---|---|---|
| AWS::KMS::Key | vault/vault + vault/key | oci_kms_vault + oci_kms_key |
| AWS::SecretsManager::Secret | vault/secret | oci_vault_secret |
| AWS::SSM::Parameter | vault/secret | oci_vault_secret |
| AWS::WAFv2::WebACL | free_form_hcl | oci_waf_web_app_firewall |

### serverless_translation

| AWS Type | OCI Template | OCI Resource |
|---|---|---|
| AWS::Lambda::Function | functions/application + functions/function | oci_functions_application + oci_functions_function |
| AWS::ECS::Service | free_form_hcl | oci_container_instances_container_instance |
| AWS::EKS::Cluster | free_form_hcl | oci_containerengine_cluster |

### observability_translation

| AWS Type | OCI Template | OCI Resource |
|---|---|---|
| AWS::Logs::LogGroup | observability/log_group | oci_logging_log_group |
| AWS::Logs::LogStream | observability/log | oci_logging_log |
| AWS::CloudWatch::Alarm | observability/metric_alarm | oci_monitoring_alarm |
| AWS::SNS::Topic | free_form_hcl | oci_ons_notification_topic |
| AWS::SQS::Queue | free_form_hcl | oci_queue_queue |

---

## Skills NOT Migrated

The following skills were intentionally left out of the structured output
migration:

- **cfn_terraform** -- Free-form by design. This skill translates raw
  CloudFormation into Terraform and does not map to a fixed set of OCI resource
  templates.
- **data_migration_planning** -- Markdown only. This skill produces a prose
  migration runbook, not Terraform HCL.

---

## Template Count Summary

| Phase | Templates Added | Running Total |
|---|---|---|
| Phase 1 (network, load balancer, OCM) | 22 | 22 |
| Phase 4 (ec2, storage, iam, security, serverless, observability) | 19 | 41 |
