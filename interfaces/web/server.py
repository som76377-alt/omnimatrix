"""Private, authenticated web studio for testing the existing Omnitrix Python core.

Keep the forwarded Codespaces port private. The random runtime token protects API
routes, but it is not a substitute for a private port or an OS sandbox.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
from datetime import datetime, timezone
import hmac
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from core.application import ChatApplication
from core.conversation import Conversation
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.implementations.workspace_inspect import WorkspaceInspectTool
from core.tools.permissions import ToolPermission


LOGGER = logging.getLogger("omnitrix.studio")
MAX_BODY_BYTES = 16 * 1024
MAX_CHAT_CHARS = 8_000
MAX_SESSIONS = 32
MAX_TEST_OUTPUT_BYTES = 64 * 1024
TEST_TIMEOUT_SECONDS = 180
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{16,128}$")
SECRET_NAME_PATTERN = re.compile(
    r"(secret|token|password|api[_-]?key|credential|private[_-]?key)",
    re.IGNORECASE,
)


def utc_now() -> str:
    """Return an offset-aware timestamp suitable for status evidence."""
    return datetime.now(timezone.utc).isoformat()


def short_git_revision(root: Path) -> str | None:
    """Return the checked-out revision without reading user-controlled commands."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def working_tree_dirty(root: Path) -> bool | None:
    """Return whether the checked-out worktree has changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def safe_test_environment() -> dict[str, str]:
    """Remove likely credentials before launching the fixed test command."""
    return {
        key: value
        for key, value in os.environ.items()
        if not SECRET_NAME_PATTERN.search(key)
    }


class StudioRuntime:
    """Own the configured orchestrator, per-browser conversations, and evidence."""

    def __init__(
        self,
        *,
        root: Path,
        config_path: Path,
        app: ChatApplication,
        omnitrix: Omnitrix,
        workspace_tool: WorkspaceInspectTool,
        access_token: str,
        workspace_read_enabled: bool,
        allowed_paths: list[str] | None,
        tests_enabled: bool,
        test_timeout_seconds: int = TEST_TIMEOUT_SECONDS,
        code_root: Path | None = None,
        auto_sync_main: bool = False,
        auto_sync_interval_seconds: int = 60,
    ) -> None:
        self.root = root
        self.code_root = (code_root or Path(__file__).resolve().parents[2]).resolve()
        self.config_path = config_path
        self.auto_sync_main = auto_sync_main
        self.auto_sync_interval_seconds = auto_sync_interval_seconds
        self.sync_status = "waiting" if auto_sync_main else "disabled"
        self.sync_last_checked: str | None = None
        self.sync_last_result = "Automatic GitHub sync is disabled."
        self.sync_restart_pending = False
        self.stop_event = threading.Event()
        self.sync_lock = threading.Lock()
        self.execution_lock = threading.Lock()
        self.active_chats = 0
        self.active_chats_lock = threading.Lock()
        self.app = app
        self.omnitrix = omnitrix
        self.workspace_tool = workspace_tool
        self.access_token = access_token
        self.workspace_read_enabled = workspace_read_enabled
        self.allowed_paths = allowed_paths
        self.tests_enabled = tests_enabled
        self.test_timeout_seconds = test_timeout_seconds
        self.sessions: OrderedDict[str, Conversation] = OrderedDict()
        self.sessions_lock = threading.Lock()
        self.test_lock = threading.Lock()
        self.test_result_lock = threading.Lock()
        self.last_test: dict[str, Any] | None = None

    def status(self) -> dict[str, Any]:
        """Expose safe runtime metadata, never credentials or absolute workspace paths."""
        models = [
            {
                "name": item.name,
                "provider": item.provider,
                "model_id": item.model_id,
                "capabilities": sorted(item.capabilities),
            }
            for item in self.omnitrix.registry.list_enabled()
        ]
        tool_details = []
        for tool in self.omnitrix.tool_registry.list():
            tool_details.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "capabilities": sorted(tool.capabilities),
                    "permission_granted": self.omnitrix.tool_permission.allows(
                        tool.capabilities
                    ),
                }
            )
        return {
            "ok": True,
            "service": "omnitrix-studio",
            "backend": "python",
            "revision": short_git_revision(self.code_root),
            "working_tree_dirty": working_tree_dirty(self.code_root),
            "code_branch": self._git_output(["branch", "--show-current"]) or "unknown",
            "auto_sync_main_enabled": self.auto_sync_main,
            "sync_status": self.sync_status,
            "sync_last_checked": self.sync_last_checked,
            "sync_last_result": self.sync_last_result,
            "sync_restart_pending": self.sync_restart_pending,
            "workspace_name": self.root.name,
            "workspace_read_enabled": self.workspace_read_enabled,
            "workspace_allowlist": self.allowed_paths,
            "tests_enabled": self.tests_enabled,
            "test_timeout_seconds": self.test_timeout_seconds,
            "provider_mode": (
                "offline-demo"
                if models and all(model["provider"] == "demo" for model in models)
                else "configured-model"
            ),
            "gemini_key_detected": bool(os.getenv("GEMINI_API_KEY")),
            "models": models,
            "tools": tool_details,
            "checked_at": utc_now(),
        }

    def _git_output(self, arguments: list[str], timeout: int = 8) -> str | None:
        """Run a fixed git metadata command without a shell; return stdout only."""
        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=self.code_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def check_for_updates(self) -> bool:
        """Fast-forward a clean checkout of main only; never reset or overwrite edits."""
        if not self.auto_sync_main or not self.sync_lock.acquire(blocking=False):
            return False
        try:
            self.sync_last_checked = utc_now()
            if self.test_lock.locked():
                self.sync_status = "deferred_busy"
                self.sync_last_result = "A test run is active; update postponed."
                return False
            with self.active_chats_lock:
                if self.active_chats:
                    self.sync_status = "deferred_busy"
                    self.sync_last_result = "A chat turn is active; update postponed."
                    return False

            branch = self._git_output(["branch", "--show-current"])
            if branch != "main":
                self.sync_status = "deferred_not_main"
                self.sync_last_result = "Auto-sync only updates the main branch checkout."
                return False

            dirty = working_tree_dirty(self.code_root)
            if dirty is not False:
                self.sync_status = "deferred_dirty"
                self.sync_last_result = "Local changes exist or Git status is unavailable; nothing was changed."
                return False

            old_revision = self._git_output(["rev-parse", "HEAD"])
            try:
                fetched = subprocess.run(
                    ["git", "fetch", "--quiet", "origin", "main"],
                    cwd=self.code_root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=45,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                self.sync_status = "error"
                self.sync_last_result = "GitHub fetch failed or timed out; current checkout was left unchanged."
                return False
            if fetched.returncode != 0:
                self.sync_status = "error"
                self.sync_last_result = "GitHub fetch failed; current checkout was left unchanged."
                return False

            remote_revision = self._git_output(["rev-parse", "refs/remotes/origin/main"])
            if not remote_revision or not old_revision:
                self.sync_status = "error"
                self.sync_last_result = "Could not verify the local and remote revisions."
                return False
            if remote_revision == old_revision:
                self.sync_status = "up_to_date"
                self.sync_last_result = "The main checkout already matches origin/main."
                return False

            if not self.execution_lock.acquire(blocking=False):
                self.sync_status = "deferred_busy"
                self.sync_last_result = "A chat or test operation began during the fetch; update postponed."
                return False
            try:
                dirty_after_fetch = working_tree_dirty(self.code_root)
                current_revision = self._git_output(["rev-parse", "HEAD"])
                if dirty_after_fetch is not False or current_revision != old_revision:
                    self.sync_status = "deferred_dirty"
                    self.sync_last_result = "Checkout changed during the update check; no merge was attempted."
                    return False

                try:
                    merged = subprocess.run(
                        ["git", "merge", "--ff-only", "refs/remotes/origin/main"],
                        cwd=self.code_root,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=30,
                        check=False,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    self.sync_status = "error"
                    self.sync_last_result = "Fast-forward update failed or timed out; no reset was attempted."
                    return False

                final_revision = self._git_output(["rev-parse", "HEAD"])
                if merged.returncode != 0 or final_revision != remote_revision:
                    self.sync_status = "error"
                    self.sync_last_result = "Fast-forward was refused; local history was not reset."
                    return False

                self.sync_status = "updated"
                self.sync_last_result = (
                    f"Updated from {old_revision[:7]} to {remote_revision[:7]}; restarting Studio to load the new code."
                )
                self.sync_restart_pending = True
                return True
            finally:
                self.execution_lock.release()
        finally:
            self.sync_lock.release()

    def conversation_for(self, session_id: str) -> Conversation:
        """Return/create a bounded in-memory conversation for a browser session."""
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError(
                "session_id must be a generated 16-128 character identifier."
            )
        with self.sessions_lock:
            conversation = self.sessions.get(session_id)
            if conversation is not None:
                self.sessions.move_to_end(session_id)
                return conversation
            while len(self.sessions) >= MAX_SESSIONS:
                self.sessions.popitem(last=False)
            conversation = Conversation()
            self.sessions[session_id] = conversation
            return conversation

    def chat(self, payload: Any) -> dict[str, Any]:
        """Send a real turn through ChatApplication/Omnitrix."""
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        message = payload.get("message")
        session_id = payload.get("session_id")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Message must not be empty.")
        if len(message) > MAX_CHAT_CHARS:
            raise ValueError(f"Message exceeds the {MAX_CHAT_CHARS}-character limit.")
        if not isinstance(session_id, str):
            raise ValueError("session_id is required.")
        conversation = self.conversation_for(session_id)
        started = time.monotonic()
        with self.active_chats_lock:
            self.active_chats += 1
        if not self.execution_lock.acquire(blocking=False):
            with self.active_chats_lock:
                self.active_chats -= 1
            raise RuntimeError("Studio is busy with another chat, test, or GitHub update; retry this request.")
        try:
            reply = self.app.send_message(conversation, message.strip())
        except Exception:
            LOGGER.warning("chat turn failed; provider exception type withheld from client")
            raise RuntimeError(
                "Omnitrix could not complete this turn. Check the configured model, "
                "provider credentials, budget policy, and server terminal output."
            ) from None
        finally:
            self.execution_lock.release()
            with self.active_chats_lock:
                self.active_chats -= 1
        return {
            "ok": True,
            "reply": reply,
            "provider_mode": self.status()["provider_mode"],
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "message_count": len(conversation.messages),
            "completed_at": utc_now(),
        }

    def run_tests(self) -> dict[str, Any]:
        """Run only the repository's fixed unittest command; never accept shell input."""
        if not self.tests_enabled:
            raise PermissionError(
                "Local test execution is disabled. Restart Studio with --allow-test-run."
            )
        if not self.test_lock.acquire(blocking=False):
            raise RuntimeError("The test suite is already running.")
        if not self.execution_lock.acquire(blocking=False):
            self.test_lock.release()
            raise RuntimeError("Studio is busy with a chat or GitHub update; retry the test run.")
        started = time.monotonic()
        finished: dict[str, Any]
        try:
            command = [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-v",
            ]
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.code_root,
                    env=safe_test_environment(),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=self.test_timeout_seconds,
                    check=False,
                )
                output = (completed.stdout or "") + (completed.stderr or "")
                output_bytes = output.encode("utf-8", errors="replace")
                truncated = len(output_bytes) > MAX_TEST_OUTPUT_BYTES
                if truncated:
                    output = (
                        output_bytes[:MAX_TEST_OUTPUT_BYTES].decode(
                            "utf-8", errors="replace"
                        )
                        + "\n… output truncated by Omnitrix Studio …"
                    )
                match = re.search(r"Ran (\d+) tests?", output)
                passed = completed.returncode == 0 and "OK" in output
                finished = {
                    "ok": True,
                    "status": "passed" if passed else "failed",
                    "test_count": int(match.group(1)) if match else None,
                    "return_code": completed.returncode,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "output": output,
                    "output_truncated": truncated,
                    "command": "python -m unittest discover -s tests -v",
                    "revision": short_git_revision(self.code_root),
                    "finished_at": utc_now(),
                }
            except subprocess.TimeoutExpired as exc:
                partial_out = exc.stdout or ""
                partial_err = exc.stderr or ""
                if isinstance(partial_out, bytes):
                    partial_out = partial_out.decode("utf-8", errors="replace")
                if isinstance(partial_err, bytes):
                    partial_err = partial_err.decode("utf-8", errors="replace")
                partial = (partial_out + partial_err).encode(
                    "utf-8", errors="replace"
                )[:MAX_TEST_OUTPUT_BYTES].decode("utf-8", errors="replace")
                finished = {
                    "ok": True,
                    "status": "timed_out",
                    "test_count": None,
                    "return_code": None,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "output": partial
                    + f"\nTimed out after {self.test_timeout_seconds} seconds.",
                    "output_truncated": False,
                    "command": "python -m unittest discover -s tests -v",
                    "revision": short_git_revision(self.code_root),
                    "finished_at": utc_now(),
                }
        finally:
            self.execution_lock.release()
            self.test_lock.release()
        with self.test_result_lock:
            self.last_test = finished
        return finished


