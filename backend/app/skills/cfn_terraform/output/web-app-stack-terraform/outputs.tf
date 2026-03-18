# =============================================================================
# Outputs – OCI 3-Tier Web Application
# =============================================================================

# --- Load Balancer ---
output "lb_public_ip" {
  description = "Public IP address of the OCI Load Balancer. Maps CFN Output: ALBEndpoint (DNS-based)."
  value       = oci_load_balancer_load_balancer.alb.ip_addresses[0].ip_address
}

output "lb_http_endpoint" {
  description = "HTTP endpoint URL of the OCI Load Balancer. Maps CFN Output: ALBEndpoint."
  value       = "http://${oci_load_balancer_load_balancer.alb.ip_addresses[0].ip_address}"
}

output "lb_https_endpoint" {
  description = "HTTPS endpoint URL (available only when ssl_certificate_name is set)."
  value       = var.ssl_certificate_name != "" ? "https://${oci_load_balancer_load_balancer.alb.ip_addresses[0].ip_address}" : "HTTPS listener not configured – set ssl_certificate_name to enable."
}

output "lb_ocid" {
  description = "OCID of the OCI Load Balancer."
  value       = oci_load_balancer_load_balancer.alb.id
}

# --- Database ---
output "db_primary_endpoint" {
  description = "Private FQDN of the PostgreSQL DB System primary endpoint. Maps CFN Output: DatabaseEndpoint. Use this as DB_HOST in application configuration."
  value       = length(oci_psql_db_system.app_db.endpoints) > 0 ? oci_psql_db_system.app_db.endpoints[0].fqdn : "pending"
}

output "db_connection_string" {
  description = "PostgreSQL JDBC connection string. Standard wire protocol – no wallet required."
  value       = length(oci_psql_db_system.app_db.endpoints) > 0 ? "jdbc:postgresql://${oci_psql_db_system.app_db.endpoints[0].fqdn}:5432/appdb" : "pending"
  sensitive   = false
}

output "db_ocid" {
  description = "OCID of the OCI PostgreSQL DB System."
  value       = oci_psql_db_system.app_db.id
}

# --- OKE Cluster ---
output "oke_cluster_id" {
  description = "OCID of the OKE cluster. Maps CFN Output: ClusterName."
  value       = oci_containerengine_cluster.app_cluster.id
}

output "oke_cluster_name" {
  description = "Display name of the OKE cluster."
  value       = oci_containerengine_cluster.app_cluster.name
}

output "oke_kubeconfig_command" {
  description = "OCI CLI command to generate a kubeconfig for the OKE cluster. Run after Phase-1 apply completes."
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.app_cluster.id} --region ${var.region} --token-version 2.0.0 --kube-endpoint PRIVATE_ENDPOINT --file ~/.kube/config"
}

# --- Kubernetes Workload ---
output "k8s_namespace" {
  description = "Kubernetes namespace where the application workload is deployed."
  value       = kubernetes_namespace.app.metadata[0].name
}

output "k8s_deployment_name" {
  description = "Kubernetes Deployment name (equivalent to ECS Service name 'app-service')."
  value       = kubernetes_deployment.app.metadata[0].name
}

output "k8s_service_name" {
  description = "Kubernetes Service name that routes traffic through the OCI Load Balancer."
  value       = kubernetes_service.app.metadata[0].name
}

output "k8s_hpa_name" {
  description = "Name of the Horizontal Pod Autoscaler (maps HighCPUAlarm-driven ECS scaling)."
  value       = kubernetes_horizontal_pod_autoscaler_v2.app.metadata[0].name
}

# --- Container Registry ---
output "ocir_repository_url" {
  description = "Full OCIR repository push/pull URL for the application image."
  value       = "${var.region}.ocir.io/${data.oci_objectstorage_namespace.ns.namespace}/${oci_artifacts_container_repository.app.display_name}"
}

# --- Secrets & Vault ---
output "db_vault_secret_id" {
  description = "OCID of the OCI Vault Secret storing the database password."
  value       = oci_vault_secret.db_password.id
  sensitive   = true
}

output "vault_id" {
  description = "OCID of the OCI KMS Vault."
  value       = oci_kms_vault.app.id
}

# --- Networking ---
output "vcn_id" {
  description = "OCID of the VCN (new or existing). Maps CFN Parameter: VpcId."
  value       = local.vcn_id
}

output "public_subnet_ids" {
  description = "OCIDs of the two public subnets used by the load balancer. Maps CFN Parameter: PublicSubnets."
  value       = [local.public_subnet_1_id, local.public_subnet_2_id]
}

output "private_app_subnet_ids" {
  description = "OCIDs of the two private application subnets used by OKE. Maps CFN Parameter: PrivateSubnets."
  value       = [local.private_app_1_id, local.private_app_2_id]
}

output "private_db_subnet_id" {
  description = "OCID of the private database subnet."
  value       = local.private_db_id
}

# --- Monitoring ---
output "ons_alert_topic_id" {
  description = "OCID of the ONS notification topic used by monitoring alarms."
  value       = oci_ons_notification_topic.alerts.id
}
