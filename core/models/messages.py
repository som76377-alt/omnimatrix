from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.models.types import ModelToolCall, ModelToolDefinition


class MessageRole(str, Enum):
    """Role of a message in a model conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class ModelToolResult:
    """Provider-neutral result of a tool execution."""

    tool_call_id: str
    tool_name: str
    success: bool
    output: Any = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.tool_call_id.strip():
            raise ValueError("Tool call ID cannot be empty.")

        if not self.tool_name.strip():
            raise ValueError("Tool name cannot be empty.")


@dataclass(frozen=True)
class ModelMessage:
    """A provider-neutral message exchanged with a model."""

    role: MessageRole
    content: str = ""
    tool_calls: tuple[ModelToolCall, ...] = ()
    tool_result: ModelToolResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.role, MessageRole):
            raise TypeError("Message role must be a MessageRole.")

        if not isinstance(self.content, str):
            raise TypeError("Message content must be a string.")

        if self.role == MessageRole.TOOL and self.tool_result is None:
            raise ValueError(
                "Tool messages require a tool result."
            )

        if self.tool_result is not None and self.role != MessageRole.TOOL:
            raise ValueError(
                "Tool results are only valid on tool messages."
            )


@dataclass(frozen=True)
class ModelRequest:
    """Structured input supplied to a model adapter."""

    messages: tuple[ModelMessage, ...] = field(default_factory=tuple)
    tools: tuple[ModelToolDefinition, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("Model request requires at least one message.")

        names = [tool.name for tool in self.tools]

        if len(names) != len(set(names)):
            raise ValueError(
                "Model request cannot contain duplicate tool names."
            )
