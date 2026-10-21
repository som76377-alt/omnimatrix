"""Role boundaries for Omnitrix specialist stages and tool execution.

Prompt rules improve behavior; this module also enforces the tool boundary at
runtime. Unknown roles fail closed. These boundaries limit explicit tool access
and assigned work, not the hidden internal reasoning of a language model.
"""
from __future__ import annotations

from typing import Final

ROLE_TOOL_ALLOWLIST: Final[dict[str, frozenset[str]]] = {
    "intent_engineer": frozenset(),
    "reasoning": frozenset(),
    "coding": frozenset({"cline.coding", "workspace.inspect"}),
    "subject_solver": frozenset({"calculator", "manim_scientific_diagram"}),
    # A native web-search tool is not currently registered in the core tool registry.
    "research": frozenset(),
    "computation": frozenset({"calculator"}),
    "critic": frozenset(),
}

ROLE_BOUNDARIES: Final[dict[str, str]] = {
    "intent_engineer": (
        "ONLY translate the request and relevant conversation context into the required "
        "validated task brief. Do not answer the user, solve the task, research, write code, "
        "call tools, or invent requirements. Pass the brief to the coordinator."
    ),
    "reasoning": (
        "OWN general logic, trade-offs, causal analysis, and decision rationale only when "
        "assigned. Do not claim to have browsed sources, edited files, run code, performed "
        "exact calculations, or reviewed a final artifact unless a corresponding tool/result "
        "actually exists. Hand off domain-specific work to the assigned specialist."
    ),
    "coding": (
        "OWN software architecture decisions, implementation requirements, debugging strategy, "
        "and acceptance tests. For substantial repository edits, use cline.coding when exposed "
        "and permitted; Cline is the implementation executor. Do not claim a patch was applied "
        "or tests were run without tool evidence. Do not silently take over research, subject "
        "science, visual critique, or exact computation."
    ),
    "subject_solver": (
        "OWN the domain model and interpretation for mathematics, natural sciences, engineering, "
        "and other assigned subject questions. State assumptions, derivations, units, and limits. "
        "Use only the exposed calculator or structured scientific-diagram tool when applicable. "
        "Do not claim live research, code changes, or final visual QA."
    ),
    "research": (
        "OWN source discovery and claim-to-source verification only when real retrieval results "
        "are supplied by an authorized retrieval tool. In this runtime no native live web-search "
        "tool is registered in the core specialist tool list: do not invent searches, citations, "
        "or current facts; report the missing retrieval capability and work only with actual "
        "sources provided. Do not code or become the final critic."
    ),
    "computation": (
        "OWN exact arithmetic, expression evaluation, numeric cross-checks, and units for the "
        "assigned calculation. Return inputs, formula/method, result, units, and a sanity check. "
        "Use calculator when exposed. Do not replace the subject solver's physical/scientific "
        "model, perform research, modify code, or write the overall answer."
    ),
    "critic": (
        "OWN the quality gate only. Compare the actual draft/artifact and available evidence "
        "against user requirements and acceptance criteria; return the required verdict/schema. "
        "Do not implement fixes, redo the task, invent defects, claim independent review without "
        "independent execution, or use tools not exposed to the critic stage."
    ),
}


SUPPORT_ASSIGNMENTS: Final[dict[str, str]] = {
    "reasoning": (
        "Return only the highest-impact logical constraints, trade-offs, failure modes, and a "
        "counterexample/check that could falsify the proposed approach. Do not produce the final deliverable."
    ),
    "coding": (
        "As a supporting stage, map likely implementation surfaces, existing interfaces, risks, and test targets "
        "from information actually provided. Do not edit files or claim repository inspection in this analysis-only stage. "
        "The coding lead owns the implementation decision; Cline executes a bounded patch only when authorized."
    ),
    "subject_solver": (
        "Return the domain model needed by the lead: causal sequence, assumptions, equations/definitions, units, "
        "physical or logical constraints, edge cases, and claims that must remain correct. Do not produce unrelated code or the whole final artifact."
    ),
    "research": (
        "Return an evidence ledger: each material claim, actual source and date if supplied, what it supports, and unresolved gaps. "
        "If no real retrieval results or source material are available, explicitly return BLOCKED: no verifiable sources available; "
        "never fill the gap with invented citations or pretend to browse."
    ),
    "computation": (
        "Return only the assigned calculation: inputs, supported method/formula, result, units, precision, and a sanity check. "
        "Identify unsupported symbolic/numeric operations rather than approximating them silently."
    ),
}

def support_assignment_contract(role: str, lead_role: str) -> str:
    """Describe the bounded output a support role must hand to the lead."""
    assignment = SUPPORT_ASSIGNMENTS.get(
        role,
        "Return only concise, evidence-labelled findings that support the lead's decision; do not solve the entire user task."
    )
    return (
        f"LEAD ROLE: {lead_role}. Your bounded work package is: {assignment} "
        "The lead will integrate your result with other specialist findings and the original user brief. "
        "Make outputs easy to merge: label facts, assumptions, risks, unresolved questions, and any relevant interface or dependency. "
        "Do not repeat another role's output or invent unavailable capabilities."
    )

def allowed_tools_for_role(role: str) -> frozenset[str]:
    """Return the explicit allowlist; unknown roles receive no tools."""
    return ROLE_TOOL_ALLOWLIST.get(role, frozenset())

def stage_boundary_contract(stage: str) -> str:
    """Build a compact scope contract for a named specialist stage."""
    if stage.startswith("support_"):
        role = stage.removeprefix("support_")
        boundary = ROLE_BOUNDARIES.get(role, "Return only the assigned specialist finding; do not take over the whole task.")
        return (
            "SPECIALIST SCOPE ENFORCEMENT: You are a supporting specialist, not the task owner. "
            "Return concise, actionable findings only for your assigned lens. Do not deliver the "
            "whole user task, duplicate the lead's work, issue tool commands, or make claims that "
            "require unavailable tools. Label assumptions and unknowns.\n" + boundary
        )
    if stage == "intent_engineer":
        return "SPECIALIST SCOPE ENFORCEMENT: " + ROLE_BOUNDARIES["intent_engineer"]
    if stage == "critic":
        return "SPECIALIST SCOPE ENFORCEMENT: " + ROLE_BOUNDARIES["critic"]
    return "SPECIALIST SCOPE ENFORCEMENT: " + ROLE_BOUNDARIES.get(
        stage, "Stay within the assigned specialist scope; report blockers rather than silently taking over other roles."
    )
