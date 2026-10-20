"""Runtime-aware Creative Studio tool registry policy tests."""
import json
import tempfile
import unittest
from pathlib import Path

from core.creative_tool_registry import load_creative_tool_registry, select_creative_tools

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "config" / "creative-studio-tools.json"


class CreativeToolRegistryTests(unittest.TestCase):
    def setUp(self):
        self.lookup = lambda name: f"/fake/bin/{name}" if name in {"manim", "ffmpeg", "cline"} else None
        self.env = {
            "GEMINI_API_KEY": "test-key-not-a-real-secret",
            "OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA": "true",
            "OLLAMA_HOST": "http://127.0.0.1:11434",
            "OMNITRIX_LOCAL_CODING_MODEL": "qwen-coder-test",
        }
        self.registry = load_creative_tool_registry(CATALOGUE, environ=self.env, executable_lookup=self.lookup)

    def engine(self, engine_id):
        return next(item for item in self.registry["engines"] if item["id"] == engine_id)

    def test_runtime_availability_is_separate_from_catalogue_integration(self):
        self.assertEqual(self.engine("manim-scientific-renderer")["runtime_state"], "installed")
        self.assertTrue(self.engine("manim-scientific-renderer")["runtime_available"])
        self.assertEqual(self.engine("blender")["runtime_state"], "not-configured")
        self.assertFalse(self.engine("blender")["runtime_available"])
        self.assertEqual(self.engine("cline-cli")["runtime_state"], "installed")
        self.assertFalse(self.engine("cline-cli")["integrated"])
        self.assertEqual(self.engine("ollama-local-coding")["runtime_state"], "configured-unverified")
        self.assertFalse(self.engine("ollama-local-coding")["integrated"])

    def test_snapshot_never_serializes_provider_secret_values(self):
        encoded = json.dumps(self.registry)
        self.assertNotIn("test-key-not-a-real-secret", encoded)
        self.assertNotIn('"GEMINI_API_KEY":', encoded)
        self.assertTrue(self.engine("ai-raster-image-generation")["requires_paid_cost_acknowledgement"])

    def test_zero_cost_selection_excludes_paid_image_generation(self):
        selected = select_creative_tools(self.registry, "prompt-to-image", spend_mode="zero_cost",
                                         consent=True, paid_cost_acknowledged=True, surface="server")
        self.assertEqual(selected, [])

    def test_paid_media_requires_allow_paid_consent_and_cost_acknowledgement(self):
        capability = "prompt-to-image"
        self.assertEqual(select_creative_tools(self.registry, capability, spend_mode="allow_paid"), [])
        self.assertEqual(select_creative_tools(self.registry, capability, spend_mode="allow_paid", consent=True), [])
        selected = select_creative_tools(self.registry, capability, spend_mode="allow_paid",
                                         consent=True, paid_cost_acknowledged=True, surface="server")
        self.assertEqual([item["id"] for item in selected], ["ai-raster-image-generation"])

    def test_paid_media_remains_unavailable_when_server_gate_is_off(self):
        registry = load_creative_tool_registry(CATALOGUE,
            environ={"GEMINI_API_KEY": "configured", "OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA": "false"},
            executable_lookup=self.lookup)
        selected = select_creative_tools(registry, "prompt-to-image", spend_mode="allow_paid",
                                          consent=True, paid_cost_acknowledged=True)
        self.assertEqual(selected, [])

    def test_browser_tools_are_not_misreported_as_server_executables(self):
        self.assertEqual(self.engine("canvas-compositor")["runtime_state"], "client-side")
        self.assertFalse(self.engine("canvas-compositor")["runtime_available"])
        browser = select_creative_tools(self.registry, "webm-render", spend_mode="zero_cost", surface="browser")
        self.assertIn("canvas-compositor", [item["id"] for item in browser])

    def test_unknown_spend_mode_and_surface_fail_closed(self):
        with self.assertRaises(ValueError):
            select_creative_tools(self.registry, "coding", spend_mode="unlimited")
        with self.assertRaises(ValueError):
            select_creative_tools(self.registry, "coding", surface="anywhere")

    def test_duplicate_catalogue_ids_are_rejected(self):
        source = json.loads(CATALOGUE.read_text(encoding="utf-8"))
        source["engines"].append(dict(source["engines"][0]))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "catalogue.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique"):
                load_creative_tool_registry(path, environ={}, executable_lookup=lambda _: None)


if __name__ == "__main__":
    unittest.main()
