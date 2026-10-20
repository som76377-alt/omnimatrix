"""Offline tests for licence-aware creative asset discovery."""
import unittest
from unittest.mock import patch

from core.creative_assets import (
    CreativeAssetError,
    _validate_download_url,
    search_creative_assets,
    download_creative_asset,
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
        with self.assertRaisesRegex(CreativeAssetError, "Commons or configured Pexels"):
            download_creative_asset(
                "https://www.pinterest.com/pin/example", provider="pinterest"
            )

    def test_invalid_limits_and_query_are_rejected(self):
        with self.assertRaises(CreativeAssetError):
            search_creative_assets("x" * 181, provider="commons", environ={})
        with self.assertRaises(CreativeAssetError):
            search_creative_assets("coil", provider="commons", limit=99, environ={})


if __name__ == "__main__":
    unittest.main()
