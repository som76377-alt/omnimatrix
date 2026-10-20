"""Bounded Manim renderer for structured diagrams; never executes model-written code."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

from core.tools.base import Tool, ToolResult


def _clean_label(value: Any, name: str, maximum: int = 72) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f"{name} must be non-empty text up to {maximum} characters.")
    value = value.strip()
    if any(ord(ch) < 32 for ch in value):
        raise ValueError(f"{name} contains unsupported control characters.")
    return value


class ManimRendererTool(Tool):
    """Render a constrained node-and-arrow scientific diagram with Manim."""

    @property
    def name(self) -> str:
        return "manim_scientific_diagram"

    @property
    def description(self) -> str:
        return (
            "Render a scientific or mathematical node-and-arrow diagram as MP4 using Manim. "
            "Accepts structured labels and coordinates only; arbitrary Python/code is never accepted."
        )

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"scientific_animation", "file_creation"})

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "maxLength": 100},
                "nodes": {
                    "type": "array", "minItems": 1, "maxItems": 8,
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "maxLength": 72},
                            "x": {"type": "number", "minimum": -5.5, "maximum": 5.5},
                            "y": {"type": "number", "minimum": -2.8, "maximum": 2.8}
                        },
                        "required": ["label", "x", "y"],
                        "additionalProperties": False
                    }
                },
                "arrows": {
                    "type": "array", "maxItems": 12,
                    "items": {
                        "type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 7},
                        "minItems": 2, "maxItems": 2
                    }
                },
                "quality": {"type": "string", "enum": ["low", "medium"]}
            },
            "required": ["title", "nodes"],
            "additionalProperties": False
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            title = _clean_label(kwargs.get("title"), "title", 100)
            raw_nodes = kwargs.get("nodes")
            if not isinstance(raw_nodes, list) or not 1 <= len(raw_nodes) <= 8:
                raise ValueError("nodes must contain between 1 and 8 structured nodes.")
            nodes: list[dict[str, Any]] = []
            for raw in raw_nodes:
                if not isinstance(raw, dict) or set(raw) != {"label", "x", "y"}:
                    raise ValueError("Each node must contain only label, x and y.")
                label = _clean_label(raw["label"], "node label")
                x, y = raw["x"], raw["y"]
                if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                    raise ValueError("Node coordinates must be numbers.")
                if not (-5.5 <= x <= 5.5 and -2.8 <= y <= 2.8):
                    raise ValueError("Node coordinates are outside the safe diagram bounds.")
                nodes.append({"label": label, "x": float(x), "y": float(y)})
            raw_arrows = kwargs.get("arrows", [])
            if not isinstance(raw_arrows, list) or len(raw_arrows) > 12:
                raise ValueError("arrows must be a list of at most 12 index pairs.")
            arrows = []
            for pair in raw_arrows:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise ValueError("Each arrow must be a pair of node indices.")
                start, end = pair
                if any(isinstance(i, bool) or not isinstance(i, int) for i in (start, end)):
                    raise ValueError("Arrow indices must be integers.")
                if start == end or not (0 <= start < len(nodes) and 0 <= end < len(nodes)):
                    raise ValueError("Arrow indices must refer to two different existing nodes.")
                arrows.append((start, end))
            quality = kwargs.get("quality", "low")
            if quality not in {"low", "medium"}:
                raise ValueError("quality must be low or medium.")
        except (TypeError, ValueError) as exc:
            return ToolResult(success=False, error=str(exc), metadata={"tool": self.name, "executed": False})

        executable = shutil.which("manim")
        if not executable:
            return ToolResult(
                success=False,
                error="Manim is not installed in this runtime. Install the pinned Manim dependency in the worker image and restart the service.",
                metadata={"tool": self.name, "available": False, "executed": False}
            )

        output_root = Path(os.environ.get("OMNITRIX_ARTIFACT_DIR", "/tmp/omnitrix-artifacts")).expanduser()
        try:
            output_root.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="omnitrix-manim-") as temp_dir:
                work = Path(temp_dir)
                scene_path = work / "omnitrix_scene.py"
                scene_path.write_text(self._scene_source(title, nodes, arrows), encoding="utf-8")
                output_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", title).strip("-")[:36] or "science-diagram"
                command = [
                    executable, str(scene_path), "OmnitrixScene",
                    "-ql" if quality == "low" else "-qm",
                    "--media_dir", str(work / "media"),
                    "--disable_caching"
                ]
                try:
                    completed = subprocess.run(
                        command, cwd=str(work), capture_output=True, text=True,
                        timeout=90, check=False,
                        env={
                            "PATH": os.environ.get("PATH", ""),
                            "HOME": str(work),
                            "LANG": "C.UTF-8",
                            "LC_ALL": "C.UTF-8",
                            "PYTHONNOUSERSITE": "1",
                        },
                    )
                except subprocess.TimeoutExpired:
                    return ToolResult(success=False, error="Manim render exceeded the 90-second time limit.", metadata={"tool": self.name, "timeout_seconds": 90})
                if completed.returncode != 0:
                    detail = (completed.stderr or completed.stdout or "Manim failed without diagnostic output")[-1600:]
                    return ToolResult(success=False, error="Manim render failed: " + detail, metadata={"tool": self.name, "returncode": completed.returncode})
                candidates = list((work / "media" / "videos").rglob("OmnitrixScene.mp4"))
                if not candidates:
                    return ToolResult(success=False, error="Manim exited successfully but no MP4 artifact was found.", metadata={"tool": self.name, "returncode": 0, "artifact_found": False})
                destination = output_root / f"{output_name}-{os.urandom(5).hex()}.mp4"
                shutil.copyfile(candidates[0], destination)
                if destination.stat().st_size <= 0 or destination.stat().st_size > 24 * 1024 * 1024:
                    destination.unlink(missing_ok=True)
                    return ToolResult(success=False, error="Rendered artifact failed the 24 MB Studio import limit.", metadata={"tool": self.name, "artifact_found": False})
                return ToolResult(
                    success=True,
                    output={"artifact_path": str(destination), "format": "mp4", "bytes": destination.stat().st_size},
                    metadata={"tool": self.name, "renderer": "manim", "quality": quality, "node_count": len(nodes), "arrow_count": len(arrows), "verified": True}
                )

        except OSError as exc:
            return ToolResult(success=False, error="Manim output storage is unavailable: " + str(exc), metadata={"tool": self.name})

    @staticmethod
    def _scene_source(title: str, nodes: list[dict[str, Any]], arrows: list[tuple[int, int]]) -> str:
        # Labels are represented as Python string literals; caller-provided source code is never accepted.
        safe_title = repr(title)
        safe_nodes = repr(nodes)
        safe_arrows = repr(arrows)
        return f'''from manim import *
TITLE = {safe_title}
NODES = {safe_nodes}
ARROWS = {safe_arrows}

class OmnitrixScene(Scene):
    def construct(self):
        heading = Text(TITLE, font_size=30).to_edge(UP, buff=0.35)
        self.play(FadeIn(heading), run_time=0.45)
        objects = []
        for item in NODES:
            box = RoundedRectangle(width=2.35, height=0.85, corner_radius=0.12, stroke_width=1.6)
            label = Text(item["label"], font_size=19)
            if label.width > 2.1:
                label.scale_to_fit_width(2.1)
            label.move_to(box.get_center())
            group = VGroup(box, label).move_to([item["x"], item["y"], 0])
            objects.append(group)
            self.play(FadeIn(group), run_time=0.25)
        for start, end in ARROWS:
            arrow = Arrow(objects[start].get_right(), objects[end].get_left(), buff=0.12, stroke_width=2, max_tip_length_to_length_ratio=0.18)
            self.play(Create(arrow), run_time=0.25)
        self.wait(0.6)
'''
