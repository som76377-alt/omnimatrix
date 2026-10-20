"""Optional, bounded local media utilities. Imports heavyweight dependencies lazily."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

MAX_LOCAL_INPUT_BYTES = max(1024, int(os.environ.get("OMNITRIX_LOCAL_TOOL_MAX_BYTES", str(512 * 1024 * 1024))))
MAX_TEXT_CHARS = 200_000
MAX_PROCESS_STDOUT_BYTES = 2 * 1024 * 1024
MAX_PROCESS_STDERR_BYTES = 64 * 1024


def _run_bounded_process(
    command: list[str], *, timeout_seconds: int, stdout_limit: int = MAX_PROCESS_STDOUT_BYTES,
    stderr_limit: int = MAX_PROCESS_STDERR_BYTES,
) -> subprocess.CompletedProcess[str]:
    """Run a fixed no-shell command with bounded in-memory output capture."""
    with tempfile.TemporaryFile(mode="w+b") as stdout_file, tempfile.TemporaryFile(mode="w+b") as stderr_file:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=stdout_file, stderr=stderr_file,
            timeout=timeout_seconds, check=False, shell=False,
        )
        stdout_file.seek(0)
        stdout = stdout_file.read(stdout_limit + 1)
        if len(stdout) > stdout_limit:
            raise RuntimeError("Local media tool output exceeded the configured safety limit.")
        stderr_file.seek(0)
        stderr = stderr_file.read(stderr_limit + 1)
        truncated = len(stderr) > stderr_limit
        stderr_text = stderr[:stderr_limit].decode("utf-8", errors="replace")
        if truncated:
            stderr_text += "\n[tool stderr truncated]"
        return subprocess.CompletedProcess(
            result.args, result.returncode,
            stdout.decode("utf-8", errors="replace"), stderr_text,
        )


def _input_path(value: Any) -> Path:
    """Accept only an existing regular file; never accept URLs or shell fragments."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("A local file path is required.")
    original = Path(value).expanduser()
    if original.is_symlink():
        raise ValueError("Symbolic-link inputs are not accepted.")
    path = original.resolve(strict=True)
    if not path.is_file() or path.is_symlink():
        raise ValueError("Input must be an existing regular local file.")
    if path.stat().st_size <= 0 or path.stat().st_size > MAX_LOCAL_INPUT_BYTES:
        raise ValueError("Input file is empty or exceeds the local processing size limit.")
    return path


def probe_media(path: str, *, timeout_seconds: int = 15) -> dict[str, Any]:
    """Return bounded FFprobe metadata without decoding media or invoking a shell."""
    binary = shutil.which("ffprobe")
    if not binary:
        raise RuntimeError("FFprobe is not installed.")
    if not 1 <= timeout_seconds <= 60:
        raise ValueError("Probe timeout must be between 1 and 60 seconds.")
    source = _input_path(path)
    result = _run_bounded_process(
        [binary, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)],
        timeout_seconds=timeout_seconds,
    )
    if result.returncode:
        raise RuntimeError("FFprobe could not read this media file.")
    try:
        data = json.loads(result.stdout[:2_000_000])
    except (json.JSONDecodeError, TypeError):
        raise RuntimeError("FFprobe returned invalid metadata.") from None
    fmt = data.get("format", {}) if isinstance(data, dict) else {}
    streams = data.get("streams", []) if isinstance(data, dict) else []
    return {
        "format_name": str(fmt.get("format_name", ""))[:200],
        "duration_seconds": _finite_nonnegative(fmt.get("duration")),
        "size_bytes": source.stat().st_size,
        "streams": [
            {
                "codec_type": str(item.get("codec_type", ""))[:40],
                "codec_name": str(item.get("codec_name", ""))[:80],
                "width": item.get("width") if isinstance(item.get("width"), int) else None,
                "height": item.get("height") if isinstance(item.get("height"), int) else None,
                "sample_rate": str(item.get("sample_rate", ""))[:20],
                "channels": item.get("channels") if isinstance(item.get("channels"), int) else None,
            }
            for item in streams[:32] if isinstance(item, dict)
        ],
    }


def _finite_nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 and number < 1e9 else None


def extract_document(path: str) -> dict[str, Any]:
    """Extract PDF/DOCX and similar supported formats through optional Docling."""
    source = _input_path(path)
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        raise RuntimeError("Docling is not installed; document extraction is unavailable.") from None
    try:
        result = DocumentConverter().convert(str(source))
        text = result.document.export_to_markdown()
    except Exception:
        raise RuntimeError("Docling could not extract this document.") from None
    return {"text": str(text)[:MAX_TEXT_CHARS], "truncated": len(str(text)) > MAX_TEXT_CHARS}


