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

## Guarded manual restart from the original objective

`Omnitrix.resume_interrupted_run(run_id, confirm_restart_from_objective=True)` is a narrow,
explicitly requested recovery path. It is not automatic resume and does not restore provider
continuation state. It first runs integrity-aware inspection, requires a non-terminal running
single-task run with consistent persisted objective metadata, and refuses chat turns whose prior
conversation context was not serialized. It also refuses if any tool execution record exists or
if a checkpoint records tool-call preparation/result. That conservative fence means the objective
can only be rerun when the journal proves no tool was dispatched. The current runtime's model
budget and tool permissions apply to the new attempt.

Before the next model call, the prior open attempt is marked `interrupted`, a new numbered attempt
is persisted, the restart decision is checkpointed, and lifecycle events are appended. The new
attempt reuses the run/task identity but receives a fresh attempt ID. A caller must explicitly pass
`confirm_restart_from_objective=True`; omission is rejected. This path does not support multi-task
plans, chat-context restoration, any run with prior tool executions, or ambiguous side effects.
Those cases remain blocked for manual reconciliation/review.

The CLI exposes these operations when given `--journal PATH`:

- `--run-objective OBJECTIVE`: execute a single task through `run()` with `--config PATH --journal PATH`, and print the resulting run ID with the result.
- `--list-runs`: list recent IDs/statuses without printing stored objective payloads.
- `--inspect-run RUN_ID`: print the read-only disposition and integrity findings.
- `--restart-run RUN_ID --confirm-restart-from-objective`: invoke the narrow guarded restart; a missing confirmation flag is a parser error.

Normal chat can opt into persistence with `--journal PATH`. The database still stores objectives in run/task payloads, so the file must be protected at rest.

## Explicitly not implemented

- Automatic process-restart resume or event replay; only the explicitly confirmed, no-tool-dispatch restart subset described above is supported.
- Re-running model calls from a durable checkpoint; current checkpoints are integrity-checked data records, not yet a complete replay position.
- Automatic retries, pause/cancel execution control, or compensating actions.
- Provider-specific or tool-specific proof that an external side effect did or did not happen.
- Cryptographic identity/authentication for the actor who records a reconciliation decision.
- A fully stable semantic action ID across changed plans; the current iteration/position scheme is conservative
  and blocks on argument mismatches but requires deterministic replay of the same task sequence.


## Opt-in replayable tool-result snapshots (schema v5)

Schema v5 adds `tool_result_snapshots`, linked to a durable tool-execution record. The executor persists a result only when the tool explicitly declares `replay_policy = "deterministic_json_v1"`; the base `Tool` contract defaults to `never`. The calculator is the initial opt-in because its arithmetic result is deterministic and has no external side effect. This policy is a promise by the tool implementation, not a general declaration that arbitrary tool output is safe to store.

Only successful outputs that serialize as finite JSON and fit within 16 KiB are snapshotted. The result payload is stored separately from the request arguments. Its SHA-256 digest binds both the replay-policy label and canonical result JSON, so tampering with either is detected. `finish_tool_execution()` commits the terminal outcome and optional snapshot in one SQLite transaction, so a crash cannot leave a terminal success with a half-written snapshot. Read access verifies the digest and refuses corrupted snapshots. A tool that does not opt in, or whose output is not eligible for bounded JSON storage, has no replay snapshot; that absence is not evidence that the tool failed.

**This is storage groundwork, not resume.** Omnitrix does not yet reconstruct the provider conversation, prove that the saved result belongs at the current model position, or feed the snapshot back into a live run. No automatic retry or resume is enabled by schema v5. Snapshot integrity detects accidental payload modification when the stored digest remains intact; it is not a signature against an actor who can rewrite both fields. The SQLite journal can contain tool outputs, so protect the local database and avoid opting sensitive-output tools in without an explicit privacy review.


## Verified replay-candidate resolution

`SQLiteJournal.resolve_replay_candidate()` is a read-only eligibility check, not a resume API. It requires the exact run ID, task ID, logical action ID, tool name, and canonical request SHA-256. It returns a result only when exactly one durable execution matches that action identity, the tool name and request digest match, the execution has a terminal `succeeded` status, and the associated opt-in snapshot passes its policy-and-payload digest check. Missing records, request mismatches, non-successful executions, missing snapshots, and duplicate logical-action identities return explicit blocked dispositions without exposing result content. Snapshot integrity errors raise and fail closed. This lookup does not prove the model is at the correct conversation position, reconstruct provider continuation state, or authorize any tool call; live restoration remains unimplemented.

## Acceptance tests

- Terminal and unknown run states do not auto-resume.
- An unresolved tool action requires reconciliation.
- `confirmed_not_applied` leads to review, never an automatic retry.
- `confirmed_applied` leads to downstream revalidation.
- Stable action keys are identical across attempt IDs for the same run/task/action.
- Changed arguments under a previously claimed key are refused.
- SQLite migration from schema v1 to v5 retains journal data and adds reconciliation, checkpoint, and replay-snapshot support.
- Checkpoint payload digest tampering, sequence gaps, and invalid task/attempt references block recovery inspection.
- Schema-v5 replay snapshots are created only for explicitly opted-in successful tools, stay within the payload size bound, survive reopen, and fail closed on digest corruption.
- Terminal outcome and replay snapshot commit atomically; invalid snapshot data leaves the tool record non-terminal.
- Missing replay snapshots never authorize rerunning a tool or automatically resuming a task.
- Replay-candidate resolution returns output only for a unique successful execution with exact run/task/action/tool/request identity and a valid opted-in snapshot.
- Missing, mismatched, uncertain, non-successful, or duplicate action records return blocked dispositions without output; corrupted snapshots fail closed.
- A real process crash before and after a simulated side effect leaves a visible uncertain record.
- A real subprocess crash at a model-call boundary leaves the latest committed checkpoint visible after reopening the journal; the run remains non-terminal and is never auto-resumed.
- A real subprocess crash after a simulated tool side effect but before outcome persistence leaves the tool execution in `running`, preserves the last `tool_call_prepared` checkpoint, and classifies the run as `reconciliation_required`.
- A real subprocess crash after the tool outcome is committed but before the orchestrator consumes the result leaves a terminal `succeeded` tool record and the run non-terminal; objective-only restart is still blocked because tool history exists, and recovery requires downstream revalidation.


