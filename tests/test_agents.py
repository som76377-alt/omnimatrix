import json
import tempfile
import unittest
from pathlib import Path

from core.agents.registry import AgentRegistry
from core.agents.router import AgentRouter


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "agents.json"


class AgentRegistryTests(unittest.TestCase):
    def test_project_agent_config_loads_all_seven_roles(self):
        registry = AgentRegistry.load(CONFIG)
        self.assertTrue(registry.enabled)
        self.assertEqual(
            {agent.role for agent in registry.list_enabled()},
            {
                "reasoning", "coding", "subject_solver", "research",
                "computation", "critic", "intent_engineer",
            },
        )

    def test_rejects_invalid_role(self):
        content = json.loads(CONFIG.read_text(encoding="utf-8"))
        content["agents"][0]["role"] = "magic"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agents.json"
            path.write_text(json.dumps(content), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported agent role"):
                AgentRegistry.load(path)

    def test_enabled_registry_requires_all_roles(self):
        with self.assertRaisesRegex(ValueError, "missing roles"):
            AgentRegistry(
                [],
                enabled=True,
            )

    def test_disabled_registry_can_be_empty(self):
        registry = AgentRegistry([], enabled=False)
        self.assertEqual(registry.list_enabled(), [])
        self.assertFalse(registry.has("critic"))


class AgentRouterTests(unittest.TestCase):
    def setUp(self):
        self.registry = AgentRegistry.load(CONFIG)
        self.router = AgentRouter(self.registry)

    def test_routes_physics_to_subject_solver(self):
        plan = self.router.route(
            "Derive why an induction stove heats a metal pan using electromagnetic induction.",
            frozenset({"reasoning"}),
        )
        self.assertIsNotNone(plan)
        self.assertEqual(plan.primary.role, "subject_solver")
        self.assertTrue(plan.needs_intent_preflight)
        self.assertTrue(plan.needs_critique)

    def test_exam_label_does_not_escalate_a_straightforward_math_problem(self):
        problem = "Solve x^2 - 5x + 6 = 0."
        labeled = self.router.route(
            "JEE Advanced: " + problem,
            frozenset({"reasoning"}),
        )
        unlabeled = self.router.route(problem, frozenset({"reasoning"}))
        self.assertEqual(labeled.primary.role, "subject_solver")
        self.assertEqual(labeled.complexity, "standard")
        self.assertFalse(labeled.needs_intent_preflight)
        self.assertFalse(labeled.needs_critique)
        self.assertEqual(labeled.primary.role, unlabeled.primary.role)
        self.assertEqual(labeled.complexity, unlabeled.complexity)
        self.assertEqual(labeled.needs_critique, unlabeled.needs_critique)

    def test_small_talk_stays_on_the_standard_route(self):
        plan = self.router.route("Hello Omnitrix", frozenset({"reasoning"}))
        self.assertEqual(plan.primary.role, "reasoning")
        self.assertEqual(plan.complexity, "standard")
        self.assertFalse(plan.needs_intent_preflight)
        self.assertFalse(plan.needs_critique)

    def test_non_stem_subjects_are_supported_without_exam_framing(self):
        plan = self.router.route(
            "Explain the economic incentives behind price discrimination and consumer surplus.",
            frozenset({"reasoning"}),
        )
        self.assertEqual(plan.primary.role, "subject_solver")
        self.assertEqual(plan.domain, "subject")

    def test_routes_repository_debugging_to_coding(self):
        plan = self.router.route(
            "Debug this repository and implement a robust fix with tests.",
            frozenset({"reasoning", "coding"}),
        )
        self.assertEqual(plan.primary.role, "coding")
        self.assertTrue(plan.needs_critique)

    def test_hybrid_science_animation_routes_implementation_to_coding_lead(self):
        plan = self.router.route(
            "Design and implement a code-rendered physics animation about electromagnetic induction.",
            frozenset({"reasoning", "coding"}),
        )
        self.assertEqual(plan.primary.role, "coding")
        self.assertIn("subject_solver", {agent.role for agent in plan.support_roles})

    def test_hybrid_researched_science_implementation_assigns_both_support_roles(self):
        plan = self.router.route(
            "Research reliable sources and implement a code-rendered physics animation about electromagnetic induction.",
            frozenset({"reasoning", "coding", "research"}),
        )
        roles = {agent.role for agent in plan.support_roles}
        self.assertEqual(plan.primary.role, "coding")
        self.assertIn("subject_solver", roles)
        self.assertIn("research", roles)

    def test_routes_short_vague_prompt_to_reasoning_with_intent_preflight(self):
        plan = self.router.route("Make it better", frozenset({"reasoning"}))
        self.assertEqual(plan.primary.role, "reasoning")
        self.assertTrue(plan.needs_intent_preflight)

    def test_short_action_request_gets_intent_engineering(self):
        plan = self.router.route(
            "Build a simple calculator app.",
            frozenset({"reasoning", "coding"}),
        )
        self.assertEqual(plan.primary.role, "coding")
        self.assertTrue(plan.needs_intent_preflight)

    def test_routes_research_requests_to_research_specialist(self):
        plan = self.router.route(
            "Find the latest scientific papers about planetary atmospheres and cite sources.",
            frozenset({"reasoning"}),
        )
        self.assertEqual(plan.primary.role, "research")
        self.assertIn("sources", plan.primary.instructions.lower())

    def test_routes_explicit_arithmetic_to_computation_specialist(self):
        plan = self.router.route("Calculate 2+2.", frozenset({"reasoning"}))
        self.assertEqual(plan.primary.role, "computation")

    def test_hybrid_coding_and_research_keeps_research_as_support(self):
        plan = self.router.route(
            "Research reliable image libraries and implement a comparison page.",
            frozenset({"reasoning", "coding"}),
        )
        self.assertEqual(plan.primary.role, "coding")
        self.assertIn("research", {agent.role for agent in plan.support_roles})

    def test_standard_fact_does_not_trigger_extra_critic(self):
        plan = self.router.route(
            "What is the boiling point of water?",
            frozenset({"reasoning"}),
        )
        self.assertEqual(plan.primary.role, "reasoning")
        self.assertFalse(plan.needs_critique)

    def test_intent_brief_is_marked_untrusted(self):
        plan = self.router.route(
            "Design and implement a complete mobile application.",
            frozenset({"reasoning", "coding"}),
        )
        text = self.router.compose_instructions(
            "BASE POLICY",
            plan,
            '{"intent":"example"}',
        )
        self.assertIn("BASE POLICY", text)
        self.assertIn("untrusted", text.lower())
        self.assertIn("ACTIVE SPECIALIST: coding", text)


if __name__ == "__main__":
    unittest.main()
