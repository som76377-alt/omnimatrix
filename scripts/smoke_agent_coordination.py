"""Live integration smoke for synchronized, role-bounded Omnitrix agents.

Uses one synthetic task only. Tool execution is disabled; no repository files are
written. Groq routes are eligible only in this run when the explicit quota gate is true.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.agents.registry import AgentRegistry
from core.contracts import BudgetLimits
from core.conversation import Conversation
from core.models.loader import ModelConfigLoader
from core.models.providers.bootstrap import build_adapter_registry
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission


CONFIG = ROOT / "config" / "mobile.models.json"
AGENT_CONFIG = ROOT / "config" / "agents.json"
REQUIRED_SUPPORT = {"research", "subject_solver"}
REQUIRED_STAGES = {"orchestrator", "support_research", "support_subject_solver", "answer_generation", "critic"}
PROMPT = (
    "Research and implement a small Python demonstration explaining the physics of how "
    "an induction cooktop heats a metal pan. Work as one coordinated team: research must "
    "separate retrieved evidence from unsupported claims; the subject solver must validate "
    "the changing magnetic field -> induced currents -> resistive heating causal chain; "
    "the coding lead must integrate their findings into one coherent response with a minimal "
    "example and testable acceptance checks. Use only actual retrieved evidence and actual "
    "tool results. If retrieval or execution is unavailable, state that limitation. Do not "
    "modify repository files and do not invoke Cline for this read-only coordination probe."
)


def fail(message: str) -> None:
    raise SystemExit("FAIL: " + message)


def main() -> int:
    if os.getenv("GROQ_FREE_QUOTA_CONFIRMED", "").strip().lower() != "true":
        fail("the live probe requires explicit GROQ_FREE_QUOTA_CONFIRMED=true; no inference was sent.")

    registry = ModelConfigLoader().load(CONFIG)
    adapters = build_adapter_registry(registry)
    agents = AgentRegistry.load(AGENT_CONFIG)
    expected_profiles = {model.name: model for model in registry.list_enabled()}
    if len(expected_profiles) != 6:
        fail(f"expected six registered model profiles, found {len(expected_profiles)}.")

    runtime = Omnitrix(
        registry=registry,
        adapter_registry=adapters,
        agent_registry=agents,
        tool_registry=build_tool_registry(enable_cline=False),
        tool_permission=ToolPermission.from_capabilities(set()),
        budget_limits=BudgetLimits(
            max_model_calls=18,
            max_tool_calls=0,
            max_estimated_cost_usd=0.0,
            spend_mode="user_provided_free_quota",
        ),
    )

    answer = runtime.chat(Conversation(), PROMPT)
    trace = runtime.last_execution_trace or {}
    activities = trace.get("activity") or []
    if not answer.strip():
        fail("the lead model returned an empty answer.")
    stages = {item.get("stage") for item in activities if isinstance(item, dict)}
    missing_stages = REQUIRED_STAGES - stages
    if missing_stages:
        fail("required coordination stages missing: " + ", ".join(sorted(missing_stages)))

    coordination = trace.get("coordination") or {}
    if coordination.get("status") != "validated" or not coordination.get("coordinator_stage_ran"):
        fail("the coordinator did not return a validated shared work plan.")
    assigned = set(coordination.get("assigned_roles") or [])
    if assigned != REQUIRED_SUPPORT:
        fail("expected exactly research and subject_solver support roles; got " + repr(sorted(assigned)))
    statuses = coordination.get("support_statuses") or {}
    if set(statuses) != REQUIRED_SUPPORT or any(statuses.get(role) != "result_received" for role in REQUIRED_SUPPORT):
        fail("not every assigned specialist returned a finding: " + json.dumps(statuses, sort_keys=True))
    if list(coordination.get("integration_order") or []) == []:
        fail("the coordinator did not provide an integration order.")

    used_profiles: set[str] = set()
    identity_failures: list[str] = []
    report = []
    for item in activities:
        if not isinstance(item, dict):
            continue
        profile_name = item.get("configured_name")
        if not isinstance(profile_name, str) or profile_name not in expected_profiles:
            identity_failures.append(f"unknown configured profile for stage {item.get('stage')}")
            continue
        profile = expected_profiles[profile_name]
        reported_model = item.get("model")
        identity_source = item.get("identity_source")
        if identity_source != "provider_response":
            identity_failures.append(
                f"{item.get('stage')}: provider did not independently report model identity ({identity_source})"
            )
        elif not isinstance(reported_model, str) or reported_model.strip().casefold() != str(profile.model_id).strip().casefold():
            identity_failures.append(
                f"{item.get('stage')}: configured {profile.model_id}, provider reported {reported_model}"
            )
        used_profiles.add(profile_name)
        report.append({
            "stage": item.get("stage"),
            "role": item.get("role"),
            "profile": profile_name,
            "provider": item.get("provider"),
            "provider_reported_model": reported_model,
            "identity_source": identity_source,
            "latency_seconds": item.get("latency_seconds"),
        })

    if identity_failures:
        fail("model identity could not be verified: " + "; ".join(identity_failures))
    if used_profiles != set(expected_profiles):
        fail(
            "expected all six distinct model profiles to contribute to this single coordinated run; "
            f"observed {len(used_profiles)}/6: {sorted(used_profiles)}"
        )

    if not any(item.get("stage") == "critic" for item in activities):
        fail("the independent final critic stage did not run.")
    print(json.dumps({
        "status": "passed",
        "coordination_status": coordination.get("status"),
        "support_statuses": statuses,
        "integration_order": coordination.get("integration_order"),
        "unique_model_profiles": len(used_profiles),
        "answer_characters": len(answer),
        "tool_calls": len(trace.get("tool_executions") or []),
        "activity": report,
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
