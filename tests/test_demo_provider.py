import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from core.orchestrator.omnitrix import Omnitrix
from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import MessageRole, ModelMessage, ModelRequest
from core.models.providers.bootstrap import build_adapter_registry
from core.models.providers.demo import DemoAdapter
from core.models.registry import ModelDefinition, ModelRegistry


class DemoProviderTests(unittest.TestCase):
    def setUp(self):
        self.adapter = DemoAdapter(
            name="offline-demo",
            model_id="offline-demo-v1",
        )

    def test_is_a_model_adapter(self):
        self.assertIsInstance(self.adapter, ModelAdapter)
        self.assertEqual(self.adapter.name, "offline-demo")
        self.assertEqual(self.adapter.provider, "demo")

    def test_chat_response_is_clearly_labelled_as_simulated(self):
        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Hello Omnitrix",
                ),
            )
        )

        response = self.adapter.generate(request)

        self.assertIsInstance(response, ModelResponse)
        self.assertEqual(response.provider, "demo")
        self.assertIn("OFFLINE DEMO", response.content)
        self.assertIn("simulated", response.content.lower())
        self.assertIn("Hello Omnitrix", response.content)
        self.assertEqual(response.tool_calls, ())

    def test_non_planner_instructions_return_demo_chat_response(self):
        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Explain task dependencies",
                ),
            ),
            instructions="You are a helpful assistant.",
        )
        response = self.adapter.generate(request)
        self.assertIn("OFFLINE DEMO", response.content)
        self.assertIn("Explain task dependencies", response.content)
        self.assertEqual(response.tool_calls, ())

    def test_planning_response_is_valid_and_explicitly_simulated(self):
        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content="Research a topic",
                ),
            ),
            instructions=(
                "You are the Omnitrix task planner. "
                "Return a valid JSON object containing tasks."
            ),
        )

        response = self.adapter.generate(request)
        payload = json.loads(response.content)

        self.assertEqual(set(payload), {"tasks"})
        self.assertEqual(len(payload["tasks"]), 1)
        self.assertIn("task_id", payload["tasks"][0])
        self.assertIn("description", payload["tasks"][0])
        self.assertIn("dependencies", payload["tasks"][0])
        self.assertIn("DEMO ONLY", payload["tasks"][0]["description"])
        self.assertEqual(response.tool_calls, ())

    def test_bootstrap_registers_demo_provider_explicitly(self):
        registry = ModelRegistry()
        registry.register(
            ModelDefinition(
                name="offline-demo",
                provider="demo",
                model_id="offline-demo-v1",
                capabilities=frozenset({"reasoning", "coding"}),
                enabled=True,
            )
        )

        adapters = build_adapter_registry(registry)

        self.assertIsInstance(
            adapters.get("offline-demo"),
            DemoAdapter,
        )

    def test_demo_config_supports_offline_chat_and_plan_generation(self):
        config_path = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "demo.models.json"
        )
        with patch.dict(os.environ, {}, clear=True):
            omnitrix = Omnitrix.from_config(config_path)
            chat_response = omnitrix.run("Hello Omnitrix")
            self.assertIn("OFFLINE DEMO", chat_response)
            self.assertIn("Hello Omnitrix", chat_response)
            plan = omnitrix.propose_plan("Research a topic")
        self.assertEqual(len(plan.tasks), 1)
        self.assertIn("DEMO ONLY", plan.tasks[0].description)


if __name__ == "__main__":
    unittest.main()
