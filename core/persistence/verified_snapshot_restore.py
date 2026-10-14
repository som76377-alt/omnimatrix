"""Reconstruct a verified provider-neutral model-state pair without resuming execution.

This is a bounded recovery building block, not a resume engine: it never calls a
provider, dispatches a tool, replays an event, or authorizes automatic resume.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.models.adapters import AdapterRegistry
from core.models.base import ModelResponse
from core.models.messages import ModelRequest
from core.persistence.model_state_snapshots import ModelStateSnapshotStore
from core.persistence.recovery_service import RecoveryService
from core.persistence.snapshot_recovery_gate import SnapshotRecoveryGateError
from core.persistence.snapshot_recovery_preflight import inspect_snapshot_preflight
from core.persistence.sqlite_journal import SQLiteJournal


@dataclass(frozen=True)
class VerifiedModelStateSnapshot:
    """A decrypted request/response pair with read-only recovery evidence."""

    snapshot_id: str
    run_id: str
    task_id: str
    attempt_id: str
    interaction_sequence: int
    request: ModelRequest
    response: ModelResponse
    preflight: Mapping[str, Any]

    @property
    def execution_authorized(self) -> bool:
        """Verified bytes never authorize a model call, tool call, or resume."""
        return False


def reconstruct_verified_snapshot_pair(
    journal: SQLiteJournal,
    recovery_service: RecoveryService,
    snapshot_store: ModelStateSnapshotStore,
    adapter_registry: AdapterRegistry,
    snapshot_id: str,
    *,
    expected_run_id: str,
    expected_task_id: str,
    expected_attempt_id: str,
) -> VerifiedModelStateSnapshot:
    """Return typed state only after identity, transcript, content, and provider checks.

    The caller must supply an explicitly enabled encrypted store and the exact
    registry intended for later policy review. This function intentionally stops
    before building a live conversation or invoking a model/tool.
    """
    if not isinstance(journal, SQLiteJournal):
        raise TypeError("journal must be a SQLiteJournal.")
    if not isinstance(recovery_service, RecoveryService):
        raise TypeError("recovery_service must be a RecoveryService.")
    if not isinstance(snapshot_store, ModelStateSnapshotStore):
        raise TypeError("snapshot_store must be a ModelStateSnapshotStore.")
    if not snapshot_store.enabled:
        raise SnapshotRecoveryGateError("Encrypted snapshot storage must be enabled.")
    if snapshot_store._journal is not journal:
        raise SnapshotRecoveryGateError("Snapshot store must use the supplied journal.")
    if not isinstance(adapter_registry, AdapterRegistry):
        raise TypeError("adapter_registry must be an AdapterRegistry.")
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise SnapshotRecoveryGateError("snapshot_id must be non-empty text.")

    evidence = inspect_snapshot_preflight(
        journal,
        recovery_service,
        snapshot_id,
        expected_run_id=expected_run_id,
        expected_task_id=expected_task_id,
        expected_attempt_id=expected_attempt_id,
        snapshot_store=snapshot_store,
        adapter_registry=adapter_registry,
    )
    expected_identity = {
        "snapshot_id": snapshot_id,
        "run_id": expected_run_id,
        "task_id": expected_task_id,
        "attempt_id": expected_attempt_id,
    }
    for field, expected in expected_identity.items():
        if evidence.get(field) != expected:
            raise SnapshotRecoveryGateError(
                f"Verified snapshot preflight {field} does not match the requested identity."
            )
    if evidence.get("can_auto_resume") is not False:
        raise SnapshotRecoveryGateError("Snapshot preflight must never authorize automatic resume.")

    transcript = evidence.get("transcript_correlation")
    if not isinstance(transcript, Mapping) or transcript.get("content_hashes_verified") is not True:
        raise SnapshotRecoveryGateError("Snapshot request/response content hashes are not verified.")

    compatibility = evidence.get("provider_continuation_compatibility")
    if not isinstance(compatibility, Mapping) or compatibility.get("checked") is not True:
        raise SnapshotRecoveryGateError("Provider continuation compatibility was not checked.")
    if compatibility.get("provider_compatible") is not True:
        raise SnapshotRecoveryGateError("No unique compatible provider/model adapter was verified.")
    if compatibility.get("restore_ready") is not False:
        raise SnapshotRecoveryGateError("Provider inspection must not claim that execution is restore-ready.")

    request, response = snapshot_store.load_pair(snapshot_id)
    if response.provider != evidence.get("provider") or response.model != evidence.get("model"):
        raise SnapshotRecoveryGateError("Decrypted response provider/model does not match preflight.")
    continuation_present = response.continuation is not None
    if compatibility.get("continuation_state_present") is not continuation_present:
        raise SnapshotRecoveryGateError("Continuation presence does not match verified provider evidence.")
    if continuation_present and compatibility.get("continuation_state_compatible") is not True:
        raise SnapshotRecoveryGateError("Decrypted continuation state is not supported by the registered adapter.")
    if not continuation_present and compatibility.get("continuation_state_compatible") not in (None, False):
        raise SnapshotRecoveryGateError("Provider evidence has an invalid missing-continuation disposition.")

    sequence = evidence.get("interaction_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise SnapshotRecoveryGateError("Verified snapshot interaction sequence is invalid.")

    return VerifiedModelStateSnapshot(
        snapshot_id=snapshot_id,
        run_id=expected_run_id,
        task_id=expected_task_id,
        attempt_id=expected_attempt_id,
        interaction_sequence=sequence,
        request=request,
        response=response,
        preflight=dict(evidence),
    )
