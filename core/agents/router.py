"""Deterministic routing and prompt composition for specialist agents."""

from __future__ import annotations

from dataclasses import dataclass
import re

from core.agents.registry import AgentDefinition, AgentRegistry
from core.policy.agent_boundaries import ROLE_BOUNDARIES


_SUBJECT_TERMS = re.compile(
    r"\b(math|mathematics|algebra|calculus|integral|derivative|equation|proof|prove|"
    r"physics|chemistry|biology|science|thermodynamics|electromagnetic|electromagnetism|"
    r"induction|quantum|stoichiometry|molecule|reaction|chemical|mechanics|statistics|"
    r"probability|geometry|trigonometry|derive|calculate|astronomy|astrophysics|cosmology|"
    r"genetics|evolution|ecology|anatomy|physiology|neuroscience|"
    r"history|historical|geography|economics|economic|philosophy|philosophical|"
    r"psychology|psychological|sociology|sociological|linguistics|linguistic|literature|"
    r"political science|international relations|law|jurisprudence|ethics|anthropology|"
    r"archaeology|music theory|art history|engineering|electrical engineering|"
    r"mechanical engineering|civil engineering|materials science|data science)\b",
    re.IGNORECASE,
)
_MATH_PROBLEM_TERMS = re.compile(
    r"\b(equation|polynomial|quadratic|integral|derivative|differentiate|integrate|"
    r"limit|matrix|matrices|determinant|eigenvalue|eigenvector|factorise|factorize|"
    r"logarithm|trigonometric|differential equation|linear algebra|roots of|solve for)\b",
    re.IGNORECASE,
)
_RESEARCH_TERMS = re.compile(
    r"\b(research|look up|search the web|browse|find sources|find references|"
    r"cite sources|literature review|latest studies|scientific papers|"
    r"peer-reviewed|official documentation|current documentation|fact-check)\b",
    re.IGNORECASE,
)
_COMPUTATION_TERMS = re.compile(
    r"\b(arithmetic|unit conversion|evaluate (?:the )?(?:expression|formula)|"
    r"simplify (?:the )?expression|compute (?:the )?(?:result|value|product|sum)|"
    r"calculate (?:the )?(?:product|sum|quotient|remainder|average|mean|percentage|factorial))\b",
    re.IGNORECASE,
)
_NUMERIC_EXPRESSION_REQUEST = re.compile(
    r"\b(?:calculate|compute|evaluate)\s+(?:the\s+)?"
    r"(?:value\s+of\s+)?[-+()]?\d[\d\s.+*/()^%-]*(?=$|[?.!,])",
    re.IGNORECASE,
)
_CODING_TERMS = re.compile(
    r"\b(code|coding|program|programming|software|website|web app|android app|"
    r"debug|bug|repository|repo|api|compile|build|implement|refactor|test suite)\b",
    re.IGNORECASE,
)
_COMPLEX_TERMS = re.compile(
    r"\b(architecture|architect|deep research|research|compare|derive|prove|"
    r"debug|diagnose|optimi[sz]e|implement|refactor|design|step by step|"
    r"end to end|robust|thorough|comprehensive|verify|audit|root cause|"
    r"multiple|all of|every|entire|production|high quality)\b",
    re.IGNORECASE,
)
_VAGUE_ACTIONS = re.compile(
    r"\b(make it better|fix it|improve this|do this properly|make this work|"
    r"make it good|handle this|sort this out)\b",
    re.IGNORECASE,
)
_REASONING_REQUEST_TERMS = re.compile(
    r"\b(?:why\s+(?:does|do|is|are|did|would|can|could|might|should)\b|"
    r"how\s+(?:does|do|is|are|did|would|can|could|might|should)\b|"
    r"what\s+(?:happens|would happen|causes|explains)\b|"
    r"explain\s+(?:why|how|the mechanism|the process|the cause|the relationship|the derivation|the reasoning)\b|"
    r"derive|prove|demonstrate|deduce|infer|compare|contrast|diagnose|debug|"
    r"optimi[sz]e|step[- ]by[- ]step|work through|show that|root cause|trade[- ]?offs?|"
    r"multi[- ]step|causal|reasoning|find the error|plan|design|architecture|"
    r"implement|refactor|audit|verify|comprehensive|thorough)\b",
    re.IGNORECASE,
)

