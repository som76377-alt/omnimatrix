import json
import tempfile
import unittest
from pathlib import Path

from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.registry import ModelDefinition, ModelRegistry
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission
from core.tools.registry import ToolRegistry
from core.tools.implementations.calculator import CalculatorTool
from core.tools.request import ToolRequest
from core.models.messages import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelToolResult,
)
from core.models.types import (
    ModelContinuation,
    ModelToolCall,
    ModelToolDefinition,
)


class FakeModel(ModelAdapter):
    @property
    def name(self):
        return "fake-model"

    @property
    def provider(self):
        return "test"

    def generate(self, request: ModelRequest):
        return ModelResponse(
            content=f"Received: {request.messages[0].content}",
            model=self.name,
            provider=self.provider,
        )


class ToolCallingTestAdapter(ModelAdapter):
    """Deterministic adapter used to test the tool execution loop."""

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    @property
    def name(self) -> str:
        return "test-tool-model"

    @property
    def provider(self) -> str:
        return "test"

    def generate(self, request: ModelRequest) -> ModelResponse:
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
                        arguments={"expression": "2 + 2"},
                    ),
                ),
                continuation=ModelContinuation(
                    provider="test",
                    state={"interaction_id": "interaction-1"},
                ),
            )

        last_message = request.messages[-1]

        if (
            last_message.role == MessageRole.TOOL
            and last_message.tool_result is not None
            and last_message.tool_result.success
        ):
            return ModelResponse(
                content=(
                    f"The calculator returned "
                    f"{last_message.tool_result.output}."
                ),
                model=self.name,
                provider=self.provider,
            )

        raise AssertionError("Unexpected model request.")


