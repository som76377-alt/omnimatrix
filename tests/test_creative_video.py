"""Offline tests for the bounded direct AI-video generation adapter."""
import base64
import json
import time
import unittest
from unittest.mock import MagicMock, patch

from core.creative_video import (
    CreativeVideoError,
    _extract_video,
    _prompt_text,
    creative_video_job_status,
    generate_creative_video,
    start_creative_video_job,
)


class CreativeVideoTests(unittest.TestCase):
    def test_missing_server_key_fails_before_network_call(self):
        with patch("core.creative_video.urllib.request.urlopen") as send:
            with self.assertRaisesRegex(CreativeVideoError, "GEMINI_API_KEY"):
                generate_creative_video("A man waves and says hi", environ={})
            send.assert_not_called()

    def test_human_action_prompt_requires_real_motion_and_audio(self):
        prompt = _prompt_text("A man waves his hand and says hi")
        self.assertIn("genuine moving video", prompt)
        self.assertIn("continuous natural motion", prompt)
        self.assertIn("audible speech/audio", prompt)
        self.assertIn("A man waves his hand and says hi", prompt)

    def test_video_parser_rejects_missing_video_bytes(self):
        with self.assertRaisesRegex(CreativeVideoError, "no downloadable video"):
            _extract_video({"steps": [{"type": "model_output", "content": [{"type": "text", "text": "done"}]}]})

    def test_direct_provider_uses_interactions_api_and_returns_real_video_bytes(self):
        video_bytes = b"fake-mp4-payload" * 300
        response_body = {
            "model": "gemini-omni-1.1-flash",
            "steps": [{
                "type": "model_output",
                "content": [{
                    "type": "video",
                    "mime_type": "video/mp4",
                    "data": base64.b64encode(video_bytes).decode("ascii"),
                }],
            }],
        }
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(response_body).encode("utf-8")
        with patch("core.creative_video.urllib.request.urlopen", return_value=response) as send:
            result = generate_creative_video(
                "A man waves and says hi",
                aspect_ratio="9:16",
                resolution="720p",
                environ={"GEMINI_API_KEY": "test-key"},
            )
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://generativelanguage.googleapis.com/v1beta/interactions")
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        self.assertEqual(request.get_method(), "POST")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "gemini-omni-1.1-flash")
        self.assertEqual(body["response_format"]["type"], "video")
        self.assertEqual(body["response_format"]["aspect_ratio"], "9:16")
        self.assertIn("audible speech/audio", body["input"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "gemini-omni-1.1-flash")
        self.assertEqual(result["mime_type"], "video/mp4")
        self.assertEqual(base64.b64decode(result["video_base64"]), video_bytes)
        self.assertEqual(result["aspect_ratio"], "9:16")
        self.assertLessEqual(result["size_bytes"], 24 * 1024 * 1024)

    def test_job_runs_asynchronously_and_result_is_consumed_once(self):
        fake_bytes = base64.b64encode(b"video-content" * 250).decode("ascii")
        provider_result = {
            "ok": True,
            "provider": "google",
            "model": "gemini-omni-1.1-flash",
            "mime_type": "video/mp4",
            "file_name": "omnitrix-test.mp4",
            "video_base64": fake_bytes,
            "size_bytes": len(base64.b64decode(fake_bytes)),
            "aspect_ratio": "16:9",
            "resolution": "720p",
            "note": "test result",
        }
        with patch("core.creative_video.generate_creative_video", return_value=provider_result):
            job = start_creative_video_job(
                "An animated test scene",
                environ={"GEMINI_API_KEY": "test-key"},
            )
            self.assertEqual(job["status"], "queued")
            self.assertEqual(job["model"], "gemini-omni-1.1-flash")
            self.assertGreater(job["estimated_cost_usd"], 0)
            deadline = time.time() + 2
            status = None
            while time.time() < deadline:
                status = creative_video_job_status(job["job_id"])
                if status.get("status") in {"completed", "failed"}:
                    break
                time.sleep(0.01)
            self.assertEqual(status["status"], "completed", status)
            downloaded = creative_video_job_status(job["job_id"], consume_result=True)
            self.assertTrue(downloaded["ok"])
            self.assertEqual(downloaded["video_base64"], fake_bytes)
            missing = creative_video_job_status(job["job_id"])
            self.assertFalse(missing["ok"])


if __name__ == "__main__":
    unittest.main()
