## Competitors

### External competitors
**Matilda Cloud**  
Link: [https://www.matildacloud.com/](https://www.matildacloud.com/)  
What seems strong:
- End-to-end migration flow: **assessment/discovery → planning → migrating → validating**
- Discovery is practical and infrastructure-aware:
    - EC2 / machine discovery
    - mapping AWS instances to OCI equivalents
    - identifying what cannot be migrated directly
    - AWS region vs OCI region mapping
    - service mapping
    - dependency analysis
    - CloudWatch/log-based sizing and optimization suggestions
- Also suggests a useful app-level framing: start with a **3-tier app**, group resources by tags, map them to OCI, and give a score for how closely the workload can move with minimal impact
- Supports non-1:1 recommendation logic, such as **Aurora → PostgreSQL** when direct mapping is not possible

**Microsoft Azure Migration Hub / Azure Migrate**  
Links:
- [https://learn.microsoft.com/en-us/azure/migration/?tabs=azure-web-services](https://learn.microsoft.com/en-us/azure/migration/?tabs=azure-web-services)
- [https://learn.microsoft.com/en-us/azure/migrate/tutorial-migrate-aws-virtual-machines?view=migrate](https://learn.microsoft.com/en-us/azure/migrate/tutorial-migrate-aws-virtual-machines?view=migrate)  

What stands out:
- Clear, step-based migration workflow
- Feels more structured than OCI today
- Still somewhat manual, but the flow is easy to understand
- Feedback suggests Microsoft likely pairs this with **dedicated engineering support and partner ecosystem**, not just tooling

**AWS Transform**  
Link: [https://aws.amazon.com/transform/?refid=0b08dd6b-2534-4ccc-8f52-e7cc74ceeb48](https://aws.amazon.com/transform/?refid=0b08dd6b-2534-4ccc-8f52-e7cc74ceeb48)  
What stands out:
- Explicitly called out as a **competitive product using agents**
- Positioned around **modernization**, not just migration
- Relevant benchmark because it is close to the direction you want: agentic workflow for migration/transformation

---

### OCI / internal competitor landscape

**Oracle Cloud Migrations**  
Link: [https://docs.oracle.com/en-us/iaas/Content/cloud-migration/home.htm](https://docs.oracle.com/en-us/iaas/Content/cloud-migration/home.htm)  
Current OCI offerings mentioned:
- Oracle Cloud Migrations for VMware and AWS EC2 VM migration
- Zero Downtime Migration (ZDM) for Oracle Database migration
- OCI GoldenGate for replication and cutover
- Cloud Lift / Adoption and Migration Program / partner services
- Oracle Cloud VMware Solution + HCX-based workloads

How OCI is perceived in the feedback:
- OCI has multiple migration-related tools and programs
- But they feel like **separate guides / point solutions**, not a unified migration product

---
## Gaps

### Gap in OCI today
The main feedback is that OCI does **not** yet have a **single integrated migration platform**. It has components, but they are fragmented and feel more like “guidance to do x, y, z” than one cohesive product.

### Technical gaps
Specific missing capabilities called out:
- No clear workflow to **snapshot OS disks from AWS and move them to OCI**
- No integrated checking for **OS type / compatibility**
- No obvious flow for creating a **golden image on OCI** and layering migration on top

### Product gaps vs competitors
Competitors appear stronger in:
- upfront **assessment/discovery**
- dependency analysis
- AWS-to-target mapping
- identifying unsupported resources
- utilization/log-based rightsizing
- structured migration workflow
- recommendation of substitutes when there is no direct mapping

### Delivery / GTM gap
The feedback also says migration is **not just a tech product**:
- Microsoft likely backs migration with hands-on support
- partner ecosystems matter a lot
- migrations are rarely fully self-service for enterprise customers