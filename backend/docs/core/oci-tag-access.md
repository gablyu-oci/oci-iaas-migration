---
title: "Using Tags to Manage Access"
source: "https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingaccesswithtags.htm"
fetched: "20260306T012112Z"
---

| Service  | Resource Type | Permissions Not Supported with the target.resource.tag Policy Variable |
| -------- | ------------- | ---------------------------------------------------------------------- |
| Database | `all`         | DATABASE\_DELETE                                                       |

**Update Tags for ExaData Infrastructure:**

Not supported at this time using tag-based access control policies.

Scenarios requiring additional policy:

**Delete a DB-System:**

To delete or update a DB-System, in addition to the expected tag-based access control policy for `db-systems`, shown here:

    allow group TestGroup to manage db-systems in compartment Compartment1 where target.resource.tag.TagNS.TagKey= 'test'

You'll need policy allowing you permissions for `db-backups, db-homes, vnics`, `subnets` and `databases`. Here is an example policy showing the additional permissions:

    allow group TestGroup to manage db-backups in compartment Compartment1 where ANY {request.permission='DB_BACKUP_DELETE', request.permission='DB_BACKUP_INSPECT'}
    allow group TestGroup to manage db-homes in compartment Compartment1 where request.permission='DB_HOME_DELETE'
    allow group TestGroup to manage vnics in compartment Compartment1 where ANY {request.permission='VNIC_DELETE', request.permission='VNIC_DETACH'}
    allow group TestGroup to manage subnets in compartment Compartment1 where request.permission='SUBNET_DETACH'
    allow group TestGroup to manage databases in compartment compartment1

**Move a DB-system to another compartment:**

To move a DB-System to another compartment, in addition to the expected tag-based access control policy for `db-systems` shown here:

    allow group TestGroup to manage db-systems in compartment Compartment1 where target.resource.tag.TagNS.TagKey= 'test'

You'll need policy allowing you permissions for `databases`, `db-homes`, and `db-backups`. Here is an example policy with the additional permissions:

    allow group TestGroup to use databases in compartment Compartment1 where request.permission='DATABASE_UPDATE'
    allow group TestGroup to manage db-backups in compartment Compartment1 where request.permission='DB_BACKUP_INSPECT'
    allow group TestGroup to manage db-homes in compartment Compartment1 where request.permission='DB_HOME_UPDATE'

**Database delete for Exadata DB-System:**

To delete a database resource for an Exadata DB-System, you'll need the expected tag-based access control policy for `db-systems` and `databases` shown here:

    allow group TestGroup to manage db-systems in compartment Compartment1 where target.resource.tag.TagNS.TagKey= 'test'
    allow group TestGroup to manage databases in compartment Compartment1 where target.resource.tag.TagNS.TagKey= 'test'

You'll also need permissions for `db-homes` and `db-backups`. Here is an example policy with the additional permissions:

    allow group TestGroup to manage db-homes in compartment Compartment1 where request.permision='DB_HOME_UPDATE'
    allow group TestGroup to manage db-backups in compartment Compartment1 where ANY {request.permission='DB_BACKUP_DELETE', request.permission='DB_BACKUP_INSPECT'}

**Delete Database:**

Deleting a database for a baremetal or virtual machine DB system is not supported using tag-based policies on the target resource.

**Database backup create:**

To create a database backup, you'll need the expected tag-based access control policy for `databases`:

    allow group TestGroup to manage databases in compartment Compartment1 where target.resource.tag.TagNS.TagKey= 'test'

You'll also need permissions for `db-backups`. Here is an example policy with the additional permissions:

    allow group TestGroup to manage db-backups in compartment Compartment1 where request.permission='DB_BACKUP_CREATE'

**Database restore:**

To restore a database backup, you'll need the expected tag-based access control policy for `databases`:

    allow group TestGroup to manage databases in compartment Compartment1 where target.resource.tag.TagNS.TagKey= 'test'

You'll also need permissions for `backups`, like the one shown here:

    allow group TestGroup to manage db-backups in compartment Compartment1 where ANY {request.permission='DB_BACKUP_INSPECT', request.permission='DB_BACKUP_CONTENT_READ'}

**Create Data Guard association:**

Creating a Data Guard association is not supported using tag-based policies on the target resource.