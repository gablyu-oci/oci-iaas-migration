"""Migration Executor — runs terraform init/plan/apply for a workload.

Executes in a child process. Writes progress to the migrations table
so the frontend can poll status.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import traceback
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path("/tmp/oci-migrations")


def _sync_database_url() -> str:
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def _update_migrate_status(
    session, migration_id: str, *,
    status: str | None = None,
    step: str | None = None,
    log_line: str | None = None,
    terraform_plan: str | None = None,
    terraform_state: dict | None = None,
    started_at: bool = False,
) -> None:
    """Update migration execution progress using raw SQL."""
    row = session.execute(
        text("SELECT migrate_logs FROM migrations WHERE id = :id"),
        {"id": migration_id},
    ).fetchone()
    logs = (row[0] if row and row[0] else []) if row else []

    sets = []
    params: dict = {"id": migration_id}

    if status:
        sets.append("migrate_status = :status")
        params["status"] = status
    if step:
        sets.append("migrate_current_step = :step")
        params["step"] = step
    if log_line:
        logs.append(f"[{time.strftime('%H:%M:%S')}] {log_line}")
        logs = logs[-100:]
        sets.append("migrate_logs = :logs")
        params["logs"] = json.dumps(logs)
    if terraform_plan is not None:
        sets.append("migrate_terraform_plan = :tfplan")
        params["tfplan"] = terraform_plan
    if terraform_state is not None:
        sets.append("migrate_terraform_state = :tfstate")
        params["tfstate"] = json.dumps(terraform_state)
    if started_at:
        sets.append("migrate_started_at = NOW()")

    if sets:
        session.execute(
            text(f"UPDATE migrations SET {', '.join(sets)} WHERE id = :id"),
            params,
        )
        session.commit()


def execute_migration(
    migration_id: str,
    workload_name: str,
    oci_connection_id: str,
    variable_overrides: dict | None = None,
) -> None:
    """Main entry point — runs in a child process."""
    import os
    os.setpgrp()
    os.environ.pop("CLAUDECODE", None)  # Allow Agent SDK nested sessions

    logging.basicConfig(level=logging.INFO)

    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        _run_execution(session, migration_id, workload_name, oci_connection_id, variable_overrides or {})
    except Exception as exc:
        logger.error("Migration execution failed: %s\n%s", exc, traceback.format_exc())
        _update_migrate_status(session, migration_id, status="failed",
                               log_line=f"FATAL: {exc}")
    finally:
        session.close()


def _run_execution(
    session, migration_id: str, workload_name: str,
    oci_connection_id: str, variable_overrides: dict,
) -> None:
    from app.db.models import OCIConnection, Assessment
    from sqlalchemy import select

    _update_migrate_status(session, migration_id, status="running",
                           step="preflight", started_at=True,
                           log_line="Starting migration execution")

    # Load OCI connection
    oci_conn = session.execute(
        select(OCIConnection).where(OCIConnection.id == UUID(oci_connection_id))
    ).scalar_one_or_none()
    if not oci_conn:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line="OCI connection not found")
        return

    # Load plan artifacts
    assessment = session.execute(
        text("SELECT dependency_artifacts FROM assessments WHERE migration_id = :mid ORDER BY created_at DESC LIMIT 1"),
        {"mid": migration_id},
    ).fetchone()
    if not assessment or not assessment[0]:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line="No plan artifacts found")
        return

    arts = assessment[0]
    wp = arts.get("workload_plans", {}).get(workload_name, {})
    if wp.get("status") != "completed":
        _update_migrate_status(session, migration_id, status="failed",
                               log_line=f"Plan for '{workload_name}' is not completed")
        return

    plan_artifacts = wp.get("artifacts", {})
    _update_migrate_status(session, migration_id,
                           log_line=f"Found {len(plan_artifacts)} plan artifacts")

    # ── Step 1: Create workspace ──────────────────────────────────────
    _update_migrate_status(session, migration_id, step="workspace",
                           log_line="Creating Terraform workspace")

    workspace = WORKSPACE_ROOT / migration_id / workload_name.replace(" ", "_")
    workspace.mkdir(parents=True, exist_ok=True)

    # Write .tf files — use synthesis if available, otherwise individual skill files
    # Never mix both (causes duplicate provider/resource declarations)
    has_synthesis = any(k.startswith("synthesis/") and k.endswith(".tf") for k in plan_artifacts)
    tf_count = 0

    # Clean workspace of any previous .tf files
    for f in workspace.glob("*.tf"):
        f.unlink()

    for key, content in plan_artifacts.items():
        if not isinstance(content, str) or not key.endswith(".tf"):
            continue
        if has_synthesis and not key.startswith("synthesis/"):
            continue  # Skip individual skill files when synthesis exists
        fname = key.split("/")[-1]
        # Fix common LLM output issues in HCL
        # 1. Invalid escape sequences: \. should be \\. in HCL regex strings
        import re
        content = re.sub(r'(?<!\\)\\\.', r'\\\\.', content)
        (workspace / fname).write_text(content)
        tf_count += 1

    _update_migrate_status(session, migration_id,
                           log_line=f"Wrote {tf_count} Terraform files to workspace")

    # Write terraform.tfvars with OCI credentials
    tfvars_lines = [
        f'tenancy_ocid     = "{oci_conn.tenancy_ocid}"',
        f'user_ocid        = "{oci_conn.user_ocid}"',
        f'fingerprint      = "{oci_conn.fingerprint}"',
        f'region           = "{oci_conn.region}"',
    ]
    if oci_conn.compartment_id:
        tfvars_lines.append(f'compartment_id   = "{oci_conn.compartment_id}"')

    # Write private key to file
    key_path = workspace / "oci_api_key.pem"
    key_path.write_text(oci_conn.private_key)
    key_path.chmod(0o600)
    tfvars_lines.append(f'private_key_path = "{key_path}"')

    # Apply variable overrides
    for k, v in variable_overrides.items():
        if isinstance(v, str):
            tfvars_lines.append(f'{k} = "{v}"')
        else:
            tfvars_lines.append(f'{k} = {json.dumps(v)}')

    (workspace / "terraform.tfvars").write_text("\n".join(tfvars_lines))

    # Ensure provider block exists
    _ensure_provider_block(workspace, oci_conn)
    _fill_missing_tfvars(workspace)

    # ── Step 2: terraform init ────────────────────────────────────────
    _update_migrate_status(session, migration_id, step="init",
                           log_line="Running terraform init")

    init_result = subprocess.run(
        ["terraform", "init", "-no-color", "-input=false"],
        cwd=str(workspace), capture_output=True, text=True, timeout=300,
    )
    _update_migrate_status(session, migration_id,
                           log_line=f"terraform init exit code: {init_result.returncode}")
    if init_result.returncode != 0:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line=f"terraform init failed:\n{init_result.stderr[:2000]}")
        return

    # ── Step 3: terraform plan ────────────────────────────────────────
    _update_migrate_status(session, migration_id, step="plan",
                           log_line="Running terraform plan")

    plan_result = subprocess.run(
        ["terraform", "plan", "-no-color", "-input=false", "-out=plan.out"],
        cwd=str(workspace), capture_output=True, text=True, timeout=600,
    )

    plan_output = plan_result.stdout + ("\n" + plan_result.stderr if plan_result.stderr else "")
    _update_migrate_status(session, migration_id,
                           terraform_plan=plan_output,
                           log_line=f"terraform plan exit code: {plan_result.returncode}")

    if plan_result.returncode != 0:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line=f"terraform plan failed:\n{plan_result.stderr[:2000]}")
        return

    # ── Step 4: Wait for approval ─────────────────────────────────────
    _update_migrate_status(session, migration_id, status="review", step="review",
                           log_line="Terraform plan ready — waiting for user approval")

    # Poll for approval (check migrate_status changes from 'review' to 'approved')
    deadline = time.time() + 3600  # 1 hour timeout
    while time.time() < deadline:
        row = session.execute(
            text("SELECT migrate_status FROM migrations WHERE id = :id"),
            {"id": migration_id},
        ).fetchone()
        current_status = row[0] if row else None

        if current_status == "approved":
            _update_migrate_status(session, migration_id,
                                   log_line="User approved — proceeding with apply")
            break
        elif current_status == "rejected":
            _update_migrate_status(session, migration_id, status="rejected",
                                   log_line="User rejected the plan")
            return
        elif current_status not in ("review",):
            # Status changed externally (cancelled, etc.)
            return

        time.sleep(5)
    else:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line="Approval timed out after 1 hour")
        return

    # ── Step 5: terraform apply ───────────────────────────────────────
    _update_migrate_status(session, migration_id, status="applying", step="apply",
                           log_line="Running terraform apply")

    apply_result = subprocess.run(
        ["terraform", "apply", "-no-color", "-input=false", "plan.out"],
        cwd=str(workspace), capture_output=True, text=True, timeout=1800,
    )

    _update_migrate_status(session, migration_id,
                           log_line=f"terraform apply exit code: {apply_result.returncode}")

    # Capture terraform apply output in logs
    for line in apply_result.stdout.split("\n")[-20:]:
        if line.strip():
            _update_migrate_status(session, migration_id, log_line=line.strip())

    if apply_result.returncode != 0:
        _update_migrate_status(session, migration_id, status="failed",
                               log_line=f"terraform apply failed:\n{apply_result.stderr[:2000]}")
        # Still try to save state
        _save_terraform_state(session, migration_id, workspace)
        return

    # ── Step 6: Save state + complete ─────────────────────────────────
    _save_terraform_state(session, migration_id, workspace)

    _update_migrate_status(session, migration_id, status="completed", step="complete",
                           log_line="Migration completed successfully")
    logger.info("Migration execution completed for %s", workload_name)


_PROVIDER_CREDENTIAL_VARS = {"tenancy_ocid", "user_ocid", "fingerprint", "private_key_path", "region"}

_FULL_PROVIDER_BLOCK = '''provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}'''


def _ensure_provider_block(workspace: Path, oci_conn) -> None:
    """Ensure a complete OCI provider configuration exists in the workspace.

    The synthesis LLM sometimes produces incomplete provider blocks (e.g.
    missing user_ocid, fingerprint, private_key_path).  This function:
    1. Replaces any incomplete provider "oci" block with the full one.
    2. Adds required_providers if absent.
    3. Adds variable declarations for credential vars that are referenced
       but not yet declared.
    """
    import re

    has_required_providers = False
    provider_file: Path | None = None        # file that contains the provider block
    provider_block_complete = False
    declared_vars: set[str] = set()
    referenced_vars: set[str] = set()

    for tf_file in workspace.glob("*.tf"):
        content = tf_file.read_text()
        if "required_providers" in content:
            has_required_providers = True
        if re.search(r'provider\s+"oci"', content):
            provider_file = tf_file
            # Check if the existing block has all required fields
            provider_block_complete = all(
                f"var.{v}" in content for v in _PROVIDER_CREDENTIAL_VARS
            )
        declared_vars.update(m.group(1) for m in re.finditer(r'variable\s+"(\w+)"', content))
        referenced_vars.update(re.findall(r'var\.(\w+)', content))

    # ── Fix incomplete provider block in-place ──────────────────────────
    if provider_file and not provider_block_complete:
        content = provider_file.read_text()
        # Replace the existing provider "oci" { ... } block with the full version
        patched = re.sub(
            r'provider\s+"oci"\s*\{[^}]*\}',
            _FULL_PROVIDER_BLOCK,
            content,
        )
        provider_file.write_text(patched)
        logger.info("Patched incomplete provider block in %s", provider_file.name)
        # Re-scan the patched file for references
        referenced_vars.update(re.findall(r'var\.(\w+)', patched))

    # ── Write provider.tf only for pieces that are completely absent ────
    parts: list[str] = []

    if not has_required_providers:
        parts.append('''terraform {
  required_providers {
    oci = {
      source = "oracle/oci"
    }
  }
}''')

    if not provider_file:
        parts.append(_FULL_PROVIDER_BLOCK)
        referenced_vars.update(_PROVIDER_CREDENTIAL_VARS)

    # Declare credential variables that are referenced but not yet declared
    missing_vars = sorted((_PROVIDER_CREDENTIAL_VARS & referenced_vars) - declared_vars)
    for var_name in missing_vars:
        parts.append(f'variable "{var_name}" {{}}')

    if parts:
        (workspace / "provider.tf").write_text("\n\n".join(parts) + "\n")
        logger.info("Wrote provider.tf with: %s", ", ".join(
            (["required_providers"] if not has_required_providers else [])
            + (["provider block"] if not provider_file else [])
            + ([f"variables: {missing_vars}"] if missing_vars else [])
        ))
    else:
        logger.info("All provider configuration already present, skipping provider.tf")


def _save_terraform_state(session, migration_id: str, workspace: Path) -> None:
    """Read and store terraform.tfstate from workspace."""
    state_path = workspace / "terraform.tfstate"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            _update_migrate_status(session, migration_id, terraform_state=state,
                                   log_line="Terraform state saved")
        except Exception as exc:
            _update_migrate_status(session, migration_id,
                                   log_line=f"Failed to save terraform state: {exc}")


def _run_oci_preflight(session, migration_id: str, oci_conn) -> None:
    """Run pre-flight checks using OCI SDK to validate auth and permissions.

    Results are logged as warnings, not blockers — terraform plan catches specifics.
    """
    _update_migrate_status(session, migration_id, step="preflight",
                           log_line="Running OCI pre-flight checks…")
    try:
        import oci
        import tempfile

        # Write private key to temp file for OCI SDK
        key_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
        key_file.write(oci_conn.private_key)
        key_file.close()

        config = {
            "user": oci_conn.user_ocid,
            "key_file": key_file.name,
            "fingerprint": oci_conn.fingerprint,
            "tenancy": oci_conn.tenancy_ocid,
            "region": oci_conn.region,
        }

        # Auth check — verify API key works
        try:
            identity = oci.identity.IdentityClient(config)
            identity.get_tenancy(oci_conn.tenancy_ocid)
            _update_migrate_status(session, migration_id,
                                   log_line="Pre-flight: Auth OK")
        except Exception as exc:
            _update_migrate_status(session, migration_id,
                                   log_line=f"Pre-flight: Auth FAILED — {exc}")
            return  # No point checking further

        # Compartment check
        if oci_conn.compartment_id:
            try:
                identity.get_compartment(oci_conn.compartment_id)
                _update_migrate_status(session, migration_id,
                                       log_line="Pre-flight: Compartment OK")
            except Exception:
                _update_migrate_status(session, migration_id,
                                       log_line=f"Pre-flight: WARN — compartment {oci_conn.compartment_id} not accessible")

        # Permission probes — quick list calls to check key permissions
        compartment = oci_conn.compartment_id or oci_conn.tenancy_ocid
        checks = [
            ("VCN", lambda: oci.core.VirtualNetworkClient(config).list_vcns(compartment, limit=1)),
            ("Compute", lambda: oci.core.ComputeClient(config).list_instances(compartment, limit=1)),
        ]
        for label, probe_fn in checks:
            try:
                probe_fn()
                _update_migrate_status(session, migration_id,
                                       log_line=f"Pre-flight: {label} permissions OK")
            except oci.exceptions.ServiceError as e:
                if e.status == 404:
                    _update_migrate_status(session, migration_id,
                                           log_line=f"Pre-flight: {label} permissions OK (empty)")
                else:
                    _update_migrate_status(session, migration_id,
                                           log_line=f"Pre-flight: WARN — {label} access denied ({e.code})")
            except Exception:
                pass

        # Cleanup temp key
        os.unlink(key_file.name)

    except ImportError:
        _update_migrate_status(session, migration_id,
                               log_line="Pre-flight: skipped (OCI SDK not installed)")
    except Exception as exc:
        _update_migrate_status(session, migration_id,
                               log_line=f"Pre-flight: error — {exc}")


def _fill_missing_tfvars(workspace: Path) -> None:
    """Scan .tf files for required variables without defaults and add placeholders
    to terraform.tfvars so that `terraform plan` doesn't fail on missing inputs.

    Uses type-aware placeholders (e.g. number → 0, bool → false, string → "placeholder").
    """
    import re

    # Parse existing tfvars to know what's already set
    tfvars_path = workspace / "terraform.tfvars"
    existing_vars: set[str] = set()
    if tfvars_path.exists():
        for line in tfvars_path.read_text().splitlines():
            m = re.match(r'(\w+)\s*=', line)
            if m:
                existing_vars.add(m.group(1))

    # Find all variable declarations across .tf files
    # A variable is "required" if it has no `default` attribute in its block
    missing: list[tuple[str, str]] = []  # (name, type)
    for tf_file in workspace.glob("*.tf"):
        content = tf_file.read_text()
        # Match variable blocks: variable "name" { ... }
        for m in re.finditer(r'variable\s+"(\w+)"\s*\{([^}]*)\}', content, re.DOTALL):
            var_name = m.group(1)
            var_body = m.group(2)
            if var_name in existing_vars:
                continue
            if re.search(r'\bdefault\s*=', var_body):
                continue
            # Extract type if present
            type_match = re.search(r'\btype\s*=\s*(\w+)', var_body)
            var_type = type_match.group(1) if type_match else "string"
            missing.append((var_name, var_type))

    if not missing:
        return

    # Append placeholder values
    placeholder_lines = ["\n# Auto-generated placeholders for terraform plan test"]
    for var_name, var_type in missing:
        if var_type == "number":
            placeholder_lines.append(f'{var_name} = 0')
        elif var_type == "bool":
            placeholder_lines.append(f'{var_name} = false')
        elif var_type == "list":
            placeholder_lines.append(f'{var_name} = []')
        elif var_type == "map":
            placeholder_lines.append(f'{var_name} = {{}}')
        elif "password" in var_name or "secret" in var_name:
            placeholder_lines.append(f'{var_name} = "Placeholder1234"')
        elif "ssh" in var_name and "key" in var_name:
            placeholder_lines.append(f'{var_name} = "ssh-rsa AAAA-placeholder"')
        else:
            placeholder_lines.append(f'{var_name} = "placeholder"')

    with open(tfvars_path, "a") as f:
        f.write("\n".join(placeholder_lines) + "\n")

    logger.info("Added %d placeholder tfvars: %s", len(missing),
                [n for n, _ in missing])


_TF_FIX_SYSTEM = """\
You are an OCI Terraform expert. You are given a set of Terraform .tf files that \
failed during `terraform init` or `terraform plan`. Fix ALL errors reported below.

