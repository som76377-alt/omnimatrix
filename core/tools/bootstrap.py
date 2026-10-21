from pathlib import Path
from typing import Iterable

from core.tools.implementations.calculator import CalculatorTool
from core.tools.implementations.cline_coding import ClineCodingTool
from core.tools.implementations.manim_renderer import ManimRendererTool
from core.tools.implementations.workspace_inspect import (
    WorkspaceInspectTool,
    supports_secure_workspace_inspection,
)
from core.tools.registry import ToolRegistry


def build_tool_registry(
    workspace_root: str | Path | None = None,
    allowed_paths: Iterable[str] | None = None,
    enable_cline: bool = False,
) -> ToolRegistry:
    """Build the default registry; workspace access still requires explicit permission."""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    # The renderer accepts structured diagram data only; it never executes model-written code.
    # Execution reports an explicit unavailable status when Manim is absent from this host.
    registry.register(ManimRendererTool())
    if enable_cline:
        if workspace_root is None:
            raise ValueError("Cline coding requires an explicit workspace_root.")
        registry.register(ClineCodingTool(workspace_root))
    if workspace_root is not None or allowed_paths is not None or supports_secure_workspace_inspection():
        registry.register(WorkspaceInspectTool(workspace_root, allowed_paths=allowed_paths))

    return registry
