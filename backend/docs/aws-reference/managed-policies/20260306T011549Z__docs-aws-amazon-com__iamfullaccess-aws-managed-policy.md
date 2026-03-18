---
title: "IAMFullAccess - AWS Managed Policy"
source: "https://docs.aws.amazon.com/aws-managed-policy/latest/reference/IAMFullAccess.html"
fetched: "20260306T011549Z"
---

# IAMFullAccess

**Description**: Provides full access to IAM via the AWS Management Console.

`IAMFullAccess` is an AWS managed policy.

## Using this policy

You can attach `IAMFullAccess` to your users, groups, and roles.

## Policy details

  - **Type**: AWS managed policy

  - **Creation time**: February 06, 2015, 18:40 UTC

  - **Edited time:** June 21, 2019, 19:40 UTC

  - **ARN**: `arn:aws:iam::aws:policy/IAMFullAccess`

## Policy version

**Policy version:** v2 (default)

The policy's default version is the version that defines the permissions for the policy. When a user or role with the policy makes a request to access an AWS resource, AWS checks the default version of the policy to determine whether to allow the request.

## JSON policy document

    {
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : [
            "iam:*",
            "organizations:DescribeAccount",
            "organizations:DescribeOrganization",
            "organizations:DescribeOrganizationalUnit",
            "organizations:DescribePolicy",
            "organizations:ListChildren",
            "organizations:ListParents",
            "organizations:ListPoliciesForTarget",
            "organizations:ListRoots",
            "organizations:ListPolicies",
            "organizations:ListTargetsForPolicy"
          ],
          "Resource" : "*"
        }
      ]
    }

## Learn more