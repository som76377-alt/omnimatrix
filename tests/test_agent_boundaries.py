import tempfile
import unittest
from pathlib import Path

from core.agents.registry import AgentRegistry
from core.models.adapters import AdapterRegistry
from core.models.registry import ModelRegistry
from core.orchestrator.omnitrix import Omnitrix
from core.policy.agent_boundaries import ROLE_TOOL_ALLOWLIST, allowed_tools_for_role, support_assignment_contract
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission
from core.tools.request import ToolRequest


ROOT = Path(__file__).resolve().parents[1]


class AgentBoundaryTests(unittest.TestCase):
    def build_runtime(self, workspace):
        tools = build_tool_registry(
            workspace_root=workspace,
            allowed_paths=("core", "tests"),
            enable_cline=True,
        )
        return Omnitrix(
            registry=ModelRegistry(),
            adapter_registry=AdapterRegistry(),
            tool_registry=tools,
            tool_permission=ToolPermission.from_capabilities(
                {"coding.execute", "workspace.read", "calculation"}
            ),
            agent_registry=AgentRegistry.load(ROOT / "config" / "agents.json"),
        )

    def test_cline_is_exposed_only_to_coding_role(self):
        self.assertIn("cline.coding", allowed_tools_for_role("coding"))
        for role in ("reasoning", "research", "computation", "subject_solver", "critic", "intent_engineer"):
            self.assertNotIn("cline.coding", allowed_tools_for_role(role))

    def test_roles_have_narrow_tool_allowlists(self):
        self.assertEqual(allowed_tools_for_role("reasoning"), frozenset())
        self.assertEqual(allowed_tools_for_role("research"), frozenset())
        self.assertEqual(allowed_tools_for_role("computation"), frozenset({"calculator"}))
        self.assertEqual(allowed_tools_for_role("coding"), frozenset({"cline.coding", "workspace.inspect"}))
        self.assertNotIn("cline.coding", ROLE_TOOL_ALLOWLIST["subject_solver"])

    def test_model_tool_surface_is_intersection_of_permission_and_role(self):
        with tempfile.TemporaryDirectory() as workspace:
            omnitrix = self.build_runtime(workspace)
            names = {tool.name for tool in omnitrix._get_authorized_model_tools(agent_role="coding")}
            self.assertIn("cline.coding", names)
            self.assertIn("workspace.inspect", names)
            self.assertNotIn("calculator", names)
            self.assertNotIn("manim_scientific_diagram", names)

            compute_names = {tool.name for tool in omnitrix._get_authorized_model_tools(agent_role="computation")}
            self.assertEqual(compute_names, {"calculator"})

            research_names = {tool.name for tool in omnitrix._get_authorized_model_tools(agent_role="research")}
            self.assertEqual(research_names, set())

    def test_runtime_rejects_cline_call_from_non_coding_role_before_dispatch(self):
        with tempfile.TemporaryDirectory() as workspace:
            omnitrix = self.build_runtime(workspace)
            request = ToolRequest(
                tool_name="cline.coding",
                arguments={"task": "Implement a focused regression test", "mode": "implement"},
            )
            result = omnitrix.execute_tool(request, agent_role="reasoning")
            self.assertFalse(result.success)
            self.assertEqual(result.metadata["denied_by"], "agent_role_scope")
            self.assertEqual(result.metadata["execution_outcome"], "not_started")

    def test_unknown_role_fails_closed(self):
        self.assertEqual(allowed_tools_for_role("made_up_role"), frozenset())

    def test_support_assignments_are_narrow_and_report_missing_retrieval(self):
        research = support_assignment_contract("research", "coding")
        coding = support_assignment_contract("coding", "reasoning")
        self.assertIn("BLOCKED", research)
        self.assertIn("never fill the gap with invented citations", research)
        self.assertIn("Do not edit files", coding)
        self.assertIn("The lead will integrate your result", research)


if __name__ == "__main__":
    unittest.main()
