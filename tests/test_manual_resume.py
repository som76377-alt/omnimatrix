import unittest

from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.messages import ModelRequest
from core.models.registry import ModelDefinition, ModelRegistry
from core.orchestrator.omnitrix import Omnitrix
from core.persistence.sqlite_journal import SQLiteJournal


class FinalAnswerAdapter(ModelAdapter):
    @property
    def name(self):
        return "resume-test-model"

    @property
    def provider(self):
        return "test"

    def generate(self, request: ModelRequest):
        return ModelResponse(
            content="Recovered safely from the original objective.",
            model=self.name,
            provider=self.provider,
        )


def build_omnitrix(journal):
    model = ModelDefinition(
        name="resume-test-model",
        provider="test",
        model_id="resume-test-model-v1",
        capabilities=frozenset({"reasoning"}),
        context_window=32000,
        enabled=True,
        metadata={"cost_class": "demo", "estimated_cost_usd": 0},
    )
    models = ModelRegistry()
    models.register(model)
    adapters = AdapterRegistry()
    adapters.register(FinalAnswerAdapter())
    return Omnitrix(registry=models, adapter_registry=adapters, journal=journal)


def create_interrupted_run(journal, run_id="run-safe", execution_kind="run"):
    objective = "Answer a question without using external tools."
    journal.create_run(
        run_id,
        status="running",
        payload={"objective": objective, "execution_kind": execution_kind},
    )
    journal.upsert_task(
        run_id,
        "task-safe",
        "running",
        {"objective": objective, "execution_kind": execution_kind},
    )
    journal.record_attempt(
        "attempt-1", run_id, "task-safe", 1, "running", {"execution_kind": execution_kind}
    )
    journal.save_checkpoint(
        run_id,
        f"{run_id}:checkpoint:0",
        0,
        "task_started",
        {"task_id": "task-safe", "attempt_id": "attempt-1"},
    )
    return objective


class GuardedManualRestartTests(unittest.TestCase):
    def test_explicit_restart_creates_new_attempt_and_finishes_same_run(self):
        with SQLiteJournal(":memory:") as journal:
            objective = create_interrupted_run(journal)
            omnitrix = build_omnitrix(journal)

            with self.assertRaisesRegex(ValueError, "Explicit confirmation"):
                omnitrix.resume_interrupted_run("run-safe")

            result = omnitrix.resume_interrupted_run(
                "run-safe", confirm_restart_from_objective=True
            )
            self.assertEqual(result, "Recovered safely from the original objective.")
            snapshot = journal.get_recovery_snapshot("run-safe")
            self.assertEqual(snapshot["run"]["status"], "completed")
            self.assertEqual(snapshot["run"]["payload"]["objective"], objective)
            attempts = sorted(snapshot["attempts"], key=lambda item: item["attempt_number"])
            self.assertEqual(len(attempts), 2)
            self.assertEqual(attempts[0]["status"], "interrupted")
            self.assertEqual(attempts[1]["status"], "completed")
            self.assertEqual(attempts[1]["attempt_number"], 2)
            self.assertEqual(snapshot["tasks"][0]["status"], "completed")
            self.assertTrue(
                any(
                    item["checkpoint_type"] == "manual_restart_authorized"
                    for item in snapshot["checkpoints"]
                )
            )

    def test_restart_is_blocked_when_any_tool_execution_exists(self):
        with SQLiteJournal(":memory:") as journal:
            create_interrupted_run(journal)
            journal.begin_tool_execution(
                "execution-1",
                "run-safe:task-safe:action-1",
                "side_effect",
                "request-digest",
                run_id="run-safe",
                task_id="task-safe",
                attempt_id="attempt-1",
                logical_action_id="iteration:1:call:0",
            )
            omnitrix = build_omnitrix(journal)
            with self.assertRaisesRegex(RuntimeError, "reconciliation_required"):
                omnitrix.resume_interrupted_run(
                    "run-safe", confirm_restart_from_objective=True
                )

    def test_restart_is_blocked_for_chat_turns_without_saved_conversation_context(self):
        with SQLiteJournal(":memory:") as journal:
            create_interrupted_run(journal, execution_kind="chat")
            omnitrix = build_omnitrix(journal)
            with self.assertRaisesRegex(RuntimeError, "chat turns"):
                omnitrix.resume_interrupted_run(
                    "run-safe", confirm_restart_from_objective=True
                )

    def test_restart_is_blocked_if_a_tool_call_boundary_was_recorded(self):
        with SQLiteJournal(":memory:") as journal:
            create_interrupted_run(journal)
            journal.save_checkpoint(
                "run-safe",
                "run-safe:checkpoint:1",
                1,
                "tool_call_prepared",
                {"task_id": "task-safe", "tool_name": "side_effect"},
            )
            omnitrix = build_omnitrix(journal)
            with self.assertRaisesRegex(RuntimeError, "tool-call boundary"):
                omnitrix.resume_interrupted_run(
                    "run-safe", confirm_restart_from_objective=True
                )


if __name__ == "__main__":
    unittest.main()
