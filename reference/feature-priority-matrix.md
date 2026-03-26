# Feature Priority Matrix

Priority tiers:
- **P0** — Must-have for competitive parity and core value proposition. Build first.
- **P1** — High-value differentiators and major gap closers. Build next.
- **P2** — Advanced capabilities for mature deployments. Build later.

---

## Phase 1: Discovery & Assessment

| # | Feature | Impact | Effort | Competitive Position | Priority | Rationale |
|---|---------|--------|--------|---------------------|----------|-----------|
| 1.1 | Agentless Discovery (IAM Role) | High | Medium | Parity (Azure, Matilda) | **P0** | Security improvement; eliminates stored credentials risk |
| 1.2 | Performance-Based Rightsizing | High | Medium | Parity (all competitors) | **P0** | Every competitor does this; we're the only one using static config matching |
| 1.3 | Dependency Mapping (live polling) | High | High | Parity (Azure, Matilda) | **P0** | Critical for wave planning; current file-upload approach is unusable at scale |
| 1.4 | Software Inventory Discovery | Medium | Medium | Parity (Azure, Matilda) | **P1** | Enables OS compat checks and 6R classification; depends on SSM access |
| 1.5 | OS Compatibility Checking | High | Low | Parity (Azure) | **P0** | Low effort, high impact; prevents migration failures from incompatible OS |
| 1.6 | Application-Centric Grouping | High | Medium | Differentiator (Matilda does this; Azure/AWS are resource-centric) | **P1** | Transforms UX from resource list to workload view |
| 1.7 | 6R Classification | Medium | Medium | Parity (Matilda, Azure, AWS) | **P1** | AI-powered; leverages our existing Claude integration |
| 1.8 | Migration Readiness Score | Medium | Low | Parity (Azure, Matilda) | **P1** | Lightweight scoring on top of existing data; great for executive reporting |
| 1.9 | Business Case / TCO Engine | High | High | Parity (Azure, AWS) | **P1** | Sales-critical; enables ROI conversations; high effort due to pricing data |

---

## Phase 2: Planning

| # | Feature | Impact | Effort | Competitive Position | Priority | Rationale |
|---|---------|--------|--------|---------------------|----------|-----------|
| 2.1 | Wave Planning | High | Medium | Parity (AWS Transform) | **P0** | Builds on dependency mapping; critical for enterprise migrations at scale |
| 2.2 | Multi-Plan Comparison | Medium | Low | Parity (OCI Cloud Migrations) | **P1** | Low effort; reuse rightsizing engine with different parameters |
| 2.3 | Landing Zone Generation | High | High | Differentiator (Matilda, AWS) | **P1** | Major value-add; generates foundation Terraform that customers need anyway |
| 2.4 | Golden Image Recommendation | Medium | Medium | Differentiator (unique) | **P2** | No competitor does this well; medium effort but lower priority |
| 2.5 | Network Topology Translation (visual) | Medium | Medium | Enhancement (current skill exists) | **P1** | Visual diff is a UX upgrade; translation logic already exists |
| 2.6 | IaC + CI/CD Integration | Medium | Medium | Parity (Matilda) | **P2** | Nice-to-have; customers can integrate Terraform output themselves |

---

## Phase 3: Migration Execution

| # | Feature | Impact | Effort | Competitive Position | Priority | Rationale |
|---|---------|--------|--------|---------------------|----------|-----------|
| 3.1 | VM Migration Orchestration | High | High | Parity (Azure, OCI CM) | **P1** | Integrate with OCI Cloud Migrations API; closes "we only translate" gap |
| 3.2 | Database Migration Orchestration | High | High | Parity (Azure, AWS) | **P1** | Decision tree + runbook generation; don't build replication, just orchestrate |
| 3.3 | Storage Migration | Medium | Medium | Parity (Azure, AWS) | **P2** | Generate migration scripts; lower priority than compute/DB |
| 3.4 | IAM Migration Agent (deploy) | Medium | Low | Enhancement (current skill translates only) | **P1** | Upgrade existing skill to actually apply policies via Terraform |
| 3.5 | Network Migration Agent (deploy) | Medium | Low | Enhancement (current skill translates only) | **P1** | Upgrade existing skill to apply VCN/NSG via Terraform |
| 3.6 | Serverless Migration Recommendations | Low | Medium | Differentiator | **P2** | Few customers migrate serverless; guidance docs sufficient for now |
| 3.7 | Migration Progress Dashboard | High | Medium | Parity (all competitors) | **P0** | Current SSE streaming is per-job; need wave-level aggregated view |

---

## Phase 4: Validation

| # | Feature | Impact | Effort | Competitive Position | Priority | Rationale |
|---|---------|--------|--------|---------------------|----------|-----------|
| 4.1 | Test Migration | High | High | Differentiator in OCI (Azure has it) | **P1** | Risk reduction is a top enterprise concern; unique in OCI ecosystem |
| 4.2 | Post-Migration Validation Checklist | High | Medium | Parity (Azure) | **P0** | Automated health checks; closes the "no validation" gap |
| 4.3 | Rollback Plan Generation | Medium | Low | Differentiator (no competitor auto-generates) | **P1** | Low effort, high confidence boost for migration teams |
| 4.4 | Compliance Validation | Medium | Medium | Parity (Azure Defender, Matilda) | **P2** | Important but can start with manual CIS checklist |
| 4.5 | Performance Comparison | Medium | Medium | Differentiator | **P2** | Requires post-migration OCI Monitoring integration |

