---
title: "AWS CLI 2.34.3 Command Reference"
source: "https://awscli.amazonaws.com/v2/documentation/api/latest/reference/iam/list-policies.html"
fetched: "20260306T011542Z"
---

## Description

Lists all the managed policies that are available in your Amazon Web Services account, including your own customer-defined managed policies and all Amazon Web Services managed policies.

You can filter the list of policies that is returned using the optional `OnlyAttached` , `Scope` , and `PathPrefix` parameters. For example, to list only the customer managed policies in your Amazon Web Services account, set `Scope` to `Local` . To list only Amazon Web Services managed policies, set `Scope` to `AWS` .

You can paginate the results using the `MaxItems` and `Marker` parameters.

For more information about managed policies, see Managed policies and inline policies in the *IAM User Guide* .

### Note

IAM resource-listing operations return a subset of the available attributes for the resource. For example, this operation does not return tags, even though they are an attribute of the returned object. To view all of the information for a customer manged policy, see

GetPolicy

.

See also: AWS API Documentation

`list-policies` is a paginated operation. Multiple API calls may be issued in order to retrieve the entire data set of results. You can disable pagination by providing the `--no-paginate` argument. When using `--output text` and the `--query` argument on a paginated response, the `--query` argument must extract data from the results of the following query expressions: `Policies`

## Options

`--scope` (string)

> 
> 
> 
> 
> The scope to use for filtering the results.
> 
> To list only Amazon Web Services managed policies, set `Scope` to `AWS` . To list only the customer managed policies in your Amazon Web Services account, set `Scope` to `Local` .
> 
> This parameter is optional. If it is not included, or if it is set to `All` , all policies are returned.
> 
> Possible values:
> 
> 

`--only-attached` | `--no-only-attached` (boolean)

> 
> 
> 
> 
> A flag to filter the results to only the attached policies.
> 
> When `OnlyAttached` is `true` , the returned list contains only the policies that are attached to an IAM user, group, or role. When `OnlyAttached` is `false` , or when the parameter is not included, all policies are returned.
> 
> 

`--path-prefix` (string)

> 
> 
> 
> 
> The path prefix for filtering the results. This parameter is optional. If it is not included, it defaults to a slash (/), listing all policies. This parameter allows (through its regex pattern ) a string of characters consisting of either a forward slash (/) by itself or a string that must begin and end with forward slashes. In addition, it can contain any ASCII character from the \! (`\u0021` ) through the DEL character (`\u007F` ), including most punctuation characters, digits, and upper and lowercased letters.
> 
> Constraints:
> 
>   - min: `1`
>   - max: `512`
>   - pattern: `((/[A-Za-z0-9\.,\+@=_-]+)*)/`
> 
> 

`--policy-usage-filter` (string)

> 
> 
> 
> 
> The policy usage method to use for filtering the results.
> 
> To list only permissions policies, set `PolicyUsageFilter` to `PermissionsPolicy` . To list only the policies used to set permissions boundaries, set the value to `PermissionsBoundary` .
> 
> This parameter is optional. If it is not included, all policies are returned.
> 
> Possible values:
> 
>   - `PermissionsPolicy`
>   - `PermissionsBoundary`
> 
> 

`--max-items` (integer)

> 
> 
> 
> 
> The total number of items to return in the commandâ€™s output. If the total number of items available is more than the value specified, a `NextToken` is provided in the commandâ€™s output. To resume pagination, provide the `NextToken` value in the `starting-token` argument of a subsequent command. **Do not** use the `NextToken` response element directly outside of the AWS CLI.
> 
> For usage examples, see Pagination in the *AWS Command Line Interface User Guide* .
> 
> 

`--cli-input-json` | `--cli-input-yaml` (string) Reads arguments from the JSON string provided. The JSON string follows the format provided by `--generate-cli-skeleton`. If other arguments are provided on the command line, those values will override the JSON-provided values. It is not possible to pass arbitrary binary values using a JSON-provided value as the string will be taken literally. This may not be specified along with `--cli-input-yaml`.

`--starting-token` (string)

> 
> 
> 
> 
> A token to specify where to start paginating. This is the `NextToken` from a previously truncated response.
> 
> For usage examples, see Pagination in the *AWS Command Line Interface User Guide* .
> 
> 

`--page-size` (integer)

> 
> 
> 
> 
> The size of each page to get in the AWS service call. This does not affect the number of items returned in the commandâ€™s output. Setting a smaller page size results in more calls to the AWS service, retrieving fewer items in each call. This can help prevent the AWS service calls from timing out.
> 
> For usage examples, see Pagination in the *AWS Command Line Interface User Guide* .
> 
> 

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

**To list managed policies that are available to your AWS account**

This example returns a collection of the first two managed policies available in the current AWS account.

    aws iam list-policies \
        --max-items 3

Output:

    {
        "Policies": [
            {
                "PolicyName": "AWSCloudTrailAccessPolicy",
                "PolicyId": "ANPAXQE2B5PJ7YEXAMPLE",
                "Arn": "arn:aws:iam::123456789012:policy/AWSCloudTrailAccessPolicy",
                "Path": "/",
                "DefaultVersionId": "v1",
                "AttachmentCount": 0,
                "PermissionsBoundaryUsageCount": 0,
                "IsAttachable": true,
                "CreateDate": "2019-09-04T17:43:42+00:00",
                "UpdateDate": "2019-09-04T17:43:42+00:00"
            },
            {
                "PolicyName": "AdministratorAccess",
                "PolicyId": "ANPAIWMBCKSKIEE64ZLYK",
                "Arn": "arn:aws:iam::aws:policy/AdministratorAccess",
                "Path": "/",
                "DefaultVersionId": "v1",
                "AttachmentCount": 6,
                "PermissionsBoundaryUsageCount": 0,
                "IsAttachable": true,
                "CreateDate": "2015-02-06T18:39:46+00:00",
                "UpdateDate": "2015-02-06T18:39:46+00:00"
            },
            {
                "PolicyName": "PowerUserAccess",
                "PolicyId": "ANPAJYRXTHIB4FOVS3ZXS",
                "Arn": "arn:aws:iam::aws:policy/PowerUserAccess",
                "Path": "/",
                "DefaultVersionId": "v5",
                "AttachmentCount": 1,
                "PermissionsBoundaryUsageCount": 0,
                "IsAttachable": true,
                "CreateDate": "2015-02-06T18:39:47+00:00",
                "UpdateDate": "2023-07-06T22:04:00+00:00"
            }
        ],
        "NextToken": "EXAMPLErZXIiOiBudWxsLCAiYm90b190cnVuY2F0ZV9hbW91bnQiOiA4fQ=="
    }

For more information, see Policies and permissions in IAM in the *AWS IAM User Guide*.