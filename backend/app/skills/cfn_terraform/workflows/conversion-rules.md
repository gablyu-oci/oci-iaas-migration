# CloudFormation to Terraform (OCI) Conversion Rules

## Overview
Systematic rules for converting AWS CloudFormation templates to OCI-compatible Terraform HCL.

## Key Differences: CloudFormation vs Terraform (OCI)

### 1. Syntax & Structure

**CloudFormation (YAML/JSON):**
```yaml
Resources:
  MyInstance:
    Type: AWS::EC2::Instance
    Properties:
      ImageId: ami-12345678
      InstanceType: t3.medium
```

**Terraform (HCL):**
```hcl
resource "oci_core_instance" "my_instance" {
  availability_domain = data.oci_identity_availability_domain.ad.name
  compartment_id      = var.compartment_id
  shape               = "VM.Standard.E4.Flex"
  source_details {
    source_type = "image"
    source_id   = var.instance_image_ocid
  }
}
```

### 2. Core Conversion Mapping

| CloudFormation Concept | Terraform Equivalent | Notes |
|------------------------|---------------------|-------|
| `Resources:` | `resource "..."` | Direct mapping |
| `Parameters:` | `variable "..."` | Input variables |
| `Outputs:` | `output "..."` | Return values |
| `!Ref` | `var.name` or `resource.id` | Context-dependent |
| `!GetAtt` | `resource.attribute` | Direct attribute access |
| `!Sub` | `"${var.name}"` | String interpolation |
| `!Join` | `join(",", list)` | Function call |
| `Fn::If` | `condition ? true : false` | Ternary operator |
| `DependsOn` | Implicit (Terraform graph) | Rarely needed explicitly |
| Nested stacks | Modules | `module "name" { source = "..." }` |

### 3. AWS → OCI Resource Mapping

#### Networking
```
AWS::EC2::VPC                    → oci_core_vcn
AWS::EC2::Subnet                 → oci_core_subnet (NOTE: regional in OCI, not AZ-specific)
AWS::EC2::InternetGateway        → oci_core_internet_gateway
AWS::EC2::NatGateway             → oci_core_nat_gateway
AWS::EC2::RouteTable             → oci_core_route_table
AWS::EC2::SecurityGroup          → oci_core_security_list (different model)
AWS::EC2::NetworkInterface       → oci_core_vnic_attachment
```

#### Compute
```
AWS::EC2::Instance               → oci_core_instance
AWS::EC2::LaunchTemplate         → oci_core_instance_configuration
AWS::AutoScaling::AutoScalingGroup → oci_core_instance_pool
AWS::AutoScaling::LaunchConfiguration → oci_core_instance_configuration
AWS::EC2::Volume (EBS)           → oci_core_volume
AWS::EC2::VolumeAttachment       → oci_core_volume_attachment
```

#### Database
```
AWS::RDS::DBInstance             → oci_database_db_system
AWS::RDS::DBSubnetGroup          → oci_database_db_system.subnet_id (embedded)
AWS::RDS::DBParameterGroup       → Managed via db_system parameters
```

#### Load Balancing
```
AWS::ElasticLoadBalancingV2::LoadBalancer → oci_load_balancer_load_balancer
AWS::ElasticLoadBalancingV2::TargetGroup  → oci_load_balancer_backend_set
AWS::ElasticLoadBalancingV2::Listener     → oci_load_balancer_listener
```

#### Storage
```
AWS::S3::Bucket                  → oci_objectstorage_bucket
AWS::S3::BucketPolicy            → oci_objectstorage_bucket.access_type + IAM policies
```

#### IAM
```
AWS::IAM::Role                   → oci_identity_dynamic_group (for instances)
AWS::IAM::Policy                 → oci_identity_policy
AWS::IAM::InstanceProfile        → oci_identity_dynamic_group (different pattern)
```

## Conversion Workflow

### Phase 1: Parse CloudFormation Template

**Extract sections:**
1. Parameters → Variables
2. Mappings → Locals or data sources
3. Conditions → Terraform conditionals
4. Resources → Resources
5. Outputs → Outputs

**Tools:**
- `cfn-flip` (YAML ↔ JSON conversion)
- `yq` / `jq` (JSON parsing)
- Python `yaml` / `json` libraries

