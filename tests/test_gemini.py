import json
import os
import unittest
from unittest.mock import patch

from core.models.base import (
    ModelAuthenticationError,
    ModelResponseError,
)
from core.models.messages import MessageRole, ModelMessage, ModelRequest, ModelToolResult
from core.models.providers.gemini import GeminiAdapter
from core.models.types import ModelContinuation, ModelToolCall, ModelToolDefinition


class FakeHTTPResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class GeminiAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = GeminiAdapter(
            name="gemini-primary",
            model_id="gemini-3.8-flash",
            api_key="test-key",
        )

    def test_successfully_normalizes_response(self):
        payload = {
            "id": "interaction-123",
            "model": "gemini-3.8-flash",
            "steps": [
                {
                    "type": "model_output",
                    "content": [
                        {
                            "type": "text",
                            "text": "Hello from Gemini.",
                        }
                    ],
                }
            ],
            "usage": {
                "total_tokens": 12,
            },
        }

        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Hello Omnitrix",
                ),
            )
        )

        with patch(
            "core.models.providers.gemini.urlopen",
            return_value=FakeHTTPResponse(payload),
        ):
            response = self.adapter.generate(request)

        self.assertEqual(response.content, "Hello from Gemini.")
        self.assertEqual(response.model, "gemini-3.8-flash")
        self.assertEqual(response.provider, "google")
        self.assertEqual(response.usage["total_tokens"], 12)
        self.assertIsNotNone(response.continuation)
        self.assertEqual(response.continuation.provider, "google")
        self.assertEqual(
            response.continuation.state["interaction_id"],
            "interaction-123",
        )
        self.assertEqual(response.tool_calls, ())

    def test_missing_api_key_fails(self):
        adapter = GeminiAdapter(
            name="gemini-primary",
            model_id="gemini-3.8-flash",
            api_key_env="OMNITRIX_TEST_MISSING_KEY",
        )

        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Hello Omnitrix",
                ),
            )
        )

        with patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            with self.assertRaises(ModelAuthenticationError):
                adapter.generate(request)

    def test_invalid_response_fails(self):
        fake_response = FakeHTTPResponse(
            {
                "model": "gemini-3.8-flash",
                "steps": [],
            }
        )

        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Hello Omnitrix",
                ),
            )
        )

        with patch(
            "core.models.providers.gemini.urlopen",
            return_value=fake_response,
        ):
            with self.assertRaises(ModelResponseError):
                self.adapter.generate(request)


    def test_extracts_native_function_call(self):
        payload = {
            "id": "interaction-tool-1",
            "model": "gemini-3.8-flash",
            "steps": [
                {
                    "type": "function_call",
                    "id": "call-1",
                    "name": "calculator",
                    "arguments": {
                        "expression": "2 + 2",
                    },
                }
            ],
        }

        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Calculate 2 + 2.",
                ),
            ),
            tools=(
                ModelToolDefinition(
                    name="calculator",
                    description="Evaluate arithmetic.",
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                            },
                        },
                        "required": ["expression"],
                    },
                ),
            ),
        )

        with patch(
            "core.models.providers.gemini.urlopen",
            return_value=FakeHTTPResponse(payload),
        ):
            response = self.adapter.generate(request)

        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(response.tool_calls[0].id, "call-1")
        self.assertEqual(response.tool_calls[0].tool_name, "calculator")
        self.assertEqual(
            response.tool_calls[0].arguments,
            {"expression": "2 + 2"},
        )
        self.assertEqual(response.content, "")

    def test_builds_native_gemini_tool_payload(self):
        captured = {}

        class CapturingResponse(FakeHTTPResponse):
            pass

        def fake_urlopen(request, timeout):
            captured["request"] = request

            return CapturingResponse(
                {
                    "id": "interaction-tool-schema",
                    "model": "gemini-3.8-flash",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Done.",
                                }
                            ],
                        }
                    ],
                }
            )

        model_tool = ModelToolDefinition(
            name="calculator",
            description="Evaluate arithmetic.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                    },
                },
                "required": ["expression"],
                "additionalProperties": False,
            },
        )

        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Calculate something.",
                ),
            ),
            tools=(model_tool,),
        )

        with patch(
            "core.models.providers.gemini.urlopen",
            side_effect=fake_urlopen,
        ):
            self.adapter.generate(request)

        body = json.loads(captured["request"].data.decode("utf-8"))

        self.assertEqual(body["model"], "gemini-3.8-flash")
        self.assertEqual(body["input"], "Calculate something.")
        self.assertEqual(
            body["tools"],
            [
                {
                    "type": "function",
                    "name": "calculator",
                    "description": "Evaluate arithmetic.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                            },
                        },
                        "required": ["expression"],
                        "additionalProperties": False,
                    },
                }
            ],
        )

    def test_builds_function_result_from_continuation(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request

            return FakeHTTPResponse(
                {
                    "id": "interaction-tool-result",
                    "model": "gemini-3.8-flash",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "The answer is 4.",
                                }
                            ],
                        }
                    ],
                }
            )

        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Calculate 2 + 2.",
                ),
                ModelMessage(
                    role=MessageRole.ASSISTANT,
                    content="",
                    tool_calls=(
                        ModelToolCall(
                            id="call-1",
                            tool_name="calculator",
                            arguments={"expression": "2 + 2"},
                        ),
                    ),
                ),
                ModelMessage(
                    role=MessageRole.TOOL,
                    tool_result=ModelToolResult(
                        tool_call_id="call-1",
                        tool_name="calculator",
                        success=True,
                        output=4,
                    ),
                ),
            ),
            tools=(
                ModelToolDefinition(
                    name="calculator",
                    description="Evaluate arithmetic.",
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                            },
                        },
                    },
                ),
            ),
            continuation=ModelContinuation(
                provider="google",
                state={
                    "interaction_id": "interaction-tool-1",
                },
            ),
        )

        with patch(
            "core.models.providers.gemini.urlopen",
            side_effect=fake_urlopen,
        ):
            response = self.adapter.generate(request)

        body = json.loads(captured["request"].data.decode("utf-8"))

        self.assertEqual(
            body["previous_interaction_id"],
            "interaction-tool-1",
        )
        self.assertEqual(
            body["input"],
            [
                {
                    "type": "function_result",
                    "name": "calculator",
                    "call_id": "call-1",
                    "result": [
                        {
                            "type": "text",
                            "text": "4",
                        }
                    ],
                }
            ],
        )
        self.assertEqual(response.content, "The answer is 4.")

    def test_continuation_sends_only_latest_tool_round_results(self):
        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Perform two calculations.",
                ),
                ModelMessage(
                    role=MessageRole.ASSISTANT,
                    tool_calls=(
                        ModelToolCall(
                            id="call-1",
                            tool_name="calculator",
                            arguments={"expression": "2 + 2"},
                        ),
                    ),
                ),
                ModelMessage(
                    role=MessageRole.TOOL,
                    tool_result=ModelToolResult(
                        tool_call_id="call-1",
                        tool_name="calculator",
                        success=True,
                        output=4,
                    ),
                ),
                ModelMessage(
                    role=MessageRole.ASSISTANT,
                    tool_calls=(
                        ModelToolCall(
                            id="call-2",
                            tool_name="calculator",
                            arguments={"expression": "3 + 3"},
                        ),
                    ),
                ),
                ModelMessage(
                    role=MessageRole.TOOL,
                    tool_result=ModelToolResult(
                        tool_call_id="call-2",
                        tool_name="calculator",
                        success=True,
                        output=6,
                    ),
                ),
            ),
            tools=(
                ModelToolDefinition(
                    name="calculator",
                    description="Evaluate arithmetic.",
                    parameters_schema={
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"},
                        },
                    },
                ),
            ),
            continuation=ModelContinuation(
                provider="google",
                state={"interaction_id": "interaction-round-2"},
            ),
        )

        captured = {}

        def fake_urlopen(http_request, timeout):
            captured["request"] = http_request
            return FakeHTTPResponse(
                {
                    "id": "interaction-round-3",
                    "model": "gemini-3.8-flash",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Done.",
                                }
                            ],
                        }
                    ],
                }
            )

        with patch(
            "core.models.providers.gemini.urlopen",
            side_effect=fake_urlopen,
        ):
            self.adapter.generate(request)

        body = json.loads(captured["request"].data.decode("utf-8"))

        self.assertEqual(body["previous_interaction_id"], "interaction-round-2")
        self.assertEqual(
            body["input"],
            [
                {
                    "type": "function_result",
                    "name": "calculator",
                    "call_id": "call-2",
                    "result": [
                        {
                            "type": "text",
                            "text": "6",
                        }
                    ],
                }
            ],
        )

    def test_adapter_properties(self):
        self.assertEqual(self.adapter.name, "gemini-primary")
        self.assertEqual(self.adapter.provider, "google")


if __name__ == "__main__":
    unittest.main()
