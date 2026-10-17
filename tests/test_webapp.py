from html.parser import HTMLParser
from pathlib import Path
import re
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
        expected = {"workspace", "chat", "status", "capabilities", "recovery"}
        self.assertTrue(expected.issubset(parser.views))
        for view in expected:
            self.assertIn(f"view-{view}", parser.ids)
        self.assertIn("chat-form", parser.ids)
        self.assertIn("file-tree", parser.ids)
        self.assertIn("editor-body", parser.ids)
        self.assertIn("run-tests", parser.ids)
        self.assertIn("workflow-list", parser.ids)
        self.assertIn("local-test-count", parser.ids)

    def test_every_local_html_asset_exists(self):
        parser = ConsoleHTMLParser()
        parser.feed(self.html)
        for asset in parser.local_assets:
            with self.subTest(asset=asset):
                self.assertTrue((WEBAPP / asset.removeprefix("./")).is_file(), asset)

    def test_all_javascript_element_lookups_resolve_in_html(self):
        parser = ConsoleHTMLParser()
        parser.feed(self.html)
        ids = set(re.findall(r'byId\("([^"]+)"\)', self.js))
        missing = sorted(ids - parser.ids)
        self.assertEqual(missing, [])

    def test_dashboard_reads_real_public_repository_api(self):
        self.assertIn("https://api.github.com/repos/${OWNER}/${REPO}", self.js)
        self.assertIn("som76377-alt", self.js)
        self.assertIn("omnimatrix", self.js)
        self.assertIn("/actions/runs?branch=main", self.js)
        self.assertIn("./status.json", self.js)
        self.assertIn("rate limit", self.js.lower())
        self.assertIn("/api/chat", self.js)
        self.assertIn("/api/workspace/list", self.js)
        self.assertIn("/tests/run", self.js)

    def test_browser_ui_is_honest_about_backend_and_read_only_scope(self):
        self.assertIn("The static GitHub Pages version cannot execute Python itself.", self.html)
        self.assertIn("READ ONLY EXPLORER", self.html)
        self.assertIn("arbitrary command execution", self.html)
        self.assertIn("offline-demo", self.js)
        self.assertNotIn("GEMINI_API_KEY=", self.html + self.js)

    def test_hosted_shell_is_network_first_and_refreshes_service_worker(self):
        self.assertIn('fetch(request)', self.worker)
        self.assertIn('caches.match(request)', self.worker)
        self.assertIn('url.pathname.endsWith("/status.json")', self.worker)
        self.assertIn("registration.update()", self.js)
        self.assertLess(self.worker.index("fetch(request)"), self.worker.index(".catch(async () =>"))

    def test_styles_include_mobile_layout_and_reduced_motion(self):
        self.assertIn("@media(max-width:620px)", self.css)
        self.assertIn(".mobile-nav", self.css)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_pages_workflow_runs_tests_before_upload_and_publish(self):
        self.assertIn("python -m unittest discover -s tests -v", self.workflow)
        self.assertIn("node --check webapp/app.js", self.workflow)
        self.assertIn("actions/upload-pages-artifact@v4", self.workflow)
        self.assertIn("actions/deploy-pages@v4", self.workflow)
        self.assertIn("needs: build", self.workflow)
        self.assertIn("GITHUB_SHA", self.workflow)

    def test_python_backend_requires_token_and_uses_fixed_test_command(self):
        server = (ROOT / "interfaces/web/server.py").read_text(encoding="utf-8")
        self.assertIn('self.headers.get("Authorization"', server)
        self.assertIn("hmac.compare_digest", server)
        self.assertIn('"unittest"', server)
        self.assertIn('"discover"', server)
        self.assertIn('"tests"', server)
        self.assertIn("MAX_TEST_OUTPUT_BYTES", server)
        self.assertIn("TEST_TIMEOUT_SECONDS", server)
        self.assertNotIn("shell=True", server)

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
