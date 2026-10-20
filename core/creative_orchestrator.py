"""Shared, persisted production plans and task coordination for Creative Studio.

This module plans and tracks assignments. It does not dispatch agents or claim that
a renderer/model ran. Worker-reported artifacts remain unverified until separate QA.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, Mapping

from core.creative_production import ProductionContractError

_LOCK = threading.RLock()
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
_STATES = {"pending", "ready", "running", "succeeded", "failed", "blocked"}
_TRANSITIONS = {
    "pending": {"ready", "blocked", "failed"},
    "ready": {"running", "blocked", "failed"},
    "running": {"succeeded", "failed", "blocked"},
    "failed": {"ready", "blocked"},
    "blocked": {"ready", "failed"},
    "succeeded": set(),
}
_RENDERERS = {"canvas-2d", "manim", "blender", "rigged-2d", "existing-assets"}
_MAX_SCENES = 12
_MAX_ASSETS = 100


def _text(value: Any, name: str, limit: int, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ProductionContractError(name + " must be text.")
    result = value.strip()
    if required and not result:
        raise ProductionContractError(name + " is required.")
    if len(result) > limit:
        raise ProductionContractError(name + " exceeds its length limit.")
    return result


def _safe_id(value: Any, name: str) -> str:
    result = _text(value, name, 100, True)
    if not _ID.fullmatch(result):
        raise ProductionContractError(name + " must use letters, numbers, underscores or hyphens.")
    return result


def _root(root: str | Path | None = None) -> Path:
    base = Path(root) if root is not None else Path(
        os.environ.get("OMNITRIX_ARTIFACT_DIR", "/tmp/omnitrix-artifacts")
    )
    return base.expanduser() / "creative-production-jobs"


def _job_path(job_id: str, root: str | Path | None = None) -> Path:
    job_id = _safe_id(job_id, "job_id")
    return _root(root) / (job_id + ".json")


def _save(plan: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".production-job-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _load(job_id: str, root: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    path = _job_path(job_id, root)
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError("Production job was not found.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Production job manifest could not be read safely.") from exc
    if not isinstance(plan, dict) or plan.get("job_id") != job_id or not isinstance(plan.get("tasks"), list):
        raise RuntimeError("Production job manifest failed its integrity shape check.")
    return plan, path


def _renderer_for(purpose: str) -> str:
    lowered = purpose.lower()
    if any(term in lowered for term in ("3d", "three-dimensional", "orbit camera", "solid model")):
        return "blender"
    if any(term in lowered for term in (
        "science", "scientific", "physics", "chemistry", "equation", "graph",
        "vector", "induction", "molecule", "math", "mathematical",
    )):
        return "manim"
    if any(term in lowered for term in ("character", "walk cycle", "wave", "human action", "gesture")):
        return "rigged-2d"
    return "canvas-2d"


def _validate_assets(raw_assets: Any) -> list[dict[str, Any]]:
    if raw_assets is None:
        return []
    if not isinstance(raw_assets, list) or len(raw_assets) > _MAX_ASSETS:
        raise ProductionContractError("assets must be a list with at most 100 entries.")
    seen: set[str] = set()
    assets = []
    for item in raw_assets:
        if not isinstance(item, dict):
            raise ProductionContractError("Every asset entry must be an object.")
        asset_id = _safe_id(item.get("asset_id"), "asset_id")
        if asset_id in seen:
            raise ProductionContractError("Asset IDs must be unique; reuse existing IDs instead of duplicating assets.")
        seen.add(asset_id)
        assets.append({
            "asset_id": asset_id,
            "kind": _text(item.get("kind", "unknown"), "asset kind", 60, True),
            "uri": _text(item.get("uri", ""), "asset URI", 1000),
            "source_url": _text(item.get("source_url", ""), "asset source URL", 2000),
            "license": _text(item.get("license", ""), "asset license", 200),
            "reuse_policy": "reuse-existing",
            "verification_status": "unverified",
            "owner_task_id": _text(item.get("owner_task_id", "existing-library"), "asset owner", 100, True),
        })
    return assets


def create_shared_production_plan(
    payload: Mapping[str, Any], *, root: str | Path | None = None,
) -> dict[str, Any]:
    """Create and persist a single shared scene/task/artifact manifest."""
    if not isinstance(payload, Mapping):
        raise ProductionContractError("Production plan payload must be an object.")
    brief = _text(payload.get("brief", payload.get("objective", "")), "brief", 4000, True)
    job_id = _safe_id(payload.get("job_id") or ("creative-" + uuid.uuid4().hex[:20]), "job_id")
    assets = _validate_assets(payload.get("assets"))
    known_assets = {item["asset_id"] for item in assets}
    raw_scenes = payload.get("scenes")
    if raw_scenes is None:
        raw_scenes = [{"scene_id": "scene-01", "purpose": brief, "duration_seconds": 5}]
    if not isinstance(raw_scenes, list) or not raw_scenes or len(raw_scenes) > _MAX_SCENES:
        raise ProductionContractError("scenes must contain between 1 and 12 scene objects.")

    scenes = []
    scene_ids: set[str] = set()
    for index, raw in enumerate(raw_scenes, start=1):
        if not isinstance(raw, dict):
            raise ProductionContractError("Every scene must be an object.")
        scene_id = _safe_id(raw.get("scene_id", "scene-" + str(index).zfill(2)), "scene_id")
        if scene_id in scene_ids:
            raise ProductionContractError("Scene IDs must be unique.")
        scene_ids.add(scene_id)
        purpose = _text(raw.get("purpose", ""), "scene purpose", 1200, True)
        duration = raw.get("duration_seconds", 5)
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 0.25 <= duration <= 180:
            raise ProductionContractError("Scene duration must be between 0.25 and 180 seconds.")
        renderer = raw.get("renderer") or _renderer_for(purpose)
        if renderer not in _RENDERERS:
            raise ProductionContractError("Unsupported renderer: " + str(renderer))
        refs = raw.get("asset_refs", [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise ProductionContractError("asset_refs must be a list of asset IDs.")
        if len(refs) != len(set(refs)) or any(ref not in known_assets for ref in refs):
            raise ProductionContractError("Each scene must reference existing unique asset IDs; do not recreate registered assets.")
        layers = raw.get("layer_refs", [])
        audio = raw.get("audio_refs", [])
        for name, values in (("layer_refs", layers), ("audio_refs", audio)):
            if not isinstance(values, list) or any(not isinstance(v, str) or len(v) > 100 for v in values):
                raise ProductionContractError(name + " must be a list of short stable IDs.")
        scene = {
            "scene_id": scene_id, "purpose": purpose,
            "duration_seconds": float(duration), "renderer": renderer,
            "camera_or_framing": _text(raw.get("camera_or_framing", "fit subject; preserve readable safe margins"), "framing", 300),
            "asset_refs": list(refs), "layer_refs": list(dict.fromkeys(layers)),
            "audio_refs": list(dict.fromkeys(audio)),
            "needs_overlays": raw.get("needs_overlays", False) is True,
            "owner_task_id": "render-" + scene_id,
            "runtime_note": {
                "canvas-2d": "Browser Canvas path; this server-side planner does not dispatch it.",
                "rigged-2d": "Shared rig module exists; manifest-to-render dispatch is not wired yet.",
                "manim": "Structured Manim route exists; executable and job availability must be probed at execution.",
                "blender": "Blender production adapter is not integrated; do not dispatch as available.",
                "existing-assets": "Consumes registered assets; does not create replacement copies.",
            }[renderer],
        }
        scenes.append(scene)

    # The task graph is shared and explicit. Every output artifact has one owner.
    tasks: list[dict[str, Any]] = []
    artifact_registry: list[dict[str, Any]] = []
    task_by_id: dict[str, dict[str, Any]] = {}

    def add_task(task_id: str, role: str, title: str, depends_on: list[str],
                 reads: list[str], writes: list[str], scene_ids: list[str] | None = None,
                 notes: str = "") -> None:
        if task_id in task_by_id:
            raise ProductionContractError("Duplicate task ID: " + task_id)
        if any(dep not in task_by_id for dep in depends_on):
            raise ProductionContractError("Task dependencies must point to tasks already in the manifest.")
        if any(item not in {a["artifact_id"] for a in artifact_registry} for item in reads):
            raise ProductionContractError("Task inputs must reference a registered artifact.")
        task = {
            "task_id": task_id, "role": role, "title": title,
            "scene_ids": list(scene_ids or []), "depends_on": list(dict.fromkeys(depends_on)),
            "reads": list(dict.fromkeys(reads)), "writes": list(dict.fromkeys(writes)),
            "status": "ready" if not depends_on else "pending",
            "evidence": [], "failure": None, "notes": notes,
            "execution_mode": "planned-not-dispatched",
            "worker_claims_are_unverified": True,
        }
        tasks.append(task)
        task_by_id[task_id] = task
        for artifact_id in task["writes"]:
            if any(a["artifact_id"] == artifact_id for a in artifact_registry):
                raise ProductionContractError("Artifact IDs must have one writer: " + artifact_id)
            artifact_registry.append({
                "artifact_id": artifact_id, "kind": "planned-output",
                "owner_task_id": task_id, "uri": None, "sha256": None,
                "verified": False, "verification_status": "not-produced",
            })

    add_task("intent-01", "intent_engineer", "Lock brief, constraints and acceptance criteria",
             [], [], ["job_brief"])
    add_task("director-01", "director", "Own the shared scene plan and dependencies",
             ["intent-01"], ["job_brief"], ["scene_plan"])
    add_task("research-01", "researcher", "Research factual claims and record source evidence",
             ["director-01"], ["scene_plan"], ["research_manifest"],
             notes="Only needed for claims requiring factual verification; source claims must include citations.")
    add_task("asset-scout-01", "asset_scout", "Find/reuse assets with source and licence metadata",
             ["director-01"], ["scene_plan"], ["asset_manifest"],
             notes="Reuse registered asset IDs first; no Pinterest scraping or automatic unlicensed reuse.")

    render_task_ids = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        dependencies = ["director-01", "asset-scout-01"]
        reads = ["scene_plan", "asset_manifest"]
        if scene["renderer"] == "manim":
            dependencies.append("research-01")
            reads.append("research_manifest")
        if scene["needs_overlays"] and scene["renderer"] not in {"manim", "existing-assets"}:
            overlay_task = "graphics-" + scene_id
            add_task(overlay_task, "graphics_engineer", "Create purposeful editable overlays for " + scene_id,
                     ["director-01", "research-01"], ["scene_plan", "research_manifest"],
                     ["graphics-" + scene_id], [scene_id],
                     notes="Only overlays; the scene renderer owns the background, main diagram and core motion.")
            dependencies.append(overlay_task)
            reads.append("graphics-" + scene_id)
        if scene["renderer"] == "manim":
            role = "renderer-manim"
        elif scene["renderer"] == "blender":
            role = "renderer-blender"
        elif scene["renderer"] == "existing-assets":
            role = "asset-composer"
        elif scene["renderer"] == "rigged-2d":
            role = "renderer-rigged-2d"
        else:
            role = "renderer-canvas-2d"
        add_task("render-" + scene_id, role, "Render scene " + scene_id,
                 dependencies, reads, ["render-" + scene_id], [scene_id],
                 notes=scene["runtime_note"] + " The assigned renderer owns this scene's core visuals.")
        render_task_ids.append("render-" + scene_id)

    add_task("editor-01", "compositor", "Assemble registered scene outputs without recreating them",
             render_task_ids + ["asset-scout-01"], ["asset_manifest"] + ["render-" + s["scene_id"] for s in scenes],
             ["edit_manifest", "draft_video"],
             notes="Preserve every scene/audio reference; no static filler when a render fails.")
    add_task("critic-01", "critic", "Inspect the actual final render and record frame/time-specific defects",
             ["editor-01"], ["draft_video", "edit_manifest"], ["qa_report"],
             notes="QA output is not independent verification until the reviewer inspects the produced artifact.")

    plan = {
        "schema_version": 1, "job_id": job_id, "revision": 1,
        "brief": brief, "status": "planned",
        "design_system": {
            "spend_mode": "zero_cost",
            "anti_slop": ["no fake metrics or filler labels", "no decorative motion without a communication purpose",
                          "no duplicated scene assets", "no unlicensed media", "no unsupported effects"],
            "accessibility": ["legible contrast", "safe text margins", "readable timing"],
        },
        "scenes": scenes, "assets": assets, "artifact_registry": artifact_registry,
        "tasks": tasks,
        "coordination_contract": {
            "single_source_of_truth": True, "manifest_revision": 1,
            "exclusive_task_ownership": True, "exclusive_artifact_writers": True,
            "parallelism": "independent tasks only",
            "handoffs_require_artifact_ids": True,
            "workers_must_report_manifest_revision": True,
            "tool_outputs_untrusted_until_verified": True,
            "no_automatic_tool_execution": True,
            "no_paid_or_external_side_effects_without_approval": True,
            "completion_requires_final_artifact_verification": True,
        },
        "release_gate": {
            "draft_artifact_exists": False, "technical_validation": False,
            "final_visual_review": False, "audio_review_if_expected": False,
            "source_license_review": False, "final_verified": False,
        },
        "created_at_epoch": None,
    }
    path = _job_path(job_id, root)
    with _LOCK:
        if path.exists():
            raise ProductionContractError("A production job with this ID already exists.")
        _save(plan, path)
    return plan


def get_shared_production_plan(job_id: str, *, root: str | Path | None = None) -> dict[str, Any]:
    with _LOCK:
        plan, _ = _load(job_id, root)
        return plan


def update_shared_production_task(
    job_id: str, task_id: str, payload: Mapping[str, Any], *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Record a worker handoff with strict dependency and output ownership checks."""
    if not isinstance(payload, Mapping):
        raise ProductionContractError("Task update must be an object.")
    target = _safe_id(task_id, "task_id")
    state = payload.get("state")
    if state not in _STATES:
        raise ProductionContractError("Unsupported task state.")
    with _LOCK:
        plan, path = _load(job_id, root)
        if isinstance(payload.get("manifest_revision"), bool) or payload.get("manifest_revision") != plan["revision"]:
            raise ProductionContractError("Manifest revision mismatch; reload the shared plan before updating task state.")
        task_map = {task["task_id"]: task for task in plan["tasks"]}
        task = task_map.get(target)
        if task is None:
            raise FileNotFoundError("Production task was not found.")
        current = task["status"]
        if state != current and state not in _TRANSITIONS[current]:
            raise ProductionContractError("Invalid task transition: " + current + " -> " + state + ".")
        if state == "ready" and any(task_map[dep]["status"] != "succeeded" for dep in task["depends_on"]):
            raise ProductionContractError("A task dependencies must all succeed before it can become ready.")
        if state == "running":
            if any(task_map[dep]["status"] != "succeeded" for dep in task["depends_on"]):
                raise ProductionContractError("A task cannot run until every dependency has succeeded.")
        if state == "succeeded":
            if current != "running":
                raise ProductionContractError("A task must be running before it can succeed.")
            if any(task_map[dep]["status"] != "succeeded" for dep in task["depends_on"]):
                raise ProductionContractError("A task cannot succeed until every dependency has succeeded.")
            evidence = payload.get("evidence")
            if not isinstance(evidence, list) or not evidence or any(not isinstance(x, str) or not x.strip() for x in evidence):
                raise ProductionContractError("Success requires concrete evidence references.")
            outputs = payload.get("outputs")
            if not isinstance(outputs, list):
                raise ProductionContractError("Success requires output records for every owned artifact.")
            expected = set(task["writes"])
            actual = set()
            for output in outputs:
                if not isinstance(output, dict):
                    raise ProductionContractError("Each output record must be an object.")
                artifact_id = _safe_id(output.get("artifact_id"), "artifact_id")
                uri = _text(output.get("uri", ""), "artifact URI", 2000, True)
                if artifact_id in actual:
                    raise ProductionContractError("Output artifact IDs must be unique.")
                actual.add(artifact_id)
                artifact = next((item for item in plan["artifact_registry"] if item["artifact_id"] == artifact_id), None)
                if artifact is None or artifact["owner_task_id"] != target:
                    raise ProductionContractError("A task may report only artifacts it owns.")
                artifact["uri"] = uri
                artifact["kind"] = _text(output.get("kind", "worker-output"), "artifact kind", 80, True)
                digest = _text(output.get("sha256", ""), "artifact sha256", 64)
                if digest and not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                    raise ProductionContractError("artifact sha256 must be a 64-character hexadecimal digest.")
                artifact["sha256"] = digest.lower() if digest else None
                artifact["verified"] = False
                artifact["verification_status"] = "reported-unverified"
            if actual != expected:
                raise ProductionContractError("Reported outputs must exactly match the task's owned artifact IDs.")
            task["evidence"] = [x[:500] for x in evidence[:20]]
        if state == "failed":
            reason = _text(payload.get("failure", ""), "failure reason", 500, True)
            task["failure"] = reason
        task["status"] = state
        if state != "failed":
            task["failure"] = None
        plan["revision"] += 1
        plan["coordination_contract"]["manifest_revision"] = plan["revision"]
        for candidate in plan["tasks"]:
            if candidate["status"] == "pending" and all(task_map[dep]["status"] == "succeeded" for dep in candidate["depends_on"]):
                candidate["status"] = "ready"
        statuses = [candidate["status"] for candidate in plan["tasks"]]
        if any(value == "failed" for value in statuses):
            plan["status"] = "needs_repair"
        elif all(value == "succeeded" for value in statuses):
            plan["status"] = "awaiting_independent_verification"
        elif any(value == "running" for value in statuses):
            plan["status"] = "in_progress"
        else:
            plan["status"] = "planned"
        plan["release_gate"]["draft_artifact_exists"] = any(
            item["artifact_id"] == "draft_video" and bool(item["uri"]) for item in plan["artifact_registry"]
        )
        # Worker-reported artifacts can never set these final verification flags.
        plan["release_gate"]["final_verified"] = False
        _save(plan, path)
        return plan