---

## Cross-Cutting: AI/Agent Enhancements

| # | Feature | Impact | Effort | Competitive Position | Priority | Rationale |
|---|---------|--------|--------|---------------------|----------|-----------|
| C.1 | Agentic Workflow Orchestration | High | High | Differentiator (AWS Transform is closest) | **P1** | Architectural upgrade; refactor existing 8 skills into coordinated agents |
| C.2 | Natural Language Assistant | Medium | Medium | Parity (AWS Transform chat) | **P2** | Nice-to-have; Claude integration makes this feasible |
| C.3 | Non-1:1 Mapping Recommendations | High | Medium | Differentiator | **P0** | Core to migration value prop; Aurora→PostgreSQL etc. |
| C.4 | Automated Remediation Suggestions | Medium | Medium | Differentiator | **P2** | Build after validation checks are solid |
| C.5 | Cost Optimization Agent | Low | Medium | Parity (Matilda optimize) | **P2** | Post-migration; lower priority than migration itself |

---

## Implementation Roadmap Summary

### P0 — Foundation (Build First)
| Feature | Est. Effort |
|---------|-------------|
| 1.1 Agentless Discovery (IAM Role) | 2-3 weeks |
| 1.2 Performance-Based Rightsizing | 2-3 weeks |
| 1.3 Dependency Mapping (live) | 3-4 weeks |
| 1.5 OS Compatibility Checking | 1 week |
| 2.1 Wave Planning | 2-3 weeks |
| 3.7 Migration Progress Dashboard | 2-3 weeks |
| 4.2 Post-Migration Validation Checklist | 2 weeks |
| C.3 Non-1:1 Mapping Recommendations | 2 weeks |
| **Total P0** | **~16-21 weeks** |

### P1 — Differentiation (Build Next)
| Feature | Est. Effort |
|---------|-------------|
| 1.4 Software Inventory Discovery | 2 weeks |
| 1.6 Application-Centric Grouping | 2-3 weeks |
| 1.7 6R Classification | 2 weeks |
| 1.8 Migration Readiness Score | 1 week |
| 1.9 Business Case / TCO Engine | 3-4 weeks |
| 2.2 Multi-Plan Comparison | 1 week |
| 2.3 Landing Zone Generation | 3-4 weeks |
| 2.5 Network Topology Translation (visual) | 2 weeks |
| 3.1 VM Migration Orchestration | 3-4 weeks |
| 3.2 Database Migration Orchestration | 3-4 weeks |
| 3.4 IAM Migration Agent (deploy) | 1 week |
| 3.5 Network Migration Agent (deploy) | 1 week |
| 4.1 Test Migration | 3-4 weeks |
| 4.3 Rollback Plan Generation | 1 week |
| C.1 Agentic Workflow Orchestration | 4-6 weeks |
| **Total P1** | **~32-43 weeks** |

### P2 — Advanced (Build Later)
| Feature | Est. Effort |
|---------|-------------|
| 2.4 Golden Image Recommendation | 2 weeks |
| 2.6 IaC + CI/CD Integration | 2-3 weeks |
| 3.3 Storage Migration | 2 weeks |
| 3.6 Serverless Migration Recommendations | 2 weeks |
| 4.4 Compliance Validation | 2-3 weeks |
| 4.5 Performance Comparison | 2-3 weeks |
| C.2 Natural Language Assistant | 3-4 weeks |
| C.4 Automated Remediation Suggestions | 2-3 weeks |
| C.5 Cost Optimization Agent | 2-3 weeks |
| **Total P2** | **~19-27 weeks** |

---

## Quick Reference: What Closes Which Gap

| Gap (from competitors-and-gaps.md) | Features that close it |
|---|---|
| No single integrated migration platform | All phases unified in one product |
| No workflow to snapshot OS disks and move to OCI | 3.1 VM Migration Orchestration |
| No integrated OS type/compatibility checking | 1.5 OS Compatibility Checking |
| No golden image flow | 2.4 Golden Image Recommendation |
| Weak upfront assessment/discovery | 1.1-1.9 (entire Phase 1) |
| No dependency analysis | 1.3 Dependency Mapping |
| No AWS-to-target mapping | Already exists; enhanced by C.3 |
| No identification of unsupported resources | 1.5 + C.3 Non-1:1 Mapping |
| No utilization/log-based rightsizing | 1.2 Performance-Based Rightsizing |
| No structured migration workflow | 2.1 Wave Planning + 3.7 Dashboard |
| No recommendation of substitutes | C.3 Non-1:1 Mapping Recommendations |
| Migration is not just tech — needs support/partners | Out of scope (GTM/delivery) |
