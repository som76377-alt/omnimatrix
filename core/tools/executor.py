from core.tools.base import ToolResult
from core.tools.permissions import ToolPermission
from core.tools.registry import ToolRegistry
from core.tools.request import ToolRequest
from core.tools.schema import validate_json_schema


class ToolExecutor:
    """Authorizes and validates registered tool requests before execution."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(
        self,
        request: ToolRequest,
        permission: ToolPermission,
    ) -> ToolResult:
        """Fail closed on permission or schema errors before calling a tool."""

        tool = self.registry.get(request.tool_name)

        if not permission.allows(tool.capabilities):
            return ToolResult(
                success=False,
                error=f"Permission denied for tool: {request.tool_name}",
            )

        try:
            errors = validate_json_schema(request.arguments, tool.parameters_schema)
        except (TypeError, ValueError) as exc:
            return ToolResult(
                success=False,
                error=f"Invalid tool schema for {request.tool_name}: {exc}",
            )

        if errors:
            return ToolResult(
                success=False,
                error=f"Invalid arguments for tool {request.tool_name}: " + "; ".join(errors),
            )

        return tool.execute(**request.arguments)
