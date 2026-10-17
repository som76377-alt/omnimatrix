import hashlib
import unittest

from core.persistence.tool_reconciliation_verifier import (
    ToolReconciliationVerifierRegistry,
    VerificationResult,
    verify_tool_reconciliation,
)


def evidence_digest():
    return hashlib.sha256(b"authoritative receipt").hexdigest()


def execution(**overrides):
    record = {
        "execution_id": "exec-1",
        "idempotency_key": "idem-1",
        "tool_name": "mail.send",
        "request_sha256": "a" * 64,
        "run_id": "run-1",
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "logical_action_id": "action-1",
        "status": "unknown",
    }
    record.update(overrides)
    return record


class FakeVerifier:
    tool_name = "mail.send"
    verifier_id = "mail.provider-receipt.v1"

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    def verify(self, identity, evidence):
        self.calls += 1
        if self.error:
            raise self.error
        if callable(self.result):
            return self.result(identity, evidence)
        if self.result is not None:
            return self.result
        return VerificationResult(
            execution_id=identity.execution_id,
            idempotency_key=identity.idempotency_key,
            tool_name=identity.tool_name,
            request_sha256=identity.request_sha256,
            run_id=identity.run_id,
            task_id=identity.task_id,
            attempt_id=identity.attempt_id,
            logical_action_id=identity.logical_action_id,
            verifier_id=self.verifier_id,
            outcome="applied",
            observed_at="2026-10-17T00:00:00Z",
            evidence_reference="provider://receipt/123",
            evidence_sha256=evidence_digest(),
        )


class ToolReconciliationVerifierTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolReconciliationVerifierRegistry()
        self.verifier = FakeVerifier()
        self.registry.register(self.verifier)
        self.evidence = {"receipt_id": "123", "claimed_outcome": "applied"}

    def test_exact_identity_and_valid_evidence_return_applied(self):
        result = verify_tool_reconciliation(execution(), self.evidence, self.registry)
        self.assertEqual(result.outcome, "applied")
        self.assertTrue(result.verified)
        self.assertEqual(result.verifier_id, self.verifier.verifier_id)
        self.assertEqual(result.reason, "verified")
        self.assertEqual(self.verifier.calls, 1)

    def test_not_applied_is_a_valid_verified_outcome_but_not_authority(self):
        self.verifier.result = lambda identity, evidence: VerificationResult(
            identity.execution_id, identity.idempotency_key, identity.tool_name,
            identity.request_sha256, identity.run_id, identity.task_id,
            identity.attempt_id, identity.logical_action_id, self.verifier.verifier_id,
            "not_applied", "2026-10-17T00:00:00Z", "provider://receipt/none", evidence_digest(),
        )
        result = verify_tool_reconciliation(execution(), self.evidence, self.registry)
        self.assertEqual(result.outcome, "not_applied")
        self.assertTrue(result.verified)
        self.assertFalse(hasattr(result, "execution_authorized"))

    def test_unknown_tool_without_verifier_fails_closed(self):
        result = verify_tool_reconciliation(
            execution(tool_name="unknown.tool"), self.evidence, self.registry
        )
        self.assertEqual((result.outcome, result.verified, result.reason),
                         ("unknown", False, "verifier_unavailable"))

    def test_missing_or_malformed_execution_identity_fails_closed(self):
        for record in (
            execution(execution_id=""),
            execution(request_sha256="not-a-digest"),
            execution(attempt_id=None),
        ):
            with self.subTest(record=record):
                result = verify_tool_reconciliation(record, self.evidence, self.registry)
                self.assertFalse(result.verified)
                self.assertEqual(result.reason, "execution_identity_invalid")
        self.assertEqual(self.verifier.calls, 0)

    def test_terminal_execution_is_not_reconciled_by_this_contract(self):
        result = verify_tool_reconciliation(
            execution(status="succeeded"), self.evidence, self.registry
        )
        self.assertEqual(result.reason, "execution_not_uncertain")
        self.assertFalse(result.verified)
        self.assertEqual(self.verifier.calls, 0)

    def test_verifier_exception_is_redacted_and_fails_closed(self):
        self.verifier.error = RuntimeError("provider secret response body")
        result = verify_tool_reconciliation(execution(), self.evidence, self.registry)
        self.assertEqual(result.reason, "verifier_error")
        self.assertEqual(result.outcome, "unknown")
        self.assertNotIn("provider secret", repr(result))

    def test_wrong_result_type_fails_closed(self):
        self.verifier.result = {"outcome": "applied"}
        result = verify_tool_reconciliation(execution(), self.evidence, self.registry)
        self.assertEqual(result.reason, "malformed_verifier_result")
        self.assertFalse(result.verified)

    def test_mismatched_execution_or_verifier_identity_fails_closed(self):
        self.verifier.result = lambda identity, evidence: VerificationResult(
            "different-exec", identity.idempotency_key, identity.tool_name,
            identity.request_sha256, identity.run_id, identity.task_id,
            identity.attempt_id, identity.logical_action_id, self.verifier.verifier_id,
            "applied", "2026-10-17T00:00:00Z", "provider://receipt/123", evidence_digest(),
        )
        result = verify_tool_reconciliation(execution(), self.evidence, self.registry)
        self.assertEqual(result.reason, "verification_identity_mismatch")
        self.assertFalse(result.verified)

    def test_task_attempt_identity_mismatch_fails_closed(self):
        self.verifier.result = lambda identity, evidence: VerificationResult(
            identity.execution_id, identity.idempotency_key, identity.tool_name,
            identity.request_sha256, identity.run_id, "different-task",
            identity.attempt_id, identity.logical_action_id, self.verifier.verifier_id,
            "applied", "2026-10-17T00:00:00Z", "provider://receipt/123", evidence_digest(),
        )
        result = verify_tool_reconciliation(execution(), self.evidence, self.registry)
        self.assertEqual(result.reason, "verification_identity_mismatch")
        self.assertFalse(result.verified)

    def test_invalid_outcome_or_evidence_metadata_fails_closed(self):
        invalid_results = (
            VerificationResult("exec-1", "idem-1", "mail.send", "a" * 64,
                               "run-1", "task-1", "attempt-1", "action-1",
                               self.verifier.verifier_id, "confirmed_applied",
                               "2026-10-17T00:00:00Z", "provider://receipt/123", evidence_digest()),
            VerificationResult("exec-1", "idem-1", "mail.send", "a" * 64,
                               "run-1", "task-1", "attempt-1", "action-1",
                               self.verifier.verifier_id, "applied",
                               "", "provider://receipt/123", evidence_digest()),
            VerificationResult("exec-1", "idem-1", "mail.send", "a" * 64,
                               "run-1", "task-1", "attempt-1", "action-1",
                               self.verifier.verifier_id, "applied",
                               "2026-10-17T00:00:00Z", "", evidence_digest()),
            VerificationResult("exec-1", "idem-1", "mail.send", "a" * 64,
                               self.verifier.verifier_id, "applied",
                               "2026-10-17T00:00:00Z", "provider://receipt/123", "bad"),
        )
        for invalid in invalid_results:
            with self.subTest(invalid=invalid):
                self.verifier.result = invalid
                result = verify_tool_reconciliation(execution(), self.evidence, self.registry)
                self.assertFalse(result.verified)
                self.assertIn(result.reason, {
                    "verification_outcome_invalid", "verification_evidence_invalid"
                })

    def test_unknown_outcome_never_counts_as_verified(self):
        self.verifier.result = lambda identity, evidence: VerificationResult(
            identity.execution_id, identity.idempotency_key, identity.tool_name,
            identity.request_sha256, identity.run_id, identity.task_id,
            identity.attempt_id, identity.logical_action_id, self.verifier.verifier_id,
            "unknown", "2026-10-17T00:00:00Z", "provider://receipt/unclear", evidence_digest(),
        )
        result = verify_tool_reconciliation(execution(), self.evidence, self.registry)
        self.assertEqual(result.reason, "outcome_unknown")
        self.assertFalse(result.verified)

    def test_unhashable_status_and_outcome_fail_closed(self):
        result = verify_tool_reconciliation(
            execution(status=["unknown"]), self.evidence, self.registry
        )
        self.assertEqual(result.reason, "execution_not_uncertain")
        self.assertFalse(result.verified)

        self.verifier.result = lambda identity, evidence: VerificationResult(
            identity.execution_id, identity.idempotency_key, identity.tool_name,
            identity.request_sha256, identity.run_id, identity.task_id,
            identity.attempt_id, identity.logical_action_id, self.verifier.verifier_id,
            ["applied"], "2026-10-17T00:00:00Z", "provider://receipt/123", evidence_digest(),
        )
        result = verify_tool_reconciliation(execution(), self.evidence, self.registry)
        self.assertEqual(result.reason, "verification_outcome_invalid")
        self.assertFalse(result.verified)

    def test_registry_rejects_duplicate_tool_verifier(self):
        with self.assertRaises(ValueError):
            self.registry.register(FakeVerifier())

    def test_operator_claim_alone_is_not_used_as_verification_result(self):
        self.verifier.result = None
        result = verify_tool_reconciliation(
            execution(), {"claimed_outcome": "not_applied"}, self.registry
        )
        self.assertEqual(result.outcome, "applied")
        self.assertTrue(result.verified)
        # The fake verifier's fixed result models an authoritative receipt; the
        # operator's claimed_outcome field is not consulted by the contract.


if __name__ == "__main__":
    unittest.main()
