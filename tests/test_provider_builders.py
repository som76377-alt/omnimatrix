import unittest

from core.models.providers.builders import build_gemini_adapter
from core.models.providers.gemini import GeminiAdapter
from core.models.registry import ModelDefinition


class ProviderBuilderTests(unittest.TestCase):
    def test_builds_gemini_adapter(self):
        model = ModelDefinition(
            name="gemini-primary",
            provider="google",
            model_id="gemini-test-model",
        )

        adapter = build_gemini_adapter(model)

        self.assertIsInstance(adapter, GeminiAdapter)
        self.assertEqual(adapter.name, "gemini-primary")
        self.assertEqual(adapter.provider, "google")

    def test_builds_gemini_adapter_with_profile_timeout_settings(self):
        model = ModelDefinition(
            name="gemini-fast-failover",
            provider="google",
            model_id="gemini-test-model",
            metadata={"timeout_seconds": 15, "max_retries": 0},
        )

        adapter = build_gemini_adapter(model)

        self.assertEqual(adapter._timeout, 15.0)
        self.assertEqual(adapter._max_retries, 0)

    def test_invalid_gemini_timeout_settings_fail(self):
        invalid_metadata = (
            {"timeout_seconds": 0},
            {"timeout_seconds": True},
            {"max_retries": -1},
            {"max_retries": True},
        )
        for metadata in invalid_metadata:
            with self.subTest(metadata=metadata):
                model = ModelDefinition(
                    name="gemini-invalid-settings",
                    provider="google",
                    model_id="gemini-test-model",
                    metadata=metadata,
                )
                with self.assertRaises(ValueError):
                    build_gemini_adapter(model)

    def test_wrong_provider_fails(self):
        model = ModelDefinition(
            name="not-gemini",
            provider="groq",
            model_id="some-model",
        )

        with self.assertRaises(ValueError):
            build_gemini_adapter(model)

    def test_missing_model_id_fails(self):
        model = ModelDefinition(
            name="gemini-primary",
            provider="google",
        )

        with self.assertRaises(ValueError):
            build_gemini_adapter(model)


if __name__ == "__main__":
    unittest.main()