"""Reusable location-locked backdrop compositor and cache utilities."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Mapping, Sequence, Protocol
import math

import pygame

from .atmosphere import CLOUD_CYCLE_PIXELS


BACKDROP_RENDER_CACHE_LIMIT = 16
HAZE_BAND_COUNT = 3
HAZE_REPEAT_WIDTH = int(CLOUD_CYCLE_PIXELS)

_PROFILE_PALETTE_CACHE: dict[str, tuple[tuple[int, int, int], ...]] = {}


class AtmosphereState(Protocol):
    """Protocol for optional atmosphere inputs used by the compositor.

    The protocol is intentionally structural so callers can pass any object or
    mapping containing these fields.
    """

    time_seconds: float
    seed: int
    cloud_phases: Sequence[float]
    wind: Any
    transition_progress: float


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise TypeError(f"{label} must be finite numeric")
    return result


def _i(value: float | int) -> int:
    return int(round(value))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _read_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be finite numeric")
    return int(value)


def _read_seed(state: Any) -> int:
    if state is None:
        return 0
    if hasattr(state, "seed"):
        try:
            return _read_int(getattr(state, "seed"), "seed")
        except TypeError:
            return 0
    if isinstance(state, Mapping):
        if "seed" in state:
            try:
                return _read_int(state.get("seed"), "seed")
            except TypeError:
                return 0
    return 0


def _read_wind(state: Any) -> tuple[float, float]:
    """Extract direction/speed from a loose wind object."""

    if state is None:
        return 0.0, 0.0
    if hasattr(state, "wind"):
        wind = getattr(state, "wind")
    else:
        wind = None
    direction = 0.0
    speed = 0.0
    if hasattr(state, "wind_speed") and hasattr(state, "wind_direction"):
        direction = _finite(getattr(state, "wind_direction"), "wind_direction")
        speed = _finite(getattr(state, "wind_speed"), "wind_speed")
    elif wind is not None:
        if isinstance(wind, Mapping):
            if "speed" in wind:
                speed = _finite(wind["speed"], "wind.speed")
            if "direction" in wind:
                direction = _finite(wind["direction"], "wind.direction")
        elif isinstance(wind, Sequence) and len(wind) >= 2:
            speed = _finite(wind[0], "wind[0]")
            direction = _finite(wind[1], "wind[1]")
    return speed, direction


def _read_cloud_phase(state: Any, index: int) -> float:
    if state is None:
        return 0.0
    raw = getattr(state, "cloud_phases", None)
    if raw is None and isinstance(state, Mapping):
        raw = state.get("cloud_phases")
    if not isinstance(raw, Sequence):
        return 0.0
    if index < len(raw):
        try:
            return float(raw[index])
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _read_time_seconds(state: Any) -> float:
    if state is None:
        return 0.0
    raw = getattr(state, "time_seconds", None)
    if raw is None and isinstance(state, Mapping):
        raw = state.get("time_seconds")
    if raw is None:
        return 0.0
    return _finite(raw, "time_seconds")


def _read_transition_progress(state: Any) -> float:
    if state is None:
        return 1.0
    raw = getattr(state, "transition_progress", None)
    if raw is None and isinstance(state, Mapping):
        raw = state.get("transition_progress")
    if raw is None:
        return 1.0
    return _clamp01(_finite(raw, "transition_progress"))


def _state_value(state: Any, name: str, default: Any = None) -> Any:
    if state is None:
        return default
    if isinstance(state, Mapping):
        return state.get(name, default)
    return getattr(state, name, default)


def _color(value: object) -> tuple[int, int, int] | None:
    if isinstance(value, str):
        text_value = value.strip().lstrip("#")
        if len(text_value) == 6:
            try:
                return tuple(int(text_value[index:index + 2], 16) for index in (0, 2, 4))
            except ValueError:
                return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) >= 3:
        try:
            return tuple(max(0, min(255, int(value[index]))) for index in range(3))
        except (TypeError, ValueError):
            return None
    return None


def _palette(value: object) -> tuple[tuple[int, int, int], ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    colors = tuple(filter(None, (_color(item) for item in value)))
    return colors if len(colors) >= 2 else None


def _profile_palette(profile_id: object) -> tuple[tuple[int, int, int], ...] | None:
    """Resolve a profile palette from the authoritative atmosphere data."""

    normalized = str(profile_id or "").strip()
    if not normalized:
        return None
    cached = _PROFILE_PALETTE_CACHE.get(normalized)
    if cached is not None:
        return cached
    # Keep this import lazy so the reusable renderer remains dependency-light
    # for procedural/legacy backgrounds while sharing one profile authority.
    from .atmosphere import AtmosphereState as RuntimeAtmosphereState

    try:
        palette = RuntimeAtmosphereState.new(profile_id=normalized).snapshot().sky_palette
    except ValueError:
        return None
    _PROFILE_PALETTE_CACHE[normalized] = palette
    return palette


def _lerp_palette(
    current: tuple[tuple[int, int, int], ...],
    target: tuple[tuple[int, int, int], ...],
    amount: float,
) -> tuple[tuple[int, int, int], ...]:
    count = max(len(current), len(target))
    if len(current) != count:
        current = tuple(current[min(index, len(current) - 1)] for index in range(count))
    if len(target) != count:
        target = tuple(target[min(index, len(target) - 1)] for index in range(count))
    fraction = _clamp01(amount)
    return tuple(
        tuple(
            int(round(start[channel] + (end[channel] - start[channel]) * fraction))
            for channel in range(3)
        )
        for start, end in zip(current, target, strict=False)
    )


def _sky_palette(
    route: Mapping[str, Any],
    atmosphere: AtmosphereState | Mapping[str, Any] | None,
) -> tuple[tuple[int, int, int], ...]:
    explicit = _palette(_state_value(atmosphere, "sky_palette"))
    if explicit is None:
        explicit = _palette(_state_value(atmosphere, "palette"))
    if explicit is not None:
        return explicit
    route_palette = _palette(route.get("sky_palette"))
    fallback = (
        route_palette
        or _profile_palette(route.get("sky_profile_id"))
        or _profile_palette("chapter_1_sunset")
        or ((20, 25, 40),)
    )
    current = _profile_palette(_state_value(atmosphere, "current_profile_id")) or fallback
    target = _profile_palette(_state_value(atmosphere, "target_profile_id")) or current
    return _lerp_palette(current, target, _read_transition_progress(atmosphere))


def _draw_opaque_sky(
    surface: pygame.Surface,
    route: Mapping[str, Any],
    atmosphere: AtmosphereState | Mapping[str, Any] | None,
) -> None:
    """Draw a cheap opaque profile sky without allocating a frame surface."""

    colors = _sky_palette(route, atmosphere)
    height = surface.get_height()
    surface.fill(colors[0])
    band_height = max(1, math.ceil(height / len(colors)))
    for index, color in enumerate(colors):
        top = index * band_height
        pygame.draw.rect(surface, color, (0, top, surface.get_width(), min(band_height, height - top)))


def _bounded_location_layer_offset(
    camera_x: float,
    rate: float,
    max_offset: float,
    layer_width: int,
    viewport_width: int,
) -> int:
    """Return world-aligned scenery with bounded relative parallax."""

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


def _draw_wrapped(surface: pygame.Surface, layer: pygame.Surface, x: int, y: int = 0) -> None:
    if layer.get_width() <= 0:
        return
    left = x % layer.get_width()
    surface.blit(layer, (left - layer.get_width(), y))
    surface.blit(layer, (left, y))


def _haze_band_rects(
    route: Mapping[str, Any],
    layer: pygame.Surface,
) -> tuple[pygame.Rect, ...]:
    """Split authored haze into the three declared atmosphere motion planes."""

    ground_y = int(route.get("ground_opaque_from_y", 240))
    haze_bottom = max(
        HAZE_BAND_COUNT,
        min(layer.get_height(), max(96, ground_y // 2)),
    )
    return tuple(
        pygame.Rect(
            0,
            (haze_bottom * index) // HAZE_BAND_COUNT,
            layer.get_width(),
            (haze_bottom * (index + 1)) // HAZE_BAND_COUNT
            - (haze_bottom * index) // HAZE_BAND_COUNT,
        )
        for index in range(HAZE_BAND_COUNT)
    )


def _atmosphere_haze_offset(
    route: Mapping[str, Any],
    atmosphere: AtmosphereState | Mapping[str, Any] | None,
    camera_x: float,
    layer_width: int,
    viewport_width: int,
    band_index: int,
) -> int:
    """Resolve one independently phased atmosphere plane.

    ``AtmosphereState.advance`` integrates the profile's declared cloud speed
    and parallax factor into each normalized cloud phase.  Convert the phase
    linearly across the authored seamless haze tile.  This keeps motion slow
    and monotonic; wrapping one full tile is visually continuous.
    """

    factors = _state_value(atmosphere, "parallax_factors", ())
    if not isinstance(factors, Sequence) or isinstance(factors, (str, bytes)):
        factors = ()
    rate = (
        float(factors[band_index])
        if band_index < len(factors)
        else float(route.get("far_parallax", 1.0))
    )
    base_x = _bounded_location_layer_offset(
        camera_x,
        rate,
        float(route.get("far_max_offset", 0.0)),
        layer_width,
        viewport_width,
    )
    phase = _read_cloud_phase(atmosphere, band_index) % 1.0
    _, direction = _read_wind(atmosphere)
    horizontal_wind = math.cos(math.radians(direction))
    direction_sign = -1 if horizontal_wind < 0.0 else 1
    phase_pixels = _i(phase * HAZE_REPEAT_WIDTH)
    return base_x + direction_sign * phase_pixels


def _draw_wrapped_band(
    surface: pygame.Surface,
    layer: pygame.Surface,
    x: int,
    band: pygame.Rect,
) -> None:
    previous_clip = surface.get_clip()
    band_clip = previous_clip.clip(
        pygame.Rect(0, band.y, surface.get_width(), band.height)
    )
    if band_clip.width <= 0 or band_clip.height <= 0:
        return
    try:
        surface.set_clip(band_clip)
        _draw_wrapped(surface, layer, x, 0)
    finally:
        surface.set_clip(previous_clip)


def _read_layer(
    route: Mapping[str, Any],
    layer_name: str,
    layers: Mapping[str, pygame.Surface | None],
) -> pygame.Surface | None:
    layer = layers.get(layer_name)
    if layer is not None:
        return layer
    if layer_name in {"far_haze", "far"}:
        return layers.get("far")
    if layer_name in {"near_occluder", "near"}:
        return layers.get("near")
    return None


def _backdrop_cache_key(
    theme: str,
    width: int,
    height: int,
    world_width: int,
    camera_x: float,
    route: Mapping[str, Any],
    layers: Mapping[str, pygame.Surface | None],
    loader_identity: Any,
) -> tuple[Any, ...]:
    return (
        str(theme),
        int(width),
        int(height),
        int(world_width),
        _i(camera_x),
        loader_identity,
        str(route.get("projection_profile_id", "")),
        str(route.get("sky_profile_id", "")),
        str(route.get("ground_opaque_from_y", "")),
        float(route.get("far_parallax", 1.0)),
        float(route.get("near_parallax", 1.0)),
        float(route.get("far_max_offset", 0)),
        float(route.get("near_max_offset", 0)),
        tuple(
            (
                key,
                None
                if layer is None
                else (
                    id(layer),
                    layer.get_size(),
                    bool(layer.get_masks()[3]),
                ),
            )
            for key, layer in (
                ("main", layers.get("main")),
                ("far", layers.get("far")),
                ("near", layers.get("near")),
                ("far_haze", layers.get("far_haze")),
                ("far_skyline", layers.get("far_skyline")),
                ("architecture", layers.get("architecture")),
                ("ground", layers.get("ground")),
                ("near_occluder", layers.get("near_occluder")),
            )
        ),
    )


def _compose_static_backdrop_layers(
    width: int,
    height: int,
    route: Mapping[str, Any],
    layers: Mapping[str, pygame.Surface | None],
    camera_x: float,
    world_width: int,
) -> tuple[pygame.Surface, pygame.Surface]:
    """Pre-render non-atmospheric elements into two reusable layers.

    Returns:
        (sky_layer, structure_layer)
    where sky_layer is the legacy fallback panorama and structure_layer
    contains only world-locked architecture and ground.
    """

    sky_layer = pygame.Surface((width, height), pygame.SRCALPHA)
    structure_layer = pygame.Surface((width, height), pygame.SRCALPHA)

    architecture = layers.get("architecture")
    ground = layers.get("ground")
    layered_route = architecture is not None and ground is not None

    main = layers.get("main")
    if not layered_route and main is not None:
        if main.get_size() != (world_width, height):
            raise ValueError("main layer must match route dimensions")
        sky_layer.blit(main, (-_i(camera_x), 0))

    if architecture is not None:
        if architecture.get_size() != (world_width, height):
            raise ValueError("architecture_asset must match route dimensions")
        if architecture.get_masks()[3]:
            structure_layer.blit(architecture, (-_i(camera_x), 0))

    if ground is not None:
        if ground.get_size() != (world_width, height):
            raise ValueError("ground_asset must match route dimensions")
        if ground.get_masks()[3]:
            structure_layer.blit(ground, (-_i(camera_x), 0))

    return sky_layer.convert_alpha(), structure_layer.convert_alpha()


def _apply_dynamic_atmosphere(
    surface: pygame.Surface,
    route: Mapping[str, Any],
    layers: Mapping[str, pygame.Surface | None],
    camera_x: float,
    atmosphere: AtmosphereState | Mapping[str, Any] | None,
    width: int,
) -> None:
    """Render cloud/haze movement and skyline in front of the static sky.

    Atmosphere defaults are intentionally static so the legacy route still renders
    with the same result even without a runtime atmosphere object.
    """

    cloud_layer = _read_layer(route, "far_haze", layers)
    if cloud_layer is None:
        return
    if not cloud_layer.get_masks()[3] or cloud_layer.get_width() <= 0:
        return

    for band_index, band in enumerate(_haze_band_rects(route, cloud_layer)):
        band_x = _atmosphere_haze_offset(
            route,
            atmosphere,
            camera_x,
            cloud_layer.get_width(),
            width,
            band_index,
        )
        _draw_wrapped_band(surface, cloud_layer, band_x, band)

    skyline = _read_layer(route, "far_skyline", layers)
    if skyline is None:
        return
    if not skyline.get_masks()[3] or skyline.get_width() <= 0:
        return

    skyline_x = _bounded_location_layer_offset(
        camera_x,
        float(route.get("far_parallax", 1.0)),
        float(route.get("far_max_offset", 0.0)),
        skyline.get_width(),
        width,
    )
    _draw_wrapped(surface, skyline, skyline_x, 0)


_BACKDROP_CACHE: OrderedDict[tuple[Any, ...], tuple[pygame.Surface, pygame.Surface]] = OrderedDict()


def render_route_backdrop(
    surface: pygame.Surface,
    theme: str,
    route: Mapping[str, Any],
    layers: Mapping[str, pygame.Surface | None],
    camera_x: float,
    world_width: int,
    *,
    atmosphere: AtmosphereState | Mapping[str, Any] | None = None,
    loader_identity: Any | None = None,
) -> None:
    """Render one scene backdrop without mutating cache entries for atmosphere."""

    world_width = max(int(world_width), int(surface.get_width()))
    width, height = surface.get_size()
    if height != 360:
        raise ValueError("route backdrop requires a 360px logical canvas")

    key = _backdrop_cache_key(
        theme,
        width,
        height,
        world_width,
        camera_x,
        route,
        layers,
        loader_identity,
    )

    cached = _BACKDROP_CACHE.get(key)
    if cached is None:
        cached = _compose_static_backdrop_layers(
            width,
            height,
            route,
            layers,
            camera_x,
            world_width,
        )
        _BACKDROP_CACHE[key] = cached
        _BACKDROP_CACHE.move_to_end(key)
        while len(_BACKDROP_CACHE) > BACKDROP_RENDER_CACHE_LIMIT:
            _BACKDROP_CACHE.popitem(last=False)
    else:
        _BACKDROP_CACHE.move_to_end(key)

    sky_layer, structure_layer = cached
    layered_route = layers.get("architecture") is not None and layers.get("ground") is not None
    if layered_route:
        _draw_opaque_sky(surface, route, atmosphere)
    else:
        surface.blit(sky_layer, (0, 0))
    _apply_dynamic_atmosphere(surface, route, layers, camera_x, atmosphere, width)
    surface.blit(structure_layer, (0, 0))


def clear_backdrop_caches() -> None:
    """Reset backdrop render caches."""

    _BACKDROP_CACHE.clear()


def backdrop_cache() -> Mapping[tuple[Any, ...], tuple[pygame.Surface, pygame.Surface]]:
    """Expose a stable read-only view for tests."""

    return dict(_BACKDROP_CACHE)


__all__ = [
    "AtmosphereState",
    "render_route_backdrop",
    "clear_backdrop_caches",
    "backdrop_cache",
    "_bounded_location_layer_offset",
    "_read_layer",
    "_compose_static_backdrop_layers",
]
