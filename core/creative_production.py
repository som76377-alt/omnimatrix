"""Small, deterministic coordination ledger for creative jobs.

This module is deliberately model-agnostic: it records ownership and dependencies
but does not claim that agents ran or that an artifact passed visual QA.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from typing import Any


class ProductionContractError(ValueError):
    """Raised when a production task violates ownership or dependency rules."""


@dataclass(frozen=True)
class ProductionArtifact:
    artifact_id: str
    kind: str
    owner_task_id: str
    uri: str | None = None
    sha256: str | None = None
    source_url: str | None = None
    license_name: str | None = None
    verified: bool = False


@dataclass
class ProductionTask:
    task_id: str
    role: str
    title: str
    depends_on: list[str] = field(default_factory=list)
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    status: str = "pending"
    evidence: list[str] = field(default_factory=list)
    failure: str | None = None


class CreativeProductionManifest:
    """Versioned single source of truth with exclusive write ownership."""

    schema_version = 1
    VALID_STATES = frozenset({"pending", "ready", "running", "succeeded", "failed", "blocked"})

    def __init__(self, job_id: str, objective: str, *, output_path: str | Path | None = None):
        if not isinstance(job_id, str) or not job_id.strip() or len(job_id) > 120:
            raise ProductionContractError("job_id must be non-empty text up to 120 characters.")
        if not isinstance(objective, str) or not objective.strip() or len(objective) > 4000:
            raise ProductionContractError("objective must be non-empty text up to 4000 characters.")
        self.job_id = job_id.strip()
        self.objective = objective.strip()
        self.output_path = Path(output_path).expanduser() if output_path else None
        self.tasks: dict[str, ProductionTask] = {}
        self.artifacts: dict[str, ProductionArtifact] = {}
        self.revision = 0
        self._lock = threading.RLock()

    def add_task(
        self, task_id: str, role: str, title: str, *,
        depends_on: list[str] | None = None,
        reads: list[str] | None = None,
        writes: list[str] | None = None,
    ) -> ProductionTask:
        with self._lock:
            for name, value, maximum in (
                ("task_id", task_id, 120), ("role", role, 80), ("title", title, 300)
            ):
                if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                    raise ProductionContractError(f"{name} must be non-empty text up to {maximum} characters.")
            if task_id in self.tasks:
                raise ProductionContractError(f"Task already exists: {task_id}")
            dependencies = list(dict.fromkeys(depends_on or []))
            input_ids = list(dict.fromkeys(reads or []))
            output_ids = list(dict.fromkeys(writes or []))
            if task_id in dependencies or any(dep not in self.tasks for dep in dependencies):
                raise ProductionContractError("Dependencies must refer to previously registered tasks and cannot include this task.")
            if any(item not in self.artifacts for item in input_ids):
                raise ProductionContractError("Every read artifact must already exist in the manifest.")
            if set(input_ids) & set(output_ids):
                raise ProductionContractError("A task cannot read and write the same artifact in one operation.")
            if any(item in self.artifacts for item in output_ids):
                raise ProductionContractError("An artifact ID may have only one writer; reuse its ID instead of recreating it.")
            task = ProductionTask(task_id, role.strip(), title.strip(), dependencies, input_ids, output_ids)
            self.tasks[task_id] = task
            for artifact_id in output_ids:
                self.artifacts[artifact_id] = ProductionArtifact(
                    artifact_id=artifact_id, kind="untyped", owner_task_id=task_id
                )
            self._refresh_ready_states()
            self.revision += 1
            self._persist()
            return task

    def register_artifact(
        self, artifact_id: str, *, kind: str, owner_task_id: str,
        uri: str | None = None, sha256: str | None = None,
        source_url: str | None = None, license_name: str | None = None,
        verified: bool = False,
    ) -> ProductionArtifact:
        with self._lock:
            task = self.tasks.get(owner_task_id)
            if task is None:
                raise ProductionContractError("Artifact owner task does not exist.")
            if artifact_id not in task.writes:
                raise ProductionContractError("Only the assigned task may register this output artifact.")
            old = self.artifacts[artifact_id]
            if old.owner_task_id != owner_task_id:
                raise ProductionContractError("Artifact write ownership cannot be transferred implicitly.")
            if not isinstance(kind, str) or not kind.strip() or len(kind) > 80:
                raise ProductionContractError("Artifact kind must be non-empty text up to 80 characters.")
            if sha256 is not None and (len(sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in sha256)):
                raise ProductionContractError("sha256 must be a 64-character hexadecimal digest.")
            artifact = ProductionArtifact(
                artifact_id=artifact_id, kind=kind.strip(), owner_task_id=owner_task_id,
                uri=uri, sha256=sha256.lower() if sha256 else None,
                source_url=source_url, license_name=license_name, verified=bool(verified),
            )
            self.artifacts[artifact_id] = artifact
            self.revision += 1
            self._persist()
            return artifact

    def set_task_state(self, task_id: str, state: str, *, evidence: list[str] | None = None, failure: str | None = None) -> ProductionTask:
        with self._lock:
            task = self.tasks.get(task_id)
            if task is None:
                raise ProductionContractError("Unknown task.")
            if state not in self.VALID_STATES:
                raise ProductionContractError("Unsupported task state.")
            allowed = {
                "pending": {"ready", "blocked", "failed"},
                "ready": {"running", "blocked", "failed"},
                "running": {"succeeded", "failed", "blocked"},
                "failed": {"ready", "blocked"},
                "blocked": {"ready", "failed"},
                "succeeded": set(),
            }
            if state != task.status and state not in allowed[task.status]:
                raise ProductionContractError(f"Invalid task transition: {task.status} -> {state}.")
            if state == "running" and any(self.tasks[dep].status != "succeeded" for dep in task.depends_on):
                raise ProductionContractError("A task cannot run until every dependency succeeds.")
            if state == "succeeded":
                if any(self.tasks[dep].status != "succeeded" for dep in task.depends_on):
                    raise ProductionContractError("A task cannot succeed until every dependency succeeds.")
                if task.status != "running":
                    raise ProductionContractError("A task must be running before it can succeed.")
                missing = [artifact_id for artifact_id in task.writes if not self.artifacts[artifact_id].uri]
                if missing:
                    raise ProductionContractError("A task cannot succeed without a URI for each output artifact.")
                if not evidence:
                    raise ProductionContractError("A task cannot succeed without concrete evidence.")
            task.status = state
            task.evidence = list(evidence or [])
            task.failure = failure[:500] if isinstance(failure, str) else None
            self._refresh_ready_states()
            self.revision += 1
            self._persist()
            return task

    def _refresh_ready_states(self) -> None:
        for task in self.tasks.values():
            if task.status == "pending" and all(self.tasks[dep].status == "succeeded" for dep in task.depends_on):
                task.status = "ready"

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": self.schema_version,
                "job_id": self.job_id,
                "objective": self.objective,
                "revision": self.revision,
                "tasks": [asdict(task) for task in self.tasks.values()],
                "artifacts": [asdict(artifact) for artifact in self.artifacts.values()],
            }

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _persist(self) -> None:
        if self.output_path is None:
            return
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        fd, temporary = tempfile.mkstemp(prefix=".production-", suffix=".tmp", dir=str(self.output_path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.output_path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
