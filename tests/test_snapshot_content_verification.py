import os
import tempfile
import unittest
from pathlib import Path

from core.models.base import ModelResponse
from core.models.messages import MessageRole, ModelMessage, ModelRequest
from core.persistence.model_state import (
    model_request_transcript_sha256,
    model_response_transcript_sha256,
)
from core.persistence.model_state_snapshots import ModelStateSnapshotStore
from core.persistence.snapshot_content_verification import verify_snapshot_content_hashes
from core.persistence.snapshot_recovery_gate import SnapshotRecoveryGateError
from core.persistence.sqlite_journal import SQLiteJournal


class SnapshotContentVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.journal = SQLiteJournal(Path(self.temp.name) / "journal.sqlite3")
        self.journal.create_run("run-1", status="running")
        self.journal.upsert_task("run-1", "task-1", "running")
        self.journal.record_attempt("attempt-1", "run-1", "task-1", 1, "running")
        self.key = os.urandom(32)
        self.store = ModelStateSnapshotStore(
            self.journal, enabled=True, encryption_key=self.key
        )
        self.request = ModelRequest(
            instructions="System instructions",
            messages=(ModelMessage(MessageRole.USER, "private prompt"),),
        )
        self.response = ModelResponse(
            content="private answer", model="test-model", provider="test",
        )
        self.snapshot_id = self.store.save_pair(
            "run-1", "task-1", "attempt-1", 0, self.request, self.response
        )

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def test_decrypted_pair_matches_transcript_hashes(self):
        result = verify_snapshot_content_hashes(
            snapshot_store=self.store,
            snapshot_id=self.snapshot_id,
            expected_request_sha256=model_request_transcript_sha256(self.request),
            expected_response_sha256=model_response_transcript_sha256(self.response),
        )
        self.assertTrue(result["content_hashes_verified"])
        self.assertTrue(result["request_sha256_verified"])
        self.assertTrue(result["response_sha256_verified"])

    def test_wrong_request_hash_is_rejected(self):
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "request hash"):
            verify_snapshot_content_hashes(
                snapshot_store=self.store,
                snapshot_id=self.snapshot_id,
                expected_request_sha256="0" * 64,
                expected_response_sha256=model_response_transcript_sha256(self.response),
            )

    def test_wrong_response_hash_is_rejected(self):
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "response hash"):
            verify_snapshot_content_hashes(
                snapshot_store=self.store,
                snapshot_id=self.snapshot_id,
                expected_request_sha256=model_request_transcript_sha256(self.request),
                expected_response_sha256="0" * 64,
            )

    def test_invalid_digest_is_rejected(self):
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "valid SHA-256"):
            verify_snapshot_content_hashes(
                snapshot_store=self.store,
                snapshot_id=self.snapshot_id,
                expected_request_sha256="not-a-digest",
                expected_response_sha256=model_response_transcript_sha256(self.response),
            )


if __name__ == "__main__":
    unittest.main()
