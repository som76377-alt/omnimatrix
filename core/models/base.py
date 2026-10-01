from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelResponse:
    """Normalized response returned by every model adapter."""

    content: str
    model: str
    provider: str
    usage: dict[str, Any] | None = None


class ModelAdapterError(RuntimeError):
    """Base error raised by a model adapter."""


class ModelAuthenticationError(ModelAdapterError):
    """Raised when model authentication fails."""


class ModelRequestError(ModelAdapterError):
    """Raised when a model request cannot be completed."""


class ModelResponseError(ModelAdapterError):
    """Raised when a provider response cannot be understood."""


class ModelAdapter(ABC):
    """Provider-independent interface for model execution."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique model identifier."""
        raise NotImplementedError

    @property
    @abstractmethod
    def provider(self) -> str:
        """Return the model provider identifier."""
        raise NotImplementedError

    @abstractmethod
    def generate(self, prompt: str) -> ModelResponse:
        """Generate a normalized response from the model."""
        raise NotImplementedError
