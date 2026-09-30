import unittest

from core.models.registry import ModelDefinition, ModelRegistry


class ModelRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModelRegistry()

        self.registry.register(
            ModelDefinition(
                name="test-coder",
                provider="test",
                capabilities=frozenset({"coding", "reasoning"}),
                context_window=128_000,
            )
        )

        self.registry.register(
            ModelDefinition(
                name="test-researcher",
                provider="test",
                capabilities=frozenset({"research", "reasoning"}),
                context_window=64_000,
            )
        )

    def test_register_and_get_model(self):
        model = self.registry.get("test-coder")

        self.assertEqual(model.provider, "test")
        self.assertEqual(model.context_window, 128_000)

    def test_model_capability(self):
        model = self.registry.get("test-coder")

        self.assertTrue(model.supports("coding"))
        self.assertFalse(model.supports("vision"))

    def test_find_capable_models(self):
        models = self.registry.find_capable("coding")

        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].name, "test-coder")

    def test_unknown_model_fails(self):
        with self.assertRaises(KeyError):
            self.registry.get("does-not-exist")

    def test_duplicate_model_fails(self):
        with self.assertRaises(ValueError):
            self.registry.register(
                ModelDefinition(
                    name="test-coder",
                    provider="test",
                )
            )


if __name__ == "__main__":
    unittest.main()
