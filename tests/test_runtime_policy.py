import unittest

from core.contracts import BudgetGuard, BudgetLimits, ErrorCode, OmnitrixError
from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import ModelRequest
from core.models.registry import ModelDefinition, ModelRegistry
from core.orchestrator.omnitrix import Omnitrix
from core.orchestrator.planning import PlanExecutionContext, PlannedTask, TaskPlan
from core.tools.base import Tool, ToolResult
from core.tools.permissions import ToolPermission
from core.tools.registry import ToolRegistry
from core.tools.request import ToolRequest


class CountingAdapter(ModelAdapter):
    name = "counting-model"
    provider = "test"

    def __init__(self):
        self.calls = 0

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        return ModelResponse("ok", self.name, self.provider)


class SideEffectTool(Tool):
    name = "side-effect"
    description = "Test-only side-effect counter"
    capabilities = frozenset({"write"})

    def __init__(self):
        self.calls = 0

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {}, "additionalProperties": False}

    def execute(self, **kwargs):
        self.calls += 1
        return ToolResult(success=True, output="changed")


class RuntimePolicyTests(unittest.TestCase):
    def build_omnitrix(self, metadata=None, tool=None):
        registry = ModelRegistry()
        registry.register(ModelDefinition(
            name="counting-model",
            provider="test",
            capabilities=frozenset({"reasoning"}),
            metadata=metadata or {},
        ))
        adapter = CountingAdapter()
        adapters = AdapterRegistry()
        adapters.register(adapter)
        tools = ToolRegistry()
        if tool is not None:
            tools.register(tool)
        omni = Omnitrix(
            registry=registry,
            adapter_registry=adapters,
            tool_registry=tools,
            tool_permission=ToolPermission.from_capabilities({"write"}),
        )
        return omni, adapter

    def test_unknown_cost_provider_is_blocked_before_generate(self):
        omni, adapter = self.build_omnitrix()
        with self.assertRaises(OmnitrixError) as caught:
            omni.run("Do a task")
        self.assertEqual(caught.exception.code, ErrorCode.BUDGET_EXCEEDED)
        self.assertEqual(adapter.calls, 0)

    def test_explicit_demo_cost_class_can_run(self):
        omni, adapter = self.build_omnitrix(
            {"cost_class": "demo", "estimated_cost_usd": 0}
        )
        self.assertEqual(omni.run("Do a task"), "ok")
        self.assertEqual(adapter.calls, 1)

    def test_paid_class_is_blocked_in_zero_cost_mode(self):
        omni, adapter = self.build_omnitrix(
            {"cost_class": "paid", "estimated_cost_usd": 0.01}
        )
        with self.assertRaises(OmnitrixError):
            omni.run("Do a task")
        self.assertEqual(adapter.calls, 0)

    def test_plan_scope_denial_precedes_tool_side_effect(self):
        tool = SideEffectTool()
        omni, _ = self.build_omnitrix(
            {"cost_class": "demo", "estimated_cost_usd": 0}, tool
        )
        result = omni.execute_tool(
            ToolRequest("side-effect", {}),
            allowed_tool_scopes=frozenset(),
        )
        self.assertFalse(result.success)
        self.assertIn("Plan scope denied", result.error)
        self.assertEqual(tool.calls, 0)

    def test_shared_tool_budget_blocks_second_side_effect(self):
        tool = SideEffectTool()
        omni, _ = self.build_omnitrix(
            {"cost_class": "demo", "estimated_cost_usd": 0}, tool
        )
        guard = BudgetGuard(BudgetLimits(max_tool_calls=1))
        first = omni.execute_tool(ToolRequest("side-effect", {}), budget_guard=guard)
        second = omni.execute_tool(ToolRequest("side-effect", {}), budget_guard=guard)
        self.assertTrue(first.success)
        self.assertFalse(second.success)
        self.assertEqual(tool.calls, 1)

    def test_plan_with_unenforceable_targets_is_rejected_before_tasks_run(self):
        omni, _ = self.build_omnitrix(
            {"cost_class": "demo", "estimated_cost_usd": 0}
        )
        plan = TaskPlan.from_tasks(
            [PlannedTask("task", "Do the task")],
            context=PlanExecutionContext(targets=("workspace/project",)),
        )
        with self.assertRaisesRegex(OmnitrixError, "cannot yet enforce"):
            omni.execute_approved_plan(omni.approve_plan(plan))


if __name__ == "__main__":
    unittest.main()
