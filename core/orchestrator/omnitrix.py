from pathlib import Path

from core.models.base import ModelAdapter
from core.models.loader import ModelConfigLoader
from core.models.registry import ModelRegistry
from core.orchestrator.analyzer import BasicTaskAnalyzer, TaskAnalyzer
from core.orchestrator.task import Task
from core.router import ModelRouter


class Omnitrix:
    """
    Central orchestration authority.

    Omnitrix analyzes a task, routes it to an appropriate registered model,
    and executes the task through that model.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        analyzer: TaskAnalyzer | None = None,
        adapters: dict[str, ModelAdapter] | None = None,
    ) -> None:
        self.registry = registry
        self.analyzer = analyzer or BasicTaskAnalyzer()
        self.router = ModelRouter(registry)
        self.adapters = adapters or {}

    @classmethod
    def from_config(
        cls,
        config_path: str | Path,
        analyzer: TaskAnalyzer | None = None,
        adapters: dict[str, ModelAdapter] | None = None,
    ) -> "Omnitrix":
        """Create an Omnitrix instance from a model configuration file."""

        registry = ModelConfigLoader().load(config_path)

        return cls(
            registry=registry,
            analyzer=analyzer,
            adapters=adapters,
        )

    def run(self, objective: str) -> str:
        task = Task(
            objective=objective,
            requirements=self.analyzer.analyze(objective),
        )
        task.start()

        selected_model = self.router.select(task.requirements)

        adapter = self.adapters.get(selected_model.name)

        if adapter is None:
            task.fail()
            raise LookupError(
                f"No adapter registered for model: {selected_model.name}"
            )

        response = adapter.generate(task.objective)

        task.complete()
        return response.content
