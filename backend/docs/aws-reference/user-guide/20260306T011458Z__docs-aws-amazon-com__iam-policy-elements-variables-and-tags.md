---
title: "IAM policy elements: Variables and tags"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_variables.html"
fetched: "20260306T011458Z"
---

# IAM policy elements: Variables and tags

Use AWS Identity and Access Management (IAM) policy variables as placeholders when you don't know the exact value of a resource or condition key when you write the policy.

If AWS cannot resolve a variable this might cause the entire statement to be invalid. For example, if you use the `aws:TokenIssueTime` variable, the variable resolves to a value only when the requester authenticated using temporary credentials (an IAM role). To prevent variables from causing invalid statements, use the ...IfExists condition operator.

## Introduction

In IAM policies, many actions allow you to provide a name for the specific resources that you want to control access to. For example, the following policy allows users to list, read, and write objects in the S3 bucket `amzn-s3-demo-bucket` for `marketing` projects.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Effect": "Allow",
                  "Action": ["s3:ListBucket"],      
                  "Resource": ["arn:aws:s3:::amzn-s3-demo-bucket"],
                  "Condition": {"StringLike": {"s3:prefix": ["marketing/*"]}}
                },
                {
                  "Effect": "Allow",
                  "Action": [
                    "s3:GetObject",
                    "s3:PutObject"
                  ],      
                  "Resource": ["arn:aws:s3:::amzn-s3-demo-bucket/marketing/*"]
                }
              ]
            }
    
    

In some cases, you might not know the exact name of the resource when you write the policy. You might want to generalize the policy so it works for many users without having to make a unique copy of the policy for each user. Instead of creating a separate policy for each user, we recommend you create a single group policy that works for any user in that group.

## Using variables in policies

You can define dynamic values inside policies by using *policy variables* that set placeholders in a policy.

Variables are marked using a **`$`** prefix followed by a pair of curly braces (**`{ }`**) that include the variable name of the value from the request.

When the policy is evaluated, the policy variables are replaced with values that come from the conditional context keys passed in the request. Variables can be used in identity-based policies, resource policies, service control policies, session policies, and VPC endpoint policies. Identity-based policies used as permissions boundaries also support policy variables.

Global condition context keys can be used as variables in requests across AWS services. Service specific condition keys can also be used as variables when interacting with AWS resources, but are only available when requests are made against resources which support them. For a list of context keys available for each AWS service and resource, see the *Service Authorization Reference*. Under certain circumstances, you canâ€™t populate global condition context keys with a value. To learn more about each key, see AWS global condition context keys.

  - Key names are case-insensitive. For example, `aws:CurrentTime` is equivalent to `AWS:currenttime`.

  - You can use any single-valued condition key as a variable. You can't use a multivalued condition key as a variable.

The following example shows a policy for an IAM role or user that replaces a specific resource name with a policy variable. You can reuse this policy by taking advantage of the `aws:PrincipalTag` condition key. When this policy is evaluated, `${aws:PrincipalTag/team}` allows the actions only if the bucket name ends with a team name from the `team` principal tag.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Effect": "Allow",
                  "Action": ["s3:ListBucket"],      
                  "Resource": ["arn:aws:s3:::amzn-s3-demo-bucket"],
                  "Condition": {"StringLike": {"s3:prefix": ["${aws:PrincipalTag/team}/*"]}}
                },
                {
                  "Effect": "Allow",
                  "Action": [
                    "s3:GetObject",
                    "s3:PutObject"
                  ],      
                  "Resource": ["arn:aws:s3:::amzn-s3-demo-bucket/${aws:PrincipalTag/team}/*"]
                }
              ]
            }
    
    

The variable is marked using a `$` prefix followed by a pair of curly braces (`{ }`). Inside the `${ }` characters, you can include the name of the value from the request that you want to use in the policy. The values you can use are discussed later on this page.

For details about this global condition key, see aws:PrincipalTag/tag-key in the list of global condition keys.

In order to use policy variables, you must include the `Version` element in a statement, and the version must be set to a version that supports policy variables. Variables were introduced in version `2012-10-17`. Earlier versions of the policy language don't support policy variables. If you don't include the `Version` element and set it to an appropriate version date, variables like `${aws:username}` are treated as literal strings in the policy.

