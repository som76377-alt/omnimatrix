from dataclasses import dataclass
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class ToolRequest:
    """Describes a requested tool execution and its optional durable identity."""

    tool_name: str
    arguments: dict[str, Any]
    run_id: str | None = None
    task_id: str | None = None
    attempt_id: str | None = None
    idempotency_key: str | None = None
    logical_action_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("Tool name cannot be empty.")

        if not isinstance(self.arguments, dict):
            raise TypeError("Tool arguments must be a dictionary.")

        if (self.run_id is None) != (self.task_id is None):
            raise ValueError("run_id and task_id must be provided together.")
        if self.run_id is not None:
            for name, value in (("run_id", self.run_id), ("task_id", self.task_id)):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{name} must be a non-empty string.")
        if self.attempt_id is not None:
            if self.run_id is None or not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
                raise ValueError("attempt_id requires run_id/task_id and must be non-empty.")
        if self.logical_action_id is not None:
            if self.run_id is None or not isinstance(self.logical_action_id, str) or not self.logical_action_id.strip():
                raise ValueError("logical_action_id requires run_id/task_id and must be non-empty.")

        if self.idempotency_key is not None and (
            not isinstance(self.idempotency_key, str) or not self.idempotency_key.strip()
        ):
            raise ValueError("idempotency_key must be a non-empty string when provided.")


def stable_tool_idempotency_key(
    run_id: str, task_id: str, logical_action_id: str
) -> str:
    """Build a deterministic key independent of attempt IDs and provider call IDs.

    The logical action identifier must be stable across attempts for the same
    task. Different arguments under the same key are rejected by ToolExecutor.
    """
    values = (run_id, task_id, logical_action_id)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("run_id, task_id, and logical_action_id must be non-empty.")
    canonical = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return "tool-action-v1:" + digest
