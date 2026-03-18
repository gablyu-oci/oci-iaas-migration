# cf2tf Tool Installation and Usage Guide

## Overview

**cf2tf** is a Python-based tool that converts AWS CloudFormation templates to Terraform (AWS provider). It automates the initial conversion of CloudFormation syntax to Terraform HCL, handling ~75% of the structural conversion work.

**Repository:** https://github.com/DontShaveTheYak/cf2tf  
**Version tested:** 0.9.1  
**License:** MIT

## Installation

### Prerequisites
- Python 3.10 or later
- pip package manager
- Internet connection (for downloading Terraform source code during conversion)

### Install via pip

```bash
pip install cf2tf
```

**Installation output:**
```
Successfully installed cf2tf-0.9.1
Dependencies installed:
- click (8.3.1)
- cfn-flip (1.3.0) 
- PyYAML (6.0.3)
- GitPython (3.1.46)
- thefuzz (0.22.1)
- requests (2.32.5)
- pytest (8.4.2)
```

### Verify installation

```bash
cf2tf --version
```

## Basic Usage

### Command syntax

```bash
cf2tf [OPTIONS] TEMPLATE_PATH
```

### Options

- `--version` - Show version and exit
- `-o, --output PATH` - Output directory path (default: creates directory matching input filename)
- `-v, --verbosity LVL` - Logging level (CRITICAL, ERROR, WARNING, INFO, DEBUG)
- `--help` - Show help message

### Example: Convert a simple VPC template

```bash
cf2tf samples/01-vpc-multi-az-networking.yaml -o output/vpc-converted
```

**What happens:**
1. cf2tf clones Terraform source code to `/tmp/terraform_src/` (first run only)
2. Parses CloudFormation YAML/JSON
3. Converts resources, parameters, outputs to Terraform HCL
4. Generates multiple `.tf` files in output directory

### Output structure

cf2tf creates a directory with separate files:

```
output/vpc-converted/
├── resource.tf    # All resource definitions
├── variable.tf    # Input variables (from Parameters)
├── data.tf        # Data sources
├── output.tf      # Outputs
└── locals.tf      # Local values
```

## Conversion Quality Analysis

### What cf2tf does well ✅

1. **Basic resource conversion:** Maps CloudFormation resource types to Terraform resources
   - `AWS::EC2::VPC` → `aws_vpc`
   - `AWS::Lambda::Function` → `aws_lambda_function`
   - `AWS::S3::Bucket` → `aws_s3_bucket`

2. **Parameter handling:** Converts CloudFormation Parameters to Terraform variables
   ```yaml
   # CloudFormation
   Parameters:
     InstanceType:
       Type: String
       Default: t3.medium
   ```
   ```hcl
   # Terraform (generated)
   variable "instance_type" {
     type    = string
     default = "t3.medium"
   }
   ```

3. **Output conversion:** Maps CloudFormation Outputs to Terraform outputs
   ```yaml
   # CloudFormation
   Outputs:
     VpcId:
       Value: !Ref VPC
   ```
   ```hcl
   # Terraform (generated)
   output "vpc_id" {
     value = aws_vpc.vpc.id
   }
   ```

4. **Tag propagation:** Preserves resource tags

5. **File organization:** Separates concerns into logical files

### Known Issues and Limitations ⚠️

#### 1. Intrinsic Function Errors

**Problem:** `!GetAZs` fails with "local variable 'az_data' referenced before assignment"

**Example error:**
```hcl
availability_zone = element(// Unable to resolve Fn::GetAZs with value: "" 
                            because local variable 'az_data' referenced before assignment, 0)
```

**Workaround:** Manually replace with data source
```hcl
data "aws_availability_zones" "available" {
  state = "available"
}

# Then use:
availability_zone = data.aws_availability_zones.available.names[0]
```

#### 2. Incorrect Attribute References

**Problem:** Uses `.arn` instead of `.id` for VPC references

**Generated (incorrect):**
```hcl
resource "aws_subnet" "public_subnet_a" {
  vpc_id = aws_vpc.vpc.arn  # WRONG! Should be .id
}
```

**Fixed:**
```hcl
resource "aws_subnet" "public_subnet_a" {
  vpc_id = aws_vpc.vpc.id  # Correct
}
```

#### 3. IAM Policy Document Syntax

**Problem:** Inline policies converted as objects instead of `jsonencode()`

**Generated (invalid):**
```hcl
force_detach_policies = [
  {
    PolicyName = "DynamoDBAccess"
    PolicyDocument = {
      Version = "2012-10-17"
      Statement = [ ... ]
    }
  }
]
```

**Fixed:**
```hcl
inline_policy {
  name = "DynamoDBAccess"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [ ... ]
  })
}
```

#### 4. VPC Gateway Attachment Type Confusion

**Problem:** Maps `AWS::EC2::VPCGatewayAttachment` to `aws_vpn_gateway_attachment` instead of inline

