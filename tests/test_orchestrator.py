import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.persistence.recovery_service import RecoveryService
from core.persistence.sqlite_journal import SQLiteJournal
from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import MessageRole, ModelRequest
from core.models.registry import ModelDefinition, ModelRegistry
from core.models.types import ModelContinuation, ModelToolCall
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission


class FakeToolCallingAdapter(ModelAdapter):
    def __init__(self):
        self.requests = []

    @property
    def name(self):
        return "fake-tool-model"

    @property
    def provider(self):
        return "test"

    def generate(self, request: ModelRequest):
        self.requests.append(request)

        if len(self.requests) == 1:
            return ModelResponse(
                content="",
                model=self.name,
                provider=self.provider,
                tool_calls=(
                    ModelToolCall(
                        id="call-1",
                        tool_name="calculator",
                        arguments={"expression": "847 * 23"},
                    ),
                ),
                continuation=ModelContinuation(
                    provider=self.provider,
                    state={"turn": 1},
                ),
            )

        tool_messages = [
            message
            for message in request.messages
            if message.role == MessageRole.TOOL
        ]

        if len(tool_messages) != 1:
            raise RuntimeError("Expected exactly one tool message.")
        if tool_messages[0].tool_result is None:
            raise RuntimeError("Expected a tool result.")
        if not tool_messages[0].tool_result.success:
            raise RuntimeError("Expected successful tool execution.")
        if tool_messages[0].tool_result.output != 19481:
            raise RuntimeError("Expected calculator result 19481.")

        return ModelResponse(
            content="The result is 19,481.",
            model=self.name,
            provider=self.provider,
        )


