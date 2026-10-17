# Omnitrix staged roadmap

This roadmap distinguishes shipped foundations from target capabilities. A phase is complete only when its acceptance tests and verification evidence exist; a document or UI label alone does not make a capability complete.

## Phase 0 — Reproducible baseline (complete)

- [x] Document CLI startup, current capabilities, and implementation boundaries.
- [x] Document architecture and staged roadmap.
- [x] Record the environment/dependency baseline: CI uses Python 3.14; application code primarily uses the standard library plus the explicitly declared `cryptography` runtime dependency in `requirements.txt`; a fully pinned lockfile is not yet present.
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
- [x] Wire the model transcript ledger into task-loop model request/response boundaries using canonical hashes; a subprocess crash test proves the unmatched request record survives, and automatic resume remains disabled.
- [x] Validate recovery position by correlating transcript sequence/identity with ordered request/response checkpoints; classify unmatched requests and the response-recorded/checkpoint-missing crash gap, with subprocess coverage and no automatic resume.
- [x] Define a versioned, bounded model-state codec with request/response round-trip tests, canonical SHA-256 verification, and fail-closed schema/size/type checks; this is in-memory only and does not persist sensitive conversation content or enable resume.
- [x] Add a verified snapshot reconstruction API that returns the typed provider-neutral request/response pair only after recovery identity, transcript correlation, decrypted content hashes, and provider compatibility pass; tests prove the API does not authorize execution.
- [ ] Restore a live model/tool conversation from verified snapshots and checkpointed provider state; metadata hashes alone cannot reconstruct the full live orchestration state, and snapshot storage alone does not resume a task or authorize re-execution.
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

- [x] Add the first bounded workspace capability: explicit opt-in, root-confined directory listing and small UTF-8 text reads; deny traversal, symlinks, hidden/secret-like paths, binary files, and oversized reads. CLI opt-in and regression tests are included. This does not complete the phase gate or claim to be a general OS sandbox.
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

**Current status (17 October 2026): alpha implemented; phase gate remains open.** A native Jetpack Compose app is merged under `android/` with Chat, Workspace, Tests & Status, and Connect screens. GitHub Actions has compiled and packaged an installable debug APK and run the Python regression suite plus Android JVM input-validation tests. Successful trusted builds are being wired to publish a direct-download GitHub Release asset.

- [x] Implement first native Compose client and authenticated Python Studio API integration.
- [x] Build an installable debug APK in CI and upload build/test artifacts.
- [ ] Verify install, pairing, real chat request, allowlisted workspace read/write and test-result display end-to-end on a physical Android device.
- [ ] Add robust session isolation, cancellation, streaming/event timelines, and recovery across app restarts.
- [ ] Replace the public Codespaces-port plus shared bearer-token development setup with a production-grade authenticated relay/backend before broader deployment.
- **Gate:** connectivity loss and app restarts do not lose or misrepresent task state; device-level smoke tests and security review pass.

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


### Phase 2 follow-up — encrypted model-state snapshots

