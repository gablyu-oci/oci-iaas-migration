# OCI Container and Kubernetes Services — IAM Permissions Reference

## Overview

OCI provides container and Kubernetes services that map to AWS EKS, ECS, ECR, and Fargate.

## Service Mapping (AWS → OCI)

| AWS Service | OCI Equivalent | Resource Type |
|---|---|---|
| EKS | Container Engine for Kubernetes (OKE) | `cluster-family` |
| ECS / Fargate | Container Instances | `container-instances` |
| ECR | Container Registry (OCIR) | `repos` |
| ECS Task Definitions | Container Images | `repos` |

## Container Engine for Kubernetes / OKE (EKS equivalent)

### Resource Types
- `cluster-family` — Group covering all OKE resources
- `clusters` — Kubernetes cluster control plane
- `nodepools` — Node pool configurations
- `workload-mappings` — Workload identity mappings

### Verbs
| Verb | Allowed Operations |
|---|---|
| `inspect` | List clusters, node pools |
| `read` | Get cluster details, get kubeconfig |
| `use` | Access cluster API, manage workloads |
| `manage` | Create, update, delete clusters and node pools |

### Example Policies
```
Allow group K8sAdmins to manage cluster-family in compartment Kubernetes
Allow group K8sDevelopers to use clusters in compartment Kubernetes
Allow group K8sDevelopers to read nodepools in compartment Kubernetes

# OKE needs access to VCN and load balancers
Allow service oke to manage virtual-network-family in compartment Kubernetes
Allow service oke to manage load-balancers in compartment Kubernetes
Allow service oke to manage block-volumes in compartment Kubernetes
```

### Accessing Cluster Resources via Workload Identity
```
Allow any-user to use cluster-family in compartment Production
  where all {request.principal.type='workload',
             request.principal.cluster_id='<cluster-ocid>',
             request.principal.namespace='<k8s-namespace>',
             request.principal.service_account='<service-account-name>'}
```

## Container Registry / OCIR (ECR equivalent)

Maps to AWS ECR.

### Resource Types
- `repos` — Container image repositories

### Verbs
| Verb | Allowed Operations |
|---|---|
| `inspect` | List repositories |
| `read` | Pull images (read-only access) |
| `use` | Pull images, view metadata |
| `manage` | Create repos, push images, delete images |

### Important Notes
- Tenancy-level repositories vs. compartment-level
- Auth tokens (not IAM keys) are used for `docker login`
- Repository paths: `<region>.ocir.io/<tenancy-namespace>/<repo-name>`

### Example Policies
```
# Allow developers to push to registry
Allow group DockerPushers to manage repos in tenancy

# Allow production compute to pull images
Allow group ProdServers to read repos in compartment Production

# Allow OKE to pull images
Allow service oke to read repos in tenancy
```

## Container Instances (ECS/Fargate equivalent)

Maps to AWS ECS Fargate.

### Resource Types
- `container-instances` — Running container workloads
- `containers` — Individual containers within an instance

### Example Policies
```
Allow group ContainerAdmins to manage container-instances in compartment Production
Allow group ContainerReadOnly to read container-instances in compartment Production
```

## AWS → OCI IAM Action Mapping

| AWS Action | OCI Equivalent Policy |
|---|---|
| `eks:CreateCluster` | `manage clusters` |
| `eks:DeleteCluster` | `manage clusters` |
| `eks:DescribeCluster` | `read clusters` |
| `eks:ListClusters` | `inspect clusters` |
| `eks:CreateNodegroup` | `manage nodepools` |
| `eks:DeleteNodegroup` | `manage nodepools` |
| `ecr:CreateRepository` | `manage repos` |
| `ecr:DeleteRepository` | `manage repos` |
| `ecr:GetAuthorizationToken` | `use repos` |
| `ecr:BatchGetImage` | `read repos` |
| `ecr:PutImage` | `manage repos` |
| `ecs:CreateCluster` | `manage container-instances` |
| `ecs:RunTask` | `manage container-instances` |
| `ecs:DescribeTasks` | `read container-instances` |

## Common Patterns

### EKS Node Group to OKE Node Pool
```
# AWS: Attach AmazonEKSWorkerNodePolicy to node IAM role
# OCI: Grant node pool service account permissions
Allow dynamic-group OKENodes to manage volume-family in compartment Production
Allow dynamic-group OKENodes to use virtual-network-family in compartment Production
Allow dynamic-group OKENodes to read repos in tenancy
```

### Dynamic Groups for OKE Workloads
```
# Define dynamic group matching OKE node instances
Any {instance.compartment.id = '<compartment-ocid>'}

# Grant permissions to that dynamic group
Allow dynamic-group OKENodeDG to manage objects in compartment Production
```