A `Version` policy element is different from a policy version. The `Version` policy element is used within a policy and defines the version of the policy language. A policy version, on the other hand, is created when you change a customer managed policy in IAM. The changed policy doesn't overwrite the existing policy. Instead, IAM creates a new version of the managed policy. To learn more about the `Version` policy element see IAM JSON policy elements: Version. To learn more about policy versions, see Versioning IAM policies.

A policy that allows a principal to get objects from the /David path of an S3 bucket looks like this:

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Effect": "Allow",
                  "Action": [
                    "s3:GetObject"
                  ],
                  "Resource": [
                    "arn:aws:s3:::amzn-s3-demo-bucket/David/*"
                  ]
                }
              ]
            }

    

If this policy is attached to user `David`, that user get objects from his own S3 bucket, but you would have to create a separate policy for each user that includes the user's name. You would then attach each policy to the individual users.

By using a policy variable, you can create policies that can be reused. The following policy allows a user to get objects from an Amazon S3 bucket if the tag-key value for `aws:PrincipalTag` matches the tag-key `owner` value passed in the request.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [{
                "Sid": "AllowUnlessOwnedBySomeoneElse",
                "Effect": "Allow",
                "Action": ["s3:GetObject"],    
                "Resource": ["*"],
                "Condition": {
                    "StringEquals": {
                      "s3:ExistingObjectTag/owner": "${aws:PrincipalTag/owner}"
                    }
                  }
                }
              ]
            }
    
    

When you use a policy variable in place of a user like this, you don't have to have a separate policy for each individual user. In the following example, the policy is attached to an IAM role that is assumed by Product Managers using temporary security credentials. When a user makes a request to add an Amazon S3 object, IAM substitutes the `dept` tag value from the current request for the `${aws:PrincipalTag}` variable and evaluates the policy.

  - JSON
    
    
    
      - ****
        
            {
                "Version":"2012-10-17",              
                "Statement": [
                    {
                        "Sid": "AllowOnlyDeptS3Prefix",
                        "Effect": "Allow",
                        "Action": [
                            "s3:GetObject"
                        ],
                        "Resource": [
                            "arn:aws:s3:::amzn-s3-demo-bucket/${aws:PrincipalTag/dept}/*"
                        ]
                    }
                ]
            }
    
    

In some AWS services you can attach your own custom attributes to resources that are created by those services. For example, you can apply tags to Amazon S3 buckets or to IAM users. These tags are key-value pairs. You define the tag key name and the value that is associated with that key name. For example, you might create a tag with a `department` key and a `Human Resources` value. For more information about tagging IAM entities, see Tags for AWS Identity and Access Management resources. For information about tagging resources created by other AWS services, see the documentation for that service. For information about using Tag Editor, see Working with Tag Editor in the *AWS Management Console User Guide*.

You can tag IAM resources to simplify discovering, organizing, and tracking your IAM resources. You can also tag IAM identities to control access to resources or to tagging itself. To learn more about using tags to control access, see Controlling access to and for IAM users and roles using tags.

## Where you can use policy variables

You can use policy variables in the `Resource` element and in string comparisons in the `Condition` element.

### Resource element

You can use a policy variable in the `Resource` element, but only in the resource portion of the ARN. This portion of the ARN appears after the fifth colon (:). You can't use a variable to replace parts of the ARN before the fifth colon, such as the service or account. For more information about the ARN format, see IAM ARNs.

To replace part of an ARN with a tag value, surround the prefix and key name with `${ }`. For example, the following Resource element refers to only a bucket that is named the same as the value in the requesting user's department tag.

`"Resource":             ["arn:aws::s3:::amzn-s3-demo-bucket/${aws:PrincipalTag/department`}"\]

Many AWS resources use ARNs that contain a user-created name. The following IAM policy ensures that only intended users with matching access-project, access-application, and access-environment tag values can modify their resources. In addition, using \* wildcard matches, they are able to allow for custom resource name suffixes.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Sid": "AllowAccessBasedOnArnMatching",
                  "Effect": "Allow",
                  "Action": [
                    "sns:CreateTopic",
                    "sns:DeleteTopic"],      
                  "Resource": ["arn:aws:sns:*:*:${aws:PrincipalTag/access-project}-${aws:PrincipalTag/access-application}-${aws:PrincipalTag/access-environment}-*"
                  ]
                }
              ]
            } 
    
    

### Condition element

