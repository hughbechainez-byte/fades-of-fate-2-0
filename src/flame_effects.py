"""Manifest-backed presentation-only flame composition for Animation V2.

This module deliberately knows nothing about health, hit queries, or burn
timers.  Combat owns those concerns; this is only the small deterministic
bridge from a frozen ``AnimationSample`` to already-authored VFX cels.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pygame


class FlameLayer(IntEnum):
    """The only legal ordering for flame composition around a whole body cel."""

    SHADOW = 0
    REAR = 1
    BODY = 2
    FRONT = 3
    CONTACT = 4


@dataclass(frozen=True, slots=True)
class FlameFrame:
    """One authored atlas rectangle; no runtime resizing is permitted."""

    asset_id: str
    rect: tuple[int, int, int, int]
    pivot: tuple[int, int] = (0, 0)


@dataclass(frozen=True, slots=True)
class FlameAtlasDefinition:
    """Lead-authored atlas address and immutable rectangle inventory."""

    path: Path
    frames: Mapping[str, tuple[FlameFrame, ...]]
    frames_per_second: int = 12


@dataclass(frozen=True, slots=True)
class FlameCommand:
    """One compositing instruction. ``surface is None`` is the body boundary."""

    layer: FlameLayer
    asset_id: str
    surface: pygame.Surface | None
    position: tuple[int, int]
    facing: int
    event_name: str | None = None


class FlameAtlasCache:
    """Load each V2 source once and retain native-size normal/mirrored cels."""

    def __init__(self) -> None:
        self._atlases: dict[Path, pygame.Surface] = {}
        self._cel_cache: dict[tuple[Path, str, int, int], pygame.Surface] = {}
        self.load_count = 0

    def clear(self) -> None:
        self._atlases.clear()
        self._cel_cache.clear()
        self.load_count = 0

    def _atlas(self, definition: FlameAtlasDefinition, *, strict: bool) -> pygame.Surface | None:
        path = definition.path.resolve()
        cached = self._atlases.get(path)
        if cached is not None:
            return cached
        if not path.is_file():
            if strict:
                raise FileNotFoundError(f"Animation V2 flame atlas is required: {path}")
            return None
        atlas = pygame.image.load(str(path))
        # Keep hard authored pixels.  ``convert_alpha`` changes storage, never
        # geometry or filtering, and is only used when a display exists.
        if pygame.display.get_surface() is not None:
            atlas = atlas.convert_alpha()
        self._atlases[path] = atlas
        self.load_count += 1
        return atlas

    def frame(
        self,
        definition: FlameAtlasDefinition,
        asset_id: str,
        local_time: float,
        facing: int,
        *,
        strict: bool,
    ) -> tuple[pygame.Surface, FlameFrame] | None:
        frames = definition.frames.get(asset_id, ())
        if not frames:
            if strict:
                raise KeyError(f"Animation V2 flame asset is undeclared: {asset_id}")
            return None
        atlas = self._atlas(definition, strict=strict)
        if atlas is None:
            return None
        phase = animation_phase(local_time, len(frames), definition.frames_per_second)
        key = (definition.path.resolve(), asset_id, phase, -1 if facing < 0 else 1)
        cached = self._cel_cache.get(key)
        frame = frames[phase]
        if cached is None:
            x, y, width, height = frame.rect
            if width <= 0 or height <= 0 or x < 0 or y < 0 or x + width > atlas.get_width() or y + height > atlas.get_height():
                raise ValueError(f"invalid authored flame rectangle for {asset_id}: {frame.rect}")
            cached = atlas.subsurface(pygame.Rect(frame.rect)).copy()
            if facing < 0:
                cached = pygame.transform.flip(cached, True, False)
            self._cel_cache[key] = cached
        return cached, frame


def animation_phase(local_time: float, frame_count: int, frames_per_second: int) -> int:
    """Select a stable looping VFX phase from local presentation time only."""

    if frame_count <= 0 or frames_per_second <= 0:
        raise ValueError("flame animation requires positive frame count and rate")
    return max(0, int(float(local_time) * frames_per_second)) % frame_count


def _layer(value: object) -> FlameLayer:
    normalized = str(value).lower()
    return {
        "shadow": FlameLayer.SHADOW,
        "rear": FlameLayer.REAR,
        "front": FlameLayer.FRONT,
        "contact": FlameLayer.CONTACT,
    }.get(normalized, FlameLayer.FRONT)


def _event_asset_ids(events: Iterable[object]) -> tuple[tuple[str, FlameLayer, str], ...]:
    """Partition authored presentation events without inferring any damage."""

    result: list[tuple[str, FlameLayer, str]] = []
    for event in events:
        name = str(getattr(event, "name", event)).lower()
        if name in {"flame_whiff", "whiff", "flame_trail"}:
            result.append(("flame_trail", FlameLayer.REAR, name))
        elif name in {"flame_contact", "contact", "hit_contact"}:
            result.extend(
                (asset, FlameLayer.CONTACT, name)
                for asset in ("flame_burst", "ember", "scorch")
            )
        elif name in {"enemy_fire", "flame_enemy_fire"}:
            result.append(("enemy_fire", FlameLayer.FRONT, name))
    return tuple(result)


class FlameCompositor:
    """Return native-cel draw commands in the exact body-occlusion order."""

    def __init__(self, atlas: FlameAtlasDefinition, cache: FlameAtlasCache | None = None, *, v2_active: bool = False) -> None:
        self.atlas = atlas
        self.cache = cache or FlameAtlasCache()
        self.v2_active = v2_active

    @staticmethod
    def socket_position(sample: object, socket: object, actor_root: tuple[int, int], facing: int) -> tuple[int, int]:
        """Resolve an authored socket around the cel root, mirroring hand X only."""

        root_x, root_y = getattr(sample, "root")
        socket_x, socket_y = getattr(socket, "position")
        sign = -1 if facing < 0 else 1
        return (int(actor_root[0] + sign * (socket_x - root_x)), int(actor_root[1] + socket_y - root_y))

    def _command(
        self,
        asset_id: str,
        layer: FlameLayer,
        position: tuple[int, int],
        local_time: float,
        facing: int,
        event_name: str | None,
    ) -> FlameCommand | None:
        loaded = self.cache.frame(self.atlas, asset_id, local_time, facing, strict=self.v2_active)
        if loaded is None:
            return None
        surface, frame = loaded
        pivot_x, pivot_y = frame.pivot
        if facing < 0:
            pivot_x = surface.get_width() - pivot_x
        return FlameCommand(layer, asset_id, surface, (position[0] - pivot_x, position[1] - pivot_y), facing, event_name)

    def plan(self, sample: object, actor_root: tuple[int, int], facing: int, local_time: float) -> tuple[FlameCommand, ...]:
        """Build rear -> BODY -> front/contact commands from frozen sample metadata."""

        sign = -1 if facing < 0 else 1
        commands: list[FlameCommand] = []
        placements: Sequence[object] = tuple(getattr(sample, "rear_vfx", ())) + tuple(getattr(sample, "front_vfx", ()))
        for placement in placements:
            command = self._command(
                str(getattr(placement, "asset_id")),
                _layer(getattr(placement, "layer")),
                self.socket_position(sample, getattr(placement, "socket"), actor_root, sign),
                local_time,
                sign,
                getattr(placement, "event_name", None),
            )
            if command is not None and command.layer < FlameLayer.BODY:
                commands.append(command)
        commands.append(FlameCommand(FlameLayer.BODY, "body", None, actor_root, sign))
        for placement in placements:
            command = self._command(
                str(getattr(placement, "asset_id")),
                _layer(getattr(placement, "layer")),
                self.socket_position(sample, getattr(placement, "socket"), actor_root, sign),
                local_time,
                sign,
                getattr(placement, "event_name", None),
            )
            if command is not None and command.layer > FlameLayer.BODY:
                commands.append(command)

        sockets = tuple(getattr(placement, "socket") for placement in placements)
        event_socket = sockets[0] if sockets else None
        if event_socket is not None:
            position = self.socket_position(sample, event_socket, actor_root, sign)
            for asset_id, layer, event_name in _event_asset_ids(getattr(sample, "events", ())):
                command = self._command(asset_id, layer, position, local_time, sign, event_name)
                if command is not None:
                    commands.append(command)
        return tuple(sorted(commands, key=lambda command: int(command.layer)))
