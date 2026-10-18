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

### Optional free specialist model profile

The default `config/mobile.models.json` is unchanged. To explicitly test the OpenRouter free-model candidates in a CLI or private Studio environment, choose the separate example profile:

```bash
# First provide OPENROUTER_API_KEY through your own shell or secret manager.
: "${OPENROUTER_API_KEY:?Set OPENROUTER_API_KEY in your secret-managed environment}"
python -m interfaces.cli.main --config config/mobile.models.openrouter-free.example.json --allow-free-quota
```

Do **not** commit the key or paste it into chat/issues. Selecting this profile intentionally routes prompts to external OpenRouter model endpoints. Current free routes have changing availability, quotas and data terms; the NVIDIA free route says not to send confidential or personal data. Use only with non-sensitive test prompts, and check the upstream terms each time. The free plan currently states 50 requests per day, so it is a small evaluation path, not an unlimited production backend. The Render start command still uses the default Google profile until an operator deliberately changes deployment configuration and adds the provider secret in the hosting dashboard.

The core application uses the Python standard library, with one explicit runtime dependency (`cryptography`) for opt-in AES-GCM encrypted model-state snapshots. Install runtime dependencies with `python -m pip install -r requirements.txt`. CI installs this file before tests. The encryption key is supplied separately by the caller and is never stored in the SQLite journal.

## Project specifications

- [Product Requirements Document](docs/PRD.md) — version 1.31; implementation status snapshot dated 18 October 2026.
- [Recovery state machine](docs/RECOVERY_STATE_MACHINE.md) — conservative post-crash dispositions and reconciliation boundaries.
- [Staged roadmap](docs/ROADMAP.md) — current phase gates and verified completion status.
- [Truthfulness and capability calibration contract](docs/TRUTHFULNESS_AND_CALIBRATION.md) — persistent runtime rules, adversarial evaluation cases, release gate, and capability-claim status definitions.
- [Rich-response formatting support](docs/FORMATTING_SUPPORT.md) — browser and Android formatting capabilities, safety boundaries, and verification.

## Omnitrix Studio — main testing app

The main Studio interface lives in `webapp/`; the Python backend is `interfaces/web/server.py`. It is a browser app backed by the **existing Python Omnitrix core**, not a simulated UI shell.

### Start the full Studio in GitHub Codespaces

