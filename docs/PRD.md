# OMNITRIX

# Product Requirements Document & Engineering Blueprint

**Version:** 1.13 — Live model-call transcript instrumentation  
**Research / snapshot date:** 13 October 2026  
**Implementation status snapshot:** 13 October 2026, branch `phase2/safe-model-transcript`; schema-v6 transcript ledger wired into journaled task-loop model calls; crash-boundary test added, CI pending  
**Status:** Research-audited specification; owner decisions remain subject to explicit review, and every implementation claim must be supported by repository evidence  
**Intended reader:** Product owner, coding assistants, reviewers, future contributors  
**Primary repository:** `som76377-alt/omnimatrix` — `main`  
**Operating constraint:** $0 spend by default; optional external resources remain disabled until explicitly approved

> **Purpose:** This is a product specification, architecture contract, implementation order, and verification manual. It is not a single prompt. When code, an AI suggestion, and this document disagree, preserve evidence, stop destructive changes, and resolve the conflict through the change-control process in this document.

**Core product thesis:** Omnitrix is one dependable AI orchestration system with strong planning, communication, evidence, policy and recovery. It may use specialist agents, models, tools, services and execution environments, but it must not become a pile of disconnected role-labelled bots. The orchestrator owns the user's objective, policy, run state, approvals and final report. Specialists are replaceable components, not independent authorities.

**Confidentiality note:** Treat this document as a project artifact. Do not put API keys, passwords, private relationship or family details, sensitive personal memory, or raw private conversation transcripts in the public repository. Keep secrets local and outside Git. Only include user preferences in project memory if approved and useful to the project.

---

# 1. How to Use This Blueprint

## 1.1 Authority and decision labels

This blueprint distinguishes decisions supported by the available conversation history and inspected repository from recommendations and unconfirmed ideas. An assistant implementing the PRD must not silently promote a recommendation into a user decision.

| Label | Meaning | Implementation behavior |
|---|---|---|
| **DECIDED** | A stable requirement explicitly repeated or strongly established by the user / existing repository | Preserve unless the owner changes it; report any conflict before changing it. |
| **RECOMMENDED** | An engineering/product choice recommended in this blueprint after analysis | Implement when compatible with constraints; record a short ADR if the choice is costly or difficult to reverse. |
| **CANDIDATE** | A plausible feature or external product to evaluate | Do not build just because it appears here. Compare value, cost, risk and evidence first. |
| **DEFERRED** | Intentionally later than the first usable release | Do not drag into the MVP unless a critical dependency requires it. |
| **OPEN** | A decision is genuinely unresolved, or evidence is insufficient | Keep configurable or ask one focused question when it blocks a material decision. Never invent an answer. |
| **REJECTED FOR NOW** | A pattern was considered but conflicts with the product’s purpose / constraints | Do not reintroduce it without explaining what changed. |

## 1.2 How future assistants should operate

Before modifying Omnitrix, an AI coding assistant must:

1. Read this PRD’s current approved version, `BLUEPRINT.md`/architecture decisions if present, the repository README, relevant source modules, current Git status, recent commits and open PRs.
2. Check whether the capability already exists in code, in the tool registry, in a provider SDK, as a maintained library, or through an existing protocol integration. Search before building.
3. Write a small change plan stating files/components to touch, invariant to preserve, risk, tests, and rollback route. For material tasks, show the plan and obtain owner approval before mutations.
4. Make the smallest modular change that solves the accepted requirement. Never replace a subsystem merely because a new framework looks attractive.
5. Run the most relevant tests and then broader CI checks. Report exact commands and actual observed results; distinguish “not run,” “failed,” “passed,” and “not applicable.”
6. Inspect the diff for unrelated edits, leaked secrets, removed tests, new dependencies, license changes, and generated files. Open a branch/PR; do not force-push or merge without explicit authorization.
7. Update the PRD, an ADR, registry schema, tests or runbook when the change alters durable behavior. Documentation must describe the shipped behavior, not aspirations.

## 1.3 Evidence boundary: what was and was not recovered

This blueprint combines (a) the user’s durable Omnitrix direction available from prior conversation context, (b) selected Omnitrix-related notes/code transcripts retrieved from the available project library, (c) direct inspection of selected files from the current GitHub repository, and (d) external technical/product research listed in Appendix A. The current core code was directly inspected in `core/orchestrator/omnitrix.py`, `core/orchestrator/planning.py`, `core/orchestrator/task.py`, `core/router.py`, `core/models/base.py`, `core/models/registry.py`, `core/models/providers/bootstrap.py`, `core/tools/registry.py`, `core/tools/executor.py`, `core/tools/permissions.py`, and tests including `tests/test_core.py` and `tests/test_planning.py`.

**Important limitation:** the tooling did not expose a complete verbatim export of every historical conversation in one readable artifact. Therefore this document does **not** claim to have audited every single past message in full. It captures the known stable decisions and available artifacts; the “decision ledger” and “open questions” deliberately prevent missing history from being replaced by guesswork. If an older transcript or an existing file later surfaces that materially contradicts this document, preserve both sources and reconcile via an ADR rather than silently discarding evidence.

## 1.4 Document maintenance

The PRD is versioned. Every change should record version/date, changed sections, reason, evidence, and whether implementation/acceptance criteria changed. Large behavioral changes need an ADR. Small wording corrections do not. A new feature should normally add or extend one bounded module, a registry entry, tests and docs—not require rewriting the orchestrator core.

**Document acceptance checklist:** readable on a phone and desktop; headings searchable; linked primary sources; no hard-coded API keys; clear decisions versus candidates; concrete requirements with IDs; failure and recovery behaviors; explicit acceptance tests; implementation sequence; known gaps; and no claim that proposed work is already implemented.

---

# 2. Executive Summary

## 2.1 Product definition

Omnitrix is a **user-directed, evidence-driven AI operating and orchestration layer**. It accepts ordinary natural-language requests, distinguishes conversation/learning from intended action, plans work, chooses a suitable model/tool/runtime based on task requirements, coordinates bounded work, checkpoints progress, verifies outcomes, and explains what it did and did not achieve. Its interface begins as a text/chat workflow and is intended to become a polished Android application with a live, observable workspace for browser, terminal, files, code and other task environments.

The product can eventually support research, programming, writing, analysis, graphics, image/audio/music/video/animation, scientific visualization, game/APK builds and other capabilities. These are **capability modules** that plug into the common orchestration, permission, artifact and verification contracts. They are not separate apps with unrelated memory and policy.

## 2.2 Strategic correction

The system should not be designed around a permanent roster of shallow role-based bots (such as a generic coding agent, research agent, writing agent and so on) whose only difference is a prompt. The core advantage should be **excellent orchestration and communication**: accurate intent detection, strong decomposition, model/tool selection, shared typed task state, well-defined handoffs, independent verification, transparent progress, approval gates and graceful recovery. A specialist is justified only when it brings a meaningful skill, bounded context, different model capability, independent verification or a distinct execution environment.

## 2.3 Non-negotiable product principles

- **User intent remains sovereign.** The system proposes and explains; the model does not grant itself permissions.
- **Truth over performance theatre.** Never claim a command ran, file changed, source was verified, image was rendered, test passed or artifact was delivered without evidence.
- **Quality floor across all enabled modalities.** A capability used once a month is not allowed to produce knowingly substandard output. Prioritize features by demand and feasibility, not by lowering their quality requirements.
- **Modular and replaceable.** Models, tools, skills, storage, UI clients and workspace runtimes sit behind typed interfaces and versioned registries.
- **$0 means a hard default.** No paid API, managed sandbox, cloud GPU, paid account, unexpected token purchase or background deployment unless the owner explicitly switches it on. Free tiers are volatile and must never be treated as guaranteed infrastructure.
- **Human control of meaningful side effects.** File writes, GitHub changes, external sends, installs, public releases, deletions, purchases and access to sensitive data have specific policies and approval gates.
- **Recoverability is a feature.** Runs must pause, resume, retry safely, cancel, report partial completion, or ask for help without pretending a failure did not happen.
- **Observability without surveillance.** Make task progress and decisions inspectable while minimizing sensitive payload logging.

## 2.4 Recommended first useful release

The first release should demonstrate one honest end-to-end vertical slice—not a giant mockup. It should have a stable Python core, local configuration, at least one tested model adapter, deterministic tool permission enforcement, validated plan proposal, approval bound to the exact plan, execution with structured events, verifiable artifacts, a concise run summary, durable local state, tests and a usable terminal/chat interface. A minimal Android client can follow once the run/event API is stable. Live remote desktop streaming and voice remain later phases.

## 2.5 What success looks like

A user writes, “Research these three approaches, compare their source evidence, create a small prototype in the project workspace, run the relevant tests, and tell me what remains uncertain.” Omnitrix should identify an appropriate read/research/build workflow, show a plan and any risk boundary, reuse existing tools/libraries where possible, obtain approval for changes, isolate code execution, preserve intermediate work, test the result, show real logs/artifact references, recover from a failed tool if safe, and provide a final answer that labels facts, assumptions, failures and unverified claims. The same system should later support a non-coding creative task without bypassing the shared safety and verification architecture.

---

# 3. Product Goals, Non-Goals, and Success Measures

## 3.1 Goals

**G-01 — A single coherent orchestrator.** User asks once; Omnitrix decides whether to answer directly, use tools, propose a plan, delegate bounded subtasks or request clarification.

**G-02 — Useful orchestration, not agent theatre.** Each subtask/agent should have a named objective, input contract, output contract, allowed tools, budget/time limit and success criteria. Do not create extra agents solely to sound sophisticated.

**G-03 — Local-first and zero-spend by default.** The app and core should operate in a degraded/local mode where feasible without any mandatory paid service. External providers are optional adapters. Free remote models may still have quotas, outages, terms and privacy trade-offs.

**G-04 — Inspectable execution.** Every run exposes states and meaningful events, not an unexplained spinner. The user can inspect what is pending, active, blocked, completed, failed or waiting for approval.

**G-05 — Safe tool/action boundary.** Tool visibility to a model does not equal permission. Authorization happens in deterministic code for every execution, including nested/MCP tools and retries.

**G-06 — Extensible modalities.** A new skill registers its schemas, tools, artifact types and evaluators without rewriting the chat client or core scheduler.

**G-07 — Reusable project memory.** The project’s approved technical decisions and task artifacts survive conversation boundaries through Git-tracked documentation and durable local run state; private memories and secrets stay separate.

**G-08 — Quality evidence.** Tests, evaluations, artifact inspections and source links are part of the deliverable, not optional ceremony.

## 3.2 Non-goals for the initial release

- A fully autonomous, unrestricted agent that can do anything on the host.
- A multi-agent simulation in which all agents share the same permissions and make recursive handoffs without a budget.
- A custom foundation model, custom GPU machine, custom inference service or expensive self-hosted cloud cluster.
- A custom payment system, marketplace, plugin store or public multi-tenant hosted SaaS.
- Full desktop/phone remote control, always-on microphone, wake-word daemon and app automation in the first milestone.
- A mandatory dependency on CrewAI, LangGraph, Microsoft Agent Framework, OpenAI-only services, or another single vendor/framework.
- Unreviewed automatic GitHub merges/releases or executing arbitrary pull request code with privileged secrets.
- Storing every raw conversation forever under the vague label “memory.”
- Making claims of scientific correctness, commercial-grade creative quality or universal capability without task-specific validation.

## 3.3 Primary success metrics

Metrics are diagnostic tools, not vanity targets. Establish a baseline with real tasks before setting aggressive service-level goals.

| Metric | Definition | Initial acceptance target |
|---|---|---|
| Task completion rate | Accepted tasks whose user-defined success conditions pass / tasks attempted | Measure on a 20–30 task benchmark; no unsupported universal target before baseline. |
| Verified completion precision | Final claims supported by explicit evidence / all substantive completion claims | 100% in deterministic tests; no known false “success” claims. |
| Safe action rate | Mutating tool calls with valid scope/approval under applicable policy | 100% in tests; zero bypasses allowed. |
| Plan validity | Plans passing ID/dependency/schema checks | 100% of plans allowed to execute. |
| Resume integrity | Interrupted runs resume without repeating completed non-idempotent actions | 100% of fault-injection test cases. |
| Procurement efficiency | Percentage of capability requests satisfied by registered existing tool/library/integration before custom implementation | Track per feature; investigate all unnecessary reinventions. |
| Budget integrity | Paid calls made when spend mode is disabled | 0; enforced in code/config and tests. |
| Quality per modality | Output passes capability-specific acceptance tests | 100% for released capability’s required release gate. |
| Recovery clarity | Failure state, impact and next safe step explained | 100% in defined failure cases. |
| Maintainability | Adding a provider/tool/skill does not require unrelated core/UI changes | Demonstrated by extension contract tests and sample plugin implementation. |

## 3.4 North-star metric

**Verified user objective completion with preserved user control.** A “successful” run is not simply one where the model produced confident text; it is a run where the requested outcome meets the acceptance criteria, evidence is available, side effects were authorized, and remaining uncertainty is explicit.

## 3.5 Repository snapshot and implementation reality

A fresh read-only inspection of the public `som76377-alt/omnimatrix` default branch (`main`) was performed for this revision on 11 October 2026. The repository tree returned 84 entries. It contains the Python orchestration/planning/task modules, model adapters and registry, tool registry/executor/permissions, model configuration JSON files, and tests including `test_planning.py`, `test_plan_approval.py`, `test_plan_execution.py`, `test_router.py` and tool tests. The inspected `README.md` is currently only 12 bytes, `.env.example` is empty, and the default-branch tree did not expose `pyproject.toml`, a requirements file, or `BLUEPRINT.md` at the root. This does not prove such files cannot exist in another branch or untracked workspace; it means the current public `main` snapshot does not provide them as visible root-level project documentation/configuration.

**Implication for Phase 0:** before adding infrastructure, document the actual Python environment, supported Python version, dependency installation and lock strategy, exact test/lint/type-check commands, environment variables and safe local startup. Do not guess these commands from the PRD; recover them from the working development environment and CI, then verify them. Keep this repository snapshot time-bound: every implementation session must inspect the current branch, working tree, recent commits and tests again.

---

# 4. User Model and Key Journeys

## 4.1 Primary persona: single owner/operator

The primary user is the project owner, not an enterprise administrator. The experience must be understandable to a capable learner who may be new to software engineering. Explain system decisions plainly; avoid making the owner understand every implementation detail to use the tool. Advanced inspection (raw logs, model IDs, token counts, plan graph, tool arguments) should be available on demand.

## 4.2 Secondary personas

- **Reviewer / collaborator:** can inspect an artifact or plan, provide review, and approve a specific contribution only when explicitly granted access. Multi-user roles are future work.
- **Capability author:** adds a skill/provider/tool via documented interfaces and the procurement process. Must not need to alter the core run loop for a normal extension.
- **Maintenance operator (future):** monitors resource usage, model availability, migrations, policy versions and local runtime health.

## 4.3 Journey A — ordinary conversational question

1. User sends a message.
2. Intent classifier labels it as conversation/information, not action.
3. Omnitrix answers directly with a confidence/uncertainty explanation where needed.
4. It does not create an execution plan or run tools unnecessarily.
5. If fresh external research is needed, it explicitly uses the available search capability and separates source facts from reasoning.
6. The conversation is saved according to the configured retention setting, without storing secrets or inferred sensitive traits as durable project memory.

**Acceptance:** A harmless question does not trigger tool execution just because a tool is available; lack of evidence is disclosed.

## 4.4 Journey B — learn-only / observation mode

A free-form user message may be an idea, observation, preference, correction or ongoing thought rather than a command. In **Learn/Observe mode**, Omnitrix summarizes what it understood and may propose a memory update or follow-up question; it must not start a workspace, call write-capable tools, create a branch, modify a file or trigger external side effects. Memory updates remain reviewable and can be edited/deleted. Switching modes must be visible, not hidden behind an implicit assumption.

Example: “I’ve noticed I learn better when I build small examples before reading a full theory.” Expected behavior: acknowledge; optionally propose the preference “Prefer concrete examples before long theory”; wait for memory approval depending on memory policy. Do not silently execute anything.

## 4.5 Journey C — multi-step task with approval

1. User states an outcome and constraints.
2. Omnitrix classifies the request and identifies ambiguity that materially changes the execution.
3. The planner creates tasks with dependencies, cost/time limits, expected outputs, verification criteria and side-effect risk.
4. Plan validator rejects malformed dependencies, cycles, unknown tools, invalid schemas or incompatible scopes.
5. UI shows summary, planned steps, tools, workspace, external calls, changes expected and budget mode.
6. Owner approves the exact plan fingerprint and scopes.
7. Scheduler checkpoints before/after each task and emits structured events.
8. Verifiers compare observed outputs against per-task criteria.
9. A failure pauses the affected branch, preserves artifacts and offers a safe retry, replan or stop option.
10. Final report lists results, changed files, tests, sources, artifact links, failures and remaining uncertainty.

## 4.6 Journey D — add a new capability

User asks for a capability such as creating a scientific animation. The procurement process inventories existing implementations and libraries, checks licenses, quality, platform support and security, then recommends a minimal reusable adapter. Only after the owner approves the proposal does implementation begin. The capability is registered with input/output schema, resource needs, policy, validators and tests. It passes sandbox and evaluation gates before being enabled. A failed capability can be disabled in configuration without damaging unrelated features.

## 4.7 Journey E — visible workspace from Android

The Android app displays chat and plan progress by default. When a task needs an environment, user opens a Workspace panel showing browser/terminal/logs/files and the task’s active step. Android sends commands to the authenticated control plane; it does not directly execute privileged local actions. The workspace runtime is isolated and emits structured events and artifact references. Streaming is a view/input channel, not a new security boundary. Disconnecting the phone must not corrupt an execution or grant extra permissions.

## 4.8 Journey F — interrupted task recovery

Power failure, killed process, rate limit, invalid model output or network loss should put the run into a known state. On restart, Omnitrix reloads the last committed checkpoint and determines whether the last side effect is completed, idempotently repeatable, or uncertain. It never blindly repeats an uncertain non-idempotent action (for example, sending a message twice). It displays “unknown outcome—check before retry,” not a fabricated success/failure.

---

# 5. Feature Scope and Release Tiers

## 5.1 Tier definitions

**M0 — Core demonstrator:** Python CLI/chat, model abstraction, structured intent/plan, exact-plan approval, tool permissions, core calculator/filesystem tools in a confined test workspace, task events, test suite, local settings and factual final reports.

**M1 — Reliable personal assistant:** durable run history (SQLite), cancellation/pause/resume, retries/idempotency, procurement/catalog, artifact store, source-backed research tools, Git/GitHub adapter with least privilege, local-first model adapter (when hardware permits), run traces and benchmark suite.

**M2 — Android companion:** native Android chat, session history, plan review/approval, streamed event timeline, artifact browsing/download, status/reconnect/cancel controls; secure pairing/authentication.

