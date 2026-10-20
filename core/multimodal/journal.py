"""Optional durable, privacy-minimized journal for multimodal task outcomes.

The journal is enabled only when OMNITRIX_MULTIMODAL_JOURNAL_PATH points to a
file-backed SQLite database, ideally on a persistent disk. It intentionally
never stores prompts, filenames, file paths, extracted text, API keys, or media.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import uuid
from typing import Any

from core.contracts import RunEvent
from core.multimodal.router import HandoffPacket, TaskRequest, TaskResult
from core.persistence.sqlite_journal import SQLiteJournal


def journal_path() -> str | None:
    """Return an explicit file-backed journal location without exposing it in status."""
    value = os.environ.get("OMNITRIX_MULTIMODAL_JOURNAL_PATH", "").strip()
    if not value or value == ":memory:":
        return None
    return str(Path(value).expanduser())


def journal_status() -> dict[str, Any]:
    """Safe status without returning a potentially sensitive local path."""
    configured = journal_path() is not None
    return {
        "enabled": configured,
        "storage": "configured_file_path" if configured else "disabled",
        "stores_raw_prompts_or_media": False,
        "durability_depends_on_persistent_storage": configured,
    }


def record_task_outcome(task: TaskRequest, result: TaskResult, packet: HandoffPacket) -> bool:
    """Append a minimal execution record. Logging failures never break user-facing work."""
    path = journal_path()
    if path is None:
        return False

    now = datetime.now(timezone.utc).isoformat()
    task_fingerprint = hashlib.sha256(task.task_id.encode("utf-8")).hexdigest()[:32]
    run_id = "multimodal-" + task_fingerprint + "-" + uuid.uuid4().hex[:8]
    journal_task_id = task_fingerprint
    attempt_id = "attempt-" + uuid.uuid4().hex
    status = "completed" if result.success else "partial" if result.evidence else "failed"
    record = {
        "schema_version": 1,
        "kind": "multimodal_task",
        "source_type": task.source_type[:80],
        "required_capabilities": sorted(item.value for item in task.required_capabilities),
        "attempted_workers": list(packet.attempted_workers)[:16],
        "worker_id": result.worker_id[:100],
        "model_id": result.model_id[:160],
        "result_status": status,
        "failure_kind": result.failure_kind.value if result.failure_kind else None,
        "retryable": bool(result.retryable),
        "evidence_count": len(result.evidence),
        "completed_step_ids": list(result.completed_steps)[:32],
    }
    event_id_start = str(uuid.uuid4())
    event_id_finish = str(uuid.uuid4())
    try:
        with SQLiteJournal(path) as journal:
            journal.create_run(run_id, status="running", payload={
                "kind": "multimodal_task",
                "schema_version": 1,
                "source_type": task.source_type[:80],
                "required_capabilities": record["required_capabilities"],
            })
            journal.upsert_task(run_id, journal_task_id, "running", {
                "schema_version": 1,
                "kind": "multimodal_task",
                "source_type": task.source_type[:80],
                "required_capabilities": record["required_capabilities"],
            })
            journal.record_attempt(
                attempt_id, run_id, journal_task_id, 1, "running",
                {"attempted_workers": list(packet.attempted_workers)[:16]},
            )
            journal.append_event(RunEvent(
                event_id=event_id_start, run_id=run_id, sequence=0,
                event_type="multimodal_task_started", timestamp=now,
                task_id=journal_task_id,
                payload={
                    "source_type": task.source_type[:80],
                    "required_capabilities": record["required_capabilities"],
                },
            ))
            journal.finish_attempt(attempt_id, status, record)
            journal.upsert_task(run_id, journal_task_id, status, record)
            journal.update_run(run_id, status, {
                "result_status": status,
                "worker_id": record["worker_id"],
                "model_id": record["model_id"],
            })
            journal.append_event(RunEvent(
                event_id=event_id_finish, run_id=run_id, sequence=1,
                event_type="multimodal_task_finished", timestamp=datetime.now(timezone.utc).isoformat(),
                task_id=journal_task_id, payload=record,
            ))
        return True
    except Exception:
        # Diagnostics are best-effort; never leak database paths or interrupt the task.
        return False
