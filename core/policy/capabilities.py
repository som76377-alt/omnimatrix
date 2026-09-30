from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilitySet:
    """
    Defines what an Omnitrix component is allowed to do.

    Capabilities are intentionally explicit. An empty set means
    no external actions are permitted.
    """

    permissions: frozenset[str] = field(default_factory=frozenset)

    def allows(self, permission: str) -> bool:
        return permission in self.permissions
