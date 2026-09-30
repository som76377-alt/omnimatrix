from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ModelResponse:
    content: str
    model: str
    provider: str
    usage: dict[str, Any] | None = None


class ModelAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique model identifier."""
        raise NotImplementedError

    @property
    @abstractmethod
    def provider(self) -> str:
        """Return the model provider."""
        raise NotImplementedError

    @abstractmethod
    def generate(self, prompt: str) -> ModelResponse:
        """Generate a response from the model."""
        raise NotImplementedError
