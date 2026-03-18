# MVP Features
## Frontend
1. Setting page: user paste AWS credntial and validate connection
2. Dashboard showing discovered resources and migration status
3. Skill runner page:
    1. Select skill
    2. Pick target resource: extracted from AWS and manually upload
    3. trigger
    4. track progress
        1. How long it's been running
        2. Which round the writer/reviewer loop is on
        3. Whether it's currently in the writer phase/reviewer phase            
4. review results and export/download package
    1. Cloudformation translation: Generate a zip file of terraforms, view md file for explanation/instruction
        1. Make sure it can be `terraform init`
    2. IAM policy translation: generate json file and view md file for explanation/instruction
    3. Dependency discovery: view graph, view the md files

## Backend API
1. Endpoints:
    1. AWS credential validation and store
    2. List extracted resources with filtering by type: User view what was pulled, browse, select what to migrate
    3. Trigger each skill individually
    4. Check job/agent status and progress via skill_run_id or sth
    5. Fetch results        
2. Validate user input format (simple, just validate if it's parseable yaml/json)  
3. Implementation: FastAPI   

## AWS SDK Integration
1. Resource extraction
    1. User connect their account
    2. Pull CloudFormation
    3. Pull IAM policies
	4. cloudtrail.json and flowlog.log
		1. CloudTrailUse the AWS SDK to call `CloudTrail.lookup_events` with filters for a specific time window
		2. Flowlogs: Query them through CloudWatch Logs Insights or Athena if the customer has them set up.
		3. Preprocess between aws sdk extraction and storage, python function that groups, deduplicates and extract relationships with pandas, derive dependency graph, then store
2. Store in PostgreSQL
3. IAM credential pairs/assume-role ARN, not yet full oauth ?

## 3 Independent skills/endpoints

## Model Gateway
1. Route each skill, and reviewer to model
2. Secret scrubbing function as input guardrail
## Rag with pgvector
1. Pre-load AWS to OCI service mappings, TF provider docs, IAM equivalence tables
2. Doc layer: Semantic search for documentation and guidance, how OCI and AWS differs (security groups, terraform syntax patterns)

## Postgres DB
1. tenants
2. AWS connections (tenant id, aws credentials, region, status)
3. `resources` table (id, migration_id, aws_type, aws_arn, raw_config, status, created_at
4. Migrations (id, tenant id, aws connection id, name, status
5. Skill runs (id, migration id, skill type, input, config, output, status, errors, created at)
6. `artifacts` table (id, skill_run_id, file_type, file_name, content, created_at)
7. Lookup layer: Keyword search for structured reference data, want exact match on resource type string, IAM action mappings
    1. `service_mappings` (aws_service, aws_resource_type, oci_service, oci_resource_type, terraform_resource, notes)
    2. `iam_mappings` (aws_action, aws_service, oci_permission, oci_service, notes)

## Auth

1. Login with email and password, isolated tenant