### Phase 2: Resource Type Translation

**For each CloudFormation resource:**

1. **Identify AWS resource type** (e.g., `AWS::EC2::Instance`)
2. **Map to OCI resource type** (e.g., `oci_core_instance`)
3. **Translate properties:**
   - AWS property → OCI argument mapping
   - Handle required vs optional differences
   - Convert enums (e.g., instance types)

**Example: EC2 Instance → OCI Compute Instance**

**AWS CloudFormation:**
```yaml
MyInstance:
  Type: AWS::EC2::Instance
  Properties:
    ImageId: !Ref LatestAmiId
    InstanceType: t3.medium
    SubnetId: !Ref PrivateSubnet1
    SecurityGroupIds:
      - !Ref WebServerSecurityGroup
    Tags:
      - Key: Name
        Value: WebServer
```

**OCI Terraform:**
```hcl
resource "oci_core_instance" "my_instance" {
  availability_domain = data.oci_identity_availability_domain.ad1.name
  compartment_id      = var.compartment_id
  shape               = "VM.Standard.E4.Flex"  # t3.medium equivalent
  
  shape_config {
    ocpus         = 2
    memory_in_gbs = 8
  }
  
  source_details {
    source_type = "image"
    source_id   = var.latest_image_ocid
  }
  
  create_vnic_details {
    subnet_id        = oci_core_subnet.private_subnet1.id
    assign_public_ip = false
    nsg_ids          = [oci_core_network_security_group.webserver.id]
  }
  
  metadata = {
    ssh_authorized_keys = var.ssh_public_key
  }
  
  freeform_tags = {
    "Name" = "WebServer"
  }
}
```

### Phase 3: Handle CloudFormation Functions

#### `!Ref` Translation

**Pattern matching:**
- `!Ref Parameter` → `var.parameter_name`
- `!Ref Resource` → `resource_type.resource_name.id`
- `!Ref AWS::Region` → `var.region`
- `!Ref AWS::AccountId` → `var.tenancy_ocid`

**Example:**
```yaml
# CloudFormation
SubnetId: !Ref PrivateSubnet

# Terraform
subnet_id = oci_core_subnet.private_subnet.id
```

#### `!GetAtt` Translation

**Direct attribute access:**
```yaml
# CloudFormation
!GetAtt MyInstance.PrivateIp

# Terraform
oci_core_instance.my_instance.private_ip
```

#### `!Sub` Translation

**String interpolation:**
```yaml
# CloudFormation
!Sub "https://${MyLoadBalancer.DNSName}/api"

# Terraform
"https://${oci_load_balancer_load_balancer.my_lb.ip_addresses[0]}/api"
```

#### `!Join` Translation

```yaml
# CloudFormation
!Join [",", [!Ref Subnet1, !Ref Subnet2]]

# Terraform
join(",", [oci_core_subnet.subnet1.id, oci_core_subnet.subnet2.id])
```

#### Conditionals

**CloudFormation:**
```yaml
Conditions:
  IsProduction: !Equals [!Ref EnvironmentType, "prod"]

Resources:
  MyInstance:
    Type: AWS::EC2::Instance
    Properties:
      InstanceType: !If [IsProduction, m5.large, t3.small]
```

**Terraform:**
```hcl
locals {
  is_production = var.environment_type == "prod"
}

resource "oci_core_instance" "my_instance" {
  shape = local.is_production ? "VM.Standard.E4.Flex" : "VM.Standard.E2.1.Micro"
}
```

### Phase 4: Networking Conversion

**Critical difference: OCI subnets are REGIONAL, not AZ-specific**

**AWS Multi-AZ Pattern:**
```yaml
PrivateSubnet1:
  Type: AWS::EC2::Subnet
  Properties:
    VpcId: !Ref VPC
    CidrBlock: 10.0.1.0/24
    AvailabilityZone: us-west-2a

PrivateSubnet2:
  Type: AWS::EC2::Subnet
  Properties:
    VpcId: !Ref VPC
    CidrBlock: 10.0.2.0/24
    AvailabilityZone: us-west-2b
```

