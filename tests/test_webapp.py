from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"


class ConsoleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.views = set()
        self.local_assets = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if values.get("data-view"):
            self.views.add(values["data-view"])
        for attr in ("src", "href"):
            target = values.get(attr, "")
            if target.startswith("./"):
                self.local_assets.append(target.split("?", 1)[0].split("#", 1)[0])
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])


class WebConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (WEBAPP / "index.html").read_text(encoding="utf-8")
        cls.js = (WEBAPP / "app.js").read_text(encoding="utf-8")
        cls.css = (WEBAPP / "styles.css").read_text(encoding="utf-8")
        cls.worker = (WEBAPP / "sw.js").read_text(encoding="utf-8")
        cls.workflow = (ROOT / ".github/workflows/deploy-webapp.yml").read_text(encoding="utf-8")

    def test_all_views_and_primary_navigation_exist(self):
        parser = ConsoleHTMLParser()
        parser.feed(self.html)
        expected = {"overview", "status", "capabilities", "workspace", "recovery"}
        self.assertTrue(expected.issubset(parser.views))
        for view in expected:
            self.assertIn(f"view-{view}", parser.ids)
        self.assertIn("status-test-count", parser.ids)
        self.assertIn("status-runs", parser.ids)
        self.assertIn("open-pulls", parser.ids)
        self.assertIn("workspace-command", parser.ids)

    def test_every_local_html_asset_exists(self):
        parser = ConsoleHTMLParser()
        parser.feed(self.html)
        for asset in parser.local_assets:
            with self.subTest(asset=asset):
                self.assertTrue((WEBAPP / asset.removeprefix("./")).is_file(), asset)

    def test_dashboard_reads_real_public_repository_api(self):
        self.assertIn("https://api.github.com/repos/${OWNER}/${REPO}", self.js)
        self.assertIn("som76377-alt", self.js)
        self.assertIn("omnimatrix", self.js)
        self.assertIn("/actions/runs?branch=main", self.js)
        self.assertIn("/pulls?state=open", self.js)
        self.assertIn("./status.json", self.js)
        self.assertIn("rate limit", self.js.lower())

    def test_browser_ui_does_not_claim_remote_python_execution(self):
        self.assertIn("does not pretend to execute it remotely", self.html)
        self.assertIn("does not directly invoke Python tools", self.html)
        self.assertIn("The browser has no connection to the Python process", self.html)
        self.assertNotIn("GEMINI_API_KEY=", self.html + self.js)

    def test_hosted_shell_is_network_first_and_refreshes_service_worker(self):
        self.assertIn('fetch(request)', self.worker)
        self.assertIn('caches.match(request)', self.worker)
        self.assertIn('url.pathname.endsWith("/status.json")', self.worker)
        self.assertIn("registration.update()", self.js)
        self.assertLess(self.worker.index("fetch(request)"), self.worker.index(".catch(async () =>"))

    def test_styles_include_mobile_layout_and_reduced_motion(self):
        self.assertIn("@media(max-width:600px)", self.css)
        self.assertIn(".mobile-nav", self.css)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_pages_workflow_runs_tests_before_upload_and_publish(self):
        self.assertIn("python -m unittest discover -s tests -v", self.workflow)
        self.assertIn("node --check webapp/app.js", self.workflow)
        self.assertIn("actions/upload-pages-artifact@v4", self.workflow)
        self.assertIn("actions/deploy-pages@v4", self.workflow)
        self.assertIn("needs: build", self.workflow)
        self.assertIn("GITHUB_SHA", self.workflow)

    @unittest.skipUnless(shutil.which("node"), "Node.js not installed in this test environment")
    def test_browser_javascript_parses(self):
        for script in ("app.js", "sw.js"):
            with self.subTest(script=script):
                result = subprocess.run(
                    ["node", "--check", str(WEBAPP / script)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
