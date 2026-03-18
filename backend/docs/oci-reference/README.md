# OCI IAM Reference Documentation

This directory contains crawled Oracle Cloud Infrastructure (OCI) IAM documentation, organized for the AWS → OCI migration project.

## 📂 Quick Start

1. **Start here:** [`index.md`](./index.md) - Complete documentation index with AWS comparison
2. **Crawl details:** [`crawl-report.md`](./crawl-report.md) - What was crawled and why
3. **Browse by topic:** Navigate to the subdirectories below

## 📁 Directory Structure

```
oci-reference/
├── README.md                # This file
├── index.md                 # Complete index with quick reference
├── crawl-report.md          # Crawl session report and coverage analysis
├── policies/                # 9 docs - Policy syntax and features
├── permissions/             # 6 docs - Verbs, resource types, API mappings
├── authentication/          # 5 docs - Users, groups, credentials
├── compartments/            # 1 doc  - Compartment management
├── conditions/              # 4 docs - Variables, tags, network sources
└── examples/                # 1 doc  - Common policy examples
```

## 🎯 Quick Reference

### OCI Policy Syntax
```
Allow <subject> to <verb> <resource-type> in <location> [where <conditions>]
```

### Permission Verbs (Cumulative)
- `inspect` - List and view metadata
- `read` - Inspect + view content
- `use` - Read + use/attach resources
- `manage` - Use + create/update/delete

### Common Resource Families
- `all-resources` - Everything
- `instance-family` - Compute instances
- `virtual-network-family` - VCNs, subnets
- `object-family` - Object Storage
- `volume-family` - Block volumes

## 🔍 Find What You Need

| Looking for... | Check... |
|---------------|----------|
| Policy syntax | `policies/policy-syntax.md` |
| Permission verbs | `permissions/verbs.md` |
| Resource types | `permissions/resources.md` |
| Conditions/variables | `conditions/conditions.md` |
| Common examples | `examples/common-policies.md` |
| Dynamic groups | `authentication/managing-dynamic-groups.md` |
| Cross-tenancy | `policies/cross-tenancy-access-policies.md` |

## 📊 Stats

- **Total documents:** 26 reference docs + 2 index files
- **Coverage:** Core IAM concepts, policy language, permissions, authentication
- **Primary source:** docs.oracle.com/en-us/iaas/Content/Identity/
- **Crawled:** 2026-03-06

## 🚀 Using This Documentation

1. **Learn OCI IAM concepts:** Start with `policies/iam-policies-overview.md`
2. **Understand policy syntax:** Read `policies/policy-syntax.md`
3. **Map AWS to OCI:** Use `index.md` for side-by-side comparison
4. **Look up specific topics:** Use category directories or `index.md` search

## 💡 Tips

- Use `index.md` for quick lookups and AWS comparisons
- Most docs include examples - look for code blocks
- Resource type families map to AWS service categories (e.g., `instance-family` ≈ EC2)
- OCI verbs are broader than AWS actions - one verb = many AWS actions

---

**For questions or to request additional documentation, see the parent project README.**
