import json

from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import MessageRole, ModelRequest


class DemoAdapter(ModelAdapter):
    """Offline demonstration adapter. It does not perform real model inference."""

    def __init__(self, name: str, model_id: str) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Adapter name cannot be empty.")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("Demo model_id cannot be empty.")

        self._name = name
        self._model_id = model_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider(self) -> str:
        return "demo"

    def supports_model_id(self, model_id: str) -> bool:
        return isinstance(model_id, str) and model_id == self._model_id

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not isinstance(request, ModelRequest):
            raise TypeError("request must be a ModelRequest.")

        if request.instructions and "You are the Omnitrix task planner." in request.instructions:
            payload = {
                "tasks": [
                    {
                        "task_id": "demo",
                        "description": (
                            "DEMO ONLY: Simulated task; no research or external "
                            "work was performed."
                        ),
                        "dependencies": [],
                    }
                ]
            }
            content = json.dumps(payload, ensure_ascii=False)
        else:
            user_messages = [
                message.content
                for message in request.messages
                if message.role == MessageRole.USER
            ]
            supplied_text = user_messages[-1] if user_messages else "(no user text)"

            content = (
                "[OFFLINE DEMO — simulated response; no real model inference "
                "or external work was performed]\n"
                f"Received input: {supplied_text}"
            )

        return ModelResponse(
            content=content,
            model=self._model_id,
            provider=self.provider,
            tool_calls=(),
        )