**OCI Regional Subnet:**
```hcl
resource "oci_core_subnet" "private_subnet" {
  cidr_block     = "10.0.1.0/24"
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  # No AZ - regional by default
  # Use multiple subnets or distribute instances manually across ADs
}
```

**Multi-AD strategy:**
```hcl
# Create separate subnets per AD if needed
resource "oci_core_subnet" "private_ad1" {
  cidr_block          = "10.0.1.0/24"
  compartment_id      = var.compartment_id
  vcn_id              = oci_core_vcn.main.id
  availability_domain = data.oci_identity_availability_domain.ad1.name  # AD-specific
}

resource "oci_core_subnet" "private_ad2" {
  cidr_block          = "10.0.2.0/24"
  compartment_id      = var.compartment_id
  vcn_id              = oci_core_vcn.main.id
  availability_domain = data.oci_identity_availability_domain.ad2.name
}
```

### Phase 5: Security Groups → Network Security Groups

**AWS Security Group:**
```yaml
WebServerSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    GroupDescription: Allow HTTP/HTTPS
    VpcId: !Ref VPC
    SecurityGroupIngress:
      - IpProtocol: tcp
        FromPort: 80
        ToPort: 80
        CidrIp: 0.0.0.0/0
      - IpProtocol: tcp
        FromPort: 443
        ToPort: 443
        CidrIp: 0.0.0.0/0
```

**OCI Network Security Group:**
```hcl
resource "oci_core_network_security_group" "webserver" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "WebServerNSG"
}

resource "oci_core_network_security_group_security_rule" "http_ingress" {
  network_security_group_id = oci_core_network_security_group.webserver.id
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

resource "oci_core_network_security_group_security_rule" "https_ingress" {
  network_security_group_id = oci_core_network_security_group.webserver.id
  direction                 = "INGRESS"
  protocol                  = "6"  # TCP
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

**Alternative: Security Lists (stateful, subnet-level):**
```hcl
resource "oci_core_security_list" "webserver" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "WebServerSecurityList"
  
  ingress_security_rules {
    protocol = "6"  # TCP
    source   = "0.0.0.0/0"
    
    tcp_options {
      min = 80
      max = 80
    }
  }
  
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    
    tcp_options {
      min = 443
      max = 443
    }
  }
}
```

### Phase 6: RDS → OCI Database

**AWS RDS Instance:**
```yaml
MyDatabase:
  Type: AWS::RDS::DBInstance
  Properties:
    Engine: postgres
    EngineVersion: "14.7"
    DBInstanceClass: db.t3.medium
    AllocatedStorage: 100
    DBName: myappdb
    MasterUsername: admin
    MasterUserPassword: !Ref DBPassword
    DBSubnetGroupName: !Ref DBSubnetGroup
    VPCSecurityGroups:
      - !Ref DatabaseSecurityGroup
```

**OCI Database System:**
```hcl
resource "oci_database_db_system" "my_database" {
  availability_domain = data.oci_identity_availability_domain.ad1.name
  compartment_id      = var.compartment_id
  subnet_id           = oci_core_subnet.database_subnet.id
  shape               = "VM.Standard.E4.Flex"  # db.t3.medium equivalent
  
  database_edition = "ENTERPRISE_EDITION_EXTREME_PERFORMANCE"  # or STANDARD_EDITION
  
  db_home {
    database {
      admin_password = var.db_password
      db_name        = "myappdb"
      pdb_name       = "myapp_pdb"
    }
    db_version = "19.0.0.0"  # Oracle DB (no direct PostgreSQL on DB Systems)
  }
  
  ssh_public_keys = [var.ssh_public_key]
  
  node_count = 1  # Single node for dev
  
  data_storage_size_in_gb = 256  # Minimum 256GB
  
  license_model = "LICENSE_INCLUDED"  # or "BRING_YOUR_OWN_LICENSE"
}
```

**NOTE: PostgreSQL on OCI requires Autonomous Database:**
```hcl
resource "oci_database_autonomous_database" "my_postgres" {
  compartment_id           = var.compartment_id
  db_name                  = "myappdb"
  admin_password           = var.db_password
  db_workload              = "OLTP"
  db_version               = "19c"  # PostgreSQL via Autonomous
  data_storage_size_in_tbs = 1
  cpu_core_count           = 1
  is_auto_scaling_enabled  = false
  license_model            = "LICENSE_INCLUDED"
}
```

### Phase 7: Auto Scaling Groups

**AWS AutoScaling:**
```yaml
WebServerGroup:
  Type: AWS::AutoScaling::AutoScalingGroup
  Properties:
    LaunchConfigurationName: !Ref LaunchConfig
    MinSize: 2
    MaxSize: 10
    DesiredCapacity: 2
    VPCZoneIdentifier:
      - !Ref PrivateSubnet1
      - !Ref PrivateSubnet2
    TargetGroupARNs:
      - !Ref WebServerTargetGroup
