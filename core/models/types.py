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


@dataclass(frozen=True)
class ModelToolDefinition:
    """Provider-neutral description of a tool a model may call."""

    name: str
    description: str
    parameters_schema: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Tool definition name cannot be empty.")

        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Tool definition description cannot be empty.")

        if not isinstance(self.parameters_schema, dict):
            raise TypeError("Tool definition parameters_schema must be a dictionary.")
