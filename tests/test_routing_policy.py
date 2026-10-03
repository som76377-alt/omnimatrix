import unittest

from core.models.registry import ModelDefinition
from core.routing_policy import FirstCandidatePolicy


class FirstCandidatePolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = FirstCandidatePolicy()

        self.first = ModelDefinition(
            name="first-model",
            provider="test",
        )

        self.second = ModelDefinition(
            name="second-model",
            provider="test",
        )

    def test_selects_first_candidate(self):
        result = self.policy.select(
            [self.first, self.second]
        )

        self.assertEqual(result.name, "first-model")

    def test_preserves_candidate_order(self):
        result = self.policy.select(
            [self.second, self.first]
        )

        self.assertEqual(result.name, "second-model")

    def test_empty_candidates_fail(self):
        with self.assertRaises(LookupError):
            self.policy.select([])


if __name__ == "__main__":
    unittest.main()
