"""One rooted, manifest-backed playable-character renderer for Animation V2.

The module is intentionally small at the gameplay boundary: it loads complete
authored cels, selects a frozen :class:`AnimationSample`, and composites that
sample around its declared root.  It contains no procedural character anatomy,
per-character scale path, animation fallback, combat damage, or hit logic.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Mapping

import pygame

from .character_animation import (
    AnimationEvent,
    AnimationSample,
    ClipSpec,
    PlayableCharacterSampler,
    PoseAnchor,
    PoseSpec,
    VfxPlacement,
    VfxSocket,
)
from .config import resource_path
from .flame_effects import FlameAtlasDefinition, FlameCompositor, FlameFrame, FlameLayer


_PLAYABLE_ALIASES = {
    "dave": "black_dave",
    "blackdave": "black_dave",
    "shellie": "shelly",
    "white dave": "white_dave",
    "white-dave": "white_dave",
}
_STATE_ALIASES = {
    "run": "walk",
    "move": "walk",
    "jog": "walk",
    "downed": "down",
    "dead": "down",
    "eliminated": "down",
    "propane": "super",
}
_FALLBACK_DAVE_ROUTE_CLIP = {
    "light": "black_dave_v2_regular_01",
    "heavy": "black_dave_v2_power_01",
    "attack_1": "black_dave_v2_regular_01",
    "attack_2": "black_dave_v2_regular_02",
    "attack_3": "black_dave_v2_regular_03",
    "attack_4": "black_dave_v2_regular_04",
}
_GENERIC_STATE_CLIP = {
    "light": "attack_1",
    "heavy": "heavy",
}


def _name(value: object) -> str:
    normalized = str(value or "black_dave").strip().lower().replace("-", "_").replace(" ", "_")
    return _PLAYABLE_ALIASES.get(normalized, normalized)


def _pair(value: object, label: str) -> tuple[int, int]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise ValueError(f"{label} must contain exactly two integer coordinates")
    return int(value[0]), int(value[1])


class PlayableAnimationV2Runtime:
    """Strict atlas loader and rooted renderer for all four playable actors."""

    def __init__(self, spec_path: Path) -> None:
        self.spec_path = spec_path.resolve()
        self.root = self.spec_path.parent.parent
        self.spec = self._load_json(self.spec_path, "playable animation V2 spec")
        if self.spec.get("schema_version") != 2:
            raise ValueError("unsupported playable animation V2 schema")
        self._atlas_paths: dict[str, Path] = {}
        self._atlas_cells: dict[tuple[str, str, int], pygame.Surface] = {}
        self._atlas_surfaces: dict[str, pygame.Surface] = {}
        self._mirrors: dict[int, pygame.Surface] = {}
        self._rows: dict[tuple[str, str], int] = {}
        self._cell_sizes: dict[str, tuple[int, int]] = {}
        self._row_counts: dict[str, int] = {}
        self._clips_by_actor: dict[str, frozenset[str]] = {}
        clips = self._compile_clips()
        self.sampler = PlayableCharacterSampler(tuple(clips), self._frame)
        self.flames = FlameCompositor(self._compile_flame_atlas(), v2_active=True)

    @classmethod
    def from_active_resources(cls) -> "PlayableAnimationV2Runtime":
        return cls(resource_path("data/playable_character_animation_v2.json"))

    @staticmethod
    def _load_json(path: Path, label: str) -> Mapping[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not load {label}: {path}") from exc
        if not isinstance(value, Mapping):
            raise ValueError(f"{label} must be an object: {path}")
        return value

    def _path(self, relative: object, label: str) -> Path:
        path = self.root / str(relative)
        resolved = path.resolve()
        if self.root not in resolved.parents or not resolved.is_file():
            raise FileNotFoundError(f"Animation V2 {label} is required: {resolved}")
        return resolved

    def _compile_clips(self) -> list[ClipSpec]:
        characters = self.spec.get("characters")
        if not isinstance(characters, Mapping):
            raise ValueError("playable animation V2 spec has no character table")
        requested = tuple(map(str, self.spec.get("required_playable_characters", ())))
        if set(requested) != set(characters):
            raise ValueError("Animation V2 character table must exactly cover the playable roster")
        compiled: list[ClipSpec] = []
        for actor, raw_definition in characters.items():
            if not isinstance(raw_definition, Mapping):
                raise ValueError(f"Animation V2 definition is invalid for {actor}")
            actor_name = _name(actor)
            atlas_path = self._path(raw_definition.get("atlas_path"), f"body atlas for {actor_name}")
            metadata_path = self._path(raw_definition.get("pose_metadata_path"), f"pose metadata for {actor_name}")
            metadata = self._load_json(metadata_path, f"pose metadata for {actor_name}")
            cell_size = _pair(metadata.get("cell_size"), f"{actor_name}.cell_size")
            root = _pair(metadata.get("root"), f"{actor_name}.root")
            if list(cell_size) != list(raw_definition.get("actor_canvas", ())):
                raise ValueError(f"{actor_name} metadata cell size does not match the V2 spec")
            if list(root) != list(raw_definition.get("world_root", ())):
                raise ValueError(f"{actor_name} metadata root does not match the V2 spec")
            columns = int(metadata.get("columns", 0))
            if columns != 5:
                raise ValueError(f"{actor_name} V2 atlas must have five authored phases per clip")
            raw_clips = metadata.get("clips")
            if not isinstance(raw_clips, Mapping) or not raw_clips:
                raise ValueError(f"{actor_name} V2 metadata has no clips")
            self._atlas_paths[actor_name] = atlas_path
            self._cell_sizes[actor_name] = cell_size
            self._row_counts[actor_name] = len(raw_clips)
            clip_ids: set[str] = set()
            for clip_id, raw_clip in raw_clips.items():
                if not isinstance(raw_clip, Mapping):
                    raise ValueError(f"{actor_name}/{clip_id} clip metadata is invalid")
                row = int(raw_clip.get("row", -1))
                raw_poses = raw_clip.get("poses")
                if row < 0 or not isinstance(raw_poses, list) or len(raw_poses) != columns:
                    raise ValueError(f"{actor_name}/{clip_id} must declare five complete poses")
                poses: list[PoseSpec] = []
                for pose_index, raw_pose in enumerate(raw_poses):
                    if not isinstance(raw_pose, Mapping):
                        raise ValueError(f"{actor_name}/{clip_id}/{pose_index} pose metadata is invalid")
                    pose_root = _pair(raw_pose.get("root"), f"{actor_name}/{clip_id}/{pose_index}.root")
                    if pose_root != root:
                        raise ValueError(f"{actor_name}/{clip_id} changes its actor root")
                    bounds = tuple(int(value) for value in raw_pose.get("body_bounds", ()))
                    if len(bounds) != 4 or bounds[0] <= 0 or bounds[1] <= 0 or bounds[2] >= cell_size[0] or bounds[3] >= cell_size[1]:
                        raise ValueError(f"{actor_name}/{clip_id}/{pose_index} clips the declared actor canvas")
                    raw_anchors = raw_pose.get("anchors", {})
                    if not isinstance(raw_anchors, Mapping):
                        raise ValueError(f"{actor_name}/{clip_id}/{pose_index} anchors are invalid")
                    anchors = tuple(
                        PoseAnchor(str(anchor_name), _pair(point, f"{actor_name}/{clip_id}/{anchor_name}"))
                        for anchor_name, point in raw_anchors.items()
                    )
                    sockets: list[VfxSocket] = []
                    raw_sockets = raw_pose.get("sockets", ())
                    if not isinstance(raw_sockets, list):
                        raise ValueError(f"{actor_name}/{clip_id}/{pose_index} sockets are invalid")
                    for raw_socket in raw_sockets:
                        if not isinstance(raw_socket, Mapping):
                            raise ValueError(f"{actor_name}/{clip_id}/{pose_index} socket is invalid")
                        sockets.append(VfxSocket(
                            name=str(raw_socket.get("name", "")),
                            position=_pair(raw_socket.get("position"), f"{actor_name}/{clip_id}.socket.position"),
                            tangent=_pair(raw_socket.get("tangent"), f"{actor_name}/{clip_id}.socket.tangent"),
                            size=int(raw_socket.get("size", 0)),
                            intensity=int(raw_socket.get("intensity", 0)),
                            visibility=str(raw_socket.get("visibility", "front_body")),
                            contact_anchor=(str(raw_socket["contact_anchor"]) if raw_socket.get("contact_anchor") else None),
                            release_anchor=(str(raw_socket["release_anchor"]) if raw_socket.get("release_anchor") else None),
                            phase_offset=float(raw_socket.get("phase_offset", 0.0)),
                        ))
                    rear = tuple(VfxPlacement("idle_loop", socket, "rear") for socket in sockets if socket.visibility == "behind_body")
                    front = tuple(VfxPlacement("idle_loop", socket, "front") for socket in sockets if socket.visibility != "behind_body")
                    raw_events = raw_pose.get("events", ())
                    if not isinstance(raw_events, list):
                        raise ValueError(f"{actor_name}/{clip_id}/{pose_index} events are invalid")
                    events = tuple(AnimationEvent(str(event), pose_index) for event in raw_events)
                    poses.append(PoseSpec(pose_index, pose_root, bounds, anchors, events, rear, front))
                clip_id_s = str(clip_id)
                self._rows[(actor_name, clip_id_s)] = row
                compiled.append(ClipSpec(actor_name, clip_id_s, bool(raw_clip.get("loop", False)), int(raw_clip.get("hold", 1)), tuple(poses)))
                clip_ids.add(clip_id_s)
            self._clips_by_actor[actor_name] = frozenset(clip_ids)
        return compiled

    def _compile_flame_atlas(self) -> FlameAtlasDefinition:
        definition = self.spec["characters"].get("black_dave")
        if not isinstance(definition, Mapping):
            raise ValueError("Black Dave V2 flame definition is required")
        atlas_path = self._path(definition.get("vfx_atlas_path"), "flame atlas")
        manifest_path = self._path("assets/sprites/black_dave_v2_flame_vfx_manifest.json", "flame manifest")
        manifest = self._load_json(manifest_path, "flame manifest")
        cell_size = _pair(manifest.get("cell_size"), "flame atlas cell size")
        columns = int(manifest.get("columns", 0))
        raw_clips = manifest.get("clips")
        if cell_size != (64, 64) or columns != 4 or not isinstance(raw_clips, Mapping):
            raise ValueError("flame V2 manifest is incomplete")
        pivots = {
            "ignition": (32, 48), "idle_loop": (32, 48), "anticipation_swell": (32, 48),
            "punch_trail": (32, 32), "power_kick_trail": (32, 32), "contact_burst": (32, 32),
            "ember_release": (32, 34), "scorch_fade": (32, 41), "enemy_feedback": (32, 42),
        }
        frames: dict[str, tuple[FlameFrame, ...]] = {}
        for asset_id, raw_clip in raw_clips.items():
            if not isinstance(raw_clip, Mapping):
                raise ValueError(f"flame clip {asset_id} is invalid")
            row = int(raw_clip.get("row", -1))
            count = int(raw_clip.get("frame_count", 0))
            if row < 0 or count != columns:
                raise ValueError(f"flame clip {asset_id} is incomplete")
            frames[str(asset_id)] = tuple(
                FlameFrame(str(asset_id), (phase * cell_size[0], row * cell_size[1], *cell_size), pivots[str(asset_id)])
                for phase in range(columns)
            )
        aliases = {
            "flame_trail": "punch_trail",
            "flame_burst": "contact_burst",
            "ember": "ember_release",
            "scorch": "scorch_fade",
            "enemy_fire": "enemy_feedback",
        }
        for alias, source in aliases.items():
            frames[alias] = frames[source]
        return FlameAtlasDefinition(atlas_path, frames, frames_per_second=12)

    def clip_ids(self, actor: object) -> frozenset[str]:
        name = _name(actor)
        try:
            return self._clips_by_actor[name]
        except KeyError as exc:
            raise ValueError(f"unregistered playable Animation V2 actor: {name}") from exc

    def _atlas(self, actor: str) -> pygame.Surface:
        cached = self._atlas_surfaces.get(actor)
        if cached is None:
            atlas = pygame.image.load(str(self._atlas_paths[actor]))
            if pygame.display.get_surface() is not None:
                atlas = atlas.convert_alpha()
            self._atlas_surfaces[actor] = atlas
            cached = atlas
        return cached

    def _frame(self, actor: str, clip_id: str, pose_index: int) -> pygame.Surface | None:
        key = (actor, clip_id, pose_index)
        cached = self._atlas_cells.get(key)
        if cached is not None:
            return cached
        row = self._rows.get((actor, clip_id))
        if row is None or pose_index not in range(5):
            return None
        width, height = self._atlas(actor).get_size()
        cell_width, cell_height = self._cell_sizes[actor]
        row_count = self._row_counts[actor]
        # Metadata has already proven the true dimensions.  This local check
        # simply protects a corrupted packaged PNG from emitting a clipped cel.
        if (width, height) != (cell_width * 5, cell_height * row_count) or (row + 1) * cell_height > height:
            raise ValueError(f"invalid V2 atlas dimensions for {actor}")
        frame = self._atlas(actor).subsurface(pygame.Rect(pose_index * cell_width, row * cell_height, cell_width, cell_height)).copy()
        self._atlas_cells[key] = frame
        return frame

    def _resolved_clip(self, actor: str, state: object, attack_execution: object | None) -> str:
        if attack_execution is not None:
            requested = str(getattr(attack_execution, "clip_id", ""))
            if requested in self.clip_ids(actor):
                return requested
            air_kind = str(getattr(attack_execution, "step_id", ""))
            if air_kind in self.clip_ids(actor):
                return air_kind
        normalized = _STATE_ALIASES.get(str(state), str(state))
        if actor == "black_dave":
            normalized = _FALLBACK_DAVE_ROUTE_CLIP.get(normalized, normalized)
            if normalized == "jump":
                normalized = "jump_rise"
        else:
            normalized = _GENERIC_STATE_CLIP.get(normalized, normalized)
            if normalized == "jump_land":
                normalized = "jump"
        if normalized not in self.clip_ids(actor):
            raise ValueError(f"no declared Animation V2 clip for {actor}/{state}")
        return normalized

    def sample(
        self,
        actor: object,
        state: object,
        authored_tick: int,
        *,
        attack_execution: object | None = None,
    ) -> AnimationSample:
        actor_name = _name(actor)
        return self.sampler.sample(actor_name, self._resolved_clip(actor_name, state, attack_execution), int(authored_tick))

    def _body_for_facing(self, body: pygame.Surface, facing: int) -> pygame.Surface:
        if facing >= 0:
            return body
        cached = self._mirrors.get(id(body))
        if cached is None:
            cached = pygame.transform.flip(body, True, False)
            self._mirrors[id(body)] = cached
        return cached

    @staticmethod
    def _shadow(surface: pygame.Surface, x: int, y: int, *, width: int, elevation: float) -> pygame.Rect:
        scale = max(0.45, 1.0 - min(180.0, max(0.0, elevation)) / 250.0)
        rect = pygame.Rect(
            x - round(width * scale * 0.5),
            y - 3 + round(min(6.0, max(0.0, elevation) * 0.045)),
            max(8, round(width * scale)),
            max(3, round(7 * scale)),
        )
        pygame.draw.ellipse(surface, (13, 16, 24), rect)
        return rect

    @staticmethod
    def _body_destination(sample: AnimationSample, body: pygame.Surface, root: tuple[int, int], facing: int) -> tuple[int, int]:
        root_x = sample.root[0] if facing >= 0 else body.get_width() - 1 - sample.root[0]
        return root[0] - root_x, root[1] - sample.root[1]

    @staticmethod
    def _presentation_events(sample: AnimationSample, *, flaming: bool, confirmed_hit: bool) -> tuple[AnimationEvent, ...]:
        if not flaming:
            return ()
        events: list[AnimationEvent] = []
        for event in sample.events:
            if event.name == "flame_contact" and not confirmed_hit:
                events.append(AnimationEvent("flame_whiff", event.phase, event.payload))
            else:
                events.append(event)
        return tuple(events)

    def draw_actor(
        self,
        surface: pygame.Surface,
        *,
        actor: object,
        state: object,
        authored_tick: int,
        x: float,
        y: float,
        z: float,
        facing: int,
        local_time: float,
        attack_execution: object | None = None,
        flaming: bool = False,
        confirmed_hit: bool = False,
    ) -> pygame.Rect:
        sample = self.sample(actor, state, authored_tick, attack_execution=attack_execution)
        actor_root = (int(round(x)), int(round(y - z)))
        shadow = self._shadow(
            surface,
            int(round(x)),
            int(round(y)),
            width=max(24, sample.body_bounds[2] - sample.body_bounds[0]),
            elevation=z,
        )
        if flaming:
            presentation = replace(sample, events=self._presentation_events(sample, flaming=True, confirmed_hit=confirmed_hit))
            commands = self.flames.plan(presentation, actor_root, facing, float(local_time))
        else:
            commands = (None,)
        bounds = shadow
        for command in commands:
            if command is None or command.layer == FlameLayer.BODY:
                body = self._body_for_facing(sample.body_surface, facing)
                rect = surface.blit(body, self._body_destination(sample, body, actor_root, facing))
            else:
                assert command.surface is not None
                rect = surface.blit(command.surface, command.position)
            bounds = bounds.union(rect)
        return bounds

    def draw_enemy_feedback(self, surface: pygame.Surface, *, x: float, y: float, facing: int, local_time: float) -> pygame.Rect:
        """Render confirmed-hit enemy fire only from the V2 flame atlas."""

        loaded = self.flames.cache.frame(self.flames.atlas, "enemy_fire", local_time, facing, strict=True)
        assert loaded is not None
        cel, frame = loaded
        pivot_x, pivot_y = frame.pivot
        if facing < 0:
            pivot_x = cel.get_width() - pivot_x
        return surface.blit(cel, (int(round(x)) - pivot_x, int(round(y)) - pivot_y))
