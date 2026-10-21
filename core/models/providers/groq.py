"""Groq Chat Completions adapter.

Groq speaks the OpenAI-compatible API, but its request should not inherit
OpenRouter-specific headers or provider metadata. Keep the endpoint, response
identity, and error classification explicitly Groq-specific.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.models.base import (
    ModelAdapterError,
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

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest.")
        if request.continuation is not None:
            raise ModelRequestError(
                "Groq uses full conversation history; provider continuation is unsupported."
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