```

**OCI Instance Pool:**
```hcl
resource "oci_core_instance_pool" "webserver_pool" {
  compartment_id = var.compartment_id
  instance_configuration_id = oci_core_instance_configuration.webserver.id
  
  placement_configurations {
    availability_domain = data.oci_identity_availability_domain.ad1.name
    primary_subnet_id   = oci_core_subnet.private_subnet1.id
  }
  
  placement_configurations {
    availability_domain = data.oci_identity_availability_domain.ad2.name
    primary_subnet_id   = oci_core_subnet.private_subnet2.id
  }
  
  size = 2  # Initial size
  
  load_balancers {
    backend_set_name = oci_load_balancer_backend_set.webserver.name
    load_balancer_id = oci_load_balancer_load_balancer.main.id
    port             = 80
    vnic_selection   = "PrimaryVnic"
  }
}

resource "oci_autoscaling_auto_scaling_configuration" "webserver" {
  compartment_id       = var.compartment_id
  auto_scaling_resources {
    id   = oci_core_instance_pool.webserver_pool.id
    type = "instancePool"
  }
  
  policies {
    display_name = "ScaleOnCPU"
    capacity {
      initial = 2
      max     = 10
      min     = 2
    }
    policy_type = "threshold"
    rules {
      action {
        type  = "CHANGE_COUNT_BY"
        value = 1
      }
      display_name = "ScaleUp"
      metric {
        metric_type = "CPU_UTILIZATION"
        threshold {
          operator = "GT"
          value    = 80
        }
      }
    }
  }
}
```

## Edge Cases & Limitations

### 1. No Direct Equivalent

**CloudFormation features without OCI mapping:**

- **DeletionPolicy: Retain** → Terraform `prevent_destroy` lifecycle
- **UpdateReplacePolicy** → Manual backup before `terraform apply`
- **CreationPolicy** (wait conditions) → `null_resource` with provisioners
- **AWS::CloudFormation::WaitCondition** → Terraform provisioners or external scripts

### 2. Intrinsic Function Complexity

**Nested functions:**
```yaml
# Complex CloudFormation
!Sub 
  - "jdbc:postgresql://${DBEndpoint}:${DBPort}/${DBName}"
  - DBEndpoint: !GetAtt MyDatabase.Endpoint.Address
    DBPort: !GetAtt MyDatabase.Endpoint.Port
    DBName: !Ref DatabaseName
```

**Terraform equivalent:**
```hcl
# More verbose but explicit
locals {
  db_endpoint = oci_database_db_system.my_database.hostname
  db_port     = 1521  # Oracle default (no PostgreSQL direct equivalent)
  db_name     = var.database_name
  jdbc_url    = "jdbc:oracle:thin:@//${local.db_endpoint}:${local.db_port}/${local.db_name}"
}
```

### 3. Mappings

**CloudFormation Mappings:**
```yaml
Mappings:
  RegionMap:
    us-east-1:
      AMI: ami-12345678
    us-west-2:
      AMI: ami-87654321

Resources:
  MyInstance:
    Properties:
      ImageId: !FindInMap [RegionMap, !Ref "AWS::Region", AMI]
```

**Terraform Locals:**
```hcl
locals {
  region_image_map = {
    "us-ashburn-1"  = "ocid1.image.oc1.iad.aaa..."
    "us-phoenix-1"  = "ocid1.image.oc1.phx.aaa..."
  }
  instance_image = local.region_image_map[var.region]
}

