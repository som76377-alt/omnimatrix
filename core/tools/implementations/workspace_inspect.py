"""Read-only, root-confined workspace inspection for coding and research tasks."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import stat
from typing import Any

from core.tools.base import Tool, ToolResult


_MAX_FILE_BYTES = 64 * 1024
_MAX_DIRECTORY_ENTRIES = 100
_DENIED_NAMES = {
    "credentials", "credentials.json", "secrets", "secrets.json",
    "id_rsa", "id_ed25519", "authorized_keys",
}
_DENIED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".sqlite3", ".db"}


def _is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith(".")
        or lowered in _DENIED_NAMES
        or lowered.startswith(".env")
        or "secret" in lowered
        or "credential" in lowered
        or "token" in lowered
        or lowered.endswith(tuple(_DENIED_SUFFIXES))
    )


class WorkspaceInspectTool(Tool):
    """List one directory or read a bounded UTF-8 text file inside a fixed root."""

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        root = Path.cwd() if workspace_root is None else Path(workspace_root)
        self._root = root.expanduser().resolve(strict=True)
        if not self._root.is_dir():
            raise ValueError("Workspace root must be an existing directory.")

    @property
    def name(self) -> str:
        return "workspace.inspect"

    @property
    def description(self) -> str:
        return (
            "Read-only inspection of the explicitly configured workspace. "
            "Use operation=list for one directory or operation=read for one small text file. "
            "Hidden files, likely secrets, symlinks, binary files, and oversized files are denied."
        )

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"workspace.read"})

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "read"],
                    "description": "List a directory or read a UTF-8 text file.",
                },
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 512,
                    "description": "Workspace-relative path; use '.' for the root directory.",
                },
            },
            "required": ["operation", "path"],
            "additionalProperties": False,
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        operation = kwargs.get("operation")
        raw_path = kwargs.get("path")
        try:
            target = self._resolve_path(raw_path)
            if operation == "list":
                return self._list_directory(target, raw_path)
            if operation == "read":
                return self._read_text(target, raw_path)
            return ToolResult(success=False, error="Unsupported workspace operation.")
        except (OSError, UnicodeError, ValueError) as exc:
            return ToolResult(
                success=False,
                error=f"Workspace inspection refused ({type(exc).__name__}).",
            )

    def _resolve_path(self, raw_path: object) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("Path must be a non-empty workspace-relative string.")
        if "\\" in raw_path or raw_path.startswith("/"):
            raise ValueError("Absolute paths and backslashes are not accepted.")
        relative = PurePosixPath(raw_path)
        if any(part in {"..", ""} for part in relative.parts):
            raise ValueError("Path traversal is not allowed.")
        if raw_path != "." and any(_is_sensitive_name(part) for part in relative.parts):
            raise ValueError("Sensitive paths are not available.")
        candidate = self._root if raw_path == "." else self._root.joinpath(*relative.parts)
        current = self._root
        if raw_path != ".":
            for part in relative.parts:
                current = current / part
                if current.is_symlink():
                    raise ValueError("Symlink paths are not available.")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(self._root):
            raise ValueError("Path escapes the configured workspace.")
        return resolved

    def _list_directory(self, target: Path, raw_path: str) -> ToolResult:
        if not target.is_dir():
            return ToolResult(success=False, error="Requested path is not a directory.")
        entries = []
        hidden_count = 0
        for item in sorted(target.iterdir(), key=lambda entry: entry.name.casefold()):
            if _is_sensitive_name(item.name) or item.is_symlink():
                hidden_count += 1
                continue
            try:
                mode = item.stat(follow_symlinks=False).st_mode
            except OSError:
                hidden_count += 1
                continue
            if stat.S_ISDIR(mode):
                entries.append({"name": item.name, "type": "directory"})
            elif stat.S_ISREG(mode):
                entries.append({"name": item.name, "type": "file", "size_bytes": mode_size(item)})
            if len(entries) >= _MAX_DIRECTORY_ENTRIES:
                break
        return ToolResult(
            success=True,
            output={
                "path": "." if raw_path == "." else raw_path,
                "entries": entries,
                "truncated": len(entries) >= _MAX_DIRECTORY_ENTRIES,
                "omitted_sensitive_or_symlink_entries": hidden_count,
                "read_only": True,
            },
        )

    def _read_text(self, target: Path, raw_path: str) -> ToolResult:
        if not target.is_file():
            return ToolResult(success=False, error="Requested path is not a regular file.")
        if target.stat().st_size > _MAX_FILE_BYTES:
            return ToolResult(success=False, error="File exceeds the 65536-byte read limit.")
        data = target.read_bytes()
        if len(data) > _MAX_FILE_BYTES:
            return ToolResult(success=False, error="File exceeds the 65536-byte read limit.")
        if b"\x00" in data:
            return ToolResult(success=False, error="Binary files are not available.")
        text = data.decode("utf-8")
        return ToolResult(
            success=True,
            output={
                "path": raw_path,
                "content": text,
                "size_bytes": len(data),
                "read_only": True,
                "untrusted_content": True,
            },
        )


def mode_size(path: Path) -> int:
    """Return file size without following a symlink."""
    return path.stat(follow_symlinks=False).st_size
