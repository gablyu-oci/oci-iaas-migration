"""Central registry of agent tools + orchestrator workflow reference.

Single source of truth for:
  - What tools exist and what each one does.
  - Which agents (orchestrator / writer / reviewer) can call which tools.
  - The orchestrator's dependency-wave workflow.

This is intentionally machine-readable (dicts + lists, not free prose) so
we can surface it to:
  - The Settings page ("available tools" tab)
  - docs/agent-architecture.md (renderer below)
  - Future audit / approval UIs that need to know what the agents can do

Keep this file in sync when adding or removing a tool: register it here
first, then wire the ``@function_tool`` in ``app.agents.tools``.
"""

from __future__ import annotations

from app.agents.orchestrator import DEPENDENCY_WAVES
from app.agents.skill_group import KNOWN_AWS_TYPES, SKILL_SPECS, SKILL_TO_AWS_TYPES


# ─── Tool registry ────────────────────────────────────────────────────────────
# Every ``@function_tool`` in ``app.agents.tools`` should have a matching
# entry here. Fields:
#   description     — one-liner shown in docs + UI
#   params          — {arg_name: type_hint_str}
#   returns         — description of the return value
#   read_only       — True if the tool cannot modify external state
#   scope           — "skill" (invoked by writer/reviewer) or "orchestrator" (invoked by orchestrator agent only)
#   used_by         — ["writer", "reviewer", "orchestrator"] subsets
#   context_scoped  — True if the tool reads MigrationContext (cannot be spoofed by LLM)
#   data_sources    — which files/tables the tool reads
#   risks           — free-text notes on what could go wrong

TOOL_REGISTRY: dict[str, dict] = {
    "lookup_aws_mapping": {
        "description": "Resolve an AWS CloudFormation type to its canonical OCI target from data/mappings/resources.yaml.",
        "params": {"aws_type": "str"},
        "returns": "JSON with oci_service, oci_terraform, skill, confidence, notes, gaps",
        "read_only": True,
        "scope": "skill",
        "used_by": ["writer", "reviewer"],
        "context_scoped": False,
        "data_sources": ["backend/data/mappings/resources.yaml"],
        "risks": "None — read-only lookup against a static YAML.",
    },
    "list_resources_for_skill": {
        "description": "Enumerate every AWS type a given skill is allowed to translate.",
        "params": {"skill": "str"},
        "returns": "JSON array of {aws_type, oci_terraform} rows",
        "read_only": True,
        "scope": "skill",
        "used_by": ["writer"],
        "context_scoped": False,
        "data_sources": ["backend/data/mappings/resources.yaml"],
        "risks": "None — read-only.",
    },
    "terraform_validate": {
        "description": (
            "Run `terraform init -backend=false && terraform validate -json` on the "
            "supplied HCL inside a bubblewrap sandbox. The agent uses this to "
            "self-check correctness before returning."
        ),
        "params": {"main_tf": "str", "variables_tf": "str (optional)", "outputs_tf": "str (optional)"},
        "returns": "JSON {valid, error_count, warning_count, diagnostics[]}",
        "read_only": True,
        "scope": "skill",
        "used_by": ["writer"],
        "context_scoped": False,
        "data_sources": ["ephemeral tmpdir only"],
        "risks": (
            "Runs a subprocess. Sandboxed via `bwrap --unshare-all --cap-drop ALL "
            "--clearenv` with read-only system binds, writable tmpdir only, dies "
            "with parent. Net is shared so `terraform init` can download providers "
            "(rely on host firewall egress policy in production)."
        ),
    },
    "list_discovered_resources": {
        "description": (
            "List AWS resources already discovered for the current migration. "
            "Reads ``migration_id`` from the trusted MigrationContext — the LLM "
            "cannot target a different migration."
        ),
        "params": {"limit": "int (default 50)"},
        "returns": "JSON array of {id, aws_type, name, aws_arn}",
        "read_only": True,
        "scope": "orchestrator",
        "used_by": ["orchestrator"],
        "context_scoped": True,
        "data_sources": ["Postgres: resources table"],
        "risks": "Database read. Scoped by aws_connection_id joined from migration_id.",
    },
    "count_resources_by_type": {
        "description": (
            "Count discovered AWS resources for the current migration, grouped "
            "by ``aws_type``. Also reads ``migration_id`` from MigrationContext."
        ),
        "params": {},
        "returns": "JSON {aws_type: count}",
        "read_only": True,
        "scope": "orchestrator",
        "used_by": ["orchestrator"],
        "context_scoped": True,
        "data_sources": ["Postgres: resources table"],
        "risks": "Database read.",
    },
}


# ─── Agent role reference ─────────────────────────────────────────────────────

AGENT_ROLES: dict[str, dict] = {
    "orchestrator": {
        "description": (
            "Python-driven (not LLM-driven). Loads the discovered resource "
            "inventory, decides which skill groups are applicable, and "
            "dispatches them across ``DEPENDENCY_WAVES`` with parallel execution "
            "within each wave. Does not itself call the LLM — the LLM calls "
            "happen inside each SkillGroup."
        ),
        "model": "n/a (Python code)",
        "tools_available": [],
    },
    "writer": {
        "description": (
            "Per skill-group, runs on the user-selected writer model. Produces "
            "the initial draft and, on subsequent iterations, revises based on "
            "reviewer feedback. Calls mapping-lookup + (for HCL skills) "
            "terraform_validate tools."
        ),
        "model": "settings.LLM_WRITER_MODEL",
        "tools_available": [t for t, m in TOOL_REGISTRY.items() if "writer" in m["used_by"]],
    },
    "reviewer": {
        "description": (
            "Per skill-group, runs on the user-selected reviewer model. Scores "
            "drafts against the skill's contract and the canonical YAML + "
            "workflow prose. Returns decision + confidence + issues, never HCL."
        ),
        "model": "settings.LLM_REVIEWER_MODEL",
        "tools_available": [t for t, m in TOOL_REGISTRY.items() if "reviewer" in m["used_by"]],
    },
}


