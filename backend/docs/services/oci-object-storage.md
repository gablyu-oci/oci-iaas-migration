---
title: "Details for Object Storage and Archive Storage"
source: "https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm"
fetched: "20260306T012148Z"
---

`GetNamespace`

API requires no permissions and returns the caller's namespace. Use the API to validate your credentials.

OBJECTSTORAGE\_NAMESPACE\_READ permission is required if you include the optional `compartmentId` parameter. Use the `compartmentId` parameter to find the namespace for a third-party tenancy.

`GetNamespaceMetadata`

OBJECTSTORAGE\_NAMESPACE\_READ

`UpdateNamespaceMetadata`

OBJECTSTORAGE\_NAMESPACE\_UPDATE

`CreateBucket`

BUCKET\_CREATE

If the KMS Key ID is provided to the operation, the following additional permissions are required:

  - KEY\_ASSOCIATE
  - The objectstorage-\<location\> subject must also have: KEY\_ENCRYPT, KEY\_DECRYPT, KEY\_READ.

`UpdateBucket`

BUCKET\_UPDATE

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must also have: KEY\_ENCRYPT, and KEY\_DECRYPT.

`GetBucket`

BUCKET\_READ

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must have KEY\_DECRYPT.

`HeadBucket`

BUCKET\_INSPECT

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must have KEY\_DECRYPT.

`ListBuckets`

BUCKET\_INSPECT

`DeleteBucket`

BUCKET\_DELETE

`ReencryptBucket`

BUCKET\_UPDATE

The objectstorage-\<location\> subject must also have: KEY\_ENCRYPT, and KEY\_DECRYPT.

`PutObject`

The permission required depends on whether the object already exists in the bucket:

  - OBJECT\_CREATE is required when an object with that name doesn't already exist in the bucket.
  - OBJECT\_OVERWRITE is required when an object with that name already exists in the bucket.

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must have KEY\_ENCRYPT.

`RenameObject`

OBJECT\_CREATE and OBJECT\_OVERWRITE

`GetObject`

OBJECT\_READ

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must have KEY\_DECRYPT.

`HeadObject`

OBJECT\_READ or OBJECT\_INSPECT

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must have KEY\_DECRYPT.

`DeleteObject`

OBJECT\_DELETE

`DeleteObjectVersion`

OBJECT\_VERSION\_DELETE

`ListObjects`

OBJECT\_INSPECT

`ListObjectVersions`

OBJECT\_INSPECT

`ReencryptObject`

OBJECT\_READ, OBJECT\_OVERWRITE

For a customer-managed key encrypted bucket, the following permissions are required:

  - KEY\_ASSOCIATE
  - Additionally, the objectstorage-\<location\> subject must also have KEY\_ENCRYPT, KEY\_DECRYPT, and KEY\_READ.

`RestoreObjects`

OBJECT\_RESTORE

`UpdateObjectStorageTier`

OBJECT\_UPDATE\_TIER

`CreateMultipartUpload`

OBJECT\_CREATE and OBJECT\_OVERWRITE

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must have KEY\_ENCRYPT.

`UploadPart`

OBJECT\_CREATE and OBJECT\_OVERWRITE

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must have KEY\_ENCRYPT.

`CommitMultipartUpload`

BUCKET\_READ, OBJECT\_CREATE, OBJECT\_READ, and OBJECT\_OVERWRITE

`ListMultipartUploadParts`

OBJECT\_INSPECT

`ListMultipartUploads`

BUCKET\_READ

`AbortMultipartUpload`

OBJECT\_DELETE

`CreatePreauthenticatedRequest`

PAR\_MANAGE

`GetPreauthenticatedRequest`

PAR\_MANAGE or BUCKET\_READ

`ListPreauthenticatedRequests`

PAR\_MANAGE or BUCKET\_READ

`DeletePreauthenticatedRequest`

PAR\_MANAGE

`PutObjectLifecyclePolicy`

BUCKET\_UPDATE, OBJECT\_CREATE, and OBJECT\_DELETE

Additionally, the objectstorage-\<location\> subject must also have: BUCKET\_INSPECT, BUCKET\_READ, OBJECT\_INSPECT.

If the bucket the lifecycle policy applies to is a customer-managed key encrypted bucket then the objectstorage-\<location\> subject must also have: KEY\_ENCRYPT, and KEY\_DECRYPT.

If the `PutObjectLifeCyclePolicy` operation also updates the object tier for example, from default to INFREQUENT\_ACCESS, the user and the objectstorage-\<location\> subject must be granted OBJECT\_UPDATE\_TIER permission.

`GetObjectLifecyclePolicy`

BUCKET\_READ

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must have KEY\_DECRYPT.

`DeleteObjectLifecyclePolicy`

BUCKET\_UPDATE

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must also have: KEY\_ENCRYPT, and KEY\_DECRYPT.

`CreateRetentionRule`

BUCKET\_UPDATE and RETENTION\_RULE\_MANAGE (and RETENTION\_RULE\_LOCK)

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must also have: KEY\_ENCRYPT, and KEY\_DECRYPT.

`GetRetentionRule`

BUCKET\_READ

`ListRetentionRule`

BUCKET\_READ

`UpdateRetentionRule`

BUCKET\_UPDATE and RETENTION\_RULE\_MANAGE (and RETENTION\_RULE\_LOCK)

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must also have: KEY\_ENCRYPT, and KEY\_DECRYPT.

`DeleteRetentionRule`

BUCKET\_UPDATE and RETENTION\_RULE\_MANAGE

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must also have: KEY\_ENCRYPT, and KEY\_DECRYPT.

`CopyObjectRequest`

OBJECT\_READ, and the second user permission required depends on whether the object already exists in the bucket:

  - OBJECT\_CREATE is required when an object with that name doesn't already exist in the bucket.
  - OBJECT\_OVERWRITE is required when an object with that name already exists in the bucket.

Additionally, the objectstorage-\<location\> subject requires OBJECT\_READ.

For a customer-managed key encrypted bucket, the objectstorage-\<location\> subject must also have KEY\_ENCRYPT, KEY\_DECRYPT.

`GetWorkRequest`

OBJECT\_READ

`ListWorkRequests`

OBJECT\_INSPECT

`CancelWorkRequest`

OBJECT\_DELETE

`CreateReplicationPolicy`

OBJECT\_READ, OBJECT\_CREATE, OBJECT\_OVERWRITE, OBJECT\_INSPECT, OBJECT\_DELETE, OBJECT\_RESTORE, BUCKET\_READ, and BUCKET\_UPDATE

The objectstorage-\<location\> subject must have the same permissions as the user.

`GetReplicationPolicy`

BUCKET\_READ

`DeleteReplicationPolicy`

OBJECT\_READ, OBJECT\_CREATE, OBJECT\_OVERWRITE, OBJECT\_INSPECT, OBJECT\_DELETE, OBJECT\_RESTORE, BUCKET\_READ, and BUCKET\_UPDATE

`ListReplicationPolicies`

BUCKET\_READ

`ListReplicationSources`

BUCKET\_READ

`MakeBucketWritable`

OBJECT\_READ, OBJECT\_CREATE, OBJECT\_OVERWRITE, OBJECT\_INSPECT, OBJECT\_DELETE, BUCKET\_READ, and BUCKET\_UPDATE