"""Capability-aware multimodal routing with context-preserving failover."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
import time
import uuid
from typing import Any, Callable, Iterable, Mapping, Protocol


class WorkerCapability(str, Enum):
    IMAGE_UNDERSTANDING = "image_understanding"
    OCR = "ocr"
    DOCUMENT_LAYOUT = "document_layout"
    PDF_EXTRACTION = "pdf_extraction"
    AUDIO_TRANSCRIPTION = "audio_transcription"
    AUDIO_UNDERSTANDING = "audio_understanding"
    VIDEO_SCENE_DETECTION = "video_scene_detection"
    VIDEO_UNDERSTANDING = "video_understanding"
    TEXT_REASONING = "text_reasoning"
    CRITIQUE = "critique"
    MEDIA_CONVERSION = "media_conversion"
    MEDIA_METADATA = "media_metadata"


class FailureKind(str, Enum):
    QUOTA = "quota"
    AUTH = "auth"
    TIMEOUT = "timeout"
    TRANSIENT = "transient"
    UNSUPPORTED = "unsupported"
    INVALID_INPUT = "invalid_input"
    DEPENDENCY_MISSING = "dependency_missing"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EvidenceItem:
    source_name: str
    source_type: str
    content: str
    worker_id: str
    model_id: str = "unknown"
    locator: str | None = None
    confidence: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_name.strip() or not self.source_type.strip():
            raise ValueError("Evidence requires source name and type.")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Evidence confidence must be between 0 and 1.")


@dataclass(frozen=True)
class TaskRequest:
    user_request: str
    required_capabilities: tuple[WorkerCapability, ...]
    source_name: str = "user_input"
    source_type: str = "text"
    payload: Mapping[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    max_handoffs: int = 3

    def __post_init__(self) -> None:
        if not self.user_request.strip():
            raise ValueError("Task request cannot be empty.")
        if not 0 <= self.max_handoffs <= 8:
            raise ValueError("max_handoffs must be between 0 and 8.")


@dataclass(frozen=True)
class HandoffPacket:
    task_id: str
    user_request: str
    source_name: str
    source_type: str
    payload: Mapping[str, Any]
    evidence: tuple[EvidenceItem, ...] = ()
    completed_steps: tuple[str, ...] = ()
    remaining_capabilities: tuple[WorkerCapability, ...] = ()
    attempted_workers: tuple[str, ...] = ()
    handoff_reason: str | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "task_id": self.task_id,
            "user_request": self.user_request, "source_name": self.source_name,
            "source_type": self.source_type, "payload": dict(self.payload),
            "evidence": [asdict(item) for item in self.evidence],
            "completed_steps": list(self.completed_steps),
            "remaining_capabilities": [item.value for item in self.remaining_capabilities],
            "attempted_workers": list(self.attempted_workers),
            "handoff_reason": self.handoff_reason,
        }

    def fingerprint(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class TaskResult:
    success: bool
    worker_id: str
    model_id: str
    evidence: tuple[EvidenceItem, ...] = ()
    completed_steps: tuple[str, ...] = ()
    failure_kind: FailureKind | None = None
    safe_message: str | None = None
    retryable: bool = False


@dataclass(frozen=True)
class WorkerSpec:
    worker_id: str
    capabilities: frozenset[WorkerCapability]
    model_id: str
    enabled: bool = True
    priority: int = 100
    requires_api_key: str | None = None
    requires_executable: str | None = None
    privacy_tier: str = "external"
    description: str = ""


class Worker(Protocol):
    def __call__(self, task: TaskRequest, handoff: HandoffPacket) -> TaskResult: ...


class WorkerRegistry:
    """Deterministic registry; capabilities must be explicitly declared."""
    def __init__(self) -> None:
        self._entries: dict[str, tuple[WorkerSpec, Worker]] = {}

    def register(self, spec: WorkerSpec, worker: Worker) -> None:
        if not spec.worker_id.strip():
            raise ValueError("Worker id cannot be empty.")
        if spec.worker_id in self._entries:
            raise ValueError(f"Worker already registered: {spec.worker_id}")
        self._entries[spec.worker_id] = (spec, worker)

    def candidates(self, capabilities: Iterable[WorkerCapability], *,
                   excluded: Iterable[str] = (), available_keys: Iterable[str] = (),
                   available_executables: Iterable[str] = (),
                   privacy_tier: str | None = None) -> list[tuple[WorkerSpec, Worker]]:
        needed, excluded_set = frozenset(capabilities), set(excluded)
        keys, executables = set(available_keys), set(available_executables)
        found = []
        for spec, worker in self._entries.values():
            if not spec.enabled or spec.worker_id in excluded_set:
                continue
            if not needed.issubset(spec.capabilities):
                continue
            if spec.requires_api_key and spec.requires_api_key not in keys:
                continue
            if spec.requires_executable and spec.requires_executable not in executables:
                continue
            if privacy_tier == "local" and spec.privacy_tier != "local":
                continue
            found.append((spec, worker))
        return sorted(found, key=lambda item: (item[0].priority, item[0].worker_id))

    def describe(self) -> list[dict[str, Any]]:
        """Safe diagnostics expose env-variable names, never secret values."""
        return [{"worker_id": s.worker_id, "model_id": s.model_id,
                 "capabilities": sorted(c.value for c in s.capabilities),
                 "enabled": s.enabled, "priority": s.priority,
                 "requires_api_key": s.requires_api_key,
                 "requires_executable": s.requires_executable,
                 "privacy_tier": s.privacy_tier, "description": s.description}
                for s, _ in sorted(self._entries.values(), key=lambda item: item[0].worker_id)]


def classify_provider_failure(exc: BaseException) -> FailureKind:
    """Classify common provider failures without exposing raw provider messages.

    Adapters should prefer typed exceptions/status codes. Text matching is a
    conservative compatibility fallback for adapters that expose only messages.
    """
    name = type(exc).__name__.lower()
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status == 429 or any(token in name for token in ("ratelimit", "quota")):
        return FailureKind.QUOTA
    if status in (401, 403) or "authentication" in name or "unauthorized" in name:
        return FailureKind.AUTH
    if isinstance(exc, (TimeoutError,)) or "timeout" in name:
        return FailureKind.TIMEOUT
    if status in (400, 413, 415, 422):
        return FailureKind.INVALID_INPUT if status in (400, 413, 422) else FailureKind.UNSUPPORTED
    if status in (502, 503, 504) or any(token in name for token in ("urlerror", "connectionerror")):
        return FailureKind.TRANSIENT
    # Do not echo exc text: it may contain response bodies or private data.
    message = str(exc).lower()[:300]
    if any(token in message for token in ("quota exceeded", "rate limit", "resource_exhausted")):
        return FailureKind.QUOTA
    if any(token in message for token in ("invalid api key", "unauthorized", "permission denied")):
        return FailureKind.AUTH
    if "unsupported" in message or "not supported" in message:
        return FailureKind.UNSUPPORTED
    return FailureKind.UNKNOWN


def route_with_failover(task: TaskRequest, registry: WorkerRegistry, *,
                        available_keys: Iterable[str] = (),
                        available_executables: Iterable[str] = (),
                        prior_evidence: Iterable[EvidenceItem] = (),
                        completed_steps: Iterable[str] = (),
                        privacy_tier: str | None = None,
                        clock: Callable[[], float] = time.monotonic
                        ) -> tuple[TaskResult, HandoffPacket]:
    """Attempt compatible workers once each; retain evidence and progress at handoff."""
    evidence, steps, attempted = list(prior_evidence), list(completed_steps), []
    packet = HandoffPacket(task.task_id, task.user_request, task.source_name,
                           task.source_type, dict(task.payload), tuple(evidence),
                           tuple(steps), task.required_capabilities)
    handoffs, last_result = 0, None
    while handoffs <= task.max_handoffs:
        choices = registry.candidates(packet.remaining_capabilities, excluded=attempted,
            available_keys=available_keys, available_executables=available_executables,
            privacy_tier=privacy_tier)
        if not choices:
            break
        spec, worker = choices[0]
        attempted.append(spec.worker_id)
        started = clock()
        try:
            result = worker(task, packet)
            if not isinstance(result, TaskResult):
                raise TypeError("Worker returned an invalid result contract.")
        except TimeoutError:
            result = TaskResult(False, spec.worker_id, spec.model_id,
                failure_kind=FailureKind.TIMEOUT, safe_message="Worker timed out.", retryable=True)
        except Exception:
            result = TaskResult(False, spec.worker_id, spec.model_id,
                failure_kind=FailureKind.UNKNOWN, safe_message="Worker failed unexpectedly.")
        _elapsed = max(0.0, clock() - started)
        last_result = result
        evidence.extend(result.evidence)
        steps.extend(step for step in result.completed_steps if step not in steps)
        if result.success:
            final = TaskResult(True, spec.worker_id, result.model_id, tuple(evidence), tuple(steps))
            return final, HandoffPacket(task.task_id, task.user_request, task.source_name,
                task.source_type, dict(task.payload), tuple(evidence), tuple(steps), (),
                tuple(attempted))
        packet = HandoffPacket(task.task_id, task.user_request, task.source_name,
            task.source_type, dict(task.payload), tuple(evidence), tuple(steps),
            task.required_capabilities, tuple(attempted),
            (result.failure_kind or FailureKind.UNKNOWN).value)
        if result.failure_kind in {FailureKind.INVALID_INPUT, FailureKind.PERMANENT}:
            break
        if handoffs >= task.max_handoffs:
            break
        handoffs += 1
    if last_result is None:
        last_result = TaskResult(False, "coordinator", "none",
            failure_kind=FailureKind.DEPENDENCY_MISSING,
            safe_message="No enabled worker has the required capabilities and credentials.")
    final = TaskResult(False, last_result.worker_id, last_result.model_id,
        tuple(evidence), tuple(steps), last_result.failure_kind or FailureKind.UNKNOWN,
        last_result.safe_message or "No compatible worker completed the task.",
        last_result.retryable)
    return final, HandoffPacket(task.task_id, task.user_request, task.source_name,
        task.source_type, dict(task.payload), tuple(evidence), tuple(steps),
        task.required_capabilities, tuple(attempted),
        (final.failure_kind or FailureKind.UNKNOWN).value)
