import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.models.base import (
    ModelAdapter,
    ModelAdapterError,
    ModelAuthenticationError,
    ModelRequestError,
    ModelResponse,
    ModelResponseError,
)


class GeminiAdapter(ModelAdapter):
    """
    Adapter for Google's Gemini Interactions API.

    The adapter translates Omnitrix's provider-independent prompt contract
    into Gemini's HTTP request format and normalizes Gemini's response.
    """

    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(
        self,
        name: str,
        model_id: str,
        api_key: str | None = None,
        api_key_env: str = "GEMINI_API_KEY",
        timeout: float = 60.0,
    ) -> None:
        if not name.strip():
            raise ValueError("Adapter name cannot be empty.")

        if not model_id.strip():
            raise ValueError("Gemini model_id cannot be empty.")

        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        self._name = name
        self._model_id = model_id
        self._api_key = api_key
        self._api_key_env = api_key_env
        self._timeout = timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider(self) -> str:
        return "google"

    def generate(self, prompt: str) -> ModelResponse:
        api_key = self._api_key or os.getenv(self._api_key_env)

        if not api_key:
            raise ModelAuthenticationError(
                f"Gemini API key not found. Set {self._api_key_env}."
            )

        payload = json.dumps(
            {
                "model": self._model_id,
                "input": prompt,
            }
        ).encode("utf-8")

        request = Request(
            self.endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
                "Api-Revision": "2026-05-20",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._timeout) as response:
                raw_body = response.read()

        except HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="replace")

            if exc.code in (401, 403):
                raise ModelAuthenticationError(
                    f"Gemini authentication failed ({exc.code})."
                ) from exc

            raise ModelRequestError(
                f"Gemini request failed ({exc.code}): {response_body}"
            ) from exc

        except URLError as exc:
            raise ModelRequestError(
                f"Gemini connection failed: {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise ModelRequestError(
                "Gemini request timed out."
            ) from exc

        try:
            data: Any = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ModelResponseError(
                "Gemini returned invalid JSON."
            ) from exc

        content = self._extract_text(data)

        usage = data.get("usage")
        if usage is not None and not isinstance(usage, dict):
            usage = None

        return ModelResponse(
            content=content,
            model=data.get("model", self._model_id),
            provider=self.provider,
            usage=usage,
        )

    def _extract_text(self, data: Any) -> str:
        steps = data.get("steps")

        if not isinstance(steps, list):
            raise ModelResponseError(
                "Gemini response does not contain valid steps."
            )

        text_parts: list[str] = []

        for step in steps:
            if not isinstance(step, dict):
                continue

            if step.get("type") != "model_output":
                continue

            content = step.get("content")

            if not isinstance(content, list):
                continue

            for item in content:
                if not isinstance(item, dict):
                    continue

                if item.get("type") == "text":
                    text = item.get("text")

                    if isinstance(text, str):
                        text_parts.append(text)

        if not text_parts:
            raise ModelResponseError(
                "Gemini response did not contain text output."
            )

        return "".join(text_parts)
