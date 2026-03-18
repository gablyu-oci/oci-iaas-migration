---
title: "Actions, resources, and condition keys for AWS Identity and Access Management (IAM)"
source: "https://docs.aws.amazon.com/IAM/latest/UserGuide/list_awsidentityandaccessmanagementiam.html"
fetched: "20260306T011530Z"
---

<table style="width:100%;">
<colgroup>
<col style="width: 16%" />
<col style="width: 16%" />
<col style="width: 16%" />
<col style="width: 16%" />
<col style="width: 16%" />
<col style="width: 16%" />
</colgroup>
<thead>
<tr class="header">
<th>Actions</th>
<th>Description</th>
<th>Access level</th>
<th>Resource types (*required)</th>
<th>Condition keys</th>
<th>Dependent actions</th>
</tr>
</thead>
<tbody>
<tr class="odd">
<td>AcceptDelegationRequest</td>
<td>Accepts a delegation request resource, granting the requested temporary access</td>
<td>Write</td>
<td><p>delegation-request*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>AddClientIDToOpenIDConnectProvider</td>
<td>Grants permission to add a new client ID (audience) to the list of registered IDs for the specified IAM OpenID Connect (OIDC) provider resource</td>
<td>Write</td>
<td><p>oidc-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>AddRoleToInstanceProfile</td>
<td>Grants permission to add an IAM role to the specified instance profile</td>
<td>Write</td>
<td><p>instance-profile*</p></td>
<td></td>
<td><p>iam:PassRole</p></td>
</tr>
<tr class="even">
<td>AddUserToGroup</td>
<td>Grants permission to add an IAM user to the specified IAM group</td>
<td>Write</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>AssociateDelegationRequest</td>
<td>Associates a delegation request resource with the calling identity</td>
<td>Write</td>
<td><p>delegation-request*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>AttachGroupPolicy</td>
<td>Grants permission to attach a managed policy to the specified IAM group</td>
<td>Permissions management</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PolicyARN</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>AttachRolePolicy</td>
<td>Grants permission to attach a managed policy to the specified IAM role</td>
<td>Permissions management</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PolicyARN</p>
<p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>AttachUserPolicy</td>
<td>Grants permission to attach a managed policy to the specified IAM user</td>
<td>Permissions management</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PolicyARN</p>
<p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ChangePassword</td>
<td>Grants permission to an IAM user to change their own password</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>CreateAccessKey</td>
<td>Grants permission to create access key and secret access key for the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>CreateAccountAlias</td>
<td>Grants permission to create an alias for your AWS account</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>CreateDelegationRequest</td>
<td>Creates an IAM delegation request resource for temporary access delegation</td>
<td>Write</td>
<td><p>delegation-request*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>iam:DelegationDuration</p>
<p>iam:NotificationChannel</p>
<p>iam:TemplateArn</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>CreateGroup</td>
<td>Grants permission to create a new group</td>
<td>Write</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>CreateInstanceProfile</td>
<td>Grants permission to create a new instance profile</td>
<td>Write</td>
<td><p>instance-profile*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>CreateLoginProfile</td>
<td>Grants permission to create a password for the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>CreateOpenIDConnectProvider</td>
<td>Grants permission to create an IAM resource that describes an identity provider (IdP) that supports OpenID Connect (OIDC)</td>
<td>Write</td>
<td><p>oidc-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>CreatePolicy</td>
<td>Grants permission to create a new managed policy</td>
<td>Permissions management</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>CreatePolicyVersion</td>
<td>Grants permission to create a new version of the specified managed policy</td>
<td>Permissions management</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>CreateRole</td>
<td>Grants permission to create a new role</td>
<td>Write</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PermissionsBoundary</p>
<p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>CreateSAMLProvider</td>
<td>Grants permission to create an IAM resource that describes an identity provider (IdP) that supports SAML 2.0</td>
<td>Write</td>
<td><p>saml-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>CreateServiceLinkedRole</td>
<td>Grants permission to create an IAM role that allows an AWS service to perform actions on your behalf</td>
<td>Write</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:AWSServiceName</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>CreateServiceSpecificCredential</td>
<td>Grants permission to create a new service-specific credential for an IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:ServiceSpecificCredentialAgeDays</p>
<p>iam:ServiceSpecificCredentialServiceName</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>CreateUser</td>
<td>Grants permission to create a new IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PermissionsBoundary</p>
<p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>CreateVirtualMFADevice</td>
<td>Grants permission to create a new virtual MFA device</td>
<td>Write</td>
<td><p>mfa*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeactivateMFADevice</td>
<td>Grants permission to deactivate the specified MFA device and remove its association with the IAM user for which it was originally enabled</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>DeleteAccessKey</td>
<td>Grants permission to delete the access key pair that is associated with the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteAccountAlias</td>
<td>Grants permission to delete the specified AWS account alias</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>DeleteAccountPasswordPolicy</td>
<td>Grants permission to delete the password policy for the AWS account</td>
<td>Permissions management</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteCloudFrontPublicKey</td>
<td>Grants permission to delete an existing CloudFront public key</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>DeleteGroup</td>
<td>Grants permission to delete the specified IAM group</td>
<td>Write</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteGroupPolicy</td>
<td>Grants permission to delete the specified inline policy from its group</td>
<td>Permissions management</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>DeleteInstanceProfile</td>
<td>Grants permission to delete the specified instance profile</td>
<td>Write</td>
<td><p>instance-profile*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteLoginProfile</td>
<td>Grants permission to delete the password for the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>DeleteOpenIDConnectProvider</td>
<td>Grants permission to delete an OpenID Connect identity provider (IdP) resource object in IAM</td>
<td>Write</td>
<td><p>oidc-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeletePolicy</td>
<td>Grants permission to delete the specified managed policy and remove it from any IAM entities (users, groups, or roles) to which it is attached</td>
<td>Permissions management</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>DeletePolicyVersion</td>
<td>Grants permission to delete a version from the specified managed policy</td>
<td>Permissions management</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteRole</td>
<td>Grants permission to delete the specified role</td>
<td>Write</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteRolePermissionsBoundary</td>
<td>Grants permission to remove the permissions boundary from a role</td>
<td>Permissions management</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteRolePolicy</td>
<td>Grants permission to delete the specified inline policy from the specified role</td>
<td>Permissions management</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteSAMLProvider</td>
<td>Grants permission to delete a SAML provider resource in IAM</td>
<td>Write</td>
<td><p>saml-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>DeleteSSHPublicKey</td>
<td>Grants permission to delete the specified SSH public key</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteServerCertificate</td>
<td>Grants permission to delete the specified server certificate</td>
<td>Write</td>
<td><p>server-certificate*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>DeleteServiceLinkedRole</td>
<td>Grants permission to delete an IAM role that is linked to a specific AWS service, if the service is no longer using it</td>
<td>Write</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteServiceSpecificCredential</td>
<td>Grants permission to delete the specified service-specific credential for an IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:ServiceSpecificCredentialServiceName</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteSigningCertificate</td>
<td>Grants permission to delete a signing certificate that is associated with the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>DeleteUser</td>
<td>Grants permission to delete the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteUserPermissionsBoundary</td>
<td>Grants permission to remove the permissions boundary from the specified IAM user</td>
<td>Permissions management</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteUserPolicy</td>
<td>Grants permission to delete the specified inline policy from an IAM user</td>
<td>Permissions management</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DeleteVirtualMFADevice</td>
<td>Grants permission to delete a virtual MFA device</td>
<td>Write</td>
<td><p>mfa</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td><p>sms-mfa</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DetachGroupPolicy</td>
<td>Grants permission to detach a managed policy from the specified IAM group</td>
<td>Permissions management</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PolicyARN</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DetachRolePolicy</td>
<td>Grants permission to detach a managed policy from the specified role</td>
<td>Permissions management</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PolicyARN</p>
<p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DetachUserPolicy</td>
<td>Grants permission to detach a managed policy from the specified IAM user</td>
<td>Permissions management</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PolicyARN</p>
<p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DisableOrganizationsRootCredentialsManagement</td>
<td>Grants permission to disable the management of member account root user credentials for an organization managed under the current account</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>DisableOrganizationsRootSessions</td>
<td>Grants permission to disable privileged root actions in member accounts for an organization managed under the current account</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>DisableOutboundWebIdentityFederation</td>
<td>Disables the outbound identity federation feature for the callers account</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>EnableMFADevice</td>
<td>Grants permission to enable an MFA device and associate it with the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>iam:RegisterSecurityKey</p>
<p>iam:FIDO-FIPS-140-2-certification</p>
<p>iam:FIDO-FIPS-140-3-certification</p>
<p>iam:FIDO-certification</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>EnableOrganizationsRootCredentialsManagement</td>
<td>Grants permission to enable the management of member account root user credentials for an organization managed under the current account</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>EnableOrganizationsRootSessions</td>
<td>Grants permission to enable privileged root actions in member accounts for an organization managed under the current account</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>EnableOutboundWebIdentityFederation</td>
<td>Enables the outbound identity federation feature for the callers account</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GenerateCredentialReport</td>
<td>Grants permission to generate a credential report for the AWS account</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GenerateOrganizationsAccessReport</td>
<td>Grants permission to generate an access report for an AWS Organizations entity</td>
<td>Read</td>
<td><p>access-report*</p></td>
<td></td>
<td><p>organizations:DescribePolicy</p>
<p>organizations:ListChildren</p>
<p>organizations:ListParents</p>
<p>organizations:ListPoliciesForTarget</p>
<p>organizations:ListRoots</p>
<p>organizations:ListTargetsForPolicy</p></td>
</tr>
<tr class="even">
<td></td>
<td><p>iam:OrganizationsPolicyId</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GenerateServiceLastAccessedDetails</td>
<td>Grants permission to generate a service last accessed data report for an IAM resource</td>
<td>Read</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td><p>policy*</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td><p>role*</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td><p>user*</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetAccessKeyLastUsed</td>
<td>Grants permission to retrieve information about when the specified access key was last used</td>
<td>Read</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetAccountAuthorizationDetails</td>
<td>Grants permission to retrieve information about all IAM users, groups, roles, and policies in your AWS account, including their relationships to one another</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetAccountEmailAddress</td>
<td>Grants permission to retrieve the email address that is associated with the account</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetAccountName</td>
<td>Grants permission to retrieve the account name that is associated with the account</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetAccountPasswordPolicy</td>
<td>Grants permission to retrieve the password policy for the AWS account</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetAccountSummary</td>
<td>Grants permission to retrieve information about IAM entity usage and IAM quotas in the AWS account</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetCloudFrontPublicKey</td>
<td>Grants permission to retrieve information about the specified CloudFront public key</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetContextKeysForCustomPolicy</td>
<td>Grants permission to retrieve a list of all of the context keys that are referenced in the specified policy</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetContextKeysForPrincipalPolicy</td>
<td>Grants permission to retrieve a list of all context keys that are referenced in all IAM policies that are attached to the specified IAM identity (user, group, or role)</td>
<td>Read</td>
<td><p>group</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td><p>role</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td><p>user</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetCredentialReport</td>
<td>Grants permission to retrieve a credential report for the AWS account</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetDelegationRequest</td>
<td>Retrieves information about a specific delegation request</td>
<td>Read</td>
<td><p>delegation-request*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetGroup</td>
<td>Grants permission to retrieve a list of IAM users in the specified IAM group</td>
<td>Read</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetGroupPolicy</td>
<td>Grants permission to retrieve an inline policy document that is embedded in the specified IAM group</td>
<td>Read</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetHumanReadableSummary</td>
<td>Retrieves a human readable summary for a given entity. At this time, only delegation request are supported</td>
<td>Read</td>
<td><p>delegation-request*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetInstanceProfile</td>
<td>Grants permission to retrieve information about the specified instance profile, including the instance profile's path, GUID, ARN, and role</td>
<td>Read</td>
<td><p>instance-profile*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetLoginProfile</td>
<td>Grants permission to retrieve the user name and password creation date for the specified IAM user</td>
<td>List</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetMFADevice</td>
<td>Grants permission to retrieve information about an MFA device for the specified user</td>
<td>Read</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetOpenIDConnectProvider</td>
<td>Grants permission to retrieve information about the specified OpenID Connect (OIDC) provider resource in IAM</td>
<td>Read</td>
<td><p>oidc-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetOrganizationsAccessReport</td>
<td>Grants permission to retrieve an AWS Organizations access report</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetOutboundWebIdentityFederationInfo</td>
<td>Retrieves the configuration information for the outbound identity federation feature for the callers account</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetPolicy</td>
<td>Grants permission to retrieve information about the specified managed policy, including the policy's default version and the total number of identities to which the policy is attached</td>
<td>Read</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetPolicyVersion</td>
<td>Grants permission to retrieve information about a version of the specified managed policy, including the policy document</td>
<td>Read</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetRole</td>
<td>Grants permission to retrieve information about the specified role, including the role's path, GUID, ARN, and the role's trust policy</td>
<td>Read</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetRolePolicy</td>
<td>Grants permission to retrieve an inline policy document that is embedded with the specified IAM role</td>
<td>Read</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetSAMLProvider</td>
<td>Grants permission to retrieve the SAML provider metadocument that was uploaded when the IAM SAML provider resource was created or updated</td>
<td>Read</td>
<td><p>saml-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetSSHPublicKey</td>
<td>Grants permission to retrieve the specified SSH public key, including metadata about the key</td>
<td>Read</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetServerCertificate</td>
<td>Grants permission to retrieve information about the specified server certificate stored in IAM</td>
<td>Read</td>
<td><p>server-certificate*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetServiceLastAccessedDetails</td>
<td>Grants permission to retrieve information about the service last accessed data report</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetServiceLastAccessedDetailsWithEntities</td>
<td>Grants permission to retrieve information about the entities from the service last accessed data report</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetServiceLinkedRoleDeletionStatus</td>
<td>Grants permission to retrieve an IAM service-linked role deletion status</td>
<td>Read</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>GetUser</td>
<td>Grants permission to retrieve information about the specified IAM user, including the user's creation date, path, unique ID, and ARN</td>
<td>Read</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>GetUserPolicy</td>
<td>Grants permission to retrieve an inline policy document that is embedded in the specified IAM user</td>
<td>Read</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListAccessKeys</td>
<td>Grants permission to list information about the access key IDs that are associated with the specified IAM user</td>
<td>List</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListAccountAliases</td>
<td>Grants permission to list the account alias that is associated with the AWS account</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListAttachedGroupPolicies</td>
<td>Grants permission to list all managed policies that are attached to the specified IAM group</td>
<td>List</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListAttachedRolePolicies</td>
<td>Grants permission to list all managed policies that are attached to the specified IAM role</td>
<td>List</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListAttachedUserPolicies</td>
<td>Grants permission to list all managed policies that are attached to the specified IAM user</td>
<td>List</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListCloudFrontPublicKeys</td>
<td>Grants permission to list all current CloudFront public keys for the account</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListDelegationRequests</td>
<td>Lists delegation requests based on the specified criteria</td>
<td>List</td>
<td></td>
<td><p>iam:DelegationRequestOwner</p></td>
<td></td>
</tr>
<tr class="odd">
<td>ListEntitiesForPolicy</td>
<td>Grants permission to list all IAM identities to which the specified managed policy is attached</td>
<td>List</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListGroupPolicies</td>
<td>Grants permission to list the names of the inline policies that are embedded in the specified IAM group</td>
<td>List</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListGroups</td>
<td>Grants permission to list the IAM groups that have the specified path prefix</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListGroupsForUser</td>
<td>Grants permission to list the IAM groups that the specified IAM user belongs to</td>
<td>List</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListInstanceProfileTags</td>
<td>Grants permission to list the tags that are attached to the specified instance profile</td>
<td>List</td>
<td><p>instance-profile*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListInstanceProfiles</td>
<td>Grants permission to list the instance profiles that have the specified path prefix</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListInstanceProfilesForRole</td>
<td>Grants permission to list the instance profiles that have the specified associated IAM role</td>
<td>List</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListMFADeviceTags</td>
<td>Grants permission to list the tags that are attached to the specified virtual mfa device</td>
<td>List</td>
<td><p>mfa*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListMFADevices</td>
<td>Grants permission to list the MFA devices for an IAM user</td>
<td>List</td>
<td><p>user</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListOpenIDConnectProviderTags</td>
<td>Grants permission to list the tags that are attached to the specified OpenID Connect provider</td>
<td>List</td>
<td><p>oidc-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListOpenIDConnectProviders</td>
<td>Grants permission to list information about the IAM OpenID Connect (OIDC) provider resource objects that are defined in the AWS account</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListOrganizationsFeatures</td>
<td>Grants permission to list the centralized root access features enabled for your organization</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListPolicies</td>
<td>Grants permission to list all managed policies</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListPoliciesGrantingServiceAccess</td>
<td>Grants permission to list information about the policies that grant an entity access to a specific service</td>
<td>List</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td><p>role*</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td><p>user*</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListPolicyTags</td>
<td>Grants permission to list the tags that are attached to the specified managed policy</td>
<td>List</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListPolicyVersions</td>
<td>Grants permission to list information about the versions of the specified managed policy, including the version that is currently set as the policy's default version</td>
<td>List</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListRolePolicies</td>
<td>Grants permission to list the names of the inline policies that are embedded in the specified IAM role</td>
<td>List</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListRoleTags</td>
<td>Grants permission to list the tags that are attached to the specified IAM role</td>
<td>List</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListRoles</td>
<td>Grants permission to list the IAM roles that have the specified path prefix</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListSAMLProviderTags</td>
<td>Grants permission to list the tags that are attached to the specified SAML provider</td>
<td>List</td>
<td><p>saml-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListSAMLProviders</td>
<td>Grants permission to list the SAML provider resources in IAM</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListSSHPublicKeys</td>
<td>Grants permission to list information about the SSH public keys that are associated with the specified IAM user</td>
<td>List</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListSTSRegionalEndpointsStatus</td>
<td>Grants permission to list the status of all active STS regional endpoints</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListServerCertificateTags</td>
<td>Grants permission to list the tags that are attached to the specified server certificate</td>
<td>List</td>
<td><p>server-certificate*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListServerCertificates</td>
<td>Grants permission to list the server certificates that have the specified path prefix</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListServiceSpecificCredentials</td>
<td>Grants permission to list the service-specific credentials that are associated with the specified IAM user</td>
<td>List</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListSigningCertificates</td>
<td>Grants permission to list information about the signing certificates that are associated with the specified IAM user</td>
<td>List</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListUserPolicies</td>
<td>Grants permission to list the names of the inline policies that are embedded in the specified IAM user</td>
<td>List</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListUserTags</td>
<td>Grants permission to list the tags that are attached to the specified IAM user</td>
<td>List</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>ListUsers</td>
<td>Grants permission to list the IAM users that have the specified path prefix</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ListVirtualMFADevices</td>
<td>Grants permission to list virtual MFA devices by assignment status</td>
<td>List</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>PassRole [permission only]</td>
<td>Grants permission to pass a role to a service</td>
<td>Write</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:AssociatedResourceArn</p>
<p>iam:PassedToService</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>PutGroupPolicy</td>
<td>Grants permission to create or update an inline policy document that is embedded in the specified IAM group</td>
<td>Permissions management</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>PutRolePermissionsBoundary</td>
<td>Grants permission to set a managed policy as a permissions boundary for a role</td>
<td>Permissions management</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>PutRolePolicy</td>
<td>Grants permission to create or update an inline policy document that is embedded in the specified IAM role</td>
<td>Permissions management</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>PutUserPermissionsBoundary</td>
<td>Grants permission to set a managed policy as a permissions boundary for an IAM user</td>
<td>Permissions management</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>PutUserPolicy</td>
<td>Grants permission to create or update an inline policy document that is embedded in the specified IAM user</td>
<td>Permissions management</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>RejectDelegationRequest</td>
<td>Rejects a delegation request, denying the requested temporary access</td>
<td>Write</td>
<td><p>delegation-request*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>RemoveClientIDFromOpenIDConnectProvider</td>
<td>Grants permission to remove the client ID (audience) from the list of client IDs in the specified IAM OpenID Connect (OIDC) provider resource</td>
<td>Write</td>
<td><p>oidc-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>RemoveRoleFromInstanceProfile</td>
<td>Grants permission to remove an IAM role from the specified EC2 instance profile</td>
<td>Write</td>
<td><p>instance-profile*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>RemoveUserFromGroup</td>
<td>Grants permission to remove an IAM user from the specified group</td>
<td>Write</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ResetServiceSpecificCredential</td>
<td>Grants permission to reset the password for an existing service-specific credential for an IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>iam:ServiceSpecificCredentialServiceName</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>ResyncMFADevice</td>
<td>Grants permission to synchronize the specified MFA device with its IAM entity (user or role)</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>SendDelegationToken</td>
<td>Sends the exchange token for an accepted delegation request</td>
<td>Write</td>
<td><p>delegation-request*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>SetDefaultPolicyVersion</td>
<td>Grants permission to set the version of the specified policy as the policy's default version</td>
<td>Permissions management</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>SetSTSRegionalEndpointStatus</td>
<td>Grants permission to activate or deactivate an STS regional endpoint</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>SetSecurityTokenServicePreferences</td>
<td>Grants permission to set the STS global endpoint token version</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>SimulateCustomPolicy</td>
<td>Grants permission to simulate whether an identity-based policy or resource-based policy provides permissions for specific API operations and resources</td>
<td>Read</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>SimulatePrincipalPolicy</td>
<td>Grants permission to simulate whether an identity-based policy that is attached to a specified IAM entity (user or role) provides permissions for specific API operations and resources</td>
<td>Read</td>
<td><p>group</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td><p>role</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td><p>user</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>TagInstanceProfile</td>
<td>Grants permission to add tags to an instance profile</td>
<td>Tagging</td>
<td><p>instance-profile*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>TagMFADevice</td>
<td>Grants permission to add tags to a virtual mfa device</td>
<td>Tagging</td>
<td><p>mfa*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>TagOpenIDConnectProvider</td>
<td>Grants permission to add tags to an OpenID Connect provider</td>
<td>Tagging</td>
<td><p>oidc-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>TagPolicy</td>
<td>Grants permission to add tags to a managed policy</td>
<td>Tagging</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>TagRole</td>
<td>Grants permission to add tags to an IAM role</td>
<td>Tagging</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>TagSAMLProvider</td>
<td>Grants permission to add tags to a SAML Provider</td>
<td>Tagging</td>
<td><p>saml-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>TagServerCertificate</td>
<td>Grants permission to add tags to a server certificate</td>
<td>Tagging</td>
<td><p>server-certificate*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>TagUser</td>
<td>Grants permission to add tags to an IAM user</td>
<td>Tagging</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UntagInstanceProfile</td>
<td>Grants permission to remove the specified tags from the instance profile</td>
<td>Tagging</td>
<td><p>instance-profile*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UntagMFADevice</td>
<td>Grants permission to remove the specified tags from the virtual mfa device</td>
<td>Tagging</td>
<td><p>mfa*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UntagOpenIDConnectProvider</td>
<td>Grants permission to remove the specified tags from the OpenID Connect provider</td>
<td>Tagging</td>
<td><p>oidc-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UntagPolicy</td>
<td>Grants permission to remove the specified tags from the managed policy</td>
<td>Tagging</td>
<td><p>policy*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UntagRole</td>
<td>Grants permission to remove the specified tags from the role</td>
<td>Tagging</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UntagSAMLProvider</td>
<td>Grants permission to remove the specified tags from the SAML Provider</td>
<td>Tagging</td>
<td><p>saml-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UntagServerCertificate</td>
<td>Grants permission to remove the specified tags from the server certificate</td>
<td>Tagging</td>
<td><p>server-certificate*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UntagUser</td>
<td>Grants permission to remove the specified tags from the user</td>
<td>Tagging</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>aws:TagKeys</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UpdateAccessKey</td>
<td>Grants permission to update the status of the specified access key as Active or Inactive</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>UpdateAccountEmailAddress</td>
<td>Grants permission to update the email address that is associated with the account</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UpdateAccountName</td>
<td>Grants permission to update the account name that is associated with the account</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>UpdateAccountPasswordPolicy</td>
<td>Grants permission to update the password policy settings for the AWS account</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UpdateAssumeRolePolicy</td>
<td>Grants permission to update the policy that grants an IAM entity permission to assume a role</td>
<td>Permissions management</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UpdateCloudFrontPublicKey</td>
<td>Grants permission to update an existing CloudFront public key</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>UpdateGroup</td>
<td>Grants permission to update the name or path of the specified IAM group</td>
<td>Write</td>
<td><p>group*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UpdateLoginProfile</td>
<td>Grants permission to change the password for the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>UpdateOpenIDConnectProviderThumbprint</td>
<td>Grants permission to update the entire list of server certificate thumbprints that are associated with an OpenID Connect (OIDC) provider resource</td>
<td>Write</td>
<td><p>oidc-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UpdateRole</td>
<td>Grants permission to update the description or maximum session duration setting of a role</td>
<td>Write</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UpdateRoleDescription</td>
<td>Grants permission to update only the description of a role</td>
<td>Write</td>
<td><p>role*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td></td>
<td><p>iam:PermissionsBoundary</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UpdateSAMLProvider</td>
<td>Grants permission to update the metadata document for an existing SAML provider resource</td>
<td>Write</td>
<td><p>saml-provider*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>UpdateSSHPublicKey</td>
<td>Grants permission to update the status of an IAM user's SSH public key to active or inactive</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UpdateServerCertificate</td>
<td>Grants permission to update the name or the path of the specified server certificate stored in IAM</td>
<td>Write</td>
<td><p>server-certificate*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>UpdateServiceSpecificCredential</td>
<td>Grants permission to update the status of a service-specific credential to active or inactive for an IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>iam:ServiceSpecificCredentialServiceName</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>UpdateSigningCertificate</td>
<td>Grants permission to update the status of the specified user signing certificate to active or disabled</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UpdateUser</td>
<td>Grants permission to update the name or the path of the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>UploadCloudFrontPublicKey</td>
<td>Grants permission to upload a CloudFront public key</td>
<td>Write</td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td>UploadSSHPublicKey</td>
<td>Grants permission to upload an SSH public key and associate it with the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>UploadServerCertificate</td>
<td>Grants permission to upload a server certificate entity for the AWS account</td>
<td>Write</td>
<td><p>server-certificate*</p></td>
<td></td>
<td></td>
</tr>
<tr class="even">
<td></td>
<td><p>aws:TagKeys</p>
<p>aws:RequestTag/${TagKey}</p></td>
<td></td>
<td></td>
<td></td>
<td></td>
</tr>
<tr class="odd">
<td>UploadSigningCertificate</td>
<td>Grants permission to upload an X.509 signing certificate and associate it with the specified IAM user</td>
<td>Write</td>
<td><p>user*</p></td>
<td></td>
<td></td>
</tr>
</tbody>
</table>