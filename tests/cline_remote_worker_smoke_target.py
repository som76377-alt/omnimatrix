"""Disposable smoke target for the remote Cline worker execution bridge.

This module is intentionally tiny and self-contained: it exercises nothing but
a pure-Python helper so the remote worker can prove it can create a scoped
file and that the resulting unittest cases pass.
"""
from __future__ import annotations

import unittest


def add_numbers(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


class AddNumbersTests(unittest.TestCase):
    def test_adds_positive_numbers(self):
        self.assertEqual(add_numbers(2, 3), 5)

    def test_adds_negative_numbers(self):
        self.assertEqual(add_numbers(-2, -3), -5)

    def test_adds_mixed_sign_numbers(self):
        self.assertEqual(add_numbers(-4, 10), 6)

    def test_adds_zero(self):
        self.assertEqual(add_numbers(0, 0), 0)


if __name__ == "__main__":
    unittest.main()
