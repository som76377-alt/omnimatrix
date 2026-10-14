"""Read-only provider compatibility checks for encrypted model snapshots.

Compatibility inspection never calls a provider and never authorizes resume.
"""
from __future__ import annotations

from typing import Any, Iterable

from core.models.base import ModelAdapter
from core.models.types import ModelContinuation


def inspect_provider_continuation_compatibility(
    *,
    provider: str,
    model: str,
    continuation: ModelContinuation | None,
    adapters: Iterable[ModelAdapter],
) -> dict[str, Any]:
    """Inspect whether the currently registered adapter recognizes snapshot state.

    The result is deliberately not a resume authorization. Even a compatible
    provider continuation does not prove that tools, checkpoints, approvals, or
    the full live execution state are safe to restore.
    """
    if not isinstance(provider, str) or not provider.strip():
        raise TypeError("provider must be non-empty text.")
    if not isinstance(model, str) or not model.strip():
        raise TypeError("model must be non-empty text.")
    if continuation is not None and not isinstance(continuation, ModelContinuation):
        raise TypeError("continuation must be a ModelContinuation or None.")

    matching = [
        adapter for adapter in adapters
        if isinstance(adapter, ModelAdapter)
        and adapter.provider == provider
        and adapter.supports_model_id(model)
    ]
    if len(matching) != 1:
        return {
            "checked": True,
            "provider": provider,
            "model": model,
            "adapter_match_count": len(matching),
            "provider_compatible": False,
            "continuation_state_present": continuation is not None,
            "continuation_state_compatible": False if continuation is not None else None,
            "restore_ready": False,
            "reason": "no_unique_registered_adapter_matches_provider_and_model",
        }

    adapter = matching[0]
    if continuation is None:
        return {
            "checked": True,
            "provider": provider,
            "model": model,
            "adapter_match_count": 1,
            "provider_compatible": True,
            "continuation_state_present": False,
            "continuation_state_compatible": None,
            "restore_ready": False,
            "reason": "no_provider_continuation_state; live reconstruction remains unimplemented",
        }

    continuation_matches_provider = continuation.provider == provider
    state_supported = continuation_matches_provider and adapter.supports_continuation(continuation)
    return {
        "checked": True,
        "provider": provider,
        "model": model,
        "adapter_match_count": 1,
        "provider_compatible": True,
        "continuation_state_present": True,
        "continuation_state_compatible": state_supported,
        "restore_ready": False,
        "reason": (
            "recognized_by_registered_adapter"
            if state_supported
            else "continuation_provider_or_state_shape_is_unsupported"
        ),
    }
