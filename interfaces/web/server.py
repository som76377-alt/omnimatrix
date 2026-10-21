"""Private, authenticated web studio for testing the existing Omnitrix Python core.

Keep the forwarded Codespaces port private. The random runtime token protects API
routes, but it is not a substitute for a private port or an OS sandbox.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict, deque
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import math
import mimetypes
import os
import stat
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request as URLRequest, urlopen as urlopen_url

from core.application import ChatApplication
from core.attachments import MAX_ATTACHMENT_BYTES, accepted_mime_type, safe_display_name
from core.contracts import BudgetLimits
from core.conversation import Conversation
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.implementations.workspace_inspect import WorkspaceInspectTool
from core.tools.permissions import ToolPermission
from core.multimodal.adapters import toolchain_status
from core.creative_director import analyze_creative_request, creative_model_status
from core.creative_production import CreativeProductionManifest, ProductionContractError
from core.creative_assets import CreativeAssetError, download_creative_asset, generate_creative_image, search_creative_assets
from core.creative_video import CreativeVideoError, creative_video_job_status, start_creative_video_job
from core.creative_tool_registry import load_creative_tool_registry
from core.creative_orchestrator import create_shared_production_plan, get_shared_production_plan, update_shared_production_task


from core.multimodal.journal import journal_status
from core.multimodal.workflow import analyze_multiple_attachments, analyze_single_attachment


# Public mobile Creative Studio uses Wikimedia Commons only. Keep this endpoint
# useful without a local runtime token while bounding requests from any one IP.
_PUBLIC_CREATIVE_RATE_LOCK = threading.Lock()
_PUBLIC_CREATIVE_REQUESTS: dict[str, deque[float]] = {}
_PUBLIC_CREATIVE_RATE_WINDOW_SECONDS = 60.0
_PUBLIC_CREATIVE_RATE_LIMIT = 24


def _allow_public_creative_request(client_ip: str) -> bool:
    now = time.monotonic()
    key = str(client_ip or "unknown")[:120]
    with _PUBLIC_CREATIVE_RATE_LOCK:
        bucket = _PUBLIC_CREATIVE_REQUESTS.setdefault(key, deque())
        while bucket and now - bucket[0] >= _PUBLIC_CREATIVE_RATE_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= _PUBLIC_CREATIVE_RATE_LIMIT:
            return False
        bucket.append(now)
        if len(_PUBLIC_CREATIVE_REQUESTS) > 1024:
            for stale_key in list(_PUBLIC_CREATIVE_REQUESTS)[:128]:
                if stale_key != key:
                    _PUBLIC_CREATIVE_REQUESTS.pop(stale_key, None)
        return True

# Model-backed mobile creative calls are more expensive than asset search.
# Bound them separately per IP and globally over a rolling day.
_PUBLIC_CREATIVE_MODEL_REQUESTS: dict[str, deque[float]] = {}
_PUBLIC_CREATIVE_MODEL_GLOBAL: deque[float] = deque()
_PUBLIC_CREATIVE_MODEL_RATE_LOCK = threading.Lock()
# Video generation is a paid provider action. Keep a stricter service-wide budget
# even if a caller fabricates the client-side consent payload.
_PUBLIC_VIDEO_REQUESTS: dict[str, deque[float]] = {}
_PUBLIC_VIDEO_GLOBAL: deque[float] = deque()
_PUBLIC_VIDEO_RATE_LOCK = threading.Lock()


def _allow_public_creative_model_request(client_ip: str) -> bool:
    now = time.monotonic()
    key = str(client_ip or "unknown")[:120]
    with _PUBLIC_CREATIVE_MODEL_RATE_LOCK:
        bucket = _PUBLIC_CREATIVE_MODEL_REQUESTS.setdefault(key, deque())
        while bucket and now - bucket[0] >= 60.0:
            bucket.popleft()
        while _PUBLIC_CREATIVE_MODEL_GLOBAL and now - _PUBLIC_CREATIVE_MODEL_GLOBAL[0] >= 86400.0:
            _PUBLIC_CREATIVE_MODEL_GLOBAL.popleft()
        if len(bucket) >= 3 or len(_PUBLIC_CREATIVE_MODEL_GLOBAL) >= 40:
            return False
        bucket.append(now)
        _PUBLIC_CREATIVE_MODEL_GLOBAL.append(now)
        if len(_PUBLIC_CREATIVE_MODEL_REQUESTS) > 1024:
            for stale_key in list(_PUBLIC_CREATIVE_MODEL_REQUESTS)[:128]:
                if stale_key != key:
                    _PUBLIC_CREATIVE_MODEL_REQUESTS.pop(stale_key, None)
        return True


def _allow_public_creative_video_request(client_ip: str) -> bool:
    """Cap paid video generation to two requests per IP and three globally per day."""
    now = time.monotonic()
    key = str(client_ip or "unknown")[:120]
    with _PUBLIC_VIDEO_RATE_LOCK:
        bucket = _PUBLIC_VIDEO_REQUESTS.setdefault(key, deque())
        while bucket and now - bucket[0] >= 86_400.0:
            bucket.popleft()
        while _PUBLIC_VIDEO_GLOBAL and now - _PUBLIC_VIDEO_GLOBAL[0] >= 86_400.0:
            _PUBLIC_VIDEO_GLOBAL.popleft()
        if len(bucket) >= 2 or len(_PUBLIC_VIDEO_GLOBAL) >= 3:
            return False
        bucket.append(now)
        _PUBLIC_VIDEO_GLOBAL.append(now)
        if len(_PUBLIC_VIDEO_REQUESTS) > 1024:
            for stale_key in list(_PUBLIC_VIDEO_REQUESTS)[:128]:
                if stale_key != key and not _PUBLIC_VIDEO_REQUESTS[stale_key]:
                    _PUBLIC_VIDEO_REQUESTS.pop(stale_key, None)
        return True



def _paid_creative_media_enabled() -> bool:
    """The owner must enable paid image/video providers on the server explicitly."""
    return os.getenv("OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA", "").strip().lower() == "true"


def _paid_creative_media_status() -> dict[str, Any]:
    """Expose readiness only; never return any credential or initiate inference."""
    enabled = _paid_creative_media_enabled()
    key_configured = bool(os.getenv("GEMINI_API_KEY", "").strip())
    model = os.getenv("OMNITRIX_VIDEO_MODEL", "gemini-omni-1.1-flash").strip()
    return {
        "ok": True,
        "enabled": enabled,
        "key_configured": key_configured,
        "model": model,
        "estimated_cost_usd_per_second_720p": 0.10,
        "message": (
            "Paid media generation is enabled; each request still requires explicit user cost acknowledgement."
            if enabled and key_configured
            else "Paid image/video generation is disabled by default. The service owner must enable OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA=true after reviewing the charges."
            if not enabled
            else "GEMINI_API_KEY is not configured on this server."
        ),
    }


LOGGER = logging.getLogger("omnitrix.studio")
MAX_BODY_BYTES = 16 * 1024
MAX_CREATIVE_BODY_BYTES = 3 * 1024 * 1024
MAX_CREATIVE_JOBS = 8
APK_DOWNLOAD_URL = "https://github.com/som76377-alt/omnimatrix/releases/latest/download/Omnitrix.apk"
MAX_PUBLIC_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_CHAT_CHARS = 8_000
MAX_SESSIONS = 32
MAX_TEST_OUTPUT_BYTES = 64 * 1024
MAX_WORKSPACE_WRITE_BYTES = 64 * 1024
TEST_TIMEOUT_SECONDS = 180
PUBLIC_CHAT_PER_MINUTE = 6
PUBLIC_CHAT_PER_DAY = 40
PUBLIC_CHAT_GLOBAL_PER_DAY = 300
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
    blocked = {"PYTHONPATH", "PYTHONHOME"}
    return {
        key: value
        for key, value in os.environ.items()
        if key not in blocked and not SECRET_NAME_PATTERN.search(key)
    }


def write_workspace_file(
    root: Path,
    relative_path: Any,
    content: Any,
    expected_sha256: Any,
    allowed_paths: list[str] | None,
) -> dict[str, Any]:
    """Atomically replace one existing allowlisted UTF-8 text file after a hash check."""
    if not isinstance(relative_path, str) or not relative_path.strip() or len(relative_path) > 512:
        raise ValueError("path must be a non-empty relative path of at most 512 characters.")
    if "\\" in relative_path or relative_path.startswith("/") or "\x00" in relative_path:
        raise ValueError("Absolute paths, backslashes, and NUL bytes are not accepted.")
    if any(part in {"", ".", ".."} for part in relative_path.split("/")):
        raise ValueError("Path traversal and explicit dot components are not accepted.")
    parts = PurePosixPath(relative_path).parts
    if not parts or any(part.startswith(".") or SECRET_NAME_PATTERN.search(part) for part in parts):
        raise PermissionError("Hidden and sensitive paths are not writable.")
    if allowed_paths is not None:
        allowed = []
        for prefix in allowed_paths:
            if not isinstance(prefix, str) or not prefix.strip():
                continue
            if prefix == ".":
                allowed.append(())
                continue
            if prefix.startswith("/") or "\\" in prefix or any(p in {"", ".", ".."} for p in prefix.split("/")):
                continue
            allowed.append(PurePosixPath(prefix).parts)
        if not any(parts[:len(prefix)] == prefix for prefix in allowed):
            raise PermissionError("The requested file is outside the configured workspace allowlist.")
    if not isinstance(content, str):
        raise ValueError("content must be a UTF-8 string.")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_WORKSPACE_WRITE_BYTES:
        raise ValueError(f"content exceeds the {MAX_WORKSPACE_WRITE_BYTES}-byte write limit.")
    if b"\x00" in encoded:
        raise ValueError("Binary content is not writable.")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("expected_sha256 must contain the original 64-character SHA-256 digest.")
    if not (
        getattr(os, "O_DIRECTORY", 0)
        and getattr(os, "O_NOFOLLOW", 0)
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
    ):
        raise RuntimeError("Secure descriptor-relative file writes are not supported on this operating system.")

    canonical_root = root.expanduser().resolve(strict=True)
    directory_flag = os.O_DIRECTORY
    nofollow_flag = os.O_NOFOLLOW
    parent_fd = os.open(os.path.sep, os.O_RDONLY | directory_flag | nofollow_flag)
    temp_name = None
    temp_fd = None
    target_fd = None
    try:
        for component in canonical_root.parts[1:]:
            next_fd = os.open(
                component,
                os.O_RDONLY | directory_flag | nofollow_flag,
                dir_fd=parent_fd,
            )
            os.close(parent_fd)
            parent_fd = next_fd

        for component in parts[:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | directory_flag | nofollow_flag,
                dir_fd=parent_fd,
            )
            os.close(parent_fd)
            parent_fd = next_fd

        target_name = parts[-1]
        try:
            info = os.stat(target_name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise ValueError("Only an existing file can be edited; new-file creation is disabled.") from exc
        if not stat.S_ISREG(info.st_mode):
            raise PermissionError("Only an existing regular file can be edited.")
        target_fd = os.open(
            target_name,
            os.O_RDONLY | nofollow_flag | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_fd,
        )
        opened_info = os.fstat(target_fd)
        if not stat.S_ISREG(opened_info.st_mode):
            raise PermissionError("Only an existing regular file can be edited.")
        if opened_info.st_size > MAX_WORKSPACE_WRITE_BYTES:
            raise ValueError("The existing file is larger than the guarded write limit.")
        old_chunks = []
        remaining = MAX_WORKSPACE_WRITE_BYTES + 1
        while remaining:
            chunk = os.read(target_fd, min(8192, remaining))
            if not chunk:
                break
            old_chunks.append(chunk)
            remaining -= len(chunk)
        old_bytes = b"".join(old_chunks)
        if len(old_bytes) > MAX_WORKSPACE_WRITE_BYTES or b"\x00" in old_bytes:
            raise PermissionError("The existing file is binary or exceeds the guarded write limit.")
        old_bytes.decode("utf-8")
        previous_hash = hashlib.sha256(old_bytes).hexdigest()
        if not hmac.compare_digest(previous_hash, expected_sha256.lower()):
            raise RuntimeError("The file changed since it was opened. Reload it before saving.")
        if not hmac.compare_digest(
            f"{opened_info.st_dev}:{opened_info.st_ino}",
            f"{info.st_dev}:{info.st_ino}",
        ):
            raise RuntimeError("The file changed while it was being checked. Reload it before saving.")

        temp_name = ".omnitrix-write-" + secrets.token_hex(12)
        temp_fd = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow_flag,
            stat.S_IMODE(opened_info.st_mode),
            dir_fd=parent_fd,
        )
        os.fchmod(temp_fd, stat.S_IMODE(opened_info.st_mode))
        view = memoryview(encoded)
        while view:
            written = os.write(temp_fd, view)
            if written <= 0:
                raise OSError("Short write while saving workspace file.")
            view = view[written:]
        os.fsync(temp_fd)
        os.close(temp_fd)
        temp_fd = None

        latest = os.stat(target_name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(latest.st_mode)
            or latest.st_dev != opened_info.st_dev
            or latest.st_ino != opened_info.st_ino
            or latest.st_size != opened_info.st_size
            or latest.st_mtime_ns != opened_info.st_mtime_ns
        ):
            raise RuntimeError("The file changed during save; no replacement was made.")

        os.rename(temp_name, target_name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temp_name = None
        os.fsync(parent_fd)
        return {
            "path": relative_path,
            "previous_sha256": previous_hash,
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "size_bytes": len(encoded),
            "written_at": utc_now(),
            "write_mode": "atomic_existing_file_only",
        }
    finally:
        if temp_fd is not None:
            os.close(temp_fd)
        if temp_name is not None:
            try:
                os.unlink(temp_name, dir_fd=parent_fd)
            except OSError:
                pass
        if target_fd is not None:
            os.close(target_fd)
        os.close(parent_fd)


class PublicChatRateLimitError(RuntimeError):
    """The anonymous mobile chat endpoint has reached a conservative request limit."""



def _validate_manim_render_arguments(arguments: Any) -> None:
    """Validate structured diagram inputs before any render process/job is started."""
    if not isinstance(arguments, dict):
        raise ValueError("Manim render arguments must be a JSON object.")
    allowed = {"title", "nodes", "arrows", "quality"}
    if set(arguments) - allowed:
        raise ValueError("Unsupported Manim render fields were supplied.")
    title = arguments.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 100:
        raise ValueError("title must be non-empty text up to 100 characters.")
    if any(ord(char) < 32 for char in title):
        raise ValueError("title contains unsupported control characters.")
    nodes = arguments.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 8:
        raise ValueError("nodes must contain between 1 and 8 structured nodes.")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or set(node) != {"label", "x", "y"}:
            raise ValueError(f"Node {index + 1} must contain only label, x and y.")
        label = node.get("label")
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 72:
            raise ValueError(f"Node {index + 1} label must be non-empty text up to 72 characters.")
        if any(ord(char) < 32 for char in label):
            raise ValueError(f"Node {index + 1} label contains unsupported control characters.")
        for axis, low, high in (("x", -5.5, 5.5), ("y", -2.8, 2.8)):
            coordinate = node.get(axis)
            if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
                raise ValueError(f"Node {index + 1} {axis} coordinate must be a finite number.")
            if not math.isfinite(float(coordinate)) or not low <= coordinate <= high:
                raise ValueError(f"Node {index + 1} {axis} coordinate is outside the safe diagram bounds.")
    arrows = arguments.get("arrows", [])
    if not isinstance(arrows, list) or len(arrows) > 12:
        raise ValueError("arrows must be a list of at most 12 index pairs.")
    for pair in arrows:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("Each arrow must be a pair of node indices.")
        start, end = pair
        if any(isinstance(index, bool) or not isinstance(index, int) for index in (start, end)):
            raise ValueError("Arrow indices must be integers.")
        if start == end or not (0 <= start < len(nodes) and 0 <= end < len(nodes)):
            raise ValueError("Arrow indices must refer to two different existing nodes.")
    quality = arguments.get("quality", "low")
    if quality not in {"low", "medium"}:
        raise ValueError("quality must be low or medium.")


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
        cline_omnitrix: Omnitrix | None = None,
        access_token: str,
        workspace_read_enabled: bool,
        allowed_paths: list[str] | None,
        workspace_write_enabled: bool = False,
        tests_enabled: bool,
        public_chat_enabled: bool = False,
        test_timeout_seconds: int = TEST_TIMEOUT_SECONDS,
        code_root: Path | None = None,
        auto_sync_main: bool = False,
        auto_sync_interval_seconds: int = 60,
    ) -> None:
        self.root = root
        self.attachment_root = self.root / "chat-attachments"
        self.attachment_root.mkdir(parents=True, exist_ok=True)
        self.attachment_lock = threading.RLock()
        self.attachment_records: dict[str, dict[str, dict[str, Any]]] = {}
        self.pending_attachments: dict[str, list[str]] = {}
        # This cache is intentionally transient. On runtime startup there is no
        # authenticated manifest for prior uploads, so discard stale orphan blobs.
        cutoff = time.time() - 24 * 60 * 60
        try:
            for stale in self.attachment_root.rglob("*"):
                if stale.is_file() and not stale.is_symlink() and stale.stat().st_mtime < cutoff:
                    stale.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("Could not prune every stale attachment blob.")
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
        self.creative_analysis_lock = threading.Lock()
        self.creative_jobs_lock = threading.RLock()
        self.creative_jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        # Manim renders are bounded, authenticated background jobs. The free web
        # service allows one render at a time and keeps only a small in-memory queue.
        self.manim_jobs_lock = threading.RLock()
        self.manim_jobs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.manim_render_lock = threading.Lock()
        self.active_chats = 0
        self.active_chats_lock = threading.Lock()
        # The public mobile activity endpoint is scoped to this opaque session ID.
        self.active_chat_session_id: str | None = None
        self.app = app
        self.omnitrix = omnitrix
        self.cline_omnitrix = cline_omnitrix
        self.cline_execution_lock = threading.Lock()
        self.workspace_tool = workspace_tool
        self.access_token = access_token
        self.workspace_read_enabled = workspace_read_enabled
        self.workspace_write_enabled = bool(workspace_write_enabled and workspace_read_enabled)
        self.allowed_paths = allowed_paths
        self.tests_enabled = tests_enabled
        self.test_timeout_seconds = test_timeout_seconds
        self.public_chat_enabled = public_chat_enabled
        self.public_chat_per_minute_limit = PUBLIC_CHAT_PER_MINUTE
        self.public_chat_per_day_limit = PUBLIC_CHAT_PER_DAY
        self.public_chat_global_per_day_limit = PUBLIC_CHAT_GLOBAL_PER_DAY
        self.public_chat_lock = threading.Lock()
        self.public_chat_events: dict[str, deque[float]] = {}
        self.public_chat_global_events: deque[float] = deque()
        self.public_attachment_lock = threading.Lock()
        self.public_attachment_events: dict[str, deque[tuple[float, int]]] = {}
        self.sessions: OrderedDict[str, Conversation] = OrderedDict()
        self.sessions_lock = threading.Lock()
        self.test_lock = threading.Lock()
        self.test_result_lock = threading.Lock()
        self.last_test: dict[str, Any] | None = None

    def start_creative_analysis(self, payload: Any) -> dict[str, Any]:
        """Start a bounded background analysis so long provider calls do not hold the HTTP request."""
        if not isinstance(payload, dict) or payload.get("consent") is not True:
            raise ValueError("Explicit preview-sharing consent is required.")
        rows = payload.get("assets")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 6:
            raise ValueError("Select between 1 and 6 timeline shots.")
        if not self.creative_analysis_lock.acquire(blocking=False):
            raise RuntimeError("Creative analysis is already running; retry this request.")

        job_id = secrets.token_urlsafe(24)
        submitted_at = utc_now()
        try:
            with self.creative_jobs_lock:
                while len(self.creative_jobs) >= MAX_CREATIVE_JOBS:
                    removable = next(
                        (key for key, value in self.creative_jobs.items()
                         if value.get("status") != "processing"),
                        None,
                    )
                    if removable is None:
                        raise RuntimeError("Creative analysis job capacity is full; retry later.")
                    self.creative_jobs.pop(removable, None)
                self.creative_jobs[job_id] = {
                    "job_id": job_id, "status": "processing",
                    "submitted_at": submitted_at, "finished_at": None, "result": None,
                }
            worker = threading.Thread(
                target=self._run_creative_analysis,
                args=(job_id, payload),
                name="omnitrix-creative-analysis",
                daemon=True,
            )
            worker.start()
        except Exception:
            with self.creative_jobs_lock:
                self.creative_jobs.pop(job_id, None)
            self.creative_analysis_lock.release()
            raise
        route = creative_model_status()
        return {
            "ok": True, "job_id": job_id, "status": "processing",
            "submitted_at": submitted_at, "provider": route.get("provider"),
            "configured_model": route.get("model"),
            "note": "Job accepted. The actual worker/model identity is reported only when analysis completes.",
        }

    def _run_creative_analysis(self, job_id: str, payload: dict[str, Any]) -> None:
        """Run a single consented provider request and persist only its bounded result."""
        try:
            result = analyze_creative_request(payload)
            if not isinstance(result, dict):
                result = {
                    "ok": False, "status": "failed",
                    "error": "Visual analysis returned an invalid response. No edits were applied.",
                }
        except ValueError as exc:
            result = {"ok": False, "status": "failed", "error": str(exc)}
        except Exception as exc:
            LOGGER.warning("Creative analysis failed safely; exception_type=%s", type(exc).__name__)
            result = {
                "ok": False, "status": "failed",
                "error": "Visual analysis failed safely. Check provider configuration and runtime logs.",
            }
        try:
            with self.creative_jobs_lock:
                record = self.creative_jobs.get(job_id)
                if record is not None:
                    record["status"] = (
                        "complete" if result.get("ok") is True and result.get("status") == "complete"
                        else "failed"
                    )
                    record["result"] = result
                    record["finished_at"] = utc_now()
                    self.creative_jobs.move_to_end(job_id)
        finally:
            self.creative_analysis_lock.release()

    def creative_job_status(self, job_id: str) -> dict[str, Any]:
        """Return only a job's state/result; never expose prompts, preview bytes, or secrets."""
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{24,64}", job_id):
            raise ValueError("Invalid creative job ID.")
        with self.creative_jobs_lock:
            record = self.creative_jobs.get(job_id)
            if record is None:
                return {"ok": False, "status": "not_found", "error": "Creative analysis job not found."}
            if record.get("status") == "processing":
                return {
                    "ok": True, "job_id": job_id, "status": "processing",
                    "submitted_at": record.get("submitted_at"),
                }
            return {
                "ok": True, "job_id": job_id, "status": record.get("status"),
                "submitted_at": record.get("submitted_at"),
                "finished_at": record.get("finished_at"),
                "result": record.get("result"),
            }

    def start_manim_render(self, payload: Any) -> dict[str, Any]:
        """Queue a consented structured diagram render and track it in the shared manifest."""
        if not isinstance(payload, dict) or payload.get("consent") is not True:
            raise ValueError("Explicit consent is required before starting a Manim render.")
        allowed = {"consent", "title", "nodes", "arrows", "quality"}
        if set(payload) - allowed:
            raise ValueError("Unsupported Manim render fields were supplied.")
        # Validate before allocating a job or starting a worker.
        tool = self.omnitrix.tool_registry.get("manim_scientific_diagram")
        if tool is None:
            raise RuntimeError("Manim renderer is not registered in this runtime.")
        arguments = {key: value for key, value in payload.items() if key != "consent"}
        _validate_manim_render_arguments(arguments)
        # Probe availability only after side-effect-free validation. Never run an
        # actual render synchronously merely to validate its arguments.
        if not shutil.which("manim"):
            fallback_available = getattr(tool, "fallback_available", None)
            if not callable(fallback_available) or not fallback_available():
                raise RuntimeError("Manim is unavailable and the bundled Pillow/imageio-ffmpeg renderer dependencies are missing.")
        now = utc_now()
        job_id = secrets.token_hex(16)
        objective = str(arguments.get("title", "Scientific diagram render"))[:100]
        manifest = CreativeProductionManifest(job_id, objective)
        manifest.add_task(
            "render-diagram", "manim_worker", "Render validated scientific diagram",
            writes=["final_mp4"],
        )
        manifest.set_task_state("render-diagram", "running")
        with self.manim_jobs_lock:
            for key, record in list(self.manim_jobs.items()):
                if record.get("status") not in {"queued", "processing"} and len(self.manim_jobs) >= MAX_CREATIVE_JOBS:
                    self.manim_jobs.pop(key, None)
            if len(self.manim_jobs) >= MAX_CREATIVE_JOBS:
                raise RuntimeError("Manim job capacity is full; retry after a render finishes.")
            if any(record.get("status") in {"queued", "processing"} for record in self.manim_jobs.values()):
                raise RuntimeError("A Manim render is already running; wait for it to finish.")
            self.manim_jobs[job_id] = {
                "job_id": job_id, "status": "queued", "submitted_at": now,
                "finished_at": None, "result": None, "manifest": manifest,
            }
        try:
            worker = threading.Thread(
                target=self._run_manim_render,
                args=(job_id, arguments),
                name="omnitrix-manim-" + job_id[:8],
                daemon=True,
            )
            worker.start()
        except Exception:
            with self.manim_jobs_lock:
                self.manim_jobs.pop(job_id, None)
            raise
        return {
            "ok": True, "job_id": job_id, "status": "queued",
            "submitted_at": now, "renderer": "manim",
            "note": "Render queued. A successful process exit alone is not a quality approval; inspect the returned artifact.",
        }

    def _run_manim_render(self, job_id: str, arguments: dict[str, Any]) -> None:
        """Execute one guarded Manim job and attach evidence to its manifest."""
        if not self.manim_render_lock.acquire(blocking=False):
            with self.manim_jobs_lock:
                record = self.manim_jobs.get(job_id)
                if record:
                    record["status"] = "failed"
                    record["result"] = {"ok": False, "error": "A Manim render is already active."}
                    record["finished_at"] = utc_now()
            return
        try:
            with self.manim_jobs_lock:
                record = self.manim_jobs.get(job_id)
                if record is None:
                    return
                record["status"] = "processing"
            result = self.omnitrix.tool_registry.get("manim_scientific_diagram").execute(**arguments)
            manifest = None
            with self.manim_jobs_lock:
                record = self.manim_jobs.get(job_id)
                if record is not None:
                    manifest = record.get("manifest")
            if not result.success or not isinstance(result.output, dict):
                error = result.error or "Manim did not return a verified MP4 artifact."
                if manifest is not None:
                    manifest.set_task_state("render-diagram", "failed", failure=error)
                payload = {"ok": False, "status": "failed", "error": error, "metadata": result.metadata or {}}
            else:
                output_path = Path(str(result.output.get("artifact_path", ""))).expanduser()
                if not output_path.is_file() or output_path.is_symlink():
                    raise RuntimeError("The renderer's reported artifact is not a regular file.")
                size = output_path.stat().st_size
                if size <= 0 or size > 24 * 1024 * 1024:
                    raise RuntimeError("The rendered MP4 exceeds the 24 MB Studio media-import limit.")
                digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
                manifest.register_artifact(
                    "final_mp4", kind="video/mp4", owner_task_id="render-diagram",
                    uri=str(output_path), sha256=digest, verified=True,
                )
                manifest.set_task_state(
                    "render-diagram", "succeeded",
                    evidence=["artifact_exists", "size_bytes:" + str(size), "sha256:" + digest],
                )
                payload = {
                    "ok": True, "status": "complete", "renderer": "manim",
                    "artifact_id": "final_mp4", "artifact_url": "/api/creative/manim-jobs/" + job_id + "/artifact",
                    "mime_type": "video/mp4", "size_bytes": size, "sha256": digest,
                    "quality_review": "not_run",
                    "note": "Technical artifact checks passed; scientific correctness, visual quality, and audio were not independently reviewed.",
                    "metadata": result.metadata or {},
                }
        except Exception as exc:
            LOGGER.warning("Manim job failed safely; exception_type=%s", type(exc).__name__)
            with self.manim_jobs_lock:
                record = self.manim_jobs.get(job_id)
                manifest = record.get("manifest") if record else None
            if manifest is not None:
                try:
                    manifest.set_task_state("render-diagram", "failed", failure="Render or artifact validation failed.")
                except (ProductionContractError, KeyError):
                    pass
            payload = {"ok": False, "status": "failed", "error": "Manim render or artifact validation failed safely."}
        finally:
            self.manim_render_lock.release()
        with self.manim_jobs_lock:
            record = self.manim_jobs.get(job_id)
            if record is not None:
                record["status"] = payload.get("status", "failed")
                record["result"] = payload
                record["finished_at"] = utc_now()
                self.manim_jobs.move_to_end(job_id)

    def manim_job_status(self, job_id: str) -> dict[str, Any]:
        """Return bounded render state without exposing the source brief or local file path."""
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
            return {"ok": False, "error": "Manim job was not found."}
        with self.manim_jobs_lock:
            record = self.manim_jobs.get(job_id)
            if record is None:
                return {"ok": False, "error": "Manim job was not found or has expired."}
            if record.get("status") in {"queued", "processing"}:
                return {"ok": True, "job_id": job_id, "status": record["status"], "submitted_at": record["submitted_at"]}
            return {
                "ok": bool((record.get("result") or {}).get("ok")),
                "job_id": job_id, "status": record.get("status"),
                "submitted_at": record.get("submitted_at"), "finished_at": record.get("finished_at"),
                "result": record.get("result"),
                "manifest": record["manifest"].to_dict() if record.get("manifest") else None,
            }

    def manim_job_artifact(self, job_id: str) -> tuple[bytes, str] | None:
        """Read only an artifact registered by a successful job in this runtime."""
        with self.manim_jobs_lock:
            record = self.manim_jobs.get(job_id)
            if not record or record.get("status") != "complete":
                return None
            result = record.get("result") or {}
            manifest = record.get("manifest")
            artifact = manifest.artifacts.get("final_mp4") if manifest is not None else None
            if not artifact or not artifact.verified or not artifact.uri:
                return None
            path = Path(artifact.uri)
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 24 * 1024 * 1024:
            return None
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != artifact.sha256:
            return None
        return content, "omnitrix-science-diagram-" + job_id[:8] + ".mp4"

    def status(self) -> dict[str, Any]:
        """Expose safe runtime metadata, never credentials or absolute workspace paths."""
        models = [
            {
                "name": item.name,
                "provider": item.provider,
                "model_id": item.model_id,
                "capabilities": sorted(item.capabilities),
                "reasoning_effort": item.metadata.get("reasoning_effort"),
                "adapter_available": (
                    self.omnitrix.adapter_registry.has(item.name)
                    and self.omnitrix.adapter_registry.get(item.name).is_available()
                ),
            }
            for item in self.omnitrix.registry.list_enabled()
        ]
        agent_registry = getattr(self.omnitrix, "agent_registry", None)
        agents = [
            {
                "name": agent.name,
                "role": agent.role,
                "stage": agent.stage,
                "purpose": agent.purpose,
                "capabilities": sorted(agent.capabilities),
                "preferred_models": list(agent.preferred_models),
                "enabled": agent.enabled,
            }
            for agent in agent_registry.list_enabled()
        ] if agent_registry is not None else []
        specialists_configured = bool(
            agent_registry is not None and agent_registry.enabled and agents
        )
        live_provider_configured = any(
            model["provider"] != "demo" and model["adapter_available"]
            for model in models
        )
        cline_tool = (
            self.cline_omnitrix.tool_registry.get("cline.coding")
            if self.cline_omnitrix is not None
            and self.cline_omnitrix.tool_registry.has("cline.coding")
            else None
        )
        cline_runtime_status = (
            cline_tool.runtime_status()
            if cline_tool is not None and callable(getattr(cline_tool, "runtime_status", None))
            else {"registered": False, "executable_found": False, "ready_to_attempt": False}
        )
        cline_worker = {
            "enabled": self.cline_omnitrix is not None,
            "endpoint": "/api/admin/cline/chat",
            "authentication": "runtime_bearer_token_required",
            "provider": os.getenv("CLINE_PROVIDER", "openrouter"),
            "model": os.getenv("CLINE_MODEL", "minimax/minimax-m3.1-flash:free"),
            "provider_key_detected": bool(os.getenv(os.getenv("CLINE_API_KEY_ENV", "OPENROUTER_API_KEY"))),
            **cline_runtime_status,
            "persistence": (
                "remote worker proposes validated changes as a reviewable pull request; never auto-merges"
                if os.getenv("CLINE_EXECUTION_BACKEND", "").strip().lower() == "github_actions"
                else "runtime filesystem only; no GitHub commit or pull request is created"
            ),
        }
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
                    **(
                        {"runtime_status": tool.runtime_status()}
                        if callable(getattr(tool, "runtime_status", None))
                        else {}
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
            "workspace_write_enabled": self.workspace_write_enabled,
            "workspace_allowlist": self.allowed_paths,
            "tests_enabled": self.tests_enabled,
            "test_timeout_seconds": self.test_timeout_seconds,
            "provider_mode": (
                "offline-demo"
                if models and all(model["provider"] == "demo" for model in models)
                else "configured-model"
            ),
            "gemini_key_detected": bool(os.getenv("GEMINI_API_KEY")),
            "openrouter_key_detected": bool(os.getenv("OPENROUTER_API_KEY")),
            "public_chat_enabled": self.public_chat_enabled,
            "cline_worker": cline_worker,
            "specialists_configured": specialists_configured,
            "specialist_runtime_active": specialists_configured and live_provider_configured,
            "specialist_settings": (
                {
                    "intent_mode": agent_registry.intent_mode,
                    "critic_mode": agent_registry.critic_mode,
                }
                if agent_registry is not None else None
            ),
            "agents": agents,
            "models": models,
            "tools": tool_details,
            "multimodal_toolchain": toolchain_status(),
            "multimodal_journal": journal_status(),
            "active_execution": getattr(self.omnitrix, "active_execution", None),
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
        if not self.auto_sync_main:
            self.sync_status = "disabled"
            self.sync_last_result = "Automatic GitHub sync is disabled."
            return False
        if not self.sync_lock.acquire(blocking=False):
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

    def mobile_health(self) -> dict[str, Any]:
        """Report hosted-chat readiness from routes available to this running process."""
        enabled_models = self.omnitrix.registry.list_enabled()
        configured_live_models = [
            model for model in enabled_models
            if model.provider not in {"demo", "test"} and model.model_id
        ]

        available_models = []
        for model in configured_live_models:
            if not self.omnitrix.adapter_registry.has(model.name):
                continue
            adapter = self.omnitrix.adapter_registry.get(model.name)
            if adapter.is_available():
                available_models.append(model)

        openrouter_reasoning_models = [
            model for model in configured_live_models
            if model.provider == "openrouter" and "reasoning" in model.capabilities
        ]
        reasoning_model = openrouter_reasoning_models[0] if openrouter_reasoning_models else None
        reasoning_specialist_available = any(
            model.provider == "openrouter"
            and "reasoning" in model.capabilities
            and model in available_models
            for model in configured_live_models
        )

        # This is a readiness hint, not a claim about the model that will answer
        # every prompt. Role-specific routing can choose a different live model.
        report_model = next(
            (
                model for model in available_models
                if model.provider == "openrouter" and "reasoning" in model.capabilities
            ),
            next(
                (model for model in available_models if model.provider == "google"),
                available_models[0] if available_models else None,
            ),
        )

        provider_keys_detected = {
            "gemini_primary": bool(os.getenv("GEMINI_API_KEY")),
            "gemini_secondary": bool(os.getenv("GEMINI_API_KEY_1")),
            "openrouter_primary": bool(os.getenv("OPENROUTER_API_KEY")),
            "openrouter_secondary": bool(os.getenv("OPENROUTER_API_KEY_1")),
            "groq_primary": bool(os.getenv("GROQ_API_KEY")),
            "groq_secondary": bool(os.getenv("GROQ_API_KEY_1")),
        }
        configured_model_routes = []
        agent_registry = self.omnitrix.agent_registry
        for model in configured_live_models:
            adapter_registered = self.omnitrix.adapter_registry.has(model.name)
            adapter = (
                self.omnitrix.adapter_registry.get(model.name)
                if adapter_registered else None
            )
            key_name = model.metadata.get(
                "api_key_env",
                {"google": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY", "groq": "GROQ_API_KEY"}.get(model.provider, ""),
            )
            route_ready = bool(adapter is not None and adapter.is_available())
            preferred_by_roles = []
            if agent_registry is not None:
                for agent in agent_registry.list_enabled():
                    if model.name in agent.preferred_models or model.model_id in agent.preferred_models:
                        preferred_by_roles.append(agent.role)
            configured_model_routes.append({
                "profile": model.name,
                "provider": model.provider,
                "model": model.model_id or model.name,
                "api_key_env": key_name,
                "key_detected": bool(os.getenv(key_name)) if key_name else False,
                "adapter_registered": adapter_registered,
                "ready": route_ready,
                "status": "ready" if route_ready else "provider_key_missing_or_adapter_unavailable",
                "preferred_by_roles": preferred_by_roles,
            })
        ready_model_route_count = sum(1 for route in configured_model_routes if route["ready"])
        cline_tool = (
            self.cline_omnitrix.tool_registry.get("cline.coding")
            if self.cline_omnitrix is not None
            and self.cline_omnitrix.tool_registry.has("cline.coding")
            else None
        )
        cline_runtime_status = (
            cline_tool.runtime_status()
            if cline_tool is not None and callable(getattr(cline_tool, "runtime_status", None))
            else {"registered": False, "executable_found": False, "ready_to_attempt": False}
        )

        available = self.public_chat_enabled and bool(available_models)
        if not self.public_chat_enabled:
            reason = "public_chat_disabled"
        elif not configured_live_models:
            reason = "model_not_configured"
        elif not available_models:
            reason = "provider_key_missing"
        else:
            reason = None

        return {
            "ok": True,
            "service": "omnitrix-mobile-api",
            "revision": self._git_output(["rev-parse", "--short=7", "HEAD"]) or "unknown",
            "chat_available": available,
            "reason": reason,
            "model": (
                report_model.model_id or report_model.name
                if report_model is not None else None
            ),
            "provider": report_model.provider if report_model is not None else None,
            "model_identity_source": (
                "configured_route_not_a_completed_request"
                if report_model is not None else "no_available_route"
            ),
            "available_models": [
                {
                    "provider": model.provider,
                    "model": model.model_id or model.name,
                }
                for model in available_models
            ],
            "gemini_key_detected": bool(os.getenv("GEMINI_API_KEY")),
            "openrouter_key_detected": bool(os.getenv("OPENROUTER_API_KEY")),
            "provider_keys_detected": provider_keys_detected,
            "all_six_key_slots_detected": all(provider_keys_detected.values()),
            "configured_model_routes": configured_model_routes,
            "configured_model_route_count": len(configured_model_routes),
            "ready_model_route_count": ready_model_route_count,
            "route_readiness_note": "Ready means the configured adapter sees its key. It does not prove a successful model inference; use execution trace/provider response metadata for that.",
            "cline_worker_enabled": self.cline_omnitrix is not None,
            "cline_cli_ready": bool(cline_runtime_status.get("ready_to_attempt")),
            "cline_worker_backend": cline_runtime_status.get("backend", "local"),
            "cline_worker_credential_configured": cline_runtime_status.get("worker_credential_configured"),
            "cline_provider_key_detected": bool(os.getenv(os.getenv("CLINE_API_KEY_ENV", "OPENROUTER_API_KEY"))),
            "reasoning_specialist_available": reasoning_specialist_available,
            "preferred_reasoning_model": (
                reasoning_model.model_id or reasoning_model.name
                if reasoning_model is not None else None
            ),
            "reasoning_route_status": (
                "ready" if reasoning_specialist_available
                else "provider_key_missing" if reasoning_model is not None
                else "model_not_configured"
            ),
        }

    def _public_session_id(self, session_id: str, client_ip: str) -> str:
        """Namespace a public session to this service and caller IP without exposing the raw ID."""
        client_key = hashlib.sha256(
            (self.access_token + "\\0" + client_ip).encode("utf-8")
        ).hexdigest()
        return "public_" + hashlib.sha256(
            (client_key + "\\0" + session_id).encode("utf-8")
        ).hexdigest()[:48]

    def mobile_activity(self, session_id: Any, client_ip: str) -> dict[str, Any]:
        """Expose only the matching mobile session's current model route; never prompts or reasoning."""
        if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
            return {"ok": True, "active": False, "status": "idle"}

        ip = client_ip.strip()[:128] if isinstance(client_ip, str) else ""
        expected_session = self._public_session_id(session_id, ip or "unknown")
        with self.active_chats_lock:
            active_session = self.active_chat_session_id

        if active_session != expected_session:
            return {"ok": True, "active": False, "status": "idle"}

        current = getattr(self.omnitrix, "active_execution", None)
        task_metadata = getattr(self.omnitrix, "active_task_metadata", None)
        if not isinstance(task_metadata, dict) and not isinstance(current, dict):
            return {"ok": True, "active": False, "status": "idle"}

        allowed_fields = (
            "status", "stage", "role", "provider", "model", "configured_model",
            "configured_name", "reasoning_effort_requested", "identity_source",
            "fallback_from_model", "fallback_reason",
        )

        def safe_activity(record: Any) -> dict[str, Any] | None:
            if not isinstance(record, dict):
                return None
            return {
                key: record.get(key)
                for key in allowed_fields + ("latency_seconds", "review_status")
                if record.get(key) is None
                or isinstance(record.get(key), (str, int, float, bool))
            }

        raw_history = task_metadata.get("model_activity", []) if isinstance(task_metadata, dict) else []
        history = [
            item for record in raw_history
            if (item := safe_activity(record)) is not None
        ] if isinstance(raw_history, list) else []
        plan = {}
        if isinstance(task_metadata, dict):
            for key in ("primary_agent_role", "task_complexity", "task_domain"):
                value = task_metadata.get(key)
                if isinstance(value, str):
                    plan[key] = value
            agent_roles = task_metadata.get("agent_roles")
            if isinstance(agent_roles, list):
                plan["agent_roles"] = [
                    role for role in agent_roles if isinstance(role, str)
                ][:12]

        return {
            "ok": True,
            "active": True,
            "status": "working",
            "activity": safe_activity(current),
            "activity_history": history[-12:],
            "plan": plan,
        }

    def run_cline_chat(self, payload: Any) -> dict[str, Any]:
        """Run a coding task through a separate, operator-authenticated Cline-enabled Omnitrix."""
        if self.cline_omnitrix is None:
            return {
                "ok": False,
                "code": "cline_unavailable",
                "error": "The authenticated Cline worker is disabled or its CLI/provider is not ready.",
            }
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        task = payload.get("task")
        if not isinstance(task, str) or not 10 <= len(task.strip()) <= 8000:
            raise ValueError("task must contain 10–8000 characters.")
        acceptance = payload.get("acceptance_criteria", [])
        paths = payload.get("files_in_scope", [])
        for field_name, values, limit, item_limit in (
            ("acceptance_criteria", acceptance, 12, 800),
            ("files_in_scope", paths, 20, 240),
        ):
            if not isinstance(values, list) or len(values) > limit or any(
                not isinstance(value, str) or not value.strip() or len(value) > item_limit
                for value in values
            ):
                raise ValueError(f"{field_name} must be a list of at most {limit} bounded non-empty strings.")
        criteria_text = "\n".join(f"- {item}" for item in acceptance) if acceptance else "- Implement the requested change with relevant tests."
        paths_text = "\n".join(f"- {item}" for item in paths) if paths else "- Choose the smallest relevant files within the configured allowlist."
        prompt = (
            "The operator explicitly authorized this coding task. You are Omnitrix's coding lead. "
            "Use the coding specialist and MUST call the cline.coding tool in implement mode; do not answer with a text-only patch. "
            "Pass the complete task, criteria, and path scope to Cline. Review its execution result and report what actually happened. "
            "Do not claim changes were committed to GitHub; this worker only changes the current runtime workspace.\n\n"
            f"CODING TASK:\n{task.strip()}\n\nACCEPTANCE CRITERIA:\n{criteria_text}\n\n"
            f"TARGET PATHS (still subject to the runtime allowlist):\n{paths_text}"
        )
        if not self.cline_execution_lock.acquire(blocking=False):
            raise RuntimeError("Cline coding task is already running; retry later.")
        try:
            conversation = Conversation()
            answer = self.cline_omnitrix.chat(conversation, prompt)
            trace = self.cline_omnitrix.last_execution_trace or {}
            executions = trace.get("tool_executions", [])
            cline_events = [
                item for item in executions
                if isinstance(item, dict) and item.get("tool_name") == "cline.coding"
            ] if isinstance(executions, list) else []
            if not cline_events:
                return {
                    "ok": False,
                    "code": "cline_not_invoked",
                    "answer": answer,
                    "execution_trace": trace,
                    "persistence": "runtime_filesystem_only; no GitHub commit or pull request is created",
                }
            return {
                "ok": any(item.get("success") is True for item in cline_events),
                "answer": answer,
                "cline_executions": cline_events,
                "execution_trace": trace,
                "persistence": "runtime_filesystem_only; no GitHub commit or pull request is created",
            }
        finally:
            self.cline_execution_lock.release()

    def chat_public(self, payload: Any, client_ip: str) -> dict[str, Any]:
        """Rate-limited public chat only; this path cannot access workspace or test APIs."""
        if not self.public_chat_enabled:
            raise PermissionError("Hosted mobile chat is not enabled on this service.")
        readiness = self.mobile_health()
        if not readiness["chat_available"]:
            raise RuntimeError("Hosted AI is not configured. The backend model key and model profile must be set before chatting.")
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("session_id must be 16–128 letters, numbers, underscores or hyphens.")
        if not isinstance(client_ip, str):
            client_ip = ""
        client_ip = client_ip.strip()[:128] or "unknown"
        client_key = hashlib.sha256(
            (self.access_token + "\\0" + client_ip).encode("utf-8")
        ).hexdigest()
        now = time.monotonic()
        with self.public_chat_lock:
            minute_cutoff = now - 60
            day_cutoff = now - 86_400
            while self.public_chat_global_events and self.public_chat_global_events[0] <= day_cutoff:
                self.public_chat_global_events.popleft()
            if len(self.public_chat_global_events) >= self.public_chat_global_per_day_limit:
                raise PublicChatRateLimitError("Omnitrix has reached its hosted daily chat limit.")

            # Retire stale client buckets so anonymous traffic cannot grow the limiter forever.
            for stale_key, stale_events in list(self.public_chat_events.items()):
                while stale_events and stale_events[0] <= day_cutoff:
                    stale_events.popleft()
                if not stale_events:
                    self.public_chat_events.pop(stale_key, None)

            client_events = self.public_chat_events.setdefault(client_key, deque())
            recent_minute_count = sum(1 for stamp in client_events if stamp > minute_cutoff)
            if recent_minute_count >= self.public_chat_per_minute_limit:
                raise PublicChatRateLimitError("Chat rate limit reached. Try again in a minute.")
            if len(client_events) >= self.public_chat_per_day_limit:
                raise PublicChatRateLimitError("This connection has reached its daily chat limit.")
            client_events.append(now)
            self.public_chat_global_events.append(now)

        # Namespace caller-provided session IDs by the rate-limit identity so one client
        # cannot intentionally reuse another client's predictable conversation ID.
        safe_payload = dict(payload)
        safe_payload["session_id"] = self._public_session_id(session_id, client_ip)
        return self.chat(safe_payload)

    def _record_public_attachment_upload(self, client_ip: str, size: int) -> None:
        """Apply per-IP upload-rate and byte budgets to unauthenticated mobile uploads."""
        if size <= 0 or size > MAX_ATTACHMENT_BYTES:
            raise OverflowError(
                f"File exceeds the configured per-file limit of {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MiB."
            )
        ip = client_ip.strip()[:128] if isinstance(client_ip, str) else ""
        client_key = hashlib.sha256(
            (self.access_token + "\\0" + (ip or "unknown")).encode("utf-8")
        ).hexdigest()
        now = time.monotonic()
        with self.public_attachment_lock:
            events = self.public_attachment_events.setdefault(client_key, deque())
            day_cutoff = now - 86_400
            minute_cutoff = now - 60
            while events and events[0][0] <= day_cutoff:
                events.popleft()
            if sum(1 for stamp, _ in events if stamp > minute_cutoff) >= 20:
                raise PublicChatRateLimitError(
                    "Attachment upload rate limit reached. Wait a minute before uploading more files."
                )
            if sum(byte_count for _, byte_count in events) + size > 1024 * 1024 * 1024:
                raise PublicChatRateLimitError(
                    "This network has reached the hosted attachment allowance of 1 GiB per 24 hours."
                )
            events.append((now, size))
            # Bound limiter memory even if many distinct clients connect.
            if len(self.public_attachment_events) > 5000:
                for key, bucket in list(self.public_attachment_events.items()):
                    while bucket and bucket[0][0] <= day_cutoff:
                        bucket.popleft()
                    if not bucket:
                        self.public_attachment_events.pop(key, None)

    def upload_attachment_public(
        self, headers: Any, stream: Any, client_ip: str
    ) -> dict[str, Any]:
        """Stage a public mobile upload in an IP-namespaced session after quota checks."""
        if not self.public_chat_enabled or not self.mobile_health().get("chat_available"):
            raise PermissionError("Hosted multimodal chat is not enabled on this service.")
        raw_session = str(headers.get("X-Session-ID", "")).strip()
        if not SESSION_ID_PATTERN.fullmatch(raw_session):
            raise ValueError("A valid chat session ID is required for uploads.")
        try:
            length = int(headers.get("Content-Length", "0"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid attachment Content-Length.") from exc
        self._record_public_attachment_upload(client_ip, length)
        # Reuse the validated private upload path, but isolate anonymous callers' records.
        safe_headers = {
            "X-Session-ID": self._public_session_id(raw_session, client_ip.strip()[:128] or "unknown"),
            "X-File-Name": headers.get("X-File-Name", ""),
            "X-File-Mime": headers.get("X-File-Mime", ""),
            "Content-Length": str(length),
        }
        return self.upload_attachment(safe_headers, stream)

    def list_attachments_public(self, session_id: Any, client_ip: str) -> dict[str, Any]:
        """Read only the current caller's namespaced mobile attachment list."""
        if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("A valid chat session ID is required.")
        ip = client_ip.strip()[:128] if isinstance(client_ip, str) else ""
        return self.list_attachments(self._public_session_id(session_id, ip or "unknown"))

    def delete_attachment_public(self, payload: Any, client_ip: str) -> dict[str, Any]:
        """Delete a staged file only from the current caller's namespaced mobile session."""
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("A valid chat session ID is required.")
        safe_payload = dict(payload)
        ip = client_ip.strip()[:128] if isinstance(client_ip, str) else ""
        safe_payload["session_id"] = self._public_session_id(session_id, ip or "unknown")
        return self.delete_attachment(safe_payload)

    def upload_attachment(self, headers: Any, stream: Any) -> dict[str, Any]:
        """Stream one user-selected media file into the private runtime without buffering it."""
        session_id = str(headers.get("X-Session-ID", "")).strip()
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("A valid chat session ID is required for uploads.")
        raw_name = unquote(str(headers.get("X-File-Name", "")))
        name = safe_display_name(raw_name)
        supplied_mime = str(headers.get("X-File-Mime", ""))
        mime_type = accepted_mime_type(name, supplied_mime)
        raw_length = headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid attachment Content-Length.") from exc
        if length <= 0:
            raise ValueError("Empty files cannot be attached.")
        if length > MAX_ATTACHMENT_BYTES:
            raise OverflowError(
                f"File exceeds the configured per-file limit of {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MiB."
            )
        self.attachment_root.mkdir(parents=True, exist_ok=True)
        free_bytes = shutil.disk_usage(self.attachment_root).free
        if free_bytes < length + 32 * 1024 * 1024:
            raise ValueError("Runtime storage is nearly full; remove files or free disk space before uploading.")
        session_key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
        session_dir = self.attachment_root / session_key
        session_dir.mkdir(parents=True, exist_ok=True)
        attachment_id = secrets.token_hex(16)
        target = session_dir / attachment_id
        digest = hashlib.sha256()
        received = 0
        try:
            with target.open("xb") as output:
                while received < length:
                    chunk = stream.read(min(256 * 1024, length - received))
                    if not chunk:
                        raise ValueError("Upload ended before the advertised file size was received.")
                    output.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            try:
                os.chmod(target, 0o600)
            except OSError:
                pass
        except Exception:
            target.unlink(missing_ok=True)
            raise

        record = {
            "id": attachment_id,
            "name": name,
            "mime_type": mime_type,
            "size": length,
            "sha256": digest.hexdigest(),
            "path": str(target),
            "created_at": utc_now(),
        }
        with self.attachment_lock:
            self.attachment_records.setdefault(session_id, {})[attachment_id] = record
            self.pending_attachments.setdefault(session_id, []).append(attachment_id)
        return {
            "ok": True,
            "attachment": {
                "id": attachment_id,
                "name": name,
                "mime_type": mime_type,
                "size": length,
                "sha256": digest.hexdigest(),
                "status": "uploaded",
            },
            "limits": {
                "file_count_limit": None,
                "per_file_bytes": MAX_ATTACHMENT_BYTES,
                "storage": "available private runtime disk",
            },
        }

    def delete_attachment(self, payload: Any) -> dict[str, Any]:
        """Delete one staged attachment only from the caller's own chat session."""
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        session_id = payload.get("session_id")
        attachment_id = payload.get("attachment_id")
        if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("A valid chat session ID is required.")
        if not isinstance(attachment_id, str) or not re.fullmatch(r"[a-f0-9]{32}", attachment_id):
            raise ValueError("Invalid attachment ID.")
        with self.attachment_lock:
            record = self.attachment_records.get(session_id, {}).pop(attachment_id, None)
            pending = self.pending_attachments.get(session_id, [])
            self.pending_attachments[session_id] = [item for item in pending if item != attachment_id]
        if not record:
            return {"ok": True, "deleted": False}
        Path(record["path"]).unlink(missing_ok=True)
        return {"ok": True, "deleted": True, "attachment_id": attachment_id}

    def list_attachments(self, session_id: Any) -> dict[str, Any]:
        """List staged files for one browser session so refreshes do not orphan the tray."""
        if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError("A valid chat session ID is required.")
        with self.attachment_lock:
            rows = self.attachment_records.get(session_id, {})
            ids = list(self.pending_attachments.get(session_id, []))
            records = [dict(rows[item]) for item in ids if item in rows]
        return {
            "ok": True,
            "attachments": [
                {
                    "id": record["id"],
                    "name": record["name"],
                    "mime_type": record["mime_type"],
                    "size": record["size"],
                    "sha256": record["sha256"],
                    "status": "uploaded",
                }
                for record in records
            ],
        }

    def _pending_attachment_records(self, session_id: str) -> list[dict[str, Any]]:
        with self.attachment_lock:
            rows = self.attachment_records.get(session_id, {})
            ids = list(self.pending_attachments.get(session_id, []))
            return [dict(rows[item]) for item in ids if item in rows]

    def _remove_staged_attachment_ids(self, session_id: str, attachment_ids: list[str]) -> None:
        if not attachment_ids:
            return
        removed: list[dict[str, Any]] = []
        with self.attachment_lock:
            rows = self.attachment_records.get(session_id, {})
            for attachment_id in attachment_ids:
                record = rows.pop(attachment_id, None)
                if record:
                    removed.append(record)
            self.pending_attachments[session_id] = [
                item for item in self.pending_attachments.get(session_id, [])
                if item not in set(attachment_ids)
            ]
        for record in removed:
            try:
                Path(record["path"]).unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Could not remove consumed attachment blob.")

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
        staged = self._pending_attachment_records(session_id)
        started = time.monotonic()
        with self.active_chats_lock:
            self.active_chats += 1
        if not self.execution_lock.acquire(blocking=False):
            with self.active_chats_lock:
                self.active_chats -= 1
            raise RuntimeError("Studio is busy with another chat, test, or GitHub update; retry this request.")
        with self.active_chats_lock:
            self.active_chat_session_id = session_id
        attachment_result: dict[str, Any] | None = None
        consumed_ids: list[str] = []
        try:
            effective_message = message.strip()
            if staged:
                # Use capability-aware routing for a single file. Keep the existing
                # bounded batch analyzer for multi-file turns to preserve batching.
                attachment_result = (
                    analyze_single_attachment(staged[0], message.strip())
                    if len(staged) == 1
                    else analyze_multiple_attachments(staged, message.strip())
                )
                context = str(attachment_result.get("context", "")).strip()
                if context:
                    if attachment_result.get("status") != "complete":
                        analyzed_count = int(attachment_result.get("analyzed", 0) or 0)
                        remaining = staged[analyzed_count:]
                        if remaining:
                            context += "\n\nFILES NOT INCLUDED IN THIS ANALYSIS (do not claim to inspect them): " + ", ".join(
                                str(item.get("name", "unnamed file")) for item in remaining
                            )
                    effective_message += "\n\n" + context
                analyzed_count = int(attachment_result.get("analyzed", 0) or 0)
                consumed_ids = [str(item["id"]) for item in staged[:analyzed_count]]
            reply = self.app.send_message(conversation, effective_message)
            if consumed_ids:
                self._remove_staged_attachment_ids(session_id, consumed_ids)
        except Exception as exc:
            # Keep provider details and user content out of the client response, but
            # record a safe exception class so production failures are diagnosable.
            LOGGER.error("chat turn failed; exception_type=%s", type(exc).__name__)
            raise RuntimeError(
                "Omnitrix could not complete this turn. Check the configured model, "
                "provider credentials, budget policy, and server terminal output."
            ) from None
        finally:
            self.execution_lock.release()
            with self.active_chats_lock:
                if self.active_chat_session_id == session_id:
                    self.active_chat_session_id = None
                self.active_chats -= 1
        result = {
            "ok": True,
            "reply": reply,
            "provider_mode": self.status()["provider_mode"],
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "message_count": len(conversation.messages),
            "completed_at": utc_now(),
            "execution_trace": getattr(self.omnitrix, "last_execution_trace", None),
        }
        if attachment_result is not None:
            result["attachment_status"] = {
                "status": attachment_result.get("status", "unknown"),
                "count": attachment_result.get("count", len(staged)),
                "analyzed": attachment_result.get("analyzed", 0),
                "remaining": max(0, len(staged) - len(consumed_ids)),
                "error": attachment_result.get("error"),
                "worker": attachment_result.get("worker"),
                "model": attachment_result.get("model"),
                "workers": attachment_result.get("workers"),
                "consumed_ids": consumed_ids,
            }
        return result

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
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "connect-src 'self' https://api.github.com; "
                "img-src 'self' data: blob: https://upload.wikimedia.org https://images.pexels.com; base-uri 'self'; form-action 'self'; "
                "frame-ancestors 'none'",
            )
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

        def _send_bytes(self, data: bytes, content_type: str, filename: str, status: int = 200) -> None:
            if len(data) > 24 * 1024 * 1024:
                self._send_json({"ok": False, "error": "The selected asset exceeds the import limit."}, 413)
                return
            safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", filename)[:120] or "creative-asset"
            self.send_response(status)
            self._headers(content_type, api=True)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", 'attachment; filename="' + safe_name + '"')
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

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

        def _json_body(self, max_bytes: int = MAX_BODY_BYTES) -> Any:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("Invalid Content-Length.") from exc
            if length < 0 or length > max_bytes:
                raise OverflowError("Request body is too large.")
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Request body must be valid UTF-8 JSON.") from exc

        def _serve_apk_download(self) -> None:
            """Stream the current APK from a fixed, trusted GitHub release URL."""
            request = URLRequest(
                APK_DOWNLOAD_URL,
                headers={
                    "User-Agent": "Omnitrix-APK-Download/1.0",
                    "Accept": "application/octet-stream",
                },
            )
            headers_sent = False
            try:
                with urlopen_url(request, timeout=60) as upstream:
                    raw_length = upstream.headers.get("Content-Length", "")
                    try:
                        length = int(raw_length)
                    except (TypeError, ValueError):
                        length = 0
                    if length <= 0 or length > MAX_PUBLIC_DOWNLOAD_BYTES:
                        self._send_json(
                            {"ok": False, "error": "APK download source returned an invalid file size."},
                            502,
                        )
                        return

                    self.send_response(200)
                    self.send_header("Content-Type", "application/vnd.android.package-archive")
                    self.send_header("Content-Disposition", 'attachment; filename="Omnitrix.apk"')
                    self.send_header("Content-Length", str(length))
                    self.send_header("Cache-Control", "public, max-age=300")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    headers_sent = True

                    remaining = length
                    while remaining > 0:
                        chunk = upstream.read(min(256 * 1024, remaining))
                        if not chunk:
                            raise OSError("APK source ended before Content-Length bytes were received")
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                    self.wfile.flush()
            except Exception as exc:
                LOGGER.warning("APK download proxy failed: %s", type(exc).__name__)
                if not headers_sent:
                    self._send_json(
                        {"ok": False, "error": "APK download is temporarily unavailable. Retry shortly."},
                        502,
                    )
                else:
                    self.close_connection = True

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            route = parsed.path
            if route == "/downloads/Omnitrix.apk":
                self._serve_apk_download()
                return
            if route == "/api/mobile/health":
                self._send_json(runtime.mobile_health())
                return
            if route == "/api/mobile/activity":
                forwarded = self.headers.get("X-Forwarded-For", "")
                client_ip = forwarded.rsplit(",", 1)[-1].strip() if forwarded else self.client_address[0]
                self._send_json(runtime.mobile_activity(self._first_query("session_id", ""), client_ip))
                return
            if route == "/api/mobile/attachments/list":
                forwarded = self.headers.get("X-Forwarded-For", "")
                client_ip = forwarded.rsplit(",", 1)[-1].strip() if forwarded else self.client_address[0]
                try:
                    self._send_json(runtime.list_attachments_public(
                        self._first_query("session_id", ""), client_ip
                    ))
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 400)
                except Exception as exc:
                    LOGGER.warning("Public attachment listing failed: %s", type(exc).__name__)
                    self._send_json({"ok": False, "error": "Attachment list is temporarily unavailable."}, 500)
                return
            if route == "/api/mobile/creative/status":
                self._send_json(creative_model_status())
                return
            if route == "/api/mobile/creative/video-status":
                self._send_json(_paid_creative_media_status())
                return
            if route.startswith("/api/mobile/creative/jobs/"):
                job_id = route.rsplit("/", 1)[-1]
                result = runtime.creative_job_status(job_id)
                self._send_json(result, 200 if result.get("ok") else 404)
                return
            if route.startswith("/api/mobile/creative/video-jobs/"):
                job_id = route.rsplit("/", 1)[-1]
                result = creative_video_job_status(
                    job_id, consume_result=self._first_query("consume", "0") == "1"
                )
                self._send_json(result, 200 if result.get("ok") else 404)
                return
            if route in {"/api/mobile/creative/search", "/api/mobile/creative/assets/download"}:
                forwarded = self.headers.get("X-Forwarded-For", "")
                client_ip = forwarded.rsplit(",", 1)[-1].strip() if forwarded else self.client_address[0]
                if not _allow_public_creative_request(client_ip):
                    self._send_json({"ok": False, "error": "Creative Studio is temporarily rate-limited for this connection. Try again in a minute.", "code": "rate_limited"}, 429)
                    return
                try:
                    if route == "/api/mobile/creative/search":
                        raw_limit = self._first_query("limit", "12")
                        try:
                            requested_limit = int(raw_limit)
                        except (TypeError, ValueError) as exc:
                            raise ValueError("Asset search limit must be an integer between 1 and 12.") from exc
                        limit = min(12, max(1, requested_limit))
                        self._send_json(search_creative_assets(
                            self._first_query("q", ""),
                            provider=self._first_query("provider", "commons"),
                            kind=self._first_query("kind", "any"),
                            limit=limit,
                        ))
                    else:
                        content, content_type, filename = download_creative_asset(
                            self._first_query("url", ""), provider=self._first_query("provider", "commons")
                        )
                        self._send_bytes(content, content_type, filename)
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 400)
                except Exception as exc:
                    LOGGER.warning("Public mobile creative request failed: %s", type(exc).__name__)
                    self._send_json({"ok": False, "error": "Online creative assets are temporarily unavailable."}, 502)
                return
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
                    if route == "/api/creative/tools":
                        self._send_json(load_creative_tool_registry())
                    elif route.startswith("/api/creative/production/jobs/"):
                        job_id = route[len("/api/creative/production/jobs/"):].strip("/")
                        if "/" in job_id or not job_id:
                            self._send_json({"ok": False, "error": "Invalid production job route."}, 404)
                        else:
                            try:
                                self._send_json({"ok": True, "plan": get_shared_production_plan(job_id)})
                            except FileNotFoundError as exc:
                                self._send_json({"ok": False, "error": str(exc)}, 404)
                        return
                    elif route.startswith("/api/creative/manim-jobs/"):
                        remainder = route[len("/api/creative/manim-jobs/"):]
                        if remainder.endswith("/artifact"):
                            job_id = remainder[:-len("/artifact")].rstrip("/")
                            artifact = runtime.manim_job_artifact(job_id)
                            if artifact is None:
                                self._send_json({"ok": False, "error": "Manim artifact is not available or failed integrity validation."}, 404)
                            else:
                                content, filename = artifact
                                self._send_bytes(content, "video/mp4", filename)
                        else:
                            result = runtime.manim_job_status(remainder)
                            self._send_json(result, 200 if result.get("ok") else 404)
                        return
                    if route == "/api/creative/search":
                        raw_limit = self._first_query("limit", "10")
                        try:
                            limit = int(raw_limit)
                        except (TypeError, ValueError) as exc:
                            raise ValueError("Asset search limit must be an integer between 1 and 12.") from exc
                        self._send_json(search_creative_assets(
                            self._first_query("q", ""),
                            provider=self._first_query("provider", "commons"),
                            kind=self._first_query("kind", "any"),
                            limit=limit,
                        ))
                    elif route == "/api/creative/assets/download":
                        provider = self._first_query("provider", "")
                        url = self._first_query("url", "")
                        content, content_type, filename = download_creative_asset(url, provider=provider)
                        self._send_bytes(content, content_type, filename)
                    elif route == "/api/creative/status":
                        self._send_json(creative_model_status())
                    elif route == "/api/creative/video-status":
                        self._send_json(_paid_creative_media_status())
                    elif route.startswith("/api/creative/jobs/"):
                        job_id = route.rsplit("/", 1)[-1]
                        result = runtime.creative_job_status(job_id)
                        self._send_json(result, 200 if result.get("ok") else 404)
                    elif route.startswith("/api/creative/video-jobs/"):
                        job_id = route.rsplit("/", 1)[-1]
                        result = creative_video_job_status(
                            job_id, consume_result=self._first_query("consume", "0") == "1"
                        )
                        self._send_json(result, 200 if result.get("ok") else 404)
                    elif route == "/api/health":
                        self._send_json(runtime.status())
                    elif route == "/api/attachments/list":
                        self._send_json(runtime.list_attachments(self._first_query("session_id", "")))
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
            public_mobile_routes = {
                "/api/mobile/chat",
                "/api/mobile/attachments/upload",
                "/api/mobile/attachments/delete",
                "/api/mobile/creative/analyze",
                "/api/mobile/creative/generate-image",
                "/api/mobile/creative/generate-video",
            }
            if route not in public_mobile_routes and not self._authorized():
                self._send_json(
                    {
                        "ok": False,
                        "error": "Runtime access token required.",
                        "code": "unauthorized",
                    },
                    401,
                )
                return
            if route == "/api/mobile/attachments/upload":
                forwarded = self.headers.get("X-Forwarded-For", "")
                client_ip = forwarded.rsplit(",", 1)[-1].strip() if forwarded else self.client_address[0]
                try:
                    self._send_json(runtime.upload_attachment_public(self.headers, self.rfile, client_ip))
                except OverflowError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 413)
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 400)
                except PermissionError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 403)
                except PublicChatRateLimitError as exc:
                    self._send_json({"ok": False, "error": str(exc), "code": "rate_limited"}, 429)
                except OSError as exc:
                    LOGGER.warning("Public attachment upload could not write storage: %s", type(exc).__name__)
                    self._send_json({"ok": False, "error": "Runtime storage could not accept this file."}, 507)
                except Exception as exc:
                    LOGGER.warning("Public attachment upload failed: %s", type(exc).__name__)
                    self._send_json({"ok": False, "error": "Attachment upload failed safely."}, 500)
                return
            if route == "/api/attachments/upload":
                try:
                    self._send_json(runtime.upload_attachment(self.headers, self.rfile))
                except OverflowError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 413)
                except ValueError as exc:
                    self._send_json({"ok": False, "error": str(exc)}, 400)
                except OSError as exc:
                    LOGGER.warning("Attachment upload could not write storage: %s", type(exc).__name__)
                    self._send_json({"ok": False, "error": "Runtime storage could not accept this file."}, 507)
                except Exception as exc:
                    LOGGER.warning("Attachment upload failed: %s", type(exc).__name__)
                    self._send_json({"ok": False, "error": "Attachment upload failed safely."}, 500)
                return
            try:
                payload = self._json_body(
                    MAX_CREATIVE_BODY_BYTES if route in {"/api/creative/analyze", "/api/mobile/creative/analyze"} else MAX_BODY_BYTES
                )
            except OverflowError as exc:
                self._send_json({"ok": False, "error": str(exc)}, 413)
                return
            except ValueError as exc:
                self._send_json({"ok": False, "error": str(exc)}, 400)
                return
            if route in {"/api/creative/generate-image", "/api/mobile/creative/generate-image"} and (
                payload.get("consent") is not True or payload.get("paid_cost_acknowledged") is not True
            ):
                self._send_json({
                    "ok": False,
                    "error": "Explicit consent and paid-image cost acknowledgement are required before calling the image model (about US$0.04 per 1K image).",
                }, 400)
                return
            if route in {"/api/creative/generate-video", "/api/mobile/creative/generate-video"} and (
                payload.get("consent") is not True or payload.get("paid_cost_acknowledged") is not True
            ):
                self._send_json({
                    "ok": False,
                    "error": "Explicit paid-video cost acknowledgement is required. Estimated cost is about US$0.80 for an 8-second 720p video; actual duration may vary.",
                }, 400)
                return
            if route in {
                "/api/creative/generate-image", "/api/mobile/creative/generate-image",
                "/api/creative/generate-video", "/api/mobile/creative/generate-video",
            } and not _paid_creative_media_enabled():
                self._send_json({
                    "ok": False,
                    "error": "Paid image/video generation is disabled on this server to prevent unsolicited charges. The service owner must set OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA=true after reviewing pricing.",
                    "code": "paid_media_disabled",
                }, 503)
                return
            if route in {
                "/api/mobile/creative/analyze",
                "/api/mobile/creative/generate-image",
                "/api/mobile/creative/generate-video",
            }:
                forwarded = self.headers.get("X-Forwarded-For", "")
                client_ip = forwarded.rsplit(",", 1)[-1].strip() if forwarded else self.client_address[0]
                if payload.get("consent") is not True:
                    self._send_json({"ok": False, "error": "Explicit consent is required before sending previews or generating media with a model."}, 400)
                    return
                limiter = _allow_public_creative_video_request if route.endswith("/generate-video") else _allow_public_creative_model_request
                if not limiter(client_ip):
                    message = (
                        "The paid video-generation limit is reached for this connection or service today."
                        if route.endswith("/generate-video")
                        else "AI creative work is rate-limited for this connection. Try again later."
                    )
                    self._send_json({"ok": False, "error": message, "code": "rate_limited"}, 429)
                    return
            try:
                if route == "/api/creative/production/plan":
                    self._send_json({"ok": True, "plan": create_shared_production_plan(payload)}, 201)
                elif route.startswith("/api/creative/production/jobs/") and "/tasks/" in route:
                    remainder = route[len("/api/creative/production/jobs/"):]
                    job_id, task_id = remainder.split("/tasks/", 1)
                    if not job_id or not task_id or "/" in task_id:
                        self._send_json({"ok": False, "error": "Invalid production task route."}, 404)
                    else:
                        self._send_json({"ok": True, "plan": update_shared_production_task(job_id, task_id, payload)})
                elif route in {"/api/creative/analyze", "/api/mobile/creative/analyze"}:
                    self._send_json(runtime.start_creative_analysis(payload), 202)
                elif route == "/api/creative/manim-render":
                    self._send_json(runtime.start_manim_render(payload), 202)
                elif route in {"/api/creative/generate-image", "/api/mobile/creative/generate-image"}:
                    self._send_json(generate_creative_image(
                        payload.get("prompt"), aspect_ratio=payload.get("aspect_ratio", "16:9")
                    ))
                elif route in {"/api/creative/generate-video", "/api/mobile/creative/generate-video"}:
                    self._send_json(start_creative_video_job(
                        payload.get("prompt"),
                        aspect_ratio=payload.get("aspect_ratio", "16:9"),
                        resolution=payload.get("resolution", "720p"),
                    ), 202)
                elif route == "/api/chat":
                    self._send_json(runtime.chat(payload))
                elif route == "/api/admin/cline/chat":
                    result = runtime.run_cline_chat(payload)
                    self._send_json(result, 200 if result.get("ok") else 503)
                elif route == "/api/attachments/delete":
                    self._send_json(runtime.delete_attachment(payload))
                elif route == "/api/mobile/attachments/delete":
                    forwarded = self.headers.get("X-Forwarded-For", "")
                    client_ip = forwarded.rsplit(",", 1)[-1].strip() if forwarded else self.client_address[0]
                    self._send_json(runtime.delete_attachment_public(payload, client_ip))
                elif route == "/api/mobile/chat":
                    forwarded = self.headers.get("X-Forwarded-For", "")
                    client_ip = forwarded.rsplit(",", 1)[-1].strip() if forwarded else self.client_address[0]
                    self._send_json(runtime.chat_public(payload, client_ip))
                elif route == "/api/workspace/write":
                    self._workspace_write(payload)
                elif route == "/api/tests/run":
                    self._send_json(runtime.run_tests())
                else:
                    self._send_json(
                        {"ok": False, "error": "API route not found."}, 404
                    )
            except PublicChatRateLimitError as exc:
                self._send_json({"ok": False, "error": str(exc), "code": "rate_limited"}, 429)
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
            if result.success and isinstance(result.output, dict):
                file_content = result.output.get("content")
                if isinstance(file_content, str):
                    result.output["sha256"] = hashlib.sha256(file_content.encode("utf-8")).hexdigest()
            self._send_json(
                {
                    "ok": result.success,
                    "output": result.output,
                    "error": result.error,
                },
                200 if result.success else 400,
            )

        def _workspace_write(self, payload: Any) -> None:
            if not runtime.workspace_write_enabled:
                raise PermissionError("Workspace writing is disabled by the runtime.")
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")
            if not runtime.execution_lock.acquire(blocking=False):
                raise RuntimeError("Studio is busy with another chat, test, or GitHub update; retry this request.")
            try:
                result = write_workspace_file(
                    runtime.root,
                    payload.get("path"),
                    payload.get("content"),
                    payload.get("expected_sha256"),
                    runtime.allowed_paths,
                )
                result["working_tree_dirty"] = working_tree_dirty(runtime.code_root)
                self._send_json({"ok": True, "result": result})
            finally:
                runtime.execution_lock.release()

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
    registry = build_tool_registry(root, allowed_paths=args.workspace_allow, enable_cline=args.enable_cline_coding)
    capabilities = {"calculation"}
    if args.allow_workspace_read:
        capabilities.add("workspace.read")
    if args.enable_cline_coding:
        capabilities.add("coding.execute")
    spend_mode = (
        "user_provided_free_quota"
        if args.allow_free_quota
        else "zero_cost_only"
    )
    # Optional deployment-specific role preferences; absent in the normal
    # Codespaces path, where Omnitrix uses the default config/agents.json.
    agent_config_path = os.getenv("OMNITRIX_AGENT_CONFIG", "").strip() or None
    omnitrix = Omnitrix.from_config(
        config_path,
        tool_registry=registry,
        tool_permission=ToolPermission.from_capabilities(capabilities),
        budget_limits=BudgetLimits(spend_mode=spend_mode),
        agent_config_path=agent_config_path,
    )
    cline_omnitrix = None
    cline_api_enabled = os.getenv("OMNITRIX_ENABLE_CLINE_API", "").strip().lower() == "true"
    remote_cline_enabled = os.getenv("CLINE_EXECUTION_BACKEND", "").strip().lower() == "github_actions"
    local_cline_ready = bool(shutil.which("cline") and os.getenv("OPENROUTER_API_KEY"))
    if cline_api_enabled and (remote_cline_enabled or local_cline_ready):
        # Keep Cline out of the unauthenticated public mobile chat runtime.
        # Remote mode delegates execution to a disposable GitHub-hosted runner;
        # its separate orchestrator remains reachable only through token-protected /api routes.
        cline_allowed_paths = ("core", "tests", "interfaces", "scripts", "config", "webapp", "docs")
        cline_registry = build_tool_registry(
            root, allowed_paths=cline_allowed_paths, enable_cline=True
        )
        cline_omnitrix = Omnitrix.from_config(
            config_path,
            tool_registry=cline_registry,
            tool_permission=ToolPermission.from_capabilities(
                {"calculation", "workspace.read", "coding.execute"}
            ),
            budget_limits=BudgetLimits(spend_mode=spend_mode),
            agent_config_path=agent_config_path,
        )
    return StudioRuntime(
        root=root,
        config_path=config_path,
        app=ChatApplication(omnitrix),
        omnitrix=omnitrix,
        workspace_tool=registry.get("workspace.inspect"),
        cline_omnitrix=cline_omnitrix,
        access_token=access_token,
        workspace_read_enabled=args.allow_workspace_read,
        allowed_paths=args.workspace_allow,
        workspace_write_enabled=args.allow_workspace_write,
        tests_enabled=args.allow_test_run,
        public_chat_enabled=(
            args.allow_public_chat
            and os.getenv("OMNITRIX_PUBLIC_CHAT_ENABLED", "").strip().lower() == "true"
        ),
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
        "--enable-cline-coding",
        action="store_true",
        help="Enable the Cline coding agent in this trusted private runtime; requires workspace read/write and an authenticated Cline CLI.",
    )
    parser.add_argument(
        "--allow-workspace-write",
        action="store_true",
        help="Enable guarded atomic writes to existing text files inside the configured workspace allowlist.",
    )
    parser.add_argument(
        "--allow-test-run",
        action="store_true",
        help="Enable the fixed Python unittest discovery command.",
    )
    parser.add_argument(
        "--allow-public-chat",
        action="store_true",
        help="Enable the narrow public mobile chat endpoint; rate limits apply and workspace/test APIs remain authenticated.",
    )
    parser.add_argument(
        "--allow-free-quota",
        action="store_true",
        help="Allow only a provider account the operator has configured for free-quota use; does not prevent billing if that provider key has billing enabled.",
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
    if args.allow_workspace_write and not args.allow_workspace_read:
        parser.error("--allow-workspace-write requires --allow-workspace-read.")
    if args.enable_cline_coding and not (args.allow_workspace_read and args.allow_workspace_write):
        parser.error("--enable-cline-coding requires --allow-workspace-read and --allow-workspace-write.")
    if args.host not in {"127.0.0.1", "::1", "0.0.0.0"}:
        parser.error("--host must be a loopback address or 0.0.0.0.")
    if args.host == "0.0.0.0":
        print(
            "SECURITY: this port may be reachable from the public internet. "
            "Every /api route requires the generated bearer token; keep that token private. "
            "The server exposes bounded workspace operations and one fixed test command, not a general shell.",
            file=sys.stderr,
        )

    access_token = args.access_token or os.getenv("OMNITRIX_RUNTIME_TOKEN", "").strip() or secrets.token_urlsafe(32)
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
        runtime.stop_event.set()
        server.server_close()
        runtime.workspace_tool.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
