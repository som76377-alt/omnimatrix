"""Versioned orchestration contracts and deterministic budget guard.

These contracts are provider-neutral. They describe work and evidence; they do
not themselves grant tool permissions or prove that a user approved an action.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
from typing import Any, Mapping


CONTRACT_VERSION = 1


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "validation_error"
    PERMISSION_DENIED = "permission_denied"
    BUDGET_EXCEEDED = "budget_exceeded"
    PROVIDER_ERROR = "provider_error"
    TOOL_ERROR = "tool_error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    UNKNOWN_OUTCOME = "unknown_outcome"
    INTERNAL_ERROR = "internal_error"


class OmnitrixError(RuntimeError):
    """Normalized error with a stable machine-readable category."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        safe_to_retry: bool = False,
    ) -> None:
        if not isinstance(code, ErrorCode):
            raise TypeError("code must be an ErrorCode.")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string.")
        if not isinstance(retryable, bool) or not isinstance(safe_to_retry, bool):
            raise TypeError("retry flags must be booleans.")
        if safe_to_retry and not retryable:
            raise ValueError("safe_to_retry requires retryable=True.")
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.safe_to_retry = safe_to_retry


class TrustLabel(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


class WorkerStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value


def _require_text_tuple(values: object, name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{name} must be an iterable of non-empty strings.")
    try:
        result = tuple(values)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ValueError(
            f"{name} must be an iterable of non-empty strings."
        ) from exc
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError(f"{name} must contain only non-empty strings.")
    return result


@dataclass(frozen=True)
class ContextItem:
    """Context passed to a worker with an explicit trust label."""

    content: str
    trust: TrustLabel
    source_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("Context content must be a string.")
        if not isinstance(self.trust, TrustLabel):
            raise TypeError("Context trust must be a TrustLabel.")
        if self.source_ref is not None:
            _require_text(self.source_ref, "source_ref")


@dataclass(frozen=True)
class WorkerRequest:
    """Bounded, versioned request to a replaceable worker implementation."""

    run_id: str
    task_id: str
    attempt_id: str
    correlation_id: str
    objective: str
    in_scope: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()
    context: tuple[ContextItem, ...] = ()
    output_schema: Mapping[str, Any] = field(default_factory=dict)
    success_criteria: tuple[str, ...] = ()
    allowed_capabilities: frozenset[str] = field(default_factory=frozenset)
    timeout_seconds: float = 60.0
    max_model_calls: int = 1
    max_output_chars: int = 20_000
    idempotency_key: str | None = None
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in ("run_id", "task_id", "attempt_id", "correlation_id", "objective"):
            _require_text(getattr(self, name), name)
        object.__setattr__(self, "in_scope", _require_text_tuple(self.in_scope, "in_scope"))
        object.__setattr__(self, "out_of_scope", _require_text_tuple(self.out_of_scope, "out_of_scope"))
        object.__setattr__(self, "success_criteria", _require_text_tuple(self.success_criteria, "success_criteria"))
        try:
            context = tuple(self.context)
        except TypeError as exc:
            raise ValueError("context must be iterable.") from exc
        if any(not isinstance(item, ContextItem) for item in context):
            raise TypeError("context entries must be ContextItem instances.")
        object.__setattr__(self, "context", context)
        if not isinstance(self.output_schema, Mapping):
            raise TypeError("output_schema must be a mapping.")
        if not isinstance(self.allowed_capabilities, (set, frozenset, tuple, list)):
            raise TypeError("allowed_capabilities must be an iterable of strings.")
        capabilities = frozenset(self.allowed_capabilities)
        if any(not isinstance(item, str) or not item.strip() for item in capabilities):
            raise ValueError("allowed_capabilities must contain non-empty strings.")
        object.__setattr__(self, "allowed_capabilities", capabilities)
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float)) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        for name in ("max_model_calls", "max_output_chars", "contract_version"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        if self.idempotency_key is not None:
            _require_text(self.idempotency_key, "idempotency_key")


@dataclass(frozen=True)
class WorkerResult:
    """Structured worker outcome; prose alone is not proof of completion."""

    status: WorkerStatus
    output: Any = None
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    usage: Mapping[str, int | float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    failure_code: ErrorCode | None = None
    retryable: bool = False
    safe_to_retry: bool = False
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.status, WorkerStatus):
            raise TypeError("status must be a WorkerStatus.")
        for name in ("evidence_refs", "artifact_refs", "warnings"):
            object.__setattr__(self, name, _require_text_tuple(getattr(self, name), name))
        if not isinstance(self.usage, Mapping):
            raise TypeError("usage must be a mapping.")
        for key, value in self.usage.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("usage keys must be non-empty strings.")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError("usage values must be non-negative numbers.")
        if self.failure_code is not None and not isinstance(self.failure_code, ErrorCode):
            raise TypeError("failure_code must be an ErrorCode or None.")
        if not isinstance(self.retryable, bool) or not isinstance(self.safe_to_retry, bool):
            raise TypeError("retry flags must be booleans.")
        if self.safe_to_retry and not self.retryable:
            raise ValueError("safe_to_retry requires retryable=True.")
        if self.status == WorkerStatus.SUCCEEDED and self.failure_code is not None:
            raise ValueError("A successful result cannot have a failure_code.")
        if self.status in {WorkerStatus.FAILED, WorkerStatus.UNKNOWN} and self.failure_code is None:
            raise ValueError("Failed or unknown results require a failure_code.")
        if isinstance(self.contract_version, bool) or not isinstance(self.contract_version, int) or self.contract_version <= 0:
            raise ValueError("contract_version must be a positive integer.")


@dataclass(frozen=True)
class RunEvent:
    """Versioned, serializable event envelope for future persistence and clients."""

    event_id: str
    run_id: str
    sequence: int
    event_type: str
    timestamp: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    task_id: str | None = None
    contract_version: int = CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in ("event_id", "run_id", "event_type", "timestamp"):
            _require_text(getattr(self, name), name)
        if self.task_id is not None:
            _require_text(self.task_id, "task_id")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer.")
        if isinstance(self.contract_version, bool) or not isinstance(self.contract_version, int) or self.contract_version <= 0:
            raise ValueError("contract_version must be a positive integer.")
        try:
            datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be an ISO-8601 datetime.") from exc
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping.")


@dataclass(frozen=True)
class BudgetLimits:
    """Hard per-run ceilings. A zero cost ceiling means no paid spend."""

    max_model_calls: int = 20
    max_tool_calls: int = 50
    max_estimated_cost_usd: float = 0.0
    spend_mode: str = "zero_cost_only"

    def __post_init__(self) -> None:
        for name in ("max_model_calls", "max_tool_calls"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")
        if isinstance(self.max_estimated_cost_usd, bool) or not isinstance(self.max_estimated_cost_usd, (int, float)) or self.max_estimated_cost_usd < 0:
            raise ValueError("max_estimated_cost_usd must be non-negative.")
        if self.spend_mode not in {"zero_cost_only", "user_provided_free_quota", "paid_allowed"}:
            raise ValueError("Unsupported spend_mode.")


class BudgetGuard:
    """Thread-safe counter and spend guard; reserve before performing a call."""

    _ZERO_COST_CLASSES = frozenset({"local", "demo", "zero_cost", "free"})

    def __init__(self, limits: BudgetLimits | None = None) -> None:
        self.limits = limits or BudgetLimits()
        self._model_calls = 0
        self._tool_calls = 0
        self._estimated_cost_usd = 0.0
        self._lock = threading.Lock()

    def reserve_model_call(
        self,
        *,
        cost_class: str,
        estimated_cost_usd: float | None = None,
    ) -> None:
        if not isinstance(cost_class, str) or not cost_class.strip():
            raise ValueError("cost_class must be a non-empty string.")
        if estimated_cost_usd is not None and (
            isinstance(estimated_cost_usd, bool)
            or not isinstance(estimated_cost_usd, (int, float))
            or estimated_cost_usd < 0
        ):
            raise ValueError("estimated_cost_usd must be non-negative or None.")
        with self._lock:
            if self._model_calls >= self.limits.max_model_calls:
                raise OmnitrixError(ErrorCode.BUDGET_EXCEEDED, "Model-call budget exhausted.")
            if self.limits.spend_mode == "zero_cost_only":
                if cost_class not in self._ZERO_COST_CLASSES:
                    raise OmnitrixError(
                        ErrorCode.BUDGET_EXCEEDED,
                        f"Cost class '{cost_class}' is not allowed in zero-cost mode.",
                    )
                if estimated_cost_usd not in (None, 0, 0.0):
                    raise OmnitrixError(
                        ErrorCode.BUDGET_EXCEEDED,
                        "Non-zero estimated cost is not allowed in zero-cost mode.",
                    )
            elif self.limits.spend_mode == "user_provided_free_quota":
                if cost_class not in self._ZERO_COST_CLASSES | {"user_provided_free_quota"}:
                    raise OmnitrixError(
                        ErrorCode.BUDGET_EXCEEDED,
                        f"Cost class '{cost_class}' is not allowed in free-quota mode.",
                    )
                if estimated_cost_usd not in (None, 0, 0.0):
                    raise OmnitrixError(
                        ErrorCode.BUDGET_EXCEEDED,
                        "Non-zero estimated cost is not allowed in free-quota mode.",
                    )
            elif estimated_cost_usd is None:
                raise OmnitrixError(
                    ErrorCode.BUDGET_EXCEEDED,
                    "Paid mode requires an estimated cost before the call.",
                )
            projected = self._estimated_cost_usd + float(estimated_cost_usd or 0.0)
            if projected > self.limits.max_estimated_cost_usd:
                raise OmnitrixError(ErrorCode.BUDGET_EXCEEDED, "Estimated cost budget exhausted.")
            self._model_calls += 1
            self._estimated_cost_usd = projected

    def reserve_tool_call(self) -> None:
        with self._lock:
            if self._tool_calls >= self.limits.max_tool_calls:
                raise OmnitrixError(ErrorCode.BUDGET_EXCEEDED, "Tool-call budget exhausted.")
            self._tool_calls += 1

    def snapshot(self) -> dict[str, int | float | str]:
        with self._lock:
            return {
                "model_calls": self._model_calls,
                "tool_calls": self._tool_calls,
                "estimated_cost_usd": self._estimated_cost_usd,
                "spend_mode": self.limits.spend_mode,
            }
