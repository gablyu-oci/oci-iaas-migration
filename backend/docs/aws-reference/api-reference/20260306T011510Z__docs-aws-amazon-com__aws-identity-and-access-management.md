---
title: "AWS Identity and Access Management"
source: "https://docs.aws.amazon.com/IAM/latest/APIReference/API_GetPolicy.html"
fetched: "20260306T011510Z"
---

# GetPolicy

Retrieves information about the specified managed policy, including the policy's default version and the total number of IAM users, groups, and roles to which the policy is attached. To retrieve the list of the specific users, groups, and roles that the policy is attached to, use ListEntitiesForPolicy. This operation returns metadata about the policy. To retrieve the actual policy document for a specific version of the policy, use GetPolicyVersion.

This operation retrieves information about managed policies. To retrieve information about an inline policy that is embedded with an IAM user, group, or role, use GetUserPolicy, GetGroupPolicy, or GetRolePolicy.

For more information about policies, see Managed policies and inline policies in the *IAM User Guide*.

## Request Parameters

For information about the parameters that are common to all actions, see Common Parameters.

  -  **PolicyArn**   
    The Amazon Resource Name (ARN) of the managed policy that you want information about.
    
    For more information about ARNs, see Amazon Resource Names (ARNs) in the *AWS General Reference*.
    
    Type: String
    
    Length Constraints: Minimum length of 20. Maximum length of 2048.
    
    Required: Yes

## Response Elements

The following element is returned by the service.

  -  **Policy**   
    A structure containing details about the policy.
    
    Type: Policy object

## Errors

For information about the errors that are common to all actions, see Common Errors.

  -  **InvalidInput**   
    The request was rejected because an invalid or out-of-range value was supplied for an input parameter.
    
    HTTP Status Code: 400

  -  **NoSuchEntity**   
    The request was rejected because it referenced a resource entity that does not exist. The error message describes the resource.
    
    HTTP Status Code: 404

  -  **ServiceFailure**   
    The request processing has failed because of an unknown error, exception or failure.
    
    HTTP Status Code: 500

## Examples

### Example

This example illustrates one usage of GetPolicy.

#### Sample Request

    https://iam.amazonaws.com/?Action=GetPolicy
    &PolicyArn=arn:aws:iam::123456789012:policy/S3-read-only-example-bucket
    &Version=2010-05-08
    &AUTHPARAMS

#### Sample Response

    <GetPolicyResponse xmlns="https://iam.amazonaws.com/doc/2010-05-08/">
      <GetPolicyResult>
        <Policy>
          <PolicyName>S3-read-only-example-bucket</PolicyName>
          <Description>Allows read-only access to the example bucket</Description>
          <DefaultVersionId>v1</DefaultVersionId>
          <PolicyId>AGPACKCEVSQ6C2EXAMPLE</PolicyId>
          <Path>/</Path>
          <Arn>arn:aws:iam::123456789012:policy/S3-read-only-example-bucket</Arn>
          <AttachmentCount>9</AttachmentCount>
          <CreateDate>2014-09-15T17:36:14Z</CreateDate>
          <UpdateDate>2014-09-15T20:31:47Z</UpdateDate>
        </Policy>
      </GetPolicyResult>
      <ResponseMetadata>
        <RequestId>684f0917-3d22-11e4-a4a0-cffb9EXAMPLE</RequestId>
      </ResponseMetadata>
    </GetPolicyResponse>

## See Also

For more information about using this API in one of the language-specific AWS SDKs, see the following: