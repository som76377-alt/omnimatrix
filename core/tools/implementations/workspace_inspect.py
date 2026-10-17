"""Read-only workspace inspection using pinned, no-follow directory handles."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import re
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
_CREDENTIAL_PATTERN = re.compile(
    r"(^|[._-])(secrets?|credentials?|tokens?|api[-_]?keys?|private[-_]?keys?)([._-]|$)"
)


def supports_secure_workspace_inspection() -> bool:
    """Return whether this OS exposes descriptor-relative no-follow primitives."""
    return bool(
        getattr(os, "O_DIRECTORY", 0)
        and getattr(os, "O_NOFOLLOW", 0)
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.listdir in os.supports_fd
    )


def _is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith(".")
        or lowered in _DENIED_NAMES
        or lowered.startswith((".env", "id_rsa", "id_ed25519"))
        or _CREDENTIAL_PATTERN.search(lowered) is not None
        or lowered.endswith(tuple(_DENIED_SUFFIXES))
    )


class WorkspaceInspectTool(Tool):
    """List one directory or read a bounded UTF-8 file under a pinned root.

    This implementation requires OS support for directory-relative opens and
    O_NOFOLLOW. It deliberately fails closed instead of falling back to a
    path-check-then-open sequence that is vulnerable to symlink races.
    """

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        root = Path.cwd() if workspace_root is None else Path(workspace_root)
        self._root = root.expanduser().resolve(strict=True)
        if not self._root.is_dir():
            raise ValueError("Workspace root must be an existing directory.")

        directory_flag = getattr(os, "O_DIRECTORY", 0)
        nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
        if not supports_secure_workspace_inspection():
            raise RuntimeError(
                "Secure workspace inspection requires directory-relative "
                "open/stat/listdir support and O_NOFOLLOW on this operating system."
            )

        self._closed = False
        self._root_fd = self._open_root_handle(
            self._root, directory_flag, nofollow_flag
        )
        if not stat.S_ISDIR(os.fstat(self._root_fd).st_mode):
            os.close(self._root_fd)
            self._closed = True
            raise ValueError("Workspace root must be an existing directory.")

    @staticmethod
    def _open_root_handle(
        root: Path, directory_flag: int, nofollow_flag: int
    ) -> int:
        """Open the canonical root from '/' without following any path component."""
        current_fd = os.open(
            os.path.sep,
            os.O_RDONLY | directory_flag | nofollow_flag,
        )
        try:
            for part in root.parts[1:]:
                next_fd = os.open(
                    part,
                    os.O_RDONLY | directory_flag | nofollow_flag,
                    dir_fd=current_fd,
                )
                os.close(current_fd)
                current_fd = next_fd
            return current_fd
        except Exception:
            os.close(current_fd)
            raise

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

    def close(self) -> None:
        """Release the pinned root directory handle."""
        if not self._closed:
            os.close(self._root_fd)
            self._closed = True

    def __del__(self) -> None:
        try:
            self.close()
        except (AttributeError, OSError):
            pass

    def execute(self, **kwargs: Any) -> ToolResult:
        operation = kwargs.get("operation")
        raw_path = kwargs.get("path")
        try:
            parts = self._path_parts(raw_path)
            if operation == "list":
                return self._list_directory(parts, raw_path)
            if operation == "read":
                return self._read_text(parts, raw_path)
            return ToolResult(success=False, error="Unsupported workspace operation.")
        except (OSError, UnicodeError, ValueError) as exc:
            return ToolResult(
                success=False,
                error=f"Workspace inspection refused ({type(exc).__name__}).",
            )

    def _path_parts(self, raw_path: object) -> tuple[str, ...]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("Path must be a non-empty workspace-relative string.")
        if "\\" in raw_path or raw_path.startswith("/"):
            raise ValueError("Absolute paths and backslashes are not accepted.")
        if raw_path == ".":
            return ()
        relative = PurePosixPath(raw_path)
        if relative.is_absolute() or any(part in {"..", ""} for part in relative.parts):
            raise ValueError("Path traversal is not allowed.")
        if any(part in {".", ".."} for part in raw_path.split("/")):
            raise ValueError("Explicit dot path components are not accepted.")
        if any(_is_sensitive_name(part) for part in relative.parts):
            raise ValueError("Sensitive paths are not available.")
        return relative.parts

    def _open_directory(self, parts: tuple[str, ...]) -> int:
        """Open each directory relative to the previous pinned handle."""
        directory_flag = os.O_DIRECTORY
        nofollow_flag = os.O_NOFOLLOW
        current_fd = os.dup(self._root_fd)
        try:
            for part in parts:
                next_fd = os.open(
                    part,
                    os.O_RDONLY | directory_flag | nofollow_flag,
                    dir_fd=current_fd,
                )
                os.close(current_fd)
                current_fd = next_fd
            return current_fd
        except Exception:
            os.close(current_fd)
            raise

    def _list_directory(self, parts: tuple[str, ...], raw_path: str) -> ToolResult:
        directory_fd = self._open_directory(parts)
        try:
            entries: list[dict[str, Any]] = []
            omitted = 0
            names = sorted(os.listdir(directory_fd), key=str.casefold)
            for name in names:
                if _is_sensitive_name(name):
                    omitted += 1
                    continue
                try:
                    info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError:
                    omitted += 1
                    continue
                if stat.S_ISLNK(info.st_mode):
                    omitted += 1
                    continue
                if stat.S_ISDIR(info.st_mode):
                    entries.append({"name": name, "type": "directory"})
                elif stat.S_ISREG(info.st_mode):
                    entries.append({
                        "name": name,
                        "type": "file",
                        "size_bytes": info.st_size,
                    })
                if len(entries) >= _MAX_DIRECTORY_ENTRIES:
                    break
            return ToolResult(
                success=True,
                output={
                    "path": "." if raw_path == "." else raw_path,
                    "entries": entries,
                    "truncated": len(entries) >= _MAX_DIRECTORY_ENTRIES,
                    "omitted_sensitive_or_symlink_entries": omitted,
                    "read_only": True,
                },
            )
        finally:
            os.close(directory_fd)

    def _read_text(self, parts: tuple[str, ...], raw_path: str) -> ToolResult:
        if not parts:
            return ToolResult(success=False, error="Requested path is not a regular file.")

        parent_fd = self._open_directory(parts[:-1])
        file_fd = None
        try:
            file_fd = os.open(
                parts[-1],
                os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
                dir_fd=parent_fd,
            )
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode):
                return ToolResult(
                    success=False,
                    error="Requested path is not a regular file.",
                )
            if info.st_size > _MAX_FILE_BYTES:
                return ToolResult(
                    success=False,
                    error="File exceeds the 65536-byte read limit.",
                )

            chunks: list[bytes] = []
            remaining = _MAX_FILE_BYTES + 1
            while remaining:
                chunk = os.read(file_fd, min(8192, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > _MAX_FILE_BYTES:
                return ToolResult(
                    success=False,
                    error="File exceeds the 65536-byte read limit.",
                )
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
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(parent_fd)
