import unittest

from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import ModelRequest
from core.models.registry import ModelDefinition, ModelRegistry
from core.orchestrator.omnitrix import Omnitrix


class StubAdapter(ModelAdapter):
    def __init__(self, name: str, provider: str, available: bool = True) -> None:
        self._name = name
        self._provider = provider
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider(self) -> str:
        return self._provider

    def is_available(self) -> bool:
        return self._available

    def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(content="stub", model=self.name, provider=self.provider)


class StandardFallbackSelectionTests(unittest.TestCase):
    def _resolve(
        self,
        *,
        fallback_provider: str = "openrouter",
        fallback_available: bool = True,
        fallback_capabilities: frozenset[str] = frozenset({"reasoning", "coding"}),
    ):
        primary = ModelDefinition(
            name="mobile-primary",
            provider="google",
            model_id="gemini-test",
            capabilities=frozenset({"reasoning"}),
            metadata={"standard_fallback_model": "mobile-fast-fallback"},
        )
        fallback = ModelDefinition(
            name="mobile-fast-fallback",
            provider=fallback_provider,
            model_id="fast-model",
            capabilities=fallback_capabilities,
            metadata={"timeout_seconds": 30, "max_output_tokens": 2048},
        )
        registry = ModelRegistry()
        registry.register(primary)
        registry.register(fallback)
        adapters = AdapterRegistry()
        adapters.register(StubAdapter(primary.name, primary.provider))
        adapters.register(
            StubAdapter(fallback.name, fallback.provider, available=fallback_available)
        )
        orchestrator = Omnitrix(registry=registry, adapter_registry=adapters)
        return orchestrator._configured_standard_fallback(
            primary, frozenset({"reasoning"})
        )

    def test_selects_configured_available_cross_provider_fallback(self):
        selected = self._resolve()
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "mobile-fast-fallback")
        self.assertEqual(selected.provider, "openrouter")

    def test_rejects_same_provider_fallback(self):
        self.assertIsNone(self._resolve(fallback_provider="google"))

    def test_rejects_unavailable_fallback_adapter(self):
        self.assertIsNone(self._resolve(fallback_available=False))

    def test_rejects_fallback_missing_required_capability(self):
        self.assertIsNone(self._resolve(fallback_capabilities=frozenset({"coding"})))


if __name__ == "__main__":
    unittest.main()
