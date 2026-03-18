---
title: "AWS CLI 2.34.3 Command Reference"
source: "https://awscli.amazonaws.com/v2/documentation/api/latest/reference/iam/create-role.html"
fetched: "20260306T011536Z"
---

## Options

`--path` (string)

> 
> 
> 
> 
> The path to the role. For more information about paths, see IAM Identifiers in the *IAM User Guide* .
> 
> This parameter is optional. If it is not included, it defaults to a slash (/).
> 
> This parameter allows (through its regex pattern ) a string of characters consisting of either a forward slash (/) by itself or a string that must begin and end with forward slashes. In addition, it can contain any ASCII character from the \! (`\u0021` ) through the DEL character (`\u007F` ), including most punctuation characters, digits, and upper and lowercased letters.
> 
> Constraints:
> 
>   - min: `1`
>   - max: `512`
>   - pattern: `(\u002F)|(\u002F[\u0021-\u007E]+\u002F)`
> 
> 

`--role-name` (string) \[required\]

> 
> 
> 
> 
> The name of the role to create.
> 
> IAM user, group, role, and policy names must be unique within the account. Names are not distinguished by case. For example, you cannot create resources named both â€œMyResourceâ€? and â€œmyresourceâ€?.
> 
> This parameter allows (through its regex pattern ) a string of characters consisting of upper and lowercase alphanumeric characters with no spaces. You can also include any of the following characters: \_+=,.@-
> 
> Constraints:
> 
>   - min: `1`
>   - max: `64`
>   - pattern: `[\w+=,.@-]+`
> 
> 

`--assume-role-policy-document` (string) \[required\]

> 
> 
> 
> 
> The trust relationship policy document that grants an entity permission to assume the role.
> 
> In IAM, you must provide a JSON policy that has been converted to a string. However, for CloudFormation templates formatted in YAML, you can provide the policy in JSON or YAML format. CloudFormation always converts a YAML policy to JSON format before submitting it to IAM.
> 
> The regex pattern used to validate this parameter is a string of characters consisting of the following:
> 
>   - Any printable ASCII character ranging from the space character (`\u0020` ) through the end of the ASCII character range
>   - The printable characters in the Basic Latin and Latin-1 Supplement character set (through `\u00FF` )
>   - The special characters tab (`\u0009` ), line feed (`\u000A` ), and carriage return (`\u000D` )
> 
> Upon success, the response includes the same trust policy in JSON format.
> 
> Constraints:
> 
>   - min: `1`
>   - max: `131072`
>   - pattern: `[\u0009\u000A\u000D\u0020-\u00FF]+`
> 
> 

`--description` (string)

> 
> 
> 
> 
> A description of the role.
> 
> Constraints:
> 
>   - max: `1000`
>   - pattern: `[\u0009\u000A\u000D\u0020-\u007E\u00A1-\u00FF]*`
> 
> 

`--max-session-duration` (integer)

> 
> 
> 
> 
> The maximum session duration (in seconds) that you want to set for the specified role. If you do not specify a value for this setting, the default value of one hour is applied. This setting can have a value from 1 hour to 12 hours.
> 
> Anyone who assumes the role from the CLI or API can use the `DurationSeconds` API parameter or the `duration-seconds` CLI parameter to request a longer session. The `MaxSessionDuration` setting determines the maximum duration that can be requested using the `DurationSeconds` parameter. If users donâ€™t specify a value for the `DurationSeconds` parameter, their security credentials are valid for one hour by default. This applies when you use the `AssumeRole*` API operations or the `assume-role*` CLI operations but does not apply when you use those operations to create a console URL. For more information, see Using IAM roles in the *IAM User Guide* .
> 
> Constraints:
> 
> 

`--permissions-boundary` (string)

> 
> 
> 
> 
> The ARN of the managed policy that is used to set the permissions boundary for the role.
> 
> A permissions boundary policy defines the maximum permissions that identity-based policies can grant to an entity, but does not grant permissions. Permissions boundaries do not define the maximum permissions that a resource-based policy can grant to an entity. To learn more, see Permissions boundaries for IAM entities in the *IAM User Guide* .
> 
> For more information about policy types, see Policy types in the *IAM User Guide* .
> 
> Constraints:
> 
> 

`--tags` (list)

