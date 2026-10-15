import unittest

from core.persistence.recovery_inventory import inspect_recovery_inventory
from core.persistence.recovery_service import RecoveryService
from core.persistence.sqlite_journal import SQLiteJournal


class RecoveryInventoryTests(unittest.TestCase):
    def setUp(self):
        self.journal = SQLiteJournal(":memory:")
        self.journal.create_run("run-1", status="running")
        self.journal.upsert_task("run-1", "task-1", "running")
        self.journal.record_attempt("attempt-1", "run-1", "task-1", 1, "running")
        self.recovery = RecoveryService(self.journal)

    def tearDown(self):
        self.journal.close()

    def inventory(self, **kwargs):
        return inspect_recovery_inventory(
            self.journal, self.recovery, "run-1", **kwargs
        )

    def test_inventory_never_authorizes_resume_and_does_not_expose_approval_payload(self):
        self.journal.save_approval(
            "approval-1", "run-1", "plan-fingerprint", "approved",
            {"secret_like_payload": "must not appear in inventory"},
        )
        result = self.inventory()
        self.assertFalse(result["can_auto_resume"])
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["disposition"], "manual_revalidation_required")
        self.assertTrue(result["approvals"][0]["requires_revalidation"])
        self.assertNotIn("secret_like_payload", repr(result))

    def test_running_tool_execution_blocks_inventory(self):
        self.journal.begin_tool_execution(
            "execution-1", "idempotency-1", "external_tool", "a" * 64,
            run_id="run-1", task_id="task-1", attempt_id="attempt-1",
            logical_action_id="action-1",
        )
        result = self.inventory()
        self.assertEqual(result["disposition"], "blocked_unknown_state")
        self.assertIn(
            "tool_execution_uncertain",
            {item["code"] for item in result["findings"]},
        )

    def test_successful_tool_without_result_checkpoint_blocks_inventory(self):
        self.journal.begin_tool_execution(
            "execution-1", "idempotency-1", "external_tool", "a" * 64,
            run_id="run-1", task_id="task-1", attempt_id="attempt-1",
            logical_action_id="action-1",
        )
        self.journal.finish_tool_execution("execution-1", "succeeded", {"success": True})
        result = self.inventory()
        self.assertEqual(result["disposition"], "blocked_unknown_state")
        self.assertIn(
            "tool_result_checkpoint_missing",
            {item["code"] for item in result["findings"]},
        )
        self.assertNotIn("success", repr(result["tool_executions"]))

    def test_unknown_tool_execution_status_blocks_inventory(self):
        self.journal.begin_tool_execution(
            "execution-1", "idempotency-1", "external_tool", "a" * 64,
            run_id="run-1", task_id="task-1", attempt_id="attempt-1",
            logical_action_id="action-1",
        )
        self.journal.finish_tool_execution("execution-1", "mystery_status", {"ignored": True})
        result = self.inventory()
        self.assertEqual(result["disposition"], "blocked_unknown_state")
        self.assertIn(
            "tool_execution_uncertain",
            {item["code"] for item in result["findings"]},
        )

    def test_orphan_result_checkpoint_blocks_inventory(self):
        self.journal.save_checkpoint(
            "run-1", "checkpoint-0", 0, "tool_call_result_received",
            {"logical_action_id": "action-without-execution", "task_id": "task-1", "attempt_id": "attempt-1"},
        )
        result = self.inventory()
        self.assertEqual(result["disposition"], "blocked_unknown_state")
        self.assertIn(
            "orphan_tool_result_checkpoint",
            {item["code"] for item in result["findings"]},
        )

    def test_failed_tool_execution_requires_manual_review_even_with_result_checkpoint(self):
        self.journal.save_checkpoint(
            "run-1", "checkpoint-0", 0, "tool_call_prepared",
            {"logical_action_id": "action-1", "task_id": "task-1", "attempt_id": "attempt-1"},
        )
        self.journal.begin_tool_execution(
            "execution-1", "idempotency-1", "external_tool", "a" * 64,
            run_id="run-1", task_id="task-1", attempt_id="attempt-1",
            logical_action_id="action-1",
        )
        self.journal.finish_tool_execution("execution-1", "failed", {"error": "private"})
        self.journal.save_checkpoint(
            "run-1", "checkpoint-1", 1, "tool_call_result_received",
            {"logical_action_id": "action-1", "task_id": "task-1", "attempt_id": "attempt-1"},
        )
        result = self.inventory()
        self.assertEqual(result["disposition"], "manual_revalidation_required")
        self.assertIn(
            "tool_failure_requires_review",
            {item["code"] for item in result["findings"]},
        )
        self.assertNotIn("private", repr(result["tool_executions"]))

    def test_snapshot_from_older_attempt_is_blocked(self):
        self.journal.save_encrypted_model_state_snapshot(
            run_id="run-1", task_id="task-1", attempt_id="attempt-1",
            interaction_sequence=0, provider="demo", model="demo-v1", key_id="key-1",
            nonce=b"0" * 12, ciphertext=b"c" * 32, payload_sha256="b" * 64,
        )
        self.journal.finish_attempt("attempt-1", "interrupted")
        self.journal.record_attempt("attempt-2", "run-1", "task-1", 2, "running")
        self.journal.save_checkpoint(
            "run-1", "checkpoint-0", 0, "task_boundary",
            {"task_id": "task-1", "attempt_id": "attempt-2"},
        )
        snapshot_id = self.journal.list_model_state_snapshot_metadata("run-1")[0]["snapshot_id"]
        result = self.inventory(snapshot_id=snapshot_id)
        self.assertEqual(result["disposition"], "blocked_unknown_state")
        self.assertIn(
            "snapshot_is_not_latest_attempt",
            {item["code"] for item in result["findings"]},
        )
        self.assertFalse(result["execution_authorized"])

    def test_checkpoint_tool_boundary_without_execution_is_blocked(self):
        self.journal.save_checkpoint(
            "run-1", "checkpoint-0", 0, "tool_call_prepared",
            {"logical_action_id": "action-missing", "task_id": "task-1", "attempt_id": "attempt-1"},
        )
        result = self.inventory()
        self.assertEqual(result["disposition"], "blocked_unknown_state")
        self.assertIn(
            "tool_boundary_execution_mismatch",
            {item["code"] for item in result["findings"]},
        )

    def test_missing_run_is_blocked_without_throwing(self):
        result = inspect_recovery_inventory(
            self.journal, self.recovery, "missing-run"
        )
        self.assertEqual(result["disposition"], "blocked_unknown_state")
        self.assertFalse(result["can_auto_resume"])


if __name__ == "__main__":
    unittest.main()
