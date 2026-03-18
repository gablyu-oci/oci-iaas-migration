---
title: "AWS JSON policy elements: NotPrincipal"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_notprincipal.html"
fetched: "20260306T011523Z"
---

# AWS JSON policy elements: NotPrincipal

The `NotPrincipal` element uses `"Effect":"Deny"` to deny access to all principals ***except*** the principal specified in the `NotPrincipal` element. A principal can be an IAM user, AWS STS federated user principal, IAM role, assumed role session, AWS account, AWS service, or other principal type. For more information about principals, see AWS JSON policy elements: Principal.

`NotPrincipal` must be used with `"Effect":"Deny"`. Using it with `"Effect":"Allow"` is not supported.

We do not recommend the use of `NotPrincipal` for new resource-based policies as part of your security and authorization strategy. When you use `NotPrincipal`, troubleshooting the effects of multiple policy types can be difficult. We recommend using the `aws:PrincipalArn` context key with ARN condition operators instead.

## Key points

  - The `NotPrincipal` element is supported in resource-based policies for some AWS services, including VPC endpoints. Resource-based policies are policies that you embed directly in a resource. You cannot use the `NotPrincipal` element in an IAM identity-based policy nor in an IAM role trust policy.

  - Don't use resource-based policy statements that include a `NotPrincipal` policy element with a `Deny` effect for IAM users or roles that have a permissions boundary policy attached. The `NotPrincipal` element with a `Deny` effect will always deny any IAM principal that has a permissions boundary policy attached, regardless of the values specified in the `NotPrincipal` element. This causes some IAM users or roles that would otherwise have access to the resource to lose access. We recommend changing your resource-based policy statements to use the condition operator ArnNotEquals with the aws:PrincipalArn context key to limit access instead of the `NotPrincipal` element. For information about permissions boundaries, see Permissions boundaries for IAM entities.

  - When you use `NotPrincipal`, you must also specify the account ARN of the not-denied principal. Otherwise, the policy might deny access to the entire account containing the principal. Depending on the service that you include in your policy, AWS might validate the account first and then the user. If an assumed-role user (someone who is using a role) is being evaluated, AWS might validate the account first, then the role, and then the assumed-role user. The assumed-role user is identified by the role session name that is specified when they assumed the role. Therefore, we strongly recommend that you explicitly include the ARN for a user's account, or include both the ARN for a role and the ARN for the account containing that role.

  - The `NotPrincipal` element isnâ€™t supported in Service Control Policies (SCP) and Resource Control Policies (RCP).

## Alternatives to the `NotPrincipal` element

When managing access control in AWS, there may be scenarios where you need to explicitly deny all principals access to a resource, except for one or more principals you specify. AWS recommends using a Deny statement with global condition context keys for more precise control and easier troubleshooting. The following examples show alternative approaches using condition operators like `StringNotEquals` or `ArnNotEquals` to deny access to all principals except those specified in the Condition element.

## Example scenario using an IAM role

You can use a resource-based policy with a Deny statement to prevent all IAM roles, except those specified in the Condition element, from accessing or manipulating your resources. This approach follows the AWS security principle that an explicit deny always takes precedence over any allow statements and helps maintain the principle of least privilege across your AWS infrastructure.

Instead of using `NotPrincipal`, we recommend using a Deny statement with global condition context keys and the condition operator like ArnNotEquals to explicitly allow an IAM role access to your resources. The following example uses aws:PrincipalArn to explicitly allow the role `read-only-role` to access Amazon S3 buckets in the `Bucket_Account_Audit` folder.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Sid": "DenyCrossAuditAccess",
                  "Effect": "Deny",
                  "Principal": "*",
                  "Action": "s3:*",
                  "Resource": [
                    "arn:aws:s3:::Bucket_Account_Audit",
                    "arn:aws:s3:::Bucket_Account_Audit/*"
                  ],
                  "Condition": {
                    "ArnNotEquals": {
                      "aws:PrincipalArn": "arn:aws:iam::444455556666:role/read-only-role"
                    }
                  }
                }
              ]
            }
    
    

## Example scenario using a service principal

You can use a Deny statement to prevent all service principals, except those specified in the `Condition` element, from accessing or manipulating your resources. This approach is particularly useful when you need to implement fine-grained access controls or establish security boundaries between different services and applications in your AWS environment.

Instead of using `NotPrincipal`, we recommend using a Deny statement with global condition context keys and the condition operator StringNotEquals to explicitly allow a service principal access to your resources. The following example uses `aws:PrincipalServiceName` to explicitly allow the AWS CodeBuild service principal to access Amazon S3 buckets in the `BUCKETNAME` folder.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Sid": "DenyNotCodeBuildAccess",
                  "Effect": "Deny",
                  "Principal": "*",
                  "Action": "s3:*",
                  "Resource": [
                    "arn:aws:s3:::BUCKETNAME",
                    "arn:aws:s3:::BUCKETNAME/*"
                  ],
                  "Condition": {
                    "StringNotEqualsIfExists": {
                      "aws:PrincipalServiceName": "codebuild.amazonaws.com"
                    }
                  }
                }
              ]
            }