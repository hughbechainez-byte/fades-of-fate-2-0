"""Render deterministic, fail-closed KO gameplay review GIFs.

This tool intentionally has no procedural or Black Dave fallback.  KO's
authored runtime hooks must exist before any review artifact is written.
Six clips exercise the real KO atlas/draw path on a runtime stage. Preparation,
daze, and super use real FadesGame fixtures and advance through the ordinary
update/draw loop, including the runtime dialogue and victim effects.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from typing import Any, Callable, Mapping, Sequence


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LOGICAL_SIZE = (640, 360)
SIMULATION_HZ = 60
DEFAULT_FPS = 30
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "build" / "ko_review_gifs"


class ReviewIntegrationError(RuntimeError):
    """Raised when the authored KO runtime cannot produce trustworthy proof."""


@dataclass(frozen=True, slots=True)
class DirectClip:
    name: str
    state_candidates: tuple[str, ...]
    seconds: float
    facing: int = 1
    movement: int = 0
    enemy_layout: str = "none"


DIRECT_CLIPS: tuple[DirectClip, ...] = (
    DirectClip("skate_right", ("skate", "skateboard", "travel", "walk"), 1.6, facing=1, movement=1),
    DirectClip("skate_left", ("skate", "skateboard", "travel", "walk"), 1.6, facing=-1, movement=-1),
    DirectClip("idle_glove_up", ("idle_glove_up", "glove_up", "gloves_on", "idle"), 2.4),
    DirectClip("target_prep", ("target_prep", "attack_prep", "warmup", "fight_stance", "prepare"), 2.2, enemy_layout="prep"),
    DirectClip("punch_jab_cross", ("punch_jab_cross", "jab_cross", "punch_1"), 1.2, enemy_layout="target"),
    DirectClip("punch_hook_uppercut", ("punch_hook_uppercut", "hook_uppercut", "punch_2"), 1.3, enemy_layout="target"),
    DirectClip("kick_roundhouse", ("kick_roundhouse", "roundhouse", "kick"), 1.3, enemy_layout="target"),
)

GAMEPLAY_CLIPS: tuple[tuple[str, float], ...] = (
    ("target_prep", 1.05),
    ("daze_wobble_fall", 5.0),
    ("super_flash_clear", 4.8),
)

EXPECTED_GIF_NAMES: tuple[str, ...] = (
    "skate_right.gif",
    "skate_left.gif",
    "idle_glove_up.gif",
    "target_prep.gif",
    "punch_jab_cross.gif",
    "punch_hook_uppercut.gif",
    "kick_roundhouse.gif",
    "daze_wobble_fall.gif",
    "super_flash_clear.gif",
)

LIGHTNING_REVIEW_STYLES: dict[
    str,
    tuple[str, tuple[int, int, int], int],
] = {
    "punch_jab_cross": ("ko_lightning_jab", (91, 226, 255), 38),
    "punch_hook_uppercut": ("ko_lightning_cross", (191, 119, 255), 46),
    "kick_roundhouse": ("ko_lightning_kick", (255, 218, 82), 52),
}
LIGHTNING_SUPER_STYLE = ("ko_lightning_super", (178, 241, 255), 88)


@dataclass(slots=True)
class RuntimeBindings:
    sprite_atlas: Any
    pixel_art: Any
    game_class: type[Any]
    input_manager_class: type[Any]
    ko_class: type[Any]
    enemy_class: type[Any]
    ko_frame: Callable[..., pygame.Surface | None]
    draw_ko: Callable[..., Any]
    animation_manifest: Any | None

    @classmethod
    def load(cls) -> "RuntimeBindings":
        sprite_atlas = importlib.import_module("src.sprite_atlas")
        pixel_art = importlib.import_module("src.pixel_art")
        game_module = importlib.import_module("src.game")
        input_module = importlib.import_module("src.input_manager")
        entities = importlib.import_module("src.entities")

        ko_frame = getattr(sprite_atlas, "ko_frame", None)
        draw_ko = getattr(pixel_art, "draw_ko", None)
        game_class = getattr(game_module, "FadesGame", None)
        input_manager_class = getattr(input_module, "InputManager", None)
        ko_class = getattr(entities, "KOCompanion", None)
        enemy_class = getattr(entities, "Enemy", None)
        missing = [
            name
            for name, value in (
                ("src.sprite_atlas.ko_frame", ko_frame),
                ("src.pixel_art.draw_ko", draw_ko),
                ("src.game.FadesGame", game_class),
                ("src.input_manager.InputManager", input_manager_class),
                ("src.entities.KOCompanion", ko_class),
                ("src.entities.Enemy", enemy_class),
            )
            if not callable(value)
        ]
        if missing:
            raise ReviewIntegrationError(
                "KO review runtime is incomplete; refusing placeholder output. Missing: "
                + ", ".join(missing)
            )

        runtime_size = tuple(getattr(game_module, "LOGICAL_SIZE", LOGICAL_SIZE))
        if runtime_size != LOGICAL_SIZE:
            raise ReviewIntegrationError(
                f"KO review requires the 640x360 logical canvas, got {runtime_size!r}"
            )
        try:
            animation_manifest = importlib.import_module("src.animation_manifest")
        except ImportError:
            animation_manifest = None
        return cls(
            sprite_atlas=sprite_atlas,
            pixel_art=pixel_art,
            game_class=game_class,
            input_manager_class=input_manager_class,
            ko_class=ko_class,
            enemy_class=enemy_class,
            ko_frame=ko_frame,
            draw_ko=draw_ko,
            animation_manifest=animation_manifest,
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return result.stdout.strip()


def _frame_durations(frame_count: int, fps: int) -> list[int]:
    """Return centisecond-safe GIF durations with an exact average cadence."""

    if frame_count < 1:
        raise ValueError("frame_count must be positive")
    if fps < 1 or fps > 60:
        raise ValueError("fps must be between 1 and 60")
    boundaries_cs = [round(index * 100 / fps) for index in range(frame_count + 1)]
    durations = [
        max(1, boundaries_cs[index + 1] - boundaries_cs[index]) * 10
        for index in range(frame_count)
    ]
    return durations


def _shared_palette(frames: Sequence[Image.Image]) -> Image.Image:
    if not frames:
        raise ValueError("at least one frame is required")
    width, height = frames[0].size
    sample_size = (min(160, width), min(90, height))
    samples = [
        frame.convert("RGB").resize(sample_size, Image.Resampling.NEAREST)
        for frame in frames
    ]
    sheet = Image.new("RGB", (sample_size[0], sample_size[1] * len(samples)))
    for index, sample in enumerate(samples):
        sheet.paste(sample, (0, index * sample_size[1]))
    return sheet.convert(
        "P",
        palette=Image.Palette.ADAPTIVE,
        colors=255,
        dither=Image.Dither.NONE,
    )


def _save_gif(frames: Sequence[Image.Image], path: Path, durations: Sequence[int]) -> None:
    if not frames:
        raise ValueError("at least one GIF frame is required")
    if len(frames) != len(durations):
        raise ValueError("GIF frame and duration counts differ")
    expected_size = frames[0].size
    if expected_size != LOGICAL_SIZE:
        raise ValueError(f"review frames must be 640x360, got {expected_size!r}")
    if any(frame.size != expected_size for frame in frames):
        raise ValueError("all GIF frames must share one logical size")
    if any(duration <= 0 or duration % 10 for duration in durations):
        raise ValueError("GIF durations must be positive centisecond multiples")

    palette = _shared_palette(frames)
    indexed = [
        frame.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE)
        for frame in frames
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    indexed[0].save(
        path,
        save_all=True,
        append_images=indexed[1:],
        duration=list(durations),
        loop=0,
        disposal=2,
        optimize=False,
    )


def _artifact_record(path: Path) -> dict[str, Any]:
    with Image.open(path) as gif:
        durations: list[int] = []
        for index in range(gif.n_frames):
            gif.seek(index)
            durations.append(int(gif.info.get("duration", 0)))
        return {
            "file": path.name,
            "sha256": _sha256(path),
            "width": gif.width,
            "height": gif.height,
            "frame_count": gif.n_frames,
            "frame_durations_ms": durations,
            "total_duration_ms": sum(durations),
        }


def _write_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def _surface_image(surface: pygame.Surface) -> Image.Image:
    return Image.frombytes(
        "RGB",
        surface.get_size(),
        pygame.image.tobytes(surface, "RGB", False),
    )


def _annotate(frame: Image.Image, label: str, frame_index: int, frame_count: int) -> Image.Image:
    shown = frame.convert("RGB")
    draw = ImageDraw.Draw(shown)
    draw.rectangle((0, 0, LOGICAL_SIZE[0] - 1, 21), fill=(14, 17, 24))
    font = ImageFont.load_default()
    draw.text((7, 6), f"KO REVIEW / {label.upper()}", fill=(246, 239, 224), font=font)
    counter = f"{frame_index + 1:03d}/{frame_count:03d}"
    counter_width = draw.textbbox((0, 0), counter, font=font)[2]
    draw.text((LOGICAL_SIZE[0] - counter_width - 7, 6), counter, fill=(169, 220, 255), font=font)
    return shown


def _call_with_supported_keywords(
    function: Callable[..., Any],
    values: Mapping[str, Any],
    *,
    label: str,
) -> Any:
    signature = inspect.signature(function)
    kwargs: dict[str, Any] = {}
    missing: list[str] = []
    for name, parameter in signature.parameters.items():
        if parameter.kind in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}:
            continue
        if name in values:
            kwargs[name] = values[name]
        elif parameter.default is parameter.empty:
            missing.append(name)
    if missing:
        raise ReviewIntegrationError(
            f"{label} has unsupported required parameters: {', '.join(missing)}"
        )
    try:
        return function(**kwargs)
    except Exception as error:
        raise ReviewIntegrationError(f"{label} failed: {error}") from error


def _runtime_ko_frame(bindings: RuntimeBindings, state: str, tick: int) -> pygame.Surface:
    frame = _call_with_supported_keywords(
        bindings.ko_frame,
        {"state": state, "tick": tick, "frame": tick, "animation_tick": tick},
        label="src.sprite_atlas.ko_frame",
    )
    if not isinstance(frame, pygame.Surface):
        raise ReviewIntegrationError(
            f"ko_frame({state!r}, {tick}) returned no authored pygame.Surface"
        )
    if not frame.get_bounding_rect(min_alpha=1).w:
        raise ReviewIntegrationError(f"ko_frame({state!r}, {tick}) is empty")
    return frame


def _draw_runtime_ko(
    bindings: RuntimeBindings,
    surface: pygame.Surface,
    *,
    x: float,
    y: float,
    facing: int,
    state: str,
    tick: int,
) -> Any:
    before = pygame.image.tobytes(surface, "RGBA", False)
    result = _call_with_supported_keywords(
        bindings.draw_ko,
        {
            "surface": surface,
            "canvas": surface,
            "x": x,
            "y": y,
            "z": 0.0,
            "facing": facing,
            "state": state,
            "frame": tick,
            "tick": tick,
            "animation_tick": tick,
            "hit_flash": 0.0,
        },
        label="src.pixel_art.draw_ko",
    )
    if pygame.image.tobytes(surface, "RGBA", False) == before:
        raise ReviewIntegrationError(
            f"draw_ko rendered no visible authored pixels for state {state!r}"
        )
    return result


def _frame_signature(surface: pygame.Surface) -> str:
    digest = hashlib.sha256()
    digest.update(f"{surface.get_width()}x{surface.get_height()}".encode("ascii"))
    digest.update(pygame.image.tobytes(surface, "RGBA", False))
    return digest.hexdigest()


def _manifest_clip_is_exact(bindings: RuntimeBindings, state: str) -> bool | None:
    clip_for = getattr(bindings.animation_manifest, "clip_for", None)
    if not callable(clip_for):
        return None
    try:
        clip = clip_for("ko", state)
    except Exception:
        return None
    return (
        str(getattr(clip, "actor", "")).strip().lower() == "ko"
        and str(getattr(clip, "state", "")).strip().lower() == state
    )


def _resolve_state(bindings: RuntimeBindings, candidates: Sequence[str]) -> tuple[str, int]:
    failures: list[str] = []
    for state in candidates:
        exact = _manifest_clip_is_exact(bindings, state)
        if exact is False:
            failures.append(f"{state}: animation manifest redirected to another clip")
            continue
        try:
            signatures = {
                _frame_signature(_runtime_ko_frame(bindings, state, tick))
                for tick in range(48)
            }
        except ReviewIntegrationError as error:
            failures.append(f"{state}: {error}")
            continue
        if len(signatures) < 4:
            failures.append(f"{state}: only {len(signatures)} distinct authored poses")
            continue
        return state, len(signatures)
    raise ReviewIntegrationError(
        "No authored KO state satisfies "
        + "/".join(candidates)
        + ". "
        + " | ".join(failures)
    )


def _resolve_direct_states(bindings: RuntimeBindings) -> tuple[dict[str, str], dict[str, int]]:
    resolved: dict[str, str] = {}
    unique_counts: dict[str, int] = {}
    by_candidates: dict[tuple[str, ...], tuple[str, int]] = {}
    for clip in DIRECT_CLIPS:
        state_and_count = by_candidates.get(clip.state_candidates)
        if state_and_count is None:
            state_and_count = _resolve_state(bindings, clip.state_candidates)
            by_candidates[clip.state_candidates] = state_and_count
        resolved[clip.name], unique_counts[clip.name] = state_and_count

    # Super is captured through the real game loop rather than the direct
    # renderer, but it still participates in authored-state, provenance, and
    # skateboard-absence validation.
    super_state, super_count = _resolve_state(
        bindings,
        ("super_flash_clear", "speed_blitz", "super"),
    )
    resolved["super_flash_clear"] = super_state
    unique_counts["super_flash_clear"] = super_count

    canonical_sequences: dict[str, tuple[str, ...]] = {}
    for state in sorted(set(resolved.values())):
        if state in canonical_sequences:
            continue
        canonical_sequences[state] = tuple(
            _frame_signature(_runtime_ko_frame(bindings, state, tick))
            for tick in range(24)
        )
    inverted: dict[tuple[str, ...], list[str]] = {}
    for state, sequence in canonical_sequences.items():
        inverted.setdefault(sequence, []).append(state)
    duplicates = [states for states in inverted.values() if len(states) > 1]
    if duplicates:
        raise ReviewIntegrationError(
            "KO states silently share the same authored animation: "
            + "; ".join(", ".join(states) for states in duplicates)
        )
    return resolved, unique_counts


def _stage_base(bindings: RuntimeBindings) -> pygame.Surface:
    draw_background = getattr(bindings.pixel_art, "draw_stage_background", None)
    if not callable(draw_background):
        raise ReviewIntegrationError("src.pixel_art.draw_stage_background is unavailable")
    failures: list[str] = []
    for theme in ("sprouts_el_cilantro", "legacy_second_street"):
        surface = pygame.Surface(LOGICAL_SIZE)
        surface.fill((12, 16, 22))
        try:
            _call_with_supported_keywords(
                draw_background,
                {
                    "surface": surface,
                    "camera_x": 800.0,
                    "stage_width": 4200.0,
                    "shake_y": 0.0,
                    "theme": theme,
                    "atmosphere": None,
                },
                label="src.pixel_art.draw_stage_background",
            )
        except ReviewIntegrationError as error:
            failures.append(str(error))
            continue
        return surface
    raise ReviewIntegrationError("Could not render a runtime stage: " + " | ".join(failures))


def _draw_enemy(
    bindings: RuntimeBindings,
    surface: pygame.Surface,
    *,
    x: float,
    state: str,
    tick: int,
    hit_flash: float = 0.0,
) -> None:
    draw_enemy = getattr(bindings.pixel_art, "draw_enemy", None)
    if not callable(draw_enemy):
        raise ReviewIntegrationError("src.pixel_art.draw_enemy is unavailable")
    _call_with_supported_keywords(
        draw_enemy,
        {
            "surface": surface,
            "x": x,
            "y": 300.0,
            "z": 0.0,
            "facing": -1,
            "state": state,
            "kind": "stick",
            "frame": tick,
            "tick": tick,
            "hit_flash": hit_flash,
        },
        label="src.pixel_art.draw_enemy",
    )


def _draw_attack_lightning(
    bindings: RuntimeBindings,
    surface: pygame.Surface,
    *,
    clip_name: str,
    tick: int,
) -> None:
    style = LIGHTNING_REVIEW_STYLES.get(clip_name)
    if style is None:
        return
    draw_effect = getattr(bindings.pixel_art, "draw_effect", None)
    if not callable(draw_effect):
        raise ReviewIntegrationError("src.pixel_art.draw_effect is unavailable")
    kind, color, radius = style
    _call_with_supported_keywords(
        draw_effect,
        {
            "surface": surface,
            "x": 382.0,
            "y": 274.0 if clip_name == "kick_roundhouse" else 258.0,
            "z": 0.0,
            "kind": f"{kind}_right",
            "frame": tick,
            "color": color,
            "radius": radius,
        },
        label=f"src.pixel_art.draw_effect:{kind}",
    )


def _validate_lightning_signatures(bindings: RuntimeBindings) -> dict[str, Any]:
    """Prove that every KO attack owns a distinct moving lightning render."""

    draw_effect = getattr(bindings.pixel_art, "draw_effect", None)
    if not callable(draw_effect):
        raise ReviewIntegrationError("src.pixel_art.draw_effect is unavailable")
    styles = dict(LIGHTNING_REVIEW_STYLES)
    styles["super_flash_clear"] = LIGHTNING_SUPER_STYLE
    signatures: set[str] = set()
    records: dict[str, Any] = {}
    for name, (kind, color, radius) in styles.items():
        frames: list[str] = []
        opaque_counts: list[int] = []
        for tick in (0, 5):
            surface = pygame.Surface((320, 180), pygame.SRCALPHA)
            _call_with_supported_keywords(
                draw_effect,
                {
                    "surface": surface,
                    "x": 160.0,
                    "y": 90.0,
                    "z": 0.0,
                    "kind": f"{kind}_right",
                    "frame": tick,
                    "color": color,
                    "radius": radius,
                },
                label=f"src.pixel_art.draw_effect:{kind}",
            )
            frames.append(_frame_signature(surface))
            opaque_counts.append(pygame.mask.from_surface(surface).count())
        if min(opaque_counts) < 20:
            raise ReviewIntegrationError(f"{kind} rendered too few visible lightning pixels")
        if frames[0] == frames[1]:
            raise ReviewIntegrationError(f"{kind} has no phase-driven lightning motion")
        if frames[0] in signatures:
            raise ReviewIntegrationError(f"{kind} duplicates another KO lightning signature")
        signatures.add(frames[0])
        records[name] = {
            "effect_kind": kind,
            "color": list(color),
            "radius": radius,
            "opaque_pixels": opaque_counts,
            "phase_motion": "pass",
        }
    return {"status": "pass", "distinct_signatures": len(signatures), "attacks": records}


def _render_direct_clip(
    bindings: RuntimeBindings,
    base: pygame.Surface,
    clip: DirectClip,
    state: str,
    fps: int,
) -> tuple[list[Image.Image], list[int]]:
    frame_count = max(2, round(clip.seconds * fps))
    frames: list[Image.Image] = []
    for index in range(frame_count):
        tick = round(index * 30 / fps)
        surface = base.copy()
        active_window = False
        if clip.enemy_layout == "target":
            active_window = frame_count // 3 <= index < frame_count * 2 // 3
            _draw_enemy(
                bindings,
                surface,
                x=402.0,
                state="hurt" if active_window else "idle",
                tick=tick,
                hit_flash=0.08 if active_window else 0.0,
            )
        elif clip.enemy_layout == "prep":
            _draw_enemy(bindings, surface, x=405.0, state="idle", tick=tick)
            _draw_enemy(bindings, surface, x=500.0, state="hurt", tick=tick, hit_flash=0.04)

        if clip.movement > 0:
            x = 190.0 + 96.0 * index / max(1, frame_count - 1)
        elif clip.movement < 0:
            x = 450.0 - 96.0 * index / max(1, frame_count - 1)
        else:
            x = 285.0
        _draw_runtime_ko(
            bindings,
            surface,
            x=x,
            y=300.0,
            facing=clip.facing,
            state=state,
            tick=tick,
        )
        if active_window:
            _draw_attack_lightning(
                bindings,
                surface,
                clip_name=clip.name,
                tick=tick,
            )
        frames.append(_annotate(_surface_image(surface), clip.name, index, frame_count))
    return frames, _frame_durations(frame_count, fps)


def _cropped_visible(surface: pygame.Surface) -> pygame.Surface:
    bounds = surface.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        raise ReviewIntegrationError("KO mirror probe rendered an empty actor")
    return surface.subsurface(bounds).copy()


def _validate_exact_mirror(
    draw_ko: Callable[..., Any] | RuntimeBindings,
    state: str,
    ticks: Sequence[int],
) -> dict[str, Any]:
    """Validate that facing is one exact horizontal mirror of authored pixels."""

    if isinstance(draw_ko, RuntimeBindings):
        bindings = draw_ko
        facing_variant = getattr(bindings.pixel_art, "_grounded_sprite_variant", None)
        if not callable(facing_variant):
            raise ReviewIntegrationError(
                "KO mirror proof requires pixel_art._grounded_sprite_variant, "
                "the facing helper used by draw_ko"
            )

        checked = 0
        for tick in ticks:
            authored = _runtime_ko_frame(bindings, state, int(tick))
            right, _ = facing_variant(authored, 1)
            left, _ = facing_variant(authored, -1)
            mirrored_left = pygame.transform.flip(left, True, False)
            if mirrored_left.get_size() != right.get_size() or pygame.image.tobytes(
                mirrored_left, "RGBA", False
            ) != pygame.image.tobytes(right, "RGBA", False):
                raise ReviewIntegrationError(
                    f"KO left/right skate body is not an exact mirror at tick {tick}"
                )

            # draw_ko adds a world-lighting shadow that intentionally does not
            # flip with the actor.  Verify separately that the public draw hook
            # actually forwards facing, while the exact comparison above is
            # performed on the authored body/board layer it blits.
            right_render = pygame.Surface((320, 208), pygame.SRCALPHA)
            left_render = pygame.Surface((320, 208), pygame.SRCALPHA)
            _draw_runtime_ko(
                bindings,
                right_render,
                x=160.0,
                y=190.0,
                facing=1,
                state=state,
                tick=int(tick),
            )
            _draw_runtime_ko(
                bindings,
                left_render,
                x=160.0,
                y=190.0,
                facing=-1,
                state=state,
                tick=int(tick),
            )
            if pygame.image.tobytes(right_render, "RGBA", False) == pygame.image.tobytes(
                left_render, "RGBA", False
            ):
                raise ReviewIntegrationError(
                    f"draw_ko ignored skate facing at tick {tick}"
                )
            checked += 1
        return {
            "status": "pass",
            "state": state,
            "ticks_checked": checked,
            "method": "draw_ko facing plus exact grounded body/board variant",
            "world_lighting_shadow_excluded": True,
        }

    painter = draw_ko

    checked = 0
    for tick in ticks:
        right = pygame.Surface((320, 208), pygame.SRCALPHA)
        left = pygame.Surface((320, 208), pygame.SRCALPHA)
        painter(right, 1, int(tick))
        painter(left, -1, int(tick))
        right_crop = _cropped_visible(right)
        left_crop = _cropped_visible(left)
        mirrored_left = pygame.transform.flip(left_crop, True, False)
        if mirrored_left.get_size() != right_crop.get_size() or pygame.image.tobytes(
            mirrored_left, "RGBA", False
        ) != pygame.image.tobytes(right_crop, "RGBA", False):
            raise ReviewIntegrationError(
                f"KO left/right skate rendering is not an exact mirror at tick {tick}"
            )
        checked += 1
    return {"status": "pass", "state": state, "ticks_checked": checked}


def _bottom_horizontal_run(frame: pygame.Surface, band_height: int = 12) -> int:
    """Return the longest continuous opaque run near an authored pose's feet.

    A skateboard deck reads as one long horizontal component.  Comparing that
    component is more discriminating than comparing the total foot span: a
    wide fighting stance can place two ordinary shoes farther apart than the
    board without ever joining them into a deck.
    """

    bounds = frame.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        return 0
    top = max(bounds.top, bounds.bottom - band_height)
    longest = 0
    for y in range(top, bounds.bottom):
        run = 0
        for x in range(bounds.left, bounds.right):
            if frame.get_at((x, y)).a >= 16:
                run += 1
                longest = max(longest, run)
            else:
                run = 0
    return longest


def _bottom_warm_board_pixels(frame: pygame.Surface, band_height: int = 14) -> int:
    """Count the visible warm deck/wheel material near the grounded edge."""

    bounds = frame.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        return 0
    top = max(bounds.top, bounds.bottom - band_height)
    count = 0
    for y in range(top, bounds.bottom):
        for x in range(bounds.left, bounds.right):
            color = frame.get_at((x, y))
            if (
                color.a >= 16
                and color.r >= 120
                and color.g >= 55
                and color.b <= 100
                and color.r >= color.g * 1.15
            ):
                count += 1
    return count


def _semantic_features(bindings: RuntimeBindings, state: str, tick: int) -> set[str] | None:
    for name in ("ko_frame_features", "ko_features", "ko_semantic_features"):
        function = getattr(bindings.sprite_atlas, name, None)
        if not callable(function):
            continue
        result = _call_with_supported_keywords(
            function,
            {"state": state, "tick": tick, "frame": tick},
            label=f"src.sprite_atlas.{name}",
        )
        if isinstance(result, Mapping):
            return {str(key).lower() for key, value in result.items() if value}
        if isinstance(result, (set, frozenset, tuple, list)):
            return {str(value).lower() for value in result}
        raise ReviewIntegrationError(f"{name} must return a mapping or collection")
    return None


def _validate_features(
    bindings: RuntimeBindings,
    states: Mapping[str, str],
    *,
    strict: bool,
) -> dict[str, Any]:
    skate_state = states["skate_right"]
    nontravel_names = (
        "idle_glove_up",
        "target_prep",
        "punch_jab_cross",
        "punch_hook_uppercut",
        "kick_roundhouse",
        "super_flash_clear",
    )
    feature_probe = _semantic_features(bindings, skate_state, 0)
    if feature_probe is not None:
        travel_features = [
            _semantic_features(bindings, skate_state, tick) or set()
            for tick in range(24)
        ]
        nontravel_features = {
            name: [
                _semantic_features(bindings, states[name], tick) or set()
                for tick in range(24)
            ]
            for name in nontravel_names
        }
        board_names = {"skateboard", "skate_board", "board"}
        glove_names = {"mma_gloves", "mma_glove", "combat_gloves", "gloves"}
        if not all(features & board_names for features in travel_features):
            raise ReviewIntegrationError("KO semantic metadata does not keep the skateboard in every travel frame")
        if any(
            features & board_names
            for clips in nontravel_features.values()
            for features in clips
        ):
            raise ReviewIntegrationError("KO semantic metadata leaks the skateboard into a non-travel state")
        combat_names = (
            "target_prep",
            "punch_jab_cross",
            "punch_hook_uppercut",
            "kick_roundhouse",
            "super_flash_clear",
        )
        if any(
            not any(features & glove_names for features in nontravel_features[name])
            for name in combat_names
        ):
            raise ReviewIntegrationError("KO semantic metadata does not identify MMA gloves in every combat clip")
        return {
            "skateboard_only_during_travel": {"status": "pass", "method": "runtime_semantic_metadata"},
            "mma_gloves_during_combat": {"status": "pass", "method": "runtime_semantic_metadata"},
        }

    skate_runs = [
        _bottom_horizontal_run(_runtime_ko_frame(bindings, skate_state, tick))
        for tick in range(24)
    ]
    skate_warm_pixels = [
        _bottom_warm_board_pixels(_runtime_ko_frame(bindings, skate_state, tick))
        for tick in range(24)
    ]
    nontravel_warm_pixels = {
        name: [
            _bottom_warm_board_pixels(_runtime_ko_frame(bindings, states[name], tick))
            for tick in range(24)
        ]
        for name in nontravel_names
    }
    minimum_skate_run = min(skate_runs)
    minimum_skate_warm_pixels = min(skate_warm_pixels)
    maximum_nontravel_warm_pixels = max(
        count
        for counts in nontravel_warm_pixels.values()
        for count in counts
    )
    warm_pixel_margin = minimum_skate_warm_pixels - maximum_nontravel_warm_pixels
    structural_pass = (
        minimum_skate_run >= 24
        and minimum_skate_warm_pixels >= 12
        and maximum_nontravel_warm_pixels <= 8
        and warm_pixel_margin >= 12
    )
    if strict and not structural_pass:
        raise ReviewIntegrationError(
            "Skateboard-only structural check is inconclusive: travel deck run "
            f"{minimum_skate_run}px, travel warm material "
            f"{minimum_skate_warm_pixels}px, non-travel warm material maximum "
            f"{maximum_nontravel_warm_pixels}px"
        )
    return {
        "skateboard_only_during_travel": {
            "status": "pass" if structural_pass else "manual_review_required",
            "method": "continuous_deck_plus_warm_bottom_material",
            "minimum_travel_horizontal_run_px": minimum_skate_run,
            "minimum_travel_warm_material_pixels": minimum_skate_warm_pixels,
            "maximum_nontravel_warm_material_pixels": maximum_nontravel_warm_pixels,
            "warm_material_separation_margin_pixels": warm_pixel_margin,
        },
        "mma_gloves_during_combat": {
            "status": "manual_review_required",
            "method": "no_runtime_semantic_metadata",
            "review_clips": [
                "idle_glove_up",
                "target_prep",
                "punch_jab_cross",
                "punch_hook_uppercut",
                "kick_roundhouse",
                "super_flash_clear",
            ],
        },
    }


def _locate_ko(game: Any, ko_class: type[Any]) -> Any | None:
    for name in ("ko_companion", "ko"):
        candidate = getattr(game, name, None)
        if isinstance(candidate, ko_class):
            return candidate
    for name in ("ko_companions", "companions", "allies"):
        candidates = getattr(game, name, ())
        if isinstance(candidates, Sequence):
            for candidate in candidates:
                if isinstance(candidate, ko_class):
                    return candidate
    return None


def _activate_tool_gameplay_fixture(
    game: Any,
    bindings: RuntimeBindings,
    scenario: str,
) -> tuple[Any, Mapping[str, Any]]:
    """Arrange deterministic actors, then hand control back to real gameplay.

    This fixture never paints or advances a substitute entity.  It uses the
    game's existing visual-evidence stage setup, real Enemy instances, and
    KOCompanion's own target-claim/action state machine.  Every subsequent
    frame goes through FadesGame.update and FadesGame.draw.
    """

    activate_scene = getattr(game, "_activate_visual_evidence_scene", None)
    if not callable(activate_scene):
        raise ReviewIntegrationError(
            "FadesGame has no deterministic visual-evidence stage setup"
        )
    activate_scene()
    # Keep the review focused on KO rather than startup HUD cards.
    game.route_card_timer = 0.0
    game.stage_banner_timer = 0.0
    companion = _locate_ko(game, bindings.ko_class)
    if companion is None:
        raise ReviewIntegrationError(
            "ordinary stage startup did not install a real KOCompanion"
        )

    owner = getattr(companion, "owner", None)
    if owner is None:
        raise ReviewIntegrationError("KOCompanion has no owning player")
    # Other helpers are parked out of the proof so only KO can damage the
    # fixture targets.  The owning human remains in the ordinary update loop.
    game.players = [owner]
    if hasattr(game, "chiefs"):
        game.chiefs.clear()
    if hasattr(game, "projectiles"):
        game.projectiles.clear()
    if hasattr(game, "spawn_queue"):
        game.spawn_queue.clear()
    game.encounter_active = False
    game.active_gate = None
    # The fixed evidence camera intersects an authored ambush trigger after a
    # few seconds.  Advance only that unrelated content cursor so the review
    # cannot acquire fresh non-fixture enemies near its final frame.
    runtime_content = getattr(game, "runtime_chapter_content", {})
    environmental_events = (
        runtime_content.get("environmental_events", ())
        if isinstance(runtime_content, Mapping)
        else ()
    )
    game._content_event_index = len(environmental_events)
    reinforcements = getattr(game, "_post_clear_reinforcements", None)
    if hasattr(reinforcements, "clear"):
        reinforcements.clear()
    game._content_event_ambush_active = False

    camera_x = float(getattr(game, "_render_camera_x", getattr(game, "camera_x", 0.0)))
    owner.x = camera_x + 92.0
    owner.y = 292.0
    if callable(getattr(owner, "set_state", None)):
        owner.set_state("idle")
    companion.x = camera_x + 244.0
    companion.y = 300.0
    companion.facing = 1

    enemy_count = 4 if scenario == "super_flash_clear" else 1
    positions = (
        (camera_x + 308.0, 300.0),
        (camera_x + 360.0, 276.0),
        (camera_x + 450.0, 318.0),
        (camera_x + 540.0, 292.0),
    )
    try:
        enemy_config = game.data["enemies"]["stick"]
    except (AttributeError, KeyError, TypeError) as error:
        raise ReviewIntegrationError("FadesGame does not expose the authored stick-enemy config") from error
    enemies: list[Any] = []
    for index, (x, y) in enumerate(positions[:enemy_count]):
        enemy = bindings.enemy_class(90_000 + index, "stick", x, y, enemy_config)
        enemy.state = "chase"
        enemy.state_clock = 0.0
        enemy.state_duration = 0.0
        enemies.append(enemy)
    game.enemies = enemies

    companion.attack_cooldown = 0.0
    companion.attack_index = 0
    if scenario == "super_flash_clear":
        every = max(1, int(companion.config.get("super_every_actions", 4)))
        companion.completed_actions = every - 1
    claim_target = getattr(companion, "_claim_target", None)
    if not callable(claim_target):
        raise ReviewIntegrationError(
            "KOCompanion has no authored target-claim/action entry point"
        )
    claim_target(enemies[0], game)
    expected_action = "super" if scenario == "super_flash_clear" else "punch_1"
    if str(getattr(companion, "pending_action", "")) != expected_action:
        raise ReviewIntegrationError(
            f"KO fixture requested {expected_action}, got {getattr(companion, 'pending_action', '')!r}"
        )
    return companion, {
        "hook": "tool_fixture:FadesGame._activate_visual_evidence_scene+KOCompanion._claim_target",
        "fixture_enemy_count": enemy_count,
        "pending_action": expected_action,
    }


def _activate_gameplay_review(game: Any, bindings: RuntimeBindings, scenario: str) -> tuple[Any, Mapping[str, Any]]:
    specific_names = {
        "target_prep": (
            "_activate_ko_prepare_review_scene",
            "activate_ko_prepare_review_scene",
        ),
        "daze_wobble_fall": (
            "_activate_ko_daze_review_scene",
            "activate_ko_daze_review_scene",
        ),
        "super_flash_clear": (
            "_activate_ko_super_review_scene",
            "activate_ko_super_review_scene",
        ),
    }[scenario]
    generic_names = (
        "_activate_ko_review_scene",
        "activate_ko_review_scene",
        "_setup_ko_review_scene",
        "setup_ko_review_scene",
    )
    hook_result: Any = None
    used_hook = ""
    for name in (*specific_names, *generic_names):
        function = getattr(game, name, None)
        if not callable(function):
            continue
        hook_result = _call_with_supported_keywords(
            function,
            {"scenario": scenario, "name": scenario, "review_scenario": scenario},
            label=f"FadesGame.{name}",
        )
        used_hook = f"FadesGame.{name}"
        break

    companion = _locate_ko(game, bindings.ko_class)
    if not used_hook and companion is not None:
        for name in ("activate_review_scenario", "start_review_scenario", "setup_review_scenario"):
            function = getattr(companion, name, None)
            if not callable(function):
                continue
            hook_result = _call_with_supported_keywords(
                function,
                {
                    "scenario": scenario,
                    "name": scenario,
                    "review_scenario": scenario,
                    "game": game,
                },
                label=f"KOCompanion.{name}",
            )
            used_hook = f"KOCompanion.{name}"
            break

    if not used_hook:
        return _activate_tool_gameplay_fixture(game, bindings, scenario)
    companion = _locate_ko(game, bindings.ko_class)
    if companion is None:
        raise ReviewIntegrationError(f"{used_hook} did not install a real KOCompanion")
    if str(getattr(game, "state", "")) != "gameplay":
        raise ReviewIntegrationError(f"{used_hook} did not enter ordinary gameplay")
    metadata = dict(hook_result) if isinstance(hook_result, Mapping) else {}
    metadata["hook"] = used_hook
    return companion, metadata


def _live_enemies(game: Any) -> list[Any]:
    inactive = {"dead", "eliminated", "removed"}
    return [
        enemy
        for enemy in list(getattr(game, "enemies", ()))
        if str(getattr(enemy, "state", "")).lower() not in inactive
    ]


def _enemy_dazed(enemy: Any) -> bool:
    state = str(getattr(enemy, "state", "")).lower()
    if any(token in state for token in ("daze", "wobbl", "stun")):
        return True
    for name in ("daze_timer", "dazed_timer", "wobble_timer", "ko_daze_timer"):
        try:
            if float(getattr(enemy, name, 0.0)) > 0.0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _render_gameplay_clip(
    bindings: RuntimeBindings,
    scenario: str,
    seconds: float,
    fps: int,
) -> tuple[list[Image.Image], list[int], dict[str, Any]]:
    random.seed(0)
    manager = bindings.input_manager_class(max_players=4, discover_controllers=False)
    game = bindings.game_class(manager, mute=True)
    frame_count = max(2, round(seconds * fps))
    frames: list[Image.Image] = []
    try:
        companion, setup = _activate_gameplay_review(game, bindings, scenario)
        requested_seconds = setup.get("duration_seconds")
        if isinstance(requested_seconds, (int, float)) and requested_seconds > 0:
            frame_count = max(2, round(float(requested_seconds) * fps))
        before_count = len(_live_enemies(game))
        minimum_required = 2 if scenario == "super_flash_clear" else 1
        if before_count < minimum_required:
            raise ReviewIntegrationError(
                f"{scenario} review hook supplied {before_count} live enemies; "
                f"at least {minimum_required} required"
            )
        enemy_states: set[str] = set()
        companion_states: set[str] = set()
        daze_observed = False
        live_counts: list[int] = [before_count]
        object_counts: list[int] = [len(list(getattr(game, "enemies", ())))]
        canvas = pygame.Surface(LOGICAL_SIZE)
        for index in range(frame_count):
            for _ in range(SIMULATION_HZ // fps):
                game.update(1.0 / SIMULATION_HZ)
            game.draw(canvas)
            enemies = list(getattr(game, "enemies", ()))
            enemy_states.update(str(getattr(enemy, "state", "")) for enemy in enemies)
            companion_states.add(str(getattr(companion, "state", "")))
            daze_observed = daze_observed or any(_enemy_dazed(enemy) for enemy in enemies)
            live_counts.append(len(_live_enemies(game)))
            object_counts.append(len(enemies))
            frames.append(_annotate(_surface_image(canvas), scenario, index, frame_count))

        final_live = live_counts[-1]
        if scenario == "target_prep":
            if "prepare" not in {state.lower() for state in companion_states}:
                raise ReviewIntegrationError("target preparation review never entered KO's prepare state")
        elif scenario == "daze_wobble_fall":
            if not daze_observed:
                raise ReviewIntegrationError("daze gameplay review never entered a dazed/wobbling enemy state")
            if final_live >= before_count:
                raise ReviewIntegrationError("daze gameplay review did not end in enemy fall/removal")
            if object_counts[-1] != 0:
                raise ReviewIntegrationError("daze gameplay review ended before the defeated enemy disappeared")
        elif scenario == "super_flash_clear":
            if final_live != 0:
                raise ReviewIntegrationError(
                    f"super gameplay review left {final_live} live enemies instead of clearing the crowd"
                )
            if object_counts[-1] != 0:
                raise ReviewIntegrationError("super gameplay review ended before the defeated crowd disappeared")
        verification = {
            "hook": setup["hook"],
            "ordinary_update_calls": frame_count * (SIMULATION_HZ // fps),
            "ordinary_draw_calls": frame_count,
            "initial_live_enemy_count": before_count,
            "final_live_enemy_count": final_live,
            "minimum_live_enemy_count": min(live_counts),
            "initial_enemy_object_count": object_counts[0],
            "final_enemy_object_count": object_counts[-1],
            "minimum_enemy_object_count": min(object_counts),
            "daze_observed": daze_observed,
            "enemy_states_observed": sorted(enemy_states),
            "ko_states_observed": sorted(companion_states),
        }
        return frames, _frame_durations(frame_count, fps), verification
    finally:
        try:
            game.close()
        finally:
            manager.close()


def _asset_provenance(bindings: RuntimeBindings, states: Mapping[str, str]) -> list[dict[str, Any]]:
    paths: set[Path] = set()
    clip_for = getattr(bindings.animation_manifest, "clip_for", None)
    if callable(clip_for):
        for state in sorted(set(states.values())):
            try:
                clip = clip_for("ko", state)
            except Exception:
                continue
            if str(getattr(clip, "actor", "")).lower() != "ko":
                raise ReviewIntegrationError(f"KO state {state!r} resolves to a non-KO animation clip")
            relative = str(getattr(clip, "atlas", ""))
            if relative:
                paths.add(PROJECT_ROOT / relative)
    paths.update(
        path
        for path in (PROJECT_ROOT / "assets" / "sprites").glob("*ko*")
        if path.is_file() and path.suffix.lower() in {".png", ".json"}
    )
    paths = {path.resolve() for path in paths if "ko_preview" not in path.name.lower()}
    if not paths:
        raise ReviewIntegrationError(
            "No KO-specific runtime asset under assets/sprites could be proven; refusing preview art"
        )
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise ReviewIntegrationError(
            "KO animation manifest references missing assets: "
            + ", ".join(str(path) for path in missing)
        )
    return [
        {
            "path": path.relative_to(PROJECT_ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(paths)
    ]


def _render_review_artifacts(
    bindings: RuntimeBindings,
    artifact_dir: Path,
    *,
    fps: int,
    strict: bool,
) -> dict[str, Any]:
    states, unique_pose_counts = _resolve_direct_states(bindings)
    if states["skate_right"] != states["skate_left"]:
        raise ReviewIntegrationError("left and right travel did not resolve to one canonical KO state")
    mirror = _validate_exact_mirror(
        bindings,
        states["skate_right"],
        tuple(range(24)),
    )
    features = _validate_features(bindings, states, strict=strict)
    lightning = _validate_lightning_signatures(bindings)
    assets = _asset_provenance(bindings, states)
    base = _stage_base(bindings)

    artifacts: dict[str, dict[str, Any]] = {}
    for clip in DIRECT_CLIPS:
        if clip.name == "target_prep":
            # The real gameplay renderer owns the target-selection bubble and
            # its LET'S GET IT text; a direct sprite-only clip would omit them.
            continue
        frames, durations = _render_direct_clip(
            bindings,
            base,
            clip,
            states[clip.name],
            fps,
        )
        path = artifact_dir / f"{clip.name}.gif"
        _save_gif(frames, path, durations)
        record = _artifact_record(path)
        record.update(
            {
                "capture": "runtime_stage_plus_pixel_art.draw_ko",
                "runtime_state": states[clip.name],
                "facing": clip.facing,
                "unique_authored_pose_count": unique_pose_counts[clip.name],
            }
        )
        if clip.name in LIGHTNING_REVIEW_STYLES:
            record["lightning_effect"] = LIGHTNING_REVIEW_STYLES[clip.name][0]
        artifacts[clip.name] = record

    gameplay_verification: dict[str, Any] = {}
    for scenario, seconds in GAMEPLAY_CLIPS:
        frames, durations, verification = _render_gameplay_clip(
            bindings,
            scenario,
            seconds,
            fps,
        )
        path = artifact_dir / f"{scenario}.gif"
        _save_gif(frames, path, durations)
        record = _artifact_record(path)
        record["capture"] = "FadesGame.update_and_draw"
        if scenario == "super_flash_clear":
            record["lightning_effect"] = LIGHTNING_SUPER_STYLE[0]
        artifacts[scenario] = record
        gameplay_verification[scenario] = verification

    dirty_lines = [
        line
        for line in _git_output("status", "--short", "--untracked-files=all").splitlines()
        if line
    ]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generator": "tools/Render-KO-Review-Gifs.py",
        "logical_size": list(LOGICAL_SIZE),
        "capture_fps": fps,
        "simulation_hz": SIMULATION_HZ,
        "gif_encoder": {
            "library": f"Pillow {Image.__version__}",
            "palette": "shared adaptive 255-color",
            "dither": "none",
            "resampling": "nearest only",
        },
        "source": {
            "root": str(PROJECT_ROOT),
            "commit": _git_output("rev-parse", "HEAD"),
            "branch": _git_output("branch", "--show-current"),
            "commit_timestamp": _git_output("show", "-s", "--format=%cI", "HEAD"),
            "dirty": bool(dirty_lines),
            "dirty_paths": dirty_lines,
            "renderer_sha256": _sha256(Path(__file__).resolve()),
            "runtime_assets": assets,
        },
        "runtime_hooks": {
            "sprite": "src.sprite_atlas.ko_frame",
            "draw": "src.pixel_art.draw_ko",
            "entity": "src.entities.KOCompanion",
            "game": "src.game.FadesGame",
        },
        "resolved_states": states,
        "mirror_validation": mirror,
        "feature_validation": features,
        "lightning_validation": lightning,
        "gameplay_validation": gameplay_verification,
        "artifacts": artifacts,
    }
    manifest_path = artifact_dir / "manifest.json"
    _write_manifest(manifest_path, manifest)
    return manifest


def render_review(output_dir: Path, *, fps: int = DEFAULT_FPS, strict: bool = True) -> dict[str, Any]:
    if fps < 1 or fps > 60 or SIMULATION_HZ % fps:
        raise ValueError("fps must be a divisor of 60 between 1 and 60")
    bindings = RuntimeBindings.load()
    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    # A failed late gameplay gate must not leave a misleading partial review.
    # Each successful file is moved into place only after all nine clips and
    # the manifest have passed.
    with tempfile.TemporaryDirectory(
        prefix=".ko-review-staging-",
        dir=output_dir.parent,
    ) as temporary:
        artifact_dir = Path(temporary)
        manifest = _render_review_artifacts(
            bindings,
            artifact_dir,
            fps=fps,
            strict=strict,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        for filename in (*EXPECTED_GIF_NAMES, "manifest.json"):
            os.replace(artifact_dir / filename, output_dir / filename)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="make the structural skateboard-only check a hard gate",
    )
    args = parser.parse_args()

    pygame.init()
    pygame.display.set_mode(LOGICAL_SIZE)
    try:
        manifest = render_review(args.output_dir, fps=args.fps, strict=args.verify)
    except (ReviewIntegrationError, ValueError) as error:
        raise SystemExit(f"KO REVIEW FAILED: {error}") from error
    finally:
        pygame.quit()

    output_dir = args.output_dir.resolve()
    for filename in EXPECTED_GIF_NAMES:
        print(output_dir / filename)
    print(output_dir / "manifest.json")
    print(f"KO_REVIEW_SOURCE_COMMIT={manifest['source']['commit']}")


if __name__ == "__main__":
    main()
