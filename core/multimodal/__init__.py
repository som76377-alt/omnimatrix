"""Optional coordinated multimodal worker layer for Omnitrix."""
from core.multimodal.router import (
    EvidenceItem, FailureKind, HandoffPacket, TaskRequest, TaskResult,
    WorkerCapability, WorkerRegistry, WorkerSpec, classify_provider_failure, route_with_failover,
)
__all__ = [
    "EvidenceItem", "FailureKind", "HandoffPacket", "TaskRequest", "TaskResult",
    "WorkerCapability", "WorkerRegistry", "WorkerSpec", "classify_provider_failure", "route_with_failover",
]
