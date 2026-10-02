from core.tools.implementations.calculator import CalculatorTool
from core.tools.registry import ToolRegistry


def build_tool_registry() -> ToolRegistry:
    """Build the default ToolRegistry for Omnitrix."""

    registry = ToolRegistry()
    registry.register(CalculatorTool())

    return registry