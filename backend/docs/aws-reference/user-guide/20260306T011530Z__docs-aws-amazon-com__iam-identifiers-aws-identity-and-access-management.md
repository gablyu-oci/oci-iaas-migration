---
title: "IAM identifiers - AWS Identity and Access Management"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html"
fetched: "20260306T011530Z"
---

# IAM identifiers

IAM uses a few different identifiers for users, IAM groups, roles, policies, and server certificates. This section describes the identifiers and when you use each.

## Friendly names and paths

When you create a user, a role, a user group, or a policy, or when you upload a server certificate, you give it a friendly name. Examples include Bob, TestApp1, Developers, ManageCredentialsPermissions, or ProdServerCert.

If you use the IAM API or AWS Command Line Interface (AWS CLI) to create IAM resources, you can add an optional path. You can use a single path, or nest multiple paths as a folder structure. For example, you could use the nested path `/division_abc/subdivision_xyz/product_1234/engineering/` to match your company organizational structure. You could then create a policy to allow all users in that path to access the policy simulator API. To view this policy, see IAM: Access the policy simulator API based on user path. For information about how a friendly name can be specified, see the User API documentation. For additional examples of how you might use paths, see IAM ARNs.

When you use CloudFormation to create resources, you can specify a path for users, IAM groups, and roles, and customer managed policies.

If you have a user and user group in the same path, IAM doesn't automatically put the user in that user group. For example, you might create a Developers user group and specify the path as `/division_abc/subdivision_xyz/product_1234/engineering/`. If you create a user named Bob and add the same path to him, this doesn't automatically put Bob in the Developers user group. IAM doesn't enforce any boundaries between users or IAM groups based on their paths. Users with different paths can use the same resources if they've been granted permission to those resources. The number and size of IAM resources in an AWS account are limited. For more information, see IAM and AWS STS quotas.

## IAM ARNs

Most resources have a friendly name for example, a user named `Bob` or a user group named `Developers`. However, the permissions policy language requires you to specify the resource or resources using the following *Amazon Resource Name (ARN)* format.

    arn:partition:service:region:account:resource

Where:

  - `partition` identifies the partition for the resource. For standard AWS Regions, the partition is `aws`. If you have resources in other partitions, the partition is `aws-partitionname`. For example, the partition for resources in the China (Beijing) Region is `aws-cn`. You cannot delegate access between accounts in different partitions.

  - `service` identifies the AWS product. IAM resources always use `iam`.

  - `region` identifies the Region of the resource. For IAM resources, this is always kept blank.

  - `account` specifies the AWS account ID with no hyphens.

  - `resource` identifies the specific resource by name.

You can specify IAM and AWS STS ARNs using the following syntax. The Region portion of the ARN is blank because IAM resources are global.

Syntax:

``` 
arn:aws:iam::account:root  
arn:aws:iam::account:user/user-name-with-path
arn:aws:iam::account:group/group-name-with-path
arn:aws:iam::account:role/role-name-with-path
arn:aws:iam::account:policy/policy-name-with-path
arn:aws:iam::account:instance-profile/instance-profile-name-with-path
arn:aws:sts::account:federated-user/user-name
arn:aws:sts::account:assumed-role/role-name/role-session-name
arn:aws:sts::account:self
arn:aws:iam::account:mfa/virtual-device-name-with-path
arn:aws:iam::account:u2f/u2f-token-id
arn:aws:iam::account:server-certificate/certificate-name-with-path
arn:aws:iam::account:saml-provider/provider-name
arn:aws:iam::account:oidc-provider/provider-name
arn:aws:iam::aws:contextProvider/context-provider-name
    
```

Many of the following examples include paths in the resource part of the ARN. Paths cannot be created or manipulated in the AWS Management Console. To use paths, you must work with the resource by using the AWS API, the AWS CLI, or the Tools for Windows PowerShell.

