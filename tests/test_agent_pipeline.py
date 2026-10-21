import json
from dataclasses import replace
import unittest
from unittest.mock import patch
from pathlib import Path

from core.agents.registry import AgentRegistry
from core.agents.router import AgentRouter
from core.conversation import Conversation
from core.models.adapters import AdapterRegistry
from core.models.base import ModelAdapter, ModelRequestError, ModelResponse, ModelResponseError
from core.models.messages import ModelRequest
from core.models.loader import ModelConfigLoader
from core.models.providers.bootstrap import build_adapter_registry
from core.models.registry import ModelDefinition, ModelRegistry
from core.contracts import BudgetLimits
from core.policy.quality import QUALITY_POLICY_MARKER
from core.orchestrator.omnitrix import Omnitrix, _safe_provider_failure_reason


ROOT = Path(__file__).resolve().parents[1]
AGENT_CONFIG = ROOT / "config" / "agents.json"


def agents_for_test_models(overrides):
    """Keep tests aligned to their intentionally different model fixtures."""
    source = AgentRegistry.load(AGENT_CONFIG)
    definitions = [
        replace(
            agent,
            preferred_models=tuple(overrides.get(agent.role, agent.preferred_models)),
        )
        for agent in source.list_enabled()
    ]
    return AgentRegistry(
        definitions,
        enabled=source.enabled,
        intent_mode=source.intent_mode,
        critic_mode=source.critic_mode,
    )


class ScriptedAdapter(ModelAdapter):
    def __init__(self, responses, name="test-live-model", provider="test"):
        self.responses = list(responses)
        self.requests: list[ModelRequest] = []
        self._name = name
        self._provider = provider

    @property
    def name(self) -> str:
        return self._name

    @property
    def provider(self) -> str:
        return self._provider

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Unexpected extra model call.")
        return ModelResponse(
            content=self.responses.pop(0),
            model=self.name,
            provider=self.provider,
        )


def make_intent_brief():
    return json.dumps({
        "intent": "Explain the physical mechanism behind induction heating.",
        "deliverable": "A clear causal explanation with a checked derivation.",
        "constraints": ["Keep the explanation scientifically accurate."],
        "assumptions": [],
        "steps": ["Explain the changing magnetic field.", "Explain induced currents and resistive heating."],
        "acceptance_criteria": ["Distinguish induction in the pan from the cooktop electronics."],
        "domain": "physics",
        "complexity": "complex",
    })


