"""Conservative recovery classification for persisted Omnitrix runs.

This module decides what review is required after interruption. It deliberately
never resumes work, retries tools, or treats a journal record as proof that an
external side effect occurred.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


TERMINAL_RUN_STATUSES = frozenset(
    {"completed", "succeeded", "failed", "cancelled", "partial", "expired"}
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
    if retry_review and applied:
        return RecoveryDecision(
            "mixed_reconciliation_review_required",
            ("Some actions are asserted applied while others are asserted not applied; inspect all effects before any continuation.",
             "Applied execution IDs: " + ", ".join(applied),
             "Retry-review execution IDs: " + ", ".join(retry_review)),
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



def classify_model_position(
    transcript: object, checkpoints: object
) -> dict[str, Any]:
    """Validate model request/response ledger alignment with durable checkpoints.

    This is read-only evidence classification. Every disposition is non-resumable;
    matching metadata cannot reconstruct the request, response, or provider state.
    """
    if not isinstance(transcript, list) or not isinstance(checkpoints, list):
        return {
            "disposition": "boundary_mismatch",
            "reasons": ["Transcript and checkpoint inventories must both be lists."],
            "model_call_count": 0,
            "transcript_record_count": 0,
            "request_checkpoint_count": 0,
            "response_checkpoint_count": 0,
            "can_auto_resume": False,
        }

    model_checkpoints = [
        item for item in checkpoints
        if isinstance(item, Mapping)
        and item.get("checkpoint_type") in {
            "model_request_started", "model_response_received"
        }
    ]
    request_checkpoints = [
        item for item in model_checkpoints
        if item.get("checkpoint_type") == "model_request_started"
    ]
    response_checkpoints = [
        item for item in model_checkpoints
        if item.get("checkpoint_type") == "model_response_received"
    ]
    reasons: list[str] = []
    disposition = "model_boundary_consistent"

    if not transcript and not model_checkpoints:
        disposition = "no_model_activity"
        reasons.append("No model transcript records or model-boundary checkpoints exist.")
    else:
        expected_sequence = 0
        expected_type = "model_request"
        pending_request: Mapping[str, Any] | None = None
        for item in transcript:
            if not isinstance(item, Mapping):
                reasons.append("Transcript contains a malformed record.")
                disposition = "boundary_mismatch"
                break
            sequence = item.get("sequence")
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence != expected_sequence:
                reasons.append(
                    f"Transcript sequence mismatch: expected {expected_sequence}, got {sequence!r}."
                )
                disposition = "boundary_mismatch"
                break
            expected_sequence += 1
            if item.get("interaction_type") != expected_type:
                reasons.append(
                    f"Transcript interaction order mismatch at sequence {sequence}: "
                    f"expected {expected_type}, got {item.get('interaction_type')!r}."
                )
                disposition = "boundary_mismatch"
                break
            if expected_type == "model_request":
                digest = item.get("request_sha256")
                if (
                    not isinstance(digest, str)
                    or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest.lower())
                ):
                    reasons.append(f"Transcript request at sequence {sequence} has no valid digest.")
                    disposition = "boundary_mismatch"
                    break
                pending_request = item
                expected_type = "model_response"
            else:
                if pending_request is None:
                    reasons.append("Transcript response has no preceding request.")
                    disposition = "boundary_mismatch"
                    break
                if (
                    item.get("request_sha256") != pending_request.get("request_sha256")
                    or item.get("task_id") != pending_request.get("task_id")
                    or item.get("attempt_id") != pending_request.get("attempt_id")
                ):
                    reasons.append(
                        f"Transcript response at sequence {sequence} does not match its request identity."
                    )
                    disposition = "boundary_mismatch"
                    break
                digest = item.get("response_sha256")
                if (
                    not isinstance(digest, str)
                    or len(digest) != 64
                    or any(character not in "0123456789abcdef" for character in digest.lower())
                ):
                    reasons.append(f"Transcript response at sequence {sequence} has no valid digest.")
                    disposition = "boundary_mismatch"
                    break
                pending_request = None
                expected_type = "model_request"

        if disposition == "model_boundary_consistent" and pending_request is not None:
            disposition = "model_call_outcome_ambiguous"
            reasons.append(
                "A durable model request has no matching response record; provider completion is unknown."
            )

        checkpoint_types = [item.get("checkpoint_type") for item in model_checkpoints]
        expected_checkpoint = "model_request_started"
        for checkpoint_type in checkpoint_types:
            if checkpoint_type != expected_checkpoint:
                reasons.append(
                    "Model-boundary checkpoints are out of order: expected "
                    f"{expected_checkpoint}, got {checkpoint_type!r}."
                )
                disposition = "boundary_mismatch"
                break
            expected_checkpoint = (
                "model_response_received"
                if expected_checkpoint == "model_request_started"
                else "model_request_started"
            )

        transcript_requests = sum(
            isinstance(item, Mapping) and item.get("interaction_type") == "model_request"
            for item in transcript
        )
        transcript_responses = sum(
            isinstance(item, Mapping) and item.get("interaction_type") == "model_response"
            for item in transcript
        )
        if disposition in {"model_boundary_consistent", "model_call_outcome_ambiguous"}:
            if transcript_responses > len(response_checkpoints):
                disposition = "model_response_checkpoint_missing"
                reasons.append(
                    "A model response is durably fingerprinted but its response checkpoint is missing."
                )
            elif transcript_requests > len(request_checkpoints):
                disposition = "boundary_mismatch"
                reasons.append(
                    "A transcript request has no corresponding request-start checkpoint."
                )
            elif len(request_checkpoints) > transcript_requests:
                disposition = "boundary_mismatch"
                reasons.append(
                    "A request-start checkpoint exists without a corresponding transcript request."
                )
            elif len(response_checkpoints) > transcript_responses:
                disposition = "boundary_mismatch"
                reasons.append(
                    "A response checkpoint exists without a corresponding transcript response."
                )
            elif transcript_requests != len(request_checkpoints) or transcript_responses != len(response_checkpoints):
                disposition = "boundary_mismatch"
                reasons.append("Transcript and checkpoint model-call counts do not align.")
            elif disposition == "model_boundary_consistent":
                reasons.append("Transcript request/response pairs align with ordered model checkpoints.")

    return {
        "disposition": disposition,
        "reasons": reasons,
        "model_call_count": sum(
            isinstance(item, Mapping) and item.get("interaction_type") == "model_response"
            for item in transcript
        ),
        "transcript_record_count": len(transcript),
        "request_checkpoint_count": len(request_checkpoints),
        "response_checkpoint_count": len(response_checkpoints),
        "can_auto_resume": False,
    }
