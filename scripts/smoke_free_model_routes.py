"""Tiny, explicit live checks for the six configured zero-price/free-quota routes.

One short request is sent to each configured model using that profile's own key.
No conversation history or user content is sent. Secrets and generated text are
never printed. A provider's free quota can still be rate-limited or exhausted;
this script deliberately does not fall back to a paid model.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.models.loader import ModelConfigLoader
from core.models.messages import MessageRole, ModelMessage, ModelRequest
from core.models.providers.bootstrap import build_adapter_registry


CONFIG = ROOT / "config" / "mobile.models.json"
EXPECTED_KEYS = {
    "GEMINI_API_KEY",
    "GEMINI_API_KEY_1",
    "OPENROUTER_API_KEY",
    "OPENROUTER_API_KEY_1",
    "GROQ_API_KEY",
    "GROQ_API_KEY_1",
}


def main() -> int:
    registry = ModelConfigLoader().load(CONFIG)
    models = registry.list_enabled()
    if len(models) != 6:
        raise SystemExit(f"FAIL: expected six enabled model profiles, found {len(models)}.")

    configured_keys = {model.metadata.get("api_key_env") for model in models}
    if configured_keys != EXPECTED_KEYS:
        raise SystemExit("FAIL: model profiles do not map one-to-one to the six expected key slots.")

    adapters = build_adapter_registry(registry)
    results = []
    prompt = "Reply with exactly ROUTE_READY and no other text."

    for model in models:
        key_env = model.metadata.get("api_key_env")
        result = {
            "profile": model.name,
            "provider": model.provider,
            "configured_model": model.model_id,
            "key_slot": key_env,
        }

        if model.metadata.get("estimated_cost_usd") != 0:
            result.update(status="refused", reason="non_zero_estimated_cost")
            results.append(result)
            print(json.dumps(result, sort_keys=True))
            continue

        if model.metadata.get("cost_class") == "free":
            if not model.model_id or not model.model_id.endswith(":free"):
                result.update(status="refused", reason="model_not_explicitly_free")
                results.append(result)
                print(json.dumps(result, sort_keys=True))
                continue
        elif model.metadata.get("cost_class") != "user_provided_free_quota":
            result.update(status="refused", reason="unrecognized_cost_class")
            results.append(result)
            print(json.dumps(result, sort_keys=True))
            continue

        if not isinstance(key_env, str) or not os.getenv(key_env):
            result.update(status="failed", reason="key_slot_missing")
            results.append(result)
            print(json.dumps(result, sort_keys=True))
            continue

        adapter = adapters.get(model.name)
        if not adapter.is_available():
            result.update(status="failed", reason="adapter_unavailable")
            results.append(result)
            print(json.dumps(result, sort_keys=True))
            continue

        # Limit free-route test output where the adapter supports that setting;
        # do not retry failed calls, and never auto-fallback to a different model.
        if hasattr(adapter, "_max_output_tokens"):
            adapter._max_output_tokens = 16
        if hasattr(adapter, "_max_retries"):
            adapter._max_retries = 0

        request = ModelRequest(
            messages=(ModelMessage(role=MessageRole.USER, content=prompt),),
            instructions=(
                "This is a minimal connectivity check for the configured model route. "
                "Answer with exactly ROUTE_READY, with no explanation and no tools."
            ),
        )
        started = time.perf_counter()
        try:
            response = adapter.generate(request)
            elapsed = round(time.perf_counter() - started, 3)
            reported_model = response.model
            identity_source = getattr(response, "model_identity_source", "unknown")
            provider_match = response.provider == model.provider
            identity_match = (
                isinstance(reported_model, str)
                and reported_model.strip().casefold() == model.model_id.casefold()
            )
            body_present = isinstance(response.content, str) and bool(response.content.strip())

            if not body_present:
                status = "failed"
                reason = "empty_response"
            elif not provider_match:
                status = "failed"
                reason = "provider_identity_mismatch"
            elif identity_source == "provider_response" and not identity_match:
                status = "failed"
                reason = "provider_model_identity_mismatch"
            elif identity_source == "provider_response":
                status = "passed"
                reason = None
            else:
                # The provider returned a response but its payload did not independently
                # report the model ID; record that distinction rather than inventing proof.
                status = "passed_configured_identity_only"
                reason = "provider_response_did_not_report_model_id"

            result.update(
                status=status,
                reason=reason,
                provider_reported=response.provider,
                provider_reported_model=reported_model,
                model_identity_source=identity_source,
                response_characters=len(response.content),
                latency_seconds=elapsed,
            )
        except Exception as exc:
            result.update(
                status="failed",
                reason="provider_call_failed",
                error_type=type(exc).__name__,
                latency_seconds=round(time.perf_counter() - started, 3),
            )

        results.append(result)
        print(json.dumps(result, sort_keys=True))

    failed = [item for item in results if item.get("status") == "failed" or item.get("status") == "refused"]
    passed = [item for item in results if item.get("status") in {"passed", "passed_configured_identity_only"}]
    if failed:
        print(f"FAIL: {len(failed)} route(s) failed or were refused; no paid fallback was attempted.")
        return 1
    print(f"PASS: all {len(passed)} configured routes returned non-empty provider responses; model identity source is recorded per route.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