def make_handler(
    runtime: StudioRuntime, web_root: Path
) -> type[BaseHTTPRequestHandler]:
    """Create a request handler bound to one runtime."""

    class StudioHandler(BaseHTTPRequestHandler):
        server_version = "OmnitrixStudio/0.1"

        def log_message(self, format_string: str, *args: Any) -> None:
            # Avoid logging chat prompts, tokens, or file contents.
            LOGGER.info("HTTP %s %s", self.command, self.path.split("?", 1)[0])

        def _headers(self, content_type: str, *, api: bool = False) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cache-Control", "no-store")
            if api:
                self.send_header("Vary", "Authorization")

        def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
            encoded = json.dumps(
                data, ensure_ascii=False, separators=(",", ":"), default=str
            ).encode("utf-8")
            self.send_response(status)
            self._headers("application/json; charset=utf-8", api=True)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _authorized(self) -> bool:
            supplied = self.headers.get("Authorization", "")
            if not supplied.startswith("Bearer "):
                return False
            return hmac.compare_digest(
                supplied.removeprefix("Bearer ").strip(),
                runtime.access_token,
            )

        def _query(self) -> dict[str, list[str]]:
            return parse_qs(urlsplit(self.path).query, keep_blank_values=True)

        def _first_query(self, name: str, default: str = "") -> str:
            values = self._query().get(name, [])
            return values[0] if values else default

        def _json_body(self) -> Any:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("Invalid Content-Length.") from exc
            if length < 0 or length > MAX_BODY_BYTES:
                raise OverflowError("Request body is too large.")
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Request body must be valid UTF-8 JSON.") from exc

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            route = parsed.path
            if route.startswith("/api/"):
                if not self._authorized():
                    self._send_json(
                        {
                            "ok": False,
                            "error": "Runtime access token required. Paste the token printed by the Studio server.",
                            "code": "unauthorized",
                        },
                        401,
                    )
                    return
                try:
                    if route == "/api/health":
                        self._send_json(runtime.status())
                    elif route == "/api/workspace/list":
                        self._workspace_list()
                    elif route == "/api/workspace/read":
                        self._workspace_read()
                    elif route == "/api/tests/latest":
                        with runtime.test_result_lock:
                            self._send_json(
                                {"ok": True, "result": runtime.last_test}
                            )
                    elif route == "/api/capabilities":
                        status = runtime.status()
                        self._send_json(
                            {
                                "ok": True,
                                "models": status["models"],
                                "tools": status["tools"],
                                "workspace_read_enabled": status[
                                    "workspace_read_enabled"
                                ],
                            }
                        )
                    else:
                        self._send_json(
                            {"ok": False, "error": "API route not found."}, 404
                        )
                except PermissionError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 403)
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 400)
                except Exception as exc:
                    LOGGER.warning("GET API route failed: %s", type(exc).__name__)
                    self._send_json(
                        {
                            "ok": False,
                            "error": "The requested operation failed safely.",
                        },
                        500,
                    )
                return
            self._serve_static(route)

        def do_POST(self) -> None:
            route = urlsplit(self.path).path
            if not route.startswith("/api/"):
                self._send_json({"ok": False, "error": "API route not found."}, 404)
                return
            if not self._authorized():
                self._send_json(
                    {
                        "ok": False,
                        "error": "Runtime access token required.",
                        "code": "unauthorized",
                    },
                    401,
                )
                return
            try:
                payload = self._json_body()
            except OverflowError as exc:
                self._send_json({"ok": False, "error": str(exc)}, 413)
                return
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, 400)
                return
            try:
                if route == "/api/chat":
                    self._send_json(runtime.chat(payload))
                elif route == "/api/tests/run":
                    self._send_json(runtime.run_tests())
                else:
                    self._send_json(
                        {"ok": False, "error": "API route not found."}, 404
                    )
            except PermissionError as exc:
                self._send_json({"ok": False, "error": str(exc)}, 403)
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, 400)
            except RuntimeError as exc:
                error_text = str(exc).lower()
                status = 409 if "already running" in error_text or "busy" in error_text else 502
                self._send_json({"ok": False, "error": str(exc)}, status)
            except Exception as exc:
                LOGGER.warning("POST API route failed: %s", type(exc).__name__)
                self._send_json(
                    {"ok": False, "error": "The requested operation failed safely."},
                    500,
                )

        def _workspace_list(self) -> None:
            if not runtime.workspace_read_enabled:
                raise PermissionError(
                    "Workspace browsing is disabled. Restart Studio with --allow-workspace-read."
                )
            raw_path = self._first_query("path", ".")
            result = runtime.workspace_tool.execute(
                operation="list",
                path=raw_path,
            )
            self._send_json(
                {
                    "ok": result.success,
                    "output": result.output,
                    "error": result.error,
                    "workspace_name": runtime.root.name,
                },
                200 if result.success else 400,
            )

        def _workspace_read(self) -> None:
            if not runtime.workspace_read_enabled:
                raise PermissionError(
                    "Workspace browsing is disabled. Restart Studio with --allow-workspace-read."
                )
            raw_path = self._first_query("path", "")
            result = runtime.workspace_tool.execute(
                operation="read",
                path=raw_path,
            )
            self._send_json(
                {
                    "ok": result.success,
                    "output": result.output,
                    "error": result.error,
                },
                200 if result.success else 400,
            )

        def _serve_static(self, route: str) -> None:
            decoded = unquote(route)
            if decoded in {"", "/"}:
                decoded = "/index.html"
            relative = decoded.lstrip("/")
            candidate = (web_root / relative).resolve()
            if not candidate.is_relative_to(web_root) or not candidate.is_file():
                self.send_error(404, "Studio asset not found.")
                return
            content = candidate.read_bytes()
            content_type, _ = mimetypes.guess_type(candidate.name)
            if candidate.suffix == ".webmanifest":
                content_type = "application/manifest+json"
            content_type = content_type or "application/octet-stream"
            if content_type.startswith("text/") or content_type in {
                "application/javascript",
                "application/manifest+json",
            }:
                content_type += "; charset=utf-8"
            self.send_response(200)
            self._headers(content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

    return StudioHandler


def build_runtime(args: argparse.Namespace, access_token: str) -> StudioRuntime:
    """Load the existing Omnitrix components without exposing arbitrary execution."""
    root = Path(args.workspace_root or ".").expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Workspace root must be an existing directory.")
    config_path = Path(args.config).expanduser().resolve(strict=True)
    if not config_path.is_file():
        raise ValueError("Model configuration must be an existing file.")
    registry = build_tool_registry(root, allowed_paths=args.workspace_allow)
    capabilities = {"calculation"}
    if args.allow_workspace_read:
        capabilities.add("workspace.read")
    omnitrix = Omnitrix.from_config(
        config_path,
        tool_registry=registry,
        tool_permission=ToolPermission.from_capabilities(capabilities),
    )
    return StudioRuntime(
        root=root,
        config_path=config_path,
        app=ChatApplication(omnitrix),
        omnitrix=omnitrix,
        workspace_tool=registry.get("workspace.inspect"),
        access_token=access_token,
        workspace_read_enabled=args.allow_workspace_read,
        allowed_paths=args.workspace_allow,
        tests_enabled=args.allow_test_run,
        test_timeout_seconds=args.test_timeout,
        code_root=Path(__file__).resolve().parents[2],
        auto_sync_main=args.auto_sync_main,
        auto_sync_interval_seconds=args.auto_sync_interval,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start the authenticated Omnitrix Studio web interface."
    )
    parser.add_argument("--config", default="config/demo.models.json")
    parser.add_argument("--workspace-root", default=".")
    parser.add_argument(
        "--workspace-allow",
        action="append",
        dest="workspace_allow",
        metavar="RELATIVE_PATH",
        help="Restrict browser/model workspace reads to this relative path prefix (repeatable).",
    )
    parser.add_argument(
        "--allow-workspace-read",
        action="store_true",
        help="Explicitly enable read-only workspace browsing and model tool access.",
    )
    parser.add_argument(
        "--allow-test-run",
        action="store_true",
        help="Enable the fixed Python unittest discovery command.",
    )
    parser.add_argument("--test-timeout", type=int, default=TEST_TIMEOUT_SECONDS)
    parser.add_argument(
        "--auto-sync-main",
        action="store_true",
        help="Poll origin/main and fast-forward only when the checkout is clean and already on main. Intended for a supervised private Codespace.",
    )
    parser.add_argument(
        "--auto-sync-interval",
        type=int,
        default=60,
        help="Seconds between safe origin/main checks (30–1800).",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--access-token",
        default=None,
        help="Optional runtime token. Prefer the random token generated at startup.",
    )
    args = parser.parse_args(argv)
    if args.test_timeout < 1 or args.test_timeout > 600:
        parser.error("--test-timeout must be between 1 and 600 seconds.")
    if args.auto_sync_interval < 30 or args.auto_sync_interval > 1800:
        parser.error("--auto-sync-interval must be between 30 and 1800 seconds.")
    if args.auto_sync_main and args.host != "0.0.0.0":
        parser.error("--auto-sync-main is intended for the supervised Codespaces server.")
    if args.port < 1 or args.port > 65535:
        parser.error("--port must be between 1 and 65535.")
    if args.workspace_allow and not args.allow_workspace_read:
        parser.error("--workspace-allow requires --allow-workspace-read.")
    if args.host not in {"127.0.0.1", "::1", "0.0.0.0"}:
        parser.error("--host must be a loopback address or 0.0.0.0.")
    if args.host == "0.0.0.0":
        print(
            "SECURITY: keep the GitHub Codespaces forwarded port PRIVATE. "
            "Do not publish this server origin.",
            file=sys.stderr,
        )

    access_token = args.access_token or secrets.token_urlsafe(32)
    try:
        runtime = build_runtime(args, access_token)
    except Exception as exc:
        parser.error(f"Could not start Omnitrix Studio ({type(exc).__name__}).")

    web_root = Path(__file__).resolve().parents[2] / "webapp"
    if not (web_root / "index.html").is_file():
        parser.error("webapp/index.html is missing from this checkout.")

    handler = make_handler(runtime, web_root)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.daemon_threads = True

    if runtime.auto_sync_main:
        def update_watcher() -> None:
            while not runtime.stop_event.wait(runtime.auto_sync_interval_seconds):
                try:
                    if runtime.check_for_updates():
                        LOGGER.info("origin/main fast-forward complete; restarting supervised Studio.")
                        time.sleep(1.2)
                        os.kill(os.getpid(), signal.SIGTERM)
                        return
                except Exception:
                    LOGGER.exception("safe auto-sync check failed")

        threading.Thread(
            target=update_watcher,
            name="omnitrix-main-sync",
            daemon=True,
        ).start()

    print("OMNITRIX STUDIO READY")
    print(f"Web interface: http://127.0.0.1:{args.port}/")
    print(f"Workspace: {runtime.root.name}")
    print(f"Runtime access token (paste into Studio): {access_token}")
    print(f"Model mode: {runtime.status()['provider_mode']}")
    print(f"Workspace read: {'ENABLED' if args.allow_workspace_read else 'DISABLED'}")
    print(f"Local test runner: {'ENABLED' if args.allow_test_run else 'DISABLED'}")
    print(f"Auto-sync origin/main: {'ENABLED' if args.auto_sync_main else 'DISABLED'}")
    if args.auto_sync_main:
        print(
            f"Auto-sync interval: {args.auto_sync_interval}s; fast-forward only on a clean main checkout."
        )
    print("Keep any forwarded Codespaces port private. Ctrl+C stops the server.")
    try:
        server.serve_forever(poll_interval=0.4)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        runtime.workspace_tool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
