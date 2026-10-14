import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from core.models.base import ModelResponse
from core.models.adapters import AdapterRegistry
from core.models.providers.demo import DemoAdapter
from core.models.messages import MessageRole, ModelMessage, ModelRequest
from core.persistence.model_state import model_request_transcript_sha256, model_response_transcript_sha256
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

    def test_real_preflight_reconstructs_pair_after_transcript_and_checkpoint_verification(self):
        request_digest = model_request_transcript_sha256(self.request)
        response_digest = model_response_transcript_sha256(self.response)
        self.journal.append_model_transcript_record(
            "run-1", 0, "model_request",
            task_id="task-1", attempt_id="attempt-1",
            provider="demo", model="demo-adapter-alias",
            request_sha256=request_digest,
        )
        self.journal.append_model_transcript_record(
            "run-1", 1, "model_response",
            task_id="task-1", attempt_id="attempt-1",
            provider="demo", model="demo-v1",
            request_sha256=request_digest, response_sha256=response_digest,
        )
        self.journal.save_checkpoint(
            "run-1", "checkpoint-0", 0, "task_started",
            {"task_id": "task-1", "attempt_id": "attempt-1"},
        )
        self.journal.save_checkpoint(
            "run-1", "checkpoint-1", 1, "model_request_started",
            {"task_id": "task-1", "attempt_id": "attempt-1", "model_name": "demo-adapter-alias"},
        )
        self.journal.save_checkpoint(
            "run-1", "checkpoint-2", 2, "model_response_received",
            {"task_id": "task-1", "attempt_id": "attempt-1", "model_name": "demo-v1"},
        )

        restored = reconstruct_verified_snapshot_pair(
            self.journal,
            self.service,
            self.store,
            self.registry,
            self.snapshot_id,
            expected_run_id="run-1",
            expected_task_id="task-1",
            expected_attempt_id="attempt-1",
        )
        self.assertEqual(restored.request, self.request)
        self.assertEqual(restored.response, self.response)
        self.assertTrue(restored.preflight["transcript_correlation"]["content_hashes_verified"])
        self.assertTrue(
            restored.preflight["provider_continuation_compatibility"]["provider_compatible"]
        )
        self.assertFalse(restored.execution_authorized)

    def test_subprocess_crash_reopen_and_verified_reconstruction(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "crash-recovery.sqlite3"
            key = os.urandom(32)
            script = textwrap.dedent(
                """
                import os
                import sys
                from core.models.base import ModelResponse
                from core.models.messages import MessageRole, ModelMessage, ModelRequest
                from core.persistence.model_state import (
                    model_request_transcript_sha256, model_response_transcript_sha256,
                )
                from core.persistence.model_state_snapshots import ModelStateSnapshotStore
                from core.persistence.sqlite_journal import SQLiteJournal

                journal = SQLiteJournal(sys.argv[1])
                journal.create_run("run-crash", status="running")
                journal.upsert_task("run-crash", "task-crash", "running")
                journal.record_attempt("attempt-crash", "run-crash", "task-crash", 1, "running")
                request = ModelRequest(
                    instructions="Crash recovery test",
                    messages=(ModelMessage(MessageRole.USER, "durable test prompt"),),
                )
                response = ModelResponse(
                    content="durable test response", provider="demo", model="demo-v1",
                )
                request_digest = model_request_transcript_sha256(request)
                response_digest = model_response_transcript_sha256(response)
                journal.append_model_transcript_record(
                    "run-crash", 0, "model_request",
                    task_id="task-crash", attempt_id="attempt-crash",
                    provider="demo", model="demo-adapter-alias",
                    request_sha256=request_digest,
                )
                journal.append_model_transcript_record(
                    "run-crash", 1, "model_response",
                    task_id="task-crash", attempt_id="attempt-crash",
                    provider="demo", model="demo-v1",
                    request_sha256=request_digest, response_sha256=response_digest,
                )
                journal.save_checkpoint(
                    "run-crash", "checkpoint-0", 0, "task_started",
                    {"task_id": "task-crash", "attempt_id": "attempt-crash"},
                )
                journal.save_checkpoint(
                    "run-crash", "checkpoint-1", 1, "model_request_started",
                    {"task_id": "task-crash", "attempt_id": "attempt-crash"},
                )
                journal.save_checkpoint(
                    "run-crash", "checkpoint-2", 2, "model_response_received",
                    {"task_id": "task-crash", "attempt_id": "attempt-crash"},
                )
                store = ModelStateSnapshotStore(
                    journal, enabled=True, encryption_key=bytes.fromhex(sys.argv[2]),
                )
                store.save_pair(
                    "run-crash", "task-crash", "attempt-crash", 0, request, response,
                )
                os._exit(73)
                """
            )
            crashed = subprocess.run(
                [sys.executable, "-c", script, str(database_path), key.hex()],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(crashed.returncode, 73, crashed.stderr)

            with SQLiteJournal(database_path) as reopened:
                metadata = reopened.list_model_state_snapshot_metadata("run-crash")
                self.assertEqual(len(metadata), 1)
                registry = AdapterRegistry()
                registry.register(DemoAdapter(name="demo-offline", model_id="demo-v1"))
                restored = reconstruct_verified_snapshot_pair(
                    reopened,
                    RecoveryService(reopened),
                    ModelStateSnapshotStore(
                        reopened, enabled=True, encryption_key=key,
                    ),
                    registry,
                    metadata[0]["snapshot_id"],
                    expected_run_id="run-crash",
                    expected_task_id="task-crash",
                    expected_attempt_id="attempt-crash",
                )
                self.assertEqual(
                    restored.request.messages[0].content, "durable test prompt"
                )
                self.assertEqual(restored.response.content, "durable test response")
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