**M3 — Interactive workspace:** per-task sandbox, browser and terminal, file pane, streamed logs/screens, session expiry, snapshot/restore and user-visible resource limits. Start with a simple embedded terminal/log viewer before full screen streaming.

**M4 — Capability ecosystem:** versioned skill manifests, procurement workflow, media and scientific tools, image/audio/video/3D/game/APK outputs with explicit validators and resource checks.

**M5 — Voice and deeper device integration:** push-to-talk first; speech-to-text, spoken replies and opt-in device actions; wake-word/continuous audio only after battery/privacy/security study.

Tiers represent dependency order, not mandatory marketing releases. Each phase needs a vertical slice, tests and rollback. Do not build all tiers at once.

## 5.2 MVP inclusion matrix

| Capability | M0 | Why / boundary |
|---|---:|---|
| Direct chat without tools | Yes | Proves the base interaction and prevents unnecessary automation. |
| Model abstraction / adapter contract | Yes | Required to preserve provider choice. |
| Capability-based model routing | Yes, basic | Prefer deterministic eligibility rules before learned optimization. |
| Proposal and plan validation | Yes | Existing implementation foundation. |
| Exact-plan approval/fingerprint | Yes | Existing foundation; tests must keep it. |
| Tool registry and deterministic authorization | Yes | Existing foundation; permissions must fail closed. |
| Structured task states and event records | Yes, simple | Necessary for transparency and later clients. |
| Persistent resumable state | Start local | SQLite or equivalent, not cloud dependency. |
| Search/research with citations | M1 | Must distinguish source output from model-generated analysis. |
| Existing-tool procurement | M1 foundation | Manual indexed search first; semantic ranking later. |
| Android chat | M2 | Start when API/event contract is stable. |
| Live interactive browser/terminal | M3 | Requires sandbox and auth first. |
| Voice and wake word | M5 | High privacy/battery complexity. |
| Always-on autonomous learning | No | Replace with opt-in, user-reviewable learn-only mode. |
| Unrestricted host shell | No | Sandbox and risk-scoped command policies required. |
| Paid cloud by default | No | Directly conflicts with zero-cost constraint. |

## 5.3 Feature priorities

Use **P0** for safety/data integrity/core viability, **P1** for first useful release, **P2** for meaningful follow-on, and **P3** for experimentation. A feature’s priority does not reduce its quality bar once enabled. A P3 video generator must meet the chosen video-specific quality acceptance criteria before claiming production readiness.

---

# 6. Product Principles and Invariants

These invariants are architecture tests. Changes that violate them are regressions even if the demo looks better.

1. **One canonical run state.** UI clients, agent components and provider adapters read/subscribe to state; none invent their own conflicting status.
2. **One deterministic policy authority.** A model, agent, MCP server or UI cannot grant permissions to itself.
3. **Tool outputs are data.** Retrieved webpages, repository files, model outputs and shell logs never override system policy merely because they contain instructions.
4. **No action without a valid scope.** Every execution resolves tool identity, schema, capability, risk, allowed target, expiry and run context.
5. **Approval binds to what will execute.** A plan approval is invalid when its content, target, tool scopes, or materially relevant policy changes. Fingerprints must cover all approval-sensitive fields, not just human-readable task labels.
6. **No silent change in intent.** If the proposed work materially exceeds the requested goal, ask for approval or refuse the extension.
7. **Explicit success criteria.** Every nontrivial task needs an observable success signal or must be reported as unverified.
8. **Durable checkpoints.** A step should have a before/after record, completion result, artifact refs and idempotency characteristics.
9. **Safe failure is still useful.** Failure should preserve state and work, explain what failed, and identify the next safe action.
10. **Configurable by manifest, not scattered conditionals.** Add providers and skills through registries/adapters whenever possible.
11. **Optional subsystem failure stays local.** If voice, live streaming, one provider, or one plugin fails, ordinary chat and other capabilities continue where possible.
12. **No mandatory paid component.** Any optional paid integration must have explicit cost and privacy disclosures and be disabled by default.
13. **No modality has a token-only quality gate.** Validate observable artifact characteristics as well as model text.
14. **Safe transparency.** Show useful state and decisions; redact secrets, tokens, personal content and protected paths from routine logs.
15. **Reversibility.** New features are removable behind interfaces, config flags or provider disablement with migrations and rollback documented.

---

# 7. Recommended System Architecture

## 7.1 Architecture choice

**RECOMMENDED: a modular monolith for the control plane, with isolated worker/workspace processes where needed.** The current project is early and the resource budget is zero. Splitting the entire product into network microservices now would add deployment, observability, security and debugging overhead before scale requires it. Keep clear Python package boundaries, typed contracts and events; split only the untrusted execution runtime and optional stream gateway into separate processes when required. That preserves easy local development and creates clean future extraction points.

![Logical Omnitrix architecture](diagrams/architecture.png)

## 7.2 Architectural layers

1. **Client layer:** initially CLI/test harness; later Android Compose app. Client sends intents and displays canonical run state. It never decides whether actions are authorized.
2. **API/session layer:** authenticated session creation, conversation/run endpoints, event streams, schema validation, cancellation, approval submission and artifact access. A transport adapter may support CLI, local HTTP, WebSocket/SSE and later another client without moving business logic into the UI.
3. **Application/orchestration layer:** intent classification, plan proposal, plan validator, execution scheduler, model router, policy engine, approvals, result verifier and final response composer.
4. **Domain layer:** typed models for run, task, plan, dependency, tool call, permission grant, artifact, evidence record, memory record, event and provider capability. Keep it mostly independent from external SDKs.
5. **Integration layer:** model adapters, search, GitHub, filesystem, media processing, MCP client/server adapters, browser automation, local model endpoint and other tools. Each integration has an adapter and schema.
6. **Runtime layer:** a per-task sandbox/worker for generated code, browser interaction, builds, media rendering and other side-effectful work. It has bounded filesystem mounts, network rules, CPU/memory/process/time limits and narrowly scoped credentials.
7. **Persistence layer:** SQLite first for local transactional state and migrations; artifacts stored separately with content hashes/metadata. Move to another database only when concurrency or operational needs justify it.
8. **Observability/evaluation layer:** structured event log, privacy-filtered logs, traces and metrics, test/evaluation datasets and artifacts. The app must remain useful when advanced observability integrations are disabled.

## 7.3 Core runtime sequence

![Run lifecycle](diagrams/lifecycle.png)

1. Normalize the user request and session/mode context.
2. Classify as ordinary answer, research, task requiring tools, multi-step plan, learn-only observation, cancellation, or clarification-needed.
3. Derive required capabilities, sensitivity, risk level, quality bar, constraints, resource budget and verification plan.
4. Query procurement/catalog for suitable existing capabilities. Do not search for generic tools if no tool is required.
5. Select eligible model/tool/runtime candidates using deterministic capability and policy filters.
6. Generate proposed plan/steps through a model only as suggestions; validate all structure in code.
7. Determine whether auto-execution is allowed or approval is required; show exact plan, scope, expected side effects and cost state.
8. Persist approval and run state; execute eligible tasks in dependency order; parallelize only when dependencies, shared-resource conflicts and budgets allow it.
9. Verify each result from independent evidence, not a model’s assertion alone.
10. Commit checkpoint/artifact metadata and emit events after each state transition.
11. Compose the final response from verified facts, tool observations, source links and unresolved issues.

## 7.4 Component contracts and dependencies

| Component | Owns | Must not own |
|---|---|---|
| `IntentClassifier` | Select interaction mode and initial capability needs | Tool execution or hidden mutation. |
| `PlanBuilder` | Propose a plan from objective + constraints | Approval, permissions or direct side effects. |
| `PlanValidator` | Validate IDs, dependencies, schema, scope references and budgets | Guess missing dependency semantics. |
| `PolicyEngine` | Evaluate authorization, risk tier, spend mode, data policy and approval rules | Natural-language-only decisions. |
| `ModelRouter` | Return eligible model candidates / selected model | Tool permissions or user approval. |
| `ProcurementService` | Search catalog for existing tools/libraries/providers and record evidence | Automatically install untrusted software. |
| `Scheduler` | Execute validated steps with bounded concurrency/checkpoints | Bypass PolicyEngine or mutate plan after approval. |
| `ToolExecutor` | Revalidate scope and execute one registered tool | Trust a model’s tool-call argument without schema checking. |
| `WorkspaceManager` | Provision/expire sandbox and artifact mounts | Expose host root or unrestricted secrets. |
| `Verifier` | Compare outputs to explicit success criteria | Mark success because an agent says “done.” |
| `MemoryService` | Retrieve/update user-approved durable records | Store all conversation content as memory by default. |
| `EventPublisher` | Emit versioned, sanitized run events | Change business state on the client’s behalf. |
| `FinalReporter` | Present results and limitations | Invent results or cite sources never accessed. |

## 7.5 Architecture anti-patterns to avoid

- One giant `omnitrix.py` with all routing, providers, tool code, database logic and Android state.
- A free-form agent-to-agent chat with no typed outputs, scheduler or stopping rule.
- Agent count as a success metric.
- `if provider == ...` scattered through orchestrator and UI instead of a provider factory/adapter.
- Hard-coded model names, tool lists, feature flags and provider secrets across multiple files.
- Putting plugin code directly in the API process with unrestricted Python and file access.
- Letting the UI pass raw shell commands directly to a privileged host executor.
- Using vector database as the only memory source before a simple structured/project-doc strategy is proven.
- Microservices, Kubernetes, cloud streaming, distributed queues or a custom model gateway before a tested local end-to-end flow exists.

---

# 8. Orchestration Model, Specialists, and Communication

## 8.1 One orchestrator, multiple bounded workers

**DECIDED:** Omnitrix should become stronger by orchestrating and communicating well, rather than depending on an arbitrary count of role-specific agents.

The main orchestrator is the only authority that can accept the user's objective, establish run policy, commit plan state, authorize tool use, decide whether to pause for approval, and write the final completion report. A specialist/worker is a bounded executor invoked for a concrete reason. Workers return a typed result and evidence bundle; they do not speak as independent products or obtain new permissions through conversational negotiation.

Useful specialist patterns include:

- **Planner:** proposes task decomposition and dependencies; never executes during proposal.
- **Research/evidence worker:** gathers source material and returns URLs, dates, supported claims, conflicts and source quality.
- **Implementation worker:** changes only an assigned workspace/branch and returns a diff, test results and artifact references.
- **Independent reviewer/verifier:** checks an output against explicit requirements, ideally without simply inheriting the implementer's narrative. Use a different method/model when that adds real independence.
- **Librarian/Procurement worker:** inventories existing code, packages, tools, APIs and licenses before recommending a new implementation.
- **Media/science capability worker:** invokes a typed workflow for a particular modality such as audio render, 3D scene or scientific plot; must attach output and modality-specific checks.

These are capability patterns, not mandatory permanent agents. A deterministic function may be preferable to a second LLM. Agent delegation is justified only when complexity, quality, parallelism, independence or tool separation materially benefits the task.

## 8.2 Specialist contract

Every specialist invocation must receive a `WorkerRequest` containing `run_id`, `task_id`, `attempt_id`, correlation/trace ID and contract version; objective and in/out-of-scope statements; only required context/dependency artifacts with trust labels; output schema and success criteria; eligible model capability class, tool handles and data scope; timeout/token/compute budget; cancellation token; and retry rules. No raw secret is included in the request unless a narrowly scoped tool needs it through a protected credential handle.

It returns `WorkerResult` with status, structured output, evidence references, artifacts, usage where available, warnings, proposed follow-ups, failure category and whether work is safe to retry. Free-text rationale is advisory; the scheduler trusts the structured status and verifier evidence more than persuasive language.

## 8.3 Communication model

Use two layers of communication:

1. **Control plane (typed state/events):** durable task states, dependency results, approval requests, cancellation, budget exhaustion, artifact registration and policy decisions. A state transition is validated in code.
2. **Content plane (model messages/artifacts):** text, source excerpts, file diffs, images, audio, video, 3D scene descriptions or other work products. It is data, not a control directive.

A worker cannot create a task by sending arbitrary chat text to the orchestrator. It must return a structured `proposed_follow_up`, which is reviewed by the scheduler/policy engine. Only the scheduler can enqueue work.

## 8.4 Handoff contract and stopping rules

Handoffs are explicit and bounded: researcher → synthesis → source-checking verifier; or implementer → independent reviewer. Each handoff specifies schema, context budget, known conflicts and required checks. Do not copy the entire conversation to every worker. Pass task-relevant context and durable artifact handles.

A handoff fails closed if the receiver is disabled, fields are missing, capabilities are unsupported, budget is exhausted or trust scope is incompatible. The parent run keeps ownership and provides the user-facing result.

- Maximum plan steps, worker invocations, model turns, retries, wall time and compute usage have configurable defaults and safe caps.
- No worker may recursively delegate without an orchestrator-issued child-task token and budget.
- Repeated identical failure signatures trigger a circuit breaker and pause.
- New dependencies created by a worker are proposals, not executable work.
- Stop when acceptance criteria pass, the user cancels, a critical policy condition is hit, budget is exhausted, a human decision is required, or further action has low expected value.
- If an answer can be given accurately without delegation, do not create a multi-agent plan just for appearance.

## 8.5 Framework policy

Frameworks such as Microsoft Agent Framework, Google ADK, LangGraph and OpenAI Agents SDK offer useful patterns for typed workflows, human-in-the-loop pauses, checkpoints, handoffs and tracing [S01–S04]. **Recommendation:** borrow proven patterns and keep Omnitrix's contracts stable. Introduce a framework only behind an adapter/prototype after a comparative test demonstrates improved correctness or maintainability. Do not migrate the early core wholesale just because a framework offers more abstractions. Re-evaluate this decision at M1, once durability and event contracts are measured.

---

# 9. Run State, Planning, Scheduling, and Recovery Semantics

## 9.1 Current foundation and gap

The repository already has a useful planning foundation: immutable `PlannedTask` and `TaskPlan`, graph validation for duplicate IDs, missing dependencies, self-dependencies and cycles, dependency readiness, deterministic plan fingerprinting, `PlanApproval`, and tests including long dependency chains. `Omnitrix.propose_plan()` validates model JSON structure, `preview_plan()` provides an execution order, and `execute_approved_plan()` checks a fingerprint before execution. Preserve and extend this work.

The repository now demonstrates a **partial durable execution foundation**, but not complete recovery. The current implementation includes a versioned SQLite journal (schema v5) for runs, tasks, attempts, events, approvals, artifact metadata and tool executions; opt-in integration around `run()` and `chat()`; a durable duplicate-execution fence; deterministic logical action keys scoped to a run/task/action; append-only reconciliation assertions; read-only recovery snapshots and conservative recovery classification; and file-backed plus real-subprocess crash-window tests. Schema v4 added append-only checkpoint records with canonical SHA-256 payload digests, while `RecoveryService.inspect()` validates checkpoint digests/sequence and run/task/attempt/tool relationships before classification. The live orchestrator now persists ordered boundary checkpoints before and after model calls, around tool calls, and when task result/failure is observed; payloads contain hashes and minimal metadata, not raw prompt/response/tool content. A subprocess crash test verifies a committed model-boundary checkpoint survives process exit. A second fault-injection test performs a simulated side effect, terminates the process before tool-outcome persistence, and verifies that the reopened journal reports an uncertain running tool requiring reconciliation. The runtime also exposes a manually confirmed restart-from-objective path for interrupted single-task runs only when the journal is intact and no tool dispatch occurred; it creates a new attempt under the same run/task identity. Chat turns and any run with tool execution history remain blocked. A further subprocess test crashes after a tool's terminal outcome is committed but before the orchestrator consumes the result, verifying that the record survives and objective-only restart still refuses to replay it. The CLI now supports recent-run listing without exposing objective payloads, read-only recovery inspection, optional journal-backed chat, and a confirmation-gated restart command. A one-shot journaled `--run-objective` mode also returns the new run ID with its result, making eligible run records discoverable for later inspection/recovery. Schema v5 adds a `tool_result_snapshots` table: only explicitly opted-in tools using `deterministic_json_v1` can persist successful finite-JSON outputs of at most 16 KiB. The calculator is currently the only default tool opting in; all other tools default to `never`. Snapshot payloads carry a SHA-256 digest, retrieval verifies the digest, and the terminal outcome plus snapshot are committed atomically. This makes selected results available for future restoration but does not reconstruct conversation/provider state or resume execution. A read-only `resolve_replay_candidate()` lookup now checks exact run/task/logical-action/tool/request identity, requires exactly one matching execution with terminal success, and returns the snapshot only after integrity verification; missing, mismatched, uncertain, or ambiguous candidates return blocked dispositions without output. This is still not live restoration: it does not prove the current model conversation position or reconstruct provider continuation state.

These foundations must not be overstated. Automatic run restoration, event replay into live execution, pause/cancel/resume, automatic retry, provider-state reconciliation, independently validated tool-specific evidence, sandbox management, mobile authentication, and the Android/live-workspace clients remain incomplete. The journal is opt-in. The current logical action ID uses tool-loop iteration and response position; it is conservative and requires the same action sequence to be reproduced. A reconciliation record is an auditable assertion, not proof of an external state. See `docs/ROADMAP.md` and `docs/RECOVERY_STATE_MACHINE.md` in the repository for the implementation boundary and recovery dispositions.

## 9.2 Run and task state model

Recommended `RunStatus` values:

- `CREATED` — request accepted and assigned an ID.
- `CLASSIFYING` — interaction mode and constraints are being derived.
- `PLANNING` — plan being proposed and validated.
- `AWAITING_APPROVAL` — specific action or plan requires owner approval.
- `READY` — valid and authorized work can begin.
- `RUNNING` — one or more tasks are active.
- `PAUSED` — user/operator paused, a human response is needed, or a client disconnected and policy says pause.
- `RECOVERING` — checking checkpoint/provider/runtime after interruption.
- `VERIFYING` — work completed but acceptance criteria are not yet proven.
- `SUCCEEDED` — required criteria passed or an explicit answer-only path is sufficient.
- `PARTIAL` — some value delivered but one or more required parts remain incomplete.
- `FAILED` — work cannot safely continue without new input or repair.
- `CANCELLED` — stopped at user/operator request; completed side effects remain documented.
- `EXPIRED` — retention policy closed the run and artifacts were handled according to policy.

Recommended `TaskStatus`: `PENDING`, `READY`, `WAITING_APPROVAL`, `RUNNING`, `CHECKPOINTING`, `VERIFYING`, `SUCCEEDED`, `FAILED_RETRYABLE`, `FAILED_FINAL`, `BLOCKED`, `CANCELLED`, `SKIPPED`. Keep retryable attempt failure separate from permanent failure. Do not conflate “waiting for approval,” “provider unavailable” and “failed.”

## 9.3 Plan data required for approvals

An approval-safe fingerprint must bind to more than task descriptions. Include canonicalized task IDs/descriptions/dependencies and concurrency groups; input and dependency artifact IDs plus content hashes; tool names/version/schema hashes; allowed capabilities/scopes and target paths/resources; model/provider class when data handling is affected; workspace/network permissions; expected side effects and resource/time budgets; verification criteria; policy version/risk tier; approval expiry; and external destination/repository/branch/recipient where applicable.

