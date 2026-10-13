import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.conversation import Conversation
from core.persistence.sqlite_journal import SQLiteJournal
from interfaces.cli.main import main, run_cli


class FakeChatApplication:
    def __init__(self) -> None:
        self.calls: list[tuple[Conversation, str]] = []

    def send_message(
        self,
        conversation: Conversation,
        user_message: str,
    ) -> str:
        self.calls.append((conversation, user_message))
        return f"Response to: {user_message}"


class FakeOmnitrix:
    pass


class CliTests(unittest.TestCase):
    def _run_cli(
        self,
        inputs: list[str],
    ) -> tuple[FakeChatApplication, Conversation, list[str]]:
        application = FakeChatApplication()
        conversation = Conversation()
        input_values = iter(inputs)
        outputs: list[str] = []

        def input_fn(prompt: str) -> str:
            return next(input_values)

        def output_fn(message: str) -> None:
            outputs.append(message)

        run_cli(
            application=application,
            conversation=conversation,
            input_fn=input_fn,
            output_fn=output_fn,
        )

        return application, conversation, outputs

    def test_cli_sends_message_and_displays_response(self):
        application, conversation, outputs = self._run_cli(
            ["Hello", "/exit"]
        )

        self.assertEqual(
            application.calls,
            [(conversation, "Hello")],
        )
        self.assertEqual(
            outputs,
            ["Response to: Hello"],
        )

    def test_cli_exit_does_not_send_message(self):
        application, conversation, outputs = self._run_cli(
            ["/exit"]
        )

        self.assertEqual(application.calls, [])
        self.assertEqual(outputs, [])
        self.assertEqual(conversation.messages, ())

    def test_cli_ignores_blank_messages(self):
        application, conversation, outputs = self._run_cli(
            ["", "   ", "Hello", "/exit"]
        )

        self.assertEqual(
            application.calls,
            [(conversation, "Hello")],
        )
        self.assertEqual(
            outputs,
            ["Response to: Hello"],
        )

    def test_list_runs_does_not_print_stored_objectives(self):
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "journal.sqlite3"
            with SQLiteJournal(journal_path) as journal:
                journal.create_run(
                    "run-visible",
                    status="running",
                    payload={
                        "objective": "SENSITIVE OBJECTIVE TEXT",
                        "execution_kind": "run",
                    },
                )

            with patch("builtins.print") as print_mock:
                main(["--journal", str(journal_path), "--list-runs"])

            output = print_mock.call_args.args[0]
            records = json.loads(output)
            self.assertEqual(records[0]["run_id"], "run-visible")
            self.assertEqual(records[0]["status"], "running")
            self.assertNotIn("SENSITIVE OBJECTIVE TEXT", output)
            self.assertNotIn("objective", records[0])

    def test_inspect_run_prints_conservative_recovery_disposition(self):
        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "journal.sqlite3"
            with SQLiteJournal(journal_path) as journal:
                journal.create_run(
                    "run-inspect",
                    status="running",
                    payload={"objective": "private", "execution_kind": "run"},
                )

            with patch("builtins.print") as print_mock:
                main([
                    "--journal", str(journal_path),
                    "--inspect-run", "run-inspect",
                ])

            output = json.loads(print_mock.call_args.args[0])
            self.assertEqual(output["run_id"], "run-inspect")
            self.assertEqual(output["decision"]["disposition"], "revalidation_required")
            self.assertFalse(output["can_auto_resume"])

    def test_restart_command_requires_explicit_confirmation(self):
        with self.assertRaises(SystemExit):
            main([
                "--config", "config/demo.models.json",
                "--journal", "journal.sqlite3",
                "--restart-run", "run-1",
            ])

    def test_restart_confirmation_flag_is_rejected_without_restart_command(self):
        with self.assertRaises(SystemExit):
            main([
                "--config", "config/demo.models.json",
                "--confirm-restart-from-objective",
            ])

    @patch("interfaces.cli.main.Omnitrix")
    def test_main_builds_application_and_starts_cli(self, omnitrix_class):
        fake_omnitrix = FakeOmnitrix()
        omnitrix_class.from_config.return_value = fake_omnitrix

        with patch("interfaces.cli.main.run_cli") as run_cli_mock:
            main(["--config", "config/models.json"])

        omnitrix_class.from_config.assert_called_once_with(
            "config/models.json"
        )
        run_cli_mock.assert_called_once()

        call_kwargs = run_cli_mock.call_args.kwargs

        self.assertIsInstance(
            call_kwargs["conversation"],
            Conversation,
        )
        self.assertEqual(
            call_kwargs["application"]._omnitrix,
            fake_omnitrix,
        )


if __name__ == "__main__":
    unittest.main()
