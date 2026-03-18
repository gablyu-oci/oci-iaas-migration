---
title: "AWS CLI 2.34.3 Command Reference"
source: "https://awscli.amazonaws.com/v2/documentation/api/latest/reference/iam/get-policy.html"
fetched: "20260306T011537Z"
---

## Description

Retrieves information about the specified managed policy, including the policyâ€™s default version and the total number of IAM users, groups, and roles to which the policy is attached. To retrieve the list of the specific users, groups, and roles that the policy is attached to, use ListEntitiesForPolicy . This operation returns metadata about the policy. To retrieve the actual policy document for a specific version of the policy, use GetPolicyVersion .

This operation retrieves information about managed policies. To retrieve information about an inline policy that is embedded with an IAM user, group, or role, use GetUserPolicy , GetGroupPolicy , or GetRolePolicy .

For more information about policies, see Managed policies and inline policies in the *IAM User Guide* .

See also: AWS API Documentation

## Options

`--policy-arn` (string) \[required\]

> 
> 
> 
> 
> The Amazon Resource Name (ARN) of the managed policy that you want information about.
> 
> For more information about ARNs, see Amazon Resource Names (ARNs) in the *Amazon Web Services General Reference* .
> 
> Constraints:
> 
> 

`--cli-input-json` | `--cli-input-yaml` (string) Reads arguments from the JSON string provided. The JSON string follows the format provided by `--generate-cli-skeleton`. If other arguments are provided on the command line, those values will override the JSON-provided values. It is not possible to pass arbitrary binary values using a JSON-provided value as the string will be taken literally. This may not be specified along with `--cli-input-yaml`.

`--generate-cli-skeleton` (string) Prints a JSON skeleton to standard output without sending an API request. If provided with no value or the value `input`, prints a sample input JSON that can be used as an argument for `--cli-input-json`. Similarly, if provided `yaml-input` it will print a sample input YAML that can be used with `--cli-input-yaml`. If provided with the value `output`, it validates the command inputs and returns a sample output JSON for that command. The generated JSON skeleton is not stable between versions of the AWS CLI and there are no backwards compatibility guarantees in the JSON skeleton generated.

## Global Options

`--debug` (boolean)

Turn on debug logging.

`--endpoint-url` (string)

Override commandâ€™s default URL with the given URL.

`--no-verify-ssl` (boolean)

By default, the AWS CLI uses SSL when communicating with AWS services. For each SSL connection, the AWS CLI will verify SSL certificates. This option overrides the default behavior of verifying SSL certificates.

`--no-paginate` (boolean)

Disable automatic pagination. If automatic pagination is disabled, the AWS CLI will only make one call, for the first page of results.

`--output` (string)

The formatting style for command output.

  - json
  - text
  - table
  - yaml
  - yaml-stream
  - off

`--query` (string)

A JMESPath query to use in filtering the response data.

`--profile` (string)

Use a specific profile from your credential file.

`--region` (string)

The region to use. Overrides config/env settings.

`--version` (string)

Display the version of this tool.

`--color` (string)

Turn on/off color output.

`--no-sign-request` (boolean)

Do not sign requests. Credentials will not be loaded if this argument is provided.

`--ca-bundle` (string)

The CA certificate bundle to use when verifying SSL certificates. Overrides config/env settings.

`--cli-read-timeout` (int)

The maximum socket read time in seconds. If the value is set to 0, the socket read will be blocking and not timeout. The default value is 60 seconds.

`--cli-connect-timeout` (int)

The maximum socket connect time in seconds. If the value is set to 0, the socket connect will be blocking and not timeout. The default value is 60 seconds.

`--cli-binary-format` (string)

The formatting style to be used for binary blobs. The default format is base64. The base64 format expects binary blobs to be provided as a base64 encoded string. The raw-in-base64-out format preserves compatibility with AWS CLI V1 behavior and binary values must be passed literally. When providing contents from a file that map to a binary blob `fileb://` will always be treated as binary and use the file contents directly regardless of the `cli-binary-format` setting. When using `file://` the file contents will need to properly formatted for the configured `cli-binary-format`.

`--no-cli-pager` (boolean)

Disable cli pager for output.

`--cli-auto-prompt` (boolean)

Automatically prompt for CLI input parameters.

`--no-cli-auto-prompt` (boolean)

Disable automatically prompt for CLI input parameters.

`--cli-error-format` (string)

The formatting style for error output. By default, errors are displayed in enhanced format.

  - legacy
  - json
  - yaml
  - text
  - table
  - enhanced

## Examples

### Note

To use the following examples, you must have the AWS CLI installed and configured. See the Getting started guide in the *AWS CLI User Guide* for more information.

Unless otherwise stated, all examples have unix-like quotation rules. These examples will need to be adapted to your terminalâ€™s quoting rules. See Using quotation marks with strings in the *AWS CLI User Guide* .

**To retrieve information about the specified managed policy**

This example returns details about the managed policy whose ARN is `arn:aws:iam::123456789012:policy/MySamplePolicy`.

    aws iam get-policy \
        --policy-arn arn:aws:iam::123456789012:policy/MySamplePolicy

Output:

    {
        "Policy": {
            "PolicyName": "MySamplePolicy",
            "CreateDate": "2015-06-17T19:23;32Z",
            "AttachmentCount": 0,
            "IsAttachable": true,
            "PolicyId": "Z27SI6FQMGNQ2EXAMPLE1",
            "DefaultVersionId": "v1",
            "Path": "/",
            "Arn": "arn:aws:iam::123456789012:policy/MySamplePolicy",
            "UpdateDate": "2015-06-17T19:23:32Z"
        }
    }

For more information, see Policies and permissions in IAM in the *AWS IAM User Guide*.