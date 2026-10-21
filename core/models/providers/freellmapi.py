"""Optional adapter for a loopback/private FreeLLMAPI OpenAI-compatible gateway."""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from core.models.base import ModelResponseError
from core.models.providers.openrouter import OpenRouterAdapter


def _validated_base_url(raw: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("FreeLLMAPI base URL must be non-empty.")
    value = raw.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("FreeLLMAPI base URL must be an absolute HTTP(S) URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("FreeLLMAPI base URL must not contain credentials, query, or fragment.")
    host = (parsed.hostname or "").casefold()
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme != "https" and not loopback:
        raise ValueError("Non-loopback FreeLLMAPI endpoints must use HTTPS.")
    if parsed.path and parsed.path != "/v1":
        raise ValueError("FreeLLMAPI base URL must point to the /v1 API root.")
    return value


class FreeLLMAPIAdapter(OpenRouterAdapter):
    """OpenAI-compatible adapter for FreeLLMAPI; model IDs may be auto-routing aliases."""

    def __init__(
        self,
        name: str,
        model_id: str,
        api_key: str | None = None,
        api_key_env: str = "FREELLMAPI_API_KEY",
        base_url: str | None = None,
        timeout: float = 75.0,
        max_output_tokens: int = 8192,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Adapter name cannot be empty.")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("FreeLLMAPI model_id cannot be empty.")
        if not isinstance(api_key_env, str) or not api_key_env.strip():
            raise ValueError("api_key_env cannot be empty.")
        configured_url = base_url or os.getenv("FREELLMAPI_BASE_URL", "http://127.0.0.1:3001/v1")
        self._freellmapi_base_url = _validated_base_url(configured_url)
        super().__init__(
            name=name,
            model_id=model_id,
            api_key=api_key,
            api_key_env=api_key_env,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
            reasoning_effort=None,
            exclude_reasoning=True,
            referer=None,
            title="Omnitrix",
        )
        self.endpoint = self._freellmapi_base_url + "/chat/completions"

    @property
    def provider(self) -> str:
        return "freellmapi"

    def is_available(self) -> bool:
        return bool(
            (self._api_key or os.getenv(self._api_key_env))
            and self._freellmapi_base_url
        )

    def _allowed_model_ids(self) -> set[str]:
        ids = {self._model_id}
        for raw in os.getenv("FREELLMAPI_ALLOWED_MODEL_IDS", "").split(","):
            candidate = raw.strip()
            if candidate:
                ids.add(candidate)
        return ids

    def supports_model_id(self, model_id: str) -> bool:
        """Allow only the configured alias and the explicitly allowlisted routed IDs."""
        return isinstance(model_id, str) and model_id in self._allowed_model_ids()

    def generate(self, request):
        response = super().generate(request)
        if response.model_identity_source == "provider_response":
            if response.model not in self._allowed_model_ids():
                raise ModelResponseError(
                    "FreeLLMAPI returned a model identity outside Omnitrix's explicit route allowlist."
                )
        return response
