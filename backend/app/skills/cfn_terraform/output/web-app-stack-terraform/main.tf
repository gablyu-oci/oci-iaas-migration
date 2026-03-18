# =============================================================================
# OCI Terraform – 3-Tier Web Application
# OCI Load Balancer + OKE (Virtual Nodes / Fargate-equivalent) + OCI PostgreSQL
# Converted from AWS CloudFormation: ALB + ECS Fargate + RDS PostgreSQL
# =============================================================================

terraform {
  required_version = ">= 1.3.0"
  required_providers {
    oci = {
      source  = "hashicorp/oci"
      version = ">= 5.0.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = ">= 2.23.0"
    }
  }
}

# ---------------------------------------------------------------------------
# OCI Provider
# ---------------------------------------------------------------------------
provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

# ---------------------------------------------------------------------------
# Kubernetes Provider
# Authenticates to the OKE cluster after it is created via the OCI CLI
# exec credential plugin. Run Phase-1 apply first (see migration_prerequisites).
# ---------------------------------------------------------------------------
provider "kubernetes" {
  host                   = local.oke_endpoint
  cluster_ca_certificate = local.oke_ca_cert

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "oci"
    args = [
      "ce", "cluster", "generate-token",
      "--cluster-id", oci_containerengine_cluster.app_cluster.id,
      "--region", var.region
    ]
  }
}

# =============================================================================
# DATA SOURCES
# =============================================================================

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.compartment_id
}

data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.compartment_id
}

data "oci_core_services" "all" {}

# ---------------------------------------------------------------------------
# Optional: reference existing VCN / subnets
# Set use_existing_vcn = true to mirror the CFN pattern of accepting VpcId
# and SubnetIds as input parameters rather than creating new networking.
# ---------------------------------------------------------------------------
data "oci_core_vcn" "existing" {
  count  = var.use_existing_vcn ? 1 : 0
  vcn_id = var.existing_vcn_id
}

data "oci_core_subnet" "existing_public_1" {
  count     = var.use_existing_vcn ? 1 : 0
  subnet_id = var.existing_public_subnet_ids[0]
}

data "oci_core_subnet" "existing_public_2" {
  count     = var.use_existing_vcn ? 1 : 0
  subnet_id = var.existing_public_subnet_ids[1]
}

data "oci_core_subnet" "existing_private_app_1" {
  count     = var.use_existing_vcn ? 1 : 0
  subnet_id = var.existing_private_app_subnet_ids[0]
}

data "oci_core_subnet" "existing_private_app_2" {
  count     = var.use_existing_vcn ? 1 : 0
  subnet_id = var.existing_private_app_subnet_ids[1]
}

data "oci_core_subnet" "existing_private_db" {
  count     = var.use_existing_vcn ? 1 : 0
  subnet_id = var.existing_private_db_subnet_id
}

# =============================================================================
# LOCALS
# =============================================================================

locals {
  name_prefix = "${var.environment}-app"

  common_tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "terraform"
    SourceStack = "cfn-3tier-web-app"
  }

  ad1 = data.oci_identity_availability_domains.ads.availability_domains[0].name
  ad2 = length(data.oci_identity_availability_domains.ads.availability_domains) > 1 ? data.oci_identity_availability_domains.ads.availability_domains[1].name : data.oci_identity_availability_domains.ads.availability_domains[0].name

  # ---------------------------------------------------------------------------
  # Resolved networking IDs – works in both new-VCN and existing-VCN modes.
  # ---------------------------------------------------------------------------
  vcn_id             = var.use_existing_vcn ? data.oci_core_vcn.existing[0].id             : oci_core_vcn.main[0].id
  public_subnet_1_id = var.use_existing_vcn ? data.oci_core_subnet.existing_public_1[0].id : oci_core_subnet.public_1[0].id
  public_subnet_2_id = var.use_existing_vcn ? data.oci_core_subnet.existing_public_2[0].id : oci_core_subnet.public_2[0].id
  private_app_1_id   = var.use_existing_vcn ? data.oci_core_subnet.existing_private_app_1[0].id : oci_core_subnet.private_app_1[0].id
  private_app_2_id   = var.use_existing_vcn ? data.oci_core_subnet.existing_private_app_2[0].id : oci_core_subnet.private_app_2[0].id
  private_db_id      = var.use_existing_vcn ? data.oci_core_subnet.existing_private_db[0].id    : oci_core_subnet.private_db[0].id

  # ---------------------------------------------------------------------------
  # OKE cluster endpoint and CA certificate – safe defaults before cluster exists
  # so the kubernetes provider config does not error during plan.
  # ---------------------------------------------------------------------------
  oke_endpoint = length(oci_containerengine_cluster.app_cluster.endpoints) > 0 ? "https://${oci_containerengine_cluster.app_cluster.endpoints[0].private_endpoint}" : "https://localhost"
  oke_ca_cert  = length(oci_containerengine_cluster.app_cluster.metadata) > 0 ? base64decode(oci_containerengine_cluster.app_cluster.metadata[0].kubernetes_api_server_cert_pem) : ""

  # ---------------------------------------------------------------------------
  # OCIR image URI – use explicit var or auto-construct from region / namespace
  # ---------------------------------------------------------------------------
  app_image = var.app_image_uri != "" ? var.app_image_uri : "${var.region}.ocir.io/${data.oci_objectstorage_namespace.ns.namespace}/acme-app:latest"

  # DB primary endpoint FQDN (resolved after oci_psql_db_system is created)
  db_host = length(oci_psql_db_system.app_db.endpoints) > 0 ? oci_psql_db_system.app_db.endpoints[0].fqdn : ""
}

