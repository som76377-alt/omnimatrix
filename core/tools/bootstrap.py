from pathlib import Path

from core.tools.implementations.calculator import CalculatorTool
from core.tools.implementations.workspace_inspect import (
    WorkspaceInspectTool,
    supports_secure_workspace_inspection,
)
from core.tools.registry import ToolRegistry


def build_tool_registry(
    workspace_root: str | Path | None = None,
) -> ToolRegistry:
    """Build the default registry; workspace access still requires explicit permission."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    if workspace_root is not None or supports_secure_workspace_inspection():
        registry.register(WorkspaceInspectTool(workspace_root))

    return registry
