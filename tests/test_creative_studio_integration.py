"""Static integration checks for the user-facing scientific-diagram path."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STUDIO_HTML = ROOT / "webapp" / "creative-studio.html"
STUDIO_JS = ROOT / "webapp" / "creative-studio.js"
STUDIO_CSS = ROOT / "webapp" / "creative-studio.css"
SERVICE_WORKER = ROOT / "webapp" / "sw.js"


class CreativeStudioIntegrationTests(unittest.TestCase):
    def test_science_diagram_controls_are_present_and_styled(self):
        html = STUDIO_HTML.read_text(encoding="utf-8")
        css = STUDIO_CSS.read_text(encoding="utf-8")
        self.assertIn('id="science-diagram-steps"', html)
        self.assertIn('id="build-science-diagram"', html)
        self.assertIn(".science-diagram-controls", css)

    def test_manim_endpoint_has_local_fallback_and_timeline_handoff(self):
        js = STUDIO_JS.read_text(encoding="utf-8")
        self.assertIn('"./api/creative/manim-render"', js)
        self.assertIn('"/artifact"', js)
        self.assertIn("async function renderLocalScienceDiagram", js)
        self.assertIn("async function buildScienceDiagramDraft", js)
        self.assertIn('$("build-science-diagram").addEventListener("click", buildScienceDiagramDraft)', js)
        self.assertIn("await importFiles([output.file])", js)
        self.assertIn("state.project.timeline.push(clip)", js)
        self.assertIn("await inspectRenderedVideo(output.file", js)
        self.assertIn("await deliverRenderedVideo(output.file", js)
        self.assertIn("does not verify scientific correctness", js)

    def test_original_fallback_creates_one_continuous_motion_clip_not_generic_cards(self):
        js = STUDIO_JS.read_text(encoding="utf-8")
        self.assertIn("async function renderOriginalMotionClip", js)
        self.assertIn("drawOriginalMotionFrame", js)
        self.assertIn("createCanvasVideoCapture(scene, 24)", js)
        self.assertIn("await importFiles([file])", js)
        self.assertNotIn('heading: "FOLLOW THE PROCESS"', js)
        self.assertNotIn('heading: "CAUSE BECOMES EFFECT"', js)

    def test_failed_online_download_falls_back_to_original_creation(self):
        js = STUDIO_JS.read_text(encoding="utf-8")
        self.assertIn("Stopping the search/import path and creating an original animated scene instead", js)
        self.assertIn("The free local route will draw a stylised animated character", js)
        self.assertIn('button.textContent = "CREATING…"', js)

    def test_mobile_scroll_and_transition_library_are_present(self):
        html = STUDIO_HTML.read_text(encoding="utf-8")
        css = STUDIO_CSS.read_text(encoding="utf-8")
        js = STUDIO_JS.read_text(encoding="utf-8")
        self.assertIn('id="shot-transition"', html)
        self.assertIn('value="circle-reveal"', html)
        self.assertIn('value="drift-up-left"', html)
        self.assertIn("overflow:visible;overscroll-behavior:auto;touch-action:auto", css)
        self.assertIn('clip.transition || "cut"', js)

    def test_service_worker_cache_version_was_bumped_for_ui_update(self):
        worker = SERVICE_WORKER.read_text(encoding="utf-8")
        self.assertIn('const CACHE_NAME = "omnitrix-shell-v4";', worker)


if __name__ == "__main__":
    unittest.main()