# ─── Orchestrator workflow (human + machine readable) ─────────────────────────

ORCHESTRATOR_WORKFLOW: dict = {
    "type": "dependency-wave parallel dispatch",
    "loop_policy": {
        "per_skill_loop": "writer → reviewer → (revise) → review, bounded",
        "max_iterations": "user-configurable (default 3)",
        "early_stop": "reviewer returns APPROVED/APPROVED_WITH_NOTES and confidence >= confidence_threshold (default 0.90)",
    },
    "waves": [
        {"wave": i, "skills": list(w)} for i, w in enumerate(DEPENDENCY_WAVES)
    ],
    "concurrency": "Within a wave every applicable skill runs via asyncio.gather; waves themselves are sequential.",
    # Derived from ``skill_group.SKILL_TO_AWS_TYPES`` — single source of truth.
    # Entries with ``None`` in the source mean the skill doesn't route off
    # raw AWS resources.
    "resource_routing": {
        skill: sorted(types) if types else "not resource-routed"
        for skill, types in SKILL_TO_AWS_TYPES.items()
    },
    # Every AWS CFN type some skill currently claims. Types NOT on this list
    # will be flagged as unknown (gap) when present in a migration inventory.
    "known_aws_types": sorted(KNOWN_AWS_TYPES),
}


# ─── Rendering helpers ────────────────────────────────────────────────────────

def render_registry_markdown() -> str:
    """Render the registry as a markdown block. Used by ``docs/agent-architecture.md``."""
    lines: list[str] = []
    lines.append("## Tool registry\n")
    lines.append("| Tool | Scope | Used by | Context-scoped | Read-only | Description |")
    lines.append("|---|---|---|:---:|:---:|---|")
    for name, meta in TOOL_REGISTRY.items():
        used = ", ".join(meta["used_by"])
        ctx = "✅" if meta["context_scoped"] else "—"
        ro = "✅" if meta["read_only"] else "—"
        lines.append(
            f"| `{name}` | {meta['scope']} | {used} | {ctx} | {ro} | {meta['description']} |"
        )
    lines.append("")
    lines.append("## Agent roles\n")
    for role, meta in AGENT_ROLES.items():
        lines.append(f"### {role}")
        lines.append(f"- **Model:** {meta['model']}")
        lines.append(f"- **Tools:** {', '.join(meta['tools_available']) or '_(none)_'}")
        lines.append(f"- {meta['description']}")
        lines.append("")
    lines.append("## Orchestrator workflow\n")
    lines.append(f"- **Type:** {ORCHESTRATOR_WORKFLOW['type']}")
    lines.append(f"- **Concurrency:** {ORCHESTRATOR_WORKFLOW['concurrency']}")
    lines.append("- **Loop policy:**")
    for k, v in ORCHESTRATOR_WORKFLOW["loop_policy"].items():
        lines.append(f"  - {k}: {v}")
    lines.append("")
    lines.append("### Dependency waves\n")
    lines.append("| Wave | Skills | Purpose |")
    lines.append("|---:|---|---|")
    purposes = {
        0: "IAM + Security (KMS/Vault) — no infra dependencies; consumed by later waves",
        1: "Networking foundation (VCN + subnets + NSGs + TGW/DRG + peering)",
        2: "Storage / database / data-migration (parallel once network + security exist)",
        3: "Compute (needs network + storage)",
        4: "Load balancers (need compute backends)",
        5: "Serverless + containers (Lambda/Functions, API Gateway, ECS/EKS)",
        6: "Observability + messaging (CloudWatch → Monitoring/Logging, SNS/SQS)",
        7: "Full CFN stack translation (when input is a CFN template)",
        8: "Per-workload runbooks and dependency-graph analysis",
        9: "Synthesis — compose every prior artifact",
    }
    for w in ORCHESTRATOR_WORKFLOW["waves"]:
        skills = ", ".join(f"`{s}`" for s in w["skills"])
        lines.append(f"| {w['wave']} | {skills} | {purposes.get(w['wave'], '')} |")

    lines.append("")
    lines.append("### Skill → AWS resource-type routing\n")
    lines.append(
        "Single source of truth: `SKILL_TO_AWS_TYPES` in "
        "[`skill_group.py`](../backend/app/agents/skill_group.py). "
        "Any AWS type NOT on this list shows up in "
        "`OrchestratorResult.unknown_resource_types` so the user sees "
        "exactly what didn't get translated.\n"
    )
    lines.append("| Skill | AWS types claimed |")
    lines.append("|---|---|")
    for skill, types in ORCHESTRATOR_WORKFLOW["resource_routing"].items():
        if types == "not resource-routed":
            lines.append(f"| `{skill}` | _(consumes skill outputs / assessment context)_ |")
        else:
            lines.append(f"| `{skill}` | " + ", ".join(f"`{t}`" for t in types) + " |")
    lines.append("")
    lines.append(
        f"**Known AWS types** ({len(ORCHESTRATOR_WORKFLOW['known_aws_types'])} total): "
        + ", ".join(f"`{t}`" for t in ORCHESTRATOR_WORKFLOW["known_aws_types"])
    )
    lines.append("")
    lines.append(
        "Anything else in a migration inventory (e.g., `AWS::Lambda::Function`, "
        "`AWS::DynamoDB::Table`, `AWS::SNS::Topic`) is flagged as **unknown / "
        "gap** — the run completes but those resources need manual migration "
        "or a new skill to handle them."
    )
    return "\n".join(lines)
