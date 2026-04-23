"""Poll OCM work-requests while a migration is running.

After our migrate step's ``terraform apply`` finishes, the
``oci_cloud_migrations_*`` resources it created kick off an asynchronous
migration inside OCM: discovery → plan → replication → launch. Those steps
are tracked as **work requests** that live beyond our Terraform apply —
we need to watch them and feed their status back into the migrate UI.

Contract:

    poll_work_requests(
        migration_id: str,
        ocm_migration_ocid: str,
        oci_config: dict,
        on_progress: callable[[WorkRequestStatus], None],
        timeout_seconds: int = 3600 * 6,
        poll_interval_seconds: int = 30,
    ) -> WorkRequestStatus

Returns the final status when all work requests reach a terminal state
(SUCCEEDED, FAILED, or CANCELED), or raises ``TimeoutError`` if the
total elapsed time exceeds the timeout.

If the ``oci`` SDK isn't importable (dev environments), the function
returns a ``WorkRequestStatus`` with ``level="sdk_unavailable"`` and logs
an advisory — the operator can check OCM progress in the Oracle Cloud
console instead.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Work-request states returned by OCI's generic work-request API.
# Terminal = the overall operation is done (one way or another).
TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELED"}
ACTIVE_STATES = {"ACCEPTED", "IN_PROGRESS", "CANCELING"}


@dataclass
class WorkRequestStatus:
    """Compact summary the UI can render without knowing OCI internals."""
    migration_ocid: str
    level: str                       # running | succeeded | failed | timeout | sdk_unavailable
    message: str                     # one-line human readable
    percent_complete: float = 0.0    # 0..100 across the whole set
    work_requests: list[dict] = field(default_factory=list)
    started_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


def _load_oci_sdk() -> Any | None:
    """Attempt to import the OCI SDK's CloudMigrationsClient. Returns None
    if the SDK isn't installed (dev/test env) so callers can fall back
    gracefully."""
    try:
        import oci  # noqa: F401
        from oci.cloud_migrations import MigrationClient  # noqa: F401
        return oci
    except ImportError as exc:
        logger.info("OCI SDK not importable (%s) — OCM watcher runs in no-op mode.", exc)
        return None


def poll_work_requests(
    migration_id: str,
    ocm_migration_ocid: str,
    oci_config: dict[str, Any],
    on_progress: Callable[[WorkRequestStatus], None] | None = None,
    timeout_seconds: int = 3600 * 6,
    poll_interval_seconds: int = 30,
) -> WorkRequestStatus:
    """Poll every work request attached to ``ocm_migration_ocid`` until done.

    ``oci_config`` shape matches ``oci.config.from_file`` output — the
    caller (migration_executor) builds it from the OCI connection record.
    The function never raises for OCI API errors mid-poll; it logs, waits,
    and retries. The only escape is the overall timeout.
    """
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    status = WorkRequestStatus(
        migration_ocid=ocm_migration_ocid,
        level="running",
        message="OCM watcher starting",
        started_at=now,
        updated_at=now,
    )

    oci_sdk = _load_oci_sdk()
    if oci_sdk is None:
        status.level = "sdk_unavailable"
        status.message = (
            "OCI Python SDK not installed on this host. Monitor OCM progress "
            "manually via the Oracle Cloud console or `oci work-requests "
            "work-request list`."
        )
        if on_progress:
            on_progress(status)
        return status

    # Import here so the module imports cleanly without the SDK.
    from oci.cloud_migrations import MigrationClient           # noqa: F401
    from oci.work_requests import WorkRequestClient

    try:
        wr_client = WorkRequestClient(oci_config)
    except Exception as exc:  # noqa: BLE001
        status.level = "failed"
        status.message = f"Failed to build OCI WorkRequestClient: {exc!s}"[:400]
        if on_progress:
            on_progress(status)
        return status

    compartment_id = oci_config.get("compartment_id") or ""
    deadline = time.time() + max(60, timeout_seconds)

    while time.time() < deadline:
        try:
            # List all work-requests in the migration's compartment, filter
            # to ones whose resource is our migration (OCIDs match).
            resp = wr_client.list_work_requests(compartment_id=compartment_id)
            matching = [
                wr for wr in (resp.data or [])
                if any(
                    getattr(res, "identifier", "") == ocm_migration_ocid
                    for res in (getattr(wr, "resources", None) or [])
                )
            ]
        except Exception as exc:  # noqa: BLE001 — never crash the polling loop
            logger.warning("work_request list failed: %s; retrying", exc)
            time.sleep(poll_interval_seconds)
            continue

        # Aggregate: overall % = mean of per-request % complete; level
        # derives from the worst terminal state.
        if not matching:
            status.message = "No OCM work-requests yet; polling…"
            status.percent_complete = 0.0
            status.work_requests = []
        else:
            pcts = [float(getattr(wr, "percent_complete", 0) or 0) for wr in matching]
            status.percent_complete = sum(pcts) / max(len(pcts), 1)
            status.work_requests = [
                {
                    "id": getattr(wr, "id", ""),
                    "operation_type": getattr(wr, "operation_type", ""),
                    "status": getattr(wr, "status", ""),
                    "percent_complete": float(getattr(wr, "percent_complete", 0) or 0),
                    "time_accepted": str(getattr(wr, "time_accepted", "")),
                    "time_finished": str(getattr(wr, "time_finished", "")),
                }
                for wr in matching
            ]
            any_failed = any(wr.get("status") == "FAILED" for wr in status.work_requests)
            all_done = all(wr.get("status") in TERMINAL_STATES for wr in status.work_requests)
            if any_failed:
                status.level = "failed"
                status.message = (
                    f"{sum(1 for wr in status.work_requests if wr['status']=='FAILED')} "
                    f"OCM work-request(s) failed — see OCM console for details."
                )
            elif all_done:
                status.level = "succeeded"
                status.message = "All OCM work-requests succeeded; replication + launch complete."
            else:
                status.level = "running"
                status.message = (
                    f"OCM: {sum(1 for wr in status.work_requests if wr['status']=='SUCCEEDED')}/"
                    f"{len(status.work_requests)} done — "
                    f"{status.percent_complete:.0f}% overall"
                )

        status.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if on_progress:
            try:
                on_progress(status)
            except Exception as exc:  # noqa: BLE001
                logger.warning("on_progress callback raised: %s", exc)

        if status.level in ("succeeded", "failed"):
            return status

        time.sleep(poll_interval_seconds)

    # Timed out
    status.level = "timeout"
    status.message = (
        f"OCM watcher timed out after {timeout_seconds}s. Overall progress "
        f"{status.percent_complete:.0f}%. Resume via OCM console."
    )
    status.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if on_progress:
        on_progress(status)
    return status


def parse_migration_ocid_from_tf_output(output_json: str) -> str | None:
    """Extract the migration_id Terraform output from ``terraform output -json``.

    Our ocm_handoff_translation skill emits
    ``output "migration_id" { value = oci_cloud_migrations_migration.main.id }``.
    Everything downstream keys off that single OCID.
    """
    import json as _json
    try:
        data = _json.loads(output_json)
    except (ValueError, TypeError):
        return None
    node = data.get("migration_id") or data.get("migration_ocid")
    if isinstance(node, dict):
        return node.get("value") or None
    if isinstance(node, str):
        return node
    return None