A plan approval is invalid if any approval-sensitive field changes. The UI shows a readable plan diff and requires re-approval. An expired or revoked approval is unusable. This extends the current fingerprint mechanism: review whether every field that changes execution behavior is covered.

## 9.4 Scheduling rules

- Execute sequentially initially for simplicity, but structure the graph so independent tasks can later fan out.
- Parallel tasks require independent writes or explicit resource-lock definitions. Shared files, branches, databases, devices and GPU memory are conflict resources.
- Pass dependency data by immutable artifact/reference or typed result rather than enormous concatenated strings.
- A downstream task may run only when required dependencies are verified-success, not merely when a worker returns.
- If a task fails, stop its dependent tasks. Independent tasks may continue only when policy says the partial state is safe.
- Record skipped tasks and why they did not run.

## 9.5 Durable checkpoint model

Persist before running any operation with meaningful side effects. Minimum checkpoint fields: `run_id`, `task_id`, `attempt_id`, status, checkpoint schema version, start/update timestamps, input/artifact fingerprints, policy/approval ID, tool/model references, retry count, last completed step, result/error category, next-action recommendation and side-effect/idempotency state.

Write state transactions so process death between tool result and event emission can be reconciled. For a build, checkpoint branch/workspace and commit ID; for external API requests, record idempotency key/provider request ID/outcome state; for a render, record command, input hashes, output hashes and validation results. An outbox-style pattern or transactional event write can keep database state and event stream consistent.

## 9.6 Retry, idempotency, and cancellation

Classify operations:

- **Pure/read-only:** normally safe to retry with exponential backoff and jitter within a retry cap.
- **Deterministic replace/write:** safe only with a known target, version check, content hash and overwrite rules.
- **Idempotent external operation:** retry only if the API guarantees idempotency or Omnitrix uses a stable idempotency key.
- **Non-idempotent operation:** do not blind retry after ambiguous outcome; reconcile by reading state or ask the owner.
- **Irreversible/high-risk operation:** explicit approval per operation and a documented cancellation boundary; provide a compensating action only if one truly exists.

Cancellation stops scheduling new tasks and sends best-effort cancellation to the active worker. If a subprocess cannot be interrupted safely, signal stopping, wait within a bounded grace period, then terminate only inside sandbox policy. Persist status and report completed side effects.

## 9.7 Approval workflow

![Trust boundaries](diagrams/trust.png)

Approval events originate from an authenticated user action on a visible plan version. Store approving session/identity, plan fingerprint, policy version, exact scopes, timestamp, expiry and optional note. Approval must not leak from one run into another. Reusable grants may cover narrow actions—for example, read-only access inside one active project folder—but never arbitrary future activity.

## 9.8 Run-engine acceptance criteria

- Invalid graph/schema never executes.
- Tampered fingerprint never executes.
- Policy change that invalidates scope forces re-evaluation.
- Crash after pure computation resumes without unnecessary repeated work.
- Crash after an external request with unknown outcome triggers reconciliation or human review.
- Cancel stops enqueuing steps and states which side effects finished.
- Failed prerequisite blocks dependent work and clearly records skips.
- Budget exhaustion pauses safely and never switches to a paid provider silently.
- Every terminal run has a final record and user-readable explanation.

---

# 10. Model Registry, Routing, and Provider Adapters

## 10.1 Current state

The repository has `ModelDefinition` and `ModelRegistry` with name, provider, model ID, declared capabilities, context window, enabled flag and metadata. `ModelRouter` filters enabled models by capability/context requirements and delegates selection to a routing policy. A provider-independent `ModelAdapter` normalizes responses. The inspected adapter bootstrap currently registers a Google provider builder. This is a useful extension seam; it does not mean every provider listed in this PRD is already implemented.

## 10.2 Model capability schema

Enrich the model manifest/config through additive, backward-compatible fields. Example:

```json
{
  "schema_version": 1,
  "models": [
    {
      "name": "local-default",
      "provider": "ollama",
      "model_id": "configured-by-owner",
      "enabled": false,
      "capabilities": ["reasoning", "tool_calling"],
      "context_window": null,
      "modalities_in": ["text"],
      "modalities_out": ["text"],
      "privacy_class": "local",
      "cost_mode": "zero_cost_only",
      "health_policy": "probe_on_use",
      "timeout_seconds": 60,
      "metadata": {"notes": "Enable after local runtime and hardware checks"}
    }
  ]
}
```

This is an illustrative shape, not a claim that the current loader supports these fields. Unknown fields should be safely ignored only where schema version allows; incompatible major schema versions should produce a clear error. Provider credentials stay out of this file and out of Git.

## 10.3 Routing requirements

Routing filters before ranking. Hard eligibility filters: required capabilities and modalities; allowed data-egress/privacy class; spend mode and remaining budget; context window/output limit; provider/model enabled and healthy status; structured-output/tool-call support; task policy, reliability and latency bounds.

Only eligible candidates are scored. Initial transparent ranking: capability fit → privacy/cost compliance → health/availability → task-specific quality class → context adequacy → latency. `FirstCandidatePolicy` may remain for test fixtures; it should not be the only production policy once several providers exist. Candidate reasons and rejections should be inspectable.

## 10.4 Provider adapter contract

Adapters normalize generation, structured output, tool-call representation, usage reporting, timeout/cancellation where available, error classification and health feedback. Provider-specific request shapes remain inside the adapter. Normalize errors into `AUTHENTICATION`, `RATE_LIMIT`, `QUOTA_EXHAUSTED`, `TRANSIENT_NETWORK`, `UNAVAILABLE`, `INVALID_REQUEST`, `UNSUPPORTED_CAPABILITY`, `POLICY_BLOCK`, `MALFORMED_RESPONSE` and `UNKNOWN`.

- Retry transient errors only within a bounded policy.
- Do not retry invalid schema/context failures unchanged.
- A malformed structured plan may receive one constrained repair attempt; if still invalid, pause and report the model’s failure.
- Do not route around legitimate safety constraints by switching models.
- Unknown errors retain a sanitized diagnostic ID and must not trigger risky fallback.

## 10.5 Fallback rules

Fallback is not merely “call the next model.” Check the next model’s privacy class, cost limit, input/output modalities, context length and reliability. Never send sensitive project content from a failed local model to a remote model unless the policy explicitly permits it and the UI discloses the transfer. With hard zero-spend mode, stop when billing behavior or provider quota is uncertain rather than using an unverified billable route.

## 10.6 Local inference and free tiers

Ollama provides local model APIs and an OpenAI-compatible subset [S06]. Local inference may reduce recurring spend and improve data control, but feasibility depends on laptop RAM/VRAM, model size, latency, disk, power and concurrent workloads. Benchmark hardware before promising quality or speed. Do not auto-download multi-gigabyte models; estimate storage/RAM and ask before downloads. Register text, embedding, vision and audio models as different capability classes.

Remote free quotas are volatile. The official Hugging Face pricing page describes free inference credits as subject to change and separately documents pay-as-you-go behavior [S07]. Therefore all external provider calls must pass a spend guard. Use `spend_mode = "zero_cost_only"` by default; separate `user-provided-free-quota` from `paid` as distinct trust/billing states; do not allow a provider to silently charge after a free quota runs out. If cost cannot be determined, mark the provider `cost_unknown` and disable it in strict mode.

## 10.7 Rate, quality and budget control

Per run, set maximum model calls, total wall time, approximate tokens/compute, output size and retries. Provider estimates are not a guarantee. Record actual usage if the API returns it. An independent global budget guard rejects requests once the cap is met. No worker can create budget by delegating. A degraded response is better than an unexpected charge.

## 10.8 Model evaluation matrix

Benchmark candidates on a fixed private task set covering direct answers, JSON/schema adherence, tool argument correctness, source-supported research, long context, coding/testing, refusal/permission behavior, latency, memory use and cost. Rate each on outcomes, not brand claims. Keep evaluation prompts/task data versioned and do not expose secret benchmarks to untrusted providers. A candidate model can be enabled for one task class and disabled for another.

---

# 11. Librarian / Procurement Agent and Tool Catalog

## 11.1 Mission

**DECIDED:** Omnitrix should check whether a maintained tool, library, existing project module, provider API or protocol integration already solves a requested problem before commissioning custom code. The Librarian/Procurement Agent is a research-and-recommendation capability that protects time, reliability and maintainability; it must not have automatic permission to install code, alter the project or enable new providers.

## 11.2 Procurement workflow

1. **Capability statement:** describe the requested outcome, supported inputs/outputs, environment, quality threshold and constraints.
2. **Internal inventory:** search the current codebase, existing registry, lockfiles, Git history, project docs and enabled tools first.
3. **Existing integration scan:** search maintained packages, official SDKs, available MCP servers, command-line tools and provider APIs. Look for a library before writing a wrapper; look for a registered tool before writing a duplicate.
4. **Evidence:** record source URLs, exact package/repository, version/release recency, license, maintenance signals, platform support, dependencies, network/data behavior, CVE/security notes and whether the source was actually inspected.
5. **Fit/risk comparison:** compare at least one existing solution with a small custom implementation when useful. Explain what is not satisfied by the existing option.
6. **Decision:** reuse existing tool; wrap it with an adapter; extend a local module; or propose new implementation. Include fallback/disable route.
7. **Approval:** install dependencies only after explicit plan approval if installation changes environment/lockfiles or introduces trust risk. No silent `pip install`, `npm install`, binary download or postinstall execution.
8. **Integration:** define schema, permissions, sandbox requirements, observability, output artifacts and tests before implementation.
9. **Registration:** add a catalog manifest entry and tests. Do not make a plugin discoverable to a model before it passes validation/policy registration.
10. **Retrospective:** record what was reused, what was custom, and why. If later evidence shows the component is obsolete, plan a migration rather than patching indefinitely.

## 11.3 Procurement decision rubric

Score options from 0–5 on: feature fit (25%), reliability/maintenance (15%), security/isolation (15%), license compatibility (10%), integration effort (10%), quality/output control (10%), resource/cost fit (10%), portability/reversibility (5%). These weights are an initial rubric, not a mathematically objective truth. A security/license disqualifier overrides the sum. Record evidence and confidence for each score; avoid false precision from unsupported ratings.

**Reject/hold an option** if the license is incompatible or unknown for intended use, project is clearly abandoned for critical functionality, dependency downloads/execution are opaque, it demands more privilege than needed, it does not support the required output quality, or it creates unavoidable paid usage. “Popular” is not proof of correctness or security.

## 11.4 Tool catalog schema

Create a versioned `tools_registry.json` for discovery metadata, but do not treat JSON as the implementation or sole permission authority. Tool executable implementations remain modular Python packages/adapters. Catalog example:

```json
{
  "schema_version": 1,
  "tools": [
    {
      "id": "filesystem.read_text",
      "version": "1.0.0",
      "title": "Read text file",
      "description": "Read a text file from an explicitly scoped workspace.",
      "provider": "builtin",
      "implementation": "core.tools.filesystem:ReadTextTool",
      "input_schema": {
        "type": "object",
        "properties": {
          "workspace_id": {"type": "string"},
          "relative_path": {"type": "string"}
        },
        "required": ["workspace_id", "relative_path"],
        "additionalProperties": false
      },
      "capabilities": ["workspace.read"],
      "risk": "low",
      "data_egress": "none",
      "idempotent": true,
      "timeout_seconds": 10,
      "enabled": true,
      "verification": ["path_within_workspace", "utf8_read_succeeded"],
      "license": "project-owned",
      "health_check": "builtin"
    }
  ]
}
```

The manifest must be schema-validated on startup and whenever refreshed. `implementation` import targets from external/untrusted manifests are forbidden by default. Third-party plugins are mapped by trusted configuration to registered adapters; a JSON file must never become an arbitrary Python import/code execution mechanism.

## 11.5 Required catalog fields

Every production tool entry needs stable ID and version; clear description; JSON Schema input/output contract; provider/implementation type; required capabilities; risk tier; idempotency/retry semantics; target/path constraints; timeout and resource caps; network/data egress disclosure; secret requirements using credential handles; license/provenance and installed version; health check; error taxonomy; output artifact types; verifier(s); lifecycle status (`candidate`, `enabled`, `disabled`, `deprecated`, `revoked`); and test reference. Fields can be added compatibly; breaking schema changes require a version migration.

## 11.6 Registry lifecycle and duplicate avoidance

`DISCOVERED → REVIEWED → APPROVED → INSTALLED/AVAILABLE → VALIDATED → ENABLED → DEPRECATED/REVOKED` is the normal lifecycle. A tool discovered by search is not immediately callable. Duplicate detection considers purpose, input/output schema, source/library name and behavioral equivalence—not only string names. If two tools overlap, choose one canonical adapter and document an alternate only if it provides real value (for example local vs remote). Keep aliases for backward compatibility and never change the behavior under an existing tool ID silently.

## 11.7 MCP and agent interoperability

Model Context Protocol (MCP) is a useful integration protocol for exposing tools and resources across compatible clients/servers. Treat each connected server as an external trust boundary: inventory tools, inspect schemas and annotations, validate arguments/results, enforce permissions locally, and use explicit authorization for resource access. Tool descriptions are not security policy. The current MCP security/authorization guidance emphasizes secure authorization, least privilege and protection against confused-deputy/token handling problems [S08–S09].

A2A may be evaluated for exchanging structured tasks between independent agents/services [S10], but it is not needed for the first release. Do not adopt a protocol simply because it is fashionable; every protocol increases auth, identity, versioning, observability and recovery requirements.

## 11.8 Procurement acceptance criteria

- When a registered tool already matches the requirement, the workflow recommends it before custom implementation.
- A discovered package is not installed or executed without authorization.
- Each enabled tool has validated schemas, declared scopes, timeout, error categories and test cases.
- A malicious manifest cannot import/execute arbitrary code.
- Revoking a tool removes it from model-visible tool definitions and executor allowlists immediately for new calls.
- Missing/invalid registry data fails with a readable diagnostic; it must not fall back to “allow everything.”

---

# 12. Memory, Project Knowledge, and GitHub as Shared Context

## 12.1 Three distinct memory types

Do not mix these stores:

1. **Conversation history:** the dialog needed for current conversational continuity; retention is configurable.
2. **Durable user preferences / personal memory:** explicitly approved, editable and deletable; avoid sensitive inference and never treat project discussion as permission to store every personal detail.
3. **Project knowledge:** PRD, architecture decisions, plans, implementation notes, testing evidence, dependency catalog, runbooks and code history, versioned with the project repository.

A fourth store—**run state and artifacts**—is transactional execution history, not natural-language “memory.” Store its structured fields locally with retention controls. Keep separate database tables/namespaces and permissions for each category.

## 12.2 What should be written to GitHub

Good candidates: `README.md`, `PRD.md`, `ARCHITECTURE.md`, `docs/adr/ADR-xxxx.md`, `docs/runbooks/`, `docs/research/`, schema examples, redacted incident reports, benchmark definitions that are safe to publish, and reproducible tests. Avoid raw full conversations by default: they may contain private information, irrelevant turns, credentials, or unreviewed claims. Use short decision summaries linked to a source transcript kept privately only when necessary and permitted.

## 12.3 Knowledge hierarchy

When information conflicts, use this precedence unless an ADR states otherwise:

1. Explicit latest owner decision recorded in the decision log.
2. Current approved PRD and accepted ADRs.
3. Current source code and tests (evidence of behavior, not necessarily desired behavior).
4. Current issue/PR scoped to an approved change.
5. Older project notes/transcripts.
6. Assistant-generated summary, unverified memory or provider output.

A detected conflict becomes a visible `DECISION_CONFLICT` event and a proposed resolution. Do not silently overwrite “frozen” project constraints.

## 12.4 Retrieval and memory write policy

- Retrieve the smallest useful context set; prefer search over injecting whole files into every prompt.
- Attach source path, commit SHA, timestamp and trust class to retrieved project knowledge.
- Use a memory write proposal showing exact text, category, reason, retention and delete option.
- Never infer long-term user preference from a single ambiguous sentence without confirmation.
- Do not store API keys, passwords, auth cookies, full environment dumps, private identifiers or sensitive personal material in ordinary memory.
- Use deterministic project files first; add embeddings/vector search only if measured retrieval misses justify it. Keep indexed records rebuildable from source files.
- Mark stale material as stale and prefer latest code or decision records; do not let an old transcript silently outrank current source.

## 12.5 GitHub workflows and permissions

Use branches and pull requests for substantive code changes. A clean change path is: issue or plan → feature branch → scoped edits → tests/lint/security checks → reviewer diff → approval → merge → release note/PRD update. GitHub OAuth/token scopes must be minimal and per-purpose. Local repository commits and remote pushes are different actions; the system must show which it is about to do.

Do not execute untrusted pull-request code in a workflow with privileged secrets. GitHub explicitly warns that `pull_request_target` can run with elevated trust and becomes dangerous when untrusted PR code is checked out/executed in that context [S11]. Use low-privilege CI events for build/test where possible, separate trusted publishing jobs, and never expose deployment secrets to external code.

## 12.6 Project memory quality gate

A generated “current state” summary must list commit/ref, file paths inspected, tests actually run, verified behavior, unresolved questions and timestamp. Do not claim “the repo is clean” unless the working tree was checked; do not claim a pull request was merged unless GitHub reports it. On startup after a long gap, Omnitrix should run a short reconciliation: current branch/status → recent commits → PRD/ADR version → known active tasks → stale or contradictory project notes.

---

# 13. Workspace Runtime, Browser, Files, and Generated Code

## 13.1 Principle

The “virtual desktop” should be a separate, controlled execution environment attached to a run—not a window into the host laptop with unrestricted privileges. The runtime may expose a terminal, browser, file browser, code editor/build process, notebook, media editor or 3D tool. The orchestrator grants only the workspace that the task needs.

OpenHands documents the rationale and pattern for a sandboxed Docker runtime containing browser/shell/tool processes, separate from orchestration [S12]. Daytona likewise documents isolated sandbox resources and code/process execution [S13]. These products are reference patterns, not requirements to purchase or adopt their hosted services.

## 13.2 Progressive implementation

1. **M1:** workspace directory under a dedicated Omnitrix data root; strict path containment and artifact hashes; no arbitrary host root access.
2. **M1/M2:** subprocess runner launched with allowlisted commands, timeout, cwd scope, environment sanitization and redacted logs. No shell interpolation with untrusted model strings; use argument arrays where possible.
3. **M3:** rootless container or equivalent isolation for untrusted/generated code where supported, with read-only mounts by default, CPU/memory/process limits and restricted network. Rootless containers help reduce daemon/host privilege [S14]; seccomp and container defaults need explicit review.
4. **M3:** isolated browser context per task/session. Playwright’s browser-context model gives independent cookies/storage and supports test isolation [S15]. User’s personal browser profile is never the default automation target.
5. **M3:** remote workspace streaming only after authentication, expiry, input authorization and isolation gates pass.

