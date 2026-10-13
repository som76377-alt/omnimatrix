# Omnitrix staged roadmap

This roadmap distinguishes shipped foundations from target capabilities. A phase is complete only when its acceptance tests and verification evidence exist; a document or UI label alone does not make a capability complete.

## Phase 0 — Reproducible baseline (complete)

- [x] Document CLI startup, current capabilities, and implementation boundaries.
- [x] Document architecture and staged roadmap.
- [x] Record the environment/dependency baseline: CI uses Python 3.14; the current application/tests use the standard library, with no third-party dependency manifest or lockfile.
- [x] Add CI for compilation, demo JSON validation, unit tests, and offline CLI smoke test.
- [x] Ignore local environments, secrets, and generated development artifacts; remove tracked Python bytecode.
- [x] Preserve an explicit zero-spend demo profile with clearly simulated output.
- **Gate:** verified on a clean GitHub Actions checkout: the documented checks and offline CLI run passed without API credentials or paid model calls. Future dependency changes must update the packaging/lock strategy and CI deliberately.

## Phase 1 — Stabilize core contracts (in progress)

- [x] Add versioned worker request/result, trust-labelled context, structured run-event, and normalized error contracts.
- [x] Add deterministic model/tool budget primitives with a strict zero-cost default and unit tests.
- [x] Bind plan fingerprints to declared tool scopes, targets, resources, verification criteria, policy version, spend mode, risk tier, and external-egress intent.
- [x] Show approval-sensitive context in the human-readable plan preview.
- [x] Validate tool arguments against a documented JSON Schema subset before tool execution; malformed/unsupported schemas fail closed.
- [x] Wire the budget guard into planner and task-loop model-call boundaries; unknown-cost providers are rejected in zero-cost mode unless explicitly classified.
- [x] Enforce exact tool-name scopes from approved plans and reject declared targets/resources/external egress that the current runtime cannot yet enforce (fail closed).
- [x] Add stable tool-execution IDs and idempotency keys at the tool boundary, with tests for duplicate requests, key/request mismatches, and uncertain outcomes.
- **Gate:** invalid plans/arguments, stale approvals, paid or unknown-cost providers in zero-cost mode, and untrusted outputs cannot trigger unauthorized side effects. This increment does not yet pass the entire Phase 1 gate.

## Phase 2 — Durable execution and recovery (in progress)

- [x] Add a versioned SQLite schema and journal primitives for runs, tasks, attempts, events, approvals, and artifact metadata.
- [x] Add atomic writes, foreign-key constraints, unique event sequence enforcement, event cursor reads, and file-backed reopen tests.
- [x] Add opt-in journal integration for `run()` and `chat()` with run/task IDs and created, started, completed, and failed events persisted around execution.
- [x] Persist a stable ID and terminal status for the initial task attempt, including failed attempts; reject attempts being finished twice.
- [x] Add a schema-v2 tool-execution journal and a durable duplicate-execution fence. A previously claimed idempotency key is never executed again automatically; arguments are represented by a SHA-256 digest rather than stored verbatim.
- [ ] Define pause, cancel, retry, resume, and cross-attempt idempotency semantics before automatic recovery.
- [ ] Preserve completed work and failed-task evidence across real process restarts.
- [x] Add real subprocess crash-injection tests that terminate the process before a side effect and after a side effect but before its checkpoint; expose read-only inspection of running/unknown tool records.
- [x] Add schema-v3 logical action IDs and deterministic idempotency keys that do not change with the attempt ID; reject changed arguments under the same key.
- [x] Add append-only reconciliation assertions and a read-only run/task/attempt/tool recovery snapshot.
- [x] Define a conservative recovery classifier: unresolved effects require reconciliation; confirmed-applied effects require downstream verification; confirmed-not-applied effects require fresh retry review; no disposition auto-resumes.
- [x] Add append-only schema-v4 checkpoints with canonical SHA-256 payload digests and a read-only recovery inspection service that validates checkpoint sequence/digests and run/task/attempt/tool references before classification.
- [x] Write digest-checked checkpoints from the live orchestrator at task start, before/after model calls, around tool calls, and before terminal lifecycle persistence; avoid storing raw prompts, model responses, tool arguments, or tool outputs in checkpoint payloads.
- [x] Verify ordered checkpoints through a real journaled run and a subprocess terminated at a model-call boundary; interrupted runs remain non-terminal and require recovery review.
- [x] Fault-inject a subprocess exit after a tool has performed a simulated external side effect but before its outcome can be committed; after reopening the database, the tool remains `running`/uncertain and recovery requires reconciliation.
- [x] Fault-inject a second crash after the tool outcome is durably committed but before the orchestrator records the returned result; confirm the terminal tool record survives and objective-only restart still refuses to replay any run with tool history.
- [x] Add an explicitly confirmed restart-from-objective path for interrupted single-task `run()` executions only when integrity inspection passes and no tool execution or tool-call boundary exists; the previous attempt is marked interrupted and a new attempt is journaled before fresh model work.
- [x] Expose privacy-conscious recent-run listing, read-only recovery inspection, optional journal-backed chat, and explicitly confirmed guarded restart through the CLI; run listings omit objective payloads.
- [x] Add a one-shot `--run-objective` CLI command that requires a journal, persists a single-task `run()` execution, and reports the new run ID alongside the result so eligible interrupted runs can be found for inspection.
- [x] Add schema-v5 durable tool-result snapshots with strict opt-in replay policy (default `never`), bounded JSON payloads, SHA-256 integrity verification, and an atomic commit with the terminal tool outcome.
- [x] Enable result snapshot persistence only for the deterministic calculator; verify custom tools remain non-replayable unless they explicitly opt in.
- [x] Add read-only replay-candidate resolution requiring exact run/task/logical-action/tool/request identity, one matching execution, terminal success, and a verified result snapshot; blocked outcomes omit result content.
- [x] Add schema-v6 privacy-minimal, append-only model request/response metadata records with contiguous ordering, SHA-256 fields, and no prompt/response body storage; migration preserves earlier journal data.
- [ ] Wire the model transcript ledger into live request/response boundaries using canonical hashes and verify it with subprocess crash tests.
- [ ] Restore a live model/tool conversation from verified snapshots and checkpointed provider state; metadata hashes alone cannot reconstruct provider state, and snapshot storage alone does not resume a task or authorize re-execution.
- [x] Add unit tests for recovery classification, reconciliation evidence, schema-v1-to-v6 migration, and cross-attempt duplicate blocking.
- [x] Version the PRD into `docs/PRD.md` and synchronize the implementation snapshot against the repository.
- [ ] Implement full conversation/provider-state restoration, pause/cancel/resume, and event replay into live execution. The current explicit restart path only reruns the original objective when no tool has ever been dispatched; it deliberately blocks chat turns, legacy runs without execution-kind metadata, and any run with a tool execution or tool-call boundary.
- [ ] Add tool/provider-specific reconciliation adapters that validate external evidence and define safe retry policies.
- **Gate:** restart/resume results match the declared state machine and never fabricate completion. The journal is opt-in and stores task objectives in its SQLite payloads; choose a protected local path and do not enable it for sensitive prompts without considering at-rest data protection. Reconciliation records are assertions, not proof. The logical action key is stable across attempts only when run/task/action identity is preserved; the current iteration/position identity conservatively blocks changed arguments but does not infer semantic equivalence. Automatic resume/retry remains unimplemented.

