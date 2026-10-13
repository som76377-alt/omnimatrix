"""Fault-injection tests for the external-side-effect crash window."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.persistence.recovery_service import RecoveryService
from core.persistence.sqlite_journal import SQLiteJournal


class ToolSideEffectCrashTests(unittest.TestCase):
    def test_crash_after_side_effect_before_outcome_commit_requires_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "side-effect-crash.sqlite3"
            marker_path = Path(directory) / "side-effect.marker"
            script = r"""
import os
import sys
from pathlib import Path
from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import ModelRequest
from core.models.registry import ModelDefinition, ModelRegistry
from core.models.types import ModelToolCall
from core.orchestrator.omnitrix import Omnitrix
from core.persistence.sqlite_journal import SQLiteJournal
from core.tools.base import Tool, ToolResult
from core.tools.permissions import ToolPermission
from core.tools.registry import ToolRegistry

class CrashAfterSideEffectTool(Tool):
    @property
    def name(self):
        return "side_effect"
    @property
    def description(self):
        return "Write a test marker, then simulate an abrupt process crash."
    @property
    def capabilities(self):
        return frozenset({"external_write"})
    @property
    def parameters_schema(self):
        return {
            "type": "object",
            "properties": {"marker_path": {"type": "string"}},
            "required": ["marker_path"],
            "additionalProperties": False,
        }
    def execute(self, **kwargs):
        Path(kwargs["marker_path"]).write_text("effect happened", encoding="utf-8")
        os._exit(74)

class ToolCallingAdapter(ModelAdapter):
    @property
    def name(self):
        return "crash-model"
    @property
    def provider(self):
        return "test"
    def generate(self, request: ModelRequest):
        return ModelResponse(
            content="",
            model=self.name,
            provider=self.provider,
            tool_calls=(
                ModelToolCall(
                    id="side-effect-call",
                    tool_name="side_effect",
                    arguments={"marker_path": sys.argv[2]},
                ),
            ),
        )

model = ModelDefinition(
    name="crash-model", provider="test", model_id="crash-model-v1",
    capabilities=frozenset({"reasoning"}), context_window=32000, enabled=True,
    metadata={"cost_class": "demo", "estimated_cost_usd": 0},
)
models = ModelRegistry()
models.register(model)
adapters = AdapterRegistry()
adapters.register(ToolCallingAdapter())
tools = ToolRegistry()
tools.register(CrashAfterSideEffectTool())
with SQLiteJournal(sys.argv[1]) as journal:
    Omnitrix(
        registry=models,
        adapter_registry=adapters,
        tool_registry=tools,
        tool_permission=ToolPermission.from_capabilities({"external_write"}),
        journal=journal,
    ).run("Execute the simulated side effect.")
"""
            completed = subprocess.run(
                [sys.executable, "-c", script, str(database_path), str(marker_path)],
                cwd=str(Path(__file__).resolve().parents[1]),
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(completed.returncode, 74, completed.stderr)
            self.assertEqual(marker_path.read_text(encoding="utf-8"), "effect happened")

            with SQLiteJournal(database_path) as journal:
                with journal._lock:
                    run = journal._connection.execute(
                        "SELECT run_id, status FROM runs"
                    ).fetchone()
                self.assertEqual(run["status"], "running")
                snapshot = journal.get_recovery_snapshot(run["run_id"])
                self.assertEqual(len(snapshot["uncertain_tool_executions"]), 1)
                execution = snapshot["uncertain_tool_executions"][0]
                self.assertEqual(execution["status"], "running")
                self.assertIsNone(execution["finished_at"])
                checkpoints = snapshot["checkpoints"]
                self.assertEqual(
                    checkpoints[-1]["checkpoint_type"], "tool_call_prepared"
                )
                inspection = RecoveryService(journal).inspect(run["run_id"])
                self.assertEqual(
                    inspection.decision.disposition, "reconciliation_required"
                )
                self.assertFalse(inspection.can_auto_resume)


if __name__ == "__main__":
    unittest.main()