You can use a policy variable for `Condition` values in any condition that involves the string operators or the ARN operators. String operators include `StringEquals`, `StringLike`, and `StringNotLike`. ARN operators include `ArnEquals` and `ArnLike`. You can't use a policy variable with other operators, such as `Numeric`, `Date`, `Boolean`, `Binary`, `IP Address`, or `Null` operators. For more information about condition operators, see IAM JSON policy elements: Condition operators.

When referencing a tag in a `Condition` element expression, use the relevant prefix and key name as the condition key. Then use the value that you want to test in the condition value.

For example, the following policy example allows full access to users, but only if the tag `costCenter` is attached to the user. The tag must also have a value of either `12345` or `67890`. If the tag has no value, or has any other value, then the request fails.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Effect": "Allow",
                  "Action": [
                      "iam:*user*"
                   ],
                  "Resource": "*",
                  "Condition": {
                    "StringLike": {
                      "iam:ResourceTag/costCenter": [ "12345", "67890" ]
                    }
                  }
                }
              ]
            }
    
    

## Policy variables with no value

When policy variables reference a condition context key that has no value or is not present in an authorization context for a request, the value is effectively null. There is no equal or like value. Condition context keys may not be present in the authorization context when:

  - You are using service specific condition context keys in requests to resources that do not support that condition key.

  - Tags on IAM principals, sessions, resources, or requests are not present.

  - Other circumstances as listed for each global condition context key in AWS global condition context keys.

When you use a variable with no value in the condition element of an IAM policy, IAM JSON policy elements: Condition operators like `StringEquals` or `StringLike` do not match, and the policy statement does not take effect.

Inverted condition operators like `StringNotEquals` or `StringNotLike` do match against a null value, as the value of the condition key they are testing against is not equal to or like the effectively null value.

In the following example, `aws:principaltag/Team` must be equal to `s3:ExistingObjectTag/Team` to allow access. Access is explicitly denied when `aws:principaltag/Team` is not set. If a variable that has no value in the authorization context is used as part of the `Resource` or `NotResource` element of a policy, the resource that includes a policy variable with no value will not match any resource.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
               {
                "Effect": "Deny", 
                "Action": "s3:GetObject",
                "Resource": "arn:aws:s3:::amzn-s3-demo-bucket/*",
                "Condition": {
                  "StringNotEquals": {
                    "s3:ExistingObjectTag/Team": "${aws:PrincipalTag/Team}"
                   }
                  }
                }
              ]
            }
    
    

## Request information that you can use for policy variables

You can use the `Condition` element of a JSON policy to compare keys in the request context with key values that you specify in your policy. When you use a policy variable, AWS substitutes a value from the request context key in place of the variable in your policy.

### Principal key values

The values for `aws:username`, `aws:userid`, and `aws:PrincipalType` depend on what type of principal initiated the request. For example, the request could be made using the credentials of an IAM user, an IAM role, or the AWS account root user. The following table shows values for these keys for different types of principals.

<table>
<colgroup>
<col style="width: 25%" />
<col style="width: 25%" />
<col style="width: 25%" />
<col style="width: 25%" />
</colgroup>
<thead>
<tr class="header">
<th>Principal</th>
<th><code>aws:username</code></th>
<th><code>aws:userid</code></th>
<th><code>aws:PrincipalType</code></th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td>AWS account root user</td>
<td>(not present)</td>
<td>AWS account ID</td>
<td><code>Account</code></td>
</tr>
<tr class="even">
<td>IAM user</td>
<td><code>IAM-user-name</code></td>
<td>unique ID</td>
<td><code>User</code></td>
</tr>
<tr class="odd">
<td>AWS STS federated user principal</td>
<td>(not present)</td>
<td><code>account</code>:<code>caller-specified-name</code></td>
<td><code>FederatedUser</code></td>
</tr>
<tr class="even">
<td>OIDC federated principal
<p>For information about policy keys that are available when you use web identity federation, see Available keys for AWS OIDC federation.</p></td>
<td>(not present)</td>
<td><p><code>role-id</code>:<code>caller-specified-role-name</code></p>
<p>where <code>role-id</code> is the unique id of the role and the caller-specified-role-name is specified by the RoleSessionName parameter passed to the AssumeRoleWithWebIdentity request.</p></td>
<td><code>AssumedRole</code></td>
</tr>
<tr class="odd">
<td>SAML federated principal
<p>For information about policy keys that are available when you use SAML federation, see Uniquely identifying users in SAML-based federation.</p></td>
<td>(not present)</td>
<td><p><code>role-id</code>:<code>caller-specified-role-name</code></p>
<p>where <code>role-id</code> is the unique id of the role and the caller-specified-role-name is specified by the Attribute element with the Name attribute set to https://aws.amazon.com/SAML/attributes/RoleSessionName.</p></td>
<td><code>AssumedRole</code></td>
</tr>
<tr class="even">
<td>Assumed role</td>
<td>(not present)</td>
<td><p><code>role-id</code>:<code>caller-specified-role-name</code></p>
<p>where <code>role-id</code> is the unique id of the role and the caller-specified-role-name is specified by the RoleSessionName parameter passed to the AssumeRole request.</p></td>
<td><code>AssumedRole</code></td>
</tr>
<tr class="odd">
<td>Role assigned to an Amazon EC2 instance</td>
<td>(not present)</td>
<td><p><code>role-id</code>:<code>ec2-instance-id</code></p>
<p>where <code>role-id</code> is the unique id of the role and the ec2-instance-id is the unique identifier of the EC2 instance.</p></td>
<td><code>AssumedRole</code></td>
</tr>
<tr class="even">
<td>Anonymous caller (Amazon SQS, Amazon SNS, and Amazon S3 only)</td>
<td>(not present)</td>
<td><code>anonymous</code></td>
<td><code>Anonymous</code></td>
</tr>
</tbody>
</table>

