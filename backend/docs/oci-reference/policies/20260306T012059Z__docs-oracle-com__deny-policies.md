---
title: "Deny Policies"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/denypolicies.htm"
fetched: "20260306T012059Z"
---

IAM deny policies limit access by removing specific permissions, ensuring only intended actions are allowed. Deny policies override allow policies to restrict access. In contrast, IAM allow policies grant permissions to access resources.

**Note**  
  
The level of access is cumulative (from the least level of access to the highest level of access). The hierarchy is `inspect` (the lowest level of access) to `read` to `use` to `manage` (the highest level of access).

For example, when allowing permissions, granting access to `manage` permissions typically means a user is also granted permissions such as `read` or `inspect`. The `manage` verb always expands scope to include the `use`, `read`, and `inspect` permissions on a resource.

However, when denying permissions, the opposite is true. When a policy is written denying access to `manage` permissions, it doesn't necessarily block permissions for `inspect`, `read`, or `use`.

For example, if you write a deny policy to block an `inspect` permission, typically you would also want to restrict the `read`, `use`, or `manage` permissions. In other words, denying the ability to `inspect` a resource would also deny the ability to `read`, `use`, or `manage` it.

For allow policies, include all metaverbs with equal or lower permissions than the specified one.

For deny policies, include all metaverbs with higher permissions than the specified one. For example, the following policy would block SampleGroup from deleting any buckets, but wouldn't block `read` access. This assumes another policy granted that access, as AuthZ is still deny by default.

    deny group SampleGroup to manage buckets in tenancy

Whereas the following policy would block SampleGroup from doing anything to those buckets. Deny access means denying all the lower level permissions as well.

    deny group SampleGroup to inspect buckets in tenancy

Specific permission strings can still be denied as they are today with allow policies, if there's a need to do so.

    deny group SampleGroup to { BUCKET_INSPECT } in tenancy