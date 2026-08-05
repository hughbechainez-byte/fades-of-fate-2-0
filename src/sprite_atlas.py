"""Authored pixel-sprite atlas loader and animation-state mapping."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

import pygame

from .animation_manifest import (
    ANIMATION_CLIPS,
    ANIMATION_PLAYBACK_HZ,
    ENEMY_STATES,
    ENEMY_VARIANT_KINDS,
    AnimationClip,
    KO_STATES,
    clip_for,
    enemy_animation_actor,
    total_authored_poses,
)
from .config import resource_path


def _state_name(state: object) -> str:
    return str(state or "idle").strip().lower().replace("-", "_").replace(" ", "_")


@lru_cache(maxsize=32)
def _load_frames(
    relative: str,
    columns: int,
    rows: int,
    canonical_flip: bool = False,
    already_canonical_indices: tuple[int, ...] = (),
    width_scale: float = 1.0,
    height_scale: float = 1.0,
) -> tuple[pygame.Surface, ...]:
    path = resource_path(relative)
    if not Path(path).is_file():
        return ()
    try:
        atlas = pygame.image.load(str(path))
        if pygame.display.get_surface() is not None:
            atlas = atlas.convert_alpha()
    except pygame.error:
        return ()
    cell_width = atlas.get_width() // columns
    cell_height = atlas.get_height() // rows
    if cell_width <= 0 or cell_height <= 0:
        return ()
    frames = tuple(
        atlas.subsurface((column * cell_width, row * cell_height, cell_width, cell_height)).copy()
        for row in range(rows)
        for column in range(columns)
    )
    if canonical_flip:
        preserved = frozenset(already_canonical_indices)
        frames = tuple(
            frame if index in preserved else pygame.transform.flip(frame, True, False)
            for index, frame in enumerate(frames)
        )
    if width_scale != 1.0 or height_scale != 1.0:
        frames = tuple(
            pygame.transform.scale(
                frame,
                (
                    max(1, round(frame.get_width() * width_scale)),
                    max(1, round(frame.get_height() * height_scale)),
                ),
            )
            for frame in frames
        )
    return frames


_ATLAS_ROWS = {
    relative: max(clip.row for clip in ANIMATION_CLIPS if clip.atlas == relative) + 1
    for relative in {clip.atlas for clip in ANIMATION_CLIPS}
}
_ATLAS_COLUMNS = {
    relative: max(clip.frame_count for clip in ANIMATION_CLIPS if clip.atlas == relative)
    for relative in {clip.atlas for clip in ANIMATION_CLIPS}
}

# Keep Shelly's personality cycle in real time on the shared 30 Hz animation
# clock, independent of the renderer's 30/60 FPS presentation rate. The cycle
# starts the waistband beat early enough to be observed during ordinary pauses.
SHELLY_IDLE_CYCLE_TICKS = int(ANIMATION_PLAYBACK_HZ * 12)
SHELLY_REFILL_WINDOW = (int(ANIMATION_PLAYBACK_HZ * 7), int(ANIMATION_PLAYBACK_HZ * 9.5))
SHELLY_PANTS_WINDOW = (int(ANIMATION_PLAYBACK_HZ * 2), int(ANIMATION_PLAYBACK_HZ * 5.5))
DAVE_UNIFORM_RENDER_SCALE = 1.12
COUCH_UNIFORM_RENDER_SCALE = 1.08
DAVE_STABLE_WALK_POSES = 12
DAVE_STABLE_WALK_TICK_MAP = (
    0, 0, 0,
    1, 1,
    2, 2,
    3,
    4,
    5, 5, 5,
    6, 6, 6,
    7, 7,
    8, 8,
    9,
    10,
    11, 11, 11,
)
DAVE_STABLE_WALK_STRIP = "assets/sprites/black_dave_walk_identity_v1.png"
ENEMY_VARIANT_ANCHORS = "assets/sprites/enemies/enemy_variant_anchors.json"


@lru_cache(maxsize=128)
def _authored_animation_frames(actor: str, state: str) -> tuple[pygame.Surface, ...]:
    """Load an authored strip without changing its aspect ratio at runtime."""

    clip = clip_for(actor, state)
    atlas = _load_frames(
        clip.atlas,
        _ATLAS_COLUMNS[clip.atlas],
        _ATLAS_ROWS[clip.atlas],
    )
    start = clip.row * _ATLAS_COLUMNS[clip.atlas]
    poses = atlas[start : start + clip.frame_count]
    if not poses:
        return poses

    uniform_scale = {
        "black_dave": DAVE_UNIFORM_RENDER_SCALE,
        # Keep Couch short and broad by respecting the squat source silhouette
        # and enlarging it uniformly—never by squeezing height independently.
        "couch": COUCH_UNIFORM_RENDER_SCALE,
    }.get(clip.actor)
    if uniform_scale is None:
        return poses

    # Dave is intentionally taller and leaner than Shelly, but must retain one
    # stable pixel aspect ratio in idle, stride, and combat. Previous X/Y
    # scales warped his limbs and made the smaller combat source keys look as
    # if he shrank whenever he threw a punch. Couch follows the same rule.
    return tuple(
        pygame.transform.scale(
            pose,
            (
                max(1, round(pose.get_width() * uniform_scale)),
                max(1, round(pose.get_height() * uniform_scale)),
            ),
        )
        for pose in poses
    )


@lru_cache(maxsize=1)
def _dave_stable_walk_frames() -> tuple[pygame.Surface, ...]:
    """Load Dave's locked-palette 12-pose gait without changing its pixels."""

    frames = _load_frames(DAVE_STABLE_WALK_STRIP, DAVE_STABLE_WALK_POSES, 1)
    if len(frames) != DAVE_STABLE_WALK_POSES:
        return ()
    return tuple(
        pygame.transform.scale(
            frame,
            (
                max(1, round(frame.get_width() * DAVE_UNIFORM_RENDER_SCALE)),
                max(1, round(frame.get_height() * DAVE_UNIFORM_RENDER_SCALE)),
            ),
        )
        for frame in frames
    )