class CoreTests(unittest.TestCase):
    def test_omnitrix_analyzes_routes_and_runs_model(self):
        registry = ModelRegistry()

        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        adapter_registry = AdapterRegistry()
        adapter_registry.register(FakeModel())

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=adapter_registry,
        )

        result = omnitrix.run("Hello Omnitrix")

        self.assertEqual(result, "Received: Hello Omnitrix")

    def test_omnitrix_can_load_models_from_config(self):
        config = {
            "models": [
                {
                    "name": "fake-model",
                    "provider": "test",
                    "capabilities": ["reasoning"],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.json"
            path.write_text(
                json.dumps(config),
                encoding="utf-8",
            )

            adapter_registry = AdapterRegistry()
            adapter_registry.register(FakeModel())

            omnitrix = Omnitrix.from_config(
                path,
                adapter_registry=adapter_registry,
            )

            result = omnitrix.run("Hello from config")

        self.assertEqual(result, "Received: Hello from config")

    def test_model_response_is_normalized(self):
        adapter = FakeModel()

        response = adapter.generate(
            ModelRequest(
                messages=(
                    ModelMessage(
                        role=MessageRole.USER,
                        content="Test prompt",
                    ),
                )
            )
        )

        self.assertEqual(response.content, "Received: Test prompt")
        self.assertEqual(response.model, "fake-model")
        self.assertEqual(response.provider, "test")

    def test_model_tool_call_stores_request(self):
        tool_call = ModelToolCall(
            id="call-1",
            tool_name="calculator",
            arguments={"expression": "6 * 7"},
        )

        self.assertEqual(tool_call.tool_name, "calculator")
        self.assertEqual(
            tool_call.arguments,
            {"expression": "6 * 7"},
        )

    def test_model_response_can_contain_tool_calls(self):
        tool_call = ModelToolCall(
            id="call-1",
            tool_name="calculator",
            arguments={"expression": "6 * 7"},
        )

        response = ModelResponse(
            content="",
            model="test-model",
            provider="test",
            tool_calls=(tool_call,),
        )

        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(
            response.tool_calls[0].tool_name,
            "calculator",
        )

    def test_model_tool_call_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            ModelToolCall(
                id="call-1",
                tool_name="",
                arguments={},
            )

    def test_model_tool_call_requires_dictionary_arguments(self):
        with self.assertRaises(TypeError):
            ModelToolCall(
                id="call-1",
                tool_name="calculator",
                arguments="6 * 7",
            )

    def test_model_tool_result_stores_result(self) -> None:
        result = ModelToolResult(
            tool_call_id="call-1",
            tool_name="calculator",
            success=True,
            output=42,
        )

        self.assertEqual(result.tool_name, "calculator")
        self.assertTrue(result.success)
        self.assertEqual(result.output, 42)

    def test_model_message_can_store_tool_result(self) -> None:
        result = ModelToolResult(
            tool_call_id="call-1",
            tool_name="calculator",
            success=True,
            output=42,
        )

        message = ModelMessage(
            role=MessageRole.TOOL,
            tool_result=result,
        )

        self.assertEqual(message.role, MessageRole.TOOL)
        self.assertEqual(message.tool_result, result)

    def test_model_message_rejects_tool_result_on_non_tool_message(self) -> None:
        result = ModelToolResult(
            tool_call_id="call-1",
            tool_name="calculator",
            success=True,
            output=42,
        )

        with self.assertRaises(ValueError):
            ModelMessage(
                role=MessageRole.USER,
                content="Calculate this.",
                tool_result=result,
            )

    def test_model_request_requires_messages(self) -> None:
        with self.assertRaises(ValueError):
            ModelRequest()

    def test_model_request_stores_messages(self) -> None:
        message = ModelMessage(
            role=MessageRole.USER,
            content="What is 2 + 2?",
        )

        request = ModelRequest(messages=(message,))

        self.assertEqual(request.messages, (message,))

    def test_omnitrix_advertises_only_authorized_tools(self) -> None:
        class InspectingAdapter(FakeModel):
            def __init__(self) -> None:
                self.requests: list[ModelRequest] = []

            def generate(self, request: ModelRequest) -> ModelResponse:
                self.requests.append(request)

                return ModelResponse(
                    content="done",
                    model=self.name,
                    provider=self.provider,
                )

        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        adapter = InspectingAdapter()
        adapters = AdapterRegistry()
        adapters.register(adapter)

        tools = build_tool_registry()

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=adapters,
            tool_registry=tools,
            tool_permission=ToolPermission.from_capabilities(
                {"calculation"}
            ),
        )

        result = omnitrix.run("Use the calculator.")

        self.assertEqual(result, "done")
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(
            adapter.requests[0].tools,
            (
                ModelToolDefinition(
                    name="calculator",
                    description="Evaluate a basic arithmetic expression.",
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "Arithmetic expression to evaluate.",
                            },
                        },
                        "required": ["expression"],
                        "additionalProperties": False,
                    },
                ),
            ),
        )

    def test_omnitrix_does_not_advertise_unauthorized_tools(self) -> None:
        class InspectingAdapter(FakeModel):
            def __init__(self) -> None:
                self.requests: list[ModelRequest] = []

            def generate(self, request: ModelRequest) -> ModelResponse:
                self.requests.append(request)

                return ModelResponse(
                    content="done",
                    model=self.name,
                    provider=self.provider,
                )

        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        adapter = InspectingAdapter()
        adapters = AdapterRegistry()
        adapters.register(adapter)

        tools = build_tool_registry()

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=adapters,
            tool_registry=tools,
            tool_permission=ToolPermission.from_capabilities(set()),
        )

        result = omnitrix.run("Use the calculator.")

        self.assertEqual(result, "done")
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(adapter.requests[0].tools, ())

    def test_omnitrix_executes_model_tool_call_loop(self) -> None:
        model = ModelDefinition(
            name="test-tool-model",
            provider="test",
            capabilities=frozenset({"reasoning"}),
        )

        registry = ModelRegistry()
        registry.register(model)

        adapter = ToolCallingTestAdapter()

        adapters = AdapterRegistry()
        adapters.register(adapter)

        tools = build_tool_registry()

        permissions = ToolPermission.from_capabilities({"calculation"})

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=adapters,
            tool_registry=tools,
            tool_permission=permissions,
        )

        result = omnitrix.run("Calculate 2 + 2.")

        self.assertEqual(
            result,
            "The calculator returned 4.",
        )

        self.assertEqual(len(adapter.requests), 2)

        first_request = adapter.requests[0]

        self.assertEqual(
            first_request.messages[0].role,
            MessageRole.USER,
        )

        second_request = adapter.requests[1]

        self.assertEqual(
            second_request.continuation,
            ModelContinuation(
                provider="test",
                state={"interaction_id": "interaction-1"},
            ),
        )

        self.assertEqual(
            len(second_request.messages),
            3,
        )

        self.assertEqual(
            second_request.messages[0].role,
            MessageRole.USER,
        )

        self.assertEqual(
            second_request.messages[1].role,
            MessageRole.ASSISTANT,
        )

        self.assertEqual(
            second_request.messages[1].tool_calls,
            (
                ModelToolCall(
                    id="call-1",
                    tool_name="calculator",
                    arguments={"expression": "2 + 2"},
                ),
            ),
        )

        self.assertEqual(
            second_request.messages[2].role,
            MessageRole.TOOL,
        )

        self.assertEqual(
            second_request.messages[2].tool_result,
            ModelToolResult(
                tool_call_id="call-1",
                tool_name="calculator",
                success=True,
                output=4,
            ),
        )

    def test_omnitrix_preserves_tool_definitions_across_tool_rounds(self) -> None:
        model = ModelDefinition(
            name="test-tool-model",
            provider="test",
            capabilities=frozenset({"reasoning"}),
        )

        registry = ModelRegistry()
        registry.register(model)

        adapter = ToolCallingTestAdapter()

        adapters = AdapterRegistry()
        adapters.register(adapter)

        tools = build_tool_registry()

        permissions = ToolPermission.from_capabilities({"calculation"})

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=adapters,
            tool_registry=tools,
            tool_permission=permissions,
        )

        omnitrix.run("Calculate 2 + 2.")

        self.assertEqual(len(adapter.requests), 2)
        self.assertEqual(
            adapter.requests[0].tools,
            adapter.requests[1].tools,
        )
        self.assertEqual(
            adapter.requests[1].tools[0].name,
            "calculator",
        )

    def test_omnitrix_executes_multiple_tool_calls_in_one_round(self):
        class MultiToolCallingAdapter(FakeModel):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def generate(self, request: ModelRequest) -> ModelResponse:
                self.calls += 1

                if self.calls == 1:
                    return ModelResponse(
                        content="",
                        model=self.name,
                        provider="test",
                        tool_calls=(
                            ModelToolCall(
                                id="call-1",
                                tool_name="calculator",
                                arguments={"expression": "2 + 2"},
                            ),
                            ModelToolCall(
                                id="call-2",
                                tool_name="calculator",
                                arguments={"expression": "3 * 3"},
                            ),
                        ),
                    )

                assert len(request.messages) == 4
                assert request.messages[2].tool_result is not None
                assert request.messages[3].tool_result is not None
                assert float(request.messages[2].tool_result.output) == 4.0
                assert float(request.messages[3].tool_result.output) == 9.0

                return ModelResponse(
                    content="Both calculations completed.",
                    model=self.name,
                    provider="test",
                )

        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        adapter = MultiToolCallingAdapter()
        adapters = AdapterRegistry()
        adapters.register(adapter)

        tools = ToolRegistry()
        tools.register(CalculatorTool())

        permission = ToolPermission.from_capabilities({"calculation"})

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=adapters,
            tool_registry=tools,
            tool_permission=permission,
        )

        result = omnitrix.run("Calculate 2 + 2 and 3 * 3.")

        self.assertEqual(result, "Both calculations completed.")

    def test_omnitrix_allows_final_response_after_max_tool_iterations(self):
        class BoundaryAdapter:
            name = "boundary-model"
            provider = "test"

            def __init__(self):
                self.calls = 0

            def generate(self, request):
                self.calls += 1

                if self.calls <= 2:
                    return ModelResponse(
                        content="",
                        model=self.name,
                        provider=self.provider,
                        tool_calls=(
                            ModelToolCall(
                                id=f"call-{self.calls}",
                                tool_name="calculator",
                                arguments={"expression": "1 + 1"},
                            ),
                        ),
                    )

                return ModelResponse(
                    content="Final answer after two tool rounds.",
                    model=self.name,
                    provider=self.provider,
                )

        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="boundary-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        adapters = AdapterRegistry()
        adapter = BoundaryAdapter()
        adapters.register(adapter)

        tools = ToolRegistry()
        tools.register(CalculatorTool())

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=adapters,
            tool_registry=tools,
            tool_permission=ToolPermission.from_capabilities({"calculation"}),
            max_tool_iterations=2,
        )

        result = omnitrix.run("Calculate something and give me the final answer.")

        self.assertEqual(result, "Final answer after two tool rounds.")
        self.assertEqual(adapter.calls, 3)


    def test_omnitrix_stops_excessive_tool_iterations(self):
        class LoopingAdapter(FakeModel):
            def generate(self, request: ModelRequest) -> ModelResponse:
                return ModelResponse(
                    content="",
                    model=self.name,
                    provider="test",
                    tool_calls=(
                        ModelToolCall(
                            id="loop-call",
                            tool_name="calculator",
                            arguments={"expression": "1 + 1"},
                        ),
                    ),
                )

        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        adapters = AdapterRegistry()
        adapters.register(LoopingAdapter())

        tools = ToolRegistry()
        tools.register(CalculatorTool())

        permission = ToolPermission.from_capabilities({"calculation"})

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=adapters,
            tool_registry=tools,
            tool_permission=permission,
            max_tool_iterations=2,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Maximum tool-call iterations exceeded.",
        ):
            omnitrix.run("Keep calculating.")

    def test_omnitrix_rejects_invalid_tool_iteration_limit(self):
        registry = ModelRegistry()

        with self.assertRaises(ValueError):
            Omnitrix(registry=registry, max_tool_iterations=0)

        with self.assertRaises(ValueError):
            Omnitrix(registry=registry, max_tool_iterations=-1)

        with self.assertRaises(TypeError):
            Omnitrix(registry=registry, max_tool_iterations=True)

    def test_missing_adapter_fails_cleanly(self):
        registry = ModelRegistry()

        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=AdapterRegistry(),
        )

        with self.assertRaises(LookupError):
            omnitrix.run("Hello Omnitrix")

    def test_omnitrix_from_config_builds_gemini_adapter(self):
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            encoding="utf-8",
        ) as file:
            json.dump(
                {
                    "models": [
                        {
                            "name": "gemini-primary",
                            "provider": "google",
                            "model_id": "gemini-test-model",
                            "capabilities": [
                                "reasoning",
                                "coding",
                            ],
                            "context_window": 32000,
                            "enabled": True,
                        }
                    ]
                },
                file,
            )
            file.flush()

            omnitrix = Omnitrix.from_config(file.name)

        self.assertTrue(
            omnitrix.adapter_registry.has("gemini-primary")
        )

        adapter = omnitrix.adapter_registry.get("gemini-primary")

        self.assertEqual(adapter.name, "gemini-primary")
        self.assertEqual(adapter.provider, "google")

    def test_omnitrix_executes_authorized_tool(self):
        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=AdapterRegistry(),
            tool_registry=build_tool_registry(),
            tool_permission=ToolPermission.from_capabilities({"calculation"}),
        )

        result = omnitrix.execute_tool(
            ToolRequest(
                tool_name="calculator",
                arguments={"expression": "6 * 7"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, 42)

    def test_omnitrix_rejects_unauthorized_tool(self):
        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=AdapterRegistry(),
            tool_registry=build_tool_registry(),
            tool_permission=ToolPermission.from_capabilities(set()),
        )

        result = omnitrix.execute_tool(
            ToolRequest(
                tool_name="calculator",
                arguments={"expression": "6 * 7"},
            )
        )

        self.assertFalse(result.success)
        self.assertIn("Permission denied", result.error)


    def test_model_request_stores_tool_definitions(self):
        tool = ModelToolDefinition(
            name="calculator",
            description="Evaluate arithmetic expressions.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                },
                "required": ["expression"],
            },
        )

        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Calculate 2 + 2",
                ),
            ),
            tools=(tool,),
        )

        self.assertEqual(request.tools, (tool,))
        self.assertEqual(request.tools[0].name, "calculator")

    def test_model_request_rejects_duplicate_tool_names(self):
        first = ModelToolDefinition(
            name="calculator",
            description="First calculator.",
            parameters_schema={"type": "object"},
        )

        second = ModelToolDefinition(
            name="calculator",
            description="Second calculator.",
            parameters_schema={"type": "object"},
        )

        with self.assertRaises(ValueError):
            ModelRequest(
                messages=(
                    ModelMessage(
                        role=MessageRole.USER,
                        content="Calculate something",
                    ),
                ),
                tools=(first, second),
            )


if __name__ == "__main__":
    unittest.main()
