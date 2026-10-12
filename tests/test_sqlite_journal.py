import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.contracts import RunEvent
from core.persistence.sqlite_journal import SQLiteJournal


class SQLiteJournalTests(unittest.TestCase):
    def test_run_task_attempt_event_and_artifact_survive_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "omnitrix.sqlite3"
            event = RunEvent(
                event_id="event-1",
                run_id="run-1",
                sequence=0,
                event_type="run_created",
                timestamp=datetime.now(timezone.utc).isoformat(),
                payload={"source": "test", "trusted": False},
            )
            with SQLiteJournal(path) as journal:
                journal.create_run("run-1", payload={"objective": "test"})
                journal.upsert_task("run-1", "task-1", "pending", {"title": "sample"})
                journal.record_attempt(
                    "attempt-1", "run-1", "task-1", 1, "started",
                    {"retryable": False},
                )
                journal.append_event(event)
                journal.save_approval(
                    "approval-1", "run-1", "fingerprint-1", "approved",
                    {"explicit_confirmation": True},
                )
                journal.register_artifact(
                    "artifact-1", "run-1", "artifacts/result.txt",
                    task_id="task-1", sha256="abc123", media_type="text/plain",
                )

            with SQLiteJournal(path) as reopened:
                run = reopened.get_run("run-1")
                self.assertEqual(run["status"], "created")
                self.assertEqual(run["payload"]["objective"], "test")
                events = reopened.list_events("run-1")
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["event_type"], "run_created")
                self.assertEqual(events[0]["payload"]["trusted"], False)

    def test_duplicate_event_sequence_is_rejected_without_overwrite(self):
        with SQLiteJournal(":memory:") as journal:
            journal.create_run("run-1")
            now = datetime.now(timezone.utc).isoformat()
            first = RunEvent("event-1", "run-1", 0, "started", now, {"n": 1})
            second = RunEvent("event-2", "run-1", 0, "finished", now, {"n": 2})
            journal.append_event(first)
            with self.assertRaises(sqlite3.IntegrityError):
                journal.append_event(second)
            events = journal.list_events("run-1")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_id"], "event-1")

    def test_attempt_can_be_finished_once_and_survives_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attempts.sqlite3"
            with SQLiteJournal(path) as journal:
                journal.create_run("run-1")
                journal.upsert_task("run-1", "task-1", "running")
                journal.record_attempt("attempt-1", "run-1", "task-1", 1, "running")
                journal.finish_attempt("attempt-1", "failed", {"error_type": "RuntimeError"})
                with self.assertRaises(RuntimeError):
                    journal.finish_attempt("attempt-1", "completed")
            with SQLiteJournal(path) as journal:
                with sqlite3.connect(path) as database:
                    row = database.execute(
                        "SELECT status, finished_at, payload_json FROM attempts WHERE attempt_id = ?",
                        ("attempt-1",),
                    ).fetchone()
                self.assertEqual(row[0], "failed")
                self.assertIsNotNone(row[1])
                self.assertIn("RuntimeError", row[2])

    def test_unknown_run_cannot_be_updated(self):
        with SQLiteJournal(":memory:") as journal:
            with self.assertRaises(KeyError):
                journal.update_run("missing", "running")

    def test_foreign_key_rejects_task_without_run(self):
        with SQLiteJournal(":memory:") as journal:
            with self.assertRaises(sqlite3.IntegrityError):
                journal.upsert_task("missing-run", "task-1", "pending")

    def test_json_payload_must_be_serializable(self):
        with SQLiteJournal(":memory:") as journal:
            with self.assertRaises(ValueError):
                journal.create_run("run-1", payload={"not_json": object()})

    def test_event_replay_cursor_returns_strictly_later_sequences(self):
        with SQLiteJournal(":memory:") as journal:
            journal.create_run("run-1")
            now = datetime.now(timezone.utc).isoformat()
            for sequence in range(3):
                journal.append_event(
                    RunEvent(
                        f"event-{sequence}", "run-1", sequence, "progress", now,
                        {"sequence": sequence},
                    )
                )
            self.assertEqual(
                [event["sequence"] for event in journal.list_events("run-1", after_sequence=0)],
                [1, 2],
            )


if __name__ == "__main__":
    unittest.main()
