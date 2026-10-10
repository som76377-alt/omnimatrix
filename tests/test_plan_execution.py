import unittest
from unittest.mock import call, patch

from core.orchestrator.omnitrix import Omnitrix
from core.orchestrator.planning import PlannedTask, TaskPlan
from core.models.registry import ModelRegistry


class PlanExecutionTests(unittest.TestCase):
    def setUp(self):
        self.omnitrix = Omnitrix(registry=ModelRegistry())
        self.run_patcher = patch.object(
            self.omnitrix,
            "run",
            side_effect=lambda objective, **kwargs: f"Completed: {objective}",
        )
        self.mock_run = self.run_patcher.start()
        self.addCleanup(self.run_patcher.stop)

    def test_plan_tasks_execute_in_dependency_order(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("report", "Write report", {"research"}),
                PlannedTask("research", "Research topic"),
                PlannedTask("review", "Review report", {"report"}),
            ]
        )

        results = self.omnitrix.execute_plan(plan)

        self.assertEqual(
            list(results),
            ["research", "report", "review"],
        )
        self.assertEqual(
            self.mock_run.call_args_list,
            [
                call("Research topic"),
                call(
                    "Write report",
                    dependency_results={"research": "Completed: Research topic"},
                ),
                call(
                    "Review report",
                    dependency_results={"report": "Completed: Write report"},
                ),
            ],
        )

    def test_failure_stops_plan_and_preserves_exception(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("report", "Write report", {"research", "calculate"}),
                PlannedTask("research", "Research topic"),
                PlannedTask("calculate", "Calculate results"),
            ]
        )
        failure = RuntimeError("model unavailable")

        def run_with_failure(objective):
            if objective == "Calculate results":
                raise failure
            return f"Completed: {objective}"

        self.mock_run.side_effect = run_with_failure

        with self.assertRaises(RuntimeError) as caught:
            self.omnitrix.execute_plan(plan)

        self.assertIs(caught.exception, failure)
        self.assertEqual(
            self.mock_run.call_args_list,
            [
                call("Research topic"),
                call("Calculate results"),
            ],
        )

    def test_independent_tasks_execute_in_declared_order(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("first", "First task"),
                PlannedTask("second", "Second task"),
            ]
        )

        results = self.omnitrix.execute_plan(plan)

        self.assertEqual(list(results), ["first", "second"])
        self.assertEqual(
            self.mock_run.call_args_list,
            [call("First task"), call("Second task")],
        )

    def test_dependent_task_receives_only_direct_dependency_results(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("research", "Research topic"),
                PlannedTask("unrelated", "Do unrelated work"),
                PlannedTask("design", "Design solution", {"research"}),
                PlannedTask("review", "Review solution", {"design"}),
            ]
        )

        def run_with_results(objective, **kwargs):
            if objective == "Research topic":
                return "Research evidence"
            if objective == "Do unrelated work":
                return "Unrelated evidence"
            if objective == "Design solution":
                self.assertEqual(
                    kwargs["dependency_results"],
                    {"research": "Research evidence"},
                )
                return "Design result"
            if objective == "Review solution":
                self.assertEqual(
                    kwargs["dependency_results"],
                    {"design": "Design result"},
                )
                return "Review result"
            self.fail(f"Unexpected objective: {objective}")

        self.mock_run.side_effect = run_with_results

        results = self.omnitrix.execute_plan(plan)

        self.assertEqual(results["review"], "Review result")

    def test_task_receives_all_direct_dependency_results(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("research", "Research topic"),
                PlannedTask("calculate", "Calculate figures"),
                PlannedTask(
                    "report",
                    "Write report",
                    {"research", "calculate"},
                ),
            ]
        )

        def run_with_results(objective, **kwargs):
            if objective == "Research topic":
                return "Research evidence"
            if objective == "Calculate figures":
                return "Calculated figures"
            if objective == "Write report":
                self.assertEqual(
                    kwargs["dependency_results"],
                    {
                        "calculate": "Calculated figures",
                        "research": "Research evidence",
                    },
                )
                return "Final report"
            self.fail(f"Unexpected objective: {objective}")

        self.mock_run.side_effect = run_with_results

        results = self.omnitrix.execute_plan(plan)

        self.assertEqual(results["report"], "Final report")

    def test_rejects_non_task_plan_input(self):
        with self.assertRaisesRegex(TypeError, "plan must be a TaskPlan"):
            self.omnitrix.execute_plan("not a plan")

        self.mock_run.assert_not_called()

    def test_empty_plan_returns_empty_results(self):
        plan = TaskPlan.from_tasks([])

        results = self.omnitrix.execute_plan(plan)

        self.assertEqual(results, {})
        self.mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