## 13.3 Workspace contract

Each workspace has an opaque ID, owner/session, run binding, root directory/container ID, base image/toolchain, creation time, expiry, read/write mounts, network policy, resource caps, credential grants, snapshot/reference, status, logs and artifact manifest. All file paths are relative to that workspace. Resolve symlinks and canonical paths before access; prevent `../` traversal and mount escape. Temporary workspaces are cleaned after retention expiry, except artifacts the owner explicitly saved.

## 13.4 Command execution safeguards

- Prefer named command tools with validated arguments to a general shell. If shell is exposed, it runs inside a sandbox with the exact current directory and only required mounts.
- Validate executable path, argument count/length, environment variable allowlist, timeout and expected output size.
- Sanitize ANSI/control codes in UI logs and escape HTML/Markdown from tool output.
- Apply output truncation plus a saved full log artifact so extremely verbose commands cannot overwhelm context or memory.
- Enforce process-tree termination and cleanup on timeout/cancel.
- Do not mount the host home directory or SSH/Git credential folders into a sandbox by default.
- Network default is deny or restricted to required destinations for sensitive tasks; any broader access is visible and policy-scoped.
- Never run an installer/build script with secrets merely because a dependency README recommends it.

## 13.5 Browser automation

Use dedicated isolated contexts with scoped cookies. Prefer explicit URLs/domains and page actions tied to the task; guard against downloaded files, redirects, pop-ups and prompt-injection content. Treat webpage text as untrusted data. Before submitting forms, sending messages, purchasing, changing account settings, deleting content or publishing, pause for explicit approval and show target, action and content. Never reuse personal logged-in browser cookies from the user’s regular browser without a separate explicit, narrowly scoped design and review.

## 13.6 Artifact management

Artifacts are first-class records: `artifact_id`, run/task, type/MIME, relative storage location, SHA-256, byte size, producer tool/version, creation timestamp, parent inputs, validation status, visibility and retention. Store large binary data outside conversational rows, with previews and metadata in the database. Artifact display must be content-type aware and safe against malicious SVG/HTML, decompression bombs, enormous media files and unexpected executable binaries. For archives, inspect paths before extraction and block absolute paths and traversal.

## 13.7 Runtime failure behavior

If sandbox startup fails, do not silently fall back to host execution. If container engine is absent, offer a read-only or explicitly limited mode, explain which tasks are disabled and how to enable a safer runtime. If the browser crashes, preserve logs/last URL and rebuild the context; do not retry a destructive form submission automatically. If workspace resource limits are hit, pause and present memory/disk/process usage and safe options. Runtime isolation and visibility are prerequisites for broader autonomous coding.

---

# 14. Android Application Requirements

## 14.1 Intended app

**DECIDED:** the long-term user experience should be a normal Android application, not a Termux-dependent workflow. The laptop may initially host development or the control plane, but the mobile client should eventually provide chat, task control and a clear view of the AI’s workspace.

**RECOMMENDED:** Kotlin + Jetpack Compose for a native UI, with an API client and unidirectional UI state flow. Android’s architecture guidance encourages a UI layer that renders app state, receives user actions and separates data/repository logic [S16]. The Android client is a separate consumer of the API contract, not the location of business policy.

## 14.2 Primary screens

1. **Home / conversation list:** recent sessions, new task, connection state, privacy/spend mode indicator.
2. **Chat:** accessible message view, attachments, explicit Learn/Observe vs Execute mode, composer, stop button, evidence/source cards.
3. **Plan review:** goal summary, dependencies/steps, tools and permission scopes, data destinations, cost mode, workspace changes, verification criteria, risks, approve/edit/reject actions.
4. **Run view:** timeline of state transitions, active task, progress estimate when grounded, logs/outputs, approval requests and retry/pause/cancel controls.
5. **Workspace:** tabs for screen/browser, terminal/logs, files/artifacts and task context; can be collapsed without stopping the task.
6. **Artifacts:** previews and downloads for supported output types; checksum/producer/validation metadata available.
7. **Settings:** model/provider enables, strict zero-cost mode, local endpoint, data-egress controls, memory preferences, retention, pairing/security, accessibility and diagnostics export.

## 14.3 Mobile interaction behavior

- Approval actions must be clear, unambiguous and accessible. Do not hide authorization in a generic “continue” button.
- Long-running work may continue if the app is backgrounded only when the server/runtime supports safe continuation and the UI can rehydrate state; Android process survival must not be assumed.
- Show last-sync time and connection banner. Reconnecting fetches the canonical run state and cursor, rather than replaying every event as a new action.
- Use adaptive layouts for narrow phones, foldables and tablets; large-screen desktop-like workspace is optional later.
- Use accessible hit targets, system font scaling, screen-reader labels, dark/light theme, color contrast and reduced-motion preferences.
- Keep heavy rendering in the runtime where possible; the phone streams a view rather than duplicating workstation computation.

## 14.4 Authentication and pairing

M2 must define the control-plane host (localhost/LAN/tunnel/remote) before shipping mobile connectivity. Use explicit pairing with a short-lived one-time code/QR and mutual identity binding; no secrets embedded in the APK. HTTPS is required outside a tightly scoped local development configuration. Tokens are stored in Android Keystore-backed storage, scoped, revocable and refreshable. Do not expose a shell/admin endpoint to the public internet. A tunnel is not authentication by itself.

## 14.5 Offline and disconnected states

Offline mode lets users review cached history and drafts. It cannot authorize actions without reaching the control plane. If a command was sent but acknowledgement was lost, the UI queries by request ID before retrying. It displays “submission status unknown” when unsure. Any offline queue must mark mutation requests as unsent/pending and require live policy/approval validation before execution.

## 14.6 Android release gate

Before beta: permissions minimized; secrets absent from APK; network security config reviewed; certificate/pairing tested; TalkBack/font scaling tested; reconnection and duplicate-submit tested; permission/approval flows tested; artifacts downloaded safely; remote API can be disabled; and app remains useful if workspace streaming is unavailable.

---

# 15. Live Workspace Streaming and Interaction

## 15.1 Architecture

![Mobile workspace architecture](diagrams/mobile.png)

Keep two separate channels:

- **Control/event channel:** authenticated HTTPS APIs plus WebSocket or Server-Sent Events for structured task-state updates, terminal text/log events and approval requests.
- **Workspace visual/input channel:** isolated screen/browser stream and bounded input events. The stream gateway translates authenticated mobile input to the workspace runtime; it is not allowed to bypass the policy/approval broker.

Choose the lightest technology that meets the UX. Start with structured terminal output, log tail and browser screenshot refresh. Add WebRTC or comparable low-latency video/input only once the control contract, identity, network access, disconnect handling and sandbox are stable. WebRTC protocol security does not replace application authorization, pairing or scope checks [S22]. This is a later engineering spike, not an MVP dependency.

## 15.2 Protocol requirements

Every event has event ID/sequence, run ID, task ID if applicable, timestamp, type, schema version, content reference or sanitized payload, and severity. The client must support replay from last acknowledged sequence, duplicate suppression, out-of-order detection and snapshot resync. Heartbeats show connection health but never imply task success. Visual frames are ephemeral; important evidence (logs, screenshots, output files and state transitions) is saved as artifacts/events.

## 15.3 Stream authorization

A stream token is scoped to one workspace/session, has short expiry, cannot open arbitrary paths/URLs, and is revocable. Check permission for keyboard/mouse/terminal input separately from viewing. A view-only observer is useful for review; input/mutation rights require a higher scope. Session expiry or revoke stops input immediately. Protect against CSRF, cross-origin WebSocket access, unbounded message sizes and replayed input events.

## 15.4 Failure modes

- **Stream disconnect:** task state may continue if allowed; reconnect with state snapshot/event cursor; do not duplicate commands.
- **Control plane disconnect:** reject new mutating inputs; visual stream can enter read-only mode only if its auth remains valid.
- **Runtime gone:** mark workspace unavailable; retain task artifacts and logs; offer restore/recreate plan.
- **Mobile app killed:** no assumptions about background UI; run state lives server-side/local backend, not only in Activity memory.
- **High latency:** throttle frame frequency/quality and prefer log/status updates. Do not use stale screen to confirm an irreversible action.
- **Untrusted input stream:** validate key events/action bounds and only route to the assigned workspace; no host-level keyboard shortcut pass-through by default.

## 15.5 Stream acceptance test

Run a task for several minutes, disconnect mobile network mid-step, reconnect, and confirm that state/order/artifacts match a server-side audit record, no commands were duplicated, and approval scope remains unchanged. Then revoke access and confirm further input is rejected promptly.

---

# 16. Voice and Device Interaction

## 16.1 Staged scope

Voice is useful but must not delay reliable task orchestration. Plan the voice path in this order: (1) push-to-talk capture; (2) speech-to-text; (3) text confirmation/edit before risky actions; (4) optional text-to-speech for the response; (5) background/wake-word investigation only after privacy, battery, Android background limits, data handling and false-activation behavior are designed.

The exploratory pipeline previously discussed—wake word → Whisper/STT → planner → device/app action → local TTS—is a candidate architecture, not yet a locked implementation. Use an interface (`SpeechInputProvider`, `TranscriptionProvider`, `SpeechOutputProvider`) so local or remote engines can be swapped. Do not assume Whisper runs efficiently on all target phones or every model/device action is supported.

## 16.2 Voice policy

- Show a visible microphone state and an unmistakable record/stop control.
- Keep raw audio ephemeral by default; persist only if user enables it and retention is shown.
- Display the transcript before high-impact actions. A transcription confidence threshold can trigger a clarification, but model confidence alone does not authorize a side effect.
- Require the same policy/approval gates as typed input. A spoken “yes” is not sufficient for a plan that has changed since it was read aloud.
- Do not continuously record in M0–M4. Wake word is deferred until the security/privacy case and platform behavior are acceptable.
- If transcription fails, ask the user to repeat or type; never invent the missing words.

## 16.3 Audio and voice-output quality

For released speech output, test intelligibility, clipped starts/ends, latency, pronunciation of filenames/code/technical names, interruption/cancel behavior, accessible text alternative and no unexpected audio capture. For creative audio/music/ASMR later, use a separate media-quality rubric (Section 18), not the voice UI rubric.

---

# 17. Capability and Skill System

## 17.1 Skills as bounded modules

A **skill** is a versioned capability workflow that binds together input schema, tools, orchestration hints, permissions, required resources, expected artifacts, verification/evaluation and user-facing description. It can contain deterministic code, model calls, external tool calls or a graph. The skill does not become a second orchestrator; it runs under the shared policy, budget and state model.

## 17.2 Skill manifest example

```json
{
  "schema_version": 1,
  "skill_id": "research.compare_sources",
  "version": "1.0.0",
  "title": "Compare source-backed claims",
  "description": "Gather and compare evidence for a defined research question.",
  "inputs": {"type": "object", "required": ["question", "source_count"]},
  "outputs": {"type": "object", "required": ["claims", "sources", "uncertainties"]},
  "required_capabilities": ["web.read", "reasoning"],
  "required_artifacts": ["source_register.json", "report.md"],
  "risk": "low",
  "data_egress": "public_query_only",
  "verification_profile": "evidence_report_v1",
  "resource_profile": {"max_steps": 8, "timeout_seconds": 300},
  "enabled": false
}
```

This manifest is a design example. Implementation must add complete schemas, version compatibility and registration validation before use. Skill IDs are stable identifiers; version and contract changes are recorded. Disable/rollback is a configuration operation.

## 17.3 Feature addition contract

New capability checklist:

1. Define problem, user value, out-of-scope behavior and quality floor.
2. Run procurement and license/security review.
3. Specify inputs, outputs, tool actions, permission scopes, budget, timeout and artifacts.
4. Add implementation behind adapter/skill interface.
5. Add deterministic unit/contract tests, failure injection, and modality-specific evaluation.
6. Add UI metadata only for controls the capability really supports.
7. Add feature flag defaulting to disabled until safe, tests passing and required resources available.
8. Update docs, registry, runbook, version and rollback instructions.
9. Execute in a test sandbox; verify artifacts from the output itself.
10. Enable on the smallest scope and monitor results before wider default availability.

## 17.4 Compatibility policy

Use semantic-version concepts for public contracts: patch for compatible bug fix, minor for additive compatible schema/API features, major for incompatible behavior/schema. Maintain migrations and deprecation warnings. Do not allow two independently versioned plugins to mutate shared global configuration with no owner. Plugin manifests are data; executable code requires a trusted installation and a least-privilege runtime.

## 17.5 Avoiding hard-coded feature lists

Prefer capability discovery from validated manifests instead of scattered conditionals such as `if skill == "music"`. Common UI surfaces render generic run status, inputs/outputs, artifacts and verification; capability-specific views are optional registered renderers with a safe fallback. Core logic should not know how to draw a waveform, open a 3D viewport or build an APK; it knows artifact type, schema, validator status and permission requirements.

---

# 18. Quality Doctrine for Every Modality

## 18.1 Universal rule

The product's quality bar does not fall because a capability is less frequently used. Prioritize implementation effort according to demand, feasibility, dependency and safety, but only enable a capability when it meets its medium-specific release gate. “The model generated something” is not the same as “the capability works.” A graceful “not supported yet” response is better than shipping low-quality output under a high-quality claim.

Every skill declares a `quality_profile_id`, acceptance tests, known limitations and supported output types. Release gating checks these requirements. A skill may be labeled **experimental** with a clear opt-in only if the user understands its limits and the mode cannot be mistaken for production quality. Never relabel experimental output as verified after generation.

## 18.2 Common quality dimensions

All capabilities are measured on: requirement adherence, correctness/factuality, completeness, reproducibility where relevant, artifact integrity, source/evidence support, latency/resource use, safety/privacy, usability/accessibility, failure transparency and editability/portability. Not every dimension has identical weight for every media type, so profiles define specific tests.

## 18.3 Capability-specific gates

| Capability | Minimum acceptance checks before enablement | Evidence to show the user |
|---|---|---|
| Research / web | Primary-source coverage appropriate to claim; dates; source links; conflict handling; fact/inference separation; no fabricated source access | Source register, claim-to-source mapping, unresolved contradictions. |
| Coding / software | Relevant test suite; format/lint/type checks when configured; diff review; dependency/license scan as applicable; build/start smoke test; clean failure reporting | Changed-file list, command outputs/status, test totals, commit/diff and unresolved warnings. |
| Data / math / science | Correct units/assumptions; numerical sanity checks; source/version of datasets; reproducible script/notebook; independent calculation or invariant checks for important outputs | Data provenance, equations/assumptions, units, checks, dataset and script artifact. |
| Graphics / images | Prompt/brief constraints, resolution/aspect/output format, no corrupted file, visual inspection, provenance/licensing, safe preview | Actual image asset, dimensions/format, generation/edit method and any known limitations. |
| Music / audio / ambience / ASMR | Valid playable audio, sample rate/bit depth/channel expectations, no clipped or empty output, length/format correct, listening review for distortion/noise/harsh artifacts, metadata/rights check | Audio artifact, encoding details, duration, validation result and audition status. |
| Video | Decodable container/codec, expected duration/frame size/frame rate, audio sync where present, no missing/duplicated critical frames, full render completes, preview inspected | Video file, metadata, render log, preview or storyboard and limitations. |
| 3D / scientific animation | Project opens; geometry/material/scale/camera/units valid; render/animation timeline verified; asset dependencies captured; scientific axis/time/units labeled where applicable | Source scene/project, exported render, key settings, dependency files, render log and visual review. |
| Games / APKs | Reproducible build, installation/signing checks, target Android/API requirements, startup/basic flows, crash/log check, permission audit, asset licensing, safe install instructions | APK/package metadata, source project, build command/result, smoke-test record and checksum. |
| UI / documents | Required structure, readable typography, no clipping/overflow, accessibility checks, links and references working, correct export | Previewable document, rendered PDF/image, link check and editable source. |
| Device / voice action | Explicit permission, correct device target, cancellation, permission denial path, privacy/battery test, confirmed result | Action transcript/status; no claim of success absent confirmation. |

## 18.4 Image and graphic workflows

A graphic workflow defines target (web/mobile/print), dimensions, color profile where relevant, alpha needs, safe-format list, number of variants, editability and rights constraints. Verify the actual file can be opened and matches requested dimensions/format. If a generated image is expected, confirm the tool actually returned an image artifact; never treat prompt text as generated artwork. Store prompt/version and output hash only where appropriate; protect private prompt content per retention settings. If exact design precision is required, prefer deterministic vector/diagram/layout tooling over a purely generative raster image.

## 18.5 Audio and music workflows

Audio generation is its own capability, not a text answer with an `.mp3` suffix. Specify length, sample rate, channels, codec, intended listening context, loudness target when relevant, loopability, fade behavior, artifact tolerance and licensing. Validation includes decoding the full file, detecting empty/truncated output, clipping, extreme silence, unexpected duration and broken loop seams; perceptual inspection remains required for release. For scientific/acoustic work, provide objective measurements and do not equate a listening impression with a measurement.

## 18.6 Video workflows

Plan video generation as a pipeline of brief/storyboard → assets → timeline/edit → render → technical validation → visual review. Track frame size, frame rate, aspect ratio, duration, audio, codecs, fonts and linked assets. A render failure preserves project and logs; it should retry only failed steps where safe. Use proxies/low-resolution previews for iteration only when the final artifact is rendered and checked at the agreed delivery settings.

## 18.7 3D and scientific animation

3D work must distinguish visual plausibility from scientific correctness. Scientific scenes require source parameters, coordinate system, units, model assumptions, timestep/solver information where relevant and validation against known invariants or reference data. Visual workflows require camera, lighting, geometry scale and material setup to be reproducible. Save the native project/scene plus render output and dependencies; a video alone is not an editable deliverable. Do not label speculative visualization as observational/scientific evidence.

## 18.8 Software and APK workflows

The capability must produce source code plus build instructions, not only a binary, unless the user specifically asks for only a binary. Check target SDK, permissions, signing state, package name, build reproducibility, startup and at least one basic user flow. Treat unsigned debug APKs honestly; do not describe them as production-ready releases. Avoid requesting broad device permissions for convenience. Generated code runs in the workspace sandbox and is reviewed/tested before export.

## 18.9 Quality profile lifecycle

Every capability’s quality profile is versioned and included in the run record. Test fixtures cover normal input, boundary input, malformed input, interruption, denied permission, low resources and unsupported environment. Changing the profile triggers evaluation against prior fixtures. Do not lower a threshold just to make CI green; create a documented exception with impact, owner approval and expiry if a legitimate trade-off is necessary.

---

# 19. Data Model, API Contracts, and Event Schema

## 19.1 Persistence recommendation

**RECOMMENDED:** SQLite for the first durable local implementation. It provides transactional data integrity without requiring a hosted database. Keep SQL access behind repository interfaces and use explicit migrations. Do not store large media binaries directly in normal run rows; store artifact metadata and a managed file path/content-addressed object. A later multi-user server can replace storage behind interfaces when a real concurrency/deployment need appears.

