import unittest

from core.contracts import BudgetGuard, BudgetLimits, ErrorCode, OmnitrixError


class BudgetGuardTests(unittest.TestCase):
    def test_zero_cost_mode_allows_only_known_zero_cost_classes(self):
        guard = BudgetGuard(BudgetLimits(max_model_calls=2, max_estimated_cost_usd=0))
        guard.reserve_model_call(cost_class="demo")
        guard.reserve_model_call(cost_class="local")
        with self.assertRaises(OmnitrixError) as caught:
            guard.reserve_model_call(cost_class="unknown")
        self.assertEqual(caught.exception.code, ErrorCode.BUDGET_EXCEEDED)
        self.assertEqual(guard.snapshot()["model_calls"], 2)

    def test_zero_cost_mode_rejects_nonzero_estimate_without_consuming_budget(self):
        guard = BudgetGuard()
        with self.assertRaises(OmnitrixError):
            guard.reserve_model_call(cost_class="free", estimated_cost_usd=0.01)
        self.assertEqual(guard.snapshot()["model_calls"], 0)

    def test_unknown_cost_is_rejected_in_zero_cost_mode(self):
        with self.assertRaises(OmnitrixError):
            BudgetGuard().reserve_model_call(cost_class="unknown", estimated_cost_usd=None)

    def test_paid_mode_requires_known_estimate_and_respects_cap(self):
        guard = BudgetGuard(BudgetLimits(max_estimated_cost_usd=0.05, spend_mode="paid_allowed"))
        with self.assertRaises(OmnitrixError):
            guard.reserve_model_call(cost_class="paid", estimated_cost_usd=None)
        guard.reserve_model_call(cost_class="paid", estimated_cost_usd=0.03)
        with self.assertRaises(OmnitrixError):
            guard.reserve_model_call(cost_class="paid", estimated_cost_usd=0.03)
        self.assertAlmostEqual(guard.snapshot()["estimated_cost_usd"], 0.03)

    def test_tool_call_budget_is_hard(self):
        guard = BudgetGuard(BudgetLimits(max_tool_calls=1))
        guard.reserve_tool_call()
        with self.assertRaises(OmnitrixError):
            guard.reserve_tool_call()
        self.assertEqual(guard.snapshot()["tool_calls"], 1)

    def test_invalid_limits_are_rejected(self):
        with self.assertRaises(ValueError):
            BudgetLimits(max_model_calls=-1)
        with self.assertRaises(ValueError):
            BudgetLimits(spend_mode="surprise")


if __name__ == "__main__":
    unittest.main()
