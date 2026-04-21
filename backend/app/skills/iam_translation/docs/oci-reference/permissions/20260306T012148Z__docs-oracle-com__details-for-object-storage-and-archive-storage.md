# Details for Object Storage and Archive Storage

Source: https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/objectstoragepolicyreference.htm
Captured: 2026-03-06

This topic covers details for writing policies to control access to Archive Storage and Object Storage.

> **Tip:** The object lifecycle policies feature requires that you grant permissions to the Object Storage service to archive and delete objects on your behalf. See "Using Object Lifecycle Policies" for more information.

## Resource-Types

### Individual Resource-Types

- `objectstorage-namespaces`
- `buckets`
- `objects`

### Aggregate Resource-Type

`object-family`

A policy that uses `<verb> object-family` is equivalent to writing one with a separate `<verb> <individual resource-type>` statement for each of the individual resource-types.

See the Details for Verb + Resource-Type Combinations table below for the API operations covered by each verb for each individual resource-type included in `object-family`.

## Supported Variables

Object Storage supports all the general variables plus the ones listed here:

| Operations for This Resource-Type | Can Use This Variable | Variable Type | Comments |
|---|---|---|---|
| `buckets` and `objects` | `target.bucket.name` | String | Use to control access to a specific bucket. **Important:** Condition matching is case insensitive — buckets `BucketA` and `bucketA` both match `where target.bucket.name="BucketA"`. |
| `buckets` and `objects` | `target.bucket.tag.<TagNamespace>.<TagKeyDefinition>` | String | Use to control access to buckets with a specific tag. **Important:** Cannot be used for `CreateBucket` or operations involving multiple buckets (such as `ListBucket`). |

> **Note:** `request.ipv4.ipaddress` and `request.vcn.id` are deprecated. Instead, create a network source object and use `request.networkSource.name` in your policy.

## Details for Verb + Resource-Type Combinations

The level of access is cumulative: `inspect` → `read` → `use` → `manage`. A `+` indicates incremental access; "no extra" indicates no incremental access.

### objectstorage-namespaces

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| read | None | `GetNamespace` | none |
| manage | OBJECTSTORAGE_NAMESPACE_READ, OBJECTSTORAGE_NAMESPACE_UPDATE | `GetNamespace` with optional `compartmentId` parameter | `GetNamespaceMetadata`, `UpdateNamespaceMetadata` |

### buckets

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | BUCKET_INSPECT | `HeadBucket`, `ListBuckets` | none |
| read | INSPECT + BUCKET_READ | INSPECT + `GetBucket`, `ListMultipartUploads`, `GetObjectLifecyclePolicy`, `GetRetentionRule`, `ListRetentionRules`, `GetReplicationPolicy`, `ListReplicationPolicies`, `ListReplicationSources` | none |
| use | READ + BUCKET_UPDATE | READ + `UpdateBucket`, `DeleteObjectLifecyclePolicy`, `ReencryptBucket`, `PutObjectLifecyclePolicy` | none |
| manage | USE + BUCKET_CREATE, BUCKET_DELETE, PAR_MANAGE, RETENTION_RULE_MANAGE, RETENTION_RULE_LOCK (if using optional rule locking) | USE + `CreateBucket`, `DeleteBucket`, `CreatePreauthenticatedRequest`, `GetPreauthenticatedRequest`, `ListPreauthenticatedRequest`, `DeletePreauthenticatedRequest`, `CreateRetentionRule`, `UpdateRetentionRule`, `DeleteRetentionRule`, `CreateReplicationPolicy`, `DeleteReplicationPolicy`, `MakeBucketWritable` (these last three also need `manage objects`) | none |

### objects

| Verbs | Permissions | APIs Fully Covered | APIs Partially Covered |
|---|---|---|---|
| inspect | OBJECT_INSPECT | `HeadObject`, `ListObjects`, `ListMultipartUploadParts` | none |
| read | INSPECT + OBJECT_READ | INSPECT + `GetObject` | none |
| use | READ + OBJECT_OVERWRITE | READ + `ReencryptObject`, `PutObject` (USE allows overwriting existing objects; creating a new object also requires OBJECT_CREATE) | `CreateMultipartUpload`, `UploadPart`, `CommitMultipartUpload` (all also need `manage objects`) |
| manage | USE + OBJECT_CREATE, OBJECT_DELETE, OBJECT_VERSION_DELETE, OBJECT_RESTORE, OBJECT_UPDATE_TIER | USE + `CreateObject`, `RenameObject`, `RestoreObject`, `DeleteObject`, `DeleteObjectVersion`, `UpdateObjectStorageTier`, `CreateMultipartUpload`, `UploadPart`, `CommitMultipartUpload`, `AbortMultipartUpload`, `PutObjectLifecyclePolicy` (also needs `manage objects`), `CreateReplicationPolicy`, `DeleteReplicationPolicy`, `MakeBucketWritable` (these also need `manage buckets`) | none |

