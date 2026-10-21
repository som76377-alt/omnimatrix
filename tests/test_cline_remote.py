from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from core.tools.implementations.cline_coding import ClineCodingTool
from core.tools.implementations.cline_remote import RemoteClineError, execute_remote


class RemoteClineConfigurationTests(unittest.TestCase):
    def test_remote_backend_fails_closed_without_github_token(self) -> None:
        with patch.dict(os.environ, {"CLINE_EXECUTION_BACKEND": "github_actions"}, clear=False):
            os.environ.pop("OMNITRIX_GITHUB_ACTIONS_TOKEN", None)
            result = execute_remote(task="Implement a small safe change.", mode="implement")
        self.assertFalse(result.success)
        self.assertIn("OMNITRIX_GITHUB_ACTIONS_TOKEN", result.error or "")
        self.assertFalse((result.metadata or {}).get("changes_applied", False))

    def test_runtime_status_does_not_claim_remote_worker_ready_without_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"CLINE_EXECUTION_BACKEND": "github_actions"}, clear=False):
                os.environ.pop("OMNITRIX_GITHUB_ACTIONS_TOKEN", None)
                tool = ClineCodingTool(Path(tmp))
                status = tool.runtime_status()
        self.assertEqual(status["backend"], "github_actions")
        self.assertFalse(status["ready_to_attempt"])
        self.assertFalse(status["worker_credential_configured"])


    def _run_remote_with_result_artifact(self, *, pr_allowed: bool):
        result_payload = {
            "status": "passed",
            "mode": "implement",
            "changed_files": ["src/example.py"],
            "tests_passed": True,
            "cline_output": "Implementation completed and tests passed.",
            "pull_request_url": None,
        }
        archive_stream = io.BytesIO()
        with zipfile.ZipFile(archive_stream, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("cline-result.json", json.dumps(result_payload))
        archive_bytes = archive_stream.getvalue()
        request_state = {"request_id": None, "created_pr_payload": None}

        def fake_api(token, path, *, method="GET", payload=None, accept="application/vnd.github+json", timeout=20):
            if method == "POST" and "/dispatches?" in path:
                request_state["request_id"] = payload["inputs"]["request_id"]
                return {}, "application/json"
            if "/workflows/cline-remote-worker.yml/runs?" in path:
                request_id = request_state["request_id"]
                return {"workflow_runs": [{
                    "id": 901,
                    "display_title": f"Cline remote worker {request_id}",
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "https://github.com/som76377-alt/omnimatrix/actions/runs/901",
                }]}, "application/json"
            if path.endswith("/actions/runs/901/artifacts"):
                return {"artifacts": [{
                    "id": 902,
                    "name": f"cline-result-{request_state['request_id']}",
                    "expired": False,
                }]}, "application/json"
            if path.endswith("/actions/artifacts/902/zip"):
                return archive_bytes, "application/zip"
            if path == "/repos/som76377-alt/omnimatrix/pulls" and method == "POST":
                request_state["created_pr_payload"] = payload
                if not pr_allowed:
                    raise RemoteClineError(
                        "GitHub rejected the worker credential or its Actions permissions. Check the Render secret and repository access."
                    )
                return {
                    "html_url": "https://github.com/som76377-alt/omnimatrix/pull/903"
                }, "application/json"
            raise AssertionError(f"Unexpected GitHub API call: {method} {path}")

        env = {
            "OMNITRIX_GITHUB_ACTIONS_TOKEN": "test-token-not-real",
            "CLINE_REMOTE_BASE_REF": "fix/model-coordination-live-checks",
            "CLINE_EXECUTION_BACKEND": "github_actions",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "core.tools.implementations.cline_remote._api", side_effect=fake_api
        ), patch("core.tools.implementations.cline_remote.time.sleep"):
            result = execute_remote(
                task="Implement an illustrative code example safely.",
                mode="implement",
                files_in_scope=["src/example.py"],
                acceptance_criteria=["Tests pass."],
            )
        return result, request_state

    def test_remote_implementation_uses_render_credential_to_open_review_pr(self) -> None:
        result, state = self._run_remote_with_result_artifact(pr_allowed=True)
        self.assertTrue(result.success, result.error)
        self.assertIn("/pull/903", result.output or "")
        self.assertEqual(
            (result.metadata or {}).get("pull_request_created_by"),
            "render_runtime_credential",
        )
        self.assertEqual(state["created_pr_payload"]["base"], "fix/model-coordination-live-checks")
        self.assertTrue(state["created_pr_payload"]["head"].startswith("cline/omnitrix-"))

    def test_remote_implementation_reports_pr_permission_failure_truthfully(self) -> None:
        result, state = self._run_remote_with_result_artifact(pr_allowed=False)
        self.assertFalse(result.success)
        self.assertTrue((result.metadata or {}).get("tests_passed"))
        self.assertIn("could not be delivered", result.error or "")
        self.assertIn("pull-request write permission", result.output or "")
        self.assertIsNotNone(state["created_pr_payload"])


if __name__ == "__main__":
    unittest.main()
