---
title: "AWS JSON policy elements: Principal"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_principal.html"
fetched: "20260306T011516Z"
---

# AWS JSON policy elements: Principal

Use the `Principal` element in a resource-based JSON policy to specify the principal that is allowed or denied access to a resource.

You must use the `Principal` element in resource-based policies. Several services support resource-based policies, including IAM. The IAM resource-based policy type is a role trust policy. In IAM roles, use the `Principal` element in the role trust policy to specify who can assume the role. For cross-account access, you must specify the 12-digit identifier of the trusted account. To learn whether principals in accounts outside of your zone of trust (trusted organization or account) have access to assume your roles, see What is IAM Access Analyzer?.

After you create the role, you can change the account to "\*" to allow everyone to assume the role. If you do this, we strongly recommend that you limit who can access the role through other means, such as a `Condition` element that limits access to only certain IP addresses. Do not leave your role accessible to everyone\!

Other examples of resources that support resource-based policies include an Amazon S3 bucket or an AWS KMS key.

You cannot use the `Principal` element in an identity-based policy. Identity-based policies are permissions policies that you attach to IAM identities (users, groups, or roles). In those cases, the principal is implicitly the identity where the policy is attached.

## How to specify a principal

You specify a principal in the `Principal` element of a resource-based policy or in condition keys that support principals.

You can specify any of the following principals in a policy:

You cannot identify a user group as a principal in a policy (such as a resource-based policy) because groups relate to permissions, not authentication, and principals are authenticated IAM entities.

You can specify more than one principal for each of the principal types in following sections using an array. Arrays can take one or more values. When you specify more than one principal in an element, you grant permissions to each principal. This is a logical `OR` and not a logical `AND`, because you authenticate as one principal at a time. If you include more than one value, use square brackets (`[` and `]`) and comma-delimit each entry for the array. The following example policy defines permissions for the 123456789012 account or the 555555555555 account.

    "Principal" : { 
    "AWS": [ 
      "123456789012",
      "555555555555" 
      ]
    }

You cannot use a wildcard to match part of a principal name or ARN.

## AWS account principals

You can specify AWS account identifiers in the `Principal` element of a resource-based policy or in condition keys that support principals. This delegates authority to the account. When you allow access to a different account, an administrator in that account must then grant access to an identity (IAM user or role) in that account. When you specify an AWS account, you can use the account ARN (arn:aws:iam::`account-ID`:root), or a shortened form that consists of the `"AWS":` prefix followed by the account ID.

For example, given an account ID of `123456789012`, you can use either of the following methods to specify that account in the `Principal` element:

    "Principal": { "AWS": "arn:aws:iam::123456789012:root" }

    "Principal": { "AWS": "123456789012" }

The account ARN and the shortened account ID behave the same way. Both delegate permissions to the account. Using the account ARN in the `Principal` element does not limit permissions to only the root user of the account.

When you save a resource-based policy that includes the shortened account ID, the service might convert it to the principal ARN. This does not change the functionality of the policy.

Some AWS services support additional options for specifying an account principal. For example, Amazon S3 lets you specify a canonical user ID using the following format:

    "Principal": { "CanonicalUser": "79a59df900b949e55d96a1e698fbacedfd6e09d98eacf8f8d5218e7cd47ef2be" }

You can also specify more than one AWS account, (or canonical user ID) as a principal using an array. For example, you can specify a principal in a bucket policy using all three methods.

    "Principal": { 
      "AWS": [
        "arn:aws:iam::123456789012:root",
        "999999999999"
      ],
      "CanonicalUser": "79a59df900b949e55d96a1e698fbacedfd6e09d98eacf8f8d5218e7cd47ef2be"
    }

## IAM role principals

You can specify IAM role principal ARNs in the `Principal` element of a resource-based policy or in condition keys that support principals. IAM roles are identities. In IAM, identities are resources to which you can assign permissions. Roles trust another authenticated identity to assume that role. This includes a principal in AWS or a user from an external identity provider (IdP). When a principal or identity assumes a role, they receive temporary security credentials with the assumed roleâ€™s permissions. When they use those session credentials to perform operations in AWS, they become a *role session principal*.

When you specify a role principal in a resource-based policy, the effective permissions for the principal are limited by any policy types that limit permissions for the role. This includes session policies and permissions boundaries. For more information about how the effective permissions for a role session are evaluated, see Policy evaluation logic.

To specify the role ARN in the `Principal` element, use the following format:

    "Principal": { "AWS": "arn:aws:iam::AWS-account-ID:role/role-name" }

