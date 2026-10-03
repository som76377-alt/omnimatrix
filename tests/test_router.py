import unittest

from core.models.registry import ModelDefinition, ModelRegistry
from core.routing_policy import RoutingPolicy
from core.router import ModelRouter, RoutingRequirements


class ModelRouterTests(unittest.TestCase):
    def setUp(self):
        self.registry = ModelRegistry()

        self.registry.register(
            ModelDefinition(
                name="small-general",
                provider="test",
                capabilities=frozenset({"reasoning"}),
                context_window=32_000,
            )
        )

        self.registry.register(
            ModelDefinition(
                name="coding-model",
                provider="test",
                capabilities=frozenset({"coding", "reasoning"}),
                context_window=128_000,
            )
        )

        self.registry.register(
            ModelDefinition(
                name="research-model",
                provider="test",
                capabilities=frozenset({"research", "reasoning"}),
                context_window=64_000,
            )
        )

    def test_selects_model_with_required_capability(self):
        router = ModelRouter(self.registry)

        result = router.select(
            RoutingRequirements(
                capabilities=frozenset({"coding"}),
            )
        )

        self.assertEqual(result.name, "coding-model")

    def test_selects_model_with_required_context(self):
        router = ModelRouter(self.registry)

        result = router.select(
            RoutingRequirements(
                capabilities=frozenset({"reasoning"}),
                minimum_context_window=100_000,
            )
        )

        self.assertEqual(result.name, "coding-model")

    def test_select_candidates_returns_all_matching_models_in_registry_order(self):
        router = ModelRouter(self.registry)

        results = router.select_candidates(
            RoutingRequirements(
                capabilities=frozenset({"reasoning"}),
            )
        )

        self.assertEqual(
            [model.name for model in results],
            ["small-general", "coding-model", "research-model"],
        )

    def test_select_candidates_applies_all_requirements(self):
        router = ModelRouter(self.registry)

        results = router.select_candidates(
            RoutingRequirements(
                capabilities=frozenset({"reasoning"}),
                minimum_context_window=60_000,
            )
        )

        self.assertEqual(
            [model.name for model in results],
            ["coding-model", "research-model"],
        )

    def test_no_matching_model_fails(self):
        router = ModelRouter(self.registry)

        with self.assertRaises(LookupError):
            router.select(
                RoutingRequirements(
                    capabilities=frozenset({"vision"}),
                )
            )


    def test_select_delegates_to_injected_policy(self):
        class SecondCandidatePolicy(RoutingPolicy):
            def select(self, candidates):
                return candidates[1]

        router = ModelRouter(
            self.registry,
            policy=SecondCandidatePolicy(),
        )

        result = router.select(
            RoutingRequirements(
                capabilities=frozenset({"reasoning"}),
            )
        )

        self.assertEqual(result.name, "coding-model")


if __name__ == "__main__":
    unittest.main()
