---
title: "AWS managed policies for job functions"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_job-functions.html"
fetched: "20260306T011550Z"
---

# AWS managed policies for job functions

We recommend using policies that grant least privilege, or granting only the permissions required to perform a task. The most secure way to grant least privilege is to write a custom policy with only the permissions needed by your team. You must create a process to allow your team to request more permissions when necessary. It takes time and expertise to create IAM customer managed policies that provide your team with only the permissions they need.

To get started adding permissions to your IAM identities (users, groups of users, and roles), you can use AWS managed policies. AWS managed policies cover common use cases and are available in your AWS account. AWS managed policies don't grant least privilege permissions. You must consider the security risk of granting your principals more permissions than they need to do their job.

You can attach AWS managed policies, including job functions, to any IAM identity. To switch to least privilege permissions, you can run AWS Identity and Access Management and Access Analyzer to monitor principals with AWS managed policies. After learning which permissions they are using, then you can write a custom policy or generate a policy with only the required permissions for your team. This is less secure, but provides more flexibility as you learn how your team is using AWS.

AWS managed policies for job functions are designed to closely align to common job functions in the IT industry. You can use these policies to grant the permissions needed to carry out the tasks expected of someone in a specific job function. These policies consolidate permissions for many services into a single policy that's easier to work with than having permissions scattered across many policies.

###### Use Roles to Combine Services

Some of the policies use IAM service roles to help you take advantage of features found in other AWS services. These policies grant access to `iam:passrole`, which allows a user with the policy to pass a role to an AWS service. This role delegates IAM permissions to the AWS service to carry out actions on your behalf.

You must create the roles according to your needs. For example, the Network Administrator policy allows a user with the policy to pass a role named "flow-logs-vpc" to the Amazon CloudWatch service. CloudWatch uses that role to log and capture IP traffic for VPCs created by the user.

To follow security best practices, the policies for job functions include filters that limit the names of valid roles that can be passed. This helps avoid granting unnecessary permissions. If your users do require the optional service roles, you must create a role that follows the naming convention specified in the policy. You then grant permissions to the role. Once that is done, the user can configure the service to use the role, granting it whatever permissions the role provides.

In the following sections, each policy's name is a link to the policy details page in the AWS Management Console. There you can see the policy document and review the permissions it grants.

## Administrator job function

**AWS managed policy name:** AdministratorAccess

**Use case:** This user has full access and can delegate permissions to every service and resource in AWS.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants all actions for all AWS services and for all resources in the account. For more information about the managed policy, see AdministratorAccess in *AWS Managed Policy Reference Guide*.

Before an IAM user or role can access the AWS Billing and Cost Management console with the permissions in this policy, you must first activate IAM user and role access. To do this, follow the instructions in Grant access to the billing console to delegate access to the billing console.

## Billing job function

**AWS managed policy name:** Billing

**Use case:** This user needs to view billing information, set up payments, and authorize payments. The user can monitor the costs accumulated for the entire AWS service.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants full permissions for managing billing, costs, payment methods, budgets, and reports. For additional cost management policy examples, see AWS Billing policy examples in the *AWS Billing and Cost Management User Guide*. For more information about the managed policy, see Billing in *AWS Managed Policy Reference Guide*.

Before an IAM user or role can access the AWS Billing and Cost Management console with the permissions in this policy, you must first activate IAM user and role access. To do this, follow the instructions in Grant access to the billing console to delegate access to the billing console.

## Database administrator job function

**AWS managed policy name:** DatabaseAdministrator

**Use case:** This user sets up, configures, and maintains databases in the AWS Cloud.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants permissions to create, configure, and maintain databases. It includes access to AWS database services, such as Amazon DynamoDB, Amazon Relational Database Service (RDS), and Amazon Redshift. View the policy for the full list of database services that this policy supports. For more information about the managed policy, see DatabaseAdministrator in *AWS Managed Policy Reference Guide*.

This job function policy supports the ability to pass roles to AWS services. The policy allows the `iam:PassRole` action for only those roles named in the following table. For more information, see Creating roles and attaching policies (console) later in this topic.

## Data scientist job function

**AWS managed policy name:** DataScientist

**Use case:** This user runs Hadoop jobs and queries. The user also accesses and analyzes information for data analytics and business intelligence.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants permissions to create, manage, and run queries on an Amazon EMR cluster and perform data analytics with tools such as Amazon QuickSight. The policy includes access to additional data scientist services, such as AWS Data Pipeline, Amazon EC2, Amazon Kinesis, Amazon Machine Learning, and SageMaker AI. View the policy for the full list of data scientist services that this policy supports. For more information about the managed policy, see DataScientist in *AWS Managed Policy Reference Guide*.

This job function policy supports the ability to pass roles to AWS services. One statement allows passing any role to SageMaker AI. Another statement allows the `iam:PassRole` action for only those roles named in the following table. For more information, see Creating roles and attaching policies (console) later in this topic.

## Developer power user job function

**AWS managed policy name:** PowerUserAccess

**Use case:** This user performs application development tasks and can create and configure resources and services that support AWS aware application development.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** The first statement of this policy uses the NotAction element to allow all actions for all AWS services and for all resources except AWS Identity and Access Management, AWS Organizations, and AWS Account Management. The second statement grants IAM permissions to create a service-linked role. This is required by some services that must access resources in another service, such as an Amazon S3 bucket. It also grants AWS Organizations permissions to view information about the user's organization, including the management account email and organization limitations. Although this policy limits IAM, AWS Organizations, it allows the user to perform all IAM Identity Center actions if IAM Identity Center is enabled. It also grants Account Management permissions to view which AWS Regions are enabled or disabled for the account.