**Generated (incorrect):**
```hcl
resource "aws_vpn_gateway_attachment" "attach_gateway" {
  vpc_id = aws_internet_gateway.internet_gateway.id  # Wrong resource type
}
```

**Fixed:**
```hcl
# Internet gateway attachment is automatic in Terraform when vpc_id is set
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.vpc.id
}
```

#### 5. DynamoDB Table Schema

**Problem:** `attribute` as a list instead of separate blocks

**Generated (invalid):**
```hcl
attribute = [
  { name = "id", type = "S" },
  { name = "timestamp", type = "N" }
]
```

**Fixed:**
```hcl
attribute {
  name = "id"
  type = "S"
}
attribute {
  name = "timestamp"
  type = "N"
}
```

#### 6. Nested Stack Support

**Problem:** Does NOT convert `AWS::CloudFormation::Stack` to Terraform modules

**Limitation:** Nested stacks require manual module creation

#### 7. Condition Logic

**Problem:** CloudFormation Conditions not always converted correctly

**Example:**
```yaml
Conditions:
  IsProduction: !Equals [!Ref Environment, "production"]
```
May not convert to Terraform `count` or `for_each` patterns.

#### 8. Lambda Function Code Inline

**Problem:** ZipFile code may not convert properly to Terraform `archive_file` data source

#### 9. AWS-Specific Only

**Critical limitation:** cf2tf only generates **AWS Terraform**, not OCI Terraform!

**Example output:**
```hcl
resource "aws_vpc" "vpc" {  # Still AWS provider!
  cidr_block = "10.0.0.0/16"
}
```

**What we need for OCI:**
```hcl
resource "oci_core_vcn" "vcn" {  # OCI provider
  compartment_id = var.compartment_id
  cidr_blocks    = ["10.0.0.0/16"]
}
```

## Conversion Workflow

### Phase 1: Initial Conversion (cf2tf)

```bash
# Convert all sample templates
for template in samples/*.yaml; do
  basename=$(basename "$template" .yaml)
  cf2tf "$template" -o "output/${basename}-converted"
done
```

### Phase 2: Manual Fixes (Required)

1. Fix attribute references (`.arn` → `.id`)
2. Fix intrinsic function errors (`!GetAZs`, `!Sub`)
3. Correct resource block syntax (IAM policies, DynamoDB attributes)
4. Remove/fix unsupported constructs

### Phase 3: AWS → OCI Translation (LLM-Assisted)

**This is where LLM enhancement is most valuable!**

For each AWS resource, map to OCI equivalent:

| AWS Resource | cf2tf Output | OCI Target | Complexity |
|--------------|--------------|------------|------------|
| `aws_vpc` | ✅ Generated | `oci_core_vcn` | Medium - Add compartment_id, regional subnets |
| `aws_subnet` | ✅ Generated | `oci_core_subnet` | High - Regional, not AZ-specific |
| `aws_security_group` | ✅ Generated | `oci_core_network_security_group` | High - Different rule model |
| `aws_db_instance` | ✅ Generated | `oci_database_db_system` | Very High - Different engines, config |
| `aws_lambda_function` | ✅ Generated | `oci_functions_function` | Very High - Different packaging, invocation |
| `aws_ecs_service` | ✅ Generated | `oci_containerengine_cluster` | Very High - Different orchestration |

## Where LLM Enhancement is Critical

### 1. Complex Conditionals

**CloudFormation:**
```yaml
Conditions:
  IsProduction: !Equals [!Ref Environment, "production"]
  HasMultiAZ: !And
    - !Condition IsProduction
    - !Equals [!Ref MultiAZ, "true"]

Resources:
  Database:
    Type: AWS::RDS::DBInstance
    Properties:
      DBInstanceClass: !If [IsProduction, db.r5.large, db.t3.small]
      MultiAZ: !Ref HasMultiAZ
```

**LLM can translate to:**
```hcl
locals {
  is_production = var.environment == "production"
  has_multi_az  = local.is_production && var.multi_az
}

resource "oci_database_db_system" "database" {
  shape = local.is_production ? "VM.Standard.E4.Flex" : "VM.Standard.E2.1.Micro"
  node_count = local.has_multi_az ? 2 : 1
  # ... OCI-specific configuration
}
```

### 2. Nested Stacks

**CloudFormation:**
```yaml
VPCStack:
  Type: AWS::CloudFormation::Stack
  Properties:
    TemplateURL: https://s3.../vpc-template.yaml
    Parameters:
      VpcCIDR: 10.0.0.0/16
```

**LLM can convert to:**
```hcl
module "vpc" {
  source = "./modules/vpc"
  
  cidr_block     = "10.0.0.0/16"
  compartment_id = var.compartment_id
}
```

### 3. Intrinsic Function Translation

