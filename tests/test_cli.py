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

    def test_one_shot_run_requires_journal_and_reports_new_run_id(self):
        with self.assertRaises(SystemExit):
            main([
                "--config", "config/demo.models.json",
                "--run-objective", "Do one task",
            ])

        with tempfile.TemporaryDirectory() as directory:
            journal_path = Path(directory) / "journal.sqlite3"

            def fake_from_config(config_path, journal):
                journal.create_run(
                    "run-one-shot",
                    status="completed",
                    payload={"objective": "private objective", "execution_kind": "run"},
                )
                return type(
                    "FakeRunner",
                    (),
                    {"run": lambda self, objective: "one-shot result"},
                )()

            with patch(
                "interfaces.cli.main.Omnitrix.from_config",
                side_effect=fake_from_config,
            ):
                with patch("builtins.print") as print_mock:
                    main([
                        "--config", "config/demo.models.json",
                        "--journal", str(journal_path),
                        "--run-objective", "Do one task",
                    ])

            output = json.loads(print_mock.call_args.args[0])
            self.assertEqual(output["run_id"], "run-one-shot")
            self.assertEqual(output["result"], "one-shot result")

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

    def test_workspace_root_requires_explicit_read_permission_flag(self):
        with self.assertRaises(SystemExit):
            main([
                "--config", "config/demo.models.json",
                "--workspace-root", ".",
            ])

    def test_workspace_allowlist_requires_explicit_read_permission_flag(self):
        with self.assertRaises(SystemExit):
            main([
                "--config", "config/demo.models.json",
                "--workspace-allow", "src",
            ])

    def test_workspace_read_is_explicit_and_root_is_passed_to_registry(self):
        with tempfile.TemporaryDirectory() as workspace:
            with patch("interfaces.cli.main.Omnitrix") as omnitrix_class:
                omnitrix_class.from_config.return_value = FakeOmnitrix()
                with patch("interfaces.cli.main.run_cli") as run_cli_mock:
                    main([
                        "--config", "config/demo.models.json",
                        "--allow-workspace-read",
                        "--workspace-root", workspace,
                        "--workspace-allow", "src",
                        "--workspace-allow", "README.md",
                    ])

            kwargs = omnitrix_class.from_config.call_args.kwargs
            self.assertEqual(kwargs["tool_permission"].capabilities, frozenset({"workspace.read"}))
            tool = kwargs["tool_registry"].get("workspace.inspect")
            self.assertEqual(tool.capabilities, frozenset({"workspace.read"}))
            self.assertEqual(tool._root, Path(workspace).resolve())
            self.assertEqual(
                tool._allowed_path_prefixes,
                frozenset({("src",), ("README.md",)}),
            )
            tool.close()
            run_cli_mock.assert_called_once()

    def test_cline_coding_requires_an_explicit_workspace(self):
        with self.assertRaises(SystemExit):
            main([
                "--config", "config/demo.models.json",
                "--enable-cline-coding",
            ])

    def test_cline_coding_is_registered_only_with_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as workspace:
            with patch("interfaces.cli.main.Omnitrix") as omnitrix_class:
                omnitrix_class.from_config.return_value = FakeOmnitrix()
                with patch("interfaces.cli.main.run_cli"):
                    main([
                        "--config", "config/demo.models.json",
                        "--workspace-root", workspace,
                        "--enable-cline-coding",
                    ])
            kwargs = omnitrix_class.from_config.call_args.kwargs
            self.assertEqual(kwargs["tool_permission"].capabilities,
                             frozenset({"coding.execute"}))
            self.assertTrue(kwargs["tool_registry"].has("cline.coding"))

    def test_workspace_read_flag_is_rejected_for_recovery_inspection(self):
        with self.assertRaises(SystemExit):
            main([
                "--journal", "journal.sqlite3",
                "--list-runs",
                "--allow-workspace-read",
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
