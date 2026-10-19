import os
import unittest
from unittest.mock import patch

from core.attachments import (
    accepted_mime_type,
    analyze_attachments,
    media_part_type,
    safe_display_name,
)


class AttachmentContractTests(unittest.TestCase):
    def test_safe_display_name_removes_path_components_and_controls(self):
        self.assertEqual(safe_display_name("../private\\notes.pdf"), "notes.pdf")
        self.assertEqual(safe_display_name(" image 01.png "), "image 01.png")
        with self.assertRaises(ValueError):
            safe_display_name("../")

    def test_supported_mime_types(self):
        self.assertEqual(accepted_mime_type("scan.pdf", "application/pdf"), "application/pdf")
        self.assertEqual(accepted_mime_type("clip.mp4", "video/mp4"), "video/mp4")
        self.assertEqual(accepted_mime_type("voice.wav", "audio/wav"), "audio/wav")
        self.assertEqual(accepted_mime_type("reference.webp", "image/webp"), "image/webp")
        with self.assertRaises(ValueError):
            accepted_mime_type("script.exe", "application/octet-stream")

    def test_media_kind_mapping(self):
        self.assertEqual(media_part_type("image/png"), "image")
        self.assertEqual(media_part_type("application/pdf"), "document")
        self.assertEqual(media_part_type("audio/mpeg"), "audio")
        self.assertEqual(media_part_type("video/webm"), "video")
        with self.assertRaises(ValueError):
            media_part_type("application/zip")

    def test_no_provider_key_is_reported_without_claiming_media_was_analyzed(self):
        record = {
            "id": "a" * 32,
            "name": "reference.png",
            "mime_type": "image/png",
            "size": 12,
            "path": "/not-opened-without-a-provider.png",
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            result = analyze_attachments([record], "Describe this image", api_key="")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["analyzed"], 0)
        self.assertIn("do not claim", result["context"].lower())
        self.assertIn("reference.png", result["context"])

    def test_empty_attachment_list_is_a_noop(self):
        result = analyze_attachments([], "Hello")
        self.assertEqual(result, {
            "status": "none", "count": 0, "analyzed": 0, "context": ""
        })


if __name__ == "__main__":
    unittest.main()
