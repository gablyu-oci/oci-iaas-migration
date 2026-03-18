---
title: "AWS Identity and Access Management"
source: "https://docs.aws.amazon.com/IAM/latest/APIReference/API_AttachRolePolicy.html"
fetched: "20260306T011505Z"
---

# AttachRolePolicy

Attaches the specified managed policy to the specified IAM role. When you attach a managed policy to a role, the managed policy becomes part of the role's permission (access) policy.

You cannot use a managed policy as the role's trust policy. The role's trust policy is created at the same time as the role, using `CreateRole`. You can update a role's trust policy using `UpdateAssumerolePolicy`.

Use this operation to attach a *managed* policy to a role. To embed an inline policy in a role, use `PutRolePolicy`. For more information about policies, see Managed policies and inline policies in the *IAM User Guide*.

As a best practice, you can validate your IAM policies. To learn more, see Validating IAM policies in the *IAM User Guide*.

## Request Parameters

For information about the parameters that are common to all actions, see Common Parameters.

  -  **PolicyArn**   
    The Amazon Resource Name (ARN) of the IAM policy you want to attach.
    
    For more information about ARNs, see Amazon Resource Names (ARNs) in the *AWS General Reference*.
    
    Type: String
    
    Length Constraints: Minimum length of 20. Maximum length of 2048.
    
    Required: Yes

  -  **RoleName**   
    The name (friendly name, not ARN) of the role to attach the policy to.
    
    This parameter allows (through its regex pattern) a string of characters consisting of upper and lowercase alphanumeric characters with no spaces. You can also include any of the following characters: \_+=,.@-
    
    Type: String
    
    Length Constraints: Minimum length of 1. Maximum length of 64.
    
    Pattern: `[\w+=,.@-]+`
    
    Required: Yes

## Errors

For information about the errors that are common to all actions, see Common Errors.

  -  **InvalidInput**   
    The request was rejected because an invalid or out-of-range value was supplied for an input parameter.
    
    HTTP Status Code: 400

  -  **LimitExceeded**   
    The request was rejected because it attempted to create resources beyond the current AWS account limits. The error message describes the limit exceeded.
    
    HTTP Status Code: 409

  -  **NoSuchEntity**   
    The request was rejected because it referenced a resource entity that does not exist. The error message describes the resource.
    
    HTTP Status Code: 404

  -  **PolicyNotAttachable**   
    The request failed because AWS service role policies can only be attached to the service-linked role for that service.
    
    HTTP Status Code: 400

  -  **ServiceFailure**   
    The request processing has failed because of an unknown error, exception or failure.
    
    HTTP Status Code: 500

  -  **UnmodifiableEntity**   
    The request was rejected because service-linked roles are protected AWS resources. Only the service that depends on the service-linked role can modify or delete the role on your behalf. The error message includes the name of the service that depends on this service-linked role. You must request the change through that service.
    
    HTTP Status Code: 400

## Examples

### Example

This example illustrates one usage of AttachRolePolicy.

#### Sample Request

    https://iam.amazonaws.com/?Action=AttachRolePolicy
    &PolicyArn=arn:aws:iam::aws:policy/ReadOnlyAccess
    &RoleName=ReadOnlyRole
    &Version=2010-05-08
    &AUTHPARAMS

#### Sample Response

    <AttachRolePolicyResponse xmlns="https://iam.amazonaws.com/doc/2010-05-08/">
      <ResponseMetadata>
        <RequestId>37a87673-3d07-11e4-bfad-8d1c6EXAMPLE</RequestId>
      </ResponseMetadata>
    </AttachRolePolicyResponse>

## See Also

For more information about using this API in one of the language-specific AWS SDKs, see the following: