from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.router import RoutingRequirements


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    objective: str
    requirements: RoutingRequirements = field(
        default_factory=RoutingRequirements
    )
    status: TaskStatus = TaskStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        self.status = TaskStatus.RUNNING

    def complete(self) -> None:
        self.status = TaskStatus.COMPLETED

    def fail(self) -> None:
        self.status = TaskStatus.FAILED