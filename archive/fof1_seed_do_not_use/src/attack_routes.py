"""Immutable, validated combat-route data for Black Dave V2.

The runtime captures an :class:`AttackExecution` at input time so later
configuration reloads or animation state changes cannot alter an attack that
is already in progress.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping


ROUTE_ACTIONS = frozenset(("regular", "kick", "power"))
ROUTE_STEP_COUNT = 7
_SOURCE = Path(__file__).resolve().parents[1] / "data" / "black_dave_v2_routes.json"


class AttackRouteError(ValueError):
    """Raised when a route cannot safely be used by the combat runtime."""


def _frozen_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class AttackRouteStep:
    step_id: str
    move_table: str
    move_index: int
    clip_id: str
    startup: float
    active: float
    recovery: float
    buffer_window: float
    cancel_start: float
    cancel_actions: frozenset[str]
    hitbox_track: str
    target_cap: int
    push_profile: str
    animation_events: tuple[str, ...]
    vfx_events: tuple[str, ...]

    @property
    def move_profile_id(self) -> str:
        return f"{self.move_table}:{self.move_index}"


@dataclass(frozen=True, slots=True)
class AttackRoute:
    action: str
    steps: tuple[AttackRouteStep, ...]


@dataclass(frozen=True, slots=True)
class AttackExecution:
    """The immutable input-time record consumed by combat and animation."""

    action: str
    index: int
    step: AttackRouteStep
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


class AttackRouteLibrary:
    def __init__(self, routes: Mapping[str, AttackRoute]) -> None:
        self._routes = MappingProxyType(dict(routes))

    @property
    def routes(self) -> Mapping[str, AttackRoute]:
        return self._routes

    def resolve(self, route_action: str, index: int) -> AttackRouteStep:
        try:
            route = self._routes[route_action]
        except KeyError as exc:
            raise AttackRouteError(f"unknown route action: {route_action}") from exc
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(route.steps):
            raise AttackRouteError(f"{route_action} route index must be between 0 and {len(route.steps) - 1}")
        return route.steps[index]

    def capture_execution(
        self, route_action: str, index: int, *, metadata: Mapping[str, Any] | None = None
    ) -> AttackExecution:
        return AttackExecution(route_action, index, self.resolve(route_action, index), _frozen_mapping(metadata or {}))


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0.0:
        raise AttackRouteError(f"{label} must be a non-negative number")
    return float(value)


def _step(raw: Mapping[str, Any], label: str) -> AttackRouteStep:
    required = ("id", "move_table", "move_index", "clip_id", "startup", "active", "recovery", "buffer_window", "cancel_start", "hitbox_track", "target_cap", "push_profile", "animation_events", "vfx_events")
    missing = [key for key in required if key not in raw]
    if missing:
        raise AttackRouteError(f"{label} is missing {', '.join(missing)}")
    move_index = raw["move_index"]
    target_cap = raw["target_cap"]
    if isinstance(move_index, bool) or not isinstance(move_index, int) or move_index < 0:
        raise AttackRouteError(f"{label}.move_index must be a non-negative integer")
    if isinstance(target_cap, bool) or not isinstance(target_cap, int) or target_cap < 1:
        raise AttackRouteError(f"{label}.target_cap must be a positive integer")
    events = raw["animation_events"]
    vfx = raw["vfx_events"]
    cancels = raw.get("cancel_actions", ())
    if not isinstance(events, list) or not isinstance(vfx, list) or not isinstance(cancels, (list, tuple, frozenset)):
        raise AttackRouteError(f"{label} events and cancel_actions must be lists")
    return AttackRouteStep(
        step_id=str(raw["id"]), move_table=str(raw["move_table"]), move_index=move_index,
        clip_id=str(raw["clip_id"]), startup=_number(raw["startup"], f"{label}.startup"),
        active=_number(raw["active"], f"{label}.active"), recovery=_number(raw["recovery"], f"{label}.recovery"),
        buffer_window=_number(raw["buffer_window"], f"{label}.buffer_window"),
        cancel_start=_number(raw["cancel_start"], f"{label}.cancel_start"),
        cancel_actions=frozenset(map(str, cancels)), hitbox_track=str(raw["hitbox_track"]),
        target_cap=target_cap, push_profile=str(raw["push_profile"]),
        animation_events=tuple(map(str, events)), vfx_events=tuple(map(str, vfx)),
    )


def validate_route_data(
    raw: Mapping[str, Any], move_tables: Mapping[str, Iterable[Any]], clip_ids: Iterable[str] | None = None
) -> AttackRouteLibrary:
    """Validate JSON source against the authoritative combat/animation IDs."""
    raw_routes = raw.get("routes")
    if not isinstance(raw_routes, Mapping) or set(raw_routes) != ROUTE_ACTIONS:
        raise AttackRouteError("routes must contain exactly regular, kick, and power")
    known_clips = None if clip_ids is None else frozenset(map(str, clip_ids))
    routes: dict[str, AttackRoute] = {}
    all_step_ids: set[str] = set()
    for action in sorted(ROUTE_ACTIONS):
        entries = raw_routes[action]
        if not isinstance(entries, list) or len(entries) != ROUTE_STEP_COUNT:
            raise AttackRouteError(f"{action} route must contain exactly seven ordered steps")
        steps = tuple(_step(entry, f"routes.{action}[{index}]") for index, entry in enumerate(entries) if isinstance(entry, Mapping))
        if len(steps) != ROUTE_STEP_COUNT:
            raise AttackRouteError(f"{action} route steps must be objects")
        clips = [step.clip_id for step in steps]
        if len(set(clips)) != len(clips) or any("placeholder" in clip.lower() for clip in clips):
            raise AttackRouteError(f"{action} route cannot repeat or use placeholder contact/finisher clips")
        for index, step in enumerate(steps):
            if not step.step_id or step.step_id in all_step_ids:
                raise AttackRouteError(f"routes.{action}[{index}].id must be globally unique")
            all_step_ids.add(step.step_id)
            table = move_tables.get(step.move_table)
            if table is None or not 0 <= step.move_index < len(tuple(table)):
                raise AttackRouteError(f"{step.step_id} references orphan move {step.move_profile_id}")
            if known_clips is not None and step.clip_id not in known_clips:
                raise AttackRouteError(f"{step.step_id} references orphan clip {step.clip_id}")
            if step.cancel_start > step.startup + step.active + step.recovery:
                raise AttackRouteError(f"{step.step_id}.cancel_start exceeds its attack duration")
        routes[action] = AttackRoute(action, steps)
    return AttackRouteLibrary(routes)


def load_black_dave_v2_routes(
    move_tables: Mapping[str, Iterable[Any]], clip_ids: Iterable[str] | None = None, *, path: Path = _SOURCE
) -> AttackRouteLibrary:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AttackRouteError(f"could not load Black Dave V2 routes: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise AttackRouteError("Black Dave V2 route source must be an object")
    return validate_route_data(raw, move_tables, clip_ids)
