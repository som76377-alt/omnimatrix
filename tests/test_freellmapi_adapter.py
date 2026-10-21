import json
import os
import unittest
from unittest.mock import MagicMock, patch

from core.models.base import ModelResponseError
from core.models.messages import MessageRole, ModelMessage, ModelRequest
from core.models.providers.freellmapi import FreeLLMAPIAdapter


class FreeLLMAPIAdapterTests(unittest.TestCase):
    def request(self):
        return ModelRequest(
            messages=(ModelMessage(role=MessageRole.USER, content="Reply ROUTE_READY."),),
        )

    def adapter(self, model_id="auto:balanced", base_url="http://127.0.0.1:3001/v1"):
        return FreeLLMAPIAdapter(
            name="freellmapi-auto-balanced",
            model_id=model_id,
            api_key_env="TEST_FREELLMAPI_KEY",
            base_url=base_url,
            timeout=3,
            max_output_tokens=32,
        )

    def mock_response(self, model="minimax/minimax-m3.1-flash:free", content="ROUTE_READY"):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({
            "model": model,
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 1},
        }).encode("utf-8")
        return response

    def test_local_gateway_uses_bearer_key_and_actual_routed_identity(self):
        adapter = self.adapter()
        with patch.dict(os.environ, {
            "TEST_FREELLMAPI_KEY": "freellmapi-test-key",
            "FREELLMAPI_ALLOWED_MODEL_IDS": "auto:balanced,minimax/minimax-m3.1-flash:free",
        }):
            with patch("core.models.providers.openrouter.urlopen", return_value=self.mock_response()) as send:
                result = adapter.generate(self.request())

        request = send.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "http://127.0.0.1:3001/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer freellmapi-test-key")
        self.assertIsNone(request.get_header("Http-referer"))
        self.assertEqual(payload["model"], "auto:balanced")
        self.assertNotIn("reasoning", payload)
        self.assertEqual(result.provider, "freellmapi")
        self.assertEqual(result.model, "minimax/minimax-m3.1-flash:free")
        self.assertEqual(result.model_identity_source, "provider_response")
        self.assertEqual(result.content, "ROUTE_READY")

    def test_rejects_model_identity_outside_the_runtime_allowlist(self):
        adapter = self.adapter()
        with patch.dict(os.environ, {
            "TEST_FREELLMAPI_KEY": "freellmapi-test-key",
            "FREELLMAPI_ALLOWED_MODEL_IDS": "auto:balanced,minimax/minimax-m3.1-flash:free",
        }):
            with patch("core.models.providers.openrouter.urlopen",
                       return_value=self.mock_response(model="some/paid-model")):
                with self.assertRaisesRegex(ModelResponseError, "outside Omnitrix"):
                    adapter.generate(self.request())

    def test_rejects_plain_http_for_non_loopback_hosts(self):
        with self.assertRaisesRegex(ValueError, "must use HTTPS"):
            self.adapter(base_url="http://gateway.example.com/v1")

    def test_accepts_https_remote_base_url_and_local_http_only(self):
        remote = self.adapter(base_url="https://gateway.example.com/v1")
        local = self.adapter(base_url="http://localhost:3001/v1")
        self.assertEqual(remote.endpoint, "https://gateway.example.com/v1/chat/completions")
        self.assertEqual(local.endpoint, "http://localhost:3001/v1/chat/completions")

    def test_requires_api_key_and_does_not_claim_live_availability_without_one(self):
        adapter = self.adapter()
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(adapter.is_available())

    def test_rejects_base_url_paths_other_than_v1(self):
        with self.assertRaisesRegex(ValueError, "must point to the /v1 API root"):
            self.adapter(base_url="http://127.0.0.1:3001/admin")


if __name__ == "__main__":
    unittest.main()
