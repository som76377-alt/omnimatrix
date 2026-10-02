from pathlib import Path

from core.models.adapters import AdapterRegistry
from core.models.loader import ModelConfigLoader
from core.models.registry import ModelRegistry
from core.models.providers.bootstrap import build_adapter_registry
from core.orchestrator.analyzer import BasicTaskAnalyzer, TaskAnalyzer
from core.orchestrator.task import Task
from core.router import ModelRouter
from core.tools.bootstrap import build_tool_registry
from core.tools.executor import ToolExecutor
from core.tools.permissions import ToolPermission
from core.tools.registry import ToolRegistry
from core.tools.base import ToolResult
from core.tools.request import ToolRequest


class Omnitrix:
    """
    Central orchestration authority.

    Omnitrix analyzes tasks, routes them to registered models,
    and controls access to registered tools.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        analyzer: TaskAnalyzer | None = None,
        adapter_registry: AdapterRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_permission: ToolPermission | None = None,
    ) -> None:
        self.registry = registry
        self.analyzer = analyzer or BasicTaskAnalyzer()
        self.router = ModelRouter(registry)
        self.adapter_registry = adapter_registry or AdapterRegistry()

        self.tool_registry = tool_registry or ToolRegistry()
        self.tool_permission = tool_permission or ToolPermission.from_capabilities(
            set()
        )
        self.tool_executor = ToolExecutor(self.tool_registry)

    @classmethod
    def from_config(
        cls,
        config_path: str | Path,
        analyzer: TaskAnalyzer | None = None,
        adapter_registry: AdapterRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_permission: ToolPermission | None = None,
    ) -> "Omnitrix":
        """Create an Omnitrix instance from a model configuration file."""

        registry = ModelConfigLoader().load(config_path)

        if adapter_registry is None:
            adapter_registry = build_adapter_registry(registry)

        if tool_registry is None:
            tool_registry = build_tool_registry()

        return cls(
            registry=registry,
            analyzer=analyzer,
            adapter_registry=adapter_registry,
            tool_registry=tool_registry,
            tool_permission=tool_permission,
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

    def execute_tool(self, request: ToolRequest) -> ToolResult:
        """Execute a tool request against the configured permissions."""

        return self.tool_executor.execute(request, self.tool_permission)
