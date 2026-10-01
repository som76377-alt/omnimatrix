from pathlib import Path

from core.models.adapters import AdapterRegistry
from core.models.loader import ModelConfigLoader
from core.models.registry import ModelRegistry
from core.models.providers.bootstrap import build_adapter_registry
from core.orchestrator.analyzer import BasicTaskAnalyzer, TaskAnalyzer
from core.orchestrator.task import Task
from core.router import ModelRouter


class Omnitrix:
    """
    Central orchestration authority.

    Omnitrix analyzes a task, routes it to an appropriate registered model,
    and executes the task through its registered adapter.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        analyzer: TaskAnalyzer | None = None,
        adapter_registry: AdapterRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.analyzer = analyzer or BasicTaskAnalyzer()
        self.router = ModelRouter(registry)
        self.adapter_registry = adapter_registry or AdapterRegistry()

    @classmethod
    def from_config(
        cls,
        config_path: str | Path,
        analyzer: TaskAnalyzer | None = None,
        adapter_registry: AdapterRegistry | None = None,
    ) -> "Omnitrix":
        """Create an Omnitrix instance from a model configuration file."""

        registry = ModelConfigLoader().load(config_path)

        if adapter_registry is None:
            adapter_registry = build_adapter_registry(registry)
        return cls(
            registry=registry,
            analyzer=analyzer,
            adapter_registry=adapter_registry,
        )

    def run(self, objective: str) -> str:
        task = Task(
            objective=objective,
            requirements=self.analyzer.analyze(objective),
        )
        task.start()

        selected_model = self.router.select(task.requirements)

        try:
            adapter = self.adapter_registry.get(selected_model.name)
        except KeyError:
            task.fail()
            raise LookupError(
                f"No adapter registered for model: {selected_model.name}"
            ) from None

        response = adapter.generate(task.objective)

        task.complete()
        return response.content