> 
> 
> 
> 
> A list of tags that you want to attach to the new role. Each tag consists of a key name and an associated value. For more information about tagging, see Tagging IAM resources in the *IAM User Guide* .
> 
> ### Note
> 
> If any one of the tags is invalid or if you exceed the allowed maximum number of tags, then the entire request fails and the resource is not created.
> 
> Constraints:
> 
> (structure)
> 
> > 
> > 
> > 
> > 
> > A structure that represents user-provided metadata that can be associated with an IAM resource. For more information about tagging, see Tagging IAM resources in the *IAM User Guide* .
> > 
> > Key -\> (string) \[required\]
> > 
> > > 
> > > 
> > > 
> > > 
> > > The key name that can be used to look up or retrieve the associated value. For example, `Department` or `Cost Center` are common choices.
> > > 
> > > Constraints:
> > > 
> > >   - min: `1`
> > >   - max: `128`
> > >   - pattern: `[\p{L}\p{Z}\p{N}_.:/=+\-@]+`
> > > 
> > > 
> > 
> > Value -\> (string) \[required\]
> > 
> > > 
> > > 
> > > 
> > > 
> > > The value associated with this tag. For example, tags with a key name of `Department` could have values such as `Human Resources` , `Accounting` , and `Support` . Tags with a key name of `Cost Center` might have values that consist of the number associated with the different cost centers in your company. Typically, many resources have tags with the same key name but with different values.
> > > 
> > > Constraints:
> > > 
> > >   - min: `0`
> > >   - max: `256`
> > >   - pattern: `[\p{L}\p{Z}\p{N}_.:/=+\-@]*`
> > > 
> > > 
> > 
> > 
> 
> 

Shorthand Syntax:

    Key=string,Value=string ...

JSON Syntax:

    [
      {
        "Key": "string",
        "Value": "string"
      }
      ...
    ]

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

**Example 1: To create an IAM role**

The following `create-role` command creates a role named `Test-Role` and attaches a trust policy to it.

    aws iam create-role \
        --role-name Test-Role \
        --assume-role-policy-document file://Test-Role-Trust-Policy.json

Output:

    {
        "Role": {
            "AssumeRolePolicyDocument": "<URL-encoded-JSON>",
            "RoleId": "AKIAIOSFODNN7EXAMPLE",
            "CreateDate": "2013-06-07T20:43:32.821Z",
            "RoleName": "Test-Role",
            "Path": "/",
            "Arn": "arn:aws:iam::123456789012:role/Test-Role"
        }
    }

The trust policy is defined as a JSON document in the *Test-Role-Trust-Policy.json* file. (The file name and extension do not have significance.) The trust policy must specify a principal.

To attach a permissions policy to a role, use the `put-role-policy` command.

For more information, see Creating IAM roles in the *AWS IAM User Guide*.

**Example 2: To create an IAM role with specified maximum session duration**

The following `create-role` command creates a role named `Test-Role` and sets a maximum session duration of 7200 seconds (2 hours).

    aws iam create-role \
        --role-name Test-Role \
        --assume-role-policy-document file://Test-Role-Trust-Policy.json \
        --max-session-duration 7200

Output:

    {
        "Role": {
            "Path": "/",
            "RoleName": "Test-Role",
            "RoleId": "AKIAIOSFODNN7EXAMPLE",
            "Arn": "arn:aws:iam::12345678012:role/Test-Role",
            "CreateDate": "2023-05-24T23:50:25+00:00",
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "Statement1",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": "arn:aws:iam::12345678012:root"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
        }
    }

For more information, see Modifying a role maximum session duration (AWS API) in the *AWS IAM User Guide*.

**Example 3: To create an IAM Role with tags**

The following command creates an IAM Role `Test-Role` with tags. This example uses the `--tags` parameter flag with the following JSON-formatted tags: `'{"Key": "Department", "Value": "Accounting"}' '{"Key": "Location", "Value": "Seattle"}'`. Alternatively, the `--tags` flag can be used with tags in the shorthand format: `'Key=Department,Value=Accounting Key=Location,Value=Seattle'`.

    aws iam create-role \
        --role-name Test-Role \
        --assume-role-policy-document file://Test-Role-Trust-Policy.json \
        --tags '{"Key": "Department", "Value": "Accounting"}' '{"Key": "Location", "Value": "Seattle"}'

Output:

    {
        "Role": {
            "Path": "/",
            "RoleName": "Test-Role",
            "RoleId": "AKIAIOSFODNN7EXAMPLE",
            "Arn": "arn:aws:iam::123456789012:role/Test-Role",
            "CreateDate": "2023-05-25T23:29:41+00:00",
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "Statement1",
                        "Effect": "Allow",
                        "Principal": {
                            "AWS": "arn:aws:iam::123456789012:root"
                        },
                        "Action": "sts:AssumeRole"
                    }
                ]
            },
            "Tags": [
                {
                    "Key": "Department",
                    "Value": "Accounting"
                },
                {
                    "Key": "Location",
                    "Value": "Seattle"
                }
            ]
        }
    }

For more information, see Tagging IAM roles in the *AWS IAM User Guide*.