"""Layered pixel-art drawing helpers for *The Fades of Fate*.

Chapter 1 uses strict manifest-declared, continuous location-locked panoramas;
missing or malformed route art is an error and cannot reveal legacy scenery.
The separate legacy stage still uses integer-aligned procedural drawing.
Transparent distant atmosphere and sparse bounded near-camera occluders
complete the Chapter 1 stack without sliding architecture or picture-band seams.

Coordinates passed to character functions are ground anchors: ``(x, y)`` is
where the character's feet touch the floor and ``z`` lifts the sprite without
moving its shadow.  Every public drawing function returns a ``pygame.Rect``
covering the area it drew, which is useful for dirty-rectangle renderers.
"""

from __future__ import annotations

import math
import os
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import pygame

try:  # resource_path also understands one-file executable extraction roots.
    from .config import resource_path
    from . import location_lock, sprite_atlas
    from . import backdrop
    from .stage_world import StageLayerPiece, StageWorld, StageWorldError
except ImportError:  # pragma: no cover - supports direct module experiments.
    def resource_path(relative: str) -> Path:
        return Path(__file__).resolve().parents[1] / relative
    import location_lock  # type: ignore[no-redef]
    import backdrop  # type: ignore[no-redef]
    sprite_atlas = None  # type: ignore[assignment]
    from stage_world import StageLayerPiece, StageWorld, StageWorldError  # type: ignore[no-redef]


DESIGN_WIDTH = 640
DESIGN_HEIGHT = 360
GROUND_Y = 292
CANONICAL_STAGE_WIDTH = 4200


class LocationArtError(RuntimeError):
    """Raised when required Chapter 1 art cannot be rendered faithfully."""


__all__ = [
    "DESIGN_WIDTH",
    "DESIGN_HEIGHT",
    "GROUND_Y",
    "LocationArtError",
    "draw_stage_background",
    "draw_stage_foreground",
    "stage_world_debug_snapshot",
    "background_cache_used",
    "draw_physical_scene_object",
    "draw_location_travel_panel",
    "draw_stage_prop",
    "draw_bmx_bike",
    "draw_sunset_epilogue",
    "shade_authored_sprite",
    "draw_player",
    "draw_fist_flames",
    "draw_chief",
    "draw_enemy",
    "draw_boss",
    "draw_projectile",
    "draw_pickup",
    "draw_effect",
    "draw_effects",
]


# A compact, warm California-evening palette.  Colors are tuples rather than
# pygame.Color instances so importing this module does not initialize pygame.
SKY_TOP = (42, 46, 83)
SKY_MID = (111, 71, 92)
SKY_LOW = (236, 137, 92)
INK = (27, 25, 35)
DEEP_INK = (15, 16, 24)
SIDEWALK = (151, 140, 132)
ROAD = (53, 55, 65)
CURB = (201, 194, 178)
GOLD = (242, 185, 48)


# Chapter 1 route dimensions, anchors, and parallax rates are manifest-backed.
# The lightweight Mapping adapters preserve the private inspection surface used
# by QA tools without reintroducing a second renderer-owned coordinate table.
_LOCATION_LOCK_CACHE: Mapping[str, Any] | None = None
_STAGE_WORLD_CACHE: dict[str, StageWorld] = {}
_STAGE_WORLD_SURFACE_CACHE: dict[tuple[str, str, int, int], pygame.Surface] = {}
_STAGE_WORLD_GLOBAL_SURFACE_CACHE: dict[tuple[str, str], pygame.Surface] = {}


def _location_manifest() -> Mapping[str, Any]:
    global _LOCATION_LOCK_CACHE
    if _LOCATION_LOCK_CACHE is None:
        manifest_path = resource_path("data/chapter1_location_lock.json")
        _LOCATION_LOCK_CACHE = location_lock.load_location_lock(
            manifest_path,
            project_root=manifest_path.parent.parent,
        )
    return _LOCATION_LOCK_CACHE


def _location_routes_by_theme() -> dict[str, Mapping[str, Any]]:
    return {
        str(route["theme"]): route
        for route in location_lock.location_routes(_location_manifest())
    }


def _location_route(theme: object) -> Mapping[str, Any] | None:
    return _location_routes_by_theme().get(_theme_key(theme))


def _stage_world(theme: str) -> StageWorld:
    """Load one validated chunk topology without loading a route panorama."""

    key = _theme_key(theme)
    cached = _STAGE_WORLD_CACHE.get(key)
    if cached is not None:
        return cached
    route = _location_route(key)
    if route is None:
        raise LocationArtError(f"no location-locked route exists for theme {key!r}")
    try:
        world = StageWorld.load_for_route(key, route)
    except (OSError, ValueError, TypeError, StageWorldError) as exc:
        raise LocationArtError(f"{key} chunked stage manifest is invalid: {exc}") from exc
    _STAGE_WORLD_CACHE[key] = world
    return world


def _stage_world_surface(
    theme: str,
    piece: StageLayerPiece,
) -> pygame.Surface:
    key = (str(theme), piece.asset, int(piece.width), int(piece.height))
    cached = _STAGE_WORLD_SURFACE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        image = pygame.image.load(str(resource_path(piece.asset)))
    except (OSError, pygame.error) as exc:
        raise LocationArtError(
            f"{theme} chunk layer is missing or unreadable: {piece.asset}"
        ) from exc
    if image.get_size() != (piece.width, piece.height):
        raise LocationArtError(
            f"{theme} chunk layer {piece.asset} must be "
            f"{piece.width}x{piece.height}, got {image.get_size()}"
        )
    surface = image.convert_alpha() if pygame.display.get_surface() is not None else image.copy()
    _STAGE_WORLD_SURFACE_CACHE[key] = surface
    return surface


def _stage_world_global_surface(theme: str, layer: str) -> pygame.Surface:
    key = (str(theme), str(layer))
    cached = _STAGE_WORLD_GLOBAL_SURFACE_CACHE.get(key)
    if cached is not None:
        return cached
    world = _stage_world(theme)
    asset = world.global_layers.get(layer)
    if asset is None:
        raise LocationArtError(f"{theme} chunked stage has no global {layer} layer")
    try:
        image = pygame.image.load(str(resource_path(asset)))
    except (OSError, pygame.error) as exc:
        raise LocationArtError(
            f"{theme} global stage layer is missing or unreadable: {asset}"
        ) from exc
    if image.get_height() != DESIGN_HEIGHT or image.get_width() <= 0:
        raise LocationArtError(
            f"{theme} global stage layer {asset} must have height {DESIGN_HEIGHT}"
        )
    surface = image.convert_alpha() if pygame.display.get_surface() is not None else image.copy()
    _STAGE_WORLD_GLOBAL_SURFACE_CACHE[key] = surface
    return surface


def _draw_stage_world_layer(
    surface: pygame.Surface,
    world: StageWorld,
    camera_x: float,
    layer: str,
    *,
    vertical_offset: int = 0,
) -> None:
    """Cull and draw one layer's independently authored world pieces."""

    offset = world.layer_offset(layer, camera_x, surface.get_width())
    for piece in world.visible_layer_pieces(
        layer,
        camera_x,
        surface.get_width(),
        margin=world.cull_margin + abs(float(world.layer_max_offsets.get(layer, 0.0))),
    ):
        image = _stage_world_surface(world.theme, piece)
        surface.blit(image, (piece.world_x + offset, vertical_offset))


def stage_world_debug_snapshot(
    theme: str,
    camera_x: float,
    viewport_width: int = DESIGN_WIDTH,
) -> dict[str, Any]:
    """Expose chunk/layer/anchor state for the in-game debug overlay and QA."""

    return _stage_world(theme).debug_snapshot(camera_x, viewport_width)


class _ManifestFieldMap(Mapping[str, Any]):
    def __init__(self, field: str) -> None:
        self.field = field

    def _values(self) -> dict[str, Any]:
        routes = _location_routes_by_theme()
        if self.field == "anchors":
            return {
                theme: {
                    str(landmark["id"]): int(landmark["world_x"])
                    for landmark in route["landmarks"]
                }
                for theme, route in routes.items()
            }
        if self.field == "parallax":
            return {
                theme: {
                    "far": float(route["far_parallax"]),
                    "near": float(route["near_parallax"]),
                }
                for theme, route in routes.items()
            }
        return {theme: int(route[self.field]) for theme, route in routes.items()}

    def __getitem__(self, key: str) -> Any:
        return self._values()[key]

    def __iter__(self):
        return iter(self._values())

    def __len__(self) -> int:
        return len(self._values())


_CHAPTER_ONE_THEME_ROUTE_WIDTHS: Mapping[str, int] = _ManifestFieldMap("world_width")
_CHAPTER_ONE_THEME_ANCHORS: Mapping[str, Mapping[str, int]] = _ManifestFieldMap("anchors")
_CHAPTER_ONE_PARALLAX_RATES: Mapping[str, Mapping[str, float]] = _ManifestFieldMap("parallax")
_THEME_SKY_BANDS = {
    "seven_eleven_underpass": (
        (54, 30, (42, 48, 79)),
        (84, 30, (67, 60, 92)),
        (114, 30, (111, 75, 96)),
        (144, 34, (166, 91, 82)),
        (178, 38, (224, 139, 86)),
    ),
    "soapy_joes_revive": (
        (54, 30, (40, 54, 82)),
        (84, 30, (66, 65, 99)),
        (114, 30, (109, 76, 105)),
        (144, 34, (184, 89, 94)),
        (178, 38, (237, 142, 91)),
    ),
}
_THEME_GROUND_PALETTES = {
    "seven_eleven_underpass": ((137, 137, 135), (101, 99, 101), (47, 50, 60)),
    "soapy_joes_revive": ((149, 145, 136), (100, 102, 105), (48, 53, 61)),
}
_THEME_LIGHT_POOLS = {
    "sprouts_el_cilantro": ((250, 110, (255, 176, 101)), (1650, 126, (232, 190, 105)), (2810, 150, (255, 151, 88))),
    "seven_eleven_underpass": ((170, 150, (255, 170, 92)), (1110, 126, (224, 152, 103)), (2410, 146, (156, 164, 177))),
    "soapy_joes_revive": ((250, 165, (94, 207, 225)), (1230, 116, (255, 156, 99)), (2460, 168, (224, 116, 143))),
}
# Route paintings deliberately share one dusk.  These low-strength grades give
# each district its own material temperature while retaining the authored
# storefront colors.  The phase drives a broad, world-space light undulation;
# it is baked into the opaque panorama once, never pasted over the viewport.
_LOCATION_LOCK_DEPTH_GRADES = {
    "sprouts_el_cilantro": ((73, 64, 100), (206, 145, 96), (48, 57, 67), 0.25),
    "seven_eleven_underpass": ((50, 68, 104), (190, 139, 100), (39, 54, 70), 1.45),
    "soapy_joes_revive": ((63, 67, 110), (190, 121, 127), (39, 61, 69), 2.65),
    "awaken_church_finale": ((62, 49, 87), (195, 111, 96), (38, 45, 61), 3.85),
}


_STAGE_PANEL_FILES = {
    "pharmacy": "assets/stage/second_street_pharmacy.png",
    "overpass": "assets/stage/second_street_overpass.png",
    "hall": "assets/stage/second_street_awaken_hall.png",
}

# (zoom, horizontal focal point, vertical focal point).  Full-frame scaling
# made Stage 1's wide establishing shot read as miniature scenery behind
# oversized brawlers.  These per-plate camera windows keep the curb at the
# simulation ground line while giving doors, shop lights, and street furniture
# a playable relationship to the character sprites.  The art remains one
# world texture and moves 1:1 with the gameplay camera.
_STAGE_PANEL_VIEWPORTS: dict[str, tuple[float, float, float]] = {}
_CHAPTER_ONE_ROUTE_SETPIECES: dict[str, tuple[str, ...]] = {}
_CHAPTER_ONE_STAGE_PANEL_SPECS: dict[str, str] = {}
_CHAPTER_ONE_STAGE_PANEL_FOCUS: dict[str, int] = {}
_CHAPTER_ONE_NEAR_LAYER_FILES: dict[str, str] = {}
_CHAPTER_ONE_NEAR_LAYER_FOCUS: dict[str, int] = {}
_SUNSET_BACKGROUND_FILE = "assets/stage/second_street_bmx_sunset_v1.png"
_AMBIENT_PLANE_RATES = {"far": 0.46, "mid": 0.74, "world": 1.0}
_AMBIENT_PARTICLE_LIMIT = 16
_CHAPTER_ONE_AMBIENT_EVENTS: dict[str, tuple[dict[str, object], ...]] = {
    "sprouts_el_cilantro": (
        {"kind": "traffic", "plane": "mid", "start": 0, "end": 3200, "y": 218, "instances": 4, "speed": 1.15, "direction": -1, "palette": ((78, 112, 138), (154, 72, 57), (188, 159, 101)), "seed": 17},
        {"kind": "market_canopy", "plane": "world", "start": 2350, "end": 3200, "anchor": 2780, "span": 430, "seed": 23},
        {"kind": "paper", "plane": "world", "start": 520, "end": 2460, "anchor": 1480, "span": 1940, "y": 286, "height": 48, "particles": 6, "speed": 0.42, "seed": 31},
    ),
    "seven_eleven_underpass": (
        {"kind": "mist", "plane": "far", "start": 1640, "end": 3000, "anchor": 2310, "span": 820, "y": 190, "height": 79, "particles": 8, "speed": 0.18, "seed": 43},
        {"kind": "traffic", "plane": "mid", "start": 1100, "end": 3100, "y": 226, "instances": 5, "speed": 1.45, "direction": 1, "palette": ((61, 78, 99), (173, 99, 63), (113, 125, 120)), "seed": 29},
        {"kind": "underpass_lights", "plane": "world", "start": 1750, "end": 3000, "anchor": 2320, "span": 560, "seed": 7},
    ),
    "soapy_joes_revive": (
        {"kind": "wash_spray", "plane": "far", "start": 0, "end": 920, "anchor": 330, "span": 690, "y": 174, "height": 91, "particles": 12, "speed": 0.55, "seed": 53},
        {"kind": "traffic", "plane": "mid", "start": 650, "end": 3200, "y": 220, "instances": 4, "speed": 1.05, "direction": -1, "palette": ((58, 108, 114), (180, 126, 73), (120, 82, 111)), "seed": 37},
        {"kind": "wash_cycle", "plane": "world", "start": 0, "end": 900, "anchor": 330, "span": 680, "seed": 13},
        {"kind": "revive_neon", "plane": "world", "start": 2020, "end": 3000, "anchor": 2520, "span": 660, "seed": 5},
    ),
    "awaken_church_finale": (
        {"kind": "birds", "plane": "far", "start": 0, "end": 1600, "y": 83, "instances": 5, "speed": 0.62, "direction": 1, "seed": 71},
        {"kind": "dust", "plane": "far", "start": 430, "end": 1600, "anchor": 1010, "span": 1080, "y": 167, "height": 104, "particles": 8, "speed": 0.24, "seed": 61},
        {"kind": "traffic", "plane": "mid", "start": 0, "end": 1600, "y": 222, "instances": 3, "speed": 0.92, "direction": -1, "palette": ((91, 97, 109), (157, 74, 59), (180, 154, 110)), "seed": 11},
        {"kind": "corridor", "plane": "world", "start": 350, "end": 1370, "anchor": 850, "span": 760, "seed": 19},
        {"kind": "crowd", "plane": "world", "start": 720, "end": 1600, "anchor": 1160, "span": 520, "instances": 4, "seed": 47},
    ),
}
_CHAPTER_ONE_STREET_PROPS = {
    "sprouts_el_cilantro": {
        "markers": ((520, "hydrant"), (960, "bollard"), (1760, "cone"), (2570, "bollard"), (3030, "hydrant")),
        "bus": 2260,
        "puddle": 2240,
    },
    "seven_eleven_underpass": {
        "markers": ((340, "bollard"), (890, "hydrant"), (1450, "cone"), (2110, "bollard"), (2740, "cone")),
        "bus": 1240,
        "puddle": 1880,
    },
    "soapy_joes_revive": {
        "markers": ((470, "hydrant"), (1070, "bollard"), (1710, "cone"), (2350, "bollard"), (2860, "hydrant")),
        "bus": 1510,
        "puddle": 420,
    },
}
_STAGE_PANEL_CACHE: dict[tuple[str, int, int], pygame.Surface | None] = {}
_STAGE_PANEL_WORLD_CACHE: dict[tuple[str, int, int, bool, bool], pygame.Surface | None] = {}
_STAGE_PANEL_BAND_CACHE: dict[tuple[str, int, int, str], pygame.Surface | None] = {}
_STAGE_CHAPTER_PANEL_CACHE: dict[tuple[str, int, int, bool], pygame.Surface | None] = {}
_STAGE_ROUTE_PANORAMA_CACHE: dict[tuple[object, ...], pygame.Surface | None] = {}
_STAGE_NEAR_LAYER_CACHE: dict[tuple[str, int, int], pygame.Surface | None] = {}
_SUNSET_BACKGROUND_CACHE: dict[tuple[int, int], dict[str, pygame.Surface] | None] = {}
_LOCATION_ART_CACHE: dict[str, dict[str, pygame.Surface | None]] = {}
_BACKGROUND_CACHE_HIT_THEMES: set[str] = set()
_TRAVEL_PANEL_CACHE: dict[tuple[object, ...], pygame.Surface] = {}
_PHYSICAL_SCENE_OBJECT_CACHE: dict[tuple[object, ...], pygame.Surface] = {}
_AMBIENT_OVERLAY_CACHE: dict[tuple[int, int, str], pygame.Surface] = {}
_WORLD_LIGHTING_CACHE_LIMIT = 16
_WORLD_LIGHTING_CACHE: OrderedDict[tuple[object, ...], pygame.Surface] = OrderedDict()

# A camera can remain settled for much longer than the actors/effects rendered
# above it.  Cache the fully composited opaque foundation at those exact
# camera positions, rather than simplifying its authored plates, parallax, or
# 2.5D ground treatment.  The bounded LRU prevents a long walk from becoming
# an unbounded collection of 640x360 surfaces.
_STAGE_BACKGROUND_FRAME_CACHE_LIMIT = 16
_STAGE_BACKGROUND_FRAME_CACHE: OrderedDict[tuple[object, ...], pygame.Surface] = OrderedDict()
_STAGE_BACKGROUND_FRAME_BUILDING: set[tuple[object, ...]] = set()

# Grounded atlas sprites are immutable for the duration of a run.  Retaining
# their exact source alongside the cached bounds/left-facing variant prevents
# ``id`` reuse and removes repeated alpha scans/flips from the crowded scene.
_GROUNDED_SPRITE_CACHE_LIMIT = 256
_GROUNDED_SPRITE_CACHE: OrderedDict[
    int,
    tuple[pygame.Surface, pygame.Rect, pygame.Surface | None, pygame.Rect | None],
] = OrderedDict()


def _i(value: float | int) -> int:
    return int(round(value))


def _rgb(value: pygame.Color | Sequence[int] | str | None, fallback: Sequence[int]) -> tuple[int, int, int]:
    """Return a safe RGB tuple for caller-provided accent colors."""

    if value is None:
        return tuple(fallback[:3])  # type: ignore[return-value]
    try:
        color = pygame.Color(value)
    except (TypeError, ValueError, IndexError):
        return tuple(fallback[:3])  # type: ignore[return-value]
    return color.r, color.g, color.b


def _shade(color: Sequence[int], amount: int) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(channel) + amount)) for channel in color[:3])  # type: ignore[return-value]


def _mix_color(source: Sequence[int], target: Sequence[int], strength: float) -> tuple[int, int, int, int]:
    """Blend RGB while retaining the source alpha exactly."""

    amount = max(0.0, min(1.0, float(strength)))
    return (
        round(int(source[0]) * (1.0 - amount) + int(target[0]) * amount),
        round(int(source[1]) * (1.0 - amount) + int(target[1]) * amount),
        round(int(source[2]) * (1.0 - amount) + int(target[2]) * amount),
        int(source[3]) if len(source) > 3 else 255,
    )


# Authored sprites already contain painted local form.  This pass only works on
# exposed top-left and lower-right edge clusters, so it adds one coherent sunset
# key light and a cool contact side without flattening the internal artwork.
# Profiles keep fur, denim, cloth and uniform metal from receiving one blanket
# filter.  Originals are retained beside cached results to make ``id`` reuse
# impossible while the cache entry lives.
_MATERIAL_LIGHTING = {
    # The hero cells have less source width than the 160px enemy cells, so
    # give their clothing and skin a slightly stronger, still localized rim
    # and contact treatment.  This raises readable material separation without
    # scaling, warping, or changing any walk roots.
    "dave": ((255, 194, 116), (12, 23, 39), 0.41, 0.33),
    "shelly": ((255, 203, 145), (23, 20, 43), 0.39, 0.30),
    "fur": ((255, 205, 125), (31, 25, 35), 0.29, 0.28),
    "enemy_cloth": ((218, 183, 123), (18, 23, 31), 0.24, 0.31),
    "security_uniform": ((129, 185, 236), (9, 18, 35), 0.32, 0.36),
    "denim": ((255, 190, 105), (13, 23, 43), 0.30, 0.32),
    "jerry": ((255, 199, 126), (18, 23, 35), 0.28, 0.29),
    "celebration": ((255, 207, 132), (19, 23, 42), 0.30, 0.27),
    "painted_metal": ((214, 236, 236), (18, 28, 35), 0.34, 0.30),
}
_MATERIAL_LIT_CACHE: dict[tuple[str, int], tuple[pygame.Surface, pygame.Surface]] = {}
_HIT_FLASH_CACHE: OrderedDict[
    tuple[int, int],
    tuple[pygame.Surface, pygame.Surface],
] = OrderedDict()
_HIT_FLASH_CACHE_LIMIT = 256


