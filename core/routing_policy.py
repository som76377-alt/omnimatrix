from abc import ABC, abstractmethod

from core.models.registry import ModelDefinition


class RoutingPolicy(ABC):
    """Chooses one model from an already-filtered candidate set."""

    @abstractmethod
    def select(self, candidates: list[ModelDefinition]) -> ModelDefinition:
        raise NotImplementedError


class FirstCandidatePolicy(RoutingPolicy):
    """Deterministically selects the first eligible candidate."""

    def select(self, candidates: list[ModelDefinition]) -> ModelDefinition:
        if not candidates:
            raise LookupError("Cannot select a model from an empty candidate set.")

        return candidates[0]
