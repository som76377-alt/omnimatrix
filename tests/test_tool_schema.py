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