- [x] Add schema-v7 storage for encrypted snapshot bytes and bounded identity metadata.
- [x] Keep persistence disabled by default and require an externally supplied 32-byte key for explicit opt-in.
- [x] Encrypt only complete request/response pairs with AES-GCM; bind run/task/attempt/sequence/provider/model/key ID as authenticated data.
- [x] Validate codec envelopes on write and read; test database reopen, ciphertext confidentiality, wrong-key/corruption rejection, identity constraints and explicit deletion.
- [x] Verify CI and review dependency, privacy and migration behavior; CI run #331 passed 321 tests, compilation, configuration validation and offline CLI smoke test.
- [x] Add a read-only, fail-closed snapshot recovery preflight that requires an integrity-clean inspection, a consistent model request/response boundary, and exact run/task/attempt/snapshot identity; it reports `can_auto_resume: false` and does not decrypt, call a provider, or replay tools.
- [x] Add read-only correlation from each snapshot's zero-based model-call ordinal to exactly one complete transcript request/response pair, checking run/task/attempt/provider/model identity, pair order, and request-digest linkage.
- [x] Verify the new decrypted snapshot request/response hash comparison in CI (run #367 passed compilation, configuration validation, the full unit-test suite, and offline CLI smoke test). With no snapshot store/key, preflight remains metadata-only and reports `content_hashes_verified: false`.
- [x] Add a read-only provider/model continuation compatibility contract for registered adapters; validate Gemini interaction IDs and fail closed for unknown, ambiguous, or malformed continuation state. Preflight can report compatibility only when an encrypted snapshot store and adapter registry are supplied; `restore_ready` remains false and no provider is called.
- [x] Restore provider-neutral request/response objects only after content-hash correlation and provider continuation compatibility are integrated; keep automatic resume disabled until full end-to-end crash recovery is tested.
- [x] Add a read-only recovery execution inventory covering all durable tool records, approval metadata, prepared/result checkpoint reconciliation, and optional encrypted snapshot identity; fail closed on uncertain effects, missing/mismatched boundaries, stale attempts, and unverifiable checkpoint identity. Newly written checkpoints bind task/attempt IDs. PR #34 adds focused tests; full live restoration and resume remain open.

- [x] Surface latest tool-reconciliation assertions in recovery inventory without exposing arbitrary evidence payloads or treating assertions as proof. Confirmed-applied/not-applied assertions remain blocked until a future tool-specific verifier supplies independently validated evidence and policy; no retry or resume is authorized. PR #34 tests latest-record selection, redaction, and fail-closed behavior.

- [x] Make recovery inventory fail closed when SQLite is closed/unavailable during initial inspection or subsequent reads; report the storage failure without treating it as an empty run. Regression test covers a closed journal. This remains diagnostic only and does not recover damaged storage.


- [x] Define a typed tool-specific reconciliation verifier contract and explicit registry. Bind results to exact execution/idempotency/tool/request-digest/run/task/attempt/logical-action identity; reject unknown tools, invalid identity, mismatched or malformed results, invalid evidence metadata, and verifier errors. Contract tests cover applied/not-applied/unknown and fail-closed paths.
- [ ] Register at least one concrete provider verifier that checks authoritative external evidence without performing the action; add integration tests against that provider's evidence format. Until this exists, no independent external verification is claimed and uncertain actions remain blocked.
- [ ] Only after concrete verifier evidence and policy are independently reviewed, design any future action-state transition. This verifier contract does not authorize retries, replay, or automatic resume.


- [x] Align recovery inventory terminal-state classification with the executor's actual `returned_failure` status. Preserve manual review for possible partial side effects and keep execution authorization and automatic resume disabled. Regression test verifies that the known terminal status is not misclassified as an unknown in-progress action.


- [x] Implement a real, read-only workspace tool as the first confined-workspace vertical slice; register it without granting permission by default and require explicit CLI opt-in.
- [x] Use pinned directory handles and directory-relative no-follow opens to prevent workspace path replacement/symlink races on supported operating systems; fail closed where the required primitives are unavailable.
- [x] Add an operator-configurable relative-path allowlist for workspace reads and listings, with traversal validation and explicit empty-list denial. This narrows exposure but is not a per-task policy.
- [ ] Add per-task workspace allowlists and provenance, and perform a separately authorized live-provider smoke test before treating workspace access as production-ready.

## Live monitoring console increment — prototype boundary preserved

- [x] Add a responsive static web console with overview, CI/test status, current-capability inventory, workspace command helper, and journal/recovery documentation.
- [x] Read public workflow-run and open-PR data from GitHub; publish a test snapshot generated only by a passing test/build workflow.
- [x] Add network-first app-shell caching, hosted updates without reinstalling, and JavaScript/HTML regression checks.
- [x] Add a main-branch Pages build/deploy workflow that runs the Python suite and browser-script syntax checks before publish.
- [ ] Verify the first public Pages deployment URL after the latest main-branch merge; a green pull-request CI run alone is not deployment evidence.
- [x] Add a private, bearer-token-protected Python Studio backend for actual core chat, bounded read-only workspace browsing, runtime model/tool status, and the fixed local test runner. The public Pages preview must not be treated as the runtime.
- [ ] Add a web API for the local recovery journal only after defining suitable per-session authorization and sensitive-data handling.

## Main Omnitrix Studio workspace increment

- [x] Replace the dashboard-only UI with a workspace-first Studio interface: file explorer, read-only source display, core-backed chat surface, local test output panel, runtime model/tool inventory, CI evidence, and recovery command guide.
- [x] Add an authenticated Python API and localhost integration tests; all browser API calls require the runtime token, and no arbitrary shell or source-write endpoint is exposed.
- [x] Add a Codespaces devcontainer that keeps port 8000 private and starts a supervised Studio process.
- [x] Add a guarded auto-sync loop for a clean `main` checkout only. It uses a fetch plus `--ff-only` merge and supervisor restart, pauses for dirty trees/other branches/active operations, and never resets local work.
- [x] Add integration tests for backend token enforcement, real offline-demo chat wiring, permission-gated workspace reads and test execution, and session validation; add isolated Git tests for update safety.
- [ ] Pass CI on the exact PR head and inspect logs for all new test classes before merging.
- [ ] Verify that main-branch merge triggers a successful Pages deploy and that the Pages preview URL no longer returns 404.
- [ ] Separately run an authorized live-provider smoke test before describing any response as genuine Gemini inference.

