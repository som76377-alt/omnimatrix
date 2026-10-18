import unittest

from core.policy.quality import (
    QUALITY_CONTRACT,
    QUALITY_POLICY_MARKER,
    has_quality_contract,
    require_quality_contract,
    with_quality_contract,
)


class QualityContractTests(unittest.TestCase):
    def test_policy_covers_completion_slop_reasoning_and_verification(self):
        for phrase in (
            "FINISH THE ACTUAL JOB",
            "ANTI-SLOP STANDARD",
            "REASONING AND VERIFICATION PROTOCOL",
            "NON-LAZY IMPLEMENTATION LOOP",
            "acceptance criteria",
            "Never invent facts",
            "Do not reveal private chain-of-thought",
            "correct it, and rerun",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), QUALITY_CONTRACT.lower())

    def test_composition_is_idempotent(self):
        once = with_quality_contract("Base instructions.")
        twice = with_quality_contract(once)
        self.assertEqual(once, twice)
        self.assertEqual(once.count(QUALITY_POLICY_MARKER), 1)
        self.assertTrue(has_quality_contract(once))

    def test_missing_policy_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "quality guardrails are missing"):
            require_quality_contract("Instructions without the required policy.")

    def test_blank_base_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            with_quality_contract("  ")


if __name__ == "__main__":
    unittest.main()
