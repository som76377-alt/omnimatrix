import unittest

from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import ModelRequest


class FakeAdapter(ModelAdapter):
    @property
    def name(self):
        return "fake-model"

    @property
    def provider(self):
        return "test"

    def generate(self, request: ModelRequest):
        return ModelResponse(
            content=f"Received: {request.messages[0].content}",
            model=self.name,
            provider=self.provider,
        )


class AdapterRegistryTests(unittest.TestCase):
    def test_register_and_get_adapter(self):
        registry = AdapterRegistry()
        adapter = FakeAdapter()

        registry.register(adapter)

        self.assertIs(registry.get("fake-model"), adapter)

    def test_has_adapter(self):
        registry = AdapterRegistry()

        self.assertFalse(registry.has("fake-model"))

        registry.register(FakeAdapter())

        self.assertTrue(registry.has("fake-model"))

    def test_duplicate_adapter_fails(self):
        registry = AdapterRegistry()

        registry.register(FakeAdapter())

        with self.assertRaises(ValueError):
            registry.register(FakeAdapter())

    def test_unknown_adapter_fails(self):
        registry = AdapterRegistry()

        with self.assertRaises(KeyError):
            registry.get("missing-model")

    def test_list_adapters(self):
        registry = AdapterRegistry()
        adapter = FakeAdapter()

        registry.register(adapter)

        self.assertEqual(registry.list(), [adapter])


if __name__ == "__main__":
    unittest.main()
