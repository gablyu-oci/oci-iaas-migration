---
title: "IAM Policies Overview"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm"
fetched: "20260306T012044Z"
---

(Optional) A compartment or tenancy to which the policy applies. For a compartment, the value includes an identifier (name or OCID).

Sometimes the policy needs to apply to the entire tenancy, and not a compartment inside the tenancy. The following is an example of a compartment-specific policy statement, in which the \<location\> is a specific compartment:

    Allow group <identifier> to <verb> <resource> in compartment <identifier>

Following is an example of a tenancy-wide policy statement, in which the \<location\> is tenancy:

    Allow group <identifier> to <verb> <resource> in tenancy