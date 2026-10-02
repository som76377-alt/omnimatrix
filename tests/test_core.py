import json
import tempfile
import unittest
from pathlib import Path

from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.registry import ModelDefinition, ModelRegistry
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission
from core.tools.request import ToolRequest


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

        adapter_registry = AdapterRegistry()
        adapter_registry.register(FakeModel())

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=adapter_registry,
        )

        result = omnitrix.run("Hello Omnitrix")

        self.assertEqual(result, "Received: Hello Omnitrix")

    def test_omnitrix_can_load_models_from_config(self):
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

            adapter_registry = AdapterRegistry()
            adapter_registry.register(FakeModel())

            omnitrix = Omnitrix.from_config(
                path,
                adapter_registry=adapter_registry,
            )

            result = omnitrix.run("Hello from config")

        self.assertEqual(result, "Received: Hello from config")

    def test_model_response_is_normalized(self):
        adapter = FakeModel()

        response = adapter.generate("Test prompt")

        self.assertEqual(response.content, "Received: Test prompt")
        self.assertEqual(response.model, "fake-model")
        self.assertEqual(response.provider, "test")

    def test_missing_adapter_fails_cleanly(self):
        registry = ModelRegistry()

        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=AdapterRegistry(),
        )

        with self.assertRaises(LookupError):
            omnitrix.run("Hello Omnitrix")

    def test_omnitrix_from_config_builds_gemini_adapter(self):
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            encoding="utf-8",
        ) as file:
            json.dump(
                {
                    "models": [
                        {
                            "name": "gemini-primary",
                            "provider": "google",
                            "model_id": "gemini-test-model",
                            "capabilities": [
                                "reasoning",
                                "coding",
                            ],
                            "context_window": 32000,
                            "enabled": True,
                        }
                    ]
                },
                file,
            )
            file.flush()

            omnitrix = Omnitrix.from_config(file.name)

        self.assertTrue(
            omnitrix.adapter_registry.has("gemini-primary")
        )

        adapter = omnitrix.adapter_registry.get("gemini-primary")

        self.assertEqual(adapter.name, "gemini-primary")
        self.assertEqual(adapter.provider, "google")

    def test_omnitrix_executes_authorized_tool(self):
        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=AdapterRegistry(),
            tool_registry=build_tool_registry(),
            tool_permission=ToolPermission.from_capabilities({"calculation"}),
        )

        result = omnitrix.execute_tool(
            ToolRequest(
                tool_name="calculator",
                arguments={"expression": "6 * 7"},
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.output, 42)

    def test_omnitrix_rejects_unauthorized_tool(self):
        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="fake-model",
                provider="test",
                capabilities=frozenset({"reasoning"}),
            )
        )

        omnitrix = Omnitrix(
            registry=registry,
            adapter_registry=AdapterRegistry(),
            tool_registry=build_tool_registry(),
            tool_permission=ToolPermission.from_capabilities(set()),
        )

        result = omnitrix.execute_tool(
            ToolRequest(
                tool_name="calculator",
                arguments={"expression": "6 * 7"},
            )
        )

        self.assertFalse(result.success)
        self.assertIn("Permission denied", result.error)


if __name__ == "__main__":
    unittest.main()
