from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """Normalized result returned by every tool."""

    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class ToolExecutionError(RuntimeError):
    """Base error raised when a tool cannot execute."""


class Tool(ABC):
    """Provider-independent interface for tool execution."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique tool identifier."""
        raise NotImplementedError

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a human-readable description of the tool."""
        raise NotImplementedError

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[str]:
        """Return the capabilities required to use this tool."""
        raise NotImplementedError

    @property
    @abstractmethod
    def parameters_schema(self) -> dict[str, Any]:
        """Return the JSON-schema-like parameter definition for this tool."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the supplied arguments."""
        raise NotImplementedError