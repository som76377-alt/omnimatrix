from core.tools.base import Tool


class ToolRegistry:
    """Stores and retrieves tools available to Omnitrix."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool by its unique name."""

        if not tool.name.strip():
            raise ValueError("Tool name cannot be empty.")

        if tool.name in self._tools:
            raise ValueError(
                f"Tool already registered: {tool.name}"
            )

        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """Return a registered tool by name."""

        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown tool: {name}"
            ) from exc

    def has(self, name: str) -> bool:
        """Return whether a tool is registered."""

        return name in self._tools

    def list(self) -> list[Tool]:
        """Return all registered tools."""

        return list(self._tools.values())