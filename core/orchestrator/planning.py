"""Validated task plans, approval context, and dependency readiness checks."""

from dataclasses import dataclass, field
import hashlib
import json
from typing import Iterable


@dataclass(frozen=True)
class PlannedTask:
    """A single unit of work within a plan."""

    task_id: str
    description: str
    dependencies: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, str) or not self.task_id.strip():
            raise ValueError("Task ID must be a non-empty string.")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("Task description must be a non-empty string.")
        if isinstance(self.dependencies, str):
            raise ValueError("Dependencies must be an iterable of task IDs.")
        try:
            dependencies = frozenset(self.dependencies)
        except TypeError as exc:
            raise ValueError("Dependencies must be an iterable of task IDs.") from exc
        if any(not isinstance(item, str) or not item.strip() for item in dependencies):
            raise ValueError("Dependency IDs must be non-empty strings.")
        object.__setattr__(self, "dependencies", dependencies)


@dataclass(frozen=True)
class PlanExecutionContext:
    """Approval-sensitive policy and scope metadata bound to a plan fingerprint.

    This records the intended execution boundary. It is not itself an
    authorization grant; execution adapters must enforce the declared scope.
    """

    tool_scopes: frozenset[str] = field(default_factory=frozenset)
    targets: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    verification: tuple[str, ...] = ()
    policy_version: str = "1"
    spend_mode: str = "zero_cost_only"
    risk_tier: str = "read_only"
    external_data_egress: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.tool_scopes, str):
            raise ValueError("tool_scopes must be an iterable of scope IDs.")
        try:
            scopes = frozenset(self.tool_scopes)
        except TypeError as exc:
            raise ValueError("tool_scopes must be an iterable of scope IDs.") from exc
        if any(not isinstance(item, str) or not item.strip() for item in scopes):
            raise ValueError("tool_scopes must contain non-empty strings.")
        object.__setattr__(self, "tool_scopes", scopes)
        for name in ("targets", "resources", "verification"):
            value = getattr(self, name)
            if isinstance(value, str):
                raise ValueError(f"{name} must be an iterable of non-empty strings.")
            try:
                items = tuple(value)
            except TypeError as exc:
                raise ValueError(f"{name} must be an iterable of non-empty strings.") from exc
            if any(not isinstance(item, str) or not item.strip() for item in items):
                raise ValueError(f"{name} must contain non-empty strings.")
            object.__setattr__(self, name, items)
        for name in ("policy_version", "spend_mode", "risk_tier"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if self.spend_mode not in {"zero_cost_only", "user_provided_free_quota", "paid_allowed"}:
            raise ValueError("Unsupported spend_mode.")
        if not isinstance(self.external_data_egress, bool):
            raise TypeError("external_data_egress must be a boolean.")


@dataclass(frozen=True)
class TaskPlan:
    """An immutable, validated collection of planned tasks and approval context."""

    tasks: tuple[PlannedTask, ...]
    context: PlanExecutionContext = field(default_factory=PlanExecutionContext)

    def __post_init__(self) -> None:
        try:
            tasks = tuple(self.tasks)
        except TypeError as exc:
            raise ValueError("Plan tasks must be iterable.") from exc
        if any(not isinstance(task, PlannedTask) for task in tasks):
            raise ValueError("Every plan entry must be a PlannedTask.")
        if not isinstance(self.context, PlanExecutionContext):
            raise TypeError("context must be a PlanExecutionContext.")
        object.__setattr__(self, "tasks", tasks)
        self.validate()

    @classmethod
    def from_tasks(
        cls,
        tasks: Iterable[PlannedTask],
        context: PlanExecutionContext | None = None,
    ) -> "TaskPlan":
        """Build a plan from an iterable of planned tasks."""
        return cls(tasks=tasks, context=context or PlanExecutionContext())

    def validate(self) -> None:
        """Reject duplicate IDs, invalid dependencies, and dependency cycles."""
        task_by_id: dict[str, PlannedTask] = {}
        for task in self.tasks:
            if task.task_id in task_by_id:
                raise ValueError(f"Duplicate task ID: {task.task_id}")
            task_by_id[task.task_id] = task
        for task in self.tasks:
            if task.task_id in task.dependencies:
                raise ValueError(f"Task '{task.task_id}' cannot depend on itself.")
            for dependency in task.dependencies:
                if dependency not in task_by_id:
                    raise ValueError(
                        f"Task '{task.task_id}' depends on unknown task '{dependency}'."
                    )

        dependency_count = {
            task_id: len(task.dependencies) for task_id, task in task_by_id.items()
        }
        dependents: dict[str, list[str]] = {task_id: [] for task_id in task_by_id}
        for task in self.tasks:
            for dependency in task.dependencies:
                dependents[dependency].append(task.task_id)

        ready = [
            task_id for task_id, count in dependency_count.items() if count == 0
        ]
        processed = 0
        index = 0
        while index < len(ready):
            task_id = ready[index]
            index += 1
            processed += 1
            for dependent_id in dependents[task_id]:
                dependency_count[dependent_id] -= 1
                if dependency_count[dependent_id] == 0:
                    ready.append(dependent_id)
        if processed != len(task_by_id):
            raise ValueError("Task plan contains a dependency cycle.")

    def ready_tasks(self, completed_task_ids: Iterable[str] = ()) -> tuple[PlannedTask, ...]:
        """Return tasks whose dependencies are all completed, in plan order."""
        try:
            completed = frozenset(completed_task_ids)
        except TypeError as exc:
            raise ValueError("Completed task IDs must be iterable.") from exc
        if any(not isinstance(item, str) or not item.strip() for item in completed):
            raise ValueError("Completed task IDs must be non-empty strings.")
        known_ids = {task.task_id for task in self.tasks}
        unknown_completed = completed - known_ids
        if unknown_completed:
            unknown_id = sorted(unknown_completed)[0]
            raise ValueError(f"Unknown completed task ID: {unknown_id}")
        return tuple(
            task for task in self.tasks
            if task.task_id not in completed and task.dependencies.issubset(completed)
        )


def fingerprint_plan(plan: TaskPlan) -> str:
    """Hash all plan fields that currently affect intended execution scope."""
    if not isinstance(plan, TaskPlan):
        raise TypeError("plan must be a TaskPlan.")
    context = plan.context
    canonical_plan = {
        "tasks": [
            {
                "task_id": task.task_id,
                "description": task.description,
                "dependencies": sorted(task.dependencies),
            }
            for task in plan.tasks
        ],
        "context": {
            "tool_scopes": sorted(context.tool_scopes),
            "targets": list(context.targets),
            "resources": list(context.resources),
            "verification": list(context.verification),
            "policy_version": context.policy_version,
            "spend_mode": context.spend_mode,
            "risk_tier": context.risk_tier,
            "external_data_egress": context.external_data_egress,
        },
    }
    encoded = json.dumps(
        canonical_plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PlanApproval:
    """Approval record bound to a specific plan fingerprint."""

    plan: TaskPlan
    fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.plan, TaskPlan):
            raise TypeError("plan must be a TaskPlan.")
        if not isinstance(self.fingerprint, str) or not self.fingerprint:
            raise ValueError("fingerprint must be a non-empty string.")
