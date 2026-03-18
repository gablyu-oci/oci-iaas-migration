---
title: "Common Policies"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm"
fetched: "20260306T012111Z"
---

**Type of access:** Ability to do all things with instance configurations, instance pools, and cluster networks in all compartments.

**Where to create the policy:** In the tenancy, so that the access is easily granted to all compartments by way of policy inheritance. To reduce the scope of access to just the instance configurations, instance pools, and cluster networks in a particular compartment, specify that compartment instead of the tenancy.

    Allow group InstancePoolAdmins to manage compute-management-family in tenancy

If a group needs to create instance configurations using existing instances as a template, and uses the API, SDKs, or command line interface (CLI) to do this, add the following statements to the policy:

    Allow group InstancePoolAdmins to read instance-family in tenancy
    Allow group InstancePoolAdmins to inspect volumes in tenancy

If a particular group needs to start, stop, or reset the instances in existing instance pools, but not create or delete instance pools, use this statement:

    Allow group InstancePoolUsers to use instance-pools in tenancy

If resources used by the instance pool contain default tags, add the following statement to the policy to give the group permission to the tag namespace `Oracle-Tags`:

    Allow group InstancePoolUsers to use tag-namespaces in tenancy where target.tag-namespace.name = 'oracle-tags'

If the instance configuration used by the instance pool launches instances in a capacity reservation, add the following statement to the policy:

    Allow service compute_management to use compute-capacity-reservations in tenancy

If the boot volume used in the instance configuration to create an instance pool is encrypted with a KMS key then, add the following statement to the policy

    allow service compute, blockstorage, compute_management to use key-family in compartment <compartment_id/<tenant_id>>