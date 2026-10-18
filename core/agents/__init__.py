"""Configurable specialist-agent layer for Omnitrix.

Specialist roles are policies over registered model adapters, not claims that
each role has a separate model/provider behind it.
"""

from core.agents.registry import AgentDefinition, AgentRegistry
from core.agents.router import AgentPlan, AgentRouter

__all__ = ["AgentDefinition", "AgentRegistry", "AgentPlan", "AgentRouter"]
