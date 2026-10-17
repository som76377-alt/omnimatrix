from pathlib import Path

from core.tools.implementations.calculator import CalculatorTool
from core.tools.implementations.workspace_inspect import WorkspaceInspectTool
from core.tools.registry import ToolRegistry


def build_tool_registry(
    workspace_root: str | Path | None = None,
) -> ToolRegistry:
    """Build the default registry; workspace access still requires explicit permission."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(WorkspaceInspectTool(workspace_root))

    return registry
