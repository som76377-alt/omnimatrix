import unittest

from core.persistence.snapshot_recovery_gate import SnapshotRecoveryGateError
from core.persistence.snapshot_transcript_correlation import (
    validate_snapshot_transcript_correlation,
)


class SnapshotTranscriptCorrelationTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            "snapshot_id": "snapshot-1",
            "run_id": "run-1",
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "interaction_sequence": 0,
            "provider": "test",
            "model": "test-model",
        }
        self.transcript = self.pair(0, "task-1", "attempt-1", "a", "b")

    @staticmethod
    def pair(start, task_id, attempt_id, request_char, response_char, provider="test", model="test-model"):
        return [
            {
                "sequence": start, "run_id": "run-1", "task_id": task_id,
                "attempt_id": attempt_id, "interaction_type": "model_request",
                "provider": provider, "model": model,
                "request_sha256": request_char * 64, "response_sha256": None,
            },
            {
                "sequence": start + 1, "run_id": "run-1", "task_id": task_id,
                "attempt_id": attempt_id, "interaction_type": "model_response",
                "provider": provider, "model": model,
                "request_sha256": request_char * 64, "response_sha256": response_char * 64,
            },
        ]

    def test_exact_complete_pair_correlates_without_claiming_content_hash_verification(self):
        result = validate_snapshot_transcript_correlation(
            snapshot_metadata=self.metadata, transcript=self.transcript
        )
        self.assertEqual(result["request_transcript_sequence"], 0)
        self.assertEqual(result["response_transcript_sequence"], 1)
        self.assertEqual(result["request_sha256"], "a" * 64)
        self.assertEqual(result["response_sha256"], "b" * 64)
        self.assertFalse(result["content_hashes_verified"])

    def test_request_adapter_alias_can_differ_from_provider_reported_model_id(self):
        transcript = self.pair(0, "task-1", "attempt-1", "a", "b", model="adapter-alias")
        transcript[1]["model"] = "provider-model-v2"
        metadata = {**self.metadata, "model": "provider-model-v2"}
        result = validate_snapshot_transcript_correlation(
            snapshot_metadata=metadata, transcript=transcript
        )
        self.assertEqual(result["response_transcript_sequence"], 1)

    def test_attempt_local_ordinal_skips_earlier_attempts_and_tasks(self):
        prior = self.pair(0, "task-1", "attempt-0", "c", "d")
        same_attempt_first = self.pair(2, "task-1", "attempt-1", "a", "b")
        same_attempt_second = self.pair(4, "task-1", "attempt-1", "e", "f")
        metadata = {**self.metadata, "interaction_sequence": 1}
        result = validate_snapshot_transcript_correlation(
            snapshot_metadata=metadata,
            transcript=prior + same_attempt_first + same_attempt_second,
        )
        self.assertEqual(result["request_transcript_sequence"], 4)
        self.assertEqual(result["response_transcript_sequence"], 5)
        self.assertEqual(result["request_sha256"], "e" * 64)

    def test_missing_response_is_blocked(self):
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "unmatched"):
            validate_snapshot_transcript_correlation(
                snapshot_metadata=self.metadata, transcript=self.transcript[:1]
            )

    def test_wrong_task_attempt_provider_or_model_is_blocked(self):
        for field, value in (
            ("provider", "other-provider"),
            ("model", "other-model"),
        ):
            with self.subTest(field=field):
                metadata = {**self.metadata, field: value}
                with self.assertRaisesRegex(SnapshotRecoveryGateError, "does not match"):
                    validate_snapshot_transcript_correlation(
                        snapshot_metadata=metadata, transcript=self.transcript
                    )

        transcript = self.pair(0, "other-task", "attempt-1", "a", "b")
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "no complete matching"):
            validate_snapshot_transcript_correlation(
                snapshot_metadata=self.metadata, transcript=transcript
            )

    def test_wrong_order_and_request_digest_mismatch_are_blocked(self):
        transcript = [dict(item) for item in self.transcript]
        transcript[0]["interaction_type"] = "model_response"
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "order"):
            validate_snapshot_transcript_correlation(
                snapshot_metadata=self.metadata, transcript=transcript
            )
        transcript = [dict(item) for item in self.transcript]
        transcript[1]["request_sha256"] = "c" * 64
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "does not match"):
            validate_snapshot_transcript_correlation(
                snapshot_metadata=self.metadata, transcript=transcript
            )

    def test_boolean_or_invalid_sequence_is_blocked(self):
        for sequence in (True, -1, "0"):
            with self.subTest(sequence=sequence):
                metadata = {**self.metadata, "interaction_sequence": sequence}
                with self.assertRaisesRegex(SnapshotRecoveryGateError, "sequence"):
                    validate_snapshot_transcript_correlation(
                        snapshot_metadata=metadata, transcript=self.transcript
                    )


if __name__ == "__main__":
    unittest.main()
