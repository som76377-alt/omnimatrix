import unittest

from core.contracts import (
    CONTRACT_VERSION,
    ContextItem,
    ErrorCode,
    OmnitrixError,
    RunEvent,
    TrustLabel,
    WorkerRequest,
    WorkerResult,
    WorkerStatus,
)


class WorkerContractTests(unittest.TestCase):
    def test_request_has_versioned_ids_and_untrusted_context(self):
        request = WorkerRequest(
            run_id="run-1",
            task_id="task-1",
            attempt_id="attempt-1",
            correlation_id="trace-1",
            objective="Summarize the evidence",
            context=(ContextItem("quoted webpage text", TrustLabel.UNTRUSTED, "https://example.invalid"),),
            success_criteria=("Cite each claim",),
        )
        self.assertEqual(request.contract_version, CONTRACT_VERSION)
        self.assertEqual(request.context[0].trust, TrustLabel.UNTRUSTED)

    def test_request_rejects_missing_correlation_id(self):
        with self.assertRaisesRegex(ValueError, "correlation_id"):
            WorkerRequest(
                run_id="run-1", task_id="task-1", attempt_id="attempt-1",
                correlation_id=" ", objective="Do work"
            )

    def test_request_rejects_invalid_timeout(self):
        with self.assertRaisesRegex(ValueError, "timeout_seconds"):
            WorkerRequest(
                run_id="run-1", task_id="task-1", attempt_id="attempt-1",
                correlation_id="trace-1", objective="Do work", timeout_seconds=0
            )

    def test_success_result_cannot_claim_failure_code(self):
        with self.assertRaisesRegex(ValueError, "successful result"):
            WorkerResult(status=WorkerStatus.SUCCEEDED, failure_code=ErrorCode.TOOL_ERROR)

    def test_unknown_outcome_requires_failure_code(self):
        with self.assertRaisesRegex(ValueError, "require a failure_code"):
            WorkerResult(status=WorkerStatus.UNKNOWN)

    def test_safe_retry_requires_retryable(self):
        with self.assertRaisesRegex(ValueError, "requires retryable"):
            WorkerResult(status=WorkerStatus.FAILED, failure_code=ErrorCode.TOOL_ERROR, safe_to_retry=True)

    def test_error_exposes_stable_code_and_retry_semantics(self):
        error = OmnitrixError(ErrorCode.TIMEOUT, "Worker timed out", retryable=True, safe_to_retry=True)
        self.assertEqual(error.code, ErrorCode.TIMEOUT)
        self.assertTrue(error.safe_to_retry)

    def test_event_requires_iso_timestamp_and_nonnegative_sequence(self):
        event = RunEvent("evt-1", "run-1", 0, "task.created", "2026-10-12T10:00:00Z")
        self.assertEqual(event.contract_version, 1)
        with self.assertRaisesRegex(ValueError, "ISO-8601"):
            RunEvent("evt-2", "run-1", 1, "task.created", "tomorrow")
        with self.assertRaisesRegex(ValueError, "non-negative"):
            RunEvent("evt-3", "run-1", -1, "task.created", "2026-10-12T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