## 19.2 Core entities

| Entity | Essential fields | Why it exists |
|---|---|---|
| `Conversation` | ID, owner/profile, created/updated, retention policy | Dialog grouping; not the authoritative execution state. |
| `Message` | ID, conversation ID, role, content/attachment refs, trust class, timestamp | User/assistant/tool-facing content. |
| `Run` | ID, conversation, objective, mode, status, policy version, spend mode, timestamps, final summary ref | One requested outcome across tasks. |
| `Plan` | ID, run, version, canonical payload, fingerprint, approval state, policy hash | Reproducible execution contract. |
| `Task` | ID, plan/run, description, dependencies, status, inputs, expected outputs, budget, retry rules | Unit of work and dependency graph node. |
| `Attempt` | ID, task, attempt number, worker/provider, start/end, outcome, diagnostic ID | Retry/recovery and audit. |
| `Approval` | ID, run/plan fingerprint, actor/session, scopes, decision, expiry, policy version | Exact approval evidence. |
| `ToolDefinition` | ID, version, schemas, capabilities, risk, implementation ref, enabled state | Tool catalog item. |
| `PermissionGrant` | ID, actor, capability, scope, target, issuer, start/expiry/revocation | Deterministic authorization state. |
| `Event` | ID/sequence, run/task, type, schema version, time, sanitized payload | Ordered timeline and replay. |
| `Artifact` | ID, run/task, MIME/type, path, hash, size, producer, validation, retention | Generated and collected files. |
| `Evidence` | ID, artifact/source ref, claim/criterion, method, status, timestamp | What supports a final claim. |
| `ProviderHealth` | provider/model, state, checked time, backoff, sanitized failure count | Circuit breaker/routing inputs. |
| `MemoryRecord` | ID, category, text/reference, approval state, source, sensitivity, expiry | Approved reusable knowledge. |
| `Workspace` | ID, owner/run, runtime ref, resource policy, expiry, status | Isolated execution context. |

Use opaque generated IDs. Avoid putting raw objectives or full prompts in routine database indexes/log identifiers. Enforce foreign keys and transactional state changes. A task/attempt record is never deleted just because a new retry begins; append new attempt history.

## 19.3 Event contract

An event should include:

```json
{
  "schema_version": 1,
  "event_id": "evt_example",
  "sequence": 42,
  "run_id": "run_example",
  "task_id": "task_example",
  "timestamp": "2026-10-11T12:00:00Z",
  "type": "task.status_changed",
  "severity": "info",
  "payload": {
    "from": "running",
    "to": "verifying",
    "summary": "Command completed; artifact checks started"
  },
  "artifact_refs": []
}
```

The values are illustrative. Use versioned schema and strict validation. Events must be sanitized before reaching mobile clients. Do not emit raw secrets, full file contents or arbitrary HTML in the default event channel. Critical events (approval required, cancellation, budget exhausted, permission denied, unknown external outcome, run terminal state) must be durable. High-frequency screen frames are not ordinary database events; they belong in the streaming channel with selective snapshots.

## 19.4 Minimum API surface (versioned)

| Method / route | Purpose | Mutates? | Security rule |
|---|---|---:|---|| `POST /v1/conversations` | Create conversation | Yes | Authenticated owner/session. |
| `POST /v1/runs` | Submit objective and mode | Yes | Idempotency key for request submission. |
| `GET /v1/runs/{id}` | Snapshot run/tasks/status | No | Run-level access check. |
| `GET /v1/runs/{id}/events?after={seq}` | Replay events | No | Cursor checked and scoped. |
| `POST /v1/runs/{id}/approvals` | Approve/reject exact plan/action | Yes | Check current fingerprint, actor and expiry. |
| `POST /v1/runs/{id}/pause` | Request pause | Yes | Authorized owner/operator. |
| `POST /v1/runs/{id}/resume` | Resume only if state/policy permits | Yes | Recheck auth, provider, policy and approval. |
| `POST /v1/runs/{id}/cancel` | Cancel run | Yes | Must not imply completed side effects were undone. |
| `GET /v1/artifacts/{id}` | Metadata/authorized download | No | Artifact scope and safe content type. |
| `POST /v1/workspaces/{id}/input` | Send scoped workspace input | Yes | Short-lived workspace/input grant. |
| `GET /v1/health` | Health/readiness probe | No | Expose no secret config. |

These are proposed contract names. Add an API version and schemas before a mobile client depends on them. For local-only M0, an in-process interface may wrap the same application service before HTTP is added. Do not build routes for hypothetical functionality too early.

## 19.5 API behavior rules

Use explicit error envelope with stable error code, safe message, diagnostic/correlation ID and retryability. Use correct HTTP status semantics; never encode a failed operation as HTTP success with only a hidden error string. Validate request size and schemas. Require idempotency key for command-like requests where a client might retry after losing acknowledgment. Return `202 Accepted` for accepted long-running work with a run ID rather than blocking the client until completion.

## 19.6 Migrations and schema evolution

Every persistent schema change includes a migration, forward compatibility plan and backup/restore test for important data. Start with a known schema version; on startup detect newer/unsupported database versions and fail clearly rather than silently corrupting. Use a disposable test database for migrations, and test both fresh install and previous-version upgrade. Make migrations small and reversible where possible; if a migration is irreversibly destructive, take and verify a backup first.

---

# 20. UX Requirements and Output Standards

## 20.1 UX philosophy

The UI should make Omnitrix feel like a capable workbench, not a mysterious spinner or a dashboard that exposes endless agent jargon. User-facing labels should explain outcomes. “Researching sources,” “Waiting for your approval,” “Running tests,” and “Outcome uncertain; checking before retry” are useful; “Agent 7 handoff state 3” is not.

## 20.2 Plan summary requirements

Before an approval gate, show: intended outcome; summary of steps/dependencies; read/write/external actions; target repository/path/account/destination; data sent to remote providers; providers/resources and cost mode; known risks; expected files/artifacts; verification criteria; estimated duration only if grounded; and whether the plan can be safely cancelled/rolled back. Avoid overloading the screen—provide a concise summary plus expandable details.

## 20.3 Final response template

Every completed/partial/failed run should finish with an appropriate form of:

- **Outcome:** completed, partial, failed, cancelled or unknown outcome.
- **What was done:** concise list of verified steps.
- **Evidence:** artifact links, source links, test/run outputs and commit/diff refs where applicable.
- **Verification:** what passed, what failed, what was not run and what remains unverified.
- **Side effects:** files/branches/external state changed; confirmation evidence if available.
- **Limitations / risks:** meaningful uncertainties or constraints.
- **Next safe choice:** at most a small number of clear options when user input is required.

Do not force a long report for a trivial conversational answer. Final response detail scales with task complexity.

## 20.4 Progress events

Meaningful progress updates should be emitted on state transitions and useful milestones. Do not invent percentage progress unless a measurable workflow gives a grounded estimate. Provide a heartbeat for a long-running step, but label it as “still running” rather than claiming progress. Show whether Omnitrix is blocked on user approval, provider rate limit, resource availability, or task dependency.

## 20.5 Empty and error states

Every screen should have a useful empty state, offline/error state, retry action where safe, and route to the original request/history. A missing workspace, disabled model or unsupported file type should not become a blank panel. Error messages are plain language with optional technical detail. Provide a diagnostic ID rather than dumping an entire stack trace by default.

## 20.6 Accessibility and internationalization

Support system font scaling, screen-reader semantics, contrast, keyboard navigation for desktop/web surfaces, reduced motion and non-color-only status labels. Keep user-facing strings separate from core state identifiers. Do not encode business logic in translated strings. English may be the first language, but structure supports localization without code rewrites.

## 20.7 Editing and human review

Allow the owner to edit an unapproved plan, change constraints, disable a proposed tool, or reject the plan. Editing creates a new plan version/fingerprint; previous approval is invalidated. Do not allow a user’s edits to be overwritten silently by an agent replan. Show a diff between versions.

---

# 21. Security, Privacy, and Permission Architecture

## 21.1 Threat model scope

The threat model includes prompt injection through user-provided content, retrieved webpages, repository files and tool output; malformed model/tool schemas; malicious or compromised plugins; credential leakage; unrestricted code execution; cross-workspace access; remote API cost abuse; replayed mobile commands; exposed terminal/stream endpoints; unsafe generated artifacts; supply-chain compromise; accidental destructive actions; and stale or untrusted memory overriding current policy. OWASP’s LLM guidance covers risks such as prompt injection, sensitive information disclosure, supply-chain issues and improper output handling; its agentic-application work adds risks specific to multi-step delegated action and authority boundaries [S17, S20]. Translate each relevant risk into deterministic controls and adversarial tests, not prompt-only mitigations.

## 21.2 Trust boundaries

![Trust boundary diagram](diagrams/trust.png)

Treat user text, model output, retrieved data, tool output, plugin manifests, browser content and generated code as separate trust classes. Data fetched from outside is not a new instruction hierarchy. Parse and validate structured output before use. Every tool execution re-checks the permission broker; filtering the tools exposed to the model is an additional guard, not sufficient authorization.

## 21.3 Authorization model

Use capability-based permissions with scoped targets. Example capability names: `workspace.read`, `workspace.write`, `shell.execute`, `browser.read`, `browser.submit_form`, `github.read`, `github.create_branch`, `github.push`, `github.merge`, `external.send_message`, `media.render`, `device.microphone`, `device.action`. A grant includes actor, capability, target/project/workspace scope, run binding if relevant, expiry, policy version, origin and revocation status.

**Risk tiers:**

- **R0 — No side effect:** pure response, formatting, internal classification. No tool permissions needed.
- **R1 — Read within approved scope:** read-only project files, local metadata or public webpages. May be auto-allowed by policy.
- **R2 — Reversible local mutation:** write to an isolated workspace, create temporary artifacts, install into disposable sandbox. Requires explicit workspace grant; plan approval may be required by project setting.
- **R3 — External or shared mutation:** push branch, create/update issue, edit remote configuration, send a message, publish a file or access account-bound actions. Requires explicit approval naming the target and expected change.
- **R4 — Destructive, public, financial, security-sensitive or hard-to-reverse:** delete important data, merge/release publicly, change permissions, expose secrets, purchase or deploy. The product should deny by default and/or require a distinct deliberate confirmation, depending on task and applicable policy. Omnitrix must not assume general approval is adequate.

A model cannot downgrade risk tier. Risk is calculated from tool definitions and arguments as well as plan metadata.

## 21.4 Secrets management

- `.env`, API keys, OAuth tokens, cookies, private SSH keys, provider files and local credential stores are ignored by Git and scrubbed from logs.
- Provide `.env.example` with names/placeholders only.
- Never put a secret in the model prompt if a tool can read it from a credential handle.
- Use short-lived, restricted tokens and rotate/revoke on suspected exposure.
- Sanitize exceptions that may include request headers, URLs with tokens, environment variables or command-line arguments.
- Exclude secrets from artifacts, diagnostic bundles and screenshots by default.
- Before uploading logs to an external support system, show the target and inspect redactions.

## 21.5 Prompt injection and untrusted content

No prompt or text filter alone reliably eliminates prompt injection. Use architectural controls: least privilege, explicit allowlists, constrained tool schemas, separate untrusted-data fields, target/domain limits, human approval for consequential actions, output validation, external-call budgets and verification. Retrieved content may be summarized or cited but cannot authorize a new tool, loosen scope, reveal credentials or change the plan automatically. If untrusted content proposes a side effect, turn it into a user-visible proposal and apply normal policy.

## 21.6 Supply-chain and package safety

Run procurement before dependency addition. Pin versions where compatible with maintenance/security; commit lockfiles; review licenses; record direct/transitive dependencies; use supported security scanners where feasible; and test rollback. Never install package suggestions directly from model text. Treat plugins, MCP servers, container images, browser extensions, local model downloads and media binaries as software supply chain inputs. Prefer well-known official registries and verify checksum/signature where available. A license compatibility problem is a release blocker, not a footnote.

## 21.7 Sandbox isolation and host safety

Use separate low-privilege process/container. Rootless Docker and seccomp are useful defense-in-depth patterns but are not a guarantee of complete isolation [S14]. Do not expose the container daemon socket to task code. No host root, device access, privileged container, or broad home directory mount. Network egress, file mounts and resources are explicitly set. For tasks that need a host-specific function, create a narrow broker tool that validates arguments and operates on approved targets, rather than giving host shell access.

## 21.8 Mobile/API security

Use HTTPS for remote connections, short-lived scoped access tokens, revocation, pairing and per-run access checks. Reject oversized payloads, invalid JSON, stale approval fingerprints, replayed command IDs and event cursor tampering. Use rate limits for expensive operations. Hide internal diagnostics/paths on public endpoints. Log security event IDs without writing secrets. If a stream token leaks, revoke only its scope quickly rather than requiring all user credentials to be rotated.

## 21.9 Privacy and retention

Make clear whether a request will send text/file/audio/image contents to a remote provider. Use provider privacy classification in routing. Local data retention is configurable by category; artifacts have their own retention. Do not collect precise phone location, contacts, microphone or other Android data unless required by an explicit skill and approved. Avoid using raw personal conversation histories as project prompts if a distilled project decision is enough. Provide delete/export controls for user memory and run data.

## 21.10 Security acceptance criteria

- Denied capability cannot be executed even if model asks for it directly.
- Tool-call arguments failing schema validation are rejected before execution.
- File path traversal and symlink escape are blocked.
- A tool’s output containing “ignore prior instructions” does not change policy.
- Secrets seeded in environment/test fixtures do not appear in logs or final responses.
- Strict zero-spend rejects a simulated paid provider before the request is sent.
- Revoked grants stop future tool execution and stream input.
- An untrusted plugin manifest cannot execute an import during discovery.
- Cancel/timeout kills or safely detaches child processes only inside managed scope.
- External side effect with ambiguous result reports uncertainty, not success or safe-to-retry by default.

---

# 22. Failure Catalogue and Recovery Decision Table

The following matrix is mandatory design input for error handling and fault-injection tests. More failure cases should be added as incidents occur.

| ID / failure | Detect via | Required behavior | Retry policy | User-visible outcome |
|---|---|---|---|---|
| F-01 Invalid model plan JSON | Parser/schema validation | Reject; preserve raw response only as sanitized debug evidence; run one constrained repair only if policy permits | Max one repair attempt | “Plan was invalid; nothing executed.” |
| F-02 Unknown dependency / graph cycle | Plan validator | Block plan before execution | No blind retry; regenerate/repair plan | Show offending task IDs and request correction/replan. |
| F-03 Approval hash mismatch | Approval gate | Reject execution; display plan diff; invalidate old approval | Re-approval required | “Plan changed after approval; review the updated version.” |
| F-04 Approval expires/revoked | Policy check before side effect | Stop before action; retain run state | Re-approval only | Identify scope/plan awaiting approval. |
| F-05 Model adapter missing | Adapter lookup | Fail the attempt; do not switch to arbitrary model | Retry after configuration repair | “Configured model has no adapter.” |
| F-06 Authentication/key invalid | Provider response | Mark model unavailable; never log key; prevent repeated hammering | No retry until credential is fixed | Actionable message and sanitized diagnostic ID. |
| F-07 Rate limit | Provider headers/error | Backoff; checkpoint wait state; route elsewhere only if eligible | Bounded exponential backoff with jitter | Show delay/state, not fake progress. |
| F-08 Free quota exhausted / cost unknown | Budget/provider status | Stop remote calls under strict zero-cost mode | No automatic paid fallback | “Provider quota unavailable; no paid fallback used.” |
| F-09 Model timeout | Timer/transport | Cancel request where possible; checkpoint | Retry idempotent requests only, within cap | Report if result is unknown or incomplete. |
| F-10 Malformed tool call | Schema/permission broker | Reject; emit audit event; possibly allow model to correct once | Bounded | No tool side effect occurred. |
| F-11 Tool exception | Structured adapter result | Classify error; save diagnostic/event; stop dependent tasks | By idempotency class only | Name the failed step and next safe route. |
| F-12 Tool permission denied | Policy result | Do not execute; do not try alternate tool to bypass policy | No automatic retry | Explain required scope or ask whether to revise. |
| F-13 Repeated agent loop | Iteration/cost budget | Stop run or subtask; mark loop failure | No immediate restart of same loop | Show loop detected, output saved and possible manual options. |
| F-14 Dependency failure | Scheduler state | Block dependents; allow safe independent tasks only | Resume after dependency resolves | Show blocked/skipped tasks and exact dependency. |
| F-15 Process crash before checkpoint | Start/heartbeat watchdog | Restart from prior persisted state; mark uncommitted attempt interrupted | Safe only after reconciliation | State that the last attempted operation may need checking. |
| F-16 Unknown outcome after external mutation | Missing response/idempotency uncertainty | Query target state or ask human; do not duplicate action | No blind retry | “Outcome not confirmed; checking before repeating.” |
| F-17 Local disk full | Filesystem error/low-space check | Stop new writes/render; preserve DB consistency; free only declared temp data | After space restored | Explain likely partial artifact and safe cleanup options. |
| F-18 Workspace/container unavailable | Runtime health | Keep control-plane state; attempt safe restore or create new isolated workspace | Bounded; no host fallback | Workspace unavailable; artifacts/logs retained where possible. |
| F-19 Unsafe archive/path | Artifact scanner | Reject extraction; quarantine artifact | No automatic bypass | Explain unsafe contents/path and retain evidence. |
| F-20 Browser context crashes | Runtime monitor | Save logs/URL; recreate isolated context if read-only | Read operations may retry; form submits require reconciliation | Report browser restart; no duplicate submission. |
| F-21 Mobile disconnect | Heartbeat/transport | Task runs or pauses according to explicit policy; state persists | Client reconnects via request ID/cursor | Show disconnected/reconnecting; no duplicate commands. |
| F-22 Event stream gap/reorder | Sequence numbers | Request missing events or full snapshot; deduplicate by event ID | Automatic resync | UI indicates resync if it cannot reconstruct state. |
| F-23 Artifact validation fails | Codec/open/hash/visual or domain tests | Mark invalid and prevent “successful deliverable” status | Retry render or repair only where safe | Clearly label artifact as failed/preview. |
| F-24 Test suite fails | CI/test result | Keep change unapproved/unmerged; preserve logs | Fix root cause; no suppress-to-pass shortcut | List failed tests; don't claim tests passed. |
| F-25 Git conflict / branch drift | Git status/merge check | Pause integration, fetch and compare; do not overwrite user changes | Controlled rebase/merge after review | Show changed files/commits and resolution needed. |
| F-26 Migration failure | DB transaction/startup check | Backup first; abort startup/write path; keep old database intact | Retry after fix/restore plan | “Database upgrade failed; original data preserved if backup succeeded.” |
| F-27 Logging/observability failure | Export/handler error | Core task may continue unless auditing is mandatory for that operation; sensitive action fails closed if audit can't be recorded | Retry log writer bounded | State observability degradation. |
| F-28 Memory conflicts with current PRD | Reconciliation checks/source timestamp | Surface decision conflict and stop affected assumption-dependent change | Wait for owner/ADR | Show both conflicting sources and proposed resolution. |
| F-29 Cancellation arrives mid-step | Cancellation token/state | Stop new steps; attempt safe interruption; reconcile current effect | No restart until user chooses | State partial completion and remaining side effects. |
| F-30 Cost/budget limit reached | Independent budget guard | Reject additional paid/compute calls and checkpoint | Resume only after budget/policy change | Clear stop reason; never silently upgrade spend. |
| F-31 New provider/skill contract mismatch | Registry validator | Keep component disabled; surface diagnostic | After schema/config/code fix | Other skills should continue normally. |
| F-32 Unexpected server/app version mismatch | API/schema compatibility | Reject unsupported mutations; allow safe status view if compatible | After upgrade/rollback | Explain required app/server update. |

