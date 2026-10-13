# Omnitrix

Omnitrix is an evolving, safety-minded AI orchestration project. It is intended to grow from a local chat-and-planning core into a system that can coordinate tools and specialized capabilities through explicit policies, verification, and durable execution state.

> **Project status:** early Python CLI prototype. It is not yet a fully autonomous desktop agent, phone app, or general-purpose system that can safely execute arbitrary real-world tasks.

## What exists today

The current codebase includes:

- An interactive command-line chat entry point.
- A model/provider abstraction and configuration-driven provider loading.
- An explicitly named offline demo provider that simulates responses without performing real model inference or external work.
- Structured task planning, plan validation, dependency-aware ordering, and passing completed dependency results to downstream tasks as untrusted context.
- A plan-approval fingerprint workflow and task lifecycle/execution observability.
- Opt-in SQLite run journaling with append-only, digest-checked checkpoints and read-only integrity-aware recovery inspection; it does not automatically resume interrupted work. The orchestrator now records ordered checkpoints at task start, model request/response boundaries, tool-call boundaries, and result/failure observation. Fault-injection tests cover a model-call crash, a crash after a simulated side effect but before its outcome is committed, and a crash after the tool outcome is committed but before the orchestrator consumes it. An explicitly confirmed restart-from-objective path is available only for interrupted single-task runs where integrity checks pass and no tool was dispatched; chat turns and runs with any tool execution remain blocked. The CLI exposes recent-run listing, read-only recovery inspection, and the same explicitly confirmed guarded restart.
- A Python `unittest` suite covering the core, planning, providers, CLI, and tool behavior.

Treat these as implemented foundations, not proof that every future capability is complete. Approval fingerprints currently cover the plan fields that exist today; an application must still obtain genuine user consent before executing an approved plan. The demo provider is simulated and must never be mistaken for live inference.

## Quick start

Use a Python interpreter compatible with the current codebase. The most recently validated development environment was Python 3.14.2.

From the repository root:

```bash
python --version
python -m unittest discover -s tests -v
python -m compileall -q core interfaces tests
python -m json.tool config/demo.models.json
```

Start an offline interactive session:

```bash
python -m interfaces.cli.main --config config/demo.models.json
```

Type a message, then enter `/exit` to quit. The demo provider deliberately labels its output as simulated. It does not call an external model.

### Durable recovery commands

Enable a local SQLite journal for an interactive session:

```bash
python -m interfaces.cli.main --config config/demo.models.json --journal .local/omnitrix.sqlite3
```

List run IDs without printing stored objectives, or inspect a run's recovery disposition:

```bash
python -m interfaces.cli.main --journal .local/omnitrix.sqlite3 --list-runs
python -m interfaces.cli.main --journal .local/omnitrix.sqlite3 --inspect-run RUN_ID
```

The only restart command requires the model config and an explicit confirmation flag. It succeeds only for an integrity-valid interrupted single-task run where no tool was dispatched:

```bash
python -m interfaces.cli.main --config config/demo.models.json --journal .local/omnitrix.sqlite3 --restart-run RUN_ID --confirm-restart-from-objective
```

Chat turns and runs with any tool execution remain blocked from objective-only restart. Protect the journal file: run/task payloads include objectives even though the run-list command does not reveal them.

## Model configuration and secrets

Model profiles live under `config/`. The offline profile is `config/demo.models.json`; provider credentials must not be committed to the repository. The Gemini adapter reads `GEMINI_API_KEY` from the process environment. Set it in your shell only when intentionally testing live provider access, and verify the configured model identifier against the provider's current documentation before relying on it.

The current application and test suite use Python's standard library; there is no third-party runtime dependency manifest or lockfile at this stage, and CI intentionally installs no packages. Re-check imports and update the packaging/lock strategy and CI deliberately if a third-party dependency is introduced.

## Project specifications

- [Product Requirements Document](docs/PRD.md) — version 1.8; implementation status snapshot dated 13 October 2026.
- [Recovery state machine](docs/RECOVERY_STATE_MACHINE.md) — conservative post-crash dispositions and reconciliation boundaries.
- [Staged roadmap](docs/ROADMAP.md) — current phase gates and verified completion status.

## Repository map

| Path | Purpose |
| --- | --- |
| `core/orchestrator/` | Planning, validation, task lifecycle, and orchestration |
| `core/models/` | Model types, registry, configuration loader, and provider adapters |
| `core/tools/` | Tool contracts, permissions, registry, and execution |
| `core/application/` | Chat application layer |
| `core/conversation/` | Conversation state |
| `interfaces/cli/` | Command-line entry point |
| `config/` | Model profiles, including the offline demo profile |
| `tests/` | Automated regression tests |
| `docs/ARCHITECTURE.md` | Current design boundaries and safety assumptions |
| `docs/ROADMAP.md` | Staged development plan |

## Engineering rules

- Prefer deterministic checks and explicit verification over trusting a model's claims of success.
- Keep external side effects behind registered tools and permission checks.
- Treat model-generated plans, tool output, and dependency results as untrusted input.
- Make failures visible; do not report success unless the relevant verifier passed.
- Preserve a zero-spend path through the offline demo provider. No silent fallback from a requested live provider to the demo provider.
- Keep changes small enough to test, but never lower correctness or quality requirements for a less frequently used feature.

## Development checks

Run the unit test suite and bytecode compilation before submitting changes:

```bash
python -m unittest discover -s tests -v
python -m compileall -q core interfaces tests
python -m json.tool config/demo.models.json
```

The project is still establishing a reproducible baseline. See [Architecture](docs/ARCHITECTURE.md) for current boundaries and [Roadmap](docs/ROADMAP.md) for the intended staged sequence.
