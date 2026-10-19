"""Offline tests for multimodal routing and context-preserving failover."""
import unittest
from core.multimodal.router import (
    EvidenceItem, FailureKind, TaskRequest, TaskResult, WorkerCapability,
    WorkerRegistry, WorkerSpec, route_with_failover,
)

class MultimodalRouterTests(unittest.TestCase):
    def test_quota_failover_preserves_evidence_and_progress(self):
        registry = WorkerRegistry()
        cap = WorkerCapability.IMAGE_UNDERSTANDING
        evidence = EvidenceItem("diagram.png", "image", "OCR: coil", "ocr", "paddleocr")
        def quota(task, packet):
            return TaskResult(False, "provider-a", "model-a", evidence=(evidence,),
                completed_steps=("ocr_complete",), failure_kind=FailureKind.QUOTA,
                safe_message="Provider quota reached.")
        def backup(task, packet):
            self.assertEqual(packet.task_id, task.task_id)
            self.assertEqual(packet.evidence[0].content, "OCR: coil")
            self.assertIn("ocr_complete", packet.completed_steps)
            self.assertEqual(packet.attempted_workers, ("provider-a",))
            return TaskResult(True, "provider-b", "model-b",
                evidence=(EvidenceItem("diagram.png", "image", "A coil is visible",
                    "provider-b", "model-b"),), completed_steps=("visual_analysis_complete",))
        registry.register(WorkerSpec("provider-a", frozenset({cap}), "model-a", priority=1), quota)
        registry.register(WorkerSpec("provider-b", frozenset({cap}), "model-b", priority=2), backup)
        task = TaskRequest("Explain the diagram", (cap,), source_name="diagram.png", source_type="image")
        result, packet = route_with_failover(task, registry)
        self.assertTrue(result.success)
        self.assertEqual(result.worker_id, "provider-b")
        self.assertEqual(len(result.evidence), 2)
        self.assertEqual(packet.attempted_workers, ("provider-a", "provider-b"))
        self.assertEqual(packet.remaining_capabilities, ())

    def test_missing_key_prevents_worker_selection(self):
        registry = WorkerRegistry()
        cap = WorkerCapability.AUDIO_TRANSCRIPTION
        registry.register(WorkerSpec("gemini", frozenset({cap}), "gemini-audio",
            requires_api_key="GEMINI_API_KEY"), lambda task, packet: self.fail("called without key"))
        result, packet = route_with_failover(TaskRequest("Transcribe", (cap,)), registry)
        self.assertFalse(result.success)
        self.assertEqual(result.failure_kind, FailureKind.DEPENDENCY_MISSING)
        self.assertEqual(packet.attempted_workers, ())

    def test_invalid_input_stops_without_retry(self):
        registry = WorkerRegistry()
        cap = WorkerCapability.PDF_EXTRACTION
        registry.register(WorkerSpec("bad-input", frozenset({cap}), "parser", priority=1),
            lambda task, packet: TaskResult(False, "bad-input", "parser",
                failure_kind=FailureKind.INVALID_INPUT, safe_message="Invalid file."))
        registry.register(WorkerSpec("backup", frozenset({cap}), "backup", priority=2),
            lambda task, packet: self.fail("must not retry invalid input"))
        result, packet = route_with_failover(TaskRequest("Read PDF", (cap,)), registry)
        self.assertFalse(result.success)
        self.assertEqual(packet.attempted_workers, ("bad-input",))

    def test_fingerprint_is_stable(self):
        task = TaskRequest("Analyze", (WorkerCapability.TEXT_REASONING,), payload={"file_id":"private-123"})
        registry = WorkerRegistry()
        _, first = route_with_failover(task, registry)
        _, second = route_with_failover(task, registry)
        self.assertEqual(first.fingerprint(), second.fingerprint())

    def test_worker_exception_is_sanitized_and_fails_over(self):
        registry = WorkerRegistry()
        cap = WorkerCapability.TEXT_REASONING
        def explode(task, packet):
            raise RuntimeError("upstream body contains fake-secret")
        registry.register(WorkerSpec("broken", frozenset({cap}), "model-1", priority=1), explode)
        registry.register(WorkerSpec("backup", frozenset({cap}), "model-2", priority=2),
            lambda task, packet: TaskResult(True, "backup", "model-2"))
        result, _ = route_with_failover(TaskRequest("Reason", (cap,)), registry)
        self.assertTrue(result.success)
        self.assertNotIn("fake-secret", result.safe_message or "")

if __name__ == "__main__":
    unittest.main()
