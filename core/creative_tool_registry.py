"""Runtime-aware registry and fail-closed policy for Creative Studio tools."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Mapping

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "creative-studio-tools.json"
PAID_FLAG = "OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA"


def _default_lookup(name: str) -> str | None:
    return shutil.which(name)


def _runtime_probe(engine: Mapping[str, Any], env: Mapping[str, str],
                   executable_lookup: Callable[[str], str | None]) -> dict[str, Any]:
    engine_id = str(engine.get("id", ""))
    runtime = str(engine.get("runtime", ""))
    declared = str(engine.get("status", "catalog-only"))
    probe: dict[str, Any] = {
        "runtime_state": "not-probed",
        "runtime_available": False,
        "availability_reason": "No runtime adapter is registered for this entry.",
    }
    if runtime in {"browser", "browser-webassembly"}:
        probe.update(runtime_state="client-side", runtime_available=False,
                     availability_reason="This server cannot verify or execute a browser-side capability.")
    elif runtime == "authenticated-python-server":
        integrated = declared.startswith("integrated")
        probe.update(runtime_state="server-route" if integrated else "catalog-only",
                     runtime_available=integrated,
                     availability_reason=("Implemented server route; provider-specific features may still need configuration."
                                          if integrated else "Server route is not marked integrated in the catalogue."))
    elif runtime == "python-subprocess":
        executable = "manim" if engine_id == "manim-scientific-renderer" else engine.get("executable")
        found = executable_lookup(str(executable)) if executable else None
        probe.update(runtime_state="installed" if found else "missing-executable",
                     runtime_available=bool(found),
                     availability_reason=("Executable found on this host." if found else
                                          f"{executable or 'Required executable'} is not installed or not on PATH."))
    elif runtime == "local-development-client":
        executable = str(engine.get("executable", ""))
        found = executable_lookup(executable) if executable else None
        probe.update(runtime_state="installed" if found else "missing-executable",
                     runtime_available=bool(found),
                     availability_reason=("Client executable found on this host; model/provider access is a separate requirement."
                                          if found else f"{executable or 'Required executable'} is not installed or not on PATH."))
    elif runtime == "local-service":
        host = str(env.get(str(engine.get("host_env", "OLLAMA_HOST")), "")).strip()
        model = str(env.get(str(engine.get("model_env", "OMNITRIX_LOCAL_CODING_MODEL")), "")).strip()
        probe.update(runtime_state="configured-unverified" if host and model else "not-configured",
                     runtime_available=bool(host and model),
                     availability_reason=("Endpoint and model name are configured, but reachability and model availability are not verified."
                                          if host and model else "Set the local service endpoint and model name; availability remains unverified until probed."))
    elif runtime == "optional-remote-worker":
        env_name = str(engine.get("worker_url_env", "OMNITRIX_" + engine_id.upper().replace("-", "_") + "_WORKER_URL"))
        worker_url = str(env.get(env_name, "")).strip()
        probe.update(runtime_state="configured-unverified" if worker_url else "not-configured",
                     runtime_available=False,
                     availability_reason=("A worker URL is configured, but no authenticated health check or execution adapter is registered."
                                          if worker_url else f"No remote worker is configured ({env_name})."))
    elif runtime.startswith("server-side-gemini-interactions"):
        key_ready = bool(str(env.get("GEMINI_API_KEY", "")).strip())
        paid_enabled = str(env.get(PAID_FLAG, "")).strip().lower() == "true"
        ready = key_ready and paid_enabled
        missing = []
        if not key_ready:
            missing.append("GEMINI_API_KEY")
        if not paid_enabled:
            missing.append(PAID_FLAG + "=true")
        probe.update(runtime_state="ready-with-consent" if ready else "disabled-or-unconfigured",
                     runtime_available=ready,
                     availability_reason=("Provider key and server-side paid-media gate are configured; per-request consent and cost acknowledgement are still mandatory."
                                          if ready else "Missing configuration: " + ", ".join(missing) + "."))
    else:
        probe.update(runtime_state="catalog-only", runtime_available=False,
                     availability_reason="Catalogue entry has no verified runtime adapter.")
    return probe


def load_creative_tool_registry(
    config_path: str | Path | None = None, *,
    environ: Mapping[str, str] | None = None,
    executable_lookup: Callable[[str], str | None] | None = None,
) -> dict[str, Any]:
    """Load the catalogue and attach runtime, consent, and spend-policy facts."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    try:
        catalogue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Creative tool catalogue could not be loaded safely.") from exc
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get("engines"), list):
        raise ValueError("Creative tool catalogue must contain an engines array.")
    env = os.environ if environ is None else environ
    lookup = _default_lookup if executable_lookup is None else executable_lookup
    seen: set[str] = set()
    engines = []
    for raw in catalogue["engines"]:
        if not isinstance(raw, dict):
            raise ValueError("Every creative tool entry must be an object.")
        engine = dict(raw)
        engine_id = str(engine.get("id", "")).strip()
        if not engine_id or engine_id in seen:
            raise ValueError("Creative tool IDs must be non-empty and unique.")
        seen.add(engine_id)
        engine.update(_runtime_probe(engine, env, lookup))
        cost_class = str(engine.get("cost_class", "unknown"))
        paid = any(word in cost_class.lower() for word in ("paid", "charges", "quota-or-charges"))
        engine["requires_explicit_consent"] = paid or "consent" in str(engine.get("status", "")).lower()
        engine["requires_paid_cost_acknowledgement"] = paid
        engine["catalogue_status"] = str(engine.get("status", "catalog-only"))
        engine["integrated"] = engine["catalogue_status"].startswith("integrated")
        engines.append(engine)
    return {"ok": True, "schema_version": int(catalogue.get("schema_version", 1)),
            "product": str(catalogue.get("product", "Omnitrix Creative Studio")),
            "default_spend_mode": str(catalogue.get("default_spend_mode", "zero_cost")),
            "engines": engines}


