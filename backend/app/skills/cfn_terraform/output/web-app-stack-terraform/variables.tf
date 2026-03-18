# =============================================================================
# Variables – OCI 3-Tier Web Application
# =============================================================================

# --- OCI Provider Authentication ---
variable "tenancy_ocid" {
  description = "OCID of the OCI tenancy."
  type        = string
}

variable "user_ocid" {
  description = "OCID of the OCI user used for provider authentication."
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint of the API signing key used for provider authentication."
  type        = string
}

variable "private_key_path" {
  description = "Filesystem path to the OCI API private key PEM file."
  type        = string
  default     = "~/.oci/oci_api_key.pem"
}

variable "region" {
  description = "OCI region identifier (e.g., us-ashburn-1, eu-frankfurt-1)."
  type        = string
  default     = "us-ashburn-1"
}

variable "compartment_id" {
  description = "OCID of the compartment in which all resources will be created."
  type        = string
}

# --- Application Identity ---
variable "environment" {
  description = "Deployment environment name (e.g., production, staging). Maps CFN Parameter: Environment."
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Short project identifier used in resource display names and freeform tags."
  type        = string
  default     = "acme"
}

# --- Networking ---
# Set use_existing_vcn = true to mirror the CFN pattern where VpcId,
# PrivateSubnets, and PublicSubnets are passed as input parameters.
# Set use_existing_vcn = false (default) to provision all networking.
variable "use_existing_vcn" {
  description = "When true, reference existing VCN/subnets via OCIDs (mirrors CFN VpcId/SubnetIds parameters). When false, create all networking from scratch."
  type        = bool
  default     = false
}

variable "existing_vcn_id" {
  description = "OCID of an existing VCN. Required when use_existing_vcn = true."
  type        = string
  default     = ""
}

variable "existing_public_subnet_ids" {
  description = "List of exactly two existing public subnet OCIDs (used for the load balancer). Required when use_existing_vcn = true. Maps CFN Parameter: PublicSubnets."
  type        = list(string)
  default     = []
}

variable "existing_private_app_subnet_ids" {
  description = "List of exactly two existing private app subnet OCIDs. Required when use_existing_vcn = true. Maps CFN Parameter: PrivateSubnets (app tier)."
  type        = list(string)
  default     = []
}

variable "existing_private_db_subnet_id" {
  description = "OCID of an existing private database subnet. Required when use_existing_vcn = true. Maps CFN Parameter: PrivateSubnets (db tier)."
  type        = string
  default     = ""
}

variable "vcn_cidr" {
  description = "CIDR block for the new VCN. Used when use_existing_vcn = false."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr_1" {
  description = "CIDR block for public subnet 1 (AD-1, load balancer). Used when use_existing_vcn = false."
  type        = string
  default     = "10.0.0.0/24"
}

variable "public_subnet_cidr_2" {
  description = "CIDR block for public subnet 2 (AD-2, load balancer). Used when use_existing_vcn = false."
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_app_subnet_cidr_1" {
  description = "CIDR block for private app subnet 1 (AD-1). Used when use_existing_vcn = false."
  type        = string
  default     = "10.0.10.0/24"
}

variable "private_app_subnet_cidr_2" {
  description = "CIDR block for private app subnet 2 (AD-2). Used when use_existing_vcn = false."
  type        = string
  default     = "10.0.11.0/24"
}

variable "private_db_subnet_cidr" {
  description = "CIDR block for private database subnet. Used when use_existing_vcn = false."
  type        = string
  default     = "10.0.20.0/24"
}

# --- Database ---
variable "db_password" {
  description = "Admin password for the PostgreSQL DB System. Maps CFN Parameter: DBPassword (NoEcho: true). Minimum 12 characters; must include upper, lower, digit, and special character."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_password) >= 12
    error_message = "Database password must be at least 12 characters."
  }
}

variable "db_storage_size_gb" {
  description = "Storage size in GB for the PostgreSQL DB System. Maps CFN RDS AllocatedStorage: 50. Minimum 50 GB."
  type        = number
  default     = 50

  validation {
    condition     = var.db_storage_size_gb >= 50
    error_message = "db_storage_size_gb must be at least 50 GB."
  }
}

variable "db_backup_retention_days" {
  description = "Number of days to retain automatic database backups. Maps CFN RDS BackupRetentionPeriod: 7."
  type        = number
  default     = 7

  validation {
    condition     = var.db_backup_retention_days >= 1 && var.db_backup_retention_days <= 35
    error_message = "db_backup_retention_days must be between 1 and 35."
  }
}

# --- OKE Cluster ---
variable "kubernetes_version" {
  description = "Kubernetes version for the OKE cluster (e.g., v1.30.1). Check OCI Console for available versions in your region."
  type        = string
  default     = "v1.30.1"
}

variable "app_desired_count" {
  description = "Desired (minimum) number of application pod replicas. Maps CFN AppService.DesiredCount: 2."
  type        = number
  default     = 2

  validation {
    condition     = var.app_desired_count >= 1
    error_message = "app_desired_count must be at least 1."
  }
}

variable "app_max_count" {
  description = "Maximum number of application pod replicas for the Horizontal Pod Autoscaler."
  type        = number
  default     = 10

  validation {
    condition     = var.app_max_count >= var.app_desired_count
    error_message = "app_max_count must be >= app_desired_count."
  }
}

# --- Kubernetes Workload ---
variable "k8s_namespace" {
  description = "Kubernetes namespace in which to deploy the application workload."
  type        = string
  default     = "acme-app"
}

variable "ocir_pull_secret_name" {
  description = "Name of the Kubernetes docker-registry secret for OCIR image pulls. Pre-create with: kubectl create secret docker-registry <name> --docker-server=<region>.ocir.io --docker-username='<namespace>/<user>' --docker-password='<auth-token>' -n <k8s_namespace>"
  type        = string
  default     = "ocir-pull-secret"
}

variable "app_image_uri" {
  description = "Full OCIR image URI for the application container (e.g., us-ashburn-1.ocir.io/myns/acme-app:latest). Leave empty to auto-construct from region and namespace."
  type        = string
  default     = ""
}

# --- Load Balancer / TLS ---
variable "ssl_certificate_name" {
  description = "Name of an SSL certificate already loaded into the OCI Load Balancer Certificates service. Leave empty to skip the HTTPS listener (port 443)."
  type        = string
  default     = ""
}

# --- Monitoring & Alerting ---
variable "alert_email" {
  description = "Email address for monitoring alarm notifications via OCI ONS. Leave empty to skip the email subscription."
  type        = string
  default     = ""
}
