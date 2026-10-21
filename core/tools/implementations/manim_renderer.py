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
import importlib.util

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
            return self._render_fallback(title, nodes, arrows, quality)

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
    def fallback_available() -> bool:
        """Return whether the pure-Python raster/MP4 fallback dependencies are importable."""
        return importlib.util.find_spec("PIL") is not None and importlib.util.find_spec("imageio_ffmpeg") is not None

    def _render_fallback(
        self,
        title: str,
        nodes: list[dict[str, Any]],
        arrows: list[tuple[int, int]],
        quality: str,
    ) -> ToolResult:
        """Render a real MP4 using generated frames when Manim is absent."""
        if not self.fallback_available():
            return ToolResult(
                success=False,
                error="Neither Manim nor the bundled Pillow/imageio-ffmpeg fallback is available.",
                metadata={"tool": self.name, "available": False, "executed": False},
            )
        try:
            from PIL import Image, ImageDraw, ImageFont
            import imageio_ffmpeg

            output_root = Path(os.environ.get("OMNITRIX_ARTIFACT_DIR", "/tmp/omnitrix-artifacts")).expanduser()
            output_root.mkdir(parents=True, exist_ok=True)
            portrait = len(nodes) > 1 and max(float(item["x"]) for item in nodes) - min(float(item["x"]) for item in nodes) < 0.2 and max(float(item["y"]) for item in nodes) - min(float(item["y"]) for item in nodes) > 0.5
            width, height = (720, 1280) if portrait else (1280, 720)
            fps = 24
            duration = max(4.5, 1.2 + 0.55 * len(nodes) + 0.35 * len(arrows))
            frame_count = min(216, int(duration * fps))
            scale = 1.0 if quality == "low" else 1.15
            box_w, box_h = ((int(560 * scale), int(108 * scale)) if portrait else (int(290 * scale), int(100 * scale)))
            font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            try:
                title_font = ImageFont.truetype(bold_path, 34 if portrait else 31)
                label_font = ImageFont.truetype(font_path, 25 if portrait else 21)
            except OSError:
                title_font = ImageFont.load_default()
                label_font = ImageFont.load_default()
            positions = []
            for item in nodes:
                px = 60 + (float(item["x"]) + 5.5) / 11.0 * (width - 120)
                py = height * 0.52 - float(item["y"]) / 2.8 * (height * 0.31)
                positions.append((int(px), int(py)))
            # The supplied diagram coordinates are normalized into a safe canvas.
            if portrait:
                ys = [p[1] for p in positions]
                if max(ys) - min(ys) < height * 0.2:
                    step = min(175, int(680 / max(1, len(nodes) - 1)))
                    positions = [(width // 2, height // 2 - (len(nodes) - 1) * step // 2 + i * step) for i in range(len(nodes))]
            else:
                xs = [p[0] for p in positions]
                if max(xs) - min(xs) < width * 0.25 and len(nodes) > 1:
                    step = int((width - box_w - 100) / (len(nodes) - 1))
                    positions = [(box_w // 2 + 50 + i * step, height // 2 + 20) for i in range(len(nodes))]
            output_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", title).strip("-")[:36] or "science-diagram"
            destination = output_root / f"{output_name}-{os.urandom(5).hex()}.mp4"
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            writer = imageio_ffmpeg.write_frames(
                str(destination), (width, height), fps=fps, codec="libx264",
                pix_fmt_in="rgb24", pix_fmt_out="yuv420p", quality=8 if quality == "low" else 9,
                macro_block_size=2, ffmpeg_log_level="error",
            )
            writer.send(None)
            try:
                for frame_index in range(frame_count):
                    elapsed = frame_index / fps
                    reveal_nodes = min(len(nodes), max(0, int(elapsed / max(0.45, duration * 0.58 / len(nodes))) + 1))
                    reveal_arrows = max(0, min(len(arrows), int((elapsed - duration * 0.62) / max(0.18, duration * 0.28 / max(1, len(arrows))) + 1)))
                    image = Image.new("RGB", (width, height), (9, 12, 16))
                    draw = ImageDraw.Draw(image)
                    draw.text((width // 2, 55 if portrait else 42), title, font=title_font, fill=(235, 241, 244), anchor="mt")
                    draw.line((width * 0.08, 112 if portrait else 96, width * 0.92, 112 if portrait else 96), fill=(57, 76, 86), width=2)
                    for arrow_index, (start, end) in enumerate(arrows[:reveal_arrows]):
                        if start >= reveal_nodes or end >= reveal_nodes:
                            continue
                        x1, y1 = positions[start]
                        x2, y2 = positions[end]
                        dx, dy = x2 - x1, y2 - y1
                        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
                        ux, uy = dx / length, dy / length
                        pad_x = box_w * 0.48
                        pad_y = box_h * 0.48
                        if abs(dx) > abs(dy):
                            sx, sy = x1 + int(ux * pad_x), y1 + int(uy * min(pad_y, abs(dy) / 2))
                            ex, ey = x2 - int(ux * pad_x), y2 - int(uy * min(pad_y, abs(dy) / 2))
                        else:
                            sx, sy = x1 + int(ux * min(pad_x, abs(dx) / 2)), y1 + int(uy * pad_y)
                            ex, ey = x2 - int(ux * min(pad_x, abs(dx) / 2)), y2 - int(uy * pad_y)
                        draw.line((sx, sy, ex, ey), fill=(73, 210, 160), width=4)
                        head = 17
                        left = (ex - int(head * (ux * 0.85 - uy * 0.55)), ey - int(head * (uy * 0.85 + ux * 0.55)))
                        right = (ex - int(head * (ux * 0.85 + uy * 0.55)), ey - int(head * (uy * 0.85 - ux * 0.55)))
                        draw.polygon([(ex, ey), left, right], fill=(73, 210, 160))
                    for node_index, item in enumerate(nodes[:reveal_nodes]):
                        cx, cy = positions[node_index]
                        rect = (cx - box_w // 2, cy - box_h // 2, cx + box_w // 2, cy + box_h // 2)
                        draw.rounded_rectangle(rect, radius=18, fill=(20, 28, 34), outline=(73, 210, 160), width=3)
                        label = str(item["label"])
                        max_chars = 34 if portrait else 22
                        wrapped = []
                        words = label.split()
                        line = ""
                        for word in words:
                            candidate = (line + " " + word).strip()
                            if len(candidate) > max_chars and line:
                                wrapped.append(line)
                                line = word
                            else:
                                line = candidate
                        if line:
                            wrapped.append(line)
                        text_y = cy - int((len(wrapped) - 1) * (label_font.size * 0.62))
                        for row_index, row in enumerate(wrapped[:3]):
                            draw.text((cx, text_y + row_index * int(label_font.size * 1.25)), row, font=label_font, fill=(240, 245, 247), anchor="mm")
                    footer = "OMNITRIX · CODE-RENDERED DIAGRAM"
                    draw.text((width // 2, height - 38), footer, font=label_font, fill=(126, 147, 157), anchor="mm")
                    writer.send(image.tobytes())
            finally:
                writer.close()
            size = destination.stat().st_size if destination.exists() else 0
            if size < 2048 or size > 24 * 1024 * 1024:
                destination.unlink(missing_ok=True)
                return ToolResult(success=False, error="Fallback MP4 failed the artifact size check.", metadata={"tool": self.name, "available": True, "artifact_found": False})
            return ToolResult(
                success=True,
                output={"artifact_path": str(destination), "format": "mp4", "bytes": size},
                metadata={"tool": self.name, "renderer": "python-raster-ffmpeg-fallback", "quality": quality, "node_count": len(nodes), "arrow_count": len(arrows), "verified": True, "manim_available": False},
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error="Code-rendered fallback failed safely: " + type(exc).__name__,
                metadata={"tool": self.name, "available": True, "executed": False},
            )

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