resource "oci_core_instance" "my_instance" {
  source_details {
    source_id = local.instance_image
  }
}
```

### 4. Nested Stacks

**CloudFormation:**
```yaml
DatabaseStack:
  Type: AWS::CloudFormation::Stack
  Properties:
    TemplateURL: https://s3.amazonaws.com/bucket/rds-template.yaml
    Parameters:
      DBPassword: !Ref MasterPassword
```

**Terraform Modules:**
```hcl
module "database" {
  source = "./modules/rds"  # or git::https://... or registry
  
  db_password = var.master_password
  compartment_id = var.compartment_id
}
```

## Validation & Testing

### Step 1: Syntax Validation
```bash
terraform init
terraform validate
```

### Step 2: Plan Review
```bash
terraform plan -out=tfplan
terraform show tfplan
```

### Step 3: Dry-Run Deploy (Test Compartment)
```bash
terraform apply -var="compartment_id=ocid1.compartment.oc1..test"
```

### Step 4: Smoke Tests
- Can instances reach internet (via NAT gateway)?
- Can load balancer route to backend instances?
- Can application connect to database?

### Step 5: Teardown
```bash
terraform destroy
```

## Automation Strategy

### Phase 1: Structural Conversion (cf2tf Tool)

**Use existing cf2tf for initial conversion:**
```bash
cf2tf -f cloudformation-template.yaml -o terraform-draft.tf
```

**Output:** Basic Terraform structure (AWS resources, not OCI)

### Phase 2: AWS → OCI Resource Mapping (LLM-Assisted)

**Workflow:**
1. Parse `terraform-draft.tf` (AWS resources)
2. For each `resource "aws_*"` block:
   - LLM maps to `oci_*` equivalent
   - LLM translates properties
   - LLM flags unmappable features
3. Generate OCI-compatible `.tf` file

**LLM Prompt Template:**
```
You are a cloud infrastructure expert specializing in AWS to OCI migrations.

Task: Convert the following AWS Terraform resource to OCI Terraform.

Input (AWS Terraform):
{aws_resource_block}

Output Requirements:
1. OCI resource type (e.g., oci_core_instance)
2. Translated arguments (map AWS properties → OCI arguments)
3. Required OCI-specific additions (compartment_id, availability_domain)
4. Gaps report (features not translatable)

OCI provider version: 5.x
Region: {target_region}
Compartment: {compartment_ocid}
```

### Phase 3: Manual Review & Refinement

**Human validates:**
- Network topology (regional subnets vs AZ-specific)
- Security rules (NSG vs Security Lists)
- Database engine (PostgreSQL → Autonomous DB Oracle? or external PostgreSQL on Compute?)
- Load balancer listeners (HTTP/HTTPS termination)

### Phase 4: Module Extraction

**Create reusable modules:**
```
modules/
  ├── networking/     # VCN, subnets, gateways
  ├── compute/        # Instances, instance pools
  ├── database/       # DB systems, autonomous DBs
  └── loadbalancer/   # LB, backend sets, listeners
```

## Output Format

For each CloudFormation template, generate:

**1. OCI Terraform Code** (`main.tf`, `variables.tf`, `outputs.tf`)  
**2. Prerequisites Checklist:**
- Compartment structure
- SSH key pairs
- Network sources (for security rules)

**3. Conversion Report:**
```yaml
source_template: "vpc-ec2-rds.yaml"
resources_converted: 23
resources_flagged: 2
conversion_rate: 92%

flagged_resources:
  - resource: "AWS::RDS::DBInstance (PostgreSQL)"
    issue: "No native PostgreSQL on OCI DB Systems; recommend Autonomous DB or Compute-based PostgreSQL"
    workaround: "Deploy PostgreSQL on OCI Compute instance or use Autonomous DB with Oracle"
  
  - resource: "AWS::CloudFormation::WaitCondition"
    issue: "No Terraform equivalent for CloudFormation wait conditions"
    workaround: "Use null_resource with local-exec provisioner for post-deploy checks"

estimated_manual_effort: "4-6 hours (database migration, wait condition removal)"
```

---

**Next Steps:**
1. Test cf2tf tool with sample templates
2. Build LLM-based AWS→OCI mapper
3. Create validation framework
4. Document module structure
