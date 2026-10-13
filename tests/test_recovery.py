import unittest

from core.persistence.recovery import classify_model_position, classify_recovery


class RecoveryClassificationTests(unittest.TestCase):
    def test_missing_run_is_not_found(self):
        self.assertEqual(classify_recovery(None).disposition, "not_found")

    def test_terminal_run_is_not_resumed(self):
        decision = classify_recovery({
            "run": {"status": "succeeded"},
            "uncertain_tool_executions": [],
        })
        self.assertEqual(decision.disposition, "terminal")
        self.assertFalse(decision.can_auto_resume)

    def test_completed_run_is_terminal(self):
        decision = classify_recovery({
            "run": {"status": "completed"},
            "uncertain_tool_executions": [],
        })
        self.assertEqual(decision.disposition, "terminal")

    def test_unresolved_tool_execution_requires_reconciliation(self):
        decision = classify_recovery({
            "run": {"status": "running"},
            "uncertain_tool_executions": [{
                "execution_id": "exec-1",
                "status": "running",
                "latest_reconciliation": None,
            }],
        })
        self.assertEqual(decision.disposition, "reconciliation_required")
        self.assertFalse(decision.can_auto_resume)

    def test_confirmed_not_applied_only_requests_retry_review(self):
        decision = classify_recovery({
            "run": {"status": "running"},
            "uncertain_tool_executions": [{
                "execution_id": "exec-1",
                "status": "running",
                "latest_reconciliation": {"decision": "confirmed_not_applied"},
            }],
        })
        self.assertEqual(decision.disposition, "retry_review_required")
        self.assertFalse(decision.can_auto_resume)

    def test_confirmed_applied_requires_downstream_revalidation(self):
        decision = classify_recovery({
            "run": {"status": "running"},
            "uncertain_tool_executions": [{
                "execution_id": "exec-1",
                "status": "unknown",
                "latest_reconciliation": {"decision": "confirmed_applied"},
            }],
        })
        self.assertEqual(decision.disposition, "revalidation_required")
        self.assertFalse(decision.can_auto_resume)

    def test_mixed_reconciliation_decisions_require_combined_review(self):
        decision = classify_recovery({
            "run": {"status": "running"},
            "uncertain_tool_executions": [
                {
                    "execution_id": "exec-applied",
                    "status": "running",
                    "latest_reconciliation": {"decision": "confirmed_applied"},
                },
                {
                    "execution_id": "exec-not-applied",
                    "status": "unknown",
                    "latest_reconciliation": {"decision": "confirmed_not_applied"},
                },
            ],
        })
        self.assertEqual(decision.disposition, "mixed_reconciliation_review_required")
        self.assertFalse(decision.can_auto_resume)

    def test_running_run_without_uncertain_tools_still_requires_revalidation(self):
        decision = classify_recovery({
            "run": {"status": "running"},
            "uncertain_tool_executions": [],
        })
        self.assertEqual(decision.disposition, "revalidation_required")
        self.assertFalse(decision.can_auto_resume)

    def test_unknown_state_fails_closed(self):
        decision = classify_recovery({
            "run": {"status": "mystery"},
            "uncertain_tool_executions": [],
        })
        self.assertEqual(decision.disposition, "blocked_unknown_state")
        self.assertFalse(decision.can_auto_resume)


class ModelRecoveryPositionTests(unittest.TestCase):
    def setUp(self):
        self.request = {
            "sequence": 0, "interaction_type": "model_request",
            "task_id": "task-1", "attempt_id": "attempt-1",
            "request_sha256": "a" * 64, "response_sha256": None,
        }
        self.response = {
            "sequence": 1, "interaction_type": "model_response",
            "task_id": "task-1", "attempt_id": "attempt-1",
            "request_sha256": "a" * 64, "response_sha256": "b" * 64,
        }
        self.checkpoints = [
            {"checkpoint_type": "model_request_started"},
            {"checkpoint_type": "model_response_received"},
        ]

    def test_no_model_activity_is_explicit(self):
        result = classify_model_position([], [])
        self.assertEqual(result["disposition"], "no_model_activity")
        self.assertFalse(result["can_auto_resume"])

    def test_matching_transcript_and_checkpoints_are_consistent(self):
        result = classify_model_position([self.request, self.response], self.checkpoints)
        self.assertEqual(result["disposition"], "model_boundary_consistent")
        self.assertEqual(result["model_call_count"], 1)
        self.assertFalse(result["can_auto_resume"])

    def test_request_without_response_is_ambiguous(self):
        result = classify_model_position([self.request], self.checkpoints[:1])
        self.assertEqual(result["disposition"], "model_call_outcome_ambiguous")
        self.assertIn("provider completion is unknown", result["reasons"][0])

    def test_response_record_without_response_checkpoint_is_detected(self):
        result = classify_model_position([self.request, self.response], self.checkpoints[:1])
        self.assertEqual(result["disposition"], "model_response_checkpoint_missing")

    def test_transcript_identity_mismatch_fails_closed(self):
        mismatched = dict(self.response, attempt_id="attempt-2")
        result = classify_model_position([self.request, mismatched], self.checkpoints)
        self.assertEqual(result["disposition"], "boundary_mismatch")

    def test_checkpoint_order_mismatch_fails_closed(self):
        result = classify_model_position(
            [self.request, self.response],
            list(reversed(self.checkpoints)),
        )
        self.assertEqual(result["disposition"], "boundary_mismatch")


if __name__ == "__main__":
    unittest.main()
