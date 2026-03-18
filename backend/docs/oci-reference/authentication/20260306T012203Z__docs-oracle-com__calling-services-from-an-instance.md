---
title: "Calling Services from an Instance"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm"
fetched: "20260306T012203Z"
---

After you have created a dynamic group, you need to create policies to permit the dynamic groups to access Oracle Cloud Infrastructure services.

Policy for dynamic groups follows the syntax described in How Policies Work. Review that topic to understand basic policy features.

The syntax to permit a dynamic group access to resources in a compartment is:

    Allow dynamic-group <dynamic_group_name> to <verb> <resource-type> in compartment <compartment_name>

The syntax to permit a dynamic group access to a tenancy is:

    Allow dynamic-group <dynamic_group_name> to <verb> <resource-type> in tenancy

Here are a few example policies:

To allow a dynamic group (FrontEnd) to use a load balancer in a specific compartment (ProjectA):

    Allow dynamic-group FrontEnd to use load-balancers in compartment ProjectA

To allow a dynamic group to launch instances in a specific compartment:

    Allow dynamic-group FrontEnd to manage instance-family in compartment ProjectA
    Allow dynamic-group FrontEnd to use volume-family in compartment ProjectA
    Allow dynamic-group FrontEnd to use virtual-network-family in compartment ProjectA

For more sample policies, see Common Policies.