import hashlib
import json
import threading
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

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

    def build_runtime(self, workspace_read_enabled, tests_enabled, workspace_write_enabled=False, allowed_paths=None):
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
            allowed_paths=allowed_paths,
            workspace_write_enabled=workspace_write_enabled,
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

    def test_manim_render_and_artifact_routes_require_runtime_token(self):
        status, body = self.request(
            "/api/creative/manim-render",
            method="POST",
            body={"consent": True, "title": "Not authorized", "nodes": [{"label": "A", "x": 0, "y": 0}]},
            authorized=False,
        )
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "unauthorized")

        status, body = self.request(
            "/api/creative/manim-jobs/" + ("a" * 32) + "/artifact",
            authorized=False,
        )
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "unauthorized")

    def test_static_studio_shell_is_available_without_runtime_token(self):
        with urlopen(self.base_url + "/", timeout=3) as response:
            body = response.read().decode("utf-8")
            csp = response.headers.get("Content-Security-Policy", "")
        self.assertEqual(response.status, 200)
        self.assertIn("Omnitrix Studio", body)
        self.assertIn('id="chat-form"', body)
        self.assertIn('id="file-tree"', body)
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_pinterest_asset_search_route_is_authenticated_and_reference_only(self):
        status, body = self.request(
            "/api/creative/search?provider=pinterest&kind=image&q=induction%20stove"
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertTrue(body["manual_reference_only"])
        self.assertEqual(body["items"], [])
        self.assertIn("pinterest.com/search/pins/", body["search_url"])

    def test_asset_search_route_rejects_requests_without_runtime_token(self):
        status, body = self.request(
            "/api/creative/search?provider=pinterest&q=coil",
            authorized=False,
        )
        self.assertEqual(status, 401)
        self.assertEqual(body["code"], "unauthorized")

    @patch("interfaces.web.server.search_creative_assets")
    def test_public_mobile_creative_search_works_without_runtime_token(self, search_assets):
        search_assets.return_value = {"ok": True, "provider": "commons", "items": []}
        status, body = self.request(
            "/api/mobile/creative/search?q=induction%20coil&provider=pexels&limit=12",
            authorized=False,
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        search_assets.assert_called_once_with(
            "induction coil", provider="pexels", kind="any", limit=12
        )

    @patch("interfaces.web.server.creative_model_status")
    def test_mobile_creative_status_is_available_without_runtime_token(self, model_status):
        model_status.return_value = {"ok": True, "configured": False, "provider": "google", "model": "unconfigured"}
        status, body = self.request("/api/mobile/creative/status", authorized=False)
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertFalse(body["configured"])

    @patch("interfaces.web.server._allow_public_creative_model_request", return_value=True)
    def test_mobile_creative_analysis_requires_explicit_consent(self, _allow):
        status, body = self.request(
            "/api/mobile/creative/analyze",
            method="POST",
            body={"consent": False, "assets": []},
            authorized=False,
        )
        self.assertEqual(status, 400, body)
        self.assertIn("Explicit consent", body["error"])

    @patch("interfaces.web.server._allow_public_creative_model_request", return_value=True)
    def test_mobile_creative_analysis_uses_bounded_public_route_after_consent(self, _allow):
        with patch.object(self.runtime, "start_creative_analysis", return_value={"ok": True, "status": "processing", "job_id": "job-test"} ) as start:
            status, body = self.request(
                "/api/mobile/creative/analyze",
                method="POST",
                body={"consent": True, "assets": [], "brief": "test"},
                authorized=False,
            )
        self.assertEqual(status, 202, body)
        self.assertTrue(body["ok"])
        start.assert_called_once()

    def test_mobile_image_generation_requires_consent_and_uses_configured_provider(self):
        with patch.dict("os.environ", {"OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA": "true"}), \
             patch("interfaces.web.server._allow_public_creative_model_request", return_value=True), \
             patch("interfaces.web.server.generate_creative_image", return_value={
                 "ok": True, "provider": "google", "model": "gemini-nano-banana-2.1",
                 "mime_type": "image/png", "image_base64": "cG5n",
             }) as generate:
            status, body = self.request(
                "/api/mobile/creative/generate-image",
                method="POST",
                body={
                    "consent": True, "paid_cost_acknowledged": True,
                    "prompt": "Original induction stove illustration",
                },
                authorized=False,
            )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        generate.assert_called_once_with(
            "Original induction stove illustration", aspect_ratio="16:9"
        )

    def test_mobile_image_generation_rejects_missing_paid_cost_acknowledgement(self):
        with patch("interfaces.web.server.generate_creative_image") as generate:
            status, body = self.request(
                "/api/mobile/creative/generate-image",
                method="POST",
                body={"consent": True, "prompt": "Original portrait illustration"},
                authorized=False,
            )
        self.assertEqual(status, 400)
        self.assertIn("cost acknowledgement", body["error"].lower())
        generate.assert_not_called()

    def test_mobile_video_generation_rejects_missing_paid_cost_acknowledgement(self):
        with patch("interfaces.web.server.start_creative_video_job") as start:
            status, body = self.request(
                "/api/mobile/creative/generate-video",
                method="POST",
                body={"consent": True, "prompt": "A person waving and saying hi"},
                authorized=False,
            )
        self.assertEqual(status, 400)
        self.assertIn("paid-video cost acknowledgement", body["error"].lower())
        start.assert_not_called()

    def test_mobile_video_generation_starts_direct_provider_job_only_after_cost_ack(self):
        with patch.dict("os.environ", {"OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA": "true"}), \
             patch("interfaces.web.server._allow_public_creative_video_request", return_value=True), \
             patch("interfaces.web.server.start_creative_video_job", return_value={
                 "ok": True, "job_id": "a" * 32, "status": "queued",
                 "provider": "google", "model": "gemini-omni-1.1-flash",
                 "estimated_cost_usd": 0.8,
             }) as start:
            status, body = self.request(
                "/api/mobile/creative/generate-video",
                method="POST",
                body={
                    "consent": True, "paid_cost_acknowledged": True,
                    "prompt": "A man waves and says hi",
                    "aspect_ratio": "9:16", "resolution": "720p",
                },
                authorized=False,
            )
        self.assertEqual(status, 202, body)
        self.assertTrue(body["ok"])
        self.assertEqual(body["model"], "gemini-omni-1.1-flash")
        start.assert_called_once_with(
            "A man waves and says hi", aspect_ratio="9:16", resolution="720p"
        )


    def test_mobile_video_status_reports_default_off_without_calling_model(self):
        with patch.dict("os.environ", {"OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA": "false"}):
            status, body = self.request(
                "/api/mobile/creative/video-status",
                authorized=False,
            )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertFalse(body["enabled"])
        self.assertIn("OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA=true", body["message"])
        self.assertIn("model", body)
        self.assertNotIn("GEMINI_API_KEY", json.dumps(body.get("message", "")))

    def test_mobile_paid_video_generation_is_disabled_by_default(self):
        with patch.dict("os.environ", {"OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA": "false"}), \
             patch("interfaces.web.server.start_creative_video_job") as start:
            status, body = self.request(
                "/api/mobile/creative/generate-video",
                method="POST",
                body={
                    "consent": True, "paid_cost_acknowledged": True,
                    "prompt": "A man waves and says hi",
                },
                authorized=False,
            )
        self.assertEqual(status, 503)
        self.assertEqual(body.get("code"), "paid_media_disabled")
        start.assert_not_called()

    def test_hosted_mobile_model_profile_keeps_baseline_and_registers_reasoning_model(self):
        config = json.loads((ROOT / "config" / "mobile.models.json").read_text(encoding="utf-8"))
        models = {model["name"]: model for model in config["models"]}
        self.assertEqual(
            set(models),
            {
                "omnitrix-primary",
                "reasoning-nemotron-super-free",
                "omnitrix-fast-fallback",
            },
        )

        baseline = models["omnitrix-primary"]
        self.assertEqual(baseline["provider"], "google")
        self.assertEqual(baseline["model_id"], "gemini-3.8-flash")
        self.assertEqual(baseline["metadata"]["cost_class"], "user_provided_free_quota")
        self.assertEqual(baseline["metadata"]["estimated_cost_usd"], 0)
        self.assertEqual(baseline["metadata"]["timeout_seconds"], 15)
        self.assertEqual(baseline["metadata"]["max_retries"], 0)
        self.assertEqual(baseline["metadata"]["standard_fallback_model"], "omnitrix-fast-fallback")

        reasoning = models["reasoning-nemotron-super-free"]
        self.assertEqual(reasoning["provider"], "openrouter")
        self.assertEqual(reasoning["model_id"], "nvidia/nemotron-3-super-120b-a12b:free")
        self.assertEqual(reasoning["metadata"]["api_key_env"], "OPENROUTER_API_KEY")
        self.assertEqual(reasoning["metadata"]["estimated_cost_usd"], 0)

        fast_fallback = models["omnitrix-fast-fallback"]
        self.assertEqual(fast_fallback["provider"], "openrouter")
        self.assertEqual(fast_fallback["model_id"], reasoning["model_id"])
        self.assertEqual(fast_fallback["metadata"]["timeout_seconds"], 30)
        self.assertEqual(fast_fallback["metadata"]["max_output_tokens"], 2048)
        self.assertEqual(fast_fallback["metadata"]["reasoning_effort"], "low")

    def test_mobile_backend_discovery_points_to_hosted_service(self):
        manifest = json.loads((ROOT / "config" / "mobile-backend.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], 1)
        self.assertTrue(manifest["chat_enabled"])
        self.assertEqual(manifest["base_url"], "https://omnitrix-studio.onrender.com")

    def test_apk_download_endpoint_streams_binary_with_download_headers(self):
        from unittest.mock import patch

        class FakeResponse:
            headers = {"Content-Length": "16"}

            def __init__(self):
                self.sent = False

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, amount=-1):
                if self.sent:
                    return b""
                self.sent = True
                return b"fake apk payload"

        with patch("interfaces.web.server.urlopen_url", return_value=FakeResponse()) as upstream:
            req = Request(self.base_url + "/downloads/Omnitrix.apk", method="GET")
            with urlopen(req, timeout=3) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type")
                disposition = response.headers.get("Content-Disposition")

        self.assertEqual(body, b"fake apk payload")
        self.assertEqual(content_type, "application/vnd.android.package-archive")
        self.assertEqual(disposition, 'attachment; filename="Omnitrix.apk"')
        upstream.assert_called_once()
        forwarded_request = upstream.call_args.args[0]
        self.assertEqual(
            forwarded_request.full_url,
            "https://github.com/som76377-alt/omnimatrix/releases/latest/download/Omnitrix.apk",
        )

    def test_public_mobile_health_is_available_without_runtime_token(self):
        status, body = self.request("/api/mobile/health", authorized=False)
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["service"], "omnitrix-mobile-api")
        self.assertFalse(body["chat_available"])
        self.assertIn("reasoning_specialist_available", body)
        self.assertIn("preferred_reasoning_model", body)
        self.assertIn("reasoning_route_status", body)
        self.assertNotIn(self.token, json.dumps(body))
        self.assertNotIn(str(self.workspace), json.dumps(body))

    def test_openrouter_only_key_makes_hosted_chat_ready_without_gemini(self):
        from unittest.mock import patch

        mobile_config = ROOT / "config" / "mobile.models.json"
        mobile_omnitrix = Omnitrix.from_config(
            mobile_config,
            tool_registry=self.runtime.omnitrix.tool_registry,
            tool_permission=self.runtime.omnitrix.tool_permission,
        )
        self.runtime.omnitrix = mobile_omnitrix
        self.runtime.public_chat_enabled = True

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "configured"}, clear=True):
            body = self.runtime.mobile_health()

        self.assertTrue(body["chat_available"])
        self.assertIsNone(body["reason"])
        self.assertTrue(body["reasoning_specialist_available"])
        self.assertTrue(body["openrouter_key_detected"])
        self.assertFalse(body["gemini_key_detected"])
        self.assertEqual(body["provider"], "openrouter")
        self.assertEqual(body["model"], "nvidia/nemotron-3-super-120b-a12b:free")
        self.assertEqual(body["reasoning_route_status"], "ready")

    def test_public_mobile_chat_is_disabled_by_default(self):
        status, body = self.request(
            "/api/mobile/chat",
            method="POST",
            body={"session_id": "test-session-12345678", "message": "Hello"},
            authorized=False,
        )
        self.assertEqual(status, 403)
        self.assertIn("not enabled", body["error"].lower())

    def test_public_mobile_chat_rate_limit_is_returned_as_http_429(self):
        from unittest.mock import patch

        self.runtime.public_chat_enabled = True
        self.runtime.public_chat_per_minute_limit = 0
        with patch.object(self.runtime, "mobile_health", return_value={"chat_available": True}):
            status, body = self.request(
                "/api/mobile/chat",
                method="POST",
                body={"session_id": "test-session-12345678", "message": "Hello"},
                authorized=False,
            )
        self.assertEqual(status, 429)
        self.assertEqual(body["code"], "rate_limited")

    def test_public_mobile_chat_rate_limit_is_enforced(self):
        from unittest.mock import patch

        self.runtime.public_chat_enabled = True
        self.runtime.public_chat_per_minute_limit = 1
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch.object(self.runtime, "mobile_health", return_value={"chat_available": True}):
                first = self.runtime.chat_public(
                    {"session_id": "test-session-12345678", "message": "Hello"},
                    "203.0.113.10",
                )
                self.assertTrue(first["ok"])
                with self.assertRaisesRegex(RuntimeError, "rate limit"):
                    self.runtime.chat_public(
                        {"session_id": "test-session-abcdefgh", "message": "Again"},
                        "203.0.113.10",
                    )

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
        self.assertFalse(body["workspace_write_enabled"])
        self.assertTrue(body["specialists_configured"])
        self.assertFalse(body["specialist_runtime_active"])
        self.assertEqual(
            {item["role"] for item in body["agents"]},
            {
                "reasoning", "coding", "subject_solver", "research",
                "computation", "critic", "intent_engineer", "orchestrator",
            },
        )
        self.assertIn("openrouter_key_detected", body)
        self.assertIn("active_execution", body)
        self.assertIsNone(body["active_execution"])
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
        trace = body["execution_trace"]
        self.assertIsInstance(trace, dict)
        self.assertEqual(len(trace["activity"]), 1)
        activity = trace["activity"][0]
        self.assertEqual(activity["provider"], "demo")
        self.assertEqual(activity["stage"], "answer_generation")
        self.assertEqual(activity["identity_source"], "adapter_metadata")

    def test_public_mobile_activity_is_session_scoped_and_exposes_only_safe_model_metadata(self):
        session_id = "mobile-session-12345678"
        client_ip = "127.0.0.1"
        self.runtime.active_chat_session_id = self.runtime._public_session_id(session_id, client_ip)
        self.runtime.omnitrix.active_execution = {
            "status": "request_in_flight",
            "stage": "primary_inference",
            "role": "subject_solver",
            "provider": "openrouter",
            "configured_model": "nvidia/nemotron-3-super-120b-a12b:free",
            "reasoning_effort_requested": "high",
            "identity_source": "configured_id_pending_provider_response",
            "private_reasoning": "must never be exposed",
        }
        self.runtime.omnitrix.active_task_metadata = {
            "objective": "PRIVATE EXAM QUESTION MUST NOT LEAK",
            "primary_agent_role": "subject_solver",
            "task_complexity": "complex",
            "task_domain": "subject",
            "agent_roles": ["intent_engineer", "subject_solver", "critic"],
            "model_activity": [{
                "status": "response_received",
                "stage": "intent_engineer",
                "role": "intent_engineer",
                "provider": "google",
                "model": "gemini-3.8-flash",
                "configured_model": "gemini-3.8-flash",
                "identity_source": "provider_response",
                "latency_seconds": 0.7,
            }],
        }

        status, body = self.request(
            "/api/mobile/activity?session_id=" + session_id,
            authorized=False,
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["active"])
        self.assertEqual(body["activity"]["role"], "subject_solver")
        self.assertEqual(body["activity"]["provider"], "openrouter")
        self.assertEqual(body["activity"]["reasoning_effort_requested"], "high")
        self.assertEqual(
            body["activity"]["identity_source"],
            "configured_id_pending_provider_response",
        )
        self.assertEqual(body["plan"]["primary_agent_role"], "subject_solver")
        self.assertEqual(body["activity_history"][0]["role"], "intent_engineer")
        self.assertNotIn("private_reasoning", json.dumps(body))
        self.assertNotIn("must never be exposed", json.dumps(body))
        self.assertNotIn("PRIVATE EXAM QUESTION MUST NOT LEAK", json.dumps(body))

        status, other = self.request(
            "/api/mobile/activity?session_id=someone-elses-session",
            authorized=False,
        )
        self.assertEqual(status, 200, other)
        self.assertFalse(other["active"])
        self.assertNotIn("nvidia/nemotron", json.dumps(other))

        self.runtime.active_chat_session_id = None
        self.runtime.omnitrix.active_execution = None

    def test_workspace_browser_fails_closed_without_explicit_opt_in(self):
        status, body = self.request("/api/workspace/read?path=notes.txt")
        self.assertEqual(status, 403)
        self.assertIn("disabled", body["error"].lower())

    def test_workspace_write_is_disabled_by_default(self):
        status, body = self.request(
            "/api/workspace/write",
            method="POST",
            body={"path": "notes.txt", "content": "changed", "expected_sha256": "0" * 64},
        )
        self.assertEqual(status, 403)
        self.assertIn("disabled", body["error"].lower())

    def test_fixed_local_test_runner_is_disabled_by_default(self):
        status, body = self.request("/api/tests/run", method="POST", body={})
        self.assertEqual(status, 403)
        self.assertIn("--allow-test-run", body["error"])

    def test_guarded_workspace_write_succeeds_with_matching_hash(self):
        self.workspace_tool.close()
        self.runtime, self.workspace_tool = self.build_runtime(
            workspace_read_enabled=True,
            tests_enabled=False,
            workspace_write_enabled=True,
            allowed_paths=["notes.txt"],
        )
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.httpd = self.start_server(self.runtime)
        self.base_url = "http://127.0.0.1:" + str(self.httpd.server_port)
        original_hash = hashlib.sha256(b"safe local note").hexdigest()
        status, body = self.request(
            "/api/workspace/write",
            method="POST",
            body={"path": "notes.txt", "content": "updated by app", "expected_sha256": original_hash},
        )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertEqual(body["result"]["previous_sha256"], original_hash)
        self.assertEqual(body["result"]["sha256"], hashlib.sha256(b"updated by app").hexdigest())
        self.assertEqual((self.workspace / "notes.txt").read_text(encoding="utf-8"), "updated by app")

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
        self.assertEqual(body["output"]["sha256"], hashlib.sha256(b"safe local note").hexdigest())
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
