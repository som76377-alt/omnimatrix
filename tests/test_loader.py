import json
import tempfile
import unittest
from pathlib import Path

from core.models.loader import ModelConfigLoader


class ModelConfigLoaderTests(unittest.TestCase):
    def write_config(self, config):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "models.json"
        path.write_text(
            json.dumps(config),
            encoding="utf-8",
        )
        self.addCleanup(directory.cleanup)
        return path

    def test_loads_models_from_json(self):
        path = self.write_config(
            {
                "models": [
                    {
                        "name": "test-model",
                        "provider": "test",
                        "capabilities": ["reasoning", "coding"],
                        "context_window": 32000,
                        "enabled": True,
                    }
                ]
            }
        )

        registry = ModelConfigLoader().load(path)
        model = registry.get("test-model")

        self.assertEqual(model.provider, "test")
        self.assertTrue(model.supports("coding"))
        self.assertEqual(model.context_window, 32000)

    def test_invalid_models_field_fails(self):
        path = self.write_config({"models": "not-a-list"})

        with self.assertRaises(ValueError):
            ModelConfigLoader().load(path)

    def test_empty_name_fails(self):
        path = self.write_config(
            {
                "models": [
                    {
                        "name": "",
                        "provider": "test",
                    }
                ]
            }
        )

        with self.assertRaises(ValueError):
            ModelConfigLoader().load(path)

    def test_empty_provider_fails(self):
        path = self.write_config(
            {
                "models": [
                    {
                        "name": "test-model",
                        "provider": "",
                    }
                ]
            }
        )

        with self.assertRaises(ValueError):
            ModelConfigLoader().load(path)

    def test_invalid_capabilities_fails(self):
        path = self.write_config(
            {
                "models": [
                    {
                        "name": "test-model",
                        "provider": "test",
                        "capabilities": "coding",
                    }
                ]
            }
        )

        with self.assertRaises(ValueError):
            ModelConfigLoader().load(path)

    def test_invalid_context_window_fails(self):
        path = self.write_config(
            {
                "models": [
                    {
                        "name": "test-model",
                        "provider": "test",
                        "context_window": -1,
                    }
                ]
            }
        )

        with self.assertRaises(ValueError):
            ModelConfigLoader().load(path)

    def test_invalid_enabled_fails(self):
        path = self.write_config(
            {
                "models": [
                    {
                        "name": "test-model",
                        "provider": "test",
                        "enabled": "yes",
                    }
                ]
            }
        )

        with self.assertRaises(ValueError):
            ModelConfigLoader().load(path)


if __name__ == "__main__":
    unittest.main()
