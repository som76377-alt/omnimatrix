import unittest
from unittest.mock import patch

from core.tools.implementations.manim_renderer import ManimRendererTool


class ManimRendererToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = ManimRendererTool()

    def test_schema_exposes_only_structured_inputs(self):
        schema = self.tool.parameters_schema
        self.assertEqual(schema["additionalProperties"], False)
        self.assertNotIn("code", schema["properties"])

    def test_invalid_node_coordinate_is_rejected_before_process_launch(self):
        with patch("core.tools.implementations.manim_renderer.shutil.which", return_value="/usr/bin/manim"), patch("core.tools.implementations.manim_renderer.subprocess.run") as run:
            result = self.tool.execute(title="Test", nodes=[{"label": "Coil", "x": 99, "y": 0}])
        self.assertFalse(result.success)
        run.assert_not_called()

    def test_invalid_arrow_index_is_rejected(self):
        result = self.tool.execute(title="Test", nodes=[{"label": "Coil", "x": 0, "y": 0}], arrows=[[0, 1]])
        self.assertFalse(result.success)

    def test_missing_manim_uses_bundled_code_renderer(self):
        import os
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as output_dir, patch.dict(os.environ, {"OMNITRIX_ARTIFACT_DIR": output_dir}), patch("core.tools.implementations.manim_renderer.shutil.which", return_value=None):
            result = self.tool.execute(
                title="Coil heats pan",
                nodes=[
                    {"label": "Alternating field", "x": -3.5, "y": 0},
                    {"label": "Pan heats", "x": 3.5, "y": 0},
                ],
                arrows=[[0, 1]],
                quality="low",
            )
            self.assertTrue(result.success, result.error)
            self.assertEqual(result.metadata["renderer"], "python-raster-ffmpeg-fallback")
            artifact = Path(result.output["artifact_path"])
            self.assertTrue(artifact.is_file())
            self.assertGreater(artifact.stat().st_size, 2048)
            self.assertEqual(result.output["format"], "mp4")


if __name__ == "__main__":
    unittest.main()
