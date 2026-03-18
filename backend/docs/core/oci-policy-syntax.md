---
title: "Policy Syntax"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm"
fetched: "20260306T012045Z"
---

Specify a single compartment or compartment path by name or OCID. Or simply specify `tenancy` to cover the entire tenancy. Remember that users, groups, and compartments reside in the tenancy. Policies can reside in (i.e., be attached to) either the tenancy or a child compartment.

**Note**

Granting Access to Specific Regions or availability domains

To create a policy that gives access to a specific region or availability domain, use the `request.region` or `request.ad` variable with a condition. See Conditions.

The location is required in the statement. If you want to attach a policy to a compartment, you must be in that compartment when you create the policy. For more information, see Policy Attachment.

To specify a compartment that is not a direct child of the compartment you are attaching the policy to, specify the path to the compartment, using the colon (:) as a separator. For more information, see Policies and Compartment Hierarchies.

**Syntax:** `[ tenancy | compartment <compartment_name> | compartment id <compartment_ocid>` \]

**Examples:**

  - To specify a compartment by name:
    
        Allow group A-Admins to manage all-resources in compartment Project-A

  - To specify a compartment by OCID:
    
        Allow group
         id ocid1.group.oc1..aaaaaaaaexampleocid to manage all-resources in compartment id ocid1.compartment.oc1..aaaaaaaaexampleocid

  - To specify multiple compartments, use separate statements:
    
        Allow group InstanceAdmins to manage instance-family in compartment Project-A
        
        Allow group InstanceAdmins to manage instance-family in compartment Project-B

  - To specify multiple compartments by OCID, use separate statements:
    
        Allow group id ocd1.group.oc1..aaaaaaaavheexampleocid to manage all-resources in compartment id ocid1.compartment.oc1..aaaaaaaayzexampleocid
        
        Allow group id ocd1.group.oc1..aaaaaaaaexampleocid to manage all-resources in compartment id ocid1.compartment.oc1..aaaaaexampledocid

  - To specify a compartment that is not a direct child of the compartment where you are attaching the policy, specify the path:
    
        Allow group InstanceAdmins to manage instance-family in compartment Project-A:Project-A2