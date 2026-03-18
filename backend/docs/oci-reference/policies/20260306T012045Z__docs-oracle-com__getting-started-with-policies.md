---
title: "Getting Started with Policies"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policygetstarted.htm"
fetched: "20260306T012045Z"
---

Yes. However, a couple things to know first:

  - Enterprise companies typically have multiple users that need similar permissions, so policies are designed to give access to *groups* of users, not individual users. A user gains access by being in a group.
  - Policies are designed to *allow* access; there's no explicit "deny" when you write a policy.

If you need to grant access to a particular user, you can add a condition to the policy that specifies the user's OCID in a variable. This construction restricts the access granted in the policy to only the user specified in the condition. For example:

    allow any-group to read object-family in compartment ObjectStorage where request.user.id ='ocid1.user.oc1..<user_OCID>'

For information about using conditions and variables in policies, see Conditions.

If you need to restrict a particular user's access, you can:

  - Remove the user from the particular group of interest
  - Delete the user entirely from IAM (you have to remove the user from all groups first)