**CloudFormation:**
```yaml
!Sub 
  - "jdbc:postgresql://${DBEndpoint}:${DBPort}/${DBName}"
  - DBEndpoint: !GetAtt MyDatabase.Endpoint.Address
    DBPort: !GetAtt MyDatabase.Endpoint.Port
```

**LLM can translate to:**
```hcl
locals {
  jdbc_url = "jdbc:postgresql://${oci_database_db_system.db.hostname}:1521/${var.db_name}"
}
```

### 4. Multi-AZ → Availability Domain Mapping

**CloudFormation (AWS):**
```yaml
PrivateSubnet1:
  Type: AWS::EC2::Subnet
  AvailabilityZone: us-east-1a
  CidrBlock: 10.0.1.0/24

PrivateSubnet2:
  Type: AWS::EC2::Subnet
  AvailabilityZone: us-east-1b
  CidrBlock: 10.0.2.0/24
```

**LLM translates to (OCI):**
```hcl
# Option 1: AD-specific subnets
data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

resource "oci_core_subnet" "private_ad1" {
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  cidr_block          = "10.0.1.0/24"
  vcn_id              = oci_core_vcn.main.id
  compartment_id      = var.compartment_id
}

# Option 2: Regional subnet (recommended for OCI)
resource "oci_core_subnet" "private" {
  cidr_block     = "10.0.1.0/24"
  vcn_id         = oci_core_vcn.main.id
  compartment_id = var.compartment_id
  # No AD specified = regional
}
```

### 5. Security Group → NSG Rule Expansion

**CloudFormation:**
```yaml
SecurityGroup:
  SecurityGroupIngress:
    - IpProtocol: tcp
      FromPort: 80
      ToPort: 443
      CidrIp: 0.0.0.0/0
```

**LLM expands to (OCI):**
```hcl
resource "oci_core_network_security_group" "web" {
  vcn_id         = oci_core_vcn.main.id
  compartment_id = var.compartment_id
}

# HTTP rule
resource "oci_core_network_security_group_security_rule" "http" {
  network_security_group_id = oci_core_network_security_group.web.id
  direction                 = "INGRESS"
  protocol                  = "6"  # TCP
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  
  tcp_options {
    destination_port_range {
      min = 80
      max = 80
    }
  }
}

# HTTPS rule
resource "oci_core_network_security_group_security_rule" "https" {
  network_security_group_id = oci_core_network_security_group.web.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}
```

### 6. Database Engine Translation

**CloudFormation:**
```yaml
DBInstance:
  Engine: postgres
  EngineVersion: "14.7"
```

**LLM handles engine mismatch:**
```hcl
# Option 1: PostgreSQL on Autonomous Database
resource "oci_database_autonomous_database" "db" {
  db_name            = var.db_name
  db_workload        = "OLTP"
  db_version         = "19c"  # Note: OCI uses Oracle versions
  # PostgreSQL compatibility requires manual setup
}

# Option 2: Self-managed PostgreSQL on Compute
resource "oci_core_instance" "postgres" {
  # Install PostgreSQL via cloud-init
  # More manual work, but direct PostgreSQL support
}
```

## Testing and Validation

### 1. Syntax Check

```bash
cd output/vpc-converted/
terraform init
terraform validate
```

**Expected issues after cf2tf:**
- Invalid attribute references
- Syntax errors in inline policies
- Missing required OCI-specific fields

### 2. Plan Dry-Run (AWS)

```bash
terraform plan
```

This will fail for AWS→OCI conversion but validates Terraform syntax.

### 3. Manual Review Checklist

- [ ] All `!Ref` and `!GetAtt` converted correctly
- [ ] IAM policies use `jsonencode()`
- [ ] VPC attachments fixed
- [ ] DynamoDB/other schema blocks correct
- [ ] Outputs reference correct attributes
- [ ] Variables have correct types

## Recommended Approach

**For this AWS→OCI migration project:**

1. ✅ **Use cf2tf for initial structure** - Gets 75% of AWS Terraform syntax right
2. ✅ **Manual fixes for cf2tf bugs** - Correct attribute references, policy syntax
3. 🚀 **LLM-powered AWS→OCI translation** - Resource-by-resource mapping with context awareness
4. ✅ **Human review and testing** - Validate generated OCI code

**cf2tf is valuable for:**
- Converting CloudFormation syntax to HCL
- Extracting parameters → variables
- Initial resource graph structure

**cf2tf is NOT sufficient for:**
- AWS → OCI provider translation (requires manual/LLM work)
- Complex conditionals and nested stacks
- Intrinsic function edge cases
- Security group rule expansion
- Database engine migrations

## Summary

**cf2tf tool status:** ✅ Installed and tested  
**Conversion rate:** ~75% structural conversion (AWS→AWS)  
**Manual effort required:** High for AWS→OCI translation  
**LLM enhancement areas:** Resource mapping, conditionals, nested stacks, multi-AZ→AD, security rules, database engines  
**Recommended workflow:** cf2tf → Manual fixes → LLM translation → Human review