def run_ocr(path: str) -> dict[str, Any]:
    """Run PaddleOCR lazily and return text plus confidence where provided."""
    source = _input_path(path)
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        raise RuntimeError("PaddleOCR is not installed; OCR is unavailable.") from None
    try:
        engine = PaddleOCR(use_textline_orientation=True, lang="en")
        raw = engine.predict(str(source))
        lines: list[dict[str, Any]] = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            texts = item.get("rec_texts", [])
            scores = item.get("rec_scores", [])
            if isinstance(texts, list):
                for index, value in enumerate(texts):
                    if isinstance(value, str) and value.strip():
                        score = scores[index] if isinstance(scores, list) and index < len(scores) else None
                        try:
                            confidence = float(score)
                        except (TypeError, ValueError):
                            confidence = None
                        lines.append({"text": value[:2000], "confidence": confidence})
        return {"lines": lines[:2000], "text": "\n".join(row["text"] for row in lines)[:MAX_TEXT_CHARS]}
    except Exception:
        raise RuntimeError("PaddleOCR failed to process this file.") from None


def transcribe_audio(path: str, *, model_size: str = "small", language: str | None = None) -> dict[str, Any]:
    """Transcribe audio with faster-whisper; model downloads are explicit, never at import."""
    source = _input_path(path)
    allowed_sizes = {"tiny", "base", "small", "medium", "large-v3"}
    if model_size not in allowed_sizes:
        raise ValueError("Unsupported transcription model size.")
    if language is not None and (not isinstance(language, str) or len(language) > 16 or not language.replace("-", "").isalpha()):
        raise ValueError("Invalid language code.")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("faster-whisper is not installed; transcription is unavailable.") from None
    local_model_path = os.environ.get("OMNITRIX_WHISPER_MODEL_PATH", "").strip()
    allow_download = os.environ.get("OMNITRIX_ALLOW_MODEL_DOWNLOAD", "").strip() == "1"
    if local_model_path:
        model_source = Path(local_model_path).expanduser()
        if not model_source.is_dir():
            raise RuntimeError("Configured Whisper model path does not exist.")
        model_source = str(model_source)
    elif allow_download:
        model_source = model_size
    else:
        raise RuntimeError(
            "Whisper weights are not configured. Set OMNITRIX_WHISPER_MODEL_PATH to local weights "
            "or explicitly set OMNITRIX_ALLOW_MODEL_DOWNLOAD=1."
        )
    device = os.environ.get("OMNITRIX_WHISPER_DEVICE", "cpu")
    compute_type = os.environ.get("OMNITRIX_WHISPER_COMPUTE_TYPE", "int8")
    try:
        model = WhisperModel(model_source, device=device, compute_type=compute_type)
        segments, info = model.transcribe(str(source), language=language, vad_filter=True)
        output = []
        chars = 0
        for segment in segments:
            text = str(segment.text).strip()
            if not text:
                continue
            remaining = MAX_TEXT_CHARS - chars
            if remaining <= 0:
                break
            text = text[:remaining]
            output.append({"start": max(0.0, float(segment.start)), "end": max(0.0, float(segment.end)), "text": text})
            chars += len(text)
        return {"language": str(getattr(info, "language", "unknown"))[:20], "segments": output, "text": "\n".join(item["text"] for item in output)}
    except Exception:
        raise RuntimeError("Audio transcription failed. Check model availability, memory and media format.") from None


def detect_scenes(path: str, *, threshold: float = 27.0, max_scenes: int = 500) -> dict[str, Any]:
    """Detect scene boundaries with PySceneDetect; frame extraction is not performed."""
    source = _input_path(path)
    if not isinstance(threshold, (int, float)) or not 1 <= threshold <= 100:
        raise ValueError("Scene threshold must be between 1 and 100.")
    if not isinstance(max_scenes, int) or not 1 <= max_scenes <= 2000:
        raise ValueError("max_scenes must be between 1 and 2000.")
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector
    except ImportError:
        raise RuntimeError("PySceneDetect is not installed; scene detection is unavailable.") from None
    try:
        video = open_video(str(source))
        manager = SceneManager()
        manager.add_detector(ContentDetector(threshold=float(threshold)))
        manager.detect_scenes(video, show_progress=False)
        scenes = manager.get_scene_list()[:max_scenes]
        return {"scenes": [{"start_seconds": start.get_seconds(), "end_seconds": end.get_seconds()} for start, end in scenes], "count": len(scenes)}
    except Exception:
        raise RuntimeError("Scene detection failed for this video.") from None
