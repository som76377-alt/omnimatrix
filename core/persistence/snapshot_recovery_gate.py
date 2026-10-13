"""Fail-closed preflight for considering a stored model snapshot during recovery.

This gate validates recovery evidence only. It does not decrypt snapshots, call a
provider, dispatch tools, or authorize resume.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SnapshotRecoveryGateError(ValueError):
    """A snapshot is not eligible for further recovery review."""


def validate_snapshot_recovery_gate(
    *,
    inspection: Mapping[str, Any],
    snapshot_metadata: Mapping[str, Any],
    expected_run_id: str,
    expected_task_id: str,
    expected_attempt_id: str,
) -> None:
    """Raise unless inspection and snapshot identities meet conservative preconditions.

    A successful return is only permission for a caller to continue recovery
    validation; it is never permission to resume a run or replay a tool.
    """
    for name, value in (
        ("expected_run_id", expected_run_id),
        ("expected_task_id", expected_task_id),
        ("expected_attempt_id", expected_attempt_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise SnapshotRecoveryGateError(f"{name} must be non-empty text.")

    if not isinstance(inspection, Mapping) or not isinstance(snapshot_metadata, Mapping):
        raise SnapshotRecoveryGateError("Inspection and snapshot metadata must be objects.")

    if inspection.get("run_id") != expected_run_id:
        raise SnapshotRecoveryGateError("Recovery inspection run identity does not match.")
    if inspection.get("integrity_errors") != []:
        raise SnapshotRecoveryGateError("Recovery inspection contains integrity errors.")

    position = inspection.get("model_position")
    if not isinstance(position, Mapping) or position.get("disposition") != "model_boundary_consistent":
        raise SnapshotRecoveryGateError("Model request/response recovery position is not consistent.")
    if position.get("can_auto_resume") is not False:
        raise SnapshotRecoveryGateError("Recovery inspection must not authorize automatic resume.")

    decision = inspection.get("decision")
    if not isinstance(decision, Mapping) or decision.get("can_auto_resume") is not False:
        raise SnapshotRecoveryGateError("Recovery decision is malformed or unsafe.")

    identity_fields = {
        "run_id": expected_run_id,
        "task_id": expected_task_id,
        "attempt_id": expected_attempt_id,
    }
    for field, expected in identity_fields.items():
        if snapshot_metadata.get(field) != expected:
            raise SnapshotRecoveryGateError(f"Snapshot {field} does not match the requested recovery identity.")

    sequence = snapshot_metadata.get("interaction_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise SnapshotRecoveryGateError("Snapshot interaction sequence is invalid.")

    snapshot_id = snapshot_metadata.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise SnapshotRecoveryGateError("Snapshot ID is missing.")

    # Deliberately no successful/resumable result is returned: callers must still
    # validate the exact transcript-to-snapshot mapping and provider continuation.
    return None
