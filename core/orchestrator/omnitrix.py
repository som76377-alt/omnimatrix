from pathlib import Path

from core.models.adapters import AdapterRegistry
from core.models.loader import ModelConfigLoader
from core.models.messages import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelToolResult,
)
from core.models.types import ModelToolDefinition
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
        max_tool_iterations: int = 8,
    ) -> None:
        if isinstance(max_tool_iterations, bool) or not isinstance(
            max_tool_iterations, int
        ):
            raise TypeError("max_tool_iterations must be an integer.")

        if max_tool_iterations <= 0:
            raise ValueError("max_tool_iterations must be positive.")

        self.registry = registry
        self.analyzer = analyzer or BasicTaskAnalyzer()
        self.router = ModelRouter(registry)
        self.adapter_registry = adapter_registry or AdapterRegistry()

        self.tool_registry = tool_registry or ToolRegistry()
        self.tool_permission = tool_permission or ToolPermission.from_capabilities(
            set()
        )
        self.max_tool_iterations = max_tool_iterations
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

        request = ModelRequest(
            messages=(
                ModelMessage(
                    role=MessageRole.USER,
                    content=task.objective,
                ),
            ),
            tools=self._get_authorized_model_tools(),
        )

        tool_iterations = 0

        while True:
            response = adapter.generate(request)

            if not response.tool_calls:
                task.complete()
                return response.content

            tool_iterations += 1

            if tool_iterations > self.max_tool_iterations:
                task.fail()
                raise RuntimeError(
                    "Maximum tool-call iterations exceeded."
                )

            assistant_message = ModelMessage(
                role=MessageRole.ASSISTANT,
                content=response.content,
                tool_calls=response.tool_calls,
            )

            tool_messages = []

            for tool_call in response.tool_calls:
                tool_result = self.execute_tool(
                    ToolRequest(
                        tool_name=tool_call.tool_name,
                        arguments=tool_call.arguments,
                    )
                )

                tool_messages.append(
                    ModelMessage(
                        role=MessageRole.TOOL,
                        tool_result=ModelToolResult(
                            tool_call_id=tool_call.id,
                            tool_name=tool_call.tool_name,
                            success=tool_result.success,
                            output=tool_result.output,
                            error=tool_result.error,
                        ),
                    )
                )

            request = ModelRequest(
                messages=(
                    request.messages
                    + (assistant_message,)
                    + tuple(tool_messages)
                ),
                tools=request.tools,
            )

    def _get_authorized_model_tools(self) -> tuple[ModelToolDefinition, ...]:
        """Return model-visible tools permitted by the current execution context."""

        tools: list[ModelToolDefinition] = []

        for tool in self.tool_registry.list():
            if not self.tool_permission.allows(tool.capabilities):
                continue

            tools.append(
                ModelToolDefinition(
                    name=tool.name,
                    description=tool.description,
                    parameters_schema=tool.parameters_schema,
                )
            )

        return tuple(tools)

    def execute_tool(self, request: ToolRequest) -> ToolResult:
        """Execute a tool request against the configured permissions."""

        return self.tool_executor.execute(request, self.tool_permission)