Examples:

    arn:aws:iam::123456789012:root
    arn:aws:iam::123456789012:user/John
    arn:aws:iam::123456789012:user/division_abc/subdivision_xyz/Jane
    arn:aws:iam::123456789012:group/Developers
    arn:aws:iam::123456789012:group/division_abc/subdivision_xyz/product_A/Developers
    arn:aws:iam::123456789012:role/S3Access
    arn:aws:iam::123456789012:role/application_abc/component_xyz/RDSAccess
    arn:aws:iam::123456789012:role/aws-service-role/access-analyzer.amazonaws.com/AWSServiceRoleForAccessAnalyzer
    arn:aws:iam::123456789012:role/service-role/QuickSightAction
    arn:aws:iam::123456789012:policy/UsersManageOwnCredentials
    arn:aws:iam::123456789012:policy/division_abc/subdivision_xyz/UsersManageOwnCredentials
    arn:aws:iam::123456789012:instance-profile/Webserver
    arn:aws:sts::123456789012:federated-user/John
    arn:aws:sts::123456789012:assumed-role/Accounting-Role/Jane
    arn:aws:sts::123456789012:self
    arn:aws:iam::123456789012:mfa/JaneMFA
    arn:aws:iam::123456789012:u2f/user/John/default (U2F security key)
    arn:aws:iam::123456789012:server-certificate/ProdServerCert
    arn:aws:iam::123456789012:server-certificate/division_abc/subdivision_xyz/ProdServerCert
    arn:aws:iam::123456789012:saml-provider/ADFSProvider
    arn:aws:iam::123456789012:oidc-provider/GoogleProvider
    arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-west-2.amazonaws.com/id/a1b2c3d4567890abcdefEXAMPLE11111
    arn:aws:iam::123456789012:oidc-provider/server.example.org
    arn:aws:iam::aws:contextProvider/IdentityCenter

The following examples provide more detail to help you understand the ARN format for different types of IAM and AWS STS resources.

  - An IAM user in the account:
    
    
    
    
    
    Each IAM user name is unique. The user name is case-insensitive for the user, such as during the sign in process, but is case-sensitive when you use it in a policy or as part of an ARN.
    
    
    
    
    
        arn:aws:iam::123456789012:user/John

  - Another user with a path reflecting an organization chart:
    
        arn:aws:iam::123456789012:user/division_abc/subdivision_xyz/Jane

  - An IAM user group:
    
        arn:aws:iam::123456789012:group/Developers

  - An IAM user group with a path:
    
        arn:aws:iam::123456789012:group/division_abc/subdivision_xyz/product_A/Developers

  - An IAM role:
    
        arn:aws:iam::123456789012:role/S3Access

  - A service-linked role:
    
        arn:aws:iam::123456789012:role/aws-service-role/access-analyzer.amazonaws.com/AWSServiceRoleForAccessAnalyzer

  - A service role:
    
        arn:aws:iam::123456789012:role/service-role/QuickSightAction

  - A managed policy:
    
        arn:aws:iam::123456789012:policy/ManageCredentialsPermissions

  - An instance profile that can be associated with an Amazon EC2 instance:
    
        arn:aws:iam::123456789012:instance-profile/Webserver

  - An AWS STS federated user principal identified in IAM as "Paulo":
    
        arn:aws:sts::123456789012:federated-user/Paulo

  - The active session of someone assuming the role of "Accounting-Role", with a role session name of "Mary":
    
        arn:aws:sts::123456789012:assumed-role/Accounting-Role/Mary

  - Represents the caller's own session when used as a resource in an API call, such as the AWS STS SetContext API, that operates on the calling session:
    
        arn:aws:sts::123456789012:self

  - The multi-factor authentication device assigned to the user named Jorge:
    
        arn:aws:iam::123456789012:mfa/Jorge

  - A server certificate:
    
        arn:aws:iam::123456789012:server-certificate/ProdServerCert

  - A server certificate with a path that reflects an organization chart:
    
        arn:aws:iam::123456789012:server-certificate/division_abc/subdivision_xyz/ProdServerCert

  - Identity providers (SAML and OIDC):
    
        arn:aws:iam::123456789012:saml-provider/ADFSProvider
        arn:aws:iam::123456789012:oidc-provider/GoogleProvider
        arn:aws:iam::123456789012:oidc-provider/server.example.org

  - OIDC identity provider with a path that reflects an Amazon EKS OIDC identity provider URL:
    
        arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-west-2.amazonaws.com/id/a1b2c3d4567890abcdefEXAMPLE11111

  - The context provider ARN used with AWS IAM Identity Center trusted identity propagation, from which the trusted context assertion was generated:
    
        arn:aws:iam::aws:contextProvider/IdentityCenter