def animation_frames(actor: object, state: object) -> tuple[pygame.Surface, ...]:
    """Return all independently selectable authored poses for one active clip."""

    clip = clip_for(str(actor), _state_name(state))
    return _authored_animation_frames(clip.actor, clip.state)


def _clip_phase_index(clip: AnimationClip, tick: int, pose_count: int) -> int:
    phase = max(0, int(tick)) // max(1, clip.hold)
    if clip.loop:
        return phase % pose_count
    return min(phase, pose_count - 1)


def _clip_frame(clip: AnimationClip, tick: int) -> pygame.Surface | None:
    poses = animation_frames(clip.actor, clip.state)
    if not poses:
        return None
    phase = _clip_phase_index(clip, tick, len(poses))
    return poses[phase]


def animation_frame(actor: object, state: object, tick: int) -> pygame.Surface | None:
    """Select a manifest-backed phase pose using runtime animation timing."""

    clip = clip_for(str(actor), _state_name(state))
    return _clip_frame(clip, tick)


def ko_frame(state: object, tick: int) -> pygame.Surface:
    """Return an exact authored KO pose and never substitute another actor.

    KO's skateboard, lab-coat/glove preparation, three strikes, and super are
    state-specific visual contracts.  A missing state or atlas is therefore a
    hard error: silently rendering Dave or KO's idle would violate both the
    gameplay read and the review provenance for the character.
    """

    state_name = _state_name(state)
    if state_name not in KO_STATES:
        raise ValueError(f"unknown KO animation state: {state_name}")
    clip = clip_for("ko", state_name)
    poses = animation_frames("ko", state_name)
    if len(poses) != clip.frame_count:
        atlas_path = Path(resource_path(clip.atlas))
        raise FileNotFoundError(
            f"KO authored atlas is missing or incomplete: {atlas_path} "
            f"({len(poses)}/{clip.frame_count} poses for {state_name})"
        )
    return poses[_clip_phase_index(clip, max(0, int(tick)), len(poses))]


