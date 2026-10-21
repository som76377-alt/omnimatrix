"""Tiny live checks for the six configured model routes.

One short request is sent to each eligible configured model using that profile's
own key. No conversation history or user content is sent. Secrets and generated
text are never printed. Groq routes are skipped unless the operator explicitly
confirms that a no-cost quota is available; no paid fallback is ever attempted.
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

        if model.provider == "groq" and os.getenv("GROQ_FREE_QUOTA_CONFIRMED", "").strip().lower() != "true":
            result.update(
                status="skipped_requires_free_quota_confirmation",
                reason="Groq models have per-token pricing; no inference request was sent without explicit free-quota confirmation.",
            )
            results.append(result)
            print(json.dumps(result, sort_keys=True))
            continue

        if model.metadata.get("estimated_cost_usd") != 0 and model.provider != "groq":
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
            # Reasoning-heavy Groq models may spend a tiny cap on internal work
            # and return no final text; use a still-small 64-token probe for Groq.
            adapter._max_output_tokens = 64 if model.provider == "groq" else 8
        if hasattr(adapter, "_max_retries"):
            # One retry is allowed for transient transport/quota responses; this is
            # still the same configured route and never triggers a paid fallback.
            adapter._max_retries = max(2, getattr(adapter, "_max_retries", 0))

        request = ModelRequest(
            messages=(ModelMessage(role=MessageRole.USER, content=prompt),),
            # Keep the probe body minimal and provider-neutral: one user message,
            # no tools, no system-role requirements, and no user conversation data.
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
            # Provider adapters intentionally sanitize their error messages; retain
            # the safe status/category so auth, timeout, and request failures are
            # distinguishable without exposing credentials or generated text.
            safe_message = str(exc)[:240]
            if "timed out" in safe_message.lower():
                failure_reason = "timeout"
            elif "authentication" in safe_message.lower() or "api key" in safe_message.lower():
                failure_reason = "authentication_or_permission"
            elif "429" in safe_message:
                failure_reason = "rate_limit_or_quota"
            else:
                failure_reason = "provider_call_failed"
            result.update(
                status="failed",
                reason=failure_reason,
                error_type=type(exc).__name__,
                safe_error=safe_message,
                latency_seconds=round(time.perf_counter() - started, 3),
            )

        results.append(result)
        print(json.dumps(result, sort_keys=True))

    failed = [item for item in results if item.get("status") == "failed" or item.get("status") == "refused"]
    passed = [item for item in results if item.get("status") in {"passed", "passed_configured_identity_only"}]
    skipped = [item for item in results if str(item.get("status", "")).startswith("skipped_")]
    if failed:
        print(f"FAIL: {len(failed)} route(s) failed or were refused; no paid fallback was attempted.")
        return 1
    if skipped:
        print(f"PARTIAL: {len(passed)} routes passed; {len(skipped)} route(s) were skipped until free-quota eligibility is explicitly confirmed.")
        return 1
    print(f"PASS: all {len(passed)} configured routes returned non-empty provider responses; model identity source is recorded per route.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
