import unittest

from core.orchestrator.planning import PlannedTask, TaskPlan


class PlannedTaskTests(unittest.TestCase):
    def test_rejects_blank_task_id(self):
        with self.assertRaises(ValueError):
            PlannedTask(task_id=" ", description="Research")

    def test_rejects_blank_description(self):
        with self.assertRaises(ValueError):
            PlannedTask(task_id="research", description=" ")

    def test_dependencies_are_immutable(self):
        dependencies = {"research"}
        task = PlannedTask("write", "Write report", dependencies)
        dependencies.add("review")

        self.assertEqual(task.dependencies, frozenset({"research"}))

    def test_rejects_string_as_dependencies(self):
        with self.assertRaises(ValueError):
            PlannedTask("write", "Write report", "research")


class TaskPlanTests(unittest.TestCase):
    def test_from_tasks_rejects_non_iterable_input(self):
        with self.assertRaisesRegex(ValueError, "Plan tasks must be iterable"):
            TaskPlan.from_tasks(123)

    def test_long_dependency_chain_does_not_exceed_recursion_limit(self):
        count = 1500
        tasks = [
            PlannedTask(
                f"t{i}",
                f"Task {i}",
                {f"t{i - 1}"} if i else frozenset(),
            )
            for i in range(count)
        ]

        plan = TaskPlan.from_tasks(tasks)

        self.assertEqual(len(plan.tasks), count)
        self.assertEqual(
            [task.task_id for task in plan.ready_tasks()],
            ["t0"],
        )

    def test_task_waits_for_all_dependencies(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("research", "Research"),
                PlannedTask("calculate", "Calculate"),
                PlannedTask("report", "Report", {"research", "calculate"}),
            ]
        )

        self.assertEqual(
            [task.task_id for task in plan.ready_tasks({"research"})],
            ["calculate"],
        )
        self.assertEqual(
            [task.task_id for task in plan.ready_tasks(
                {"research", "calculate"}
            )],
            ["report"],
        )

    def test_accepts_valid_dependency_chain(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("research", "Research the topic"),
                PlannedTask("draft", "Write a draft", {"research"}),
                PlannedTask("review", "Review the draft", {"draft"}),
            ]
        )

        self.assertEqual(len(plan.tasks), 3)

    def test_rejects_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, "Duplicate task ID"):
            TaskPlan.from_tasks(
                [
                    PlannedTask("research", "Research"),
                    PlannedTask("research", "Research again"),
                ]
            )

    def test_rejects_unknown_dependency(self):
        with self.assertRaisesRegex(ValueError, "unknown task"):
            TaskPlan.from_tasks(
                [PlannedTask("draft", "Write a draft", {"research"})]
            )

    def test_rejects_self_dependency(self):
        with self.assertRaisesRegex(ValueError, "cannot depend on itself"):
            TaskPlan.from_tasks(
                [PlannedTask("research", "Research", {"research"})]
            )

    def test_rejects_dependency_cycle(self):
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            TaskPlan.from_tasks(
                [
                    PlannedTask("a", "First", {"b"}),
                    PlannedTask("b", "Second", {"a"}),
                ]
            )

    def test_rejects_longer_dependency_cycle(self):
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            TaskPlan.from_tasks(
                [
                    PlannedTask("a", "First", {"c"}),
                    PlannedTask("b", "Second", {"a"}),
                    PlannedTask("c", "Third", {"b"}),
                ]
            )

    def test_initially_ready_tasks_have_no_dependencies(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("research", "Research"),
                PlannedTask("draft", "Draft", {"research"}),
                PlannedTask("review", "Review", {"draft"}),
            ]
        )

        self.assertEqual(
            [task.task_id for task in plan.ready_tasks()],
            ["research"],
        )

    def test_ready_tasks_unlock_after_dependencies_complete(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("research", "Research"),
                PlannedTask("draft", "Draft", {"research"}),
                PlannedTask("review", "Review", {"draft"}),
            ]
        )

        self.assertEqual(
            [task.task_id for task in plan.ready_tasks({"research"})],
            ["draft"],
        )

    def test_independent_tasks_can_be_ready_together(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("research", "Research"),
                PlannedTask("calculate", "Calculate"),
                PlannedTask("report", "Report", {"research", "calculate"}),
            ]
        )

        self.assertEqual(
            [task.task_id for task in plan.ready_tasks()],
            ["research", "calculate"],
        )

    def test_completed_tasks_are_not_returned_as_ready(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("research", "Research"),
                PlannedTask("draft", "Draft", {"research"}),
            ]
        )

        self.assertEqual(
            [task.task_id for task in plan.ready_tasks({"research"})],
            ["draft"],
        )

    def test_rejects_unknown_completed_task_id(self):
        plan = TaskPlan.from_tasks([PlannedTask("research", "Research")])

        with self.assertRaisesRegex(ValueError, "Unknown completed task ID"):
            plan.ready_tasks({"missing"})

    def test_ready_tasks_preserve_declared_plan_order(self):
        plan = TaskPlan.from_tasks(
            [
                PlannedTask("second", "Second independent task"),
                PlannedTask("first", "First independent task"),
            ]
        )

        self.assertEqual(
            [task.task_id for task in plan.ready_tasks()],
            ["second", "first"],
        )


if __name__ == "__main__":
    unittest.main()
