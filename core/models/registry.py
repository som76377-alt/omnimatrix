from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelDefinition:
    """
    Static description of a model known to Omnitrix.

    This does not communicate with the model.
    It describes what the model is and what it can do.
    """

    name: str
    provider: str
    model_id: str | None = None
    capabilities: frozenset[str] = field(default_factory=frozenset)
    context_window: int | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


class ModelRegistry:
    """Stores and retrieves models known to Omnitrix."""

    def __init__(self) -> None:
        self._models: dict[str, ModelDefinition] = {}

    def register(self, model: ModelDefinition) -> None:
        if model.name in self._models:
            raise ValueError(f"Model already registered: {model.name}")

        self._models[model.name] = model

    def get(self, name: str) -> ModelDefinition:
        try:
            return self._models[name]
        except KeyError as exc:
            raise KeyError(f"Unknown model: {name}") from exc

    def list_enabled(self) -> list[ModelDefinition]:
        return [
            model
            for model in self._models.values()
            if model.enabled
        ]

    def find_capable(self, capability: str) -> list[ModelDefinition]:
        return [
            model
            for model in self.list_enabled()
            if model.supports(capability)
        ]
