"""Run a small live smoke benchmark against Omnitrix's configured free Reasoning model.

This is an opt-in diagnostic, not a proof of model accuracy. It makes one provider
request per selected case and prints responses for human review. Never include
private, personal, or confidential content in benchmark prompts.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.agents.registry import AgentRegistry
from core.models.loader import ModelConfigLoader
from core.models.messages import MessageRole, ModelMessage, ModelRequest
from core.models.providers.bootstrap import build_adapter_registry
from core.orchestrator.omnitrix import Omnitrix


DEFAULT_CONFIG = ROOT / "config" / "mobile.models.json"
DEFAULT_CASES = ROOT / "benchmarks" / "reasoning_v1.json"
AGENT_CONFIG = ROOT / "config" / "agents.json"


def load_cases(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("Benchmark file must be a version 1 JSON object.")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark file must contain a non-empty cases list.")
    seen: set[str] = set()
    for item in cases:
        if not isinstance(item, dict):
            raise ValueError("Each benchmark case must be an object.")
        case_id, prompt = item.get("id"), item.get("prompt")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise ValueError("Each benchmark case needs a unique non-empty id.")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Benchmark case {case_id!r} needs a prompt.")
        signals = item.get("review_signals", [])
        if not isinstance(signals, list) or not all(isinstance(x, str) for x in signals):
            raise ValueError(f"Benchmark case {case_id!r} has invalid review_signals.")
        seen.add(case_id)
    return cases


def run(config_path: Path, cases_path: Path, limit: int) -> dict[str, Any]:
    if not os.getenv("OPENROUTER_API_KEY"):
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set in this runtime. "
            "Configure it in the environment where this command is running; do not paste it into chat."
        )

    registry = ModelConfigLoader().load(config_path)
    model = registry.get("reasoning-nemotron-super-free")
    if model is None or not model.enabled:
        raise RuntimeError("The configured Reasoning model is missing or disabled.")
    if model.provider != "openrouter" or not model.model_id or not model.model_id.endswith(":free"):
        raise RuntimeError("Refusing live benchmark: the selected model is not explicitly a :free OpenRouter route.")
    if model.metadata.get("estimated_cost_usd") != 0:
        raise RuntimeError("Refusing live benchmark: model profile does not declare zero estimated cost.")

    adapters = build_adapter_registry(registry)
    adapter = adapters.get(model.name)
    if not adapter.is_available():
        raise RuntimeError("OpenRouter adapter reports that no API key is configured.")
    reasoning = AgentRegistry.load(AGENT_CONFIG).get("reasoning")
    if reasoning is None or not reasoning.enabled:
        raise RuntimeError("Reasoning specialist is missing or disabled.")

    cases = load_cases(cases_path)[:limit]
    results: list[dict[str, Any]] = []
    instructions = (
        Omnitrix.DEFAULT_INSTRUCTIONS
        + "\n\nACTIVE SPECIALIST: reasoning\n"
        + reasoning.instructions
    )

    for case in cases:
        request = ModelRequest(
            messages=(ModelMessage(role=MessageRole.USER, content=case["prompt"]),),
            instructions=instructions,
        )
        started = time.perf_counter()
        response = adapter.generate(request)
        elapsed = round(time.perf_counter() - started, 3)
        answer = response.content
        lowered = answer.casefold()
        signals = case.get("review_signals", [])
        results.append({
            "case_id": case["id"],
            "latency_seconds": elapsed,
            "provider_reported": response.provider,
            "model_reported": response.model,
            "review_signals_found": [signal for signal in signals if signal.casefold() in lowered],
            "review_signals_missing": [signal for signal in signals if signal.casefold() not in lowered],
            "usage": response.usage,
            "response": answer,
        })

    return {
        "benchmark_version": 1,
        "configured_model": model.model_id,
        "provider": model.provider,
        "case_count": len(results),
        "note": "Review signals are lexical hints only. Human review is required; this is not an accuracy score.",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--limit", type=int, default=3, help="Maximum cases to run (default: 3 to conserve free quota).")
    parser.add_argument("--output", type=Path, help="Optional path to save the JSON report.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1.")

    try:
        report = run(args.config, args.cases, args.limit)
    except Exception as exc:
        print(f"Benchmark failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
