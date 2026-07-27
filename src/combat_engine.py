"""Deterministic, renderer-independent combat geometry for a belt brawler.

The engine uses three world axes without requiring a 3D renderer:

``x``
    Horizontal progress through the stage.
``depth``
    The walkable lane, visually projected toward/away from the camera.
``elevation``
    Height above the floor.  Feet are the elevation origin for actors.

All public geometry uses floats and stable entity identifiers.  That keeps the
module suitable for players, CPU companions, enemies, pets, and projectiles,
while rendering remains free to use pixels, sprites, or a perspective camera.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Callable, Hashable, Iterable, Iterator, Mapping, Sequence, TypeVar


EntityId = Hashable
EPSILON = 1.0e-7
_T = TypeVar("_T")


class AttackRejectionReason(str, Enum):
    """Stable reason codes returned by :func:`query_attack_detailed`."""

    INACTIVE = "inactive"
    DISABLED = "disabled"
    DEFEATED = "defeated"
    INVULNERABLE = "invulnerable"
    SELF = "self"
    ALREADY_HIT = "already-hit"
    REHIT_DELAY = "rehit-delay"
    WRONG_FACTION = "wrong-faction"
    GROUNDED_MISMATCH = "grounded-mismatch"
    AIRBORNE_MISMATCH = "airborne-mismatch"
    REQUIRED_TAGS = "required-tags"
    DOWNED = "downed"
    BLOCKED = "blocked"
    ARMOR = "armor"
    BLOCKED_TAGS = "blocked-tags"
    BEHIND = "behind"
    HORIZONTAL_RANGE = "horizontal-range"
    DEPTH_RANGE = "depth-range"
    ELEVATION_RANGE = "elevation-range"
    PREDICATE = "predicate"
    TARGET_CAP = "target-cap"


def _finite(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label} must be finite")
    return value


def _positive(value: float, label: str, *, allow_zero: bool = False) -> float:
    value = _finite(value, label)
    if value < 0.0 if allow_zero else value <= 0.0:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{label} must be {qualifier}")
    return value


def stable_id_key(value: EntityId) -> tuple[str, str]:
    """Return a cross-run ordering key for normal string/integer IDs."""

    return type(value).__qualname__, repr(value)


@dataclass(frozen=True, slots=True)
class AABB2:
    """Axis-aligned box on the stage floor (x/depth plane)."""

    min_x: float
    max_x: float
    min_depth: float
    max_depth: float

    def __post_init__(self) -> None:
        for name in ("min_x", "max_x", "min_depth", "max_depth"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.max_x < self.min_x or self.max_depth < self.min_depth:
            raise ValueError("AABB maximums must not be less than minimums")

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def depth(self) -> float:
        return self.max_depth - self.min_depth

    def expanded(self, x: float, depth: float | None = None) -> AABB2:
        depth = x if depth is None else depth
        x = _positive(x, "x expansion", allow_zero=True)
        depth = _positive(depth, "depth expansion", allow_zero=True)
        return AABB2(
            self.min_x - x,
            self.max_x + x,
            self.min_depth - depth,
            self.max_depth + depth,
        )

    def intersects(self, other: AABB2, *, touching: bool = True) -> bool:
        if touching:
            return not (
                self.max_x < other.min_x
                or other.max_x < self.min_x
                or self.max_depth < other.min_depth
                or other.max_depth < self.min_depth
            )
        return not (
            self.max_x <= other.min_x
            or other.max_x <= self.min_x
            or self.max_depth <= other.min_depth
            or other.max_depth <= self.min_depth
        )


@dataclass(slots=True)
class PushBody:
    """Mutable actor footprint used for movement and crowd separation."""

    entity_id: EntityId
    x: float
    depth: float
    elevation: float = 0.0
    half_width: float = 10.0
    half_depth: float = 5.0
    height: float = 48.0
    mass: float = 1.0
    movable: bool = True
    enabled: bool = True
    layer: int = 1
    mask: int = 0xFFFFFFFF

    def __post_init__(self) -> None:
        self.x = _finite(self.x, "x")
        self.depth = _finite(self.depth, "depth")
        self.elevation = _finite(self.elevation, "elevation")
        self.half_width = _positive(self.half_width, "half_width")
        self.half_depth = _positive(self.half_depth, "half_depth")
        self.height = _positive(self.height, "height")
        self.mass = _positive(self.mass, "mass")
        if self.layer <= 0 or self.mask < 0:
            raise ValueError("collision layer must be positive and mask non-negative")

    @property
    def bounds_2d(self) -> AABB2:
        return AABB2(
            self.x - self.half_width,
            self.x + self.half_width,
            self.depth - self.half_depth,
            self.depth + self.half_depth,
        )

    @property
    def top_elevation(self) -> float:
        return self.elevation + self.height


@dataclass(frozen=True, slots=True)
class HurtBox:
    """Damageable volume anchored at an actor's feet."""

    entity_id: EntityId
    team: Hashable
    x: float
    depth: float
    elevation: float = 0.0
    half_width: float = 10.0
    half_depth: float = 5.0
    height: float = 48.0
    enabled: bool = True
    vulnerable: bool = True
    grounded: bool | None = None
    tags: frozenset[str] = field(default_factory=frozenset)
    # The prior authoritative sample is optional.  When it is present the
    # attack query resolves the relative motion of the hit and hurt volumes,
    # rather than only asking whether the two end-of-frame rectangles overlap.
    # This is deliberately world-space data: render interpolation never leaks
    # into combat contact.
    sweep_from_x: float | None = None
    sweep_from_depth: float | None = None
    defeated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "depth", _finite(self.depth, "depth"))
        object.__setattr__(self, "elevation", _finite(self.elevation, "elevation"))
        object.__setattr__(self, "half_width", _positive(self.half_width, "half_width"))
        object.__setattr__(self, "half_depth", _positive(self.half_depth, "half_depth"))
        object.__setattr__(self, "height", _positive(self.height, "height"))
        object.__setattr__(self, "tags", frozenset(self.tags))
        if (self.sweep_from_x is None) != (self.sweep_from_depth is None):
            raise ValueError("hurtbox sweep origin requires both x and depth")
        if self.sweep_from_x is not None:
            object.__setattr__(self, "sweep_from_x", _finite(self.sweep_from_x, "sweep_from_x"))
            object.__setattr__(self, "sweep_from_depth", _finite(self.sweep_from_depth, "sweep_from_depth"))

    @property
    def bounds_2d(self) -> AABB2:
        return AABB2(
            self.x - self.half_width,
            self.x + self.half_width,
            self.depth - self.half_depth,
            self.depth + self.half_depth,
        )

    @property
    def swept_bounds_2d(self) -> AABB2:
        """Broadphase envelope for current and previous authoritative samples."""

        start_x, start_depth = self.sweep_start
        start = AABB2(
            start_x - self.half_width,
            start_x + self.half_width,
            start_depth - self.half_depth,
            start_depth + self.half_depth,
        )
        current = self.bounds_2d
        return AABB2(
            min(start.min_x, current.min_x),
            max(start.max_x, current.max_x),
            min(start.min_depth, current.min_depth),
            max(start.max_depth, current.max_depth),
        )

    @property
    def top_elevation(self) -> float:
        return self.elevation + self.height

    @property
    def is_grounded(self) -> bool:
        if self.grounded is not None:
            return self.grounded
        return self.elevation <= 0.5

    @property
    def sweep_start(self) -> tuple[float, float]:
        """Return the start of this authoritative movement sample."""

        return (
            self.x if self.sweep_from_x is None else self.sweep_from_x,
            self.depth if self.sweep_from_depth is None else self.sweep_from_depth,
        )


