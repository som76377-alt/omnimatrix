"""Lazy probes for optional multimodal providers and local tools."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any
from core.multimodal.router import WorkerCapability, WorkerSpec

OPTIONAL_TOOLCHAIN: dict[str, dict[str, Any]] = {
    "gemini": {"kind":"provider","env":"GEMINI_API_KEY","capabilities":["image_understanding","audio_understanding","video_understanding","pdf_extraction","audio_transcription"]},
    "openrouter": {"kind":"provider","env":"OPENROUTER_API_KEY","capabilities":["text_reasoning","critique"]},
    "qwen3_omni": {"kind":"local_model","module":"transformers","capabilities":["image_understanding","audio_understanding","video_understanding"]},
    "qwen3_vl": {"kind":"local_model","module":"transformers","capabilities":["image_understanding"]},
    "paddleocr": {"kind":"python_tool","module":"paddleocr","enable_env":"OMNITRIX_ENABLE_PADDLEOCR","capabilities":["ocr"]},
    "docling": {"kind":"python_tool","module":"docling","enable_env":"OMNITRIX_ENABLE_DOCLING","capabilities":["document_layout","pdf_extraction"]},
    "qwen3_asr": {"kind":"local_model","module":"transformers","capabilities":["audio_transcription"]},
    "faster_whisper": {"kind":"python_tool","module":"faster_whisper","enable_env":"OMNITRIX_ENABLE_FASTER_WHISPER","model_env":"OMNITRIX_WHISPER_MODEL_PATH","download_env":"OMNITRIX_ALLOW_MODEL_DOWNLOAD","capabilities":["audio_transcription"]},
    "ffmpeg": {"kind":"system_tool","executable":"ffmpeg","capabilities":["media_conversion"]},
    "ffprobe": {"kind":"system_tool","executable":"ffprobe","capabilities":["media_metadata"]},
    "pyscenedetect": {"kind":"python_tool","module":"scenedetect","capabilities":["video_scene_detection"]},
}

_MAPPING = {
    "gemini": ("gemini.multimodal","GEMINI_API_KEY",None,"external",10),
    "openrouter": ("openrouter.text","OPENROUTER_API_KEY",None,"external",20),
    "qwen3_omni": ("qwen3_omni.local",None,None,"local",50),
    "qwen3_vl": ("qwen3_vl.local",None,None,"local",60),
    "paddleocr": ("paddleocr.local",None,None,"local",30),
    "docling": ("docling.local",None,None,"local",35),
    "qwen3_asr": ("qwen3_asr.local",None,None,"local",40),
    "faster_whisper": ("faster_whisper.local",None,None,"local",45),
    "ffmpeg": ("ffmpeg.system",None,"ffmpeg","local",5),
    "ffprobe": ("ffprobe.system",None,"ffprobe","local",5),
    "pyscenedetect": ("pyscenedetect.local",None,None,"local",15),
}

def toolchain_status() -> dict[str, dict[str, Any]]:
    """Safe inventory: configuration/dependency presence is not a live health check."""
    status: dict[str, dict[str, Any]] = {}
    implemented = {"gemini", "openrouter", "ffmpeg", "paddleocr", "docling", "faster_whisper", "pyscenedetect", "ffprobe"}
    for name, spec in OPTIONAL_TOOLCHAIN.items():
        configured = False
        explicitly_enabled = not bool(spec.get("enable_env"))
        model_ready = True
        dependency_installed = False
        if spec["kind"] == "provider":
            configured = bool(os.environ.get(spec["env"], "").strip())
        elif spec["kind"] == "system_tool":
            dependency_installed = shutil.which(spec["executable"]) is not None
        else:
            try:
                dependency_installed = importlib.util.find_spec(spec["module"]) is not None
            except (ImportError, ValueError, ModuleNotFoundError):
                dependency_installed = False
        if spec.get("enable_env"):
            explicitly_enabled = os.environ.get(spec["enable_env"], "").strip() == "1"
        if spec.get("model_env"):
            model_path = os.environ.get(spec["model_env"], "").strip()
            local_model_ready = bool(model_path and Path(model_path).expanduser().is_dir())
            download_allowed = os.environ.get(spec.get("download_env", ""), "").strip() == "1"
            model_ready = local_model_ready or download_allowed
            configured = local_model_ready
        # This is adapter readiness, not provider health or model correctness.
        adapter_ready = name in implemented and (
            configured if spec["kind"] == "provider" else
            dependency_installed if spec["kind"] == "system_tool" else
            (dependency_installed and explicitly_enabled and model_ready)
            if spec["kind"] == "python_tool" else False
        )
        status[name] = {
            "kind": spec["kind"],
            "configured": configured,
            "explicit_opt_in": explicitly_enabled,
            "model_ready": model_ready,
            "dependency_installed": dependency_installed,
            "adapter_implemented": name in implemented,
            "available": adapter_ready,
            "runtime_health_checked": False,
            "capabilities": list(spec["capabilities"]),
        }
    return status

def discover_worker_specs() -> list[WorkerSpec]:
    """Describe available integrations without downloading model weights."""
    status = toolchain_status()
    workers = []
    for name, tool in OPTIONAL_TOOLCHAIN.items():
        worker_id, key, executable, privacy, priority = _MAPPING[name]
        workers.append(WorkerSpec(worker_id, frozenset(WorkerCapability(c) for c in tool["capabilities"]),
            name, enabled=bool(status[name]["available"]), priority=priority,
            requires_api_key=key, requires_executable=executable, privacy_tier=privacy,
            description=f"Optional {tool['kind']} adapter; see docs/MULTIMODAL_WORKERS.md."))
    return workers

def run_ffmpeg(arguments: list[str], *, timeout_seconds: int = 60) -> subprocess.CompletedProcess[str]:
    """Run FFmpeg without a shell, with validated arguments and a strict timeout."""
    binary = shutil.which("ffmpeg")
    if not binary:
        raise RuntimeError("FFmpeg is not installed; media conversion is unavailable.")
    if not 1 <= timeout_seconds <= 600:
        raise ValueError("FFmpeg timeout must be between 1 and 600 seconds.")
    if not arguments or any(not isinstance(arg, str) or "\x00" in arg for arg in arguments):
        raise ValueError("Invalid FFmpeg arguments.")
    command = [binary, "-nostdin", "-hide_banner", "-loglevel", "error", *arguments]
    # FFmpeg output is normally written to a caller-supplied file. Discard stdout
    # to avoid an unbounded in-memory buffer if a caller chooses stdout as output.
    with tempfile.TemporaryFile(mode="w+b") as stderr_file:
        completed = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr_file,
            timeout=timeout_seconds, check=False, shell=False,
        )
        stderr_file.seek(0)
        raw_stderr = stderr_file.read(64 * 1024 + 1)
        stderr_text = raw_stderr[:64 * 1024].decode("utf-8", errors="replace")
        if len(raw_stderr) > 64 * 1024:
            stderr_text += "\n[FFmpeg stderr truncated]"
        return subprocess.CompletedProcess(completed.args, completed.returncode, "", stderr_text)
