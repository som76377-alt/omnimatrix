import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.models.base import ModelResponse
from core.models.adapters import AdapterRegistry
from core.models.providers.demo import DemoAdapter
from core.models.messages import MessageRole, ModelMessage, ModelRequest
from core.persistence.model_state_snapshots import ModelStateSnapshotStore
from core.persistence.recovery_service import RecoveryService
from core.persistence.snapshot_recovery_gate import SnapshotRecoveryGateError
from core.persistence.sqlite_journal import SQLiteJournal
from core.persistence.verified_snapshot_restore import reconstruct_verified_snapshot_pair


class VerifiedSnapshotReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.journal = SQLiteJournal(Path(self.temp.name) / "journal.sqlite3")
        self.journal.create_run("run-1", status="running")
        self.journal.upsert_task("run-1", "task-1", "running")
        self.journal.record_attempt("attempt-1", "run-1", "task-1", 1, "running")
        self.store = ModelStateSnapshotStore(
            self.journal, enabled=True, encryption_key=os.urandom(32)
        )
        self.request = ModelRequest(
            instructions="Safe test instructions",
            messages=(ModelMessage(MessageRole.USER, "test prompt"),),
        )
        self.response = ModelResponse(
            content="test response", provider="demo", model="demo-v1"
        )
        self.snapshot_id = self.store.save_pair(
            "run-1", "task-1", "attempt-1", 0, self.request, self.response
        )
        self.registry = AdapterRegistry()
        self.adapter = DemoAdapter(name="demo-offline", model_id="demo-v1")
        self.registry.register(self.adapter)
        self.service = RecoveryService(self.journal)
        self.evidence = {
            "snapshot_id": self.snapshot_id,
            "run_id": "run-1",
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "interaction_sequence": 0,
            "provider": "demo",
            "model": "demo-v1",
            "transcript_correlation": {"content_hashes_verified": True},
            "provider_continuation_compatibility": {
                "checked": True,
                "provider_compatible": True,
                "continuation_state_present": False,
                "continuation_state_compatible": None,
                "restore_ready": False,
            },
            "can_auto_resume": False,
        }

    def tearDown(self):
        self.journal.close()
        self.temp.cleanup()

    def reconstruct(self, evidence=None):
        with patch(
            "core.persistence.verified_snapshot_restore.inspect_snapshot_preflight",
            return_value=evidence if evidence is not None else self.evidence,
        ):
            return reconstruct_verified_snapshot_pair(
                self.journal,
                self.service,
                self.store,
                self.registry,
                self.snapshot_id,
                expected_run_id="run-1",
                expected_task_id="task-1",
                expected_attempt_id="attempt-1",
            )

    def test_reconstructs_typed_pair_but_never_authorizes_execution(self):
        restored = self.reconstruct()
        self.assertEqual(restored.request, self.request)
        self.assertEqual(restored.response, self.response)
        self.assertEqual(restored.interaction_sequence, 0)
        self.assertFalse(restored.execution_authorized)
        self.assertFalse(restored.preflight["can_auto_resume"])

    def test_unverified_content_is_blocked(self):
        evidence = {
            **self.evidence,
            "transcript_correlation": {"content_hashes_verified": False},
        }
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "content hashes"):
            self.reconstruct(evidence)

    def test_unknown_or_unchecked_provider_is_blocked(self):
        evidence = {
            **self.evidence,
            "provider_continuation_compatibility": {
                "checked": False,
                "provider_compatible": False,
                "restore_ready": False,
            },
        }
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "not checked"):
            self.reconstruct(evidence)

    def test_provider_incompatibility_is_blocked(self):
        evidence = {
            **self.evidence,
            "provider_continuation_compatibility": {
                "checked": True,
                "provider_compatible": False,
                "continuation_state_present": False,
                "continuation_state_compatible": None,
                "restore_ready": False,
            },
        }
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "No unique compatible"):
            self.reconstruct(evidence)

    def test_identity_mismatch_is_blocked(self):
        evidence = {**self.evidence, "attempt_id": "other-attempt"}
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "attempt_id"):
            self.reconstruct(evidence)

    def test_disabled_snapshot_store_is_blocked(self):
        disabled = ModelStateSnapshotStore(self.journal)
        with patch(
            "core.persistence.verified_snapshot_restore.inspect_snapshot_preflight",
            return_value=self.evidence,
        ):
            with self.assertRaisesRegex(SnapshotRecoveryGateError, "must be enabled"):
                reconstruct_verified_snapshot_pair(
                    self.journal,
                    self.service,
                    disabled,
                    self.registry,
                    self.snapshot_id,
                    expected_run_id="run-1",
                    expected_task_id="task-1",
                    expected_attempt_id="attempt-1",
                )


if __name__ == "__main__":
    unittest.main()
