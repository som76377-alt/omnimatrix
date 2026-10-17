import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.models.adapters import AdapterRegistry
from core.models.providers.gemini import GeminiAdapter
from core.models.registry import ModelDefinition, ModelRegistry
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission


class FakeHTTPResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class WorkspaceProviderIntegrationTests(unittest.TestCase):
    def test_gemini_tool_call_reads_workspace_and_returns_result_to_model(self):
        responses = [
            {
                "id": "interaction-tool-call",
                "model": "gemini-3.8-flash",
                "steps": [
                    {
                        "type": "function_call",
                        "id": "call-workspace-1",
                        "name": "workspace.inspect",
                        "arguments": {
                            "operation": "read",
                            "path": "notes.txt",
                        },
                    }
                ],
            },
            {
                "id": "interaction-final",
                "model": "gemini-3.8-flash",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [
                            {
                                "type": "text",
                                "text": "The note describes induction as the starting point.",
                            }
                        ],
                    }
                ],
            },
        ]
        sent_payloads = []

        def fake_urlopen(http_request, timeout):
            sent_payloads.append(json.loads(http_request.data.decode("utf-8")))
            return FakeHTTPResponse(responses[len(sent_payloads) - 1])

        model = ModelDefinition(
            name="gemini-primary",
            provider="google",
            model_id="gemini-3.8-flash",
            capabilities=frozenset({"reasoning"}),
            context_window=32000,
            enabled=True,
            metadata={"cost_class": "demo", "estimated_cost_usd": 0},
        )
        model_registry = ModelRegistry()
        model_registry.register(model)
        adapters = AdapterRegistry()
        adapters.register(
            GeminiAdapter(
                name="gemini-primary",
                model_id="gemini-3.8-flash",
                api_key="test-key",
                max_retries=0,
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "notes.txt").write_text(
                "Induction creates a changing magnetic field that heats the pan.",
                encoding="utf-8",
            )
            omnitrix = Omnitrix(
                registry=model_registry,
                adapter_registry=adapters,
                tool_registry=build_tool_registry(workspace_root=directory),
                tool_permission=ToolPermission.from_capabilities(
                    {"workspace.read"}
                ),
            )
            with patch(
                "core.models.providers.gemini.urlopen",
                side_effect=fake_urlopen,
            ):
                result = omnitrix.run(
                    "Read notes.txt and summarize its main point."
                )

        self.assertEqual(
            result,
            "The note describes induction as the starting point.",
        )
        self.assertEqual(len(sent_payloads), 2)

        first_payload = sent_payloads[0]
        self.assertEqual(first_payload["input"][0]["content"][0]["text"],
                         "Read notes.txt and summarize its main point.")
        self.assertEqual(
            [tool["name"] for tool in first_payload["tools"]],
            ["workspace.inspect"],
        )

        second_payload = sent_payloads[1]
        self.assertEqual(
            second_payload["previous_interaction_id"],
            "interaction-tool-call",
        )
        function_results = [
            item for item in second_payload["input"]
            if item.get("type") == "function_result"
        ]
        self.assertEqual(len(function_results), 1)
        self.assertEqual(function_results[0]["name"], "workspace.inspect")
        self.assertEqual(function_results[0]["call_id"], "call-workspace-1")
        returned_result = json.loads(
            function_results[0]["result"][0]["text"]
        )
        self.assertEqual(
            returned_result["content"],
            "Induction creates a changing magnetic field that heats the pan.",
        )
        self.assertTrue(returned_result["untrusted_content"])


if __name__ == "__main__":
    unittest.main()
