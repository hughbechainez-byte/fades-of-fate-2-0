"""Flag-gated Black Dave identity preview for the next character pass.

The preview is intentionally separate from the full Animation V2 library.  It
loads only the new rooted whole-cels needed to review identity, footprint, and
core motion in real gameplay; the complete per-state hero library remains the
next authored phase after review.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pygame

from .character_animation import AnimationEvent, AnimationSample, PoseAnchor


_STATE_ALIASES = {
    "run": "walk",
    "move": "walk",
    "jog": "walk",
    "downed": "down",
    "dead": "down",
    "eliminated": "down",
    "propane": "super",
}


class BlackDavePreviewLayer:
    """Render the review-only Black Dave pose board at one fixed baked scale."""

    def __init__(self, metadata_path: Path) -> None:
        self.metadata_path = metadata_path.resolve()
        self.root = self.metadata_path.parent.parent.parent
        self.metadata = self._load_json(self.metadata_path)
        if self.metadata.get("status") != "review_preview":
            raise ValueError("Black Dave preview metadata must remain explicitly review-only")
        self.cell_size = self._pair(self.metadata.get("cell_size"), "cell_size")
        self.root_point = self._pair(self.metadata.get("root"), "root")
        self.atlas_path = self._inside_root(self.metadata.get("atlas_path"), "atlas")
        self._atlas_surface: pygame.Surface | None = None
        self._cells: dict[int, pygame.Surface] = {}
        self._mirrors: dict[int, pygame.Surface] = {}
        self._poses: dict[str, Mapping[str, Any]] = {
            str(pose["id"]): pose for pose in self.metadata.get("poses", ())
        }
        if not self._poses or len(self._poses) != int(self.metadata.get("columns", 0)):
            raise ValueError("Black Dave preview must declare one complete pose record per atlas column")
        self._clips: dict[str, tuple[str, ...]] = {
            str(clip_id): tuple(str(pose_id) for pose_id in clip.get("poses", ()))
            for clip_id, clip in self.metadata.get("clips", {}).items()
            if isinstance(clip, Mapping)
        }
        if not self._clips:
            raise ValueError("Black Dave preview has no review clips")

    @staticmethod
    def _load_json(path: Path) -> Mapping[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not load Black Dave preview metadata: {path}") from exc
        if not isinstance(value, Mapping):
            raise ValueError("Black Dave preview metadata must be an object")
        return value

    @staticmethod
    def _pair(value: object, label: str) -> tuple[int, int]:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(f"Black Dave preview {label} must contain two coordinates")
        return int(value[0]), int(value[1])

    def _inside_root(self, relative: object, label: str) -> Path:
        candidate = (self.root / str(relative)).resolve()
        if self.root not in candidate.parents or not candidate.is_file():
            raise FileNotFoundError(f"Black Dave preview {label} is required: {candidate}")
        return candidate

    @property
    def active(self) -> bool:
        return True

    def _atlas(self) -> pygame.Surface:
        if self._atlas_surface is None:
            atlas = pygame.image.load(str(self.atlas_path))
            if pygame.display.get_surface() is not None:
                atlas = atlas.convert_alpha()
            expected = (self.cell_size[0] * len(self._poses), self.cell_size[1])
            if atlas.get_size() != expected:
                raise ValueError(f"Black Dave preview atlas dimensions are {atlas.get_size()}, expected {expected}")
            if not atlas.get_bounding_rect(min_alpha=1).width:  # pragma: no cover - corrupt-art guard
                raise ValueError("Black Dave preview atlas is empty")
            self._atlas_surface = atlas
        return self._atlas_surface

    def _cell(self, pose_id: str) -> pygame.Surface:
        pose = self._poses.get(pose_id)
        if pose is None:
            raise ValueError(f"Black Dave preview references unknown pose: {pose_id}")
        index = int(pose["index"])
        cached = self._cells.get(index)
        if cached is None:
            cached = self._atlas().subsurface(
                pygame.Rect(index * self.cell_size[0], 0, self.cell_size[0], self.cell_size[1])
            ).copy()
            self._cells[index] = cached
        return cached

    def body_for_facing(self, body: pygame.Surface, facing: int) -> pygame.Surface:
        if facing >= 0:
            return body
        cached = self._mirrors.get(id(body))
        if cached is None:
            cached = pygame.transform.flip(body, True, False)
            self._mirrors[id(body)] = cached
        return cached

    def _clip_id(self, state: object, attack_execution: object | None) -> str:
        if attack_execution is not None:
            step_id = str(getattr(attack_execution, "step_id", "")).lower()
            if "air_kick" in step_id or step_id.endswith("kick"):
                return "air_kick"
            if "air_punch" in step_id or step_id.endswith("punch"):
                return "air_punch"
            route_id = str(getattr(attack_execution, "route_id", ""))
            if route_id == "regular":
                return "light"
            if route_id == "kick":
                return "heavy"
            if route_id == "power":
                return "super"
        normalized = _STATE_ALIASES.get(str(state).strip().lower(), str(state).strip().lower())
        if normalized == "air_attack":
            normalized = "air_punch"
        if normalized in {"jump", "jump_takeoff", "jump_rise", "jump_apex", "jump_fall", "jump_land"}:
            normalized = normalized if normalized != "jump" else "jump_rise"
        if normalized in self._clips:
            return normalized
        if normalized in {"light", "heavy"} and normalized in self._clips:
            return normalized
        return "idle"

    def sample(
        self,
        state: object,
        authored_tick: int,
        *,
        attack_execution: object | None = None,
    ) -> AnimationSample:
        clip_id = self._clip_id(state, attack_execution)
        pose_ids = self._clips[clip_id]
        if not pose_ids:
            raise ValueError(f"Black Dave preview clip has no poses: {clip_id}")
        clip_meta = self.metadata.get("clips", {}).get(clip_id, {})
        hold = max(1, int(clip_meta.get("hold", 1))) if isinstance(clip_meta, Mapping) else 1
        pose_index = (max(0, int(authored_tick)) // hold) % len(pose_ids)
        pose_id = pose_ids[pose_index]
        pose = self._poses[pose_id]
        anchors = tuple(
            PoseAnchor(str(name), self._pair(position, f"{clip_id}.{name}"))
            for name, position in pose.get("anchors", {}).items()
        )
        events = tuple(AnimationEvent(str(name), pose_index) for name in pose.get("events", ()))
        return AnimationSample(
            actor_id="black_dave",
            clip_id=f"black_dave_preview_{clip_id}",
            pose_index=int(pose["index"]),
            body_surface=self._cell(pose_id),
            root=self.root_point,
            body_bounds=tuple(int(value) for value in pose["body_bounds"]),
            anchors=anchors,
            events=events,
            rear_vfx=(),
            front_vfx=(),
        )
