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
- A typed tool-reconciliation verifier contract and registry with fail-closed validation. This is contract groundwork only: no concrete external-provider verifier is registered, and the contract does not authorize retries, replay, or automatic resume.
- An opt-in, read-only `workspace.inspect` tool that lists one directory or reads a bounded UTF-8 text file under a configured root. Hidden/secret-like paths, symlinks, binary files, and oversized files are denied; workspace access is not granted unless the operator passes an explicit CLI flag.
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
python -m interfaces.cli.main --config config/demo.models.json --journal .local/omnitrix.sqlite3 --run-objective "Summarize the task in one sentence"
```

The one-shot `--run-objective` command creates a durable `run()` record and prints its run ID with the result. The restart command requires the model config and an explicit confirmation flag. It succeeds only for an integrity-valid interrupted single-task run where no tool was dispatched:

```bash
python -m interfaces.cli.main --config config/demo.models.json --journal .local/omnitrix.sqlite3 --restart-run RUN_ID --confirm-restart-from-objective
```

Chat turns and runs with any tool execution remain blocked from objective-only restart. Protect the journal file: run/task payloads include objectives even though the run-list command does not reveal them.

### Explicit read-only workspace access

Workspace inspection is off by default. To let a model that supports tool calls inspect files under the current directory, run:

```bash
python -m interfaces.cli.main --config config/demo.models.json --allow-workspace-read --workspace-root .
```

Choose the root deliberately. The tool can list one directory at a time or read a UTF-8 text file up to 64 KiB. It hides dotfiles and common secret-like filenames, refuses symlink paths, and never writes or executes files. On operating systems that support directory-relative opens and `O_NOFOLLOW`, it pins the workspace root and opens each path component relative to a directory handle; unsupported systems fail closed when workspace access is explicitly enabled. To reduce exposure further, repeat `--workspace-allow` with relative path prefixes such as `src` or `README.md`; only those prefixes and their descendants can be inspected. An empty explicit allowlist denies all paths. Omitting the allowlist permits all otherwise-eligible paths under the configured root. This is not a complete OS sandbox or a per-task allowlist, so do not expose sensitive workspaces to an untrusted model provider. Tool output is untrusted input. The offline demo provider remains simulated and may not invoke tools.

Example restricted session:

```bash
python -m interfaces.cli.main --config config/demo.models.json --allow-workspace-read --workspace-root . --workspace-allow src --workspace-allow README.md
```

## Model configuration and secrets

Model profiles live under `config/`. The offline profile is `config/demo.models.json`; provider credentials must not be committed to the repository. The Gemini adapter reads `GEMINI_API_KEY` from the process environment. Set it in your shell only when intentionally testing live provider access, and verify the configured model identifier against the provider's current documentation before relying on it.

The core application uses the Python standard library, with one explicit runtime dependency (`cryptography`) for opt-in AES-GCM encrypted model-state snapshots. Install runtime dependencies with `python -m pip install -r requirements.txt`. CI installs this file before tests. The encryption key is supplied separately by the caller and is never stored in the SQLite journal.

## Project specifications

- [Product Requirements Document](docs/PRD.md) — version 1.27; implementation status snapshot dated 17 October 2026.
- [Recovery state machine](docs/RECOVERY_STATE_MACHINE.md) — conservative post-crash dispositions and reconciliation boundaries.
- [Staged roadmap](docs/ROADMAP.md) — current phase gates and verified completion status.

## Omnitrix Studio — main testing app

The main Studio interface lives in `webapp/`; the Python backend is `interfaces/web/server.py`. It is a browser app backed by the **existing Python Omnitrix core**, not a simulated UI shell.

### Start the full Studio in GitHub Codespaces

Open [Create/open an Omnitrix Codespace](https://codespaces.new/som76377-alt/omnimatrix). The checked-in devcontainer installs the existing Python dependencies, keeps forwarded port 8000 private, and starts the Studio supervisor automatically. Open the forwarded **Omnitrix Studio** port from the Codespaces Ports panel.

The startup script generates a runtime access token outside the repository. In the Codespaces terminal, print it and paste it into **Connect runtime** in the app:

```bash
cat /tmp/omnitrix-studio-runtime-token
```

The private port must remain private. The token is kept in that browser tab's session storage, not committed to Git. The startup profile grants the existing calculator tool, enables bounded read-only workspace inspection for selected source/documentation directories, and enables only the fixed test command `python -m unittest discover -s tests -v`. It does **not** expose a general shell, file writes, or arbitrary command execution.

The chat sends messages through `ChatApplication` and the existing `Omnitrix` orchestrator. The default `config/demo.models.json` profile deliberately uses the simulated offline provider, so replies are marked **OFFLINE DEMO** rather than presented as real inference. The workspace editor is read-only; it shows the active Codespace files when allowed and falls back to public `main` snapshots where the runtime denies access.

### GitHub-connected updates

On the normal, clean `main` checkout, the Codespaces supervisor checks `origin/main` about once per minute. It only uses `git fetch` followed by `git merge --ff-only` if the working tree is clean and the checkout is already on `main`. On a successful fast-forward it restarts the Python server with the same private runtime token; the browser's service worker checks for the new interface assets. **Local edits are never reset or discarded.** If the tree is dirty, Studio reports that auto-sync is paused until those changes are committed or otherwise handled. It deliberately does not auto-sync feature branches.

The GitHub Pages URL, `https://som76377-alt.github.io/omnimatrix/`, is a public static preview for the interface and GitHub-sourced CI status; it cannot run Python, read a private Codespace filesystem, or perform actual chat/tool actions. To use the **full main app**, use the private Codespaces port.

