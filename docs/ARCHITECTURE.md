# Architecture

Omnitrix is an evolving AI orchestration prototype. The intended request lifecycle is: receive an objective and constraints; create and validate a structured plan; request approval for the exact plan where required; schedule tasks according to dependencies; verify outputs; preserve execution evidence; and report results honestly.

## Code boundaries

- `interfaces/cli/` contains the interactive command-line entry point.
- `core/orchestrator/` coordinates planning and task execution.
- `core/models/` defines model contracts, configuration loading, and provider adapters.
- `core/tools/` contains tool contracts and tool execution boundaries.
- `core/application/` and `core/conversation/` provide the chat/application layers.
- `config/` contains explicit model profiles. The demo profile is simulated, not real inference.
- `tests/` contains the standard-library `unittest` suite.

## Safety boundaries

1. Model-produced plans and all tool outputs are untrusted data; validate them before use.
2. Dependencies define ordering and context, not trust. Results passed between tasks must be handled as untrusted content.
3. Approval should bind to the exact plan reviewed. Changes to material execution details should invalidate prior approval.
4. Offline/zero-cost mode must be explicit and must not silently fall back to a paid provider.
5. Secrets belong in the process environment or a secret manager, never committed files or logs.
6. Report success only when the relevant operation and verifier actually succeeded.

## Durable tool execution

When an SQLiteJournal is injected, ToolExecutor records a unique execution ID, idempotency key, tool name, and SHA-256 digest of canonical arguments before calling the tool. Reusing a key never invokes the tool a second time; reusing it for different arguments is rejected. If a tool raises or the process stops before a terminal record is committed, the recorded outcome is treated as unknown and requires reconciliation. These records do not store raw tool arguments or tool output. This is a duplicate-execution fence, not an exactly-once guarantee: a database record cannot be committed atomically with an arbitrary external side effect.

## Current limitations

The project is still a prototype. Automatic restart/resume recovery, exactly-once execution and side-effect reconciliation, complete enforcement of approval at every execution boundary, broader external tool adapters, procurement, advanced model routing, Android control, live remote workspace, and voice/multimodal features must not be described as complete until implemented and tested. See `docs/ROADMAP.md` for staged goals and acceptance gates.