For the items in this table, note the following:

  - *not present* means that the value is not in the current request information, and any attempt to match it fails and causes the statement to be invalid.

  - `role-id` is a unique identifier assigned to each role at creation. You can display the role ID with the AWS CLI command: `aws iam get-role               --role-name rolename`

  - `caller-specified-name` and `caller-specified-role-name` are names that are passed by the calling process (such as an application or service) when it makes a call to get temporary credentials.

  - `ec2-instance-id` is a value assigned to the instance when it is launched and appears on the **Instances** page of the Amazon EC2 console. You can also display the instance ID by running the AWS CLI command: `aws               ec2 describe-instances`

### Information available in requests for federated principals

Federated principals are users who are authenticated using a system other than IAM. For example, a company might have an application for use in-house that makes calls to AWS. It might be impractical to give an IAM identity to every corporate user who uses the application. Instead, the company might use a proxy (middle-tier) application that has a single IAM identity, or the company might use a SAML identity provider (IdP). The proxy application or SAML IdP authenticates individual users using the corporate network. A proxy application can then use its IAM identity to get temporary security credentials for individual users. A SAML IdP can in effect exchange identity information for AWS temporary security credentials. The temporary credentials can then be used to access AWS resources.

Similarly, you might create an app for a mobile device in which the app needs to access AWS resources. In that case, you might use *OIDC federation*, where the app authenticates the user using a well-known identity provider like Login with Amazon, Amazon Cognito, Facebook, or Google. The app can then use the user's authentication information from these providers to get temporary security credentials for accessing AWS resources.

The recommended way to use OIDC federation is by taking advantage of Amazon Cognito and the AWS mobile SDKs. For more information, see the following:

### Special characters

There are a few special predefined policy variables that have fixed values that enable you to represent characters that otherwise have special meaning. If these special characters are part of the string, you are trying to match and you inserted them literally they would be misinterpreted. For example, inserting an \* asterisk in the string would be interpreted as a wildcard, matching any characters, instead of as a literal \*. In these cases, you can use the following predefined policy variables:

  - **${\*}** - use where you need an \* (asterisk) character.

  - **${?}** - use where you need a ? (question mark) character.

  - **${$}** - use where you need a $ (dollar sign) character.

These predefined policy variables can be used in any string where you can use regular policy variables.

## Specifying default values

To add a default value to a variable, surround the default value with single quotes (`' '`), and separate the variable text and the default value with a comma and space (` ,  `).

For example, if a principal is tagged with `team=yellow`, they can access `ExampleCorp's` Amazon S3 bucket named `amzn-s3-demo-bucket-yellow`. A policy with this resource allows team members to access their team bucket, but not those of other teams. For users without team tags, it sets a default value of `company-wide` for the bucket name. These users can access only the `amzn-s3-demo-bucket-company-wide` bucket where they can view broad information, such as instructions for joining a team.

    "Resource":"arn:aws:s3:::amzn-s3-demo-bucket-${aws:PrincipalTag/team, 'company-wide'}"

## For more information

For more information about policies, see the following: