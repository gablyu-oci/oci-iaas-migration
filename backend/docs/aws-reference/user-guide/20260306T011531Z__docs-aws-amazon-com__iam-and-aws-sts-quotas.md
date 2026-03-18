---
title: "IAM and AWS STS quotas"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_iam-quotas.html"
fetched: "20260306T011531Z"
---

# IAM and AWS STS quotas

AWS Identity and Access Management (IAM) and AWS Security Token Service (STS) have quotas that limit the size of objects. This affects how you name an object, the number of objects you can create, and the number of characters you can use when you pass an object.

## IAM name requirements

IAM names have the following requirements and restrictions:

  - Policy documents can contain only the following Unicode characters: horizontal tab (U+0009), linefeed (U+000A), carriage return (U+000D), and characters in the range U+0020 to U+00FF.

  - Names of users, groups, roles, policies, instance profiles, server certificates, and paths must be alphanumeric, including the following common characters: plus (+), equals (=), comma (,), period (.), at (@), underscore (\_), and hyphen (-). Path names must begin and end with a forward slash (/).

  - Names of users, groups, roles, and instance profiles must be unique within the account. They arenâ€™t distinguished by case, for example, you can't create groups named both `ADMINS` and `admins`.

  - The external ID value that a third party uses to assume a role must have a minimum of 2 characters and a maximum of 1,224 characters. The value must be alphanumeric without white space. It can also include the following symbols: plus (+), equal (=), comma (,), period (.), at (@), colon (:), forward slash (/), and hyphen (-). For more information about the external ID, see Access to AWS accounts owned by third parties.

  - Policy names for inline policies must be unique to the user, group, or role they're embedded in. The names can contain any Basic Latin (ASCII) characters except for the following reserved characters: backward slash (\\), forward slash (/), asterisk (\*), question mark (?), and white space. These characters are reserved according to RFC 3986, section 2.2.

  - User passwords (login profiles) can contain any Basic Latin (ASCII) characters.

  - AWS account ID aliases must be unique across AWS products, and must be alphanumeric following DNS naming conventions. An alias must be lowercase, it must not start or end with a hyphen, it can't contain two consecutive hyphens, and it can't be a 12-digit number.

For a list of Basic Latin (ASCII) characters, go to the Library of Congress Basic Latin (ASCII) Code Table.

## IAM object quotas

Quotas, also referred to as limits in AWS, are the maximum values for the resources, actions, and items in your AWS account. Use Service Quotas to manage your IAM quotas.

For the list of IAM service endpoints and service quotas, see AWS Identity and Access Management endpoints and quotas in the *AWS General Reference*.

**To request a quota increase**

1.  Follow the sign-in procedure appropriate to your user type as described in the topic How to sign in to AWS in the *AWS Sign-In User Guide* to sign in to the AWS Management Console.

2.  Open the Service Quotas console.

3.  In the navigation pane, choose **AWS services**.

4.  On the navigation bar, choose the **US East (N. Virginia)** Region. Then search for `IAM`.

5.  Choose **AWS Identity and Access Management (IAM)**, choose a quota, and follow the directions to request a quota increase.

For more information, see Requesting a Quota Increase in the *Service Quotas User Guide*.

To see an example of how to request an IAM quota increase using the Service Quotas console, watch the following video.

You can request an increase to default quotas for adjustable IAM quotas. Requests up to the maximum quota are automatically approved and completed within a few minutes.

The following table lists the resources for which quota increases area can be automatically approved.

| Resource                              | Default quota   | Maximum quota   |
| ------------------------------------- | --------------- | --------------- |
| Customer managed policies per account | 1500            | 5000            |
| Groups per account                    | 300             | 500             |
| Instance profiles per account         | 1000            | 5000            |
| Managed policies per role             | 10              | 25              |
| Managed policies per user             | 10              | 20              |
| Managed policies per group            | 10              | 10              |
| Role trust policy length              | 2048 characters | 4096 characters |
| Roles per account                     | 1000            | 5000            |
| Server certificates per account       | 20              | 1000            |
| OpenId connect providers per account  | 100             | 700             |

## IAM Access Analyzer quotas

For the list of IAM Access Analyzer service endpoints and service quotas, see IAM Access Analyzer endpoints and quotas in the *AWS General Reference*.

## IAM Roles Anywhere quotas

For the list of IAM Roles Anywhere service endpoints and service quotas, see AWS Identity and Access Management Roles Anywhere endpoints and quotas in the *AWS General Reference*.

## STS request quotas

The AWS Security Token Service (AWS STS) enforces the following request quotas.

For AWS STS requests made using AWS credentials, the default request quota is **600 requests per second**, per account, per Region. The following AWS STS operations share this quota:

Requests to AWS STS by AWS service principals, such as those used to assume roles for use with an AWS service, do not consume STS request per second quota in your accounts.

For example, if an AWS account makes 100 GetCallerIdentity requests per second and 100 AssumeRole calls per second in the same region, that account is consuming 200 of its available 600 STS requests per second for that region.

For cross-account AssumeRole requests, only the account making the AssumeRole request impacts the STS quota. The target account does not have any of itâ€™s quota consumed.

To request an increase to STS request quotas, please open a ticket with AWS support.

With the upcoming changes to the AWS STS global endpoint (`https://sts.amazonaws.com`), requests to the global endpoint will not share a requests per second (RPS) quota with AWS STS Regional endpoints in Regions that are enabled by default. When a request to the AWS STS global endpoint originates from a single Region, it will count against the global endpoint's RPS quota. However, when requests come from multiple Regions, each additional Region will receive its own independent RPS quota. For more information about the AWS STS global endpoint changes, see AWS STS global endpoint changes.

## IAM and STS character limits

The following are the maximum character counts and size limits for IAM and AWS STS. You can't request an increase for the following limits.

<table>
<colgroup>
<col style="width: 50%" />
<col style="width: 50%" />
</colgroup>
<thead>
<tr class="header">
<th>Description</th>
<th>Limit</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td>Alias for an AWS account ID</td>
<td>3â€“63 characters</td>
</tr>
<tr class="even">
<td>For inline policies</td>
<td>You can add as many inline policies as you want to an IAM user, role, or group. But the total aggregate policy size (the sum size of all inline policies) per entity can't exceed the following limits:

<ul>
<li><p>User policy size can't exceed 2,048 characters.</p></li>
<li><p>Role policy size can't exceed 10,240 characters.</p></li>
<li><p>Group policy size can't exceed 5,120 characters.</p></li>
</ul>

<p>IAM doesn't count white space when calculating the size of a policy against these limits.</p>

</td>
</tr>
<tr class="odd">
<td>For customer managed policies</td>
<td>

<p>IAM doesn't count white space when calculating the size of a policy against this limit.</p>

</td>
</tr>
<tr class="even">
<td>Group name</td>
<td>128 characters</td>
</tr>
<tr class="odd">
<td>Instance profile name</td>
<td>128 characters</td>
</tr>
<tr class="even">
<td>Password for a login profile</td>
<td>1â€“128 characters</td>
</tr>
<tr class="odd">
<td>Path</td>
<td>512 characters</td>
</tr>
<tr class="even">
<td>Policy name</td>
<td>128 characters</td>
</tr>
<tr class="odd">
<td>Role name</td>
<td>64 characters

<p>If you intend to use a role with the <strong>Switch Role</strong> feature in the AWS Management Console, then the combined <code>Path</code> and <code>RoleName</code> can't exceed 64 characters.</p>

</td>
</tr>
<tr class="even">
<td>Role session duration</td>
<td><p>12 hours</p>
<p>When you assume a role from the AWS CLI or API, you can use the <code>duration-seconds</code> CLI parameter or the <code>DurationSeconds</code> API parameter to request a longer role session. You can specify a value from 900 seconds (15 minutes) up to the maximum session duration setting for the role, which can range 1â€“12 hours. If you don't specify a value for the <code>DurationSeconds</code> parameter, your security credentials are valid for one hour. IAM users who switch roles in the console are granted the maximum session duration, or the remaining time in the user's session, whichever is less. The maximum session duration setting doesn't limit sessions assumed by AWS services. To learn how to view the maximum value for your role, see Update the maximum session duration for a role.</p></td>
</tr>
<tr class="odd">
<td>Role session name</td>
<td>64 characters</td>
</tr>
<tr class="even">
<td>Role session policies</td>
<td>
<ul>
<li><p>The size of the passed JSON policy document and all passed managed policy ARN characters combined can't exceed 2,048 characters.</p></li>
<li><p>You can pass a maximum of 10 managed policy ARNs when you create a session.</p></li>
<li><p>You can pass only one JSON policy document when you programmatically create a temporary session for a role or AWS STS federated user principal.</p></li>
<li><p>Additionally, an AWS conversion compresses the passed session policies and session tags into a packed binary format that has <strong>a separate limit</strong>. The <code>PackedPolicySize</code> response element indicates by percentage how close the policies and tags for your request are to the upper size limit.</p></li>
<li><p>We recommend that you pass session policies using the AWS CLI or AWS API. The AWS Management Console might add additional console session information to the packed policy.</p></li>
</ul>
</td>
</tr>
<tr class="odd">
<td>Role session tags</td>
<td>
<ul>
<li><p>Session tags must meet the tag key limit of 128 characters and the tag value limit of 256 characters.</p></li>
<li><p>You can pass up to 50 session tags.</p></li>
<li><p>An AWS conversion compresses the passed session policies and session tags into a packed binary format that has a separate limit. You can pass session tags using the AWS CLI or AWS API. The <code>PackedPolicySize</code> response element indicates by percentage how close the policies and tags for your request are to the upper size limit.</p></li>
</ul>
</td>
</tr>
<tr class="even">
<td>SAML authentication response base64 encoded</td>
<td>100,000 characters
<p>This character limit applies to <code>assume-role-with-saml</code> CLI or <code>AssumeRoleWithSAML</code> API operation.</p></td>
</tr>
<tr class="odd">
<td>Tag key</td>
<td>128 characters
<p>This character limit applies to tags on IAM resources and session tags.</p></td>
</tr>
<tr class="even">
<td>Tag value</td>
<td>256 characters
<p>This character limit applies to tags on IAM resources and session tags.</p>
<p>Tag values can be empty which means tag values can have a length of 0 characters.</p></td>
</tr>
<tr class="odd">
<td><p>Unique IDs created by IAM</p></td>
<td><p>128 characters. For example:</p>

<ul>
<li><p>User IDs that begin with <code>AIDA</code></p></li>
<li><p>Group IDs that begin with <code>AGPA</code></p></li>
<li><p>Role IDs that begin with <code>AROA</code></p></li>
<li><p>Managed policy IDs that begin with <code>ANPA</code></p></li>
<li><p>Server certificate IDs that begin with <code>ASCA</code></p></li>
</ul>

<p>This isn't intended to be an exhaustive list, nor is it a guarantee that IDs of a certain type begin only with the specified letter combination.</p>

</td>
</tr>
<tr class="even">
<td>User name</td>
<td>64 characters</td>
</tr>
</tbody>
</table>