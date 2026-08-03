"""Authored pixel-sprite atlas loader and animation-state mapping."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

import pygame

from .animation_manifest import (
    ANIMATION_CLIPS,
    ANIMATION_PLAYBACK_HZ,
    AnimationClip,
    clip_for,
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
DAVE_STABLE_WALK_HOLD_TICKS = 2
DAVE_STABLE_WALK_STRIP = "assets/sprites/black_dave_walk_12.png"


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


def player_frame(character: object, state: object, tick: int) -> pygame.Surface | None:
    """Return one of the hero's authored phase poses."""

    name = str(character or "black_dave").strip().lower().replace("-", "_").replace(" ", "_")
    name = "shelly" if name in {"shelly", "shellie"} else "black_dave"
    state_name = _state_name(state)
    tick = max(0, int(tick))
    if name == "black_dave" and state_name == "walk":
        frames = _dave_stable_walk_frames()
        if frames:
            return frames[(tick // DAVE_STABLE_WALK_HOLD_TICKS) % len(frames)]
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


def enemy_frame(kind: object, state: object, tick: int) -> pygame.Surface | None:
    enemy_kind = str(kind or "stick").strip().lower().replace("-", "_").replace(" ", "_")
    if enemy_kind in {"shopping_cart", "cart_pusher"}:
        enemy_kind = "cart"
    elif enemy_kind in {"makeshift_whip", "cord"}:
        enemy_kind = "whip"
    elif enemy_kind in {"broken_pipe", "thrower"}:
        enemy_kind = "pipe"
    if enemy_kind not in {"stick", "cart", "whip", "pipe"}:
        enemy_kind = "stick"
    return animation_frame(enemy_kind, state, tick)


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


__all__ = [
    "ANIMATION_PLAYBACK_HZ",
    "animation_frame",
    "animation_frames",
    "boss_frame",
    "chief_frame",
    "clear_cache",
    "enemy_frame",
    "jerry_frame",
    "player_frame",
    "player_fist_anchors",
    "sunset_frame",
    "total_authored_poses",
    "victory_frame",
]