# =============================================================================
# NETWORKING – VCN  (created only when use_existing_vcn = false)
# =============================================================================

resource "oci_core_vcn" "main" {
  count          = var.use_existing_vcn ? 0 : 1
  compartment_id = var.compartment_id
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${local.name_prefix}-vcn"
  dns_label      = "appvcn"

  freeform_tags = local.common_tags
}

resource "oci_core_internet_gateway" "igw" {
  count          = var.use_existing_vcn ? 0 : 1
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main[0].id
  display_name   = "${local.name_prefix}-igw"
  enabled        = true

  freeform_tags = local.common_tags
}

resource "oci_core_nat_gateway" "nat" {
  count          = var.use_existing_vcn ? 0 : 1
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main[0].id
  display_name   = "${local.name_prefix}-nat"
  block_traffic  = false

  freeform_tags = local.common_tags
}

resource "oci_core_service_gateway" "sgw" {
  count          = var.use_existing_vcn ? 0 : 1
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main[0].id
  display_name   = "${local.name_prefix}-sgw"

  services {
    service_id = data.oci_core_services.all.services[0].id
  }

  freeform_tags = local.common_tags
}

# --- Route Tables ---

resource "oci_core_route_table" "public" {
  count          = var.use_existing_vcn ? 0 : 1
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main[0].id
  display_name   = "${local.name_prefix}-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.igw[0].id
  }

  freeform_tags = local.common_tags
}

resource "oci_core_route_table" "private" {
  count          = var.use_existing_vcn ? 0 : 1
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main[0].id
  display_name   = "${local.name_prefix}-private-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_nat_gateway.nat[0].id
  }

  route_rules {
    destination       = data.oci_core_services.all.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.sgw[0].id
  }

  freeform_tags = local.common_tags
}

# --- Default Security List (allow all egress, no ingress) ---

resource "oci_core_security_list" "default" {
  count          = var.use_existing_vcn ? 0 : 1
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main[0].id
  display_name   = "${local.name_prefix}-default-sl"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
    stateless   = false
  }

  freeform_tags = local.common_tags
}

# --- Subnets ---

resource "oci_core_subnet" "public_1" {
  count             = var.use_existing_vcn ? 0 : 1
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.main[0].id
  cidr_block        = var.public_subnet_cidr_1
  display_name      = "${local.name_prefix}-public-subnet-1"
  dns_label         = "pubsub1"
  route_table_id    = oci_core_route_table.public[0].id
  security_list_ids = [oci_core_security_list.default[0].id]

  freeform_tags = local.common_tags
}

resource "oci_core_subnet" "public_2" {
  count             = var.use_existing_vcn ? 0 : 1
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.main[0].id
  cidr_block        = var.public_subnet_cidr_2
  display_name      = "${local.name_prefix}-public-subnet-2"
  dns_label         = "pubsub2"
  route_table_id    = oci_core_route_table.public[0].id
  security_list_ids = [oci_core_security_list.default[0].id]

  freeform_tags = local.common_tags
}

resource "oci_core_subnet" "private_app_1" {
  count                      = var.use_existing_vcn ? 0 : 1
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.main[0].id
  cidr_block                 = var.private_app_subnet_cidr_1
  display_name               = "${local.name_prefix}-private-app-subnet-1"
  dns_label                  = "appsub1"
  prohibit_public_ip_on_vnic = true
  route_table_id             = oci_core_route_table.private[0].id
  security_list_ids          = [oci_core_security_list.default[0].id]

  freeform_tags = local.common_tags
}

resource "oci_core_subnet" "private_app_2" {
  count                      = var.use_existing_vcn ? 0 : 1
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.main[0].id
  cidr_block                 = var.private_app_subnet_cidr_2
  display_name               = "${local.name_prefix}-private-app-subnet-2"
  dns_label                  = "appsub2"
  prohibit_public_ip_on_vnic = true
  route_table_id             = oci_core_route_table.private[0].id
  security_list_ids          = [oci_core_security_list.default[0].id]

  freeform_tags = local.common_tags
}

