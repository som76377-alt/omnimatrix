import tempfile
import unittest
from pathlib import Path

from core.persistence.recovery_service import RecoveryService
from core.persistence.snapshot_recovery_preflight import inspect_snapshot_preflight, SnapshotRecoveryGateError
from core.persistence.sqlite_journal import SQLiteJournal


class SnapshotRecoveryPreflightTests(unittest.TestCase):
    def test_missing_snapshot_is_blocked_before_any_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = SQLiteJournal(Path(directory) / "journal.sqlite3")
            try:
                journal.create_run("run-1", status="running")
                journal.upsert_task("run-1", "task-1", "running")
                journal.record_attempt("attempt-1", "run-1", "task-1", 1, "running")
                service = RecoveryService(journal)
                with self.assertRaisesRegex(SnapshotRecoveryGateError, "missing"):
                    inspect_snapshot_preflight(
                        journal, service, "missing-snapshot",
                        expected_run_id="run-1",
                        expected_task_id="task-1",
                        expected_attempt_id="attempt-1",
                    )
            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()