If your `Principal` element in a role trust policy contains an ARN that points to a specific IAM role, then that ARN transforms to the role's unique principal ID when you save the policy. This helps mitigate the risk of someone escalating their privileges by removing and recreating the role. You don't normally see this ID in the console, because IAM uses a reverse transformation back to the role ARN when the trust policy is displayed. However, if you delete the role, then you break the relationship. The policy no longer applies, even if you recreate the role because the new role has a new principal ID that does not match the ID stored in the trust policy. When this happens, the principal ID appears in resource-based policies because AWS can no longer map it back to a valid ARN. The end result is that if you delete and recreate a role referenced in a trust policy's `Principal` element, you must edit the role in the policy to replace the principal ID with the correct ARN. The ARN once again transforms into the role's new principal ID when you save the policy. For more information, see Understanding AWS's Handling of Deleted IAM roles in Policies.

Alternatively, you can specify the role principal as the principal in a resource-based policy or create a broad-permission policy that uses the `aws:PrincipalArn` condition key. When you use this key, the role session principal is granted the permissions based on the ARN of role that was assumed, and not the ARN of the resulting session. Because AWS does not convert condition key ARNs to IDs, permissions granted to the role ARN persist if you delete the role and then create a new role with the same name. Identity-based policy types, such as permissions boundaries or session policies, do not limit permissions granted using the `aws:PrincipalArn` condition key with a wildcard(\*) in the `Principal` element, unless the identity-based policies contain an explicit deny.

## Role session principals

You can specify role sessions in the `Principal` element of a resource-based policy or in condition keys that support principals. When a principal or identity assumes a role, they receive temporary security credentials with the assumed roleâ€™s permissions. When they use those session credentials to perform operations in AWS, they become a *role session principal*.

The format that you use for a role session principal depends on the AWS STS operation that was used to assume the role.

Additionally, administrators can design a process to control how role sessions are issued. For example, they can provide a one-click solution for their users that creates a predictable session name. If your administrator does this, you can use role session principals in your policies or condition keys. Otherwise, you can specify the role ARN as a principal in the `aws:PrincipalArn` condition key. How you specify the role as a principal can change the effective permissions for the resulting session. For more information, see IAM role principals.

## Assumed-role session principals

An *assumed-role session principal* is a session principal that results from using the AWS STS `AssumeRole` operation. For more information about which principals can assume a role using this operation, see Compare AWS STS credentials.

To specify the assumed-role session ARN in the `Principal` element, use the following format:

    "Principal": { "AWS": "arn:aws:sts::AWS-account-ID:assumed-role/role-name/role-session-name" }

When you specify an assumed-role session in a `Principal` element, you cannot use a wildcard "\*" to mean all sessions. Principals must always name a specific session.

## OIDC federated principals

An OIDC federated principal is the principal used when calling AWS STS `AssumeRoleWithWebIdentity` API with a JSON web token (JWT) from an OIDC compliant IDP, also known as OpenID Provider (OP), to request temporary AWS credentials. An OIDC federated principal can represent an OIDC IDP in your AWS account, or the 4 built in identity providers: Login with Amazon, Google, Facebook, and Amazon Cognito.

Users, workloads, or systems whoâ€™ve been issued a JWT from their OIDC IDP can call `AssumeRoleWithWebIdentity` using the JWT to request temporary AWS security credentials for an IAM role that is configured to trust the OIDC IDP that issued the JWT. The JWT can be an id token, access token, or a JWT token delivered by any other method as long as it meets the requirements listed by AWS STS. For more information, see Common scenarios and Requesting credentials through an OIDC provider.

Use this principal type in your role trust policy to allow or deny permissions to call `AssumeRoleWIthWebIdentity` using an OIDC IDP that exists in your AWS account, or one of the four built in IDPs. To specify the OIDC federated principal ARN in the `Principal` element of a role trust policy, use one of the following four formats for the built in OIDC IDPs:

    "Principal": { "Federated": "cognito-identity.amazonaws.com" }

    "Principal": { "Federated": "www.amazon.com" }

    "Principal": { "Federated": "graph.facebook.com" }

    "Principal": { "Federated": "accounts.google.com" }

When using a OIDC provider you add to your account, such as GitHub, you specify the provider's ARN in your role's trust policy. This configuration allows you to write IAM policies that control access specifically for users authenticated through your custom identity provider.

    "Principal": { "Federated": "arn:aws:iam::AWS-account-ID:oidc-provider/full-OIDC-identity-provider-URL" }

For example, if GitHub was the trusted web identity provider, the OIDC role session ARN in the `Principal` element of a role trust policy uses the following format:

    "Principal": { "Federated": "arn:aws:iam::AWS-account-ID:oidc-provider/tokens.actions.githubusercontent.com" }