class SpecialistPipelineTests(unittest.TestCase):
    def build_omnitrix(self, responses):
        models = ModelRegistry()
        models.register(ModelDefinition(
            name="test-live-model",
            provider="test",
            model_id="test-live-model-v1",
            capabilities=frozenset({"reasoning", "coding", "research"}),
            context_window=32000,
            metadata={"cost_class": "demo", "estimated_cost_usd": 0},
        ))
        adapter = ScriptedAdapter(responses)
        adapters = AdapterRegistry()
        adapters.register(adapter)
        agent_registry = AgentRegistry.load(AGENT_CONFIG)
        return (
            Omnitrix(
                registry=models,
                adapter_registry=adapters,
                agent_registry=agent_registry,
            ),
            adapter,
        )

    def test_complex_physics_request_runs_intent_specialist_and_critic(self):
        draft = "The changing coil field induces currents in the pan, and resistance converts electrical energy into heat."
        corrected = "The changing coil current creates a changing magnetic field. This induces circulating currents in the conductive pan; the pan's electrical resistance converts that energy into heat."
        critique = json.dumps({
            "verdict": "revise",
            "issues": ["Make the field-to-current-to-heat causal chain explicit."],
            "corrected_answer": corrected,
        })
        omnitrix, adapter = self.build_omnitrix([make_intent_brief(), draft, critique])

        result = omnitrix.chat(
            Conversation(),
            "Derive the causal physics of how an induction stove heats a metal pan, and check the explanation.",
        )

        self.assertEqual(result, corrected)
        self.assertEqual(len(adapter.requests), 3)
        self.assertTrue(all(
            request.instructions and QUALITY_POLICY_MARKER in request.instructions
            for request in adapter.requests
        ))
        trace = omnitrix.last_execution_trace
        self.assertIsNotNone(trace)
        activity = trace["activity"]
        self.assertEqual(
            [item["stage"] for item in activity],
            ["intent_engineer", "answer_generation", "critic"],
        )
        self.assertEqual(activity[1]["role"], "subject_solver")
        self.assertEqual(activity[1]["model"], "test-live-model")
        self.assertEqual(activity[2]["review_status"], "revised")
        self.assertEqual(adapter.requests[0].tools, ())
        self.assertIn("ACTIVE SPECIALIST: subject_solver", adapter.requests[1].instructions)
        self.assertIn("STRUCTURED INTENT BRIEF", adapter.requests[1].instructions)
        self.assertIn("untrusted", adapter.requests[1].instructions.lower())
        self.assertEqual(adapter.requests[2].tools, ())

    def test_complex_hybrid_request_coordinates_research_and_subject_handoffs(self):
        coordinator = json.dumps({
            "objective_summary": "Create a code-rendered physics animation with the correct induction mechanism and honest evidence boundaries.",
            "work_packages": [
                {
                    "role": "research",
                    "assignment": "Check whether verifiable source retrieval is available; if not, state the exact evidence limitation and do not invent sources.",
                    "expected_output": "A short evidence/gap ledger.",
                    "acceptance_criteria": [
                        "Mark live retrieval blocked if no actual retrieval tool/results are available.",
                        "Do not fabricate citations."
                    ],
                    "depends_on": [],
                },
                {
                    "role": "subject_solver",
                    "assignment": "Specify the physically correct induction chain and misleading simplifications to avoid; use the research result only to understand evidence gaps.",
                    "expected_output": "Causal sequence, assumptions, and physics acceptance checks.",
                    "acceptance_criteria": [
                        "Distinguish the changing magnetic field, induced currents in the pan, and resistive heating.",
                        "Do not invent component motion or arbitrary object slicing."
                    ],
                    "depends_on": ["research"],
                },
            ],
            "integration_order": ["research", "subject_solver"],
            "final_acceptance_criteria": [
                "The rendered explanation follows the checked physical sequence.",
                "Unavailable source retrieval is disclosed; no fake citations are introduced.",
                "Only purposeful explanatory graphics are used."
            ],
            "cline_handoff": {"task": "", "acceptance_criteria": [], "files_in_scope": []},
        })
        research_finding = (
            "BLOCKED: this core run exposes no native live web-search tool or retrieved source results. "
            "Do not claim current source verification or invent citations."
        )
        subject_finding = (
            "Use this causal chain: alternating coil current produces a changing magnetic field; "
            "the field induces circulating currents in the conductive pan; pan resistance converts "
            "electrical energy into heat. Avoid arbitrary object slicing."
        )
        draft = "The coil's changing current creates a changing magnetic field, inducing currents in the pan; resistance heats it."
        critique = json.dumps({"verdict": "pass", "issues": [], "corrected_answer": ""})
        omnitrix, adapter = self.build_omnitrix([
            make_intent_brief(), coordinator, research_finding, subject_finding, draft, critique,
        ])

        result = omnitrix.chat(
            Conversation(),
            "Research and implement a code-rendered physics animation about electromagnetic induction.",
        )

        self.assertIn("changing magnetic field", result)
        activity = omnitrix.last_execution_trace["activity"]
        self.assertEqual(
            [item["stage"] for item in activity],
            ["intent_engineer", "orchestrator", "support_research", "support_subject_solver", "answer_generation", "critic"],
        )
        requests = adapter.requests
        self.assertIn("COORDINATOR-ASSIGNED WORK PACKAGE", requests[2].instructions)
        self.assertIn("SHARED TEAM OWNERSHIP MAP", requests[2].instructions)
        self.assertIn('"role": "subject_solver"', requests[2].instructions)
        self.assertIn("COORDINATOR-ASSIGNED WORK PACKAGE", requests[3].instructions)
        self.assertIn("SHARED TEAM OWNERSHIP MAP", requests[3].instructions)
        self.assertIn("BLOCKED: this core run exposes no native live web-search tool", requests[3].messages[-1].content)
        self.assertIn("COORDINATOR-VALIDATED WORK MAP", requests[4].instructions)
        self.assertIn("BLOCKED: this core run exposes no native live web-search tool", requests[4].instructions)
        self.assertEqual(requests[1].tools, ())
        self.assertEqual(requests[2].tools, ())
        self.assertEqual(requests[3].tools, ())
        trace = omnitrix.last_execution_trace["coordination"]
        self.assertEqual(trace["status"], "validated")
        self.assertEqual(trace["assigned_roles"], ["research", "subject_solver"])
        self.assertEqual(trace["support_statuses"], {
            "research": "result_received",
            "subject_solver": "result_received",
        })
    def test_simple_fact_skips_extra_preflight_and_critic_calls(self):
        omnitrix, adapter = self.build_omnitrix(["Water boils at about 100 °C at 1 atmosphere."])
        result = omnitrix.chat(Conversation(), "What is the boiling point of water?")
        self.assertIn("100", result)
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(len(omnitrix.last_execution_trace["activity"]), 1)
        self.assertEqual(
            omnitrix.last_execution_trace["activity"][0]["stage"],
            "answer_generation",
        )
        self.assertIn(QUALITY_POLICY_MARKER, adapter.requests[0].instructions)

    def _build_two_model_omnitrix(self, primary_responses, specialist_responses):
        models = ModelRegistry()
        models.register(ModelDefinition(
            name="omnitrix-primary",
            provider="google",
            model_id="gemini-3.8-flash",
            capabilities=frozenset({"reasoning", "coding"}),
            context_window=32000,
            metadata={
                "cost_class": "user_provided_free_quota",
                "estimated_cost_usd": 0,
                "agent_approved_cost": True,
            },
        ))
        models.register(ModelDefinition(
            name="reasoning-nemotron-super-free",
            provider="openrouter",
            model_id="nvidia/nemotron-3-super-120b-a12b:free",
            capabilities=frozenset({"reasoning", "coding"}),
            context_window=262144,
            metadata={
                "cost_class": "free",
                "estimated_cost_usd": 0,
                "agent_approved_cost": True,
                "reasoning_effort": "high",
            },
        ))
        primary_adapter = ScriptedAdapter(
            primary_responses, name="omnitrix-primary", provider="google"
        )
        specialist_adapter = ScriptedAdapter(
            specialist_responses,
            name="reasoning-nemotron-super-free",
            provider="openrouter",
        )
        adapters = AdapterRegistry()
        adapters.register(primary_adapter)
        adapters.register(specialist_adapter)
        omnitrix = Omnitrix(
            registry=models,
            adapter_registry=adapters,
            agent_registry=agents_for_test_models({
                "intent_engineer": ["omnitrix-primary", "gemini-3.8-flash"],
                "orchestrator": ["reasoning-nemotron-super-free", "nvidia/nemotron-3-super-120b-a12b:free"],
                "reasoning": ["reasoning-nemotron-super-free", "nvidia/nemotron-3-super-120b-a12b:free"],
                "coding": ["reasoning-nemotron-super-free", "nvidia/nemotron-3-super-120b-a12b:free"],
                "subject_solver": ["reasoning-nemotron-super-free", "nvidia/nemotron-3-super-120b-a12b:free"],
                "research": ["reasoning-nemotron-super-free", "nvidia/nemotron-3-super-120b-a12b:free"],
                "computation": ["reasoning-nemotron-super-free", "nvidia/nemotron-3-super-120b-a12b:free"],
                "critic": ["omnitrix-primary", "gemini-3.8-flash", "reasoning-nemotron-super-free"],
            }),
            budget_limits=BudgetLimits(spend_mode="user_provided_free_quota"),
        )
        return omnitrix, primary_adapter, specialist_adapter

    def test_simple_greeting_uses_primary_model_without_spending_nemotron_request(self):
        omnitrix, primary, specialist = self._build_two_model_omnitrix(
            ["Hello! What would you like to explore?"],
            [],
        )
        result = omnitrix.chat(Conversation(), "Hello Omnitrix")
        self.assertIn("Hello", result)
        self.assertEqual(len(primary.requests), 1)
        self.assertEqual(len(specialist.requests), 0)
        trace = omnitrix.last_execution_trace
        self.assertEqual(trace["complexity"], "standard")
        self.assertEqual(len(trace["activity"]), 1)
        self.assertEqual(trace["activity"][0]["configured_name"], "omnitrix-primary")

    def test_brain_keeps_greetings_fast_and_routes_causal_questions_to_reasoning(self):
        router = AgentRouter(AgentRegistry.load(AGENT_CONFIG))
        greeting = router.route("Hello, how are you?", frozenset({"reasoning"}))
        causal_question = router.route(
            "Why does induction heat a metal pan?",
            frozenset({"reasoning"}),
        )
        self.assertEqual(greeting.complexity, "standard")
        self.assertEqual(causal_question.complexity, "complex")

    def test_primary_provider_failure_falls_back_once_to_available_reasoning_model(self):
        omnitrix, primary, specialist = self._build_two_model_omnitrix(
            [],
            ["Fallback answer from reasoning model."],
        )

        def fail_primary(request):
            primary.requests.append(request)
            raise RuntimeError("simulated provider failure")

        primary.generate = fail_primary
        result = omnitrix.chat(Conversation(), "Hello Omnitrix")

        self.assertEqual(result, "Fallback answer from reasoning model.")
        self.assertEqual(len(primary.requests), 1)
        self.assertEqual(len(specialist.requests), 1)
        activity = omnitrix.last_execution_trace["activity"]
        self.assertEqual(activity[-1]["provider"], "openrouter")
        self.assertEqual(
            activity[-1]["configured_name"],
            "reasoning-nemotron-super-free",
        )
        fallbacks = omnitrix.last_execution_trace["provider_fallbacks"]
        self.assertEqual(len(fallbacks), 1)
        self.assertEqual(fallbacks[0]["from_provider"], "google")
        self.assertEqual(fallbacks[0]["to_provider"], "openrouter")
        self.assertEqual(fallbacks[0]["reason_code"], "provider_error")
        self.assertEqual(fallbacks[0]["exception_type"], "RuntimeError")

    def test_empty_primary_answer_uses_bounded_provider_fallback(self):
        omnitrix, primary, specialist = self._build_two_model_omnitrix(
            [""],
            ["A valid fallback answer."],
        )

        result = omnitrix.chat(Conversation(), "Hello Omnitrix")

        self.assertEqual(result, "A valid fallback answer.")
        self.assertEqual(len(primary.requests), 1)
        self.assertEqual(len(specialist.requests), 1)
        fallbacks = omnitrix.last_execution_trace["provider_fallbacks"]
        self.assertEqual(len(fallbacks), 1)
        self.assertEqual(fallbacks[0]["reason_code"], "invalid_provider_response")
        self.assertEqual(fallbacks[0]["to_provider"], "openrouter")

    def test_failed_support_specialist_retries_once_on_a_different_profile(self):
        source = AgentRegistry.load(AGENT_CONFIG)
        agents = AgentRegistry(
            source.list_enabled(),
            enabled=True,
            intent_mode="off",
            critic_mode="always",
        )
        models = ModelRegistry()
        adapters = AdapterRegistry()
        for index in range(6):
            name = f"free-profile-{index}"
            models.register(ModelDefinition(
                name=name,
                provider="test",
                model_id=name,
                capabilities=frozenset({"reasoning", "coding", "research"}),
                context_window=32000,
                metadata={"cost_class": "free", "estimated_cost_usd": 0},
            ))
            adapters.register(ScriptedAdapter(
                ["The integrated answer contains the verified causal chain."],
                name=name,
                provider="test",
            ))
        omnitrix = Omnitrix(
            registry=models,
            adapter_registry=adapters,
            agent_registry=agents,
            budget_limits=BudgetLimits(
                max_model_calls=18,
                max_estimated_cost_usd=0.0,
                spend_mode="zero_cost_only",
            ),
        )
        coordinator = json.dumps({
            "objective_summary": "Produce one accurate induction-heating explainer.",
            "work_packages": [
                {
                    "role": "research",
                    "assignment": "Report evidence availability and limitations.",
                    "expected_output": "Evidence limitation.",
                    "acceptance_criteria": ["Do not invent retrieved sources."],
                    "depends_on": [],
                },
                {
                    "role": "subject_solver",
                    "assignment": "Validate the physical cause-and-effect chain.",
                    "expected_output": "Causal sequence.",
                    "acceptance_criteria": ["Include changing field, induced currents, and resistive heating."],
                    "depends_on": ["research"],
                },
            ],
            "integration_order": ["research", "subject_solver"],
            "final_acceptance_criteria": ["Preserve the checked causal chain."],
            "cline_handoff": {"task": "", "acceptance_criteria": [], "files_in_scope": []},
        })
        stage_calls = []
        failed_subject_profile = {"name": None}
        responses = {
            "orchestrator": coordinator,
            "support_research": "No external sources were retrieved by this probe; no citation is claimed.",
            "support_subject_solver": "A changing magnetic field induces currents in the pan; resistance heats the pan.",
            "critic": json.dumps({"verdict": "pass", "issues": [], "corrected_answer": ""}),
        }

        def scripted_stage(*, task, stage, model, adapter, messages, instructions, budget_guard):
            stage_calls.append((stage, model.name))
            if stage == "support_subject_solver" and failed_subject_profile["name"] is None:
                failed_subject_profile["name"] = model.name
                raise ModelRequestError("simulated first specialist route failure")
            return responses[stage]

        with patch.object(omnitrix, "_run_agent_stage", side_effect=scripted_stage):
            result = omnitrix.chat(
                Conversation(),
                "Explain the physics of how an induction cooktop heats a metal pan and verify the explanation.",
            )

        self.assertIn("verified causal chain", result)
        subject_profiles = [
            name for stage, name in stage_calls if stage == "support_subject_solver"
        ]
        self.assertEqual(len(subject_profiles), 2)
        self.assertNotEqual(subject_profiles[0], subject_profiles[1])
        trace = omnitrix.last_execution_trace["coordination"]
        self.assertEqual(trace["support_statuses"]["subject_solver"], "result_received")
        self.assertTrue(any(
            stage == "critic" for stage, _ in stage_calls
        ))

    def test_provider_429_classifies_quota_and_rate_limit_messages_safely(self):
        self.assertEqual(
            _safe_provider_failure_reason(RuntimeError(
                'Gemini request failed (429): {"error":{"message":"Requests per minute exceeded"}}'
            )),
            "http_429_rate_limited",
        )
        self.assertEqual(
            _safe_provider_failure_reason(RuntimeError(
                'Gemini request failed (429): {"error":{"message":"Daily quota exceeded"}}'
            )),
            "http_429_daily_quota",
        )
        self.assertEqual(
            _safe_provider_failure_reason(RuntimeError(
                'Gemini request failed (429): {"error":{"message":"You exceeded your current quota, check billing"}}'
            )),
            "http_429_quota_exhausted",
        )

    def test_complex_science_uses_specialist_once_and_lightweight_independent_review(self):
        draft = "A changing coil current creates a changing magnetic field, inducing currents in the conductive pan; electrical resistance converts energy into heat."
        critique = json.dumps({
            "verdict": "pass",
            "issues": [],
            "corrected_answer": "",
        })
        omnitrix, primary, specialist = self._build_two_model_omnitrix(
            [make_intent_brief(), critique],
            [draft],
        )
        result = omnitrix.chat(
            Conversation(),
            "Derive the causal physics of how an induction stove heats a metal pan, and check the explanation.",
        )
        self.assertIn("changing magnetic field", result)
        self.assertEqual(len(specialist.requests), 1)
        self.assertEqual(len(primary.requests), 2)
        activity = omnitrix.last_execution_trace["activity"]
        self.assertEqual(
            [item["stage"] for item in activity],
            ["intent_engineer", "answer_generation", "critic"],
        )
        self.assertEqual(activity[1]["provider"], "openrouter")
        self.assertEqual(activity[1]["reasoning_effort_requested"], "high")
        self.assertEqual(activity[2]["provider"], "google")

    def test_malformed_intent_json_is_rejected(self):
        self.assertIsNone(Omnitrix._validate_intent_brief("not json"))

    def test_role_preferences_select_the_coding_specialist_candidate(self):
        config_path = ROOT / "config" / "mobile.models.openrouter-free.example.json"
        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "test-gemini-key",
                "OPENROUTER_API_KEY": "test-openrouter-key",
            },
        ):
            models = ModelConfigLoader().load(config_path)
            adapters = build_adapter_registry(models)
            omnitrix = Omnitrix(
                registry=models,
                adapter_registry=adapters,
                agent_registry=agents_for_test_models({
                    "coding": ["cohere/north-mini-code:free"],
                    "orchestrator": ["nvidia/nemotron-3-super-120b-a12b:free"],
                    "reasoning": ["nvidia/nemotron-3-super-120b-a12b:free"],
                    "subject_solver": ["nvidia/nemotron-3-super-120b-a12b:free"],
                    "research": ["nvidia/nemotron-3-super-120b-a12b:free"],
                    "computation": ["nvidia/nemotron-3-super-120b-a12b:free"],
                    "critic": ["cohere/north-mini-code:free", "nvidia/nemotron-3-super-120b-a12b:free"],
                }),
                budget_limits=BudgetLimits(spend_mode="user_provided_free_quota"),
            )

            selected = omnitrix._select_agent_model(
                omnitrix.agent_registry.get("coding"),
                models.get("omnitrix-primary"),
                required_capabilities=frozenset({"coding"}),
            )

        self.assertEqual(selected.name, "cohere-north-mini-code-free")

    def test_reasoning_role_prefers_registered_openrouter_model_when_key_is_available(self):
        config_path = ROOT / "config" / "mobile.models.json"
        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "test-gemini-key",
                "OPENROUTER_API_KEY": "test-openrouter-key",
            },
        ):
            models = ModelConfigLoader().load(config_path)
            adapters = build_adapter_registry(models)
            omnitrix = Omnitrix(
                registry=models,
                adapter_registry=adapters,
                agent_registry=AgentRegistry.load(AGENT_CONFIG),
                budget_limits=BudgetLimits(spend_mode="user_provided_free_quota"),
            )

            selected = omnitrix._select_agent_model(
                omnitrix.agent_registry.get("reasoning"),
                models.get("omnitrix-primary"),
                required_capabilities=frozenset({"reasoning"}),
            )

        self.assertEqual(selected.name, "coding-minimax-m31-free")
        self.assertEqual(selected.provider, "openrouter")
        self.assertEqual(selected.model_id, "minimax/minimax-m3.1-flash:free")

    def test_coordinated_stages_use_distinct_profiles_until_available_pool_is_exhausted(self):
        # All six routes are present in the test environment, and Groq's free-quota
        # use is explicitly enabled here. This tests selection only; it sends no API calls.
        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "test-gemini-key",
                "GEMINI_API_KEY_1": "test-gemini-key-2",
                "OPENROUTER_API_KEY": "test-openrouter-key",
                "OPENROUTER_API_KEY_1": "test-openrouter-key-2",
                "GROQ_API_KEY": "test-groq-key",
                "GROQ_API_KEY_1": "test-groq-key-2",
                "GROQ_FREE_QUOTA_CONFIRMED": "true",
            },
        ):
            models = ModelConfigLoader().load(ROOT / "config" / "mobile.models.json")
            adapters = build_adapter_registry(models)
            agents = AgentRegistry.load(AGENT_CONFIG)
            omnitrix = Omnitrix(
                registry=models,
                adapter_registry=adapters,
                agent_registry=agents,
                budget_limits=BudgetLimits(spend_mode="user_provided_free_quota"),
            )
            lead = models.get("coding-minimax-m31-free")
            used = {lead.name}
            chosen = []
            for role in ("intent_engineer", "orchestrator", "research", "subject_solver", "critic"):
                selected = omnitrix._select_agent_model(
                    agents.get(role),
                    lead,
                    required_capabilities=frozenset({"reasoning"}),
                    prefer_independent_provider=role == "critic",
                    exclude_model_names=frozenset(used),
                )
                chosen.append(selected)
                used.add(selected.name)

            self.assertEqual(len(used), 6, "All six profiles should be assigned before a profile is reused.")
            self.assertEqual(
                {model.name for model in chosen},
                {model.name for model in models.list_enabled()} - {lead.name},
            )
            self.assertNotEqual(chosen[-1].provider, lead.provider)

    def test_groq_profiles_remain_gated_without_explicit_free_quota_confirmation(self):
        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "test-gemini-key",
                "GEMINI_API_KEY_1": "test-gemini-key-2",
                "OPENROUTER_API_KEY": "test-openrouter-key",
                "OPENROUTER_API_KEY_1": "test-openrouter-key-2",
                "GROQ_API_KEY": "test-groq-key",
                "GROQ_API_KEY_1": "test-groq-key-2",
                "GROQ_FREE_QUOTA_CONFIRMED": "false",
            },
        ):
            models = ModelConfigLoader().load(ROOT / "config" / "mobile.models.json")
            adapters = build_adapter_registry(models)
            agents = AgentRegistry.load(AGENT_CONFIG)
            omnitrix = Omnitrix(
                registry=models,
                adapter_registry=adapters,
                agent_registry=agents,
                budget_limits=BudgetLimits(spend_mode="user_provided_free_quota"),
            )
            selected = omnitrix._select_agent_model(
                agents.get("research"),
                models.get("omnitrix-primary"),
                required_capabilities=frozenset({"reasoning"}),
            )
            self.assertNotIn(selected.provider, {"groq"})
            groq = models.get("groq-gpt-oss-120b")
            cost_class, estimate = omnitrix._effective_model_cost(groq)
            self.assertEqual(cost_class, "provider_billed_usage")
            self.assertEqual(estimate, 0.001)

    def test_confirmed_groq_free_quota_uses_zero_cost_budget_class(self):
        with patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "test-gemini-key",
                "GEMINI_API_KEY_1": "test-gemini-key-2",
                "OPENROUTER_API_KEY": "test-openrouter-key",
                "OPENROUTER_API_KEY_1": "test-openrouter-key-2",
                "GROQ_API_KEY": "test-groq-key",
                "GROQ_API_KEY_1": "test-groq-key-2",
                "GROQ_FREE_QUOTA_CONFIRMED": "true",
            },
        ):
            models = ModelConfigLoader().load(ROOT / "config" / "mobile.models.json")
            adapters = build_adapter_registry(models)
            agents = AgentRegistry.load(AGENT_CONFIG)
            omnitrix = Omnitrix(
                registry=models,
                adapter_registry=adapters,
                agent_registry=agents,
                budget_limits=BudgetLimits(spend_mode="user_provided_free_quota"),
            )
            selected = omnitrix._select_agent_model(
                agents.get("research"),
                models.get("omnitrix-primary"),
                required_capabilities=frozenset({"reasoning"}),
            )
            self.assertEqual(selected.name, "groq-gpt-oss-120b")
            cost_class, estimate = omnitrix._effective_model_cost(selected)
            self.assertEqual(cost_class, "user_provided_free_quota")
            self.assertEqual(estimate, 0.0)

    def test_budget_mode_prevents_free_agent_from_routing_to_user_quota_model(self):
        models = ModelRegistry()
        models.register(ModelDefinition(
            name="openrouter-free",
            provider="openrouter",
            model_id="nvidia/nemotron-3-super-120b-a12b:free",
            capabilities=frozenset({"reasoning", "coding"}),
            metadata={"cost_class": "free", "estimated_cost_usd": 0},
        ))
        models.register(ModelDefinition(
            name="cohere-free",
            provider="openrouter",
            model_id="cohere/north-mini-code:free",
            capabilities=frozenset({"reasoning", "coding"}),
            metadata={"cost_class": "free", "estimated_cost_usd": 0},
        ))
        models.register(ModelDefinition(
            name="google-free-quota",
            provider="google",
            model_id="gemini-3.8-flash",
            capabilities=frozenset({"reasoning", "coding"}),
            metadata={
                "cost_class": "user_provided_free_quota",
                "estimated_cost_usd": 0,
                "agent_approved_cost": True,
            },
        ))
        adapters = AdapterRegistry()
        adapters.register(ScriptedAdapter([], name="openrouter-free", provider="openrouter"))
        adapters.register(ScriptedAdapter([], name="cohere-free", provider="openrouter"))
        adapters.register(ScriptedAdapter([], name="google-free-quota", provider="google"))
        omnitrix = Omnitrix(
            registry=models,
            adapter_registry=adapters,
            agent_registry=AgentRegistry.load(AGENT_CONFIG),
            budget_limits=BudgetLimits(spend_mode="zero_cost_only"),
        )
        critic = omnitrix.agent_registry.get("critic")
        selected = omnitrix._select_agent_model(
            critic,
            models.get("openrouter-free"),
            required_capabilities=frozenset({"reasoning"}),
            prefer_independent_provider=True,
        )
        # An explicit cross-model approval is not allowed to bypass the active
        # runtime spend mode. Google free-quota access is not zero-cost-only.
        self.assertEqual(selected.name, "cohere-free")
        self.assertNotEqual(selected.name, "openrouter-free")

    def test_invalid_critic_payload_preserves_original_answer(self):
        answer, status = Omnitrix._apply_critic_result(
            '{"verdict":"revise","issues":"not-an-array","corrected_answer":"bad"}',
            "original answer",
        )
        self.assertEqual(answer, "original answer")
        self.assertNotEqual(status, "revised")


if __name__ == "__main__":
    unittest.main()