## Permissions Required for Each API Operation

| API Operation | Permissions Required |
|---|---|
| `GetNamespace` | None (returns the caller's namespace — use to validate credentials). OBJECTSTORAGE_NAMESPACE_READ required if including the optional `compartmentId` parameter. |
| `GetNamespaceMetadata` | OBJECTSTORAGE_NAMESPACE_READ |
| `UpdateNamespaceMetadata` | OBJECTSTORAGE_NAMESPACE_UPDATE |
| `CreateBucket` | BUCKET_CREATE |
| `UpdateBucket` | BUCKET_UPDATE |
| `GetBucket` | BUCKET_READ |
| `HeadBucket` | BUCKET_INSPECT |
| `ListBuckets` | BUCKET_INSPECT |
| `DeleteBucket` | BUCKET_DELETE |
| `ReencryptBucket` | BUCKET_UPDATE |
| `PutObject` | OBJECT_CREATE when the object does not already exist; OBJECT_OVERWRITE when an object with that name already exists in the bucket. |
| `RenameObject` | OBJECT_CREATE and OBJECT_OVERWRITE |
| `GetObject` | OBJECT_READ |
| `HeadObject` | OBJECT_READ or OBJECT_INSPECT |
| `DeleteObject` | OBJECT_DELETE |
| `DeleteObjectVersion` | OBJECT_VERSION_DELETE |
| `ListObjects` | OBJECT_INSPECT |
| `ReencryptObject` | OBJECT_READ & OBJECT_OVERWRITE |
| `RestoreObjects` | OBJECT_RESTORE |
| `UpdateObjectStorageTier` | OBJECT_UPDATE_TIER |
| `CreateMultipartUpload` | OBJECT_CREATE and OBJECT_OVERWRITE |
| `UploadPart` | OBJECT_CREATE and OBJECT_OVERWRITE |
| `CommitMultipartUpload` | OBJECT_CREATE and OBJECT_OVERWRITE |
| `ListMultipartUploadParts` | OBJECT_INSPECT |
| `ListMultipartUploads` | BUCKET_READ |
| `AbortMultipartUpload` | OBJECT_DELETE |
| `CreatePreauthenticatedRequest` | PAR_MANAGE |
| `GetPreauthenticatedRequest` | PAR_MANAGE or BUCKET_READ |
| `ListPreauthenticatedRequests` | PAR_MANAGE or BUCKET_READ |
| `DeletePreauthenticatedRequest` | PAR_MANAGE |
| `PutObjectLifecyclePolicy` | BUCKET_UPDATE, OBJECT_CREATE, and OBJECT_DELETE |
| `GetObjectLifecyclePolicy` | BUCKET_READ |
| `DeleteObjectLifecyclePolicy` | BUCKET_UPDATE |
| `CreateRetentionRule` | BUCKET_UPDATE & RETENTION_RULE_MANAGE (& RETENTION_RULE_LOCK) |
| `GetRetentionRule` | BUCKET_READ |
| `ListRetentionRule` | BUCKET_READ |
| `UpdateRetentionRule` | BUCKET_UPDATE & RETENTION_RULE_MANAGE (& RETENTION_RULE_LOCK) |
| `DeleteRetentionRule` | BUCKET_UPDATE & RETENTION_RULE_MANAGE |
| `CreateCopyRequest` | OBJECT_READ, OBJECT_CREATE, OBJECT_OVERWRITE, and OBJECT_INSPECT |
| `GetWorkRequest` | OBJECT_READ |
| `ListWorkRequests` | OBJECT_INSPECT |
| `CancelWorkRequest` | OBJECT_DELETE |
| `CreateReplicationPolicy` | OBJECT_READ, OBJECT_CREATE, OBJECT_OVERWRITE, OBJECT_INSPECT, OBJECT_DELETE, OBJECT_RESTORE, BUCKET_READ, and BUCKET_UPDATE |
| `GetReplicationPolicy` | BUCKET_READ |
| `DeleteReplicationPolicy` | OBJECT_READ, OBJECT_CREATE, OBJECT_OVERWRITE, OBJECT_INSPECT, OBJECT_DELETE, OBJECT_RESTORE, BUCKET_READ, and BUCKET_UPDATE |
| `ListReplicationPolicies` | BUCKET_READ |
| `ListReplicationSources` | BUCKET_READ |
| `MakeBucketWritable` | OBJECT_READ, OBJECT_CREATE, OBJECT_OVERWRITE, OBJECT_INSPECT, OBJECT_DELETE, BUCKET_READ, and BUCKET_UPDATE |
