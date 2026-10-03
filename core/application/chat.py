from core.conversation import Conversation
from core.orchestrator.omnitrix import Omnitrix


class ChatApplication:
    """Application boundary for conversational interactions."""

    def __init__(self, omnitrix: Omnitrix) -> None:
        self._omnitrix = omnitrix

    def send_message(
        self,
        conversation: Conversation,
        user_message: str,
    ) -> str:
        """Process one user message through Omnitrix."""
        return self._omnitrix.chat(
            conversation,
            user_message,
        )
