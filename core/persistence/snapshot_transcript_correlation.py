"""Fail-closed metadata correlation between an encrypted snapshot and transcript.

This validates the exact model-call slot and identity without decrypting content.
It deliberately does not claim that snapshot payload hashes match transcript
request/response hashes; that requires decrypting the pair with the external key.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.persistence.snapshot_recovery_gate import SnapshotRecoveryGateError


def validate_snapshot_transcript_correlation(
    *, snapshot_metadata: Mapping[str, Any], transcript: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Validate a snapshot's call ordinal against one complete transcript pair.

    interaction_sequence is the zero-based model-call ordinal. The append-only
    transcript stores two records per completed call: request at 2*n and response
    at 2*n+1. Any gap, ambiguous boundary, or identity mismatch blocks preflight.
    """
    sequence = snapshot_metadata.get("interaction_sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise SnapshotRecoveryGateError("Snapshot interaction sequence is invalid.")

    request_index = sequence * 2
    response_index = request_index + 1
    if response_index >= len(transcript):
        raise SnapshotRecoveryGateError(
            "Snapshot has no complete matching request/response transcript pair."
        )

    request = transcript[request_index]
    response = transcript[response_index]
    if not isinstance(request, Mapping) or not isinstance(response, Mapping):
        raise SnapshotRecoveryGateError("Matching transcript pair is malformed.")

    expected_request_fields = {
        "interaction_type": "model_request",
        "sequence": request_index,
        "run_id": snapshot_metadata.get("run_id"),
        "task_id": snapshot_metadata.get("task_id"),
        "attempt_id": snapshot_metadata.get("attempt_id"),
        "provider": snapshot_metadata.get("provider"),
        "model": snapshot_metadata.get("model"),
    }
    expected_response_fields = {
        "interaction_type": "model_response",
        "sequence": response_index,
        "run_id": snapshot_metadata.get("run_id"),
        "task_id": snapshot_metadata.get("task_id"),
        "attempt_id": snapshot_metadata.get("attempt_id"),
        "provider": snapshot_metadata.get("provider"),
        "model": snapshot_metadata.get("model"),
    }
    for record, expected, label in (
        (request, expected_request_fields, "request"),
        (response, expected_response_fields, "response"),
    ):
        for field, value in expected.items():
            if record.get(field) != value:
                raise SnapshotRecoveryGateError(
                    f"Snapshot does not match transcript {label} {field}."
                )

    request_digest = request.get("request_sha256")
    response_request_digest = response.get("request_sha256")
    response_digest = response.get("response_sha256")
    for label, digest in (
        ("request", request_digest),
        ("response request", response_request_digest),
        ("response", response_digest),
    ):
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest.lower())
        ):
            raise SnapshotRecoveryGateError(f"Transcript {label} digest is invalid.")
    if request_digest != response_request_digest:
        raise SnapshotRecoveryGateError(
            "Transcript response request digest does not match its request."
        )

    return {
        "interaction_sequence": sequence,
        "request_transcript_sequence": request_index,
        "response_transcript_sequence": response_index,
        "request_sha256": request_digest,
        "response_sha256": response_digest,
        "content_hashes_verified": False,
    }
