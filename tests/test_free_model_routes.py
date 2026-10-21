import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from core.models.loader import ModelConfigLoader
from core.models.providers.bootstrap import build_adapter_registry
from core.models.providers.groq import GroqAdapter
from core.models.providers.gemini import GeminiAdapter
from core.models.providers.openrouter import OpenRouterAdapter
from core.agents.registry import AgentRegistry


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIG = ROOT / "config" / "mobile.models.json"
AGENT_CONFIG = ROOT / "config" / "agents.json"


class FreeModelRouteConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModelConfigLoader().load(MODEL_CONFIG)
        self.adapters = build_adapter_registry(self.registry)
        self.agents = AgentRegistry.load(AGENT_CONFIG)

    def test_six_distinct_profiles_use_all_six_key_slots(self):
        models = self.registry.list_enabled()
        self.assertEqual(len(models), 6)
        self.assertEqual(len({(m.provider, m.model_id) for m in models}), 6)
        self.assertEqual(
            {m.metadata.get("api_key_env") for m in models},
            {
                "GEMINI_API_KEY", "GEMINI_API_KEY_1",
                "OPENROUTER_API_KEY", "OPENROUTER_API_KEY_1",
                "GROQ_API_KEY", "GROQ_API_KEY_1",
            },
        )

    def test_all_six_profiles_build_provider_specific_adapters(self):
        self.assertIsInstance(self.adapters.get("omnitrix-primary"), GeminiAdapter)
        self.assertIsInstance(self.adapters.get("gemini-flash-lite"), GeminiAdapter)
        self.assertIsInstance(self.adapters.get("coding-minimax-m31-free"), OpenRouterAdapter)
        self.assertIsInstance(self.adapters.get("orchestrator-nemotron-ultra-free"), OpenRouterAdapter)
        self.assertIsInstance(self.adapters.get("groq-gpt-oss-120b"), GroqAdapter)
        self.assertIsInstance(self.adapters.get("groq-gpt-oss-20b"), GroqAdapter)
        self.assertEqual(self.adapters.get("groq-gpt-oss-120b").provider, "groq")
        self.assertEqual(
            self.adapters.get("groq-gpt-oss-120b").endpoint,
            "https://api.groq.com/openai/v1/chat/completions",
        )

    def test_secondary_keys_are_used_by_their_own_model_profiles(self):
        models = {m.name: m for m in self.registry.list_enabled()}
        self.assertEqual(models["gemini-flash-lite"].metadata["api_key_env"], "GEMINI_API_KEY_1")
        self.assertEqual(models["orchestrator-nemotron-ultra-free"].metadata["api_key_env"], "OPENROUTER_API_KEY_1")
        self.assertEqual(models["groq-gpt-oss-20b"].metadata["api_key_env"], "GROQ_API_KEY_1")

    def test_every_agent_has_valid_configured_model_preferences(self):
        known = {m.name for m in self.registry.list_enabled()}
        self.assertEqual(len(self.agents.list_enabled()), 8)
        for agent in self.agents.list_enabled():
            self.assertTrue(agent.preferred_models, agent.role)
            self.assertTrue(
                all(item in known for item in agent.preferred_models),
                f"{agent.role} references an unregistered model profile",
            )

    def test_free_quota_profiles_never_declare_positive_estimated_cost(self):
        for model in self.registry.list_enabled():
            self.assertEqual(model.metadata.get("estimated_cost_usd"), 0, model.name)
            self.assertTrue(model.metadata.get("agent_approved_cost"), model.name)


if __name__ == "__main__":
    unittest.main()
