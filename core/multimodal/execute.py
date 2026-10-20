"""Convenience entry point for executing a task against configured provider adapters."""
from __future__ import annotations
import os
import shutil
from typing import Iterable
from core.multimodal.router import EvidenceItem, TaskRequest, TaskResult, HandoffPacket, route_with_failover
from core.multimodal.providers import build_provider_registry
from core.multimodal.journal import record_task_outcome


def execute_provider_task(
    task: TaskRequest, *,
    prior_evidence: Iterable[EvidenceItem] = (),
    completed_steps: Iterable[str] = (),
    privacy_tier: str | None = None,
) -> tuple[TaskResult, HandoffPacket]:
    """Run a bounded provider task using only credentials present server-side."""
    available_keys = [name for name in ("GEMINI_API_KEY", "OPENROUTER_API_KEY")
                      if os.environ.get(name, "").strip()]
    executables = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name)]
    result, packet = route_with_failover(
        task, build_provider_registry(), available_keys=available_keys,
        available_executables=executables, prior_evidence=prior_evidence,
        completed_steps=completed_steps, privacy_tier=privacy_tier,
    )
    record_task_outcome(task, result, packet)
    return result, packet
