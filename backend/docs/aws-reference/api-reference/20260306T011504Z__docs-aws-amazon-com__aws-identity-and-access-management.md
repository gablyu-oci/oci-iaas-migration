---
title: "AWS Identity and Access Management"
source: "https://docs.aws.amazon.com/IAM/latest/APIReference/API_CreatePolicy.html"
fetched: "20260306T011504Z"
---

# CreatePolicy

Creates a new managed policy for your AWS account.

This operation creates a policy version with a version identifier of `v1` and sets v1 as the policy's default version. For more information about policy versions, see Versioning for managed policies in the *IAM User Guide*.

As a best practice, you can validate your IAM policies. To learn more, see Validating IAM policies in the *IAM User Guide*.

For more information about managed policies in general, see Managed policies and inline policies in the *IAM User Guide*.

## Request Parameters

For information about the parameters that are common to all actions, see Common Parameters.

  -  **Description**   
    A friendly description of the policy.
    
    Typically used to store information about the permissions defined in the policy. For example, "Grants access to production DynamoDB tables."
    
    The policy description is immutable. After a value is assigned, it cannot be changed.
    
    Type: String
    
    Length Constraints: Maximum length of 1000.
    
    Required: No

  -  **Path**   
    The path for the policy.
    
    For more information about paths, see IAM identifiers in the *IAM User Guide*.
    
    This parameter is optional. If it is not included, it defaults to a slash (/).
    
    This parameter allows (through its regex pattern) a string of characters consisting of either a forward slash (/) by itself or a string that must begin and end with forward slashes. In addition, it can contain any ASCII character from the \! (`\u0021`) through the DEL character (`\u007F`), including most punctuation characters, digits, and upper and lowercased letters.
    
    
    
    
    
    You cannot use an asterisk (\*) in the path name.
    
    
    
    
    
    Type: String
    
    Length Constraints: Minimum length of 1. Maximum length of 512.
    
    Pattern: `((/[A-Za-z0-9\.,\+@=_-]+)*)/`
    
    Required: No

  -  **PolicyDocument**   
    The JSON policy document that you want to use as the content for the new policy.
    
    You must provide policies in JSON format in IAM. However, for CloudFormation templates formatted in YAML, you can provide the policy in JSON or YAML format. CloudFormation always converts a YAML policy to JSON format before submitting it to IAM.
    
    The maximum length of the policy document that you can pass in this operation, including whitespace, is listed below. To view the maximum character counts of a managed policy with no whitespaces, see IAM and AWS STS character quotas.
    
    To learn more about JSON policy grammar, see Grammar of the IAM JSON policy language in the *IAM User Guide*.
    
    The regex pattern used to validate this parameter is a string of characters consisting of the following:
    
    
    
      - Any printable ASCII character ranging from the space character (`\u0020`) through the end of the ASCII character range
    
      - The printable characters in the Basic Latin and Latin-1 Supplement character set (through `\u00FF`)
    
      - The special characters tab (`\u0009`), line feed (`\u000A`), and carriage return (`\u000D`)
    
    
    
    Type: String
    
    Length Constraints: Minimum length of 1. Maximum length of 131072.
    
    Pattern: `[\u0009\u000A\u000D\u0020-\u00FF]+`
    
    Required: Yes

  -  **PolicyName**   
    The friendly name of the policy.
    
    IAM user, group, role, and policy names must be unique within the account. Names are not distinguished by case. For example, you cannot create resources named both "MyResource" and "myresource".
    
    Type: String
    
    Length Constraints: Minimum length of 1. Maximum length of 128.
    
    Pattern: `[\w+=,.@-]+`
    
    Required: Yes

  -  **Tags.member.N**   
    A list of tags that you want to attach to the new IAM customer managed policy. Each tag consists of a key name and an associated value. For more information about tagging, see Tagging IAM resources in the *IAM User Guide*.
    
    
    
    
    
    If any one of the tags is invalid or if you exceed the allowed maximum number of tags, then the entire request fails and the resource is not created.
    
    
    
    
    
    Type: Array of Tag objects
    
    Array Members: Maximum number of 50 items.
    
    Required: No

## Response Elements

The following element is returned by the service.

  -  **Policy**   
    A structure containing details about the new policy.
    
    Type: Policy object

## Errors

For information about the errors that are common to all actions, see Common Errors.

  -  **ConcurrentModification**   
    The request was rejected because multiple requests to change this object were submitted simultaneously. Wait a few minutes and submit your request again.
    
    HTTP Status Code: 409

  -  **EntityAlreadyExists**   
    The request was rejected because it attempted to create a resource that already exists.
    
    HTTP Status Code: 409

  -  **InvalidInput**   
    The request was rejected because an invalid or out-of-range value was supplied for an input parameter.
    
    HTTP Status Code: 400

  -  **LimitExceeded**   
    The request was rejected because it attempted to create resources beyond the current AWS account limits. The error message describes the limit exceeded.
    
    HTTP Status Code: 409

  -  **MalformedPolicyDocument**   
    The request was rejected because the policy document was malformed. The error message describes the specific error.
    
    HTTP Status Code: 400

  -  **ServiceFailure**   
    The request processing has failed because of an unknown error, exception or failure.
    
    HTTP Status Code: 500

## Examples

### Example

This example illustrates one usage of CreatePolicy.

#### Sample Request

    https://iam.amazonaws.com/?Action=CreatePolicy
    &PolicyDocument={"Version":"2012-10-17",                "Statement":[{"Effect":"Allow","Action":"s3:ListAllMyBuckets",
    "Resource":"arn:aws:s3:::*"},{"Effect":"Allow","Action":["s3:Get*","s3:List*"],"Resource":
    ["arn:aws:s3:::EXAMPLE-BUCKET","arn:aws:s3:::EXAMPLE-BUCKET/*"]}]}
    &PolicyName=S3-read-only-example-bucket
    &Version=2010-05-08
    &AUTHPARAMS

#### Sample Response

    <CreatePolicyResponse xmlns="https://iam.amazonaws.com/doc/2010-05-08/">
      <CreatePolicyResult>
        <Policy>
          <PolicyName>S3-read-only-example-bucket</PolicyName>
          <DefaultVersionId>v1</DefaultVersionId>
          <PolicyId>AGPACKCEVSQ6C2EXAMPLE</PolicyId>
          <Path>/</Path>
          <Arn>arn:aws:iam::123456789012:policy/S3-read-only-example-bucket</Arn>
          <AttachmentCount>0</AttachmentCount>
          <CreateDate>2014-09-15T17:36:14.673Z</CreateDate>
          <UpdateDate>2014-09-15T17:36:14.673Z</UpdateDate>
        </Policy>
      </CreatePolicyResult>
      <ResponseMetadata>
        <RequestId>ca64c9e1-3cfe-11e4-bfad-8d1c6EXAMPLE</RequestId>
      </ResponseMetadata>
    </CreatePolicyResponse>

## See Also

For more information about using this API in one of the language-specific AWS SDKs, see the following: