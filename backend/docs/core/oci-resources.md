---
title: "Resources"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/policyreference_topic-ResourceTypes.htm"
fetched: "20260306T012134Z"
---

Resource types are defined by Oracle. The resource type specifies the type or resource to which the policy applies.

**Syntax:**

    <resource> | all-resources

More options exist to make policies more granular, such as the ability to specify conditions under which the access is granted.

Other ways to make policies more granular are available, such as the ability to specify conditions under which the access is granted. For more information, see Conditions.

For more information about service resource types, see Detailed Service Policy Reference, or the service you're using.

## Individual Resource Types

An individual resource type includes a specific type of resource. If you have several `vcns`, then all users in the subject can perform the verb. For example, the `vcns` resource type is specifically for virtual cloud networks (VCNs). Other individual resource types include `subnets`, `instances`, and `volumes`. See the service details for more information about supported resource types.

**Example**

:

    Allow group HelpDesk to manage vcns in tenancy

Other options exist for making policies more granular, such as the ability to specify conditions under which the access is granted.

## Family Resource Types

To make policy writing easier, family resource types include several individual resource types that are often managed together. For example, the virtual-network-family type brings together various resource types related to the management of VCNs (for example, vcns, subnets, route-tables, security-lists, and more). If you need to write a more granular policy that gives access to only an individual resource type, you can. But you can also easily write a policy to give access to a broader range of resources.

In another example, Block Volume has volumes, volume-attachments, and volume-backups. If you need to give access to only making backups of volumes, you can specify the volume-backups resource type in your policy. But if you need to give broad access to all resources, you can specify the family type called `volume-family`.

**Example**

:

    Allow group A-Users to manage volume-family in compartment Project-A

**Important**

When a service introduces new individual resource types, they are typically included in the family type for that service. For example, if Networking introduces a new individual resource type, it's automatically included in the definition of the virtual-network-family resource type. For more information about changes to the definitions of resource types during service updates, see Policies and Service Updates.

## Access That Requires Several Resource Types

**Example**:

Some API operations require access to several resource types. For example, the `LaunchInstance` operation requires the ability to create compute instances and work with a cloud network. The `CreateVolumeBackup` operation requires access to both the volume and the volume backup. You need separate policy statements to give access to each resource type.

    Allow group A-Users to manage volumes in compartment Project-A

    Allow group B-Users to manage volume-backups in compartment Project-A

These individual statements don't have to be in the same policy, and a user can gain the required access from being in different groups.

For example, George might be in a group that gives the required level of access to the volumes resource type, and in another group that gives the required level of access to the `volume-backups` resource type. The sum of the individual statements, gives George access to `CreateVolumeBackup`.

## All Resources

To specify all of the resources in a compartment or tenancy, use `all-resources`. For example:

    Allow group A-Admins to manage all-resources in compartment Project-A