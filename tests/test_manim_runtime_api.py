import tempfile
import threading
import time
import unittest
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.tools.base import ToolResult
from interfaces.web.server import StudioRuntime


class FakeManimTool:
    name = "manim_scientific_diagram"

    def __init__(self, artifact_path=None, result=None):
        self.artifact_path = artifact_path
        self.result = result

    def execute(self, **kwargs):
        if self.result is not None:
            return self.result
        self.artifact_path.write_bytes(b"verified-test-mp4-bytes" * 256)
        return ToolResult(
            success=True,
            output={"artifact_path": str(self.artifact_path), "format": "mp4", "bytes": self.artifact_path.stat().st_size},
            metadata={"tool": self.name, "renderer": "manim", "verified": True},
        )


def make_runtime(tool):
    runtime = object.__new__(StudioRuntime)
    runtime.omnitrix = SimpleNamespace(
        tool_registry=SimpleNamespace(get=lambda name: tool if name == "manim_scientific_diagram" else None)
    )
    runtime.manim_jobs_lock = threading.RLock()
    runtime.manim_jobs = OrderedDict()
    runtime.manim_render_lock = threading.Lock()
    return runtime


class ManimRuntimeApiTests(unittest.TestCase):
    def test_requires_explicit_consent(self):
        runtime = make_runtime(FakeManimTool())
        with self.assertRaisesRegex(ValueError, "Explicit consent"):
            runtime.start_manim_render({"title": "Test", "nodes": [{"label": "A", "x": 0, "y": 0}]})

    def test_rejects_extra_fields(self):
        runtime = make_runtime(FakeManimTool())
        with self.assertRaisesRegex(ValueError, "Unsupported Manim render fields"):
            runtime.start_manim_render({
                "consent": True, "title": "Test",
                "nodes": [{"label": "A", "x": 0, "y": 0}],
                "python": "not accepted",
            })

    def test_missing_manim_is_reported_without_queuing(self):
        tool = FakeManimTool(result=ToolResult(
            success=False,
            error="Manim is not installed in this runtime.",
            metadata={"tool": "manim_scientific_diagram", "available": False, "executed": False},
        ))
        runtime = make_runtime(tool)
        with patch("interfaces.web.server.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Manim is not installed"):
                runtime.start_manim_render({
                    "consent": True, "title": "Test",
                    "nodes": [{"label": "A", "x": 0, "y": 0}],
                })
        self.assertEqual(len(runtime.manim_jobs), 0)

    def test_successful_render_is_tracked_and_artifact_hash_is_checked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "test.mp4"
            runtime = make_runtime(FakeManimTool(artifact))
            with patch("interfaces.web.server.shutil.which", return_value="/usr/bin/manim"):
                accepted = runtime.start_manim_render({
                    "consent": True,
                    "title": "Induction",
                    "nodes": [
                        {"label": "Alternating field", "x": -2, "y": 0},
                        {"label": "Pan heats", "x": 2, "y": 0},
                    ],
                    "arrows": [[0, 1]],
                    "quality": "low",
                })
            self.assertEqual(accepted["status"], "queued")
            job_id = accepted["job_id"]
            deadline = time.monotonic() + 3
            status = runtime.manim_job_status(job_id)
            while status.get("status") in {"queued", "processing"} and time.monotonic() < deadline:
                time.sleep(0.01)
                status = runtime.manim_job_status(job_id)
            self.assertEqual(status["status"], "complete")
            self.assertEqual(status["result"]["quality_review"], "not_run")
            self.assertEqual(status["manifest"]["tasks"][0]["status"], "succeeded")
            self.assertTrue(status["manifest"]["artifacts"][0]["verified"])
            download = runtime.manim_job_artifact(job_id)
            self.assertIsNotNone(download)
            self.assertEqual(download[0], artifact.read_bytes())
            artifact.write_bytes(b"tampered")
            self.assertIsNone(runtime.manim_job_artifact(job_id))


if __name__ == "__main__":
    unittest.main()
