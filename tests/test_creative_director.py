"""Offline regression tests for consent-gated Creative Studio direction."""
import base64
import json
import unittest
from unittest.mock import Mock

from core.creative_director import (
    CreativeDirectorError,
    analyze_creative_request,
    creative_model_status,
    validate_plan,
)


def preview_url():
    # Marker-only JPEG is sufficient for the mocked analyzer; production sends it to the provider.
    # Minimal SOF marker for a bounded 1 x 1 JPEG header; the mocked analyzer never decodes pixels.
    image = b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00\xff\xd9"
    return "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")


def make_payload():
    return {
        "consent": True,
        "brief": "A short, restrained science explainer.",
        "consent_clip_ids": ["clip-1"],
        "allow_reorder": False,
        "assets": [{
            "asset_id": "asset-1",
            "clip_id": "clip-1",
            "name": "coil.png",
            "preview_data_url": preview_url(),
            "duration": 4,
            "motion": "none",
            "fit": "cover",
        }],
    }


def candidate_plan():
    return {
        "schema_version": 1,
        "summary": "Use a clear establishing shot, then a measured push-in.",
        "observations": [{
            "asset_id": "asset-1",
            "clip_id": "clip-1",
            "observation": "The preview shows a coil; fine details are not clear at thumbnail size.",
        }],
        "operations": [
            {"type": "set_duration", "asset_id": "asset-1", "clip_id": "clip-1", "duration_seconds": 3.5},
            {"type": "set_motion", "asset_id": "asset-1", "clip_id": "clip-1", "preset": "slow-zoom"},
            {"type": "set_title_style", "asset_id": "asset-1", "clip_id": "clip-1",
             "position": "bottom", "font": "sans", "size": 44, "color": "#d6fa62"},
        ],
    }


