import os
import tempfile
import unittest
from pathlib import Path

from core.models.base import ModelResponse
from core.models.messages import MessageRole, ModelMessage, ModelRequest
from core.persistence.model_state_snapshots import (
    ModelStateSnapshotError,
    ModelStateSnapshotStore,
)
from core.persistence.sqlite_journal import SQLiteJournal


class ModelStateSnapshotStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "snapshots.sqlite3"
        self.journal = SQLiteJournal(self.db_path)
        self.journal.create_run("run-1", status="running")
        self.journal.upsert_task("run-1", "task-1", "running")
        self.journal.record_attempt("attempt-1", "run-1", "task-1", 1, "running")
        self.key = os.urandom(32)
        self.request = ModelRequest(
            instructions="Keep this private prompt encrypted.",
            messages=(ModelMessage(MessageRole.USER, "private request text"),),
        )
        self.response = ModelResponse(
            content="private response text", model="test-model", provider="test",
        )

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def store(self, **kwargs):
        return ModelStateSnapshotStore(
            self.journal, enabled=True, encryption_key=self.key, **kwargs
        )

    def test_persistence_is_disabled_by_default(self):
        store = ModelStateSnapshotStore(self.journal)
        self.assertFalse(store.enabled)
        with self.assertRaisesRegex(ModelStateSnapshotError, "disabled"):
            store.save_pair("run-1", "task-1", "attempt-1", 0, self.request, self.response)

    def test_opt_in_requires_external_32_byte_key(self):
        with self.assertRaisesRegex(ModelStateSnapshotError, "32-byte"):
            ModelStateSnapshotStore(self.journal, enabled=True, encryption_key=b"short")

    def test_pair_survives_database_reopen_and_round_trips(self):
        snapshot_id = self.store().save_pair(
            "run-1", "task-1", "attempt-1", 0, self.request, self.response
        )
        self.journal.close()
        self.journal = SQLiteJournal(self.db_path)
        request, response = self.store().load_pair(snapshot_id)
        self.assertEqual(request, self.request)
        self.assertEqual(response, self.response)

    def test_sqlite_contains_ciphertext_not_model_content(self):
        snapshot_id = self.store().save_pair(
            "run-1", "task-1", "attempt-1", 0, self.request, self.response
        )
        row = self.journal.get_encrypted_model_state_snapshot(snapshot_id)
        self.assertIsNotNone(row)
        self.assertNotIn(b"private request text", row["ciphertext"])
        self.assertNotIn(b"private response text", row["ciphertext"])
        self.assertNotIn("encryption_key", row)

    def test_wrong_key_and_wrong_key_id_fail_closed(self):
        snapshot_id = self.store().save_pair(
            "run-1", "task-1", "attempt-1", 0, self.request, self.response
        )
        wrong_key = ModelStateSnapshotStore(
            self.journal, enabled=True, encryption_key=os.urandom(32)
        )
        with self.assertRaisesRegex(ModelStateSnapshotError, "authentication failed"):
            wrong_key.load_pair(snapshot_id)
        wrong_id = ModelStateSnapshotStore(
            self.journal, enabled=True, encryption_key=self.key, key_id="other-key"
        )
        with self.assertRaisesRegex(ModelStateSnapshotError, "identifier"):
            wrong_id.load_pair(snapshot_id)

    def test_ciphertext_tampering_fails_authentication(self):
        snapshot_id = self.store().save_pair(
            "run-1", "task-1", "attempt-1", 0, self.request, self.response
        )
        row = self.journal.get_encrypted_model_state_snapshot(snapshot_id)
        corrupted = bytes([row["ciphertext"][0] ^ 1]) + row["ciphertext"][1:]
        with self.journal._transaction() as db:
            db.execute(
                "UPDATE model_state_snapshots SET ciphertext = ? WHERE snapshot_id = ?",
                (corrupted, snapshot_id),
            )
        with self.assertRaisesRegex(ModelStateSnapshotError, "authentication failed"):
            self.store().load_pair(snapshot_id)

    def test_identity_must_match_persisted_attempt(self):
        with self.assertRaisesRegex(ValueError, "identity does not match"):
            self.store().save_pair(
                "run-1", "task-1", "missing-attempt", 0, self.request, self.response
            )

    def test_duplicate_interaction_sequence_is_rejected(self):
        store = self.store()
        store.save_pair("run-1", "task-1", "attempt-1", 0, self.request, self.response)
        with self.assertRaises(Exception):
            store.save_pair("run-1", "task-1", "attempt-1", 0, self.request, self.response)

    def test_explicit_delete_removes_sensitive_snapshot(self):
        store = self.store()
        snapshot_id = store.save_pair(
            "run-1", "task-1", "attempt-1", 0, self.request, self.response
        )
        self.assertTrue(store.delete(snapshot_id))
        self.assertFalse(store.delete(snapshot_id))
        with self.assertRaisesRegex(KeyError, "Unknown model-state snapshot"):
            store.load_pair(snapshot_id)


if __name__ == "__main__":
    unittest.main()