RULES:
- Return a JSON object where each key is a filename (e.g. "01-networking.tf", \
"variables.tf") and the value is the COMPLETE corrected file content.
- Include ALL files (even unchanged ones) so the full workspace can be rebuilt.
- You MUST preserve all resource definitions. Only fix HCL syntax, provider \
attribute names, and variable declarations.
- Do NOT remove, rename, or restructure any `resource` blocks. The migration \
intent must be preserved exactly.
- Ensure no duplicate provider, required_providers, or variable declarations.
- Ensure all referenced variables are declared.
- Ensure all resource attributes are valid for the OCI Terraform provider.
- Do NOT include terraform.tfvars or .pem files — only .tf files.
"""

def test_plan(
    migration_id: str,
    workload_name: str,
    oci_connection_id: str,
    variable_overrides: dict | None = None,
) -> None:
    """Run terraform init + plan only (no apply). Single pass — reports pass/fail."""
    import os
    os.setpgrp()
    os.environ.pop("CLAUDECODE", None)
    logging.basicConfig(level=logging.INFO)

    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        from app.db.models import OCIConnection, Assessment
        from sqlalchemy import select as _select

        _update_migrate_status(session, migration_id, status="testing", step="init",
                               log_line="Starting terraform test (init + plan only)")

        # Load OCI connection
        oci_conn = session.execute(
            _select(OCIConnection).where(OCIConnection.id == UUID(oci_connection_id))
        ).scalar_one_or_none()
        if not oci_conn:
            _update_migrate_status(session, migration_id, status="test_failed",
                                   log_line="OCI connection not found")
            return

        # Load plan artifacts from DB (may include LLM-fixed versions)
        assessment = session.execute(
            text("SELECT dependency_artifacts FROM assessments WHERE migration_id = :mid ORDER BY created_at DESC LIMIT 1"),
            {"mid": migration_id},
        ).fetchone()
        if not assessment or not assessment[0]:
            _update_migrate_status(session, migration_id, status="test_failed",
                                   log_line="No plan artifacts found")
            return

        arts = assessment[0]
        wp = arts.get("workload_plans", {}).get(workload_name, {})
        plan_artifacts = wp.get("artifacts", {})

        # Create workspace
        workspace = WORKSPACE_ROOT / migration_id / workload_name.replace(" ", "_")
        workspace.mkdir(parents=True, exist_ok=True)

        # Clean old .tf files and terraform state
        for f in workspace.glob("*.tf"):
            f.unlink()
        tf_dir = workspace / ".terraform"
        if tf_dir.exists():
            shutil.rmtree(tf_dir)
        lock_file = workspace / ".terraform.lock.hcl"
        if lock_file.exists():
            lock_file.unlink()

        # Write .tf files (synthesis only if available)
        has_synthesis = any(k.startswith("synthesis/") and k.endswith(".tf") for k in plan_artifacts)
        import re
        for key, content in plan_artifacts.items():
            if not isinstance(content, str) or not key.endswith(".tf"):
                continue
            if has_synthesis and not key.startswith("synthesis/"):
                continue
            fname = key.split("/")[-1]
            content = re.sub(r'(?<!\\)\\\.', r'\\\\.', content)
            (workspace / fname).write_text(content)

        # Write tfvars
        tfvars_lines = [
            f'tenancy_ocid     = "{oci_conn.tenancy_ocid}"',
            f'user_ocid        = "{oci_conn.user_ocid}"',
            f'fingerprint      = "{oci_conn.fingerprint}"',
            f'region           = "{oci_conn.region}"',
        ]
        if oci_conn.compartment_id:
            tfvars_lines.append(f'compartment_id   = "{oci_conn.compartment_id}"')
        key_path = workspace / "oci_api_key.pem"
        key_path.write_text(oci_conn.private_key)
        key_path.chmod(0o600)
        tfvars_lines.append(f'private_key_path = "{key_path}"')
        for k, v in (variable_overrides or {}).items():
            if isinstance(v, str):
                tfvars_lines.append(f'{k} = "{v}"')
        (workspace / "terraform.tfvars").write_text("\n".join(tfvars_lines))

        _ensure_provider_block(workspace, oci_conn)
        _fill_missing_tfvars(workspace)

        # ── Pre-flight OCI checks ────────────────────────────────────
        _run_oci_preflight(session, migration_id, oci_conn)

        # terraform init
        _update_migrate_status(session, migration_id, step="init",
                               log_line="Running terraform init…")
        init_result = subprocess.run(
            ["terraform", "init", "-no-color", "-input=false"],
            cwd=str(workspace), capture_output=True, text=True, timeout=300,
        )
        _update_migrate_status(session, migration_id,
                               log_line=f"terraform init exit code: {init_result.returncode}")
        if init_result.returncode != 0:
            _update_migrate_status(session, migration_id, status="test_failed", step="init",
                                   log_line=f"terraform init FAILED:\n{init_result.stderr[:3000]}")
            return

        _update_migrate_status(session, migration_id, log_line="terraform init OK")

        # terraform plan
        _update_migrate_status(session, migration_id, step="plan",
                               log_line="Running terraform plan…")
        plan_result = subprocess.run(
            ["terraform", "plan", "-no-color", "-input=false"],
            cwd=str(workspace), capture_output=True, text=True, timeout=600,
        )
        plan_output = plan_result.stdout + ("\n" + plan_result.stderr if plan_result.stderr else "")
        _update_migrate_status(session, migration_id, terraform_plan=plan_output,
                               log_line=f"terraform plan exit code: {plan_result.returncode}")

        if plan_result.returncode != 0:
            _update_migrate_status(session, migration_id, status="test_failed", step="plan",
                                   log_line=f"terraform plan FAILED:\n{plan_result.stderr[:3000]}")
            return

        # Success
        add_count = plan_output.count(" will be created")
        change_count = plan_output.count(" will be updated")
        _update_migrate_status(session, migration_id, status="test_passed", step="plan",
                               log_line=f"Test PASSED — Plan: {add_count} to add, {change_count} to change")

    except Exception as exc:
        _update_migrate_status(session, migration_id, status="test_failed",
                               log_line=f"Test failed: {exc}")
    finally:
        session.close()


# ── LLM-driven terraform fix (called from API, not from test_plan) ──────────

def _extract_resources(tf_content: str) -> set[str]:
    """Extract resource declarations from HCL content. Returns set of 'type.name' strings."""
    import re
    return set(re.findall(r'resource\s+"(\w+)"\s+"(\w+)"', tf_content))


def fix_terraform(migration_id: str, workload_name: str) -> None:
    """Read failing terraform logs, send to LLM to fix .tf files, persist results.

    Triggered by user clicking "Fix .tf" after a test failure. Runs in a child
    process. Sets migrate_status to 'fixing' while running, then back to
    'test_failed' (with fixed artifacts) so the user can re-test.

    Includes:
    - Versioned snapshots (synthesis_v{N}/) for rollback/diff
    - Semantic drift guard (warns if resources removed)
    - Fix history tracking
    """
    import os, re
    from datetime import datetime, timezone
    os.setpgrp()
    os.environ.pop("CLAUDECODE", None)
    logging.basicConfig(level=logging.INFO)

    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        _update_migrate_status(session, migration_id, status="fixing", step="llm_fix",
                               log_line="Starting LLM-driven .tf fix…")

        # Get the terraform error logs from the migration record
        row = session.execute(
            text("SELECT migrate_logs, migrate_terraform_plan, migrate_current_step "
                 "FROM migrations WHERE id = :id"),
            {"id": migration_id},
        ).fetchone()
        if not row:
            _update_migrate_status(session, migration_id, status="test_failed",
                                   log_line="Migration not found")
            return

        logs = row[0] or []
        tf_plan_output = row[1] or ""
        failed_step = row[2] or "init"

        # Extract error text from logs
        error_lines = [l for l in logs if "FAILED" in l or "Error" in l]
        error_text = "\n".join(error_lines[-5:])
        if tf_plan_output and "Error" in tf_plan_output:
            error_text += "\n\n" + tf_plan_output[:3000]
        if not error_text.strip():
            error_text = "\n".join(logs[-10:])

        # Load current .tf files from DB artifacts
        assessment = session.execute(
            text("SELECT dependency_artifacts FROM assessments WHERE migration_id = :mid ORDER BY created_at DESC LIMIT 1"),
            {"mid": migration_id},
        ).fetchone()
        if not assessment or not assessment[0]:
            _update_migrate_status(session, migration_id, status="test_failed",
                                   log_line="No plan artifacts found for fix")
            return

        arts = assessment[0]
        wp = arts.get("workload_plans", {}).get(workload_name, {})
        plan_artifacts = wp.get("artifacts", {})

        # Collect the .tf files
        has_synthesis = any(k.startswith("synthesis/") and k.endswith(".tf") for k in plan_artifacts)
        tf_files: dict[str, str] = {}
        for key, content in plan_artifacts.items():
            if not isinstance(content, str) or not key.endswith(".tf"):
                continue
            if has_synthesis and not key.startswith("synthesis/"):
                continue
            fname = key.split("/")[-1]
            tf_files[fname] = content

        if not tf_files:
            _update_migrate_status(session, migration_id, status="test_failed",
                                   log_line="No .tf files found in artifacts")
            return

        # ── Snapshot current .tf files before fix (versioned backup) ──
        fix_count = wp.get("fix_count", 0) + 1
        version_prefix = f"synthesis_v{fix_count}/" if has_synthesis else f"v{fix_count}/"
        for key, content in list(plan_artifacts.items()):
            if not isinstance(content, str) or not key.endswith(".tf"):
                continue
            if has_synthesis and not key.startswith("synthesis/"):
                continue
            # e.g. synthesis/01-networking.tf → synthesis_v1/01-networking.tf
            backup_key = key.replace("synthesis/", version_prefix) if has_synthesis else f"{version_prefix}{key}"
            plan_artifacts[backup_key] = content

        # Collect original resources for drift detection
        original_resources: set[tuple[str, str]] = set()
        for content in tf_files.values():
            original_resources.update(_extract_resources(content))

        _update_migrate_status(session, migration_id,
                               log_line=f"Sending {len(tf_files)} .tf files + error to LLM (fix #{fix_count})…")

        # Call LLM
        from app.gateway.model_gateway import get_anthropic_client
        client = get_anthropic_client()

        user_prompt = (
            f"## Terraform {failed_step} error\n"
            f"```\n{error_text[:4000]}\n```\n\n"
            f"## Current .tf files\n\n"
        )
        for fname, content in sorted(tf_files.items()):
            user_prompt += f"### {fname}\n```hcl\n{content}\n```\n\n"
        user_prompt += (
            "Fix ALL errors above. Return a JSON object mapping filename → corrected content "
            "for EVERY .tf file (include unchanged files too)."
        )

        from app.gateway.model_gateway import get_model
        resp = client.messages.create(
            model=get_model("migration_execution", "generate"),
            max_tokens=32768,
            system=[{"type": "text", "text": _TF_FIX_SYSTEM}],
            messages=[
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": "{"},
            ],
        )

        raw = "{" + (resp.content[0].text if resp.content else "")
        start, end = raw.find("{"), raw.rfind("}") + 1
        candidate = raw[start:end] if (start != -1 and end > start) else raw
        try:
            fixed_files = json.loads(candidate)
        except json.JSONDecodeError:
            try:
                fixed_files = json.loads(candidate, strict=False)
            except json.JSONDecodeError:
                from json_repair import repair_json
                fixed_files = repair_json(candidate, return_objects=True)

        if not isinstance(fixed_files, dict) or not fixed_files:
            _update_migrate_status(session, migration_id, status="test_failed",
                                   log_line="LLM returned invalid response — fix failed")
            return

        # ── Semantic drift guard ─────────────────────────────────────
        fixed_resources: set[tuple[str, str]] = set()
        for content in fixed_files.values():
            if isinstance(content, str):
                fixed_resources.update(_extract_resources(content))

        removed = original_resources - fixed_resources
        added = fixed_resources - original_resources
        files_changed = []

        if removed:
            removed_str = ", ".join(f"{t}.{n}" for t, n in sorted(removed))
            _update_migrate_status(session, migration_id,
                                   log_line=f"WARNING: Fix removed resources: {removed_str}")

        if added:
            added_str = ", ".join(f"{t}.{n}" for t, n in sorted(added))
            _update_migrate_status(session, migration_id,
                                   log_line=f"INFO: Fix added resources: {added_str}")

        # Persist fixed .tf files back to assessment artifacts
        wrote = 0
        for fname, content in fixed_files.items():
            if not isinstance(content, str) or not fname.endswith(".tf"):
                continue
            fname = fname.split("/")[-1]
            content = re.sub(r'(?<!\\)\\\.', r'\\\\.', content)
            key = f"synthesis/{fname}" if has_synthesis else fname
            if plan_artifacts.get(key) != content:
                files_changed.append(fname)
            plan_artifacts[key] = content
            wrote += 1

        # ── Update fix history ───────────────────────────────────────
        fix_history = wp.get("fix_history", [])
        fix_history.append({
            "fixed_at": datetime.now(timezone.utc).isoformat(),
            "fix_number": fix_count,
            "error_summary": error_text[:500],
            "files_changed": files_changed,
            "resources_removed": [f"{t}.{n}" for t, n in sorted(removed)],
            "resources_added": [f"{t}.{n}" for t, n in sorted(added)],
        })
        wp["fix_count"] = fix_count
        wp["fix_history"] = fix_history
        wp["artifacts"] = plan_artifacts
        arts.setdefault("workload_plans", {})[workload_name] = wp

        session.execute(
            text("UPDATE assessments SET dependency_artifacts = :arts WHERE migration_id = :mid"),
            {"arts": json.dumps(arts), "mid": migration_id},
        )
        session.commit()

        drift_warn = f" WARNING: {len(removed)} resource(s) removed!" if removed else ""
        _update_migrate_status(session, migration_id, status="test_failed",
                               log_line=f"Fix #{fix_count} complete — rewrote {len(files_changed)} file(s).{drift_warn} Click 'Re-test on OCI'.")

    except Exception as exc:
        logger.error("fix_terraform failed: %s", exc)
        _update_migrate_status(session, migration_id, status="test_failed",
                               log_line=f"Fix failed: {exc}")
    finally:
        session.close()


def approve_migration(migration_id: str) -> None:
    """Called from the API to approve a terraform plan."""
    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        session.execute(
            text("UPDATE migrations SET migrate_status = 'approved' WHERE id = :id AND migrate_status = 'review'"),
            {"id": migration_id},
        )
        session.commit()
    finally:
        session.close()


def reject_migration(migration_id: str) -> None:
    """Called from the API to reject a terraform plan."""
    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        session.execute(
            text("UPDATE migrations SET migrate_status = 'rejected' WHERE id = :id AND migrate_status = 'review'"),
            {"id": migration_id},
        )
        session.commit()
    finally:
        session.close()


def rollback_migration(migration_id: str) -> None:
    """Run terraform destroy to rollback a migration."""
    engine = create_engine(_sync_database_url(), echo=False)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        # Find workspace
        row = session.execute(
            text("SELECT migrate_workload_name FROM migrations WHERE id = :id"),
            {"id": migration_id},
        ).fetchone()
        if not row or not row[0]:
            return

        workload_name = row[0]
        workspace = WORKSPACE_ROOT / migration_id / workload_name.replace(" ", "_")

        # Check if there's anything to destroy
        tfstate_path = workspace / "terraform.tfstate"
        if not workspace.exists() or not tfstate_path.exists():
            _update_migrate_status(session, migration_id, status="rolled_back",
                                   log_line="Nothing to rollback — no terraform state exists")
            return

        _update_migrate_status(session, migration_id, status="rolling_back", step="destroy",
                               log_line="Running terraform destroy for rollback")

        destroy_result = subprocess.run(
            ["terraform", "destroy", "-no-color", "-input=false", "-auto-approve"],
            cwd=str(workspace), capture_output=True, text=True, timeout=1800,
        )

        if destroy_result.returncode == 0:
            _update_migrate_status(session, migration_id, status="rolled_back",
                                   log_line="Rollback completed — all resources destroyed")
            _save_terraform_state(session, migration_id, workspace)
        else:
            _update_migrate_status(session, migration_id, status="failed",
                                   log_line=f"Rollback failed:\n{destroy_result.stderr[:2000]}")
    finally:
        session.close()
