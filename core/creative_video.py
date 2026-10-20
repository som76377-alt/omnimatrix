"""Bounded direct text-to-video generation via the Gemini Interactions API.

Video generation is a paid external side effect. The HTTP route requires explicit
per-request price acknowledgement; generation runs in a worker so the UI can poll
a job rather than hold one long request open.
"""
from __future__ import annotations

import base64
from collections import deque
from dataclasses import dataclass
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


MODEL_DEFAULT = "gemini-omni-1.1-flash"
MAX_PROMPT_CHARS = 4000
MAX_VIDEO_BYTES = 24 * 1024 * 1024
MAX_RESPONSE_BYTES = 36 * 1024 * 1024
VIDEO_SECONDS_ESTIMATE = 8
VIDEO_COST_USD_PER_SECOND_720P = 0.10
_JOB_MAX = 8
_JOB_MAX_ACTIVE = 2
_JOB_TTL_SECONDS = 30 * 60
_USER_AGENT = "OmnitrixCreativeStudio/1.0 (direct video generation)"


class CreativeVideoError(ValueError):
    """Safe error for invalid, unavailable, or failed video generation."""


def _prompt_text(value: Any) -> str:
    if not isinstance(value, str):
        raise CreativeVideoError("Describe the video in plain text.")
    prompt = value.strip()
    if not prompt:
        raise CreativeVideoError("The video prompt cannot be empty.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise CreativeVideoError(f"The video prompt exceeds {MAX_PROMPT_CHARS} characters.")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in prompt):
        raise CreativeVideoError("The video prompt contains unsupported control characters.")
    # Ask for genuine movement and spoken audio when the request calls for dialogue.
    # Keep the original prompt intact; do not replace an action with text overlays.
    action_words = re.compile(r"\b(wav(?:e|es|ing)|walk(?:s|ing)?|run(?:s|ning)?|dance(?:s|ing)?|talk(?:s|ing)?|say(?:s|ing)?|speaks?|sing(?:s|ing)?|moves?|drives?)\b", re.I)
    dialogue_words = re.compile(r"\b(say|says|saying|speaks?|talks?|talking|dialogue|voice|sings?|singing|audio)\b", re.I)
    if action_words.search(prompt):
        prompt = (
            "Create a genuine moving video, not a still image, slideshow, storyboard, "
            "or collection of title cards. Show the action actually happening with "
            "continuous natural motion and coherent anatomy. "
            + ("Include natural, synchronized audible speech/audio for the requested dialogue; do not replace speech with on-screen text. " if dialogue_words.search(prompt) else "")
            + "User's scene brief: " + prompt
        )
    return prompt

def _model_id(env: Any) -> str:
    model = str(env.get("OMNITRIX_VIDEO_MODEL", MODEL_DEFAULT)).strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", model):
        raise CreativeVideoError("The configured video model identifier is invalid.")
    return model


def _extract_video(payload: Any) -> tuple[bytes, str]:
    if not isinstance(payload, dict):
        raise CreativeVideoError("The video provider returned an invalid response.")
    steps = payload.get("steps")
    if not isinstance(steps, list):
        steps = []
    # REST Interactions API returns model_output steps with video data in content.
    candidates: list[dict[str, Any]] = []
    for step in steps:
        if isinstance(step, dict) and step.get("type") == "model_output":
            content = step.get("content", [])
            if isinstance(content, list):
                candidates.extend(part for part in content if isinstance(part, dict))
    for part in candidates:
        mime = str(part.get("mime_type") or part.get("mimeType") or "").lower()
        encoded = part.get("data")
        if mime.startswith("video/") and isinstance(encoded, str):
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise CreativeVideoError("The video provider returned corrupted video data.") from exc
            if len(raw) < 2048:
                raise CreativeVideoError("The provider's video output was empty or incomplete.")
            if len(raw) > MAX_VIDEO_BYTES:
                raise CreativeVideoError("The generated video exceeds the phone's 24 MB save limit. Request a shorter/lower-resolution clip.")
            return raw, mime if mime in {"video/mp4", "video/webm"} else "video/mp4"
        if mime.startswith("video/") and part.get("uri"):
            raise CreativeVideoError(
                "The provider returned a hosted-video URI instead of inline video bytes. "
                "URI delivery is not enabled in this build, so no local file was saved."
            )
    raise CreativeVideoError("The model returned no downloadable video. It may have rejected the prompt or lacks video-generation access.")


def generate_creative_video(
    prompt: Any,
    *,
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    environ: Any = None,
) -> dict[str, Any]:
    """Create one actual video with native audio when supported by the model."""
    env = os.environ if environ is None else environ
    api_key = str(env.get("GEMINI_API_KEY", "")).strip()
    if not api_key:
        raise CreativeVideoError("Direct AI video is unavailable because GEMINI_API_KEY is not configured on the server.")
    model = _model_id(env)
    text = _prompt_text(prompt)
    if aspect_ratio not in {"16:9", "9:16"}:
        raise CreativeVideoError("Aspect ratio must be 16:9 or 9:16.")
    if resolution not in {"360p", "720p"}:
        raise CreativeVideoError("This mobile workflow supports 360p or 720p output.")
    request_body = {
        "model": model,
        "input": text,
        "response_format": {
            "type": "video",
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
        },
    }
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(request_body, separators=(",", ":")).encode("utf-8"),
        headers={
            "User-Agent": _USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise CreativeVideoError(
                "Gemini rejected the video request. The API key may lack paid video-model access or billing is not enabled."
            ) from exc
        if exc.code == 429:
            raise CreativeVideoError("Gemini video quota or rate limit reached. No video was returned; try again later.")
        if exc.code in {400, 404}:
            raise CreativeVideoError(
                f"Gemini rejected this video request (HTTP {exc.code}). Check model access and prompt support."
            ) from exc
        raise CreativeVideoError(f"Gemini video generation returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CreativeVideoError("Gemini video generation could not reach the provider. Check server connectivity and retry.") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise CreativeVideoError("The provider response exceeds the bounded 36 MB transfer limit.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CreativeVideoError("The provider returned invalid JSON instead of a video result.") from exc
    video_bytes, mime_type = _extract_video(payload)
    encoded = base64.b64encode(video_bytes).decode("ascii")
    extension = "webm" if mime_type == "video/webm" else "mp4"
    return {
        "ok": True,
        "provider": "google",
        "model": str(payload.get("model") or model),
        "mime_type": mime_type,
        "file_name": f"omnitrix-ai-video-{uuid.uuid4().hex[:8]}.{extension}",
        "video_base64": encoded,
        "size_bytes": len(video_bytes),
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "note": "This file was returned by a video-generation model. Playback, speech/audio, and scene quality still need human inspection.",
    }


@dataclass
class _VideoJob:
    job_id: str
    status: str
    created_at: float
    prompt: str
    aspect_ratio: str
    resolution: str
    model: str
    result: dict[str, Any] | None = None
    error: str = ""
    updated_at: float = 0.0


_JOB_LOCK = threading.RLock()
_JOBS: dict[str, _VideoJob] = {}
_GLOBAL_REQUEST_TIMES: deque[float] = deque()


def _prune_jobs(now: float) -> None:
    stale = [key for key, item in _JOBS.items() if now - item.updated_at > _JOB_TTL_SECONDS]
    for key in stale:
        _JOBS.pop(key, None)
    if len(_JOBS) > _JOB_MAX:
        finished = sorted(
            (item for item in _JOBS.values() if item.status in {"completed", "failed"}),
            key=lambda item: item.updated_at,
        )
        while len(_JOBS) > _JOB_MAX and finished:
            _JOBS.pop(finished.pop(0).job_id, None)


def start_creative_video_job(
    prompt: Any,
    *,
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    environ: Any = None,
) -> dict[str, Any]:
    """Start a bounded async job; the paid request is never run without route consent."""
    env = os.environ if environ is None else environ
    if not str(env.get("GEMINI_API_KEY", "")).strip():
        raise CreativeVideoError("Direct AI video needs GEMINI_API_KEY configured as a server-side secret.")
    text = _prompt_text(prompt)
    model = _model_id(env)
    if aspect_ratio not in {"16:9", "9:16"}:
        raise CreativeVideoError("Aspect ratio must be 16:9 or 9:16.")
    if resolution not in {"360p", "720p"}:
        raise CreativeVideoError("This mobile workflow supports 360p or 720p output.")
    now = time.time()
    with _JOB_LOCK:
        _prune_jobs(now)
        active = sum(1 for item in _JOBS.values() if item.status in {"queued", "processing"})
        if active >= _JOB_MAX_ACTIVE:
            raise CreativeVideoError("Omnitrix is already generating two videos. Wait for one to finish before starting another.")
        # Bound accepted generations over a rolling day, not for the life of
        # this process. A never-pruned deque would eventually disable generation
        # permanently after enough successful or failed requests.
        while _GLOBAL_REQUEST_TIMES and now - _GLOBAL_REQUEST_TIMES[0] >= 86_400.0:
            _GLOBAL_REQUEST_TIMES.popleft()
        if len(_GLOBAL_REQUEST_TIMES) >= 100:
            raise CreativeVideoError("The local video request guard reached its rolling 24-hour limit. Try again tomorrow.")
        _GLOBAL_REQUEST_TIMES.append(now)
        job_id = uuid.uuid4().hex
        job = _VideoJob(job_id, "queued", now, text, aspect_ratio, resolution, model, updated_at=now)
        _JOBS[job_id] = job

    def worker() -> None:
        with _JOB_LOCK:
            current = _JOBS.get(job_id)
            if current is None:
                return
            current.status = "processing"
            current.updated_at = time.time()
        try:
            result = generate_creative_video(
                text, aspect_ratio=aspect_ratio, resolution=resolution, environ=env
            )
            with _JOB_LOCK:
                current = _JOBS.get(job_id)
                if current is not None:
                    current.status = "completed"
                    current.result = result
                    current.updated_at = time.time()
        except Exception as exc:
            message = str(exc) if isinstance(exc, CreativeVideoError) else "Unexpected error during video generation. No video file was returned."
            with _JOB_LOCK:
                current = _JOBS.get(job_id)
                if current is not None:
                    current.status = "failed"
                    current.error = message[:500]
                    current.updated_at = time.time()

    threading.Thread(target=worker, name="omnitrix-video-" + job_id[:8], daemon=True).start()
    return {
        "ok": True,
        "job_id": job_id,
        "status": "queued",
        "provider": "google",
        "model": model,
        "estimated_cost_usd": round(VIDEO_SECONDS_ESTIMATE * VIDEO_COST_USD_PER_SECOND_720P, 2),
        "estimated_video_seconds": VIDEO_SECONDS_ESTIMATE,
        "resolution": resolution,
        "message": "Paid AI video generation queued. Estimated 720p cost is about US$0.10 per generated second; the model may choose a different final duration.",
    }


def creative_video_job_status(job_id: str, *, consume_result: bool = False) -> dict[str, Any]:
    if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
        return {"ok": False, "error": "Video job was not found."}
    with _JOB_LOCK:
        _prune_jobs(time.time())
        job = _JOBS.get(job_id)
        if job is None:
            return {"ok": False, "error": "Video job was not found or has expired."}
        payload: dict[str, Any] = {
            "ok": True,
            "job_id": job.job_id,
            "status": job.status,
            "provider": "google",
            "model": job.model,
        }
        if job.status == "failed":
            payload["error"] = job.error
        elif job.status == "completed" and job.result:
            payload.update({
                "file_name": job.result["file_name"],
                "mime_type": job.result["mime_type"],
                "size_bytes": job.result["size_bytes"],
                "aspect_ratio": job.result["aspect_ratio"],
                "resolution": job.result["resolution"],
                "note": job.result["note"],
            })
            if consume_result:
                payload["video_base64"] = job.result["video_base64"]
                _JOBS.pop(job_id, None)
        return payload