resource "oci_core_subnet" "private_db" {
  count                      = var.use_existing_vcn ? 0 : 1
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.main[0].id
  cidr_block                 = var.private_db_subnet_cidr
  display_name               = "${local.name_prefix}-private-db-subnet"
  dns_label                  = "dbsub"
  prohibit_public_ip_on_vnic = true
  route_table_id             = oci_core_route_table.private[0].id
  security_list_ids          = [oci_core_security_list.default[0].id]

  freeform_tags = local.common_tags
}

# =============================================================================
# NETWORK SECURITY GROUPS
# Maps: AWS Security Groups → OCI NSGs
# NSGs are stateful (like AWS SGs). Rules are separate resources.
# Source SG references → NETWORK_SECURITY_GROUP source/destination type.
# =============================================================================

# --- NSG: Load Balancer (maps ALBSecurityGroup) ---
resource "oci_core_network_security_group" "alb" {
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${local.name_prefix}-alb-nsg"

  freeform_tags = local.common_tags
}

# HTTP ingress (80) from internet
resource "oci_core_network_security_group_security_rule" "alb_http_ingress" {
  network_security_group_id = oci_core_network_security_group.alb.id
  direction                 = "INGRESS"
  protocol                  = "6" # TCP
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  stateless                 = false

  tcp_options {
    destination_port_range {
      min = 80
      max = 80
    }
  }
}

# HTTPS ingress (443) from internet
resource "oci_core_network_security_group_security_rule" "alb_https_ingress" {
  network_security_group_id = oci_core_network_security_group.alb.id
  direction                 = "INGRESS"
  protocol                  = "6" # TCP
  source                    = "0.0.0.0/0"
  source_type               = "CIDR_BLOCK"
  stateless                 = false

  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

# ALB egress to app tier on port 8080
resource "oci_core_network_security_group_security_rule" "alb_egress_app" {
  network_security_group_id = oci_core_network_security_group.alb.id
  direction                 = "EGRESS"
  protocol                  = "6" # TCP
  destination               = oci_core_network_security_group.app.id
  destination_type          = "NETWORK_SECURITY_GROUP"
  stateless                 = false

  tcp_options {
    destination_port_range {
      min = 8080
      max = 8080
    }
  }
}

# --- NSG: App tier (maps AppSecurityGroup) ---
resource "oci_core_network_security_group" "app" {
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${local.name_prefix}-app-nsg"

  freeform_tags = local.common_tags
}

# App ingress on 8080 – only from ALB NSG
resource "oci_core_network_security_group_security_rule" "app_ingress_from_alb" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "INGRESS"
  protocol                  = "6" # TCP
  source                    = oci_core_network_security_group.alb.id
  source_type               = "NETWORK_SECURITY_GROUP"
  stateless                 = false

  tcp_options {
    destination_port_range {
      min = 8080
      max = 8080
    }
  }
}

# App egress to DB NSG on 5432
resource "oci_core_network_security_group_security_rule" "app_egress_db" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "6" # TCP
  destination               = oci_core_network_security_group.db.id
  destination_type          = "NETWORK_SECURITY_GROUP"
  stateless                 = false

  tcp_options {
    destination_port_range {
      min = 5432
      max = 5432
    }
  }
}

# App egress to internet (image pulls, external APIs)
resource "oci_core_network_security_group_security_rule" "app_egress_internet" {
  network_security_group_id = oci_core_network_security_group.app.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  stateless                 = false
}

# --- NSG: Database tier (maps DBSecurityGroup) ---
resource "oci_core_network_security_group" "db" {
  compartment_id = var.compartment_id
  vcn_id         = local.vcn_id
  display_name   = "${local.name_prefix}-db-nsg"

  freeform_tags = local.common_tags
}

# DB ingress on 5432 – only from App NSG
resource "oci_core_network_security_group_security_rule" "db_ingress_from_app" {
  network_security_group_id = oci_core_network_security_group.db.id
  direction                 = "INGRESS"
  protocol                  = "6" # TCP
  source                    = oci_core_network_security_group.app.id
  source_type               = "NETWORK_SECURITY_GROUP"
  stateless                 = false

  tcp_options {
    destination_port_range {
      min = 5432
      max = 5432
    }
  }
}

# DB egress to OCI services (backups, patches)
resource "oci_core_network_security_group_security_rule" "db_egress_services" {
  network_security_group_id = oci_core_network_security_group.db.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = data.oci_core_services.all.services[0].cidr_block
  destination_type          = "SERVICE_CIDR_BLOCK"
  stateless                 = false
}

