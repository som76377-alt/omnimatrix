import unittest

from core.models.providers.bootstrap import build_adapter_registry
from core.models.providers.gemini import GeminiAdapter
from core.models.registry import ModelDefinition, ModelRegistry


class BootstrapTests(unittest.TestCase):
    def test_builds_adapter_for_enabled_google_model(self) -> None:
        registry = ModelRegistry()

        registry.register(
            ModelDefinition(
                name="gemini-test",
                provider="google",
                model_id="gemini-test-model",
                enabled=True,
            )
        )

        adapters = build_adapter_registry(registry)

        self.assertTrue(adapters.has("gemini-test"))
        self.assertIsInstance(
            adapters.get("gemini-test"),
            GeminiAdapter,
        )

    def test_builds_adapters_for_multiple_enabled_models(self) -> None:
        registry = ModelRegistry()

        registry.register(
            ModelDefinition(
                name="gemini-one",
                provider="google",
                model_id="gemini-model-one",
                enabled=True,
            )
        )
        registry.register(
            ModelDefinition(
                name="gemini-two",
                provider="google",
                model_id="gemini-model-two",
                enabled=True,
            )
        )

        adapters = build_adapter_registry(registry)

        self.assertTrue(adapters.has("gemini-one"))
        self.assertTrue(adapters.has("gemini-two"))
        self.assertEqual(len(adapters.list()), 2)

    def test_ignores_disabled_models(self) -> None:
        registry = ModelRegistry()

        registry.register(
            ModelDefinition(
                name="disabled-gemini",
                provider="google",
                model_id="gemini-disabled",
                enabled=False,
            )
        )

        adapters = build_adapter_registry(registry)

        self.assertFalse(adapters.has("disabled-gemini"))
        self.assertEqual(len(adapters.list()), 0)

    def test_unsupported_provider_fails_clearly(self) -> None:
        registry = ModelRegistry()

        registry.register(
            ModelDefinition(
                name="unknown-model",
                provider="unknown-provider",
                model_id="unknown-model-v1",
                enabled=True,
            )
        )

        with self.assertRaisesRegex(
            LookupError,
            "No adapter builder registered for provider: unknown-provider",
        ):
            build_adapter_registry(registry)


if __name__ == "__main__":
    unittest.main()