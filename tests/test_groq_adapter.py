import json
import os
import unittest
from unittest.mock import MagicMock, patch

from core.models.messages import MessageRole, ModelMessage, ModelRequest
from core.models.providers.groq import GroqAdapter


class GroqAdapterTests(unittest.TestCase):
    def test_uses_groq_endpoint_bearer_key_and_provider_reported_model(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "model": "openai/gpt-oss-120b",
            "choices": [{
                "message": {"content": "ROUTE_READY"},
            }],
            "usage": {"prompt_tokens": 8, "completion_tokens": 1},
        }).encode()

        adapter = GroqAdapter(
            name="groq-gpt-oss-120b",
            model_id="openai/gpt-oss-120b",
            api_key_env="TEST_GROQ_KEY",
            max_output_tokens=16,
            timeout=3,
            referer=None,
            title="Omnitrix",
        )
        request = ModelRequest(
            messages=(ModelMessage(role=MessageRole.USER, content="Reply ROUTE_READY."),),
        )
        with patch.dict(os.environ, {"TEST_GROQ_KEY": "unit-test-key"}):
            with patch("core.models.providers.groq.urlopen", return_value=response) as send:
                result = adapter.generate(request)

        http_request = send.call_args.args[0]
        self.assertEqual(http_request.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(http_request.get_header("Authorization"), "Bearer unit-test-key")
        self.assertIsNone(http_request.get_header("X-title"))
        self.assertEqual(result.provider, "groq")
        self.assertEqual(result.model, "openai/gpt-oss-120b")
        self.assertEqual(result.model_identity_source, "provider_response")
        self.assertEqual(result.content, "ROUTE_READY")

    def test_missing_groq_key_fails_before_network_call(self):
        adapter = GroqAdapter(
            name="groq-test",
            model_id="openai/gpt-oss-20b",
            api_key_env="OMNITRIX_TEST_MISSING_GROQ_KEY",
            timeout=1,
        )
        with patch.dict(os.environ, {}, clear=True):
            with patch("core.models.providers.groq.urlopen") as send:
                with self.assertRaisesRegex(Exception, "Groq API key not found"):
                    adapter.generate(ModelRequest(
                        messages=(ModelMessage(role=MessageRole.USER, content="Hello"),),
                    ))
                send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
