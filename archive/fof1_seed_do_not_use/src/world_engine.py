"""Reusable 2.5D world, projection, collision, and camera primitives.

The game simulation lives on a flat floor described by ``x`` (stage progress)
and ``depth`` (movement toward/away from the viewer). ``elevation`` is a third,
independent value used for jumps, knock-ups, and projectiles.  Rendering uses an
orthographic or lightly-oblique projection, so billboard sprites always face the
camera and deliberately remain the same size at every depth.

The module is renderer-agnostic.  Pygame callers can use ``ProjectedPoint.xy``
as the sprite's feet position and sort actors with ``projection.depth_sort_key``.
All classes accept plain dictionaries through ``from_dict`` for stage-data files.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any, Literal


EPSILON = 1.0e-6


def _finite(value: float, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _clamp(value: float, low: float, high: float) -> float:
    if low > high:
        midpoint = (low + high) * 0.5
        return midpoint
    return max(low, min(high, value))


def _move_toward(value: float, target: float, maximum_delta: float) -> float:
    if value < target:
        return min(target, value + maximum_delta)
    return max(target, value - maximum_delta)


@dataclass(frozen=True, slots=True)
class WorldPoint:
    """A point in beat-em-up simulation space.

    ``depth`` is the grounded lane coordinate. ``elevation`` never changes the
    point's collision footprint or draw order, which keeps jumping actors aligned
    with enemies on the floor beneath them.
    """

    x: float
    depth: float
    elevation: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "depth", _finite(self.depth, "depth"))
        object.__setattr__(self, "elevation", _finite(self.elevation, "elevation"))

    def moved(self, dx: float = 0.0, ddepth: float = 0.0, delevation: float = 0.0) -> WorldPoint:
        return WorldPoint(self.x + dx, self.depth + ddepth, self.elevation + delevation)

    def with_elevation(self, elevation: float) -> WorldPoint:
        return WorldPoint(self.x, self.depth, elevation)


@dataclass(frozen=True, slots=True)
class ProjectedPoint:
    """Screen-space result plus stable rendering metadata for one world point."""

    x: float
    y: float
    world_depth: float
    elevation: float
    draw_order: float
    sprite_scale: float = 1.0
    sprite_rotation_degrees: float = 0.0

    @property
    def xy(self) -> tuple[float, float]:
        return self.x, self.y

    @property
    def pixel_xy(self) -> tuple[int, int]:
        return int(round(self.x)), int(round(self.y))


ProjectionMode = Literal["orthographic", "oblique", "oblique_orthographic"]


@dataclass(frozen=True, slots=True)
class ProjectionConfig:
    """Configuration for a camera-facing sprite projection.

    Orthographic mode maps depth only to screen Y. Oblique modes additionally
    shear screen X by ``oblique_x_per_depth`` to reveal more of 3D scenery
    while retaining unscaled, unrotated sprites.
    """

    mode: ProjectionMode = "orthographic"
    screen_origin_x: float = 0.0
    floor_screen_y: float = 235.0
    pixels_per_world_x: float = 1.0
    pixels_per_depth: float = 1.0
    pixels_per_elevation: float = 1.0
    oblique_x_per_depth: float = 0.0
    pixel_snap: bool = True

    def __post_init__(self) -> None:
        if self.mode not in {"orthographic", "oblique", "oblique_orthographic"}:
            raise ValueError("mode must be orthographic or oblique")
        for name in ("screen_origin_x", "floor_screen_y", "oblique_x_per_depth"):
            object.__setattr__(self, name, _finite(getattr(self, name), name))
        for name in ("pixels_per_world_x", "pixels_per_depth", "pixels_per_elevation"):
            value = _finite(getattr(self, name), name)
            if value <= 0.0:
                raise ValueError(f"{name} must be greater than zero")
            object.__setattr__(self, name, value)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProjectionConfig:
        allowed = {field for field in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in allowed})


class BeatEmUpProjection:
    """Projects floor-space actors without perspective scaling.

    A sprite is rendered as a billboard anchored at the projected feet point.
    Regardless of world depth, ``ProjectedPoint.sprite_scale`` is always ``1``
    and ``sprite_rotation_degrees`` is always ``0``.
    """

    def __init__(self, config: ProjectionConfig | None = None) -> None:
        self.config = config or ProjectionConfig()

    def project(
        self,
        point: WorldPoint,
        *,
        camera_x: float = 0.0,
        camera_depth: float = 0.0,
        screen_shake: tuple[float, float] = (0.0, 0.0),
    ) -> ProjectedPoint:
        camera_x = _finite(camera_x, "camera_x")
        camera_depth = _finite(camera_depth, "camera_depth")
        shake_x = _finite(screen_shake[0], "screen_shake.x")
        shake_y = _finite(screen_shake[1], "screen_shake.y")
        cfg = self.config
        depth_delta = point.depth - camera_depth
        shear = cfg.oblique_x_per_depth if cfg.mode != "orthographic" else 0.0
        screen_x = (
            cfg.screen_origin_x
            + (point.x - camera_x) * cfg.pixels_per_world_x
            + depth_delta * shear
            + shake_x
        )
        screen_y = (
            cfg.floor_screen_y
            + depth_delta * cfg.pixels_per_depth
            - point.elevation * cfg.pixels_per_elevation
            + shake_y
        )
        if cfg.pixel_snap:
            screen_x = float(round(screen_x))
            screen_y = float(round(screen_y))
        return ProjectedPoint(
            x=screen_x,
            y=screen_y,
            world_depth=point.depth,
            elevation=point.elevation,
            draw_order=point.depth,
            sprite_scale=1.0,
            sprite_rotation_degrees=0.0,
        )

    def project_shadow(
        self,
        point: WorldPoint,
        *,
        camera_x: float = 0.0,
        camera_depth: float = 0.0,
        screen_shake: tuple[float, float] = (0.0, 0.0),
    ) -> ProjectedPoint:
        """Project the floor point directly below an elevated actor."""

        return self.project(
            point.with_elevation(0.0),
            camera_x=camera_x,
            camera_depth=camera_depth,
            screen_shake=screen_shake,
        )

    def project_many(
        self,
        points: Iterable[WorldPoint],
        *,
        camera_x: float = 0.0,
        camera_depth: float = 0.0,
        screen_shake: tuple[float, float] = (0.0, 0.0),
    ) -> tuple[ProjectedPoint, ...]:
        return tuple(
            self.project(
                point,
                camera_x=camera_x,
                camera_depth=camera_depth,
                screen_shake=screen_shake,
            )
            for point in points
        )

    def unproject_floor(
        self,
        screen_x: float,
        screen_y: float,
        *,
        elevation: float = 0.0,
        camera_x: float = 0.0,
        camera_depth: float = 0.0,
        screen_shake: tuple[float, float] = (0.0, 0.0),
    ) -> WorldPoint:
        """Invert a projected point when its elevation is known."""

        cfg = self.config
        shake_x, shake_y = screen_shake
        depth_delta = (
            float(screen_y) - cfg.floor_screen_y - float(shake_y) + float(elevation) * cfg.pixels_per_elevation
        ) / cfg.pixels_per_depth
        shear = cfg.oblique_x_per_depth if cfg.mode != "orthographic" else 0.0
        world_x = (
            float(screen_x)
            - cfg.screen_origin_x
            - float(shake_x)
            - depth_delta * shear
        ) / cfg.pixels_per_world_x + float(camera_x)
        return WorldPoint(world_x, depth_delta + float(camera_depth), float(elevation))

    @staticmethod
    def depth_sort_key(point: WorldPoint, layer: int = 0) -> tuple[float, int, float]:
        """Back-to-front feet ordering; elevation intentionally has no effect."""

        return point.depth, int(layer), point.x

    @staticmethod
    def sprite_scale_at_depth(_depth: float) -> float:
        """Billboards never shrink or grow as their lane depth changes."""

        return 1.0


Rail = tuple[tuple[float, float], ...]


def _normalise_rail(points: Iterable[Sequence[float]], label: str) -> Rail:
    rail = tuple((_finite(point[0], f"{label}.x"), _finite(point[1], f"{label}.depth")) for point in points)
    if not rail:
        raise ValueError(f"{label} must contain at least one point")
    rail = tuple(sorted(rail, key=lambda point: point[0]))
    if any(right[0] - left[0] <= EPSILON for left, right in zip(rail, rail[1:])):
        raise ValueError(f"{label} x values must be unique")
    return rail


def _sample_rail(rail: Rail, x: float) -> float:
    if len(rail) == 1 or x <= rail[0][0]:
        return rail[0][1]
    if x >= rail[-1][0]:
        return rail[-1][1]
    for left, right in zip(rail, rail[1:]):
        if left[0] <= x <= right[0]:
            amount = (x - left[0]) / (right[0] - left[0])
            return left[1] + (right[1] - left[1]) * amount
    return rail[-1][1]


@dataclass(frozen=True, slots=True)
class WalkableRegion:
    """A floor strip bounded by piecewise-linear back and front guard rails."""

    x_min: float
    x_max: float
    back_rail: Rail
    front_rail: Rail
    name: str = "floor"
    priority: int = 0

    def __post_init__(self) -> None:
        x_min = _finite(self.x_min, "x_min")
        x_max = _finite(self.x_max, "x_max")
        if x_max <= x_min:
            raise ValueError("x_max must be greater than x_min")
        back = _normalise_rail(self.back_rail, "back_rail")
        front = _normalise_rail(self.front_rail, "front_rail")
        sample_xs = {x_min, x_max, *(point[0] for point in back), *(point[0] for point in front)}
        if any(_sample_rail(back, x) > _sample_rail(front, x) for x in sample_xs if x_min <= x <= x_max):
            raise ValueError("back_rail must not cross in front of front_rail")
        object.__setattr__(self, "x_min", x_min)
        object.__setattr__(self, "x_max", x_max)
        object.__setattr__(self, "back_rail", back)
        object.__setattr__(self, "front_rail", front)
        object.__setattr__(self, "priority", int(self.priority))

    @classmethod
    def rectangular(
        cls,
        x_min: float,
        x_max: float,
        depth_min: float,
        depth_max: float,
        *,
        name: str = "floor",
        priority: int = 0,
    ) -> WalkableRegion:
        return cls(
            x_min=x_min,
            x_max=x_max,
            back_rail=((x_min, depth_min), (x_max, depth_min)),
            front_rail=((x_min, depth_max), (x_max, depth_max)),
            name=name,
            priority=priority,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WalkableRegion:
        if "back_rail" in data and "front_rail" in data:
            back = tuple(tuple(point) for point in data["back_rail"])
            front = tuple(tuple(point) for point in data["front_rail"])
        else:
            back = ((data["x_min"], data["depth_min"]), (data["x_max"], data["depth_min"]))
            front = ((data["x_min"], data["depth_max"]), (data["x_max"], data["depth_max"]))
        return cls(
            x_min=data["x_min"],
            x_max=data["x_max"],
            back_rail=back,
            front_rail=front,
            name=str(data.get("name", "floor")),
            priority=int(data.get("priority", 0)),
        )

    def depth_bounds(self, x: float, radius: float = 0.0) -> tuple[float, float]:
        x = _clamp(float(x), self.x_min, self.x_max)
        radius = max(0.0, float(radius))
        back = _sample_rail(self.back_rail, x) + radius
        front = _sample_rail(self.front_rail, x) - radius
        if back > front:
            midpoint = (back + front) * 0.5
            return midpoint, midpoint
        return back, front

    def contains(self, point: WorldPoint, radius: float = 0.0) -> bool:
        radius = max(0.0, float(radius))
        if not self.x_min + radius <= point.x <= self.x_max - radius:
            return False
        back, front = self.depth_bounds(point.x, radius)
        return back <= point.depth <= front

    def clamp(self, point: WorldPoint, radius: float = 0.0) -> WorldPoint:
        radius = max(0.0, float(radius))
        low_x = self.x_min + radius
        high_x = self.x_max - radius
        x = _clamp(point.x, low_x, high_x)
        back, front = self.depth_bounds(x, radius)
        return WorldPoint(x, _clamp(point.depth, back, front), point.elevation)


@dataclass(frozen=True, slots=True)
class RectObstacle:
    """An axis-aligned solid footprint on the stage floor."""

    x_min: float
    x_max: float
    depth_min: float
    depth_max: float
    name: str = "obstacle"

    def __post_init__(self) -> None:
        for field_name in ("x_min", "x_max", "depth_min", "depth_max"):
            object.__setattr__(self, field_name, _finite(getattr(self, field_name), field_name))
        if self.x_max <= self.x_min or self.depth_max <= self.depth_min:
            raise ValueError("obstacle maximums must be greater than minimums")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RectObstacle:
        return cls(
            x_min=data["x_min"],
            x_max=data["x_max"],
            depth_min=data["depth_min"],
            depth_max=data["depth_max"],
            name=str(data.get("name", "obstacle")),
        )

    def contains(self, point: WorldPoint, radius: float = 0.0) -> bool:
        radius = max(0.0, float(radius))
        return (
            self.x_min - radius <= point.x <= self.x_max + radius
            and self.depth_min - radius <= point.depth <= self.depth_max + radius
        )

    @property
    def minimum_span(self) -> float:
        return min(self.x_max - self.x_min, self.depth_max - self.depth_min)

    def escape_candidates(self, point: WorldPoint, radius: float = 0.0) -> tuple[WorldPoint, ...]:
        radius = max(0.0, float(radius))
        return (
            WorldPoint(self.x_min - radius - EPSILON, point.depth, point.elevation),
            WorldPoint(self.x_max + radius + EPSILON, point.depth, point.elevation),
            WorldPoint(point.x, self.depth_min - radius - EPSILON, point.elevation),
            WorldPoint(point.x, self.depth_max + radius + EPSILON, point.elevation),
        )


@dataclass(frozen=True, slots=True)
class StageGeometry:
    """Walkable floor regions, guard rails, and solid obstacle footprints."""

    regions: tuple[WalkableRegion, ...]
    obstacles: tuple[RectObstacle, ...] = ()

    def __post_init__(self) -> None:
        regions = tuple(self.regions)
        obstacles = tuple(self.obstacles)
        if not regions:
            raise ValueError("StageGeometry requires at least one walkable region")
        object.__setattr__(self, "regions", regions)
        object.__setattr__(self, "obstacles", obstacles)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StageGeometry:
        return cls(
            regions=tuple(WalkableRegion.from_dict(item) for item in data["regions"]),
            obstacles=tuple(RectObstacle.from_dict(item) for item in data.get("obstacles", ())),
        )

    @property
    def x_bounds(self) -> tuple[float, float]:
        return min(region.x_min for region in self.regions), max(region.x_max for region in self.regions)

    def _footprint_sample_xs(self, point: WorldPoint, radius: float) -> tuple[float, ...]:
        left = point.x - radius
        right = point.x + radius
        sample_xs = {left, point.x, right}
        for region in self.regions:
            if left - EPSILON <= region.x_min <= right + EPSILON:
                sample_xs.add(region.x_min)
            if left - EPSILON <= region.x_max <= right + EPSILON:
                sample_xs.add(region.x_max)
        return tuple(sorted(sample_xs))

    def _floor_contains(self, point: WorldPoint, radius: float) -> bool:
        """Test an actor footprint against the *union* of floor regions.

        Region edges are often only data breakpoints where one street rail
        segment hands off to the next.  Shrinking every region by ``radius``
        turns those internal handoffs into invisible walls.  Sampling the
        footprint endpoints plus every crossed breakpoint keeps true exterior
        edges solid while allowing a body to straddle contiguous regions.
        """

        for sample_x in self._footprint_sample_xs(point, radius):
            covered = False
            for region in self.regions:
                if region.x_min - EPSILON <= sample_x <= region.x_max + EPSILON:
                    back, front = region.depth_bounds(sample_x, radius)
                    if back - EPSILON <= point.depth <= front + EPSILON:
                        covered = True
                        break
            if not covered:
                return False
        return True

    def _touches_contiguous_handoff(self, point: WorldPoint, radius: float) -> bool:
        """Return whether a footprint overlaps a connected region handoff."""

        left = point.x - radius
        right = point.x + radius
        for first in self.regions:
            seam_x = first.x_max
            if not left - EPSILON <= seam_x <= right + EPSILON:
                continue
            first_back, first_front = first.depth_bounds(seam_x, radius)
            for second in self.regions:
                if abs(second.x_min - seam_x) > EPSILON:
                    continue
                second_back, second_front = second.depth_bounds(seam_x, radius)
                if max(first_back, second_back) <= min(first_front, second_front) + EPSILON:
                    return True
        return False

    def _nearest_floor_depth(self, point: WorldPoint, radius: float) -> WorldPoint | None:
        """Project only depth onto the nearest value valid for the full footprint."""

        candidate_depths = {point.depth}
        for sample_x in self._footprint_sample_xs(point, radius):
            for region in self.regions:
                if region.x_min - EPSILON <= sample_x <= region.x_max + EPSILON:
                    candidate_depths.update(region.depth_bounds(sample_x, radius))
        for depth in sorted(candidate_depths, key=lambda value: (abs(value - point.depth), value)):
            candidate = WorldPoint(point.x, depth, point.elevation)
            if self._floor_contains(candidate, radius):
                return candidate
        return None

    def _axis_path_is_obstacle_free(self, start: WorldPoint, end: WorldPoint, radius: float) -> bool:
        """Check an axis-aligned movement leg against expanded obstacle bounds."""

        vertical = abs(start.x - end.x) <= EPSILON
        horizontal = abs(start.depth - end.depth) <= EPSILON
        if not vertical and not horizontal:
            raise ValueError("obstacle path check requires an axis-aligned leg")
        for obstacle in self.obstacles:
            x_min = obstacle.x_min - radius
            x_max = obstacle.x_max + radius
            depth_min = obstacle.depth_min - radius
            depth_max = obstacle.depth_max + radius
            if vertical:
                path_min = min(start.depth, end.depth)
                path_max = max(start.depth, end.depth)
                if x_min <= start.x <= x_max and path_max >= depth_min and path_min <= depth_max:
                    return False
            else:
                path_min = min(start.x, end.x)
                path_max = max(start.x, end.x)
                if depth_min <= start.depth <= depth_max and path_max >= x_min and path_min <= x_max:
                    return False
        return True

    def _seam_slide_candidate(
        self,
        current: WorldPoint,
        desired: WorldPoint,
        radius: float,
        max_correction: float,
    ) -> WorldPoint | None:
        """Make a bounded depth-first slide through a contiguous rail seam."""

        if not self._touches_contiguous_handoff(desired, radius):
            return None
        candidate = self._nearest_floor_depth(desired, radius)
        if candidate is None or abs(candidate.depth - desired.depth) > max_correction + EPSILON:
            return None
        depth_first = WorldPoint(current.x, candidate.depth, current.elevation)
        if not self.is_walkable(depth_first, radius) or not self.is_walkable(candidate, radius):
            return None
        if not self._axis_path_is_obstacle_free(current, depth_first, radius):
            return None
        if not self._axis_path_is_obstacle_free(depth_first, candidate, radius):
            return None
        return candidate

    def _clamp_to_region(self, region: WalkableRegion, point: WorldPoint, radius: float) -> WorldPoint | None:
        """Clamp toward one region without shrinking its internal seam edges."""

        stage_min_x, stage_max_x = self.x_bounds
        low_x = region.x_min + (radius if abs(region.x_min - stage_min_x) <= EPSILON else 0.0)
        high_x = region.x_max - (radius if abs(region.x_max - stage_max_x) <= EPSILON else 0.0)
        if low_x > high_x + EPSILON:
            return None
        x = _clamp(point.x, low_x, high_x)
        back, front = region.depth_bounds(x, radius)
        return WorldPoint(x, _clamp(point.depth, back, front), point.elevation)

    def is_walkable(self, point: WorldPoint, radius: float = 0.0) -> bool:
        radius = max(0.0, float(radius))
        if not self._floor_contains(point, radius):
            return False
        return not any(obstacle.contains(point, radius) for obstacle in self.obstacles)

    def clamp_to_walkable(self, point: WorldPoint, radius: float = 0.0) -> WorldPoint:
        """Return the nearest valid floor point, including obstacle ejection."""

        radius = max(0.0, float(radius))
        candidates: list[tuple[WalkableRegion, WorldPoint]] = []
        for region in self.regions:
            candidate = self._clamp_to_region(region, point, radius)
            if candidate is not None:
                candidates.append((region, candidate))
        valid = [(region, candidate) for region, candidate in candidates if self.is_walkable(candidate, radius)]
        if valid:
            return min(valid, key=lambda item: self._distance_squared(point, item[1]))[1]

        frontier = candidates
        for _ in range(len(self.obstacles) + 2):
            next_frontier: list[tuple[WalkableRegion, WorldPoint]] = []
            for region, candidate in frontier:
                colliders = [obstacle for obstacle in self.obstacles if obstacle.contains(candidate, radius)]
                if not colliders and self.is_walkable(candidate, radius):
                    valid.append((region, candidate))
                    continue
                for obstacle in colliders:
                    for escaped in obstacle.escape_candidates(candidate, radius):
                        adjusted = self._clamp_to_region(region, escaped, radius)
                        if adjusted is None:
                            continue
                        if self.is_walkable(adjusted, radius):
                            valid.append((region, adjusted))
                        else:
                            next_frontier.append((region, adjusted))
            if valid:
                return min(valid, key=lambda item: self._distance_squared(point, item[1]))[1]
            frontier = next_frontier
        raise ValueError("no walkable point remains after applying obstacles and actor radius")

    def resolve_move(
        self,
        start: WorldPoint,
        dx: float,
        ddepth: float,
        *,
        radius: float = 0.0,
        slide: bool = True,
        max_step: float = 8.0,
    ) -> WorldPoint:
        """Move across the floor without tunnelling, sliding along rails/solids.

        Elevation is intentionally preserved and does not bypass guard rails: a
        jumping fighter still moves along the same 3D-like floor footprint.
        """

        dx = _finite(dx, "dx")
        ddepth = _finite(ddepth, "ddepth")
        max_step = _finite(max_step, "max_step")
        if max_step <= 0.0:
            raise ValueError("max_step must be greater than zero")
        current = self.clamp_to_walkable(start, radius)
        collision_step = min((obstacle.minimum_span * 0.45 for obstacle in self.obstacles), default=max_step)
        safe_step = max(EPSILON * 10.0, min(max_step, collision_step))
        steps = max(1, int(math.ceil(max(abs(dx), abs(ddepth)) / safe_step)))
        step_x = dx / steps
        step_depth = ddepth / steps
        for _ in range(steps):
            desired = current.moved(step_x, step_depth)
            if self.is_walkable(desired, radius):
                current = desired
                continue
            if not slide:
                continue
            if not self._floor_contains(desired, radius):
                seam_slide = self._seam_slide_candidate(
                    current,
                    desired,
                    radius,
                    max_correction=max(radius, min(max_step, 8.0)),
                )
                if seam_slide is not None:
                    current = seam_slide
                    continue
            options: list[WorldPoint] = [current]
            x_only = current.moved(step_x, 0.0)
            if self.is_walkable(x_only, radius):
                options.append(x_only)
                x_then_depth = x_only.moved(0.0, step_depth)
                if self.is_walkable(x_then_depth, radius):
                    options.append(x_then_depth)
            depth_only = current.moved(0.0, step_depth)
            if self.is_walkable(depth_only, radius):
                options.append(depth_only)
                depth_then_x = depth_only.moved(step_x, 0.0)
                if self.is_walkable(depth_then_x, radius):
                    options.append(depth_then_x)
            current = min(options, key=lambda option: self._distance_squared(option, desired))
        return current

    @staticmethod
    def _distance_squared(left: WorldPoint, right: WorldPoint) -> float:
        return (left.x - right.x) ** 2 + (left.depth - right.depth) ** 2


@dataclass(frozen=True, slots=True)
class CameraZone:
    """Data-driven camera behaviour active over a horizontal world interval."""

    name: str
    x_min: float
    x_max: float
    camera_min_x: float | None = None
    camera_max_x: float | None = None
    dead_zone_left: float | None = None
    dead_zone_right: float | None = None
    follow_speed: float | None = None
    lookahead_seconds: float | None = None
    max_lookahead: float | None = None
    entry_pan_seconds: float = 0.0
    priority: int = 0

    def __post_init__(self) -> None:
        x_min = _finite(self.x_min, "zone.x_min")
        x_max = _finite(self.x_max, "zone.x_max")
        if x_max <= x_min:
            raise ValueError("zone x_max must be greater than x_min")
        object.__setattr__(self, "x_min", x_min)
        object.__setattr__(self, "x_max", x_max)
        for field_name in (
            "camera_min_x",
            "camera_max_x",
            "dead_zone_left",
            "dead_zone_right",
            "follow_speed",
            "lookahead_seconds",
            "max_lookahead",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _finite(value, f"zone.{field_name}"))
        entry = _finite(self.entry_pan_seconds, "zone.entry_pan_seconds")
        if entry < 0.0:
            raise ValueError("entry_pan_seconds cannot be negative")
        object.__setattr__(self, "entry_pan_seconds", entry)
        object.__setattr__(self, "priority", int(self.priority))
        if self.camera_min_x is not None and self.camera_max_x is not None:
            if self.camera_max_x < self.camera_min_x:
                raise ValueError("camera_max_x cannot be less than camera_min_x")
        if self.dead_zone_left is not None and self.dead_zone_right is not None:
            if self.dead_zone_right <= self.dead_zone_left:
                raise ValueError("dead_zone_right must be greater than dead_zone_left")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CameraZone:
        allowed = {field for field in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in allowed})

    def contains(self, world_x: float) -> bool:
        return self.x_min <= world_x <= self.x_max


@dataclass(frozen=True, slots=True)
class CameraView:
    """One camera frame ready for rendering and diagnostic logging."""

    x: float
    render_x: float
    shake_x: float
    shake_y: float
    zone_name: str | None
    encounter_locked: bool
    scripted_pan: bool


class CameraDirector:
    """Dead-zone follow camera with zones, pans, encounter locks, and shake."""

    def __init__(
        self,
        *,
        viewport_width: float,
        stage_min_x: float,
        stage_max_x: float,
        zones: Sequence[CameraZone] = (),
        initial_x: float = 0.0,
        dead_zone_left: float | None = None,
        dead_zone_right: float | None = None,
        follow_speed: float = 480.0,
        lookahead_seconds: float = 0.16,
        max_lookahead: float = 72.0,
        pixels_per_world_x: float = 1.0,
        pixel_snap: bool = True,
    ) -> None:
        self.viewport_width = _finite(viewport_width, "viewport_width")
        self.stage_min_x = _finite(stage_min_x, "stage_min_x")
        self.stage_max_x = _finite(stage_max_x, "stage_max_x")
        self.pixels_per_world_x = _finite(pixels_per_world_x, "pixels_per_world_x")
        if self.viewport_width <= 0.0 or self.pixels_per_world_x <= 0.0:
            raise ValueError("viewport_width and pixels_per_world_x must be greater than zero")
        if self.stage_max_x <= self.stage_min_x:
            raise ValueError("stage_max_x must be greater than stage_min_x")
        self.dead_zone_left = (
            self.viewport_width * 0.34 if dead_zone_left is None else _finite(dead_zone_left, "dead_zone_left")
        )
        self.dead_zone_right = (
            self.viewport_width * 0.66 if dead_zone_right is None else _finite(dead_zone_right, "dead_zone_right")
        )
        if not 0.0 <= self.dead_zone_left < self.dead_zone_right <= self.viewport_width:
            raise ValueError("dead zone must be ordered inside the viewport")
        self.follow_speed = _finite(follow_speed, "follow_speed")
        self.lookahead_seconds = _finite(lookahead_seconds, "lookahead_seconds")
        self.max_lookahead = _finite(max_lookahead, "max_lookahead")
        if self.follow_speed < 0.0 or self.lookahead_seconds < 0.0 or self.max_lookahead < 0.0:
            raise ValueError("camera motion settings cannot be negative")
        self.pixel_snap = bool(pixel_snap)
        self.zones = tuple(zones)
        self._x = self._clamp_stage(_finite(initial_x, "initial_x"))
        self._active_zone: CameraZone | None = None
        self._lock_min: float | None = None
        self._lock_max: float | None = None
        self._pan_start = 0.0
        self._pan_target = 0.0
        self._pan_duration = 0.0
        self._pan_elapsed = 0.0
        self._pan_easing: Literal["linear", "smoothstep"] = "smoothstep"
        self._panning = False
        self._shake_duration = 0.0
        self._shake_remaining = 0.0
        self._shake_amplitude_x = 0.0
        self._shake_amplitude_y = 0.0
        self._shake_frequency = 0.0
        self._shake_phase = 0.0
        self._shake_x = 0.0
        self._shake_y = 0.0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CameraDirector:
        defaults = dict(data.get("defaults", {}))
        direct_keys = {
            "viewport_width",
            "stage_min_x",
            "stage_max_x",
            "initial_x",
            "dead_zone_left",
            "dead_zone_right",
            "follow_speed",
            "lookahead_seconds",
            "max_lookahead",
            "pixels_per_world_x",
            "pixel_snap",
        }
        defaults.update({key: value for key, value in data.items() if key in direct_keys})
        defaults["zones"] = tuple(CameraZone.from_dict(item) for item in data.get("zones", ()))
        return cls(**defaults)

    @property
    def x(self) -> float:
        return self._x

    @property
    def active_zone(self) -> CameraZone | None:
        return self._active_zone

    @property
    def encounter_locked(self) -> bool:
        return self._lock_min is not None

    @property
    def panning(self) -> bool:
        return self._panning

    def set_encounter_lock(self, camera_min_x: float | None = None, camera_max_x: float | None = None) -> None:
        """Restrict camera motion during combat; no arguments freezes it in place."""

        if camera_min_x is None and camera_max_x is None:
            camera_min_x = camera_max_x = self._x
        elif camera_min_x is None:
            camera_min_x = camera_max_x
        elif camera_max_x is None:
            camera_max_x = camera_min_x
        assert camera_min_x is not None and camera_max_x is not None
        camera_min_x = _finite(camera_min_x, "camera_min_x")
        camera_max_x = _finite(camera_max_x, "camera_max_x")
        if camera_max_x < camera_min_x:
            raise ValueError("camera_max_x cannot be less than camera_min_x")
        self._lock_min = self._clamp_stage(camera_min_x)
        self._lock_max = self._clamp_stage(camera_max_x)
        self._x = self._clamp_effective(self._x)
        self.cancel_pan()

    def clear_encounter_lock(self) -> None:
        self._lock_min = None
        self._lock_max = None

    def pan_to(
        self,
        target_camera_x: float,
        duration: float,
        *,
        easing: Literal["linear", "smoothstep"] = "smoothstep",
    ) -> None:
        """Start a deterministic scripted camera pan in camera-left coordinates."""

        target = self._clamp_effective(_finite(target_camera_x, "target_camera_x"))
        duration = _finite(duration, "duration")
        if easing not in {"linear", "smoothstep"}:
            raise ValueError("easing must be 'linear' or 'smoothstep'")
        if duration <= 0.0:
            self._x = target
            self.cancel_pan()
            return
        self._pan_start = self._x
        self._pan_target = target
        self._pan_duration = duration
        self._pan_elapsed = 0.0
        self._pan_easing = easing
        self._panning = True

    def pan_to_world(
        self,
        world_x: float,
        duration: float,
        *,
        anchor_screen_x: float | None = None,
        easing: Literal["linear", "smoothstep"] = "smoothstep",
    ) -> None:
        anchor = self.viewport_width * 0.5 if anchor_screen_x is None else float(anchor_screen_x)
        target = float(world_x) - anchor / self.pixels_per_world_x
        self.pan_to(target, duration, easing=easing)

    def cancel_pan(self) -> None:
        self._panning = False
        self._pan_elapsed = 0.0
        self._pan_duration = 0.0

    def trigger_shake(
        self,
        strength: float,
        duration: float,
        *,
        vertical_strength: float | None = None,
        frequency: float = 23.0,
        phase: float = 0.0,
    ) -> None:
        """Start a deterministic decaying shake measured in screen pixels."""

        strength = abs(_finite(strength, "strength"))
        duration = _finite(duration, "duration")
        vertical = strength if vertical_strength is None else abs(_finite(vertical_strength, "vertical_strength"))
        frequency = _finite(frequency, "frequency")
        if duration <= 0.0 or (strength <= 0.0 and vertical <= 0.0):
            self.clear_shake()
            return
        if frequency < 0.0:
            raise ValueError("frequency cannot be negative")
        self._shake_duration = duration
        self._shake_remaining = duration
        self._shake_amplitude_x = strength
        self._shake_amplitude_y = vertical
        self._shake_frequency = frequency
        self._shake_phase = _finite(phase, "phase")
        self._shake_x = 0.0
        self._shake_y = 0.0

    def clear_shake(self) -> None:
        self._shake_duration = 0.0
        self._shake_remaining = 0.0
        self._shake_x = 0.0
        self._shake_y = 0.0

    def update(
        self,
        dt: float,
        focus: WorldPoint | float | Sequence[WorldPoint | float],
        *,
        velocity_x: float = 0.0,
    ) -> CameraView:
        dt = _finite(dt, "dt")
        if dt < 0.0:
            raise ValueError("dt cannot be negative")
        focus_values = self._focus_values(focus)
        centre = sum(focus_values) / len(focus_values) if focus_values else self._x + self._viewport_world_width * 0.5
        previous_zone = self._active_zone
        self._active_zone = self._select_zone(centre)

        if previous_zone is not self._active_zone and previous_zone is not None and not self._panning:
            seconds = self._active_zone.entry_pan_seconds if self._active_zone else 0.0
            if seconds > 0.0:
                self.pan_to(self._follow_target(focus_values, velocity_x), seconds)

        if self._panning:
            self._pan_elapsed = min(self._pan_duration, self._pan_elapsed + dt)
            amount = self._pan_elapsed / self._pan_duration
            if self._pan_easing == "smoothstep":
                amount = amount * amount * (3.0 - 2.0 * amount)
            self._x = self._clamp_effective(self._pan_start + (self._pan_target - self._pan_start) * amount)
            if self._pan_elapsed >= self._pan_duration:
                self._x = self._clamp_effective(self._pan_target)
                self._panning = False
        elif focus_values:
            target = self._clamp_effective(self._follow_target(focus_values, velocity_x))
            speed = self._effective_setting("follow_speed", self.follow_speed)
            self._x = target if speed <= 0.0 else _move_toward(self._x, target, speed * dt)
            self._x = self._clamp_effective(self._x)

        self._update_shake(dt)
        base_x = float(round(self._x)) if self.pixel_snap else self._x
        render_x = base_x - self._shake_x / self.pixels_per_world_x
        return CameraView(
            x=self._x,
            render_x=render_x,
            shake_x=self._shake_x,
            shake_y=self._shake_y,
            zone_name=self._active_zone.name if self._active_zone else None,
            encounter_locked=self.encounter_locked,
            scripted_pan=self._panning,
        )

    @property
    def _viewport_world_width(self) -> float:
        return self.viewport_width / self.pixels_per_world_x

    def _clamp_stage(self, camera_x: float) -> float:
        high = max(self.stage_min_x, self.stage_max_x - self._viewport_world_width)
        return _clamp(camera_x, self.stage_min_x, high)

    def _zone_bounds(self) -> tuple[float, float]:
        low = self.stage_min_x
        high = max(low, self.stage_max_x - self._viewport_world_width)
        if self._active_zone is not None:
            if self._active_zone.camera_min_x is not None:
                low = max(low, self._active_zone.camera_min_x)
            if self._active_zone.camera_max_x is not None:
                high = min(high, self._active_zone.camera_max_x)
        if high < low:
            high = low
        return low, high

    def _clamp_effective(self, camera_x: float) -> float:
        low, high = self._zone_bounds()
        if self._lock_min is not None and self._lock_max is not None:
            lock_low = max(low, self._lock_min)
            lock_high = min(high, self._lock_max)
            if lock_high < lock_low:
                anchor = _clamp(self._lock_min, low, high)
                lock_low = lock_high = anchor
            low, high = lock_low, lock_high
        return _clamp(camera_x, low, high)

    def _select_zone(self, world_x: float) -> CameraZone | None:
        candidates = [zone for zone in self.zones if zone.contains(world_x)]
        if not candidates:
            return None
        return max(candidates, key=lambda zone: (zone.priority, -(zone.x_max - zone.x_min)))

    def _effective_setting(self, field_name: str, default: float) -> float:
        if self._active_zone is not None:
            value = getattr(self._active_zone, field_name)
            if value is not None:
                return float(value)
        return default

    def _follow_target(self, focus_values: Sequence[float], velocity_x: float) -> float:
        if not focus_values:
            return self._x
        left = self._effective_setting("dead_zone_left", self.dead_zone_left)
        right = self._effective_setting("dead_zone_right", self.dead_zone_right)
        if not 0.0 <= left < right <= self.viewport_width:
            raise ValueError("active camera-zone dead zone must be ordered inside the viewport")
        lookahead_seconds = self._effective_setting("lookahead_seconds", self.lookahead_seconds)
        max_lookahead = self._effective_setting("max_lookahead", self.max_lookahead)
        lookahead = _clamp(float(velocity_x) * lookahead_seconds, -max_lookahead, max_lookahead)
        minimum = min(focus_values) + lookahead
        maximum = max(focus_values) + lookahead
        left_world = left / self.pixels_per_world_x
        right_world = right / self.pixels_per_world_x
        dead_width = right_world - left_world
        if maximum - minimum > dead_width:
            return (minimum + maximum) * 0.5 - (left_world + right_world) * 0.5
        if minimum < self._x + left_world:
            return minimum - left_world
        if maximum > self._x + right_world:
            return maximum - right_world
        return self._x

    @staticmethod
    def _focus_values(focus: WorldPoint | float | Sequence[WorldPoint | float]) -> tuple[float, ...]:
        if isinstance(focus, WorldPoint):
            return (focus.x,)
        if isinstance(focus, (int, float)):
            return (_finite(focus, "focus"),)
        return tuple(item.x if isinstance(item, WorldPoint) else _finite(item, "focus") for item in focus)

    def _update_shake(self, dt: float) -> None:
        if self._shake_remaining <= 0.0 or self._shake_duration <= 0.0:
            self._shake_x = 0.0
            self._shake_y = 0.0
            return
        self._shake_remaining = max(0.0, self._shake_remaining - dt)
        if self._shake_remaining <= 0.0:
            self._shake_x = 0.0
            self._shake_y = 0.0
            return
        age = self._shake_duration - self._shake_remaining
        decay = self._shake_remaining / self._shake_duration
        angle = math.tau * self._shake_frequency * age + self._shake_phase
        shake_x = math.sin(angle) * self._shake_amplitude_x * decay
        shake_y = math.sin(angle * 1.371 + math.pi * 0.5) * self._shake_amplitude_y * decay
        if self.pixel_snap:
            shake_x = float(round(shake_x))
            shake_y = float(round(shake_y))
        self._shake_x = shake_x
        self._shake_y = shake_y


__all__ = [
    "BeatEmUpProjection",
    "CameraDirector",
    "CameraView",
    "CameraZone",
    "ProjectedPoint",
    "ProjectionConfig",
    "RectObstacle",
    "StageGeometry",
    "WalkableRegion",
    "WorldPoint",
]
