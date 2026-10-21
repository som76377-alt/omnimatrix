"""End-to-end Cline tool invocation through Omnitrix's actual orchestration loop.

The outer model is deterministic test scaffolding; the coding work itself is
performed by the real Cline CLI with an explicitly free OpenRouter model in a
temporary workspace. No repository files are changed by this test.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.contracts import BudgetLimits
from core.conversation import Conversation
from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelResponse
from core.models.loader import ModelConfigLoader
from core.models.messages import ModelRequest
from core.models.types import ModelToolCall
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission


CONFIG = ROOT / "config" / "mobile.models.json"
TARGET = "tests/cline_smoke_target.py"


class DeterministicToolCallingAdapter(ModelAdapter):
    """Only simulates the outer model's tool-choice decision, never Cline's work."""

    def __init__(self, name: str, provider: str):
        self._name = name
        self._provider = provider
        self._requested_tool = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider(self) -> str:
        return self._provider

    def generate(self, request: ModelRequest) -> ModelResponse:
        if not self._requested_tool and any(tool.name == "cline.coding" for tool in request.tools):
            self._requested_tool = True
            return ModelResponse(
                content="",
                model=self.name,
                provider=self.provider,
                tool_calls=(
                    ModelToolCall(
                        id="cline-integration-smoke",
                        tool_name="cline.coding",
                        arguments={
                            "task": (
                                "Edit tests/cline_smoke_target.py so the constant "
                                "CLINE_INTEGRATION_RESULT equals 'Cline integration test updated'. "
                                "Do not modify any other file."
                            ),
                            "mode": "implement",
                            "context": "This is an isolated integration test of the Omnitrix-to-Cline tool path.",
                            "acceptance_criteria": [
                                "CLINE_INTEGRATION_RESULT equals exactly 'Cline integration test updated'",
                                "Only tests/cline_smoke_target.py is changed",
                            ],
                            "files_in_scope": [TARGET],
                            "timeout_seconds": 180,
                        },
                    ),
                ),
            )
        return ModelResponse(
            content="The Cline tool result was received by Omnitrix.",
            model=self.name,
            provider=self.provider,
        )


def main() -> int:
    if not os.getenv("OPENROUTER_API_KEY"):
        print("FAIL: OPENROUTER_API_KEY is missing; no task was run.")
        return 1
    if not __import__("shutil").which("cline"):
        print("FAIL: Cline CLI is not installed.")
        return 1

    model_registry = ModelConfigLoader().load(CONFIG)
    adapters = AdapterRegistry()
    for model in model_registry.list_enabled():
        adapters.register(DeterministicToolCallingAdapter(model.name, model.provider))

    with tempfile.TemporaryDirectory(prefix="omnitrix-cline-integration-") as temp:
        workspace = Path(temp) / "workspace"
        (workspace / "tests").mkdir(parents=True)
        target = workspace / TARGET
        target.write_text(
            "CLINE_INTEGRATION_RESULT = 'not updated'\n",
            encoding="utf-8",
        )

        tools = build_tool_registry(
            workspace,
            allowed_paths=("tests",),
            enable_cline=True,
        )
        omnitrix = Omnitrix.from_config(
            CONFIG,
            adapter_registry=adapters,
            tool_registry=tools,
            tool_permission=ToolPermission.from_capabilities(
                {"calculation", "workspace.read", "coding.execute"}
            ),
            budget_limits=BudgetLimits(spend_mode="user_provided_free_quota"),
            agent_config_path=Path(temp) / "no-agents.json",
        )
        try:
            answer = omnitrix.chat(
                Conversation(),
                "Implement the small coding task in the allowed test file using the Cline coding tool.",
            )
            trace = omnitrix.last_execution_trace or {}
            events = trace.get("tool_executions", [])
            cline_events = [
                item for item in events
                if isinstance(item, dict) and item.get("tool_name") == "cline.coding"
            ]
            updated = target.read_text(encoding="utf-8")
            if not cline_events or not any(item.get("success") is True for item in cline_events):
                print("FAIL: Omnitrix did not record a successful cline.coding execution.")
                print({"tool_events": cline_events, "answer_length": len(answer)})
                return 1
            if "CLINE_INTEGRATION_RESULT = 'Cline integration test updated'" not in updated:
                print("FAIL: Cline ran through Omnitrix but did not satisfy the file acceptance check.")
                print({"tool_events": cline_events, "updated_file": updated[:1000]})
                return 1
            print({
                "status": "passed",
                "path": TARGET,
                "cline_execution": cline_events,
                "outer_model": "deterministic test adapter",
                "coding_agent": "Cline CLI",
                "coding_model": os.getenv("CLINE_MODEL", "minimax/minimax-m3.1-flash:free"),
                "persistence": "temporary integration workspace only",
            })
            return 0
        finally:
            tools.get("workspace.inspect").close()


if __name__ == "__main__":
    raise SystemExit(main())
