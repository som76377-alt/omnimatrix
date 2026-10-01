from typing import Callable

from core.models.base import ModelAdapter
from core.models.registry import ModelDefinition


AdapterBuilder = Callable[[ModelDefinition], ModelAdapter]


class ModelAdapterFactory:
    """Creates model adapters from registered provider builders."""

    def __init__(self) -> None:
        self._builders: dict[str, AdapterBuilder] = {}

    def register(
        self,
        provider: str,
        builder: AdapterBuilder,
    ) -> None:
        """Register an adapter builder for a provider."""
        if not provider.strip():
            raise ValueError("Provider cannot be empty.")

        if provider in self._builders:
            raise ValueError(
                f"Adapter builder already registered: {provider}"
            )

        self._builders[provider] = builder

    def create(self, model: ModelDefinition) -> ModelAdapter:
        """Create an adapter for the given model definition."""
        try:
            builder = self._builders[model.provider]
        except KeyError as exc:
            raise LookupError(
                f"No adapter builder registered for provider: "
                f"{model.provider}"
            ) from exc

        return builder(model)

    def has_builder(self, provider: str) -> bool:
        """Return whether a builder is registered for a provider."""
        return provider in self._builders