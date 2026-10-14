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
        self.transcript = [
            {
                "sequence": 0, "run_id": "run-1", "task_id": "task-1",
                "attempt_id": "attempt-1", "interaction_type": "model_request",
                "provider": "test", "model": "test-model",
                "request_sha256": "a" * 64, "response_sha256": None,
            },
            {
                "sequence": 1, "run_id": "run-1", "task_id": "task-1",
                "attempt_id": "attempt-1", "interaction_type": "model_response",
                "provider": "test", "model": "test-model",
                "request_sha256": "a" * 64, "response_sha256": "b" * 64,
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

    def test_missing_response_is_blocked(self):
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "complete"):
            validate_snapshot_transcript_correlation(
                snapshot_metadata=self.metadata, transcript=self.transcript[:1]
            )

    def test_wrong_task_attempt_provider_or_model_is_blocked(self):
        for field, value in (
            ("task_id", "other-task"),
            ("attempt_id", "other-attempt"),
            ("provider", "other-provider"),
            ("model", "other-model"),
        ):
            with self.subTest(field=field):
                transcript = [dict(item) for item in self.transcript]
                transcript[1][field] = value
                with self.assertRaisesRegex(SnapshotRecoveryGateError, "does not match"):
                    validate_snapshot_transcript_correlation(
                        snapshot_metadata=self.metadata, transcript=transcript
                    )

    def test_wrong_order_and_request_digest_mismatch_are_blocked(self):
        transcript = [dict(item) for item in self.transcript]
        transcript[0]["interaction_type"] = "model_response"
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "interaction_type"):
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