## 22.1 Failure recovery algorithm

For every failure, the recovery coordinator must answer: (1) what was the last durable state? (2) could a side effect have occurred? (3) is the operation idempotent? (4) is the current permission/approval still valid? (5) are dependencies and artifacts intact? (6) does the task remain inside budget? (7) is a safe retry available? If any critical answer is unknown, **pause and reconcile** rather than retrying. Save a small diagnostic bundle with redacted logs, event IDs, versions, attempt number and reproduction details. Do not include secrets or raw personal content by default.

## 22.2 Incident severity

- **SEV-0 security/budget violation:** unintended credential exposure, unauthorized side effect, spend against explicit zero-cost policy or cross-workspace access. Stop affected integrations, revoke scopes and preserve sanitized evidence immediately.
- **SEV-1 data integrity/run corruption:** invalid state transition, lost artifacts or duplicate non-idempotent action. Pause affected execution and recover from verified backup/checkpoint.
- **SEV-2 feature degradation:** provider, workspace, streaming, media or voice capability fails while core chat remains available. Disable isolated component and provide degraded mode.
- **SEV-3 cosmetic/non-blocking:** UI formatting, optional event or documentation issue. Track and fix without compromising higher-priority safety work.

---

# 23. Observability, Evidence, and Diagnostics

## 23.1 What to record

Use structured logs and traceable run events. Each task/run should correlate with a trace/run ID and capture: state transitions; policy decision outcomes and reason codes; model/provider/model version; tool ID/version; start/end/duration; usage and cost status if returned; retry count; sanitized errors; artifact IDs/hashes; verification outcome; approval record; and cancellation/unknown side-effect state. OpenTelemetry semantic conventions provide a stable vocabulary for traces, metrics and logs [S18]; adopt only fields applicable to the local architecture.

## 23.2 What not to record by default

Do not log raw API keys, cookies, authorization headers, full environment, private SSH content, all message content, sensitive files, audio/video frames, personal data or full shell environment. Logs should make it possible to debug without becoming a second unrestricted copy of user data. When payload capture is needed for debugging, require an explicit local diagnostic mode with clear retention and redaction.

## 23.3 Minimum metrics

- runs by terminal status and task class;
- plan invalidation/schema errors;
- model selection/rejection reasons, provider health, rate-limit and timeout counts;
- tool calls by tool/version/status/risk tier;
- approval waits, rejects and expired approvals;
- retry counts and recoveries after process restart;
- tasks stuck beyond expected timeout;
- artifact validation pass/fail and bytes written;
- sandbox resource limit hits;
- local disk use, database growth and retention cleanup outcomes;
- quality evaluation results by task profile;
- budget guard rejects and actual provider usage where available;
- mobile event lag, reconnects and duplicate-submit prevention events.

## 23.4 Tracing model

A trace contains an orchestration span; child spans for classification, planning, router selection, tool procurement, approval wait, worker execution, provider calls, verification and artifact write. Avoid recording entire prompts or tool outputs as span attributes. Record content hashes, IDs and bounded redacted summaries instead. Trace backend may be local logs initially; external telemetry export is opt-in because it can transfer sensitive metadata.

## 23.5 Final report evidence graph

For each substantive claim, store a relation to supporting evidence: a URL/source excerpt, successful command output, test result, artifact hash, commit SHA, schema validator result or direct state observation. A claim can be `SUPPORTED`, `CONTRADICTED`, `INFERRED`, `UNVERIFIED` or `STALE`. The final response composer should not elevate inference or stale data to verified fact.

## 23.6 Health checks

Separate liveness (“process is alive”) from readiness (“can accept safe tasks”). Do not fail all readiness because one optional provider is down; report per-component health. A missing critical database migration, corrupt registry or unavailable required secure runtime may disable mutations while still allowing a limited status/help surface. Health endpoints must not expose model keys, filesystem layouts or sensitive configuration.

---

# 24. Testing, Evaluations, and Release Gates

## 24.1 Test pyramid

1. **Unit tests:** plan graph validation, fingerprint canonicalization, capability decisions, budget guards, schemas, idempotency classification, state transitions and redaction.
2. **Contract tests:** all model adapters, tool adapters, skills and runtimes satisfy common schemas and error semantics using fake/test endpoints.
3. **Integration tests:** database migrations, run/event persistence, tool authorization, artifact store, workspace launch/timeout/cleanup and API auth.
4. **End-to-end tests:** user request → plan → approval → execution → verification → final report.
5. **Fault injection:** crash at each checkpoint, timeout during external request, duplicate client retry, corrupted artifact, quota exhausted, lost stream sequence, permission revoked mid-run, database migration failure and full disk.
6. **Security tests:** traversal, malicious tool output, prompt injection, manifest import injection, token leak sentinel, workspace boundary, untrusted archive and over-budget call.
7. **Quality evaluations:** task-specific datasets with clear scoring guidance, human spot checks and regression comparisons.
8. **Visual QA:** rendered PDF/document/image/video/3D viewport as appropriate; text-extraction success alone is not enough for visual artifacts.

## 24.2 Existing tests to preserve

Current tests already exercise important areas such as valid plans, dependency graphs, cycle detection, long chains, tool iterations, adapter behavior, tool permissions and exact plan fingerprint approval. Preserve those protections and add regression fixtures whenever a bug is fixed. Refactoring should not delete tests in order to make the build pass.

## 24.3 Golden task benchmark

Build a small stable private benchmark (start around 20–30 representative tasks, then expand) spanning: simple chat with no tools; request needing one read tool; research with conflicting sources; malformed planner JSON; multi-step plan with dependencies; approval invalidation; file write in workspace; test failure; quota exhaustion; restart after checkpoint; external side effect unknown outcome; prompt injection in a webpage; adding a tool through procurement; audio/image/video/3D output when those capabilities are ready; and Android disconnect/reconnect.

For each fixture, define intended mode, expected side effects, permission decisions, success criteria, allowed model variance, failure path, required evidence and scoring rubric. Keep tests deterministic with mocked provider outputs; use real model integration tests separately and label them as non-deterministic. Never use a model judge as the only safety gate.

## 24.4 Release gate

A feature cannot be considered “done” until:

- acceptance criteria are mapped to test or direct inspection evidence;
- unit/contract/integration tests relevant to the change pass;
- full CI passes, or each failed/non-run check is explained and approved as a known blocker;
- security, privacy, budget and license impacts were reviewed;
- visual artifacts were rendered and inspected where relevant;
- errors/cancellation/retry/disconnection are covered;
- logs are sanitized and secrets check is clean;
- docs/registry/ADR/migrations are updated;
- rollback/disable steps work;
- final report accurately labels the results.

## 24.5 Evidence report template

```text
Change / run:
Commit or branch:
Acceptance criteria covered:
Commands actually run:
Unit / contract tests:
Integration / end-to-end tests:
Security / secret scan:
Artifact checks:
Manual visual review:
Failures / warnings / skipped tests:
Known limitations:
Rollback / disable route:
Evidence links or artifact IDs:
```

---

# 25. Product and Framework Landscape Review

## 25.1 Purpose and limits of this comparison

The purpose of product research is to borrow mature patterns and avoid unnecessary reinvention—not to assemble Omnitrix out of the maximum number of fashionable packages. Features, prices, licensing and APIs change; links below point to primary or vendor documentation available during the 11 October 2026 research snapshot. Re-check a product before adopting it. Marketing documentation demonstrates a claimed capability, not an independent quality guarantee.

## 25.2 Relevant systems and lessons

| Product / project | What it contributes | Risks / fit limits | Omnitrix recommendation |
|---|---|---|---|
| **Microsoft Agent Framework** [S01] | Agent/workflow patterns, tools, memory, human-in-the-loop and checkpoint capabilities; actively documented evolution from prior Microsoft agent stacks | May impose abstractions or hosting preferences; migration has cost; evolving APIs need verification | Study workflow/checkpoint concepts. Prototype only if it materially simplifies a concrete gap; do not replace the existing core in one move. |
| **Google ADK** [S02] | Sequential/parallel/loop workflow agent patterns and explicit agent structures | Model/provider ecosystem fit and added conceptual framework | Useful reference for bounded orchestration patterns. Keep capability interfaces provider-independent. |
| **LangGraph** [S03] | Graph workflows, persistent state/checkpoints and resumability patterns | Framework state design can become another source of truth if mixed with Omnitrix storage | Inspect its checkpoint semantics and failure behavior. Compare against a simple local SQLite scheduler before adoption. |
| **OpenAI Agents SDK** [S04] | Small agent primitives, handoffs, guardrails and tracing; sandboxing integration directions | Vendor/API dependence if adopted as central runtime; not all features are provider-neutral | Learn from contract design and tracing, but keep provider adapter surface open. |
| **LiteLLM** [S05] | Model routing/proxy, retries/fallbacks and provider abstraction | Adds proxy/operational dependency and configuration; cost tracking does not replace an independent hard budget guard | Consider only if number of remote providers creates measurable integration overhead. In M0, current adapter registry likely suffices. |
| **Ollama** [S06] | Local inference endpoint and OpenAI-compatible subset | Requires local model storage/resources; compatibility is a subset, models vary in quality and capability | Best candidate for optional local inference adapter after hardware benchmark. No automatic giant download. |
| **Hugging Face Inference Providers** [S07] | Convenient access to many hosted inference providers | Free tier is limited/changeable; pay-as-you-go can continue after credits, so risk of unexpected charges | Optional remote integration only behind strict zero-spend guard and provider-specific cost-state configuration. |
| **Model Context Protocol (MCP)** [S08–S09] | Interoperability contract for tool/resource servers | Remote tool descriptions cannot be trusted as policy; authorization, token handling and server trust boundaries are nontrivial | Support as a tool adapter after local policy/registry is robust; do not expose every connected tool by default. |
| **Agent2Agent (A2A)** [S10] | Protocol for discovering/communicating with independent agents | Adds identity, authentication, version compatibility, state correlation and error recovery | Defer. Use internal typed worker messages until independent agent-service interop is a demonstrated requirement. |
| **OpenHands runtime** [S12] | Reference architecture for isolated code/browser/shell execution | Complete runtime may be heavier than a local personal assistant needs | Borrow sandbox/control-plane separation concepts. Evaluate installation/license before packaging any code. |
| **Daytona sandboxes** [S13] | Isolated environments with process/code execution and resource allocation | Hosted/runtime costs, terms and service availability; not appropriate as a hard zero-cost dependency | Study as a benchmark; local sandbox should work independently. Use hosted resources only if owner opts in and budget permits. |
| **Playwright** [S15] | Browser automation with isolated contexts and separate storage/cookies | Browser automation still requires action-level policy, safe session handling and site-specific reliability | Candidate for task-scoped browser automation with isolated contexts; never default to personal browser profile. |
| **OpenTelemetry** [S18] | Common tracing/log/metric semantics across components | External telemetry export can expose metadata; extensive instrumentation may burden MVP | Start with structured local events; add OpenTelemetry-compatible tracing once run IDs/state transitions stabilize. |
| **Android Jetpack Compose** [S16] | Native declarative UI and state-driven architecture recommendations | Requires Kotlin/Android build and release workflow | Recommended for the future Android client; keep it separate from core business rules. |
| **OWASP GenAI/LLM guidance** [S17] | Risk categories around prompt injection, excessive agency, insecure plugin design and disclosure | Guidance identifies risk classes but does not configure secure behavior by itself | Map each risk to a deterministic test and permission boundary, not just prompt wording. |
| **GitHub Actions security guidance** [S11] | Trust distinction for `pull_request`, `pull_request_target`, secrets and untrusted PR execution | Workflows still require repository-specific review | Use least privilege and separate trusted publishing from untrusted build/test. |

## 25.3 Architecture decision scorecard

Scores are directional (1 = weak fit, 5 = strong fit) based on current project scale and constraints, not benchmark claims.

| Option | $0/local fit | Preserves current core | Operational simplicity | Durable workflow potential | Recommendation |
|---|---:|---:|---:|---:|---|
| Keep Python core, modular monolith + SQLite | 5 | 5 | 5 | 4 | **Select now** |
| Replace all orchestration with one agent framework | 2–4 | 1 | 2–3 | 4 | Reject wholesale replacement; consider small prototype. |
| Microservices + queue + cloud DB from day one | 1 | 2 | 1 | 5 | Defer; disproportionate for a zero-budget personal product. |
| All capabilities as independent role-based agents | 3 | 2 | 2 | 3 | Reject as primary organizing principle. |
| One unrestricted super-agent with all tools | 4 | 3 | 4 | 1 | Reject: weak boundaries and difficult recovery/audit. |
| Core orchestrator + typed optional specialist workers | 5 | 5 | 4 | 4 | **Select as product model** |
| Local model only, permanently | 5 | 5 | 4 | 2–4 | Useful privacy/offline option, but should remain one adapter because hardware/quality varies. |
| Hosted API and cloud sandbox mandatory | 1 | 3 | 3 | 4 | Reject as default due spend and availability dependency. |

## 25.4 Recommended build-vs-buy decision

Build Omnitrix-owned policy, task state, plan/approval binding, run lifecycle, evidence model, artifact metadata and project-specific UX because these encode the product’s differentiation and safety invariants. Reuse mature libraries for HTTP, schema validation, database access/migrations, local inference, browser automation, rendering and protocol implementations after licensing/security review. Do not reinvent an entire workflow engine, model proxy, browser engine or video encoder unless a measured requirement cannot be met. Conversely, do not outsource the policy/approval authority to an external framework that cannot enforce the product’s exact rules.

## 25.5 Naming and trademark diligence

“Omnitrix” is the current internal project codename, not a cleared public brand. The word is associated with existing entertainment intellectual property, so brand-confusion and trademark diligence is a launch gate, not a task to defer until after publishing. Search the official trademark registries for India and every intended launch jurisdiction, relevant goods/services classes and similar spellings; check copyright, app-store naming and domain conflicts separately. Public search tools are discovery aids, not legal opinions. This blueprint does not determine whether the name is legally available. Keep internal repository naming separate from final public branding until the owner has completed appropriate checks and, if needed, obtained qualified legal advice [S19].

---

# 26. Technology Decisions and Recommended Stack

## 26.1 Decision summary

| Area | Recommended starting point | Why | Replace/upgrade when |
|---|---|---|---|
| Core language | Python, current repo | Already implemented; broad model/tool/media ecosystem; readable for iterative development | Only if a measured boundary/scale requirement justifies a new component. |
| App architecture | Modular monolith with package boundaries | Simple local operations and testability | Extract runtime/stream gateway only where isolation/concurrency requires. |
| State database | SQLite + explicit migrations | Local, no server bill, transactional run state; WAL and backup behavior must be understood and tested [S21] | Multi-user concurrent server requirements become real. |
| Artifact storage | Managed local filesystem/content-addressed paths + metadata table | Low-cost, supports binary outputs | Larger multi-host storage needs. |
| Model config | Versioned JSON/YAML config validated by schema | Human-editable, easy onboarding | Do not add dynamic config server without need. |
| Tool catalog | Versioned `tools_registry.json` plus trusted implementation registry | Search/reuse and permission metadata separate from executable code | Catalog size/ownership demands more advanced query index. |
| HTTP API | Framework chosen after smallest viable need (FastAPI is a candidate) | Python fit and typed API patterns; confirm dependency/cost/license | When UI/API stable; not needed before local in-process vertical slice. |
| Event transport | Local event interface first; SSE/WebSocket adapter later | Avoid coupling logic to transport | Once Android streaming starts. |
| Local model runtime | Optional Ollama adapter | Local/offline path; existing compatible interface can reduce effort | Hardware/model benchmark favours another runtime. |
| Remote model adapter | Existing Google integration plus future adapters | Protect current foundation | Add only after config/test/provider privacy review. |
| Workspace | Scoped local worker first; rootless container when available | Low-cost staged safety | Untrusted code execution requires actual isolation before wider use. |
| Browser | Playwright candidate, isolated contexts | Established automation/isolation model [S15] | If target environment requires an alternative. |
| Android | Kotlin + Jetpack Compose | Native UX and state-driven UI [S16] | Keep API contracts stable; platform choice revisited only before substantial investment. |
| Tracing | Structured log/event, optional OpenTelemetry | Debuggable without hosted dependency | When tracing across many components is useful. |
| Version control | GitHub repo, branches/PRs/CI | Shared reviewed code and project decisions | Keep secrets and private memories out of repo. |

## 26.2 Dependency policy

Before adding a dependency, record purpose, official source, version, license, maintenance/security status, transitive cost and alternatives. Pin/lock dependencies. Avoid adding a heavy framework for a feature that needs only a small adapter. Update deliberately—one dependency group at a time—and run compatibility tests. A package update is not “safe” solely because CI compiles.

## 26.3 Zero-cost operating mode

Default settings:

```yaml
runtime:
  mode: local_first
  allow_paid_providers: false
  allow_unknown_cost_providers: false
  allow_remote_workspace: false
  allow_remote_telemetry: false
  require_approval_for_external_mutation: true
  require_approval_for_dependency_install: true
  default_network_policy: restricted
  require_sandbox_for_generated_code: true
```

This is a policy example, not the current repository config format. Ensure config values are validated at startup and that missing values choose safe defaults. A feature may still need internet for public research or provider calls; the spend switch only governs money, while data-egress policy separately governs remote data disclosure.

## 26.4 Operating mode profiles

- `strict_local`: no remote model/data egress; local tools only; best for private project work.
- `zero_cost_remote_allowed`: can use configured providers whose cost state is explicitly free and whose data policy permits use; stop on uncertain costs/quota.
- `owner_approved_paid`: disabled by default; activation requires explicit settings confirmation, provider-specific budget cap and visibility at run start.
- `offline_read_only`: direct response from available local model/docs and read-only local tools; mark unavailable capabilities clearly.

Changing profile invalidates queued action eligibility and may invalidate existing approvals if data or cost policy changes.

---

# 27. Implementation Roadmap and Correct Sequence

## 27.1 Strategy: build vertical slices, not disconnected infrastructure

Each phase must leave the project in a runnable state. Build one small end-to-end feature, instrument it, test it, then extend. Do not implement Android UI that relies on an unstable state model; do not stream a terminal before a safe workspace exists; do not expand tool autonomy before permissions and recovery work.

