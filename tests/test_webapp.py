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
        cls.creative_html = (WEBAPP / "creative-studio.html").read_text(encoding="utf-8")
        cls.creative_js = (WEBAPP / "creative-studio.js").read_text(encoding="utf-8")
        cls.creative_css = (WEBAPP / "creative-studio.css").read_text(encoding="utf-8")

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

    def test_creative_studio_files_assets_and_local_first_contract(self):
        parser = ConsoleHTMLParser()
        parser.feed(self.creative_html)
        self.assertIn("preview-canvas", parser.ids)
        self.assertIn("media-input", parser.ids)
        self.assertIn("timeline-list", parser.ids)
        self.assertIn("inspector-form", parser.ids)
        for asset in parser.local_assets:
            with self.subTest(asset=asset):
                self.assertTrue((WEBAPP / asset.removeprefix("./")).is_file(), asset)
        referenced_ids = set(re.findall(r'\$\("([^"]+)"\)', self.creative_js))
        missing = sorted(referenced_ids - parser.ids)
        self.assertEqual(missing, [])
        self.assertIn("indexedDB", self.creative_js)
        self.assertIn("MediaRecorder", self.creative_js)
        self.assertIn("drawGraphicLayers(clip, localTime)", self.creative_js)
        self.assertIn("add-rect-layer", self.creative_html)
        self.assertIn("add-circle-layer", self.creative_html)
        self.assertIn("graphic-layer-animation", self.creative_html)
        self.assertIn("scale-in", self.creative_js)
        self.assertIn("layers: Array.isArray(clip.layers)", self.creative_js)
        self.assertIn("explicit consent", self.creative_html.lower())
        self.assertIn("real generated mp4 with movement and audio", self.creative_html.lower())
        self.assertIn('id="paid-video-consent"', self.creative_html)
        self.assertIn('id="generate-ai-video"', self.creative_html)
        self.assertIn("integrated-shared-model-role", (ROOT / "config/creative-studio-agents.json").read_text(encoding="utf-8"))
        self.assertIn('"status": "integrated"', (ROOT / "config/creative-studio-tools.json").read_text(encoding="utf-8"))
        self.assertIn('"./api/creative/analyze"', self.creative_js)
        self.assertIn('"./api/mobile/creative/analyze"', self.creative_js)
        self.assertIn('if (!$("ai-consent").checked)', self.creative_js)
        self.assertIn("consent_clip_ids", self.creative_js)
        self.assertNotIn('fetch("https://', self.creative_js)

    def test_dashboard_reads_real_public_repository_api(self):
        self.assertIn('const GITHUB_API = "https://api.github.com/repos/" + OWNER + "/" + REPO;', self.js)
        self.assertIn("som76377-alt", self.js)
        self.assertIn("omnimatrix", self.js)
        self.assertIn("/actions/runs?branch=main", self.js)
        self.assertIn("./status.json", self.js)
        self.assertIn("rate limit", self.js.lower())
        self.assertIn('apiRequest("/chat"', self.js)
        self.assertIn('apiRequest("/workspace/list?path="', self.js)
        self.assertIn('apiRequest("/tests/run"', self.js)

    def test_chat_has_sanitized_markdown_math_code_and_diagram_rendering(self):
        self.assertIn("marked@18.1.1", self.html)
        self.assertIn("dompurify@3.4.16", self.html)
        self.assertIn("katex@0.19.0", self.html)
        self.assertIn("highlight.js@11.12.0", self.html)
        self.assertIn("contrib/mhchem.min.js", self.html)
        core_pos = self.html.index("katex.min.js")
        chemistry_pos = self.html.index("contrib/mhchem.min.js")
        auto_render_pos = self.html.index("contrib/auto-render.min.js")
        self.assertLess(core_pos, chemistry_pos)
        self.assertLess(chemistry_pos, auto_render_pos)
        self.assertIn("window.DOMPurify.sanitize(parsed", self.js)
        self.assertIn("target.innerHTML = window.DOMPurify.sanitize(parsed", self.js)
        self.assertNotIn("target.innerHTML = parsed", self.js)
        self.assertIn("renderMathInElement(target", self.js)
        self.assertIn(r'left: "\\(", right: "\\)", display: false', self.js)
        self.assertIn(r'left: "\\[", right: "\\]", display: true', self.js)
        self.assertNotIn(r'left: "\\begin{align}"', self.js)
        self.assertIn(r'"\\dv":', self.js)
        self.assertIn(r'"\\pdv":', self.js)
        self.assertIn(r'"\\ket":', self.js)
        self.assertIn(r'"\\braket":', self.js)
        self.assertIn("renderGitHubAlerts(target)", self.js)
        self.assertIn("renderChartBlocks(target)", self.js)
        self.assertIn('["bar", "line", "scatter", "pie"]', self.js)
        self.assertIn("600 total points", self.js)
        self.assertIn("Use either numeric x-values or categorical x-values", self.js)
        self.assertIn("Math.abs(value) <= 1e100", self.js)
        self.assertIn('document.createElementNS(CHART_SVG_NS', self.js)
        self.assertIn("renderMathCodeBlocks(target)", self.js)
        self.assertIn("renderBareMathEnvironments(target)", self.js)
        self.assertIn("language-latex", self.js)
        self.assertIn("language-equation", self.js)
        self.assertIn("renderKatexBlock(container, tex, displayMode)", self.js)
        self.assertIn("renderMediaBlocks(target)", self.js)
        self.assertIn("language-audio", self.js)
        self.assertIn("language-video", self.js)
        self.assertIn('media.preload = "none"', self.js)
        self.assertIn('media.referrerPolicy = "no-referrer"', self.js)
        self.assertIn('url.protocol !== "https:"', self.js)
        self.assertIn(".message-media audio", self.css)
        self.assertIn(".message-math-fence", self.css)
        self.assertIn("renderMermaidBlocks(target)", self.js)
        self.assertIn('securityLevel: "strict"', self.js)
        self.assertIn('const bubble = node("div", "message-bubble");', self.js)
        self.assertIn("renderRichContent(bubble, content)", self.js)
        self.assertIn(".message-bubble .katex-display", self.css)
        self.assertIn(".message-bubble table", self.css)
        self.assertIn(".message-bubble blockquote.rich-alert-warning", self.css)
        self.assertIn(".message-bubble .message-chart svg", self.css)

    def test_chat_model_label_is_driven_by_provider_trace_and_live_status(self):
        self.assertIn('id="chat-thread-subtitle" aria-live="polite"', self.html)
        self.assertIn("function describeExecutionTrace(trace)", self.js)
        self.assertIn("function traceIdentityLabel(item)", self.js)
        self.assertIn('identity_source === "provider_response"', self.js)
        self.assertIn('apiRequest("/health"', self.js)
        self.assertIn("active_execution", self.js)
        self.assertIn("reasoning_effort_requested", self.js)
        self.assertIn("NO MODEL IDENTITY TRACE", self.js)
        self.assertIn(".message-model-identity", self.css)
        self.assertIn("provider did not report identity", self.js)

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

    def test_creative_direction_requires_explicit_consent_and_review(self):
        self.assertIn('id="open-ai-director"', self.creative_html)
        self.assertIn('id="ai-consent"', self.creative_html)
        self.assertIn('id="ai-analyze"', self.creative_html)
        self.assertIn('id="ai-plan-preview"', self.creative_html)
        self.assertIn('id="ai-apply-plan"', self.creative_html)
        self.assertIn('if (!$("ai-consent").checked)', self.creative_js)
        self.assertIn('"./api/creative/analyze"', self.creative_js)
        self.assertIn('"./api/mobile/creative/analyze"', self.creative_js)
        self.assertIn("aiTimelineSignature() !== state.creativeSnapshot", self.creative_js)
        self.assertIn("Nothing has been edited yet.", self.creative_js)
        self.assertIn("resized JPEG thumbnails and limited clip metadata", self.creative_html)

    def test_creative_api_is_authenticated_bounded_and_uses_shared_worker(self):
        server = (ROOT / "interfaces/web/server.py").read_text(encoding="utf-8")
        director = (ROOT / "core/creative_director.py").read_text(encoding="utf-8")
        self.assertIn('route == "/api/creative/status"', server)
        self.assertIn('"/api/creative/analyze", "/api/mobile/creative/analyze"', server)
        self.assertIn("MAX_CREATIVE_BODY_BYTES", server)
        self.assertIn("runtime.start_creative_analysis(payload)", server)
        self.assertIn("self.creative_analysis_lock", server)
        self.assertIn("def start_creative_analysis", server)
        self.assertIn("def creative_job_status", server)
        self.assertIn('route.startswith("/api/creative/jobs/")', server)
        self.assertIn("pollAiCreativeJob", self.creative_js)
        self.assertIn("from core.multimodal.workflow import analyze_multiple_attachments", director)
        self.assertIn("used_resized_previews_only", director)
        self.assertIn("edits_applied", director)
        self.assertIn("Consent", director)

    @unittest.skipUnless(shutil.which("node"), "Node.js not installed in this test environment")
    def test_browser_javascript_parses(self):
        for script in ("app.js", "sw.js", "creative-studio.js"):
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
