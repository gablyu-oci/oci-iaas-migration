# OCI IAM Documentation Reference Index

This directory contains comprehensive Oracle Cloud Infrastructure (OCI) Identity and Access Management (IAM) documentation, crawled and organized for the AWS → OCI migration project.

## Directory Structure

```
oci-reference/
├── policies/          # Policy syntax, structure, and advanced features
├── permissions/       # Permission verbs, resource types, and API mappings
├── authentication/    # Users, groups, dynamic groups, and credentials
├── compartments/      # Compartment hierarchy and management
├── conditions/        # Policy conditions, variables, tags, and network sources
└── examples/          # Common policies and real-world examples
```

---

## 📋 Policies

Core policy language, syntax, and configuration:

- **iam-policies-overview.md** - Overview of IAM policies and how they work
- **iam-without-identity-domains.md** - IAM introduction (non-identity domain mode)
- **policy-syntax.md** - Complete policy syntax reference
- **getting-started-with-policies.md** - Getting started guide for writing policies
- **how-policies-work.md** - Deep dive into policy evaluation and mechanics
- **advanced-policy-features.md** - Advanced features (conditions, variables, scoping)
- **deny-policies.md** - Deny policy syntax and use cases
- **cross-tenancy-access-policies.md** - Cross-tenancy policies using endorse/admit
- **writing-policies-for-dynamic-groups.md** - Policies for instance/resource principals

**Key topics:** Policy statement structure, verb+resource-type combinations, location (tenancy vs. compartment), OCID vs. name references

---

## 🔑 Permissions

Permission verbs, resource types, and API operation mappings:

- **verbs.md** - Explanation of the four permission verbs (inspect, read, use, manage)
- **resources.md** - Complete list of resource types and families
- **policy-reference.md** - General policy reference and variables
- **details-for-iam-without-identity-domains.md** - IAM-specific permissions and API operations
- **details-for-the-core-services.md** - Core Services (Compute, Networking, Block Storage) permissions
- **details-for-object-storage-and-archive-storage.md** - Object Storage permissions and API mappings

**Key topics:** Permission verb hierarchy (inspect < read < use < manage), cumulative permissions, resource-type families (instance-family, object-family, virtual-network-family), API operation → permission mappings

---

## 👤 Authentication

Users, groups, credentials, and identity principals:

- **managing-groups.md** - Creating and managing IAM groups
- **managing-dynamic-groups.md** - Dynamic groups for compute instances
- **calling-services-from-an-instance.md** - Instance principals and service-to-service auth
- **managing-user-credentials.md** - API keys, auth tokens, passwords
- **required-keys-and-ocids.md** - API signing keys and OCIDs

**Key topics:** User groups vs. dynamic groups, instance principals, resource principals, API key authentication, OCID structure

---

## 📦 Compartments

Compartment hierarchy and organization:

- **managing-compartments.md** - Creating, organizing, and managing compartments

**Key topics:** Compartment hierarchy, resource organization, policy attachment, moving resources between compartments

---

## ⚙️ Conditions

Policy conditions, variables, and advanced filtering:

- **conditions.md** - Complete guide to policy conditions
- **general-variables-for-all-requests.md** - General variables (request.user, request.principal, etc.)
- **using-tags-to-manage-access.md** - Tag-based access control
- **managing-network-sources.md** - Network source restrictions

**Key topics:** Condition syntax (where, all{}, any{}), tag variables (target.resource.tag, request.principal.tag), network sources, request context variables (request.region, request.ad)

---

## 📚 Examples

Common policies and real-world patterns:

- **common-policies.md** - Extensive collection of common policy examples for various services

**Key topics:** Admin policies, network admin policies, storage admin policies, service-specific examples

---

## 🔍 Quick Reference

### Permission Verb Hierarchy

```
inspect < read < use < manage
```

Each level is cumulative (e.g., `manage` includes all `use`, `read`, and `inspect` permissions).

### Basic Policy Syntax

```
Allow <subject> to <verb> <resource-type> in <location> [where <conditions>]
```

**Example:**
```
Allow group NetworkAdmins to manage virtual-network-family in compartment Production
```

### Common Resource Type Families

- `all-resources` - All OCI resources
- `instance-family` - Compute instances and related resources
- `volume-family` - Block volumes and backups
- `virtual-network-family` - VCNs, subnets, route tables, security lists
- `object-family` - Object Storage buckets and objects
- `database-family` - Database resources

### Key Differences from AWS IAM

1. **Policy Language:**
   - OCI: Human-readable statements (`Allow group X to manage Y in compartment Z`)
   - AWS: JSON-based with Effect, Action, Resource, Condition blocks

2. **Permission Model:**
   - OCI: 4-level verb hierarchy (inspect/read/use/manage)
   - AWS: Granular action-based (e.g., `s3:GetObject`, `s3:PutObject`)

3. **Resource Organization:**
   - OCI: Compartment hierarchy
   - AWS: Account + region + resource ARN

4. **Policy Attachment:**
   - OCI: Policies attached to compartments, apply to groups
   - AWS: Policies attached to users/groups/roles or resources

5. **Conditions:**
   - OCI: `where` clause with variables (e.g., `request.user.id`, `target.resource.tag`)
   - AWS: Condition block with keys and operators

---

## 📊 Coverage Summary

Total documents: 26

**By category:**
- Policies: 9 documents
- Permissions: 6 documents
- Authentication: 5 documents
- Compartments: 1 document
- Conditions: 4 documents
- Examples: 1 document

**Primary sources:**
- https://docs.oracle.com/en-us/iaas/Content/Identity/
- https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/
- https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/

---

## 🎯 Next Steps for Migration

1. **Map AWS IAM Policies → OCI:**
   - Identify AWS policy actions → Map to OCI permission verbs
   - Identify AWS resources → Map to OCI resource types
   - Identify AWS conditions → Map to OCI where clauses

2. **Understand Compartment Strategy:**
   - AWS Accounts/OUs → OCI Compartments
   - Plan compartment hierarchy for resource isolation

3. **Translate Identity Concepts:**
   - AWS Roles → OCI Dynamic Groups (for service principals)
   - AWS IAM Users/Groups → OCI IAM Users/Groups
   - AWS Cross-account access → OCI Cross-tenancy (endorse/admit)

4. **Reference This Index:**
   - Use this index to quickly find relevant OCI concepts
   - Cross-reference AWS IAM features with OCI equivalents

---

**Last Updated:** 2026-03-06  
**Crawl Session:** oci-iam-docs-crawler