## Network administrator job function

**AWS managed policy name:** NetworkAdministrator

**Use case:** This user is tasked with setting up and maintaining AWS network resources.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants permissions to create and maintain network resources in Auto Scaling, Amazon EC2, AWS Direct Connect, RouteÂ 53, Amazon CloudFront, Elastic Load Balancing, AWS Elastic Beanstalk, Amazon SNS, CloudWatch, CloudWatch Logs, Amazon S3, IAM, and Amazon Virtual Private Cloud. For more information about the managed policy, see NetworkAdministrator in *AWS Managed Policy Reference Guide*.

This job function requires the ability to pass roles to AWS services. The policy grants `iam:GetRole` and `iam:PassRole` for only those roles named in the following table. For more information, see Creating roles and attaching policies (console) later in this topic.

| Use case                                                                                                                               | Role name (\* is a wildcard) | Service role type to select                                                            | AWS managed policy to select                                                                                                                              |
| -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Allows Amazon VPC to create and manage logs in CloudWatch Logs on the user's behalf to monitor IP traffic going in and out of your VPC | flow-logs-\*    | Create a role with a trust policy as defined in the Amazon VPC User Guide | This use case does not have an existing AWS managed policy, but the documentation lists the required permissions. See Amazon VPC User Guide. |

## Read-only access

**AWS managed policy name:** ReadOnlyAccess

**Use case:** This user requires read-only access to every resource in an AWS account.

This user will also have access to read data in storage services like Amazon S3 buckets and Amazon DynamoDB tables.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants permissions to list, get, describe, and otherwise view resources and their attributes. It does not include mutating functions like create or delete. This policy does include read-only access to security-related AWS services, such as AWS Identity and Access Management and AWS Billing and Cost Management. View the policy for the full list of services and actions that this policy supports. For more information about the managed policy, see ReadOnlyAccess in *AWS Managed Policy Reference Guide*. If you need a similar policy that does not grant access to read data in storage services, see View-only user job function.

## MCP service actions full access

**AWS managed policy name:** AWSMcpServiceActionsFullAccess

**Use case:** This user requires access to AWS services using AWS MCP servers. This policy does not grant access to actions taken by an MCP service to other AWS services.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants permissions to call any AWS MCP service action. You can use when you do not need to specify permissions per AWS MCP service. It does not grant permissions to actions taken by the MCP service to other AWS services, those permissions must always be granted separately and in addition to MCP service actions. For more information about the managed policy, see AWSMcpServiceActionsFullAccess in *AWS Managed Policy Reference Guide*.

## Security auditor job function

**AWS managed policy name:** SecurityAudit

**Use case:** This user monitors accounts for compliance with security requirements. This user can access logs and events to investigate potential security breaches or potential malicious activity.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants permissions to view configuration data for many AWS services and to review their logs. For more information about the managed policy, see SecurityAudit in *AWS Managed Policy Reference Guide*.

## Support user job function

**AWS managed policy name:** AWSSupportAccess

**Use case:** This user contacts AWS Support, creates support cases, and views the status of existing cases.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants permissions to create and update Support cases. For more information about the managed policy, see AWSSupportAccess in *AWS Managed Policy Reference Guide*.

## System administrator job function

**AWS managed policy name:** SystemAdministrator

**Use case:** This user sets up and maintains resources for development operations.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants permissions to create and maintain resources across a large variety of AWS services, including AWS CloudTrail, Amazon CloudWatch, AWS CodeCommit, AWS CodeDeploy, AWS Config, AWS Directory Service, Amazon EC2, AWS Identity and Access Management, AWS Key Management Service, AWS Lambda, Amazon RDS, RouteÂ 53, Amazon S3, Amazon SES, Amazon SQS, AWS Trusted Advisor, and Amazon VPC. For more information about the managed policy, see SystemAdministrator in *AWS Managed Policy Reference Guide*.

This job function requires the ability to pass roles to AWS services. The policy grants `iam:GetRole` and `iam:PassRole` for only those roles named in the following table. For more information, see Creating roles and attaching policies (console) later in this topic. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

## View-only user job function

**AWS managed policy name:** ViewOnlyAccess

**Use case:** This user can view a list of AWS resources and basic metadata in the account across services. The user cannot read resource content or metadata that goes beyond the quota and list information for resources.

**Policy updates:** AWS maintains and updates this policy. For a history of changes for this policy, view the policy in the IAM console and then choose the **Policy versions** tab. For more information about job function policy updates, see Updates to AWS managed policies for job functions.

**Policy description:** This policy grants `List*`, `Describe*`, `Get*`, `View*`, and `Lookup*` access to resources for AWS services. To see what actions this policy includes for each service, see ViewOnlyAccess. For more information about the managed policy, see ViewOnlyAccess in *AWS Managed Policy Reference Guide*.

## Updates to AWS managed policies for job functions

These policies are all maintained by AWS and are kept up to date to include support for new services and new capabilities as they are added by AWS services. These policies cannot be modified by customers. You can make a copy of the policy and then modify the copy, but that copy is not automatically updated as AWS introduces new services and API operations.

For a job function policy, you can view the version history and the time and date of each update in the IAM console. To do this, use the links on this page to view the policy details. Then choose the **Policy versions** tab to view the versions. This page shows the last 25 versions of a policy. To view all of the versions for a policy, call the get-policy-version AWS CLI command or the GetPolicyVersion API operation.

You can have up to five versions of a customer managed policy, but AWS retains the full version history of AWS managed policies.