class CreativeDirectorTests(unittest.TestCase):
    def analyzer_for(self, payload, candidate=None):
        result_text = json.dumps(candidate if candidate is not None else candidate_plan())
        def fake_analyzer(records, question):
            self.assertEqual(len(records), len(payload["assets"]))
            self.assertTrue(all(record["mime_type"] == "image/jpeg" for record in records))
            self.assertTrue(all(__import__("pathlib").Path(record["path"]).is_file() for record in records))
            self.assertIn("Return ONLY one JSON object", question)
            return {
                "status": "complete",
                "analyzed": len(records),
                "context": "Worker: gemini.multimodal; model/tool: gemini-test\n" + result_text,
                "worker": "gemini.multimodal",
                "model": "gemini-test",
            }
        return fake_analyzer

    def test_missing_consent_is_rejected_before_model_call(self):
        payload = make_payload()
        payload["consent"] = False
        analyzer = Mock()
        with self.assertRaises(CreativeDirectorError):
            analyze_creative_request(payload, analyzer=analyzer, environ={"GEMINI_API_KEY": "test"})
        analyzer.assert_not_called()

    def test_consent_selection_must_match_exact_submitted_clip_ids(self):
        payload = make_payload()
        payload["consent_clip_ids"] = []
        with self.assertRaisesRegex(CreativeDirectorError, "exact consented selection"):
            analyze_creative_request(payload, analyzer=Mock(), environ={"GEMINI_API_KEY": "test"})

    def test_rejects_non_jpeg_and_original_file_payloads(self):
        payload = make_payload()
        payload["assets"][0]["preview_data_url"] = "data:image/png;base64,AAAA"
        with self.assertRaisesRegex(CreativeDirectorError, "resized JPEG"):
            analyze_creative_request(payload, analyzer=Mock(), environ={"GEMINI_API_KEY": "test"})


    def test_rejects_jpeg_larger_than_thumbnail_bounds(self):
        payload = make_payload()
        # A 500 x 220 SOF header exceeds the browser thumbnail's actual bound.
        oversized = b"\xff\xd8\xff\xc0\x00\x11\x08\x00\xdc\x01\xf4\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00\xff\xd9"
        payload["assets"][0]["preview_data_url"] = "data:image/jpeg;base64," + base64.b64encode(oversized).decode("ascii")
        with self.assertRaisesRegex(CreativeDirectorError, "no larger than 360"):
            analyze_creative_request(payload, analyzer=Mock(), environ={"GEMINI_API_KEY": "test"})

    def test_unconfigured_provider_returns_unavailable_not_success(self):
        payload = make_payload()
        analyzer = Mock()
        result = analyze_creative_request(payload, analyzer=analyzer, environ={})
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("plan", result)
        analyzer.assert_not_called()

    def test_valid_plan_is_schema_checked_and_never_applied_by_backend(self):
        payload = make_payload()
        result = analyze_creative_request(
            payload, analyzer=self.analyzer_for(payload), environ={"GEMINI_API_KEY": "test"}
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["worker"], "gemini.multimodal")
        self.assertEqual(result["model"], "gemini-test")
        self.assertEqual(result["plan"]["operations"][0]["duration_seconds"], 3.5)
        self.assertFalse(result["edits_applied"])
        self.assertTrue(result["used_resized_previews_only"])

    def test_rejects_unknown_asset_ids_without_partial_application(self):
        payload = make_payload()
        plan = candidate_plan()
        plan["operations"][0]["asset_id"] = "asset-not-approved"
        result = analyze_creative_request(
            payload, analyzer=self.analyzer_for(payload, plan), environ={"GEMINI_API_KEY": "test"}
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "invalid_plan")
        self.assertNotIn("plan", result)

    def test_rejects_unsupported_transition_operations(self):
        payload = make_payload()
        plan = candidate_plan()
        plan["operations"].append({
            "type": "cross_dissolve", "asset_id": "asset-1", "clip_id": "clip-1", "duration_seconds": 1
        })
        result = analyze_creative_request(
            payload, analyzer=self.analyzer_for(payload, plan), environ={"GEMINI_API_KEY": "test"}
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "invalid_plan")
        self.assertIn("unsupported edit operation", result["error"])

    def test_rejects_malformed_model_json(self):
        payload = make_payload()
        analyzer = lambda records, question: {
            "status": "complete", "analyzed": 1,
            "context": "Worker: gemini.multimodal; model/tool: gemini-test\nnot json",
            "worker": "gemini.multimodal", "model": "gemini-test",
        }
        result = analyze_creative_request(payload, analyzer=analyzer, environ={"GEMINI_API_KEY": "test"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "invalid_plan")
        self.assertNotIn("plan", result)

    def test_provider_partial_result_does_not_claim_a_completed_plan(self):
        payload = make_payload()
        analyzer = lambda records, question: {"status": "partial", "analyzed": 0, "context": "partial"}
        result = analyze_creative_request(payload, analyzer=analyzer, environ={"GEMINI_API_KEY": "test"})
        self.assertFalse(result["ok"])
        self.assertNotEqual(result["status"], "complete")
        self.assertNotIn("plan", result)


    def test_video_duration_cannot_exceed_remaining_source_length(self):
        assets = [{
            "asset_id": "asset-1", "clip_id": "clip-1", "name": "clip.mp4",
            "media_type": "video/mp4", "source_duration": 12.0, "source_in": 4.0,
        }]
        plan = {
            "schema_version": 1, "summary": "Use a clip within source bounds.", "observations": [],
            "operations": [{
                "type": "set_duration", "asset_id": "asset-1", "clip_id": "clip-1",
                "duration_seconds": 9.0,
            }],
        }
        with self.assertRaisesRegex(CreativeDirectorError, "remaining source clip length"):
            validate_plan(plan, assets, allow_reorder=False)

    def test_reorder_requires_every_selected_clip_exactly_once_and_permission(self):
        rows = [
            {"asset_id": "asset-1", "clip_id": "clip-1", "name": "One"},
            {"asset_id": "asset-2", "clip_id": "clip-2", "name": "Two"},
        ]
        plan = {"schema_version": 1, "summary": "Order", "observations": [],
                "operations": [{"type": "reorder_timeline", "clip_ids": ["clip-2", "clip-1"]}]}
        with self.assertRaisesRegex(CreativeDirectorError, "only when every timeline shot"):
            validate_plan(plan, rows, allow_reorder=False)
        with self.assertRaisesRegex(CreativeDirectorError, "every approved clip"):
            validate_plan({"schema_version": 1, "summary": "Order", "observations": [],
                           "operations": [{"type": "reorder_timeline", "clip_ids": ["clip-1"]}]},
                          rows, allow_reorder=True)
        valid = validate_plan(plan, rows, allow_reorder=True)
        self.assertEqual(valid["operations"][0]["clip_ids"], ["clip-2", "clip-1"])

    def test_model_status_does_not_claim_live_health(self):
        self.assertFalse(creative_model_status({})["configured"])
        status = creative_model_status({"GEMINI_API_KEY": "present", "OMNITRIX_MULTIMODAL_MODEL": "demo-model"})
        self.assertTrue(status["configured"])
        self.assertFalse(status["runtime_health_checked"])
        self.assertEqual(status["model"], "demo-model")


if __name__ == "__main__":
    unittest.main()
