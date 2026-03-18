---
title: "Managing Dynamic Groups"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingdynamicgroups.htm"
fetched: "20260306T012202Z"
---

To include all instances in a specific compartment that are tagged with a specific tag namespace, key, and value, add a rule with the following syntax:

`All {instance.compartment.id = '<compartment_ocid>', tag.<tagnamespace>.<tagkey>.value='<tagvalue>'}`

All instances that are in the identified compartment and that are assigned the tagnamespace.tagkey with the specified tag value are included.

**Example:** Assume you have a tag namespace called `department` and a tag key called `operations`. You want to include all instances that are tagged with the value 45, that are in a particular compartment.

Enter the following statement in the text box:

    All {instance.compartment.id='ocid1:compartment:oc1:phx:oc1:phx:samplecompartmentocid6q6igvfauxmima74jv,',
    tag.department.operations.value='45'}