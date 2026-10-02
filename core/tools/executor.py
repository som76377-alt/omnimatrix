from core.tools.base import ToolResult
from core.tools.permissions import ToolPermission
from core.tools.registry import ToolRegistry
from core.tools.request import ToolRequest


class ToolExecutor:
    """Authorizes and executes registered tools."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(
        self,
        request: ToolRequest,
        permission: ToolPermission,
    ) -> ToolResult:
        """Execute a tool request if its capabilities are permitted."""

        tool = self.registry.get(request.tool_name)

        if not permission.allows(tool.capabilities):
            return ToolResult(
                success=False,
                error=(
                    f"Permission denied for tool: "
                    f"{request.tool_name}"
                ),
            )

        return tool.execute(**request.arguments)