See Configuring OpenID Connect in Amazon Web Services for more information.

OIDC federated principals are not supported in policy types other than role trust policies.

## SAML federated principals

A *SAML federated principal* is a principal that is used when calling AWS STS `AssumeRoleWithSAML` API to request temporary AWS credentials using a SAML assertion. You can use your SAML identity provider (IDP) to sign in, and then assume an IAM role using this operation. Similar to `AssumeRoleWithWebIdentity`, `AssumeRoleWithSAML` doesn't require AWS credentials for authentication. Instead, users first authenticate with their SAML identity provider, then make the `AssumeRoleWithSAML` API call using their SAML assertion, or are redirected to the AWS Sign-In/SAML page to sign into the AWS Management Console. For more information about which principals can assume a role using this operation, see Compare AWS STS credentials.

Use this principal type in your role trust policy to allow or deny permissions based on the trusted SAML identity provider. To specify the SAML identity role session ARN in the `Principal` element of a role trust policy, use the following format:

    "Principal": { "Federated": "arn:aws:iam::AWS-account-ID:saml-provider/provider-name" }

## IAM user principals

You can specify IAM users in the `Principal` element of a resource-based policy or in condition keys that support principals.

    "Principal": { "AWS": "arn:aws:iam::AWS-account-ID:user/user-name" }

    "Principal": {
      "AWS": [
        "arn:aws:iam::AWS-account-ID:user/user-name-1", 
        "arn:aws:iam::AWS-account-ID:user/user-name-2"
      ]
    }

When you specify users in a `Principal` element, you cannot use a wildcard (`*`) to mean "all users". Principals must always name specific users.

If your `Principal` element in a role trust policy contains an ARN that points to a specific IAM user, then IAM transforms the ARN to the user's unique principal ID when you save the policy. This helps mitigate the risk of someone escalating their privileges by removing and recreating the user. You don't normally see this ID in the console, because there is also a reverse transformation back to the user's ARN when the trust policy is displayed. However, if you delete the user, then you break the relationship. The policy no longer applies, even if you recreate the user. That's because the new user has a new principal ID that does not match the ID stored in the trust policy. When this happens, the principal ID appears in resource-based policies because AWS can no longer map it back to a valid ARN. The result is that if you delete and recreate a user referenced in a trust policy `Principal` element, you must edit the role to replace the now incorrect principal ID with the correct ARN. IAM once again transforms ARN into the user's new principal ID when you save the policy.

## IAM Identity Center principals

In IAM Identity Center, the principal in a resource-based policy must be defined as the AWS account principal. To specify access, reference the role ARN of the permission set in the condition block. For details, see Referencing permission sets in resource policies, Amazon EKS, and AWS KMS in the *IAM Identity Center User Guide*.

## AWS STS federated user principals

You can specify *federated user sessions* in the `Principal` element of a resource-based policy or in condition keys that support principals.

AWS recommends that you limit the use of AWS STS federated user sessions. Instead, use IAM roles.

An AWS STS federated user principal is created through the `GetFederationToken` operation called with long-lived IAM credentials. Federated user permissions are the intersection of the principal that called `GetFederationToken` and the session policies passed as parameters to the `GetFederationToken` API.

In AWS, IAM users or an AWS account root user can authenticate using long-term access keys. For more information about which principals can federate using this operation, see Compare AWS STS credentials.

  - **IAM federated user** â€“ An IAM user federates using the `GetFederationToken` operation that results in a federated user session for that IAM user.

  - **Federated root user** â€“ A root user federates using the `GetFederationToken` operation that results in a federated user session for that root user.

When an IAM user or root user requests temporary credentials from AWS STS using this operation, they begin a temporary federated user session. This sessionâ€™s ARN is based on the original identity that was federated.

To specify the federated user session ARN in the `Principal` element, use the following format:

    "Principal": { "AWS": "arn:aws:sts::AWS-account-ID:federated-user/user-name" }

## AWS service principals

You can specify AWS services in the `Principal` element of a resource-based policy or in condition keys that support principals. A *service principal* is an identifier for a service.

IAM roles that can be assumed by an AWS service are called *service roles*. Service roles must include a trust policy. *Trust policies* are resource-based policies attached to a role that defines which principals can assume the role. Some service roles have predefined trust policies. However, in some cases, you must specify the service principal in the trust policy. The service principal in an IAM policy can't be `"Service": "*"`.

The identifier for a service principal includes the service name, and is usually in the following format:

`service-name`.amazonaws.com

The service principal is defined by the service. You can find the service principal for some services by opening AWS services that work with IAM, checking whether the service has **Yes** in the **Service-linked role** column, and opening the **Yes** link to view the service-linked role documentation for that service. Find the **Service-Linked Role Permissions** section for that service to view the service principal.

