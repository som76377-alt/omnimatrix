# Omnitrix recovery state machine (Phase 2)

## Scope and safety boundary

This document defines the first conservative recovery classifier. It is read-only:
it describes the next review action for a persisted run, but it does not schedule work,
retry a tool, resume a model call, or grant approval. A durable journal record is evidence
of what Omnitrix recorded, not proof of what happened in an external system.

The implementation is `core/persistence/recovery.py`; persisted snapshots are provided by
`SQLiteJournal.get_recovery_snapshot(run_id)`.

## Recovery dispositions

| Disposition | Condition | Allowed next step |
|---|---|---|
| `not_found` | No run record exists | Stop; do not infer a run from task/tool records |
| `terminal` | Run status is completed, succeeded, failed, cancelled, partial, or expired | Show recorded outcome; do not resume |
| `reconciliation_required` | One or more tool actions are running/unknown without a decisive reconciliation record | Inspect the target system or request human review; no retry |
| `retry_review_required` | Reconciliation evidence says the action was not applied | Recheck approval, policy, target and current state; a new attempt is not started automatically |
| `mixed_reconciliation_review_required` | Some uncertain actions are asserted applied and others not applied | Review all effects together before continuing; no retry or resume |
| `revalidation_required` | An action was confirmed applied, or a run was interrupted while running/recovering/verifying | Verify downstream state and re-evaluate policy before continuation |
| `manual_resume_review` | Run is created, ready, paused, awaiting approval, or blocked | Review plan, artifacts, approval expiry and completed work |
| `blocked_unknown_state` | Missing/malformed snapshot fields or unrecognized run state | Fail closed and require diagnosis |

Every disposition currently sets `can_auto_resume=false`. That is intentional until full run restoration,
approval revalidation, checkpoint integrity and tool-specific policies are implemented.

## Logical tool-action identity

- Each tool intent inside a journaled task receives a deterministic `logical_action_id` based on its tool-loop iteration and position in that response.
- Its idempotency key is derived from `run_id + task_id + logical_action_id`, not `attempt_id` or the provider-generated tool-call ID.
- The journal stores the logical action ID and a digest of canonicalized tool name/arguments. The same key with different arguments is rejected.
- A future retry must reuse the same run/task/action identity for the same logical side effect. If a re-planned attempt changes arguments or action ordering, Omnitrix must stop for review instead of guessing that it is the same operation.
- This prevents duplicate execution across attempts when the same logical identity is preserved. It does not create exactly-once delivery or reconcile external systems.

## Reconciliation evidence

Reconciliation is append-only in `tool_reconciliations`. Each record contains the execution ID, decision,
operator/actor label, timestamp and evidence payload. Decisions are:

- `confirmed_applied`: treat the effect as applied and verify downstream state.
- `confirmed_not_applied`: retry may be considered only after fresh policy/approval/target checks.
- `unresolved`: remain blocked pending more evidence.

A reconciliation record does not rewrite the original tool-execution status, execute a retry, or prove its
own claim. The latest record guides classification; the full history remains available for audit. Tool-specific
reconciliation adapters and evidence validation are still future work.

## Durable checkpoints and integrity-aware inspection

Schema v4 adds an append-only `checkpoints` table. Each checkpoint has a run-local sequence,
type, JSON payload, creation timestamp and SHA-256 digest of canonical JSON (UTF-8, sorted keys,
compact separators). A unique constraint prevents two checkpoints from claiming the same sequence.
`SQLiteJournal.save_checkpoint()` rejects unknown runs and invalid sequence values; inserts cannot
silently replace an existing checkpoint; writes must use the next contiguous sequence number. `RecoveryService.inspect(run_id)` reconstructs the stored
snapshot and checks checkpoint digests and sequence continuity, task/attempt relationships, and
run-scoped event/tool references before returning a disposition. Integrity failures become
`blocked_unknown_state`, never a best-effort resume.

The digest is an integrity check against accidental payload changes when the stored digest remains
intact; it is not a keyed MAC or signature and cannot detect a database actor who rewrites both
payload and digest. Inspection is read-only and never restores a live orchestrator, repeats a model
call, retries a tool, or authorizes execution. The live orchestrator now writes ordered checkpoints for task start, model request start/response receipt, tool-call preparation/result receipt, task result readiness, and observed task failure. Payloads keep only IDs, counts, names, statuses, and hashes rather than raw prompts, responses, arguments, or outputs. A process crash can therefore leave useful boundary evidence. These checkpoints still do not contain the serialized conversation/provider continuation, and the orchestrator does not resume from them.

## Explicitly not implemented

- Automatic process-restart resume or event replay.
- Re-running model calls from a durable checkpoint; current checkpoints are integrity-checked data records, not yet a complete replay position.
- Automatic retries, pause/cancel execution control, or compensating actions.
- Provider-specific or tool-specific proof that an external side effect did or did not happen.
- Cryptographic identity/authentication for the actor who records a reconciliation decision.
- A fully stable semantic action ID across changed plans; the current iteration/position scheme is conservative
  and blocks on argument mismatches but requires deterministic replay of the same task sequence.

## Acceptance tests

- Terminal and unknown run states do not auto-resume.
- An unresolved tool action requires reconciliation.
- `confirmed_not_applied` leads to review, never an automatic retry.
- `confirmed_applied` leads to downstream revalidation.
- Stable action keys are identical across attempt IDs for the same run/task/action.
- Changed arguments under a previously claimed key are refused.
- SQLite migration from schema v1 to v4 retains journal data and adds reconciliation plus checkpoint support.
- Checkpoint payload digest tampering, sequence gaps, and invalid task/attempt references block recovery inspection.
- A real process crash before and after a simulated side effect leaves a visible uncertain record.
- A real subprocess crash at a model-call boundary leaves the latest committed checkpoint visible after reopening the journal; the run remains non-terminal and is never auto-resumed.