## Schema-v6 privacy-minimal model transcript metadata

Schema v6 adds an append-only `model_transcript` ledger for ordered model request/response boundaries. It records run/task/attempt IDs, interaction type, optional provider/model labels, SHA-256 request/response digests, tool-call count, and timestamp. It deliberately does **not** store prompt text, model response text, tool arguments, or tool outputs. Sequence numbers must be contiguous per run, and SQLite triggers reject updates/deletes through ordinary SQL operations.

This is correlation and crash-position groundwork, not a restorable conversation. Hashes cannot reconstruct content or provider continuation state; a digest is not authentication against an actor able to rewrite the database schema or triggers. At schema-v6 introduction this was groundwork only; the live task-loop instrumentation and its first subprocess crash test are now documented in the following section. It still must not be described as a complete runtime transcript or used to resume work. Existing v1-v5 journals migrate forward without deleting prior records.


## Live model transcript instrumentation

The live orchestrator now appends metadata-only transcript records around each task-loop model call. Before sending a request it hashes a canonical JSON representation of instructions, ordered messages (including tool results), authorized tool definitions, and provider continuation state; after a response it hashes normalized response content, tool calls, usage metadata, and continuation state. Only the digest, provider/model identifiers, request/response boundary type, tool-call count, and run/task/attempt linkage are stored. Raw prompt, response, tool arguments, tool outputs, and continuation state are not written to this ledger. If canonical serialization fails, a journaled model call fails closed rather than sending a request whose transcript cannot be recorded.

A process crash inside the adapter leaves a durable request record without a matching response record. That is evidence of an unresolved model-call boundary, not proof that the provider did or did not complete generation. Sequence numbers are contiguous per run, but transcript metadata still cannot reconstruct the message payload or provider continuation; hashes are not signatures and do not authenticate a database against a privileged writer. Planner calls outside a journaled task run are not covered by this transcript instrumentation. The existing checkpoint ledger remains a separate integrity-checked boundary record, and automatic resume remains disabled.


## Model recovery-position validation

Recovery inspection now compares the metadata transcript with the ordered model-boundary checkpoints. It verifies contiguous transcript sequence numbers, request/response alternation, matching request fingerprints and task/attempt identities, valid digest presence, and the order/counts of `model_request_started` and `model_response_received` checkpoints. It reports one of `no_model_activity`, `model_boundary_consistent`, `model_call_outcome_ambiguous`, `model_response_checkpoint_missing`, or a fail-closed `boundary_mismatch`. The inspection output includes the position summary and remains read-only.

An unmatched request is classified as `model_call_outcome_ambiguous`: the provider may or may not have completed the generation. A durable response fingerprint without its response checkpoint is classified separately as `model_response_checkpoint_missing`, covering a crash in the gap between those two commits. Missing or misordered boundaries and mismatched task/attempt identities block inspection as `blocked_unknown_state`. These labels describe persisted evidence only; they do not restore message content, establish provider-side state, authorize replay, or enable automatic resume. Every disposition keeps `can_auto_resume=false`.


## Versioned model-state codec (schema v1)

`core.persistence.model_state` defines a bounded, canonical JSON envelope for normalized `ModelRequest` and `ModelResponse` objects. It preserves message order, tool definitions/calls/results, usage metadata, and opaque provider continuation fields when those values are finite JSON-compatible data. Decoding checks the schema version, exact envelope shapes, 64 KiB encoded-payload limit, SHA-256 digest, and model-type constraints before constructing objects. Unknown schema versions, altered payloads, malformed structures, non-JSON values, and oversized payloads fail closed.

This is deliberately an in-memory codec, not a persistence feature. The envelope contains potentially sensitive prompt, response, tool, and continuation data. No database table or automatic orchestration path stores or consumes it yet; do not log it or commit real user content. A matching digest detects accidental or unsophisticated payload changes but is not a signature against a privileged database writer. Even a successful round trip does not prove provider continuation is still valid, authorize a tool action, or enable resume.


## Encrypted model-state snapshot storage (schema v7)

The opt-in `ModelStateSnapshotStore` stores complete normalized request/response pairs as AES-GCM authenticated ciphertext. The default is disabled. Enabling it requires a caller-supplied 32-byte key held outside the journal and a key identifier; the key is never written to SQLite. Associated authenticated data binds the ciphertext to the snapshot's run/task/attempt/interaction sequence, provider, model and key ID. The plaintext pair is bounded and validated by the versioned model-state codec both before storage and after decryption. Only ciphertext, nonce, digest and limited identity metadata are stored. An explicit delete operation supports retention/privacy cleanup.

A missing/wrong key, key-ID mismatch, authentication failure, digest mismatch, malformed decoded pair or mismatched stored identity fails closed. AES-GCM protects confidentiality and detects unauthorized ciphertext/associated-data changes, but it does not protect against deletion, rollback of the whole database, a compromised process while the key is available, or unsafe key handling by the caller. SQLite is not itself encrypted. Do not keep the key next to the database or commit it. **This feature does not resume a run**: it does not establish provider continuation validity, reconstruct all runtime state, or authorize replay/tool execution; `can_auto_resume` remains false.
