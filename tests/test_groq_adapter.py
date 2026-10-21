import json
import os
import unittest
from unittest.mock import MagicMock, patch

from core.models.base import ModelResponseError
from core.models.messages import MessageRole, ModelMessage, ModelRequest
from core.models.providers.groq import GroqAdapter


class GroqAdapterTests(unittest.TestCase):
    def make_adapter(self, model_id="openai/gpt-oss-120b"):
        return GroqAdapter(
            name="groq-test",
            model_id=model_id,
            api_key_env="TEST_GROQ_KEY",
            max_output_tokens=16,
            timeout=3,
            referer=None,
            title="Omnitrix",
        )

    def make_request(self):
        return ModelRequest(
            messages=(ModelMessage(role=MessageRole.USER, content="Reply ROUTE_READY."),),
        )

    def test_uses_groq_endpoint_and_gpt_oss_compatible_reasoning_fields(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "model": "openai/gpt-oss-120b",
            "choices": [{
                "message": {
                    "content": "ROUTE_READY",
                    "reasoning": "private reasoning must not be returned",
                },
            }],
            "usage": {"prompt_tokens": 8, "completion_tokens": 1},
        }).encode()

        adapter = self.make_adapter()
        with patch.dict(os.environ, {
            "TEST_GROQ_KEY": "unit-test-key",
            "GROQ_FREE_QUOTA_CONFIRMED": "true",
        }):
            with patch("core.models.providers.groq.urlopen", return_value=response) as send:
                result = adapter.generate(self.make_request())

        http_request = send.call_args.args[0]
        body = json.loads(http_request.data.decode("utf-8"))
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertIs(body["include_reasoning"], False)
        self.assertNotIn("reasoning_format", body)
        self.assertNotIn("reasoning", body)
        self.assertEqual(http_request.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(http_request.get_header("Authorization"), "Bearer unit-test-key")
        self.assertIsNone(http_request.get_header("X-title"))
        self.assertEqual(result.provider, "groq")
        self.assertEqual(result.model, "openai/gpt-oss-120b")
        self.assertEqual(result.model_identity_source, "provider_response")
        self.assertEqual(result.content, "ROUTE_READY")
        self.assertNotIn("private reasoning", result.content)

    def test_empty_final_content_does_not_fall_back_to_reasoning_field(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "model": "openai/gpt-oss-20b",
            "choices": [{
                "message": {
                    "content": None,
                    "reasoning": "this is not the final answer",
                },
            }],
        }).encode()
        adapter = self.make_adapter("openai/gpt-oss-20b")
        with patch.dict(os.environ, {
            "TEST_GROQ_KEY": "unit-test-key",
            "GROQ_FREE_QUOTA_CONFIRMED": "true",
        }):
            with patch("core.models.providers.groq.urlopen", return_value=response):
                with self.assertRaisesRegex(ModelResponseError, "no final answer text"):
                    adapter.generate(self.make_request())

    def test_missing_groq_key_fails_before_network_call(self):
        adapter = self.make_adapter("openai/gpt-oss-20b")
        with patch.dict(os.environ, {"GROQ_FREE_QUOTA_CONFIRMED": "true"}, clear=True):
            with patch("core.models.providers.groq.urlopen") as send:
                with self.assertRaisesRegex(Exception, "Groq API key not found"):
                    adapter.generate(self.make_request())
                send.assert_not_called()

    def test_gpt_oss_reasoning_fields_are_not_applied_to_other_models(self):
        adapter = self.make_adapter("qwen/qwen3.8-27b")
        payload = adapter._build_payload(self.make_request())
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["reasoning_format"], "hidden")
        self.assertNotIn("include_reasoning", payload)


if __name__ == "__main__":
    unittest.main()
