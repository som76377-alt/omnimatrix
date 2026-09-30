import unittest

from core.orchestrator.analyzer import BasicTaskAnalyzer


class BasicTaskAnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.analyzer = BasicTaskAnalyzer()

    def test_every_task_requires_reasoning(self):
        result = self.analyzer.analyze("Explain quantum computing")

        self.assertIn("reasoning", result.capabilities)

    def test_website_task_requires_coding(self):
        result = self.analyzer.analyze(
            "Build a responsive ecommerce website"
        )

        self.assertIn("coding", result.capabilities)

    def test_research_task_requires_research(self):
        result = self.analyzer.analyze(
            "Research browser automation frameworks"
        )

        self.assertIn("research", result.capabilities)

    def test_browser_task_requires_browser(self):
        result = self.analyzer.analyze(
            "Open the website in a browser and inspect it"
        )

        self.assertIn("browser", result.capabilities)

    def test_testing_task_requires_testing(self):
        result = self.analyzer.analyze(
            "Run the tests and perform QA"
        )

        self.assertIn("testing", result.capabilities)

    def test_combined_task_gets_multiple_capabilities(self):
        result = self.analyzer.analyze(
            "Build a website, test it, and inspect it in the browser"
        )

        self.assertEqual(
            result.capabilities,
            frozenset({
                "reasoning",
                "coding",
                "testing",
                "browser",
            }),
        )


if __name__ == "__main__":
    unittest.main()
