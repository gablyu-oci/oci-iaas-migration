3 tier app positioned as an **agent-assisted migration platform/program**, not just a translator.

## Overview
1. Planning/Assessment
	1. scan and identify
	2. workloads associated resources (cloud watch logs assessment)
	3. Mapping to OCI resources (90% migrated as is)
	4. test and validation report
2. Migrate
	1. migrate VMs using what? (disks, os image etc.)
	2. IAM agents
	3. Networking Migration Agents
	4. RF - Cloud Watch Agents
	5. Storage: object storage/s3 storage migration
	6. database migrations
3. Validate
	1. test & End to end validation using agents
	2. run validations

## Phase 1: Planning / assessment
Main functions
1. **Map AWS resources to OCI**
2. **Identify gaps / incompatibilities**
3. **Recommend substitutes and target architectures**
4. **Generate migration plan and artifacts**

Examples:
- discover EC2 and related resources
- read tags and group workloads
- map AWS constructs to OCI equivalents
- analyze dependencies
- use CloudWatch or other signals for sizing / optimization
- identify what can migrate directly vs what needs redesign

**Recommendation engine**
- recommend OCI target services
- flag unsupported or non-1:1 mappings
- suggest substitutions, such as **Aurora → PostgreSQL**
- produce a migration similarity / readiness score

**Planning output**
- diagrams, documents, migration plan, and sequencing
- clear explanation of what happens before / during / after migration

**Migration workflow**
- eventually support the actual move, not just analysis
- include validation after migration
- ideally fit into a broader assisted migration motion, where humans/partners can step in when needed