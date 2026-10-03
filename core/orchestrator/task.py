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
        self._require_status(TaskStatus.PENDING)
        self.status = TaskStatus.RUNNING

    def complete(self) -> None:
        self._require_status(TaskStatus.RUNNING)
        self.status = TaskStatus.COMPLETED

    def fail(self) -> None:
        self._require_status(TaskStatus.RUNNING)
        self.status = TaskStatus.FAILED

    def _require_status(self, expected: TaskStatus) -> None:
        if self.status != expected:
            raise RuntimeError(
                f"Cannot transition task from {self.status.value} "
                f"to the requested state."
            )
