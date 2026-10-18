import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.run_reasoning_v1 import load_cases


class ReasoningBenchmarkFixtureTests(unittest.TestCase):
    def test_checked_in_benchmark_has_unique_ids_and_nonempty_prompts(self):
        path = Path(__file__).resolve().parents[1] / "benchmarks" / "reasoning_v1.json"
        cases = load_cases(path)
        self.assertGreaterEqual(len(cases), 3)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertTrue(all(case["prompt"].strip() for case in cases))

    def test_rejects_duplicate_case_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps({
                "version": 1,
                "cases": [
                    {"id": "same", "prompt": "First"},
                    {"id": "same", "prompt": "Second"},
                ],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique"):
                load_cases(path)

    def test_rejects_unsupported_benchmark_version(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps({"version": 2, "cases": [{"id": "x", "prompt": "Prompt"}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "version 1"):
                load_cases(path)


if __name__ == "__main__":
    unittest.main()