# =============================================================================
# DATABASE – OCI PostgreSQL DB System  (oci_psql_db_system)
#
# Maps: AWS::RDS::DBInstance
#   Engine:               postgres 15.4   → db_version = "15"
#   DBInstanceClass:      db.t3.medium    → shape PostgreSQL.VM.Standard.E4.Flex.2.32GB
#   AllocatedStorage:     50 GB           → storage_size_in_gbs = 50
#   MultiAZ:              true            → instance_count = 2
#   BackupRetentionPeriod: 7              → management_policy.backup_policy.retention_days = 7
#   DeletionProtection:   true            → lifecycle { prevent_destroy = true }
#   StorageEncrypted:     true            → OCI storage is encrypted at rest by default
#
# oci_psql_db_system (GA 2024) advantages over ADB for this mapping:
#   • Standard PostgreSQL wire protocol – no wallet / mTLS required
#   • Supports standard PostgreSQL extensions
#   • 50 GB minimum storage (ADB forces 1 TB minimum)
#   • Configurable backup retention (ADB uses fixed 60-day retention)
#   • Comparable cost profile to RDS db.t3.medium
# =============================================================================

resource "oci_psql_db_system" "app_db" {
  compartment_id = var.compartment_id
  display_name   = "${local.name_prefix}-db"

  # PostgreSQL 15 maps RDS EngineVersion "15.4"
  db_version = "15"

  # Shape closest to db.t3.medium (2 vCPU / 4 GB RAM).
  # PostgreSQL DB Systems use OCI flexible shapes.
  shape = "PostgreSQL.VM.Standard.E4.Flex.2.32GB"

  # Storage – 50 GB directly maps RDS AllocatedStorage: 50
  storage_details {
    is_regionally_durable = true
    system_type           = "OCI_OPTIMIZED_STORAGE"
    storage_size_in_gbs   = var.db_storage_size_gb
  }

  # Credentials – maps MasterUsername/MasterUserPassword
  credentials {
    username = "appuser"
    password_details {
      password_type = "PLAIN_TEXT"
      password      = var.db_password
    }
  }

  # Networking – private subnet + DB NSG
  network_details {
    subnet_id                  = local.private_db_id
    nsg_ids                    = [oci_core_network_security_group.db.id]
    is_reader_endpoint_enabled = true
  }

  # HA – instance_count = 2 maps MultiAZ: true
  # A standby instance is placed in a second AD for automatic failover.
  instance_count          = 2
  instance_memory_size_in_gbs = 32
  instance_ocpu_count     = 2

  # Backup – maps BackupRetentionPeriod: 7 days
  management_policy {
    backup_policy {
      backup_start     = "02:00"
      days_of_the_week = ["SUNDAY"]
      kind             = "DAILY"
      retention_days   = var.db_backup_retention_days
    }
    maintenance_window_start = "SUNDAY 03:00"
  }

  freeform_tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-db"
  })

  lifecycle {
    # Maps DeletionProtection: true – prevents accidental terraform destroy
    prevent_destroy = true
    # Ignore credential drift after initial provisioning
    ignore_changes = [credentials]
  }
}

# =============================================================================
# CONTAINER REGISTRY – OCI Container Registry (OCIR)
# Maps: ECR repository referenced in ECS TaskDefinition image URI
# =============================================================================

resource "oci_artifacts_container_repository" "app" {
  compartment_id = var.compartment_id
  display_name   = "${local.name_prefix}/acme-app"
  is_public      = false
  is_immutable   = false

  freeform_tags = local.common_tags
}

# =============================================================================
# OKE CLUSTER – Maps AWS::ECS::Cluster
# OCI Kubernetes Engine with Virtual Nodes provides a Fargate-equivalent
# serverless compute experience (no node pool VMs to manage).
# =============================================================================

resource "oci_containerengine_cluster" "app_cluster" {
  compartment_id     = var.compartment_id
  kubernetes_version = var.kubernetes_version
  name               = "${local.name_prefix}-cluster"
  vcn_id             = local.vcn_id

  # ENHANCED_CLUSTER provides Container Insights-equivalent observability
  type = "ENHANCED_CLUSTER"

  endpoint_config {
    is_public_ip_enabled = false
    subnet_id            = local.private_app_1_id
    nsg_ids              = [oci_core_network_security_group.app.id]
  }

  options {
    service_lb_subnet_ids = [
      local.public_subnet_1_id,
      local.public_subnet_2_id
    ]

    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }

    kubernetes_network_config {
      pods_cidr     = "10.244.0.0/16"
      services_cidr = "10.96.0.0/16"
    }
  }

  freeform_tags = local.common_tags
}

# --- OKE Virtual Node Pool (Fargate-equivalent serverless pods) ---
# Maps ECS Fargate launch type + DesiredCount: 2
# Pod shape Pod.Standard.E4.Flex maps Fargate Cpu=256/Memory=512
resource "oci_containerengine_virtual_node_pool" "app" {
  cluster_id     = oci_containerengine_cluster.app_cluster.id
  compartment_id = var.compartment_id
  display_name   = "${local.name_prefix}-virtual-node-pool"

  pod_configuration {
    shape     = "Pod.Standard.E4.Flex"
    subnet_id = local.private_app_1_id
    nsg_ids   = [oci_core_network_security_group.app.id]
  }

  # Spread across two ADs – maps ECS multi-AZ subnet configuration
  placement_configurations {
    availability_domain = local.ad1
    fault_domain        = ["FAULT-DOMAIN-1", "FAULT-DOMAIN-2", "FAULT-DOMAIN-3"]
    subnet_id           = local.private_app_1_id
  }

  placement_configurations {
    availability_domain = local.ad2
    fault_domain        = ["FAULT-DOMAIN-1", "FAULT-DOMAIN-2", "FAULT-DOMAIN-3"]
    subnet_id           = local.private_app_2_id
  }

  size = var.app_desired_count

  freeform_tags = local.common_tags
}