@dataclass(frozen=True, slots=True)
class HitBox:
    """One active attack volume and its gameplay payload."""

    attack_id: EntityId
    owner_id: EntityId
    team: Hashable
    x: float
    depth: float
    elevation: float = 0.0
    half_width: float = 18.0
    half_depth: float = 8.0
    height: float = 42.0
    damage: float = 1.0
    stun: float = 0.1
    knockback_x: float = 0.0
    knockback_depth: float = 0.0
    launch_elevation: float = 0.0
    depth_tolerance: float = 0.0
    hit_grounded: bool = True
    hit_airborne: bool = True
    friendly_fire: bool = False
    enabled: bool = True
    required_tags: frozenset[str] = field(default_factory=frozenset)
    blocked_tags: frozenset[str] = field(default_factory=frozenset)
    hitstop_seconds: float = 0.045
    camera_strength: float = 2.5
    camera_seconds: float = 0.12
    max_targets: int | None = None
    # Optional movement of the attack volume during its active window.  It is
    # paired with HurtBox.sweep_from_* by query_attack for continuous contact.
    sweep_from_x: float | None = None
    sweep_from_depth: float | None = None
    # Directional strikes use their fighter's body position as an origin.  A
    # target can overlap the extended fist box without being behind the actor.
    facing_x: float = 0.0
    front_origin_x: float | None = None
    front_origin_depth: float | None = None
    rear_tolerance: float = 0.0
    # Execution-level memory is supplied to query_attack_detailed.  Keeping the
    # policy on the hitbox lets single-hit and intentional multi-hit moves use
    # one deterministic query path without giving this pure module ownership of
    # mutable combatant state.
    max_hits_per_target: int | None = 1
    # Same time unit as the caller-provided ``now`` and ``last_hit_times``.
    rehit_delay: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "x",
            "depth",
            "elevation",
            "damage",
            "stun",
            "knockback_x",
            "knockback_depth",
            "launch_elevation",
            "depth_tolerance",
            "hitstop_seconds",
            "camera_strength",
            "camera_seconds",
            "facing_x",
            "rear_tolerance",
            "rehit_delay",
        ):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        object.__setattr__(self, "half_width", _positive(self.half_width, "half_width"))
        object.__setattr__(self, "half_depth", _positive(self.half_depth, "half_depth"))
        object.__setattr__(self, "height", _positive(self.height, "height"))
        for name in (
            "damage",
            "stun",
            "launch_elevation",
            "depth_tolerance",
            "hitstop_seconds",
            "camera_strength",
            "camera_seconds",
            "rehit_delay",
        ):
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} must be non-negative")
        object.__setattr__(self, "required_tags", frozenset(self.required_tags))
        object.__setattr__(self, "blocked_tags", frozenset(self.blocked_tags))
        if self.max_targets is not None and self.max_targets <= 0:
            raise ValueError("max_targets must be positive or None")
        if self.max_hits_per_target is not None and (
            isinstance(self.max_hits_per_target, bool)
            or not isinstance(self.max_hits_per_target, int)
            or self.max_hits_per_target <= 0
        ):
            raise ValueError("max_hits_per_target must be a positive integer or None")
        if self.rear_tolerance < 0.0:
            raise ValueError("rear_tolerance must be non-negative")
        if (self.sweep_from_x is None) != (self.sweep_from_depth is None):
            raise ValueError("hitbox sweep origin requires both x and depth")
        if self.sweep_from_x is not None:
            object.__setattr__(self, "sweep_from_x", _finite(self.sweep_from_x, "sweep_from_x"))
            object.__setattr__(self, "sweep_from_depth", _finite(self.sweep_from_depth, "sweep_from_depth"))
        if (self.front_origin_x is None) != (self.front_origin_depth is None):
            raise ValueError("hitbox front origin requires both x and depth")
        if self.front_origin_x is not None:
            object.__setattr__(self, "front_origin_x", _finite(self.front_origin_x, "front_origin_x"))
            object.__setattr__(self, "front_origin_depth", _finite(self.front_origin_depth, "front_origin_depth"))
        if abs(self.facing_x) <= EPSILON:
            object.__setattr__(self, "facing_x", 0.0)
        else:
            object.__setattr__(self, "facing_x", 1.0 if self.facing_x > 0.0 else -1.0)

    @property
    def bounds_2d(self) -> AABB2:
        return AABB2(
            self.x - self.half_width,
            self.x + self.half_width,
            self.depth - self.half_depth - self.depth_tolerance,
            self.depth + self.half_depth + self.depth_tolerance,
        )

    @property
    def top_elevation(self) -> float:
        return self.elevation + self.height

    @property
    def sweep_start(self) -> tuple[float, float]:
        """Return the start of this attack-volume sample."""

        return (
            self.x if self.sweep_from_x is None else self.sweep_from_x,
            self.depth if self.sweep_from_depth is None else self.sweep_from_depth,
        )

    @property
    def swept_bounds_2d(self) -> AABB2:
        """Broadphase envelope for the complete active-window movement."""

        start_x, start_depth = self.sweep_start
        start = AABB2(
            start_x - self.half_width,
            start_x + self.half_width,
            start_depth - self.half_depth - self.depth_tolerance,
            start_depth + self.half_depth + self.depth_tolerance,
        )
        current = self.bounds_2d
        return AABB2(
            min(start.min_x, current.min_x),
            max(start.max_x, current.max_x),
            min(start.min_depth, current.min_depth),
            max(start.max_depth, current.max_depth),
        )

    @property
    def front_origin(self) -> tuple[float, float]:
        """Return the fighter anchor used to reject rear-side contacts."""

        return (
            self.x if self.front_origin_x is None else self.front_origin_x,
            self.depth if self.front_origin_depth is None else self.front_origin_depth,
        )


