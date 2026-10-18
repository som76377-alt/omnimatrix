import unittest

from core.orchestrator.omnitrix import Omnitrix
from core.policy.response_formatting import (
    RESPONSE_FORMATTING_CONTRACT,
    RESPONSE_FORMATTING_POLICY_MARKER,
    RESPONSE_FORMATTING_POLICY_VERSION,
    has_response_formatting_contract,
    with_response_formatting_contract,
)


class ResponseFormattingContractTests(unittest.TestCase):
    def test_contract_covers_supported_special_renderers(self):
        for required in (
            "inline TeX",
            r"\begin{align}",
            r"\ce{...}",
            "Mermaid",
            "fenced `chart`",
            '"bar", "line", "scatter", and "pie"',
            "[!WARNING]",
            "Do not emit arbitrary HTML",
        ):
            with self.subTest(required=required):
                self.assertIn(required.lower(), RESPONSE_FORMATTING_CONTRACT.lower())

    def test_contract_composition_is_idempotent(self):
        once = with_response_formatting_contract("Base instructions.")
        twice = with_response_formatting_contract(once)
        self.assertEqual(once, twice)
        self.assertTrue(has_response_formatting_contract(once))
        self.assertEqual(once.count(RESPONSE_FORMATTING_POLICY_MARKER), 1)

    def test_default_chat_instructions_include_rendering_guidance(self):
        self.assertTrue(has_response_formatting_contract(Omnitrix.DEFAULT_INSTRUCTIONS))
        self.assertIn(RESPONSE_FORMATTING_POLICY_VERSION, Omnitrix.DEFAULT_INSTRUCTIONS)

    def test_empty_base_instructions_are_rejected(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    with_response_formatting_contract(value)


if __name__ == "__main__":
    unittest.main()
