---
title: "Conditions"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/conditions.htm"
fetched: "20260306T012135Z"
---

If the variable is *not applicable* to the incoming request, the condition evaluates the request as `false` and the request is declined. For example, here are some basic policy statements that together let someone add or remove users from any group except `Administrators`:

    Allow group GroupAdmins to use users in tenancy where target.group.name != 'Administrators'
    
    Allow group GroupAdmins to use groups in tenancy where target.group.name != 'Administrators'

If a user in `GroupAdmins` tried to call a general API operation for users, such as `ListUsers` or `UpdateUser` (which lets you change the user's description), the request is declined, even though those API operations are covered by `use users`. The example policy statement for `use users` includes a `target.group.name` variable, but the `ListUsers` or `UpdateUser` request doesn't specify a group. The request is declined because a `target.group.name` wasn't provided.

To grant access to a general user when an API operation doesn't involve a particular group, you need to add another statement that gives the level of access that you want to grant but doesn't include the condition. For example, to grant access to `ListUsers`, you need a statement similar to this statement:

    Allow group GroupAdmins to inspect users in tenancy

To grant access to `UpdateUser`, you need this statement (which also covers `ListUsers` because the `use` verb includes the capabilities of the `inspect` verb):

    Allow group GroupAdmins to use users in tenancy

This general concept also applies any other resource type with target variables, for example, `ListGroups`.