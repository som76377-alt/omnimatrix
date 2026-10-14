import unittest

from core.models.providers.demo import DemoAdapter
from core.models.providers.gemini import GeminiAdapter
from core.models.types import ModelContinuation
from core.persistence.snapshot_provider_compatibility import (
    inspect_provider_continuation_compatibility,
)


class SnapshotProviderCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.gemini = GeminiAdapter(name="gemini-fast", model_id="gemini-2.5-flash")
        self.demo = DemoAdapter(name="demo-offline", model_id="demo-v1")

    def inspect(self, provider="google", model="gemini-2.5-flash", continuation=None, adapters=None):
        return inspect_provider_continuation_compatibility(
            provider=provider,
            model=model,
            continuation=continuation,
            adapters=adapters if adapters is not None else [self.gemini, self.demo],
        )

    def test_valid_gemini_interaction_state_is_recognized_without_resume_authorization(self):
        result = self.inspect(continuation=ModelContinuation(
            provider="google", state={"interaction_id": "interaction-123"}
        ))
        self.assertTrue(result["provider_compatible"])
        self.assertTrue(result["continuation_state_compatible"])
        self.assertFalse(result["restore_ready"])
        self.assertEqual(result["reason"], "recognized_by_registered_adapter")

    def test_wrong_provider_or_malformed_state_fails_closed(self):
        for continuation in (
            ModelContinuation(provider="other", state={"interaction_id": "interaction-123"}),
            ModelContinuation(provider="google", state={"unexpected": "value"}),
            ModelContinuation(provider="google", state={"interaction_id": ""}),
        ):
            with self.subTest(continuation=continuation):
                result = self.inspect(continuation=continuation)
                self.assertFalse(result["continuation_state_compatible"])
                self.assertFalse(result["restore_ready"])

    def test_unknown_model_or_provider_fails_closed(self):
        for provider, model in (("google", "unknown-model"), ("unknown", "gemini-2.5-flash")):
            with self.subTest(provider=provider, model=model):
                result = self.inspect(provider=provider, model=model)
                self.assertFalse(result["provider_compatible"])
                self.assertFalse(result["restore_ready"])

    def test_ambiguous_adapter_match_fails_closed(self):
        duplicate = GeminiAdapter(name="gemini-fast-duplicate", model_id="gemini-2.5-flash")
        result = self.inspect(
            continuation=ModelContinuation(provider="google", state={"interaction_id": "x"}),
            adapters=[self.gemini, duplicate],
        )
        self.assertFalse(result["provider_compatible"])
        self.assertEqual(result["adapter_match_count"], 2)

    def test_missing_continuation_is_reported_without_claiming_restore_ready(self):
        result = self.inspect(continuation=None)
        self.assertTrue(result["provider_compatible"])
        self.assertIsNone(result["continuation_state_compatible"])
        self.assertFalse(result["restore_ready"])
        self.assertIn("reconstruction remains unimplemented", result["reason"])

    def test_demo_model_is_matched_by_provider_model_id(self):
        result = self.inspect(
            provider="demo", model="demo-v1", adapters=[self.demo]
        )
        self.assertTrue(result["provider_compatible"])
        self.assertFalse(result["restore_ready"])


if __name__ == "__main__":
    unittest.main()
