from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolRequest:
    """Describes a requested tool execution."""

    tool_name: str
    arguments: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.tool_name.strip():
            raise ValueError("Tool name cannot be empty.")

        if not isinstance(self.arguments, dict):
            raise TypeError("Tool arguments must be a dictionary.")