**Deliverables:** approved PRD and decision ledger; inventory existing code/tests; current-run behavior summary; usable README and developer runbook; verified dependency/install strategy; configuration/security review; branch/PR conventions; feature checklist.

**Tasks:** capture current status and test baseline; identify existing implementation vs aspirational features; locate TODOs and undocumented assumptions; run tests; document current provider config and missing capabilities; create ADR template; verify `.gitignore` and `.env.example`; establish zero-cost policy tests; recover exact commands and dependency versions from the actual development environment/CI rather than inventing them. The public `main` snapshot inspected for v1.1 has a minimal README and no visible root-level dependency manifest, so this is a concrete cleanup item.

**Gate:** a new developer can reproduce setup and tests from documented steps, and no destructive architectural rewrite is in progress.

## 27.3 Phase 1 — stabilize core contracts

**Deliverables:** versioned domain entities; error taxonomy; plan and task transition tests; extend approval fingerprint to cover all relevant scopes/targets/resources/verification/policy fields; typed `WorkerRequest`/`WorkerResult`; structured event contract; budget guard.

**Tasks:** preserve current task graph validations; make state transition rules explicit; create stable IDs; enforce schema validation at every tool boundary; define idempotency/retry flags; remove provider-specific conditionals from core where feasible.

**Gate:** invalid plans, invalid tool args, stale approvals, paid providers under zero-cost and untrusted outputs cannot trigger side effects in tests.

## 27.4 Phase 2 — durable local state and recovery

**Implementation status as of 13 October 2026 — in progress, not complete.**

**Implemented foundation:** versioned SQLite schema through v3; durable run/task/attempt/event/approval/artifact metadata; opt-in journal integration for the initial task lifecycle; tool-execution claims and duplicate blocking; logical action identity that excludes attempt IDs; append-only reconciliation assertions; read-only run recovery snapshots and a conservative recovery classifier; migration, reopen, cross-attempt identity, reconciliation and subprocess crash-window tests.

**Still required:** durable restoration of an entire run; a verified checkpoint/replay algorithm; pause/cancel/resume; automatic policy and approval revalidation; provider/tool-specific reconciliation with validated evidence; a safe retry protocol for confirmed-not-applied actions; backups and retention cleanup; broader fault injection at every meaningful checkpoint.

**Gate:** killing the process at controlled points must not corrupt the run or repeat non-idempotent side effects blindly. The present implementation satisfies only a subset of this gate: it preserves evidence and blocks ambiguous duplicate actions, but does not automatically resume work.

## 27.5 Phase 3 — tool registry and procurement

**Deliverables:** schema-validated catalog; tool registration adapter; `tools_registry.json` sample; searchable existing-capability index; procurement report; disable/revoke flow; license/provenance fields.

**Tasks:** seed actual built-in tools; add manifest validator; create procurement checklist/rubric; test unknown-manifest rejection; route new integrations through adapters; keep executable imports restricted to trusted code.

**Gate:** Omnitrix can answer “what tool already does this?” with evidence and can demonstrate safe reuse without installation or arbitrary import.

## 27.6 Phase 4 — model routing, cost and quality evaluation

**Deliverables:** expanded provider capability metadata; model-health/cooldown; strict spend modes; routing reasons; deterministic adapter contract tests; model benchmark harness; local provider feasibility report from actual hardware.

**Tasks:** add failure normalization; fallback eligibility matrix; quota exhaustion handling; structured output checks; one additional adapter only if the test workload demonstrates value; benchmark local model sizes before download.

**Gate:** provider outage/invalid key/quota exhausted never creates silent paid usage or unauthorized data egress.

## 27.7 Phase 5 — verified artifact workflow and confined workspace

**Deliverables:** workspace/artifact interface; dedicated workspace root; scoped filesystem tools; command runner limits; artifact hashing/validation; sandbox strategy; safe cleanup.

**Tasks:** test traversal/symlink escape; add argument-based process invocation; capture stdout/stderr as artifacts; classify commands by risk; validate output file MIME/size; build in a disposable directory; ensure user files are never overwritten without approval.

**Gate:** create/edit/test one small project artifact end-to-end with verified output and rollback; no arbitrary host-root execution.

## 27.8 Phase 6 — GitHub development workflow

**Deliverables:** least-privilege GitHub integration; create feature branch; inspect diffs; run tests; open PR; status and review summary; CI gate and secret scanning.

**Tasks:** distinguish local commits/pushes/merges; avoid elevated workflows for untrusted PR code; record commit SHA; ensure source update and PRD update when behavior changes.

**Gate:** full branch/PR lifecycle works in a test repository without exposing secrets; merges remain human-controlled unless explicitly changed later.

## 27.9 Phase 7 — client API and Android chat

**Deliverables:** API v1 schemas, authentication/pairing, native Compose conversation screen, plan approval screen, run timeline, artifacts list, reconnect/cancel/pause and clear connection/spend state.

**Tasks:** make API commands idempotent; handle app background/kill; implement state snapshot/event replay; secure token storage; accessibility; end-to-end Android test against local control plane.

**Gate:** restart/disconnect cannot lose run status or duplicate command; risky approval visibly binds to exact plan hash.

## 27.10 Phase 8 — live browser/terminal workspace

**Deliverables:** sandboxed browser/terminal, structured log streaming, file/artifact viewer, scoped input relay, expiry/revocation, snapshot restore and connection recovery.

**Tasks:** start with text stream and screenshots; benchmark latency; add visual WebRTC stream only if needed; test view-only vs input scopes; test revoked token and app disconnect.

**Gate:** no host privileged access; remote input routes only into assigned workspace; revocation blocks future input; reconnection preserves consistent state.

## 27.11 Phase 9 — modality-specific skills

Ship each skill independently with its own quality profile: research/source comparison; code/build; data/science; graphics/images; audio/music; video; 3D/scientific animation; games/APKs. Add only when the toolchain is available and tests can be run. Do not declare all capabilities done because the registry lists them.

**Gate:** one end-to-end demonstration + boundary/failure cases + artifact inspection + rollback/disable path for each released skill.

## 27.12 Phase 10 — voice and broader device integration

Start with push-to-talk and transcripts. Evaluate local vs remote STT/TTS, battery, latency and accessibility. Add opt-in device action capabilities individually, each behind Android permissions and the normal run policy. Consider wake word only after the app lifecycle, data retention and accidental activation cases are proven.

**Gate:** raw audio behavior is transparent, dangerous/irreversible actions require visible confirmation, denied permissions fail gracefully and audio can be fully disabled.

## 27.13 Phase 11 — hardening and optional multi-user support

Only after the personal single-user path works: concurrency/load testing, optional remote deployment, multi-user roles, server database, quotas and remote workspace lifecycle. Add these only for demonstrated need and only with privacy/auth model review. Two humans may pair for review, but that does not require building enterprise multi-tenancy in MVP.

## 27.14 Dependency map

Core plan/policy → durable state → tool registry → routing and budget → workspace/artifacts → GitHub workflow → API/events → Android chat → workspace streaming → multimodal skill suite → voice. Security, tests, quality, observability and docs run through every phase, not only at the end.

## 27.15 Stop/go rules

Stop a phase when core tests regress, a new dependency adds unexplained cost, the architecture requires broad unrelated rewrites, there is no clean rollback, or quality evidence is missing. Go forward only after the phase gate passes. If time/resources are limited, reduce feature breadth or defer expensive modules; never silently reduce the agreed quality floor for a released capability.

---

# 28. Repository Structure and Modular Extension Seams

## 28.1 Guiding rule

The following is a **target structure**, not an instruction to move every file immediately. Keep existing stable modules and migrate gradually with tests. A layout change should be justified by a requirement or repeated maintenance pain—not by aesthetics alone.

```text
omnimatrix/
├── README.md
├── PRD.md                         # approved product blueprint or pointer to current version
├── ARCHITECTURE.md                # short architecture map / invariants
├── BLUEPRINT.md                   # preserve current project conventions if it remains active
├── pyproject.toml                 # dependencies, tool config, test settings
├── .env.example                   # placeholder names only
├── .gitignore
├── config/
│   ├── app.example.yaml
│   ├── models.example.json
│   └── policies.example.yaml
├── schemas/
│   ├── run-event.v1.json
│   ├── tool-manifest.v1.json
│   └── skill-manifest.v1.json
├── docs/
│   ├── adr/ADR-0001-*.md
│   ├── runbooks/
│   ├── research/
│   └── release-notes/
├── core/
│   ├── domain/                    # typed entities / enums / contracts
│   ├── application/               # use cases, APIs, command/query services
│   ├── orchestrator/              # retain current modules; evolve run engine
│   ├── routing/                   # routing policies and eligibility reasons
│   ├── policy/                    # permissions, risk, cost, data egress, approvals
│   ├── models/                    # retain adapters/registry, add contract tests
│   ├── tools/                     # registry, executor and tool adapters
│   │   ├── builtin/
│   │   └── adapters/
│   ├── procurement/               # catalog search, scoring, provenance
│   ├── skills/                    # manifest loader and skill interfaces
│   ├── memory/                    # categories, review, retrieval and deletion
│   ├── persistence/               # repositories, migrations, transactions
│   ├── events/                    # event schema, publisher and subscribers
│   ├── artifacts/                 # files, hashes, previews and retention
│   ├── workspace/                 # isolated runtime abstractions
│   ├── verification/              # checks, result evidence and profiles
│   └── observability/              # logs, traces, metrics, redaction
├── api/                            # optional transport adapters; no domain policy
├── clients/
│   └── android/                    # later native Kotlin/Compose app
├── config_examples/
│   ├── tools_registry.example.json
│   └── skills_registry.example.json
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── end_to_end/
│   ├── fault_injection/
│   ├── security/
│   └── evaluations/
└── scripts/                        # safe development/validation commands
```

## 28.2 Dependency direction

`domain` depends on standard library/types wherever practical. `application` depends on domain interfaces. Infrastructure adapters implement those interfaces. UI/API depends on application services, not direct database/tool internals. `orchestrator` coordinates interfaces but must not import every provider’s SDK. Plugins/skills call granted interfaces. A tool does not import the mobile client; a database repository does not choose a model; model adapters do not authorize shell access.

## 28.3 When to create a module

Create a new package when it has a distinct responsibility, contract, tests or lifecycle—not for every single class. Avoid premature abstraction if only one simple function exists, but use an interface at replacement boundaries (model providers, runtime, persistence, tool executor, events, storage). Keep module count understandable and package names meaningful.

## 28.4 Refactoring protocol

1. Capture current test baseline and Git working tree.
2. Identify public imports/interfaces and callers.
3. Add characterization tests for current behavior.
4. Extract one seam with compatibility imports/aliases if needed.
5. Update tests and references in the same small PR.
6. Run tests and compare outputs.
7. Remove compatibility path only in a separate approved cleanup after callers are migrated.
8. Update architecture map and ADR if the dependency graph changes.

---

# 29. Functional Requirements Catalogue

Each requirement ID is stable for issues and tests. Priority tags: **P0** safety/core, **P1** initial useful release, **P2** next stages, **P3** future capability. The status is target requirement unless specifically described under the current baseline in Sections 9–10.

| ID | Priority | Requirement | Acceptance evidence |
|---|---|---|---|
| FR-001 | P0 | Accept ordinary natural-language input and preserve the original objective separately from generated interpretation. | Tests show objective remains unchanged across planning/attempts; edits create new versions. |
| FR-002 | P0 | Distinguish conversational, learn-only, read/research, mutation and clarification-needed modes. | Mode fixtures show no tool execution in observation-only messages. |
| FR-003 | P0 | Validate plans against schema, unique IDs, dependencies, self-cycles and graph cycles before execution. | Existing planner tests plus malformed-plan fixtures. |
| FR-004 | P0 | Bind approval to canonical plan fingerprint, relevant scopes, targets, policy and verification fields. | Tamper any protected field; execution is rejected. |
| FR-005 | P0 | Authorize every tool invocation in deterministic code; fail closed on unknown tool/capability. | Negative permission tests; no implementation path bypasses executor. |
| FR-006 | P0 | Enforce strict zero-cost mode before sending external requests. | Simulated paid/unknown-cost model is rejected before adapter network call. |
| FR-007 | P0 | Treat external/retrieved/tool/model content as untrusted data. | Prompt-injection fixture cannot alter policy or create new grants. |
| FR-008 | P0 | Never claim a mutation, test, build or artifact succeeded without observed evidence. | Final-report fixtures reject unsupported success statements. |
| FR-009 | P0 | Require explicit authorization for R3/R4 effects under risk policy. | Tool/action matrix asserts correct approval requirement per risk. |
| FR-010 | P0 | Keep credentials outside prompts, Git and routine logs. | Secret sentinel test across logs, responses, artifacts and diagnostics. |
| FR-011 | P1 | Register model definitions with capabilities, provider and enabled state via validated configuration. | Bad config gives actionable error; disabled provider is not selected. |
| FR-012 | P1 | Normalize provider responses/errors behind a shared adapter interface. | Provider contract suite passes against fakes and each enabled adapter. |
| FR-013 | P1 | Filter models by capability, context, privacy and cost before ranking. | Candidate trace shows hard constraints are not overridden by ranking. |
| FR-014 | P1 | Maintain per-provider health, cooldown and bounded retry policy. | Rate-limit/outage tests show no retry storm. |
| FR-015 | P1 | Permit only bounded repair of malformed model output. | Invalid output is never passed downstream before validation. |
| FR-016 | P1 | Store run/task/attempt state durably and restore after process restart. | Crash/restart fault injection resumes from checkpoint. |
| FR-017 | P1 | Expose canonical state transitions and durable event sequence. | Replay after cursor restores identical timeline without duplicates. |
| FR-018 | P1 | Distinguish succeeded, partial, failed, cancelled, blocked and unknown outcome. | Status transition tests and final-report mapping pass. |
| FR-019 | P1 | Support pause, cancel and resume with policy rechecks. | Cancellation prevents new steps; resume revalidates approval/scopes. |
| FR-020 | P1 | Classify task operations for idempotency and retry safety. | Non-idempotent unknown outcome does not auto-retry. |
| FR-021 | P1 | Attach explicit verification criteria and evidence links to nontrivial tasks. | Required criteria either pass or result cannot be `SUCCEEDED`. |
| FR-022 | P1 | Maintain tool registry separate from executable implementations. | Catalog parse cannot import or execute unknown code. |
| FR-023 | P1 | Run procurement before custom implementation or dependency installation. | Example request recommends an existing matching tool with evidence. |
| FR-024 | P1 | Record tool version/schema/provenance/license/network/risk/timeout metadata. | Enabled tools without required metadata are rejected. |
| FR-025 | P1 | Disable/revoke a tool without unrelated core rewrites. | Revocation removes tool from new model requests and executor authorization. |
| FR-026 | P1 | Scope filesystem operations to workspaces and block traversal/symlink escape. | Path attack tests cannot read/write outside allowed root. |
| FR-027 | P1 | Confine generated/untrusted code to an explicitly approved runtime. | Missing sandbox disables execution instead of host fallback. |
| FR-028 | P1 | Record artifacts with hashes, producer, parent inputs and validation state. | Artifact provenance tests reproduce metadata; tampering changes hash. |
| FR-029 | P1 | Keep user preferences, project knowledge, conversation history and run state separate. | Access/retention/delete tests for each category. |
| FR-030 | P1 | Propose durable memory changes for user review under approved memory settings. | Learn-only test proposes but does not silently persist a preference. |
| FR-031 | P1 | Use GitHub branch/PR workflow and maintain verifiable commit/diff evidence. | Test repository flow records SHA and test status before PR/merge. |
| FR-032 | P1 | Maintain traceable, privacy-filtered observability. | Run can be debugged by IDs without leaking secret sentinel data. |
| FR-033 | P1 | Produce a truthful final result with done/failed/unverified sections. | Golden task eval checks claim-to-evidence coverage. |
| FR-034 | P2 | Expose stable versioned API for run creation, status, events, approvals, cancellation and artifacts. | Contract tests include idempotency, auth and schema failures. |
| FR-035 | P2 | Build a native Android chat app as a client of the canonical API. | Android app survives orientation changes, process death and reconnect. |
| FR-036 | P2 | Securely pair Android to the control plane with scoped/revocable credentials. | Pair/revoke/expiry/replay tests pass. |
| FR-037 | P2 | Support event cursor replay and state resync in clients. | Disconnect/reconnect has no missing or duplicated action. |
| FR-038 | P2 | Display exact plan/scopes/cost mode and changed plan version before approval. | Usability/security test confirms approval is intelligible. |
| FR-039 | P2 | Provide workspace view, logs, browser/terminal and artifacts under isolated runtime. | Security gate + workflow acceptance tests pass. |
| FR-040 | P2 | Separate stream viewing rights from interactive workspace input rights. | View-only token rejects keyboard/mouse/terminal mutation events. |
| FR-041 | P2 | Retain workspace logs/artifacts after a disconnect or runtime failure when possible. | Runtime interruption tests preserve output and error state. |
| FR-042 | P2 | Register versioned skills with schemas, permissions, outputs and quality profiles. | A sample skill is added without core/UI rewrite. |
| FR-043 | P2 | Apply per-modality quality gate before marking deliverable as ready. | Invalid media/build outputs fail release despite model-generated explanation. |
| FR-044 | P2 | Make optional modules feature-flagged and independently disableable. | Disabling streaming/voice does not break text chat and run history. |
| FR-045 | P3 | Support push-to-talk STT/TTS with visible capture state and confirmation before risky action. | No hidden recording; failed transcription cannot trigger the wrong action. |
| FR-046 | P3 | Evaluate wake word only after battery/privacy/safety and platform testing. | Decision is documented; default off until explicit release approval. |
| FR-047 | P3 | Support multiple human reviewers only with explicit roles and access scopes. | Unauthorized reviewer cannot approve or retrieve other user’s runs. |
| FR-048 | P3 | Support optional remote deployment only with secure auth, privacy and operational budget review. | Deployment runbook, cost guard, security check and rollback pass. |
| FR-049 | P1 | Preserve a documented quality floor regardless of capability frequency. | Every enabled skill has a quality profile and required tests. |
| FR-050 | P1 | Ensure no paid/unverified option is silently selected after quota or provider failure. | Budget fault injection asserts zero paid adapter calls under strict mode. |

---

# 30. Risks, Open Decisions, and Decision Ledger

## 30.1 Risk register

