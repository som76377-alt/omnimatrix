import unittest

from core.models.base import ModelAdapter, ModelResponse
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
    def test_omnitrix_uses_model(self):
        omnitrix = Omnitrix(FakeModel())
        result = omnitrix.run("Hello Omnitrix")
        self.assertEqual(result, "Received: Hello Omnitrix")


if __name__ == "__main__":
    unittest.main()