The following example shows a policy that can be attached to a service role. The policy enables two services, Amazon ECS and Elastic Load Balancing, to assume the role. The services can then perform any tasks granted by the permissions policy assigned to the role (not shown). To specify multiple service principals, you do not specify two `Service` elements; you can have only one. Instead, you use an array of multiple service principals as the value of a single `Service` element.

    "Principal": {
        "Service": [
            "ecs.amazonaws.com",
            "elasticloadbalancing.amazonaws.com"
       ]
    }

## AWS service principals in opt-in Regions

You can launch resources in several AWS Regions and some of those Regions you must opt in to. For a complete list of Regions you must opt in to, see Managing AWS Regions in the *AWS General Reference* guide.

When an AWS service in an opt-in Region makes a request within the same Region, the service principal name format is identified as the non-regionalized version of their service principal name:

`service-name`.amazonaws.com

When an AWS service in an opt-in Region makes a cross-region request to another Region, the service principal name format is identified as the regionalized version of their service principal name:

`service-name`.`{region}`.amazonaws.com

For example, you have an Amazon SNS topic located in Region `ap-southeast-1` and an Amazon S3 bucket located in opt-in Region `ap-east-1`. You want to configure S3 bucket notifications to publish messages to the SNS topic. To allow the S3 service to post messages to the SNS topic you must grant the S3 service principal `sns:Publish` permission via the resource-based access policy of the topic.

If you specify the non-regionalized version of the S3 service principal, `s3.amazonaws.com`, in the topic access policy, the `sns:Publish` request from the bucket to the topic will fail. The following example specifies the non-regionalized S3 service principal in the `Principal` policy element of the SNS topic access policy.

    "Principal": { "Service": "s3.amazonaws.com" }

Since the bucket is located in an opt-in Region and the request is made outside of that same Region, the S3 service principal appears as the regionalized service principal name, `s3.ap-east-1.amazonaws.com`. You must use the regionalized service principal name when an AWS service in an opt-in Region makes a request to another Region. After you specify the regionalized service principal name, if the bucket makes an `sns:Publish` request to the SNS topic located in another Region, the request will be successful. The following example specifies the regionalized S3 service principal in the `Principal` policy element of the SNS topic access policy.

    "Principal": { "Service": "s3.ap-east-1.amazonaws.com" }

Resource policies or service principal-based allow-lists for cross-Region requests from an opt-in Region to another Region will only be successful if you specify the regionalized service principal name.

For IAM role trust policies, we recommend using the non-regionalized service principal name. IAM resources are global and therefore the same role can be used in any Region.

## All principals

You can use a wildcard (\*) to specify all principals in the `Principal` element of a resource-based policy or in condition keys that support principals. Resource-based policies *grant* permissions and condition keys are used to limit the conditions of a policy statement.

We strongly recommend that you do not use a wildcard (\*) in the `Principal` element of a resource-based policy with an `Allow` effect unless you intend to grant public or anonymous access. Otherwise, specify intended principals, services, or AWS accounts in the `Principal` element and then further restrict access in the `Condition` element. This is especially true for IAM role trust policies, because they allow other principals to become a principal in your account.

For resource-based policies, using a wildcard (\*) with an `Allow` effect grants access to all users, including anonymous users (public access). For IAM users and role principals within your account, no other permissions are required. For principals in other accounts, they must also have identity-based permissions in their account that allow them to access your resource. This is called cross-account access.

For anonymous users, the following elements are equivalent:

    "Principal": "*"

    "Principal" : { "AWS" : "*" }

You cannot use a wildcard to match part of a principal name or ARN.

The following example shows a resource-based policy that can be used instead of AWS JSON policy elements: NotPrincipal to explicitly deny all principals *except* for the ones specified in the `Condition` element. This policy should be added to an Amazon S3 bucket.

  - JSON
    
    
    
      - ****
        
            {
              "Version":"2012-10-17",                
              "Statement": [
                {
                  "Sid": "UsePrincipalArnInsteadOfNotPrincipalWithDeny",
                  "Effect": "Deny",
                  "Action": "s3:*",
                  "Principal": "*",
                  "Resource": [
                    "arn:aws:s3:::amzn-s3-demo-bucket/*",
                    "arn:aws:s3:::amzn-s3-demo-bucket"
                  ],
                  "Condition": {
                    "ArnNotEquals": {
                      "aws:PrincipalArn": "arn:aws:iam::444455556666:user/user-name"
                    }
                  }
                }
              ]
            }
    
    

## More information

For more information, see the following: