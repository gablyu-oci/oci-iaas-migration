---
title: "Cross-Tenancy Access Policies"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/iam-cross-domain.htm"
fetched: "20260306T012203Z"
---

Use cross-tenancy policy statements to create IAM policies that work across tenancies.

You can create cross-tenancy policy statements, in addition to the required user and service policy statements, to share resources with another organization that has its own tenancy. That organization might be another business unit in your company, a company customer, a company that provides services to you, and so on.

To access and share resources, the administrators of both tenancies need to create special policy statements that explicitly state the resources that can be accessed and shared. These special statements use the words *Define*, *Endorse*, and *Admit*.

## Endorse, Admit, and Define Statements

Use the following special start words in cross-tenancy statements:

  - **Endorse**: States the general set of abilities that a group *in your own tenancy* can perform in other tenancies. The *Endorse* statement always belongs in the tenancy that contains the group of users crossing the boundaries to work with another tenancy's resources. In the examples, this tenancy is called the *source tenancy*.

  - **Admit**: States the kind of ability *in your own tenancy* that you want to grant a group from the other tenancy. The *Admit* statement belongs in the tenancy that is granting "admittance" to the tenancy. The *Admit* statement identifies the group of users that requires resource access from the source tenancy and is identified with a corresponding *Endorse* statement. In the examples, this tenancy is called the *destination tenancy*.

  - **Define**: Assigns an alias to a tenancy OCID for *Endorse* and *Admit* policy statements. The *Define* statement is also required in the destination tenancy to assign an alias to the source IAM group OCID for *Admit* statements.
    
    Include a *Define* statement in the same policy statement as the *Endorse* or *Admit* policy statement.

The *Endorse* and *Admit* statements work together. An *Endorse* statement resides in the source tenancy and an *Admit* statement resides in the destination tenancy. Without a corresponding statement that specifies access, a particular *Endorse* or *Admit* statement grants no access. *Both tenancies must agree on access.*

**Important**  
  
In addition to policy statements, target and source tenancies must subscribe to the same regions to share resources.

## Cross-Tenancy Examples

  - The following policy lets the group `StorageAdmins` manage resources in the destination tenancy Object Storage resources:
    
        Endorse group StorageAdmins to manage object-family in any-tenancy 
    
    The following policy statements endorse the IAM group `StorageAdmins` in the source tenancy to do anything with all Object Storage resources in your destination tenancy:
    
    
    
        Define tenancy SourceTenancy as ocid1.tenancy.oc1.exampleuniqueID
        Define group StorageAdmins as ocid1.group.oc1.exampleuniqueID
        Admit group StorageAdmins of tenancy SourceTenancy to manage object-family in tenancy 
    
    

  - To write a policy that reduces the scope of tenancy access, the source administrator must reference the destination tenancy OCID provided by the destination administrator. The following policy statements endorse the IAM group `StorageAdmins` group to manage Object Storage resources in `DestinationTenancy` only:
    
    
    
        Define tenancy DestinationTenancy as ocid1.tenancy.oc1..<unique_ID>
        Endorse group StorageAdmins to manage object-family in tenancy DestinationTenancy
    
    
    
    These example policy statements endorse the IAM group `StorageAdmins` in the source tenancy to manage Object Storage resources only the `SharedBuckets` compartment:
    
    
    
        Define tenancy SourceTenancy as ocid1.tenancy.oc1..exampleuniqueID
        Define group StorageAdmins as ocid1.group.oc1..exampleuniqueID
        Admit group StorageAdmins of tenancy SourceTenancy to manage object-family in compartment SharedBuckets