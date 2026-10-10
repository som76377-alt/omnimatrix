import unittest
from unittest.mock import patch

from core.models.messages import MessageRole
from core.models.registry import ModelRegistry
from core.orchestrator.omnitrix import Omnitrix


class PlanContextTests(unittest.TestCase):
    def setUp(self):
        self.omnitrix = Omnitrix(registry=ModelRegistry())

    def test_run_includes_dependency_results_in_user_message(self):
        captured = {}

        def capture_task(task, messages):
            captured["messages"] = messages
            return "captured"

        with patch.object(
            self.omnitrix,
            "_execute_task",
            side_effect=capture_task,
        ):
            result = self.omnitrix.run(
                "Design solution",
                dependency_results={"research": "Research evidence"},
            )

        self.assertEqual(result, "captured")
        messages = captured["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, MessageRole.USER)
        self.assertIn("Design solution", messages[0].content)
        self.assertIn("research", messages[0].content)
        self.assertIn("Research evidence", messages[0].content)

    def test_run_rejects_non_dictionary_dependency_results(self):
        with self.assertRaisesRegex(
            TypeError,
            "dependency_results must be a dictionary or None",
        ):
            self.omnitrix.run(
                "Design solution",
                dependency_results="not a dictionary",
            )

    def test_run_rejects_blank_dependency_task_id(self):
        with self.assertRaisesRegex(
            ValueError,
            "Dependency task IDs must be non-empty strings",
        ):
            self.omnitrix.run(
                "Design solution",
                dependency_results={" ": "Research evidence"},
            )

    def test_run_rejects_non_string_dependency_result(self):
        with self.assertRaisesRegex(
            TypeError,
            "Dependency results must be strings",
        ):
            self.omnitrix.run(
                "Design solution",
                dependency_results={"research": 123},
            )


if __name__ == "__main__":
    unittest.main()
