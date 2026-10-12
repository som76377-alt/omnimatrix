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

## Phase 1 — Domain and policy foundations

- Make plan, task, tool request, and worker result structures explicit and versionable.
- Validate unknown tools, malformed arguments, invalid dependencies/cycles, missing dependencies, and invalid state transitions at trust boundaries.
- Extend approval fingerprints to cover every execution-relevant field, including requested capability/scopes, targets, resources, cost policy, and verification requirements.
- Separate user approval from plan construction and from execution; reject stale approvals.
- Define typed worker outcomes and safe error categories.
- **Gate:** tests demonstrate that malformed plans, invalid arguments, stale approvals, and paid-provider use in zero-cost mode cannot cause side effects.

## Phase 2 — Durable execution and recovery

- Persist task records, state transitions, events, approvals, and artifact references in SQLite.
- Define pause, cancel, retry, resume, and idempotency semantics.
- Preserve completed work and failed-task evidence across restarts.
- Add fault-injection tests around crashes between side effects and checkpoint writes.
- **Gate:** restart/resume results match the declared state machine and never fabricate completion.

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
