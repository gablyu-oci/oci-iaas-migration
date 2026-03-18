---
title: "Details for IAM without Identity Domains"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/iampolicyreference.htm"
fetched: "20260306T012059Z"
---

`ListRegions`

TENANCY\_INSPECT

`ListRegionSubscriptions`

TENANCY\_INSPECT

`CreateRegionSubscription`

TENANCY\_UPDATE

`GetTenancy`

TENANCY\_INSPECT

`GetAuthenticationPolicy`

AUTHENTICATION\_POLICY\_INSPECT

`UpdateAuthenticationPolicy`

AUTHENTICATION\_POLICY\_UPDATE

`ListAvailabilityDomains`

COMPARTMENT\_INSPECT

`ListFaultDomains`

COMPARTMENT\_INSPECT

`ListCompartments`

COMPARTMENT\_INSPECT

`GetCompartment`

COMPARTMENT\_INSPECT

`UpdateCompartment`

COMPARTMENT\_UPDATE

`CreateCompartment`

COMPARTMENT\_CREATE

`RecoverCompartment`

COMPARTMENT\_RECOVER

`DeleteCompartment`

COMPARTMENT\_DELETE

`MoveCompartment`

There is not a single permission associated with the `MoveCompartment` operation. This operation requires `manage all-resources` permissions on the lowest shared parent compartment of the current compartment and the destination compartment.

`GetWorkRequest`

COMPARTMENT\_READ

`ListUsers`

USER\_INSPECT

`GetUser`

USER\_INSPECT

`UpdateUser`

USER\_UPDATE

`UpdateUserState`

USER\_UPDATE and USER\_UNBLOCK

`CreateUser`

USER\_CREATE

`DeleteUser`

USER\_DELETE

`CreateOrResetUIPassword`

USER\_UPDATE and USER\_UIPASS\_RESET

`ListApiKeys`

USER\_READ

`UploadApiKey`

USER\_UPDATE and USER\_APIKEY\_ADD

`DeleteApiKey`

USER\_UPDATE and USER\_APIKEY\_REMOVE

`ListAuthTokens`

USER\_READ

`UpdateAuthToken`

USER\_UPDATE and USER\_AUTHTOKEN\_RESET

`CreateAuthToken`

USER\_UPDATE and USER\_AUTHTOKEN\_SET

`DeleteAuthToken`

USER\_UPDATE and USER\_AUTHTOKEN\_REMOVE

`ListSwiftPasswords`

USER\_READ

`UpdateSwiftPassword`

USER\_UPDATE and USER\_SWIFTPASS\_RESET

`CreateSwiftPassword`

USER\_UPDATE and USER\_SWIFTPASS\_SET

`DeleteSwiftPassword`

USER\_UPDATE and USER\_SWIFTPASS\_REMOVE

`ListCustomerSecretKeys`

USER\_READ

`CreateSecretKey`

USER\_UPDATE and USER\_SECRETKEY\_ADD

`UpdateCustomerSecretKey`

USER\_UPDATE and USER\_SECRETKEY\_UPDATE

`DeleteCustomerSecretKey`

USER\_UPDATE and USER\_SECRETKEY\_REMOVE

`CreateOAuthClientCredential`

USER\_UPDATE and USER\_OAUTH2\_CLIENT\_CRED\_CREATE

`UpdateOAuthClientCredential`

USER\_UPDATE and USER\_OAUTH2\_CLIENT\_CRED\_UPDATE

`ListOAuthClientCredentials`

USER\_READ

`DeleteOAuthClientCredential`

USER\_UPDATE and USER\_OAUTH2\_CLIENT\_CRED\_REMOVE

`LinkSupportAccount`

USER\_SUPPORT\_ACCOUNT\_LINK

`UnlinkSupportAccount`

USER\_SUPPORT\_ACCOUNT\_UNLINK

`CreateSmtpCredential`

CREDENTIAL\_ADD

`ListSmtpCredentials`

CREDENTIAL\_INSPECT

`UpdateSmtpCredential`

CREDENTIAL\_UPDATE

`DeleteSmtpCredential`

CREDENTIAL\_REMOVE

`ListUserGroupMemberships`

GROUP\_INSPECT and USER\_INSPECT

`GetUserGroupMembership`

USER\_INSPECT and GROUP\_INSPECT

`AddUserToGroup`

