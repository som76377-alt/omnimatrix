import copy
import hashlib
import json
import unittest

from core.models.base import ModelResponse
from core.models.messages import (
    MessageRole,
    ModelMessage,
    ModelRequest,
    ModelToolResult,
)
from core.models.types import ModelContinuation, ModelToolCall, ModelToolDefinition
from core.persistence.model_state import (
    MAX_MODEL_STATE_BYTES,
    ModelStateCodecError,
    decode_model_state,
    encode_model_state,
)


class ModelStateCodecTests(unittest.TestCase):
    def setUp(self):
        self.request = ModelRequest(
            instructions="Follow the user's objective carefully.",
            messages=(
                ModelMessage(MessageRole.USER, "Calculate 12 times 9."),
                ModelMessage(
                    MessageRole.ASSISTANT,
                    tool_calls=(
                        ModelToolCall(
                            id="call-1",
                            tool_name="calculator",
                            arguments={"expression": "12 * 9"},
                        ),
                    ),
                ),
                ModelMessage(
                    MessageRole.TOOL,
                    tool_result=ModelToolResult(
                        tool_call_id="call-1",
                        tool_name="calculator",
                        success=True,
                        output={"value": 108},
                    ),
                ),
            ),
            tools=(
                ModelToolDefinition(
                    name="calculator",
                    description="Evaluate safe arithmetic.",
                    parameters_schema={"type": "object", "required": ["expression"]},
                ),
            ),
            continuation=ModelContinuation(
                provider="test",
                state={"turn": 2, "opaque": {"cursor": "abc"}},
            ),
        )
        self.response = ModelResponse(
            content="The result is 108.",
            model="test-model",
            provider="test",
            usage={"input_tokens": 20, "output_tokens": 8},
            tool_calls=(),
            continuation=ModelContinuation(provider="test", state={"turn": 3}),
        )

    def test_request_round_trip_preserves_ordered_messages_tools_and_continuation(self):
        envelope = encode_model_state(self.request)
        restored = decode_model_state(envelope)
        self.assertEqual(restored, self.request)
        self.assertEqual([message.role for message in restored.messages], [
            MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL
        ])

    def test_response_round_trip(self):
        self.assertEqual(decode_model_state(encode_model_state(self.response)), self.response)

    def test_payload_tampering_is_rejected(self):
        envelope = copy.deepcopy(encode_model_state(self.request))
        envelope["payload"]["messages"][0]["content"] = "changed"
        with self.assertRaisesRegex(ModelStateCodecError, "digest mismatch"):
            decode_model_state(envelope)

    def test_unknown_schema_version_is_rejected(self):
        envelope = encode_model_state(self.request)
        envelope["schema_version"] = 2
        with self.assertRaisesRegex(ModelStateCodecError, "Unsupported"):
            decode_model_state(envelope)

    def test_unknown_payload_fields_are_rejected(self):
        envelope = encode_model_state(self.response)
        envelope["payload"]["unexpected"] = True
        canonical = json.dumps(
            envelope["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        envelope["payload_sha256"] = hashlib.sha256(canonical).hexdigest()
        with self.assertRaisesRegex(ModelStateCodecError, "invalid shape"):
            decode_model_state(envelope)

    def test_non_json_continuation_state_is_rejected(self):
        request = ModelRequest(
            messages=(ModelMessage(MessageRole.USER, "Hello"),),
            continuation=ModelContinuation(provider="test", state={"bad": object()}),
        )
        with self.assertRaisesRegex(ModelStateCodecError, "JSON-compatible"):
            encode_model_state(request)

    def test_oversized_state_is_rejected(self):
        response = ModelResponse(
            content="x" * (MAX_MODEL_STATE_BYTES + 100),
            model="test-model",
            provider="test",
        )
        with self.assertRaisesRegex(ModelStateCodecError, "exceeds"):
            encode_model_state(response)

    def test_malformed_envelope_is_rejected(self):
        with self.assertRaisesRegex(ModelStateCodecError, "invalid shape"):
            decode_model_state({"schema_version": 1, "payload": {}})


if __name__ == "__main__":
    unittest.main()
