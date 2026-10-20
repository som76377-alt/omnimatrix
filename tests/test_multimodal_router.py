"""Offline tests for multimodal routing and context-preserving failover."""
import unittest
from core.multimodal.router import (
    EvidenceItem, FailureKind, TaskRequest, TaskResult, WorkerCapability, classify_provider_failure,
    WorkerRegistry, WorkerSpec, route_with_failover,
)

def route_packet(task):
    from core.multimodal.router import HandoffPacket
    return HandoffPacket(task.task_id, task.user_request, task.source_name, task.source_type,
                         dict(task.payload), remaining_capabilities=task.required_capabilities)


class MultimodalRouterTests(unittest.TestCase):
    def test_provider_failure_classifier_recognizes_quota_and_auth(self):
        class ProviderError(Exception):
            def __init__(self, message, status_code):
                super().__init__(message)
                self.status_code = status_code
        self.assertEqual(classify_provider_failure(ProviderError("busy", 429)), FailureKind.QUOTA)
        self.assertEqual(classify_provider_failure(ProviderError("no", 401)), FailureKind.AUTH)
        self.assertEqual(classify_provider_failure(TimeoutError()), FailureKind.TIMEOUT)
        self.assertEqual(classify_provider_failure(ProviderError("secret upstream payload", 503)),
                         FailureKind.TRANSIENT)

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

    def test_toolchain_status_never_exposes_secret_values_or_fake_health(self):
        import os
        from unittest.mock import patch
        from core.multimodal.adapters import toolchain_status
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "test-secret-value",
            "OPENROUTER_API_KEY": "another-test-secret",
        }):
            status = toolchain_status()
        serialized = str(status)
        self.assertNotIn("test-secret-value", serialized)
        self.assertNotIn("another-test-secret", serialized)
        self.assertTrue(status["gemini"]["configured"])
        self.assertFalse(status["gemini"]["runtime_health_checked"])
        self.assertFalse(status["qwen3_omni"]["available"])
        self.assertFalse(status["qwen3_vl"]["adapter_implemented"])

    def test_provider_registry_only_advertises_explicit_capabilities(self):
        from core.multimodal.providers import build_provider_registry
        registry = build_provider_registry()
        specs = registry.describe()
        by_id = {item["worker_id"]: item for item in specs}
        self.assertIn("image_understanding", by_id["gemini.multimodal"]["capabilities"])
        self.assertIn("text_reasoning", by_id["openrouter.text"]["capabilities"])
        self.assertNotIn("image_understanding", by_id["openrouter.text"]["capabilities"])

    def test_execute_provider_task_reports_missing_keys_without_network(self):
        import os
        from unittest.mock import patch
        from core.multimodal.execute import execute_provider_task
        task = TaskRequest("Explain this text", (WorkerCapability.TEXT_REASONING,))
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "OPENROUTER_API_KEY": ""}):
            result, packet = execute_provider_task(task)
        self.assertFalse(result.success)
        self.assertEqual(result.failure_kind, FailureKind.DEPENDENCY_MISSING)
        self.assertEqual(packet.attempted_workers, ())

    def test_openrouter_worker_parses_response_with_mocked_transport(self):
        import io
        import json
        import os
        from unittest.mock import patch
        from core.multimodal.providers import openrouter_text_worker
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, limit=-1):
                return json.dumps({"choices":[{"message":{"content":"Grounded answer."}}]}).encode()
        task = TaskRequest("Explain", (WorkerCapability.TEXT_REASONING,))
        handoff = route_packet(task)
        with patch.dict(os.environ, {"OPENROUTER_API_KEY":"test-only-not-a-real-key"}):
            with patch("core.multimodal.providers.urlopen", return_value=Response()):
                result = openrouter_text_worker(task, handoff)
        self.assertTrue(result.success)
        self.assertEqual(result.evidence[0].content, "Grounded answer.")
        self.assertEqual(result.model_id, "openrouter/free")

if __name__ == "__main__":
    unittest.main()
