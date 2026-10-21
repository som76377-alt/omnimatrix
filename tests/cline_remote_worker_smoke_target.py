"""Disposable smoke test for the remote Cline execution bridge.

This module is intentionally self-contained: it exercises no application code so
that a failure here points squarely at the remote worker bridge rather than at
the wider Omnitrix test suite.
"""
from __future__ import annotations

import unittest


def add_numbers(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


class AddNumbersSmokeTests(unittest.TestCase):
    def test_adds_two_positive_numbers(self) -> None:
        self.assertEqual(add_numbers(2, 3), 5)

    def test_adds_two_negative_numbers(self) -> None:
        self.assertEqual(add_numbers(-2, -3), -5)

    def test_adds_mixed_sign_numbers(self) -> None:
        self.assertEqual(add_numbers(-4, 9), 5)

    def test_adds_zero(self) -> None:
        self.assertEqual(add_numbers(0, 0), 0)
        self.assertEqual(add_numbers(0, 7), 7)
        self.assertEqual(add_numbers(7, 0), 7)

    def test_addition_is_commutative(self) -> None:
        self.assertEqual(add_numbers(2, 3), add_numbers(3, 2))


if __name__ == "__main__":
    unittest.main()
