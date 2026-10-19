"""Tests for the Studio single-attachment coordinator integration."""
import unittest
from unittest.mock import patch

from core.multimodal.router import EvidenceItem, FailureKind, TaskResult
from core.multimodal.workflow import analyze_multiple_attachments, analyze_single_attachment


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

    def test_image_uses_labelled_local_ocr_fallback_after_remote_failure(self):
        failure = TaskResult(False, "coordinator", "none",
            failure_kind=FailureKind.DEPENDENCY_MISSING,
            safe_message="No remote visual worker.")
        evidence = EvidenceItem("diagram.png", "ocr", '{"text":"coil"}',
                                "paddleocr.local", "local:paddleocr")
        local_success = TaskResult(True, "paddleocr.local", "local:paddleocr",
                                   evidence=(evidence,))
        with patch("core.multimodal.workflow.execute_provider_task",
                   side_effect=[(failure, None), (local_success, None)]) as execute:
            result = analyze_single_attachment(self.record, "Describe it")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["analyzed"], 1)
        self.assertIn("OCR text only", result["context"])
        self.assertIn("not full multimodal understanding", result["context"].lower())
        self.assertEqual([x.value for x in execute.call_args_list[1].args[0].required_capabilities], ["ocr"])
        self.assertEqual(execute.call_args_list[1].kwargs["privacy_tier"], "local")

    def test_audio_uses_local_transcription_as_limited_fallback(self):
        record = dict(self.record, name="clip.wav", mime_type="audio/wav")
        failure = TaskResult(False, "coordinator", "none",
            failure_kind=FailureKind.QUOTA, safe_message="Remote quota reached.")
        evidence = EvidenceItem("clip.wav", "transcript", '{"text":"hello"}',
                                "faster_whisper.local", "local:faster-whisper")
        local_success = TaskResult(True, "faster_whisper.local", "local:faster-whisper",
                                   evidence=(evidence,))
        with patch("core.multimodal.workflow.execute_provider_task",
                   side_effect=[(failure, None), (local_success, None)]) as execute:
            result = analyze_single_attachment(record, "Transcribe")
        self.assertEqual(result["status"], "partial")
        self.assertIn("Transcript only", result["context"])
        self.assertEqual([x.value for x in execute.call_args_list[1].args[0].required_capabilities], ["audio_transcription"])

    def test_multi_file_flow_keeps_batching_then_falls_back_in_order(self):
        records = [
            dict(self.record, id="1" * 32, name="one.png"),
            dict(self.record, id="2" * 32, name="two.png"),
            dict(self.record, id="3" * 32, name="three.png"),
        ]
        batch_result = {"status": "partial", "count": 3, "analyzed": 1,
                        "context": "Gemini completed first file.", "error": "quota"}
        local_result = {"status": "partial", "count": 1, "analyzed": 1,
                        "context": "OCR text for second file.", "error": "limited",
                        "worker": "paddleocr.local", "model": "local:paddleocr"}
        with patch("core.multimodal.workflow.analyze_attachments", return_value=batch_result), \\
             patch("core.multimodal.workflow._try_local_extraction",
                   side_effect=[local_result, None]) as fallback:
            result = analyze_multiple_attachments(records, "Describe all")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["analyzed"], 2)
        self.assertIn("Gemini completed first file", result["context"])
        self.assertIn("OCR text for second file", result["context"])
        self.assertEqual(fallback.call_count, 2)
        self.assertEqual(fallback.call_args_list[0].args[0]["name"], "two.png")
        self.assertEqual(fallback.call_args_list[1].args[0]["name"], "three.png")
        self.assertEqual(result["worker"], "mixed")
        self.assertEqual(result["model"], "multiple")

    def test_complete_multi_file_batch_does_not_reprocess_files(self):
        records = [self.record, dict(self.record, id="b" * 32, name="two.png")]
        batch_result = {"status": "complete", "count": 2, "analyzed": 2,
                        "context": "Both files completed.", "error": None}
        with patch("core.multimodal.workflow.analyze_attachments", return_value=batch_result), \\
             patch("core.multimodal.workflow._try_local_extraction") as fallback:
            result = analyze_multiple_attachments(records, "Describe all")
        self.assertEqual(result["worker"], "gemini.multimodal")
        self.assertEqual(result["analyzed"], 2)
        fallback.assert_not_called()

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