Open [Create/open an Omnitrix Codespace](https://codespaces.new/som76377-alt/omnimatrix). The checked-in devcontainer installs the Python dependencies and starts the Studio supervisor automatically. Port 8000 is configured for **public forwarding** so the native Android app can reach it without browser session cookies. Treat this as a deliberate security trade-off: all API calls require the generated bearer token over HTTPS, but a public endpoint is not the same as a private Codespaces port.

The startup script generates a random runtime access token outside the repository and prints it to the Codespaces terminal. In the app's **Connect** screen, enter the forwarded HTTPS URL for port 8000 and that token. To print the token again in the Codespaces terminal:

```bash
cat /tmp/omnitrix-studio-runtime-token
```

Never commit or share the token; the Android app stores its URL and token in AndroidX encrypted preferences. The API exposes no arbitrary shell or arbitrary command execution. The Codespaces startup profile grants bounded workspace access and a fixed test command. The Android client can save changes only to existing allowlisted UTF-8 files using a stale-write check; it does not automatically commit or push those edits to GitHub.

The chat sends requests through `ChatApplication` and the existing `Omnitrix` orchestrator in the running Python backend. The default `config/demo.models.json` profile deliberately uses a simulated offline provider, so the connection is live but model replies are **not** live AI inference until a real provider and credential are explicitly configured. The browser's source viewer is read-only; the native Android workspace can edit existing allowlisted files through the guarded API.

### GitHub-connected updates

On the normal, clean `main` checkout, the Codespaces supervisor checks `origin/main` about once per minute. It only uses `git fetch` followed by `git merge --ff-only` if the working tree is clean and the checkout is already on `main`. On a successful fast-forward it restarts the Python server with the same private runtime token; the browser's service worker checks for the new interface assets. **Local edits are never reset or discarded.** If the tree is dirty, Studio reports that auto-sync is paused until those changes are committed or otherwise handled. It deliberately does not auto-sync feature branches.

The GitHub Pages URL, `https://som76377-alt.github.io/omnimatrix/`, is a public static preview for the interface and GitHub-sourced CI status; it cannot run Python, read the Codespaces filesystem, or perform actual chat/tool actions. To use live backend features in the APK, keep the Codespace running and connect to its forwarded HTTPS port.

### Build and test status

The Pages deployment workflow runs Python compilation, configuration validation, JavaScript syntax checks, and the full unit-test suite before it publishes. The deployed `status.json` records the passing test count and exact commit SHA for that published build. Recent GitHub Actions runs and locally executed Codespaces test runs are shown separately, so CI status is not confused with the current workspace result.

Repository Pages publishing must be configured once at **Settings → Pages → Build and deployment → Source → GitHub Actions**. Each merge to `main` triggers a new deployment attempt. A 404 means the published artifact/deployment still needs checking in the repository's [Actions](https://github.com/som76377-alt/omnimatrix/actions) and [Pages settings](https://github.com/som76377-alt/omnimatrix/settings/pages); a green pull-request CI run alone does not prove Pages has deployed.

## Repository map

| Path | Purpose |
| --- | --- |
| `core/orchestrator/` | Planning, validation, task lifecycle, and orchestration |
| `core/agents/` | Configurable specialist roles, adaptive intent briefs, and critique stages |
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
| `docs/SPECIALIST_AGENTS.md` | Specialist role design, candidate-model evidence, budgets, and evaluation plan |

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


## Native Android app

The Android client is a native Jetpack Compose app, not a WebView wrapper. The interface is intentionally minimal: black canvas, acid-green accents, readable fixed-width type, four plain-text destinations (**Chat**, **Repo**, **Runs**, **Account**) and no dashboard-card clutter.

### APK

The Android Actions workflow runs the Python regression suite, Android JVM tests, Kotlin compilation and APK assembly. A successful main-branch build publishes the installable debug APK and SHA-256 checksum as a GitHub Release.

- [Download the latest Omnitrix APK](https://github.com/som76377-alt/omnimatrix/releases/latest/download/Omnitrix.apk)
- [View release history](https://github.com/som76377-alt/omnimatrix/releases)
- [View Android build workflow](https://github.com/som76377-alt/omnimatrix/actions/workflows/android-apk.yml)
- [Automatic updates and one-time signing setup](docs/ANDROID_AUTO_UPDATES.md)

These are debug builds, not Play Store-signed releases. The signing key is generated by the CI runner, so to replace an APK signed by a different runner you may need to uninstall the previous test build first.

### GitHub sign-in (only for repository edits)

The APK automatically reads public repository files and real GitHub Actions runs without signing in. To commit file changes from the app, the Account screen uses GitHub's device authorization flow. This requires a GitHub OAuth App owned/controlled by the person setting up the app; Omnitrix does not embed a client secret.

1. Open [GitHub Developer settings](https://github.com/settings/developers) and create an OAuth App.
2. Use `Omnitrix Android` as the app name and `https://github.com/som76377-alt/omnimatrix` as its homepage. The device flow ignores the callback URL, but the registration form requires a value; `https://github.com/login/device` is suitable here.
3. In the OAuth App settings, enable **Device Flow**. GitHub's documentation says device flow must be enabled before the app can request verification codes.
4. Copy the OAuth App's **Client ID** (not a client secret) into Omnitrix → **Account** → **Sign in with GitHub**. Complete the displayed code flow in GitHub once.

See [GitHub's OAuth app setup guide](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app) and [device authorization documentation](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow).

Omnitrix requests the `public_repo` and `read:user` OAuth scopes. **`public_repo` can read and modify public repositories for the authorized GitHub account; it is not restricted to Omnitrix.** The app stores its access/refresh tokens in Android encrypted preferences and refreshes expiring access tokens when supported. Sign out to remove stored GitHub credentials.

The app reads public files and workflow-run status from GitHub on launch without asking for a Codespaces URL or sign-in. Anonymous file viewing is read-only. To write changes, sign in; editing remains allowlisted to selected source/document folders and existing UTF-8 files up to 64 KiB. Saving requires explicit confirmation and creates a commit directly on `main`; this is not a local-only draft. CI status is read-only in the app; the Runs screen links to GitHub Actions for further control.

### Hosted chat status

A Render deployment blueprint is checked in at `render.yaml`. The Android app discovers the backend through `config/mobile-backend.json`, so the endpoint can be configured later without rebuilding the APK. That manifest remains disabled until a real service is deployed and its URL is verified.

The hosted service is designed to expose only one unauthenticated route, the mobile chat endpoint. Workspace reads/writes, local test execution, and the development API remain token-protected. Public chat has in-memory IP/global rate limits; these are basic abuse controls, not production-grade identity or billing protection. Do not use this setup with a paid Gemini key or a key attached to billing.

**Deployment is not complete yet.** Connect the Render integration to the Render account that should own the service, deploy the repository's Blueprint, and set `GEMINI_API_KEY` as a server-side secret using a Google AI Studio Free Tier key with billing disabled. The model profile is `gemini-3.8-flash`; the key is never stored in this repository or APK. After Render provides the service URL, update `config/mobile-backend.json` with that verified HTTPS URL and set `chat_enabled` to `true`. The APK then discovers the service automatically over the internet.

Render's free web services sleep after 15 minutes without inbound traffic and usually need about a minute to wake. This gives the app a stable service address without Codespaces, but it is not an always-awake service. If the backend is offline or its free provider quota is exhausted, chat will not work until the service/quota is available again.
