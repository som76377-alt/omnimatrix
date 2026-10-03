import unittest

from core.application.chat import ChatApplication
from core.conversation import Conversation


class FakeOmnitrix:
    def __init__(self) -> None:
        self.calls: list[tuple[Conversation, str]] = []

    def chat(
        self,
        conversation: Conversation,
        user_message: str,
    ) -> str:
        self.calls.append((conversation, user_message))
        return "Fake response"


class ChatApplicationTests(unittest.TestCase):
    def test_send_message_delegates_to_omnitrix(self):
        omnitrix = FakeOmnitrix()
        application = ChatApplication(omnitrix)
        conversation = Conversation()

        result = application.send_message(
            conversation,
            "Hello Omnitrix",
        )

        self.assertEqual(result, "Fake response")
        self.assertEqual(
            omnitrix.calls,
            [(conversation, "Hello Omnitrix")],
        )

    def test_send_message_returns_omnitrix_response_unchanged(self):
        omnitrix = FakeOmnitrix()
        application = ChatApplication(omnitrix)
        conversation = Conversation()

        result = application.send_message(
            conversation,
            "Calculate something",
        )

        self.assertIsInstance(result, str)
        self.assertEqual(result, "Fake response")


if __name__ == "__main__":
    unittest.main()
