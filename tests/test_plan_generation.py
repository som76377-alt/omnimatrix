import unittest
from unittest.mock import patch

from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import ModelRequest
from core.models.registry import ModelDefinition, ModelRegistry
from core.orchestrator.omnitrix import Omnitrix
from core.orchestrator.planning import TaskPlan


class FakePlannerAdapter(ModelAdapter):
    name = "fake-planner"
    provider = "test"

    def __init__(self, content, tool_calls=()):
        self.content = content
        self.tool_calls = tool_calls
        self.requests = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            content=self.content,
            model=self.name,
            provider=self.provider,
            tool_calls=self.tool_calls,
        )


class PlanGenerationTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModelRegistry()
        self.registry.register(
            ModelDefinition(
                name="fake-planner",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        self.adapter = FakePlannerAdapter(
            '{"tasks":['
            '{"task_id":"research","description":"Research the topic",'
            '"dependencies":[]},'
            '{"task_id":"report","description":"Write the report",'
            '"dependencies":["research"]}'
            ']}'
        )
        self.adapters = AdapterRegistry()
        self.adapters.register(self.adapter)

        self.omnitrix = Omnitrix(
            registry=self.registry,
            adapter_registry=self.adapters,
        )

    def test_valid_response_returns_validated_plan(self):
        plan = self.omnitrix.propose_plan("Research a topic and write a report")

        self.assertIsInstance(plan, TaskPlan)
        self.assertEqual(
            [task.task_id for task in plan.tasks],
            ["research", "report"],
        )
        self.assertEqual(
            plan.tasks[1].dependencies,
            frozenset({"research"}),
        )

    def test_planning_request_exposes_no_tools(self):
        self.omnitrix.propose_plan("Create a research plan")

        self.assertEqual(len(self.adapter.requests), 1)
        self.assertEqual(self.adapter.requests[0].tools, ())

    def test_proposing_plan_does_not_execute_tasks(self):
        with (
            patch.object(self.omnitrix, "run") as mock_run,
            patch.object(self.omnitrix, "execute_plan") as mock_execute,
        ):
            self.omnitrix.propose_plan("Create a research plan")

        mock_run.assert_not_called()
        mock_execute.assert_not_called()

    def test_rejects_invalid_json(self):
        self.adapter.content = "This is not JSON"

        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            self.omnitrix.propose_plan("Create a plan")

    def test_rejects_unexpected_top_level_fields(self):
        self.adapter.content = '{"tasks":[],"extra":"unexpected"}'

        with self.assertRaisesRegex(ValueError, "only 'tasks'"):
            self.omnitrix.propose_plan("Create a plan")

    def test_rejects_empty_task_list(self):
        self.adapter.content = '{"tasks":[]}'

        with self.assertRaisesRegex(ValueError, "non-empty tasks array"):
            self.omnitrix.propose_plan("Create a plan")

    def test_rejects_unknown_dependency(self):
        self.adapter.content = (
            '{"tasks":[{"task_id":"report","description":"Write report",'
            '"dependencies":["missing"]}]}'
        )

        with self.assertRaisesRegex(ValueError, "unknown task"):
            self.omnitrix.propose_plan("Create a plan")

    def test_rejects_dependency_cycle(self):
        self.adapter.content = (
            '{"tasks":['
            '{"task_id":"a","description":"Task A","dependencies":["b"]},'
            '{"task_id":"b","description":"Task B","dependencies":["a"]}'
            ']}'
        )

        with self.assertRaisesRegex(ValueError, "cycle"):
            self.omnitrix.propose_plan("Create a plan")

    def test_rejects_duplicate_task_ids(self):
        self.adapter.content = (
            '{"tasks":['
            '{"task_id":"same","description":"First","dependencies":[]},'
            '{"task_id":"same","description":"Second","dependencies":[]}'
            ']}'
        )

        with self.assertRaisesRegex(ValueError, "Duplicate task ID"):
            self.omnitrix.propose_plan("Create a plan")

    def test_rejects_self_dependency(self):
        self.adapter.content = (
            '{"tasks":[{"task_id":"a","description":"Task A",'
            '"dependencies":["a"]}]}'
        )

        with self.assertRaisesRegex(ValueError, "cannot depend on itself"):
            self.omnitrix.propose_plan("Create a plan")

    def test_rejects_malformed_task_structure(self):
        self.adapter.content = (
            '{"tasks":[{"task_id":"a","description":"Task A"}]}'
        )

        with self.assertRaisesRegex(ValueError, "invalid structure"):
            self.omnitrix.propose_plan("Create a plan")

    def test_fails_if_no_reasoning_model_is_available(self):
        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="no-reasoning",
                provider="test",
                capabilities=frozenset({"coding"}),
            )
        )
        omnitrix = Omnitrix(registry=registry)

        with self.assertRaises(LookupError):
            omnitrix.propose_plan("Create a plan")

    def test_rejects_model_tool_calls(self):
        self.adapter.tool_calls = (object(),)

        with self.assertRaisesRegex(ValueError, "must not request tool calls"):
            self.omnitrix.propose_plan("Create a plan")

    def test_rejects_blank_objective_without_calling_model(self):
        with self.assertRaisesRegex(ValueError, "non-empty string"):
            self.omnitrix.propose_plan("   ")

        self.assertEqual(self.adapter.requests, [])


if __name__ == "__main__":
    unittest.main()
