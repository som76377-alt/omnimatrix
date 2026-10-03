import unittest

from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import MessageRole, ModelRequest
from core.models.registry import ModelDefinition, ModelRegistry
from core.models.types import ModelContinuation, ModelToolCall
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission


class FakeToolCallingAdapter(ModelAdapter):
    def __init__(self):
        self.requests = []

    @property
    def name(self):
        return "fake-tool-model"

    @property
    def provider(self):
        return "test"

    def generate(self, request: ModelRequest):
        self.requests.append(request)

        if len(self.requests) == 1:
            return ModelResponse(
                content="",
                model=self.name,
                provider=self.provider,
                tool_calls=(
                    ModelToolCall(
                        id="call-1",
                        tool_name="calculator",
                        arguments={"expression": "847 * 23"},
                    ),
                ),
                continuation=ModelContinuation(
                    provider=self.provider,
                    state={"turn": 1},
                ),
            )

        tool_messages = [
            message
            for message in request.messages
            if message.role == MessageRole.TOOL
        ]

        if len(tool_messages) != 1:
            raise RuntimeError("Expected exactly one tool message.")
        if tool_messages[0].tool_result is None:
            raise RuntimeError("Expected a tool result.")
        if not tool_messages[0].tool_result.success:
            raise RuntimeError("Expected successful tool execution.")
        if tool_messages[0].tool_result.output != 19481:
            raise RuntimeError("Expected calculator result 19481.")

        return ModelResponse(
            content="The result is 19,481.",
            model=self.name,
            provider=self.provider,
        )


class OmnitrixOrchestratorTests(unittest.TestCase):
    def test_tool_call_continuation_flow(self):
        model = ModelDefinition(
            name="fake-tool-model",
            provider="test",
            model_id="fake-tool-model-v1",
            capabilities=frozenset({"reasoning", "calculation"}),
            context_window=32000,
            enabled=True,
        )

        model_registry = ModelRegistry()
        model_registry.register(model)

        adapter = FakeToolCallingAdapter()
        adapter_registry = AdapterRegistry()
        adapter_registry.register(adapter)

        omnitrix = Omnitrix(
            registry=model_registry,
            adapter_registry=adapter_registry,
            tool_registry=build_tool_registry(),
            tool_permission=ToolPermission.from_capabilities({"calculation"}),
        )

        result = omnitrix.run(
            "Calculate 847 * 23 using the calculator tool."
        )

        self.assertEqual(result, "The result is 19,481.")
        self.assertEqual(len(adapter.requests), 2)

        first_request = adapter.requests[0]
        self.assertEqual(
            first_request.messages[0].content,
            "Calculate 847 * 23 using the calculator tool.",
        )
        self.assertEqual(len(first_request.tools), 1)
        self.assertEqual(first_request.tools[0].name, "calculator")

        second_request = adapter.requests[1]
        self.assertIsNotNone(second_request.continuation)
        self.assertEqual(
            second_request.continuation.state["turn"],
            1,
        )

        tool_messages = [
            message
            for message in second_request.messages
            if message.role == MessageRole.TOOL
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(
            tool_messages[0].tool_result.output,
            19481,
        )


if __name__ == "__main__":
    unittest.main()
