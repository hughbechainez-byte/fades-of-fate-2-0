"""Deterministic atmosphere state and profile loading."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

from .config import resource_path


_ATMO_DATA = resource_path("data/atmosphere.json")
_CLOUD_PHASE_COUNT = 3


def _finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a finite number") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _bounded_float(value: Any, label: str, minimum: float, maximum: float) -> float:
    result = _finite_float(value, label)
    if not minimum <= result <= maximum:
        raise ValueError(f"{label} must be between {minimum:g} and {maximum:g}")
    return result


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a non-negative integer") from error
    if result < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    if float(result) != _finite_float(value, label):
        raise ValueError(f"{label} must be a non-negative integer")
    return result


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    result = value.strip()
    if not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _wrap_degrees(value: float) -> float:
    wrapped = value % 360.0
    if wrapped == 360.0:
        return 0.0
    return wrapped


def _lerp(a: float, b: float, amount: float) -> float:
    return a + (b - a) * amount


def _lerp_degrees(a: float, b: float, amount: float) -> float:
    delta = ((b - a + 180.0) % 360.0) - 180.0
    return _wrap_degrees(a + delta * amount)


def _hex_color(value: Any, label: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a #RRGGBB color")
    normalized = value.strip()
    if len(normalized) != 7 or not normalized.startswith("#"):
        raise ValueError(f"{label} must be a #RRGGBB color")
    try:
        return tuple(int(normalized[index:index + 2], 16) for index in (1, 3, 5))
    except ValueError as error:
        raise ValueError(f"{label} must be a #RRGGBB color") from error


def _phase_from_seed(seed: int, index: int) -> float:
    state = (seed ^ (index * 2654435761)) & 0xFFFFFFFF
    return round(((state * 1103515245 + 12345) & 0xFFFFFFFF) / 4294967296.0, 6)


def _quantize(value: float) -> float:
    return round(value, 6)


def _wrap_phase(value: float) -> float:
    return value - math.floor(value)


class _AtmosphereProfile:
    __slots__ = (
        "id",
        "palette",
        "wind_direction",
        "wind_speed",
        "cloud_speeds",
        "parallax_factors",
        "transition_duration",
    )

    def __init__(
        self,
        *,
        profile_id: str,
        palette: list[str],
        wind_direction: float,
        wind_speed: float,
        cloud_speeds: list[float],
        parallax_factors: list[float],
        transition_duration: float,
    ) -> None:
        self.id = _identifier(profile_id, "profile id")
        if not isinstance(palette, list) or not palette:
            raise ValueError(f"profile '{self.id}' palette must be a non-empty list")
        self.palette = tuple(
            _hex_color(value, f"profile '{self.id}' palette[{index}]")
            for index, value in enumerate(palette)
        )
        self.wind_direction = _wrap_degrees(_bounded_float(wind_direction, "wind_direction", -3600.0, 3600.0))
        self.wind_speed = _bounded_float(wind_speed, "wind_speed", 0.0, float("inf"))
        if not isinstance(cloud_speeds, list) or len(cloud_speeds) != _CLOUD_PHASE_COUNT:
            raise ValueError(f"profile '{self.id}' cloud_speeds must have {_CLOUD_PHASE_COUNT} values")
        self.cloud_speeds = tuple(_bounded_float(value, f"profile '{self.id}' cloud_speed", 0.0, float("inf")) for value in cloud_speeds)
        if not isinstance(parallax_factors, list) or len(parallax_factors) != _CLOUD_PHASE_COUNT:
            raise ValueError(f"profile '{self.id}' parallax_factors must have {_CLOUD_PHASE_COUNT} values")
        self.parallax_factors = tuple(
            _bounded_float(value, f"profile '{self.id}' parallax_factor", 0.0, float("inf"))
            for value in parallax_factors
        )
        self.transition_duration = _bounded_float(transition_duration, f"profile '{self.id}' transition_duration", 0.0, float("inf"))


def _load_data() -> tuple[dict[str, _AtmosphereProfile], str, dict[str, str]]:
    try:
        raw = json.loads(_ATMO_DATA.read_text(encoding="utf-8-sig"))
    except OSError as error:
        raise RuntimeError(f"unable to read atmosphere data: {error}") from error
    if not isinstance(raw, Mapping):
        raise ValueError("atmosphere data must be an object")
    default_profile = _identifier(raw.get("default_profile_id", "chapter_1_sunset"), "default_profile_id")
    profiles_payload = raw.get("profiles")
    if not isinstance(profiles_payload, Mapping):
        raise ValueError("atmosphere.profiles must be an object")
    profiles: dict[str, _AtmosphereProfile] = {}
    for profile_id, payload in profiles_payload.items():
        if not isinstance(payload, Mapping):
            raise ValueError(f"profile '{profile_id}' must be an object")
        profiles[_identifier(profile_id, "profile id")] = _AtmosphereProfile(
            profile_id=str(profile_id),
            palette=list(payload.get("palette", [])),
            wind_direction=payload.get("wind_direction", 0.0),
            wind_speed=payload.get("wind_speed", 0.0),
            cloud_speeds=list(payload.get("cloud_speeds", [])),
            parallax_factors=list(payload.get("parallax_factors", [])),
            transition_duration=payload.get("transition_duration_seconds", 1.0),
        )
    route_payload = raw.get("route_profile_map")
    route_profiles: dict[str, str] = {}
    if isinstance(route_payload, Mapping):
        for route_id, value in route_payload.items():
            route_profiles[_identifier(route_id, "route id")] = _identifier(value, "route profile id")
    return profiles, default_profile, route_profiles


def _seed_profile_seed(seed: int, profile_id: str) -> tuple[float, float, float]:
    return (
        _phase_from_seed(seed, 0),
        _phase_from_seed(seed + _string_hash(profile_id), 1),
        _phase_from_seed(seed + _string_hash(profile_id) + 17, 2),
    )


def _string_hash(value: str) -> int:
    result = 2166136261
    for ch in value:
        result ^= ord(ch)
        result = (result * 16777619) & 0xFFFFFFFF
    return result


_PROFILES, _DEFAULT_PROFILE_ID, _ROUTE_PROFILES = _load_data()
if _DEFAULT_PROFILE_ID not in _PROFILES:
    raise ValueError(f"default profile '{_DEFAULT_PROFILE_ID}' is missing")
_PALETTE_LENGTH = len(_PROFILES[_DEFAULT_PROFILE_ID].palette)
for _profile_id, _profile in _PROFILES.items():
    if len(_profile.palette) != _PALETTE_LENGTH:
        raise ValueError(
            f"profile '{_profile_id}' palette must contain {_PALETTE_LENGTH} colors"
        )
for _route_id, _route_profile_id in _ROUTE_PROFILES.items():
    if _route_profile_id not in _PROFILES:
        raise ValueError(
            f"route '{_route_id}' references unknown profile '{_route_profile_id}'"
        )


def _get_profile(profile_id: str) -> _AtmosphereProfile:
    normalized = _identifier(profile_id, "profile_id")
    try:
        return _PROFILES[normalized]
    except KeyError as error:
        raise ValueError(f"unknown profile_id '{normalized}'") from error


def _clamp01(value: float) -> float:
    return _bounded_float(value, "transition_progress", 0.0, 1.0)


def _sequence_profile_for_route(route_id: str) -> str | None:
    return _ROUTE_PROFILES.get(_identifier(route_id, "route_id"))


@dataclass(frozen=True, slots=True)
class AtmosphereSnapshot:
    time_seconds: float = 0.0
    seed: int = 0
    cloud_phases: tuple[float, ...] = ()
    wind_direction: float = 0.0
    wind_speed: float = 0.0
    current_profile_id: str = _DEFAULT_PROFILE_ID
    target_profile_id: str = _DEFAULT_PROFILE_ID
    transition_progress: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "time_seconds", _quantize(_bounded_float(self.time_seconds, "time_seconds", 0.0, float("inf"))))
        object.__setattr__(self, "seed", _non_negative_int(self.seed, "seed"))
        if len(self.cloud_phases) != _CLOUD_PHASE_COUNT:
            raise ValueError(f"cloud_phases must contain {_CLOUD_PHASE_COUNT} values")
        object.__setattr__(
            self,
            "cloud_phases",
            tuple(
                _quantize(_wrap_phase(_finite_float(value, "cloud_phase")))
                for value in self.cloud_phases
            ),
        )
        object.__setattr__(
            self,
            "wind_direction",
            _quantize(_wrap_degrees(_finite_float(self.wind_direction, "wind_direction"))),
        )
        object.__setattr__(
            self,
            "wind_speed",
            _quantize(_bounded_float(self.wind_speed, "wind_speed", 0.0, float("inf"))),
        )
        object.__setattr__(self, "current_profile_id", _identifier(self.current_profile_id, "current_profile_id"))
        object.__setattr__(self, "target_profile_id", _identifier(self.target_profile_id, "target_profile_id"))
        _get_profile(self.current_profile_id)
        _get_profile(self.target_profile_id)
        object.__setattr__(
            self,
            "transition_progress",
            _quantize(_clamp01(self.transition_progress)),
        )

    @property
    def sky_palette(self) -> tuple[tuple[int, int, int], ...]:
        """Return the currently blended immutable RGB sky palette."""

        current = _get_profile(self.current_profile_id)
        target = _get_profile(self.target_profile_id)
        fraction = 1.0 if current.id == target.id else self.transition_progress
        return tuple(
            tuple(
                int(round(_lerp(float(source[channel]), float(destination[channel]), fraction)))
                for channel in range(3)
            )
            for source, destination in zip(current.palette, target.palette, strict=True)
        )

    @property
    def parallax_factors(self) -> tuple[float, ...]:
        """Return the currently blended per-cloud-layer parallax factors."""

        current = _get_profile(self.current_profile_id)
        target = _get_profile(self.target_profile_id)
        fraction = 1.0 if current.id == target.id else self.transition_progress
        return tuple(
            _quantize(_lerp(source, destination, fraction))
            for source, destination in zip(
                current.parallax_factors,
                target.parallax_factors,
                strict=True,
            )
        )

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | object) -> AtmosphereSnapshot:
        if not isinstance(values, Mapping):
            raise ValueError("snapshot must be a mapping")
        current = _identifier(values.get("current_profile_id", _DEFAULT_PROFILE_ID), "current_profile_id")
        target = _identifier(values.get("target_profile_id", current), "target_profile_id")
        _get_profile(target)
        if current not in _PROFILES:
            raise ValueError(f"unknown current_profile_id '{current}'")
        seed = _non_negative_int(values.get("seed", 0), "seed")
        phases = values.get("cloud_phases")
        if phases is None:
            phases = _seed_profile_seed(seed, current)
        if not isinstance(phases, (tuple, list)):
            raise ValueError("cloud_phases must be an array")
        if len(phases) != _CLOUD_PHASE_COUNT:
            raise ValueError(f"cloud_phases must contain {_CLOUD_PHASE_COUNT} values")
        return cls(
            time_seconds=values.get("time_seconds", 0.0),
            seed=seed,
            cloud_phases=tuple(phases),
            wind_direction=values.get("wind_direction", _get_profile(current).wind_direction),
            wind_speed=values.get("wind_speed", _get_profile(current).wind_speed),
            current_profile_id=current,
            target_profile_id=target,
            transition_progress=values.get("transition_progress", 1.0),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "time_seconds": self.time_seconds,
            "seed": self.seed,
            "cloud_phases": list(self.cloud_phases),
            "wind_direction": self.wind_direction,
            "wind_speed": self.wind_speed,
            "current_profile_id": self.current_profile_id,
            "target_profile_id": self.target_profile_id,
            "transition_progress": self.transition_progress,
        }


@dataclass(slots=True)
class AtmosphereState:
    """Mutable, update-step atmosphere state used by progression saves."""

    time_seconds: float = 0.0
    seed: int = 0
    cloud_phases: tuple[float, ...] = ()
    wind_direction: float = 0.0
    wind_speed: float = 0.0
    current_profile_id: str = _DEFAULT_PROFILE_ID
    target_profile_id: str = _DEFAULT_PROFILE_ID
    transition_progress: float = 1.0

    def __post_init__(self) -> None:
        self.time_seconds = _bounded_float(self.time_seconds, "time_seconds", 0.0, float("inf"))
        self.seed = _non_negative_int(self.seed, "seed")
        if not self.cloud_phases:
            self.cloud_phases = _seed_profile_seed(self.seed, self.current_profile_id)
        if len(self.cloud_phases) != _CLOUD_PHASE_COUNT:
            raise ValueError(f"cloud_phases must contain {_CLOUD_PHASE_COUNT} values")
        self.cloud_phases = tuple(
            _wrap_phase(_finite_float(value, "cloud_phase"))
            for value in self.cloud_phases
        )
        self.wind_direction = _wrap_degrees(_finite_float(self.wind_direction, "wind_direction"))
        self.wind_speed = _bounded_float(self.wind_speed, "wind_speed", 0.0, float("inf"))
        self.current_profile_id = _identifier(self.current_profile_id, "current_profile_id")
        self.target_profile_id = _identifier(self.target_profile_id, "target_profile_id")
        _get_profile(self.current_profile_id)
        _get_profile(self.target_profile_id)
        self.transition_progress = _clamp01(self.transition_progress)
        self._recompute_targets()

    @classmethod
    def new(
        cls,
        *,
        seed: int = 0,
        profile_id: str = _DEFAULT_PROFILE_ID,
    ) -> AtmosphereState:
        profile = _get_profile(profile_id)
        return cls(
            seed=_non_negative_int(seed, "seed"),
            cloud_phases=_seed_profile_seed(_non_negative_int(seed, "seed"), profile.id),
            wind_direction=profile.wind_direction,
            wind_speed=profile.wind_speed,
            current_profile_id=profile.id,
            target_profile_id=profile.id,
            transition_progress=1.0,
        )

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | object) -> AtmosphereState:
        if not isinstance(values, Mapping):
            raise ValueError("atmosphere must be a mapping")
        current = _identifier(
            values.get("current_profile_id", _DEFAULT_PROFILE_ID),
            "current_profile_id",
        )
        target = _identifier(
            values.get("target_profile_id", current),
            "target_profile_id",
        )
        current_profile = _get_profile(current)
        _get_profile(target)
        seed = _non_negative_int(values.get("seed", 0), "seed")
        phases = values.get("cloud_phases")
        if phases is None:
            phases = _seed_profile_seed(seed, current)
        if not isinstance(phases, (tuple, list)):
            raise ValueError("cloud_phases must be an array")
        if len(phases) != _CLOUD_PHASE_COUNT:
            raise ValueError(
                f"cloud_phases must contain {_CLOUD_PHASE_COUNT} values"
            )
        return cls(
            time_seconds=values.get("time_seconds", 0.0),
            seed=seed,
            cloud_phases=tuple(phases),
            wind_direction=values.get(
                "wind_direction",
                current_profile.wind_direction,
            ),
            wind_speed=values.get("wind_speed", current_profile.wind_speed),
            current_profile_id=current,
            target_profile_id=target,
            transition_progress=values.get("transition_progress", 1.0),
        )

    @staticmethod
    def _duration_seconds(current: _AtmosphereProfile, target: _AtmosphereProfile) -> float:
        return max(0.001, max(current.transition_duration, target.transition_duration))

    def _recompute_targets(self) -> None:
        current = _get_profile(self.current_profile_id)
        target = _get_profile(self.target_profile_id)
        self.current_profile_id = current.id
        self.target_profile_id = target.id
        if self.current_profile_id == self.target_profile_id:
            self.transition_progress = 1.0
        self.transition_progress = _clamp01(self.transition_progress)

    @property
    def _transition_fraction(self) -> float:
        return 1.0 if self.current_profile_id == self.target_profile_id else self.transition_progress

    def snapshot(self) -> AtmosphereSnapshot:
        return AtmosphereSnapshot.from_mapping(self.to_mapping())

    def set_target_profile(self, profile_id: str) -> None:
        target = _identifier(profile_id, "target_profile_id")
        _get_profile(target)
        # Route selection is intentionally allowed to reaffirm the active
        # target.  Treat that as a no-op so the handoff started by an
        # interlevel bridge is not restarted when gameplay begins.
        if target == self.target_profile_id:
            return
        if target == self.current_profile_id:
            self.target_profile_id = target
            self.transition_progress = 1.0
            self.wind_direction = _get_profile(self.current_profile_id).wind_direction
            self.wind_speed = _get_profile(self.current_profile_id).wind_speed
            return
        self.target_profile_id = target
        self.transition_progress = 0.0

    def set_profile_for_route(self, route_id: str) -> None:
        profile_id = _sequence_profile_for_route(route_id)
        if profile_id is None:
            raise ValueError(f"route '{route_id}' has no atmosphere profile")
        self.set_target_profile(profile_id)

    def _wind_direction(self, fraction: float) -> float:
        if self.current_profile_id == self.target_profile_id:
            return _get_profile(self.current_profile_id).wind_direction
        current_profile = _get_profile(self.current_profile_id)
        target_profile = _get_profile(self.target_profile_id)
        return _lerp_degrees(current_profile.wind_direction, target_profile.wind_direction, fraction)

    def _wind_speed(self, fraction: float) -> float:
        if self.current_profile_id == self.target_profile_id:
            return _get_profile(self.current_profile_id).wind_speed
        current_profile = _get_profile(self.current_profile_id)
        target_profile = _get_profile(self.target_profile_id)
        return _lerp(current_profile.wind_speed, target_profile.wind_speed, fraction)

    def _cloud_speeds(self, fraction: float) -> tuple[float, float, float]:
        current_profile = _get_profile(self.current_profile_id)
        target_profile = _get_profile(self.target_profile_id)
        if self.current_profile_id == self.target_profile_id:
            return current_profile.cloud_speeds
        return tuple(
            _lerp(current, target, fraction)
            for current, target in zip(current_profile.cloud_speeds, target_profile.cloud_speeds, strict=False)
        )

    def _parallax(self, fraction: float) -> tuple[float, float, float]:
        current_profile = _get_profile(self.current_profile_id)
        target_profile = _get_profile(self.target_profile_id)
        if self.current_profile_id == self.target_profile_id:
            return current_profile.parallax_factors
        return tuple(
            _lerp(current, target, fraction)
            for current, target in zip(current_profile.parallax_factors, target_profile.parallax_factors, strict=False)
        )

    @staticmethod
    def _integrated_layer_motion(
        current: _AtmosphereProfile,
        target: _AtmosphereProfile,
        layer_index: int,
        start_fraction: float,
        end_fraction: float,
        duration: float,
    ) -> float:
        """Integrate one linearly blended layer exactly over a transition."""

        velocity_start = (
            current.cloud_speeds[layer_index] + current.wind_speed
        )
        velocity_delta = (
            target.cloud_speeds[layer_index]
            + target.wind_speed
            - velocity_start
        )
        parallax_start = current.parallax_factors[layer_index]
        parallax_delta = (
            target.parallax_factors[layer_index] - parallax_start
        )
        linear = velocity_start * parallax_delta + velocity_delta * parallax_start
        quadratic = velocity_delta * parallax_delta
        return duration * (
            velocity_start
            * parallax_start
            * (end_fraction - start_fraction)
            + 0.5
            * linear
            * (end_fraction * end_fraction - start_fraction * start_fraction)
            + (quadratic / 3.0)
            * (
                end_fraction * end_fraction * end_fraction
                - start_fraction * start_fraction * start_fraction
            )
        )

    def advance(self, dt: float, *, paused: bool = False) -> None:
        dt = _bounded_float(dt, "dt", 0.0, float("inf"))
        if paused or dt == 0.0:
            return
        current_profile = _get_profile(self.current_profile_id)
        target_profile = _get_profile(self.target_profile_id)
        phase_deltas = [0.0] * _CLOUD_PHASE_COUNT
        remaining_dt = dt

        if self.current_profile_id != self.target_profile_id:
            duration = self._duration_seconds(current_profile, target_profile)
            start_fraction = self.transition_progress
            transition_dt = min(
                remaining_dt,
                max(0.0, (1.0 - start_fraction) * duration),
            )
            end_fraction = min(
                1.0,
                start_fraction + transition_dt / duration,
            )
            for layer_index in range(_CLOUD_PHASE_COUNT):
                phase_deltas[layer_index] += self._integrated_layer_motion(
                    current_profile,
                    target_profile,
                    layer_index,
                    start_fraction,
                    end_fraction,
                    duration,
                )
            self.transition_progress = end_fraction
            remaining_dt = max(0.0, remaining_dt - transition_dt)

            if end_fraction >= 1.0:
                self.current_profile_id = self.target_profile_id
                current_profile = target_profile
                self.transition_progress = 1.0

        active_profile = _get_profile(self.current_profile_id)
        if remaining_dt:
            for layer_index in range(_CLOUD_PHASE_COUNT):
                phase_deltas[layer_index] += remaining_dt * (
                    active_profile.cloud_speeds[layer_index]
                    + active_profile.wind_speed
                ) * active_profile.parallax_factors[layer_index]

        if self.current_profile_id == self.target_profile_id:
            self.wind_direction = active_profile.wind_direction
            self.wind_speed = active_profile.wind_speed
        else:
            self.wind_direction = self._wind_direction(self.transition_progress)
            self.wind_speed = self._wind_speed(self.transition_progress)

        self.cloud_phases = tuple(
            _wrap_phase(phase + delta)
            for phase, delta in zip(
                self.cloud_phases,
                phase_deltas,
                strict=True,
            )
        )
        self.time_seconds += dt

    def to_mapping(self) -> dict[str, Any]:
        return {
            "time_seconds": self.time_seconds,
            "seed": self.seed,
            "cloud_phases": list(self.cloud_phases),
            "wind_direction": self.wind_direction,
            "wind_speed": self.wind_speed,
            "current_profile_id": self.current_profile_id,
            "target_profile_id": self.target_profile_id,
            "transition_progress": self.transition_progress,
        }


__all__ = [
    "AtmosphereState",
    "AtmosphereSnapshot",
]