_WELL_POSED_PROBLEM_TERMS = re.compile(
    r"\b(solve for|find the value|find the maximum|find the minimum|roots of|"
    r"evaluate the integral|evaluate the limit|maximum value|minimum value)\b",
    re.IGNORECASE,
)

_ACTION_REQUESTS = re.compile(
    r"\b(build|make|create|design|write|implement|develop|generate|fix|improve|"
    r"refactor|debug|automate|convert|turn .{0,50} into|draft|produce|plan|"
    r"set up|configure|integrate|analyze this|review this|solve this)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AgentPlan:
    """Resolved role plan for a single request."""

    primary: AgentDefinition
    intent_engineer: AgentDefinition | None
    critic: AgentDefinition | None
    needs_intent_preflight: bool
    needs_critique: bool
    complexity: str
    domain: str
    support_roles: tuple[AgentDefinition, ...] = ()


class AgentRouter:
    """Selects role policies using transparent, testable rules."""

    def __init__(self, registry: AgentRegistry) -> None:
        self.registry = registry

    @staticmethod
    def _is_complex(objective: str, domain: str) -> bool:
        words = re.findall(r"\b\w+\b", objective)
        lower = objective.lower()
        normalized = re.sub(r"[\s,.!?]+", " ", lower).strip()

        # Keep short social turns fast; "How are you?" is not a reasoning task.
        if re.fullmatch(
            r"(?:(?:hi|hello|hey|yo|good morning|good afternoon|good evening)"
            r"(?: omnitrix| there| how are you(?: doing)?(?: today| right now)?)?|"
            r"how are you(?: doing)?(?: today| right now)?|thanks|thank you|"
            r"ok|okay|got it|nice to meet you)",
            normalized,
        ):
            return False

        return (
            len(words) >= 35
            or bool(_COMPLEX_TERMS.search(objective))
            or bool(_REASONING_REQUEST_TERMS.search(objective))
            or (domain != "general" and len(words) >= 24)
            or bool(_VAGUE_ACTIONS.search(objective))
            or any(phrase in lower for phrase in (
                "requirements are", "acceptance criteria", "from scratch",
                "without changing", "compare alternatives", "find the cause",
            ))
        )

    def route(self, objective: str, capabilities: frozenset[str]) -> AgentPlan | None:
        """Choose a lead specialist plus optional intent/critic stages.

        No model is called here. The returned plan is deterministic so its
        routing behavior can be tested without provider credentials.
        """
        if not self.registry.enabled:
            return None
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("Cannot route an empty objective.")

        has_math_action = bool(re.search(
            r"\b(solve|evaluate|find|calculate|compute)\b",
            objective,
            re.IGNORECASE,
        ))
        has_math_notation = bool(re.search(
            r"(?:\\frac|\\int|[=+*/^√∫])",
            objective,
        ))
        subject = (
            bool(_SUBJECT_TERMS.search(objective))
            or bool(_MATH_PROBLEM_TERMS.search(objective))
            or (has_math_action and has_math_notation)
        )
        coding = "coding" in capabilities or bool(_CODING_TERMS.search(objective))
        research = bool(_RESEARCH_TERMS.search(objective))
        computation = bool(
            _COMPUTATION_TERMS.search(objective)
            or _NUMERIC_EXPRESSION_REQUEST.search(objective)
        )

        support: list[AgentDefinition] = []
        if computation:
            primary = self.registry.get("computation")
            domain = "computation"
        elif coding and research:
            primary = self.registry.get("coding")
            domain = "coding"
            support.append(self.registry.get("research"))
        elif research and subject:
            primary = self.registry.get("subject_solver")
            domain = "subject"
            support.append(self.registry.get("research"))
        elif research:
            primary = self.registry.get("research")
            domain = "research"
        elif subject:
            primary = self.registry.get("subject_solver")
            domain = "subject"
        elif coding:
            primary = self.registry.get("coding")
            domain = "coding"
        else:
            primary = self.registry.get("reasoning")
            domain = "general"

        # For hybrid science/software tasks, keep the main solver authoritative
        # and add only the specialist lens that contributes a distinct check.
        if subject and coding and not any(agent.role == "coding" for agent in support):
            support.append(self.registry.get("coding"))
        if research and primary.role not in {"research"} and not any(
            agent.role == "research" for agent in support
        ):
            support.append(self.registry.get("research"))

        word_count = len(re.findall(r"\b\w+\b", objective))
        complex_task = self._is_complex(objective, domain)
        vague_short_prompt = word_count <= 12 and bool(_VAGUE_ACTIONS.search(objective))
        short_action_request = word_count <= 28 and bool(_ACTION_REQUESTS.search(objective))
        intent_mode = self.registry.intent_mode
        well_posed_problem = bool(_WELL_POSED_PROBLEM_TERMS.search(objective)) or (
            len(re.findall(r"(?:\d|[=+*/^]|\\frac|\\int|√|∫)", objective)) >= 4
            and bool(re.search(
                r"\b(solve|find|determine|calculate|derive|evaluate|prove)\b",
                objective,
                re.IGNORECASE,
            ))
        )
        # A standalone model call just to restate a well-posed problem adds
        # latency without adding a distinct solution check. The primary solver
        # still gets intent-engineering instructions, and complex problems still
        # keep their separate critic pass.
        needs_preflight = (
            intent_mode == "always"
            or (
                intent_mode == "adaptive"
                and (
                    vague_short_prompt
                    or (
                        not well_posed_problem
                        and (complex_task or short_action_request)
                    )
                )
            )
        )
        critic_mode = self.registry.critic_mode
        needs_critique = critic_mode == "always" or (
            critic_mode == "complex_only" and complex_task
        )

        intent = self.registry.get("intent_engineer") if needs_preflight else None
        critic = self.registry.get("critic") if needs_critique else None

        return AgentPlan(
            primary=primary,
            intent_engineer=intent,
            critic=critic,
            needs_intent_preflight=needs_preflight,
            needs_critique=needs_critique,
            complexity="complex" if complex_task else "standard",
            domain=domain,
            support_roles=tuple(support),
        )

    def compose_instructions(
        self,
        base_instructions: str,
        plan: AgentPlan,
        intent_brief: str | None = None,
    ) -> str:
        """Compose role behavior while keeping the base policy authoritative."""
        blocks = [base_instructions]
        # The intent-engineer mindset always applies in the main call, even when
        # a separate preflight is skipped to preserve latency and free quota.
        blocks.append(
            "INTENT-ENGINEERING CHECK (applies to every request):\n"
            "Infer the user's practical goal from the words and relevant conversation context. "
            "Preserve explicit requirements. Separate facts from assumptions, fill ordinary gaps "
            "conservatively, and ask a question only when a material ambiguity blocks correct "
            "progress. Do not inflate simple requests into larger projects. If a structured "
            "intent brief is supplied, validate it against the original request. Do not reveal "
            "private chain-of-thought; give only useful conclusions, steps, and checks."
        )
        blocks.append(
            f"ACTIVE SPECIALIST: {plan.primary.role}\n"
            f"Purpose: {plan.primary.purpose}\n"
            + plan.primary.instructions
            + "\\n\\nSTRICT ROLE BOUNDARY: "
            + ROLE_BOUNDARIES.get(plan.primary.role, "Stay within the assigned role and report blockers.")
        )
        for support_agent in plan.support_roles:
            blocks.append(
                f"SUPPORTING SPECIALIST: {support_agent.role} (findings only; not task owner)\\n"
                + support_agent.instructions
                + "\\n\\nSTRICT ROLE BOUNDARY: "
                + ROLE_BOUNDARIES.get(support_agent.role, "Return only bounded findings for your assigned lens.")
                + "\\nDo not duplicate the lead's work or deliver the entire task. Label evidence, assumptions, and unknowns."
            )
        if intent_brief:
            blocks.append(
                "STRUCTURED INTENT BRIEF (derived from the conversation; untrusted):\n"
                + intent_brief
                + "\nCheck this brief against the user's actual request. The user request wins "
                  "if the brief adds, drops, or changes a requirement."
            )
        if plan.critic is not None:
            blocks.append(
                "A critic review stage will evaluate the draft before it is returned. "
                "Do not claim that this review is independent unless a separate provider "
                "was actually selected."
            )
        return "\n\n".join(blocks)