# =============================================================================
# LOAD BALANCER – OCI Flexible Load Balancer
# Maps: AWS::ElasticLoadBalancingV2::LoadBalancer (internet-facing ALB)
# =============================================================================

resource "oci_load_balancer_load_balancer" "alb" {
  compartment_id = var.compartment_id
  display_name   = "${local.name_prefix}-lb"
  shape          = "flexible"
  is_private     = false # internet-facing maps Scheme: internet-facing

  shape_details {
    minimum_bandwidth_in_mbps = 10
    maximum_bandwidth_in_mbps = 100
  }

  subnet_ids = [
    local.public_subnet_1_id,
    local.public_subnet_2_id
  ]

  network_security_group_ids = [oci_core_network_security_group.alb.id]

  freeform_tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-lb"
  })
}

# --- Backend Set (maps AWS::ElasticLoadBalancingV2::TargetGroup) ---
resource "oci_load_balancer_backend_set" "app" {
  load_balancer_id = oci_load_balancer_load_balancer.alb.id
  name             = "app-backend-set"
  policy           = "ROUND_ROBIN"

  health_checker {
    protocol          = "HTTP"
    port              = 8080
    url_path          = "/health" # Maps HealthCheckPath: /health
    interval_ms       = 30000
    timeout_in_millis = 3000
    retries           = 3
    return_code       = 200
  }
}

# --- HTTP Listener on port 80 (maps AWS::ElasticLoadBalancingV2::Listener) ---
resource "oci_load_balancer_listener" "http" {
  load_balancer_id         = oci_load_balancer_load_balancer.alb.id
  name                     = "http-listener"
  default_backend_set_name = oci_load_balancer_backend_set.app.name
  port                     = 80
  protocol                 = "HTTP"

  connection_configuration {
    idle_timeout_in_seconds = 60
  }
}

# --- HTTPS Listener on port 443 ---
# Conditionally created when ssl_certificate_name is provided.
# The ALBSecurityGroup allows port 443 from 0.0.0.0/0 – mirrored in the ALB NSG.
resource "oci_load_balancer_listener" "https" {
  count = var.ssl_certificate_name != "" ? 1 : 0

  load_balancer_id         = oci_load_balancer_load_balancer.alb.id
  name                     = "https-listener"
  default_backend_set_name = oci_load_balancer_backend_set.app.name
  port                     = 443
  protocol                 = "HTTP"

  ssl_configuration {
    certificate_name        = var.ssl_certificate_name
    verify_peer_certificate = false
  }

  connection_configuration {
    idle_timeout_in_seconds = 60
  }
}

# =============================================================================
# KUBERNETES NAMESPACE
# Created before workload resources; depends on virtual node pool being ACTIVE.
# =============================================================================

resource "kubernetes_namespace" "app" {
  metadata {
    name = var.k8s_namespace
    labels = {
      environment = var.environment
      project     = var.project_name
    }
  }

  depends_on = [oci_containerengine_virtual_node_pool.app]
}

# =============================================================================
# KUBERNETES CONFIG MAP
# Maps: ECS TaskDefinition ContainerDefinitions[0].Environment
# DB_HOST resolved from the oci_psql_db_system primary endpoint FQDN.
# DB_PORT and ENVIRONMENT passed through directly.
# =============================================================================

