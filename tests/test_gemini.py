import json
import os
import unittest
from unittest.mock import patch

from core.models.base import (
    ModelAuthenticationError,
    ModelResponseError,
)
from core.models.providers.gemini import GeminiAdapter


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

        with patch(
            "core.models.providers.gemini.urlopen",
            return_value=FakeHTTPResponse(payload),
        ):
            response = self.adapter.generate("Hello Omnitrix")

        self.assertEqual(response.content, "Hello from Gemini.")
        self.assertEqual(response.model, "gemini-3.8-flash")
        self.assertEqual(response.provider, "google")
        self.assertEqual(response.usage["total_tokens"], 12)

    def test_missing_api_key_fails(self):
        adapter = GeminiAdapter(
            name="gemini-primary",
            model_id="gemini-3.8-flash",
            api_key_env="OMNITRIX_TEST_MISSING_KEY",
        )

        with patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            with self.assertRaises(ModelAuthenticationError):
                adapter.generate("Hello Omnitrix")

    def test_invalid_response_fails(self):
        fake_response = FakeHTTPResponse(
            {
                "model": "gemini-3.8-flash",
                "steps": [],
            }
        )

        with patch(
            "core.models.providers.gemini.urlopen",
            return_value=fake_response,
        ):
            with self.assertRaises(ModelResponseError):
                self.adapter.generate("Hello Omnitrix")

    def test_adapter_properties(self):
        self.assertEqual(self.adapter.name, "gemini-primary")
        self.assertEqual(self.adapter.provider, "google")


if __name__ == "__main__":
    unittest.main()
