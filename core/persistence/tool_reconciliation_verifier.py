"""Fail-closed contract for tool-specific reconciliation verification.

This module validates verifier output, but does not provide a concrete provider
verifier. A registered verifier must independently consult authoritative evidence
and must never execute, retry, or mutate the external action being checked.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Protocol


_OUTCOMES = frozenset({"applied", "not_applied", "unknown"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExecutionIdentity:
    """Minimum durable identity that a verifier result must bind to exactly."""

    execution_id: str
    idempotency_key: str
    tool_name: str
    request_sha256: str
    run_id: str
    task_id: str
    attempt_id: str
    logical_action_id: str


@dataclass(frozen=True)
class VerificationResult:
    """Narrow verifier claim; never an execution or retry authorization."""

    execution_id: str
    idempotency_key: str
    tool_name: str
    request_sha256: str
    verifier_id: str
    outcome: str
    observed_at: str
    evidence_reference: str
    evidence_sha256: str


class ToolReconciliationVerifier(Protocol):
    """Independent, read-only verifier for one exact tool integration."""

    tool_name: str
    verifier_id: str

    def verify(
        self,
        execution: ExecutionIdentity,
        evidence: Mapping[str, Any],
    ) -> VerificationResult:
        """Check authoritative external evidence without performing the action."""
        ...


class ToolReconciliationVerifierRegistry:
    """Explicit allow-list of verifiers keyed by exact tool name."""

    def __init__(self) -> None:
        self._verifiers: dict[str, ToolReconciliationVerifier] = {}

    def register(self, verifier: ToolReconciliationVerifier) -> None:
        tool_name = getattr(verifier, "tool_name", None)
        verifier_id = getattr(verifier, "verifier_id", None)
        verify = getattr(verifier, "verify", None)
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("Verifier tool_name must be non-empty text.")
        if not isinstance(verifier_id, str) or not verifier_id.strip():
            raise ValueError("Verifier verifier_id must be non-empty text.")
        if not callable(verify):
            raise ValueError("Verifier must provide a callable verify method.")
        if tool_name in self._verifiers:
            raise ValueError(f"Verifier already registered for tool: {tool_name}")
        self._verifiers[tool_name] = verifier

    def get(self, tool_name: str) -> ToolReconciliationVerifier | None:
        return self._verifiers.get(tool_name)


@dataclass(frozen=True)
class ReconciliationVerification:
    """Fail-closed outcome suitable for diagnostics, not for resuming execution."""

    outcome: str
    verified: bool
    verifier_id: str | None
    reason: str


def _execution_identity(record: Mapping[str, Any]) -> ExecutionIdentity | None:
    values = {
        key: record.get(key)
        for key in (
            "execution_id", "idempotency_key", "tool_name", "request_sha256",
            "run_id", "task_id", "attempt_id", "logical_action_id",
        )
    }
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        return None
    if not _SHA256_RE.fullmatch(values["request_sha256"]):
        return None
    return ExecutionIdentity(**values)


def verify_tool_reconciliation(
    execution_record: Mapping[str, Any],
    evidence: Mapping[str, Any],
    registry: ToolReconciliationVerifierRegistry,
) -> ReconciliationVerification:
    """Verify a claim against a registered tool-specific verifier, failing closed.

    This is deliberately not wired to retry, replay, journal mutation, or resume.
    Operator-provided evidence is input to the verifier, never proof by itself.
    """
    if not isinstance(execution_record, Mapping) or not isinstance(evidence, Mapping):
        return ReconciliationVerification("unknown", False, None, "invalid_input")
    if not isinstance(registry, ToolReconciliationVerifierRegistry):
        return ReconciliationVerification("unknown", False, None, "invalid_registry")

    status = execution_record.get("status")
    if status not in {"running", "unknown"}:
        return ReconciliationVerification("unknown", False, None, "execution_not_uncertain")

    identity = _execution_identity(execution_record)
    if identity is None:
        return ReconciliationVerification("unknown", False, None, "execution_identity_invalid")

    verifier = registry.get(identity.tool_name)
    if verifier is None:
        return ReconciliationVerification("unknown", False, None, "verifier_unavailable")

    try:
        result = verifier.verify(identity, evidence)
    except Exception:
        # Do not leak provider response bodies, credentials, or arbitrary exception text.
        return ReconciliationVerification(
            "unknown", False, getattr(verifier, "verifier_id", None), "verifier_error"
        )

    if not isinstance(result, VerificationResult):
        return ReconciliationVerification(
            "unknown", False, verifier.verifier_id, "malformed_verifier_result"
        )
    if (
        result.execution_id != identity.execution_id
        or result.idempotency_key != identity.idempotency_key
        or result.tool_name != identity.tool_name
        or result.request_sha256 != identity.request_sha256
        or result.verifier_id != verifier.verifier_id
    ):
        return ReconciliationVerification(
            "unknown", False, verifier.verifier_id, "verification_identity_mismatch"
        )
    if result.outcome not in _OUTCOMES:
        return ReconciliationVerification(
            "unknown", False, verifier.verifier_id, "verification_outcome_invalid"
        )
    if (
        not isinstance(result.observed_at, str) or not result.observed_at.strip()
        or not isinstance(result.evidence_reference, str) or not result.evidence_reference.strip()
        or not isinstance(result.evidence_sha256, str)
        or not _SHA256_RE.fullmatch(result.evidence_sha256)
    ):
        return ReconciliationVerification(
            "unknown", False, verifier.verifier_id, "verification_evidence_invalid"
        )
    if result.outcome == "unknown":
        return ReconciliationVerification("unknown", False, verifier.verifier_id, "outcome_unknown")
    return ReconciliationVerification(result.outcome, True, verifier.verifier_id, "verified")
