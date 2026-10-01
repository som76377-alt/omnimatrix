from core.models.base import ModelAdapter


class AdapterRegistry:
    """Stores model adapters available to Omnitrix."""

    def __init__(self) -> None:
        self._adapters: dict[str, ModelAdapter] = {}

    def register(self, adapter: ModelAdapter) -> None:
        """Register an adapter by its unique model name."""
        if adapter.name in self._adapters:
            raise ValueError(
                f"Adapter already registered: {adapter.name}"
            )

        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> ModelAdapter:
        """Return a registered adapter by model name."""
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown adapter: {name}"
            ) from exc

    def has(self, name: str) -> bool:
        """Return whether an adapter is registered."""
        return name in self._adapters

    def list(self) -> list[ModelAdapter]:
        """Return all registered adapters."""
        return list(self._adapters.values())
