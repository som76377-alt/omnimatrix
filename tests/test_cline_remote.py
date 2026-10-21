from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core.tools.implementations.cline_coding import ClineCodingTool
from core.tools.implementations.cline_remote import execute_remote


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


if __name__ == "__main__":
    unittest.main()
