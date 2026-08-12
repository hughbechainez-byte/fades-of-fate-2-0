"""Chunked, world-space stage data for the 2.5D beat-em-up renderer.

The location-lock manifest describes *what* a route is.  This module describes
how that route is traversed: each chunk owns a contiguous piece of the street,
its scenery layer assets, landmark references, physical props, collision
references, encounter markers, and foreground occluders.  The renderer can
therefore cull and draw only nearby pieces without mutating any world
coordinate when the camera moves.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Mapping, Sequence
from typing import Any

from .config import load_json


CHUNK_MANIFEST_SCHEMA_VERSION = 1
DEFAULT_CULL_MARGIN = 96.0
WORLD_LOCKED_LAYERS = frozenset({"architecture", "ground"})
REQUIRED_CHUNK_LAYERS = (
    "far_skyline",
    "architecture",
    "ground",
    "near_occluder",
)


class StageWorldError(ValueError):
    """Raised when a chunk manifest cannot describe a safe stage."""


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StageWorldError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise StageWorldError(f"{label} must be a finite number")
    return result


def _positive_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise StageWorldError(f"{label} must be a positive integer")
    return value


def _non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StageWorldError(f"{label} must be a non-negative integer")
    return value


def _strings(value: object, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise StageWorldError(f"{label} must be a list of strings")
    result = tuple(str(item).strip() for item in value)
    if any(not item for item in result):
        raise StageWorldError(f"{label} cannot contain empty strings")
    if len(set(result)) != len(result):
        raise StageWorldError(f"{label} cannot contain duplicates")
    return result


def _asset_path(value: object, label: str) -> str:
    path = str(value or "").replace("\\", "/").strip()
    if not path.startswith("assets/") or not path.lower().endswith(".png"):
        raise StageWorldError(f"{label} must be an assets/... PNG")
    return path


@dataclass(frozen=True, slots=True)
class StageLayerPiece:
    """One independently drawable layer piece in world coordinates."""

    layer: str
    asset: str
    world_x: int
    width: int
    height: int

    @classmethod
    def from_mapping(
        cls,
        layer: str,
        data: Mapping[str, Any],
        *,
        label: str,
    ) -> "StageLayerPiece":
        if not isinstance(data, Mapping):
            raise StageWorldError(f"{label} must be an object")
        return cls(
            layer=str(layer),
            asset=_asset_path(data.get("asset"), f"{label}.asset"),
            world_x=int(_finite(data.get("world_x", 0), f"{label}.world_x")),
            width=_positive_int(data.get("width"), f"{label}.width"),
            height=_positive_int(data.get("height"), f"{label}.height"),
        )

    @property
    def world_right(self) -> int:
        return self.world_x + self.width


@dataclass(frozen=True, slots=True)
class StageSpawnMarker:
    """A deterministic encounter/camera/spawn point owned by a chunk."""

    marker_id: str
    kind: str
    world_x: float
    encounter_index: int | None = None

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        label: str,
    ) -> "StageSpawnMarker":
        if not isinstance(data, Mapping):
            raise StageWorldError(f"{label} must be an object")
        marker_id = str(data.get("id", "")).strip()
        kind = str(data.get("kind", "")).strip()
        if not marker_id or not kind:
            raise StageWorldError(f"{label} requires id and kind")
        raw_index = data.get("encounter_index")
        encounter_index = None if raw_index is None else _non_negative_int(raw_index, f"{label}.encounter_index")
        return cls(
            marker_id=marker_id,
            kind=kind,
            world_x=_finite(data.get("world_x"), f"{label}.world_x"),
            encounter_index=encounter_index,
        )


@dataclass(frozen=True, slots=True)
class StageChunk:
    """A contiguous route section and all authored systems attached to it."""

    chunk_id: str
    world_x: int
    width: int
    layer_pieces: tuple[StageLayerPiece, ...]
    landmark_ids: tuple[str, ...]
    collision_ids: tuple[str, ...]
    physical_scene_object_ids: tuple[str, ...]
    spawn_markers: tuple[StageSpawnMarker, ...]
    foreground_layers: tuple[str, ...]
    seam_anchor: str

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        label: str,
    ) -> "StageChunk":
        if not isinstance(data, Mapping):
            raise StageWorldError(f"{label} must be an object")
        chunk_id = str(data.get("id", "")).strip()
        if not chunk_id:
            raise StageWorldError(f"{label}.id must be non-empty")
        raw_layers = data.get("layers")
        if not isinstance(raw_layers, Mapping):
            raise StageWorldError(f"{label}.layers must be an object")
        layer_pieces = tuple(
            StageLayerPiece.from_mapping(
                str(layer),
                piece,
                label=f"{label}.layers.{layer}",
            )
            for layer, piece in raw_layers.items()
        )
        piece_layers = {piece.layer for piece in layer_pieces}
        missing = [layer for layer in REQUIRED_CHUNK_LAYERS if layer not in piece_layers]
        if missing:
            raise StageWorldError(f"{label}.layers missing {', '.join(missing)}")
        markers = tuple(
            StageSpawnMarker.from_mapping(marker, label=f"{label}.spawn_markers[{index}]")
            for index, marker in enumerate(data.get("spawn_markers", ()))
        )
        return cls(
            chunk_id=chunk_id,
            world_x=_non_negative_int(data.get("world_x"), f"{label}.world_x"),
            width=_positive_int(data.get("width"), f"{label}.width"),
            layer_pieces=layer_pieces,
            landmark_ids=_strings(data.get("landmark_ids", ()), f"{label}.landmark_ids"),
            collision_ids=_strings(data.get("collision_ids", ()), f"{label}.collision_ids"),
            physical_scene_object_ids=_strings(
                data.get("physical_scene_object_ids", ()),
                f"{label}.physical_scene_object_ids",
            ),
            spawn_markers=markers,
            foreground_layers=_strings(
                data.get("foreground_layers", ("near_occluder",)),
                f"{label}.foreground_layers",
            ),
            seam_anchor=str(data.get("seam_anchor", "")).strip(),
        )

    @property
    def world_right(self) -> int:
        return self.world_x + self.width

    def contains(self, world_x: float) -> bool:
        return self.world_x <= float(world_x) < self.world_right

    def intersects(self, left: float, right: float) -> bool:
        return self.world_right > float(left) and self.world_x < float(right)

    def piece(self, layer: str) -> StageLayerPiece:
        for candidate in self.layer_pieces:
            if candidate.layer == layer:
                return candidate
        raise StageWorldError(f"{self.chunk_id} has no {layer} layer")


@dataclass(frozen=True, slots=True)
class StageWorld:
    """Validated route topology used by the renderer and debug overlay."""

    theme: str
    world_width: int
    chunks: tuple[StageChunk, ...]
    global_layers: Mapping[str, str]
    layer_rates: Mapping[str, float]
    layer_max_offsets: Mapping[str, float]
    cull_margin: float = DEFAULT_CULL_MARGIN

    @classmethod
    def from_route(
        cls,
        route: Mapping[str, Any],
        manifest: Mapping[str, Any],
    ) -> "StageWorld":
        theme = str(route.get("theme", "")).strip()
        if not theme:
            raise StageWorldError("route.theme must be non-empty")
        if not isinstance(manifest, Mapping):
            raise StageWorldError("stage chunk manifest must be an object")
        if manifest.get("schema_version") != CHUNK_MANIFEST_SCHEMA_VERSION:
            raise StageWorldError(
                f"stage chunk manifest schema must be {CHUNK_MANIFEST_SCHEMA_VERSION}"
            )
        raw_routes = manifest.get("routes")
        if isinstance(raw_routes, Mapping):
            record = raw_routes.get(theme)
        elif isinstance(raw_routes, Sequence) and not isinstance(raw_routes, (str, bytes)):
            record = next(
                (item for item in raw_routes if isinstance(item, Mapping) and str(item.get("theme")) == theme),
                None,
            )
        else:
            record = None
        if not isinstance(record, Mapping):
            raise StageWorldError(f"stage chunk manifest has no route for {theme!r}")
        world_width = _positive_int(route.get("world_width"), f"{theme}.world_width")
        if int(record.get("world_width", -1)) != world_width:
            raise StageWorldError(f"{theme} chunk width disagrees with location lock")

        raw_chunks = record.get("chunks")
        if not isinstance(raw_chunks, Sequence) or isinstance(raw_chunks, (str, bytes)) or not raw_chunks:
            raise StageWorldError(f"{theme}.chunks must be a non-empty list")
        chunks = tuple(
            StageChunk.from_mapping(chunk, label=f"{theme}.chunks[{index}]")
            for index, chunk in enumerate(raw_chunks)
        )
        cursor = 0
        ids: set[str] = set()
        for index, chunk in enumerate(chunks):
            if chunk.chunk_id in ids:
                raise StageWorldError(f"duplicate chunk id {chunk.chunk_id!r}")
            ids.add(chunk.chunk_id)
            if chunk.world_x != cursor:
                raise StageWorldError(
                    f"{theme}.chunks[{index}] must start at {cursor}, got {chunk.world_x}"
                )
            if chunk.world_right > world_width:
                raise StageWorldError(f"{chunk.chunk_id} extends beyond route width")
            if index < len(chunks) - 1 and not chunk.seam_anchor:
                raise StageWorldError(f"{chunk.chunk_id} requires a seam_anchor")
            cursor = chunk.world_right
        if cursor != world_width:
            raise StageWorldError(f"{theme}.chunks cover {cursor}, expected {world_width}")

        global_layers = {
            str(name): _asset_path(value, f"{theme}.global_layers.{name}")
            for name, value in (record.get("global_layers") or {}).items()
        }
        if "far_haze" not in global_layers:
            raise StageWorldError(f"{theme}.global_layers requires far_haze")

        far_rate = _finite(route.get("far_parallax", 1.0), f"{theme}.far_parallax")
        near_rate = _finite(route.get("near_parallax", 1.0), f"{theme}.near_parallax")
        far_max = max(0.0, _finite(route.get("far_max_offset", 0.0), f"{theme}.far_max_offset"))
        near_max = max(0.0, _finite(route.get("near_max_offset", 0.0), f"{theme}.near_max_offset"))
        layer_rates = {
            "far_skyline": far_rate,
            "architecture": 1.0,
            "ground": 1.0,
            "near_occluder": near_rate,
        }
        layer_max_offsets = {
            "far_skyline": far_max,
            "architecture": 0.0,
            "ground": 0.0,
            "near_occluder": near_max,
        }
        return cls(
            theme=theme,
            world_width=world_width,
            chunks=chunks,
            global_layers=global_layers,
            layer_rates=layer_rates,
            layer_max_offsets=layer_max_offsets,
        )

    @classmethod
    def from_theme(cls, theme: str, route: Mapping[str, Any], manifest: Mapping[str, Any]) -> "StageWorld":
        normalized = str(theme).strip()
        if normalized != str(route.get("theme", "")).strip():
            raise StageWorldError(f"stage world theme mismatch: {normalized!r}")
        return cls.from_route(route, manifest)

    @classmethod
    def load_for_route(cls, theme: str, route: Mapping[str, Any]) -> "StageWorld":
        return cls.from_theme(theme, route, load_json("data/stage_chunks.json"))

    def clamp_camera(self, camera_x: float, viewport_width: int) -> float:
        width = max(1, int(viewport_width))
        return max(0.0, min(float(self.world_width - width), _finite(camera_x, "camera_x")))

    def active_chunks(
        self,
        camera_x: float,
        viewport_width: int,
        *,
        margin: float | None = None,
    ) -> tuple[StageChunk, ...]:
        camera = self.clamp_camera(camera_x, viewport_width)
        padding = self.cull_margin if margin is None else max(0.0, _finite(margin, "margin"))
        left = max(0.0, camera - padding)
        right = min(float(self.world_width), camera + int(viewport_width) + padding)
        return tuple(chunk for chunk in self.chunks if chunk.intersects(left, right))

    def layer_offset(self, layer: str, camera_x: float, viewport_width: int) -> int:
        if layer not in self.layer_rates:
            raise StageWorldError(f"unknown stage layer {layer!r}")
        camera = self.clamp_camera(camera_x, viewport_width)
        physical_limit = max(0, self.world_width - int(viewport_width))
        rate = float(self.layer_rates[layer])
        drift_limit = min(float(physical_limit), float(self.layer_max_offsets[layer]))
        if rate < 1.0:
            drift = min(drift_limit, camera * (1.0 - rate))
            offset = -camera + drift
        else:
            drift = min(drift_limit, camera * (rate - 1.0))
            offset = -camera - drift
        return int(round(max(-physical_limit, min(0.0, offset))))

    def visible_layer_pieces(
        self,
        layer: str,
        camera_x: float,
        viewport_width: int,
        *,
        margin: float | None = None,
    ) -> tuple[StageLayerPiece, ...]:
        chunks = self.active_chunks(camera_x, viewport_width, margin=margin)
        pieces: list[StageLayerPiece] = []
        for chunk in chunks:
            pieces.append(chunk.piece(layer))
        return tuple(pieces)

    def chunk_at(self, world_x: float) -> StageChunk | None:
        return next((chunk for chunk in self.chunks if chunk.contains(world_x)), None)

    def debug_snapshot(self, camera_x: float, viewport_width: int) -> dict[str, Any]:
        active = self.active_chunks(camera_x, viewport_width)
        return {
            "theme": self.theme,
            "world_width": self.world_width,
            "camera_x": round(self.clamp_camera(camera_x, viewport_width), 3),
            "active_chunk_ids": [chunk.chunk_id for chunk in active],
            "active_chunk_count": len(active),
            "total_chunk_count": len(self.chunks),
            "layer_offsets": {
                layer: self.layer_offset(layer, camera_x, viewport_width)
                for layer in self.layer_rates
            },
            "active_landmark_ids": [
                landmark_id
                for chunk in active
                for landmark_id in chunk.landmark_ids
            ],
            "active_collision_ids": [
                collision_id
                for chunk in active
                for collision_id in chunk.collision_ids
            ],
            "active_spawn_marker_ids": [
                marker.marker_id
                for chunk in active
                for marker in chunk.spawn_markers
            ],
        }

    def asset_paths(self) -> tuple[str, ...]:
        paths = list(self.global_layers.values())
        paths.extend(piece.asset for chunk in self.chunks for piece in chunk.layer_pieces)
        return tuple(dict.fromkeys(paths))


__all__ = [
    "CHUNK_MANIFEST_SCHEMA_VERSION",
    "DEFAULT_CULL_MARGIN",
    "REQUIRED_CHUNK_LAYERS",
    "StageChunk",
    "StageLayerPiece",
    "StageSpawnMarker",
    "StageWorld",
    "StageWorldError",
    "WORLD_LOCKED_LAYERS",
]