def player_frame(character: object, state: object, tick: int) -> pygame.Surface | None:
    """Return one of the hero's authored phase poses."""

    name = str(character or "black_dave").strip().lower().replace("-", "_").replace(" ", "_")
    if name == "ko":
        return ko_frame(state, tick)
    if name in {"jermaine", "white_dave"}:
        return None
    name = "shelly" if name in {"shelly", "shellie"} else "black_dave"
    state_name = _state_name(state)
    tick = max(0, int(tick))
    if name == "black_dave" and state_name == "walk":
        frames = _dave_stable_walk_frames()
        if frames:
            return frames[DAVE_STABLE_WALK_TICK_MAP[tick % len(DAVE_STABLE_WALK_TICK_MAP)]]
    if name == "shelly" and state_name == "idle":
        # Shelly primarily uses the same restrained breathing language as Dave,
        # with two short personality beats folded into each idle cycle.
        idle_phase = tick % SHELLY_IDLE_CYCLE_TICKS
        refill_start, refill_end = SHELLY_REFILL_WINDOW
        pants_start, pants_end = SHELLY_PANTS_WINDOW
        if refill_start <= idle_phase < refill_end:
            poses = animation_frames("shelly", "refill")
            phase = min(len(poses) - 1, (idle_phase - refill_start) * len(poses) // (refill_end - refill_start))
            return poses[phase] if poses else None
        if pants_start <= idle_phase < pants_end:
            poses = animation_frames("shelly", "pants")
            phase = min(len(poses) - 1, (idle_phase - pants_start) * len(poses) // (pants_end - pants_start))
            return poses[phase] if poses else None
        breath_tick = idle_phase
        if idle_phase >= refill_end:
            breath_tick -= refill_end - refill_start
        if idle_phase >= pants_end:
            breath_tick -= pants_end - pants_start
        return _clip_frame(clip_for("shelly", "idle"), breath_tick)
    return animation_frame(name, state_name, tick)


def _is_dave_skin(pixel: pygame.Color) -> bool:
    """Recognize Dave's warm skin ramp while rejecting denim, ink and flashes."""

    return (
        pixel.a >= 96
        and pixel.r >= 58
        and pixel.r - pixel.g >= 12
        and pixel.g - pixel.b >= 4
        and pixel.r - pixel.b >= 24
    )


@lru_cache(maxsize=1)
def _load_dave_fist_metadata() -> tuple[
    tuple[int, int],
    dict[str, tuple[tuple[tuple[int, int], tuple[int, int]], ...]],
]:
    """Load and strictly validate the builder-authored semantic hand map."""

    try:
        path = Path(resource_path("assets/sprites/black_dave_fist_anchors.json"))
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported Dave fist metadata version")
        raw_cell_size = payload.get("cell_size")
        if not isinstance(raw_cell_size, list) or len(raw_cell_size) != 2:
            raise ValueError("invalid Dave fist metadata cell size")
        cell_size = (int(raw_cell_size[0]), int(raw_cell_size[1]))
        if cell_size[0] <= 0 or cell_size[1] <= 0:
            raise ValueError("invalid Dave fist metadata dimensions")
        raw_states = payload.get("states")
        if not isinstance(raw_states, dict):
            raise ValueError("Dave fist metadata has no states")

        parsed: dict[str, tuple[tuple[tuple[int, int], tuple[int, int]], ...]] = {}
        for clip in (candidate for candidate in ANIMATION_CLIPS if candidate.actor == "black_dave"):
            raw_phases = raw_states.get(clip.state)
            if not isinstance(raw_phases, list) or len(raw_phases) != clip.frame_count:
                raise ValueError(f"incomplete Dave fist metadata for {clip.state}")
            phases: list[tuple[tuple[int, int], tuple[int, int]]] = []
            for raw_phase in raw_phases:
                if not isinstance(raw_phase, dict):
                    raise ValueError(f"invalid Dave fist phase for {clip.state}")
                points: list[tuple[int, int]] = []
                for key in ("rear", "lead"):
                    raw_point = raw_phase.get(key)
                    if not isinstance(raw_point, list) or len(raw_point) != 2:
                        raise ValueError(f"missing {key} Dave fist landmark for {clip.state}")
                    point = (int(raw_point[0]), int(raw_point[1]))
                    if not (0 <= point[0] < cell_size[0] and 0 <= point[1] < cell_size[1]):
                        raise ValueError(f"out-of-cell Dave fist landmark for {clip.state}")
                    points.append(point)
                if points[0] == points[1]:
                    raise ValueError(f"collapsed Dave fist landmarks for {clip.state}")
                phases.append((points[0], points[1]))
            parsed[clip.state] = tuple(phases)
        return cell_size, parsed
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # The JSON is packaged with every build. A corrupt/missing external
        # asset must degrade to conservative body-relative anchors, never crash
        # startup or revive the old shoe/face color-extreme selection.
        return (128, 128), {}


def _fallback_dave_fist_anchors(
    frame: pygame.Surface,
    state: str,
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return conservative body-relative points only when metadata is absent."""

    bounds = frame.get_bounding_rect(min_alpha=16)
    if not bounds.w or not bounds.h:
        centre = (frame.get_width() // 2, frame.get_height() // 2)
        return centre, (min(frame.get_width() - 1, centre[0] + 1), centre[1])
    if state == "down":
        normalized = ((0.55, 0.34), (0.72, 0.46))
    elif state == "walk":
        normalized = ((0.28, 0.48), (0.70, 0.46))
    elif state.startswith("attack_") or state in {"heavy", "air_attack"}:
        normalized = ((0.30, 0.34), (0.76, 0.32))
    else:
        normalized = ((0.30, 0.36), (0.65, 0.36))
    return tuple(
        (
            max(0, min(frame.get_width() - 1, bounds.left + round((bounds.w - 1) * x_ratio))),
            max(0, min(frame.get_height() - 1, bounds.top + round((bounds.h - 1) * y_ratio))),
        )
        for x_ratio, y_ratio in normalized
    )  # type: ignore[return-value]


@lru_cache(maxsize=256)
def _dave_fist_anchors(state: str, phase: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return authored rear/lead hands on one canonical right-facing cel."""

    poses = animation_frames("black_dave", state)
    if not poses:
        return ()  # type: ignore[return-value]
    frame = poses[max(0, min(len(poses) - 1, phase))]
    cell_size, states = _load_dave_fist_metadata()
    state_phases = states.get(state)
    if not state_phases or phase >= len(state_phases):
        return _fallback_dave_fist_anchors(frame, state)
    scale_x = frame.get_width() / cell_size[0]
    scale_y = frame.get_height() / cell_size[1]
    return tuple(
        (
            max(0, min(frame.get_width() - 1, round((point_x + 0.5) * scale_x - 0.5))),
            max(0, min(frame.get_height() - 1, round((point_y + 0.5) * scale_y - 0.5))),
        )
        for point_x, point_y in state_phases[phase]
    )  # type: ignore[return-value]


def player_fist_anchors(
    character: object,
    state: object,
    tick: int,
) -> tuple[tuple[int, int], ...]:
    """Return canonical local ``(rear, lead)`` fist points for the selected cel.

    Coordinates use the unflipped surface returned by :func:`player_frame`.
    Callers rendering a left-facing sprite should mirror each X coordinate as
    ``surface_width - 1 - x``.  Non-Dave characters return an empty tuple.
    """

    name = str(character or "black_dave").strip().lower().replace("-", "_").replace(" ", "_")
    if name not in {"black_dave", "blackdave", "dave"}:
        return ()
    clip = clip_for("black_dave", _state_name(state))
    poses = animation_frames(clip.actor, clip.state)
    if not poses:
        return ()
    phase = _clip_phase_index(clip, tick, len(poses))
    return _dave_fist_anchors(clip.state, phase)


def chief_frame(state: object, tick: int) -> pygame.Surface | None:
    resolved = clip_for("chief", _state_name(state))
    # The legacy maul strip is a 256px-wide composite with a pre-painted human
    # victim. Runtime combat already renders the actual Enemy separately, so
    # using that strip doubled Chief's dimensions and invented a second target.
    # Keep the behavior state but render Chief's ordinary authored bite cel.
    runtime_state = "attack" if resolved.state == "maul" else resolved.state
    return animation_frame("chief", runtime_state, tick)


def enemy_frame(
    kind: object,
    state: object,
    tick: int,
    variant_id: object | None = None,
) -> pygame.Surface | None:
    """Return a complete authored enemy cel for a runtime kind/variant pair.

    Named variants resolve to their own manifest actors. Legacy homeless roles
    retain their existing procedural presentation by returning ``None`` when
    they do not have a dedicated actor.
    """

    enemy_kind = str(kind or "stick").strip().lower().replace("-", "_").replace(" ", "_")
    variant = str(variant_id or "").strip().lower().replace("-", "_").replace(" ", "_")
    if enemy_kind in {"shopping_cart", "cart_pusher"}:
        enemy_kind = "cart"
    elif enemy_kind in {"makeshift_whip", "cord"}:
        enemy_kind = "whip"
    elif enemy_kind in {"broken_pipe", "thrower"}:
        enemy_kind = "pipe"
    actor = enemy_animation_actor(enemy_kind, variant or None)
    if enemy_kind == "homeless" and actor != variant:
        return None
    return animation_frame(actor, state, tick)


@lru_cache(maxsize=1)
def _load_enemy_variant_anchor_metadata() -> tuple[
    tuple[int, int],
    dict[str, dict[str, tuple[dict[str, object], ...]]],
]:
    """Load builder-authored cel landmarks without deriving them from pixels."""

    try:
        payload = json.loads(Path(resource_path(ENEMY_VARIANT_ANCHORS)).read_text(encoding="utf-8"))
        if payload.get("version") != 1:
            raise ValueError("unsupported enemy variant anchor metadata version")
        raw_cell_size = payload.get("cell_size")
        if not (
            isinstance(raw_cell_size, list)
            and len(raw_cell_size) == 2
            and all(isinstance(value, int) and not isinstance(value, bool) for value in raw_cell_size)
        ):
            raise ValueError("invalid enemy variant anchor cell size")
        cell_size = (raw_cell_size[0], raw_cell_size[1])
        if cell_size[0] <= 0 or cell_size[1] <= 0:
            raise ValueError("invalid enemy variant anchor dimensions")
        raw_actors = payload.get("actors")
        if not isinstance(raw_actors, dict):
            raise ValueError("enemy variant anchor metadata has no actors")
        expected_actors = frozenset(ENEMY_VARIANT_KINDS)
        normalized_actor_names = {
            str(name).strip().lower().replace("-", "_").replace(" ", "_")
            for name in raw_actors
        }
        if normalized_actor_names != expected_actors or len(raw_actors) != len(expected_actors):
            raise ValueError("enemy variant anchor metadata actor roster is incomplete")

        actors: dict[str, dict[str, tuple[dict[str, object], ...]]] = {}
        point_fields = ("root", "rear_hand", "lead_hand", "weapon_anchor", "release_anchor")
        for raw_actor, raw_actor_payload in raw_actors.items():
            actor = str(raw_actor).strip().lower().replace("-", "_").replace(" ", "_")
            if not actor or not isinstance(raw_actor_payload, dict):
                raise ValueError("invalid enemy variant anchor actor")
            raw_states = raw_actor_payload.get("states")
            if not isinstance(raw_states, dict):
                raise ValueError(f"enemy variant anchor actor {actor!r} has no states")
            states: dict[str, tuple[dict[str, object], ...]] = {}
            for raw_state, raw_phases in raw_states.items():
                state = _state_name(raw_state)
                if state in states:
                    raise ValueError(f"enemy variant anchor actor {actor!r} repeats {state!r}")
                if not isinstance(raw_phases, list) or not raw_phases:
                    raise ValueError(f"enemy variant anchor actor {actor!r} has invalid {state!r} phases")
                expected_phase_count = clip_for(actor, state).frame_count
                if len(raw_phases) != expected_phase_count:
                    raise ValueError(
                        f"enemy variant anchor actor {actor!r} has {len(raw_phases)} {state!r} phases; "
                        f"expected {expected_phase_count}"
                    )
                phases: list[dict[str, object]] = []
                for raw_phase in raw_phases:
                    if not isinstance(raw_phase, dict):
                        raise ValueError(f"enemy variant anchor actor {actor!r} has invalid {state!r} phase")
                    source_key = raw_phase.get("source_key")
                    held_gear = raw_phase.get("held_gear")
                    if not isinstance(source_key, str) or not source_key.strip():
                        raise ValueError(f"enemy variant anchor actor {actor!r} has no source key")
                    if not isinstance(held_gear, bool):
                        raise ValueError(f"enemy variant anchor actor {actor!r} has invalid held-gear state")
                    phase: dict[str, object] = {
                        "source_key": source_key,
                        "held_gear": held_gear,
                    }
                    for field in point_fields:
                        raw_point = raw_phase.get(field)
                        if raw_point is None:
                            point = None
                        elif (
                            isinstance(raw_point, list)
                            and len(raw_point) == 2
                            and all(isinstance(value, int) and not isinstance(value, bool) for value in raw_point)
                        ):
                            point = (raw_point[0], raw_point[1])
                            if not (0 <= point[0] < cell_size[0] and 0 <= point[1] < cell_size[1]):
                                raise ValueError(
                                    f"enemy variant anchor actor {actor!r} has out-of-cell {field!r}"
                                )
                        else:
                            raise ValueError(
                                f"enemy variant anchor actor {actor!r} has invalid {field!r}"
                            )
                        phase[field] = point
                    if phase["root"] is None:
                        raise ValueError(f"enemy variant anchor actor {actor!r} has no root")
                    phases.append(phase)
                states[state] = tuple(phases)
            if frozenset(states) != frozenset(ENEMY_STATES):
                raise ValueError(f"enemy variant anchor actor {actor!r} has an incomplete state roster")
            actors[actor] = states
        return cell_size, actors
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        # Dedicated weapon release points must never be guessed from alpha
        # bounds or a silhouette centroid. Callers can fail closed when a
        # required authored landmark is absent.
        return (0, 0), {}


def enemy_pose_anchors(
    kind: object,
    state: object,
    tick: int,
    variant_id: object | None = None,
) -> dict[str, object]:
    """Return authored cell-local landmarks for the selected enemy cel.

    Points use the canonical right-facing atlas cell. A left-facing caller
    mirrors X as ``frame_width - 1 - x``. Legacy actors return an empty map.
    """

    variant = str(variant_id or "").strip().lower().replace("-", "_").replace(" ", "_")
    actor = enemy_animation_actor(kind, variant or None)
    if not variant or actor != variant:
        return {}
    _, actors = _load_enemy_variant_anchor_metadata()
    states = actors.get(actor)
    if not states:
        return {}
    clip = clip_for(actor, _state_name(state))
    phases = states.get(clip.state)
    if not phases:
        return {}
    phase = _clip_phase_index(clip, tick, len(phases))
    return dict(phases[phase])


def enemy_root_anchor(
    kind: object,
    state: object,
    tick: int,
    variant_id: object | None = None,
) -> tuple[int, int] | None:
    """Return the authored ground root for one dedicated enemy pose."""

    point = enemy_pose_anchors(kind, state, tick, variant_id).get("root")
    return point if isinstance(point, tuple) else None


def enemy_release_anchor(
    kind: object,
    state: object,
    tick: int,
    variant_id: object | None = None,
) -> tuple[int, int] | None:
    """Return the authored projectile-release point for one enemy pose."""

    point = enemy_pose_anchors(kind, state, tick, variant_id).get("release_anchor")
    return point if isinstance(point, tuple) else None


def boss_frame(state: object, tick: int) -> pygame.Surface | None:
    return animation_frame("couch", state, tick)


def jerry_frame(state: object, tick: int) -> pygame.Surface | None:
    """Return Jerry's walker-supported idle, dialogue, or pointing pose."""

    return animation_frame("jerry", state, tick)


def victory_frame(index: int) -> pygame.Surface | None:
    """Return one of eight authored Dave/Shelly/Chief celebration poses."""

    frames = animation_frames("victory", "celebration")
    if not frames:
        return None
    return frames[max(0, min(len(frames) - 1, int(index)))]


def sunset_frame(index: int) -> pygame.Surface | None:
    """Return one of eight detailed Dave/Shelly/Chief BMX ride-off poses."""

    frames = animation_frames("sunset", "ride")
    if not frames:
        return None
    return frames[max(0, int(index)) % len(frames)]


def clear_cache() -> None:
    """Reload edited external atlases on the next draw."""

    _load_frames.cache_clear()
    _authored_animation_frames.cache_clear()
    _dave_stable_walk_frames.cache_clear()
    _load_dave_fist_metadata.cache_clear()
    _dave_fist_anchors.cache_clear()
    _load_enemy_variant_anchor_metadata.cache_clear()


__all__ = [
    "ANIMATION_PLAYBACK_HZ",
    "animation_frame",
    "animation_frames",
    "boss_frame",
    "chief_frame",
    "clear_cache",
    "enemy_frame",
    "enemy_pose_anchors",
    "enemy_release_anchor",
    "enemy_root_anchor",
    "jerry_frame",
    "ko_frame",
    "player_frame",
    "player_fist_anchors",
    "sunset_frame",
    "total_authored_poses",
    "victory_frame",
]