def _material_lit_sprite(sprite: pygame.Surface, profile: str, *, cache: bool = True) -> pygame.Surface:
    """Add material-specific edge light without changing alpha or silhouette."""

    key = (str(profile), id(sprite))
    cached = _MATERIAL_LIT_CACHE.get(key) if cache else None
    if cached is not None and cached[0] is sprite:
        return cached[1]
    bounds = sprite.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        return sprite
    key_light, contact_color, light_strength, shade_strength = _MATERIAL_LIGHTING.get(
        str(profile), _MATERIAL_LIGHTING["enemy_cloth"]
    )
    lit = sprite.copy()
    mask = pygame.mask.from_surface(sprite)
    lower_contact = bounds.bottom - max(2, bounds.h // 18)
    width, height = sprite.get_size()

    # Shifted-mask subtraction isolates the two directional edge families in
    # native SDL code.  It is the same localized form treatment as a hand-drawn
    # one-pixel rim, but avoids a Python pixel scan and first-pose frame hitch.
    from_upper_left = pygame.Mask((width, height))
    from_upper_left.draw(mask, (1, 1))
    light_edge = mask.copy()
    light_edge.erase(from_upper_left, (0, 0))
    from_lower_right = pygame.Mask((width, height))
    from_lower_right.draw(mask, (-1, -1))
    shade_edge = mask.copy()
    shade_edge.erase(from_lower_right, (0, 0))

    contact_surface = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.rect(contact_surface, (255, 255, 255, 255), (bounds.left, lower_contact, bounds.w, bounds.bottom - lower_contact))
    contact_mask = mask.overlap_mask(pygame.mask.from_surface(contact_surface), (0, 0))
    shade_edge.draw(contact_mask, (0, 0))

    light_add = tuple(max(1, round(channel * light_strength * 0.19)) for channel in key_light)
    light_layer = light_edge.to_surface(setcolor=(*light_add, 255), unsetcolor=(0, 0, 0, 255))
    lit.blit(light_layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    multiplier = tuple(
        max(0, min(255, round(255 * (1.0 - shade_strength * 0.55) + channel * shade_strength * 0.55)))
        for channel in contact_color
    )
    shade_layer = shade_edge.to_surface(setcolor=(*multiplier, 255), unsetcolor=(255, 255, 255, 255))
    lit.blit(shade_layer, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    if cache:
        _MATERIAL_LIT_CACHE[key] = (sprite, lit)
    return lit


def shade_authored_sprite(sprite: pygame.Surface, material: str = "enemy_cloth") -> pygame.Surface:
    """Public, cached material-lighting entry point for authored composites."""

    return _material_lit_sprite(sprite, material)


def _hit_flash_sprite(
    sprite: pygame.Surface,
    strength: float,
    *,
    cache: bool = True,
) -> pygame.Surface:
    """Apply one warm additive palette lift while preserving alpha and form."""

    amount = max(0.0, min(1.0, float(strength)))
    if amount <= 0.0:
        return sprite
    level = max(1, min(15, round(amount * 15.0)))
    key = (id(sprite), level)
    cached = _HIT_FLASH_CACHE.get(key) if cache else None
    if cached is not None and cached[0] is sprite:
        _HIT_FLASH_CACHE.move_to_end(key)
        return cached[1]

    # RGB-only additive blending retains the exact authored alpha/silhouette
    # and the relative dark-to-light material structure.  A slightly warm lift
    # belongs to the established sunset palette and avoids a flat white cutout.
    normalized = level / 15.0
    lift = (
        round(118 * normalized),
        round(106 * normalized),
        round(78 * normalized),
        0,
    )
    flashed = sprite.copy()
    flashed.fill(lift, special_flags=pygame.BLEND_RGB_ADD)
    if cache:
        _HIT_FLASH_CACHE[key] = (sprite, flashed)
        _HIT_FLASH_CACHE.move_to_end(key)
        while len(_HIT_FLASH_CACHE) > _HIT_FLASH_CACHE_LIMIT:
            _HIT_FLASH_CACHE.popitem(last=False)
    return flashed


_STATE_RIM_CACHE: dict[tuple[int, str], tuple[pygame.Surface, pygame.Surface]] = {}


def _state_rim_sprite(
    sprite: pygame.Surface,
    state: str,
    accent: Sequence[int],
) -> pygame.Surface:
    """Add a restrained colored rim to charged character states."""

    state_name = str(state)
    rim_colors = {
        "super": (86, 219, 255),
        "special": (255, 190, 80),
        "propane": (255, 119, 63),
    }
    color = rim_colors.get(state_name)
    if color is None:
        return sprite
    key = (id(sprite), state_name)
    cached = _STATE_RIM_CACHE.get(key)
    if cached is not None and cached[0] is sprite:
        return cached[1]
    bounds = sprite.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        return sprite
    mask = pygame.mask.from_surface(sprite)
    inset = pygame.Mask(sprite.get_size())
    inset.draw(mask, (-1, -1))
    rim = mask.copy()
    rim.erase(inset, (0, 0))
    tint = tuple(min(255, max(0, int(channel))) for channel in color)
    lit = sprite.copy()
    layer = rim.to_surface(setcolor=(*tint, 255), unsetcolor=(0, 0, 0, 255))
    strength = 0.22 if state_name != "super" else 0.28
    layer.fill((255, 255, 255, round(255 * strength)), special_flags=pygame.BLEND_RGBA_MULT)
    lit.blit(layer, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    _STATE_RIM_CACHE[key] = (sprite, lit)
    return lit


_CHARACTER_SHEEN_CACHE: dict[tuple[int, str, int], tuple[pygame.Surface, pygame.Surface]] = {}


def _character_sheen_sprite(
    sprite: pygame.Surface,
    profile: str,
    frame: int,
) -> pygame.Surface:
    """Sweep a restrained material highlight through authored character art."""

    profile_name = str(profile)
    # Dave's authored skin, denim, shoes, and vest already carry deliberate
    # highlights. A frame-driven diagonal sweep reads as a flashing glare on
    # his larger silhouette, so preserve his painted palette unchanged.
    if profile_name == "dave":
        return sprite
    phase = int(frame) % 6
    key = (id(sprite), profile_name, phase)
    cached = _CHARACTER_SHEEN_CACHE.get(key)
    if cached is not None and cached[0] is sprite:
        return cached[1]
    bounds = sprite.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        return sprite
    sheen = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
    travel = max(1, bounds.w + bounds.h // 2)
    offset = bounds.left - bounds.h // 2 + (travel * phase) // 5
    tint = (255, 239, 194, 48) if profile_name == "dave" else (255, 216, 231, 44)
    pygame.draw.polygon(
        sheen,
        tint,
        [
            (offset, bounds.bottom + 2),
            (offset + max(4, bounds.w // 7), bounds.bottom + 2),
            (offset + bounds.h // 2 + max(4, bounds.w // 7), bounds.top - 2),
            (offset + bounds.h // 2, bounds.top - 2),
        ],
    )
    mask = pygame.mask.from_surface(sprite)
    alpha = mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
    sheen.blit(alpha, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    lit = sprite.copy()
    # The sheen carries a deliberately low alpha.  RGB-only additive blits
    # ignore that alpha on Pygame's RGB canvas and turn the traveling highlight
    # into a solid white slash; ordinary RGBA compositing preserves the soft
    # material glint while keeping the authored silhouette intact.
    lit.blit(sheen, (0, 0))
    _CHARACTER_SHEEN_CACHE[key] = (sprite, lit)
    while len(_CHARACTER_SHEEN_CACHE) > 512:
        _CHARACTER_SHEEN_CACHE.pop(next(iter(_CHARACTER_SHEEN_CACHE)))
    return lit


_CHARACTER_EMBLEM_CACHE: dict[tuple[int, str, int], tuple[pygame.Surface, pygame.Surface]] = {}


def _character_emblem_sprite(
    sprite: pygame.Surface,
    profile: str,
    frame: int,
) -> pygame.Surface:
    """Add a tiny masked identity marker to the character's torso plane."""

    profile_name = str(profile)
    phase = int(frame) % 4
    key = (id(sprite), profile_name, phase)
    cached = _CHARACTER_EMBLEM_CACHE.get(key)
    if cached is not None and cached[0] is sprite:
        return cached[1]
    bounds = sprite.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        return sprite
    marker_x = bounds.left + max(2, int(bounds.w * 0.58))
    marker_y = bounds.top + max(4, int(bounds.h * 0.47))
    emblem = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
    border = (35, 27, 38, 220)
    fill = (219, 71, 73, 220) if profile_name == "dave" else (202, 75, 139, 210)
    pygame.draw.rect(emblem, border, (marker_x - 3, marker_y - 2, 7, 6))
    pygame.draw.rect(emblem, fill, (marker_x - 2, marker_y - 1, 5, 4))
    pygame.draw.rect(emblem, (255, 236, 177, 210), (marker_x - 1 + phase % 2, marker_y, 2, 2))
    mask = pygame.mask.from_surface(sprite)
    alpha = mask.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
    emblem.blit(alpha, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    lit = sprite.copy()
    lit.blit(emblem, (0, 0))
    _CHARACTER_EMBLEM_CACHE[key] = (sprite, lit)
    while len(_CHARACTER_EMBLEM_CACHE) > 512:
        _CHARACTER_EMBLEM_CACHE.pop(next(iter(_CHARACTER_EMBLEM_CACHE)))
    return lit


_SECURITY_UNIFORM_CACHE: dict[tuple[int, str], tuple[pygame.Surface, pygame.Surface]] = {}


def _security_uniform_frame(authored: pygame.Surface, state_name: str) -> pygame.Surface:
    """Turn the full authored stick pose into a readable, geared guard.

    The source pose supplies the high-frame-count anatomy.  A fast material tint
    remaps its full value structure into navy, then restores the face and places
    gear from the native silhouette centroid.  Walking, striking, hurt and prone
    poses therefore all keep their badge, patches and flashlight without a
    first-use pixel-scan hitch.
    """

    cache_key = (id(authored), str(state_name))
    cached = _SECURITY_UNIFORM_CACHE.get(cache_key)
    if cached is not None and cached[0] is authored:
        return cached[1]
    guard = authored.copy()
    bounds = authored.get_bounding_rect(min_alpha=1)
    if not bounds.w or not bounds.h:
        return authored

    mask = pygame.mask.from_surface(authored)
    horizontal = bounds.w > bounds.h * 1.18 and state_name in {"down", "dead", "downed"}
    centroid_x, centroid_y = mask.centroid()
    body_x = centroid_x or bounds.centerx
    if horizontal:
        head_x = bounds.right - max(9, round(bounds.h * 0.28))
        head_y = bounds.top + max(7, round(bounds.h * 0.30))
    else:
        head_x = body_x
        head_y = bounds.top + max(9, round(bounds.h * 0.17))
    torso_top = bounds.top + round(bounds.h * 0.30)
    belt_y = bounds.top + round(bounds.h * 0.61)

    # RGB blend flags preserve source alpha and all hand-painted value changes.
    # The cool multiplier/add pair makes even the boots and old jacket read as
    # one issued uniform while avoiding a frame-by-frame Python pixel loop.
    guard.fill((118, 158, 225), special_flags=pygame.BLEND_RGB_MULT)
    guard.fill((4, 9, 22), special_flags=pygame.BLEND_RGB_ADD)
    face_rect = pygame.Rect(head_x - 9, head_y - 9, 18, 21).clip(bounds)
    if face_rect.w and face_rect.h:
        guard.blit(authored, face_rect, face_rect)

    if horizontal:
        gear_y = centroid_y or bounds.centery
        gear_x = centroid_x or bounds.centerx
        # Horizontal badge, belt and clipped-on flashlight remain readable on
        # the final prone silhouette rather than floating above the body.
        pygame.draw.rect(guard, (8, 14, 25), (gear_x - 13, gear_y - 5, 28, 4))
        pygame.draw.rect(guard, (181, 135, 48), (gear_x - 2, gear_y - 5, 5, 4))
        pygame.draw.polygon(guard, (226, 184, 72), [(gear_x - 11, gear_y - 12), (gear_x - 6, gear_y - 14), (gear_x - 3, gear_y - 10), (gear_x - 7, gear_y - 7)])
        pygame.draw.rect(guard, (16, 20, 28), (gear_x + 11, gear_y - 10, 15, 6))
        pygame.draw.polygon(guard, (71, 132, 158), [(gear_x + 24, gear_y - 11), (gear_x + 34, gear_y - 14), (gear_x + 34, gear_y - 4), (gear_x + 24, gear_y - 7)])
        pygame.draw.rect(guard, (167, 215, 232), (gear_x + 23, gear_y - 9, 4, 4))
        pygame.draw.rect(guard, (245, 255, 238), (gear_x + 25, gear_y - 8, 3, 2))
        pygame.draw.line(guard, (87, 133, 183), (head_x - 8, head_y - 8), (head_x + 8, head_y - 8), 4)
    else:
        shoulder_y = torso_top + max(2, bounds.h // 25)
        shoulder_span = max(13, bounds.h // 6)
        # Structured shirt panels and epaulets cover the ragged-jacket read.
        pygame.draw.line(guard, (11, 22, 40), (body_x, shoulder_y + 2), (body_x, belt_y - 3), 2)
        for side in (-1, 1):
            patch_x = body_x + side * shoulder_span
            pygame.draw.rect(guard, (14, 25, 45), (patch_x - 4, shoulder_y - 2, 8, 7))
            pygame.draw.rect(guard, (71, 125, 184), (patch_x - 3, shoulder_y - 1, 6, 4))
            pygame.draw.rect(guard, (226, 184, 72), (patch_x - 1, shoulder_y, 2, 2))
        # Gold shield, name plate and high-contrast duty belt.
        badge_x = body_x + 6
        badge_y = shoulder_y + 7
        pygame.draw.polygon(
            guard,
            (247, 207, 91),
            [(badge_x - 3, badge_y), (badge_x + 3, badge_y), (badge_x + 2, badge_y + 6), (badge_x, badge_y + 8), (badge_x - 2, badge_y + 6)],
        )
        pygame.draw.rect(guard, (255, 244, 181), (badge_x - 1, badge_y + 2, 2, 3))
        pygame.draw.rect(guard, (168, 199, 219), (body_x - 8, badge_y + 1, 7, 2))
        pygame.draw.rect(guard, (7, 12, 22), (body_x - shoulder_span, belt_y - 2, shoulder_span * 2, 6))
        pygame.draw.rect(guard, (202, 151, 50), (body_x - 3, belt_y - 1, 6, 4))
        pygame.draw.rect(guard, (232, 196, 91), (body_x - 1, belt_y, 2, 2))
        for offset in (-shoulder_span + 3, shoulder_span - 7):
            pygame.draw.rect(guard, (32, 41, 53), (body_x + offset, belt_y - 1, 5, 7))
        # A clipped duty flashlight is present in every phase.  Its cool lens
        # and steel collar make it distinct from the retained dark baton.
        flashlight_x = body_x + shoulder_span - 2
        pygame.draw.rect(guard, (5, 10, 17), (flashlight_x - 3, belt_y - 3, 7, 15))
        pygame.draw.rect(guard, (112, 135, 151), (flashlight_x - 3, belt_y - 1, 7, 3))
        pygame.draw.polygon(
            guard,
            (67, 128, 153),
            [(flashlight_x - 3, belt_y + 10), (flashlight_x + 4, belt_y + 10), (flashlight_x + 7, belt_y + 18), (flashlight_x - 6, belt_y + 18)],
        )
        pygame.draw.rect(guard, (190, 235, 245), (flashlight_x - 2, belt_y + 9, 5, 3))
        pygame.draw.rect(guard, (244, 255, 238), (flashlight_x - 1, belt_y + 10, 2, 2))
        # The existing beanie silhouette becomes a billed uniform cap.
        cap_y = head_y - max(8, bounds.h // 12)
        pygame.draw.line(guard, (8, 16, 30), (head_x - 11, cap_y), (head_x + 10, cap_y), 6)
        pygame.draw.line(guard, (36, 65, 102), (head_x - 9, cap_y - 1), (head_x + 7, cap_y - 1), 3)
        pygame.draw.rect(guard, (11, 22, 40), (head_x + 5, cap_y + 2, 11, 3))
        pygame.draw.rect(guard, (226, 184, 72), (head_x - 1, cap_y - 2, 3, 3))

    _SECURITY_UNIFORM_CACHE[cache_key] = (authored, guard)
    return guard


def _face_sign(facing: object) -> int:
    if isinstance(facing, str):
        return -1 if facing.strip().lower() in {"left", "l", "west", "-1"} else 1
    try:
        return -1 if float(facing) < 0 else 1
    except (TypeError, ValueError):
        return 1


def _state_name(state: object) -> str:
    return str(state or "idle").strip().lower().replace("-", "_").replace(" ", "_")


def _pixel_disc(surface: pygame.Surface, color: Sequence[int], center: tuple[int, int], radius: int) -> pygame.Rect:
    """Draw a row-built disc whose edge remains crisp under nearest scaling."""

    cx, cy = center
    r = max(1, int(radius))
    rows: list[pygame.Rect] = []
    # Quantizing the horizontal radius in two-pixel steps produces deliberate
    # clusters instead of the vector-smooth look of a Flash-era ellipse.
    for dy in range(-r, r + 1):
        half = int(math.sqrt(max(0, r * r - dy * dy)))
        if r >= 5:
            half = max(1, (half // 2) * 2)
        rect = pygame.Rect(cx - half, cy + dy, half * 2 + 1, 1)
        pygame.draw.rect(surface, color, rect)
        rows.append(rect)
    return rows[0].unionall(rows[1:])


def _toned_oval(
    surface: pygame.Surface,
    rect: pygame.Rect | tuple[int, int, int, int],
    outline: Sequence[int],
    shadow: Sequence[int],
    base: Sequence[int],
    light: Sequence[int],
) -> pygame.Rect:
    """Build a four-tone oval from hard-edged nested shapes."""

    bounds = pygame.Rect(rect)
    pygame.draw.ellipse(surface, outline, bounds)
    inner = bounds.inflate(-4, -4)
    if inner.w > 0 and inner.h > 0:
        pygame.draw.ellipse(surface, shadow, inner)
        upper = pygame.Rect(inner.x + 1, inner.y, max(1, inner.w - 2), max(1, inner.h * 2 // 3))
        pygame.draw.ellipse(surface, base, upper)
        pygame.draw.rect(surface, light, (inner.x + inner.w // 4, inner.y + 2, max(2, inner.w // 3), 2))
    return bounds


def _outlined_poly(
    surface: pygame.Surface,
    points: Sequence[tuple[int, int]],
    fill: Sequence[int],
    outline: Sequence[int] = DEEP_INK,
    width: int = 2,
) -> pygame.Rect:
    rect = pygame.draw.polygon(surface, outline, points)
    pygame.draw.polygon(surface, fill, points)
    pygame.draw.lines(surface, outline, True, points, max(1, width))
    return rect


def _outlined_line(
    surface: pygame.Surface,
    start: tuple[int, int],
    end: tuple[int, int],
    color: Sequence[int],
    width: int,
    outline: Sequence[int] = DEEP_INK,
) -> pygame.Rect:
    pygame.draw.line(surface, outline, start, end, width + 3)
    return pygame.draw.line(surface, color, start, end, width)


_FONT_CACHE: dict[int, pygame.font.Font] = {}


def _font(size: int) -> pygame.font.Font:
    if not pygame.font.get_init():
        pygame.font.init()
    key = max(8, int(size))
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        try:
            cached.size("M")
            return cached
        except pygame.error:
            # Pygame invalidates Font handles across quit/reinitialize cycles.
            # This occurs in test harnesses and can also happen after a display
            # recovery, so discard stale handles instead of crashing a draw.
            _FONT_CACHE.clear()
    face = pygame.font.Font(None, key)
    _FONT_CACHE[key] = face
    return face


def _label(
    surface: pygame.Surface,
    text: str,
    x: int,
    y: int,
    color: Sequence[int] = (240, 235, 218),
    size: int = 13,
    *,
    centered: bool = False,
) -> pygame.Rect:
    """Render hard-edged text with a one-pixel offset shadow."""

    message = str(text).upper()
    face = _font(size)
    shadow = face.render(message, False, DEEP_INK)
    image = face.render(message, False, color)
    left = int(x - image.get_width() // 2) if centered else int(x)
    surface.blit(shadow, (left + 1, int(y) + 1))
    return surface.blit(image, (left, int(y)))


def _onscreen(left: int, width: int, screen_width: int, margin: int = 64) -> bool:
    return left + width >= -margin and left <= screen_width + margin


def _theme_key(theme: object) -> str:
    """Normalize a campaign theme without making the renderer stateful."""

    return str(theme or "legacy_second_street").strip().lower().replace("-", "_").replace(" ", "_")


def _theme_route_scale(theme: str, world_width: int) -> float:
    """Scale a Chapter 1 route coordinate into the authored world width."""

    route_width = _CHAPTER_ONE_THEME_ROUTE_WIDTHS.get(theme)
    if route_width is None:
        return world_width / CANONICAL_STAGE_WIDTH
    return world_width / float(route_width)


def _theme_anchor_world_x(theme: str, anchor: str, stage_width: int | float) -> int:
    """Return a named Chapter 1 landmark's world anchor for visual QA/tools."""

    key = _theme_key(theme)
    if key not in _CHAPTER_ONE_THEME_ANCHORS or anchor not in _CHAPTER_ONE_THEME_ANCHORS[key]:
        raise KeyError(f"unknown Chapter 1 theme anchor: {theme!r}/{anchor!r}")
    width = max(DESIGN_WIDTH, _i(stage_width))
    return _i(_CHAPTER_ONE_THEME_ANCHORS[key][anchor] * _theme_route_scale(key, width))


def _building_shell(
    surface: pygame.Surface,
    camera_x: float,
    world_x: float,
    y: int,
    width: int,
    height: int,
    wall: Sequence[int],
    trim: Sequence[int],
) -> tuple[int, pygame.Rect] | None:
    sx = _i(world_x - camera_x)
    if not _onscreen(sx, width, surface.get_width()):
        return None
    body = pygame.Rect(sx, y, width, height)
    pygame.draw.rect(surface, DEEP_INK, body.inflate(6, 6))
    pygame.draw.rect(surface, wall, body)
    pygame.draw.rect(surface, trim, (sx, y, width, 5))
    return sx, body


def _draw_pharmacy(surface: pygame.Surface, cx: float, wx: float, scale: float) -> None:
    width = max(260, _i(500 * scale))
    result = _building_shell(surface, cx, wx, 126, width, 112, (202, 62, 61), (255, 193, 129))
    if result is None:
        return
    sx, _ = result
    # Red corner pharmacy with generic signage and no trade dress or real logo.
    pygame.draw.rect(surface, (242, 225, 197), (sx + 16, 145, width - 32, 25))
    _label(surface, "CORNER PHARMACY", sx + width // 2, 149, (138, 35, 40), 17, centered=True)
    window_y = 180
    for px in range(sx + 18, sx + width - 26, 62):
        pygame.draw.rect(surface, INK, (px - 2, window_y - 2, 48, 51))
        pygame.draw.rect(surface, (71, 108, 123), (px, window_y, 44, 47))
        pygame.draw.rect(surface, (248, 183, 108), (px + 5, window_y + 7, 3, 28))
    # A broad striped awning makes this readable even when labels are hidden.
    for index, px in enumerate(range(sx + 10, sx + width - 8, 24)):
        pygame.draw.rect(surface, (244, 224, 195) if index % 2 else (177, 37, 44), (px, 171, 24, 9))
    pygame.draw.rect(surface, (70, 53, 49), (sx + width - 55, 184, 36, 54))
    pygame.draw.rect(surface, (238, 222, 194), (sx + width - 49, 190, 24, 8))
    pygame.draw.rect(surface, (122, 167, 171), (sx + width - 46, 192, 18, 4))
    # Brick joints, rooftop HVAC and window reflections add local texture.
    for row_y in range(132, 146, 6):
        offset = 9 if (row_y // 6) % 2 else 0
        for px in range(sx + offset, sx + width, 24):
            pygame.draw.rect(surface, (155, 43, 48), (px, row_y, 12, 1))
    pygame.draw.rect(surface, (73, 75, 78), (sx + 38, 112, 57, 14))
    pygame.draw.rect(surface, (117, 119, 117), (sx + 43, 115, 47, 8))
    pygame.draw.rect(surface, (194, 122, 91), (sx + 49, 118, 30, 2))
    for px in range(sx + 26, sx + width - 70, 62):
        pygame.draw.polygon(surface, (143, 184, 186), [(px + 4, 184), (px + 15, 180), (px + 9, 223), (px + 4, 223)])


def _draw_market(surface: pygame.Surface, cx: float, wx: float, scale: float) -> None:
    width = max(250, _i(470 * scale))
    result = _building_shell(surface, cx, wx, 139, width, 99, (223, 196, 142), (55, 112, 87))
    if result is None:
        return
    sx, _ = result
    pygame.draw.rect(surface, (48, 89, 72), (sx + 14, 151, width - 28, 26))
    _label(surface, "TOWN MARKET", sx + width // 2, 156, (244, 225, 163), 18, centered=True)
    for px in range(sx + 24, sx + width - 34, 58):
        pygame.draw.rect(surface, INK, (px - 2, 186, 46, 42))
        pygame.draw.rect(surface, (59, 93, 92), (px, 188, 42, 38))
        pygame.draw.rect(surface, (214, 104, 76), (px + 5, 203, 32, 3))
    pygame.draw.rect(surface, (111, 70, 49), (sx + width - 57, 184, 37, 54))
    pygame.draw.rect(surface, (233, 216, 159), (sx + width - 51, 191, 25, 7))
    # Produce crates and old stucco chips keep the market from reading as flat.
    for box_x, box_y, box_color in ((sx + 24, 218, (148, 91, 48)), (sx + 47, 221, (99, 126, 66)), (sx + 67, 216, (183, 126, 56))):
        pygame.draw.rect(surface, (48, 42, 38), (box_x - 2, box_y - 2, 21, 20))
        pygame.draw.rect(surface, box_color, (box_x, box_y, 17, 16))
        pygame.draw.line(surface, _shade(box_color, 35), (box_x + 3, box_y + 3), (box_x + 14, box_y + 3), 2)
    for px, py in ((sx + 17, 181), (sx + 124, 142), (sx + width - 93, 178)):
        pygame.draw.rect(surface, (184, 156, 112), (px, py, 12, 3))


def _draw_signal(surface: pygame.Surface, screen_x: int, street_name: str) -> None:
    if not _onscreen(screen_x, 80, surface.get_width(), 80):
        return
    pygame.draw.rect(surface, (61, 68, 67), (screen_x, 91, 5, 147))
    pygame.draw.rect(surface, (61, 68, 67), (screen_x, 91, 61, 5))
    pygame.draw.rect(surface, (54, 57, 55), (screen_x + 44, 96, 19, 40))
    for offset, color in ((5, (209, 52, 50)), (17, (230, 177, 45)), (29, (48, 138, 75))):
        pygame.draw.rect(surface, DEEP_INK, (screen_x + 49, 97 + offset, 9, 9))
        pygame.draw.rect(surface, color, (screen_x + 51, 99 + offset, 5, 5))
    sign_width = max(62, len(street_name) * 7)
    pygame.draw.rect(surface, (30, 91, 72), (screen_x - sign_width + 5, 101, sign_width, 16))
    _label(surface, street_name, screen_x - sign_width + 9, 103, (240, 238, 213), 12)


def _draw_underpass(surface: pygame.Surface, cx: float, wx: float, scale: float) -> None:
    width = max(340, _i(540 * scale))
    sx = _i(wx - cx)
    if not _onscreen(sx, width, surface.get_width()):
        return
    pygame.draw.rect(surface, (91, 91, 97), (sx, 98, width, 36))
    pygame.draw.rect(surface, (52, 54, 62), (sx, 98, width, 7))
    pygame.draw.rect(surface, (177, 169, 151), (sx, 134, width, 7))
    for px in (sx + 34, sx + width - 62):
        pygame.draw.rect(surface, (95, 91, 91), (px, 134, 27, 104))
        pygame.draw.rect(surface, (63, 63, 69), (px + 5, 141, 17, 97))
    # Deep shade beneath the freeway gives the stage a dramatic mid-level beat.
    pygame.draw.rect(surface, (37, 39, 50), (sx + 61, 141, width - 122, 97))
    for px in range(sx + 80, sx + width - 70, 72):
        pygame.draw.rect(surface, (103, 93, 85), (px, 154, 44, 4))
    sign_x = sx + width // 2 - 31
    pygame.draw.rect(surface, (29, 87, 113), (sign_x, 106, 62, 22))
    pygame.draw.rect(surface, (224, 228, 216), (sign_x + 3, 109, 56, 16), 2)
    _label(surface, "I-8", sx + width // 2, 108, (244, 242, 221), 16, centered=True)
    # Amber sodium lights, expansion seams and a stylized graffiti panel.
    for px in range(sx + 95, sx + width - 85, 95):
        pygame.draw.rect(surface, (53, 47, 43), (px - 5, 139, 12, 4))
        pygame.draw.rect(surface, (245, 187, 94), (px - 3, 141, 8, 3))
        pygame.draw.polygon(surface, (87, 70, 58), [(px - 13, 144), (px + 15, 144), (px + 28, 188), (px - 24, 188)])
    art_x = sx + width // 2 - 38
    pygame.draw.rect(surface, (46, 43, 51), (art_x - 3, 181, 82, 31))
    pygame.draw.lines(surface, (177, 76, 104), False, [(art_x, 203), (art_x + 15, 187), (art_x + 28, 202), (art_x + 45, 185), (art_x + 73, 201)], 4)
    pygame.draw.lines(surface, (68, 157, 166), False, [(art_x + 4, 207), (art_x + 29, 191), (art_x + 51, 207), (art_x + 75, 190)], 2)


def _draw_service_row(surface: pygame.Surface, cx: float, gas_x: float, scale: float) -> None:
    # Generic fuel canopy.
    sx = _i(gas_x - cx)
    gas_w = max(190, _i(300 * scale))
    if _onscreen(sx, gas_w, surface.get_width()):
        pygame.draw.rect(surface, (235, 229, 205), (sx, 160, gas_w, 14))
        pygame.draw.rect(surface, (55, 154, 157), (sx, 160, gas_w, 5))
        for px in (sx + 22, sx + gas_w - 29):
            pygame.draw.rect(surface, (209, 204, 188), (px, 174, 7, 64))
        for px in (sx + 69, sx + gas_w - 91):
            pygame.draw.rect(surface, (39, 48, 57), (px, 193, 27, 45))
            pygame.draw.rect(surface, (90, 159, 151), (px + 4, 198, 19, 12))
        _label(surface, "FUEL", sx + gas_w // 2, 161, (34, 80, 85), 14, centered=True)

    # Coffee counter with a steaming cup pictogram.
    coffee_x = gas_x + 330 * scale
    result = _building_shell(surface, cx, coffee_x, 161, max(145, _i(225 * scale)), 77, (116, 72, 54), (220, 160, 85))
    if result is not None:
        bx, body = result
        pygame.draw.rect(surface, (55, 43, 42), (bx + 12, 179, body.width - 24, 23))
        _label(surface, "COFFEE", bx + body.width // 2, 181, (244, 216, 164), 15, centered=True)
        pygame.draw.rect(surface, (218, 205, 173), (bx + body.width // 2 - 8, 208, 17, 15))
        pygame.draw.rect(surface, (218, 205, 173), (bx + body.width // 2 + 9, 211, 6, 8), 2)
        pygame.draw.rect(surface, (239, 194, 109), (bx + body.width // 2 - 4, 204, 3, 4))

    # Turquoise car wash portals.
    wash_x = gas_x + 585 * scale
    wash_w = max(190, _i(290 * scale))
    result = _building_shell(surface, cx, wash_x, 145, wash_w, 93, (96, 151, 155), (226, 212, 163))
    if result is not None:
        bx, body = result
        _label(surface, "CAR WASH", bx + body.width // 2, 151, (35, 65, 72), 16, centered=True)
        for px in (bx + 20, bx + body.width // 2 + 4):
            portal_w = body.width // 2 - 30
            pygame.draw.rect(surface, (31, 45, 54), (px, 177, portal_w, 61))
            pygame.draw.rect(surface, (77, 111, 118), (px + 6, 183, portal_w - 12, 55), 4)


def _draw_rise_hall(surface: pygame.Surface, cx: float, wx: float, scale: float) -> None:
    width = max(330, _i(590 * scale))
    sx = _i(wx - cx)
    if not _onscreen(sx, width, surface.get_width()):
        return
    # Fictionalized dark modern hall inspired by the destination's massing.
    pygame.draw.rect(surface, DEEP_INK, (sx - 4, 87, width + 8, 151))
    pygame.draw.rect(surface, (40, 44, 52), (sx, 91, width, 147))
    pygame.draw.polygon(surface, (58, 61, 68), [(sx, 91), (sx + width - 72, 91), (sx + width, 126), (sx + width, 238), (sx, 238)])
    pygame.draw.rect(surface, (30, 33, 40), (sx + width // 2 - 70, 146, 140, 92))
    for px in range(sx + 20, sx + width - 18, 65):
        pygame.draw.rect(surface, (78, 115, 127), (px, 111, 38, 22))
        pygame.draw.rect(surface, (235, 167, 95), (px + 4, 115, 30, 4))
    pygame.draw.rect(surface, (188, 137, 75), (sx + width // 2 - 54, 159, 108, 6))
    _label(surface, "RISE HALL", sx + width // 2, 118, (224, 214, 191), 20, centered=True)
    pygame.draw.rect(surface, (89, 96, 101), (sx + width // 2 - 56, 171, 52, 67))
    pygame.draw.rect(surface, (89, 96, 101), (sx + width // 2 + 4, 171, 52, 67))
    # Recessed uplights and angular landscaping preserve the dark modern mass.
    for px in range(sx + 28, sx + width - 20, 84):
        pygame.draw.rect(surface, (30, 33, 39), (px, 221, 38, 17))
        pygame.draw.polygon(surface, (179, 125, 72), [(px + 15, 220), (px + 21, 220), (px + 30, 191), (px + 6, 191)])
    pygame.draw.polygon(surface, (38, 64, 49), [(sx + 18, 238), (sx + 32, 209), (sx + 45, 238)])
    pygame.draw.polygon(surface, (51, 82, 62), [(sx + width - 53, 238), (sx + width - 39, 201), (sx + width - 23, 238)])


def _draw_level_one_landmarks(surface: pygame.Surface, cx: float, world_width: int) -> None:
    """Draw the west-side Sprouts-to-El-Cilantro route in fixed world space."""

    scale = world_width / 3200.0
    world = lambda value: value * scale

    # The opening shot is deliberately a deep parking lot: the market sits
    # back from the walk lane while cart returns and parked cars establish the
    # amount of asphalt between the player and the green storefront.
    sprouts_width = max(520, _i(690 * scale))
    result = _building_shell(
        surface,
        cx,
        world(-40),
        112,
        sprouts_width,
        126,
        (213, 197, 151),
        (57, 121, 73),
    )
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (49, 103, 65), (sx + 64, 130, body.w - 128, 31))
        pygame.draw.rect(surface, (231, 211, 155), (sx + 73, 136, body.w - 146, 18))
        _label(surface, "SPROUTS FARM MARKET", sx + body.w // 2, 136, (37, 101, 61), 20, centered=True)
        for px in range(sx + 31, sx + body.w - 36, 64):
            pygame.draw.rect(surface, DEEP_INK, (px - 2, 174, 49, 56))
            pygame.draw.rect(surface, (54, 91, 92), (px, 176, 45, 52))
            pygame.draw.polygon(surface, (116, 166, 157), [(px + 4, 178), (px + 19, 178), (px + 7, 222)])
            pygame.draw.rect(surface, (232, 166, 79), (px + 7, 217, 31, 4))
        for crate_x, color in ((sx + 28, (171, 105, 54)), (sx + 50, (89, 135, 68)), (sx + body.w - 72, (196, 143, 60))):
            pygame.draw.rect(surface, DEEP_INK, (crate_x - 2, 214, 24, 18))
            pygame.draw.rect(surface, color, (crate_x, 216, 20, 14))
        pygame.draw.rect(surface, (83, 86, 83), (sx + 93, 97, 68, 15))
        pygame.draw.rect(surface, (142, 145, 135), (sx + 99, 100, 56, 9))

    # The Wells driveway is a short visual separator rather than a full combat
    # arena.  Its monument sign is readable long before the bank shell.
    bank_width = max(230, _i(315 * scale))
    result = _building_shell(surface, cx, world(760), 151, bank_width, 87, (190, 168, 132), (137, 50, 46))
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (92, 39, 42), (sx + 17, 166, body.w - 34, 18))
        _label(surface, "WELLS DRIVE", sx + body.w // 2, 168, (246, 215, 146), 14, centered=True)
        for px in range(sx + 25, sx + body.w - 42, 57):
            pygame.draw.rect(surface, (47, 73, 84), (px, 193, 40, 40))
            pygame.draw.rect(surface, (150, 194, 196), (px + 4, 197, 30, 3))

    # Remodeled blue big-box facade and mural wall between the driveway and
    # Town & Country.  The altered display name keeps the reference playful.
    mart_width = max(370, _i(490 * scale))
    result = _building_shell(surface, cx, world(1080), 125, mart_width, 113, (194, 190, 177), (48, 113, 174))
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (37, 92, 156), (sx + 18, 141, body.w - 36, 28))
        _label(surface, "WALL-MART", sx + body.w // 2, 145, (241, 226, 172), 19, centered=True)
        mural = pygame.Rect(sx + 26, 180, max(70, body.w // 3), 48)
        pygame.draw.rect(surface, (43, 75, 96), mural)
        pygame.draw.polygon(surface, (224, 135, 80), [(mural.x, mural.bottom), (mural.x + 31, mural.y + 13), (mural.x + 59, mural.bottom)])
        pygame.draw.polygon(surface, (72, 142, 119), [(mural.x + 42, mural.bottom), (mural.x + 78, mural.y + 8), (mural.x + 112, mural.bottom)])
        for px in range(mural.right + 16, sx + body.w - 32, 58):
            pygame.draw.rect(surface, INK, (px - 2, 181, 44, 49))
            pygame.draw.rect(surface, (60, 94, 107), (px, 183, 40, 45))

    # The long tan-column rhythm is the most durable Town & Country cue and
    # should dominate the middle third even if tenant names change later.
    strip_width = max(720, _i(940 * scale))
    result = _building_shell(surface, cx, world(1510), 137, strip_width, 101, (203, 178, 136), (129, 76, 54))
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (109, 60, 47), (sx + 14, 149, body.w - 28, 24))
        _label(surface, "TOWN & COUNTRY", sx + body.w // 2, 152, (247, 220, 162), 18, centered=True)
        tenant_names = ("MARKET", "SHOES", "CAFE", "WIRELESS", "FAMILY")
        bay_width = max(82, (body.w - 42) // len(tenant_names))
        for index, tenant in enumerate(tenant_names):
            bay_x = sx + 20 + index * bay_width
            pygame.draw.rect(surface, (66, 72, 73), (bay_x, 183, bay_width - 18, 47))
            pygame.draw.rect(surface, (128, 171, 167), (bay_x + 4, 187, bay_width - 26, 4))
            _label(surface, tenant, bay_x + (bay_width - 18) // 2, 174, (62, 46, 43), 11, centered=True)
            pygame.draw.rect(surface, (229, 205, 165), (bay_x - 7, 173, 7, 65))
        pygame.draw.rect(surface, (229, 205, 165), (sx + body.w - 18, 173, 7, 65))

    # Madison is an unmistakable level-end bend.  Cross-street signals and the
    # restaurant's green/orange frontage are separated so the camera reveals
    # the destination after the intersection rather than all at once.
    _draw_signal(surface, _i(world(2520) - cx), "MADISON")
    goodwill_width = max(170, _i(205 * scale))
    result = _building_shell(surface, cx, world(2550), 145, goodwill_width, 93, (217, 210, 190), (48, 97, 160))
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (39, 83, 145), (sx + 12, 158, body.w - 24, 23))
        _label(surface, "GOODWILL", sx + body.w // 2, 161, (240, 229, 185), 14, centered=True)
        for px in range(sx + 18, sx + body.w - 28, 48):
            pygame.draw.rect(surface, (50, 77, 91), (px, 191, 35, 39))
            pygame.draw.rect(surface, (129, 170, 176), (px + 4, 195, 27, 3))
    cilantro_width = max(390, _i(440 * scale))
    result = _building_shell(surface, cx, world(2760), 126, cilantro_width, 112, (223, 192, 132), (42, 111, 73))
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (38, 105, 70), (sx + 14, 141, body.w - 28, 31))
        pygame.draw.rect(surface, (230, 143, 55), (sx + 21, 147, body.w - 42, 5))
        _label(surface, "EL CILANTRO", sx + body.w // 2, 148, (250, 229, 172), 21, centered=True)
        for px in range(sx + 27, sx + body.w - 36, 66):
            pygame.draw.rect(surface, INK, (px - 2, 184, 50, 46))
            pygame.draw.rect(surface, (50, 84, 83), (px, 186, 46, 42))
            pygame.draw.rect(surface, (241, 173, 75), (px + 5, 190, 35, 4))
        pygame.draw.rect(surface, (92, 55, 42), (sx + body.w - 68, 179, 43, 59))


def _draw_level_one_ground_markers(surface: pygame.Surface, cx: float, world_width: int) -> None:
    """Anchor the Sprouts lot and Madison crossing to world progression."""

    scale = world_width / 3200.0
    width = surface.get_width()
    # Angled parking bays disappear after the market lot, providing a strong
    # visual signal that the player has left the opening location.
    for world_x in range(40, 760, 95):
        sx = _i(world_x * scale - cx)
        if _onscreen(sx, 48, width):
            pygame.draw.line(surface, (193, 188, 160), (sx, 305), (sx + 36, 342), 2)
    lot_arrow = _i(330 * scale - cx)
    if _onscreen(lot_arrow, 50, width):
        pygame.draw.polygon(surface, (203, 190, 133), [(lot_arrow, 326), (lot_arrow + 28, 326), (lot_arrow + 28, 319), (lot_arrow + 46, 333), (lot_arrow + 28, 347), (lot_arrow + 28, 340), (lot_arrow, 340)])
    cross_x = _i(2520 * scale - cx)
    for offset in range(-34, 49, 14):
        if _onscreen(cross_x + offset, 10, width):
            pygame.draw.rect(surface, (211, 205, 181), (cross_x + offset, 292, 8, 68))


def _draw_backlot(
    surface: pygame.Surface,
    cx: float,
    start_world_x: float,
    end_world_x: float,
    *,
    asphalt: Sequence[int],
    stripe: Sequence[int],
    seed: int = 0,
) -> None:
    """Draw a recessed, world-locked parking setback behind the sidewalk."""

    left = _i(start_world_x - cx)
    right = _i(end_world_x - cx)
    if right <= -64 or left >= surface.get_width() + 64:
        return
    width = max(2, right - left)
    pygame.draw.rect(surface, _shade(asphalt, -22), (left, 208, width, 31))
    pygame.draw.rect(surface, asphalt, (left, 213, width, 25))
    pygame.draw.line(surface, _shade(asphalt, 24), (left, 214), (right, 214), 2)
    # The converging marks establish actual setback depth rather than a row of
    # disconnected foreground props.  The phase is based on world X so it does
    # not swim while the camera moves.
    bay_step = 52
    first = left - ((left + seed) % bay_step) - bay_step
    for sx in range(first, right + bay_step, bay_step):
        pygame.draw.line(surface, stripe, (sx, 237), (sx + 22, 216), 1)
        pygame.draw.line(surface, _shade(stripe, -28), (sx + 3, 237), (sx + 25, 216), 1)


def _draw_chain_link(surface: pygame.Surface, screen_x: int, width: int, *, top: int = 156, bottom: int = 238) -> None:
    """Draw a compact freeway/lot fence with grounded posts and diamond mesh."""

    if not _onscreen(screen_x, width, surface.get_width()):
        return
    left = max(-12, screen_x)
    right = min(surface.get_width() + 12, screen_x + width)
    pygame.draw.rect(surface, (50, 54, 60), (left, bottom - 3, max(1, right - left), 3))
    for px in range(left - 4, right + 5, 34):
        pygame.draw.rect(surface, (61, 66, 71), (px, top, 3, bottom - top))
        pygame.draw.rect(surface, (123, 126, 121), (px + 1, top + 4, 1, bottom - top - 9))
    for py in range(top + 8, bottom - 5, 9):
        for px in range(left - 8, right + 12, 18):
            pygame.draw.line(surface, (105, 112, 111), (px, py), (px + 9, py + 5), 1)
            pygame.draw.line(surface, (77, 84, 87), (px + 9, py + 5), (px + 18, py), 1)


def _draw_neon_tube(surface: pygame.Surface, rect: pygame.Rect, color: Sequence[int], glow: Sequence[int]) -> None:
    """Draw a small two-tone sign tube, intentionally hard edged and crisp."""

    pygame.draw.rect(surface, _shade(glow, -52), rect.inflate(4, 4))
    pygame.draw.rect(surface, glow, rect.inflate(2, 2))
    pygame.draw.rect(surface, color, rect)


def _draw_level_two_landmarks(surface: pygame.Surface, cx: float, world_width: int) -> None:
    """Render the 8-Twelve, Madison Plaza, and I-8 northbound route."""

    scale = world_width / 3000.0
    world = lambda value: value * scale

    _draw_backlot(surface, cx, world(-110), world(690), asphalt=(86, 87, 92), stripe=(180, 171, 145), seed=7)
    market_w = max(500, _i(620 * scale))
    result = _building_shell(surface, cx, world(-95), 121, market_w, 117, (214, 207, 180), (207, 75, 57))
    if result is not None:
        sx, body = result
        # Three narrow color bands and a tall price tower recall a convenience
        # corner without borrowing a real chain's logo or exact lettering.
        pygame.draw.rect(surface, (229, 226, 204), (sx + 16, 140, body.w - 32, 34))
        pygame.draw.rect(surface, (203, 63, 54), (sx + 16, 141, body.w - 32, 5))
        pygame.draw.rect(surface, (244, 150, 55), (sx + 16, 147, body.w - 32, 5))
        pygame.draw.rect(surface, (64, 132, 90), (sx + 16, 153, body.w - 32, 5))
        _label(surface, "8-TWELVE MARKET", sx + body.w // 2 - 28, 157, (47, 61, 54), 18, centered=True)
        for px in range(sx + 24, sx + body.w - 65, 61):
            pygame.draw.rect(surface, DEEP_INK, (px - 2, 179, 48, 50))
            pygame.draw.rect(surface, (59, 96, 105), (px, 181, 44, 46))
            pygame.draw.rect(surface, (142, 193, 191), (px + 4, 185, 28, 3))
            pygame.draw.rect(surface, (229, 176, 82), (px + 6, 211, 31, 3))
        pygame.draw.rect(surface, (56, 56, 58), (sx + body.w - 55, 177, 34, 61))
        pygame.draw.rect(surface, (123, 180, 181), (sx + body.w - 50, 184, 20, 24))
        tower_x = sx + body.w - 4
        pygame.draw.rect(surface, DEEP_INK, (tower_x, 111, 41, 85))
        pygame.draw.rect(surface, (232, 227, 195), (tower_x + 4, 115, 33, 76))
        for row, color in enumerate(((203, 60, 52), (239, 150, 54), (54, 132, 86))):
            pygame.draw.rect(surface, color, (tower_x + 7, 121 + row * 17, 27, 8))
        _label(surface, "8", tower_x + 21, 165, (53, 63, 57), 16, centered=True)

    _draw_signal(surface, _i(world(730) - cx), "MADISON")
    _draw_backlot(surface, cx, world(820), world(1770), asphalt=(91, 88, 87), stripe=(183, 169, 133), seed=21)
    plaza_w = max(720, _i(880 * scale))
    result = _building_shell(surface, cx, world(810), 134, plaza_w, 104, (194, 165, 124), (111, 67, 50))
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (93, 55, 45), (sx + 15, 148, body.w - 30, 24))
        _label(surface, "MADISON PLAZA", sx + body.w // 2, 151, (246, 215, 160), 18, centered=True)
        tenants = (("NAILS", (185, 91, 109)), ("MART", (71, 122, 110)), ("WASH", (70, 111, 147)), ("EATS", (186, 112, 61)))
        bay = max(92, (body.w - 44) // len(tenants))
        for index, (name, accent) in enumerate(tenants):
            x = sx + 22 + index * bay
            pygame.draw.rect(surface, (52, 59, 65), (x, 181, bay - 19, 49))
            pygame.draw.rect(surface, accent, (x + 3, 184, bay - 25, 5))
            _label(surface, name, x + (bay - 19) // 2, 173, (244, 222, 174), 11, centered=True)
            pygame.draw.rect(surface, (113, 153, 159), (x + 8, 194, max(6, bay - 35), 3))
            pygame.draw.rect(surface, (225, 202, 159), (x - 6, 174, 6, 64))

    ramp_x = _i(world(1870) - cx)
    if _onscreen(ramp_x, _i(290 * scale), surface.get_width()):
        pygame.draw.polygon(surface, (90, 91, 95), [(ramp_x, 152), (ramp_x + _i(250 * scale), 112), (ramp_x + _i(290 * scale), 238), (ramp_x, 238)])
        pygame.draw.line(surface, (187, 176, 154), (ramp_x + 9, 155), (ramp_x + _i(248 * scale), 120), 4)
        for offset in range(20, max(30, _i(230 * scale)), 36):
            pygame.draw.line(surface, (65, 67, 74), (ramp_x + offset, 174), (ramp_x + offset + 28, 168), 2)
    _draw_chain_link(surface, ramp_x - 18, max(120, _i(310 * scale)), top=151)
    _draw_underpass(surface, cx, world(2210), scale)


def _draw_level_three_landmarks(surface: pygame.Surface, cx: float, world_width: int) -> None:
    """Render the Soapy Jo's wash, Broadway bend, and Revive approach."""

    scale = world_width / 3000.0
    world = lambda value: value * scale

    _draw_backlot(surface, cx, world(-120), world(780), asphalt=(80, 94, 101), stripe=(174, 200, 190), seed=14)
    wash_w = max(620, _i(745 * scale))
    result = _building_shell(surface, cx, world(-105), 112, wash_w, 126, (85, 145, 153), (238, 184, 91))
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (27, 83, 103), (sx + 16, 132, body.w - 32, 35))
        pygame.draw.rect(surface, (44, 191, 184), (sx + 18, 137, body.w - 36, 5))
        _label(surface, "SOAPY JO'S", sx + body.w // 2, 143, (245, 229, 169), 22, centered=True)
        for index, px in enumerate((sx + 28, sx + body.w // 2 + 10)):
            portal_w = max(94, body.w // 2 - 48)
            pygame.draw.rect(surface, DEEP_INK, (px - 3, 174, portal_w + 6, 64))
            pygame.draw.rect(surface, (34, 66, 83), (px, 177, portal_w, 61))
            pygame.draw.rect(surface, (68, 180, 180), (px + 5, 181, portal_w - 10, 5))
            # The alternating scrubber strands give the wash a mechanical,
            # animated-looking silhouette while remaining a fixed landmark.
            for brush_x in range(px + 13, px + portal_w - 8, 18):
                brush_y = 188 + ((brush_x // 18 + index) % 2) * 4
                pygame.draw.rect(surface, (86, 202, 190), (brush_x, brush_y, 8, 34))
                pygame.draw.rect(surface, (42, 128, 140), (brush_x + 2, brush_y + 3, 3, 29))
        for bubble_x, bubble_y, size in ((sx + 42, 119, 5), (sx + 82, 111, 3), (sx + body.w - 66, 122, 4)):
            _pixel_disc(surface, (150, 222, 214), (bubble_x, bubble_y), size)

    _draw_signal(surface, _i(world(1010) - cx), "BROADWAY")
    _draw_backlot(surface, cx, world(900), world(1930), asphalt=(92, 88, 84), stripe=(186, 170, 141), seed=31)
    turn_w = max(710, _i(900 * scale))
    result = _building_shell(surface, cx, world(900), 137, turn_w, 101, (180, 157, 130), (104, 65, 54))
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (90, 58, 48), (sx + 14, 149, body.w - 28, 25))
        _label(surface, "BROADWAY CORNER", sx + body.w // 2, 152, (246, 217, 165), 18, centered=True)
        tenants = (("TACOS", (196, 102, 54)), ("TIRES", (86, 108, 123)), ("MOBILE", (89, 142, 146)), ("VINTAGE", (142, 83, 98)))
        bay = max(92, (body.w - 44) // len(tenants))
        for index, (name, accent) in enumerate(tenants):
            x = sx + 22 + index * bay
            pygame.draw.rect(surface, (48, 56, 62), (x, 182, bay - 18, 48))
            _draw_neon_tube(surface, pygame.Rect(x + 5, 185, bay - 28, 3), accent, _shade(accent, 54))
            _label(surface, name, x + (bay - 18) // 2, 174, (235, 219, 181), 11, centered=True)
            pygame.draw.rect(surface, (118, 155, 158), (x + 8, 197, max(6, bay - 34), 2))

    _draw_backlot(surface, cx, world(2140), world(2990), asphalt=(73, 77, 84), stripe=(167, 157, 137), seed=5)
    revive_w = max(580, _i(700 * scale))
    result = _building_shell(surface, cx, world(2160), 105, revive_w, 133, (44, 54, 65), (212, 119, 71))
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (31, 37, 48), (sx + 18, 127, body.w - 36, 43))
        _draw_neon_tube(surface, pygame.Rect(sx + body.w // 2 - 82, 138, 164, 5), (255, 213, 123), (186, 79, 91))
        _label(surface, "REVIVE", sx + body.w // 2, 147, (248, 222, 161), 23, centered=True)
        for px in range(sx + 30, sx + body.w - 30, 68):
            pygame.draw.rect(surface, (19, 26, 37), (px, 179, 49, 59))
            pygame.draw.rect(surface, (65, 114, 130), (px + 4, 183, 41, 46))
            pygame.draw.rect(surface, (203, 139, 83), (px + 8, 189, 32, 2))
        pygame.draw.rect(surface, (155, 111, 69), (sx + body.w // 2 - 40, 194, 80, 44))
        pygame.draw.rect(surface, (39, 48, 58), (sx + body.w // 2 - 34, 198, 68, 40))
        for px in (sx + 31, sx + body.w - 48):
            pygame.draw.polygon(surface, (54, 86, 64), [(px, 238), (px + 11, 205), (px + 23, 238)])


def _draw_level_four_landmarks(surface: pygame.Surface, cx: float, world_width: int) -> None:
    """Render the compact Revive/Awaken lot where Couch's showdown lands."""

    scale = world_width / 1600.0
    world = lambda value: value * scale
    _draw_backlot(surface, cx, world(-90), world(1590), asphalt=(64, 67, 76), stripe=(164, 151, 122), seed=44)

    revive_w = max(550, _i(650 * scale))
    result = _building_shell(surface, cx, world(-55), 109, revive_w, 129, (48, 57, 66), (211, 117, 68))
    if result is not None:
        sx, body = result
        pygame.draw.rect(surface, (27, 34, 44), (sx + 17, 129, body.w - 34, 41))
        _draw_neon_tube(surface, pygame.Rect(sx + 43, 137, min(176, body.w - 86), 5), (251, 214, 122), (182, 75, 91))
        _label(surface, "REVIVE", sx + min(132, body.w // 2), 146, (246, 221, 162), 22, centered=True)
        for px in range(sx + 26, sx + body.w - 25, 62):
            pygame.draw.rect(surface, (18, 25, 34), (px, 179, 45, 59))
            pygame.draw.rect(surface, (59, 104, 120), (px + 4, 183, 37, 46))
        pygame.draw.rect(surface, (207, 150, 86), (sx + body.w - 77, 175, 50, 63))

    annex_w = max(660, _i(840 * scale))
    result = _building_shell(surface, cx, world(500), 82, annex_w, 156, (47, 51, 61), (210, 123, 73))
    if result is not None:
        sx, body = result
        # Orange vertical fins and a warm entry make the former church-like
        # mass unmistakable without needing a photographic backdrop.
        pygame.draw.polygon(surface, (64, 68, 76), [(sx, 84), (sx + body.w - 90, 84), (sx + body.w, 123), (sx + body.w, 238), (sx, 238)])
        for px in range(sx + 26, sx + body.w - 34, 76):
            pygame.draw.rect(surface, (91, 104, 110), (px, 109, 42, 29))
            pygame.draw.rect(surface, (228, 154, 84), (px + 4, 114, 34, 4))
        pygame.draw.rect(surface, (28, 34, 43), (sx + body.w // 2 - 100, 142, 200, 96))
        pygame.draw.rect(surface, (214, 139, 76), (sx + body.w // 2 - 91, 148, 182, 6))
        _label(surface, "AWAKEN ANNEX", sx + body.w // 2, 118, (244, 219, 166), 20, centered=True)
        _label(surface, "REVIVE FRONT LOT", sx + body.w // 2, 162, (235, 183, 111), 13, centered=True)
        pygame.draw.rect(surface, (94, 104, 107), (sx + body.w // 2 - 72, 174, 68, 64))
        pygame.draw.rect(surface, (94, 104, 107), (sx + body.w // 2 + 4, 174, 68, 64))
        for px in range(sx + 20, sx + body.w - 20, 96):
            pygame.draw.rect(surface, (31, 35, 42), (px, 224, 49, 14))
            pygame.draw.polygon(surface, (53, 86, 66), [(px + 9, 224), (px + 23, 194), (px + 37, 224)])
    _draw_chain_link(surface, _i(world(1330) - cx), max(150, _i(220 * scale)), top=170)


def _draw_chapter_one_ground_markers(surface: pygame.Surface, cx: float, world_width: int, theme: str) -> None:
    """Add route-specific road references after the shared street is painted."""

    if theme == "sprouts_el_cilantro":
        _draw_level_one_ground_markers(surface, cx, world_width)
        return
    scale = _theme_route_scale(theme, world_width)
    world = lambda value: value * scale
    width = surface.get_width()
    if theme == "seven_eleven_underpass":
        cross_x = _i(world(730) - cx)
        for offset in range(-42, 56, 14):
            if _onscreen(cross_x + offset, 10, width):
                pygame.draw.rect(surface, (213, 205, 180), (cross_x + offset, 292, 8, 68))
        # Freeway drain grates are fixed to the underpass approach.
        for route_x in (2020, 2160, 2380):
            sx = _i(world(route_x) - cx)
            if _onscreen(sx, 42, width):
                pygame.draw.rect(surface, (24, 28, 35), (sx, 302, 41, 5))
                for slot in range(sx + 4, sx + 38, 7):
                    pygame.draw.rect(surface, (102, 103, 100), (slot, 303, 2, 3))
    elif theme == "soapy_joes_revive":
        # Water tracks leave the wash and turn into a Broadway crosswalk.
        for route_x in (230, 382, 538):
            sx = _i(world(route_x) - cx)
            if _onscreen(sx, 80, width):
                pygame.draw.ellipse(surface, (48, 82, 94), (sx, 312, 78, 9))
                pygame.draw.rect(surface, (108, 166, 169), (sx + 19, 315, 34, 1))
        cross_x = _i(world(1010) - cx)
        for offset in range(-36, 50, 14):
            if _onscreen(cross_x + offset, 10, width):
                pygame.draw.rect(surface, (212, 204, 177), (cross_x + offset, 292, 8, 68))

def _draw_parked_car(surface: pygame.Surface, x: int, y: int, color: Sequence[int], facing: int = 1) -> None:
    """Draw a shaded background sedan with readable glass and chrome."""

    car = pygame.Surface((92, 39), pygame.SRCALPHA)
    outline = (26, 29, 38)
    dark = _shade(color, -48)
    light = _shade(color, 32)
    pygame.draw.ellipse(car, (22, 24, 31), (6, 27, 77, 10))
    _outlined_poly(car, [(5, 19), (17, 11), (30, 5), (61, 5), (73, 13), (86, 18), (88, 29), (4, 29)], color, outline, 2)
    pygame.draw.polygon(car, dark, [(5, 23), (88, 22), (88, 29), (4, 29)])
    pygame.draw.polygon(car, (56, 84, 101), [(23, 11), (32, 7), (43, 7), (43, 17), (16, 17)])
    pygame.draw.polygon(car, (45, 69, 87), [(47, 7), (59, 7), (69, 16), (47, 16)])
    pygame.draw.rect(car, (121, 172, 185), (26, 9, 14, 2))
    pygame.draw.rect(car, light, (9, 20, 26, 3))
    pygame.draw.rect(car, (242, 205, 112), (82, 19, 6, 5))
    for wheel_x in (17, 69):
        pygame.draw.ellipse(car, outline, (wheel_x, 24, 16, 14))
        pygame.draw.ellipse(car, (101, 107, 112), (wheel_x + 4, 28, 8, 7))
        pygame.draw.rect(car, (191, 197, 193), (wheel_x + 7, 29, 2, 5))
    if facing < 0:
        car = pygame.transform.flip(car, True, False)
    surface.blit(car, (x, y - 39))


def _draw_palm(surface: pygame.Surface, x: int, base_y: int, height: int) -> None:
    """Draw a distant block-cluster palm for the Southern California skyline."""

    trunk = (58, 47, 53)
    frond_dark = (40, 57, 57)
    frond = (49, 75, 66)
    top_y = base_y - height
    pygame.draw.lines(surface, (36, 35, 42), False, [(x + 5, base_y), (x + 2, top_y + 22), (x, top_y)], 7)
    pygame.draw.lines(surface, trunk, False, [(x + 5, base_y), (x + 2, top_y + 22), (x, top_y)], 4)
    for py in range(top_y + 13, base_y - 7, 12):
        pygame.draw.rect(surface, (92, 64, 53), (x - 1 + (py // 12) % 2, py, 5, 2))
    fronds = (
        [(x, top_y + 3), (x - 25, top_y - 4), (x - 40, top_y + 2), (x - 20, top_y + 2)],
        [(x, top_y + 3), (x + 22, top_y - 8), (x + 41, top_y - 2), (x + 21, top_y + 3)],
        [(x, top_y + 3), (x - 18, top_y + 12), (x - 35, top_y + 19), (x - 15, top_y + 10)],
        [(x, top_y + 3), (x + 17, top_y + 12), (x + 35, top_y + 20), (x + 14, top_y + 10)],
        [(x, top_y + 2), (x - 8, top_y - 18), (x + 1, top_y - 27), (x + 5, top_y - 13)],
    )
    for index, points in enumerate(fronds):
        pygame.draw.polygon(surface, frond_dark, points)
        pygame.draw.line(surface, frond if index % 2 else (65, 88, 72), points[0], points[2], 2)
    _pixel_disc(surface, (74, 58, 48), (x, top_y + 3), 5)


def _draw_bus_stop(surface: pygame.Surface, x: int) -> None:
    pygame.draw.rect(surface, (42, 47, 55), (x, 178, 4, 101))
    pygame.draw.rect(surface, (52, 111, 128), (x - 10, 178, 25, 30))
    pygame.draw.rect(surface, (180, 222, 224), (x - 7, 182, 19, 4))
    _label(surface, "BUS", x + 2, 190, (226, 238, 224), 11, centered=True)
    pygame.draw.rect(surface, (44, 47, 53), (x + 9, 260, 48, 5))
    pygame.draw.rect(surface, (104, 75, 52), (x + 13, 252, 42, 8))
    pygame.draw.rect(surface, (44, 47, 53), (x + 15, 264, 4, 15))
    pygame.draw.rect(surface, (44, 47, 53), (x + 49, 264, 4, 15))


def _draw_street_marker(surface: pygame.Surface, sx: int, prop: str) -> None:
    """Draw one small world-authoritative curb marker."""

    if prop == "hydrant":
        pygame.draw.rect(surface, (65, 35, 37), (sx - 6, 258, 16, 20))
        pygame.draw.rect(surface, (194, 61, 53), (sx - 4, 253, 12, 24))
        pygame.draw.rect(surface, (244, 101, 71), (sx - 6, 254, 16, 5))
        pygame.draw.rect(surface, (92, 45, 43), (sx - 8, 273, 20, 5))
    elif prop == "cone":
        _outlined_poly(surface, [(sx, 252), (sx + 9, 276), (sx - 9, 276)], (226, 101, 44), (63, 45, 43), 2)
        pygame.draw.rect(surface, (237, 223, 185), (sx - 5, 265, 10, 4))
        pygame.draw.rect(surface, (47, 43, 43), (sx - 12, 275, 24, 4))
    else:
        pygame.draw.rect(surface, (36, 39, 44), (sx - 5, 252, 12, 27))
        pygame.draw.rect(surface, (218, 184, 66), (sx - 4, 257, 10, 5))


def _draw_street_props(
    surface: pygame.Surface,
    cx: float,
    world_width: int,
    scale: float,
    theme: str = "legacy_second_street",
) -> None:
    """Layer vehicles, street furniture and depth anchors over the ground."""

    width = surface.get_width()
    theme = _theme_key(theme)
    specification = _CHAPTER_ONE_STREET_PROPS.get(theme)
    if specification is not None:
        route_scale = _theme_route_scale(theme, world_width)
        wx = lambda route_x: route_x * route_scale
        # Chapter 1 plates now own their parked set dressing.  Do not paint a
        # second batch of miniature code cars over the authored streetscape:
        # it muddied the scale read and made the playable lane feel toy-like.
        cars: tuple[tuple[float, Sequence[int], int], ...] = ()
        marker_props = tuple(specification["markers"])
        bus_world_x = specification["bus"]
        puddle_world_x = specification["puddle"]
        detail_scale = route_scale
    else:
        wx = lambda canonical: canonical * scale
        cars = (
            (wx(820), (83, 121, 139), -1),
            (wx(1290), (154, 76, 68), 1),
            (wx(2820), (178, 145, 67), -1),
            (wx(3300), (71, 113, 89), 1),
        )
        marker_props = ((520, "hydrant"), (1380, "cone"), (2070, "bollard"), (3120, "cone"), (4040, "hydrant"))
        bus_world_x = 1125
        puddle_world_x = 2530
        detail_scale = scale
    for world_x, color, facing in cars:
        sx = _i(world_x - cx)
        if _onscreen(sx, 92, width):
            _draw_parked_car(surface, sx, 278, color, facing)

    if bus_world_x is not None:
        bus_x = _i(wx(bus_world_x) - cx)
        if _onscreen(bus_x, 70, width):
            _draw_bus_stop(surface, bus_x)

    # Hydrants, bollards and traffic cones punctuate the long corridor.
    for canonical, prop in marker_props:
        sx = _i(wx(canonical) - cx)
        if not _onscreen(sx, 18, width):
            continue
        _draw_street_marker(surface, sx, prop)

    # Storm drains, oil rainbows and broken asphalt sell foreground depth.
    drain_step = max(210, _i(390 * detail_scale))
    drain_start = int(cx // drain_step) * drain_step
    for world_x in range(drain_start, _i(cx) + width + drain_step, drain_step):
        sx = world_x - _i(cx) + 83
        pygame.draw.rect(surface, (23, 28, 35), (sx, 287, 34, 6))
        for slot in range(sx + 4, sx + 31, 6):
            pygame.draw.rect(surface, (78, 80, 80), (slot, 288, 2, 4))
    puddle_x = _i(wx(puddle_world_x) - cx)
    if _onscreen(puddle_x, 85, width):
        pygame.draw.ellipse(surface, (35, 47, 62), (puddle_x, 314, 85, 15))
        pygame.draw.rect(surface, (90, 123, 137), (puddle_x + 17, 318, 38, 2))
        pygame.draw.rect(surface, (184, 112, 116), (puddle_x + 57, 321, 13, 1))

    crack_step = 173
    crack_start = -(int(cx) % crack_step)
    for index, sx in enumerate(range(crack_start, width + crack_step, crack_step)):
        y = 306 + (index * 13 + int(cx // crack_step) * 7) % 31
        pygame.draw.lines(surface, (29, 31, 39), False, [(sx + 31, y), (sx + 39, y + 3), (sx + 35, y + 8), (sx + 47, y + 10)], 2)

    # A near-camera vignette of cropped road debris acts as foreground framing.
    pygame.draw.polygon(surface, (31, 33, 43), [(0, 347), (54, 350), (75, 360), (0, 360)])
    pygame.draw.polygon(surface, (31, 33, 43), [(world_width % 39 + width - 72, 352), (width, 346), (width, 360), (width - 95, 360)])

def _draw_chapter_one_world_markers(surface: pygame.Surface, cx: float, world_width: int, theme: str) -> None:
    """Restore small route markers above the slow panoramic scenery.

    These markers move one-to-one with the simulation camera.  Larger physical
    obstacle sprites are depth-sorted by ``FadesGame`` after the background,
    so this pass deliberately avoids baking non-collidable foreground masses
    into the panorama.
    """

    specification = _CHAPTER_ONE_STREET_PROPS.get(theme)
    if specification is None:
        return
    width = surface.get_width()
    route_scale = _theme_route_scale(theme, world_width)
    for route_x, prop in specification["markers"]:
        sx = _layer_screen_x(float(route_x) * route_scale, cx)
        if _onscreen(sx, 18, width):
            _draw_street_marker(surface, sx, str(prop))


def _stage_panel(name: str, width: int, height: int) -> pygame.Surface | None:
    """Load an authored panel, applying its intentional gameplay framing."""

    key = (name, width, height)
    if key in _STAGE_PANEL_CACHE:
        return _STAGE_PANEL_CACHE[key]
    relative = _STAGE_PANEL_FILES.get(name)
    if relative is None:
        return None
    try:
        loaded = pygame.image.load(str(resource_path(relative)))
        viewport = _STAGE_PANEL_VIEWPORTS.get(name)
        if viewport is None:
            panel = pygame.transform.scale(loaded, (width, height))
        else:
            zoom, focal_x, focal_y = viewport
            # Cover first, then crop from an authored focal point.  This is a
            # camera framing operation, not an actor or world-scale change:
            # after composition the resulting panel remains a 1:1 world plate.
            base_scale = max(width / loaded.get_width(), height / loaded.get_height())
            scaled_w = max(width, _i(loaded.get_width() * base_scale * zoom))
            scaled_h = max(height, _i(loaded.get_height() * base_scale * zoom))
            scaled = pygame.transform.scale(loaded, (scaled_w, scaled_h))
            crop_x = _i((scaled_w - width) * max(0.0, min(1.0, focal_x)))
            crop_y = _i((scaled_h - height) * max(0.0, min(1.0, focal_y)))
            panel = pygame.Surface((width, height), pygame.SRCALPHA)
            panel.blit(scaled, (-crop_x, -crop_y))
    except (pygame.error, OSError, ValueError):
        panel = None
    _STAGE_PANEL_CACHE[key] = panel
    return panel


def _stage_panel_world_anchors(world_width: int, panel_width: int) -> dict[str, int]:
    """Return fixed world-X anchors for the three landmark paintings."""

    return {
        "pharmacy": 0,
        "overpass": _i(world_width * 0.32),
        "hall": max(0, world_width - panel_width),
    }


def _world_stage_panel(name: str, width: int, height: int, fade_left: bool, fade_right: bool) -> pygame.Surface | None:
    """Load a landmark panel with cached transparent world-space edge fades."""

    key = (name, width, height, fade_left, fade_right)
    if key in _STAGE_PANEL_WORLD_CACHE:
        return _STAGE_PANEL_WORLD_CACHE[key]
    source = _stage_panel(name, width, height)
    if source is None:
        _STAGE_PANEL_WORLD_CACHE[key] = None
        return None
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    panel.blit(source, (0, 0))
    # Keep the handoff narrow.  A broad fade exposes too much of the fallback
    # façade underneath and reads as a translucent duplicate building.
    fade_width = min(28, max(1, width // 12))
    for offset in range(fade_width):
        alpha = _i(255 * (offset + 1) / fade_width)
        if fade_left:
            panel.fill((255, 255, 255, alpha), (offset, 0, 1, height), special_flags=pygame.BLEND_RGBA_MULT)
        if fade_right:
            panel.fill((255, 255, 255, alpha), (width - 1 - offset, 0, 1, height), special_flags=pygame.BLEND_RGBA_MULT)
    _STAGE_PANEL_WORLD_CACHE[key] = panel
    return panel


def _chapter_one_world_panel(
    name: str,
    width: int,
    height: int,
    fade_left: bool = False,
) -> pygame.Surface | None:
    """Return one opaque, fixed world plate.

    Route boundaries are hard, world-registered changes of location rather
    than translucent crossfades.  A crossfade made the outgoing and incoming
    architecture read as two cutout pictures passing through one another.
    """

    key = (name, width, height, fade_left)
    if key in _STAGE_CHAPTER_PANEL_CACHE:
        return _STAGE_CHAPTER_PANEL_CACHE[key]
    source = _stage_panel(name, width, height)
    if source is None:
        _STAGE_CHAPTER_PANEL_CACHE[key] = None
        return None
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    panel.blit(source, (0, 0))
    # ``fade_left`` remains part of the cache key while older callers are
    # phased out.  The incoming plate is deliberately opaque either way.
    del fade_left
    _STAGE_CHAPTER_PANEL_CACHE[key] = panel
    return panel


def _layer_screen_x(world_x: float, camera_x: float, parallax: float = 1.0) -> int:
    """Project a world anchor into one horizontal scenery layer.

    Landmark art always uses the default one-to-one rate.  Only decorative
    layers that cannot affect navigation may opt into a different parallax
    rate; keeping that distinction explicit prevents signs, doors and physical
    props from drifting away from their authored world locations.
    """

    return _i(world_x - camera_x * parallax)


def _draw_stage_panels(surface: pygame.Surface, cx: float, world_width: int) -> bool:
    """Draw painted landmarks at fixed world coordinates over the fallback."""

    width, height = surface.get_size()
    extra_x = max(64, width // 7)
    extra_y = max(32, height // 9)
    panel_w, panel_h = width + extra_x, height + extra_y
    anchors = _stage_panel_world_anchors(world_width, panel_w)
    panels = {
        "pharmacy": _world_stage_panel("pharmacy", panel_w, panel_h, False, True),
        "overpass": _world_stage_panel("overpass", panel_w, panel_h, True, True),
        "hall": _world_stage_panel("hall", panel_w, panel_h, True, False),
    }
    if not all(panels.values()):
        return False

    panel_y = -(extra_y // 3)
    for name, panel in panels.items():
        sx = _layer_screen_x(anchors[name], cx)
        if _onscreen(sx, panel_w, width):
            surface.blit(panel, (sx, panel_y))  # type: ignore[arg-type]

    # Parody signage shares the same world anchors, so it remains attached to
    # its building instead of drifting at a fraction of camera speed.
    def sign(text: str, world_x: int, py: int, foreground: Sequence[int], backing: Sequence[int]) -> None:
        px = _layer_screen_x(world_x, cx)
        if not _onscreen(px - 80, 160, width):
            return
        face = _font(16)
        image = face.render(text, False, foreground)
        box = pygame.Rect(px - image.get_width() // 2 - 6, py - 3, image.get_width() + 12, image.get_height() + 5)
        pygame.draw.rect(surface, (27, 24, 32), box.inflate(4, 4))
        pygame.draw.rect(surface, backing, box)
        pygame.draw.rect(surface, _shade(backing, 38), (box.x + 3, box.y + 2, box.w - 6, 2))
        surface.blit(image, (px - image.get_width() // 2, py))

    sign("WALLIE'S RX", anchors["pharmacy"] + 185, 104, (255, 228, 181), (157, 39, 67))
    sign("PETBO", anchors["pharmacy"] + 522, 143, (231, 246, 232), (39, 105, 117))
    sign("8-TWELVE", anchors["overpass"] + 78, 145, (255, 231, 174), (168, 64, 58))
    sign("EIGHT-UP", anchors["overpass"] + 354, 151, (243, 239, 203), (43, 106, 102))
    sign("WAKEN HALL", anchors["hall"] + 405, 112, (255, 225, 157), (40, 78, 88))
    return True


def _chapter_one_panel_dimensions(surface: pygame.Surface) -> tuple[int, int, int]:
    """Return one broad, near-native source crop for route traversal.

    A plate intentionally spans more than one screen width.  That keeps each
    block readable as a place the party actually travels through and leaves
    only narrow, fixed world boundaries between locations.
    """

    width, height = surface.get_size()
    panel_h = height + max(96, height // 3)
    panel_w = max(width + 144, _i(panel_h * 1672 / 941))
    return panel_w, panel_h, -max(24, panel_h // 10)


def _stage_band_range(panel_h: int, band: str) -> tuple[int, int, bool, bool]:
    """Return source rows and vertical feather flags for one depth band."""

    if band == "far":
        return 0, _i(panel_h * 0.40), False, True
    if band == "mid":
        return _i(panel_h * 0.34), _i(panel_h * 0.75), True, True
    if band == "ground":
        return _i(panel_h * 0.70), panel_h, True, False
    raise KeyError(f"unknown stage depth band: {band!r}")


def _stage_band_horizontal_fade(panel_w: int) -> int:
    return min(42, max(12, panel_w // 18))


def _stage_panel_band(name: str, panel_w: int, panel_h: int, band: str) -> pygame.Surface | None:
    """Extract and cache a feathered runtime band from an authored painting."""

    key = (name, panel_w, panel_h, band)
    if key in _STAGE_PANEL_BAND_CACHE:
        return _STAGE_PANEL_BAND_CACHE[key]
    source = _stage_panel(name, panel_w, panel_h)
    if source is None:
        _STAGE_PANEL_BAND_CACHE[key] = None
        return None
    top, bottom, fade_top, fade_bottom = _stage_band_range(panel_h, band)
    band_h = max(1, bottom - top)
    layer = pygame.Surface((panel_w, band_h), pygame.SRCALPHA)
    layer.blit(source, (0, -top))

    vertical_fade = min(28, max(8, band_h // 7))
    for offset in range(vertical_fade):
        alpha = _i(255 * (offset + 1) / vertical_fade)
        if fade_top:
            layer.fill((255, 255, 255, alpha), (0, offset, panel_w, 1), special_flags=pygame.BLEND_RGBA_MULT)
        if fade_bottom:
            layer.fill((255, 255, 255, alpha), (0, band_h - 1 - offset, panel_w, 1), special_flags=pygame.BLEND_RGBA_MULT)

    horizontal_fade = _stage_band_horizontal_fade(panel_w)
    for offset in range(horizontal_fade):
        alpha = _i(255 * (offset + 1) / horizontal_fade)
        layer.fill((255, 255, 255, alpha), (offset, 0, 1, band_h), special_flags=pygame.BLEND_RGBA_MULT)
        layer.fill((255, 255, 255, alpha), (panel_w - 1 - offset, 0, 1, band_h), special_flags=pygame.BLEND_RGBA_MULT)
    _STAGE_PANEL_BAND_CACHE[key] = layer
    return layer


def _tiled_stage_layer_origin(camera_x: float, rate: float, panel_w: int) -> int:
    """Return a deterministic pixel-aligned origin for a repeating depth band."""

    fade = _stage_band_horizontal_fade(panel_w)
    period = max(1, panel_w - fade)
    return -fade - (_i(camera_x * rate) % period)


def _chapter_one_stage_layer_offsets(surface: pygame.Surface, cx: float, theme: str) -> dict[str, int]:
    """Expose exact manifest-backed layer offsets for renderer/QA parity."""

    route = _location_route(theme)
    if route is None:
        raise LocationArtError(f"no location-locked route exists for theme {theme!r}")
    width = surface.get_width()
    layer_width = int(route["world_width"])
    main_x = -_i(cx)
    far_x = _bounded_location_layer_offset(
        cx,
        float(route["far_parallax"]),
        float(route["far_max_offset"]),
        layer_width,
        width,
    )
    sky_x = far_x
    near_x = _bounded_location_layer_offset(
        cx,
        float(route["near_parallax"]),
        float(route["near_max_offset"]),
        layer_width,
        width,
    )
    return {
        "far": far_x,
        "main": main_x,
        "mid": main_x,
        "ground": main_x,
        "architecture": main_x,
        "skyline": sky_x,
        "near_occluder": near_x,
        "near": near_x,
    }


def _chapter_one_stage_panel_placement(
    surface: pygame.Surface,
    cx: float,
    world_width: int,
    theme: str,
) -> tuple[str, pygame.Rect] | None:
    """Return the single world-anchored authored set-piece rectangle."""

    panel_name = _CHAPTER_ONE_STAGE_PANEL_SPECS.get(theme)
    if panel_name is None:
        return None
    panel_w, panel_h, panel_y = _chapter_one_panel_dimensions(surface)
    scale = _theme_route_scale(theme, world_width)
    focus = float(_CHAPTER_ONE_STAGE_PANEL_FOCUS[theme]) * scale
    world_x = max(0, min(world_width - panel_w, _i(focus - panel_w / 2)))
    return panel_name, pygame.Rect(_layer_screen_x(world_x, cx), panel_y, panel_w, panel_h)


def _chapter_one_route_setpiece_placements(
    surface: pygame.Surface,
    cx: float,
    world_width: int,
    theme: str,
) -> tuple[tuple[str, pygame.Rect], ...]:
    """Return the source layout used to build one continuous route panorama.

    The sources overlap by a broad, fixed world span so the compositor can
    interlock them into one panorama.  They are not independent backdrop
    layers at runtime: every source ends up in the same 1:1 world texture.
    """

    sources = _CHAPTER_ONE_ROUTE_SETPIECES.get(theme)
    if not sources:
        return ()
    _, panel_h, panel_y = _chapter_one_panel_dimensions(surface)
    # Long routes get four unique district blocks; the shorter finale gets
    # two.  At 160 world pixels the handoff is wide enough to establish a
    # believable street transition before the camera crosses it, instead of a
    # thin image edge behind a pole.
    count = min(len(sources), 2 if world_width <= DESIGN_WIDTH * 3 else 4)
    count = max(1, count)
    overlap = min(160, max(112, panel_h // 3)) if count > 1 else 0
    panel_w = max(
        DESIGN_WIDTH + 128,
        math.ceil((world_width + overlap * max(0, count - 1)) / count),
    )
    stride = max(1, panel_w - overlap)
    starts = tuple(stride * index for index in range(count))
    return tuple(
        (
            sources[index],
            pygame.Rect(_layer_screen_x(world_x, cx), panel_y, panel_w, panel_h),
        )
        for index, world_x in enumerate(starts)
    )


def _location_locked_depth_treatment(panel: pygame.Surface, theme: str) -> pygame.Surface:
    """Bake restrained world-space color depth into one opaque route plate."""

    grade = _LOCATION_LOCK_DEPTH_GRADES.get(theme)
    treated = panel.copy()
    if grade is None:
        return treated
    sky_tint, facade_tint, ground_tint, phase = grade
    width, height = treated.get_size()
    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    sky_bottom = min(height, 130)
    facade_bottom = min(height, 234)

    # Three nearly transparent shelves separate sky, architecture and combat
    # floor.  Their low alpha preserves signs and pixels instead of repainting
    # the route with a screen-space vignette.
    pygame.draw.rect(overlay, (*sky_tint, 5), (0, 0, width, sky_bottom))
    pygame.draw.rect(
        overlay,
        (*facade_tint, 4),
        (0, sky_bottom, width, max(0, facade_bottom - sky_bottom)),
    )
    pygame.draw.rect(
        overlay,
        (*ground_tint, 6),
        (0, facade_bottom, width, max(0, height - facade_bottom)),
    )

    # Thirty-two world pixels is broad enough to read as gradual sunset falloff
    # at the 640px viewport, while integer alpha steps retain the game's crisp
    # pixel palette.  Two long waves avoid obvious repetition between cameras.
    step = 32
    for world_x in range(0, width, step):
        center = world_x + step * 0.5
        wave = 0.62 * math.sin(center / 410.0 + phase)
        wave += 0.38 * math.sin(center / 173.0 + phase * 0.73)
        strength = max(0, min(10, round(5.0 + wave * 4.0)))
        strip_width = min(step, width - world_x)
        pygame.draw.rect(
            overlay,
            (*sky_tint, max(1, strength // 2)),
            (world_x, 0, strip_width, sky_bottom),
        )
        pygame.draw.rect(
            overlay,
            (*facade_tint, max(1, strength)),
            (world_x, sky_bottom, strip_width, max(0, facade_bottom - sky_bottom)),
        )
        pygame.draw.rect(
            overlay,
            # The transparent far plate owns most skyline pixels, so the
            # opaque foundation carries its clearest depth shift in pavement.
            # A maximum alpha of twenty remains subtle while keeping the road
            # from collapsing to one flat value across adjacent cameras.
            (*ground_tint, max(1, strength * 2)),
            (world_x, facade_bottom, strip_width, max(0, height - facade_bottom)),
        )
    treated.blit(overlay, (0, 0))
    return treated


def _chapter_one_route_panorama(
    surface: pygame.Surface,
    world_width: int,
    theme: str,
) -> pygame.Surface:
    """Return the manifest-declared opaque main panorama without fallback."""

    del surface
    route = _location_route(theme)
    if route is None:
        raise LocationArtError(f"no location-locked route exists for theme {theme!r}")
    route_width = int(route["world_width"])
    if int(world_width) != route_width:
        raise LocationArtError(
            f"{theme} requires a {route_width}px world, got {int(world_width)}px"
        )
    layers = _location_art_layers(theme)
    main = layers["main"]
    if main is None:  # pragma: no cover - strict loader never caches this.
        raise LocationArtError(f"{theme} has no opaque main panorama")
    return main


def _load_location_art_asset(
    route: Mapping[str, Any],
    asset_field: str,
    *,
    required: bool = True,
    opaque: bool,
) -> pygame.Surface | None:
    if not required and asset_field not in route:
        return None
    if asset_field not in route:
        raise LocationArtError(f"{route['theme']} missing required route field {asset_field!r}")
    relative = str(route[asset_field])
    if not relative:
        raise LocationArtError(f"{route['theme']} {asset_field} must be a non-empty path")
    expected = (int(route["world_width"]), DESIGN_HEIGHT)
    path = resource_path(relative)
    try:
        image = pygame.image.load(str(path))
    except (OSError, pygame.error) as exc:
        raise LocationArtError(
            f"{route['theme']} {asset_field} is missing or unreadable: {relative}"
        ) from exc
    if image.get_size() != expected:
        raise LocationArtError(
            f"{route['theme']} {asset_field} must be {expected[0]}x{expected[1]}, "
            f"got {image.get_width()}x{image.get_height()}"
        )
    has_pixel_alpha = bool(image.get_masks()[3])
    if opaque:
        if has_pixel_alpha and pygame.mask.from_surface(image, 254).count() != expected[0] * expected[1]:
            raise LocationArtError(f"{route['theme']} main panorama must be fully opaque")
        image = image.convert() if pygame.display.get_surface() is not None else image.copy()
    else:
        if required and not has_pixel_alpha:
            raise LocationArtError(
                f"{route['theme']} {asset_field} must retain transparent alpha"
            )
        image = image.convert_alpha() if pygame.display.get_surface() is not None else image.copy()
    return image


def _location_art_layers(theme: str) -> dict[str, pygame.Surface | None]:
    """Load and retain one layered backdrop surface set for a Chapter 1 route."""

    key = _theme_key(theme)
    cached = _LOCATION_ART_CACHE.get(key)
    if cached is not None:
        _BACKGROUND_CACHE_HIT_THEMES.add(key)
        route = _location_route(key)
        if route is not None:
            _STAGE_ROUTE_PANORAMA_CACHE[
                ("location-lock", key, int(route["world_width"]), DESIGN_HEIGHT)
            ] = cached["main"]
        return cached
    route = _location_route(key)
    if route is None:
        raise LocationArtError(f"no location-locked route exists for theme {theme!r}")
    main = _load_location_art_asset(route, "main_panorama_asset", opaque=True)
    far = _load_location_art_asset(route, "far_asset", opaque=False)
    near = _load_location_art_asset(route, "near_asset", opaque=False)

    far_haze = _load_location_art_asset(
        route,
        "far_haze_asset",
        required=False,
        opaque=False,
    )
    far_skyline = _load_location_art_asset(
        route,
        "far_skyline_asset",
        required=False,
        opaque=False,
    )
    architecture = _load_location_art_asset(
        route,
        "architecture_asset",
        required=False,
        opaque=False,
    )
    ground = _load_location_art_asset(
        route,
        "ground_asset",
        required=False,
        opaque=False,
    )
    near_occluder = _load_location_art_asset(
        route,
        "near_occluder_asset",
        required=False,
        opaque=False,
    )

    # Legacy field compatibility: keep old route keys and provide aliases for
    # the compositing runtime.
    layers = {
        "main": _location_locked_depth_treatment(main, key),
        "far": far,
        "near": near,
        "far_haze": far_haze or far,
        "far_skyline": far_skyline,
        "architecture": architecture,
        "ground": ground,
        "near_occluder": near_occluder or near,
    }
    _LOCATION_ART_CACHE[key] = layers
    _STAGE_ROUTE_PANORAMA_CACHE[
        ("location-lock", key, int(route["world_width"]), DESIGN_HEIGHT)
    ] = layers["main"]
    return layers


def background_cache_used(theme: object) -> bool:
    """Return whether this route reused any in-memory scenery surface."""

    return _theme_key(theme) in _BACKGROUND_CACHE_HIT_THEMES


def _bounded_location_layer_offset(
    camera_x: float,
    rate: float,
    max_offset: float,
    layer_width: int,
    viewport_width: int,
) -> int:
    """Return world-aligned scenery with only bounded relative parallax drift."""

    physical_limit = max(0, int(layer_width) - int(viewport_width))
    camera = max(0, min(physical_limit, _i(camera_x)))
    drift_limit = max(0, min(physical_limit, _i(max_offset)))
    if float(rate) < 1.0:
        drift = min(drift_limit, _i(camera * (1.0 - float(rate))))
        offset = -camera + drift
    else:
        drift = min(drift_limit, _i(camera * (float(rate) - 1.0)))
        offset = -camera - drift
    return max(-physical_limit, min(0, offset))


def _draw_location_locked_background(
    surface: pygame.Surface,
    cx: float,
    world_width: int,
    theme: str,
    atmosphere: Any | None = None,
) -> None:
    route = _location_route(theme)
    if route is None:
        raise LocationArtError(f"no location-locked route exists for theme {theme!r}")
    if surface.get_height() != DESIGN_HEIGHT:
        raise LocationArtError(
            f"location-locked routes require a {DESIGN_HEIGHT}px logical canvas"
        )
    if int(route["world_width"]) != int(world_width):
        raise LocationArtError(
            f"{theme} runtime width disagrees with chapter1_location_lock.json"
        )
    # The authored panorama is the visual authority. The chunk renderer was
    # introduced for culling, but its low-detail architecture and ground plates
    # accidentally replaced this panorama and caused the rectangular-scene
    # regression. The shared compositor keeps the panorama at a 1:1 world
    # anchor, then adds only transparent atmosphere and ground detail.
    backdrop.render_route_backdrop(
        surface,
        theme,
        route,
        _location_art_layers(theme),
        cx,
        world_width,
        atmosphere=atmosphere,
        loader_identity=id(pygame.image.load),
    )
    # Final composition keeps the recovered authored panorama authoritative,
    # then layers depth activity around a perspective-registered ground pass.
    # Physical cars and fighters are drawn later by the game in depth order.
    _draw_chapter_one_ambient_plane(
        surface, cx, world_width, theme, "far", atmosphere=atmosphere
    )
    _draw_chapter_one_ambient_plane(
        surface, cx, world_width, theme, "mid", atmosphere=atmosphere
    )
    _draw_gameplay_ground_plane(surface, cx, world_width, theme)
    _draw_chapter_one_ambient_plane(
        surface, cx, world_width, theme, "world", atmosphere=atmosphere
    )
    _draw_world_lighting(surface, cx, world_width, theme)


def _draw_chapter_one_stage_panel(surface: pygame.Surface, cx: float, world_width: int, theme: str) -> bool:
    """Crop the already-composited route panorama at the live camera point."""

    panel = _chapter_one_route_panorama(surface, world_width, theme)
    if panel is None:
        return False
    if panel.get_height() == DESIGN_HEIGHT:
        surface.blit(panel, (_layer_screen_x(0, cx), 0))
        return True
    _, _, panel_y = _chapter_one_panel_dimensions(surface)
    surface.blit(panel, (_layer_screen_x(0, cx), panel_y))
    return True


def _draw_chapter_one_route_transition_anchors(
    surface: pygame.Surface,
    cx: float,
    world_width: int,
    theme: str,
) -> None:
    """Register each district change to a world-space utility landmark.

    The art is preblended into a single opaque panorama before rendering.  A
    one-to-one utility landmark makes each real block boundary legible as a
    place in the street rather than an exposed image edge; it moves at the
    exact same rate as every building and player.
    """

    width, height = surface.get_size()
    palette_seed = (sum(ord(character) for character in theme) % 3) - 1
    placements = _chapter_one_route_setpiece_placements(surface, cx, world_width, theme)
    if len(placements) < 2:
        return
    previous_right = placements[0][1].right
    for index, (_, rect) in enumerate(placements[1:], start=1):
        overlap = max(1, previous_right - rect.x)
        x = rect.x + overlap // 2
        previous_right = rect.right
        if not _onscreen(x - 54, 108, width):
            continue
        pole_top = 8 + (index + palette_seed) % 2 * 13
        base = min(height - 64, 284)
        # The black outer edge keeps the landmark crisp against both bright
        # sunset and underpass plates, while two warm/cool ridges give it the
        # same material read as the authored street furniture.
        pygame.draw.ellipse(surface, (13, 15, 22), (x - 30, base - 2, 60, 8))
        for support_x in (x - 45, x + 37):
            pygame.draw.rect(surface, (22, 24, 30), (support_x, pole_top + 106, 8, base - pole_top - 104))
            pygame.draw.rect(surface, (79, 83, 89), (support_x + 2, pole_top + 108, 2, base - pole_top - 110))
        pygame.draw.rect(surface, (18, 20, 27), (x - 9, pole_top, 18, base - pole_top + 2))
        pygame.draw.rect(surface, (78, 53, 42), (x - 5, pole_top + 2, 7, base - pole_top - 1))
        pygame.draw.rect(surface, (170, 109, 65), (x - 3, pole_top + 5, 2, base - pole_top - 10))
        for band_y in range(pole_top + 29, base - 6, 31):
            pygame.draw.rect(surface, (39, 30, 33), (x - 9, band_y, 18, 3))
            pygame.draw.rect(surface, (116, 73, 49), (x - 5, band_y + 1, 8, 1))
        crossbar_y = pole_top + 39
        pygame.draw.rect(surface, (20, 21, 26), (x - 42, crossbar_y, 84, 7))
        pygame.draw.rect(surface, (106, 73, 52), (x - 36, crossbar_y + 2, 72, 2))
        pygame.draw.line(surface, (22, 20, 27), (x - 134, crossbar_y + 7), (x, crossbar_y + 11), 2)
        pygame.draw.line(surface, (22, 20, 27), (x, crossbar_y + 11), (x + 134, crossbar_y + 6), 2)
        pygame.draw.rect(surface, (215, 164, 91), (x - 17, crossbar_y + 7, 3, 4))
        pygame.draw.rect(surface, (215, 164, 91), (x + 14, crossbar_y + 7, 3, 4))
        # A grounded collar prevents the pole from reading as a screen-space
        # overlay and provides a tiny gameplay-scale landmark at each block.
        pygame.draw.rect(surface, (31, 33, 39), (x - 18, base - 4, 36, 7))
        pygame.draw.rect(surface, (92, 87, 82), (x - 13, base - 3, 26, 2))


def _draw_world_lighting(surface: pygame.Surface, cx: float, world_width: int, theme: str) -> None:
    """Add transparent, world-locked light pools without repainting scenery."""

    width, height = surface.get_size()
    cache_key = (theme, width, height, int(world_width), round(float(cx), 6))
    overlay = _WORLD_LIGHTING_CACHE.get(cache_key)
    if overlay is not None:
        _WORLD_LIGHTING_CACHE.move_to_end(cache_key)
        surface.blit(overlay, (0, 0))
        return
    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    scale = _theme_route_scale(theme, world_width) if theme in _CHAPTER_ONE_THEME_ROUTE_WIDTHS else world_width / CANONICAL_STAGE_WIDTH
    specs = _THEME_LIGHT_POOLS.get(
        theme,
        ((250, 105, (255, 174, 102)), (820, 92, (235, 196, 107)), (2420, 83, (246, 148, 96)), (3740, 120, (151, 178, 205))),
    )
    for canonical, pool_width, color in specs:
        left = _layer_screen_x(canonical * scale, cx)
        scaled_width = max(24, _i(pool_width * scale))
        if not _onscreen(left, scaled_width, width):
            continue
        # Repeated low-alpha shelves suggest falloff without laying a large,
        # flat color wedge over the painting's authored asphalt texture.
        for y, spread, alpha in ((275, 0, 18), (289, 11, 10), (307, 24, 5)):
            pygame.draw.polygon(
                overlay,
                (*color, alpha),
                [
                    (left - spread, y),
                    (left + scaled_width + spread, y),
                    (left + scaled_width + spread + 9, y + 8),
                    (left - spread - 7, y + 8),
                ],
            )
        pygame.draw.rect(overlay, (*_shade(color, 42), 28), (left + 7, 275, max(7, scaled_width - 14), 2))

    # Cool lower corners frame the combat lane while preserving the painting's
    # texture and its warm focal lights.
    for inset, alpha in ((0, 34), (12, 22), (26, 12)):
        pygame.draw.polygon(overlay, (12, 16, 29, alpha), [(0, height), (0, height - 31 - inset), (94 + inset, height)])
        pygame.draw.polygon(overlay, (12, 16, 29, alpha), [(width, height), (width, height - 31 - inset), (width - 94 - inset, height)])
    _WORLD_LIGHTING_CACHE[cache_key] = overlay
    _WORLD_LIGHTING_CACHE.move_to_end(cache_key)
    while len(_WORLD_LIGHTING_CACHE) > _WORLD_LIGHTING_CACHE_LIMIT:
        _WORLD_LIGHTING_CACHE.popitem(last=False)
    surface.blit(overlay, (0, 0))


def _draw_gameplay_ground_plane(surface: pygame.Surface, cx: float, world_width: int, theme: str) -> None:
    """Register the authored road to the 1:1 gameplay world with perspective."""

    width, height = surface.get_size()
    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    scale = _theme_route_scale(theme, world_width) if theme in _CHAPTER_ONE_THEME_ROUTE_WIDTHS else world_width / CANONICAL_STAGE_WIDTH
    horizon_y = min(height - 64, 284)
    vanish_x = width // 2
    pygame.draw.line(overlay, (231, 211, 176, 34), (0, horizon_y), (width, horizon_y), 1)

    seam_step = max(96, _i(178 * scale))
    first_world_x = int(cx // seam_step) * seam_step - seam_step
    for world_x in range(first_world_x, _i(cx) + width + seam_step, seam_step):
        top_x = _layer_screen_x(world_x, cx)
        bottom_x = vanish_x + _i((top_x - vanish_x) * 1.24)
        pygame.draw.line(overlay, (205, 191, 166, 23), (top_x, horizon_y), (bottom_x, height), 1)
        pygame.draw.line(overlay, (19, 24, 34, 34), (top_x + 2, horizon_y + 2), (bottom_x + 3, height), 1)

    dash_step = max(112, _i(156 * scale))
    first_dash = int(cx // dash_step) * dash_step - dash_step
    for world_x in range(first_dash, _i(cx) + width + dash_step, dash_step):
        sx = _layer_screen_x(world_x, cx)
        pygame.draw.polygon(
            overlay,
            (183, 166, 128, 38),
            [(sx, 334), (sx + 62, 334), (sx + 70, 338), (sx - 4, 338)],
        )
        pygame.draw.line(overlay, (238, 218, 174, 22), (sx + 7, 335), (sx + 43, 335), 1)
    surface.blit(overlay, (0, 0))


def _ambient_plane_offset(camera_x: float, plane: str) -> int:
    """Return a deterministic pixel offset for one ambient depth plane."""

    if plane not in _AMBIENT_PLANE_RATES:
        raise KeyError(f"unknown ambient plane: {plane!r}")
    return -_i(camera_x * _AMBIENT_PLANE_RATES[plane])


def _ambient_motion_tick(atmosphere: Any | None) -> int:
    """Return a deterministic 30 Hz presentation tick for ambient life."""

    return max(0, int(backdrop._read_time_seconds(atmosphere) * 30.0))  # type: ignore[attr-defined]


def _chapter_one_ambient_particle_count(theme: str) -> int:
    """Return the authored worst-case particle count for one route."""

    return sum(max(0, int(event.get("particles", 0))) for event in _CHAPTER_ONE_AMBIENT_EVENTS.get(theme, ()))


def _ambient_event_visible(
    surface: pygame.Surface,
    cx: float,
    world_width: int,
    theme: str,
    event: dict[str, object],
) -> bool:
    """Gate localized presentation by its 1:1 route interval."""

    scale = _theme_route_scale(theme, world_width)
    start = float(event.get("start", 0.0)) * scale
    end = float(event.get("end", _CHAPTER_ONE_THEME_ROUTE_WIDTHS.get(theme, world_width))) * scale
    margin = 96
    return end >= cx - margin and start <= cx + surface.get_width() + margin


def _ambient_anchor_x(event: dict[str, object], cx: float, world_width: int, theme: str) -> int:
    scale = _theme_route_scale(theme, world_width)
    return _i(float(event.get("anchor", 0.0)) * scale - cx)


def _draw_ambient_vehicle(
    surface: pygame.Surface,
    x: int,
    y: int,
    color: Sequence[int],
    facing: int,
) -> None:
    """Draw a small far-lane vehicle with readable glass and lamps."""

    vehicle = pygame.Surface((42, 15), pygame.SRCALPHA)
    body = _rgb(color, (104, 104, 110))
    pygame.draw.ellipse(vehicle, (13, 17, 24, 116), (3, 10, 36, 5))
    pygame.draw.polygon(vehicle, (*_shade(body, -45), 232), [(2, 7), (9, 3), (29, 3), (38, 7), (40, 11), (1, 11)])
    pygame.draw.rect(vehicle, (*body, 238), (5, 6, 31, 5))
    pygame.draw.polygon(vehicle, (55, 83, 101, 235), [(11, 4), (17, 1), (28, 2), (33, 5)])
    pygame.draw.rect(vehicle, (208, 223, 216, 230), (35, 7, 5, 2))
    pygame.draw.rect(vehicle, (204, 63, 52, 225), (2, 7, 3, 2))
    for wheel_x in (8, 30):
        pygame.draw.rect(vehicle, (18, 21, 27, 245), (wheel_x, 10, 6, 4))
        pygame.draw.rect(vehicle, (109, 113, 116, 235), (wheel_x + 2, 11, 2, 2))
    if facing < 0:
        vehicle = pygame.transform.flip(vehicle, True, False)
    surface.blit(vehicle, (x, y - 15))


def _draw_ambient_particle(
    surface: pygame.Surface,
    kind: str,
    x: int,
    y: int,
    size: int,
    index: int,
) -> None:
    """Draw one bounded route-specific particle on an alpha plane."""

    if kind == "paper":
        color = (226, 213, 179, 150) if index % 2 else (170, 194, 181, 142)
        pygame.draw.polygon(surface, color, [(x, y), (x + size + 2, y - 1), (x + size + 3, y + size), (x + 1, y + size + 1)])
        pygame.draw.line(surface, (87, 82, 78, 130), (x + 1, y), (x + size + 2, y + size), 1)
    elif kind == "mist":
        mist = (151, 174, 181, 20 + size * 7)
        pygame.draw.ellipse(surface, mist, (x, y, 16 + size * 7, 4 + size * 2))
        pygame.draw.rect(surface, (184, 196, 194, 18 + size * 5), (x + 5, y + 2, 12 + size * 5, 2))
    elif kind == "wash_spray":
        color = (145, 232, 231, 145) if index % 3 else (226, 244, 223, 172)
        pygame.draw.rect(surface, color, (x, y, max(1, size - 1), size + 2))
        if index % 4 == 0:
            pygame.draw.ellipse(surface, (103, 204, 216, 125), (x - 2, y - 3, size + 5, size + 5), 1)
    elif kind == "dust":
        color = (231, 181, 117, 74) if index % 2 else (179, 135, 104, 66)
        pygame.draw.rect(surface, color, (x, y, size + 1, max(1, size - 1)))
        pygame.draw.rect(surface, (246, 211, 157, 46), (x + size + 2, y - 1, 1, 1))


def _draw_ambient_particles(
    surface: pygame.Surface,
    cx: float,
    world_width: int,
    theme: str,
    event: dict[str, object],
    limit: int,
    motion_tick: int,
) -> int:
    """Render a deterministic, budget-clamped localized particle field."""

    requested = max(0, int(event.get("particles", 0)))
    count = min(requested, max(0, limit), _AMBIENT_PARTICLE_LIMIT)
    if count <= 0:
        return 0
    kind = str(event["kind"])
    plane = str(event["plane"])
    scale = _theme_route_scale(theme, world_width)
    span = max(48, _i(float(event.get("span", 480.0)) * scale))
    center = _ambient_anchor_x(event, cx, world_width, theme)
    base_y = _i(float(event.get("y", 210.0)))
    field_height = max(8, _i(float(event.get("height", 54.0))))
    seed = int(event.get("seed", 0))
    rate = _AMBIENT_PLANE_RATES[plane]
    relative_motion = _i(cx * (1.0 - rate)) + _i(
        motion_tick * float(event.get("speed", 0.35))
    )
    width = surface.get_width()
    for index in range(count):
        local_x = (seed * 37 + index * 83 + relative_motion) % span
        x = center - span // 2 + local_x
        y = base_y + (seed * 13 + index * 29 + relative_motion // 5) % field_height
        if -40 <= x <= width + 40:
            _draw_ambient_particle(surface, kind, x, y, 1 + (seed + index * 5) % 3, index)
    return count


def _draw_ambient_traffic(
    surface: pygame.Surface,
    cx: float,
    event: dict[str, object],
    motion_tick: int,
) -> None:
    plane = str(event["plane"])
    count = max(1, min(6, int(event.get("instances", 3))))
    seed = int(event.get("seed", 0))
    base_y = _i(float(event.get("y", 252.0)))
    palette = tuple(event.get("palette", ((93, 104, 112),)))
    period = surface.get_width() + 116
    spacing = max(64, period // count)
    direction = -1 if int(event.get("direction", 1)) < 0 else 1
    shift = _ambient_plane_offset(cx, plane) + direction * _i(
        motion_tick * float(event.get("speed", 1.0))
    )
    for index in range(count):
        x = -58 + ((seed * 41 + index * spacing + shift) % period)
        y = base_y + (index % 2) * 5
        color = palette[index % len(palette)]
        _draw_ambient_vehicle(surface, x, y, color, direction)  # type: ignore[arg-type]


def _draw_ambient_birds(
    surface: pygame.Surface,
    cx: float,
    event: dict[str, object],
    motion_tick: int,
) -> None:
    """Draw a small far-sky flock whose wing and travel phases are visible."""

    count = max(1, min(8, int(event.get("instances", 5))))
    seed = int(event.get("seed", 0))
    direction = -1 if int(event.get("direction", 1)) < 0 else 1
    period = surface.get_width() + 150
    travel = direction * _i(motion_tick * float(event.get("speed", 0.6)))
    camera_shift = _ambient_plane_offset(cx, str(event["plane"]))
    base_y = _i(float(event.get("y", 82.0)))
    for index in range(count):
        x = -75 + ((seed * 19 + index * 137 + camera_shift + travel) % period)
        y = base_y + (index * 13 + seed) % 39
        wing = 2 + ((motion_tick // 4 + index) % 2) * 2
        color = (42, 37, 49, 185)
        pygame.draw.line(surface, color, (x - 5, y + wing), (x, y), 2)
        pygame.draw.line(surface, color, (x, y), (x + 5, y + wing), 2)


def _draw_market_canopy(surface: pygame.Surface, center: int, span: int, seed: int) -> None:
    half = min(208, max(118, span // 2))
    left, right = center - half, center + half
    pygame.draw.line(surface, (70, 48, 43, 214), (left, 185), (right, 194), 2)
    bulb_colors = ((255, 192, 91, 230), (236, 102, 72, 220), (92, 205, 190, 215))
    for index, x in enumerate(range(left + 10, right - 4, 22)):
        y = 185 + _i((x - left) * 9 / max(1, right - left))
        color = bulb_colors[(index + seed) % len(bulb_colors)]
        pygame.draw.rect(surface, (34, 29, 31, 210), (x - 1, y, 4, 5))
        pygame.draw.rect(surface, color, (x, y + 1, 2, 3))
    # A service counter and warm silhouettes make the destination legible
    # without laying a second storefront image over the authored painting.
    pygame.draw.rect(surface, (47, 34, 32, 170), (center - 79, 222, 158, 20))
    pygame.draw.rect(surface, (232, 149, 72, 172), (center - 70, 225, 140, 3))
    for x in (center - 45, center + 31):
        pygame.draw.circle(surface, (29, 29, 34, 190), (x, 222), 4)
        pygame.draw.rect(surface, (29, 29, 34, 190), (x - 3, 226, 7, 12))


def _draw_underpass_lights(surface: pygame.Surface, center: int, span: int, seed: int) -> None:
    half = min(285, max(180, span // 2))
    left, right = center - half, center + half
    pygame.draw.rect(surface, (8, 14, 23, 54), (left, 151, max(1, right - left), 102))
    for index, x in enumerate(range(left + 34, right - 20, 74)):
        lamp = (255, 193, 105, 224) if (index + seed) % 3 else (133, 205, 226, 220)
        pygame.draw.rect(surface, (21, 24, 29, 230), (x - 6, 157, 14, 5))
        pygame.draw.rect(surface, lamp, (x - 3, 159, 8, 2))
        pygame.draw.polygon(surface, (*lamp[:3], 22), [(x - 4, 162), (x + 5, 162), (x + 29, 249), (x - 26, 249)])
    # Paired streaks suggest live freeway traffic beyond the combat lane.
    for index, y in enumerate((229, 239, 249)):
        x = left + 42 + ((seed * 17 + index * 131) % max(80, right - left - 120))
        pygame.draw.rect(surface, (239, 195, 111, 148), (x, y, 27 + index * 8, 2))
        pygame.draw.rect(surface, (196, 55, 54, 124), (x + 40 + index * 8, y + 3, 18, 2))


def _draw_wash_cycle(surface: pygame.Surface, center: int, span: int, seed: int) -> None:
    half = min(330, max(210, span // 2))
    for portal_index, portal_center in enumerate((center - half // 2, center + half // 2)):
        box = pygame.Rect(portal_center - 82, 172, 164, 70)
        pygame.draw.arc(surface, (90, 231, 220, 182), box, math.pi, math.tau, 3)
        pygame.draw.arc(surface, (211, 244, 226, 112), box.inflate(-12, -8), math.pi, math.tau, 2)
        for strand in range(-58, 61, 15):
            phase = (strand // 15 + seed + portal_index) % 3
            top = 184 + phase * 3
            pygame.draw.rect(surface, (43, 142, 158, 132), (portal_center + strand, top, 5, 48))
            pygame.draw.rect(surface, (118, 222, 211, 150), (portal_center + strand + 1, top + 4, 2, 37))


def _draw_revive_neon(surface: pygame.Surface, center: int, span: int, seed: int) -> None:
    half = min(310, max(170, span // 2))
    colors = ((80, 212, 222, 105), (236, 98, 129, 104), (251, 174, 83, 102))
    for index in range(7):
        x = center - half + 22 + (index * 91 + seed * 7) % max(92, half * 2 - 70)
        y = 296 + (index * 7 + seed) % 31
        length = 22 + (index * 13) % 37
        color = colors[index % len(colors)]
        pygame.draw.polygon(surface, color, [(x, y), (x + length, y), (x + length - 7, y + 3), (x + 4, y + 3)])
        pygame.draw.rect(surface, (*color[:3], max(20, color[3] // 2)), (x + 6, y + 5, max(5, length - 15), 1))


def _draw_corridor(surface: pygame.Surface, center: int, span: int, seed: int) -> None:
    half = min(305, max(190, span // 2))
    vanishing = (center, 166)
    pygame.draw.polygon(surface, (10, 15, 24, 82), [(center - half, 236), (center + half, 236), (center + 72, 167), (center - 72, 167)])
    for index, depth in enumerate((0.18, 0.34, 0.52, 0.72, 0.91)):
        inset = _i(half * depth)
        y = 166 + _i(70 * depth)
        color = (228, 143, 76, 150) if (index + seed) % 2 else (115, 177, 190, 130)
        pygame.draw.line(surface, color, (center - inset, y), (center + inset, y), 2)
        pygame.draw.line(surface, (57, 63, 71, 135), vanishing, (center - inset, y), 1)
        pygame.draw.line(surface, (57, 63, 71, 135), vanishing, (center + inset, y), 1)
    pygame.draw.rect(surface, (248, 180, 89, 192), (center - 19, 169, 38, 3))
    pygame.draw.rect(surface, (241, 216, 162, 92), (center - 42, 173, 84, 2))


def _draw_ambient_crowd(
    surface: pygame.Surface,
    center: int,
    span: int,
    instances: int,
    seed: int,
    motion_tick: int,
) -> None:
    count = max(1, min(6, instances))
    half = min(250, max(100, span // 2))
    for index in range(count):
        x = center - half + 28 + (seed * 23 + index * 101) % max(80, half * 2 - 56)
        base_y = 254 + (index % 2) * 4 + ((motion_tick // 8 + index) % 2)
        pygame.draw.circle(surface, (22, 24, 31, 176), (x, base_y - 24), 5)
        pygame.draw.polygon(surface, (25, 28, 36, 178), [(x - 5, base_y - 18), (x + 6, base_y - 18), (x + 10, base_y), (x - 9, base_y)])
        pygame.draw.rect(surface, (171, 104, 70, 105), (x - 3, base_y - 16, 6, 2))


def _draw_ambient_event(
    surface: pygame.Surface,
    cx: float,
    world_width: int,
    theme: str,
    event: dict[str, object],
    particle_limit: int,
    motion_tick: int,
) -> int:
    kind = str(event["kind"])
    if kind == "traffic":
        _draw_ambient_traffic(surface, cx, event, motion_tick)
        return 0
    if kind == "birds":
        _draw_ambient_birds(surface, cx, event, motion_tick)
        return 0
    if int(event.get("particles", 0)):
        return _draw_ambient_particles(
            surface,
            cx,
            world_width,
            theme,
            event,
            particle_limit,
            motion_tick,
        )

    center = _ambient_anchor_x(event, cx, world_width, theme)
    span = max(1, _i(float(event.get("span", 480.0)) * _theme_route_scale(theme, world_width)))
    seed = int(event.get("seed", 0))
    if kind == "market_canopy":
        _draw_market_canopy(surface, center, span, seed + motion_tick // 12)
    elif kind == "underpass_lights":
        _draw_underpass_lights(surface, center, span, seed + motion_tick // 3)
    elif kind == "wash_cycle":
        _draw_wash_cycle(surface, center, span, seed + motion_tick // 4)
    elif kind == "revive_neon":
        _draw_revive_neon(surface, center, span, seed + motion_tick // 5)
    elif kind == "corridor":
        _draw_corridor(surface, center, span, seed + motion_tick // 10)
    elif kind == "crowd":
        _draw_ambient_crowd(
            surface,
            center,
            span,
            int(event.get("instances", 4)),
            seed,
            motion_tick,
        )
    return 0


def _draw_chapter_one_ambient_plane(
    surface: pygame.Surface,
    cx: float,
    world_width: int,
    theme: str,
    plane: str,
    *,
    atmosphere: Any | None = None,
) -> int:
    """Composite one deterministic ambient plane and return particles consumed."""

    if plane not in _AMBIENT_PLANE_RATES:
        raise KeyError(f"unknown ambient plane: {plane!r}")
    events = _CHAPTER_ONE_AMBIENT_EVENTS.get(theme, ())
    visible_events = tuple(
        event
        for event in events
        if event.get("plane") == plane
        and _ambient_event_visible(surface, cx, world_width, theme, event)
    )
    if not visible_events:
        return 0
    cache_key = (*surface.get_size(), plane)
    overlay = _AMBIENT_OVERLAY_CACHE.get(cache_key)
    if overlay is None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        _AMBIENT_OVERLAY_CACHE[cache_key] = overlay
    else:
        overlay.fill((0, 0, 0, 0))
    particles = 0
    motion_tick = _ambient_motion_tick(atmosphere)
    for event in visible_events:
        particles += _draw_ambient_event(
            overlay,
            cx,
            world_width,
            theme,
            event,
            max(0, _AMBIENT_PARTICLE_LIMIT - particles),
            motion_tick,
        )
    surface.blit(overlay, (0, 0))
    return particles


def _stage_near_layer_height(surface_height: int) -> int:
    """Reserve only the lower combat-lane edge for authored occluders."""

    return min(96, max(56, _i(surface_height * 0.27)))


def _stage_near_layer(theme: str, tile_width: int, band_height: int) -> pygame.Surface | None:
    """Return the cached, unscaled manifest near layer for compatibility."""

    del tile_width, band_height
    route = _location_route(theme)
    if route is None:
        return None
    return _location_art_layers(theme)["near"]


def _chapter_one_near_layer_offset(surface: pygame.Surface, cx: float, theme: str) -> int:
    """Return one bounded, pixel-aligned manifest near-layer offset."""

    route = _location_route(theme)
    if route is None:
        raise LocationArtError(f"no location-locked route exists for theme {theme!r}")
    return _stage_world(theme).layer_offset("near_occluder", cx, surface.get_width())


def _draw_chapter_one_near_layer(
    surface: pygame.Surface,
    cx: float,
    theme: str,
    vertical_offset: int = 0,
) -> bool:
    """Draw the cached sparse manifest near plate after actors."""

    route = _location_route(theme)
    if route is None:
        return False
    world = _stage_world(theme)
    _draw_stage_world_layer(
        surface,
        world,
        cx,
        "near_occluder",
        vertical_offset=vertical_offset,
    )
    return True


def _draw_foreground_framing(
    surface: pygame.Surface,
    cx: float,
    world_width: int,
    theme: str,
    vertical_offset: int = 0,
) -> None:
    """Draw world-repeating near silhouettes after actors for real occlusion."""

    width, height = surface.get_size()
    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    rate = _CHAPTER_ONE_PARALLAX_RATES.get(theme, {}).get("near", 1.12)
    detail_scale = _theme_route_scale(theme, world_width) if theme in _CHAPTER_ONE_THEME_ROUTE_WIDTHS else world_width / CANONICAL_STAGE_WIDTH
    bottom = height + vertical_offset
    step = max(390, _i(520 * detail_scale))
    first = int((cx * rate) // step) * step - step
    theme_seed = sum(ord(char) for char in theme) % 97
    for world_x in range(first, _i(cx * rate) + width + step, step):
        sx = _layer_screen_x(world_x + 74 + theme_seed, cx, rate)
        if not _onscreen(sx, 104, width, 24):
            continue
        pygame.draw.polygon(overlay, (13, 17, 25, 132), [(sx - 18, bottom), (sx + 7, bottom - 15), (sx + 80, bottom - 9), (sx + 104, bottom)])
        pygame.draw.rect(overlay, (79, 69, 61, 128), (sx + 18, bottom - 13, 37, 3))
        pygame.draw.rect(overlay, (128, 101, 67, 94), (sx + 62, bottom - 8, 11, 2))

    # A low guardrail periodically crosses the front edge and can cover feet,
    # making the actor visibly occupy the space between the road and camera.
    rail_step = max(720, _i(910 * detail_scale))
    rail_first = int((cx * rate) // rail_step) * rail_step - rail_step
    for world_x in range(rail_first, _i(cx * rate) + width + rail_step, rail_step):
        sx = _layer_screen_x(world_x + 238 + theme_seed, cx, rate)
        if not _onscreen(sx, 154, width, 32):
            continue
        pygame.draw.line(overlay, (20, 24, 31, 196), (sx, bottom - 30), (sx + 154, bottom - 27), 5)
        pygame.draw.line(overlay, (104, 101, 91, 184), (sx + 2, bottom - 32), (sx + 152, bottom - 29), 2)
        for post_x in (sx + 9, sx + 73, sx + 139):
            pygame.draw.rect(overlay, (25, 29, 36, 214), (post_x, bottom - 34, 7, 34))
            pygame.draw.rect(overlay, (114, 108, 95, 176), (post_x + 2, bottom - 31, 2, 27))

    # The lower grade separates feet and shadows while preserving road texture.
    for y, alpha in ((bottom - 18, 8), (bottom - 11, 12), (bottom - 5, 18)):
        pygame.draw.rect(overlay, (7, 10, 18, alpha), (0, y, width, max(1, bottom - y)))
    surface.blit(overlay, (0, 0))


def draw_stage_foreground(
    surface: pygame.Surface,
    camera_x: float,
    stage_width: float,
    shake_y: float = 0.0,
    *,
    theme: str = "legacy_second_street",
) -> pygame.Rect:
    """Draw the near 2.5D occlusion layer after actors and effects."""

    theme = _theme_key(theme)
    width = surface.get_width()
    world_width = max(width, _i(stage_width))
    cx = max(0.0, min(float(camera_x), max(0, world_width - width)))
    vertical_offset = _i(shake_y)
    route = _location_route(theme)
    if route is not None:
        if surface.get_height() != DESIGN_HEIGHT:
            raise LocationArtError(
                f"location-locked routes require a {DESIGN_HEIGHT}px logical canvas"
            )
        if int(route["world_width"]) != world_width:
            raise LocationArtError(
                f"{theme} runtime width disagrees with chapter1_location_lock.json"
            )
        _draw_chapter_one_near_layer(surface, cx, theme, vertical_offset)
    elif theme == "legacy_second_street":
        _draw_foreground_framing(surface, cx, world_width, theme, vertical_offset)
    else:
        raise LocationArtError(
            f"unknown stage theme {theme!r}; retired Chapter 1 scenery is disabled"
        )
    return surface.get_rect()


def _stage_background_frame_key(
    theme: str,
    width: int,
    height: int,
    world_width: int,
    camera_x: float,
) -> tuple[object, ...]:
    """Return a cache key for one exact, unshaken opaque world frame.

    The helper identities intentionally participate in the key.  They are
    stable in the shipped renderer, while development-time patched loaders
    naturally receive an uncached frame instead of accidentally reusing art
    from the unpatched route.
    """

    return (
        theme,
        int(width),
        int(height),
        int(world_width),
        round(float(camera_x), 6),
        id(pygame.image.load),
        id(_chapter_one_route_panorama),
        id(_location_art_layers),
        id(_stage_world),
        id(_stage_world_surface),
        id(_draw_location_locked_background),
    )


def _store_stage_background_frame(key: tuple[object, ...], frame: pygame.Surface) -> None:
    """Insert one composed frame into the bounded backdrop LRU."""

    _STAGE_BACKGROUND_FRAME_CACHE[key] = frame
    _STAGE_BACKGROUND_FRAME_CACHE.move_to_end(key)
    while len(_STAGE_BACKGROUND_FRAME_CACHE) > _STAGE_BACKGROUND_FRAME_CACHE_LIMIT:
        _STAGE_BACKGROUND_FRAME_CACHE.popitem(last=False)


def draw_stage_background(
    surface: pygame.Surface,
    camera_x: float,
    stage_width: float,
    shake_y: float = 0.0,
    *,
    theme: str = "legacy_second_street",
    atmosphere: Any | None = None,
) -> pygame.Rect:
    """Draw a strict location-locked route or the non-campaign legacy stage."""

    theme = _theme_key(theme)
    width, height = surface.get_size()
    vertical_offset = _i(shake_y)
    if vertical_offset:
        world_layer = pygame.Surface((width, height))
        draw_stage_background(
            world_layer,
            camera_x,
            stage_width,
            0.0,
            theme=theme,
            atmosphere=atmosphere,
        )
        # Camera shake must never reveal a synthetic clear color at either
        # edge.  In particular, a negative shake previously exposed SKY_TOP
        # beneath the authored asphalt and read as a warped/missing floor.
        # Extend the rendered world with its own edge scanlines, then take the
        # vertically shifted viewport from that overscanned composition.
        overscan = abs(vertical_offset)
        world_overscan = pygame.Surface((width, height + overscan * 2))
        world_overscan.blit(world_layer, (0, overscan))
        top_edge = world_layer.subsurface((0, 0, width, 1))
        bottom_edge = world_layer.subsurface((0, height - 1, width, 1))
        world_overscan.blit(
            pygame.transform.scale(top_edge, (width, overscan)),
            (0, 0),
        )
        world_overscan.blit(
            pygame.transform.scale(bottom_edge, (width, overscan)),
            (0, overscan + height),
        )
        source_y = overscan - vertical_offset
        surface.blit(
            world_overscan,
            (0, 0),
            pygame.Rect(0, source_y, width, height),
        )
        return surface.get_rect()
    world_width = max(width, _i(stage_width))
    cx = max(0.0, min(float(camera_x), max(0, world_width - width)))
    route = _location_route(theme)
    if route is not None and atmosphere is not None:
        _draw_location_locked_background(
            surface,
            cx,
            world_width,
            theme,
            atmosphere=atmosphere,
        )
        return surface.get_rect()
    frame_key = _stage_background_frame_key(theme, width, height, world_width, cx)
    cached = _STAGE_BACKGROUND_FRAME_CACHE.get(frame_key)
    if cached is not None:
        _BACKGROUND_CACHE_HIT_THEMES.add(_theme_key(theme))
        _STAGE_BACKGROUND_FRAME_CACHE.move_to_end(frame_key)
        surface.blit(cached, (0, 0))
        return surface.get_rect()
    if frame_key not in _STAGE_BACKGROUND_FRAME_BUILDING:
        # Build through this same public renderer so the cached result remains
        # pixel-identical to the normal route, including every authored plate
        # and parallax calculation.  The in-progress guard lets the nested
        # call fall through to the real drawing body exactly once.
        baked = pygame.Surface((width, height))
        _STAGE_BACKGROUND_FRAME_BUILDING.add(frame_key)
        try:
            draw_stage_background(
                baked,
                cx,
                world_width,
                0.0,
                theme=theme,
                atmosphere=None,
            )
            if pygame.display.get_surface() is not None:
                baked = baked.convert()
            _store_stage_background_frame(frame_key, baked)
        finally:
            _STAGE_BACKGROUND_FRAME_BUILDING.discard(frame_key)
        surface.blit(baked, (0, 0))
        return surface.get_rect()
    if route is not None:
        _draw_location_locked_background(surface, cx, world_width, theme, atmosphere=None)
        return surface.get_rect()
    if theme != "legacy_second_street":
        raise LocationArtError(
            f"unknown stage theme {theme!r}; retired Chapter 1 scenery is disabled"
        )
    scale = world_width / CANONICAL_STAGE_WIDTH

    # Pixel-banded July sunset.  Bands are intentionally visible.
    surface.fill(SKY_TOP)
    bands = _THEME_SKY_BANDS.get(theme, (
        (54, 30, (57, 49, 84)),
        (84, 30, (84, 57, 87)),
        (114, 30, SKY_MID),
        (144, 34, (175, 92, 88)),
        (178, 38, SKY_LOW),
    ))
    for top, band_h, color in bands:
        pygame.draw.rect(surface, color, (0, top, width, band_h))

    # Sparse hand-placed stars and dither clusters keep the upper sky alive.
    for index in range(21):
        sx = (index * 83 - _i(cx * 0.018)) % (width + 40) - 20
        sy = 17 + (index * 29) % 82
        star = (193, 191, 201) if index % 3 else (245, 212, 157)
        pygame.draw.rect(surface, star, (sx, sy, 1 if index % 4 else 2, 1))
    cloud_shift = _i(cx * 0.035)
    for base_x, base_y, cloud_w in ((80, 67, 92), (365, 43, 116), (610, 92, 74)):
        sx = (base_x - cloud_shift) % (width + 180) - 90
        pygame.draw.rect(surface, (71, 55, 82), (sx, base_y, cloud_w, 4))
        pygame.draw.rect(surface, (89, 62, 87), (sx + 18, base_y - 4, cloud_w - 35, 4))
        pygame.draw.rect(surface, (122, 73, 91), (sx + 35, base_y + 4, cloud_w - 48, 2))

    sun_x = _i(width * 0.78 - cx * 0.025)
    _pixel_disc(surface, (250, 190, 104), (sun_x, 92), 20)
    pygame.draw.rect(surface, (250, 211, 126), (sun_x - 16, 89, 32, 6))

    # Blocky foothills and utility skyline parallax more slowly than storefronts.
    parallax = _i(cx * 0.13)
    ridge: list[tuple[int, int]] = [(-80, 218)]
    for px in range(-80, width + 100, 80):
        world_segment = px + parallax
        peak = 152 + abs(((world_segment // 80) * 37) % 47)
        ridge.extend([(px + 23, peak), (px + 56, peak + 16), (px + 80, 218)])
    ridge.extend([(width + 100, 240), (-80, 240)])
    pygame.draw.polygon(surface, (70, 60, 77), ridge)
    pygame.draw.rect(surface, (66, 63, 70), (0, 218, width, 20))
    palm_shift = _i(cx * 0.17)
    for index, base_x in enumerate(range(-120, width + 220, 310)):
        _draw_palm(surface, base_x - (palm_shift % 310), 221, 74 + (index % 3) * 13)

    # Fine utility poles are placed in world space and stay behind buildings.
    street_scale = _theme_route_scale(theme, world_width) if theme in _CHAPTER_ONE_THEME_ROUTE_WIDTHS else scale
    pole_step = max(180, _i(330 * street_scale))
    first_pole = int(cx // pole_step) * pole_step
    for world_x in range(first_pole, _i(cx) + width + pole_step, pole_step):
        sx = world_x - _i(cx)
        pygame.draw.rect(surface, (66, 55, 52), (sx, 104, 4, 134))
        pygame.draw.rect(surface, (66, 55, 52), (sx - 15, 116, 34, 4))
        pygame.draw.line(surface, (45, 41, 48), (sx - 15, 121), (sx + pole_step - 15, 128), 2)

    wx = lambda canonical: canonical * scale
    if theme == "sprouts_el_cilantro":
        _draw_level_one_landmarks(surface, cx, world_width)
    elif theme == "seven_eleven_underpass":
        _draw_level_two_landmarks(surface, cx, world_width)
    elif theme == "soapy_joes_revive":
        _draw_level_three_landmarks(surface, cx, world_width)
    else:
        _draw_pharmacy(surface, cx, wx(30), scale)
        _draw_market(surface, cx, wx(590), scale)
        _draw_signal(surface, _i(wx(1190) - cx), "MADISON")
        _draw_underpass(surface, cx, wx(1450), scale)
        _draw_service_row(surface, cx, wx(2110), scale)
        _draw_signal(surface, _i(wx(3190) - cx), "BROADWAY")
        _draw_rise_hall(surface, cx, wx(3490), scale)

    # Sidewalk, curb and road occupy fixed screen-depth bands.
    sidewalk, curb_tone, road_tone = _THEME_GROUND_PALETTES.get(theme, (SIDEWALK, (115, 109, 108), ROAD))
    pygame.draw.rect(surface, sidewalk, (0, 238, width, 43))
    pygame.draw.rect(surface, _shade(sidewalk, -36), (0, 238, width, 5))
    seam_step = max(42, _i(88 * street_scale))
    seam_start = -(int(cx) % seam_step)
    for sx in range(seam_start, width + seam_step, seam_step):
        pygame.draw.line(surface, (126, 119, 116), (sx, 240), (sx + 13, 279), 2)
    pygame.draw.rect(surface, CURB, (0, 278, width, 8))
    pygame.draw.rect(surface, curb_tone, (0, 285, width, 4))
    pygame.draw.rect(surface, road_tone, (0, 289, width, max(1, height - 289)))
    pygame.draw.rect(surface, _shade(road_tone, -9), (0, 300, width, max(1, height - 300)))

    # Moving road texture prevents the ground from feeling like a static HUD.
    dash_step = 136
    dash_start = -(int(cx) % dash_step)
    for sx in range(dash_start, width + dash_step, dash_step):
        pygame.draw.rect(surface, (195, 166, 90), (sx, 335, 72, 4))
        pygame.draw.rect(surface, (230, 210, 151), (sx + 3, 335, 39, 1))
    debris_step = 97
    debris_start = -(int(cx) % debris_step)
    for index, sx in enumerate(range(debris_start, width + debris_step, debris_step)):
        dy = 304 + ((index + int(cx // debris_step)) * 11) % 29
        color = (85, 78, 72) if index % 2 else (106, 91, 77)
        pygame.draw.rect(surface, color, (sx + 31, dy, 5 + index % 4, 2))

    _draw_street_props(surface, cx, world_width, scale, theme)

    if theme in _CHAPTER_ONE_THEME_ROUTE_WIDTHS:
        _draw_chapter_one_ground_markers(surface, cx, world_width, theme)
        # The painting is deliberately last among broad opaque scenery passes,
        # so flat fallback façades and road bands can no longer cover it.
        _draw_chapter_one_stage_panel(surface, cx, world_width, theme)
        _draw_chapter_one_route_transition_anchors(surface, cx, world_width, theme)
        _draw_chapter_one_ambient_plane(surface, cx, world_width, theme, "far")
        _draw_chapter_one_ambient_plane(surface, cx, world_width, theme, "mid")
        _draw_gameplay_ground_plane(surface, cx, world_width, theme)
        _draw_chapter_one_ambient_plane(surface, cx, world_width, theme, "world")
        # Route plates already contain their curb furniture.  Do not paste the
        # simplified fallback hydrants/cones over them: that was the last
        # source of mismatched bush/prop art in the gameplay world.
    else:
        _draw_stage_panels(surface, cx, world_width)

    _draw_world_lighting(surface, cx, world_width, theme)

    # Only the non-campaign legacy street reaches this footer. Chapter routes
    # return from the strict manifest renderer above and own their copy there.
    progress = int(min(100, max(0, 100 * cx / max(1, world_width - width))))
    _label(surface, f"SECOND STREET  {progress:02d}%", 8, 8, (235, 221, 187), 13)
    return surface.get_rect()


def _travel_panel_cache_key(
    panel: Mapping[str, Any],
    width: int,
    height: int,
) -> tuple[object, ...]:
    waypoints = tuple(
        (
            str(item.get("id", "")),
            str(item.get("display_name", "")),
            str(item.get("address", "")),
        )
        for item in panel.get("waypoints", ())
        if isinstance(item, Mapping)
    )
    return (str(panel.get("id", "")), int(width), int(height), waypoints)


def _travel_panel_strip(
    panel: Mapping[str, Any],
    width: int,
    height: int,
) -> pygame.Surface:
    """Build one cached, moving non-combat corridor strip from manifest copy."""

    key = _travel_panel_cache_key(panel, width, height)
    cached = _TRAVEL_PANEL_CACHE.get(key)
    if cached is not None:
        return cached
    waypoints = tuple(
        item for item in panel.get("waypoints", ()) if isinstance(item, Mapping)
    )
    if len(waypoints) < 2:
        raise LocationArtError("travel panels require at least two manifest waypoints")
    strip_width = max(width * 3, width * len(waypoints))
    strip = pygame.Surface((strip_width, height), pygame.SRCALPHA)
    pygame.draw.rect(strip, (85, 82, 86), (0, 196, strip_width, 92))
    pygame.draw.rect(strip, (47, 50, 61), (0, 288, strip_width, height - 288))

    # Distant utilities move with the cached strip and establish real travel
    # without importing any retired Chapter 1 storefront imagery.
    for x in range(42, strip_width, 168):
        pygame.draw.rect(strip, (45, 42, 48), (x, 82, 4, 154))
        pygame.draw.rect(strip, (99, 74, 62), (x + 1, 84, 1, 149))
        pygame.draw.line(strip, (38, 36, 44), (x - 32, 101), (x + 136, 106), 1)

    segment = strip_width / len(waypoints)
    shell_colors = (
        ((173, 157, 136), (84, 105, 113)),
        ((139, 161, 164), (58, 91, 109)),
        ((191, 148, 101), (113, 72, 57)),
        ((151, 149, 158), (70, 74, 91)),
    )
    for index, waypoint in enumerate(waypoints):
        center = _i(segment * (index + 0.5))
        seed = sum(ord(char) for char in str(waypoint.get("id", "")))
        shell_width = min(_i(segment * 0.58), 410)
        shell_height = 56 + seed % 34
        wall, trim = shell_colors[seed % len(shell_colors)]
        left = center - shell_width // 2
        top = 221 - shell_height
        pygame.draw.rect(strip, DEEP_INK, (left - 4, top - 4, shell_width + 8, shell_height + 8))
        pygame.draw.rect(strip, wall, (left, top, shell_width, shell_height))
        pygame.draw.rect(strip, trim, (left, top, shell_width, 7))
        # Wide asphalt setbacks and driveway breaks are always preserved; the
        # manifest waypoint names identify the specific omitted corridor stop.
        pygame.draw.rect(strip, (109, 106, 103), (left - 54, 221, shell_width + 108, 44))
        driveway = left - 28 if index % 2 == 0 else left + shell_width - 18
        pygame.draw.polygon(
            strip,
            (131, 126, 117),
            [(driveway, 221), (driveway + 54, 221), (driveway + 73, 265), (driveway - 16, 265)],
        )
        bay_count = max(2, min(8, shell_width // 54))
        for bay in range(bay_count):
            bay_x = left + 16 + bay * max(28, (shell_width - 32) // bay_count)
            pygame.draw.rect(strip, (45, 56, 65), (bay_x, top + 25, 22, shell_height - 29))
            pygame.draw.rect(strip, (111, 148, 154), (bay_x + 2, top + 27, 18, 3))
        name = str(waypoint.get("display_name", "TRAVEL STOP"))
        address = str(waypoint.get("address", ""))
        _label(strip, name, center, max(128, top - 24), (255, 232, 171), 15, centered=True)
        _label(strip, address, center, max(145, top - 8), (190, 221, 229), 12, centered=True)

    for x in range(0, strip_width, 132):
        pygame.draw.rect(strip, (223, 193, 105), (x, 331, 74, 4))
    _TRAVEL_PANEL_CACHE[key] = strip
    return strip


def _travel_panel_camera_x(
    panel: Mapping[str, Any],
    progress: float,
    width: int,
    height: int = DESIGN_HEIGHT,
) -> int:
    strip = _travel_panel_strip(panel, width, height)
    phase = max(0.0, min(1.0, float(progress)))
    return _i((strip.get_width() - width) * phase)


def draw_location_travel_panel(
    surface: pygame.Surface,
    panel: Mapping[str, Any],
    progress: float,
    *,
    atmosphere: Any | None = None,
) -> pygame.Rect:
    """Render a pixel-aligned moving bridge between two locked route strips."""

    width, height = surface.get_size()
    backdrop._draw_opaque_sky(  # type: ignore[attr-defined]
        surface,
        {
            "sky_profile_id": getattr(
                atmosphere,
                "current_profile_id",
                "chapter_1_sunset",
            )
        },
        atmosphere,
    )
    time_seconds = backdrop._read_time_seconds(atmosphere)  # type: ignore[attr-defined]
    cloud_shift = _i(time_seconds * 7.0)
    for cloud_x, cloud_y, cloud_width in ((72, 62, 112), (332, 38, 146), (590, 91, 96)):
        sx = (cloud_x + cloud_shift) % (width + 190) - 95
        pygame.draw.rect(surface, (116, 71, 102), (sx, cloud_y, cloud_width, 5))
        pygame.draw.rect(surface, (172, 87, 104), (sx + 25, cloud_y - 5, max(22, cloud_width - 52), 5))
    strip = _travel_panel_strip(panel, width, height)
    camera = _travel_panel_camera_x(panel, progress, width, height)
    surface.blit(strip, (-camera, 0))
    return surface.get_rect()


def _vehicle_variant_surface(
    sprite: pygame.Surface,
    feature: Mapping[str, Any],
) -> pygame.Surface:
    """Apply a deterministic paint, condition, and accessory treatment."""

    model = str(feature.get("model", "sedan"))
    width_scale, height_scale = {
        "sedan": (1.0, 1.0),
        "wagon": (1.0, 1.0),
        "coupe": (1.0, 0.92),
        "compact": (0.88, 0.96),
    }.get(model, (1.0, 1.0))
    variant = pygame.transform.smoothscale(
        sprite,
        (
            max(1, round(sprite.get_width() * width_scale)),
            max(1, round(sprite.get_height() * height_scale)),
        ),
    )
    paint = tuple(int(value) for value in feature.get("paint_color", (190, 156, 104)))
    target_luma = max(1.0, sum(paint) / 3.0)
    for x in range(variant.get_width()):
        for y in range(variant.get_height()):
            pixel = variant.get_at((x, y))
            # The authored bodies are warm tan. This mask leaves tires,
            # windows, chrome, lamps, and transparent pixels untouched.
            if pixel.a < 8 or pixel.r < 60 or pixel.r - pixel.b < 16 or pixel.g - pixel.b < 7:
                continue
            luma = 0.30 * pixel.r + 0.59 * pixel.g + 0.11 * pixel.b
            scale = luma / target_luma
            recolored = tuple(max(0, min(255, round(channel * scale))) for channel in paint)
            variant.set_at((x, y), (*recolored, pixel.a))

    width, height = variant.get_size()
    condition = str(feature.get("condition", "clean"))
    if condition in {"weathered", "dusty"}:
        count = 18 if condition == "weathered" else 11
        for index in range(count):
            x = (index * 37 + width // 9) % max(1, width)
            y = height * 3 // 4 + (index * 11) % max(1, height // 5)
            pygame.draw.rect(variant, (57, 45, 39, 145), (x, y, 2 + index % 3, 1))

    accessory = str(feature.get("accessory", "none"))
    if accessory == "roof_rack":
        rack_y = max(1, height // 25)
        left, right = width * 7 // 20, width * 15 // 20
        pygame.draw.line(variant, (24, 28, 31, 255), (left, rack_y), (right, rack_y), 2)
        for support_x in (left + 3, right - 3):
            pygame.draw.line(variant, (74, 76, 75, 255), (support_x, rack_y), (support_x, rack_y + 4), 2)
    elif accessory == "rear_window_sticker":
        sticker = pygame.Rect(width * 13 // 20, height // 5, 5, 4)
        pygame.draw.rect(variant, (230, 237, 201, 255), sticker)
        pygame.draw.rect(variant, (63, 121, 151, 255), sticker, 1)
    elif accessory == "church_decal":
        center_x, center_y = width * 13 // 20, height // 4
        pygame.draw.line(variant, (238, 235, 211, 255), (center_x, center_y - 3), (center_x, center_y + 4), 2)
        pygame.draw.line(variant, (238, 235, 211, 255), (center_x - 3, center_y), (center_x + 3, center_y), 2)
    return variant


def _physical_scene_object_sprite(feature: Mapping[str, Any]) -> pygame.Surface:
    asset = str(feature.get("asset", "")).strip()
    kind = str(feature.get("kind", "")).strip().lower()
    if kind not in location_lock.SUPPORTED_PHYSICAL_SCENE_OBJECT_KINDS:
        raise LocationArtError(f"unsupported physical scene object kind: {kind!r}")
    if not asset:
        raise LocationArtError("physical scene object asset must be declared")
    physical_height = float(feature.get("physical_height_m", 0.0))
    # The projection calibration measures the shipped Dave idle silhouette at
    # 134 logical pixels.  Physical props must use that same screen-space
    # ruler; the previous 120px fallback made a 1.35m sedan undersized despite
    # otherwise correct world placement.
    reference_adult_height_px = 134.0
    physical_visible_height = max(
        1,
        int(
            round(
                float(
                    feature.get(
                        "render_height_px",
                        physical_height / 1.8 * reference_adult_height_px,
                    )
                )
            )
        ),
    )
    # Parked vehicles sit on the far scenery apron, not in the fighters'
    # active lane.  Preserve their measured physical dimensions, then apply
    # the explicit visual-depth factor from the route manifest so a car does
    # not read as a foreground giant beside the production hero silhouettes.
    visual_depth_scale = float(feature.get("visual_depth_scale", 1.0))
    visible_height = max(1, int(round(physical_visible_height * visual_depth_scale)))
    paint_color = tuple(int(value) for value in feature.get("paint_color", ()))
    model = str(feature.get("model", ""))
    condition = str(feature.get("condition", ""))
    accessory = str(feature.get("accessory", ""))
    facing = -1 if int(feature.get("facing", 1)) < 0 else 1
    key = (
        asset,
        kind,
        physical_visible_height,
        visual_depth_scale,
        visible_height,
        paint_color,
        model,
        condition,
        accessory,
        facing,
        id(pygame.image.load),
    )
    cached = _PHYSICAL_SCENE_OBJECT_CACHE.get(key)
    if cached is not None:
        return cached
    path = resource_path(asset)
    try:
        authored = pygame.image.load(str(path))
    except (OSError, pygame.error) as exc:
        raise LocationArtError(f"physical scene object asset is missing: {asset}") from exc
    if not authored.get_masks()[3]:
        raise LocationArtError(f"physical scene object asset must retain alpha: {asset}")
    authored = authored.convert_alpha() if pygame.display.get_surface() is not None else authored.copy()
    visible_bounds = authored.get_bounding_rect(min_alpha=1)
    if not visible_bounds.width or not visible_bounds.height:
        raise LocationArtError(f"physical scene object asset has no visible pixels: {asset}")
    visible = authored.subsurface(visible_bounds).copy()
    visible_width = max(1, int(round(visible.get_width() * visible_height / visible.get_height())))
    sprite = pygame.transform.smoothscale(visible, (visible_width, visible_height))
    if kind == "sedan":
        sprite = _vehicle_variant_surface(sprite, feature)
    if facing < 0:
        sprite = pygame.transform.flip(sprite, True, False)
    _PHYSICAL_SCENE_OBJECT_CACHE[key] = sprite
    return sprite


def draw_physical_scene_object(
    surface: pygame.Surface,
    x: float,
    y: float,
    feature: Mapping[str, Any],
    frame: int = 0,
) -> pygame.Rect:
    """Draw a validated physical prop at a bottom-center projected anchor."""

    del frame  # Reserved for future animated physical props.
    sprite = _physical_scene_object_sprite(feature)
    _shadow(
        surface,
        x,
        y,
        max(18, int(round(sprite.get_width() * 0.78))),
        max(5, min(9, sprite.get_height() // 11)),
        elevation=float(feature.get("elevation", 0.0)),
    )
    rect = sprite.get_rect(midbottom=(_i(x), _i(y)))
    # Two compact tire contacts stop a parked car from hovering above the
    # painted apron while retaining the broader soft shadow beneath its body.
    contact_width = max(7, sprite.get_width() // 15)
    for center_x in (
        rect.centerx - sprite.get_width() * 3 // 10,
        rect.centerx + sprite.get_width() * 3 // 10,
    ):
        pygame.draw.ellipse(
            surface,
            (7, 10, 16),
            (center_x - contact_width // 2, rect.bottom - 2, contact_width, 4),
        )
    surface.blit(sprite, rect)
    return rect


def _shadow(
    surface: pygame.Surface,
    x: float,
    y: float,
    width: int,
    height: int = 7,
    *,
    elevation: float = 0.0,
) -> pygame.Rect:
    # Sunset light comes from screen upper-left, so the broad cast edge shifts
    # subtly down-right while the darkest contact core stays under the feet.
    lift = max(0.0, float(elevation))
    if lift > 0.0:
        # Airborne actors lose their tight contact shadow.  The remaining cast
        # shadow contracts, shifts with the sunset light and fades continuously
        # while its world-ground anchor stays independent of sprite height.
        scale = max(0.42, 1.0 - min(lift, 180.0) / 240.0)
        cast_width = max(6, round(width * scale))
        cast_height = max(3, round(height * (0.58 + 0.42 * scale)))
        cast_shift = 2 + round(min(7.0, lift * 0.055))
        alpha = max(58, round(255.0 * (1.0 - min(lift, 180.0) / 235.0)))
        rect = pygame.Rect(
            _i(x) - cast_width // 2 + cast_shift,
            _i(y) - cast_height // 2 + 1 + max(0, cast_shift - 2) // 2,
            cast_width,
            cast_height,
        )
        ambient = rect.inflate(-max(2, cast_width // 7), -min(2, cast_height - 1))
        bounds = rect.union(ambient)
        layer = pygame.Surface(bounds.size, pygame.SRCALPHA)
        pygame.draw.ellipse(layer, (14, 17, 25, alpha), rect.move(-bounds.x, -bounds.y))
        pygame.draw.ellipse(
            layer,
            (26, 29, 37, max(42, round(alpha * 0.82))),
            ambient.move(-bounds.x, -bounds.y),
        )
        surface.blit(layer, bounds.topleft)
        return bounds

    rect = pygame.Rect(_i(x) - width // 2 + 2, _i(y) - height // 2 + 1, width, height)
    pygame.draw.ellipse(surface, (14, 17, 25), rect)
    ambient = rect.inflate(-max(6, width // 7), -2)
    pygame.draw.ellipse(surface, (26, 29, 37), ambient)
    contact = pygame.Rect(
        _i(x) - max(3, width // 5),
        _i(y) - 2,
        max(6, width * 2 // 5),
        max(3, height // 2),
    )
    pygame.draw.ellipse(surface, (8, 12, 19), contact)
    pygame.draw.rect(surface, (55, 49, 48), (contact.x + 2, contact.y, max(2, contact.w // 3), 1))
    return rect.union(contact)


def _grounded_sprite_variant(
    sprite: pygame.Surface,
    facing: object,
) -> tuple[pygame.Surface, pygame.Rect]:
    """Return a cached facing variant and immutable-local alpha bounds.

    Actor frames are atlas-backed and repeated many times per frame in a
    crowded fight.  Their content does not change, so the expensive alpha
    scan and mirrored allocation belong to the first use of a pose, not every
    actor draw.  Procedural fallback frames safely age out of this bounded
    cache because each entry keeps its source surface for identity checking.
    """

    key = id(sprite)
    cached = _GROUNDED_SPRITE_CACHE.get(key)
    if cached is None or cached[0] is not sprite:
        cached = (sprite, sprite.get_bounding_rect(min_alpha=1), None, None)
        _GROUNDED_SPRITE_CACHE[key] = cached
    _GROUNDED_SPRITE_CACHE.move_to_end(key)
    while len(_GROUNDED_SPRITE_CACHE) > _GROUNDED_SPRITE_CACHE_LIMIT:
        _GROUNDED_SPRITE_CACHE.popitem(last=False)

    if _face_sign(facing) >= 0:
        return cached[0], cached[1]

    mirrored = cached[2]
    mirrored_bounds = cached[3]
    if mirrored is None or mirrored_bounds is None:
        mirrored = pygame.transform.flip(sprite, True, False)
        mirrored_bounds = mirrored.get_bounding_rect(min_alpha=1)
        cached = (sprite, cached[1], mirrored, mirrored_bounds)
        _GROUNDED_SPRITE_CACHE[key] = cached
        _GROUNDED_SPRITE_CACHE.move_to_end(key)
    return mirrored, mirrored_bounds


def _blit_grounded(
    surface: pygame.Surface,
    sprite: pygame.Surface,
    x: float,
    y: float,
    z: float,
    facing: object,
    bottom: int,
) -> pygame.Rect:
    image, bounds = _grounded_sprite_variant(sprite, facing)
    destination = (_i(x) - image.get_width() // 2, _i(y - z) - bottom)
    body = surface.blit(image, destination)
    if bounds.w and bounds.h:
        return bounds.move(destination)
    return body


def draw_stage_prop(
    surface: pygame.Surface,
    x: float,
    y: float,
    kind: object = "planter",
    frame: int = 0,
) -> pygame.Rect:
    """Draw a depth-sorted physical stage prop with a clear collision footprint."""

    prop = str(kind or "planter").strip().lower().replace("-", "_").replace(" ", "_")
    sprite = pygame.Surface((96, 72), pygame.SRCALPHA)
    outline = (27, 27, 34)
    _shadow(surface, x, y, 65 if prop == "dumpster" else 54, 8)

    if prop == "dumpster":
        # Layered steel panels, lid ribs, wheels and a tiny abstract sticker.
        pygame.draw.rect(sprite, outline, (10, 18, 76, 44))
        pygame.draw.polygon(sprite, (36, 74, 69), [(13, 21), (83, 21), (78, 58), (17, 58)])
        pygame.draw.polygon(sprite, (53, 101, 91), [(15, 23), (82, 23), (80, 31), (14, 35)])
        pygame.draw.rect(sprite, (76, 124, 108), (19, 28, 5, 24))
        pygame.draw.rect(sprite, (27, 59, 58), (70, 31, 6, 23))
        pygame.draw.line(sprite, (22, 50, 49), (29, 28), (29, 56), 2)
        pygame.draw.line(sprite, (22, 50, 49), (61, 27), (61, 55), 2)
        pygame.draw.rect(sprite, (210, 156, 68), (40, 38, 17, 10))
        pygame.draw.rect(sprite, (225, 220, 185), (43, 40, 11, 2))
        pygame.draw.rect(sprite, outline, (18, 58, 13, 8))
        pygame.draw.rect(sprite, outline, (66, 58, 13, 8))
        pygame.draw.rect(sprite, (89, 92, 91), (21, 60, 7, 5))
        pygame.draw.rect(sprite, (89, 92, 91), (69, 60, 7, 5))
        glint_x = 18 + (int(frame) * 4) % 52
        pygame.draw.rect(sprite, (181, 211, 180), (glint_x, 27, 6, 2))
        if int(frame) % 6 in {2, 3}:
            pygame.draw.rect(sprite, (226, 193, 100), (51, 34, 3, 2))
        bottom = 66
    elif prop == "cart_return":
        # Green-roofed Sprouts lot corral with nested carts and wheel detail.
        pygame.draw.rect(sprite, outline, (9, 18, 78, 8))
        pygame.draw.rect(sprite, (47, 112, 70), (12, 20, 72, 4))
        for post_x in (14, 80):
            pygame.draw.rect(sprite, outline, (post_x - 2, 24, 7, 42))
            pygame.draw.rect(sprite, (171, 184, 178), (post_x, 26, 3, 37))
        for index in range(3):
            cart_x = 25 + index * 15
            pygame.draw.lines(sprite, outline, False, [(cart_x, 35), (cart_x + 7, 55), (cart_x + 25, 55), (cart_x + 28, 40)], 4)
            pygame.draw.lines(sprite, (183, 197, 192), False, [(cart_x, 35), (cart_x + 7, 55), (cart_x + 25, 55), (cart_x + 28, 40)], 2)
            pygame.draw.line(sprite, (183, 197, 192), (cart_x - 3, 34), (cart_x + 8, 34), 2)
            for wheel_x in (cart_x + 9, cart_x + 23):
                pygame.draw.ellipse(sprite, outline, (wheel_x - 3, 57, 7, 7))
                pygame.draw.rect(sprite, (121, 131, 130), (wheel_x - 1, 59, 3, 3))
                spoke_phase = (int(frame) + index) % 4
                spoke = ((0, -2), (2, 0), (0, 2), (-2, 0))[spoke_phase]
                pygame.draw.line(
                    sprite,
                    (221, 231, 221),
                    (wheel_x, 60),
                    (wheel_x + spoke[0], 60 + spoke[1]),
                    1,
                )
        glint_x = 14 + (int(frame) * 5) % 60
        pygame.draw.rect(sprite, (225, 240, 225), (glint_x, 20, 5, 2))
        bottom = 66
    elif prop in {"barrier", "road_barrier"}:
        # Bright construction barrier doubles as a readable arena rail.
        pulse = (255, 211, 86) if (int(frame) // 8) % 2 else (236, 122, 48)
        pygame.draw.rect(sprite, outline, (9, 26, 78, 22))
        pygame.draw.rect(sprite, (230, 113, 44), (12, 29, 72, 16))
        for px in range(14, 82, 20):
            pygame.draw.polygon(sprite, (245, 232, 194), [(px, 29), (px + 9, 29), (px + 20, 45), (px + 11, 45)])
        for leg_x in (18, 68):
            pygame.draw.rect(sprite, outline, (leg_x, 45, 9, 19))
            pygame.draw.rect(sprite, (193, 84, 38), (leg_x + 2, 47, 5, 15))
            pygame.draw.rect(sprite, outline, (leg_x - 6, 61, 21, 5))
        for lamp_x in (20, 72):
            pygame.draw.rect(sprite, outline, (lamp_x, 18, 8, 10))
            pygame.draw.rect(sprite, pulse, (lamp_x + 2, 20, 4, 5))
        bottom = 66
    elif prop == "bollards":
        for px in (22, 46, 70):
            pygame.draw.rect(sprite, outline, (px - 5, 26, 14, 38))
            pygame.draw.rect(sprite, (188, 151, 48), (px - 2, 29, 8, 31))
            pygame.draw.rect(sprite, (244, 218, 113), (px - 2, 36, 8, 5))
            pygame.draw.rect(sprite, (107, 78, 38), (px - 7, 61, 18, 5))
            reflector_y = 31 + ((int(frame) + px) % 5)
            pygame.draw.rect(sprite, (255, 246, 174), (px - 2, reflector_y, 8, 2))
        bottom = 66
    else:
        # Concrete planter with several hard-edged succulent clusters.
        pygame.draw.polygon(sprite, outline, [(9, 37), (87, 37), (79, 66), (17, 66)])
        pygame.draw.polygon(sprite, (91, 88, 84), [(13, 40), (83, 40), (76, 62), (20, 62)])
        pygame.draw.rect(sprite, (141, 132, 119), (17, 42, 62, 5))
        pygame.draw.rect(sprite, (64, 50, 43), (18, 34, 61, 8))
        for root_x, color in ((28, (62, 111, 71)), (49, (74, 129, 82)), (68, (53, 98, 66))):
            sway = ((int(frame) + root_x // 7) % 6) - 2
            pygame.draw.polygon(sprite, outline, [(root_x, 38), (root_x - 14 + sway, 15), (root_x - 4, 35), (root_x + sway, 8), (root_x + 5, 34), (root_x + 16 + sway, 14), (root_x + 7, 39)])
            pygame.draw.polygon(sprite, color, [(root_x, 37), (root_x - 10 + sway, 18), (root_x - 3, 34), (root_x + sway, 12), (root_x + 4, 34), (root_x + 12 + sway, 18), (root_x + 6, 38)])
            pygame.draw.rect(sprite, _shade(color, 34), (root_x + sway // 2, 17, 2, 16))
            if (int(frame) + root_x) % 7 == 0:
                pygame.draw.rect(sprite, (191, 222, 142), (root_x + 4 + sway, 18, 3, 2))
        bottom = 66

    return _blit_grounded(surface, _material_lit_sprite(sprite, "painted_metal", cache=False), x, y, 0.0, 1, bottom)


def draw_bmx_bike(surface: pygame.Surface, x: float, y: float, frame: int = 0) -> pygame.Rect:
    """Draw Dave's bright, carefully parked BMX as a readable world landmark."""

    sprite = pygame.Surface((118, 78), pygame.SRCALPHA)
    outline, chrome, blue, blue_light, gold = (24, 25, 34), (203, 215, 220), (43, 126, 224), (104, 194, 250), (244, 193, 63)
    wheel_y = 59
    for wheel_x in (25, 87):
        pygame.draw.ellipse(sprite, outline, (wheel_x - 17, wheel_y - 17, 34, 34), 4)
        pygame.draw.ellipse(sprite, chrome, (wheel_x - 13, wheel_y - 13, 26, 26), 2)
        pygame.draw.rect(sprite, gold, (wheel_x - 2, wheel_y - 2, 5, 5))
        for angle in range(0, 360, 45):
            dx = int(round(math.cos(math.radians(angle)) * 11))
            dy = int(round(math.sin(math.radians(angle)) * 11))
            pygame.draw.line(sprite, chrome, (wheel_x, wheel_y), (wheel_x + dx, wheel_y + dy), 1)
    # A compact diamond frame, handlebars, peg and a chain detail sell the BMX.
    pygame.draw.lines(sprite, outline, False, [(25, wheel_y), (48, 28), (67, wheel_y), (25, wheel_y)], 6)
    pygame.draw.lines(sprite, blue, False, [(25, wheel_y), (48, 28), (67, wheel_y), (25, wheel_y)], 3)
    _outlined_line(sprite, (48, 28), (87, wheel_y), blue, 4, outline)
    _outlined_line(sprite, (48, 28), (53, 15), chrome, 3, outline)
    _outlined_line(sprite, (53, 15), (67, 15), chrome, 3, outline)
    _outlined_line(sprite, (67, wheel_y), (84, 21), chrome, 3, outline)
    _outlined_line(sprite, (79, 18), (97, 15), chrome, 3, outline)
    pygame.draw.rect(sprite, outline, (40, 22, 17, 5))
    pygame.draw.rect(sprite, (40, 43, 50), (42, 22, 13, 3))
    pygame.draw.line(sprite, gold, (34, 55), (65, 55), 2)
    pygame.draw.rect(sprite, blue_light if (frame // 5) % 2 else blue, (49, 38, 8, 3))
    return _blit_grounded(surface, _material_lit_sprite(sprite, "painted_metal", cache=False), x, y, 0.0, 1, 73)


def _sunset_background_dimensions(surface: pygame.Surface) -> tuple[int, int, int]:
    width, height = surface.get_size()
    layer_h = height + max(24, height // 10)
    layer_w = max(width + 64, _i(layer_h * 1672 / 941))
    return layer_w, layer_h, -(layer_h - height) // 2


def _sunset_background_layers(surface: pygame.Surface) -> dict[str, pygame.Surface] | None:
    """Load and cache nearest-scaled, feathered depth bands for the finale."""

    width, height = surface.get_size()
    key = (width, height)
    if key in _SUNSET_BACKGROUND_CACHE:
        return _SUNSET_BACKGROUND_CACHE[key]
    try:
        source = pygame.image.load(str(resource_path(_SUNSET_BACKGROUND_FILE)))
        layer_w, layer_h, _ = _sunset_background_dimensions(surface)
        scaled = pygame.transform.scale(source, (layer_w, layer_h))
        ranges = {
            "far": (0, _i(layer_h * 0.47), False, True),
            "mid": (_i(layer_h * 0.40), _i(layer_h * 0.77), True, True),
            "ground": (_i(layer_h * 0.70), _i(layer_h * 0.92), True, True),
            "near": (_i(layer_h * 0.88), layer_h, True, False),
        }
        layers: dict[str, pygame.Surface] = {}
        for name, (top, bottom, fade_top, fade_bottom) in ranges.items():
            layer = pygame.Surface((layer_w, layer_h), pygame.SRCALPHA)
            layer.blit(scaled, (0, top), area=pygame.Rect(0, top, layer_w, max(1, bottom - top)))
            feather = min(14, max(4, (bottom - top) // 8))
            for offset in range(feather):
                alpha = _i(255 * (offset + 1) / feather)
                if fade_top:
                    layer.fill((255, 255, 255, alpha), (0, top + offset, layer_w, 1), special_flags=pygame.BLEND_RGBA_MULT)
                if fade_bottom:
                    layer.fill((255, 255, 255, alpha), (0, bottom - 1 - offset, layer_w, 1), special_flags=pygame.BLEND_RGBA_MULT)
            layers[name] = layer
    except (pygame.error, OSError, ValueError):
        layers = None  # type: ignore[assignment]
    _SUNSET_BACKGROUND_CACHE[key] = layers
    return layers


def _sunset_layer_offsets(surface: pygame.Surface, progress: float) -> dict[str, int]:
    """Return bounded pixel-aligned pans for the four closing-tableau planes."""

    width = surface.get_width()
    layer_w, _, _ = _sunset_background_dimensions(surface)
    travel = max(0, layer_w - width)
    phase = min(1.0, max(0.0, float(progress)))
    return {
        "far": -_i(travel * 0.16 * phase),
        "mid": -_i(travel * 0.42 * phase),
        "ground": -_i(travel * 0.74 * phase),
        "near": -_i(travel * phase),
    }


def _draw_sunset_background(surface: pygame.Surface, progress: float) -> bool:
    layers = _sunset_background_layers(surface)
    if layers is None:
        return False
    _, _, y = _sunset_background_dimensions(surface)
    offsets = _sunset_layer_offsets(surface, progress)
    for plane in ("far", "mid", "ground"):
        surface.blit(layers[plane], (offsets[plane], y))
    return True


def _draw_sunset_foreground(surface: pygame.Surface, progress: float) -> bool:
    layers = _sunset_background_layers(surface)
    if layers is None:
        return False
    _, _, y = _sunset_background_dimensions(surface)
    surface.blit(layers["near"], (_sunset_layer_offsets(surface, progress)["near"], y))
    return True


def _draw_sunset_fallback_background(surface: pygame.Surface) -> None:
    width, height = surface.get_size()
    for y, color in ((0, (57, 44, 87)), (55, (116, 70, 100)), (112, (221, 126, 91)), (170, (247, 177, 99)), (218, (99, 83, 94))):
        pygame.draw.rect(surface, color, (0, y, width, min(60, height - y)))
    sun_x = int(width * 0.74)
    _pixel_disc(surface, (255, 216, 114), (sun_x, 112), 42)
    for ridge_x in range(-60, width + 90, 90):
        peak = 176 + ((ridge_x // 90) % 3) * 9
        pygame.draw.polygon(surface, (74, 63, 83), [(ridge_x, 232), (ridge_x + 44, peak), (ridge_x + 92, 232)])
    pygame.draw.rect(surface, (58, 56, 72), (0, 232, width, height - 232))
    pygame.draw.rect(surface, (41, 43, 56), (0, 276, width, height - 276))


def _draw_sunset_wheel_motion(surface: pygame.Surface, party_x: int, bob: int, elapsed: float) -> None:
    """Add restrained code-rendered spoke glints over the authored BMX wheels."""

    angle = float(elapsed) * 8.4
    for wheel_x in (party_x + 67, party_x + 130):
        wheel_y = 261 + bob
        dx = _i(math.cos(angle) * 17)
        dy = _i(math.sin(angle) * 17)
        pygame.draw.line(surface, (177, 201, 204), (wheel_x - dx, wheel_y - dy), (wheel_x + dx, wheel_y + dy), 1)
        pygame.draw.rect(surface, (238, 188, 91), (wheel_x + dx - 1, wheel_y + dy - 1, 3, 2))


def draw_sunset_epilogue(surface: pygame.Surface, elapsed: float) -> None:
    """A layered closing tableau: Shelly and Chief walk while Dave rides."""

    progress = min(1.0, max(0.0, elapsed / 4.5))
    if not _draw_sunset_background(surface, progress):
        _draw_sunset_fallback_background(surface)
    party_x = int(42 + progress * 118)
    bob = int(math.sin(elapsed * 8.0) * 2)
    # Eight authored keys at 10 poses per second retain the 0.8-second BMX
    # stride on both 30 and 60 FPS presentation loops.
    group_frame = sprite_atlas.sunset_frame(int(elapsed * 10.0)) if sprite_atlas is not None else None
    if group_frame is not None:
        # The authored strip keeps Dave's body attached to the BMX, animates the
        # raised pedal leg, and gives Shelly and Chief a shared eight-key gait.
        lit_group = shade_authored_sprite(group_frame, "celebration")
        surface.blit(lit_group, (party_x, 286 - lit_group.get_height() + bob))
        _draw_sunset_wheel_motion(surface, party_x, bob, elapsed)
    else:  # pragma: no cover - only used if optional packaged art is missing.
        draw_bmx_bike(surface, party_x + 80, 286 + bob, int(elapsed * 12))
    _draw_sunset_foreground(surface, progress)


def _draw_dave(sprite: pygame.Surface, state: str, frame: int, accent: tuple[int, int, int]) -> None:
    # Five skin values and three material ramps keep tiny forms dimensional.
    outline = (35, 26, 29)
    skin_deep = (82, 46, 39)
    skin_shadow = (126, 70, 49)
    skin = (177, 108, 68)
    skin_light = (218, 147, 92)
    rim = (246, 181, 113)
    beard = (38, 27, 29)
    pants_deep = (23, 29, 43)
    pants = (39, 52, 72)
    pants_light = (62, 78, 99)
    gold = (239, 190, 72)
    center = 46
    moving = state in {"walk", "run", "dash", "dodge"}
    attacking = state in {"attack", "punch", "combo", "light", "heavy", "air_attack", "attack_1", "attack_2"}
    special = state in {"special", "super", "shockwave", "speaker"}
    hurt = state in {"hurt", "hitstun"}
    downed = state in {"down", "downed", "dead", "eliminated"}
    stride = 5 if moving and (frame // 2) % 2 else -3 if moving else 0

    if downed:
        # A fully horizontal defeat silhouette prevents an idle-looking knockdown.
        pygame.draw.ellipse(sprite, outline, (12, 71, 72, 15))
        pygame.draw.rect(sprite, pants_deep, (18, 69, 38, 12))
        pygame.draw.rect(sprite, pants, (22, 67, 35, 9))
        pygame.draw.rect(sprite, pants_light, (23, 68, 20, 3))
        pygame.draw.rect(sprite, outline, (52, 63, 26, 17))
        pygame.draw.rect(sprite, accent, (50, 65, 24, 12))
        pygame.draw.rect(sprite, _shade(accent, 38), (53, 66, 15, 3))
        _toned_oval(sprite, (70, 61, 20, 20), outline, skin_deep, skin, skin_light)
        pygame.draw.rect(sprite, beard, (76, 74, 12, 5))
        pygame.draw.rect(sprite, (242, 242, 226), (9, 70, 17, 8))
        pygame.draw.rect(sprite, gold, (76, 66, 11, 2))
        pygame.draw.rect(sprite, rim, (82, 63, 4, 2))
        pygame.draw.rect(sprite, _shade(accent, 20), (12, 71, 7, 3))
        return

    crouch = 6 if state == "dodge" else 0
    foot_y = 88
    # Back leg first; broad shoes and long narrow limbs retain Dave's slim build.
    pygame.draw.rect(sprite, outline, (center - 13 + stride, 57 + crouch, 11, 29 - crouch))
    pygame.draw.rect(sprite, pants_deep, (center - 10 + stride, 58 + crouch, 7, 26 - crouch))
    pygame.draw.rect(sprite, pants, (center - 8 + stride, 59 + crouch, 4, 21 - crouch))
    pygame.draw.rect(sprite, outline, (center + 1 - stride, 57 + crouch, 11, 29 - crouch))
    pygame.draw.rect(sprite, pants, (center + 3 - stride, 59 + crouch, 7, 25 - crouch))
    pygame.draw.rect(sprite, pants_light, (center + 4 - stride, 60 + crouch, 3, 18 - crouch))
    # Layered premium sneakers: outsole, upper, color panel and laces.
    for shoe_x in (center - 18 + stride, center - stride):
        pygame.draw.rect(sprite, outline, (shoe_x, foot_y - 8, 20, 9))
        pygame.draw.rect(sprite, (228, 229, 220), (shoe_x + 2, foot_y - 7, 17, 6))
        pygame.draw.rect(sprite, _shade(accent, 20), (shoe_x + 4, foot_y - 6, 7, 3))
        pygame.draw.rect(sprite, (250, 247, 228), (shoe_x + 12, foot_y - 6, 5, 2))
        pygame.draw.rect(sprite, outline, (shoe_x + 1, foot_y - 1, 19, 3))

    # Back arm and shoulder mass, outlined independently from the tank.
    back_arm = [(center - 12, 38 + crouch), (center - 20, 40 + crouch), (center - 22, 62 + crouch), (center - 15, 66 + crouch), (center - 9, 48 + crouch)]
    _outlined_poly(sprite, back_arm, skin_shadow, outline, 2)
    pygame.draw.polygon(sprite, skin, [(center - 17, 41 + crouch), (center - 19, 44 + crouch), (center - 19, 57 + crouch), (center - 16, 56 + crouch)])
    pygame.draw.rect(sprite, rim, (center - 19, 43 + crouch, 2, 10))

    torso = [(center - 13, 34 + crouch), (center - 9, 30 + crouch), (center + 10, 30 + crouch), (center + 14, 37 + crouch), (center + 10, 61 + crouch), (center - 10, 61 + crouch)]
    _outlined_poly(sprite, torso, skin_shadow, outline, 2)
    tank_points = [(center - 9, 31 + crouch), (center - 4, 31 + crouch), (center - 2, 39 + crouch), (center + 3, 39 + crouch), (center + 5, 31 + crouch), (center + 10, 32 + crouch), (center + 9, 58 + crouch), (center - 8, 58 + crouch)]
    _outlined_poly(sprite, tank_points, accent, outline, 2)
    pygame.draw.polygon(sprite, _shade(accent, -39), [(center - 7, 48 + crouch), (center + 9, 43 + crouch), (center + 9, 58 + crouch), (center - 8, 58 + crouch)])
    pygame.draw.rect(sprite, _shade(accent, 42), (center - 6, 34 + crouch, 3, 12))
    pygame.draw.rect(sprite, skin_light, (center - 11, 34 + crouch, 3, 11))

    if special:
        # Both hands grip a substantial speaker; LEDs and cone rings read clearly.
        _outlined_poly(sprite, [(center + 10, 37), (center + 18, 41), (center + 16, 61), (center + 9, 59)], skin, outline, 2)
        pygame.draw.rect(sprite, rim, (center + 13, 42, 2, 11))
        pygame.draw.rect(sprite, outline, (center - 22, 56, 48, 24))
        pygame.draw.rect(sprite, (42, 48, 61), (center - 19, 59, 42, 18))
        pygame.draw.rect(sprite, (70, 78, 91), (center - 16, 61, 36, 3))
        pulse = (105, 242, 255) if frame % 2 else (52, 164, 207)
        for cone_x in (center - 12, center + 9):
            pygame.draw.ellipse(sprite, outline, (cone_x - 7, 64, 14, 12))
            pygame.draw.ellipse(sprite, pulse, (cone_x - 5, 66, 10, 8), 2)
            pygame.draw.rect(sprite, (211, 251, 255), (cone_x - 1, 69, 3, 3))
        pygame.draw.rect(sprite, _shade(accent, 35), (center - 4, 57, 9, 3))
        pygame.draw.rect(sprite, skin_light, (center - 23, 59, 7, 8))
        pygame.draw.rect(sprite, skin_light, (center + 20, 59, 7, 8))
    elif attacking:
        heavy = state == "heavy"
        air = state == "air_attack"
        reach = 37 if heavy else 31
        # Foreshortened shoulder-to-fist chain with a bright contact rim.
        arm = [(center + 9, 35 + crouch), (center + 18, 32 + crouch), (center + reach, 36 + crouch), (center + reach + 2, 46 + crouch), (center + 16, 45 + crouch), (center + 9, 43 + crouch)]
        _outlined_poly(sprite, arm, skin, outline, 3)
        pygame.draw.polygon(sprite, skin_light, [(center + 16, 34 + crouch), (center + reach - 1, 37 + crouch), (center + reach - 1, 40 + crouch), (center + 17, 39 + crouch)])
        _toned_oval(sprite, (center + reach - 3, 34 + crouch, 15, 14), outline, skin_deep, skin, rim)
        pygame.draw.rect(sprite, (255, 244, 183), (center + reach + 10, 38 + crouch, 5, 3))
        pygame.draw.rect(sprite, (255, 151, 74), (center + reach + 16, 35 + crouch, 3, 8))
        if air:
            _outlined_line(sprite, (center + 3, 65), (center + 30, 72), pants_light, 8, outline)
            pygame.draw.rect(sprite, (244, 242, 224), (center + 27, 68, 18, 9))
    else:
        front_arm = [(center + 9, 36 + crouch), (center + 17, 39 + crouch), (center + 17, 61 + crouch), (center + 10, 66 + crouch), (center + 7, 61 + crouch)]
        _outlined_poly(sprite, front_arm, skin, outline, 2)
        pygame.draw.rect(sprite, skin_light, (center + 12, 41 + crouch, 3, 14))
        _toned_oval(sprite, (center + 8, 57 + crouch, 13, 13), outline, skin_deep, skin, rim)
        # Speaker remains recognizably clipped to the rear hip.
        pygame.draw.rect(sprite, outline, (center - 17, 57 + crouch, 13, 18))
        pygame.draw.rect(sprite, (55, 64, 78), (center - 14, 60 + crouch, 8, 12))
        pygame.draw.ellipse(sprite, (98, 178, 197), (center - 12, 64 + crouch, 5, 5), 1)

    # Head sits last so its outline stays clean over the shoulders.
    _toned_oval(sprite, (center - 13, 8 + crouch, 27, 29), outline, skin_deep, skin, skin_light)
    pygame.draw.rect(sprite, rim, (center - 8, 11 + crouch, 9, 3))
    # Close-shaved scalp under a backwards matching cap.
    pygame.draw.rect(sprite, outline, (center - 13, 6 + crouch, 27, 10))
    pygame.draw.rect(sprite, _shade(accent, -38), (center - 11, 7 + crouch, 23, 7))
    pygame.draw.rect(sprite, accent, (center - 8, 7 + crouch, 17, 3))
    pygame.draw.rect(sprite, outline, (center - 23, 9 + crouch, 12, 6))
    pygame.draw.rect(sprite, accent, (center - 21, 10 + crouch, 10, 3))
    # Beard planes, gold glasses, studs, brows, eyes and broad smile.
    pygame.draw.polygon(sprite, beard, [(center - 11, 22 + crouch), (center + 12, 21 + crouch), (center + 9, 34 + crouch), (center, 38 + crouch), (center - 9, 33 + crouch)])
    pygame.draw.polygon(sprite, skin_shadow, [(center - 5, 22 + crouch), (center + 6, 22 + crouch), (center + 4, 28 + crouch), (center - 4, 28 + crouch)])
    pygame.draw.rect(sprite, gold, (center - 10, 18 + crouch, 9, 6), 2)
    pygame.draw.rect(sprite, gold, (center + 1, 18 + crouch, 9, 6), 2)
    pygame.draw.rect(sprite, gold, (center - 1, 20 + crouch, 3, 2))
    pygame.draw.rect(sprite, (39, 42, 45), (center - 7, 20 + crouch, 4, 2))
    pygame.draw.rect(sprite, (39, 42, 45), (center + 4, 20 + crouch, 4, 2))
    pygame.draw.rect(sprite, (246, 253, 255), (center - 15, 22 + crouch, 3, 3))
    pygame.draw.rect(sprite, (154, 235, 255), (center + 13, 22 + crouch, 3, 3))
    pygame.draw.rect(sprite, outline, (center - 7, 28 + crouch, 15, 6))
    pygame.draw.rect(sprite, (255, 247, 223), (center - 5, 29 + crouch, 11, 3))
    pygame.draw.rect(sprite, (197, 70, 63), (center - 3, 33 + crouch, 7, 2))
    if hurt:
        pygame.draw.rect(sprite, (255, 247, 196), (center - 18, 11 + crouch, 3, 17))
        pygame.draw.rect(sprite, (255, 100, 77), (center - 22, 17 + crouch, 3, 8))


@lru_cache(maxsize=1)
def _ko_preview_sprite() -> pygame.Surface | None:
    """Load the authored KO preview cutout used by the engine capture path."""

    try:
        source = pygame.image.load(str(resource_path("assets/ko_preview_cutout.png"))).convert_alpha()
    except (FileNotFoundError, pygame.error):
        return None
    target_height = 112
    scale = target_height / max(1, source.get_height())
    size = (max(1, round(source.get_width() * scale)), target_height)
    return pygame.transform.smoothscale(source, size)


def _ko_preview_enabled() -> bool:
    """Keep the capture-only KO cutout out of ordinary gameplay renders."""

    return os.environ.get("FADES_KO_PREVIEW", "").strip().lower() in {"1", "true", "yes", "on"}


def _draw_shelly(sprite: pygame.Surface, state: str, frame: int, accent: tuple[int, int, int]) -> None:
    outline = (42, 29, 34)
    skin_deep = (143, 79, 82)
    skin_shadow = (193, 116, 112)
    skin = (227, 157, 142)
    skin_light = (250, 194, 172)
    rim = (255, 220, 190)
    hair_deep = (49, 29, 27)
    hair = (78, 43, 34)
    hair_mid = (119, 67, 47)
    hair_light = (164, 99, 61)
    cargo_deep = (45, 51, 39)
    cargo = (83, 96, 68)
    cargo_light = (124, 136, 91)
    center = 45
    moving = state in {"walk", "run", "dash", "dodge"}
    attacking = state in {"attack", "torch", "flame", "combo", "light", "heavy", "air_attack"}
    special = state in {"special", "super", "chief", "call_chief"}
    refill = state == "idle" and 112 <= frame % 160 <= 143
    hurt = state in {"hurt", "hitstun"}
    downed = state in {"down", "downed", "dead", "eliminated"}
    stride = 4 if moving and (frame // 2) % 2 else -3 if moving else 0

    if downed:
        pygame.draw.ellipse(sprite, outline, (11, 70, 77, 16))
        pygame.draw.rect(sprite, cargo_deep, (17, 69, 45, 11))
        pygame.draw.rect(sprite, cargo, (20, 67, 39, 9))
        pygame.draw.rect(sprite, cargo_light, (22, 68, 24, 3))
        pygame.draw.rect(sprite, (23, 25, 29), (44, 72, 14, 3))
        pygame.draw.rect(sprite, accent, (53, 64, 22, 13))
        pygame.draw.rect(sprite, _shade(accent, 42), (56, 65, 12, 3))
        _toned_oval(sprite, (72, 60, 21, 21), outline, skin_deep, skin, skin_light)
        pygame.draw.rect(sprite, hair, (78, 59, 13, 6))
        pygame.draw.rect(sprite, hair_mid, (81, 60, 7, 2))
        pygame.draw.rect(sprite, hair_light, (83, 60, 3, 2))
        pygame.draw.ellipse(sprite, hair_deep, (87, 55, 9, 9))
        pygame.draw.rect(sprite, rim, (76, 63, 4, 2))
        pygame.draw.rect(sprite, (215, 207, 187), (13, 72, 13, 4))
        return

    crouch = 5 if state == "dodge" else 0
    # Wider hips taper to compact boots, retaining a short athletic stance.
    pygame.draw.rect(sprite, outline, (center - 17 + stride, 57 + crouch, 15, 27 - crouch))
    pygame.draw.rect(sprite, cargo_deep, (center - 14 + stride, 58 + crouch, 11, 24 - crouch))
    pygame.draw.rect(sprite, cargo, (center - 11 + stride, 58 + crouch, 7, 20 - crouch))
    pygame.draw.rect(sprite, outline, (center + 2 - stride, 57 + crouch, 15, 27 - crouch))
    pygame.draw.rect(sprite, cargo, (center + 4 - stride, 58 + crouch, 11, 24 - crouch))
    pygame.draw.rect(sprite, cargo_light, (center + 5 - stride, 59 + crouch, 4, 17 - crouch))
    for shoe_x in (center - 20 + stride, center + 1 - stride):
        pygame.draw.rect(sprite, outline, (shoe_x, 80, 21, 9))
        pygame.draw.rect(sprite, (72, 63, 56), (shoe_x + 2, 81, 18, 5))
        pygame.draw.rect(sprite, (215, 207, 187), (shoe_x + 2, 86, 19, 2))

    # Hip block, generous cargo pockets and her signature thigh strap.
    hips = [(center - 17, 50 + crouch), (center - 12, 45 + crouch), (center + 12, 45 + crouch), (center + 18, 51 + crouch), (center + 15, 63 + crouch), (center - 15, 63 + crouch)]
    _outlined_poly(sprite, hips, cargo, outline, 2)
    pygame.draw.polygon(sprite, cargo_deep, [(center - 16, 55 + crouch), (center + 17, 51 + crouch), (center + 15, 62 + crouch), (center - 15, 62 + crouch)])
    pygame.draw.rect(sprite, cargo_light, (center - 16, 51 + crouch, 10, 8))
    pygame.draw.rect(sprite, cargo_light, (center + 7, 50 + crouch, 10, 8))
    pygame.draw.rect(sprite, outline, (center + 5, 58 + crouch, 14, 5))
    pygame.draw.rect(sprite, (23, 25, 29), (center + 7, 59 + crouch, 11, 2))

    # A narrow waist transitions into a subtly soft exposed tummy.
    torso = [(center - 12, 32 + crouch), (center - 8, 28 + crouch), (center + 9, 28 + crouch), (center + 13, 34 + crouch), (center + 10, 49 + crouch), (center + 13, 52 + crouch), (center - 13, 52 + crouch), (center - 10, 48 + crouch)]
    _outlined_poly(sprite, torso, skin_shadow, outline, 2)
    top = [(center - 10, 29 + crouch), (center + 9, 29 + crouch), (center + 11, 41 + crouch), (center - 10, 41 + crouch)]
    _outlined_poly(sprite, top, accent, outline, 2)
    pygame.draw.polygon(sprite, _shade(accent, -37), [(center - 9, 37 + crouch), (center + 11, 34 + crouch), (center + 11, 41 + crouch), (center - 10, 41 + crouch)])
    pygame.draw.rect(sprite, _shade(accent, 42), (center - 7, 31 + crouch, 4, 7))
    pygame.draw.rect(sprite, skin, (center - 9, 42 + crouch, 19, 9))
    pygame.draw.rect(sprite, skin_light, (center - 5, 43 + crouch, 9, 3))
    pygame.draw.rect(sprite, skin_shadow, (center + 6, 47 + crouch, 4, 3))
    pygame.draw.rect(sprite, (124, 71, 73), (center, 47 + crouch, 2, 3))

    # Back arm has extra width and rounded shading for the requested softness.
    back_arm = [(center - 10, 31 + crouch), (center - 20, 34 + crouch), (center - 21, 54 + crouch), (center - 14, 58 + crouch), (center - 8, 43 + crouch)]
    _outlined_poly(sprite, back_arm, skin_shadow, outline, 2)
    pygame.draw.rect(sprite, skin, (center - 18, 36 + crouch, 4, 15))
    pygame.draw.rect(sprite, skin_light, (center - 18, 37 + crouch, 2, 9))

    if attacking:
        heavy = state == "heavy"
        reach = 34 if heavy else 29
        arm = [(center + 8, 32 + crouch), (center + 18, 34 + crouch), (center + reach, 26 + crouch), (center + reach + 7, 30 + crouch), (center + 18, 44 + crouch), (center + 9, 42 + crouch)]
        _outlined_poly(sprite, arm, skin, outline, 2)
        pygame.draw.polygon(sprite, skin_light, [(center + 16, 35 + crouch), (center + reach, 28 + crouch), (center + reach + 3, 30 + crouch), (center + 18, 39 + crouch)])
        # Compact R-shaped micro-torch: a short fuel body, side trigger and
        # angled nozzle. Keep the prop small so it reads as a tool, not a grenade.
        torch_x = center + reach + 5
        torch_y = 36 + crouch
        torch_outline = [(torch_x - 4, torch_y + 2), (torch_x - 4, torch_y - 12), (torch_x - 1, torch_y - 16), (torch_x + 3, torch_y - 16), (torch_x + 5, torch_y - 13), (torch_x + 5, torch_y - 9), (torch_x + 3, torch_y - 7), (torch_x + 6, torch_y - 3), (torch_x + 6, torch_y + 2)]
        pygame.draw.polygon(sprite, outline, torch_outline)
        pygame.draw.rect(sprite, (54, 65, 70), (torch_x - 2, torch_y - 10, 5, 11))
        pygame.draw.rect(sprite, (117, 139, 141), (torch_x - 1, torch_y - 9, 3, 9))
        pygame.draw.rect(sprite, (63, 183, 193), (torch_x - 1, torch_y - 7, 3, 3))
        pygame.draw.line(sprite, outline, (torch_x + 1, torch_y - 14), (torch_x + 5, torch_y - 18), 3)
        pygame.draw.line(sprite, (202, 218, 205), (torch_x + 2, torch_y - 15), (torch_x + 5, torch_y - 18), 1)
        pygame.draw.line(sprite, (202, 218, 205), (torch_x + 3, torch_y - 6), (torch_x + 5, torch_y - 3), 1)
        flame = [(torch_x + 3, torch_y - 16), (torch_x + 1, torch_y - 24), (torch_x + 5, torch_y - 30), (torch_x + 9, torch_y - 23), (torch_x + 7, torch_y - 16)]
        pygame.draw.polygon(sprite, (202, 52, 36), flame)
        pygame.draw.polygon(sprite, (255, 116, 37), [(torch_x + 3, torch_y - 17), (torch_x + 3, torch_y - 24), (torch_x + 6, torch_y - 20), (torch_x + 6, torch_y - 17)])
        pygame.draw.rect(sprite, (255, 239, 128), (torch_x + 3, torch_y - 20, 3, 5))
        pygame.draw.rect(sprite, (255, 218, 133), (torch_x + 10, torch_y - 26, 5, 3))
        if state == "air_attack":
            _outlined_line(sprite, (center + 5, 66), (center + 31, 70), cargo_light, 10, outline)
            pygame.draw.rect(sprite, (82, 67, 57), (center + 28, 67, 19, 9))
    elif special:
        # Calling Chief: open stance, whistle fingers and gold energy cue.
        front_arm = [(center + 9, 33), (center + 17, 31), (center + 24, 22), (center + 19, 18), (center + 9, 27)]
        _outlined_poly(sprite, front_arm, skin, outline, 2)
        pygame.draw.rect(sprite, rim, (center + 18, 20, 5, 3))
        for dx, dy in ((29, 14), (35, 10), (37, 18)):
            pygame.draw.rect(sprite, GOLD, (center + dx, dy, 4, 3))
        pygame.draw.lines(sprite, (255, 238, 149), False, [(center + 23, 19), (center + 33, 15), (center + 42, 16)], 2)
    elif refill:
        pygame.draw.rect(sprite, outline, (center - 27, 48, 13, 24))
        pygame.draw.rect(sprite, (183, 189, 185), (center - 24, 50, 8, 20))
        pygame.draw.rect(sprite, (65, 143, 158), (center - 23, 55, 6, 7))
        pygame.draw.rect(sprite, (224, 229, 220), (center - 22, 52, 4, 2))
        pygame.draw.rect(sprite, outline, (center - 22, 44, 5, 7))
        pygame.draw.lines(sprite, outline, False, [(center - 19, 46), (center + 14, 49), (center + 17, 44)], 2)
        pygame.draw.rect(sprite, outline, (center + 13, 41, 9, 15))
        pygame.draw.rect(sprite, (68, 77, 82), (center + 16, 43, 4, 11))
        pygame.draw.rect(sprite, skin, (center + 10, 48, 8, 9))
    else:
        front_arm = [(center + 9, 32 + crouch), (center + 18, 35 + crouch), (center + 18, 54 + crouch), (center + 12, 60 + crouch), (center + 8, 54 + crouch)]
        _outlined_poly(sprite, front_arm, skin, outline, 2)
        pygame.draw.rect(sprite, skin_light, (center + 13, 37 + crouch, 3, 13))
        pygame.draw.rect(sprite, outline, (center + 16, 52 + crouch, 7, 17))
        pygame.draw.rect(sprite, (70, 77, 82), (center + 18, 54 + crouch, 3, 13))
        pygame.draw.rect(sprite, (77, 170, 182), (center + 18, 53 + crouch, 4, 3))

    # High bun, layered brunette hair and expressive face.
    _toned_oval(sprite, (center - 2, 1 + crouch, 18, 17), outline, hair_deep, hair, hair_light)
    pygame.draw.rect(sprite, hair_mid, (center + 4, 3 + crouch, 5, 4))
    _toned_oval(sprite, (center - 13, 10 + crouch, 27, 26), outline, skin_deep, skin, skin_light)
    pygame.draw.polygon(sprite, hair, [(center - 13, 18 + crouch), (center - 10, 10 + crouch), (center + 10, 10 + crouch), (center + 13, 18 + crouch), (center + 9, 17 + crouch), (center + 6, 13 + crouch), (center - 3, 16 + crouch), (center - 9, 25 + crouch)])
    pygame.draw.rect(sprite, hair_deep, (center - 14, 17 + crouch, 5, 16))
    pygame.draw.rect(sprite, hair_mid, (center - 10, 15 + crouch, 3, 12))
    pygame.draw.rect(sprite, hair_light, (center + 7, 12 + crouch, 3, 7))
    pygame.draw.rect(sprite, outline, (center - 5, 21 + crouch, 3, 2))
    pygame.draw.rect(sprite, outline, (center + 4, 21 + crouch, 3, 2))
    pygame.draw.rect(sprite, (255, 240, 221), (center - 4, 28 + crouch, 9, 3))
    pygame.draw.rect(sprite, (187, 77, 81), (center - 2, 31 + crouch, 6, 2))
    if hurt:
        pygame.draw.rect(sprite, (255, 248, 199), (center - 18, 13 + crouch, 3, 15))
        pygame.draw.rect(sprite, (255, 103, 76), (center - 22, 18 + crouch, 3, 7))


def _draw_motion_echo(
    surface: pygame.Surface,
    sprite: pygame.Surface,
    x: float,
    y: float,
    z: float,
    facing: object,
    bottom: int,
    state: str,
    frame: int,
) -> None:
    """Leave one low-alpha directional cel behind high-speed player poses."""

    profiles = {
        "attack_1": (3, 42),
        "attack_2": (4, 50),
        "attack_3": (5, 58),
        "heavy": (5, 54),
        "air_attack": (4, 46),
        "dodge": (4, 52),
        "super": (5, 48),
    }
    spec = profiles.get(state)
    if spec is None:
        return
    offset, alpha = spec
    # Alternate the strength by cel so the echo breathes instead of reading
    # as a static duplicate when a pose holds for multiple ticks.
    alpha = max(18, min(76, alpha + (6 if frame % 2 else -4)))
    echo = sprite.copy()
    echo.set_alpha(alpha)
    direction = _face_sign(facing)
    _blit_grounded(surface, echo, x - direction * offset, y, z, facing, bottom)


def _draw_action_ribbon(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float,
    facing: object,
    state: str,
    bottom: int,
    frame: int,
) -> None:
    """Draw two restrained timing ribbons behind fast authored action cels."""

    specs = {
        "attack_1": (18, 38, (255, 190, 102)),
        "attack_2": (24, 44, (255, 220, 125)),
        "attack_3": (30, 51, (255, 239, 169)),
        "heavy": (28, 48, (255, 171, 91)),
        "air_attack": (26, 44, (154, 235, 255)),
        "dodge": (22, 36, (122, 220, 242)),
        "super": (34, 56, (255, 239, 151)),
    }
    spec = specs.get(state)
    if spec is None:
        return
    reach, lift, color = spec
    direction = _face_sign(facing)
    anchor_y = _i(y - z) - int(bottom) + lift
    phase = int(frame) % 4
    for index in range(2):
        offset = phase * 2 + index * 5
        start = (_i(x) - direction * (reach - offset), anchor_y + index * 5)
        end = (_i(x) - direction * (reach + 14 - offset), anchor_y + 8 + index * 5)
        pygame.draw.line(surface, (51, 36, 43), start, end, 4)
        pygame.draw.line(surface, color, start, end, 1)


def _draw_footfall_ticks(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float,
    facing: object,
    state: str,
    frame: int,
) -> None:
    """Punctuate the twelve-pose gait at the two real heel contacts."""

    if state not in {"walk", "run", "move", "jog"}:
        return
    # Hero walk clips hold each authored key for two 30 Hz ticks.  The old
    # eight-tick loop fired three decorative footfalls per stride and made the
    # marks disagree with the actual left/right heel strikes.  Keep the
    # effect phase-locked to the manifest's twelve-pose gait instead.
    phase = int(frame) % 24
    if phase not in {0, 1, 12, 13}:
        return
    direction = _face_sign(facing)
    ground_y = _i(y - z) + 2
    contact = phase in {0, 12}
    lead = 12 if contact else 8
    rear = -10 if contact else -6
    color = (188, 170, 132) if contact else (124, 111, 101)
    for offset, length in ((lead, 7 if contact else 5), (rear, 5 if contact else 4)):
        start_x = _i(x) + direction * offset
        pygame.draw.line(
            surface,
            (49, 43, 46),
            (start_x - length // 2, ground_y),
            (start_x + length // 2, ground_y),
            3,
        )
        pygame.draw.line(
            surface,
            color,
            (start_x - length // 2, ground_y - 1),
            (start_x + length // 2, ground_y - 1),
            1,
        )


def _walk_bob(frame: int) -> int:
    """Return a one-pixel weight arc without moving the grounded shadow."""

    # Heel strike, compression, passing, and toe-off form a gentle arc.  The
    # 24-step stream gives the new in-between cels their own weight transfer.
    return (0, 0, -1, -1, -2, -2, -3, -2, -2, -1, -1, 0, 0, 0, -1, -1, -2, -2, -3, -2, -2, -1, -1, 0)[int(frame) % 24]


def _draw_walk_followthrough(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float,
    facing: object,
    state: str,
    frame: int,
) -> None:
    """Give the leading hand and shoulder a small counter-swing between keys."""

    if state not in {"walk", "run", "move", "jog"}:
        return
    phase = int(frame) % 24
    if phase not in {3, 4, 5, 15, 16, 17}:
        return
    direction = _face_sign(facing)
    center_x = _i(x) + direction * (11 if phase < 12 else -11)
    shoulder_y = _i(y - z) - 52
    weight = 2 if phase in {4, 16} else 1
    pygame.draw.line(
        surface,
        (104, 82, 84),
        (center_x - direction * 5, shoulder_y + weight),
        (center_x + direction * 3, shoulder_y - 2),
        1,
    )
    if phase in {4, 16}:
        pygame.draw.rect(surface, (184, 129, 101), (center_x + direction * 5, shoulder_y - 4, 2, 2))


def _draw_stride_accents(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float,
    facing: object,
    state: str,
    frame: int,
) -> None:
    """Add a tiny contact puff and passing sweep to make stride beats readable."""

    if state not in {"walk", "run", "move", "jog"}:
        return
    phase = int(frame) % 24
    direction = _face_sign(facing)
    ground_y = _i(y - z) + 2
    if phase in {0, 12}:
        # Two-pixel dust puffs arrive on contact, then disappear before the
        # next authored key; this supports both heroes without obscuring feet.
        side = direction if phase == 0 else -direction
        cx = _i(x) + side * 11
        pygame.draw.line(surface, (110, 94, 90), (cx - 4, ground_y - 1), (cx - 1, ground_y - 3), 1)
        pygame.draw.line(surface, (177, 145, 112), (cx + 1, ground_y - 1), (cx + 5, ground_y - 4), 1)
        pygame.draw.rect(surface, (196, 161, 121), (cx - 7, ground_y - 5, 2, 2))
        pygame.draw.rect(surface, (139, 117, 103), (cx + 7, ground_y - 3, 2, 2))
    elif phase in {6, 18}:
        # Passing phase: a short low sweep implies the leg is moving through
        # the lane while keeping the authored body silhouette untouched.
        cx = _i(x) - direction * 7
        pygame.draw.line(surface, (77, 71, 75), (cx - direction * 5, ground_y), (cx + direction * 4, ground_y), 1)
    elif phase in {3, 9, 15, 21}:
        # The raised foot crosses the lane between the major keys. A single
        # warm pixel pair keeps that arc readable without drawing a second
        # false contact or changing the collision root.
        cx = _i(x) + direction * (3 if phase in {3, 15} else -3)
        pygame.draw.rect(surface, (157, 128, 99), (cx, ground_y - 3, 2, 1))


def _draw_walk_echo(
    surface: pygame.Surface,
    sprite: pygame.Surface,
    x: float,
    y: float,
    z: float,
    facing: object,
    bottom: int,
    state: str,
    frame: int,
) -> None:
    """Carry a low-alpha passing echo through the fastest stride phases."""

    if state not in {"walk", "run", "move", "jog"}:
        return
    phase = int(frame) % 24
    if phase not in {4, 5, 6, 7, 16, 17, 18, 19}:
        return
    direction = _face_sign(facing)
    lead = 4 + ((phase // 2) % 3)
    echo = sprite.copy()
    echo.set_alpha(42 if phase in {4, 16} else 62)
    _blit_grounded(surface, echo, x - direction * lead, y, z, facing, bottom)
    if phase in {6, 18}:
        echo.set_alpha(22)
        _blit_grounded(surface, echo, x - direction * (lead + 4), y, z, facing, bottom)


def draw_player(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float,
    facing: object,
    state: object,
    character: object,
    frame: int,
    player_color: pygame.Color | Sequence[int] | str | None,
    *,
    hit_flash: float = 0.0,
) -> pygame.Rect:
    """Draw Black Dave or Shelly as a large, arcade-readable pixel sprite.

    Fast authored cels get one restrained, direction-aware afterimage.  It is
    drawn beneath the current cel so the silhouette stays readable while
    attacks, dodges and aerial strikes carry visible momentum.
    """

    name = str(character or "black_dave").strip().lower().replace(" ", "_").replace("-", "_")
    state_name = _state_name(state)
    accent_default = (217, 72, 64) if name in {"black_dave", "dave", "blackdave"} else (195, 74, 124)
    accent = _rgb(player_color, accent_default)
    if name in {"black_dave", "dave", "blackdave"} and _ko_preview_enabled() and _ko_preview_sprite() is not None:
        ko = _ko_preview_sprite()
        if ko is not None:
            _shadow(surface, x, y, 43, 9, elevation=z)
            return _blit_grounded(
                surface,
                _hit_flash_sprite(ko, hit_flash),
                x,
                y,
                z,
                facing,
                ko.get_height() - 4,
            )
    authored = sprite_atlas.player_frame(name, state_name, int(frame)) if sprite_atlas is not None else None
    if authored is not None:
        _shadow(
            surface,
            x,
            y,
            51 if name in {"black_dave", "dave", "blackdave"} else 53,
            10,
            elevation=z,
        )
        profile = "dave" if name in {"black_dave", "dave", "blackdave"} else "shelly"
        clean_dave_walk = profile == "dave" and state_name == "walk"
        if clean_dave_walk:
            # The stable walk strip owns Dave's palette, light direction,
            # landmarks and weight arc. Frame-driven embellishments made the
            # same held pose shimmer, so walking uses only the authored pixels
            # plus the intentional combat hit flash.
            rendered = _hit_flash_sprite(authored, hit_flash)
        else:
            rendered = _state_rim_sprite(
                _character_sheen_sprite(
                    _character_emblem_sprite(
                        _hit_flash_sprite(_material_lit_sprite(authored, profile), hit_flash),
                        profile,
                        int(frame),
                    ),
                    profile,
                    int(frame),
                ),
                state_name,
                accent,
            )
            _draw_footfall_ticks(surface, x, y, z, facing, state_name, int(frame))
            _draw_stride_accents(surface, x, y, z, facing, state_name, int(frame))
            _draw_walk_followthrough(surface, x, y, z, facing, state_name, int(frame))
            _draw_walk_echo(surface, rendered, x, y, z, facing, authored.get_height() - 4, state_name, int(frame))
        _draw_action_ribbon(surface, x, y, z, facing, state_name, authored.get_height() - 4, int(frame))
        _draw_motion_echo(surface, rendered, x, y, z, facing, authored.get_height() - 4, state_name, int(frame))
        draw_y = (
            y - _walk_bob(int(frame))
            if not clean_dave_walk and state_name in {"walk", "run", "move", "jog"}
            else y
        )
        return _blit_grounded(
            surface,
            rendered,
            x,
            draw_y,
            z,
            facing,
            authored.get_height() - 4,
        )

    _shadow(
        surface,
        x,
        y,
        43 if name in {"black_dave", "dave", "blackdave"} else 47,
        9,
        elevation=z,
    )
    sprite = pygame.Surface((104, 96), pygame.SRCALPHA)
    if name in {"shelly", "shellie"}:
        _draw_shelly(sprite, state_name, int(frame), accent)
    else:
        _draw_dave(sprite, state_name, int(frame), accent)
    profile = "shelly" if name in {"shelly", "shellie"} else "dave"
    rendered = _state_rim_sprite(
        _character_sheen_sprite(
            _character_emblem_sprite(
                _hit_flash_sprite(
                    _material_lit_sprite(sprite, profile, cache=False),
                    hit_flash,
                    cache=False,
                ),
                profile,
                int(frame),
            ),
            profile,
            int(frame),
        ),
        state_name,
        accent,
    )
    _draw_footfall_ticks(surface, x, y, z, facing, state_name, int(frame))
    _draw_stride_accents(surface, x, y, z, facing, state_name, int(frame))
    _draw_walk_followthrough(surface, x, y, z, facing, state_name, int(frame))
    _draw_walk_echo(surface, rendered, x, y, z, facing, 90, state_name, int(frame))
    _draw_action_ribbon(surface, x, y, z, facing, state_name, 90, int(frame))
    _draw_motion_echo(surface, rendered, x, y, z, facing, 90, state_name, int(frame))
    draw_y = y - _walk_bob(int(frame)) if state_name in {"walk", "run", "move", "jog"} else y
    return _blit_grounded(surface, rendered, x, draw_y, z, facing, 90)


def draw_fist_flames(
    surface: pygame.Surface,
    x: float,
    y: float,
    facing: object = 1,
    frame: int = 0,
    *,
    z: float = 0.0,
    state: object = "idle",
    sprite_tick: int | None = None,
) -> pygame.Rect:
    """Attach persistent pixel fire to Dave's fists on the exact rendered cel.

    This is intentionally an overlay rather than a replacement player strip:
    Dave keeps his full authored combat poses while the 60 Hz simulation stays
    untouched and ignition remains obvious between individual punches.  The
    anchor conversion mirrors :func:`draw_player`, including facing and jump
    height, so idle, locomotion, attacks, hurt and down poses cannot leave the
    fire floating at a fixed world offset.
    """

    direction = _face_sign(facing)
    phase = max(0, int(frame))
    pose_tick = phase if sprite_tick is None else max(0, int(sprite_tick))
    state_name = _state_name(state)
    centres: tuple[tuple[int, int], ...] = ()
    if sprite_atlas is not None:
        authored = sprite_atlas.player_frame("black_dave", state_name, pose_tick)
        anchors = sprite_atlas.player_fist_anchors("black_dave", state_name, pose_tick)
        if authored is not None and anchors:
            width = authored.get_width()
            left = _i(x) - width // 2
            top = _i(y - z) - (authored.get_height() - 4)
            centres = tuple(
                (
                    left + (anchor_x if direction > 0 else width - 1 - anchor_x),
                    top + anchor_y,
                )
                for anchor_x, anchor_y in anchors
            )
    if not centres:
        # Safe fallback for direct-module experiments where the atlas is not
        # importable. Runtime builds use the pose-specific branch above.
        centres = (
            (_i(x + direction * 26), _i(y - z - 46)),
            (_i(x + direction * 14), _i(y - z - 35)),
        )

    striking = state_name.startswith("attack_") or state_name in {
        "light",
        "heavy",
        "air_attack",
        "super",
    }
    rects: list[pygame.Rect] = []
    for index, (cx, cy) in enumerate(centres):
        flicker = ((phase * 3 + index * 5) % 7) - 3
        sway = -1 if (phase + index) % 2 else 1
        if striking:
            # Three nested, asymmetric ribbons read as a punch carrying fire,
            # rather than the old small triangle pasted behind the glove.
            trail = 24 + index * 4 + (phase % 3) * 2
            trail_outer = [
                (cx + direction * 8, cy - 8),
                (cx + direction * 13, cy - 2),
                (cx + direction * 8, cy + 8),
                (cx - direction * (trail - 5), cy + 10),
                (cx - direction * (trail + 16), cy + 3 + sway),
                (cx - direction * (trail + 7), cy - 3),
                (cx - direction * (trail + 19), cy - 9 - sway),
                (cx - direction * (trail - 2), cy - 8),
            ]
            trail_mid = [
                (cx + direction * 9, cy - 5),
                (cx + direction * 12, cy),
                (cx + direction * 8, cy + 5),
                (cx - direction * (trail + 8), cy + 5),
                (cx - direction * (trail - 1), cy),
                (cx - direction * (trail + 11), cy - 5),
            ]
            trail_inner = [
                (cx + direction * 8, cy - 2),
                (cx + direction * 11, cy),
                (cx + direction * 7, cy + 2),
                (cx - direction * max(8, trail - 2), cy + 2),
                (cx - direction * (trail + 6), cy),
                (cx - direction * max(8, trail - 2), cy - 2),
            ]
            rects.append(pygame.draw.polygon(surface, (62, 25, 32), [(px + direction * 2, py + 2) for px, py in trail_outer]))
            rects.append(pygame.draw.polygon(surface, (188, 43, 26), trail_outer))
            rects.append(pygame.draw.polygon(surface, (255, 101, 24), trail_mid))
            rects.append(pygame.draw.polygon(surface, (255, 204, 70), trail_inner))
            rects.append(
                pygame.draw.line(
                    surface,
                    (255, 248, 185),
                    (cx - direction * max(7, trail - 7), cy - 1),
                    (cx + direction * 8, cy - 1),
                    2,
                )
            )
            for spark_index, (distance, dy) in enumerate(((trail + 14, -13), (trail + 3, 13), (trail // 2, -16))):
                spark_x = cx - direction * distance
                spark_y = cy + dy + ((phase + spark_index + index) % 3) - 1
                size = 3 if spark_index == 0 else 2
                spark = pygame.Rect(spark_x - size // 2, spark_y - size // 2, size, size)
                pygame.draw.rect(surface, (255, 241, 139) if spark_index != 1 else (255, 126, 30), spark)
                rects.append(spark)

        flame_height = 24 + ((phase + index * 2) % 4) + max(0, -flicker)
        outer = [
            (cx - 12, cy + 8),
            (cx - 11, cy - 3),
            (cx - 7, cy - 11 - sway),
            (cx - 3, cy - 7),
            (cx + sway, cy - flame_height),
            (cx + 4, cy - 12 + flicker),
            (cx + 8, cy - 17 - sway),
            (cx + 9, cy - 5),
            (cx + 12, cy + 8),
        ]
        shadow = [(px + direction * 2, py + 2) for px, py in outer]
        rects.append(pygame.draw.polygon(surface, (56, 23, 31), shadow))
        rects.append(pygame.draw.polygon(surface, (185, 42, 26), outer))
        middle = [
            (cx - 8, cy + 7),
            (cx - 7, cy - 3),
            (cx - 3, cy - 11 + sway),
            (cx, cy - 6),
            (cx + 3, cy - 18 - flicker),
            (cx + 7, cy - 5),
            (cx + 8, cy + 7),
        ]
        rects.append(pygame.draw.polygon(surface, (255, 93, 23), middle))
        inner = [
            (cx - 5, cy + 6),
            (cx - 4, cy - 3),
            (cx - 1, cy - 8 - sway),
            (cx + 2, cy - 4),
            (cx + 4, cy - 12 + flicker),
            (cx + 6, cy + 6),
        ]
        rects.append(pygame.draw.polygon(surface, (255, 174, 40), inner))
        core = [(cx - 2, cy + 5), (cx - 2, cy - 2), (cx + 1, cy - 7), (cx + 3, cy + 5)]
        rects.append(pygame.draw.polygon(surface, (255, 244, 139), core))
        rects.append(pygame.draw.rect(surface, (255, 255, 224), (cx - 1, cy, 3, 5)))
        # A glowing cuff grounds each silhouette directly on its authored fist.
        rects.append(pygame.draw.ellipse(surface, (83, 28, 29), (cx - 11, cy + 3, 22, 9)))
        rects.append(pygame.draw.arc(surface, (255, 195, 58), (cx - 9, cy + 3, 18, 7), math.pi, math.tau, 2))
        # Broken heat contours and three independent ember paths create motion
        # even while Dave holds an idle pose.
        heat_shift = (phase + index * 2) % 3
        for heat_index, inflate in enumerate((0, 7)):
            heat_box = pygame.Rect(cx - 15 - inflate // 2, cy - 25 - inflate, 30 + inflate, 34 + inflate)
            rects.append(
                pygame.draw.arc(
                    surface,
                    (245, 112 + heat_index * 35, 64),
                    heat_box,
                    3.65 + heat_shift * 0.08,
                    4.45 + heat_shift * 0.08,
                    1,
                )
            )
        for ember_index, (dx, dy, size) in enumerate(((-15, -12, 3), (12, -20, 2), (-6, -30, 2))):
            drift = sway * (1 + ember_index)
            ember = pygame.Rect(cx + dx + drift, cy + dy + (phase + ember_index) % 4, size, size)
            pygame.draw.rect(surface, (255, 224, 99) if ember_index != 1 else (255, 91, 25), ember)
            rects.append(ember)
    return rects[0].unionall(rects[1:]).inflate(6, 6)


def draw_comic_speech_bubble(
    surface: pygame.Surface,
    x: float,
    y: float,
    width: int,
    height: int = 28,
    facing: object = -1,
) -> pygame.Rect:
    """Draw a chunky comic bubble; callers render their own text inside it."""

    bubble_width = max(74, int(width))
    bubble_height = max(22, int(height))
    rect = pygame.Rect(_i(x - bubble_width / 2), _i(y - bubble_height), bubble_width, bubble_height)
    direction = 1 if float(facing) >= 0 else -1
    tail_x = rect.centerx - direction * max(10, bubble_width // 5)
    tail = [(tail_x - 7, rect.bottom - 2), (tail_x + 7, rect.bottom - 2), (tail_x + direction * 14, rect.bottom + 12)]
    outline = (32, 32, 43)
    shadow_rect = rect.move(2, 3)
    pygame.draw.rect(surface, outline, shadow_rect, border_radius=5)
    pygame.draw.polygon(surface, outline, [(px + 2, py + 3) for px, py in tail])
    pygame.draw.rect(surface, (255, 250, 220), rect, border_radius=5)
    pygame.draw.rect(surface, (46, 54, 75), rect, 2, border_radius=5)
    pygame.draw.polygon(surface, (255, 250, 220), tail)
    pygame.draw.lines(surface, (46, 54, 75), True, tail, 2)
    pygame.draw.rect(surface, (255, 205, 73), (rect.x + 5, rect.y + 4, 3, 3))
    pygame.draw.rect(surface, (255, 205, 73), (rect.right - 8, rect.bottom - 7, 3, 3))
    return rect.union(shadow_rect).union(pygame.Rect(min(point[0] for point in tail), min(point[1] for point in tail), max(point[0] for point in tail) - min(point[0] for point in tail) + 1, max(point[1] for point in tail) - min(point[1] for point in tail) + 1))


def draw_chief(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float = 0,
    facing: object = 1,
    state: object = "idle",
    frame: int = 0,
) -> pygame.Rect:
    """Draw Chief with a muscular pit-bull silhouette and jeweled collar."""

    state_name = _state_name(state)
    authored = sprite_atlas.chief_frame(state_name, int(frame)) if sprite_atlas is not None else None
    if authored is not None:
        attacking = state_name in {"attack", "bite", "super", "vicious", "charge", "frenzy", "maul"}
        _shadow(surface, x, y, 55 if attacking else 49, 8, elevation=z)
        return _blit_grounded(
            surface,
            _material_lit_sprite(authored, "fur"),
            x,
            y,
            z,
            facing,
            authored.get_height() - 4,
        )

    attacking = state_name in {"attack", "bite", "super", "vicious", "charge", "frenzy", "maul"}
    super_mode = state_name in {"super", "vicious", "frenzy"}
    running = state_name in {"run", "walk", "charge", "super", "frenzy", "follow"}
    _shadow(surface, x, y, 48 if attacking else 41, 8, elevation=z)
    sprite = pygame.Surface((82, 62), pygame.SRCALPHA)
    outline = (37, 29, 31)
    fur_deep = (93, 57, 45)
    fur_shadow = (139, 86, 57)
    fur = (190, 129, 76)
    fur_light = (229, 174, 105)
    rim = (250, 203, 132)
    body_x = 13 if attacking else 19
    body_y = 23 if attacking else 25
    body_w = 42 if attacking else 36
    step = 4 if running and (int(frame) // 2) % 2 else -2 if running else 0

    if super_mode:
        # Gold/white speed streaks echo the collar and make frenzy unmistakable.
        pygame.draw.rect(sprite, (255, 230, 119), (2, 17, 17, 3))
        pygame.draw.rect(sprite, (255, 249, 207), (6, 24, 12, 2))
        pygame.draw.rect(sprite, (242, 159, 58), (1, 31, 14, 3))

    # Tail, barrel chest and visible shoulder muscle groups.
    _outlined_line(sprite, (body_x + 3, body_y + 7), (body_x - 12, body_y - (6 if running else 2)), fur_shadow, 5, outline)
    _toned_oval(sprite, (body_x, body_y, body_w, 24), outline, fur_deep, fur, fur_light)
    pygame.draw.polygon(sprite, fur_shadow, [(body_x + 2, body_y + 13), (body_x + body_w - 3, body_y + 10), (body_x + body_w - 6, body_y + 23), (body_x + 6, body_y + 23)])
    pygame.draw.rect(sprite, fur_light, (body_x + 8, body_y + 4, 14, 4))
    pygame.draw.rect(sprite, rim, (body_x + 10, body_y + 3, 8, 2))

    # Short, powerful legs with differently phased paws.
    leg_positions = (body_x + 7 + step, body_x + body_w - 13 - step)
    for index, leg_x in enumerate(leg_positions):
        pygame.draw.rect(sprite, outline, (leg_x, body_y + 17, 10, 18))
        pygame.draw.rect(sprite, fur_shadow if index == 0 else fur, (leg_x + 2, body_y + 18, 6, 15))
        pygame.draw.rect(sprite, fur_light, (leg_x + 1, body_y + 30, 11, 5))
        pygame.draw.rect(sprite, outline, (leg_x, body_y + 34, 13, 3))

    head_x = body_x + body_w - 1
    head_y = 22 if attacking else 23
    _toned_oval(sprite, (head_x - 9, head_y - 9, 25, 26), outline, fur_deep, fur, fur_light)
    # Small folded ears atop a very broad head.
    _outlined_poly(sprite, [(head_x - 7, head_y - 7), (head_x - 5, head_y - 16), (head_x + 1, head_y - 8)], fur_shadow, outline, 2)
    _outlined_poly(sprite, [(head_x + 7, head_y - 7), (head_x + 13, head_y - 14), (head_x + 13, head_y - 3)], fur_shadow, outline, 2)
    pygame.draw.rect(sprite, rim, (head_x - 4, head_y - 5, 7, 2))

    muzzle_w = 17 if attacking else 13
    _toned_oval(sprite, (head_x + 5, head_y + 1, muzzle_w, 13), outline, fur_deep, fur_light, rim)
    pygame.draw.rect(sprite, outline, (head_x + muzzle_w + 1, head_y + 4, 5, 5))
    eye_color = (255, 84, 58) if super_mode else (31, 28, 30)
    pygame.draw.rect(sprite, eye_color, (head_x + 5, head_y - 2, 3, 3))
    pygame.draw.rect(sprite, (255, 230, 173), (head_x + 6, head_y - 2, 1, 1))
    if attacking:
        pygame.draw.polygon(sprite, outline, [(head_x + 8, head_y + 10), (head_x + 24, head_y + 9), (head_x + 20, head_y + 18), (head_x + 10, head_y + 17)])
        for tooth_x in (head_x + 11, head_x + 17, head_x + 21):
            pygame.draw.polygon(sprite, (255, 246, 220), [(tooth_x, head_y + 10), (tooth_x + 3, head_y + 10), (tooth_x + 1, head_y + 15)])
        pygame.draw.rect(sprite, (206, 66, 65), (head_x + 13, head_y + 15, 8, 2))

    # Oversized Cuban links alternate orientation, with diamonds and medallion.
    collar_y = head_y + 8
    for index, px in enumerate(range(head_x - 8, head_x + 10, 4)):
        pygame.draw.rect(sprite, outline, (px - 1, collar_y - 1 + index % 2, 7, 6))
        pygame.draw.rect(sprite, GOLD if index % 2 else (255, 219, 93), (px, collar_y + index % 2, 5, 4))
        if index % 2 == 0:
            pygame.draw.rect(sprite, (245, 253, 255), (px + 2, collar_y, 2, 2))
    pygame.draw.rect(sprite, outline, (head_x - 1, collar_y + 4, 10, 10))
    pygame.draw.polygon(sprite, GOLD, [(head_x + 4, collar_y + 5), (head_x + 8, collar_y + 9), (head_x + 4, collar_y + 13), (head_x, collar_y + 9)])
    pygame.draw.rect(sprite, (239, 252, 255), (head_x + 3, collar_y + 7, 3, 3))
    pygame.draw.rect(sprite, (119, 231, 255), (head_x + 5, collar_y + 10, 2, 2))
    return _blit_grounded(surface, _material_lit_sprite(sprite, "fur", cache=False), x, y, z, facing, 58)


def draw_enemy(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float = 0,
    facing: object = -1,
    state: object = "idle",
    kind: object = "stick",
    frame: int = 0,
    tint: pygame.Color | Sequence[int] | str | None = None,
    *,
    hit_flash: float = 0.0,
) -> pygame.Rect:
    """Draw a distinct, shaded silhouette for each configurable archetype."""

    enemy_kind = str(kind or "stick").strip().lower().replace("-", "_").replace(" ", "_")
    if enemy_kind in {"shopping_cart", "cart_pusher"}:
        enemy_kind = "cart"
    elif enemy_kind in {"makeshift_whip", "cord"}:
        enemy_kind = "whip"
    elif enemy_kind in {"broken_pipe", "thrower"}:
        enemy_kind = "pipe"
    security = enemy_kind in {"security", "security_guard", "guard"}
    state_name = _state_name(state)
    # Security guards deliberately reuse the authored sixteen-pose stick
    # motion strip. Their uniform overlay makes the role readable without
    # introducing a low-frame-count exception to the animation-floor rule.
    authored_kind = "stick" if security else enemy_kind
    authored = sprite_atlas.enemy_frame(authored_kind, state_name, int(frame)) if sprite_atlas is not None else None
    if authored is not None:
        _shadow(surface, x, y, 67 if enemy_kind == "cart" else 47, 9, elevation=z)
        sprite = _security_uniform_frame(authored, state_name) if security else authored
        profile = "security_uniform" if security else "enemy_cloth"
        rendered = _hit_flash_sprite(_material_lit_sprite(sprite, profile), hit_flash)
        return _blit_grounded(
            surface,
            rendered,
            x,
            y,
            z,
            facing,
            authored.get_height() - 4,
        )

    attacking = state_name in {"attack", "swing", "throw", "charge", "heavy", "windup"}
    moving = state_name in {"walk", "run", "charge", "chase", "recovery"}
    hurt = state_name in {"hurt", "hitstun"}
    downed = state_name in {"down", "dead"}
    palette = {
        "stick": ((91, 55, 43), (142, 87, 58), (194, 135, 88), (225, 169, 111), (100, 74, 59), (66, 46, 39)),
        "cart": ((126, 74, 56), (176, 114, 80), (218, 163, 117), (244, 198, 148), (72, 95, 91), (61, 48, 41)),
        "whip": ((76, 45, 42), (112, 67, 60), (151, 96, 76), (190, 130, 97), (115, 72, 105), (51, 39, 39)),
        "pipe": ((103, 65, 49), (146, 93, 66), (190, 140, 99), (224, 177, 125), (67, 87, 110), (68, 45, 39)),
        "security": ((63, 43, 36), (104, 72, 56), (154, 108, 78), (211, 159, 112), (27, 47, 91), (31, 29, 34)),
    }
    skin_deep, skin_shadow, skin, skin_light, clothes_default, hair = palette.get(enemy_kind, palette["stick"])
    clothes = _rgb(tint, clothes_default)
    clothes_deep = _shade(clothes, -42)
    clothes_light = _shade(clothes, 35)
    outline = (33, 27, 30)
    _shadow(surface, x, y, 57 if enemy_kind == "cart" else 40, 9, elevation=z)
    sprite = pygame.Surface((128, 94), pygame.SRCALPHA)
    center = 50 if enemy_kind == "cart" else 55
    step = 5 if moving and (int(frame) // 2) % 2 else -3 if moving else 0

    if downed:
        pygame.draw.ellipse(sprite, outline, (13, 73, 73, 14))
        pygame.draw.rect(sprite, clothes_deep, (18, 70, 45, 12))
        pygame.draw.rect(sprite, clothes, (22, 68, 42, 10))
        _toned_oval(sprite, (63, 63, 22, 21), outline, skin_deep, skin, skin_light)
        pygame.draw.rect(sprite, hair, (67, 62, 15, 6))
        profile = "security_uniform" if security else "enemy_cloth"
        rendered = _hit_flash_sprite(
            _material_lit_sprite(sprite, profile, cache=False),
            hit_flash,
            cache=False,
        )
        return _blit_grounded(surface, rendered, x, y, z, facing, 89)

    # Uneven gait and damaged boots create a deliberately unstable stance.
    pygame.draw.rect(sprite, outline, (center - 13 + step, 58, 12, 29))
    pygame.draw.rect(sprite, (47, 46, 45), (center - 10 + step, 60, 7, 24))
    pygame.draw.rect(sprite, outline, (center + 2 - step, 57, 12, 30))
    pygame.draw.rect(sprite, (57, 53, 49), (center + 4 - step, 59, 7, 25))
    pygame.draw.rect(sprite, (103, 74, 53), (center - 17 + step, 82, 17, 7))
    pygame.draw.rect(sprite, outline, (center - 18 + step, 87, 19, 3))
    pygame.draw.rect(sprite, (92, 67, 51), (center + 1 - step, 82, 18, 7))
    pygame.draw.rect(sprite, outline, (center, 87, 20, 3))

    torso = [(center - 15, 34), (center - 8, 29), (center + 10, 31), (center + 16, 42), (center + 12, 64), (center - 12, 65), (center - 18, 51)]
    _outlined_poly(sprite, torso, clothes, outline, 2)
    pygame.draw.polygon(sprite, clothes_deep, [(center - 15, 50), (center + 14, 43), (center + 12, 63), (center - 12, 64)])
    pygame.draw.rect(sprite, clothes_light, (center - 10, 35, 5, 13))
    # Layered tears, safety pin and stitched patch are tiny but high contrast.
    pygame.draw.rect(sprite, _shade(clothes, 50), (center - 10, 51, 10, 8))
    pygame.draw.rect(sprite, outline, (center - 8, 53, 6, 2))
    pygame.draw.line(sprite, (213, 211, 186), (center + 5, 42), (center + 11, 48), 1)
    pygame.draw.line(sprite, (213, 211, 186), (center + 11, 42), (center + 5, 48), 1)

    # Slumped back arm and hand.
    _outlined_poly(sprite, [(center - 12, 35), (center - 21, 40), (center - 22, 62), (center - 15, 67), (center - 9, 48)], skin_shadow, outline, 2)
    pygame.draw.rect(sprite, skin, (center - 19, 42, 3, 14))
    _toned_oval(sprite, (center - 23, 58, 12, 13), outline, skin_deep, skin, skin_light)

    # Head is larger and more expressive than before, with asymmetrical hair.
    _toned_oval(sprite, (center - 13, 8, 27, 28), outline, skin_deep, skin, skin_light)
    pygame.draw.polygon(sprite, hair, [(center - 14, 17), (center - 11, 7), (center - 5, 5), (center - 3, 10), (center + 2, 4), (center + 6, 10), (center + 13, 8), (center + 14, 18)])
    pygame.draw.rect(sprite, _shade(hair, 27), (center - 8, 10, 4, 7))
    pygame.draw.rect(sprite, outline, (center - 6, 20, 3, 3))
    pygame.draw.rect(sprite, outline, (center + 4, 19, 3, 3))
    pygame.draw.rect(sprite, skin_deep, (center - 4, 27, 11, 3))
    pygame.draw.rect(sprite, (230, 211, 174), (center + 2, 27, 3, 2))

    # Weapon arm and prop each establish a unique attack silhouette.
    if enemy_kind == "cart":
        _outlined_line(sprite, (center + 9, 40), (center + 24, 55), skin, 8, outline)
        cart_x = center + 20
        cart_top = 49 if attacking else 53
        pygame.draw.line(sprite, outline, (center + 13, 43), (cart_x + 7, cart_top), 6)
        pygame.draw.line(sprite, (174, 183, 181), (center + 13, 43), (cart_x + 7, cart_top), 3)
        pygame.draw.polygon(sprite, outline, [(cart_x + 4, cart_top), (cart_x + 45, cart_top + 3), (cart_x + 38, 79), (cart_x + 12, 79)])
        pygame.draw.polygon(sprite, (108, 121, 123), [(cart_x + 7, cart_top + 3), (cart_x + 41, cart_top + 6), (cart_x + 35, 75), (cart_x + 14, 75)])
        for py in range(cart_top + 8, 74, 6):
            pygame.draw.line(sprite, (177, 187, 184), (cart_x + 10, py), (cart_x + 39, py + 1), 1)
        pygame.draw.rect(sprite, (137, 74, 45), (cart_x + 15, cart_top + 9, 10, 12))
        pygame.draw.polygon(sprite, (74, 111, 93), [(cart_x + 25, cart_top + 8), (cart_x + 36, cart_top + 12), (cart_x + 31, cart_top + 22)])
        for wheel_x in (cart_x + 11, cart_x + 34):
            pygame.draw.ellipse(sprite, outline, (wheel_x, 75, 10, 11))
            pygame.draw.ellipse(sprite, (119, 125, 124), (wheel_x + 3, 78, 4, 5))
        if attacking:
            pygame.draw.rect(sprite, (255, 230, 137), (cart_x + 47, cart_top + 7, 5, 3))
            pygame.draw.rect(sprite, (255, 112, 67), (cart_x + 52, cart_top + 4, 3, 8))
    elif enemy_kind == "whip":
        _outlined_poly(sprite, [(center + 10, 36), (center + 20, 40), (center + 25, 53), (center + 18, 58), (center + 9, 47)], skin, outline, 2)
        hand = (center + 21, 51)
        pygame.draw.rect(sprite, outline, (hand[0] - 2, hand[1] - 3, 10, 7))
        pygame.draw.rect(sprite, (98, 52, 38), (hand[0], hand[1] - 1, 7, 3))
        points = [hand, (center + 37, 34 if attacking else 57), (center + 45, 12 if attacking else 68), (center + 56, 24 if attacking else 73)]
        pygame.draw.lines(sprite, outline, False, points, 5)
        pygame.draw.lines(sprite, (126, 77, 52), False, points, 2)
        pygame.draw.rect(sprite, (213, 168, 102), (points[-1][0] - 2, points[-1][1] - 2, 5, 5))
    elif enemy_kind == "pipe":
        arm_end = (center + 24, 27 if attacking else 51)
        _outlined_line(sprite, (center + 10, 39), arm_end, skin, 8, outline)
        pipe_end = (center + 43, 12 if attacking else 36)
        _outlined_line(sprite, arm_end, pipe_end, (125, 139, 143), 5, outline)
        pygame.draw.rect(sprite, (197, 207, 201), (pipe_end[0] - 4, pipe_end[1] - 3, 9, 3))
        pygame.draw.rect(sprite, (165, 75, 54), (pipe_end[0] + 1, pipe_end[1], 5, 3))
    else:
        arm_end = (center + 21, 48)
        _outlined_line(sprite, (center + 10, 38), arm_end, skin, 8, outline)
        stick_end = (center + 42, 10 if attacking else 31)
        _outlined_line(sprite, arm_end, stick_end, (113, 72, 43), 5, outline)
        pygame.draw.rect(sprite, (174, 116, 61), (stick_end[0] - 3, stick_end[1] - 4, 7, 9))

    if hurt:
        pygame.draw.rect(sprite, (255, 244, 187), (center - 20, 13, 3, 20))
        pygame.draw.rect(sprite, (255, 92, 69), (center - 25, 19, 4, 9))
    profile = "security_uniform" if security else "enemy_cloth"
    rendered = _hit_flash_sprite(
        _material_lit_sprite(sprite, profile, cache=False),
        hit_flash,
        cache=False,
    )
    return _blit_grounded(surface, rendered, x, y, z, facing, 90)


def draw_boss(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float = 0,
    facing: object = -1,
    state: object = "idle",
    frame: int = 0,
    *,
    hit_flash: float = 0.0,
) -> pygame.Rect:
    """Draw Couch with boss-scale mass, personality and readable weapons."""

    state_name = _state_name(state)
    authored = sprite_atlas.boss_frame(state_name, int(frame)) if sprite_atlas is not None else None
    if authored is not None:
        _shadow(surface, x, y, 82, 12, elevation=z)
        rendered = _hit_flash_sprite(_material_lit_sprite(authored, "denim"), hit_flash)
        return _blit_grounded(
            surface,
            rendered,
            x,
            y,
            z,
            facing,
            authored.get_height() - 4,
        )

    laughing = state_name in {"idle", "laugh", "taunt"} and ((int(frame) // 3) % 4 in {1, 2} or state_name == "laugh")
    pump = state_name in {"pump_attack", "special", "pump", "charge"}
    stick_attack = state_name in {"attack", "swing", "heavy", "stick", "windup"}
    attacking = pump or stick_attack
    hurt = state_name in {"hurt", "hitstun"}
    downed = state_name in {"down", "dead"}
    _shadow(surface, x, y, 68, 11, elevation=z)
    sprite = pygame.Surface((136, 106), pygame.SRCALPHA)
    center = 62
    outline = (38, 27, 31)
    skin_deep = (102, 58, 48)
    skin_shadow = (145, 86, 59)
    skin = (190, 126, 76)
    skin_light = (229, 164, 100)
    rim = (252, 202, 126)
    blue_deep = (21, 47, 94)
    blue = (38, 88, 169)
    blue_mid = (58, 122, 211)
    blue_light = (99, 164, 235)
    hair_deep = (45, 30, 29)
    hair = (70, 43, 35)
    hair_light = (121, 70, 45)

    if downed:
        pygame.draw.ellipse(sprite, outline, (12, 79, 108, 18))
        pygame.draw.rect(sprite, blue_deep, (24, 74, 66, 17))
        pygame.draw.rect(sprite, blue, (29, 71, 62, 13))
        _toned_oval(sprite, (91, 66, 30, 28), outline, skin_deep, skin, skin_light)
        for ox, oy in ((96, 65), (103, 62), (112, 66), (117, 72)):
            _pixel_disc(sprite, hair, (ox, oy), 4)
        rendered = _hit_flash_sprite(
            _material_lit_sprite(sprite, "denim", cache=False),
            hit_flash,
            cache=False,
        )
        return _blit_grounded(surface, rendered, x, y, z, facing, 99)

    # Short legs and oversized shoes support the broad upper silhouette.
    pygame.draw.rect(sprite, outline, (center - 22, 72, 18, 25))
    pygame.draw.rect(sprite, blue_deep, (center - 19, 73, 13, 21))
    pygame.draw.rect(sprite, blue, (center - 15, 74, 8, 18))
    pygame.draw.rect(sprite, outline, (center + 5, 72, 18, 25))
    pygame.draw.rect(sprite, blue, (center + 8, 73, 12, 21))
    pygame.draw.rect(sprite, blue_light, (center + 9, 74, 4, 14))
    for shoe_x in (center - 29, center + 1):
        pygame.draw.rect(sprite, outline, (shoe_x, 91, 29, 10))
        pygame.draw.rect(sprite, (226, 228, 219), (shoe_x + 3, 92, 25, 6))
        pygame.draw.rect(sprite, (99, 148, 216), (shoe_x + 7, 93, 10, 3))
        pygame.draw.rect(sprite, outline, (shoe_x + 1, 98, 29, 3))

    # Back arm appears behind the torso and has a strong rounded forearm.
    _outlined_poly(sprite, [(center - 24, 39), (center - 36, 45), (center - 39, 69), (center - 28, 76), (center - 20, 57)], skin_shadow, outline, 3)
    pygame.draw.rect(sprite, skin, (center - 34, 47, 5, 16))
    pygame.draw.rect(sprite, rim, (center - 34, 48, 2, 11))
    _toned_oval(sprite, (center - 40, 65, 17, 16), outline, skin_deep, skin, skin_light)

    # The jumpsuit is separated into shadow, base, highlight and piping planes.
    body = [(center - 27, 34), (center - 17, 28), (center + 18, 29), (center + 29, 39), (center + 34, 68), (center + 23, 79), (center - 24, 79), (center - 35, 68)]
    _outlined_poly(sprite, body, blue, outline, 3)
    pygame.draw.polygon(sprite, blue_deep, [(center - 32, 55), (center + 30, 48), (center + 33, 68), (center + 22, 78), (center - 23, 78), (center - 34, 68)])
    pygame.draw.polygon(sprite, blue_mid, [(center - 24, 35), (center - 11, 30), (center - 7, 67), (center - 25, 68)])
    pygame.draw.rect(sprite, blue_light, (center - 19, 37, 5, 24))
    pygame.draw.rect(sprite, (225, 230, 232), (center - 1, 31, 4, 38))
    pygame.draw.rect(sprite, (123, 185, 240), (center + 14, 34, 5, 21))

    # Open jacket and waistband reveal shaded caramel midriff folds.
    pygame.draw.polygon(sprite, skin_shadow, [(center - 19, 53), (center + 21, 52), (center + 25, 66), (center + 17, 72), (center - 18, 71), (center - 25, 64)])
    pygame.draw.rect(sprite, skin, (center - 17, 54, 37, 12))
    pygame.draw.rect(sprite, skin_light, (center - 11, 55, 19, 4))
    pygame.draw.rect(sprite, skin_deep, (center + 13, 60, 7, 4))
    pygame.draw.rect(sprite, (106, 61, 51), (center, 62, 3, 3))
    pygame.draw.rect(sprite, blue_deep, (center - 25, 68, 51, 8))
    pygame.draw.rect(sprite, blue_light, (center - 19, 69, 37, 3))

    # Front arm changes from planted fist to high, readable weapon arcs.
    if attacking:
        shoulder = (center + 22, 39)
        hand = (center + 36, 55)
        _outlined_line(sprite, shoulder, hand, skin, 11, outline)
        _toned_oval(sprite, (hand[0] - 6, hand[1] - 6, 16, 16), outline, skin_deep, skin, skin_light)
        if pump:
            tip = (center + 60, 27 if int(frame) % 2 else 39)
            _outlined_line(sprite, hand, tip, (128, 142, 146), 6, outline)
            pygame.draw.rect(sprite, outline, (tip[0] - 8, tip[1] - 5, 18, 8))
            pygame.draw.rect(sprite, (49, 54, 61), (tip[0] - 6, tip[1] - 3, 14, 4))
            pygame.draw.rect(sprite, (207, 65, 56), (hand[0] - 2, hand[1] - 8, 7, 12))
            pygame.draw.rect(sprite, (235, 113, 72), (hand[0], hand[1] - 6, 3, 7))
            pygame.draw.rect(sprite, (255, 230, 151), (tip[0] + 12, tip[1] - 2, 5, 3))
        else:
            tip = (center + 53, 10 if int(frame) % 2 else 23)
            _outlined_line(sprite, hand, tip, (112, 70, 40), 6, outline)
            pygame.draw.rect(sprite, (170, 110, 57), (tip[0] - 4, tip[1] - 5, 9, 11))
            pygame.draw.rect(sprite, (226, 169, 94), (tip[0] - 2, tip[1] - 3, 3, 5))
            pygame.draw.rect(sprite, (255, 102, 68), (tip[0] + 7, tip[1] - 3, 4, 10))
    else:
        front_arm = [(center + 20, 38), (center + 31, 44), (center + 32, 67), (center + 24, 75), (center + 17, 67)]
        _outlined_poly(sprite, front_arm, skin, outline, 3)
        pygame.draw.rect(sprite, skin_light, (center + 25, 46, 4, 15))
        _toned_oval(sprite, (center + 22, 65, 17, 17), outline, skin_deep, skin, rim)
        _outlined_line(sprite, (center + 33, 69), (center + 45, 93), (112, 70, 40), 5, outline)

    # Face and curls sit above the body; separated curls survive game scaling.
    _toned_oval(sprite, (center - 17, 6, 35, 35), outline, skin_deep, skin, skin_light)
    pygame.draw.rect(sprite, rim, (center - 9, 10, 10, 3))
    curls = ((-16, 4), (-11, -1), (-4, -4), (4, -3), (11, 1), (16, 8), (-18, 12), (17, 16), (-15, 22))
    for index, (ox, oy) in enumerate(curls):
        _pixel_disc(sprite, hair_deep, (center + ox, 10 + oy), 6)
        _pixel_disc(sprite, hair if index % 2 else hair_light, (center + ox + 1, 9 + oy), 4)
    pygame.draw.rect(sprite, outline, (center - 8, 22, 3, 3))
    pygame.draw.rect(sprite, outline, (center + 6, 22, 3, 3))
    pygame.draw.rect(sprite, skin_deep, (center - 1, 23, 3, 6))
    if laughing:
        pygame.draw.rect(sprite, outline, (center - 9, 29, 19, 10))
        pygame.draw.rect(sprite, (255, 242, 211), (center - 7, 30, 15, 3))
        pygame.draw.rect(sprite, (199, 66, 67), (center - 5, 36, 11, 3))
        pygame.draw.rect(sprite, (255, 226, 142), (center - 31, 18, 8, 3))
        pygame.draw.rect(sprite, (255, 226, 142), (center + 25, 17, 9, 3))
    else:
        pygame.draw.rect(sprite, outline, (center - 6, 31, 14, 5))
        pygame.draw.rect(sprite, (255, 240, 211), (center - 4, 31, 10, 2))
    if hurt:
        pygame.draw.rect(sprite, (255, 247, 194), (center - 25, 9, 4, 24))
        pygame.draw.rect(sprite, (255, 92, 66), (center - 31, 16, 4, 10))
    rendered = _hit_flash_sprite(
        _material_lit_sprite(sprite, "denim", cache=False),
        hit_flash,
        cache=False,
    )
    return _blit_grounded(surface, rendered, x, y, z, facing, 101)


def draw_projectile(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float = 0,
    facing: object = 1,
    kind: object = "pipe",
    frame: int = 0,
) -> pygame.Rect:
    """Draw a shaded projectile plus a compact direction-of-travel trail."""

    px, py = _i(x), _i(y - z)
    direction = _face_sign(facing)
    projectile = str(kind or "pipe").strip().lower().replace("-", "_")
    phase = int(frame) % 4
    if projectile in {"bb", "bb_pellet"}:
        # The pellet is intentionally oversized by a few pixels for gameplay
        # readability, with a crisp streak that still reads at 2x/3x scale.
        trail_end = px - direction * (10 + phase * 2)
        pygame.draw.line(surface, (54, 92, 111), (trail_end, py), (px - direction * 3, py), 2)
        pygame.draw.line(surface, (151, 226, 249), (px - direction * 7, py), (px, py), 1)
        pygame.draw.rect(surface, (24, 39, 48), (px - 3, py - 3, 6, 6))
        pygame.draw.rect(surface, (157, 224, 241), (px - 2, py - 2, 4, 4))
        pygame.draw.rect(surface, (248, 255, 255), (px, py - 2, 2, 2))
        casing_x = px - direction * (7 + phase)
        casing_y = py + ((phase + 1) % 3) - 1
        pygame.draw.rect(surface, (245, 208, 91), (casing_x, casing_y, 2, 2))
        return pygame.Rect(min(px - 4, trail_end), py - 4, abs(px - trail_end) + 8, 8)
    if projectile in {"flame", "torch", "fire"}:
        outer = [(px - direction * 4, py), (px + direction * 7, py - 8), (px + direction * 25, py - 3), (px + direction * 31, py), (px + direction * 22, py + 6), (px + direction * 7, py + 8)]
        rect = pygame.draw.polygon(surface, (115, 38, 41), outer)
        middle = [(px, py), (px + direction * 9, py - 6), (px + direction * 24, py), (px + direction * 9, py + 6)]
        pygame.draw.polygon(surface, (242, 78, 31), middle)
        pygame.draw.polygon(surface, (255, 157, 43), [(px + direction * 2, py), (px + direction * 11, py - 4), (px + direction * 18, py), (px + direction * 10, py + 4)])
        pygame.draw.rect(surface, (255, 244, 153), (px + min(0, direction * 8), py - 2, 9, 4))
        pygame.draw.rect(surface, (255, 203, 69), (px + direction * 24, py - 10 + phase * 3, 3, 3))
        pygame.draw.rect(surface, (242, 91, 38), (px + direction * 15, py + 9 - phase, 2, 2))
        return rect.inflate(8, 12)
    if projectile in {"sonic", "sound", "speaker_wave"}:
        radius = 8 + phase * 4
        rects: list[pygame.Rect] = []
        for index, inset in enumerate((0, 5, 9)):
            r = max(3, radius - inset)
            ring = pygame.Rect(px - r, py - max(3, r // 2), r * 2, max(6, r))
            pygame.draw.ellipse(surface, (38, 82, 106), ring, 4)
            pygame.draw.ellipse(surface, (74, 221, 241) if index == 0 else (164, 247, 253), ring, 2)
            rects.append(ring)
        pygame.draw.rect(surface, (235, 255, 255), (px + direction * (radius - 1), py - 2, 5, 5))
        pygame.draw.rect(surface, (92, 222, 244), (px - direction * (radius + 5), py - 1, 4, 3))
        return rects[0].unionall(rects[1:]).inflate(7, 7)
    if projectile in {"rock", "debris"}:
        points = [(px - 7, py - 3), (px - 2, py - 8), (px + 7, py - 5), (px + 9, py + 2), (px + 3, py + 8), (px - 7, py + 5)]
        rect = pygame.draw.polygon(surface, (37, 34, 37), points)
        pygame.draw.polygon(surface, (105, 99, 91), [(px - 5, py - 2), (px - 1, py - 6), (px + 6, py - 3), (px + 5, py + 4), (px - 3, py + 5)])
        pygame.draw.rect(surface, (174, 158, 132), (px - 1, py - 5, 5, 3))
        pygame.draw.rect(surface, (224, 211, 181), (px, py - 5, 3, 2))
        pygame.draw.rect(surface, (72, 65, 62), (px - direction * 14, py + 1, 5, 2))
        pygame.draw.rect(surface, (105, 92, 79), (px - direction * 23, py - 1, 3, 2))
        return rect.inflate(25, 8)

    # Pipe/stick angles cycle through four hand-pixelled poses, retaining rust,
    # highlight and an under-painted motion trail instead of filtered rotation.
    length = 22
    offsets = ((direction * length, 0), (direction * 16, -16), (0, -length), (direction * 16, 16))
    dx, dy = offsets[phase]
    metal = projectile in {"pipe", "broken_pipe"}
    color = (124, 141, 145) if metal else (121, 78, 45)
    start = (px - dx // 2, py - dy // 2)
    end = (px + dx // 2, py + dy // 2)
    pygame.draw.line(surface, (48, 40, 42), (start[0] - direction * 8, start[1]), (end[0] - direction * 8, end[1]), 3)
    rect = _outlined_line(surface, start, end, color, 5, (30, 29, 33))
    pygame.draw.line(surface, _shade(color, 50), (start[0] + 1, start[1] - 1), (end[0] + 1, end[1] - 1), 2)
    if metal:
        pygame.draw.rect(surface, (179, 75, 53), (px - 3, py - 2, 6, 4))
        pygame.draw.rect(surface, (221, 221, 205), (end[0] - 2, end[1] - 2, 4, 3))
    return rect.inflate(22, 16)


def draw_pickup(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float = 0,
    kind: object = "bb_ammo",
    frame: int = 0,
) -> pygame.Rect:
    """Draw a readable non-solid pickup at a floor anchor."""

    px, py = _i(x), _i(y - z)
    pickup = str(kind or "bb_ammo").strip().lower().replace("-", "_")
    bob = (0, 1, 2, 1)[int(frame) % 4]
    shadow = pygame.Rect(px - 13, py - 3, 26, 7)
    pygame.draw.ellipse(surface, (13, 17, 24), shadow)
    pygame.draw.ellipse(surface, (36, 38, 46), shadow.inflate(-8, -3))
    if pickup in {"super_butane", "butane", "propane", "fuel"}:
        # Shelly's refill is a tiny magenta steel canister, not a generic gray
        # square: rolled rim, valve, form shadow, specular edge and flame mark.
        rect = pygame.Rect(px - 9, py - 24 - bob, 18, 22)
        pygame.draw.rect(surface, (25, 23, 34), rect.inflate(4, 3), border_radius=3)
        pygame.draw.rect(surface, (113, 37, 78), rect, border_radius=2)
        pygame.draw.rect(surface, (189, 60, 119), (rect.x + 2, rect.y + 2, 11, rect.h - 4), border_radius=2)
        pygame.draw.rect(surface, (236, 112, 158), (rect.x + 3, rect.y + 3, 3, rect.h - 7))
        pygame.draw.rect(surface, (70, 30, 59), (rect.right - 5, rect.y + 2, 4, rect.h - 4))
        pygame.draw.rect(surface, (28, 31, 39), (px - 5, rect.y - 5, 10, 5))
        pygame.draw.rect(surface, (160, 177, 181), (px - 3, rect.y - 7, 6, 3))
        pygame.draw.rect(surface, (233, 244, 238), (px - 1, rect.y - 7, 2, 2))
        pygame.draw.polygon(surface, (255, 199, 67), [(px, rect.y + 7), (px - 4, rect.y + 14), (px, rect.y + 12), (px + 3, rect.y + 17), (px + 5, rect.y + 9)])
        pygame.draw.rect(surface, (255, 242, 167), (px - 1, rect.y + 11, 2, 4))
        glint_phase = (int(frame) // 2) % 7
        glint_x = rect.x + 2 + min(rect.w - 5, glint_phase * 2)
        pygame.draw.rect(surface, (255, 246, 213), (glint_x, rect.y + 4, 2, 5))
        return shadow.union(rect.inflate(4, 9))
    if pickup not in {"bb_ammo", "bb", "ammo"}:
        rect = pygame.Rect(px - 9, py - 15 - bob, 18, 14)
        pygame.draw.rect(surface, (22, 27, 34), rect.inflate(4, 4))
        pygame.draw.rect(surface, (67, 82, 93), rect)
        pygame.draw.rect(surface, (112, 139, 151), (rect.x + 2, rect.y + 2, rect.w - 5, 4))
        pygame.draw.rect(surface, (38, 48, 58), (rect.right - 5, rect.y + 3, 4, rect.h - 4))
        pygame.draw.rect(surface, (209, 227, 225), (rect.x + 3, rect.y + 3, 3, 2))
        glint_phase = (int(frame) // 2) % 8
        glint_x = rect.x + 3 + min(rect.w - 7, glint_phase * 2)
        pygame.draw.rect(surface, (247, 255, 246), (glint_x, rect.y + 3, 2, 2))
        return shadow.union(rect.inflate(4, 4))

    rect = pygame.Rect(px - 12, py - 17 - bob, 24, 15)
    pygame.draw.rect(surface, (24, 41, 52), rect)
    pygame.draw.rect(surface, (104, 194, 221), rect, 2)
    pygame.draw.rect(surface, (177, 228, 238), (rect.x + 3, rect.y + 3, rect.width - 6, 3))
    pygame.draw.rect(surface, (51, 111, 135), (rect.x + 3, rect.y + 7, rect.width - 6, 5))
    pygame.draw.rect(surface, (15, 28, 39), (rect.right - 5, rect.y + 3, 3, rect.height - 5))
    pygame.draw.line(surface, (221, 247, 247), (rect.x + 4, rect.y + 3), (rect.x + 11, rect.y + 3), 1)
    pygame.draw.rect(surface, (238, 249, 245), (rect.x + 7, rect.y + 7, 3, 3))
    pygame.draw.rect(surface, (238, 249, 245), (rect.x + 14, rect.y + 7, 3, 3))
    pygame.draw.rect(surface, (255, 215, 76), (rect.centerx - 2, rect.y - 2, 4, 3))
    glint_phase = (int(frame) // 2) % 8
    glint_x = rect.x + 4 + min(rect.w - 8, glint_phase * 2)
    pygame.draw.rect(surface, (241, 255, 255), (glint_x, rect.y + 3, 2, 2))
    return shadow.union(rect.inflate(0, 2))


def draw_effect(
    surface: pygame.Surface,
    x: float,
    y: float,
    z: float = 0,
    kind: object = "hit",
    frame: int = 0,
    color: pygame.Color | Sequence[int] | str | None = None,
    radius: int = 24,
) -> pygame.Rect:
    """Draw layered arcade combat feedback with bright one-frame cores."""

    cx, cy = _i(x), _i(y - z)
    effect = str(kind or "hit").strip().lower().replace("-", "_").replace(" ", "_")
    base = _rgb(color, (255, 218, 91))
    phase = max(0, int(frame))

    if effect in {"pickup", "pickup_collect"}:
        radius = max(7, min(int(radius) + phase * 3, 28))
        points = []
        for index in range(8):
            angle = index * math.tau / 8.0
            length = radius if index % 2 == 0 else max(4, radius // 2)
            points.append((cx + int(math.cos(angle) * length), cy + int(math.sin(angle) * length * 0.7)))
        rect = pygame.draw.lines(surface, (31, 53, 54), True, points, 4)
        pygame.draw.lines(surface, base, True, points, 2)
        pygame.draw.rect(surface, (246, 255, 220), (cx - 2, cy - 2, 5, 5))
        for index in range(4):
            angle = index * math.tau / 4.0 + 0.2
            sx = cx + int(math.cos(angle) * (radius + 4))
            sy = cy + int(math.sin(angle) * (radius * 0.65 + 4))
            pygame.draw.rect(surface, base, (sx - 1, sy - 1, 3, 3))
        return rect.inflate(8, 8)

    if effect in {"shockwave", "speaker", "sonic"}:
        r = max(5, min(int(radius) * 3, 7 + phase * 5))
        points = [
            (cx - r, cy),
            (cx - r + 5, cy - max(3, r // 3)),
            (cx, cy - max(5, r // 2)),
            (cx + r - 5, cy - max(3, r // 3)),
            (cx + r, cy),
            (cx + r - 5, cy + max(3, r // 3)),
            (cx, cy + max(5, r // 2)),
            (cx - r + 5, cy + max(3, r // 3)),
        ]
        rect = pygame.draw.lines(surface, (23, 69, 93), True, points, 7)
        pygame.draw.lines(surface, base if color else (75, 226, 242), True, points, 4)
        inner_points = [(cx + (px - cx) * 2 // 3, cy + (py - cy) * 2 // 3) for px, py in points]
        pygame.draw.lines(surface, (195, 251, 255), True, inner_points, 2)
        if phase % 2 == 0:
            pygame.draw.rect(surface, (214, 252, 255), (cx - r, cy - 1, 4, 3))
            pygame.draw.rect(surface, (214, 252, 255), (cx + r - 3, cy - 1, 4, 3))
        for angle_index in range(6):
            dx = int(math.cos(angle_index * math.pi / 3) * (r + 6))
            dy = int(math.sin(angle_index * math.pi / 3) * max(4, r // 2 + 3))
            pygame.draw.rect(surface, (112, 235, 249), (cx + dx - 2, cy + dy - 1, 4, 3))
        return rect.inflate(8, 8)

    if effect in {"flame_trail", "flame_trail_right", "flame_trail_left"}:
        direction = -1 if effect.endswith("_left") else 1
        reach = max(28, min(72, int(radius) + 18 + phase * 3))
        outer = [
            (cx + direction * 16, cy - 10),
            (cx + direction * 23, cy - 2),
            (cx + direction * 17, cy + 10),
            (cx - direction * max(17, reach - 15), cy + 12),
            (cx - direction * (reach + 12), cy + 5),
            (cx - direction * max(14, reach - 3), cy),
            (cx - direction * (reach + 16), cy - 10),
            (cx - direction * max(15, reach - 13), cy - 9),
        ]
        shadow = [(px, py + 2) for px, py in outer]
        rects = [
            pygame.draw.polygon(surface, (51, 22, 31), shadow),
            pygame.draw.polygon(surface, (184, 41, 25), outer),
        ]
        middle = [
            (cx + direction * 15, cy - 7),
            (cx + direction * 20, cy),
            (cx + direction * 14, cy + 7),
            (cx - direction * (reach + 4), cy + 6),
            (cx - direction * max(12, reach - 8), cy),
            (cx - direction * (reach + 7), cy - 6),
        ]
        rects.append(pygame.draw.polygon(surface, base if color else (255, 91, 23), middle))
        inner = [
            (cx + direction * 13, cy - 3),
            (cx + direction * 18, cy),
            (cx + direction * 12, cy + 3),
            (cx - direction * max(11, reach - 1), cy + 3),
            (cx - direction * max(8, reach - 13), cy),
            (cx - direction * max(11, reach - 1), cy - 3),
        ]
        rects.append(pygame.draw.polygon(surface, (255, 171, 38), inner))
        rects.append(
            pygame.draw.line(surface, (255, 246, 169), (cx - direction * (reach - 10), cy - 1), (cx + direction * 13, cy - 1), 3)
        )
        # Broken hot-air contours sit above the opaque ribbons instead of
        # blurring them, preserving the pixel silhouette at gameplay scale.
        for heat_index, y_offset in enumerate((-18, 16)):
            heat_rect = pygame.Rect(cx - reach - 8, cy + y_offset - 4, reach + 24, 10)
            rects.append(
                pygame.draw.arc(
                    surface,
                    (235, 104 + heat_index * 38, 70),
                    heat_rect,
                    0.18 if direction > 0 else math.pi + 0.18,
                    2.68 if direction > 0 else math.tau - 0.18,
                    1,
                )
            )
        for index, (dx, dy) in enumerate(((-reach - 11, -13), (-reach - 2, 11), (-reach + 10, -18), (-reach // 2, 16), (-reach // 3, -14))):
            ember_x = cx + direction * dx
            size = 4 if index == 0 else 3 if index < 3 else 2
            ember = pygame.Rect(ember_x - size // 2, cy + dy + (phase + index) % 5, size, max(2, size - 1))
            pygame.draw.rect(surface, (255, min(244, 156 + index * 19), 52 + index * 8), ember)
            rects.append(ember)
        return rects[0].unionall(rects[1:]).inflate(6, 6)

    if effect in {"flame_burst", "fire_burst"}:
        r = max(16, min(int(radius) + 6, 20 + phase * 5))
        points: list[tuple[int, int]] = []
        for index in range(24):
            angle = index * math.pi / 12.0
            length = r if index % 4 == 0 else max(8, r * 3 // 4) if index % 2 == 0 else max(6, r // 2)
            points.append((cx + int(math.cos(angle) * length), cy + int(math.sin(angle) * length)))
        shadow = [(px + (2 if px >= cx else -2), py + (2 if py >= cy else -2)) for px, py in points]
        rects = [
            pygame.draw.polygon(surface, (55, 22, 29), shadow),
            pygame.draw.polygon(surface, (197, 43, 24), points),
        ]
        rects.append(_pixel_disc(surface, base if color else (255, 91, 24), (cx, cy), max(8, r * 3 // 5)))
        rects.append(_pixel_disc(surface, (255, 177, 44), (cx - 1, cy - 1), max(5, r * 2 // 5)))
        rects.append(_pixel_disc(surface, (255, 247, 169), (cx - 2, cy - 2), max(3, r // 5)))
        for spoke in range(8):
            angle = spoke * math.tau / 8.0 + 0.12
            start = (cx + int(math.cos(angle) * r * 0.56), cy + int(math.sin(angle) * r * 0.56))
            end = (cx + int(math.cos(angle) * (r + 8)), cy + int(math.sin(angle) * (r + 8)))
            rects.append(pygame.draw.line(surface, (255, 221, 103), start, end, 2))
        for heat_radius in (r + 8, r + 15):
            heat_box = pygame.Rect(cx - heat_radius, cy - heat_radius, heat_radius * 2, heat_radius * 2)
            rects.append(pygame.draw.arc(surface, (232, 99, 62), heat_box, 0.2 + phase * 0.05, 1.42 + phase * 0.05, 1))
            rects.append(pygame.draw.arc(surface, (232, 99, 62), heat_box, 3.25 + phase * 0.05, 4.45 + phase * 0.05, 1))
        for index, angle in enumerate((0.22, 0.78, 1.18, 1.84, 2.45, 3.42, 4.08, 4.76, 5.22, 5.68)):
            distance = r + 9 + (index % 3) * 5
            ex = cx + int(math.cos(angle) * distance)
            ey = cy + int(math.sin(angle) * distance * 0.72)
            size = 4 if index % 3 == 0 else 3 if index % 2 == 0 else 2
            ember = pygame.Rect(ex - size // 2, ey - size // 2, size, size)
            pygame.draw.rect(surface, (255, 221, 91) if index % 2 == 0 else (255, 103, 29), ember)
            rects.append(ember)
        return rects[0].unionall(rects[1:]).inflate(7, 7)

    if effect in {"scorch", "flame_scorch"}:
        r = max(10, int(radius))
        height = max(5, r // 3)
        outer = pygame.Rect(cx - r, cy - height // 2, r * 2, height)
        inner = outer.inflate(-max(4, r // 3), -2)
        pygame.draw.ellipse(surface, (42, 29, 31), outer)
        pygame.draw.ellipse(surface, (91, 42, 31), inner, max(1, 3 - min(2, phase // 2)))
        crack_color = (183, 69, 35) if phase < 4 else (105, 53, 37)
        rects = [outer]
        for x_sign in (-1, 1):
            line = pygame.draw.lines(
                surface,
                crack_color,
                False,
                [
                    (cx + x_sign * 2, cy),
                    (cx + x_sign * max(6, r // 3), cy - 2),
                    (cx + x_sign * max(9, r * 2 // 3), cy + x_sign),
                ],
                2,
            )
            rects.append(line)
        for dx in (-r // 2, r // 2):
            pygame.draw.rect(surface, (237, 89, 35), (cx + dx - 1, cy - height // 2, 3, 2))
        if phase < 5:
            pygame.draw.rect(surface, (255, 198, 88), (cx - 2, cy - 1, 5, 2))
            pygame.draw.rect(surface, (255, 237, 169), (cx, cy - 2, 2, 2))
        return rects[0].unionall(rects[1:]).inflate(3, 3)

    if effect in {"enemy_fire", "enemy_on_fire"}:
        rects: list[pygame.Rect] = []
        tongues = ((-19, -10, 7), (-11, -22, 10), (0, -31, 13), (12, -20, 10), (20, -8, 7))
        for index, (dx, dy, scale) in enumerate(tongues):
            flicker = ((phase + index * 2) % 5) - 2
            fx, fy = cx + dx, cy + dy
            tongue = [
                (fx - scale, fy + 8),
                (fx - scale + 2, fy - 3),
                (fx, fy - scale - flicker),
                (fx + scale - 2, fy - 2),
                (fx + scale, fy + 8),
            ]
            rects.append(pygame.draw.polygon(surface, (59, 23, 29), [(px + 1, py + 2) for px, py in tongue]))
            rects.append(pygame.draw.polygon(surface, (215, 51, 24), tongue))
            inner = [(fx - 4, fy + 7), (fx - 2, fy - 1), (fx + 1, fy - 6 - flicker), (fx + 4, fy + 7)]
            rects.append(pygame.draw.polygon(surface, (255, 142, 33), inner))
            rects.append(pygame.draw.rect(surface, (255, 240, 128), (fx - 1, fy + 1, 3, 6)))
        # A hot waistline, charred contact pockets, rising smoke and loose
        # sparks sell a body briefly engulfed without creating burn gameplay.
        base_outer = pygame.Rect(cx - 25, cy - 8, 50, 13)
        rects.append(pygame.draw.ellipse(surface, (66, 24, 27), base_outer))
        rects.append(pygame.draw.arc(surface, (255, 118, 27), base_outer.inflate(-6, -3), math.pi, math.tau, 3))
        for smoke_index, (dx, dy, size) in enumerate(((-8, -50, 7), (6, -57, 6), (14, -47, 4))):
            smoke = pygame.Rect(cx + dx + ((phase + smoke_index) % 3) - 1, cy + dy, size, max(3, size - 2))
            pygame.draw.rect(surface, (72 + smoke_index * 9, 61 + smoke_index * 8, 67 + smoke_index * 8), smoke)
            rects.append(smoke)
        for spark_index, (dx, dy, size) in enumerate(((-27, -31, 3), (25, -37, 3), (-17, -48, 2), (18, -55, 2), (2, -64, 2))):
            spark = pygame.Rect(cx + dx, cy + dy + (phase + spark_index) % 5, size, size)
            pygame.draw.rect(surface, (255, 223, 91) if spark_index % 2 == 0 else (255, 91, 24), spark)
            rects.append(spark)
        for heat_radius in (31, 38):
            heat_box = pygame.Rect(cx - heat_radius, cy - 48 - heat_radius // 3, heat_radius * 2, heat_radius)
            rects.append(pygame.draw.arc(surface, (217, 91, 63), heat_box, 3.5, 5.8, 1))
        return rects[0].unionall(rects[1:]).inflate(6, 6)

    if effect == "ember":
        rise = min(18, phase * 3)
        pieces: list[pygame.Rect] = []
        for index, (dx, dy, size) in enumerate(((-7, 2, 4), (3, -5, 3), (10, 1, 2), (-1, -11, 3))):
            drift = -1 if (phase + index) % 2 else 1
            piece = pygame.Rect(cx + dx + drift * phase - size // 2, cy + dy - rise - size // 2, size, size)
            shadow = piece.move(1, 1).inflate(2, 2)
            pygame.draw.rect(surface, (74, 27, 30), shadow)
            pygame.draw.rect(surface, (255, 235, 118) if index % 2 == 0 else (255, 111, 31), piece)
            if index == 0:
                pygame.draw.rect(surface, (255, 252, 203), (piece.x + 1, piece.y, 2, 2))
            pieces.extend((shadow, piece))
        return pieces[0].unionall(pieces[1:]).inflate(2, 2)

    if effect in {"flame", "burn", "fire"}:
        rects = [pygame.Rect(cx - 12, cy - 7, 24, 14), pygame.Rect(cx - 8, cy - 19, 16, 17), pygame.Rect(cx - 4, cy - 29, 9, 14)]
        pygame.draw.polygon(surface, (86, 35, 40), [(cx - 13, cy + 6), (cx - 9, cy - 10), (cx - 3, cy - 3), (cx, cy - 23), (cx + 6, cy - 11), (cx + 12, cy + 6)])
        pygame.draw.rect(surface, (222, 55, 29), rects[0])
        pygame.draw.polygon(surface, (255, 119, 32), [(cx - 8, cy + 3), (cx - 5, cy - 17), (cx, cy - 9), (cx + 4, cy - 27), (cx + 8, cy + 3)])
        pygame.draw.rect(surface, (255, 224, 91), rects[2])
        pygame.draw.rect(surface, (255, 250, 190), (cx - 2, cy - 17, 5, 12))
        pygame.draw.rect(surface, (240, 83, 35), (cx + 14, cy - 16 + phase % 5, 3, 3))
        pygame.draw.rect(surface, (255, 185, 51), (cx - 15, cy - 9 - phase % 3, 2, 2))
        return rects[0].unionall(rects[1:])

    if effect in {"dust", "land", "step"}:
        spread = min(int(radius), 5 + phase * 3)
        pieces: list[pygame.Rect] = []
        dust_colors = ((92, 82, 76), (145, 128, 108), (198, 172, 134), (111, 101, 93))
        for index, (dx, dy, size) in enumerate(((-spread, 0, 7), (-spread // 2, -6, 5), (spread // 2, -5, 7), (spread, 1, 5))):
            piece = pygame.Rect(cx + dx - size // 2, cy + dy - size // 2, size, size)
            pygame.draw.rect(surface, (49, 45, 46), piece.inflate(2, 2))
            pygame.draw.rect(surface, base if color else dust_colors[index], piece)
            pygame.draw.rect(surface, _shade(base if color else dust_colors[index], 28), (piece.x + 1, piece.y, max(1, piece.w - 2), 2))
            pieces.append(piece)
        ring = pygame.Rect(cx - spread - 5, cy - max(4, spread // 2), max(12, spread * 2 + 10), max(8, spread))
        pygame.draw.arc(surface, (54, 47, 48), ring, 0.1, math.pi - 0.1, 3)
        pygame.draw.arc(surface, base if color else (205, 174, 130), ring.inflate(-3, -2), 0.15, math.pi - 0.15, 1)
        pieces.append(ring)
        return pieces[0].unionall(pieces[1:])

    if effect in {"chief_super", "claw", "slash", "dog_slash"}:
        slash_color = base if color else (247, 231, 193)
        pieces = []
        for offset in (-8, 0, 8):
            pygame.draw.line(surface, (74, 34, 42), (cx - 19, cy + offset + 9), (cx + 20, cy + offset - 9), 7)
            line = pygame.draw.line(surface, slash_color, (cx - 18, cy + offset + 8), (cx + 19, cy + offset - 8), 3)
            pygame.draw.rect(surface, (255, 255, 233), (cx + 17, cy + offset - 10, 5, 4))
            pieces.append(line)
        pygame.draw.rect(surface, (238, 74, 57), (cx + 13, cy - 11, 4, 4))
        pygame.draw.rect(surface, (255, 155, 70), (cx - 23, cy + 10, 4, 3))
        return pieces[0].unionall(pieces[1:]).inflate(12, 12)

    # Default hit spark is a chunky eight-point star.
    r = max(6, min(int(radius), 10 + phase * 2))
    points = [
        (cx, cy - r),
        (cx + 3, cy - 4),
        (cx + r, cy - 2),
        (cx + 5, cy + 2),
        (cx + r // 2, cy + r),
        (cx, cy + 5),
        (cx - r // 2, cy + r),
        (cx - 5, cy + 2),
        (cx - r, cy - 2),
        (cx - 3, cy - 4),
    ]
    shadow_points = [(px + (2 if px >= cx else -2), py + (2 if py >= cy else -2)) for px, py in points]
    pygame.draw.polygon(surface, (92, 38, 44), shadow_points)
    rect = pygame.draw.polygon(surface, base, points)
    inner = [(cx, cy - r // 2), (cx + r // 2, cy), (cx, cy + r // 2), (cx - r // 2, cy)]
    pygame.draw.polygon(surface, (255, 248, 189), inner)
    pygame.draw.rect(surface, (255, 255, 239), (cx - 3, cy - 3, 6, 6))
    drift = (phase % 5) - 2
    for index, (dx, dy, shard_color) in enumerate(((-r - 7, -5, (255, 118, 57)), (r + 5, -8, (255, 226, 98)), (-r // 2, r + 7, (255, 182, 65)), (r // 2, r + 4, (255, 244, 171)))):
        shard_x = cx + dx + drift * (1 if index % 2 == 0 else -1)
        shard_y = cy + dy + (phase // 2 if index in {1, 3} else 0)
        pygame.draw.rect(surface, shard_color, (shard_x, shard_y, 4, 3))
        if phase >= 2:
            pygame.draw.rect(surface, (255, 247, 195), (shard_x + 1, shard_y - 2, 2, 1))
    return rect.inflate(18, 18)


# Plural alias is convenient for engines that name the effect renderer after
# their ECS component collection.
draw_effects = draw_effect
