---
title: "Managing Compartments"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcompartments.htm"
fetched: "20260306T012112Z"
---

When you move a compartment, some polices will be automatically updated. Policies that specify the compartment hierarchy down to the compartment being moved will automatically be updated when the policy is attached to a shared ancestor of the current and target parent. Consider the following examples:

**Example 1: Policy automatically updated**

In this example, you move compartment A from Operations:Test to Operations:Dev. The policy that governs compartment A is attached to the shared parent, Operations. When the compartment is moved, the policy statement is automatically updated by the IAM service to specify the new compartment location.

The policy

    Allow group G1 to manage buckets in compartment Test:A 

is updated to

    Allow group G1 to manage buckets in compartment Dev:A

No manual intervention is required to allow group G1 to continue to access compartment A in its location.

**Example 2: Policy not updated**

In this example, you move compartment A from Operations:Test to Operations:Dev. However, the policy that governs compartment A here is attached directly to the Test compartment. When the compartment is moved, the policy is not automatically updated. The policy that specifies compartment A is no longer valid and must be manually removed. Group G1 no longer has access to compartment A in its new location under Dev. Unless another existing policy grants access to group G1, you must create a new policy to allow G1 to continue to manage buckets in compartment A.

**Example 3: Policy attached to the tenancy is updated**

In this example, you move compartment A from Operations:Test to HR:Prod. The policy that governs compartment A is attached to the tenancy, which is a shared ancestor by the original parent compartment and the new parent compartment. Therefore, when the compartment is moved, the policy statement is automatically updated by the IAM service to specify the new compartment location.

The policy statement:

    Allow group G1 to manage buckets in compartment Operations:Test:A 

is updated to

    Allow group G1 to manage buckets in compartment HR:Prod:A

No manual intervention is required to allow group G1 to continue to access compartment A.