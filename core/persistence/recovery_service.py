"""Read-only, integrity-aware inspection of persisted runs.

Inspection is deliberately separate from execution: a valid snapshot is evidence
for human review, not permission to resume or repeat external side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from core.persistence.recovery import (
    RecoveryDecision,
    classify_model_position,
    classify_recovery,
)
from core.persistence.sqlite_journal import SQLiteJournal


@dataclass(frozen=True)
class RecoveryInspection:
    """Integrity findings plus a conservative recovery disposition."""

    run_id: str
    decision: RecoveryDecision
    integrity_errors: tuple[str, ...]
    checkpoint_count: int
    latest_checkpoint_id: str | None
    model_position: Mapping[str, Any] | None = None

    @property
    def can_auto_resume(self) -> bool:
        """Inspection never authorizes execution, even when data validates."""
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "decision": self.decision.to_dict(),
            "integrity_errors": list(self.integrity_errors),
            "checkpoint_count": self.checkpoint_count,
            "latest_checkpoint_id": self.latest_checkpoint_id,
            "model_position": dict(self.model_position or {}),
            "can_auto_resume": False,
        }


class RecoveryService:
    """Reconstruct and validate the journal's known state without replaying it."""

    def __init__(self, journal: SQLiteJournal) -> None:
        if not isinstance(journal, SQLiteJournal):
            raise TypeError("journal must be a SQLiteJournal.")
        self._journal = journal

    def inspect(self, run_id: str) -> RecoveryInspection:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be a non-empty string.")
        try:
            snapshot = self._journal.get_recovery_snapshot(run_id)
        except (ValueError, TypeError, KeyError) as exc:
            # Malformed persisted JSON must become a blocked inspection result,
            # not an exception that could be mistaken for a missing/empty run.
            decision = RecoveryDecision(
                "blocked_unknown_state",
                ("Persisted recovery snapshot could not be decoded.", type(exc).__name__),
                can_auto_resume=False,
            )
            return RecoveryInspection(run_id, decision, (type(exc).__name__,), 0, None)
        if snapshot is None:
            return RecoveryInspection(
                run_id, classify_recovery(None), (), 0, None
            )

        errors = self._validate_snapshot(run_id, snapshot)
        checkpoints = snapshot.get("checkpoints", [])
        try:
            transcript = self._journal.list_model_transcript(run_id)
            model_position = classify_model_position(transcript, checkpoints)
        except (ValueError, TypeError, KeyError) as exc:
            model_position = {
                "disposition": "boundary_mismatch",
                "reasons": ["Model transcript could not be inspected.", type(exc).__name__],
                "model_call_count": 0,
                "transcript_record_count": 0,
                "request_checkpoint_count": 0,
                "response_checkpoint_count": 0,
                "can_auto_resume": False,
            }

        if errors:
            decision = RecoveryDecision(
                "blocked_unknown_state",
                ("Persisted recovery state failed integrity validation.", *errors),
                can_auto_resume=False,
            )
        else:
            decision = classify_recovery(snapshot)
            position_disposition = model_position["disposition"]
            if position_disposition == "model_call_outcome_ambiguous":
                decision = RecoveryDecision(
                    "model_call_outcome_ambiguous",
                    tuple(model_position["reasons"]),
                    can_auto_resume=False,
                )
            elif position_disposition == "model_response_checkpoint_missing":
                decision = RecoveryDecision(
                    "model_response_checkpoint_missing",
                    tuple(model_position["reasons"]),
                    can_auto_resume=False,
                )
            elif position_disposition == "boundary_mismatch":
                decision = RecoveryDecision(
                    "blocked_unknown_state",
                    ("Model transcript and checkpoint boundaries are inconsistent.",
                     *tuple(model_position["reasons"])),
                    can_auto_resume=False,
                )

        latest_id = checkpoints[-1].get("checkpoint_id") if checkpoints else None
        return RecoveryInspection(
            run_id=run_id,
            decision=decision,
            integrity_errors=tuple(errors),
            checkpoint_count=len(checkpoints),
            latest_checkpoint_id=latest_id,
            model_position=model_position,
        )

    @staticmethod
    def _validate_snapshot(run_id: str, snapshot: Mapping[str, Any]) -> list[str]:
        errors: list[str] = []
        run = snapshot.get("run")
        if not isinstance(run, Mapping) or run.get("run_id") != run_id:
            errors.append("Run record is missing or its ID does not match the requested run.")
            return errors

        tasks = snapshot.get("tasks")
        attempts = snapshot.get("attempts")
        checkpoints = snapshot.get("checkpoints")
        events = snapshot.get("events")
        uncertain = snapshot.get("uncertain_tool_executions")
        for field, value in (
            ("tasks", tasks), ("attempts", attempts), ("checkpoints", checkpoints),
            ("events", events), ("uncertain_tool_executions", uncertain),
        ):
            if not isinstance(value, list):
                errors.append(f"Snapshot field '{field}' is not a list.")
        if errors:
            return errors

        task_ids: set[str] = set()
        for task in tasks:
            if not isinstance(task, Mapping) or task.get("run_id") != run_id:
                errors.append("Task record is malformed or belongs to another run.")
                continue
            task_id = task.get("task_id")
            if not isinstance(task_id, str) or not task_id or task_id in task_ids:
                errors.append("Task IDs must be non-empty and unique within the run.")
            else:
                task_ids.add(task_id)

        attempt_ids: set[str] = set()
        for attempt in attempts:
            if not isinstance(attempt, Mapping) or attempt.get("run_id") != run_id:
                errors.append("Attempt record is malformed or belongs to another run.")
                continue
            attempt_id, task_id = attempt.get("attempt_id"), attempt.get("task_id")
            if not isinstance(attempt_id, str) or not attempt_id or attempt_id in attempt_ids:
                errors.append("Attempt IDs must be non-empty and unique.")
            else:
                attempt_ids.add(attempt_id)
            if task_id not in task_ids:
                errors.append(f"Attempt '{attempt_id}' refers to an unknown task.")

        expected_sequence = 0
        checkpoint_ids: set[str] = set()
        for checkpoint in checkpoints:
            if not isinstance(checkpoint, Mapping) or checkpoint.get("run_id") != run_id:
                errors.append("Checkpoint record is malformed or belongs to another run.")
                continue
            checkpoint_id = checkpoint.get("checkpoint_id")
            sequence = checkpoint.get("sequence")
            payload = checkpoint.get("payload")
            stored_digest = checkpoint.get("payload_sha256")
            if not isinstance(checkpoint_id, str) or not checkpoint_id or checkpoint_id in checkpoint_ids:
                errors.append("Checkpoint IDs must be non-empty and unique.")
            else:
                checkpoint_ids.add(checkpoint_id)
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence != expected_sequence:
                errors.append(
                    f"Checkpoint sequence gap or disorder: expected {expected_sequence}, got {sequence!r}."
                )
                if isinstance(sequence, int) and not isinstance(sequence, bool):
                    expected_sequence = sequence + 1
            else:
                expected_sequence += 1
            if not isinstance(payload, Mapping):
                errors.append(f"Checkpoint '{checkpoint_id}' payload is not an object.")
                continue
            try:
                canonical = json.dumps(
                    dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                actual_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            except (TypeError, ValueError):
                errors.append(f"Checkpoint '{checkpoint_id}' payload is not JSON-serializable.")
                continue
            if not isinstance(stored_digest, str) or actual_digest != stored_digest:
                errors.append(f"Checkpoint '{checkpoint_id}' payload digest mismatch.")

        previous_sequence = -1
        event_ids: set[str] = set()
        for event in events:
            if not isinstance(event, Mapping) or event.get("run_id") != run_id:
                errors.append("Event record is malformed or belongs to another run.")
                continue
            sequence, event_id = event.get("sequence"), event.get("event_id")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= previous_sequence:
                errors.append("Event sequences must be integers in strictly increasing order.")
            elif sequence >= 0:
                previous_sequence = sequence
            if not isinstance(event_id, str) or not event_id or event_id in event_ids:
                errors.append("Event IDs must be non-empty and unique.")
            else:
                event_ids.add(event_id)

        for execution in uncertain:
            if not isinstance(execution, Mapping):
                errors.append("Uncertain tool execution inventory contains a malformed record.")
                continue
            if execution.get("run_id") != run_id:
                errors.append("Uncertain tool execution belongs to another run.")
            task_id = execution.get("task_id")
            if task_id is not None and task_id not in task_ids:
                errors.append("Uncertain tool execution refers to an unknown task.")
            attempt_id = execution.get("attempt_id")
            if attempt_id is not None and attempt_id not in attempt_ids:
                errors.append("Uncertain tool execution refers to an unknown attempt.")

        return errors
