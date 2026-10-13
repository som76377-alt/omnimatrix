import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.persistence.sqlite_journal import SQLiteJournal
from core.tools.base import ToolResult
from core.tools.executor import ToolExecutor
from core.tools.permissions import ToolPermission
from core.tools.registry import ToolRegistry
from core.tools.request import ToolRequest


class SideEffectTool:
    name = "side-effect"
    description = "Test tool that records whether execution occurred."
    capabilities = frozenset({"testing"})
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "minLength": 1},
            "count": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    def __init__(self):
        self.calls = 0

    def execute(self, **kwargs):
        self.calls += 1
        return ToolResult(success=True, output=kwargs)


class ToolSchemaValidationTests(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.tool = SideEffectTool()
        self.registry.register(self.tool)
        self.executor = ToolExecutor(self.registry)
        self.permission = ToolPermission.from_capabilities({"testing"})

    def execute(self, arguments):
        return self.executor.execute(
            ToolRequest(tool_name="side-effect", arguments=arguments),
            self.permission,
        )

    def test_valid_arguments_execute_once(self):
        result = self.execute({"path": "artifact.txt", "count": 3})
        self.assertTrue(result.success)
        self.assertEqual(self.tool.calls, 1)

    def test_missing_required_argument_is_rejected_before_side_effect(self):
        result = self.execute({"count": 2})
        self.assertFalse(result.success)
        self.assertIn("required property is missing", result.error)
        self.assertEqual(self.tool.calls, 0)

    def test_additional_argument_is_rejected_before_side_effect(self):
        result = self.execute({"path": "artifact.txt", "unexpected": True})
        self.assertFalse(result.success)
        self.assertIn("additional property is not allowed", result.error)
        self.assertEqual(self.tool.calls, 0)

    def test_wrong_type_and_numeric_bounds_are_rejected(self):
        wrong_type = self.execute({"path": "artifact.txt", "count": True})
        too_large = self.execute({"path": "artifact.txt", "count": 6})
        self.assertFalse(wrong_type.success)
        self.assertFalse(too_large.success)
        self.assertEqual(self.tool.calls, 0)

    def test_malformed_schema_fails_closed(self):
        self.tool.parameters_schema = {
            "type": "object",
            "properties": {"path": {"type": "not-a-real-type"}},
        }
        result = self.execute({"path": "artifact.txt"})
        self.assertFalse(result.success)
        self.assertIn("Invalid tool schema", result.error)
        self.assertEqual(self.tool.calls, 0)

    def test_duplicate_idempotency_key_is_not_executed_again_after_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "tool-executions.sqlite3"
            request = ToolRequest(
                tool_name="side-effect",
                arguments={"path": "artifact.txt", "count": 3},
                idempotency_key="run-1:attempt-1:call-1",
            )
            with SQLiteJournal(database_path) as journal:
                executor = ToolExecutor(self.registry, journal=journal)
                first = executor.execute(request, self.permission)
                self.assertTrue(first.success)
                self.assertEqual(self.tool.calls, 1)

            with SQLiteJournal(database_path) as journal:
                executor = ToolExecutor(self.registry, journal=journal)
                duplicate = executor.execute(request, self.permission)
                self.assertFalse(duplicate.success)
                self.assertIn("Duplicate tool request was not executed", duplicate.error)
                self.assertEqual(duplicate.metadata["prior_status"], "succeeded")
                self.assertEqual(self.tool.calls, 1)

    def test_crash_after_effect_before_checkpoint_remains_unknown_after_restart(self):
        class EffectThenInterrupt(SideEffectTool):
            def execute(self, **kwargs):
                self.calls += 1
                # Represents an external action succeeding before the process
                # disappears prior to finish_tool_execution().
                raise SystemExit("simulated process interruption after side effect")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "interrupted-tool.sqlite3"
            interrupted_tool = EffectThenInterrupt()
            registry = ToolRegistry()
            registry.register(interrupted_tool)
            request = ToolRequest(
                tool_name="side-effect",
                arguments={"path": "possibly-created.txt"},
                idempotency_key="durable-action",
            )
            with SQLiteJournal(path) as journal:
                executor = ToolExecutor(registry, journal=journal)
                with self.assertRaisesRegex(SystemExit, "simulated process interruption"):
                    executor.execute(request, self.permission)
                self.assertEqual(interrupted_tool.calls, 1)

            with SQLiteJournal(path) as reopened:
                uncertain = reopened.list_uncertain_tool_executions()
                self.assertEqual(len(uncertain), 1)
                self.assertEqual(uncertain[0]["status"], "running")
                executor = ToolExecutor(registry, journal=reopened)
                duplicate = executor.execute(request, self.permission)
                self.assertFalse(duplicate.success)
                self.assertEqual(duplicate.metadata["prior_status"], "running")
                self.assertEqual(interrupted_tool.calls, 1)

    def test_real_subprocess_crashes_leave_uncertain_actions_blocked(self):
        child_code = r\'''\
import os
import sys
from pathlib import Path

from core.persistence.sqlite_journal import SQLiteJournal
from core.tools.base import ToolResult
from core.tools.executor import ToolExecutor
from core.tools.permissions import ToolPermission
from core.tools.registry import ToolRegistry
from core.tools.request import ToolRequest

database_path, marker_path, crash_point = sys.argv[1:]

class CrashBoundaryTool:
    name = "side-effect"
    description = "Subprocess crash-injection test tool."
    capabilities = frozenset({"testing"})
    parameters_schema = {
        "type": "object",
        "properties": {"path": {"type": "string", "minLength": 1}},
        "required": ["path"],
        "additionalProperties": False,
    }

    def execute(self, **kwargs):
        if crash_point == "before_effect":
            # Abruptly terminate after ToolExecutor has durably claimed the key,
            # but before this tool performs its simulated external side effect.
            os._exit(71)
        with open(marker_path, "a", encoding="utf-8") as marker:
            marker.write("effect committed\\n")
            marker.flush()
            os.fsync(marker.fileno())
        # Simulate the dangerous window: external effect happened, but the
        # executor has not yet written a terminal outcome to SQLite.
        os._exit(72)

registry = ToolRegistry()
registry.register(CrashBoundaryTool())
with SQLiteJournal(database_path) as journal:
    executor = ToolExecutor(registry, journal=journal)
    executor.execute(
        ToolRequest(
            tool_name="side-effect",
            arguments={"path": "artifact.txt"},
            idempotency_key="crash-action-key",
        ),
        ToolPermission.from_capabilities({"testing"}),
    )
os._exit(99)  # Reaching this line would mean the crash injection failed.
\'''
        project_root = Path(__file__).resolve().parents[1]

        for crash_point, expected_exit, effect_expected in (
            ("before_effect", 71, False),
            ("after_effect_before_checkpoint", 72, True),
        ):
            with self.subTest(crash_point=crash_point), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                database_path = root / "journal.sqlite3"
                marker_path = root / "external-effect.txt"

                # Initialize the durable schema before the child process starts.
                with SQLiteJournal(database_path):
                    pass

                process = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        child_code,
                        str(database_path),
                        str(marker_path),
                        crash_point,
                    ],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                self.assertEqual(
                    process.returncode,
                    expected_exit,
                    msg=f"Child did not stop at the expected crash point. stderr={process.stderr!r}",
                )
                self.assertEqual(marker_path.exists(), effect_expected)

                with SQLiteJournal(database_path) as reopened:
                    uncertain = reopened.list_uncertain_tool_executions()
                    self.assertEqual(len(uncertain), 1)
                    record = uncertain[0]
                    self.assertEqual(record["idempotency_key"], "crash-action-key")
                    self.assertEqual(record["status"], "running")
                    self.assertIsNone(record["finished_at"])

                    # Restart must not imply the action's result or replay it.
                    duplicate = ToolExecutor(
                        self.registry, journal=reopened
                    ).execute(
                        ToolRequest(
                            tool_name="side-effect",
                            arguments={"path": "artifact.txt"},
                            idempotency_key="crash-action-key",
                        ),
                        self.permission,
                    )
                    self.assertFalse(duplicate.success)
                    self.assertEqual(duplicate.metadata["prior_status"], "running")
                    self.assertEqual(self.tool.calls, 0)

                if effect_expected:
                    self.assertEqual(
                        marker_path.read_text(encoding="utf-8"),
                        "effect committed\\n",
                    )

    def test_idempotency_key_cannot_be_reused_for_different_arguments(self):
        with SQLiteJournal(":memory:") as journal:
            executor = ToolExecutor(self.registry, journal=journal)
            first = executor.execute(
                ToolRequest(
                    tool_name="side-effect",
                    arguments={"path": "first.txt"},
                    idempotency_key="same-action",
                ),
                self.permission,
            )
            different = executor.execute(
                ToolRequest(
                    tool_name="side-effect",
                    arguments={"path": "different.txt"},
                    idempotency_key="same-action",
                ),
                self.permission,
            )
            self.assertTrue(first.success)
            self.assertFalse(different.success)
            self.assertIn("different request", different.error)
            self.assertEqual(self.tool.calls, 1)

    def test_exception_is_recorded_as_unknown_and_never_retried_automatically(self):
        class RaisesAfterSideEffect(SideEffectTool):
            def execute(self, **kwargs):
                self.calls += 1
                raise RuntimeError("simulated interruption after action")

        raising_tool = RaisesAfterSideEffect()
        registry = ToolRegistry()
        registry.register(raising_tool)
        request = ToolRequest(
            tool_name="side-effect",
            arguments={"path": "possibly-created.txt"},
            idempotency_key="uncertain-action",
        )
        with SQLiteJournal(":memory:") as journal:
            executor = ToolExecutor(registry, journal=journal)
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                executor.execute(request, self.permission)
            duplicate = executor.execute(request, self.permission)
            self.assertFalse(duplicate.success)
            self.assertEqual(duplicate.metadata["prior_status"], "unknown")
            self.assertEqual(duplicate.metadata["execution_outcome"], "unknown")
            self.assertEqual(raising_tool.calls, 1)



if __name__ == "__main__":
    unittest.main()