Another important ARN is the root user ARN. Although this is not an IAM resource, you should be familiar with the format of this ARN. It is often used in the Principal element of a resource-based policy.

The following example shows a policy you could assign to Richard to allow him to manage his access keys. Notice that the resource is the IAM user Richard.

  - JSON
    
    
    
      - ****
        
            {
                "Version":"2012-10-17",              
                "Statement": [
                    {
                        "Sid": "ManageRichardAccessKeys",
                        "Effect": "Allow",
                        "Action": [
                            "iam:*AccessKey*",
                            "iam:GetUser"
                        ],
                        "Resource": "arn:aws:iam::*:user/division_abc/subdivision_xyz/Richard"
                    },
                    {
                        "Sid": "ListForConsole",
                        "Effect": "Allow",
                        "Action": "iam:ListUsers",
                        "Resource": "*"
                    }
                ]
            }
    
    

When you use ARNs to identify resources in an IAM policy, you can include *policy variables*. Policy variables can include placeholders for runtime information (such as the user's name) as part of the ARN. For more information, see IAM policy elements: Variables and tags

### Using wildcards and paths in ARNs

You can use wildcards in the `resource` portion of the ARN to specify multiple users or IAM groups or policies. For example, to specify all users working on product\_1234, you use:

    arn:aws:iam::123456789012:user/division_abc/subdivision_xyz/product_1234/*

If you have users whose names start with the string `app_`, you could refer to them all with the following ARN.

    arn:aws:iam::123456789012:user/division_abc/subdivision_xyz/product_1234/app_*

To specify all users, IAM groups, or policies in your AWS account, use a wildcard after the `user/`, `group/`, or `policy/` part of the ARN, respectively.

    arn:aws:iam::123456789012:user/*
    arn:aws:iam::123456789012:group/*
    arn:aws:iam::123456789012:policy/*

If you specify the following ARN for a user `arn:aws:iam::111122223333:user/*` it matches both of the following examples.

    arn:aws:iam::111122223333:user/John
    arn:aws:iam::111122223333:user/division_abc/subdivision_xyz/JaneDoe

But, if you specify the following ARN for a user `arn:aws:iam::111122223333:user/division_abc*` it matches the second example, but not the first.

    arn:aws:iam::111122223333:user/John
    arn:aws:iam::111122223333:user/division_abc/subdivision_xyz/Jane

Don't use a wildcard in the `user/`, `group/`, or `policy/` part of the ARN. For example, IAM does not allow the following:

    arn:aws:iam::123456789012:u*

When you specify an incomplete ARN (one with fewer than the standard six fields) in an identity-based policy, AWS automatically completes the ARN by adding wildcard characters (\*) to all missing fields. For example, specifying `arn:aws:sqs` is equivalent to `arn:aws:sqs:*:*:*`, which grants access to all Amazon SQS resources across all regions and accounts.

###### Example use of paths and ARNs for a project-based user group

Paths cannot be created or manipulated in the AWS Management Console. To use paths you must work with the resource by using the AWS API, the AWS CLI, or the Tools for Windows PowerShell.

In this example, Jules in the Marketing\_Admin user group creates a project-based user group within the /marketing/ path. Jules assigns users from different parts of the company to the user group. This example illustrates that a user's path isn't related to the user groups the user is in.

The marketing group has a new product they'll be launching, so Jules creates a new user group in the /marketing/ path called Widget\_Launch. Jules then assigns the following policy to the user group, which gives the user group access to objects in the part of the `example_bucket` that is designated to this particular launch.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Effect": "Allow",
                  "Action": "s3:*",
                  "Resource": "arn:aws:s3:::example_bucket/marketing/newproductlaunch/widget/*"
                },
                {
                  "Effect": "Allow",
                  "Action": "s3:ListBucket*",
                  "Resource": "arn:aws:s3:::example_bucket",
                  "Condition": {"StringLike": {"s3:prefix": "marketing/newproductlaunch/widget/*"}}
                }
              ]
            }
    
    

Jules then assigns the users who are working on this launch to the user group. This includes Patricia and Eli from the /marketing/ path. It also includes Chris and Chloe from the /sales/ path, and Alice and Jim from the /legal/ path.

## Unique identifiers

When IAM creates a user, user group, role, policy, instance profile, or server certificate, it assigns a unique ID to each resource. The unique ID looks like this:

`AIDAJQABLZS4A3QDU576Q`

For the most part, you use friendly names and ARNs when you work with IAM resources. That way you don't need to know the unique ID for a specific resource. However, the unique ID can sometimes be useful when it isn't practical to use friendly names.

One example reuses friendly names in your AWS account. Within your account, a friendly name for a user, user group, role, or policy must be unique. For example, you might create an IAM user named `John`. Your company uses Amazon S3 and has a bucket with folders for each employee. IAM user `John` is a member of an IAM user group named `User-S3-Access` with permissions that allows users access only to their own folders in the bucket. For an example of how you might create an identity-based policy that allows IAM users to access their own bucket object in S3 using the friendly name of users, see Amazon S3: Allows IAM users access to their S3 home directory, programmatically and in the console.

Suppose that the employee named John leaves your company and you delete the corresponding IAM user named `John`. But later another employee named John starts, and you create a new IAM user named `John`. You add the new IAM user named `John` to the existing IAM user group `User-S3-Access`. If the policy associated to the user group specifies the friendly IAM user name `John`, the policy allows the new John to access information that was left by the former John.

In general, we recommend that you specify the ARN for the resource in your policies instead of its unique ID. However, every IAM user has a unique ID, even if you create a new IAM user that reuses a friendly name you deleted before. In the example, the old IAM user `John` and the new IAM user `John` have different unique IDs. You can create resource-based policies that grant access by unique ID and not just by user name. Doing so reduces the chance that you could inadvertently grant access to information that an employee should not have.

The following example shows how you might specify unique IDs in the Principal element of a resource-based policy.

    "Principal": {
      "AWS": [
        "arn:aws:iam::111122223333:role/role-name",
        "AIDACKCEVSQ6C2EXAMPLE",
        "AROADBQP57FF2AEXAMPLE"
      }

The following example shows how you might specify unique IDs in the Condition element of a policy using global condition key aws:userid.

    "Condition": {
        "StringLike": {
          "aws:userId": [
            "AIDACKCEVSQ6C2EXAMPLE",
            "AROADBQP57FF2AEXAMPLE:role-session-name",
            "AROA1234567890EXAMPLE:*",
            "111122223333"
          ]
        }
      }

Another example where user IDs can be useful is if you maintain your own database (or other store) of IAM user or role information. The unique ID can provide a unique identifier for each IAM user or role you create. This is the case when you have IAM users or roles that reuse a name, as in the previous example.

## Understanding unique ID prefixes

IAM uses the following prefixes to indicate what type of resource each unique ID applies to. Prefixes may vary based on when they were created.

| Prefix | Resource type                                                                                                                                         |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| ABIA   | AWS STS service bearer token                                                                                                             |
| ACCA   | Context-specific credential                                                                                                                           |
| AGPA   | User group                                                                                                                                            |
| AIDA   | IAM user                                                                                                                                              |
| AIPA   | Amazon EC2 instance profile                                                                                                                           |
| AKIA   | Access key                                                                                                                                            |
| ANPA   | Managed policy                                                                                                                                        |
| ANVA   | Version in a managed policy                                                                                                                           |
| APKA   | Public key                                                                                                                                            |
| AROA   | Role                                                                                                                                                  |
| ASCA   | Certificate                                                                                                                                           |
| ASIA   | Temporary (AWS STS) access key IDs use this prefix, but are unique only in combination with the secret access key and the session token. |

## Getting the unique identifier

The unique ID for an IAM resource is not available in the IAM console. To get the unique ID, you can use the following AWS CLI commands or IAM API calls.

AWS CLI:

IAM API: