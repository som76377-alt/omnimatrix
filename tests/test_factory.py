import unittest

from core.models.base import ModelAdapter, ModelResponse
from core.models.factory import ModelAdapterFactory
from core.models.messages import ModelRequest
from core.models.registry import ModelDefinition


class FakeAdapter(ModelAdapter):
    def __init__(self, name: str, provider: str):
        self._name = name
        self._provider = provider

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider(self) -> str:
        return self._provider

    def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content=request.messages[0].content,
            model=self.name,
            provider=self.provider,
        )


class ModelAdapterFactoryTests(unittest.TestCase):
    def setUp(self):
        self.factory = ModelAdapterFactory()

        self.model = ModelDefinition(
            name="test-model",
            provider="test",
            model_id="test-model-v1",
        )

    def test_register_and_create_adapter(self):
        self.factory.register(
            "test",
            lambda model: FakeAdapter(
                name=model.name,
                provider=model.provider,
            ),
        )

        adapter = self.factory.create(self.model)

        self.assertEqual(adapter.name, "test-model")
        self.assertEqual(adapter.provider, "test")

    def test_has_builder(self):
        self.factory.register(
            "test",
            lambda model: FakeAdapter(
                name=model.name,
                provider=model.provider,
            ),
        )

        self.assertTrue(self.factory.has_builder("test"))
        self.assertFalse(self.factory.has_builder("unknown"))

    def test_duplicate_builder_fails(self):
        builder = lambda model: FakeAdapter(
            name=model.name,
            provider=model.provider,
        )

        self.factory.register("test", builder)

        with self.assertRaises(ValueError):
            self.factory.register("test", builder)

    def test_empty_provider_fails(self):
        with self.assertRaises(ValueError):
            self.factory.register(
                "",
                lambda model: FakeAdapter(
                    name=model.name,
                    provider=model.provider,
                ),
            )

    def test_unknown_provider_fails(self):
        with self.assertRaises(LookupError):
            self.factory.create(self.model)


if __name__ == "__main__":
    unittest.main()