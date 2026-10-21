"""Groq Chat Completions adapter.

Groq is OpenAI-compatible, but GPT-OSS has model-specific reasoning fields:
it does not accept reasoning_format. Never leak internal reasoning into the
user-facing answer; consume only the final message content.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.models.base import (
    ModelAuthenticationError,
    ModelRequestError,
    ModelResponse,
    ModelResponseError,
)
from core.models.messages import ModelRequest
from core.models.providers.openrouter import OpenRouterAdapter


class GroqAdapter(OpenRouterAdapter):
    """Groq Cloud adapter using the OpenAI-compatible Chat Completions API."""

    endpoint = "https://api.groq.com/openai/v1/chat/completions"

    @property
    def provider(self) -> str:
        return "groq"

    def is_available(self) -> bool:
        # Never treat a paid-by-token route as free unless the operator explicitly
        # confirms eligibility for a free quota. This is a safety gate, not a claim
        # that Groq is free or that a request cannot incur a charge.
        return (
            os.getenv("GROQ_FREE_QUOTA_CONFIRMED", "").strip().lower() == "true"
            and super().is_available()
        )

    def _build_payload(self, request: ModelRequest) -> dict:
        payload = super()._build_payload(request)
        # Do not inherit OpenRouter's provider-specific reasoning object.
        payload.pop("reasoning", None)
        model_id = self._model_id.casefold()
        if model_id.startswith("openai/gpt-oss-"):
            # Groq documents that GPT-OSS does not support reasoning_format.
            # include_reasoning=false is its supported way to omit reasoning
            # tokens while retaining the final answer in message.content.
            payload.pop("reasoning_format", None)
            payload["include_reasoning"] = False
            payload["reasoning_effort"] = "low"
        else:
            payload.setdefault("reasoning_effort", "low")
            payload.setdefault("reasoning_format", "hidden")
        return payload

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest.")
        if request.continuation is not None:
            raise ModelRequestError(
                "Groq uses full conversation history; provider continuation is unsupported."
            )
        if os.getenv("GROQ_FREE_QUOTA_CONFIRMED", "").strip().lower() != "true":
            raise ModelAuthenticationError(
                "Groq route is gated until GROQ_FREE_QUOTA_CONFIRMED=true; no request was sent."
            )
        api_key = self._api_key or os.getenv(self._api_key_env)
        if not api_key:
            raise ModelAuthenticationError(
                f"Groq API key not found. Set {self._api_key_env}."
            )

        payload = self._build_payload(request)
        http_request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Omnitrix/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self._timeout) as response:
                raw_body = response.read()
        except HTTPError as exc:
            status = exc.code
            try:
                exc.close()
            except Exception:
                pass
            if status in (401, 403):
                raise ModelAuthenticationError(
                    f"Groq authentication/permission failed ({status})."
                ) from exc
            raise ModelRequestError(
                f"Groq request failed with HTTP {status}; automatic retry is disabled."
            ) from exc
        except (URLError, TimeoutError) as exc:
            if isinstance(exc, TimeoutError):
                message = f"Groq request timed out after {self._timeout:g} seconds."
            else:
                message = f"Groq connection failed: {exc.reason}"
            raise ModelRequestError(message) from exc

        try:
            data = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ModelResponseError("Groq returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise ModelResponseError("Groq returned an invalid response object.")

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelResponseError("Groq response did not contain a valid choice.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ModelResponseError("Groq response did not contain a message object.")

        content = self._extract_content(message.get("content"))
        if not content.strip():
            # GPT-OSS may include a separate reasoning field. It is not a user-facing
            # answer and must never be substituted for a missing final response.
            raise ModelResponseError(
                "Groq returned no final answer text; reasoning content was not exposed as a substitute."
            )
        tool_calls = self._extract_tool_calls(message.get("tool_calls", []))
        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = None
        reported_model = data.get("model")
        identity_source = "provider_response"
        if not isinstance(reported_model, str) or not reported_model.strip():
            reported_model = self._model_id
            identity_source = "configured_fallback"

        return ModelResponse(
            content=content,
            model=reported_model,
            provider=self.provider,
            usage=usage,
            tool_calls=tuple(tool_calls),
            model_identity_source=identity_source,
        )
