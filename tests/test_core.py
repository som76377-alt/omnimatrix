import unittest

from core.models.base import ModelAdapter, ModelResponse
from core.models.registry import ModelDefinition, ModelRegistry
from core.orchestrator.omnitrix import Omnitrix


class FakeModel(ModelAdapter):
    @property
    def name(self):
        return "fake-model"

    @property
    def provider(self):
        return "test"

    def generate(self, prompt):
        return ModelResponse(
            content=f"Received: {prompt}",
            model=self.name,
            provider=self.provider,
        )


class CoreTests(unittest.TestCase):
    def test_omnitrix_analyzes_routes_and_runs_model(self):
        registry = ModelRegistry()

        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        adapter = FakeModel()

        omnitrix = Omnitrix(
            registry=registry,
            adapters={"fake-model": adapter},
        )

        result = omnitrix.run("Hello Omnitrix")

        self.assertEqual(result, "Received: Hello Omnitrix")


if __name__ == "__main__":
    unittest.main()
