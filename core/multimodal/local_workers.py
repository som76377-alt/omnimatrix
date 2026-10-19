"""Callable local-only workers for OCR, document parsing, ASR and scene detection."""
from __future__ import annotations

import json
from typing import Any

from core.multimodal.adapters import toolchain_status
from core.multimodal.local_tools import detect_scenes, extract_document, run_ocr, transcribe_audio
from core.multimodal.router import (
    EvidenceItem, FailureKind, TaskResult, WorkerCapability, WorkerRegistry, WorkerSpec,
)


def _path_from_task(task: Any) -> str:
    payload = task.payload if isinstance(task.payload, dict) else {}
    path = payload.get("path")
    records = payload.get("records")
    if not path and isinstance(records, list) and len(records) == 1 and isinstance(records[0], dict):
        path = records[0].get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("This local worker requires payload.path pointing to a staged local file.")
    return path


def _worker(worker_id: str, model_id: str, capability: WorkerCapability, operation: Any):
    def run(task: Any, handoff: Any) -> TaskResult:
        try:
            path = _path_from_task(task)
            output = operation(path)
            rendered = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
            evidence = EvidenceItem(
                source_name=task.source_name,
                source_type=task.source_type,
                content=rendered[:200_000],
                worker_id=worker_id,
                model_id=model_id,
                metadata={"origin": "local_tool", "untrusted_content": True},
            )
            return TaskResult(True, worker_id, model_id, evidence=(evidence,),
                              completed_steps=(worker_id + ".complete",))
        except ValueError:
            return TaskResult(False, worker_id, model_id,
                              failure_kind=FailureKind.INVALID_INPUT,
                              safe_message="The local tool received an invalid input.")
        except RuntimeError as exc:
            message = str(exc)
            missing = "not installed" in message or "not available" in message
            return TaskResult(False, worker_id, model_id,
                failure_kind=FailureKind.DEPENDENCY_MISSING if missing else FailureKind.PERMANENT,
                safe_message=message[:180])
        except Exception:
            return TaskResult(False, worker_id, model_id,
                              failure_kind=FailureKind.UNKNOWN,
                              safe_message="The local media worker failed.")
    return run


def register_local_workers(registry: WorkerRegistry) -> WorkerRegistry:
    """Register local tools only when their Python dependencies are present."""
    status = toolchain_status()
    definitions = [
        ("paddleocr.local", "paddleocr", WorkerCapability.OCR, run_ocr),
        ("docling.local", "docling", WorkerCapability.PDF_EXTRACTION, extract_document),
        ("faster_whisper.local", "faster_whisper", WorkerCapability.AUDIO_TRANSCRIPTION, transcribe_audio),
        ("pyscenedetect.local", "pyscenedetect", WorkerCapability.VIDEO_SCENE_DETECTION, detect_scenes),
    ]
    for worker_id, key, capability, operation in definitions:
        available = bool(status.get(key, {}).get("dependency_installed"))
        registry.register(
            WorkerSpec(
                worker_id=worker_id,
                capabilities=frozenset({capability}),
                model_id="local:" + key,
                enabled=available,
                priority=15,
                privacy_tier="local",
                description="Local processing; extracted content is untrusted evidence.",
            ),
            _worker(worker_id, "local:" + key, capability, operation),
        )
    return registry
