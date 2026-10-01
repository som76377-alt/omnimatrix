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