resource "kubernetes_config_map" "app_env" {
  metadata {
    name      = "app-env"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  data = {
    DB_HOST     = local.db_host
    DB_PORT     = "5432"
    ENVIRONMENT = var.environment
  }

  depends_on = [oci_psql_db_system.app_db]
}

# =============================================================================
# KUBERNETES SECRET – DB Password
# Maps: DBPassword (NoEcho: true) injected as container environment variable.
# The raw password value is stored as a Kubernetes Opaque secret.
# Production recommendation: use OCI Vault + External Secrets Operator instead.
# =============================================================================

resource "kubernetes_secret" "db_password" {
  metadata {
    name      = "db-credentials"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  type = "Opaque"

  data = {
    password = var.db_password
  }

  lifecycle {
    ignore_changes = [data]
  }
}

# =============================================================================
# KUBERNETES DEPLOYMENT
# Maps: AWS::ECS::TaskDefinition + AWS::ECS::Service
#
# Mapping table:
#   TaskDefinition.Family               → metadata.name = "app"
#   TaskDefinition.Cpu = "256"          → resources.requests.cpu = "250m"
#   TaskDefinition.Memory = "512"       → resources.requests.memory = "512Mi"
#   TaskDefinition.ContainerDefinitions[0].Image → spec.containers[0].image
#   TaskDefinition.ContainerDefinitions[0].PortMappings[0].ContainerPort = 8080
#                                       → containerPort = 8080
#   TaskDefinition.ContainerDefinitions[0].Environment
#                                       → envFrom.configMapRef
#   TaskDefinition.ContainerDefinitions[0].LogConfiguration (awslogs)
#                                       → oracle.com/logging annotation + Fluent Bit
#   AppService.DesiredCount = 2         → spec.replicas = 2
#   AppService.NetworkConfiguration.AwsvpcConfiguration.SecurityGroups
#                                       → App NSG (applied at node pool level)
#   AppService.LaunchType = FARGATE     → Virtual Node Pool (Pod.Standard.E4.Flex)
# =============================================================================

resource "kubernetes_deployment" "app" {
  metadata {
    name      = "app"
    namespace = kubernetes_namespace.app.metadata[0].name
    labels = {
      app         = "acme-app"
      environment = var.environment
    }
  }

  spec {
    # Maps AppService.DesiredCount = 2
    replicas = var.app_desired_count

    selector {
      match_labels = {
        app = "acme-app"
      }
    }

    template {
      metadata {
        labels = {
          app         = "acme-app"
          environment = var.environment
        }
        annotations = {
          # OCI Logging integration – directs stdout/stderr to OCI Logging service.
          # Requires the OCI Logging Fluent Bit DaemonSet deployed on the cluster.
          # Deploy with: helm install oci-logging oci://...
          "oracle.com/logging" = "true"
        }
      }

      spec {
        container {
          name = "app"
          # Maps TaskDefinition image URI – resolved from OCIR
          image             = local.app_image
          image_pull_policy = "Always"

          # Maps TaskDefinition.ContainerDefinitions[0].PortMappings ContainerPort: 8080
          port {
            container_port = 8080
            name           = "http"
            protocol       = "TCP"
          }

          # Maps TaskDefinition.Cpu = "256" / Memory = "512"
          # 256 ECS CPU units ≈ 250m Kubernetes CPU
          resources {
            requests = {
              cpu    = "250m"
              memory = "512Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "1Gi"
            }
          }

          # Maps TaskDefinition.Environment: DB_HOST, DB_PORT, ENVIRONMENT
          env_from {
            config_map_ref {
              name = kubernetes_config_map.app_env.metadata[0].name
            }
          }

          # DB_PASSWORD injected from Kubernetes Secret (maps DBPassword NoEcho)
          env {
            name = "DB_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.db_password.metadata[0].name
                key  = "password"
              }
            }
          }

          # Liveness probe – mirrors ECS task health check
          liveness_probe {
            http_get {
              path = "/health"
              port = 8080
            }
            initial_delay_seconds = 30
            period_seconds        = 30
            timeout_seconds       = 5
            failure_threshold     = 3
          }

          # Readiness probe – gates traffic until container is ready
          readiness_probe {
            http_get {
              path = "/health"
              port = 8080
            }
            initial_delay_seconds = 10
            period_seconds        = 10
            timeout_seconds       = 3
            failure_threshold     = 3
          }
        }

        # OCIR image pull secret.
        # Pre-create with:
        #   kubectl create secret docker-registry ocir-pull-secret \
        #     --docker-server=<region>.ocir.io \
        #     --docker-username='<namespace>/<username>' \
        #     --docker-password='<oci-auth-token>' \
        #     -n <k8s_namespace>
        image_pull_secret {
          name = var.ocir_pull_secret_name
        }

        # Spread pods across availability domains for HA
        # Maps ECS multi-AZ subnet placement (PrivateSubnets across AZs)
        topology_spread_constraint {
          max_skew           = 1
          topology_key       = "topology.kubernetes.io/zone"
          when_unsatisfiable = "DoNotSchedule"
          label_selector {
            match_labels = {
              app = "acme-app"
            }
          }
        }
      }
    }
  }

  depends_on = [
    oci_containerengine_virtual_node_pool.app,
    kubernetes_config_map.app_env,
    kubernetes_secret.db_password
  ]
}

# =============================================================================
# HORIZONTAL POD AUTOSCALER
# Maps: AWS::CloudWatch::Alarm HighCPUAlarm (CPUUtilization > 80%)
# Replaces ECS Service auto-scaling driven by the CloudWatch alarm.
# Scale range: app_desired_count (min) → app_max_count (max)
# =============================================================================

resource "kubernetes_horizontal_pod_autoscaler_v2" "app" {
  metadata {
    name      = "app-hpa"
    namespace = kubernetes_namespace.app.metadata[0].name
  }

  spec {
    scale_target_ref {
      api_version = "apps/v1"
      kind        = "Deployment"
      name        = kubernetes_deployment.app.metadata[0].name
    }

    min_replicas = var.app_desired_count
    max_replicas = var.app_max_count

    metric {
      type = "Resource"
      resource {
        name = "cpu"
        target {
          type                = "Utilization"
          average_utilization = 80 # Maps HighCPUAlarm Threshold: 80
        }
      }
    }
  }

  depends_on = [kubernetes_deployment.app]
}

