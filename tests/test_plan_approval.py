import unittest
from unittest.mock import patch

from core.models.registry import ModelRegistry
from core.orchestrator.omnitrix import Omnitrix
from core.orchestrator.planning import (
    PlanApproval,
    PlannedTask,
    TaskPlan,
    fingerprint_plan,
)


class PlanApprovalTests(unittest.TestCase):
    def setUp(self):
        self.omnitrix = Omnitrix(registry=ModelRegistry())
        # Deliberately list a dependent task before its prerequisite.
        self.plan = TaskPlan.from_tasks(
            [
                PlannedTask(
                    "report",
                    "Write the report",
                    frozenset({"research"}),
                ),
                PlannedTask("research", "Research the topic"),
                PlannedTask("summary", "Summarize the findings"),
            ]
        )

    def test_preview_shows_dependency_execution_order(self):
        preview = self.omnitrix.preview_plan(self.plan)

        self.assertIn("\n", preview)
        self.assertNotIn("\\n", preview)

        self.assertLess(
            preview.index("[research]"),
            preview.index("[report]"),
        )
        self.assertIn("Depends on: research", preview)
        self.assertIn("1. [research]", preview)
        self.assertIn("2. [report]", preview)
        self.assertIn("3. [summary]", preview)

    def test_approve_plan_binds_exact_plan_fingerprint(self):
        approval = self.omnitrix.approve_plan(self.plan)

        self.assertIsInstance(approval, PlanApproval)
        self.assertIs(approval.plan, self.plan)
        self.assertEqual(approval.fingerprint, fingerprint_plan(self.plan))

    def test_approved_execution_runs_the_approved_plan(self):
        approval = self.omnitrix.approve_plan(self.plan)

        with patch.object(
            self.omnitrix,
            "run",
            side_effect=["research result", "report result", "summary result"],
        ) as mock_run:
            results = self.omnitrix.execute_approved_plan(approval)

        self.assertEqual(
            results,
            {
                "research": "research result",
                "report": "report result",
                "summary": "summary result",
            },
        )
        self.assertEqual(
            [call.args[0] for call in mock_run.call_args_list],
            [
                "Research the topic",
                "Write the report",
                "Summarize the findings",
            ],
        )

    def test_approved_execution_rejects_mismatched_fingerprint(self):
        approval = self.omnitrix.approve_plan(self.plan)
        changed_plan = TaskPlan.from_tasks(
            [
                PlannedTask(
                    "report",
                    "Write a different report",
                    frozenset({"research"}),
                ),
                PlannedTask("research", "Research the topic"),
                PlannedTask("summary", "Summarize the findings"),
            ]
        )
        tampered_approval = PlanApproval(
            plan=changed_plan,
            fingerprint=approval.fingerprint,
        )

        with patch.object(self.omnitrix, "run") as mock_run:
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                self.omnitrix.execute_approved_plan(tampered_approval)

        mock_run.assert_not_called()

    def test_approved_execution_rejects_wrong_input_type(self):
        with self.assertRaises(TypeError):
            self.omnitrix.execute_approved_plan(self.plan)

    def test_preview_rejects_wrong_input_type(self):
        with self.assertRaises(TypeError):
            self.omnitrix.preview_plan("not a plan")

    def test_empty_plan_preview_is_explicit(self):
        preview = self.omnitrix.preview_plan(TaskPlan.from_tasks([]))

        self.assertIn("nothing will execute", preview)


if __name__ == "__main__":
    unittest.main()
