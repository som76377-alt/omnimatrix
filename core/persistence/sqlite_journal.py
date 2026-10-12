"""SQLite-backed durable journal primitives for Omnitrix.

This module stores execution evidence; it does not schedule work or authorize
side effects. Callers must still enforce approval and policy before execution.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterator, Mapping


_SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Journal values must be JSON-serializable.") from exc


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value


class SQLiteJournal:
    """Thread-safe SQLite journal with atomic schema initialization.

    A single connection is protected by a re-entrant lock. File-backed journals
    survive process restarts; passing ":memory:" is useful for isolated tests.
    The class deliberately does not claim crash-safe replay semantics yet.
    """

    def __init__(self, path: str | Path) -> None:
        if not isinstance(path, (str, Path)):
            raise TypeError("path must be a string or pathlib.Path.")
        self.path = ":memory:" if str(path) == ":memory:" else str(Path(path).expanduser())
        if self.path != ":memory:":
            Path(self.path).resolve().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.path, timeout=5.0, check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if self.path != ":memory:":
            self._connection.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations "
                    "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                )
                row = self._connection.execute(
                    "SELECT MAX(version) AS version FROM schema_migrations"
                ).fetchone()
                version = row["version"] if row and row["version"] is not None else 0
                if version > _SCHEMA_VERSION:
                    raise RuntimeError("Journal schema is newer than this Omnitrix version.")
                if version < 1:
                    statements = (
                        """CREATE TABLE runs (
                            run_id TEXT PRIMARY KEY,
                            status TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            payload_json TEXT NOT NULL
                        )""",
                        """CREATE TABLE tasks (
                            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                            task_id TEXT NOT NULL,
                            status TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            payload_json TEXT NOT NULL,
                            PRIMARY KEY (run_id, task_id)
                        )""",
                        """CREATE TABLE attempts (
                            attempt_id TEXT PRIMARY KEY,
                            run_id TEXT NOT NULL,
                            task_id TEXT NOT NULL,
                            attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
                            status TEXT NOT NULL,
                            started_at TEXT NOT NULL,
                            finished_at TEXT,
                            payload_json TEXT NOT NULL,
                            FOREIGN KEY (run_id, task_id) REFERENCES tasks(run_id, task_id)
                                ON DELETE CASCADE,
                            UNIQUE (run_id, task_id, attempt_number)
                        )""",
                        """CREATE TABLE events (
                            event_id TEXT PRIMARY KEY,
                            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                            sequence INTEGER NOT NULL CHECK (sequence >= 0),
                            event_type TEXT NOT NULL,
                            timestamp TEXT NOT NULL,
                            task_id TEXT,
                            contract_version INTEGER NOT NULL CHECK (contract_version > 0),
                            payload_json TEXT NOT NULL,
                            UNIQUE (run_id, sequence)
                        )""",
                        """CREATE TABLE approvals (
                            approval_id TEXT PRIMARY KEY,
                            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                            fingerprint TEXT NOT NULL,
                            status TEXT NOT NULL,
                            created_at TEXT NOT NULL,
                            payload_json TEXT NOT NULL
                        )""",
                        """CREATE TABLE artifacts (
                            artifact_id TEXT PRIMARY KEY,
                            run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                            task_id TEXT,
                            uri TEXT NOT NULL,
                            sha256 TEXT,
                            media_type TEXT,
                            created_at TEXT NOT NULL,
                            metadata_json TEXT NOT NULL
                        )""",
                    )
                    for statement in statements:
                        self._connection.execute(statement)
                    self._connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (1, _now()),
                    )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def create_run(
        self, run_id: str, status: str = "created",
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        run_id = _required_text(run_id, "run_id")
        status = _required_text(status, "status")
        timestamp = _now()
        with self._transaction() as db:
            db.execute(
                "INSERT INTO runs(run_id, status, created_at, updated_at, payload_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, status, timestamp, timestamp, _json(dict(payload or {}))),
            )

    def update_run(
        self, run_id: str, status: str, payload: Mapping[str, Any] | None = None
    ) -> None:
        run_id = _required_text(run_id, "run_id")
        status = _required_text(status, "status")
        with self._transaction() as db:
            cursor = db.execute(
                "UPDATE runs SET status = ?, updated_at = ?, payload_json = ? WHERE run_id = ?",
                (status, _now(), _json(dict(payload or {})), run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Unknown run_id: {run_id}")

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run_id = _required_text(run_id, "run_id")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

    def upsert_task(
        self, run_id: str, task_id: str, status: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        run_id = _required_text(run_id, "run_id")
        task_id = _required_text(task_id, "task_id")
        status = _required_text(status, "status")
        with self._transaction() as db:
            db.execute(
                """INSERT INTO tasks(run_id, task_id, status, updated_at, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(run_id, task_id) DO UPDATE SET
                    status=excluded.status, updated_at=excluded.updated_at,
                    payload_json=excluded.payload_json""",
                (run_id, task_id, status, _now(), _json(dict(payload or {}))),
            )

    def record_attempt(
        self, attempt_id: str, run_id: str, task_id: str, attempt_number: int,
        status: str, payload: Mapping[str, Any] | None = None,
        finished_at: str | None = None,
    ) -> None:
        attempt_id = _required_text(attempt_id, "attempt_id")
        run_id = _required_text(run_id, "run_id")
        task_id = _required_text(task_id, "task_id")
        status = _required_text(status, "status")
        if isinstance(attempt_number, bool) or not isinstance(attempt_number, int) or attempt_number < 1:
            raise ValueError("attempt_number must be a positive integer.")
        with self._transaction() as db:
            db.execute(
                """INSERT INTO attempts
                (attempt_id, run_id, task_id, attempt_number, status, started_at, finished_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (attempt_id, run_id, task_id, attempt_number, status, _now(),
                 finished_at, _json(dict(payload or {}))),
            )

    def append_event(self, event: Any) -> None:
        """Persist a validated RunEvent without silently replacing duplicates."""
        required = ("event_id", "run_id", "sequence", "event_type", "timestamp",
                    "payload", "contract_version")
        if any(not hasattr(event, field) for field in required):
            raise TypeError("event must satisfy the RunEvent contract.")
        with self._transaction() as db:
            db.execute(
                """INSERT INTO events
                (event_id, run_id, sequence, event_type, timestamp, task_id,
                 contract_version, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (_required_text(event.event_id, "event_id"),
                 _required_text(event.run_id, "run_id"), event.sequence,
                 _required_text(event.event_type, "event_type"),
                 _required_text(event.timestamp, "timestamp"),
                 getattr(event, "task_id", None), event.contract_version,
                 _json(dict(event.payload))),
            )

    def list_events(self, run_id: str, after_sequence: int = -1) -> list[dict[str, Any]]:
        run_id = _required_text(run_id, "run_id")
        if isinstance(after_sequence, bool) or not isinstance(after_sequence, int) or after_sequence < -1:
            raise ValueError("after_sequence must be an integer greater than or equal to -1.")
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM events WHERE run_id = ? AND sequence > ? ORDER BY sequence",
                (run_id, after_sequence),
            ).fetchall()
        events = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            events.append(item)
        return events

    def save_approval(
        self, approval_id: str, run_id: str, fingerprint: str, status: str,
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        values = (
            _required_text(approval_id, "approval_id"),
            _required_text(run_id, "run_id"),
            _required_text(fingerprint, "fingerprint"),
            _required_text(status, "status"),
            _now(),
            _json(dict(payload or {})),
        )
        with self._transaction() as db:
            db.execute(
                """INSERT INTO approvals
                (approval_id, run_id, fingerprint, status, created_at, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)""", values,
            )

    def register_artifact(
        self, artifact_id: str, run_id: str, uri: str, *,
        task_id: str | None = None, sha256: str | None = None,
        media_type: str | None = None, metadata: Mapping[str, Any] | None = None,
    ) -> None:
        values = (
            _required_text(artifact_id, "artifact_id"),
            _required_text(run_id, "run_id"),
            _required_text(uri, "uri"),
            task_id, sha256, media_type, _now(), _json(dict(metadata or {})),
        )
        with self._transaction() as db:
            db.execute(
                """INSERT INTO artifacts
                (artifact_id, run_id, task_id, uri, sha256, media_type, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", values,
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteJournal":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
