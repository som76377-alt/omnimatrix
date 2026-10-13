from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolRequest:
    """Describes a requested tool execution and its optional durable identity."""

    tool_name: str
    arguments: dict[str, Any]
    run_id: str | None = None
    task_id: str | None = None
    attempt_id: str | None = None
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("Tool name cannot be empty.")

        if not isinstance(self.arguments, dict):
            raise TypeError("Tool arguments must be a dictionary.")

        context = (self.run_id, self.task_id, self.attempt_id)
        if any(value is not None for value in context):
            if any(not isinstance(value, str) or not value.strip() for value in context):
                raise ValueError(
                    "run_id, task_id, and attempt_id must be provided together."
                )

        if self.idempotency_key is not None and (
            not isinstance(self.idempotency_key, str) or not self.idempotency_key.strip()
        ):
            raise ValueError("idempotency_key must be a non-empty string when provided.")
