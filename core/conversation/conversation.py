from dataclasses import dataclass, field

from core.models.messages import MessageRole, ModelMessage


@dataclass
class Conversation:
    """In-memory conversational history for a single chat session."""

    _messages: list[ModelMessage] = field(default_factory=list)

    @property
    def messages(self) -> tuple[ModelMessage, ...]:
        """Return the conversation history as an immutable snapshot."""
        return tuple(self._messages)

    def add_user_message(self, content: str) -> None:
        """Append a user message to the conversation."""
        self._messages.append(
            ModelMessage(
                role=MessageRole.USER,
                content=content,
            )
        )

    def add_assistant_message(self, content: str) -> None:
        """Append an assistant message to the conversation."""
        self._messages.append(
            ModelMessage(
                role=MessageRole.ASSISTANT,
                content=content,
            )
        )

    def clear(self) -> None:
        """Remove all messages from the conversation."""
        self._messages.clear()
