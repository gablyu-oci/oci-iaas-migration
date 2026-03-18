---
title: "PowerUserAccess - AWS Managed Policy"
source: "https://docs.aws.amazon.com/aws-managed-policy/latest/reference/PowerUserAccess.html"
fetched: "20260306T011549Z"
---

# PowerUserAccess

**Description**: Provides full access to AWS services and resources, but does not allow management of Users and groups.

`PowerUserAccess` is an AWS managed policy.

## Using this policy

You can attach `PowerUserAccess` to your users, groups, and roles.

## Policy details

  - **Type**: AWS managed policy

  - **Creation time**: February 06, 2015, 18:39 UTC

  - **Edited time:** February 12, 2026, 17:59 UTC

  - **ARN**: `arn:aws:iam::aws:policy/PowerUserAccess`

## Policy version

**Policy version:** v12 (default)

The policy's default version is the version that defines the permissions for the policy. When a user or role with the policy makes a request to access an AWS resource, AWS checks the default version of the policy to determine whether to allow the request.

## JSON policy document

    {
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "NotAction" : [
            "iam:*",
            "organizations:*",
            "account:*"
          ],
          "Resource" : "*"
        },
        {
          "Effect" : "Allow",
          "Action" : [
            "account:GetAccountInformation",
            "account:GetGovCloudAccountInformation",
            "account:GetPrimaryEmail",
            "account:ListRegions",
            "iam:CreateServiceLinkedRole",
            "iam:DeleteServiceLinkedRole",
            "iam:ListRoles",
            "organizations:DescribeEffectivePolicy",
            "organizations:DescribeOrganization"
          ],
          "Resource" : "*"
        }
      ]
    }

## Learn more