## Phase 3 — Tool catalog and procurement

- Maintain a typed tool registry with capability, permission, cost, trust, and verification metadata.
- Build a librarian/procurement workflow that searches existing libraries/tools before creating replacements.
- Treat all retrieved documentation and tool output as untrusted input.
- **Gate:** selection is explainable, policy checked, and tested against duplicate-tool and malicious-description cases.

## Phase 4 — Model routing and evaluations

- Separate planner, implementer, researcher, and verifier *capabilities* without assuming separate named agents always improve results.
- Route using task fit, quality evidence, privacy, latency, availability, and an explicit budget.
- Track provider calls and enforce zero-spend mode in code.
- Add representative evaluations and regression thresholds before changing routing policy.
- **Gate:** routes are reproducible under policy, spend limits are enforced, and scores reflect task outcomes rather than model self-assessment.

## Phase 5 — Artifacts and confined workspace

- Introduce durable artifacts, provenance, hashes, and per-task workspace boundaries.
- Make filesystem operations scoped and auditable.
- Add cleanup, quota, and path-traversal tests.
- **Gate:** tasks cannot read or write outside explicitly granted workspace scopes.

## Phase 6 — GitHub adapter

- Add an application-level GitHub tool with repository/branch scope, diff review, test evidence, and explicit write approval.
- Keep credentials in a secret store/environment; never expose tokens in logs or model context.
- Use branches and pull requests as the default review path; verify remote state after every mutation.
- **Gate:** tests cover denied permissions, stale base refs, failed writes, secret redaction, and accurate reporting of commit/PR status.

## Phase 7 — Android chat application

- Build a phone-first chat UI and reliable API boundary to the orchestrator.
- Add authentication, session isolation, cancel/status controls, streaming/event timelines, and accessible error states.
- **Gate:** connectivity loss and app restarts do not lose or misrepresent task state.

## Phase 8 — Live workspace / desktop streaming

- Add a controlled remote workspace with explicit session permissions and visible browser/terminal activity.
- Separate command execution, screen streaming, clipboard, file transfer, and repository access permissions.
- **Gate:** user can observe and stop actions; session isolation, authentication, and recovery are tested.

## Phase 9 — Modality-specific creation and scientific tools

- Add each medium as a separately evaluated capability (for example, research, coding, graphics, audio, video, 3D, scientific visualization, and game/APK work).
- Set quality gates appropriate to the medium; prioritize implementation effort by demand and feasibility without lowering the quality standard.
- **Gate:** a representative benchmark and provenance/validation path exist for each claimed capability.

## Phase 10 — Voice interaction

- Add wake/activation controls, speech-to-text, turn management, tool execution status, interruption, and text-to-speech.
- Keep voice-triggered side effects behind the same policy/approval model as typed requests.
- **Gate:** false activations, recognition uncertainty, interruption, and accidental actions have dedicated tests.

## Phase 11 — Hardening and operations

- Add structured audit traces, provider health handling, security review, redaction, dependency maintenance, and backup/recovery guidance.
- Run end-to-end fault and abuse-case evaluations before expanding privileges.
- **Gate:** evidence-based quality and safety thresholds are met for each enabled capability.

## Working rule

Do not skip foundational safety and recovery work to make a demo look more autonomous. A small feature that is verified, recoverable, and honest about its limits is preferable to a wider feature that can claim success incorrectly.
