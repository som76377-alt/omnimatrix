import os
import unittest
from unittest.mock import patch

from core.agents.registry import AgentRegistry
from core.models.loader import ModelConfigLoader
from core.models.providers.bootstrap import build_adapter_registry
from core.models.providers.freellmapi import FreeLLMAPIAdapter


ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
MODEL_CONFIG = ROOT / "config" / "mobile.models.freellmapi.json"
AGENT_CONFIG = ROOT / "config" / "agents.freellmapi.json"


class FreeLLMAPIProfileTests(unittest.TestCase):
    def test_optional_profile_keeps_six_direct_routes_and_adds_one_gateway_route(self):
        registry = ModelConfigLoader().load(MODEL_CONFIG)
        models = {model.name: model for model in registry.list_enabled()}
        self.assertEqual(len(models), 7)
        self.assertEqual(
            {model.provider for model in models.values()},
            {"google", "openrouter", "groq", "freellmapi"},
        )
        self.assertEqual(models["freellmapi-auto-balanced"].model_id, "auto:balanced")
        self.assertEqual(
            models["freellmapi-auto-balanced"].metadata["api_key_env"],
            "FREELLMAPI_API_KEY",
        )

    def test_gateway_profile_is_first_preference_for_every_enabled_specialist(self):
        registry = AgentRegistry.load(AGENT_CONFIG)
        known = {model.name for model in ModelConfigLoader().load(MODEL_CONFIG).list_enabled()}
        agents = registry.list_enabled()
        self.assertEqual(len(agents), 8)
        for agent in agents:
            self.assertEqual(agent.preferred_models[0], "freellmapi-auto-balanced", agent.role)
            self.assertTrue(all(name in known for name in agent.preferred_models), agent.role)

    def test_bootstrap_registers_a_separate_gateway_adapter(self):
        registry = ModelConfigLoader().load(MODEL_CONFIG)
        with patch.dict(os.environ, {
            "FREELLMAPI_API_KEY": "freellmapi-test-key",
            "FREELLMAPI_BASE_URL": "http://127.0.0.1:3001/v1",
        }):
            adapters = build_adapter_registry(registry)
        adapter = adapters.get("freellmapi-auto-balanced")
        self.assertIsInstance(adapter, FreeLLMAPIAdapter)
        self.assertEqual(adapter.provider, "freellmapi")
        self.assertEqual(adapter.endpoint, "http://127.0.0.1:3001/v1/chat/completions")


if __name__ == "__main__":
    unittest.main()