# =============================================================================
# KUBERNETES SERVICE
# Maps: AWS::ECS::Service LoadBalancers configuration + TargetGroup
#
# The OCI cloud-controller-manager annotation attaches this Service to the
# pre-created OCI Load Balancer backend set, rather than creating a new LB.
# Maps AppService.LoadBalancers ContainerName=app, ContainerPort=8080.
# DependsOn: Listener → depends_on oci_load_balancer_backend_set.app
# =============================================================================

resource "kubernetes_service" "app" {
  metadata {
    name      = "app-service"
    namespace = kubernetes_namespace.app.metadata[0].name
    labels = {
      app = "acme-app"
    }
    annotations = {
      # Attach to the pre-created OCI Load Balancer
      "service.beta.kubernetes.io/oci-load-balancer-id"            = oci_load_balancer_load_balancer.alb.id
      "service.beta.kubernetes.io/oci-load-balancer-shape"         = "flexible"
      "service.beta.kubernetes.io/oci-load-balancer-backend-set"   = oci_load_balancer_backend_set.app.name
      # Use NSG-based security rule management
      "oci.oraclecloud.com/security-rule-management-mode"          = "NSG"
    }
  }

  spec {
    selector = {
      app = "acme-app"
    }

    # Maps AppService ContainerPort 8080 exposed via Listener port 80
    port {
      name        = "http"
      port        = 80
      target_port = 8080
      protocol    = "TCP"
    }

    type = "LoadBalancer"
  }

  depends_on = [
    kubernetes_deployment.app,
    oci_load_balancer_backend_set.app,
    oci_load_balancer_listener.http
  ]
}

# =============================================================================
# LOGGING – OCI Logging Service
# Maps: AWS::Logs::LogGroup (/ecs/${StackName}/app, RetentionInDays: 14)
#
# OCI minimum log retention is 30 days (cannot match the requested 14 days).
# For cost control, configure an archival rule to Object Storage after 14 days.
# Application container logs require the OCI Logging Fluent Bit DaemonSet.
# =============================================================================

resource "oci_logging_log_group" "app" {
  compartment_id = var.compartment_id
  display_name   = "${local.name_prefix}-log-group"
  description    = "Application log group for ${local.name_prefix}"

  freeform_tags = local.common_tags
}

# Custom log for application container stdout/stderr
resource "oci_logging_log" "app_container" {
  display_name = "${local.name_prefix}-app-container-log"
  log_group_id = oci_logging_log_group.app.id
  log_type     = "CUSTOM"
  is_enabled   = true

  # OCI minimum retention is 30 days; CFN requested 14 days.
  retention_duration = 30

  freeform_tags = local.common_tags
}

# OKE cluster control-plane logs (API server activity)
resource "oci_logging_log" "oke_cluster" {
  display_name = "${local.name_prefix}-oke-cluster-log"
  log_group_id = oci_logging_log_group.app.id
  log_type     = "SERVICE"
  is_enabled   = true

  configuration {
    source {
      category    = "api"
      resource    = oci_containerengine_cluster.app_cluster.id
      service     = "oke"
      source_type = "OCISERVICE"
    }
    compartment_id = var.compartment_id
  }

  retention_duration = 30

  freeform_tags = local.common_tags
}

# =============================================================================
# NOTIFICATIONS – OCI ONS Topic
# Maps: SNS topic (implicit in CloudWatch Alarm ActionsEnabled)
# Alarms require an explicit ONS topic in OCI.
# =============================================================================

resource "oci_ons_notification_topic" "alerts" {
  compartment_id = var.compartment_id
  name           = "${local.name_prefix}-alerts"
  description    = "Alerting topic for ${local.name_prefix} monitoring alarms"

  freeform_tags = local.common_tags
}

resource "oci_ons_subscription" "alert_email" {
  count = var.alert_email != "" ? 1 : 0

  compartment_id = var.compartment_id
  topic_id       = oci_ons_notification_topic.alerts.id
  protocol       = "EMAIL"
  endpoint       = var.alert_email

  freeform_tags = local.common_tags
}

# =============================================================================
# MONITORING – OCI Monitoring Alarms
# Maps: AWS::CloudWatch::Alarm (HighCPUAlarm)
#
# CPUUtilization / AWS/ECS  → oci_containerengine CPUUtilization MQL
# Namespace: AWS/ECS        → oci_containerengine
# Period: 300 + EvalPeriods: 2 (10 min) → pending_duration = PT10M
# Threshold: 80             → > 80 in MQL
# =============================================================================

