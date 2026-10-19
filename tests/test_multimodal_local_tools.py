"""Offline tests for safe optional local media adapters."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.multimodal import local_tools


class LocalToolSafetyTests(unittest.TestCase):
    def test_missing_binary_is_reported_without_shell_execution(self):
        with patch("core.multimodal.local_tools.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "FFprobe is not installed"):
                local_tools.probe_media("/tmp/no-such-file.mp4")

    def test_probe_timeout_is_bounded(self):
        with patch("core.multimodal.local_tools.shutil.which", return_value="/usr/bin/ffprobe"):
            with self.assertRaises(ValueError):
                local_tools.probe_media("/tmp/file.mp4", timeout_seconds=0)

    def test_rejects_empty_and_oversized_files(self):
        with TemporaryDirectory() as directory:
            empty = Path(directory) / "empty.wav"
            empty.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                local_tools._input_path(str(empty))
            large = Path(directory) / "large.wav"
            large.write_bytes(b"x" * 20)
            with patch.object(local_tools, "MAX_LOCAL_INPUT_BYTES", 10):
                with self.assertRaisesRegex(ValueError, "size limit"):
                    local_tools._input_path(str(large))

    def test_optional_dependencies_fail_cleanly(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "file.pdf"
            path.write_bytes(b"%PDF fake test data")
            with patch("builtins.__import__", side_effect=ImportError("missing optional dependency")):
                with self.assertRaisesRegex(RuntimeError, "Docling is not installed"):
                    local_tools.extract_document(str(path))

    def test_invalid_transcription_options_are_rejected_before_model_load(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "file.wav"
            path.write_bytes(b"fake audio")
            with self.assertRaises(ValueError):
                local_tools.transcribe_audio(str(path), model_size="unbounded")
            with self.assertRaises(ValueError):
                local_tools.transcribe_audio(str(path), language="bad language code")

    def test_local_workers_are_registered_without_claiming_missing_tools_are_enabled(self):
        from core.multimodal.providers import build_provider_registry
        registry = build_provider_registry()
        by_id = {item["worker_id"]: item for item in registry.describe()}
        self.assertIn("paddleocr.local", by_id)
        self.assertIn("docling.local", by_id)
        self.assertIn("faster_whisper.local", by_id)
        self.assertIn("pyscenedetect.local", by_id)
        from core.multimodal.adapters import toolchain_status
        self.assertEqual(by_id["paddleocr.local"]["enabled"], toolchain_status()["paddleocr"]["available"])


if __name__ == "__main__":
    unittest.main()
