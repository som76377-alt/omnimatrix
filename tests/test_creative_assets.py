"""Offline tests for licence-aware creative asset discovery."""
import unittest
import base64
import json
from unittest.mock import patch

from core.creative_assets import (
    CreativeAssetError,
    _validate_download_url,
    search_creative_assets,
    download_creative_asset,
    generate_creative_image,
)


class CreativeAssetSearchTests(unittest.TestCase):
    def test_pinterest_is_reference_only_and_never_returns_downloadable_items(self):
        result = search_creative_assets(
            "induction stove science", provider="pinterest", kind="image", environ={}
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["manual_reference_only"])
        self.assertEqual(result["items"], [])
        self.assertIn("induction+stove+science", result["search_url"])
        self.assertIn("pinterest.com/search/pins/", result["search_url"])

    def test_image_generation_requires_a_server_side_gemini_key(self):
        with self.assertRaisesRegex(CreativeAssetError, "GEMINI_API_KEY"):
            generate_creative_image("A scientific induction coil", environ={})

    def test_image_generation_parses_bounded_inline_image_response(self):
        image_bytes = b"\x89PNG\r\n\x1a\n" + (b"image-data" * 150)
        response_body = {
            "model": "gemini-nano-banana-2.1",
            "steps": [{
                "type": "model_output",
                "content": [{
                    "type": "image",
                    "mime_type": "image/png",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }],
            }],
        }
        response = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(response_body).encode("utf-8")
        with patch("core.creative_assets.urllib.request.urlopen", return_value=response) as send:
            result = generate_creative_image(
                "An original technical illustration of an induction stove",
                environ={"GEMINI_API_KEY": "test-key"},
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "google")
        self.assertEqual(result["model"], "gemini-nano-banana-2.1")
        self.assertEqual(result["mime_type"], "image/png")
        self.assertEqual(base64.b64decode(result["image_base64"]), image_bytes)
        self.assertLessEqual(result["size_bytes"], 6 * 1024 * 1024)
        request = send.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/v1beta/interactions"))
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "gemini-nano-banana-2.1")
        self.assertEqual(payload["response_format"]["type"], "image")
        self.assertEqual(payload["response_format"]["aspect_ratio"], "16:9")

    def test_pexels_requires_explicit_server_side_key(self):
        with patch("core.creative_assets._read_json") as read_json:
            with self.assertRaisesRegex(CreativeAssetError, "PEXELS_API_KEY"):
                search_creative_assets("ocean", provider="pexels", environ={})
            read_json.assert_not_called()

    def test_commons_maps_source_and_licence_metadata(self):
        payload = {
            "query": {
                "pages": [{
                    "pageid": 123,
                    "title": "File:Induction coil.jpg",
                    "imageinfo": [{
                        "url": "https://upload.wikimedia.org/wikipedia/commons/1/1a/Induction_coil.jpg",
                        "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Induction_coil.jpg/960px-Induction_coil.jpg",
                        "mime": "image/jpeg",
                        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Induction_coil.jpg",
                        "extmetadata": {
                            "LicenseShortName": {"value": "CC BY-SA 4.0"},
                            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                            "Artist": {"value": "Example photographer"},
                            "ImageDescription": {"value": "A close-up induction coil."},
                        },
                    }],
                }]
            }
        }
        with patch("core.creative_assets._read_json", return_value=payload):
            result = search_creative_assets("induction coil", provider="commons", kind="image", environ={})
        self.assertEqual(result["count"], 1)
        asset = result["items"][0]
        self.assertEqual(asset["provider"], "commons")
        self.assertEqual(asset["title"], "Induction coil.jpg")
        self.assertEqual(asset["license"], "CC BY-SA 4.0")
        self.assertTrue(asset["rights_verified"])
        self.assertEqual(asset["attribution"], "Example photographer")
        self.assertEqual(asset["kind"], "image")

    def test_unknown_licence_is_not_marked_reusable(self):
        payload = {
            "query": {"pages": [{
                "pageid": 1, "title": "File:Unknown.jpg",
                "imageinfo": [{
                    "url": "https://upload.wikimedia.org/a.jpg",
                    "thumburl": "https://upload.wikimedia.org/a.jpg",
                    "mime": "image/jpeg", "descriptionurl": "https://commons.wikimedia.org/wiki/File:Unknown.jpg",
                    "extmetadata": {},
                }],
            }]}
        }
        with patch("core.creative_assets._read_json", return_value=payload):
            result = search_creative_assets("unknown", provider="commons", environ={})
        self.assertFalse(result["items"][0]["rights_verified"])

    def test_asset_download_url_rejects_non_allowlisted_hosts(self):
        for url in (
            "http://upload.wikimedia.org/file.jpg",
            "https://127.0.0.1/private",
            "https://evil.example/payload.jpg",
            "https://upload.wikimedia.org.evil.example/file.jpg",
            "https://user@upload.wikimedia.org/file.jpg",
        ):
            with self.subTest(url=url):
                with self.assertRaises(CreativeAssetError):
                    _validate_download_url(url, frozenset({"upload.wikimedia.org"}))

    def test_download_refuses_pinterest_as_a_media_provider(self):
        with self.assertRaisesRegex(CreativeAssetError, "Only Commons"):
            download_creative_asset(
                "https://www.pinterest.com/pin/example", provider="pinterest"
            )

    def test_commons_search_automatically_broadens_specific_queries(self):
        def fake_search(query, kind, limit):
            if query == "induction stove":
                return [{
                    "id": "commons-1", "asset_url": "https://upload.wikimedia.org/one.jpg",
                    "title": "Induction stove", "provider": "commons",
                }]
            return []

        with patch("core.creative_assets._commons_search", side_effect=fake_search) as search:
            result = search_creative_assets(
                "induction stove magnetic field pan atoms", provider="commons", limit=4, environ={}
            )
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["query"], "induction stove magnetic field pan atoms")
        self.assertIn("induction stove", result["search_queries"])
        self.assertGreaterEqual(search.call_count, 2)

    def test_invalid_limits_and_query_are_rejected(self):
        with self.assertRaises(CreativeAssetError):
            search_creative_assets("x" * 181, provider="commons", environ={})
        with self.assertRaises(CreativeAssetError):
            search_creative_assets("coil", provider="commons", limit=99, environ={})


    def test_google_search_falls_back_to_manual_reference_without_legacy_api_credentials(self):
        result = search_creative_assets("induction pan", provider="google", environ={})
        self.assertTrue(result["manual_reference_only"])
        self.assertIn("google.com/search?", result["search_url"])
        self.assertIn("tbm=isch", result["search_url"])

    def test_google_search_normalizes_unverified_image_results(self):
        payload = {"items": [{"title": "Induction pan", "link": "https://images.example.test/pan.jpg", "mime": "image/jpeg", "displayLink": "example.test", "image": {"contextLink": "https://example.test/article", "thumbnailLink": "https://images.example.test/thumb.jpg"}}]}
        parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse("https://images.example.test/pan.jpg")
        with patch("core.creative_assets._read_json", return_value=payload), patch("core.creative_assets._validate_public_image_url", return_value=parsed):
            result = search_creative_assets("induction pan", provider="google", environ={"GOOGLE_CSE_API_KEY": "key", "GOOGLE_CSE_CX": "cx"})
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["provider"], "google")
        self.assertFalse(result["items"][0]["rights_verified"])
        self.assertIn("private draft", result["items"][0]["license"])

    def test_google_import_rejects_local_and_non_https_urls(self):
        validator = __import__("core.creative_assets", fromlist=["_validate_public_image_url"])._validate_public_image_url
        for url in ("http://example.com/pan.jpg", "https://127.0.0.1/pan.jpg", "https://localhost/pan.jpg"):
            with self.subTest(url=url):
                with self.assertRaises(CreativeAssetError):
                    validator(url)

if __name__ == "__main__":
    unittest.main()
