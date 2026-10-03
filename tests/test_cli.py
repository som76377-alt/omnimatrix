import unittest
from unittest.mock import patch

from core.conversation import Conversation
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