class OmnitrixOrchestratorTests(unittest.TestCase):
    def test_tool_call_continuation_flow(self):
        model = ModelDefinition(
            name="fake-tool-model",
            provider="test",
            model_id="fake-tool-model-v1",
            capabilities=frozenset({"reasoning", "calculation"}),
            context_window=32000,
            enabled=True,
            metadata={"cost_class": "demo", "estimated_cost_usd": 0},
        )

        model_registry = ModelRegistry()
        model_registry.register(model)

        adapter = FakeToolCallingAdapter()
        adapter_registry = AdapterRegistry()
        adapter_registry.register(adapter)

        omnitrix = Omnitrix(
            registry=model_registry,
            adapter_registry=adapter_registry,
            tool_registry=build_tool_registry(),
            tool_permission=ToolPermission.from_capabilities({"calculation"}),
        )

        result = omnitrix.run(
            "Calculate 847 * 23 using the calculator tool."
        )

        self.assertEqual(result, "The result is 19,481.")
        self.assertEqual(len(adapter.requests), 2)

        first_request = adapter.requests[0]
        self.assertEqual(
            first_request.messages[0].content,
            "Calculate 847 * 23 using the calculator tool.",
        )
        self.assertEqual(len(first_request.tools), 1)
        self.assertEqual(first_request.tools[0].name, "calculator")

        second_request = adapter.requests[1]
        self.assertIsNotNone(second_request.continuation)
        self.assertEqual(
            second_request.continuation.state["turn"],
            1,
        )

        tool_messages = [
            message
            for message in second_request.messages
            if message.role == MessageRole.TOOL
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(
            tool_messages[0].tool_result.output,
            19481,
        )


    def test_run_persists_task_lifecycle_to_sqlite(self):
        model = ModelDefinition(
            name="fake-tool-model",
            provider="test",
            model_id="fake-tool-model-v1",
            capabilities=frozenset({"reasoning", "calculation"}),
            context_window=32000,
            enabled=True,
            metadata={"cost_class": "demo", "estimated_cost_usd": 0},
        )
        model_registry = ModelRegistry()
        model_registry.register(model)
        adapter_registry = AdapterRegistry()
        adapter_registry.register(FakeToolCallingAdapter())

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "journal.sqlite3"
            with SQLiteJournal(database_path) as journal:
                omnitrix = Omnitrix(
                    registry=model_registry,
                    adapter_registry=adapter_registry,
                    tool_registry=build_tool_registry(),
                    tool_permission=ToolPermission.from_capabilities({"calculation"}),
                    journal=journal,
                )
                result = omnitrix.run("Calculate 847 * 23 using the calculator tool.")
                self.assertEqual(result, "The result is 19,481.")

            with sqlite3.connect(database_path) as database:
                run_rows = database.execute(
                    "SELECT run_id, status, payload_json FROM runs"
                ).fetchall()
                task_rows = database.execute(
                    "SELECT run_id, task_id, status, payload_json FROM tasks"
                ).fetchall()
                attempt_rows = database.execute(
                    "SELECT run_id, task_id, attempt_number, status, finished_at FROM attempts"
                ).fetchall()
                tool_execution_rows = database.execute(
                    "SELECT run_id, task_id, attempt_id, tool_name, status, finished_at, request_sha256 "
                    "FROM tool_executions"
                ).fetchall()
                event_rows = database.execute(
                    "SELECT event_type, sequence FROM events ORDER BY sequence"
                ).fetchall()
                checkpoint_rows = database.execute(
                    "SELECT checkpoint_type, sequence, payload_json, payload_sha256 "
                    "FROM checkpoints ORDER BY sequence"
                ).fetchall()

            self.assertEqual(len(run_rows), 1)
            self.assertEqual(run_rows[0][1], "completed")
            self.assertEqual(len(task_rows), 1)
            self.assertEqual(task_rows[0][2], "completed")
            self.assertIn("Calculate 847 * 23", run_rows[0][2])
            self.assertIn("Calculate 847 * 23", task_rows[0][3])
            self.assertEqual(
                event_rows,
                [
                    ("run_created", 0),
                    ("task_started", 1),
                    ("attempt_started", 2),
                    ("attempt_completed", 3),
                    ("task_completed", 4),
                ],
            )
            self.assertEqual(len(attempt_rows), 1)
            self.assertEqual(attempt_rows[0][2], 1)
            self.assertEqual(attempt_rows[0][3], "completed")
            self.assertIsNotNone(attempt_rows[0][4])
            self.assertEqual(
                [row[0] for row in checkpoint_rows],
                [
                    "task_started",
                    "model_request_started",
                    "model_response_received",
                    "tool_call_prepared",
                    "tool_call_result_received",
                    "model_request_started",
                    "model_response_received",
                    "task_result_ready",
                ],
            )
            self.assertEqual(
                [row[1] for row in checkpoint_rows],
                list(range(len(checkpoint_rows))),
            )
            self.assertTrue(all(len(row[3]) == 64 for row in checkpoint_rows))
            self.assertNotIn("Calculate 847 * 23", "".join(row[2] for row in checkpoint_rows))
            with SQLiteJournal(database_path) as journal:
                inspection = RecoveryService(journal).inspect(run_rows[0][0])
                self.assertEqual(inspection.integrity_errors, ())
                self.assertEqual(inspection.checkpoint_count, len(checkpoint_rows))
                self.assertEqual(inspection.decision.disposition, "terminal")

            self.assertEqual(len(tool_execution_rows), 1)
            self.assertEqual(tool_execution_rows[0][0], run_rows[0][0])
            self.assertEqual(tool_execution_rows[0][1], task_rows[0][1])
            self.assertEqual(tool_execution_rows[0][3], "calculator")
            self.assertEqual(tool_execution_rows[0][4], "succeeded")
            self.assertIsNotNone(tool_execution_rows[0][5])
            self.assertEqual(len(tool_execution_rows[0][6]), 64)

    def test_failed_run_persists_failed_attempt(self):
        class FailingAdapter(ModelAdapter):
            @property
            def name(self):
                return "failing-model"

            @property
            def provider(self):
                return "test"

            def generate(self, request: ModelRequest):
                raise RuntimeError("synthetic provider failure")

        model = ModelDefinition(
            name="failing-model",
            provider="test",
            model_id="failing-model-v1",
            capabilities=frozenset({"reasoning", "testing"}),
            context_window=32000,
            enabled=True,
            metadata={"cost_class": "demo", "estimated_cost_usd": 0},
        )
        model_registry = ModelRegistry()
        model_registry.register(model)
        adapter_registry = AdapterRegistry()
        adapter_registry.register(FailingAdapter())

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "failed.sqlite3"
            with SQLiteJournal(database_path) as journal:
                omnitrix = Omnitrix(
                    registry=model_registry,
                    adapter_registry=adapter_registry,
                    journal=journal,
                )
                with self.assertRaisesRegex(RuntimeError, "synthetic provider failure"):
                    omnitrix.run("A deliberately failing test task")
            with sqlite3.connect(database_path) as database:
                attempt = database.execute(
                    "SELECT status, finished_at, payload_json FROM attempts"
                ).fetchone()
                events = database.execute(
                    "SELECT event_type FROM events ORDER BY sequence"
                ).fetchall()
            self.assertEqual(attempt[0], "failed")
            self.assertIsNotNone(attempt[1])
            self.assertIn("RuntimeError", attempt[2])
            self.assertEqual(
                [event[0] for event in events],
                ["run_created", "task_started", "attempt_started", "attempt_failed", "task_failed"],
            )


if __name__ == "__main__":
    unittest.main()
