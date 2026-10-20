"""Tests for query decomposition used by online visual-reference search."""
import unittest

from core.creative_search_planner import build_search_query_variants


class CreativeSearchPlannerTests(unittest.TestCase):
    def test_human_action_brief_becomes_separate_visual_queries(self):
        queries = build_search_query_variants(
            "CREATE A VIDEO OF A MAN WAVING HIS HAND AND SAYING HI"
        )
        self.assertGreaterEqual(len(queries), 3)
        self.assertIn("man waving", queries)
        self.assertIn("man saying hi", queries)
        self.assertIn("person waving", queries)
        self.assertFalse(any("create a video" in query.lower() for query in queries))

    def test_long_science_brief_is_shortened_without_losing_main_concept(self):
        queries = build_search_query_variants(
            "Create a video explaining how an induction stove heats a pan with a magnetic field"
        )
        self.assertIn("induction stove", queries)
        self.assertIn("magnetic field", queries)
        self.assertLessEqual(len(queries), 6)
        self.assertTrue(all(2 <= len(query.split()) for query in queries))

    def test_queries_are_deduplicated_case_insensitively_and_bounded(self):
        queries = build_search_query_variants("Man waving, man waving", limit=20)
        self.assertLessEqual(len(queries), 6)
        self.assertEqual(len({query.casefold() for query in queries}), len(queries))

    def test_blank_or_non_text_queries_are_safe(self):
        self.assertEqual(build_search_query_variants("   "), [])
        self.assertEqual(build_search_query_variants(None), [])
        self.assertEqual(build_search_query_variants("person walking", limit=0), ["person walking"])


if __name__ == "__main__":
    unittest.main()
