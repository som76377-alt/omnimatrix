import unittest

from core.conversation import Conversation
from core.models.messages import MessageRole


class ConversationTests(unittest.TestCase):
    def test_new_conversation_is_empty(self):
        conversation = Conversation()

        self.assertEqual(conversation.messages, ())

    def test_add_user_message(self):
        conversation = Conversation()

        conversation.add_user_message("Hello Omnitrix")

        self.assertEqual(len(conversation.messages), 1)
        self.assertEqual(conversation.messages[0].role, MessageRole.USER)
        self.assertEqual(
            conversation.messages[0].content,
            "Hello Omnitrix",
        )

    def test_add_assistant_message(self):
        conversation = Conversation()

        conversation.add_assistant_message("Hello.")

        self.assertEqual(len(conversation.messages), 1)
        self.assertEqual(
            conversation.messages[0].role,
            MessageRole.ASSISTANT,
        )
        self.assertEqual(
            conversation.messages[0].content,
            "Hello.",
        )

    def test_messages_preserve_conversation_order(self):
        conversation = Conversation()

        conversation.add_user_message("First")
        conversation.add_assistant_message("Second")
        conversation.add_user_message("Third")

        self.assertEqual(
            [message.content for message in conversation.messages],
            ["First", "Second", "Third"],
        )

    def test_messages_returns_immutable_snapshot(self):
        conversation = Conversation()
        conversation.add_user_message("Hello")

        messages = conversation.messages

        self.assertIsInstance(messages, tuple)

        conversation.add_assistant_message("Hi")

        self.assertEqual(
            [message.content for message in messages],
            ["Hello"],
        )

    def test_clear_removes_all_messages(self):
        conversation = Conversation()

        conversation.add_user_message("Hello")
        conversation.add_assistant_message("Hi")

        conversation.clear()

        self.assertEqual(conversation.messages, ())


if __name__ == "__main__":
    unittest.main()
