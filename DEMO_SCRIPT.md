# OCI IaaS Migration Tool — SVP Demo Script (5 minutes)

---

## Opening — Set the Stage (30s)

> Hello everyone and thank you for viewing this demo for **OCI IaaS Migration Tool**. It is an AI-powered platform that takes a live AWS environment and produces deployable OCI infrastructure. 

The migration has three phases:
>
> - **Phase 1 — Discover & Assess**: Connect to AWS, discover resources, analyze dependencies, and generate the full migration plan — Terraform, mapping tables, runbook.
> - **Phase 2 — Migrate**: Deploy that Terraform directly to OCI.
> - **Phase 3 — Validate**: AI agents run end-to-end testing to confirm everything works.
>
> Let me show you."

---

## AWS Connection & Migration Setup (30s)

> *Connections page → Add Connection*

> "First, I connect to my AWS account with name, region, credentials. The system validates via AWS STS in real time."

> *Show validated connection card, then Dashboard → New Migration*

> "Now I create a Migration linked to that connection. I've deployed **two real CloudFormation stacks on AWS** for this demo:
>
> The first is a simple **WordPress app**. it has a single EC2 instance running and a local database
>
> The second is a **multi-tier web application in a VPC** — much more complex. Full VPC with public/private subnets across two availability zones, loadbalancers, frontend and backend fleets with Auto Scaling, bastion host, Gateway, etc.

---

## Phase 1: Discover & Assess (3 min)

### Step 1 — Discovery (30s)

> *Click "Extract All Resources"*

> "The system scans 20+ AWS service APIs — EC2, VPCs, subnets, security groups, RDS, load balancers, CloudFormation stacks, IAM, EBS, route tables — deduplicates by ARN, and stores every resource with its full config."

> *Show resource breakdown grouped by type*

> "You can see it pulling in both stacks — the WordPress instance with its security group, and the entire multi-tier VPC stack: the VPC, the four subnets, the two ALBs, the bastion host, the frontend and backend instances, the NAT Gateway, all the route tables and ACLs. Everything discovered automatically."

### Step 2 — Assessment & Resource Grouping (1 min)

> *Click "Run Assessment"*

> "Assessment collects **CloudWatch metrics** for rightsizing, queries **CloudTrail** and **VPC Flow Logs** to map dependencies, then **AI agents group resources into workloads** — by tags, shared networking, and traffic patterns. WordPress gets identified as a single self-contained workload; the multi-tier app gets grouped as one complex workload with all its components. It also runs **6R classification**, readiness scoring, and **TCO comparison**."

> *Show Assessment Detail — TCO chart, readiness scores, dependency graph*

### Step 3 — Plan Generation (1.5 min)

> *Navigate to Plan step*

> "Now the workloads are bound to the migration, and the **agent orchestrator** takes over. It looks at every resource type in each workload and routes them to the right **translation skill** — Network, Compute, Database, CFN-to-Terraform, Load Balancer, Storage, IAM. Each skill runs an **Enhancement → Review → Fix** loop with confidence scoring — not one-shot, a quality-controlled pipeline.
>
> For the multi-tier stack, the orchestrator is routing the VPC, subnets, and ACLs to **Network Translation**, the ALBs to **Load Balancer Translation**, the EC2 instances and Auto Scaling Groups to **Compute Translation**, and the full CloudFormation template to **CFN-to-Terraform**. It builds the dependency order — networking first, then compute, then load balancers."

> *Click "Generate Plan" → show results once complete*

> "Four outputs. The **AWS-to-OCI resource mapping table** — VPC maps to VCN, the public and private subnets map to OCI subnets, the ALBs map to OCI Load Balancers, Security Groups become Network Security Groups, and the EC2 `t3.small` instances become `VM.Standard.E4.Flex` shapes."

> *Show mapping table*

> "**Shape and config recommendations** — instance type to OCI Flex shape, volume tiers, database engine mappings."

> "The **Terraform files** — generated specifically for these stacks. `01-networking.tf` with the VCN, four subnets, NSGs, route tables. `02-compute.tf` with the OCI instances. `03-loadbalancer.tf` with the OCI Load Balancers and backend sets. Apply-ready."

> *Show syntax-highlighted TF*

> "And the **migration runbook** — step-by-step execution, timing estimates, rollback procedures, anomaly analysis."

---

## Phase 2: Migrate (30s)

> "Phase 2 — deploy. I connect OCI credentials, the system runs `terraform plan` for review, and after approval, `terraform apply` deploys directly into an OCI compartment. The customer opens the **OCI Console** and sees their resources live — or applies the Terraform through OCI Resource Manager. This phase is still being refined, but the core pipeline works."

---

## Phase 3: Validate (15s)

> "Phase 3 — AI agents run end-to-end validation against the deployed resources. Networking, compute, load balancing — all verified. Produces a validation report with pass/fail and any drift. This is actively being built out."

---

## Close (15s)

> "Three phases. **Discover & Assess** generates the full plan with Terraform and runbooks. **Migrate** deploys to OCI. **Validate** proves it works. What took weeks now takes minutes. That's the tool."

---

## Q&A Prep

**Q: How accurate is the Terraform?**
> "Every skill runs Enhancement → Review → Fix with confidence scoring. Below 85% gets reworked. Gaps are flagged explicitly."

**Q: What AWS services are supported?**
> "EC2, VPC, RDS/Aurora, EBS, ALB/NLB, CloudFormation, IAM, Auto Scaling, Lambda. Roadmap: S3, ECS/EKS, DynamoDB, ElastiCache, SQS/SNS."

**Q: Why these two stacks for the demo?**
> "They represent the two ends of the spectrum. WordPress is a classic single-instance lift-and-shift — simple but common. The multi-tier VPC app has real production complexity: multi-AZ, public/private subnet separation, bastion host, dual ALBs, Auto Scaling, NAT Gateway. If the tool handles both, it handles the middle too."

**Q: How does it handle complex multi-tier apps?**
> "CloudTrail and Flow Logs map real traffic patterns. The multi-tier demo has frontend, backend, bastion, and two ALBs across four subnets — the AI correctly groups them as one workload based on shared VPC, traffic, and CloudFormation tags."

**Q: How mature is Validate?**
> "Same agent infrastructure as discovery and planning — we're extending it for post-deployment checks. Goal is closed-loop: deploy, test, report."

**Q: Cost model?**
> "AI API costs — a few dollars per migration with 50–100 resources. Compared to weeks of engineering time, immediate ROI."
