"""Fail-closed metadata correlation between an encrypted snapshot and transcript.

The snapshot interaction sequence is scoped to a run/task/attempt, whereas the
append-only transcript sequence is global to the run. This module maps between
those coordinate systems without decrypting model content.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.persistence.snapshot_recovery_gate import SnapshotRecoveryGateError


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def validate_snapshot_transcript_correlation(
    *, snapshot_metadata: Mapping[str, Any], transcript: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Validate the snapshot's attempt-local ordinal against one complete pair.

    Transcript records use global run-level sequence numbers. Snapshot
    interaction_sequence is the zero-based call ordinal for the exact run/task/
    attempt identity. Each complete model call must be adjacent request/response
    records. Any malformed, unmatched, or identity-inconsistent boundary blocks.
    """
    ordinal = snapshot_metadata.get("interaction_sequence")
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
        raise SnapshotRecoveryGateError("Snapshot interaction sequence is invalid.")

    if not isinstance(transcript, Sequence) or isinstance(transcript, (str, bytes)):
        raise SnapshotRecoveryGateError("Model transcript must be an ordered record sequence.")

    matching_pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    index = 0
    while index < len(transcript):
        if index + 1 >= len(transcript):
            raise SnapshotRecoveryGateError("Transcript ends with an unmatched model request.")
        request, response = transcript[index], transcript[index + 1]
        if not isinstance(request, Mapping) or not isinstance(response, Mapping):
            raise SnapshotRecoveryGateError("Transcript contains a malformed model record.")
        if request.get("interaction_type") != "model_request":
            raise SnapshotRecoveryGateError("Transcript request/response order is invalid.")
        if response.get("interaction_type") != "model_response":
            raise SnapshotRecoveryGateError("Transcript request has no adjacent response.")
        if request.get("sequence") != index or response.get("sequence") != index + 1:
            raise SnapshotRecoveryGateError("Transcript global sequence is not contiguous.")
        if (
            request.get("run_id") != snapshot_metadata.get("run_id")
            or response.get("run_id") != snapshot_metadata.get("run_id")
        ):
            raise SnapshotRecoveryGateError("Transcript run identity does not match snapshot.")
        for field in ("task_id", "attempt_id"):
            if request.get(field) != response.get(field):
                raise SnapshotRecoveryGateError(f"Transcript request/response {field} mismatch.")
        if request.get("request_sha256") != response.get("request_sha256"):
            raise SnapshotRecoveryGateError("Transcript response request digest does not match its request.")
        if not _valid_digest(request.get("request_sha256")):
            raise SnapshotRecoveryGateError("Transcript request digest is invalid.")
        if not _valid_digest(response.get("response_sha256")):
            raise SnapshotRecoveryGateError("Transcript response digest is invalid.")

        if (
            request.get("task_id") == snapshot_metadata.get("task_id")
            and request.get("attempt_id") == snapshot_metadata.get("attempt_id")
        ):
            matching_pairs.append((request, response))
        index += 2

    if ordinal >= len(matching_pairs):
        raise SnapshotRecoveryGateError(
            "Snapshot has no complete matching request/response pair for its task/attempt ordinal."
        )
    request, response = matching_pairs[ordinal]
    # The request record labels the selected Omnitrix model/adapter; the
    # response record labels the provider-reported model ID. Those may differ
    # (for example, an adapter alias can map to a concrete provider model ID).
    # The provider must agree on both records, while the snapshot's model field
    # must match the provider-reported response model.
    for record, label in ((request, "request"), (response, "response")):
        if record.get("provider") != snapshot_metadata.get("provider"):
            raise SnapshotRecoveryGateError(
                f"Snapshot does not match transcript {label} provider."
            )
        if not isinstance(record.get("model"), str) or not record.get("model").strip():
            raise SnapshotRecoveryGateError(
                f"Transcript {label} model identity is missing."
            )
    if response.get("model") != snapshot_metadata.get("model"):
        raise SnapshotRecoveryGateError(
            "Snapshot does not match transcript response model."
        )

    return {
        "interaction_sequence": ordinal,
        "request_transcript_sequence": request["sequence"],
        "response_transcript_sequence": response["sequence"],
        "request_sha256": request["request_sha256"],
        "response_sha256": response["response_sha256"],
        "content_hashes_verified": False,
    }
