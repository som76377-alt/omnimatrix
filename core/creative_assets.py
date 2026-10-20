"""License-aware, bounded creative asset discovery for Omnitrix Studio.

Wikimedia Commons works without an API key. Pexels is optional and only enabled
when the owner configures PEXELS_API_KEY. Pinterest is deliberately a reference
search link, not scraped or bulk-downloaded: its developer rules prohibit
unauthorised scraping and restrict storage/reuse of API data.
"""
from __future__ import annotations

from html import unescape
import base64
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import PurePosixPath
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from core.creative_search_planner import build_search_query_variants


MAX_QUERY_CHARS = 180
MAX_RESULTS = 12
MAX_DOWNLOAD_BYTES = 24 * 1024 * 1024
_USER_AGENT = "OmnitrixCreativeStudio/1.0 (license-aware asset search)"
_ALLOWED_DOWNLOAD_HOSTS = {
    "commons": frozenset({"upload.wikimedia.org"}),
    "pexels": frozenset({"images.pexels.com", "videos.pexels.com"}),
}
_ALLOWED_MIME = frozenset({
    "image/jpeg", "image/png", "image/webp", "image/avif",
    "video/mp4", "video/webm", "video/ogg",
})


class CreativeAssetError(ValueError):
    """A safe error raised for invalid or unavailable asset-search operations."""


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain(value: Any, limit: int = 500) -> str:
    if not isinstance(value, str):
        return ""
    parser = _TextOnly()
    try:
        parser.feed(value)
        text = unescape(" ".join(parser.parts))
    except Exception:
        text = re.sub(r"<[^>]*>", " ", value)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _safe_text(value: Any, name: str, max_length: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise CreativeAssetError(f"{name} must be text.")
    text = value.strip()
    if required and not text:
        raise CreativeAssetError(f"{name} cannot be empty.")
    if len(text) > max_length:
        raise CreativeAssetError(f"{name} exceeds the {max_length}-character limit.")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text):
        raise CreativeAssetError(f"{name} contains unsupported control characters.")
    return text


