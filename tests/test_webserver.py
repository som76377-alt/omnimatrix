import json
import threading
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from core.application import ChatApplication
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission
from interfaces.web.server import StudioRuntime, make_handler


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "webapp"
DEMO_CONFIG = ROOT / "config" / "demo.models.json"


class StudioServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "workspace"
        self.workspace.mkdir()
        (self.workspace / "notes.txt").write_text("safe local note", encoding="utf-8")
        self.token = "test-token-not-a-real-secret"
        self.runtime, self.workspace_tool = self.build_runtime(
            workspace_read_enabled=False,
            tests_enabled=False,
        )
        self.httpd = self.start_server(self.runtime)
        self.base_url = "http://127.0.0.1:" + str(self.httpd.server_port)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.workspace_tool.close()
        self.temp.cleanup()

    def build_runtime(self, workspace_read_enabled, tests_enabled):
        registry = build_tool_registry(self.workspace)
        permission = {"calculation"}
        if workspace_read_enabled:
            permission.add("workspace.read")
        omnitrix = Omnitrix.from_config(
            DEMO_CONFIG,
            tool_registry=registry,
            tool_permission=ToolPermission.from_capabilities(permission),
        )
        runtime = StudioRuntime(
            root=self.workspace,
            config_path=DEMO_CONFIG,
            app=ChatApplication(omnitrix),
            omnitrix=omnitrix,
            workspace_tool=registry.get("workspace.inspect"),
            access_token=self.token,
            workspace_read_enabled=workspace_read_enabled,
            allowed_paths=None,
            tests_enabled=tests_enabled,
            test_timeout_seconds=5,
        )
        return runtime, registry.get("workspace.inspect")

    def start_server(self, runtime):
        server = __import__("http.server", fromlist=["ThreadingHTTPServer"]).ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(runtime, WEB_ROOT)
        )
        server.daemon_threads = True
        self.thread = threading.Thread(target=server.serve_forever, daemon=True)
        self.thread.start()
        return server

    def request(self, path, *, method="GET", body=None, authorized=True):
        headers = {}
        data = None
        if authorized:
            headers["Authorization"] = "Bearer " + self.token
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read()
            return exc.code, json.loads(raw.decode("utf-8"))

    def test_static_studio_shell_is_available_without_runtime_token(self):
        with urlopen(self.base_url + "/", timeout=3) as response:
            body = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Omnitrix Studio", body)
        self.assertIn('id="chat-form"', body)
        self.assertIn('id="file-tree"', body)

    def test_api_rejects_missing_or_wrong_token(self):
        status, body = self.request("/api/health", authorized=False)
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "unauthorized")
        wrong = Request(
            self.base_url + "/api/health",
            headers={"Authorization": "Bearer not-the-token"},
        )
        with self.assertRaises(HTTPError) as context:
            urlopen(wrong, timeout=3)
        self.assertEqual(context.exception.code, 401)

    def test_health_reports_real_registry_without_leaking_secret_or_root(self):
        status, body = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["provider_mode"], "offline-demo")
        self.assertIn("calculator", {item["name"] for item in body["tools"]})
        self.assertFalse(body["workspace_read_enabled"])
        encoded = json.dumps(body)
        self.assertNotIn(self.token, encoded)
        self.assertNotIn(str(self.workspace), encoded)

    def test_chat_reaches_existing_demo_orchestrator_and_labels_simulation(self):
        status, body = self.request(
            "/api/chat",
            method="POST",
            body={"session_id": "test-session-12345678", "message": "Hello from Studio"},
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertIn("OFFLINE DEMO", body["reply"])
        self.assertEqual(body["provider_mode"], "offline-demo")
        self.assertEqual(body["message_count"], 2)

    def test_workspace_browser_fails_closed_without_explicit_opt_in(self):
        status, body = self.request("/api/workspace/read?path=notes.txt")
        self.assertEqual(status, 403)
        self.assertIn("disabled", body["error"].lower())

    def test_fixed_local_test_runner_is_disabled_by_default(self):
        status, body = self.request("/api/tests/run", method="POST", body={})
        self.assertEqual(status, 403)
        self.assertIn("--allow-test-run", body["error"])

    def test_workspace_browser_reads_bounded_file_when_explicitly_enabled(self):
        self.workspace_tool.close()
        self.runtime, self.workspace_tool = self.build_runtime(
            workspace_read_enabled=True,
            tests_enabled=False,
        )
        # Switch this request handler to the same runtime object used by the test.
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.httpd = self.start_server(self.runtime)
        self.base_url = "http://127.0.0.1:" + str(self.httpd.server_port)
        status, body = self.request("/api/workspace/read?path=notes.txt")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertEqual(body["output"]["content"], "safe local note")
        self.assertTrue(body["output"]["untrusted_content"])

    def test_session_id_and_message_are_validated(self):
        status, body = self.request(
            "/api/chat",
            method="POST",
            body={"session_id": "bad", "message": "hello"},
        )
        self.assertEqual(status, 400)
        self.assertIn("session_id", body["error"])
        status, body = self.request(
            "/api/chat",
            method="POST",
            body={"session_id": "session-1234567890123", "message": ""},
        )
        self.assertEqual(status, 400)
        self.assertIn("empty", body["error"].lower())


if __name__ == "__main__":
    unittest.main()
