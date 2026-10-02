from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ToolPermission:
    """Capabilities an execution context is allowed to use."""

    capabilities: frozenset[str]

    @classmethod
    def from_capabilities(
        cls,
        capabilities: Iterable[str],
    ) -> "ToolPermission":
        normalized = frozenset(capability.strip() for capability in capabilities)

        if "" in normalized:
            raise ValueError("Capabilities cannot contain empty values.")

        return cls(capabilities=normalized)

    def allows(self, required_capabilities: frozenset[str]) -> bool:
        """Return whether all required capabilities are permitted."""

        return required_capabilities.issubset(self.capabilities)