@dataclass(frozen=True, slots=True)
class StageObstacle:
    """A solid stage rectangle, including a thin wall or scenery rail."""

    obstacle_id: EntityId
    bounds: AABB2
    min_elevation: float = 0.0
    max_elevation: float = math.inf
    enabled: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "min_elevation", _finite(self.min_elevation, "min_elevation"))
        max_elevation = float(self.max_elevation)
        if math.isnan(max_elevation):
            raise ValueError("max_elevation must not be NaN")
        object.__setattr__(self, "max_elevation", max_elevation)
        if self.max_elevation <= self.min_elevation:
            raise ValueError("max_elevation must exceed min_elevation")

    @property
    def bounds_2d(self) -> AABB2:
        return self.bounds

    @classmethod
    def rail(
        cls,
        obstacle_id: EntityId,
        *,
        start: tuple[float, float],
        end: tuple[float, float],
        thickness: float = 2.0,
        height: float = math.inf,
    ) -> StageObstacle:
        """Create an axis-aligned thin obstacle for a curb, wall, or railing."""

        thickness = _positive(thickness, "thickness")
        x1, d1 = map(float, start)
        x2, d2 = map(float, end)
        if abs(x1 - x2) > EPSILON and abs(d1 - d2) > EPSILON:
            raise ValueError("rails must be horizontal or depth-aligned")
        half = thickness * 0.5
        return cls(
            obstacle_id,
            AABB2(min(x1, x2) - half, max(x1, x2) + half, min(d1, d2) - half, max(d1, d2) + half),
            max_elevation=height,
        )


