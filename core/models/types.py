from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelToolCall:
    """A normalized request from a model to use an Omnitrix tool."""

    id: str
    tool_name: str
    arguments: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Tool call ID cannot be empty.")

        if not self.tool_name.strip():
            raise ValueError("Tool name cannot be empty.")

        if not isinstance(self.arguments, dict):
            raise TypeError("Tool arguments must be a dictionary.")