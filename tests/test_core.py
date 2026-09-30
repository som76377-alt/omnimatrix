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

    def test_omnitrix_can_load_models_from_config(self):
        import json
        import tempfile
        from pathlib import Path

        config = {
            "models": [
                {
                    "name": "fake-model",
                    "provider": "test",
                    "capabilities": ["reasoning"],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "models.json"
            path.write_text(
                json.dumps(config),
                encoding="utf-8",
            )

            omnitrix = Omnitrix.from_config(
                path,
                adapters={"fake-model": FakeModel()},
            )

            result = omnitrix.run("Hello from config")

        self.assertEqual(result, "Received: Hello from config")
if __name__ == "__main__":
    unittest.main()
