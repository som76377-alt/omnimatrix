"""Opt-in AES-GCM encrypted storage for paired model request/response snapshots.

The encryption key is supplied by the caller and is never written to SQLite.
This module stores recoverable model data but does not restore or resume runs.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.models.base import ModelResponse
from core.models.messages import ModelRequest
from core.persistence.model_state import (
    MAX_MODEL_STATE_BYTES,
    ModelStateCodecError,
    decode_model_state,
    encode_model_state,
)
from core.persistence.sqlite_journal import SQLiteJournal


MAX_SNAPSHOT_PLAINTEXT_BYTES = (2 * MAX_MODEL_STATE_BYTES) + 1024
NONCE_BYTES = 12
KEY_BYTES = 32


class ModelStateSnapshotError(ValueError):
    """Snapshot storage is disabled, invalid, unavailable, or fails integrity checks."""


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ModelStateSnapshotError("Snapshot must contain finite JSON-compatible values.") from exc


def _identity(
    run_id: str, task_id: str, attempt_id: str, interaction_sequence: int,
    provider: str, model: str, key_id: str,
) -> dict[str, Any]:
    for name, value in (("run_id", run_id), ("task_id", task_id), ("attempt_id", attempt_id),
                        ("provider", provider), ("model", model), ("key_id", key_id)):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ModelStateSnapshotError(f"{name} must be non-empty text of at most 200 characters.")
    if isinstance(interaction_sequence, bool) or not isinstance(interaction_sequence, int) or interaction_sequence < 0:
        raise ModelStateSnapshotError("interaction_sequence must be a non-negative integer.")
    return {
        "schema_version": 1, "run_id": run_id, "task_id": task_id,
        "attempt_id": attempt_id, "interaction_sequence": interaction_sequence,
        "provider": provider, "model": model, "key_id": key_id,
    }


class ModelStateSnapshotStore:
    """Encrypted snapshot store; disabled unless the caller explicitly opts in.

    Provide a 32-byte key from a separate secret source. Do not store that key
    beside the SQLite database or commit it to source control. Losing the key
    makes snapshots permanently unreadable. Existing snapshots never authorize
    replay, tool execution, or automatic resume.
    """

    def __init__(
        self, journal: SQLiteJournal, *, enabled: bool = False,
        encryption_key: bytes | None = None, key_id: str = "local-v1",
    ) -> None:
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be a bool.")
        if not enabled:
            self._journal = journal
            self._enabled = False
            self._key = None
            self._key_id = key_id
            return
        if not isinstance(encryption_key, bytes) or len(encryption_key) != KEY_BYTES:
            raise ModelStateSnapshotError("Opt-in storage requires an externally supplied 32-byte AES key.")
        if not isinstance(key_id, str) or not key_id.strip() or len(key_id) > 200:
            raise ModelStateSnapshotError("key_id must be non-empty text of at most 200 characters.")
        self._journal = journal
        self._enabled = True
        self._key = bytes(encryption_key)
        self._key_id = key_id

    @property
    def enabled(self) -> bool:
        return self._enabled

    def save_pair(
        self, run_id: str, task_id: str, attempt_id: str, interaction_sequence: int,
        request: ModelRequest, response: ModelResponse,
    ) -> str:
        """Atomically persist one complete request/response pair, never a half-pair."""
        if not self._enabled or self._key is None:
            raise ModelStateSnapshotError("Model-state snapshot persistence is disabled.")
        if not isinstance(request, ModelRequest) or not isinstance(response, ModelResponse):
            raise TypeError("save_pair requires a ModelRequest and ModelResponse.")
        if not response.provider.strip() or not response.model.strip():
            raise ModelStateSnapshotError("Response provider and model must be non-empty.")
        identity = _identity(
            run_id, task_id, attempt_id, interaction_sequence,
            response.provider, response.model, self._key_id,
        )
        try:
            pair = {
                "request": encode_model_state(request),
                "response": encode_model_state(response),
            }
        except ModelStateCodecError as exc:
            raise ModelStateSnapshotError("Model request/response failed codec validation.") from exc
        plaintext = _canonical_json(pair)
        if len(plaintext) > MAX_SNAPSHOT_PLAINTEXT_BYTES:
            raise ModelStateSnapshotError("Combined model-state snapshot exceeds the size limit.")
        digest = hashlib.sha256(plaintext).hexdigest()
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext, _canonical_json(identity))
        snapshot_id = self._journal.save_encrypted_model_state_snapshot(
            run_id=run_id, task_id=task_id, attempt_id=attempt_id,
            interaction_sequence=interaction_sequence, provider=response.provider,
            model=response.model, key_id=self._key_id, nonce=nonce,
            ciphertext=ciphertext, payload_sha256=digest,
        )
        return snapshot_id

    def load_pair(self, snapshot_id: str) -> tuple[ModelRequest, ModelResponse]:
        """Decrypt and validate a stored pair; never executes or resumes anything."""
        if not self._enabled or self._key is None:
            raise ModelStateSnapshotError("Model-state snapshot persistence is disabled.")
        row = self._journal.get_encrypted_model_state_snapshot(snapshot_id)
        if row is None:
            raise KeyError(f"Unknown model-state snapshot: {snapshot_id}")
        if not hmac.compare_digest(row["key_id"], self._key_id):
            raise ModelStateSnapshotError("Snapshot encryption key identifier does not match.")
        identity = _identity(
            row["run_id"], row["task_id"], row["attempt_id"], row["interaction_sequence"],
            row["provider"], row["model"], row["key_id"],
        )
        try:
            plaintext = AESGCM(self._key).decrypt(
                row["nonce"], row["ciphertext"], _canonical_json(identity)
            )
        except (InvalidTag, ValueError) as exc:
            raise ModelStateSnapshotError("Snapshot authentication failed; refusing to load it.") from exc
        if len(plaintext) > MAX_SNAPSHOT_PLAINTEXT_BYTES:
            raise ModelStateSnapshotError("Stored model-state snapshot exceeds the size limit.")
        actual_digest = hashlib.sha256(plaintext).hexdigest()
        if not hmac.compare_digest(actual_digest, row["payload_sha256"]):
            raise ModelStateSnapshotError("Snapshot plaintext digest mismatch.")
        try:
            pair = json.loads(plaintext)
            if not isinstance(pair, dict) or set(pair) != {"request", "response"}:
                raise ModelStateSnapshotError("Decrypted snapshot has an invalid shape.")
            request = decode_model_state(pair["request"])
            response = decode_model_state(pair["response"])
        except (json.JSONDecodeError, UnicodeDecodeError, ModelStateCodecError) as exc:
            raise ModelStateSnapshotError("Decrypted snapshot failed model-state validation.") from exc
        if not isinstance(request, ModelRequest) or not isinstance(response, ModelResponse):
            raise ModelStateSnapshotError("Snapshot must contain a request/response pair.")
        if response.provider != row["provider"] or response.model != row["model"]:
            raise ModelStateSnapshotError("Snapshot provider/model identity mismatch.")
        return request, response

    def delete(self, snapshot_id: str) -> bool:
        """Explicitly delete a snapshot for privacy/retention control."""
        if not self._enabled:
            raise ModelStateSnapshotError("Model-state snapshot persistence is disabled.")
        return self._journal.delete_encrypted_model_state_snapshot(snapshot_id)
