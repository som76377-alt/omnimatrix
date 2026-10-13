import unittest

from core.persistence.snapshot_recovery_gate import (
    SnapshotRecoveryGateError,
    validate_snapshot_recovery_gate,
)


class SnapshotRecoveryGateTests(unittest.TestCase):
    def setUp(self):
        self.inspection = {
            "run_id": "run-1",
            "integrity_errors": [],
            "decision": {"disposition": "revalidation_required", "can_auto_resume": False},
            "model_position": {
                "disposition": "model_boundary_consistent",
                "can_auto_resume": False,
            },
        }
        self.metadata = {
            "snapshot_id": "snapshot-1",
            "run_id": "run-1",
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "interaction_sequence": 0,
        }

    def gate(self, **overrides):
        metadata = {**self.metadata, **overrides}
        return validate_snapshot_recovery_gate(
            inspection=self.inspection,
            snapshot_metadata=metadata,
            expected_run_id="run-1",
            expected_task_id="task-1",
            expected_attempt_id="attempt-1",
        )

    def test_consistent_inspection_and_exact_identity_pass_preflight(self):
        self.assertIsNone(self.gate())

    def test_wrong_run_is_rejected(self):
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "run identity"):
            self.gate(run_id="other-run")

    def test_wrong_task_or_attempt_is_rejected(self):
        for field in ("task_id", "attempt_id"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(SnapshotRecoveryGateError, "does not match"):
                    self.gate(**{field: "other"})

    def test_integrity_errors_block_preflight(self):
        self.inspection["integrity_errors"] = ["checkpoint digest mismatch"]
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "integrity errors"):
            self.gate()

    def test_ambiguous_model_position_blocks_preflight(self):
        self.inspection["model_position"]["disposition"] = "model_call_outcome_ambiguous"
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "not consistent"):
            self.gate()

    def test_automatic_resume_can_never_be_enabled_by_this_gate(self):
        self.inspection["model_position"]["can_auto_resume"] = True
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "must not authorize"):
            self.gate()

    def test_invalid_sequence_and_missing_snapshot_id_are_rejected(self):
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "sequence"):
            self.gate(interaction_sequence=True)
        with self.assertRaisesRegex(SnapshotRecoveryGateError, "Snapshot ID"):
            self.gate(snapshot_id="")


if __name__ == "__main__":
    unittest.main()
