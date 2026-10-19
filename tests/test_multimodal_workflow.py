"""Tests for the Studio single-attachment coordinator integration."""
import unittest
from unittest.mock import patch

from core.multimodal.router import EvidenceItem, FailureKind, TaskResult
from core.multimodal.workflow import analyze_single_attachment


class SingleAttachmentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "id": "a" * 32, "name": "diagram.png", "mime_type": "image/png",
            "path": "/private/staged/diagram.png", "size": 12,
        }

    def test_success_returns_grounded_worker_identity_and_context(self):
        evidence = EvidenceItem("diagram.png", "image/png", "A coil is visible.",
                                "gemini.multimodal", "gemini-test")
        with patch("core.multimodal.workflow.execute_provider_task",
                   return_value=(TaskResult(True, "gemini.multimodal", "gemini-test",
                                            evidence=(evidence,)), None)) as execute:
            result = analyze_single_attachment(self.record, "Describe it")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["analyzed"], 1)
        self.assertIn("A coil is visible", result["context"])
        self.assertIn("gemini-test", result["context"])
        task = execute.call_args.args[0]
        self.assertEqual(task.payload["path"], self.record["path"])
        self.assertIn("image_understanding", [item.value for item in task.required_capabilities])

    def test_missing_worker_does_not_claim_to_have_seen_media(self):
        failure = TaskResult(False, "coordinator", "none", failure_kind=FailureKind.DEPENDENCY_MISSING,
                             safe_message="No enabled worker has the required capabilities.")
        with patch("core.multimodal.workflow.execute_provider_task", return_value=(failure, None)):
            result = analyze_single_attachment(self.record, "Describe it")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["analyzed"], 0)
        self.assertIn("was not analyzed", result["context"])
        self.assertIn("Do not claim", result["context"])

    def test_pdf_requests_allow_compatible_document_fallback(self):
        record = dict(self.record, name="notes.pdf", mime_type="application/pdf")
        with patch("core.multimodal.workflow.execute_provider_task") as execute:
            execute.return_value = (TaskResult(False, "coordinator", "none",
                failure_kind=FailureKind.DEPENDENCY_MISSING,
                safe_message="No compatible worker."), None)
            analyze_single_attachment(record, "Summarize")
        task = execute.call_args.args[0]
        self.assertEqual([item.value for item in task.required_capabilities], ["pdf_extraction"])

    def test_unknown_image_subtype_is_still_routed_as_image(self):
        record = dict(self.record, mime_type="image/tiff")
        with patch("core.multimodal.workflow.execute_provider_task") as execute:
            execute.return_value = (TaskResult(False, "coordinator", "none",
                failure_kind=FailureKind.DEPENDENCY_MISSING,
                safe_message="No compatible worker."), None)
            analyze_single_attachment(record, "Describe it")
        task = execute.call_args.args[0]
        self.assertEqual([item.value for item in task.required_capabilities], ["image_understanding"])


if __name__ == "__main__":
    unittest.main()
