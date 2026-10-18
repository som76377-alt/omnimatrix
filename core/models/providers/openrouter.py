"""OpenRouter Chat Completions adapter for opt-in free/hosted model candidates.

This adapter intentionally does not retry requests automatically: a timed-out
inference request may still have been processed upstream. Omnitrix owns retry
and recovery policy.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.models.base import (
    ModelAdapter,
    ModelAuthenticationError,
    ModelRequestError,
    ModelResponse,
    ModelResponseError,
)
from core.models.messages import MessageRole, ModelRequest
from core.models.types import ModelToolCall


class OpenRouterAdapter(ModelAdapter):
    """Adapter for OpenRouter's OpenAI-compatible chat-completions endpoint."""

    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(
        self,
        name: str,
        model_id: str,
        api_key: str | None = None,
        api_key_env: str = "OPENROUTER_API_KEY",
        timeout: float = 60.0,
        max_output_tokens: int = 8192,
        referer: str | None = "https://github.com/som76377-alt/omnimatrix",
        title: str = "Omnitrix",
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Adapter name cannot be empty.")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("OpenRouter model_id cannot be empty.")
        if not isinstance(api_key_env, str) or not api_key_env.strip():
            raise ValueError("api_key_env cannot be empty.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")
        if (
            isinstance(max_output_tokens, bool)
            or not isinstance(max_output_tokens, int)
            or not 1 <= max_output_tokens <= 65_536
        ):
            raise ValueError("max_output_tokens must be between 1 and 65536.")
        if referer is not None and not isinstance(referer, str):
            raise TypeError("referer must be a string or None.")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title cannot be empty.")

        self._name = name
        self._model_id = model_id
        self._api_key = api_key
        self._api_key_env = api_key_env
        self._timeout = float(timeout)
        self._max_output_tokens = max_output_tokens
        self._referer = referer
        self._title = title

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider(self) -> str:
        return "openrouter"

    def supports_model_id(self, model_id: str) -> bool:
        return isinstance(model_id, str) and model_id == self._model_id

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest.")
        if request.continuation is not None:
            raise ModelRequestError(
                "OpenRouter uses full conversation history; provider continuation is unsupported."
            )
        api_key = self._api_key or os.getenv(self._api_key_env)
        if not api_key:
            raise ModelAuthenticationError(
                f"OpenRouter API key not found. Set {self._api_key_env}."
            )

        payload = self._build_payload(request)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-Title": self._title,
        }
        if self._referer:
            headers["HTTP-Referer"] = self._referer
        http_request = Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
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
                    f"OpenRouter authentication/permission failed ({status})."
                ) from exc
            # Do not echo arbitrary provider error bodies: they may contain user data.
            raise ModelRequestError(
                f"OpenRouter request failed with HTTP {status}; automatic retry is disabled."
            ) from exc
        except (URLError, TimeoutError) as exc:
            if isinstance(exc, TimeoutError):
                message = f"OpenRouter request timed out after {self._timeout:g} seconds."
            else:
                message = f"OpenRouter connection failed: {exc.reason}"
            raise ModelRequestError(message) from exc

        try:
            data: Any = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ModelResponseError("OpenRouter returned invalid JSON.") from exc
        if not isinstance(data, dict):
            raise ModelResponseError("OpenRouter returned an invalid response object.")

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelResponseError("OpenRouter response did not contain a valid choice.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ModelResponseError("OpenRouter response did not contain a message object.")

        content = self._extract_content(message.get("content"))
        tool_calls = self._extract_tool_calls(message.get("tool_calls", []))
        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = None
        response_model = data.get("model")
        if not isinstance(response_model, str) or not response_model.strip():
            response_model = self._model_id

        return ModelResponse(
            content=content,
            model=response_model,
            provider=self.provider,
            usage=usage,
            tool_calls=tuple(tool_calls),
        )

    def _build_payload(self, request: ModelRequest) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        if request.instructions:
            messages.append({"role": "system", "content": request.instructions})

        for message in request.messages:
            if message.role == MessageRole.USER:
                messages.append({"role": "user", "content": message.content})
            elif message.role == MessageRole.ASSISTANT:
                item: dict[str, Any] = {
                    "role": "assistant",
                    "content": message.content or None,
                }
                if message.tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.tool_name,
                                "arguments": json.dumps(
                                    call.arguments,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            },
                        }
                        for call in message.tool_calls
                    ]
                messages.append(item)
            elif message.role == MessageRole.TOOL:
                result = message.tool_result
                if result is None:
                    raise ModelRequestError("Tool message is missing its result.")
                output: Any = result.output if result.success else {
                    "error": result.error or "Tool execution failed."
                }
                content = (
                    output
                    if isinstance(output, str)
                    else json.dumps(output, ensure_ascii=False, default=str)
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": result.tool_call_id,
                    "content": content,
                })

        if not messages or not any(item["role"] == "user" for item in messages):
            raise ModelRequestError("OpenRouter request requires at least one user message.")

        payload: dict[str, Any] = {
            "model": self._model_id,
            "messages": messages,
            "max_tokens": self._max_output_tokens,
        }
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters_schema,
                    },
                }
                for tool in request.tools
            ]
            payload["tool_choice"] = "auto"
        return payload

    @staticmethod
    def _extract_content(raw: Any) -> str:
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list):
            parts: list[str] = []
            for item in raw:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        raise ModelResponseError("OpenRouter returned an invalid message content.")

    @staticmethod
    def _extract_tool_calls(raw: Any) -> list[ModelToolCall]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ModelResponseError("OpenRouter returned invalid tool calls.")
        calls: list[ModelToolCall] = []
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ModelResponseError("OpenRouter returned an invalid tool call.")
            call_id = item.get("id")
            function = item.get("function")
            if not isinstance(call_id, str) or not call_id.strip() or not isinstance(function, dict):
                raise ModelResponseError("OpenRouter tool call is missing its identity/function.")
            name = function.get("name")
            arguments = function.get("arguments", "{}")
            if not isinstance(name, str) or not name.strip():
                raise ModelResponseError("OpenRouter tool call has an invalid function name.")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError as exc:
                    raise ModelResponseError(
                        f"OpenRouter tool call {index} has invalid JSON arguments."
                    ) from exc
            if not isinstance(arguments, dict):
                raise ModelResponseError(
                    f"OpenRouter tool call {index} arguments must be a JSON object."
                )
            calls.append(ModelToolCall(
                id=call_id,
                tool_name=name,
                arguments=arguments,
            ))
        return calls