| Risk | Likelihood / impact | Mitigation | Trigger for review |
|---|---|---|---|
| R-01 Scope explosion across chat, workspace, voice and media | High / High | Follow tiered roadmap, one vertical slice per phase, hard gates | Two phases depend on unbuilt future infrastructure or PRs routinely rewrite multiple subsystems. |
| R-02 Free inference quota/model availability changes | High / Medium | Local-first option, configurable adapters, strict no-paid fallback | Provider quota or terms change, or model stops returning required schema. |
| R-03 Unsafe tool/host access | Medium / Critical | Deterministic permission broker, sandbox, least privilege, adversarial tests | Any tool executes outside declared scope. |
| R-04 Incorrect success reports | Medium / High | Independent verification, evidence graph, claim-to-evidence tests | Any user-facing claim lacks supporting record. |
| R-05 Duplicate non-idempotent action on retry | Medium / High | Idempotency ledger, outcome reconciliation, manual pause | Network timeout after an external mutation with no confirmation. |
| R-06 Feature quality inconsistent across modalities | High / High | Capability-specific quality profiles and acceptance gates | Capability is marked enabled without artifact-level validation. |
| R-07 Framework lock-in / repeated architecture migration | Medium / Medium | Thin adapters, ADR, prototype benchmark before adoption | Framework dependency spreads into domain model or provider adapters. |
| R-08 Public/private project data leakage | Medium / Critical | Separate project memory and personal data, secret scanning, opt-in export | Raw conversation or credentials appear in Git/logs/remote request. |
| R-09 Mobile remote endpoint exposed | Medium / Critical | Pairing, scoped tokens, HTTPS, no public raw shell, revocation tests | Tunnel/LAN server becomes reachable outside intended network. |
| R-10 Workspace isolation insufficient | Medium / Critical | Rootless sandbox, network limits, path tests, host mounts disabled | Generated code runs on host or can escape workspace. |
| R-11 Live streaming adds latency/complexity early | High / Medium | Build event/log UI first; WebRTC only after security/runtime | Core progress/recovery still unreliable when streaming work begins. |
| R-12 Maintenance burden from too many agents/tools | High / Medium | Require quantified value and procurement review | Multiple components duplicate work with unclear ownership. |
| R-13 Model routing scores falsely precise | Medium / Medium | Explainable hard filters + measured evals; avoid ungrounded rankings | Routing decisions made from invented provider capabilities/quality. |
| R-14 License/trademark issue blocks public use | Low–Medium / High | Provenance and license review; brand clearance before publication | App is prepared for store/public launch under project codename. |
| R-15 SQLite/run state schema evolves poorly | Medium / High | Migrations, repository boundary, backup/restore and version tests | Schema change breaks upgrade or leaves orphaned artifacts/events. |
| R-16 Personal compute insufficient for local model/media tasks | High / Medium | Benchmark early; use smaller/local optional models; defer heavyweight features | RAM/VRAM/disk limits repeatedly halt workloads. |
| R-17 AI coding assistant invents repository state | Medium / High | Require fresh repo inspection/commands/evidence and explicit report | Assistant describes tests/branches/merges without tool output. |
| R-18 PRD becomes stale as code evolves | High / Medium | Change checklist, ADRs and versioned test evidence | Behavior changes without documentation/acceptance updates. |

## 30.2 Open questions that must not block unrelated work

| ID | Open question | Default until decided | When it becomes blocking |
|---|---|---|---|
| OQ-01 | Where will the control plane run long term: laptop, home server or optional hosted environment? | Local laptop for early phases; no public exposure. | Before Android pairing / remote workspace. |
| OQ-02 | What are laptop CPU/RAM/GPU/storage specs? | Do not make local model performance promises or auto-download models. | Before selecting a local inference profile or media workload. |
| OQ-03 | Which providers/accounts are genuinely available at no cost? | Disable unverified provider config and spend by default. | Before enabling a remote adapter. |
| OQ-04 | What is the preferred public product name after trademark diligence? | Omnitrix is an internal codename until cleared. | Before public app-store/commercial branding. |
| OQ-05 | Is multi-user/reviewer support needed soon? | One owner/operator; add reviewer only after explicit role definition. | Before exposing remote endpoints to a second person. |
| OQ-06 | How long should conversations, memories, artifacts and logs be retained? | Minimal retention by category, user-controlled; no “store everything forever.” | Before external deployment or long-term automatic capture. |
| OQ-07 | Is browser interaction required to use personal login sessions? | No personal browser cookies; isolated fresh profile only. | Before any account-bound automation. |
| OQ-08 | What remote streaming latency/resolution is acceptable? | Event log + occasional screenshot first. | Before selecting WebRTC or video transport. |
| OQ-09 | Which modality is highest priority after core reliability? | Choose based on user demand and feasibility; keep quality floor constant. | At Phase 9 planning. |
| OQ-10 | Should a paid tier ever be enabled? | Strict zero-cost mode; all pay-as-you-go disabled. | Only after explicit budget and privacy decision. |

## 30.3 Decision ledger

| Decision | Status | Rationale / consequence |
|---|---|---|
| Orchestrator-centered product; agents are bounded specialists | DECIDED | Communication/planning/recovery are the differentiation; agent count alone is not value. |
| Librarian/procurement checks existing tools first | DECIDED | Avoid reinvention and dependency sprawl; evidence and license matter. |
| `$0` default and no silent paid fallback | DECIDED | Hard operational constraint; free provider credits/quota may change. |
| GitHub is shared code/project decision memory | DECIDED | Durable source of truth for technical decisions, not a dump of private chats. |
| Native Android app rather than Termux as end user UX | DECIDED | Phone-first normal app; chat plus workspace later. |
| Virtual workspace visible/streamed on phone | DECIDED as long-term direction | Build after runtime security, durable state and event API. |
| Learn/Observe mode for untagged thought | DECIDED concept | Avoid treating all speech/text as executable commands; memory writes reviewable. |
| High-quality graphics, music/audio, video, 3D/science animation, software/APKs and other capabilities | DECIDED quality doctrine; implementation scope phased | Each enabled modality needs its own release gate. |
| Python core already in repo; preserve and extend | RECOMMENDED based on current repo | Minimizes rewrite; validate current branch before every substantial change. |
| Modular monolith + SQLite, separate isolated runtime | RECOMMENDED | Best balance for early local-first personal project. |
| Kotlin/Jetpack Compose | RECOMMENDED | Native client with state-driven architecture; revisit only before major investment. |
| MCP integration | CANDIDATE / staged | Useful interop but separate trust boundary; not a shortcut around local permission control. |
| A2A protocol | DEFERRED | Independent agent service communication not needed for current personal MVP. |
| Wake word/always-on voice | DEFERRED | Privacy, false activation and battery costs; push-to-talk first. |
| Hosted sandbox/managed GPU | DEFERRED / optional | Conflicts with strict zero-spend default unless explicitly approved. |

## 30.4 Change-control rule

When a new idea conflicts with the blueprint, do not suppress the idea or silently overwrite the blueprint. Write a short proposal: objective; user value; affected decisions; alternatives; dependency/cost/privacy risks; reversible experiment; tests; impact on roadmap. If accepted, update the decision ledger and, for major architecture changes, add an ADR. The repository source may show how the app behaves today; the PRD describes the intended product; a conflict between them is work to resolve, not evidence that either should automatically win.

---


# Appendix A. Research Sources and Evidence Register

## A.1 How to read this register

These sources are primary product documentation, protocol specifications, security guidance or official platform documentation. They establish what the source says it supports; they do **not** independently prove that a product is best, secure in every deployment, free forever, or suitable for Omnitrix. Recommendations in this PRD are engineering judgments constrained by the current repository, the $0 default, user privacy and the staged roadmap. Re-check documentation, version numbers, licenses, pricing and terms before adopting a dependency. Links were reviewed for this research snapshot on 11 October 2026; pages may subsequently change.

| ID | Primary source | Why it is cited / limits |
|---|---|---|
| S01 | [Microsoft Agent Framework documentation](https://learn.microsoft.com/en-us/agent-framework/) | Workflow, handoff, checkpoint and human-in-the-loop patterns. Studied as a reference, not selected as Omnitrix's core. |
| S02 | [Google Agent Development Kit documentation](https://google.github.io/adk-docs/) | Workflow and agent orchestration patterns. APIs and workflow recommendations evolve; verify the exact version before prototyping. |
| S03 | [LangGraph persistence and durable execution](https://langchain-ai.github.io/langgraph/concepts/durable_execution/) | Checkpoints and resumption patterns. The existence of persistence features does not remove the need to define Omnitrix's own domain state and approval invariants. |
| S04 | [OpenAI Agents SDK guide](https://developers.openai.com/api/docs/guides/agents/sdk) | Agent runtime, handoffs, guardrails, state, sandbox and evaluation concepts. Vendor-specific functionality must remain behind adapters if used. |
| S05 | [LiteLLM documentation](https://docs.litellm.ai/docs/) and [routing](https://docs.litellm.ai/docs/routing) | Multi-provider interface and routing/retry patterns. Its routing/cost features do not replace a separate, fail-closed spend guard. |
| S06 | [Ollama OpenAI compatibility documentation](https://docs.ollama.com/api/openai-compatibility) | Local inference integration path and compatibility boundaries. Support is a subset; per-model capabilities must be tested rather than assumed. |
| S07 | [Hugging Face Inference Providers pricing and billing](https://huggingface.co/docs/inference-providers/en/pricing) | Illustrates that free credits are limited/changeable and pay-as-you-go may be available after credits. This is evidence for strict spend controls, not a claim that this provider is required. |
| S08 | [Model Context Protocol specification](https://modelcontextprotocol.io/specification/) | Protocol overview and tool/resource interoperability. Protocol support does not imply that a connected tool is trusted or authorized. |
| S09 | [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) | HTTP authorization and token-handling boundary. Transport-specific requirements differ; verify the specification version supported by each server/client. |
| S10 | [Agent2Agent protocol documentation](https://a2a-protocol.org/) | Cross-agent interoperability, task lifecycle and discovery concepts. Deferred until a real cross-process or cross-vendor need exists. |
| S11 | [GitHub Actions: securely using `pull_request_target`](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target) | Explains elevated trust and secret exposure risks when handling untrusted pull-request code. Workflows must be reviewed against current GitHub guidance. |
| S12 | [OpenHands runtime architecture](https://github.com/OpenHands/docs/blob/main/openhands/usage/architecture/runtime.mdx) | Example of separating orchestration from a sandboxed code-execution runtime. Do not infer complete security from the word “sandbox.” |
| S13 | [Daytona sandbox documentation](https://www.daytona.io/docs/en/sandboxes/) | Reference for isolated environments and resource allocation. Hosted services are not a default dependency under the zero-cost rule. |
| S14 | [Docker rootless mode](https://docs.docker.com/engine/security/rootless/) and [seccomp profiles](https://docs.docker.com/engine/security/seccomp/) | Defense-in-depth controls for containerized execution. Containers are not automatically a perfect security boundary; host configuration and workload threat model matter. |
| S15 | [Playwright browser contexts](https://playwright.dev/docs/browser-contexts) | Isolated browser contexts and separation of cookies/storage. Isolation does not authorize account access or bypass site policies. |
| S16 | [Android Jetpack Compose UI architecture](https://developer.android.com/develop/ui/compose/architecture) and [app architecture guide](https://developer.android.com/topic/architecture) | State-driven UI and separation of UI, data and business layers. Supports a native client recommendation, not a requirement to build Android before the core is stable. |
| S17 | [OWASP GenAI / LLM Top 10 project](https://owasp.org/www-project-top-10-for-large-language-model-applications/) | Security risk taxonomy including prompt injection, disclosure, insecure output handling and excessive agency. A taxonomy is not a substitute for threat modeling and tests. |
| S18 | [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/) | Common names for trace, metric and log attributes. Telemetry must still be privacy-filtered; external export is disabled by default. |
| S19 | [IP India Trade Marks Registry](https://ipindia.gov.in/), [USPTO trademark search](https://www.uspto.gov/trademarks/search), and [EUIPO](https://euipo.europa.eu/) | Official starting points for name clearance in relevant jurisdictions. Search results do not themselves constitute legal advice or establish availability. |
| S20 | [OWASP Agentic AI security initiative / Agentic Applications Top 10](https://genai.owasp.org/2025/12/09/owasp-genai-security-project-releases-top-10-risks-and-mitigations-for-agentic-ai-security/) | Agent-specific risk classes and mitigations. Used to reinforce bounded authority, least privilege, deterministic controls and security testing. Re-check for newer revisions. |
| S21 | [SQLite Write-Ahead Logging](https://www.sqlite.org/wal.html) and [SQLite backup API](https://www.sqlite.org/backup.html) | Database behavior and backup/restore references. WAL improves reader/writer concurrency in specific ways but does not eliminate schema, locking, backup or corruption handling requirements. |
| S22 | [WebRTC security architecture (RFC 8827)](https://www.rfc-editor.org/rfc/rfc8827) | Security architecture for WebRTC. Relevant only if interactive live workspace streaming reaches the roadmap; authentication and authorization remain application responsibilities. |

## A.2 Research-derived decisions versus claims

- **Selected now:** preserve the current Python core; strengthen typed contracts, policy boundaries, durable state, evidence, tests and modularity before expanding the UI/runtime surface.
- **Recommended, not yet implemented:** SQLite-backed run journal and migrations; independently enforced cost/egress guard; approval fingerprints covering every behavior-changing field; tool procurement registry; isolated workspace runtime; versioned event API; native Android client after API stability.
- **Candidates, not commitments:** LiteLLM, Ollama, MCP, Playwright, OpenTelemetry, Docker/rootless runtime, WebRTC and hosted sandbox products. Adoption requires a focused prototype, version/license/security review, resource/cost estimate and tests.
- **Deferred:** mandatory cloud hosting, mandatory paid inference, always-on wake word, distributed microservices, A2A federation and a large permanent roster of role-labelled agents.
- **Not proven by these sources:** that any free tier will remain available, that any model is best for every modality, that a framework guarantees correct planning, that a container is escape-proof, that a generated artifact is high quality without inspection, or that the public name “Omnitrix” is legally available.

## A.3 Source refresh and contradiction procedure

Before a release that depends on an external product, the procurement record must include the exact URL, page title, access date, package/version, license, relevant capability claim, known limitations, security advisories checked, expected cost and a test showing the integration works in Omnitrix. If vendor docs conflict with observed behavior, prefer reproducible tests for runtime behavior and official terms for license/billing; document the discrepancy. Do not turn a search snippet into a product commitment. Revisit the landscape at least before public release and after any provider, protocol, pricing or security change that affects a hard requirement.

# Appendix B. Owner Acceptance Checklist for This Specification

This is a checklist for reviewing the document itself, not proof that the implementation already passes it.

- [ ] The owner confirms the core direction: orchestration and communication quality over agent count.
- [ ] The owner confirms the $0-by-default rule and no silent paid fallback.
- [ ] The owner confirms Learn/Observe mode must not execute actions or write memory without review.
- [ ] The owner confirms native Android is the intended eventual user experience and live workspace is staged after core safety/recovery.
- [ ] The owner confirms the modality quality floor applies to every capability that is enabled, even if used infrequently.
- [ ] Open questions remain open unless the owner explicitly decides them.
- [ ] The current repository has been re-inspected before implementation begins; source links in this document are not a substitute for fresh code/test evidence.
- [ ] The first implementation slice has measurable acceptance criteria, tests, rollback instructions and a clear stop/go gate.
- [ ] No credentials, raw private conversations or unrelated sensitive personal details are added to GitHub project memory.
- [ ] A versioned change record is created whenever this blueprint's accepted behavior changes.

# Appendix C. Change Log

| Version | Date | Change |
|---|---|---|
| 1.0 | 11 October 2026 | Initial large baseline draft: requirements, architecture, failure handling, quality doctrine, roadmap, risks and decision ledger. |
| 1.1 | 11 October 2026 | Added missing source register for all cited source IDs; expanded official primary-source research; clarified trademark diligence; added source refresh rules and owner acceptance checklist. |
| 1.2 | 13 October 2026 | Synchronized implementation status against the repository; documented schema-v3 journal, stable logical tool-action identity, append-only reconciliation evidence, conservative recovery classification, and remaining Phase 2 gaps. |
| 1.3 | 13 October 2026 | Added schema-v4 append-only checkpoints with canonical payload digests and read-only recovery inspection that blocks on checkpoint corruption or inconsistent run/task/attempt/tool references; clarified that complete execution-position checkpointing and automatic restoration remain unimplemented. |
| 1.4 | 13 October 2026 | Integrated digest-checked checkpoints into live task/model/tool lifecycle boundaries, minimized checkpoint payloads to metadata and hashes, and added a real subprocess crash test proving a model-call boundary checkpoint survives process exit; full conversation/provider restoration and automatic resume remain unimplemented. |
| 1.5 | 13 October 2026 | Added real subprocess fault injection after a simulated external side effect but before tool-outcome persistence; verified the tool remains uncertain after restart and recovery requires reconciliation. Automatic replay/resume remains unimplemented. |
| 1.6 | 13 October 2026 | Added explicitly confirmed restart-from-objective for interrupted single-task runs only when integrity checks pass and no tool execution/tool-call boundary exists; records the interrupted attempt, creates a new attempt, and applies current runtime budgets/permissions. Full provider/chat restoration and restart after tool dispatch remain unsupported. |
| 1.7 | 13 October 2026 | Added fault injection after a successful tool outcome is durably committed but before the orchestrator consumes the result; verified the terminal tool record survives, the run remains non-terminal, and objective-only restart is blocked by any tool history. |
| 1.8 | 13 October 2026 | Added CLI commands to list recent run IDs without exposing objectives, inspect recovery disposition/integrity, enable journal-backed chat, and invoke the guarded restart only with explicit confirmation. |
| 1.9 | 13 October 2026 | Added a one-shot journaled `--run-objective` CLI mode that executes `run()` and reports its new run ID with the result, closing the CLI path for discovering eligible interrupted single-task runs. |
| 1.10 | 13 October 2026 | Added schema-v5 opt-in tool-result snapshots with a default-deny replay policy, a 16 KiB finite-JSON limit, SHA-256 verification, atomic terminal-outcome/snapshot commits, and tests/docs clarifying that result storage does not yet restore a live conversation or resume execution. |
| 1.11 | 13 October 2026 | Added a read-only replay-candidate resolver that requires exact run/task/action/tool/request identity, a unique successful execution, and a verified opted-in snapshot; all missing, mismatched, uncertain, or ambiguous candidates fail closed without returning result content. |

## Version 1.12 change log — schema-v6 transcript metadata groundwork

Schema v6 introduces an append-only model request/response metadata ledger with contiguous per-run sequence numbers, run/task/attempt linkage, provider/model labels, bounded tool-call counts, and optional SHA-256 digests. It stores no prompt or response bodies and uses database triggers to reject ordinary updates/deletes. This is intentionally not a complete transcript and cannot restore provider state. Live orchestrator instrumentation and process-crash verification remain open; automatic resume remains disabled.


## Version 1.13 change log — live model-call transcript instrumentation

The task execution loop now records canonical SHA-256 request and response fingerprints in the schema-v6 metadata ledger. Request fingerprints cover ordered message context, tool definitions and continuation state; response fingerprints cover normalized content, tool calls, usage metadata and continuation state. Only hashes and bounded metadata are persisted. A subprocess crash test verifies that an adapter crash leaves the request record durable and no fabricated response record. This does not restore provider state or enable automatic resume. Planner calls made outside a journaled task run are not covered.