def select_creative_tools(
    registry: Mapping[str, Any], capability: str, *,
    spend_mode: str = "zero_cost", consent: bool = False,
    paid_cost_acknowledged: bool = False, surface: str = "server",
) -> list[dict[str, Any]]:
    """Return eligible tools, never execute them; unknown policies fail closed."""
    if spend_mode not in {"zero_cost", "allow_paid"}:
        raise ValueError("spend_mode must be zero_cost or allow_paid.")
    if surface not in {"server", "browser"}:
        raise ValueError("surface must be server or browser.")
    if not isinstance(capability, str) or not capability.strip():
        raise ValueError("capability must be a non-empty string.")
    eligible = []
    for engine in registry.get("engines", []):
        if capability not in engine.get("capabilities", []):
            continue
        runtime = str(engine.get("runtime", ""))
        if surface == "browser":
            available = runtime in {"browser", "browser-webassembly"} and str(engine.get("catalogue_status", "")).startswith("integrated")
        else:
            available = bool(engine.get("runtime_available")) and runtime not in {"browser", "browser-webassembly"}
        if not available:
            continue
        cost = str(engine.get("cost_class", "unknown")).lower()
        paid = bool(engine.get("requires_paid_cost_acknowledgement")) or any(
            word in cost for word in ("paid", "charges", "quota-or-charges"))
        if paid and not (spend_mode == "allow_paid" and consent and paid_cost_acknowledged):
            continue
        if spend_mode == "zero_cost" and not (cost.startswith("zero_") or cost == "zero_incremental_cost"):
            continue
        if bool(engine.get("requires_explicit_consent")) and not consent:
            continue
        eligible.append({"id": engine["id"], "label": engine.get("label", engine["id"]),
                         "runtime": runtime, "cost_class": engine.get("cost_class", "unknown"),
                         "capabilities": list(engine.get("capabilities", [])),
                         "runtime_state": engine.get("runtime_state")})
    return eligible
