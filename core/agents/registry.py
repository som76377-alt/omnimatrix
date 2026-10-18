"""Configuration and validation for Omnitrix specialist roles."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_ALLOWED_ROLES = {
    "intent_engineer",
    "reasoning",
    "coding",
    "subject_solver",
    "research",
    "computation",
    "critic",
}
_ALLOWED_STAGES = {"context", "preflight", "review"}
_ALLOWED_INTENT_MODES = {"adaptive", "always", "off"}
_ALLOWED_CRITIC_MODES = {"complex_only", "always", "off"}


@dataclass(frozen=True)
class AgentDefinition:
    """A configurable role with instructions and optional model preferences."""

    name: str
    role: str
    stage: str
    purpose: str
    instructions: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    preferred_models: tuple[str, ...] = ()
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Agent name cannot be blank.")
        if self.role not in _ALLOWED_ROLES:
            raise ValueError(f"Unsupported agent role: {self.role}")
        if self.stage not in _ALLOWED_STAGES:
            raise ValueError(f"Unsupported agent stage: {self.stage}")
        if not self.purpose.strip() or not self.instructions.strip():
            raise ValueError(f"Agent '{self.name}' needs purpose and instructions.")
        if not self.capabilities:
            raise ValueError(f"Agent '{self.name}' must declare at least one capability.")
        if not all(isinstance(item, str) and item.strip() for item in self.preferred_models):
            raise ValueError(f"Agent '{self.name}' has invalid preferred_models.")


class AgentRegistry:
    """Loads role definitions without binding them to a particular model vendor."""

    def __init__(
        self,
        agents: list[AgentDefinition],
        *,
        enabled: bool = True,
        intent_mode: str = "adaptive",
        critic_mode: str = "complex_only",
    ) -> None:
        if not isinstance(enabled, bool):
            raise ValueError("Agent system enabled must be a boolean.")
        if intent_mode not in _ALLOWED_INTENT_MODES:
            raise ValueError(f"Unsupported intent_mode: {intent_mode}")
        if critic_mode not in _ALLOWED_CRITIC_MODES:
            raise ValueError(f"Unsupported critic_mode: {critic_mode}")

        self.enabled = enabled
        self.intent_mode = intent_mode
        self.critic_mode = critic_mode
        self._agents: dict[str, AgentDefinition] = {}
        roles: set[str] = set()

        for agent in agents:
            if agent.name in self._agents:
                raise ValueError(f"Duplicate agent name: {agent.name}")
            if agent.role in roles:
                raise ValueError(f"Duplicate agent role: {agent.role}")
            roles.add(agent.role)
            self._agents[agent.name] = agent

        if enabled:
            missing = _ALLOWED_ROLES.difference(roles)
            if missing:
                raise ValueError(
                    "Enabled agent configuration is missing roles: "
                    + ", ".join(sorted(missing))
                )

    @classmethod
    def load(cls, path: str | Path) -> "AgentRegistry":
        """Load an agent profile and fail clearly on malformed configuration."""
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as stream:
            payload: Any = json.load(stream)

        if not isinstance(payload, dict):
            raise ValueError("Agent configuration must be a JSON object.")
        if payload.get("schema_version") != 1:
            raise ValueError("Agent configuration schema_version must be 1.")

        enabled = payload.get("enabled", True)
        settings = payload.get("settings", {})
        entries = payload.get("agents")
        if not isinstance(settings, dict):
            raise ValueError("Agent configuration 'settings' must be an object.")
        if not isinstance(entries, list):
            raise ValueError("Agent configuration 'agents' must be a list.")

        definitions: list[AgentDefinition] = []
        for index, item in enumerate(entries):
            if not isinstance(item, dict):
                raise ValueError(f"Agent entry at index {index} must be an object.")

            name = item.get("name")
            role = item.get("role")
            stage = item.get("stage")
            purpose = item.get("purpose")
            instructions = item.get("instructions")
            capabilities = item.get("capabilities", [])
            preferred_models = item.get("preferred_models", [])
            agent_enabled = item.get("enabled", True)

            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Agent entry at index {index} has an invalid name.")
            if not isinstance(role, str):
                raise ValueError(f"Agent '{name}' has an invalid role.")
            if not isinstance(stage, str):
                raise ValueError(f"Agent '{name}' has an invalid stage.")
            if not isinstance(purpose, str):
                raise ValueError(f"Agent '{name}' has an invalid purpose.")
            if not isinstance(instructions, str):
                raise ValueError(f"Agent '{name}' has invalid instructions.")
            if not isinstance(capabilities, list) or not all(
                isinstance(value, str) and value.strip() for value in capabilities
            ):
                raise ValueError(f"Agent '{name}' has invalid capabilities.")
            if not isinstance(preferred_models, list) or not all(
                isinstance(value, str) and value.strip() for value in preferred_models
            ):
                raise ValueError(f"Agent '{name}' has invalid preferred_models.")
            if not isinstance(agent_enabled, bool):
                raise ValueError(f"Agent '{name}' enabled must be a boolean.")

            definitions.append(
                AgentDefinition(
                    name=name,
                    role=role,
                    stage=stage,
                    purpose=purpose,
                    instructions=instructions,
                    capabilities=frozenset(capabilities),
                    preferred_models=tuple(preferred_models),
                    enabled=agent_enabled,
                )
            )

        return cls(
            definitions,
            enabled=enabled,
            intent_mode=settings.get("intent_mode", "adaptive"),
            critic_mode=settings.get("critic_mode", "complex_only"),
        )

    def get(self, role: str) -> AgentDefinition:
        """Get an enabled role by its stable role ID."""
        if not self.enabled:
            raise LookupError("The specialist-agent system is disabled.")
        for agent in self._agents.values():
            if agent.role == role and agent.enabled:
                return agent
        raise LookupError(f"No enabled agent is configured for role: {role}")

    def has(self, role: str) -> bool:
        if not self.enabled:
            return False
        return any(agent.role == role and agent.enabled for agent in self._agents.values())

    def list_enabled(self) -> list[AgentDefinition]:
        if not self.enabled:
            return []
        return [agent for agent in self._agents.values() if agent.enabled]
