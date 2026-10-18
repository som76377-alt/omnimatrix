import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from core.models.base import (
    ModelAuthenticationError,
    ModelRequestError,
    ModelResponseError,
)
from core.models.messages import MessageRole, ModelMessage, ModelRequest, ModelToolResult
from core.models.providers.openrouter import OpenRouterAdapter
from core.models.types import ModelToolCall, ModelToolDefinition


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class OpenRouterAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = OpenRouterAdapter(
            name="openrouter-test",
            model_id="nvidia/nemotron-3-super-120b-a12b:free",
            api_key="test-key",
        )

    def test_builds_system_messages_tool_calls_and_tool_results(self):
        request = ModelRequest(
            instructions="System instruction",
            messages=(
                ModelMessage(role=MessageRole.USER, content="Inspect this file."),
                ModelMessage(
                    role=MessageRole.ASSISTANT,
                    content="I will inspect it.",
                    tool_calls=(
                        ModelToolCall(
                            id="call-1",
                            tool_name="workspace.inspect",
                            arguments={"path": "README.md"},
                        ),
                    ),
                ),
                ModelMessage(
                    role=MessageRole.TOOL,
                    tool_result=ModelToolResult(
                        tool_call_id="call-1",
                        tool_name="workspace.inspect",
                        success=True,
                        output={"contents": "sample"},
                    ),
                ),
            ),
            tools=(
                ModelToolDefinition(
                    name="workspace.inspect",
                    description="Read a bounded text file",
                    parameters_schema={"type": "object", "properties": {"path": {"type": "string"}}},
                ),
            ),
        )

        payload = self.adapter._build_payload(request)
        self.assertEqual(payload["messages"][0], {
            "role": "system", "content": "System instruction"
        })
        self.assertEqual(payload["messages"][1]["role"], "user")
        self.assertEqual(
            payload["messages"][2]["tool_calls"][0]["function"]["name"],
            "workspace.inspect",
        )
        self.assertEqual(payload["messages"][3]["tool_call_id"], "call-1")
        self.assertEqual(json.loads(payload["messages"][3]["content"]), {"contents": "sample"})
        self.assertEqual(payload["tools"][0]["function"]["name"], "workspace.inspect")

    def test_normalizes_text_and_tool_call_response(self):
        body = {
            "model": self.adapter._model_id,
            "choices": [{
                "message": {
                    "content": "Calling a tool.",
                    "tool_calls": [{
                        "id": "call-2",
                        "type": "function",
                        "function": {
                            "name": "workspace.inspect",
                            "arguments": '{"path":"README.md"}',
                        },
                    }],
                },
            }],
            "usage": {"prompt_tokens": 23, "completion_tokens": 7},
        }
        with patch(
            "core.models.providers.openrouter.urlopen",
            return_value=FakeResponse(body),
        ):
            response = self.adapter.generate(
                ModelRequest(messages=(ModelMessage(role=MessageRole.USER, content="Read README."),))
            )
        self.assertEqual(response.provider, "openrouter")
        self.assertEqual(response.content, "Calling a tool.")
        self.assertEqual(response.tool_calls[0].arguments, {"path": "README.md"})
        self.assertEqual(response.usage["prompt_tokens"], 23)
        self.assertIsNone(response.continuation)

    def test_rejects_non_object_tool_arguments(self):
        with self.assertRaisesRegex(ModelResponseError, "arguments must be a JSON object"):
            self.adapter._extract_tool_calls([{
                "id": "call-3",
                "function": {"name": "workspace.inspect", "arguments": "[]"},
            }])

    def test_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            adapter = OpenRouterAdapter(
                name="openrouter-no-key",
                model_id="nvidia/nemotron-3-super-120b-a12b:free",
            )
            self.assertFalse(adapter.is_available())
            with self.assertRaises(ModelAuthenticationError):
                adapter.generate(
                    ModelRequest(messages=(ModelMessage(role=MessageRole.USER, content="Hi"),))
                )

    def test_authentication_error_does_not_expose_response_body(self):
        response = HTTPError(
            url=self.adapter.endpoint,
            code=401,
            msg="Unauthorised",
            hdrs=None,
            fp=BytesIO(b"body should not leak user prompt"),
        )
        with patch("core.models.providers.openrouter.urlopen", side_effect=response):
            with self.assertRaises(ModelAuthenticationError) as raised:
                self.adapter.generate(
                    ModelRequest(messages=(ModelMessage(role=MessageRole.USER, content="Hi"),))
                )
        self.assertNotIn("body should not leak", str(raised.exception))

    def test_rate_limit_is_a_request_error_without_automatic_retries(self):
        response = HTTPError(
            url=self.adapter.endpoint,
            code=429,
            msg="Rate limit",
            hdrs=None,
            fp=BytesIO(b"private provider response body"),
        )
        with patch("core.models.providers.openrouter.urlopen", side_effect=response) as mocked:
            with self.assertRaises(ModelRequestError) as raised:
                self.adapter.generate(
                    ModelRequest(messages=(ModelMessage(role=MessageRole.USER, content="Hi"),))
                )
        mocked.assert_called_once()
        self.assertIn("HTTP 429", str(raised.exception))
        self.assertNotIn("private provider response", str(raised.exception))

    def test_invalid_response_json_is_rejected(self):
        with patch(
            "core.models.providers.openrouter.urlopen",
            return_value=FakeResponse({"not_choices": []}),
        ):
            with self.assertRaisesRegex(ModelResponseError, "valid choice"):
                self.adapter.generate(
                    ModelRequest(messages=(ModelMessage(role=MessageRole.USER, content="Hi"),))
                )


if __name__ == "__main__":
    unittest.main()
