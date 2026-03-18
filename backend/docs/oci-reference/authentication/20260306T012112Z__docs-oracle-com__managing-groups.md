---
title: "Managing Groups"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managinggroups.htm"
fetched: "20260306T012112Z"
---

When creating a group, you must provide a unique, unchangeable *name* for the group. The name must be unique across all groups within your tenancy. You must also provide the group with a *description* (although it can be an empty string), which is a non-unique, changeable description for the group. Oracle will also assign the group a unique ID called an Oracle Cloud ID (OCID). For more information, see Resource Identifiers.

**Note**

If you delete a group and then create a new group with the same name, they'll be considered different groups because they'll have different OCIDs.

A group has no permissions until you write at least one **policyÂ ** that gives that group permission to either the tenancy or a compartment. When writing the policy, you can specify the group by using either the unique name or the group's OCID. Per the preceding note, even if you specify the group name in the policy, IAM internally uses the OCID to determine the group. For information about writing policies, see Managing Policies.

You can delete a group, but only if the group is empty.

For information about the number of groups you can have, see Limits by Service.

If you're federating with an identity provider, you'll create mappings between the identity provider's groups and your IAM groups. For more information, see Federating with Identity Providers.