GROUP\_UPDATE and USER\_UPDATE

`RemoveUserFromGroup`

GROUP\_UPDATE and USER\_UPDATE

`ListGroups`

GROUP\_INSPECT

`GetGroup`

GROUP\_INSPECT

`UpdateGroup`

GROUP\_UPDATE

`CreateGroup`

GROUP\_CREATE

`DeleteGroup`

GROUP\_DELETE

`ListDynamicGroups`

DYNAMIC\_GROUP\_INSPECT

`GetDynamicGroup`

DYNAMIC\_GROUP\_INSPECT

`UpdateDynamicGroup`

DYNAMIC\_GROUP\_UPDATE

`CreateDynamicGroup`

DYNAMIC\_GROUP\_CREATE

`DeleteDynamicGroup`

DYNAMIC\_GROUP\_DELETE

`GetNetworkSource`

NETWORK\_SOURCE\_INSPECT

`ListNetworkSources`

NETWORK\_SOURCE\_INSPECT

`CreateNetworkSource`

NETWORK\_SOURCE\_CREATE

`UpdateNetworkSource`

NETWORK\_SOURCE\_UPDATE

`DeleteNetworkSource`

NETWORK\_SOURCE\_DELETE

`ListPolicies`

POLICY\_READ

`GetPolicy`

POLICY\_READ

`UpdatePolicy`

POLICY\_UPDATE

`CreatePolicy`

POLICY\_CREATE

`DeletePolicy`

POLICY\_DELETE

`ListIdentityProviders`

IDENTITY\_PROVIDER\_INSPECT

`GetIdentityProvider`

IDENTITY\_PROVIDER\_INSPECT

`UpdateIdentityProvider`

IDENTITY\_PROVIDER\_UPDATE

`CreateIdentityProvider`

IDENTITY\_PROVIDER\_CREATE

`DeleteIdentityProvider`

IDENTITY\_PROVIDER\_DELETE

`ListIdpGroupMappings`

IDENTITY\_PROVIDER\_INSPECT and GROUP\_INSPECT

`GetIdpGroupMapping`

IDENTITY\_PROVIDER\_INSPECT and GROUP\_INSPECT

`AddIdpGroupMapping`

IDENTITY\_PROVIDER\_UPDATE and GROUP\_UPDATE

`DeleteIdpGroupMapping`

IDENTITY\_PROVIDER\_UPDATE and GROUP\_UPDATE

`ListTagNamespaces`

TAG\_NAMESPACE\_INSPECT

`ListTaggingWorkRequest`

TAG\_NAMESPACE\_INSPECT

`ListTaggingWorkRequestErrors`

TAG\_NAMESPACE\_INSPECT

`ListTaggingWorkRequestLogs`

TAG\_NAMESPACE\_INSPECT

`GetTaggingWorkRequest`

TAG\_NAMESPACE\_INSPECT

`GetTagNamespace`

TAG\_NAMESPACE\_INSPECT

`CreateTagNamespace`

TAG\_NAMESPACE\_CREATE

`UpdateTagNamespace`

TAG\_NAMESPACE\_UPDATE

`ChangeTagNamespaceCompartment`

TAG\_NAMESPACE\_MOVE

`CascadeDeleteTagNamespace`

TAG\_NAMESPACE\_DELETE

`DeleteTagNamespace`

TAG\_NAMESPACE\_DELETE

`ListTags`

TAG\_NAMESPACE\_INSPECT

`BulkEditTags`

TAG\_NAMESPACE\_INSPECT

`ListCostTrackingTags`

TAG\_NAMESPACE\_INSPECT

`GetTag`

TAG\_NAMESPACE\_INSPECT

`CreateTag`

TAG\_NAMESPACE\_USE

`UpdateTag`

TAG\_NAMESPACE\_USE

`DeleteTag`

TAG\_NAMESPACE\_DELETE

`BulkDeleteTags`

TAG\_NAMESPACE\_DELETE

`ListTagDefaults`

TAG\_DEFAULT\_INSPECT

`GetTagDefault`

TAG\_DEFAULT\_INSPECT

`CreateTagDefault`

TAG\_DEFAULT\_MANAGE

`UpdateTagDefault`

TAG\_DEFAULT\_MANAGE

`DeleteTagDefault`

TAG\_DEFAULT\_MANAGE