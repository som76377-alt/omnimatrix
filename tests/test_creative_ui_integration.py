"""Static integration checks for the online-to-draft Creative Studio workflow."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CreativeUiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chat_js = (ROOT / "webapp" / "app.js").read_text(encoding="utf-8")
        cls.studio_js = (ROOT / "webapp" / "creative-studio.js").read_text(encoding="utf-8")
        cls.studio_html = (ROOT / "webapp" / "creative-studio.html").read_text(encoding="utf-8")
        cls.director = (ROOT / "core" / "creative_director.py").read_text(encoding="utf-8")

    def test_explicit_creation_prompt_hands_off_in_same_tab_without_prompt_in_url(self):
        self.assertIn("shouldLaunchCreativeStudio(message, readyAttachments.length)", self.chat_js)
        self.assertIn('sessionStorage.setItem("omnitrix-creative-brief-pending", message)', self.chat_js)
        self.assertIn('target.searchParams.set("autoDraft", "1")', self.chat_js)
        self.assertNotIn('target.searchParams.set("creativeBrief"', self.chat_js)
        self.assertIn('sessionStorage.getItem("omnitrix-creative-brief-pending")', self.studio_js)
        self.assertIn("await buildDraftFromBrief()", self.studio_js)

    def test_online_asset_sources_are_explicit_and_license_aware(self):
        for element_id in (
            "online-asset-query", "online-asset-provider", "search-online-assets",
            "pinterest-reference", "build-from-brief", "online-asset-results",
        ):
            self.assertIn('id="' + element_id + '"', self.studio_html)
        self.assertIn("./api/creative/search?", self.studio_js)
        self.assertIn("./api/creative/assets/download?", self.studio_js)
        self.assertIn("rightsVerified", self.studio_js)
        self.assertIn("safeExternalHttps", self.studio_js)
        self.assertIn("Pins are not copied automatically", self.studio_js)

    def test_automatic_remote_visual_analysis_requires_explicit_per_run_consent(self):
        self.assertIn('id="auto-creative-consent"', self.studio_html)
        self.assertIn('if (!$("auto-creative-consent").checked || state.autoFinishBusy) return;', self.studio_js)
        self.assertIn('if (!state.creativeStatus || !state.creativeStatus.configured)', self.studio_js)
        self.assertIn("await runAiDirection()", self.studio_js)
        self.assertIn("No AI visual analysis was claimed", self.studio_js)

    def test_export_reopens_webm_and_checks_actual_decoded_frames(self):
        self.assertIn("async function inspectRenderedVideo(blob, expectedDuration)", self.studio_js)
        self.assertIn('waitForVideoEvent(video, "loadedmetadata"', self.studio_js)
        self.assertIn("possible black/blank output", self.studio_js)
        self.assertIn("This is technical QA, not an AI artistic review.", self.studio_js)
        self.assertIn("could not be verified", self.studio_js)

    def test_graphics_engineer_outputs_only_bounded_native_layers(self):
        self.assertIn("STRICT ANTI-SLOP RULES", self.director)
        self.assertIn('{"text", "rect", "circle", "line", "arrow"}', self.director)
        for element_id in ("add-text-layer", "add-rect-layer", "add-circle-layer", "add-line-layer", "add-arrow-layer"):
            self.assertIn('id="' + element_id + '"', self.studio_html)
        self.assertIn('const allowedLayerTypes = new Set(["text", "rect", "circle", "line", "arrow"])', self.studio_js)
        self.assertIn("A shot may have no more than three added graphic layers.", self.studio_js)
        self.assertIn('case "remove_clip":', self.studio_js)
        self.assertIn("At least one selected shot must remain in the edit", self.studio_js)


if __name__ == "__main__":
    unittest.main()