resource "oci_monitoring_alarm" "high_cpu" {
  compartment_id = var.compartment_id
  display_name   = "${local.name_prefix}-high-cpu"
  is_enabled     = true

  metric_compartment_id = var.compartment_id
  namespace             = "oci_containerengine"
  # MQL: average CPU > 80% over the evaluation window
  query = "CPUUtilization[5m]{clusterName = \"${local.name_prefix}-cluster\"}.mean() > 80"

  resolution = "5m"
  # Maps EvaluationPeriods: 2 × Period: 300 s = 10 minutes
  pending_duration = "PT10M"
  severity         = "CRITICAL"
  body             = "High CPU utilization on OKE cluster ${local.name_prefix}-cluster. Average CPU > 80% sustained over 10 minutes."

  destinations                                  = [oci_ons_notification_topic.alerts.topic_url]
  is_notifications_per_metric_dimension_enabled = false
  message_format                                = "ONS_OPTIMIZED"

  freeform_tags = local.common_tags
}

# Additional alarm: LB 5xx errors for operational visibility
resource "oci_monitoring_alarm" "lb_5xx" {
  compartment_id = var.compartment_id
  display_name   = "${local.name_prefix}-lb-5xx"
  is_enabled     = true

  metric_compartment_id = var.compartment_id
  namespace             = "oci_lbaas"
  query                 = "HttpResponses5xx[5m]{lbId = \"${oci_load_balancer_load_balancer.alb.id}\"}.sum() > 10"

  resolution       = "5m"
  pending_duration = "PT5M"
  severity         = "WARNING"
  body             = "Load Balancer 5xx error rate exceeded threshold."

  destinations   = [oci_ons_notification_topic.alerts.topic_url]
  message_format = "ONS_OPTIMIZED"

  freeform_tags = local.common_tags
}

# =============================================================================
# IAM – Dynamic Group + Policies
# Maps: AWS::IAM::Role (TaskExecutionRole for ECS Fargate)
#
# OCI uses Dynamic Groups (who) + Policies (what) instead of IAM Roles.
# The ECS task execution role's ECR pull permission maps to a policy allowing
# the OKE pods dynamic group to read repos from OCIR.
# =============================================================================

resource "oci_identity_dynamic_group" "oke_pods" {
  # Dynamic groups are tenancy-scoped resources
  compartment_id = var.tenancy_ocid
  name           = "${local.name_prefix}-oke-pods"
  description    = "Dynamic group for OKE pods in ${local.name_prefix} cluster"
  # Match all instances in the compartment.
  # For fine-grained pod-level identity use OKE Workload Identity instead.
  matching_rule = "ALL {instance.compartment.id = '${var.compartment_id}'}"

  freeform_tags = local.common_tags
}

resource "oci_identity_policy" "oke_pods" {
  compartment_id = var.compartment_id
  name           = "${local.name_prefix}-oke-pods-policy"
  description    = "Allows OKE pods to pull images from OCIR and access OCI services"

  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.oke_pods.name} to read repos in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.oke_pods.name} to use secret-family in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.oke_pods.name} to read vaults in compartment id ${var.compartment_id}",
    "Allow dynamic-group ${oci_identity_dynamic_group.oke_pods.name} to manage objects in compartment id ${var.compartment_id}"
  ]

  freeform_tags = local.common_tags
}

resource "oci_identity_policy" "oke_lb" {
  compartment_id = var.compartment_id
  name           = "${local.name_prefix}-oke-lb-policy"
  description    = "Allows OKE cloud controller manager to manage load balancers"

  statements = [
    "Allow service oke to manage load-balancers in compartment id ${var.compartment_id}",
    "Allow service oke to use virtual-network-family in compartment id ${var.compartment_id}"
  ]

  freeform_tags = local.common_tags
}

# =============================================================================
# VAULT & SECRET – Secure DB password storage
# Maps: DBPassword (NoEcho: true) – stores the password in OCI Vault
# for auditability and rotation; injected into pods via Kubernetes Secret.
# =============================================================================

resource "oci_kms_vault" "app" {
  compartment_id = var.compartment_id
  display_name   = "${local.name_prefix}-vault"
  vault_type     = "DEFAULT"

  freeform_tags = local.common_tags
}

resource "oci_kms_key" "app" {
  compartment_id      = var.compartment_id
  display_name        = "${local.name_prefix}-master-key"
  management_endpoint = oci_kms_vault.app.management_endpoint

  key_shape {
    algorithm = "AES"
    length    = 32
  }

  freeform_tags = local.common_tags
}

resource "oci_vault_secret" "db_password" {
  compartment_id = var.compartment_id
  vault_id       = oci_kms_vault.app.id
  key_id         = oci_kms_key.app.id
  secret_name    = "${local.name_prefix}-db-password"
  description    = "Database admin password for ${local.name_prefix}"

  secret_content {
    content_type = "BASE64"
    content      = base64encode(var.db_password)
    name         = "db-password-v1"
  }

  freeform_tags = local.common_tags
}
