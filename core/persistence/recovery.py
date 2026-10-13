"""Conservative recovery classification for persisted Omnitrix runs.

This module decides what review is required after interruption. It deliberately
never resumes work, retries tools, or treats a journal record as proof that an
external side effect occurred.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


TERMINAL_RUN_STATUSES = frozenset(
    {"succeeded", "failed", "cancelled", "partial", "expired"}
)
UNCERTAIN_TOOL_STATUSES = frozenset({"running", "unknown"})


@dataclass(frozen=True)
class RecoveryDecision:
    """Read-only recovery recommendation; not an authorization to execute."""

    disposition: str
    reasons: tuple[str, ...]
    can_auto_resume: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "reasons": list(self.reasons),
            "can_auto_resume": self.can_auto_resume,
        }


def classify_recovery(snapshot: Mapping[str, Any] | None) -> RecoveryDecision:
    """Classify a journal snapshot using conservative recovery rules.

    Dispositions:
    - not_found: no such run exists in this journal.
    - terminal: the run already has a terminal status.
    - reconciliation_required: a tool outcome is ambiguous and not resolved.
    - retry_review_required: evidence says an action was not applied; retry still
      requires policy/approval revalidation and is never started here.
    - revalidation_required: re-check provider/task/policy state before deciding.
    - manual_resume_review: a non-running run needs explicit operator review.
    - blocked_unknown_state: an unrecognized state must not be guessed.
    """
    if snapshot is None or not isinstance(snapshot, Mapping):
        return RecoveryDecision("not_found", ("No persisted run snapshot exists.",))

    run = snapshot.get("run")
    if not isinstance(run, Mapping):
        return RecoveryDecision("not_found", ("Snapshot has no persisted run record.",))

    status = run.get("status")
    if not isinstance(status, str) or not status:
        return RecoveryDecision("blocked_unknown_state", ("Run status is missing or invalid.",))

    if status in TERMINAL_RUN_STATUSES:
        return RecoveryDecision("terminal", (f"Run already has terminal status '{status}'.",))

    uncertain = snapshot.get("uncertain_tool_executions", [])
    if not isinstance(uncertain, list):
        return RecoveryDecision(
            "blocked_unknown_state", ("Uncertain tool execution inventory is malformed.",)
        )

    unresolved: list[str] = []
    retry_review: list[str] = []
    applied: list[str] = []
    for record in uncertain:
        if not isinstance(record, Mapping):
            return RecoveryDecision(
                "blocked_unknown_state", ("Tool execution inventory contains an invalid record.",)
            )
        record_status = record.get("status")
        if record_status not in UNCERTAIN_TOOL_STATUSES:
            continue
        reconciliation = record.get("latest_reconciliation")
        decision = reconciliation.get("decision") if isinstance(reconciliation, Mapping) else None
        execution_id = str(record.get("execution_id", "unknown"))
        if decision == "confirmed_applied":
            applied.append(execution_id)
        elif decision == "confirmed_not_applied":
            retry_review.append(execution_id)
        else:
            unresolved.append(execution_id)

    if unresolved:
        return RecoveryDecision(
            "reconciliation_required",
            ("Tool outcome is ambiguous; no retry or resume is safe by default.",
             "Unresolved execution IDs: " + ", ".join(unresolved)),
        )
    if retry_review:
        return RecoveryDecision(
            "retry_review_required",
            ("Evidence records that an action was not applied; re-check policy, approval, and target state before any new attempt.",
             "Executions requiring retry review: " + ", ".join(retry_review)),
        )
    if applied:
        return RecoveryDecision(
            "revalidation_required",
            ("An interrupted action is recorded as applied; verify downstream state before continuing.",
             "Applied execution IDs: " + ", ".join(applied)),
        )

    if status in {"running", "recovering", "verifying"}:
        return RecoveryDecision(
            "revalidation_required",
            (f"Run was in '{status}' state; revalidate checkpoints, provider state, and current policy before continuing.",),
        )
    if status in {"created", "ready", "paused", "awaiting_approval", "blocked"}:
        return RecoveryDecision(
            "manual_resume_review",
            (f"Run is '{status}'; inspect plan, approvals, and completed work before an operator-authorized resume.",),
        )
    return RecoveryDecision(
        "blocked_unknown_state",
        (f"Run status '{status}' is not covered by the recovery state machine.",),
    )
