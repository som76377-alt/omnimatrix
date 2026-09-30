from dataclasses import dataclass, field

from core.models.registry import ModelDefinition, ModelRegistry


@dataclass(frozen=True)
class RoutingRequirements:
    """Requirements a model must satisfy for a task."""

    capabilities: frozenset[str] = field(default_factory=frozenset)
    minimum_context_window: int | None = None


class ModelRouter:
    """Selects an eligible model from the model registry."""

    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def select(self, requirements: RoutingRequirements) -> ModelDefinition:
        candidates = self.registry.list_enabled()

        candidates = [
            model
            for model in candidates
            if requirements.capabilities.issubset(model.capabilities)
        ]

        if requirements.minimum_context_window is not None:
            candidates = [
                model
                for model in candidates
                if (
                    model.context_window is not None
                    and model.context_window
                    >= requirements.minimum_context_window
                )
            ]

        if not candidates:
            raise LookupError(
                "No registered model satisfies the routing requirements."
            )

        return candidates[0]
