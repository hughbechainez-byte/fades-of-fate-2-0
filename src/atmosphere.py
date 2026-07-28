"""Deterministic atmosphere state and profile loading."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_MODULE_DIR = Path(__file__).resolve().parent
_ATMO_DATA = _MODULE_DIR.parent / "data" / "atmosphere.json"
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
        self.palette = tuple(palette)
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


def _get_profile(profile_id: str) -> _AtmosphereProfile:
    return _PROFILES[_identifier(profile_id, "profile_id")]


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
            tuple(_wrap_phase(_finite_float(value, "cloud_phase")) for value in self.cloud_phases),
        )
        object.__setattr__(self, "wind_direction", _wrap_degrees(_finite_float(self.wind_direction, "wind_direction")))
        object.__setattr__(self, "wind_speed", _bounded_float(self.wind_speed, "wind_speed", 0.0, float("inf")))
        object.__setattr__(self, "current_profile_id", _identifier(self.current_profile_id, "current_profile_id"))
        object.__setattr__(self, "target_profile_id", _identifier(self.target_profile_id, "target_profile_id"))
        _get_profile(self.current_profile_id)
        _get_profile(self.target_profile_id)
        object.__setattr__(self, "transition_progress", _clamp01(self.transition_progress))

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | object) -> AtmosphereSnapshot:
        if not isinstance(values, Mapping):
            raise ValueError("snapshot must be a mapping")
        current = _identifier(values.get("current_profile_id", _DEFAULT_PROFILE_ID), "current_profile_id")
        target = _identifier(values.get("target_profile_id", current), "target_profile_id")
        _get_profile(target)
        if current not in _PROFILES:
            raise ValueError(f"unknown current_profile_id '{current}'")
        phases = values.get("cloud_phases", [0.0] * _CLOUD_PHASE_COUNT)
        if not isinstance(phases, (tuple, list)):
            raise ValueError("cloud_phases must be an array")
        if len(phases) != _CLOUD_PHASE_COUNT:
            raise ValueError(f"cloud_phases must contain {_CLOUD_PHASE_COUNT} values")
        return cls(
            time_seconds=values.get("time_seconds", 0.0),
            seed=values.get("seed", 0),
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
        self.time_seconds = _quantize(_bounded_float(self.time_seconds, "time_seconds", 0.0, float("inf")))
        self.seed = _non_negative_int(self.seed, "seed")
        if not self.cloud_phases:
            self.cloud_phases = _seed_profile_seed(self.seed, self.current_profile_id)
        if len(self.cloud_phases) != _CLOUD_PHASE_COUNT:
            raise ValueError(f"cloud_phases must contain {_CLOUD_PHASE_COUNT} values")
        self.cloud_phases = tuple(_quantize(_wrap_phase(_finite_float(value, "cloud_phase"))) for value in self.cloud_phases)
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
        payload = AtmosphereSnapshot.from_mapping(values)
        state = cls(
            time_seconds=payload.time_seconds,
            seed=payload.seed,
            cloud_phases=payload.cloud_phases,
            wind_direction=payload.wind_direction,
            wind_speed=payload.wind_speed,
            current_profile_id=payload.current_profile_id,
            target_profile_id=payload.target_profile_id,
            transition_progress=payload.transition_progress,
        )
        return state

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
        if target == self.current_profile_id:
            self.target_profile_id = target
            self.transition_progress = 1.0
            self.wind_direction = _get_profile(self.current_profile_id).wind_direction
            self.wind_speed = _get_profile(self.current_profile_id).wind_speed
            return
        self.target_profile_id = target
        if self.target_profile_id != target:
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

    def advance(self, dt: float, *, paused: bool = False) -> None:
        dt = _bounded_float(dt, "dt", 0.0, float("inf"))
        if paused or dt == 0.0:
            return
        current_profile = _get_profile(self.current_profile_id)
        target_profile = _get_profile(self.target_profile_id)
        start_fraction = self.transition_progress if self.current_profile_id != self.target_profile_id else 1.0

        if self.current_profile_id != self.target_profile_id:
            duration = self._duration_seconds(current_profile, target_profile)
            self.transition_progress = _clamp01(self.transition_progress + dt / duration)
            if self.transition_progress >= 1.0:
                self.current_profile_id = self.target_profile_id
                current_profile = target_profile
                self.transition_progress = 1.0
                target_profile = current_profile
        end_fraction = self.transition_progress if self.current_profile_id != self.target_profile_id else 1.0

        if self.current_profile_id == self.target_profile_id and start_fraction < 1.0:
            start_fraction = 1.0

        self.wind_direction = self._wind_direction(end_fraction)
        wind_start = self._wind_speed(start_fraction)
        wind_end = self._wind_speed(end_fraction)
        wind_average = _lerp(wind_start, wind_end, 0.5)
        self.wind_speed = _bounded_float(
            wind_average,
            "wind_speed",
            0.0,
            float("inf"),
        )
        cloud_start = self._cloud_speeds(start_fraction)
        cloud_end = self._cloud_speeds(end_fraction)
        parallax = self._parallax(end_fraction)
        cloud_speed_average = tuple(
            _lerp(start_speed, end_speed, 0.5)
            for start_speed, end_speed in zip(cloud_start, cloud_end, strict=False)
        )

        cloud_phases = []
        for phase, cloud_speed, layer_scale in zip(self.cloud_phases, cloud_speed_average, parallax, strict=False):
            cloud_delta = dt * (cloud_speed + wind_average) * layer_scale
            cloud_phases.append(_quantize(_wrap_phase(phase + cloud_delta)))
        self.cloud_phases = tuple(cloud_phases)
        self.time_seconds = _quantize(self.time_seconds + dt)

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
