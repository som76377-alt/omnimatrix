from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from core.models.messages import ModelRequest
from core.models.types import ModelContinuation, ModelToolCall


@dataclass(frozen=True)
class ModelResponse:
    """Normalized response returned by every model adapter."""

    content: str
    model: str
    provider: str
    usage: dict[str, Any] | None = None
    tool_calls: tuple[ModelToolCall, ...] = ()
    continuation: ModelContinuation | None = None


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

    def supports_model_id(self, model_id: str) -> bool:
        """Return whether this adapter can serve a provider-reported model ID.

        Adapters whose configured name differs from the provider model ID should
        override this method. Recovery inspection uses it without making a call.
        """
        return isinstance(model_id, str) and model_id == self.name

    def supports_continuation(self, continuation: ModelContinuation) -> bool:
        """Fail closed unless an adapter explicitly validates its state format."""
        return False

    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a normalized response from the model."""
        raise NotImplementedError
