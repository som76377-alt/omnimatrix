import json
import os
import time
from typing import Any, Callable
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
from core.models.types import (
    ModelContinuation,
    ModelToolCall,
)


class GeminiAdapter(ModelAdapter):
    """
    Adapter for Google's Gemini Interactions API.

    The adapter translates Omnitrix's provider-independent model contract
    into Gemini's native interaction and function-calling format.
    """

    endpoint = "https://generativelanguage.googleapis.com/v1beta/interactions"

    def __init__(
        self,
        name: str,
        model_id: str,
        api_key: str | None = None,
        api_key_env: str = "GEMINI_API_KEY",
        timeout: float = 60.0,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Adapter name cannot be empty.")

        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("Gemini model_id cannot be empty.")

        if timeout <= 0:
            raise ValueError("Timeout must be greater than zero.")

        if isinstance(max_retries, bool) or not isinstance(max_retries, int):
            raise TypeError("max_retries must be an integer.")

        if max_retries < 0:
            raise ValueError("max_retries cannot be negative.")

        if retry_backoff < 0:
            raise ValueError("retry_backoff cannot be negative.")

        if not callable(sleep):
            raise TypeError("sleep must be callable.")

        self._name = name
        self._model_id = model_id
        self._api_key = api_key
        self._api_key_env = api_key_env
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._sleep = sleep

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider(self) -> str:
        return "google"

    def generate(self, request: ModelRequest) -> ModelResponse:
        api_key = self._api_key or os.getenv(self._api_key_env)

        if not api_key:
            raise ModelAuthenticationError(
                f"Gemini API key not found. Set {self._api_key_env}."
            )

        payload = self._build_payload(request)

        http_request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )

        raw_body = self._send_request(http_request)

        try:
            data: Any = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ModelResponseError(
                "Gemini returned invalid JSON."
            ) from exc

        if not isinstance(data, dict):
            raise ModelResponseError(
                "Gemini returned an invalid response object."
            )

        interaction_id = data.get("id")

        if not isinstance(interaction_id, str) or not interaction_id.strip():
            raise ModelResponseError(
                "Gemini response did not contain a valid interaction ID."
            )

        content = self._extract_text(data)
        tool_calls = self._extract_tool_calls(data)

        usage = data.get("usage")
        if usage is not None and not isinstance(usage, dict):
            usage = None

        continuation = ModelContinuation(
            provider=self.provider,
            state={
                "interaction_id": interaction_id,
            },
        )

        return ModelResponse(
            content=content,
            model=data.get("model", self._model_id),
            provider=self.provider,
            usage=usage,
            tool_calls=tuple(tool_calls),
            continuation=continuation,
        )

    def _send_request(self, http_request: Request) -> bytes:
        attempt = 0

        while True:
            try:
                with urlopen(http_request, timeout=self._timeout) as response:
                    return response.read()

            except HTTPError as exc:
                try:
                    response_body = exc.read().decode("utf-8", errors="replace")
                finally:
                    exc.close()

                if exc.code in (401, 403):
                    raise ModelAuthenticationError(
                        f"Gemini authentication failed ({exc.code})."
                    ) from exc

                if exc.code not in (429, 500, 502, 503, 504):
                    raise ModelRequestError(
                        f"Gemini request failed ({exc.code}): {response_body}"
                    ) from exc

                if attempt >= self._max_retries:
                    raise ModelRequestError(
                        f"Gemini request failed ({exc.code}) after "
                        f"{attempt + 1} attempts: {response_body}"
                    ) from exc

                self._sleep(self._retry_backoff * (2 ** attempt))
                attempt += 1

            except (URLError, TimeoutError) as exc:
                if attempt >= self._max_retries:
                    if isinstance(exc, TimeoutError):
                        message = (
                            f"Gemini request timed out after "
                            f"{attempt + 1} attempts."
                        )
                    else:
                        message = (
                            f"Gemini connection failed after "
                            f"{attempt + 1} attempts: {exc.reason}"
                        )

                    raise ModelRequestError(message) from exc

                self._sleep(self._retry_backoff * (2 ** attempt))
                attempt += 1

    def _build_payload(self, request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model_id,
            "tools": self._build_tools(request),
        }

        if request.instructions is not None:
            payload["system_instruction"] = request.instructions

        if request.continuation is None:
            payload["input"] = self._build_initial_input(request)
        else:
            if request.continuation.provider != self.provider:
                raise ModelRequestError(
                    "Model continuation belongs to a different provider."
                )

            interaction_id = request.continuation.state.get("interaction_id")

            if not isinstance(interaction_id, str) or not interaction_id.strip():
                raise ModelRequestError(
                    "Gemini continuation does not contain a valid interaction ID."
                )

            payload["previous_interaction_id"] = interaction_id
            payload["input"] = self._build_tool_result_input(request)

        return payload

    def _build_tools(self, request: ModelRequest) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema,
            }
            for tool in request.tools
        ]

    def _build_initial_input(
        self,
        request: ModelRequest,
    ) -> list[dict[str, Any]]:
        inputs: list[dict[str, Any]] = []

        for message in request.messages:
            if message.role == MessageRole.USER:
                inputs.append(
                    {
                        "type": "user_input",
                        "content": [
                            {
                                "type": "text",
                                "text": message.content,
                            }
                        ],
                    }
                )
            elif message.role == MessageRole.ASSISTANT:
                if message.tool_calls:
                    continue

                inputs.append(
                    {
                        "type": "model_output",
                        "content": [
                            {
                                "type": "text",
                                "text": message.content,
                            }
                        ],
                    }
                )

        if not inputs:
            raise ModelRequestError(
                "Gemini request requires at least one user message."
            )

        return inputs

    def _build_tool_result_input(
        self,
        request: ModelRequest,
    ) -> list[dict[str, Any]]:
        messages = request.messages

        latest_tool_call_index = None

        for index in range(len(messages) - 1, -1, -1):
            message = messages[index]

            if message.role == MessageRole.ASSISTANT and message.tool_calls:
                latest_tool_call_index = index
                break

        if latest_tool_call_index is None:
            raise ModelRequestError(
                "Gemini continuation requires a preceding assistant tool call."
            )

        results: list[dict[str, Any]] = []

        for message in messages[latest_tool_call_index + 1:]:
            if message.role != MessageRole.TOOL:
                continue

            if message.tool_result is None:
                continue

            result = message.tool_result

            if result.success:
                output = result.output
            else:
                output = {
                    "error": result.error or "Tool execution failed."
                }

            if isinstance(output, str):
                text = output
            else:
                text = json.dumps(output, default=str)

            results.append(
                {
                    "type": "function_result",
                    "name": result.tool_name,
                    "call_id": result.tool_call_id,
                    "result": [
                        {
                            "type": "text",
                            "text": text,
                        }
                    ],
                }
            )

        if not results:
            raise ModelRequestError(
                "Gemini continuation requires at least one tool result."
            )

        return results

    def _extract_text(self, data: dict[str, Any]) -> str:
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

                if item.get("type") != "text":
                    continue

                text = item.get("text")

                if isinstance(text, str):
                    text_parts.append(text)

        return "".join(text_parts)

    def _extract_tool_calls(
        self,
        data: dict[str, Any],
    ) -> list[ModelToolCall]:
        steps = data.get("steps")

        if not isinstance(steps, list):
            raise ModelResponseError(
                "Gemini response does not contain valid steps."
            )

        tool_calls: list[ModelToolCall] = []

        for step in steps:
            if not isinstance(step, dict):
                continue

            if step.get("type") != "function_call":
                continue

            call_id = step.get("id")
            name = step.get("name")
            arguments = step.get("arguments")

            if not isinstance(call_id, str) or not call_id.strip():
                raise ModelResponseError(
                    "Gemini function call is missing a valid ID."
                )

            if not isinstance(name, str) or not name.strip():
                raise ModelResponseError(
                    "Gemini function call is missing a valid name."
                )

            if not isinstance(arguments, dict):
                raise ModelResponseError(
                    f"Gemini function call '{name}' has invalid arguments."
                )

            tool_calls.append(
                ModelToolCall(
                    id=call_id,
                    tool_name=name,
                    arguments=arguments,
                )
            )

        return tool_calls


if __name__ == "__main__":
    raise SystemExit(
        "GeminiAdapter is a library component and is not a standalone command."
    )
