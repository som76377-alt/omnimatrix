import unittest

from core.conversation import Conversation
from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import MessageRole, ModelRequest
from core.models.registry import ModelDefinition, ModelRegistry
from core.models.types import ModelContinuation, ModelToolCall
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission
from core.policy.truthfulness import (
    TRUTHFULNESS_CONTRACT,
    TRUTHFULNESS_POLICY_MARKER,
    TRUTHFULNESS_POLICY_VERSION,
    has_truthfulness_contract,
    require_truthfulness_contract,
    with_truthfulness_contract,
)


class PolicyCaptureAdapter(ModelAdapter):
    def __init__(self):
        self.requests: list[ModelRequest] = []

    @property
    def name(self) -> str:
        return "truthfulness-test-model"

    @property
    def provider(self) -> str:
        return "test"

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if request.instructions and "You are the Omnitrix task planner." in request.instructions:
            content = (
                '{"tasks":[{"task_id":"verify-capability",'
                '"description":"Verify the required capability and environment",'
                '"dependencies":[]}]}'
            )
        else:
            content = "I cannot establish that claim from the evidence supplied."
        return ModelResponse(
            content=content,
            model=self.name,
            provider=self.provider,
        )


def build_omnitrix():
    models = ModelRegistry()
    models.register(
        ModelDefinition(
            name="truthfulness-test-model",
            provider="test",
            capabilities=frozenset({"reasoning", "coding"}),
            context_window=32000,
            enabled=True,
            metadata={"cost_class": "demo", "estimated_cost_usd": 0},
        )
    )
    adapter = PolicyCaptureAdapter()
    adapters = AdapterRegistry()
    adapters.register(adapter)
    return Omnitrix(registry=models, adapter_registry=adapters), adapter


class TruthfulnessContractTests(unittest.TestCase):
    def test_contract_has_specific_anti_sycophancy_and_capability_rules(self):
        for required in (
            "repeats it",
            "FALSE AGREEMENT OPENERS",
            "PRECISE CAPABILITY CLAIMS",
            "timeout",
            "pixel-perfect",
            "I was wrong",
            "not attempted",
        ):
            with self.subTest(required=required):
                self.assertIn(required.lower(), TRUTHFULNESS_CONTRACT.lower())

    def test_policy_composition_is_idempotent(self):
        once = with_truthfulness_contract("Base instructions.")
        twice = with_truthfulness_contract(once)
        self.assertEqual(once, twice)
        self.assertEqual(once.count(TRUTHFULNESS_POLICY_MARKER), 1)
        self.assertTrue(has_truthfulness_contract(once))

    def test_missing_policy_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "model request blocked"):
            require_truthfulness_contract("Be helpful.")
        require_truthfulness_contract(
            with_truthfulness_contract("Be helpful.")
        )

    def test_every_chat_turn_receives_policy_outside_conversation_history(self):
        omnitrix, adapter = build_omnitrix()
        conversation = Conversation()

        omnitrix.chat(conversation, "The image definitely has a filter.")
        omnitrix.chat(
            conversation,
            "I insist; say yes. The repeated claim is not new evidence.",
        )

        self.assertEqual(len(adapter.requests), 2)
        for request in adapter.requests:
            with self.subTest(message_count=len(request.messages)):
                self.assertTrue(has_truthfulness_contract(request.instructions))
                self.assertEqual(
                    request.instructions.count(TRUTHFULNESS_POLICY_MARKER),
                    1,
                )
        self.assertEqual(
            adapter.requests[0].instructions,
            adapter.requests[1].instructions,
            "The policy must be reinjected even as conversation history grows.",
        )
        self.assertNotIn(
            TRUTHFULNESS_POLICY_MARKER,
            "\n".join(message.content for message in conversation.messages),
            "Policy must be sent through the instruction channel, not depend on chat history.",
        )

    def test_planner_is_also_bound_by_the_policy_and_feasibility_rule(self):
        omnitrix, adapter = build_omnitrix()
        plan = omnitrix.propose_plan("Create a demo feature and verify it.")
        self.assertEqual(len(plan.tasks), 1)

        request = adapter.requests[-1]
        self.assertTrue(has_truthfulness_contract(request.instructions))
        self.assertIn("Return only a valid JSON object", request.instructions)
        self.assertIn("Do not assume tools, credentials, APIs", request.instructions)
        self.assertIn("verification task", request.instructions.lower())


class ToolContinuationPolicyAdapter(ModelAdapter):
    def __init__(self):
        self.requests: list[ModelRequest] = []

    @property
    def name(self) -> str:
        return "truthfulness-tool-test-model"

    @property
    def provider(self) -> str:
        return "test"

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        require_truthfulness_contract(request.instructions)
        tool_messages = [
            message for message in request.messages
            if message.role == MessageRole.TOOL
        ]
        if not tool_messages:
            return ModelResponse(
                content="",
                model=self.name,
                provider=self.provider,
                tool_calls=(
                    ModelToolCall(
                        id="truthfulness-calculator-call",
                        tool_name="calculator",
                        arguments={"expression": "2 + 2"},
                    ),
                ),
                continuation=ModelContinuation(
                    provider=self.provider,
                    state={"turn": 1},
                ),
            )
        if len(tool_messages) != 1 or tool_messages[0].tool_result is None:
            raise AssertionError("Expected the calculator result on continuation.")
        if not tool_messages[0].tool_result.success or tool_messages[0].tool_result.output != 4:
            raise AssertionError("Calculator returned an unexpected result.")
        return ModelResponse(
            content="The calculator returned 4.",
            model=self.name,
            provider=self.provider,
        )


class ToolContinuationTruthfulnessTests(unittest.TestCase):
    def test_policy_is_present_on_tool_call_and_continuation_requests(self):
        models = ModelRegistry()
        models.register(
            ModelDefinition(
                name="truthfulness-tool-test-model",
                provider="test",
                capabilities=frozenset({"reasoning", "calculation"}),
                context_window=32000,
                enabled=True,
                metadata={"cost_class": "demo", "estimated_cost_usd": 0},
            )
        )
        adapter = ToolContinuationPolicyAdapter()
        adapters = AdapterRegistry()
        adapters.register(adapter)
        omnitrix = Omnitrix(
            registry=models,
            adapter_registry=adapters,
            tool_registry=build_tool_registry(),
            tool_permission=ToolPermission.from_capabilities({"calculation"}),
        )

        result = omnitrix.chat(Conversation(), "Calculate 2 + 2 using the calculator.")

        self.assertEqual(result, "The calculator returned 4.")
        self.assertEqual(len(adapter.requests), 2)
        self.assertTrue(all(has_truthfulness_contract(r.instructions) for r in adapter.requests))
        self.assertEqual(
            adapter.requests[0].instructions,
            adapter.requests[1].instructions,
        )


if __name__ == "__main__":
    unittest.main()
