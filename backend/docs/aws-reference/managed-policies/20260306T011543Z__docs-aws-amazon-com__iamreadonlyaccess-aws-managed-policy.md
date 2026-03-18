---
title: "IAMReadOnlyAccess - AWS Managed Policy"
source: "https://docs.aws.amazon.com/aws-managed-policy/latest/reference/IAMReadOnlyAccess.html"
fetched: "20260306T011543Z"
---

# IAMReadOnlyAccess

**Description**: Provides read only access to IAM via the AWS Management Console.

`IAMReadOnlyAccess` is an AWS managed policy.

## Using this policy

You can attach `IAMReadOnlyAccess` to your users, groups, and roles.

## Policy details

  - **Type**: AWS managed policy

  - **Creation time**: February 06, 2015, 18:40 UTC

  - **Edited time:** January 25, 2018, 19:11 UTC

  - **ARN**: `arn:aws:iam::aws:policy/IAMReadOnlyAccess`

## Policy version

**Policy version:** v4 (default)

The policy's default version is the version that defines the permissions for the policy. When a user or role with the policy makes a request to access an AWS resource, AWS checks the default version of the policy to determine whether to allow the request.

## JSON policy document

    {
      "Version" : "2012-10-17",
      "Statement" : [
        {
          "Effect" : "Allow",
          "Action" : [
            "iam:GenerateCredentialReport",
            "iam:GenerateServiceLastAccessedDetails",
            "iam:Get*",
            "iam:List*",
            "iam:SimulateCustomPolicy",
            "iam:SimulatePrincipalPolicy"
          ],
          "Resource" : "*"
        }
      ]
    }

## Learn more