"""Compare decrypted snapshot payloads with metadata-only transcript digests."""
from __future__ import annotations

import hmac
from typing import Any

from core.persistence.model_state import (
    model_request_transcript_sha256,
    model_response_transcript_sha256,
)
from core.persistence.model_state_snapshots import ModelStateSnapshotStore, ModelStateSnapshotError
from core.persistence.snapshot_recovery_gate import SnapshotRecoveryGateError


def verify_snapshot_content_hashes(
    *,
    snapshot_store: ModelStateSnapshotStore,
    snapshot_id: str,
    expected_request_sha256: str,
    expected_response_sha256: str,
) -> dict[str, Any]:
    """Decrypt a stored pair and compare exact canonical hashes; never resumes a run."""
    if not isinstance(snapshot_store, ModelStateSnapshotStore):
        raise TypeError("snapshot_store must be a ModelStateSnapshotStore.")
    for name, value in (
        ("expected_request_sha256", expected_request_sha256),
        ("expected_response_sha256", expected_response_sha256),
    ):
        if (
            not isinstance(value, str) or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value.lower())
        ):
            raise SnapshotRecoveryGateError(f"{name} is not a valid SHA-256 digest.")

    request, response = snapshot_store.load_pair(snapshot_id)
    actual_request = model_request_transcript_sha256(request)
    actual_response = model_response_transcript_sha256(response)
    if not hmac.compare_digest(actual_request, expected_request_sha256.lower()):
        raise SnapshotRecoveryGateError("Decrypted snapshot request hash does not match transcript.")
    if not hmac.compare_digest(actual_response, expected_response_sha256.lower()):
        raise SnapshotRecoveryGateError("Decrypted snapshot response hash does not match transcript.")
    return {
        "content_hashes_verified": True,
        "request_sha256_verified": True,
        "response_sha256_verified": True,
    }