### Build and test status

The Pages deployment workflow runs Python compilation, configuration validation, JavaScript syntax checks, and the full unit-test suite before it publishes. The deployed `status.json` records the passing test count and exact commit SHA for that published build. Recent GitHub Actions runs and locally executed Codespaces test runs are shown separately, so CI status is not confused with the current workspace result.

Repository Pages publishing must be configured once at **Settings → Pages → Build and deployment → Source → GitHub Actions**. Each merge to `main` triggers a new deployment attempt. A 404 means the published artifact/deployment still needs checking in the repository's [Actions](https://github.com/som76377-alt/omnimatrix/actions) and [Pages settings](https://github.com/som76377-alt/omnimatrix/settings/pages); a green pull-request CI run alone does not prove Pages has deployed.

## Repository map

| Path | Purpose |
| --- | --- |
| `core/orchestrator/` | Planning, validation, task lifecycle, and orchestration |
| `core/models/` | Model types, registry, configuration loader, and provider adapters |
| `core/tools/` | Tool contracts, permissions, registry, and execution |
| `core/application/` | Chat application layer |
| `core/conversation/` | Conversation state |
| `interfaces/cli/` | Command-line entry point |
| `interfaces/web/` | Private Codespaces Studio backend and bounded browser API |
| `webapp/` | Studio interface, read-only source explorer, chat, and test/status panels |
| `.devcontainer/` | Private Codespaces setup and supervised Studio launcher |
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


## Native Android app (first build)

The android/ project is the native Android client; it is not the browser Studio wrapped in a WebView. Its four bottom-navigation screens are Chat, Workspace, Tests & Status, and Connect. The app talks to the existing Python Studio API for chat, bounded workspace file access, and the fixed automated test suite. The runtime URL and bearer token are stored using AndroidX encrypted preferences.

### APK build and download

The Android APK GitHub Actions workflow compiles the Android project, runs the Python regression suite plus Android JVM input-validation tests, assembles a debug APK, and uploads it as the omnitrix-android-debug-apk artifact. Download the artifact ZIP from a successful workflow run and install the included APK on Android. Debug APKs are not release-signed for Play Store distribution; Android may require allowing installation from the download source.

The Studio port is configured for public forwarding because the native app cannot use the browser's signed-in Codespaces cookies. Its /api/* operations require a 256-bit random bearer token; keep that token private and store it only in the app's encrypted preferences. The exposed API has no arbitrary-shell route. Workspace writing is limited to existing, allowlisted UTF-8 files, uses an expected SHA-256 to prevent stale overwrites, and atomically replaces the file; new files, deletes, hidden/secret-like paths, and paths outside the allowlist are refused. This public-port arrangement is a security tradeoff; review it before production use.

The bundled profile is still offline-demo: it simulates model replies and is not live inference. A configured provider and its secret must be set up separately to use actual model inference. Workspace saves update the Codespaces checkout only; they do not silently commit or push changes to GitHub. The existing auto-sync only fast-forwards a clean main checkout and pauses on local modifications.
