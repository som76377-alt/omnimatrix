"""Privacy and durability tests for the optional multimodal journal."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.multimodal.journal import journal_status, record_task_outcome
from core.multimodal.router import (
    EvidenceItem, HandoffPacket, TaskRequest, TaskResult, WorkerCapability,
)
from core.persistence.sqlite_journal import SQLiteJournal


class MultimodalJournalTests(unittest.TestCase):
    def test_journal_is_disabled_without_explicit_file_path(self):
        with patch.dict(os.environ, {"OMNITRIX_MULTIMODAL_JOURNAL_PATH": ""}):
            self.assertFalse(journal_status()["enabled"])
            task = TaskRequest("summarize", (WorkerCapability.TEXT_REASONING,))
            packet = HandoffPacket(
                task.task_id, task.user_request, task.source_name, task.source_type,
                dict(task.payload), remaining_capabilities=task.required_capabilities,
            )
            result = TaskResult(False, "coordinator", "none")
            self.assertFalse(record_task_outcome(task, result, packet))

    def test_outcome_survives_reopen_without_storing_prompts_paths_or_extracted_text(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "multimodal.sqlite3"
            task = TaskRequest(
                "private request phrase must not be persisted",
                (WorkerCapability.OCR,),
                source_name="private-name.png",
                source_type="image/png",
                payload={"path": "/private/staged/private-name.png",
                         "records": [{"name": "private-name.png"}]},
            )
            evidence = EvidenceItem(
                "private-name.png", "ocr", "private extracted text must not be persisted",
                "paddleocr.local", "local:paddleocr",
            )
            result = TaskResult(
                True, "paddleocr.local", "local:paddleocr",
                evidence=(evidence,), completed_steps=("paddleocr.local.complete",),
            )
            packet = HandoffPacket(
                task.task_id, task.user_request, task.source_name, task.source_type,
                dict(task.payload), evidence=(evidence,), completed_steps=result.completed_steps,
                attempted_workers=("paddleocr.local",),
            )
            with patch.dict(os.environ, {"OMNITRIX_MULTIMODAL_JOURNAL_PATH": str(database_path)}):
                self.assertTrue(journal_status()["enabled"])
                self.assertTrue(record_task_outcome(task, result, packet))

            with SQLiteJournal(database_path) as journal:
                runs = journal.list_runs(limit=10)
                self.assertEqual(len(runs), 1)
                snapshot = journal.get_recovery_snapshot(runs[0]["run_id"])
                self.assertIsNotNone(snapshot)
                saved = json.dumps(snapshot, ensure_ascii=False)
                self.assertIn("paddleocr.local", saved)
                self.assertIn("completed", saved)
                self.assertNotIn("private request phrase", saved)
                self.assertNotIn("/private/staged/private-name.png", saved)
                self.assertNotIn("private-name.png", saved)
                self.assertNotIn("private extracted text", saved)
                self.assertEqual([event["sequence"] for event in snapshot["events"]], [0, 1])


if __name__ == "__main__":
    unittest.main()
