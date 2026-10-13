import tempfile
import unittest
from pathlib import Path

from core.persistence.recovery_service import RecoveryService
from core.persistence.sqlite_journal import SQLiteJournal


class RecoveryServiceTests(unittest.TestCase):
    def test_checkpoint_survives_reopen_and_inspection_never_authorizes_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recovery.sqlite3"
            with SQLiteJournal(path) as journal:
                journal.create_run("run-1", status="running")
                journal.upsert_task("run-1", "task-1", "running")
                journal.record_attempt("attempt-1", "run-1", "task-1", 1, "running")
                journal.save_checkpoint(
                    "run-1", "checkpoint-0", 0, "task_boundary",
                    {"task_id": "task-1", "completed": []},
                )
            with SQLiteJournal(path) as reopened:
                inspection = RecoveryService(reopened).inspect("run-1")
                self.assertEqual(inspection.decision.disposition, "revalidation_required")
                self.assertEqual(inspection.checkpoint_count, 1)
                self.assertEqual(inspection.latest_checkpoint_id, "checkpoint-0")
                self.assertEqual(inspection.integrity_errors, ())
                self.assertFalse(inspection.can_auto_resume)
                self.assertFalse(inspection.to_dict()["can_auto_resume"])

    def test_checkpoint_payload_digest_mismatch_blocks_recovery(self):
        with SQLiteJournal(":memory:") as journal:
            journal.create_run("run-1", status="running")
            journal.save_checkpoint("run-1", "checkpoint-0", 0, "task_boundary", {"step": 1})
            with journal._transaction() as db:
                db.execute(
                    "UPDATE checkpoints SET payload_json = ? WHERE checkpoint_id = ?",
                    ('{"step":2}', "checkpoint-0"),
                )
            inspection = RecoveryService(journal).inspect("run-1")
            self.assertEqual(inspection.decision.disposition, "blocked_unknown_state")
            self.assertTrue(any("digest mismatch" in error for error in inspection.integrity_errors))
            self.assertFalse(inspection.can_auto_resume)

    def test_checkpoint_sequence_gap_blocks_recovery(self):
        with SQLiteJournal(":memory:") as journal:
            journal.create_run("run-1", status="running")
            journal.save_checkpoint("run-1", "checkpoint-0", 0, "task_boundary", {"step": 0})
            journal.save_checkpoint("run-1", "checkpoint-2", 2, "task_boundary", {"step": 2})
            inspection = RecoveryService(journal).inspect("run-1")
            self.assertEqual(inspection.decision.disposition, "blocked_unknown_state")
            self.assertTrue(any("sequence gap" in error for error in inspection.integrity_errors))

    def test_attempt_referring_to_missing_task_blocks_recovery(self):
        with SQLiteJournal(":memory:") as journal:
            journal.create_run("run-1", status="running")
            # Simulate a malformed legacy/manual database edit that bypassed FK checks.
            journal._connection.execute("PRAGMA foreign_keys = OFF")
            with journal._transaction() as db:
                db.execute(
                    """INSERT INTO tasks(run_id, task_id, status, updated_at, payload_json)
                       VALUES ('run-1', 'task-1', 'running', 'now', '{}')"""
                )
                db.execute(
                    """INSERT INTO attempts
                       (attempt_id, run_id, task_id, attempt_number, status, started_at, finished_at, payload_json)
                       VALUES ('attempt-1', 'run-1', 'missing-task', 1, 'running', 'now', NULL, '{}')"""
                )
            inspection = RecoveryService(journal).inspect("run-1")
            self.assertEqual(inspection.decision.disposition, "blocked_unknown_state")
            self.assertTrue(any("unknown task" in error for error in inspection.integrity_errors))

    def test_missing_run_is_reported_without_auto_resume(self):
        with SQLiteJournal(":memory:") as journal:
            inspection = RecoveryService(journal).inspect("missing-run")
            self.assertEqual(inspection.decision.disposition, "not_found")
            self.assertFalse(inspection.can_auto_resume)


if __name__ == "__main__":
    unittest.main()
