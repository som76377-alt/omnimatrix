import unittest

from core.persistence.recovery import classify_recovery


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


if __name__ == "__main__":
    unittest.main()
