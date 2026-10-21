import json
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

    def test_validates_coordinator_work_packages_and_dependency_order(self):
        plan = {
            "objective_summary": "Build a causally correct induction explainer.",
            "work_packages": [
                {
                    "role": "research",
                    "assignment": "Identify the causal claims and evidence gaps.",
                    "expected_output": "A concise evidence ledger.",
                    "acceptance_criteria": ["Claims only rely on actual sources."],
                    "depends_on": [],
                },
                {
                    "role": "subject_solver",
                    "assignment": "Validate the physical mechanism.",
                    "expected_output": "Causal sequence and edge cases.",
                    "acceptance_criteria": ["Field-to-current-to-heat chain is correct."],
                    "depends_on": ["research"],
                },
            ],
            "integration_order": ["research", "subject_solver"],
            "final_acceptance_criteria": ["Integrated result retains uncertainty and correct physics."],
            "cline_handoff": {"task": "", "acceptance_criteria": [], "files_in_scope": []},
        }
        validated = Omnitrix._validate_coordination_plan(
            json.dumps(plan), ("research", "subject_solver"),
            primary_role="reasoning", cline_available=False,
        )
        self.assertIsNotNone(validated)
        self.assertEqual(validated["integration_order"], ["research", "subject_solver"])

        plan["work_packages"][0]["depends_on"] = ["subject_solver"]
        self.assertIsNone(Omnitrix._validate_coordination_plan(
            json.dumps(plan), ("research", "subject_solver"),
            primary_role="reasoning", cline_available=False,
        ))

    def test_coordinator_cannot_scope_cline_outside_workspace(self):
        plan = {
            "objective_summary": "Implement a code-rendered physics explainer.",
            "work_packages": [{
                "role": "subject_solver",
                "assignment": "Specify the causal physics.",
                "expected_output": "Causal sequence and checks.",
                "acceptance_criteria": ["The physical mechanism is accurate."],
                "depends_on": [],
            }],
            "integration_order": ["subject_solver"],
            "final_acceptance_criteria": ["The final animation matches the causal model."],
            "cline_handoff": {
                "task": "Implement the agreed animation and tests.",
                "acceptance_criteria": ["Relevant tests pass."],
                "files_in_scope": ["../README.md"],
            },
        }
        self.assertIsNone(Omnitrix._validate_coordination_plan(
            json.dumps(plan), ("subject_solver",),
            primary_role="coding", cline_available=True,
        ))


if __name__ == "__main__":
    unittest.main()
