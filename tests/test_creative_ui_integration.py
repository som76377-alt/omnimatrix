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

    def test_post_render_critic_requires_explicit_consent_and_allows_one_correction_pass(self):
        self.assertIn("async function critiqueRenderedDraft(inspection, renderSignature)", self.studio_js)
        self.assertIn("POST-RENDER VISUAL CRITIC", self.studio_js)
        self.assertIn("const runPostRenderCritic = Boolean", self.studio_js)
        self.assertIn('await renderVideo({ autoCritiqueRetry: true })', self.studio_js)
        self.assertIn("A single bounded re-render will follow.", self.studio_js)
        self.assertIn("sampled frames from the rendered draft", self.studio_html.lower())

    def test_export_reopens_webm_and_checks_actual_decoded_frames(self):
        self.assertIn("async function inspectRenderedVideo(blob, expectedDuration, reviewClipIds, renderTimelineSnapshot)", self.studio_js)
        self.assertIn('waitForVideoEvent(video, "loadedmetadata"', self.studio_js)
        self.assertIn("possible black/blank output", self.studio_js)
        self.assertIn("majority of sampled frames are near-black/blank", self.studio_js)
        self.assertIn("Export blocked — no video was saved", self.studio_js)
        self.assertIn("motionDetected", self.studio_js)
        self.assertIn("frameDelta", self.studio_js)
        self.assertIn("function createCanvasVideoCapture(source, fps)", self.studio_js)
        self.assertIn("source.captureStream(0)", self.studio_js)
        self.assertLess(self.studio_js.index('"video/webm;codecs=vp8"'), self.studio_js.index('"video/webm;codecs=vp9"'))
        self.assertIn("The first timeline clip never decoded a video frame", self.studio_js)
        self.assertIn("This is technical QA, not a guarantee of artistic quality.", self.studio_js)
        self.assertIn("could not be verified", self.studio_js)

    def test_original_animation_is_decoded_and_motion_checked_before_import(self):
        start = self.studio_js.index("async function renderOriginalMotionClip(brief)")
        end = self.studio_js.index("async function requestGeneratedImage(brief)", start)
        original = self.studio_js[start:end]
        self.assertIn("await inspectRenderedVideo(blob, duration, [], [])", original)
        self.assertIn("if (!inspection.motionDetected)", original)
        self.assertIn("No clip was imported", original)
        self.assertLess(original.index("await inspectRenderedVideo(blob, duration, [], [])"), original.index("const output = new File([blob]"))
        render = self.studio_js.split("async function renderVideo(options)", 1)[1].split("async function ensureCurrentPreviewSource()", 1)[0]
        self.assertLess(render.index("await ensureCurrentPreviewSource()"), render.index("recorder.start(500)"))
        self.assertIn("inspectionFailure", render)
        self.assertIn("no video was saved", render.lower())

    def test_rigged_character_engine_has_connected_joints_and_deterministic_action_poses(self):
        start = self.studio_js.index("function drawRiggedHuman(")
        end = self.studio_js.index("function drawOriginalMotionFrame(", start)
        rig = self.studio_js[start:end]
        for action in ("wave", "run", "walk", "dance", "jump", "nod", "idle"):
            self.assertIn('"' + action + '"', rig)
        for invariant in ("const child=", "const leftElbow=", "const rightElbow=", "const leftWrist=", "const rightWrist=", "const leftKnee=", "const rightKnee=", "function limb(", "function joint(", 'g.fillText("Hi!", bubbleX, bubbleY)'):
            self.assertIn(invariant, rig)
        self.assertIn("drawRiggedHuman(g, brief, elapsed, duration, width, height)", self.studio_js)
        self.assertIn("floorY - (127 + lift) * unit", rig)
        self.assertNotIn("if (person && waving)", self.studio_js)
        self.assertIn("Layered vector human rig", self.studio_js)

    def test_graphics_engineer_outputs_only_bounded_native_layers(self):
        self.assertIn("STRICT ANTI-SLOP RULES", self.director)
        self.assertIn('{"text", "rect", "circle", "line", "arrow"}', self.director)
        for element_id in ("add-text-layer", "add-rect-layer", "add-circle-layer", "add-line-layer", "add-arrow-layer"):
            self.assertIn('id="' + element_id + '"', self.studio_html)
        self.assertIn('const allowedLayerTypes = new Set(["text", "rect", "circle", "line", "arrow"])', self.studio_js)
        self.assertIn("A shot may have no more than three added graphic layers.", self.studio_js)
        self.assertIn('case "remove_clip":', self.studio_js)
        self.assertIn("At least one selected shot must remain in the edit", self.studio_js)



    def test_prompt_to_video_defaults_to_original_generation_and_always_renders(self):
        self.assertIn('<option value="original" selected>Original graphics + AI image generation (default)</option>', self.studio_html)
        self.assertIn('if (provider === "original")', self.studio_js)
        self.assertIn("await assembleOriginalGraphicFallback(brief)", self.studio_js)
        fallback = self.studio_js.split("async function assembleOriginalGraphicFallback(brief)", 1)[1].split("\\n  function renderAssets()", 1)[0]
        self.assertIn("await requestGeneratedImage(brief)", fallback)
        self.assertIn("await renderVideo()", fallback)
        self.assertIn("uses gemini omni flash to generate moving footage and native audio", self.studio_html.lower())
        self.assertIn('id="paid-video-consent"', self.studio_html)
        self.assertIn('id="generate-ai-video"', self.studio_html)
        self.assertIn('"./api/mobile/creative/generate-video"', self.studio_js)
        self.assertIn('paid_cost_acknowledged: true', self.studio_js)
        self.assertIn("needsDirectAiVideo", self.studio_js)
        self.assertNotIn('if ($("auto-creative-consent").checked) {\\n      try {\\n        onlineStatus("No suitable source media.', fallback)


    def test_human_motion_or_dialogue_uses_stylised_local_action_and_keeps_paid_option(self):
        self.assertIn("function needsDirectAiVideo(brief)", self.studio_js)
        self.assertIn("The free local route will draw a stylised animated character", self.studio_js)
        self.assertIn('if (needsDirectAiVideo(brief))', self.studio_js)
        self.assertIn('generateDirectAiVideo(String($("creative-brief").value || "").trim())', self.studio_js)
        self.assertIn('await renderVideo()', self.studio_js)
        self.assertIn("async function renderOriginalMotionClip(brief)", self.studio_js)
        self.assertIn("file.omnitrixThumbnail instanceof Blob", self.studio_js)
        self.assertIn("output.omnitrixDuration = duration", self.studio_js)
        self.assertIn('g.fillText("Hi!", bubbleX, bubbleY)', self.studio_js)
        self.assertIn("does not embed spoken audio", self.studio_html.lower())
        self.assertLess(self.studio_html.index('<details class="advanced-brief-controls">'), self.studio_html.index('<details class="paid-video-options">'))

if __name__ == "__main__":
    unittest.main()