@dataclass(frozen=True, slots=True)
class StageBounds:
    """Outer walkable rails for a stage or camera segment."""

    min_x: float
    max_x: float
    min_depth: float
    max_depth: float

    def __post_init__(self) -> None:
        for name in ("min_x", "max_x", "min_depth", "max_depth"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        if self.max_x <= self.min_x or self.max_depth <= self.min_depth:
            raise ValueError("stage bounds must have positive area")

    def allowed_centers(self, body: PushBody) -> AABB2:
        allowed = AABB2(
            self.min_x + body.half_width,
            self.max_x - body.half_width,
            self.min_depth + body.half_depth,
            self.max_depth - body.half_depth,
        )
        if allowed.width < 0.0 or allowed.depth < 0.0:
            raise ValueError("push body is larger than the stage bounds")
        return allowed


class SpatialHash:
    """Small deterministic broadphase for world-space combat geometry.

    IDs come from ``entity_id``, ``attack_id``, or ``obstacle_id``.  Callers
    can also pass an explicit key when those IDs share a namespace.  Moving
    items are indexed by ``swept_bounds_2d`` when available, so a hurt volume
    that crossed a query between fixed samples remains discoverable.
    """

    def __init__(self, cell_size: float = 64.0) -> None:
        self.cell_size = _positive(cell_size, "cell_size")
        self._cells: dict[tuple[int, int], set[EntityId]] = {}
        self._entries: dict[EntityId, tuple[object, AABB2, tuple[tuple[int, int], ...]]] = {}

    def clear(self) -> None:
        self._cells.clear()
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def _cells_for(self, bounds: AABB2) -> tuple[tuple[int, int], ...]:
        min_x = math.floor(bounds.min_x / self.cell_size)
        max_x = math.floor((bounds.max_x - EPSILON) / self.cell_size)
        min_d = math.floor(bounds.min_depth / self.cell_size)
        max_d = math.floor((bounds.max_depth - EPSILON) / self.cell_size)
        if bounds.width <= EPSILON:
            max_x = min_x
        if bounds.depth <= EPSILON:
            max_d = min_d
        return tuple((cx, cd) for cx in range(min_x, max_x + 1) for cd in range(min_d, max_d + 1))

    @staticmethod
    def _default_key(item: object) -> EntityId:
        for attribute in ("entity_id", "attack_id", "obstacle_id"):
            if hasattr(item, attribute):
                return getattr(item, attribute)
        raise TypeError("spatial-hash items need an ID attribute or explicit key")

    @staticmethod
    def _default_bounds(item: object) -> AABB2:
        for attribute in ("swept_bounds_2d", "bounds_2d"):
            if hasattr(item, attribute):
                bounds = getattr(item, attribute)
                if isinstance(bounds, AABB2):
                    return bounds
                raise TypeError(f"{attribute} must be an AABB2")
        raise TypeError("spatial-hash items need bounds_2d or explicit bounds")

    def insert(self, item: _T, *, key: EntityId | None = None, bounds: AABB2 | None = None) -> None:
        key = self._default_key(item) if key is None else key
        bounds = self._default_bounds(item) if bounds is None else bounds
        if not isinstance(bounds, AABB2):
            raise TypeError("bounds must be an AABB2")
        if key in self._entries:
            self.remove(key)
        cells = self._cells_for(bounds)
        self._entries[key] = item, bounds, cells
        for cell in cells:
            self._cells.setdefault(cell, set()).add(key)

    def remove(self, key: EntityId) -> bool:
        entry = self._entries.pop(key, None)
        if entry is None:
            return False
        for cell in entry[2]:
            values = self._cells[cell]
            values.discard(key)
            if not values:
                del self._cells[cell]
        return True

    def rebuild(self, items: Iterable[_T], *, key: Callable[[_T], EntityId] | None = None) -> None:
        self.clear()
        for item in items:
            self.insert(item, key=key(item) if key is not None else None)

    def query(self, bounds: AABB2) -> tuple[object, ...]:
        keys: set[EntityId] = set()
        for cell in self._cells_for(bounds):
            keys.update(self._cells.get(cell, ()))
        matches = [
            (key, self._entries[key][0])
            for key in keys
            if self._entries[key][1].intersects(bounds)
        ]
        matches.sort(key=lambda pair: stable_id_key(pair[0]))
        return tuple(item for _, item in matches)


@dataclass(frozen=True, slots=True)
class SweepContact:
    obstacle_id: EntityId
    normal_x: float
    normal_depth: float
    time: float
    x: float
    depth: float


@dataclass(frozen=True, slots=True)
class MovementResult:
    start_x: float
    start_depth: float
    x: float
    depth: float
    requested_x: float
    requested_depth: float
    contacts: tuple[SweepContact, ...] = ()
    started_overlapping: bool = False

    @property
    def applied_x(self) -> float:
        return self.x - self.start_x

    @property
    def applied_depth(self) -> float:
        return self.depth - self.start_depth

    @property
    def blocked_x(self) -> bool:
        return abs(self.applied_x - self.requested_x) > 1.0e-5

    @property
    def blocked_depth(self) -> bool:
        return abs(self.applied_depth - self.requested_depth) > 1.0e-5


def _vertical_overlap(
    bottom_a: float,
    top_a: float,
    bottom_b: float,
    top_b: float,
    *,
    touching: bool = False,
) -> bool:
    if touching:
        return bottom_a <= top_b + EPSILON and bottom_b <= top_a + EPSILON
    return bottom_a < top_b - EPSILON and bottom_b < top_a - EPSILON


def _obstacle_blocks(body: PushBody, obstacle: StageObstacle) -> bool:
    return obstacle.enabled and _vertical_overlap(
        body.elevation,
        body.top_elevation,
        obstacle.min_elevation,
        obstacle.max_elevation,
    )


def _point_inside_strict(x: float, depth: float, bounds: AABB2) -> bool:
    return (
        bounds.min_x + EPSILON < x < bounds.max_x - EPSILON
        and bounds.min_depth + EPSILON < depth < bounds.max_depth - EPSILON
    )


def _depenetrate_point(x: float, depth: float, bounds: AABB2, skin: float) -> tuple[float, float, float, float]:
    candidates = (
        (abs(x - bounds.min_x), bounds.min_x - skin, depth, -1.0, 0.0),
        (abs(bounds.max_x - x), bounds.max_x + skin, depth, 1.0, 0.0),
        (abs(depth - bounds.min_depth), x, bounds.min_depth - skin, 0.0, -1.0),
        (abs(bounds.max_depth - depth), x, bounds.max_depth + skin, 0.0, 1.0),
    )
    _, x, depth, nx, nd = min(candidates, key=lambda item: (item[0], abs(item[3]) < 0.5, item[3], item[4]))
    return x, depth, nx, nd


def _sweep_point_aabb(
    x: float,
    depth: float,
    delta_x: float,
    delta_depth: float,
    bounds: AABB2,
) -> tuple[float, float, float] | None:
    if abs(delta_x) <= EPSILON:
        if x < bounds.min_x or x > bounds.max_x:
            return None
        tx_entry, tx_exit = -math.inf, math.inf
    elif delta_x > 0.0:
        tx_entry = (bounds.min_x - x) / delta_x
        tx_exit = (bounds.max_x - x) / delta_x
    else:
        tx_entry = (bounds.max_x - x) / delta_x
        tx_exit = (bounds.min_x - x) / delta_x

    if abs(delta_depth) <= EPSILON:
        if depth < bounds.min_depth or depth > bounds.max_depth:
            return None
        td_entry, td_exit = -math.inf, math.inf
    elif delta_depth > 0.0:
        td_entry = (bounds.min_depth - depth) / delta_depth
        td_exit = (bounds.max_depth - depth) / delta_depth
    else:
        td_entry = (bounds.max_depth - depth) / delta_depth
        td_exit = (bounds.min_depth - depth) / delta_depth

    entry = max(tx_entry, td_entry)
    exit_time = min(tx_exit, td_exit)
    if entry > exit_time + EPSILON or exit_time < 0.0 or entry < -EPSILON or entry > 1.0 + EPSILON:
        return None

    if tx_entry > td_entry + EPSILON or (
        abs(tx_entry - td_entry) <= EPSILON and abs(delta_x) >= abs(delta_depth)
    ):
        return max(0.0, entry), -1.0 if delta_x > 0.0 else 1.0, 0.0
    return max(0.0, entry), 0.0, -1.0 if delta_depth > 0.0 else 1.0


def _bounds_collision(
    x: float,
    depth: float,
    delta_x: float,
    delta_depth: float,
    allowed: AABB2,
) -> tuple[float, float, float, EntityId] | None:
    candidates: list[tuple[float, float, float, EntityId]] = []
    if delta_x < -EPSILON and x + delta_x < allowed.min_x:
        candidates.append(((allowed.min_x - x) / delta_x, 1.0, 0.0, "stage:left"))
    elif delta_x > EPSILON and x + delta_x > allowed.max_x:
        candidates.append(((allowed.max_x - x) / delta_x, -1.0, 0.0, "stage:right"))
    if delta_depth < -EPSILON and depth + delta_depth < allowed.min_depth:
        candidates.append(((allowed.min_depth - depth) / delta_depth, 0.0, 1.0, "stage:back"))
    elif delta_depth > EPSILON and depth + delta_depth > allowed.max_depth:
        candidates.append(((allowed.max_depth - depth) / delta_depth, 0.0, -1.0, "stage:front"))
    if not candidates:
        return None
    return min(candidates, key=lambda value: (value[0], stable_id_key(value[3])))


def sweep_move(
    body: PushBody,
    delta_x: float,
    delta_depth: float,
    *,
    obstacles: Iterable[StageObstacle] = (),
    bounds: StageBounds | None = None,
    skin: float = 1.0e-4,
    max_slides: int = 4,
) -> MovementResult:
    """Sweep a body through world geometry and return a sliding movement.

    This function is pure: use :func:`move_body` to apply its result.  Obstacles
    lower than an actor's feet are ignored, allowing jumps over short rails.
    """

    delta_x = _finite(delta_x, "delta_x")
    delta_depth = _finite(delta_depth, "delta_depth")
    skin = _positive(skin, "skin", allow_zero=True)
    if max_slides <= 0:
        raise ValueError("max_slides must be positive")

    start_x, start_depth = body.x, body.depth
    x, depth = start_x, start_depth
    contacts: list[SweepContact] = []
    blockers = sorted(
        (obstacle for obstacle in obstacles if _obstacle_blocks(body, obstacle)),
        key=lambda obstacle: stable_id_key(obstacle.obstacle_id),
    )
    expanded = [(obstacle, obstacle.bounds.expanded(body.half_width, body.half_depth)) for obstacle in blockers]
    started_overlapping = False

    # Repair bad spawn points deterministically before the continuous sweep.
    for _ in range(max(1, len(expanded) * 2)):
        repaired = False
        for obstacle, obstacle_bounds in expanded:
            if _point_inside_strict(x, depth, obstacle_bounds):
                started_overlapping = True
                x, depth, nx, nd = _depenetrate_point(x, depth, obstacle_bounds, skin)
                contacts.append(SweepContact(obstacle.obstacle_id, nx, nd, 0.0, x, depth))
                repaired = True
        if not repaired:
            break

    allowed = bounds.allowed_centers(body) if bounds is not None else None
    if allowed is not None:
        clamped_x = min(allowed.max_x, max(allowed.min_x, x))
        clamped_depth = min(allowed.max_depth, max(allowed.min_depth, depth))
        if abs(clamped_x - x) > EPSILON or abs(clamped_depth - depth) > EPSILON:
            started_overlapping = True
            x, depth = clamped_x, clamped_depth

    remaining_x, remaining_depth = delta_x, delta_depth
    elapsed_fraction = 0.0
    remaining_fraction = 1.0
    for _ in range(max_slides):
        if abs(remaining_x) + abs(remaining_depth) <= EPSILON:
            break
        hit: tuple[float, float, float, EntityId] | None = None
        for obstacle, obstacle_bounds in expanded:
            collision = _sweep_point_aabb(x, depth, remaining_x, remaining_depth, obstacle_bounds)
            if collision is None:
                continue
            candidate = collision[0], collision[1], collision[2], obstacle.obstacle_id
            if hit is None or (candidate[0], stable_id_key(candidate[3])) < (hit[0], stable_id_key(hit[3])):
                hit = candidate
        if allowed is not None:
            bound_hit = _bounds_collision(x, depth, remaining_x, remaining_depth, allowed)
            if bound_hit is not None and (
                hit is None
                or (bound_hit[0], stable_id_key(bound_hit[3])) < (hit[0], stable_id_key(hit[3]))
            ):
                hit = bound_hit

        if hit is None:
            x += remaining_x
            depth += remaining_depth
            remaining_x = remaining_depth = 0.0
            break

        local_time, nx, nd, obstacle_id = hit
        local_time = min(1.0, max(0.0, local_time))
        travel = max(0.0, local_time - EPSILON)
        x += remaining_x * travel
        depth += remaining_depth * travel
        world_time = elapsed_fraction + remaining_fraction * local_time
        contacts.append(SweepContact(obstacle_id, nx, nd, world_time, x, depth))

        leftover = 1.0 - local_time
        remaining_x *= leftover
        remaining_depth *= leftover
        # Remove only motion into the surface; retain tangent motion for slide.
        inward = remaining_x * nx + remaining_depth * nd
        if inward < 0.0:
            remaining_x -= inward * nx
            remaining_depth -= inward * nd
        elapsed_fraction = world_time
        remaining_fraction *= leftover

    if allowed is not None:
        x = min(allowed.max_x, max(allowed.min_x, x))
        depth = min(allowed.max_depth, max(allowed.min_depth, depth))
    return MovementResult(
        start_x,
        start_depth,
        x,
        depth,
        delta_x,
        delta_depth,
        tuple(contacts),
        started_overlapping,
    )


def move_body(body: PushBody, delta_x: float, delta_depth: float, **kwargs: object) -> MovementResult:
    """Apply :func:`sweep_move` to a mutable ``PushBody``."""

    result = sweep_move(body, delta_x, delta_depth, **kwargs)
    body.x, body.depth = result.x, result.depth
    return result


@dataclass(frozen=True, slots=True)
class SeparationResult:
    iterations: int
    resolved_pairs: tuple[tuple[EntityId, EntityId], ...]
    moved_ids: tuple[EntityId, ...]
    max_remaining_overlap: float


def _push_layers_overlap(a: PushBody, b: PushBody) -> bool:
    return bool(a.mask & b.layer) and bool(b.mask & a.layer)


def _pair_penetration(a: PushBody, b: PushBody, spacing: float) -> tuple[float, float]:
    return (
        a.half_width + b.half_width + spacing - abs(b.x - a.x),
        a.half_depth + b.half_depth + spacing - abs(b.depth - a.depth),
    )


def _ordered_push_pair(a: PushBody, b: PushBody) -> tuple[PushBody, PushBody]:
    if stable_id_key(a.entity_id) <= stable_id_key(b.entity_id):
        return a, b
    return b, a


def separate_push_bodies(
    bodies: Sequence[PushBody],
    *,
    crowd_spacing: float = 0.0,
    bounds: StageBounds | None = None,
    obstacles: Iterable[StageObstacle] = (),
    iterations: int = 16,
    tolerance: float = 1.0e-3,
    cell_size: float = 64.0,
) -> SeparationResult:
    """Resolve actor stacking with deterministic mass-weighted pushback.

    The supplied bodies are mutated.  Identical inputs produce identical
    positions regardless of input sequence order.  Disabled, vertically
    separated, and mask-incompatible bodies do not push each other.
    """

    crowd_spacing = _positive(crowd_spacing, "crowd_spacing", allow_zero=True)
    tolerance = _positive(tolerance, "tolerance", allow_zero=True)
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    obstacle_tuple = tuple(obstacles)
    active = sorted((body for body in bodies if body.enabled), key=lambda body: stable_id_key(body.entity_id))
    if len({body.entity_id for body in active}) != len(active):
        raise ValueError("push-body entity IDs must be unique")

    moved: set[EntityId] = set()
    resolved: set[tuple[EntityId, EntityId]] = set()
    completed_iterations = 0
    for pass_index in range(iterations):
        completed_iterations = pass_index + 1
        broadphase = SpatialHash(cell_size)
        for body in active:
            broadphase.insert(body, bounds=body.bounds_2d.expanded(crowd_spacing * 0.5))

        pairs: list[tuple[PushBody, PushBody]] = []
        seen: set[tuple[EntityId, EntityId]] = set()
        for a in active:
            query_bounds = a.bounds_2d.expanded(crowd_spacing)
            for candidate in broadphase.query(query_bounds):
                if not isinstance(candidate, PushBody) or candidate is a:
                    continue
                first, second = _ordered_push_pair(a, candidate)
                pair_id = first.entity_id, second.entity_id
                if pair_id not in seen:
                    seen.add(pair_id)
                    pairs.append((first, second))
        pairs.sort(key=lambda pair: (stable_id_key(pair[0].entity_id), stable_id_key(pair[1].entity_id)))

        max_correction = 0.0
        for a, b in pairs:
            if not _push_layers_overlap(a, b) or not _vertical_overlap(
                a.elevation,
                a.top_elevation,
                b.elevation,
                b.top_elevation,
            ):
                continue
            overlap_x, overlap_depth = _pair_penetration(a, b, crowd_spacing)
            if overlap_x <= tolerance or overlap_depth <= tolerance:
                continue

            # The least-penetrating axis is the most natural escape direction.
            axis_x = overlap_x <= overlap_depth
            correction = (overlap_x if axis_x else overlap_depth) + tolerance
            inv_a = (1.0 / a.mass) if a.movable else 0.0
            inv_b = (1.0 / b.mass) if b.movable else 0.0
            inv_total = inv_a + inv_b
            if inv_total <= EPSILON:
                continue

            if axis_x:
                difference = b.x - a.x
            else:
                difference = b.depth - a.depth
            direction = 1.0 if difference > EPSILON else -1.0 if difference < -EPSILON else 1.0
            amount_a = correction * (inv_a / inv_total)
            amount_b = correction * (inv_b / inv_total)
            delta_a = (-direction * amount_a, 0.0) if axis_x else (0.0, -direction * amount_a)
            delta_b = (direction * amount_b, 0.0) if axis_x else (0.0, direction * amount_b)

            if amount_a > 0.0:
                move_body(a, *delta_a, obstacles=obstacle_tuple, bounds=bounds)
                moved.add(a.entity_id)
            if amount_b > 0.0:
                move_body(b, *delta_b, obstacles=obstacle_tuple, bounds=bounds)
                moved.add(b.entity_id)
            resolved.add((a.entity_id, b.entity_id))
            max_correction = max(max_correction, correction)
        if max_correction <= tolerance:
            break

    max_remaining = 0.0
    for index, a in enumerate(active):
        for b in active[index + 1 :]:
            if not _push_layers_overlap(a, b) or not _vertical_overlap(a.elevation, a.top_elevation, b.elevation, b.top_elevation):
                continue
            overlap_x, overlap_depth = _pair_penetration(a, b, crowd_spacing)
            if overlap_x > 0.0 and overlap_depth > 0.0:
                max_remaining = max(max_remaining, min(overlap_x, overlap_depth))
    return SeparationResult(
        completed_iterations,
        tuple(sorted(resolved, key=lambda pair: (stable_id_key(pair[0]), stable_id_key(pair[1])))),
        tuple(sorted(moved, key=stable_id_key)),
        max_remaining,
    )


@dataclass(frozen=True, slots=True)
class HitstopEvent:
    attack_id: EntityId
    attacker_id: EntityId
    target_id: EntityId
    seconds: float


@dataclass(frozen=True, slots=True)
class CameraImpactEvent:
    attack_id: EntityId
    target_id: EntityId
    world_x: float
    world_depth: float
    direction_x: float
    direction_depth: float
    strength: float
    seconds: float


@dataclass(frozen=True, slots=True)
class AttackResult:
    attack_id: EntityId
    attacker_id: EntityId
    target_id: EntityId
    damage: float
    stun: float
    knockback_x: float
    knockback_depth: float
    launch_elevation: float
    distance_squared: float
    contact_x: float
    contact_depth: float
    hitstop: HitstopEvent
    camera: CameraImpactEvent


@dataclass(frozen=True, slots=True)
class AttackEvaluation:
    """One target's deterministic acceptance or rejection record."""

    attack_id: EntityId
    target_id: EntityId
    accepted: bool
    reason: AttackRejectionReason | None
    horizontal_gap: float
    depth_gap: float
    elevation_gap: float
    missing_tags: frozenset[str] = field(default_factory=frozenset)
    blocked_tags: frozenset[str] = field(default_factory=frozenset)
    rehit_remaining: float = 0.0


@dataclass(frozen=True, slots=True)
class AttackQueryReport:
    """Detailed attack contacts plus an evaluation for every broadphase target."""

    results: tuple[AttackResult, ...]
    evaluations: tuple[AttackEvaluation, ...]

    @property
    def rejected(self) -> tuple[AttackEvaluation, ...]:
        return tuple(evaluation for evaluation in self.evaluations if not evaluation.accepted)


def _axis_sweep_interval(relative_start: float, relative_delta: float, half_extent: float) -> tuple[float, float] | None:
    """Return the fixed-sample interval where one relative axis overlaps."""

    if abs(relative_delta) <= EPSILON:
        if relative_start < -half_extent - EPSILON or relative_start > half_extent + EPSILON:
            return None
        return 0.0, 1.0
    first = (-half_extent - relative_start) / relative_delta
    second = (half_extent - relative_start) / relative_delta
    entry = max(0.0, min(first, second))
    exit_time = min(1.0, max(first, second))
    if entry > exit_time + EPSILON:
        return None
    return entry, exit_time


def _attack_planar_intervals(
    hitbox: HitBox,
    hurtbox: HurtBox,
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    hit_start_x, hit_start_depth = hitbox.sweep_start
    hurt_start_x, hurt_start_depth = hurtbox.sweep_start
    relative_x = hit_start_x - hurt_start_x
    relative_depth = hit_start_depth - hurt_start_depth
    relative_delta_x = (hitbox.x - hit_start_x) - (hurtbox.x - hurt_start_x)
    relative_delta_depth = (hitbox.depth - hit_start_depth) - (hurtbox.depth - hurt_start_depth)
    horizontal = _axis_sweep_interval(
        relative_x,
        relative_delta_x,
        hitbox.half_width + hurtbox.half_width,
    )
    depth = _axis_sweep_interval(
        relative_depth,
        relative_delta_depth,
        hitbox.half_depth + hitbox.depth_tolerance + hurtbox.half_depth,
    )
    return horizontal, depth


def _attack_planar_rejection(hitbox: HitBox, hurtbox: HurtBox) -> AttackRejectionReason | None:
    horizontal, depth = _attack_planar_intervals(hitbox, hurtbox)
    if horizontal is None:
        return AttackRejectionReason.HORIZONTAL_RANGE
    if depth is None:
        return AttackRejectionReason.DEPTH_RANGE
    if max(horizontal[0], depth[0]) <= min(horizontal[1], depth[1]) + EPSILON:
        return None
    # Both axes overlap somewhere in the sample, but not at the same time.
    # Attribute the miss to the axis that had already left range.
    if horizontal[1] < depth[0]:
        return AttackRejectionReason.HORIZONTAL_RANGE
    return AttackRejectionReason.DEPTH_RANGE


def _attack_swept_intersects(hitbox: HitBox, hurtbox: HurtBox) -> bool:
    """Return whether x/depth volumes overlap at one common sample time."""

    return _attack_planar_rejection(hitbox, hurtbox) is None


def _attack_is_front_facing(hitbox: HitBox, hurtbox: HurtBox) -> bool:
    """Reject a rear-side target even if its broad hurtbox touches a fist."""

    if hitbox.facing_x == 0.0:
        return True
    origin_x, _ = hitbox.front_origin
    # Use the hurtbox's nearest forward edge instead of only its centre. This
    # still permits a body that honestly overlaps the fighter's front plane.
    # Check both samples so a target that crossed the fist from front to rear
    # during an active window still registers as a legitimate landed blow.
    sample_x = (hurtbox.sweep_start[0], hurtbox.x)
    for x in sample_x:
        forward_edge = x + hurtbox.half_width if hitbox.facing_x > 0.0 else x - hurtbox.half_width
        if (forward_edge - origin_x) * hitbox.facing_x >= -hitbox.rear_tolerance:
            return True
    return False


_DEFEATED_TAGS = frozenset({"dead", "defeated", "eliminated"})
_DOWNED_TAGS = frozenset({"down", "downed", "knocked_down", "prone"})
_BLOCK_TAGS = frozenset({"block", "blocked", "blocking", "guarding", "parry"})
_ARMOR_TAGS = frozenset({"armor", "armored", "armoured", "super_armor"})


def _normalized_tags(tags: Iterable[str]) -> frozenset[str]:
    return frozenset(str(tag).strip().lower().replace("-", "_").replace(" ", "_") for tag in tags)


def _blocked_tag_rejection(tags: frozenset[str]) -> AttackRejectionReason:
    normalized = _normalized_tags(tags)
    if normalized.intersection(_DOWNED_TAGS):
        return AttackRejectionReason.DOWNED
    if normalized.intersection(_BLOCK_TAGS):
        return AttackRejectionReason.BLOCKED
    if normalized.intersection(_ARMOR_TAGS):
        return AttackRejectionReason.ARMOR
    return AttackRejectionReason.BLOCKED_TAGS


def _interval_gap(first_min: float, first_max: float, second_min: float, second_max: float) -> float:
    return max(0.0, first_min - second_max, second_min - first_max)


def _attack_evaluation_gaps(hitbox: HitBox, hurtbox: HurtBox) -> tuple[float, float, float]:
    hit_swept = hitbox.swept_bounds_2d
    hurt_swept = hurtbox.swept_bounds_2d
    return (
        _interval_gap(hit_swept.min_x, hit_swept.max_x, hurt_swept.min_x, hurt_swept.max_x),
        _interval_gap(
            hit_swept.min_depth,
            hit_swept.max_depth,
            hurt_swept.min_depth,
            hurt_swept.max_depth,
        ),
        _interval_gap(
            hitbox.elevation,
            hitbox.top_elevation,
            hurtbox.elevation,
            hurtbox.top_elevation,
        ),
    )


def _attack_sort_key(hitbox: HitBox, hurtbox: HurtBox) -> tuple[object, ...]:
    if hitbox.facing_x != 0.0:
        origin_x, origin_depth = hitbox.front_origin
        forward_samples = (
            (hurtbox.sweep_start[0] - origin_x) * hitbox.facing_x,
            (hurtbox.x - origin_x) * hitbox.facing_x,
        )
        positive_samples = [sample for sample in forward_samples if sample >= -hitbox.rear_tolerance]
        forward_distance = max(0.0, min(positive_samples, default=max(forward_samples)))
        lane_distance = abs(hurtbox.depth - origin_depth)
        # A clear lane wins over a marginally closer target in the next lane;
        # the weight keeps normal punches intuitively nearest-front after that.
        intent_distance = forward_distance + lane_distance * 1.5
        return intent_distance, lane_distance, forward_distance, stable_id_key(hurtbox.entity_id)
    dx = hurtbox.x - hitbox.x
    dd = hurtbox.depth - hitbox.depth
    return dx * dx + dd * dd, abs(dd), stable_id_key(hurtbox.entity_id)


@dataclass(slots=True)
class _AttackEvaluationDraft:
    hurtbox: HurtBox
    reason: AttackRejectionReason | None
    missing_tags: frozenset[str] = field(default_factory=frozenset)
    blocked_tags: frozenset[str] = field(default_factory=frozenset)
    rehit_remaining: float = 0.0


def _attack_rejection(
    hitbox: HitBox,
    hurtbox: HurtBox,
    *,
    already_hit: frozenset[EntityId],
    hit_counts: Mapping[EntityId, int],
    last_hit_times: Mapping[EntityId, float],
    now: float | None,
    predicate: Callable[[HurtBox], bool] | None = None,
) -> tuple[
    AttackRejectionReason | None,
    frozenset[str],
    frozenset[str],
    float,
]:
    if not hitbox.enabled:
        return AttackRejectionReason.INACTIVE, frozenset(), frozenset(), 0.0
    if not hurtbox.enabled:
        return AttackRejectionReason.DISABLED, frozenset(), frozenset(), 0.0
    if hurtbox.defeated or _normalized_tags(hurtbox.tags).intersection(_DEFEATED_TAGS):
        return AttackRejectionReason.DEFEATED, frozenset(), frozenset(), 0.0
    if not hurtbox.vulnerable:
        return AttackRejectionReason.INVULNERABLE, frozenset(), frozenset(), 0.0
    if hurtbox.entity_id == hitbox.owner_id:
        return AttackRejectionReason.SELF, frozenset(), frozenset(), 0.0
    if hurtbox.entity_id in already_hit:
        return AttackRejectionReason.ALREADY_HIT, frozenset(), frozenset(), 0.0

    try:
        hit_count = max(0, int(hit_counts.get(hurtbox.entity_id, 0)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"hit count for {hurtbox.entity_id!r} must be an integer") from exc
    has_last_hit = hurtbox.entity_id in last_hit_times
    if has_last_hit:
        hit_count = max(1, hit_count)
    if hitbox.max_hits_per_target is not None and hit_count >= hitbox.max_hits_per_target:
        return AttackRejectionReason.ALREADY_HIT, frozenset(), frozenset(), 0.0
    if hitbox.rehit_delay > 0.0 and has_last_hit and now is not None:
        last_hit = _finite(last_hit_times[hurtbox.entity_id], f"last hit time for {hurtbox.entity_id!r}")
        remaining = max(0.0, hitbox.rehit_delay - (now - last_hit))
        if remaining > EPSILON:
            return AttackRejectionReason.REHIT_DELAY, frozenset(), frozenset(), remaining

    if not hitbox.friendly_fire and hurtbox.team == hitbox.team:
        return AttackRejectionReason.WRONG_FACTION, frozenset(), frozenset(), 0.0
    if hurtbox.is_grounded and not hitbox.hit_grounded:
        return AttackRejectionReason.GROUNDED_MISMATCH, frozenset(), frozenset(), 0.0
    if not hurtbox.is_grounded and not hitbox.hit_airborne:
        return AttackRejectionReason.AIRBORNE_MISMATCH, frozenset(), frozenset(), 0.0
    missing_tags = hitbox.required_tags.difference(hurtbox.tags)
    if missing_tags:
        return AttackRejectionReason.REQUIRED_TAGS, frozenset(missing_tags), frozenset(), 0.0
    blocked_tags = hitbox.blocked_tags.intersection(hurtbox.tags)
    if blocked_tags:
        blocked = frozenset(blocked_tags)
        return _blocked_tag_rejection(blocked), frozenset(), blocked, 0.0
    if not _attack_is_front_facing(hitbox, hurtbox):
        return AttackRejectionReason.BEHIND, frozenset(), frozenset(), 0.0
    planar_rejection = _attack_planar_rejection(hitbox, hurtbox)
    if planar_rejection is not None:
        return planar_rejection, frozenset(), frozenset(), 0.0
    if not _vertical_overlap(
        hitbox.elevation,
        hitbox.top_elevation,
        hurtbox.elevation,
        hurtbox.top_elevation,
        touching=True,
    ):
        return AttackRejectionReason.ELEVATION_RANGE, frozenset(), frozenset(), 0.0
    if predicate is not None and not predicate(hurtbox):
        return AttackRejectionReason.PREDICATE, frozenset(), frozenset(), 0.0
    return None, frozenset(), frozenset(), 0.0


def _attack_result(hitbox: HitBox, hurtbox: HurtBox) -> AttackResult:
    dx = hurtbox.x - hitbox.x
    dd = hurtbox.depth - hitbox.depth
    length = math.hypot(dx, dd)
    if length <= EPSILON:
        direction_x, direction_depth = (1.0, 0.0)
    else:
        direction_x, direction_depth = dx / length, dd / length
    contact_x = min(hitbox.x + hitbox.half_width, max(hitbox.x - hitbox.half_width, hurtbox.x))
    contact_depth = min(
        hitbox.depth + hitbox.half_depth + hitbox.depth_tolerance,
        max(hitbox.depth - hitbox.half_depth - hitbox.depth_tolerance, hurtbox.depth),
    )
    hitstop = HitstopEvent(hitbox.attack_id, hitbox.owner_id, hurtbox.entity_id, hitbox.hitstop_seconds)
    camera = CameraImpactEvent(
        hitbox.attack_id,
        hurtbox.entity_id,
        contact_x,
        contact_depth,
        direction_x,
        direction_depth,
        hitbox.camera_strength,
        hitbox.camera_seconds,
    )
    return AttackResult(
        hitbox.attack_id,
        hitbox.owner_id,
        hurtbox.entity_id,
        hitbox.damage,
        hitbox.stun,
        hitbox.knockback_x,
        hitbox.knockback_depth,
        hitbox.launch_elevation,
        dx * dx + dd * dd,
        contact_x,
        contact_depth,
        hitstop,
        camera,
    )


def query_attack_detailed(
    hitbox: HitBox,
    hurtboxes: Iterable[HurtBox] | SpatialHash,
    *,
    already_hit: Iterable[EntityId] = (),
    predicate: Callable[[HurtBox], bool] | None = None,
    hit_counts: Mapping[EntityId, int] | None = None,
    last_hit_times: Mapping[EntityId, float] | None = None,
    now: float | None = None,
) -> AttackQueryReport:
    """Return contacts and stable per-target rejection diagnostics.

    Directional strikes first reject rear-side targets, then choose the best
    front/lane intent; neutral volumes remain nearest-first.  Both use stable
    IDs as a final tie-breaker.  Swept hit/hurt samples make a crossing inside
    an active window count even when neither final rectangle overlaps.  Target
    caps are applied after every other rule so capped candidates remain visible
    to combat debug tooling.  ``hit_counts`` and ``last_hit_times`` are caller-
    owned execution memory; this function never mutates either mapping.
    """

    if isinstance(hurtboxes, SpatialHash):
        candidates = [
            candidate
            for candidate in hurtboxes.query(hitbox.swept_bounds_2d)
            if isinstance(candidate, HurtBox)
        ]
    else:
        candidates = list(hurtboxes)
    candidates.sort(key=lambda hurtbox: _attack_sort_key(hitbox, hurtbox))

    blocked = frozenset(already_hit)
    counts = {} if hit_counts is None else hit_counts
    last_times = {} if last_hit_times is None else last_hit_times
    now_value = None if now is None else _finite(now, "now")
    drafts: list[_AttackEvaluationDraft] = []
    for hurtbox in candidates:
        reason, missing_tags, blocked_tags, rehit_remaining = _attack_rejection(
            hitbox,
            hurtbox,
            already_hit=blocked,
            hit_counts=counts,
            last_hit_times=last_times,
            now=now_value,
            predicate=predicate,
        )
        drafts.append(
            _AttackEvaluationDraft(
                hurtbox,
                reason,
                missing_tags,
                blocked_tags,
                rehit_remaining,
            )
        )

    accepted_indices = [index for index, draft in enumerate(drafts) if draft.reason is None]
    if hitbox.max_targets is not None:
        for index in accepted_indices[hitbox.max_targets :]:
            drafts[index].reason = AttackRejectionReason.TARGET_CAP
        accepted_indices = accepted_indices[: hitbox.max_targets]

    results = tuple(_attack_result(hitbox, drafts[index].hurtbox) for index in accepted_indices)
    evaluations: list[AttackEvaluation] = []
    for draft in drafts:
        horizontal_gap, depth_gap, elevation_gap = _attack_evaluation_gaps(hitbox, draft.hurtbox)
        evaluations.append(
            AttackEvaluation(
                hitbox.attack_id,
                draft.hurtbox.entity_id,
                draft.reason is None,
                draft.reason,
                horizontal_gap,
                depth_gap,
                elevation_gap,
                draft.missing_tags,
                draft.blocked_tags,
                draft.rehit_remaining,
            )
        )
    return AttackQueryReport(results, tuple(evaluations))


def query_attack(
    hitbox: HitBox,
    hurtboxes: Iterable[HurtBox] | SpatialHash,
    *,
    already_hit: Iterable[EntityId] = (),
    predicate: Callable[[HurtBox], bool] | None = None,
) -> tuple[AttackResult, ...]:
    """Backward-compatible contact-only wrapper around the detailed query."""

    return query_attack_detailed(
        hitbox,
        hurtboxes,
        already_hit=already_hit,
        predicate=predicate,
    ).results


__all__ = [
    "AABB2",
    "AttackEvaluation",
    "AttackQueryReport",
    "AttackRejectionReason",
    "AttackResult",
    "CameraImpactEvent",
    "HitBox",
    "HitstopEvent",
    "HurtBox",
    "MovementResult",
    "PushBody",
    "SeparationResult",
    "SpatialHash",
    "StageBounds",
    "StageObstacle",
    "SweepContact",
    "move_body",
    "query_attack",
    "query_attack_detailed",
    "separate_push_bodies",
    "stable_id_key",
    "sweep_move",
]
