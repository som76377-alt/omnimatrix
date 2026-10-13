"""Versioned, integrity-checked serialization for normalized model state.

This codec is an in-memory serialization contract only. It does not persist data,
store provider secrets, or authorize conversation restoration or execution.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping

from core.models.base import ModelResponse
from core.models.messages import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelToolResult,
)
from core.models.types import ModelContinuation, ModelToolCall, ModelToolDefinition


MODEL_STATE_SCHEMA_VERSION = 1
MAX_MODEL_STATE_BYTES = 65_536


class ModelStateCodecError(ValueError):
    """A model-state envelope is invalid, unsupported, or exceeds safe limits."""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ModelStateCodecError("Model state must contain finite JSON-compatible values.") from exc


def _continuation_to_dict(value: ModelContinuation | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"provider": value.provider, "state": value.state}


def _continuation_from_dict(value: object) -> ModelContinuation | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"provider", "state"}:
        raise ModelStateCodecError("Continuation envelope has an invalid shape.")
    if not isinstance(value["provider"], str) or not isinstance(value["state"], dict):
        raise ModelStateCodecError("Continuation provider/state types are invalid.")
    return ModelContinuation(provider=value["provider"], state=dict(value["state"]))


def _tool_call_to_dict(call: ModelToolCall) -> dict[str, Any]:
    return {"id": call.id, "tool_name": call.tool_name, "arguments": call.arguments}


def _tool_call_from_dict(value: object) -> ModelToolCall:
    if not isinstance(value, Mapping) or set(value) != {"id", "tool_name", "arguments"}:
        raise ModelStateCodecError("Tool-call envelope has an invalid shape.")
    if not isinstance(value["id"], str) or not isinstance(value["tool_name"], str):
        raise ModelStateCodecError("Tool-call identity fields must be strings.")
    if not isinstance(value["arguments"], dict):
        raise ModelStateCodecError("Tool-call arguments must be an object.")
    return ModelToolCall(value["id"], value["tool_name"], dict(value["arguments"]))


def _tool_definition_to_dict(tool: ModelToolDefinition) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters_schema": tool.parameters_schema,
    }


def _tool_definition_from_dict(value: object) -> ModelToolDefinition:
    expected = {"name", "description", "parameters_schema"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ModelStateCodecError("Tool-definition envelope has an invalid shape.")
    if not isinstance(value["name"], str) or not isinstance(value["description"], str):
        raise ModelStateCodecError("Tool-definition text fields must be strings.")
    if not isinstance(value["parameters_schema"], dict):
        raise ModelStateCodecError("Tool-definition parameters_schema must be an object.")
    return ModelToolDefinition(
        value["name"], value["description"], dict(value["parameters_schema"])
    )


def _message_to_dict(message: ModelMessage) -> dict[str, Any]:
    result = None
    if message.tool_result is not None:
        result = {
            "tool_call_id": message.tool_result.tool_call_id,
            "tool_name": message.tool_result.tool_name,
            "success": message.tool_result.success,
            "output": message.tool_result.output,
            "error": message.tool_result.error,
        }
    return {
        "role": message.role.value,
        "content": message.content,
        "tool_calls": [_tool_call_to_dict(call) for call in message.tool_calls],
        "tool_result": result,
    }


def _message_from_dict(value: object) -> ModelMessage:
    expected = {"role", "content", "tool_calls", "tool_result"}
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ModelStateCodecError("Message envelope has an invalid shape.")
    if not isinstance(value["role"], str) or not isinstance(value["content"], str):
        raise ModelStateCodecError("Message role/content types are invalid.")
    if not isinstance(value["tool_calls"], list):
        raise ModelStateCodecError("Message tool_calls must be a list.")
    try:
        role = MessageRole(value["role"])
        calls = tuple(_tool_call_from_dict(call) for call in value["tool_calls"])
        raw_result = value["tool_result"]
        result = None
        if raw_result is not None:
            expected_result = {"tool_call_id", "tool_name", "success", "output", "error"}
            if not isinstance(raw_result, Mapping) or set(raw_result) != expected_result:
                raise ModelStateCodecError("Tool-result envelope has an invalid shape.")
            if (
                not isinstance(raw_result["tool_call_id"], str)
                or not isinstance(raw_result["tool_name"], str)
                or not isinstance(raw_result["success"], bool)
                or (raw_result["error"] is not None and not isinstance(raw_result["error"], str))
            ):
                raise ModelStateCodecError("Tool-result field types are invalid.")
            result = ModelToolResult(
                tool_call_id=raw_result["tool_call_id"],
                tool_name=raw_result["tool_name"],
                success=raw_result["success"],
                output=raw_result["output"],
                error=raw_result["error"],
            )
        return ModelMessage(role=role, content=value["content"], tool_calls=calls, tool_result=result)
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ModelStateCodecError):
            raise
        raise ModelStateCodecError("Message data violates model type constraints.") from exc


def _payload_to_dict(value: ModelRequest | ModelResponse) -> dict[str, Any]:
    if isinstance(value, ModelRequest):
        return {
            "kind": "request",
            "instructions": value.instructions,
            "messages": [_message_to_dict(message) for message in value.messages],
            "tools": [_tool_definition_to_dict(tool) for tool in value.tools],
            "continuation": _continuation_to_dict(value.continuation),
        }
    if isinstance(value, ModelResponse):
        if not all(isinstance(item, str) for item in (value.content, value.model, value.provider)):
            raise ModelStateCodecError("Response content/model/provider must be strings.")
        if value.usage is not None and not isinstance(value.usage, dict):
            raise ModelStateCodecError("Response usage must be an object or null.")
        return {
            "kind": "response",
            "content": value.content,
            "model": value.model,
            "provider": value.provider,
            "usage": value.usage,
            "tool_calls": [_tool_call_to_dict(call) for call in value.tool_calls],
            "continuation": _continuation_to_dict(value.continuation),
        }
    raise TypeError("Only ModelRequest and ModelResponse can be encoded.")


def encode_model_state(value: ModelRequest | ModelResponse) -> dict[str, Any]:
    """Create a bounded envelope. Callers must decide whether storing it is appropriate."""
    payload = _payload_to_dict(value)
    canonical_payload = _canonical_json(payload)
    if len(canonical_payload.encode("utf-8")) > MAX_MODEL_STATE_BYTES:
        raise ModelStateCodecError(
            f"Model state exceeds the {MAX_MODEL_STATE_BYTES}-byte limit."
        )
    return {
        "schema_version": MODEL_STATE_SCHEMA_VERSION,
        "payload": payload,
        "payload_sha256": hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest(),
    }


def decode_model_state(envelope: object) -> ModelRequest | ModelResponse:
    """Verify schema, size and digest before reconstructing normalized model data."""
    if not isinstance(envelope, Mapping) or set(envelope) != {
        "schema_version", "payload", "payload_sha256"
    }:
        raise ModelStateCodecError("Model-state envelope has an invalid shape.")
    version = envelope["schema_version"]
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != MODEL_STATE_SCHEMA_VERSION
    ):
        raise ModelStateCodecError(f"Unsupported model-state schema version: {version!r}.")
    payload = envelope["payload"]
    digest = envelope["payload_sha256"]
    if not isinstance(payload, Mapping):
        raise ModelStateCodecError("Model-state payload must be an object.")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ModelStateCodecError("Model-state digest is invalid.")
    if any(character not in "0123456789abcdef" for character in digest.lower()):
        raise ModelStateCodecError("Model-state digest must be hexadecimal.")
    canonical_payload = _canonical_json(dict(payload))
    encoded = canonical_payload.encode("utf-8")
    if len(encoded) > MAX_MODEL_STATE_BYTES:
        raise ModelStateCodecError(
            f"Model state exceeds the {MAX_MODEL_STATE_BYTES}-byte limit."
        )
    actual_digest = hashlib.sha256(encoded).hexdigest()
    if not hmac.compare_digest(actual_digest, digest.lower()):
        raise ModelStateCodecError("Model-state payload digest mismatch.")

    kind = payload.get("kind")
    try:
        if kind == "request":
            if set(payload) != {"kind", "instructions", "messages", "tools", "continuation"}:
                raise ModelStateCodecError("Request payload has an invalid shape.")
            if (
                payload["instructions"] is not None
                and not isinstance(payload["instructions"], str)
            ):
                raise ModelStateCodecError("Request instructions must be a string or null.")
            if not isinstance(payload["messages"], list) or not isinstance(payload["tools"], list):
                raise ModelStateCodecError("Request messages/tools must be lists.")
            return ModelRequest(
                instructions=payload["instructions"],
                messages=tuple(_message_from_dict(item) for item in payload["messages"]),
                tools=tuple(_tool_definition_from_dict(item) for item in payload["tools"]),
                continuation=_continuation_from_dict(payload["continuation"]),
            )
        if kind == "response":
            if set(payload) != {
                "kind", "content", "model", "provider", "usage", "tool_calls", "continuation"
            }:
                raise ModelStateCodecError("Response payload has an invalid shape.")
            if not all(isinstance(payload[key], str) for key in ("content", "model", "provider")):
                raise ModelStateCodecError("Response content/model/provider must be strings.")
            if payload["usage"] is not None and not isinstance(payload["usage"], dict):
                raise ModelStateCodecError("Response usage must be an object or null.")
            if not isinstance(payload["tool_calls"], list):
                raise ModelStateCodecError("Response tool_calls must be a list.")
            return ModelResponse(
                content=payload["content"],
                model=payload["model"],
                provider=payload["provider"],
                usage=payload["usage"],
                tool_calls=tuple(_tool_call_from_dict(item) for item in payload["tool_calls"]),
                continuation=_continuation_from_dict(payload["continuation"]),
            )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ModelStateCodecError):
            raise
        raise ModelStateCodecError("Model-state payload violates model type constraints.") from exc
    raise ModelStateCodecError("Model-state payload kind must be request or response.")
