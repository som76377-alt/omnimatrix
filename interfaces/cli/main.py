import argparse

from core.application import ChatApplication
from core.conversation import Conversation
from core.orchestrator.omnitrix import Omnitrix


def run_cli(
    application: ChatApplication,
    conversation: Conversation,
    input_fn=input,
    output_fn=print,
) -> None:
    """Run an interactive Omnitrix chat session."""

    while True:
        user_message = input_fn("> ")

        if user_message.strip() == "/exit":
            return

        if not user_message.strip():
            continue

        response = application.send_message(
            conversation,
            user_message,
        )

        output_fn(response)


def main(argv: list[str] | None = None) -> None:
    """Build Omnitrix and start the interactive CLI."""

    parser = argparse.ArgumentParser(
        description="Start an Omnitrix chat session."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the Omnitrix model configuration file.",
    )

    args = parser.parse_args(argv)

    omnitrix = Omnitrix.from_config(args.config)
    application = ChatApplication(omnitrix)
    conversation = Conversation()

    run_cli(
        application=application,
        conversation=conversation,
    )


if __name__ == "__main__":
    main()
