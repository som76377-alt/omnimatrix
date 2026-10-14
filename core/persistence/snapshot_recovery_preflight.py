"""Read-only lookup that gates encrypted model snapshots on recovery evidence.

This is preflight only: it does not decrypt state, call a model, resume a run,
or authorize replay of any tool.
"""
from __future__ import annotations

from typing import Any

from core.persistence.recovery_service import RecoveryService
from core.persistence.model_state_snapshots import ModelStateSnapshotStore
from core.persistence.snapshot_content_verification import verify_snapshot_content_hashes
from core.persistence.snapshot_recovery_gate import (
    SnapshotRecoveryGateError,
    validate_snapshot_recovery_gate,
)
from core.persistence.snapshot_transcript_correlation import (
    validate_snapshot_transcript_correlation,
)
from core.persistence.sqlite_journal import SQLiteJournal


def inspect_snapshot_preflight(
    journal: SQLiteJournal,
    recovery_service: RecoveryService,
    snapshot_id: str,
    *,
    expected_run_id: str,
    expected_task_id: str,
    expected_attempt_id: str,
    snapshot_store: ModelStateSnapshotStore | None = None,
) -> dict[str, Any]:
    """Return sanitized identity after recovery and transcript-correlation checks."""
    if not isinstance(journal, SQLiteJournal):
        raise TypeError("journal must be a SQLiteJournal.")
    if not isinstance(recovery_service, RecoveryService):
        raise TypeError("recovery_service must be a RecoveryService.")
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise SnapshotRecoveryGateError("snapshot_id must be non-empty text.")

    matches = [
        item for item in journal.list_model_state_snapshot_metadata(expected_run_id)
        if item.get("snapshot_id") == snapshot_id
    ]
    if len(matches) != 1:
        raise SnapshotRecoveryGateError("Snapshot is missing or does not belong to the requested run.")

    inspection = recovery_service.inspect(expected_run_id).to_dict()
    metadata = matches[0]
    validate_snapshot_recovery_gate(
        inspection=inspection,
        snapshot_metadata=metadata,
        expected_run_id=expected_run_id,
        expected_task_id=expected_task_id,
        expected_attempt_id=expected_attempt_id,
    )
    correlation = validate_snapshot_transcript_correlation(
        snapshot_metadata=metadata,
        transcript=journal.list_model_transcript(expected_run_id),
    )
    content_verification = {"content_hashes_verified": False}
    if snapshot_store is not None:
        if not isinstance(snapshot_store, ModelStateSnapshotStore):
            raise TypeError("snapshot_store must be a ModelStateSnapshotStore.")
        if snapshot_store._journal is not journal:
            raise SnapshotRecoveryGateError("Snapshot store must use the same journal as preflight.")
        content_verification = verify_snapshot_content_hashes(
            snapshot_store=snapshot_store,
            snapshot_id=snapshot_id,
            expected_request_sha256=correlation["request_sha256"],
            expected_response_sha256=correlation["response_sha256"],
        )

    return {
        "snapshot_id": snapshot_id,
        "run_id": expected_run_id,
        "task_id": expected_task_id,
        "attempt_id": expected_attempt_id,
        "interaction_sequence": metadata["interaction_sequence"],
        "provider": metadata["provider"],
        "model": metadata["model"],
        "transcript_correlation": {**correlation, **content_verification},
        "recovery_disposition": inspection["decision"]["disposition"],
        "model_position_disposition": inspection["model_position"]["disposition"],
        "can_auto_resume": False,
    }