def _read_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 12) -> dict[str, Any]:
    req_headers = {"User-Agent": _USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise CreativeAssetError("The asset provider rejected its credentials or access scope.") from exc
        if exc.code == 429:
            raise CreativeAssetError("The asset provider rate limit was reached. Try later.") from exc
        raise CreativeAssetError(f"The asset provider returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CreativeAssetError("Online asset search is unavailable from this server right now.") from exc
    if len(raw) > 4 * 1024 * 1024:
        raise CreativeAssetError("The asset provider response was too large.")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CreativeAssetError("The asset provider returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise CreativeAssetError("The asset provider returned an invalid response.")
    return data


def generate_creative_image(
    prompt: Any, *, environ: Any = None, aspect_ratio: str = "16:9"
) -> dict[str, Any]:
    """Generate one original image through the current Gemini Interactions API."""
    text = _safe_text(prompt, "Image prompt", 1800, required=True)
    env = os.environ if environ is None else environ
    api_key = str(env.get("GEMINI_API_KEY", "")).strip()
    if not api_key:
        raise CreativeAssetError("AI image generation is unavailable because GEMINI_API_KEY is not configured.")
    model = str(env.get("OMNITRIX_IMAGE_MODEL", "gemini-nano-banana-2.1")).strip()
    # The old 2.5 Flash Image endpoint was shut down in October 2026. Migrate this
    # known legacy default rather than repeatedly attempting a dead endpoint.
    if model == "gemini-2.5-flash-image":
        model = "gemini-nano-banana-2.1"
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", model):
        raise CreativeAssetError("The configured image model name is invalid.")
    if aspect_ratio not in {"16:9", "9:16", "1:1"}:
        raise CreativeAssetError("Image aspect ratio must be 16:9, 9:16, or 1:1.")
    instruction = (
        "Create one original, professionally art-directed image asset. This is a single scene image, "
        "not a video, slideshow, title card, poster, collage, or interface. Use the exact subject and "
        "physical action in the user's brief, credible anatomy and object relationships, deliberate composition, "
        "clear focal hierarchy, matte colours, crisp detail, and a clean background appropriate to the scene. "
        "Avoid generic stock-photo staging, random decorative particles, glowing HUDs, glossy plastic, excessive "
        "gradients, watermarks, brand logos, fake interfaces, misspelled text, and arbitrary object slicing. "
        "Do not render captions; any labels will be added separately by the editor. User's visual brief: "
        + text
    )
    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"
    body = json.dumps({
        "model": model,
        "input": instruction,
        "response_format": {
            "type": "image",
            "mime_type": "image/png",
            "aspect_ratio": aspect_ratio,
            "image_size": "1K",
        },
    }, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise CreativeAssetError("The image provider rejected the request. Check the server key and image-model access.") from exc
        if exc.code == 429:
            raise CreativeAssetError("The image provider quota or rate limit was reached.") from exc
        if exc.code in {400, 404}:
            raise CreativeAssetError(f"The image provider rejected the request (HTTP {exc.code}). Check model access and prompt support.") from exc
        raise CreativeAssetError(f"The image provider returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CreativeAssetError("AI image generation is temporarily unavailable from this server.") from exc
    if len(raw) > 8 * 1024 * 1024:
        raise CreativeAssetError("The generated image response exceeded the size limit.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CreativeAssetError("The image provider returned invalid JSON.") from exc
    parts: list[dict[str, Any]] = []
    steps = payload.get("steps", []) if isinstance(payload, dict) else []
    for step in steps if isinstance(steps, list) else []:
        if isinstance(step, dict) and step.get("type") == "model_output":
            content = step.get("content", [])
            if isinstance(content, list):
                parts.extend(part for part in content if isinstance(part, dict))
    for part in parts:
        mime = str(part.get("mime_type") or part.get("mimeType") or "").lower()
        encoded = part.get("data")
        if mime not in {"image/png", "image/jpeg", "image/webp"} or not isinstance(encoded, str):
            continue
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error):
            continue
        if len(image_bytes) < 1024:
            raise CreativeAssetError("The image provider returned an empty or incomplete image.")
        if len(image_bytes) > 6 * 1024 * 1024:
            raise CreativeAssetError("The generated image exceeds the 6 MB import limit.")
        return {
            "ok": True,
            "provider": "google",
            "model": str(payload.get("model") or model),
            "mime_type": mime,
            "image_base64": base64.b64encode(image_bytes).decode("ascii"),
            "size_bytes": len(image_bytes),
            "estimated_cost_usd": 0.04,
            "note": "One original 1K image was generated. Inspect composition and factual details before publishing.",
        }
    raise CreativeAssetError("The configured model returned no supported image. No image was imported.")


def _google_images_search(query: str, limit: int, env: Any) -> list[dict[str, Any]]:
    """Use Google Custom Search JSON API rather than scraping the Images UI."""
    api_key = str(env.get("GOOGLE_CSE_API_KEY", "")).strip()
    cx = str(env.get("GOOGLE_CSE_CX", "")).strip()
    if not api_key or not cx:
        raise CreativeAssetError("Google Images search is not configured yet. Add GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX as server-side secrets, then restart/redeploy Omnitrix.")
    params = urllib.parse.urlencode({"key": api_key, "cx": cx, "q": query, "searchType": "image", "safe": "active", "num": str(min(limit, 10)), "imgSize": "large"})
    data = _read_json("https://www.googleapis.com/customsearch/v1?" + params)
    rows = data.get("items", [])
    items: list[dict[str, Any]] = []
    if not isinstance(rows, list):
        return items
    allowed_mime = {"image/jpeg", "image/png", "image/webp", "image/avif"}
    for row in rows:
        if not isinstance(row, dict):
            continue
        link = str(row.get("link") or "")
        mime = str(row.get("mime") or "").split(";")[0].strip().lower()
        image_meta = row.get("image") if isinstance(row.get("image"), dict) else {}
        context = str(image_meta.get("contextLink") or "")
        preview = str(image_meta.get("thumbnailLink") or link)
        if mime not in allowed_mime or not link.startswith("https://") or not context.startswith("https://"):
            continue
        try:
            _validate_public_image_url(link)
            _validate_public_image_url(preview)
        except CreativeAssetError:
            continue
        items.append({"id": "google-" + hashlib.sha256(link.encode("utf-8")).hexdigest()[:20], "provider": "google", "title": _plain(row.get("title") or "Google Images result", 240), "description": "Google Images result. Inspect the original source and its rights before reuse.", "kind": "image", "mime_type": mime, "preview_url": preview, "asset_url": link, "source_page": context, "attribution": _plain(row.get("displayLink") or "", 180), "license": "Rights not verified — private draft only; check the original source before reuse", "license_url": context, "rights_verified": False, "duration": 0})
        if len(items) >= limit:
            break
    return items


def _validate_public_image_url(url: Any) -> urllib.parse.ParseResult:
    """Allow HTTPS public hosts only; reject private/local addresses and unsafe redirects."""
    if not isinstance(url, str) or len(url) > 3000:
        raise CreativeAssetError("Image URL is invalid.")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in {None, 443} or parsed.fragment:
        raise CreativeAssetError("Only public HTTPS image URLs are supported.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise CreativeAssetError("Private or local image hosts are not allowed.")
    try:
        addresses = {ipaddress.ip_address(info[4][0].split("%")[0]) for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except (OSError, ValueError, IndexError) as exc:
        raise CreativeAssetError("The image host could not be verified as publicly reachable.") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise CreativeAssetError("Image imports cannot target private, reserved, or local network addresses.")
    return parsed


class _PublicImageRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_image_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def _commons_search(query: str, kind: str, limit: int) -> list[dict[str, Any]]:
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "gsrwhat": "text",
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": "960",
        "format": "json",
        "formatversion": "2",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    data = _read_json(url, headers={"Accept": "application/json"})
    pages = data.get("query", {}).get("pages", [])
    if isinstance(pages, dict):
        pages = list(pages.values())
    items: list[dict[str, Any]] = []
    if not isinstance(pages, list):
        return items
    for page in pages:
        if not isinstance(page, dict):
            continue
        imageinfo = page.get("imageinfo")
        if not isinstance(imageinfo, list) or not imageinfo or not isinstance(imageinfo[0], dict):
            continue
        info = imageinfo[0]
        mime = str(info.get("mime", "")).lower()
        is_image = mime.startswith("image/")
        is_video = mime.startswith("video/")
        if kind == "image" and not is_image:
            continue
        if kind == "video" and not is_video:
            continue
        if not (is_image or is_video):
            continue
        ext = info.get("extmetadata") if isinstance(info.get("extmetadata"), dict) else {}
        def meta(key: str, max_length: int = 300) -> str:
            value = ext.get(key)
            return _plain(value.get("value", "") if isinstance(value, dict) else value, max_length)
        license_name = meta("LicenseShortName", 100) or meta("UsageTerms", 100)
        license_url = meta("LicenseUrl", 500)
        source_page = str(info.get("descriptionurl") or page.get("canonicalurl") or "")
        media_url = str(info.get("url") or "")
        preview_url = str(info.get("thumburl") or (media_url if is_image else ""))
        if not media_url or not source_page or not preview_url:
            continue
        author = meta("Artist", 250) or str(info.get("user", ""))[:250]
        items.append({
            "id": "commons-" + str(page.get("pageid", "")),
            "provider": "commons",
            "title": _plain(str(page.get("title", "Untitled file")).removeprefix("File:"), 240),
            "description": meta("ImageDescription", 360),
            "kind": "image" if is_image else "video",
            "mime_type": mime,
            "preview_url": preview_url,
            "asset_url": media_url if is_video else preview_url,
            "source_page": source_page,
            "attribution": author,
            "license": license_name or "Licence metadata not found — verify before use",
            "license_url": license_url,
            "rights_verified": bool(license_name and license_url),
            "duration": 0,
        })
    return items[:limit]


def _pexels_search(query: str, kind: str, limit: int, api_key: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if kind in {"image", "any"}:
        params = urllib.parse.urlencode({"query": query, "per_page": str(limit), "orientation": "landscape"})
        photos = _read_json(
            "https://api.pexels.com/v1/search?" + params,
            headers={"Authorization": api_key},
        ).get("photos", [])
        if isinstance(photos, list):
            for photo in photos:
                if not isinstance(photo, dict) or not isinstance(photo.get("src"), dict):
                    continue
                src = photo["src"]
                preview = str(src.get("medium") or src.get("large") or "")
                if not preview:
                    continue
                items.append({
                    "id": "pexels-photo-" + str(photo.get("id", "")),
                    "provider": "pexels",
                    "title": _plain(photo.get("alt") or f"Photo by {photo.get('photographer', 'Pexels contributor')}", 240),
                    "description": _plain(photo.get("alt", ""), 360),
                    "kind": "image",
                    "mime_type": "image/jpeg",
                    "preview_url": preview,
                    "asset_url": preview,
                    "source_page": str(photo.get("url") or "https://www.pexels.com/"),
                    "attribution": _plain(photo.get("photographer", ""), 180),
                    "license": "Pexels License — review current licence terms",
                    "license_url": "https://www.pexels.com/license/",
                    "rights_verified": True,
                    "duration": 0,
                })
    if kind in {"video", "any"} and len(items) < limit:
        params = urllib.parse.urlencode({"query": query, "per_page": str(limit - len(items))})
        videos = _read_json(
            "https://api.pexels.com/v1/videos/search?" + params,
            headers={"Authorization": api_key},
        ).get("videos", [])
        if isinstance(videos, list):
            for video in videos:
                if not isinstance(video, dict):
                    continue
                files = video.get("video_files")
                if not isinstance(files, list):
                    continue
                usable = [
                    f for f in files
                    if isinstance(f, dict)
                    and str(f.get("file_type", "")).lower() in {"video/mp4", "video/webm"}
                    and isinstance(f.get("link"), str)
                ]
                if not usable:
                    continue
                usable.sort(key=lambda f: (
                    0 if int(f.get("width") or 99999) <= 1280 else 1,
                    abs(int(f.get("width") or 1280) - 960),
                ))
                selected = usable[0]
                preview = str(video.get("image") or "")
                if not preview:
                    continue
                items.append({
                    "id": "pexels-video-" + str(video.get("id", "")),
                    "provider": "pexels",
                    "title": f"Pexels video {video.get('id', '')}",
                    "description": "Stock video clip; inspect its content before using it.",
                    "kind": "video",
                    "mime_type": str(selected.get("file_type") or "video/mp4"),
                    "preview_url": preview,
                    "asset_url": str(selected["link"]),
                    "source_page": str(video.get("url") or "https://www.pexels.com/videos/"),
                    "attribution": _plain(video.get("user", {}).get("name", "") if isinstance(video.get("user"), dict) else "", 180),
                    "license": "Pexels License — review current licence terms",
                    "license_url": "https://www.pexels.com/license/",
                    "rights_verified": True,
                    "duration": max(0, int(video.get("duration") or 0)),
                })
    return items[:limit]


def search_creative_assets(
    query: Any,
    *,
    provider: Any = "commons",
    kind: Any = "any",
    limit: Any = 10,
    environ: Any = None,
) -> dict[str, Any]:
    """Search bounded public assets and return normalized source/licence metadata."""
    q = _safe_text(query, "Search query", MAX_QUERY_CHARS, required=True)
    provider = _safe_text(provider, "Provider", 30, required=True).lower()
    kind = _safe_text(kind, "Asset type", 20, required=True).lower()
    if provider not in {"commons", "pexels", "pinterest", "google"}:
        raise CreativeAssetError("Choose Wikimedia Commons, configured Pexels, or Pinterest references.")
    if kind not in {"any", "image", "video"}:
        raise CreativeAssetError("Asset type must be any, image or video.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_RESULTS:
        raise CreativeAssetError(f"Result limit must be between 1 and {MAX_RESULTS}.")
    env = os.environ if environ is None else environ
    variants = build_search_query_variants(q)
    search_links = [
        {"query": candidate, "url": (
            "https://www.pinterest.com/search/pins/?" + urllib.parse.urlencode({"q": candidate})
            if provider == "pinterest"
            else "https://www.google.com/search?" + urllib.parse.urlencode({"tbm": "isch", "q": candidate})
        )}
        for candidate in variants
    ]
    if provider == "pinterest":
        return {
            "ok": True, "provider": "pinterest", "query": q, "items": [],
            "search_queries": variants, "search_links": search_links,
            "manual_reference_only": True, "search_url": search_links[0]["url"],
            "note": (
                "Pinterest is reference search only in this build. Open a targeted query, inspect the Pin "
                "and source page, and import only media you have permission to use. Pinterest account access "
                "requires an approved app and OAuth; this route does not log in as you or scrape Pins."
            ),
        }

    searched_queries: list[str] = []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    if provider == "google":
        if not str(env.get("GOOGLE_CSE_API_KEY", "")).strip() or not str(env.get("GOOGLE_CSE_CX", "")).strip():
            return {
                "ok": True, "provider": "google", "query": q, "items": [], "count": 0,
                "search_queries": variants, "search_links": search_links,
                "manual_reference_only": True, "search_url": search_links[0]["url"],
                "note": (
                    "Google Images is being opened as a set of focused visual-reference searches. "
                    "The official Custom Search JSON API is closed to new customers; direct image imports "
                    "remain unverified and should be treated as private drafts until reuse rights are checked."
                ),
            }
        for candidate in variants:
            if len(items) >= limit:
                break
            searched_queries.append(candidate)
            try:
                rows = _google_images_search(candidate, limit - len(items), env)
            except CreativeAssetError:
                # A configured legacy API may be unavailable or denied. Fall back
                # to visible searches rather than falsely claiming search succeeded.
                return {
                    "ok": True, "provider": "google", "query": q, "items": [], "count": 0,
                    "search_queries": variants, "search_links": search_links,
                    "manual_reference_only": True, "search_url": search_links[0]["url"],
                    "note": "The configured Google image-search API could not be used. Open the focused browser searches instead.",
                }
            for item in rows:
                identity = str(item.get("id") or item.get("asset_url") or "")
                if identity and identity not in seen:
                    seen.add(identity)
                    items.append(item)
                    if len(items) >= limit:
                        break
    elif provider == "pexels":
        api_key = str(env.get("PEXELS_API_KEY", "")).strip()
        if not api_key:
            raise CreativeAssetError("Pexels is not configured yet. Add PEXELS_API_KEY as a server-side secret, or use Google Images for manual visual references.")
        for candidate in variants:
            if len(items) >= limit:
                break
            searched_queries.append(candidate)
            rows = _pexels_search(candidate, kind, limit - len(items), api_key)
            for item in rows:
                identity = str(item.get("id") or item.get("asset_url") or "")
                if identity and identity not in seen:
                    seen.add(identity)
                    items.append(item)
                    if len(items) >= limit:
                        break
    else:
        # Query the most specific phrase first, then distinct action/object
        # phrases and short concepts. Do not manufacture "broader" searches by
        # blindly truncating the first N words of the user's prompt.
        for candidate in variants:
            if len(items) >= limit:
                break
            searched_queries.append(candidate)
            for item in _commons_search(candidate, kind, limit - len(items)):
                identity = str(item.get("id") or item.get("asset_url") or "")
                if identity and identity not in seen:
                    seen.add(identity)
                    items.append(item)
                    if len(items) >= limit:
                        break
    return {
        "ok": True, "provider": provider, "query": q, "search_queries": searched_queries, "search_links": search_links if provider == "google" else [], "items": items[:limit],
        "count": min(len(items), limit),
        "note": (
            "Search metadata is not visual verification. Confirm each result actually matches the scene. "
            "Only results with a known licence and licence URL are eligible for automatic selection."
        ),
    }


class _AllowedRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_download_url(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _validate_download_url(url: Any, allowed_hosts: frozenset[str]) -> urllib.parse.ParseResult:
    if not isinstance(url, str) or len(url) > 3000:
        raise CreativeAssetError("Asset URL is invalid.")
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.hostname.lower() not in allowed_hosts
        or parsed.username or parsed.password
        or parsed.port not in {None, 443}
        or parsed.fragment
    ):
        raise CreativeAssetError("Downloads are restricted to the selected asset provider's official media hosts.")
    return parsed


def download_creative_asset(
    url: Any,
    *,
    provider: Any,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> tuple[bytes, str, str]:
    """Download one chosen search result from an allowlisted HTTPS host only."""
    name = _safe_text(provider, "Provider", 30, required=True).lower()
    if name in {"google", "web"}:
        parsed = _validate_public_image_url(url)
        allowed = None
    else:
        if name not in _ALLOWED_DOWNLOAD_HOSTS:
            raise CreativeAssetError("Only Commons, configured Pexels, or selected Google Images results may be downloaded directly.")
        allowed = _ALLOWED_DOWNLOAD_HOSTS[name]
        parsed = _validate_download_url(url, allowed)
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1024 <= max_bytes <= MAX_DOWNLOAD_BYTES:
        raise CreativeAssetError("Invalid asset download size limit.")
    request = urllib.request.Request(urllib.parse.urlunparse(parsed), headers={"User-Agent": _USER_AGENT, "Accept": "image/*" if name in {"google", "web"} else "image/*,video/mp4,video/webm"}, method="GET")
    opener = urllib.request.build_opener(_PublicImageRedirects() if name in {"google", "web"} else _AllowedRedirects(allowed))
    try:
        with opener.open(request, timeout=20) as response:
            if name in {"google", "web"}:
                _validate_public_image_url(response.geturl())
            else:
                _validate_download_url(response.geturl(), allowed)
            content_type = str(response.headers.get_content_type() or "").lower()
            length_header = response.headers.get("Content-Length", "")
            try:
                advertised_length = int(length_header)
            except (TypeError, ValueError):
                advertised_length = 0
            if advertised_length > max_bytes:
                raise CreativeAssetError("The selected asset exceeds the 24 MB import limit.")
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise CreativeAssetError("The selected asset exceeds the 24 MB import limit.")
    except CreativeAssetError:
        raise
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403, 404}:
            raise CreativeAssetError("The asset host would not provide this file. Open the source page to check it.") from exc
        raise CreativeAssetError(f"The asset host returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CreativeAssetError("Could not download that asset from the source host.") from exc
    if content_type not in _ALLOWED_MIME:
        suffix = PurePosixPath(parsed.path).suffix.lower()
        extension_mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".webp": "image/webp", ".avif": "image/avif",
            ".mp4": "video/mp4", ".webm": "video/webm", ".ogv": "video/ogg",
        }
        content_type = extension_mime.get(suffix, "")
    if name in {"google", "web"} and not content_type.startswith("image/"):
        raise CreativeAssetError("Google Images import only accepts image files, not videos or other content.")
    if content_type not in _ALLOWED_MIME or not data:
        raise CreativeAssetError("The source did not return a supported image or video file.")
    filename = PurePosixPath(parsed.path).name[:180] or ("asset.mp4" if content_type.startswith("video/") else "asset.jpg")
    return data, content_type, filename
