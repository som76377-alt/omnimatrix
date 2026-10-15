"""Read-only recovery inventory for checkpoints, tools, approvals and snapshots.

The inventory is evidence for a human review, never permission to resume execution.
It intentionally omits approval payloads, tool outcomes and model content.
"""
from __future__ import annotations

from typing import Any

from core.persistence.recovery_service import RecoveryService
from core.persistence.sqlite_journal import SQLiteJournal


_TERMINAL_TOOL_STATUSES = {"succeeded", "failed"}
_UNCERTAIN_TOOL_STATUSES = {"running", "unknown"}
_TERMINAL_APPROVAL_STATUSES = {
    "approved", "rejected", "denied", "cancelled", "expired", "revoked",
}


def inspect_recovery_inventory(
    journal: SQLiteJournal,
    recovery_service: RecoveryService,
    run_id: str,
    *,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Summarize recovery evidence and fail closed on ambiguous execution history.

    This function performs read-only journal queries. It does not decrypt model
    state, contact providers, replay events, invoke tools, or authorize resume.
    An approval is reported as historical metadata only; it is never treated as
    permission to resume a previously interrupted execution.
    """
    if not isinstance(journal, SQLiteJournal):
        raise TypeError("journal must be a SQLiteJournal.")
    if not isinstance(recovery_service, RecoveryService):
        raise TypeError("recovery_service must be a RecoveryService.")
    if recovery_service._journal is not journal:
        raise ValueError("recovery_service must inspect the supplied journal.")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be non-empty text.")
    if snapshot_id is not None and (
        not isinstance(snapshot_id, str) or not snapshot_id.strip()
    ):
        raise ValueError("snapshot_id must be non-empty text when supplied.")

    findings: list[dict[str, str]] = []

    def finding(code: str, severity: str, message: str) -> None:
        findings.append({"code": code, "severity": severity, "message": message})

    inspection = recovery_service.inspect(run_id)
    try:
        snapshot = journal.get_recovery_snapshot(run_id)
        tool_records = journal.list_tool_executions(run_id)
        approvals = journal.list_approvals(run_id)
        snapshot_metadata = journal.list_model_state_snapshot_metadata(run_id)
    except (ValueError, TypeError, KeyError, RuntimeError) as exc:
        finding(
            "journal_inventory_unreadable", "block",
            f"Recovery inventory could not be read ({type(exc).__name__}).",
        )
        return {
            "run_id": run_id,
            "disposition": "blocked_unknown_state",
            "findings": findings,
            "inspection": inspection.to_dict(),
            "tool_executions": [],
            "approvals": [],
            "snapshot": None,
            "can_auto_resume": False,
            "execution_authorized": False,
        }

    if snapshot is None:
        finding("run_not_found", "block", "No durable run record exists for this ID.")
        return {
            "run_id": run_id,
            "disposition": "blocked_unknown_state",
            "findings": findings,
            "inspection": inspection.to_dict(),
            "tool_executions": [],
            "approvals": [],
            "snapshot": None,
            "can_auto_resume": False,
            "execution_authorized": False,
        }

    if inspection.integrity_errors or inspection.decision.disposition == "blocked_unknown_state":
        finding(
            "recovery_integrity_blocked", "block",
            "The recovery inspection found inconsistent or unreadable persisted state.",
        )

    checkpoints = snapshot.get("checkpoints", [])
    prepared: dict[str, dict[str, Any]] = {}
    result_received: set[str] = set()
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            finding("malformed_checkpoint", "block", "A checkpoint is not an object.")
            continue
        payload = checkpoint.get("payload")
        if not isinstance(payload, dict):
            finding("malformed_checkpoint_payload", "block", "A checkpoint payload is not an object.")
            continue
        action_id = payload.get("logical_action_id")
        checkpoint_type = checkpoint.get("checkpoint_type")
        if checkpoint_type in {"tool_call_prepared", "tool_call_result_received"}:
            if (
                not isinstance(payload.get("task_id"), str)
                or not payload.get("task_id")
                or not isinstance(payload.get("attempt_id"), str)
                or not payload.get("attempt_id")
            ):
                finding(
                    "tool_checkpoint_identity_missing", "block",
                    "A tool-call checkpoint lacks task/attempt identity.",
                )
            if not isinstance(action_id, str) or not action_id:
                finding(
                    "tool_checkpoint_action_identity_missing", "block",
                    "A tool-call checkpoint lacks a logical action ID.",
                )
        if isinstance(action_id, str) and action_id:
            if checkpoint_type == "tool_call_prepared":
                if action_id in prepared:
                    finding(
                        "duplicate_tool_prepared_checkpoint", "block",
                        "Multiple prepared checkpoints use the same logical action ID.",
                    )
                prepared[action_id] = checkpoint
            elif checkpoint_type == "tool_call_result_received":
                result_received.add(action_id)

    execution_by_action: dict[str, list[dict[str, Any]]] = {}
    task_by_id = {item.get("task_id"): item for item in snapshot.get("tasks", [])}
    attempt_by_id = {item.get("attempt_id"): item for item in snapshot.get("attempts", [])}
    for record in tool_records:
        task_id = record.get("task_id")
        attempt_id = record.get("attempt_id")
        attempt = attempt_by_id.get(attempt_id)
        if (
            record.get("run_id") != run_id
            or task_id not in task_by_id
            or attempt is None
            or attempt.get("task_id") != task_id
        ):
            finding(
                "tool_execution_identity_mismatch", "block",
                f"Tool execution {record.get('execution_id')} has inconsistent run/task/attempt identity.",
            )
        action_id = record.get("logical_action_id")
        if isinstance(action_id, str) and action_id:
            execution_by_action.setdefault(action_id, []).append(record)
        else:
            finding(
                "tool_execution_action_identity_missing", "block",
                f"Tool execution {record.get('execution_id')} has no logical action ID.",
            )
        status = record.get("status")
        if status in _UNCERTAIN_TOOL_STATUSES or status not in _TERMINAL_TOOL_STATUSES:
            finding(
                "tool_execution_uncertain", "block",
                f"Tool execution {record.get('execution_id')} has non-terminal or unknown status.",
            )
        elif status == "succeeded":
            finding(
                "tool_effect_requires_verification", "review",
                f"Successful tool execution {record.get('execution_id')} needs downstream verification.",
            )
        elif status == "failed":
            finding(
                "tool_failure_requires_review", "review",
                f"Failed tool execution {record.get('execution_id')} may have partial side effects.",
            )
        if status in _TERMINAL_TOOL_STATUSES and action_id and action_id not in result_received:
            finding(
                "tool_result_checkpoint_missing", "block",
                f"Tool execution {record.get('execution_id')} has no matching result checkpoint.",
            )

    for action_id in prepared:
        matches = execution_by_action.get(action_id, [])
        if len(matches) != 1:
            finding(
                "tool_boundary_execution_mismatch", "block",
                f"Prepared tool action {action_id} has {len(matches)} matching execution records.",
            )
    for action_id, matches in execution_by_action.items():
        if action_id not in prepared or len(matches) != 1:
            finding(
                "tool_execution_checkpoint_mismatch", "block",
                f"Logical action {action_id} does not map to exactly one prepared checkpoint.",
            )
    for action_id in result_received:
        if action_id not in execution_by_action:
            finding(
                "orphan_tool_result_checkpoint", "block",
                f"Tool result checkpoint {action_id} has no matching durable execution record.",
            )

    approval_summaries = []
    for approval in approvals:
        status = approval.get("status")
        approval_summaries.append({
            "approval_id": approval.get("approval_id"),
            "fingerprint": approval.get("fingerprint"),
            "status": status,
            "created_at": approval.get("created_at"),
            "requires_revalidation": status == "approved",
        })
        if status == "approved":
            finding(
                "approval_requires_revalidation", "review",
                f"Approval {approval.get('approval_id')} is historical and must be rebound to the exact current plan.",
            )
        elif status not in _TERMINAL_APPROVAL_STATUSES:
            finding(
                "approval_status_unknown", "block",
                f"Approval {approval.get('approval_id')} has an unrecognized or pending status.",
            )

    selected_snapshot = None
    if snapshot_id is not None:
        matches = [item for item in snapshot_metadata if item.get("snapshot_id") == snapshot_id]
        if len(matches) != 1:
            finding(
                "snapshot_not_found_or_ambiguous", "block",
                "The requested snapshot does not resolve to exactly one metadata record for this run.",
            )
        else:
            selected_snapshot = matches[0]
            tasks = {item.get("task_id"): item for item in snapshot.get("tasks", [])}
            attempts = {item.get("attempt_id"): item for item in snapshot.get("attempts", [])}
            task_id = selected_snapshot.get("task_id")
            attempt_id = selected_snapshot.get("attempt_id")
            task = tasks.get(task_id)
            attempt = attempts.get(attempt_id)
            if task is None or attempt is None or attempt.get("task_id") != task_id:
                finding(
                    "snapshot_task_attempt_mismatch", "block",
                    "Snapshot task/attempt identity does not match the journal.",
                )
            else:
                task_attempts = [
                    item for item in snapshot.get("attempts", [])
                    if item.get("task_id") == task_id
                ]
                latest_attempt = max(
                    task_attempts,
                    key=lambda item: item.get("attempt_number", 0),
                    default=None,
                )
                if latest_attempt is None or latest_attempt.get("attempt_id") != attempt_id:
                    finding(
                        "snapshot_is_not_latest_attempt", "block",
                        "Snapshot belongs to an older attempt than the latest journaled attempt.",
                    )
            if checkpoints:
                latest_checkpoint = checkpoints[-1]
                payload = latest_checkpoint.get("payload")
                if not isinstance(payload, dict):
                    finding(
                        "latest_checkpoint_identity_unverifiable", "block",
                        "Latest checkpoint payload cannot be used to verify snapshot identity.",
                    )
                elif payload.get("task_id") != task_id or payload.get("attempt_id") != attempt_id:
                    finding(
                        "snapshot_latest_checkpoint_mismatch", "block",
                        "Snapshot task/attempt differs from the latest checkpoint identity.",
                    )
            else:
                finding(
                    "snapshot_without_checkpoint", "block",
                    "No checkpoint exists to anchor snapshot recovery.",
                )

    block_codes = {item["code"] for item in findings if item["severity"] == "block"}
    review_codes = {item["code"] for item in findings if item["severity"] == "review"}
    if block_codes:
        disposition = "blocked_unknown_state"
    elif review_codes:
        disposition = "manual_revalidation_required"
    else:
        disposition = inspection.decision.disposition

    safe_tool_records = [{
        "execution_id": item.get("execution_id"),
        "tool_name": item.get("tool_name"),
        "logical_action_id": item.get("logical_action_id"),
        "task_id": item.get("task_id"),
        "attempt_id": item.get("attempt_id"),
        "status": item.get("status"),
        "started_at": item.get("started_at"),
        "finished_at": item.get("finished_at"),
        "has_outcome_record": bool(item.get("outcome")),
    } for item in tool_records]

    return {
        "run_id": run_id,
        "disposition": disposition,
        "findings": findings,
        "inspection": inspection.to_dict(),
        "tool_executions": safe_tool_records,
        "approvals": approval_summaries,
        "snapshot": ({
            key: selected_snapshot.get(key)
            for key in (
                "snapshot_id", "run_id", "task_id", "attempt_id",
                "interaction_sequence", "provider", "model", "created_at",
            )
        } if selected_snapshot is not None else None),
        "can_auto_resume": False,
        "execution_authorized": False,
    }
