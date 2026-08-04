"""Validate Chapter 1 content, location art, and reproducible CPU budgets.

Pacing values are content contracts, not inferred or observed playthrough
times.  Performance values are actual CPU timings for ``FadesGame.update``
and logical-surface ``FadesGame.draw`` calls under SDL's headless video driver;
they are not displayed frame-rate measurements.  The location-lock validator
also supports an alternate project root so the Windows build can verify the
assembled and installed packages rather than trusting the source tree.
"""

from __future__ import annotations

import argparse
import ast
from collections import Counter
from copy import deepcopy
from datetime import date
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import textwrap
import time
from typing import Any, Callable, Mapping, Sequence


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pygame  # noqa: E402

from src.chapter_content import (  # noqa: E402
    compile_couch_contract,
    load_chapter_content,
    pace_profile,
)
from src.config import load_gameplay  # noqa: E402
from src.entities import Projectile  # noqa: E402
from src.atmosphere import AtmosphereState  # noqa: E402
from src.game import FadesGame, LOGICAL_SIZE, SelectSlot  # noqa: E402
from src.input_manager import InputManager  # noqa: E402
from src import pixel_art  # noqa: E402
from src import location_lock  # noqa: E402
from src.stage_world import StageWorld, StageWorldError  # noqa: E402


REPORT_SCHEMA_VERSION = 2
BENCHMARK_LEVEL_ID = "chapter_1_level_4"
BENCHMARK_PLAYER_COUNT = 4
FIXED_HZ = 60
FIXED_STEP_BUDGET_MS = 1000.0 / FIXED_HZ
DEFAULT_WARMUP_FRAMES = 15
DEFAULT_BENCHMARK_FRAMES = 120
DEFAULT_EFFECT_BUDGET = 48
DEFAULT_DEBRIS_BUDGET = 24
DEFAULT_SCENERY_SWEEP_FRAMES = 40
MAX_BENCHMARK_FRAMES = 600
MAX_WARMUP_FRAMES = 180
MAX_EFFECT_BUDGET = 512
MAX_DEBRIS_BUDGET = 256
MAX_SCENERY_SWEEP_FRAMES = 240
_PROFILE_NAMES = ("normal", "experienced", "minimum")
_LEVEL_IDS = (
    "chapter_1_level_1",
    "chapter_1_level_2",
    "chapter_1_level_3",
    "chapter_1_level_4",
)
_MANDATORY_LANDMARK_ORDER = {
    "chapter_1_level_1": (
        "sprouts_parking_lot",
        "wells_fargo_pad",
        "walmart_neighborhood_market",
        "town_country",
        "goodwill_frontage",
        "madison_intersection",
        "el_cilantro_madison",
    ),
    "chapter_1_level_2": (
        "seven_eleven",
        "carls_jr_pad",
        "madison_plaza",
        "former_union_bank",
        "valvoline",
        "freeway_approach",
        "i8_underpass",
    ),
    "chapter_1_level_3": (
        "soapy_joes",
        "starbucks_pad",
        "marechiaro",
        "carls_boot_leather",
        "cvs_broadway_corner",
        "broadway_turn",
        "revive_pathway",
    ),
    "chapter_1_level_4": (
        "awaken_church_lot",
        "awaken_facade",
        "awaken_front_lot",
        "daves_bmx",
    ),
}
_EXPECTED_ENDPOINTS = {
    "chapter_1_level_1": ("sprouts_parking_lot", "el_cilantro_madison"),
    "chapter_1_level_2": ("seven_eleven", "i8_underpass"),
    "chapter_1_level_3": ("soapy_joes", "revive_pathway"),
    "chapter_1_level_4": ("awaken_church_lot", "daves_bmx"),
}
_LOCATION_ASSET_PREFIX = "assets/stage/chapter1_location_locked/"
_LEGACY_LOCATION_ASSET_FIELDS = (
    "main_panorama_asset",
    "far_asset",
    "near_asset",
)
_LAYERED_LOCATION_ASSET_FIELDS = (
    "far_haze_asset",
    "far_skyline_asset",
    "architecture_asset",
    "ground_asset",
    "near_occluder_asset",
)
_LOCATION_ASSET_FIELDS = (
    *_LEGACY_LOCATION_ASSET_FIELDS,
    *_LAYERED_LOCATION_ASSET_FIELDS,
)
_LAYERED_FIELD_ALIASES = {
    "far_haze_asset": "haze_asset",
    "far_skyline_asset": "skyline_asset",
}
_PHYSICAL_SCENE_OBJECT_FIELDS = (
    "id",
    "kind",
    "asset",
    "world_x",
    "depth",
    "elevation",
    "anchor",
    "physical_height_m",
)
_LANDMARK_SOURCE_FIELDS = (
    "source_date",
    "imagery_date",
    "access_date",
    "source_urls",
    "view_direction",
    "durable_massing",
    "parking_setback",
    "driveway_placement",
    "neighboring_anchors",
    "confidence",
)
_CONFIDENCE_VALUES = {"high", "medium", "low"}
_MANDATORY_REFERENCE_IDS = (
    "ref_full_corridor_map",
    "ref_sprouts_official",
    "ref_sprouts_lot",
    "ref_walgreens_east_view",
    "ref_town_country_west_view",
    "ref_el_cilantro_corner",
    "ref_seven_eleven",
    "ref_madison_plaza_west_view",
    "ref_i8_underpass_view",
    "ref_soapy_joes_official",
    "ref_soapy_joes_west_view",
    "ref_revive_pathway",
    "ref_awaken_west_view",
    "ref_awaken_official",
)
_EFFECT_KINDS = (
    "shock",
    "fist",
    "hit",
    "flame_burst",
    "scorch",
    "ember",
    "flame",
    "impact",
    "spawn",
)
_INTEGRATION_CHECK_CAMERA_FRACTIONS = (0.0, 0.25, 0.5, 0.75, 1.0)
_INTEGRATION_REQUIRED_ROUTE_MARKERS = {
    "chapter_1_level_1": (
        "sprouts_parking_lot",
        "wells_fargo_pad",
        "madison_intersection",
        "el_cilantro_madison",
    ),
    "chapter_1_level_2": (
        "seven_eleven",
        "carls_jr_pad",
        "madison_plaza",
        "i8_underpass",
    ),
    "chapter_1_level_3": (
        "soapy_joes",
        "starbucks_pad",
        "broadway_turn",
        "revive_pathway",
    ),
    "chapter_1_level_4": (
        "awaken_church_lot",
        "awaken_facade",
        "awaken_front_lot",
        "daves_bmx",
    ),
}
_INTEGRATION_REFERENCE_KEYWORDS = {
    "actor_dave": ("black_dave", "dave"),
    "actor_shelly": ("shelly",),
    "actor_chief": ("chief",),
    "environment_pole": ("pole", "light_pole", "bollard"),
    "environment_curb": ("curb", "curbs", "median", "driveway", "street", "sidewalk"),
    "environment_door": ("door",),
    "environment_sedan": ("car", "sedan"),
    "actor_enemy": ("enemy", "couch", "stick", "cart", "whip", "pipe", "security"),
}


def _read_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _contains_ordered_subsequence(values: Sequence[str], required: Sequence[str]) -> bool:
    cursor = iter(values)
    return all(any(candidate == expected for candidate in cursor) for expected in required)


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(value)
    return ()


def _contains_token(values: Sequence[str], needles: Sequence[str]) -> bool:
    normalized = {str(value).lower() for value in values}
    return any(any(needle in value for value in normalized) for needle in needles)


def _stable_json_digest(value: Mapping[str, Any] | Sequence[Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _finite_number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _projection_profiles(gameplay: Mapping[str, Any]) -> Mapping[str, Any]:
    engine = gameplay.get("engine", {})
    if not isinstance(engine, Mapping):
        return {}
    profiles = engine.get("projection_profiles", gameplay.get("projection_profiles", {}))
    return profiles if isinstance(profiles, Mapping) else {}


def _active_projection_profile_id(gameplay: Mapping[str, Any]) -> str:
    engine = gameplay.get("engine", {})
    if not isinstance(engine, Mapping):
        return ""
    projection = engine.get("projection", {})
    if not isinstance(projection, Mapping):
        return ""
    return str(projection.get("profile_id", "")).strip()


def _asset_inventory_digest(
    routes: Sequence[Mapping[str, Any]],
    *,
    authoritative_files: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    entries: list[dict[str, Any]] = []
    for route in routes:
        level_id = str(route.get("level_id", ""))
        assets = route.get("assets", {})
        if not isinstance(assets, Mapping):
            continue
        for field, value in sorted(assets.items()):
            if not isinstance(value, Mapping) or not value.get("sha256"):
                continue
            entries.append(
                {
                    "scope": "route_asset",
                    "level_id": level_id,
                    "field": str(field),
                    "path": str(value.get("path", "")).replace("\\", "/"),
                    "size": value.get("size"),
                    "sha256": str(value["sha256"]),
                }
            )
    for field, value in sorted((authoritative_files or {}).items()):
        if not isinstance(value, Mapping) or not value.get("sha256"):
            continue
        entries.append(
            {
                "scope": "authoritative_runtime_file",
                "field": str(field),
                "path": str(value.get("path", "")).replace("\\", "/"),
                "size_bytes": value.get("size_bytes"),
                "sha256": str(value["sha256"]),
            }
        )
    return _stable_json_digest(entries)


def _alpha_is_opaque_from_row(surface: pygame.Surface, start_y: int) -> bool:
    start = max(0, min(surface.get_height(), int(start_y)))
    if surface.get_masks()[3] == 0:
        return True
    rgba = pygame.image.tobytes(surface, "RGBA", False)
    width = surface.get_width()
    stride = width * 4
    for y in range(start, surface.get_height()):
        row = rgba[y * stride : (y + 1) * stride]
        if any(alpha != 255 for alpha in row[3::4]):
            return False
    return True


def _surface_has_transparency(surface: pygame.Surface) -> bool:
    if surface.get_masks()[3] == 0:
        return False
    rgba = pygame.image.tobytes(surface, "RGBA", False)
    return any(alpha < 255 for alpha in rgba[3::4])


def _format_reference_tokens(route: Mapping[str, Any], gameplay_level: Mapping[str, Any] | None) -> list[str]:
    tokens: list[str] = []
    for field in ("landmarks", "opposite_side_landmarks", "registered_features"):
        for item in _as_sequence(route.get(field, ())):
            if not isinstance(item, Mapping):
                continue
            feature_id = str(item.get("id", "")).strip()
            if feature_id:
                tokens.append(feature_id.lower())
            kind = str(item.get("kind", "")).strip().lower()
            if kind:
                tokens.append(kind)
    if gameplay_level is not None:
        geometry = gameplay_level.get("stage_geometry", {})
        for item in _as_sequence(geometry.get("obstacles", ())):
            if not isinstance(item, Mapping):
                continue
            obstacle_id = str(item.get("id", "")).strip().lower()
            if obstacle_id:
                tokens.append(obstacle_id)
            obstacle_kind = str(item.get("kind", "")).strip().lower()
            if obstacle_kind:
                tokens.append(obstacle_kind)
            location_feature_id = str(item.get("location_feature_id", "")).strip().lower()
            if location_feature_id:
                tokens.append(location_feature_id)
        for item in _as_sequence(geometry.get("rails", ())):
            if not isinstance(item, Mapping):
                continue
            for key in ("near_depth", "far_depth", "start_x", "end_x"):
                value = item.get(key)
                if value is not None:
                    tokens.append(str(value).lower())
    return sorted(set(tokens))


def _surface_is_fully_opaque(surface: pygame.Surface) -> bool:
    """Return whether every source pixel has alpha 255, regardless of PNG mode."""

    if surface.get_masks()[3] == 0:
        return True
    rgba = pygame.image.tobytes(surface, "RGBA", False)
    return all(alpha == 255 for alpha in rgba[3::4])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _raw_campaign_chapters(
    gameplay: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    """Read only the canonical ``campaign.chapters`` authoring container."""

    campaign = gameplay.get("campaign", {})
    if not isinstance(campaign, Mapping):
        return ()
    chapters = campaign.get("chapters", ())
    if not isinstance(chapters, Sequence) or isinstance(chapters, (str, bytes)):
        return ()
    return tuple(chapter for chapter in chapters if isinstance(chapter, Mapping))


def _raw_campaign_levels(gameplay: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Flatten canonical authored chapters in the same order as runtime config."""

    levels: list[dict[str, Any]] = []
    for chapter in _raw_campaign_chapters(gameplay):
        chapter_levels = chapter.get("levels", ())
        if not isinstance(chapter_levels, Sequence) or isinstance(chapter_levels, (str, bytes)):
            continue
        levels.extend(dict(level) for level in chapter_levels if isinstance(level, Mapping))
    return tuple(levels)


def build_location_lock_report(
    project_root: Path | str = PROJECT_ROOT,
    *,
    manifest: Mapping[str, Any] | None = None,
    gameplay: Mapping[str, Any] | None = None,
    chapter_content: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate source or packaged Chapter 1 location data and image assets.

    The function deliberately reads files relative to ``project_root`` rather
    than through ``resource_path``.  The Windows build uses that distinction
    to catch incomplete package and Desktop copies.
    """

    root = Path(project_root).resolve()
    checks: list[dict[str, Any]] = []
    route_results: list[dict[str, Any]] = []

    def record(
        condition: bool,
        check_id: str,
        detail: str,
        *,
        level_id: str | None = None,
    ) -> None:
        item: dict[str, Any] = {
            "id": check_id,
            "status": "pass" if condition else "fail",
            "detail": detail,
        }
        if level_id is not None:
            item["level_id"] = level_id
        checks.append(item)

    try:
        manifest_data = (
            dict(manifest)
            if manifest is not None
            else _read_json_file(root / "data" / "chapter1_location_lock.json")
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        record(False, "manifest_readable", str(error))
        return {
            "classification": "chapter1_location_lock_source_or_package_validation",
            "project_root": str(root),
            "checks": checks,
            "errors": [checks[-1]],
            "routes": route_results,
            "passed": False,
        }

    try:
        gameplay_data = (
            dict(gameplay)
            if gameplay is not None
            else _read_json_file(root / "data" / "gameplay.json")
        )
        record(True, "gameplay_readable", "data/gameplay.json is readable")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        gameplay_data = {}
        record(False, "gameplay_readable", str(error))

    try:
        content_data = (
            dict(chapter_content)
            if chapter_content is not None
            else _read_json_file(root / "data" / "chapter_content.json")
        )
        record(True, "chapter_content_readable", "data/chapter_content.json is readable")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        content_data = {}
        record(False, "chapter_content_readable", str(error))

    try:
        atmosphere_data = _read_json_file(root / "data" / "atmosphere.json")
        record(True, "atmosphere_readable", "data/atmosphere.json is readable")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        atmosphere_data = {}
        record(False, "atmosphere_readable", str(error))

    projection_profiles = _projection_profiles(gameplay_data)
    active_projection_profile_id = _active_projection_profile_id(gameplay_data)
    chapter_projection = projection_profiles.get("chapter1_oblique_v2")
    record(
        isinstance(chapter_projection, Mapping),
        "chapter1_projection_profile_defined",
        (
            "engine.projection_profiles contains chapter1_oblique_v2"
            if isinstance(chapter_projection, Mapping)
            else f"available_profiles={sorted(str(key) for key in projection_profiles)!r}"
        ),
    )
    record(
        active_projection_profile_id == "chapter1_oblique_v2",
        "chapter1_projection_profile_active",
        f"active_profile_id={active_projection_profile_id!r}",
    )
    atmosphere_profiles = atmosphere_data.get("profiles", {})
    if not isinstance(atmosphere_profiles, Mapping):
        atmosphere_profiles = {}
    route_atmosphere_profiles = atmosphere_data.get("route_profile_map", {})
    if not isinstance(route_atmosphere_profiles, Mapping):
        route_atmosphere_profiles = {}

    authoritative_manifest: Mapping[str, Any] | None = None
    try:
        authoritative_manifest = location_lock.validate_location_lock(
            manifest_data,
            project_root=root,
            validate_assets=True,
        )
        record(
            True,
            "authoritative_manifest_validation",
            "src.location_lock accepted geography, provenance, spacing, and assets",
        )
    except (location_lock.LocationLockError, OSError, ValueError) as error:
        record(False, "authoritative_manifest_validation", str(error))
    if authoritative_manifest is not None:
        try:
            location_lock.validate_gameplay_locations(
                gameplay_data,
                authoritative_manifest,
            )
            record(
                True,
                "authoritative_gameplay_location_validation",
                "gameplay route facts and registered collision features agree",
            )
        except (location_lock.LocationLockError, OSError, ValueError) as error:
            record(False, "authoritative_gameplay_location_validation", str(error))
        try:
            location_lock.validate_chapter_content_locations(
                content_data,
                authoritative_manifest,
                gameplay=gameplay_data,
            )
            record(
                True,
                "authoritative_chapter_content_location_validation",
                "narrative endpoints and travel handoffs agree",
            )
        except (location_lock.LocationLockError, OSError, ValueError) as error:
            record(False, "authoritative_chapter_content_location_validation", str(error))
    else:
        record(
            False,
            "authoritative_gameplay_location_validation",
            "skipped because authoritative manifest validation failed",
        )
        record(
            False,
            "authoritative_chapter_content_location_validation",
            "skipped because authoritative manifest validation failed",
        )

    schema_version = manifest_data.get("schema_version")
    record(
        isinstance(schema_version, int) and not isinstance(schema_version, bool) and schema_version == 2,
        "manifest_schema_version",
        f"schema_version={schema_version!r}",
    )
    record(
        _is_iso_date(manifest_data.get("research_access_date")),
        "manifest_research_access_date",
        f"research_access_date={manifest_data.get('research_access_date')!r}",
    )
    references_value = manifest_data.get("mandatory_references", ())
    references = (
        tuple(reference for reference in references_value if isinstance(reference, Mapping))
        if isinstance(references_value, Sequence)
        and not isinstance(references_value, (str, bytes))
        else ()
    )
    reference_ids = tuple(str(reference.get("id", "")) for reference in references)
    record(
        reference_ids == _MANDATORY_REFERENCE_IDS,
        "mandatory_reference_coverage",
        (
            f"expected={list(_MANDATORY_REFERENCE_IDS)!r}; "
            f"actual={list(reference_ids)!r}"
        ),
    )
    invalid_references = [
        str(reference.get("id", "<missing>"))
        for reference in references
        if not (
            isinstance(reference.get("url"), str)
            and str(reference["url"]).startswith("https://")
            and str(reference.get("address", "")).strip()
            and str(reference.get("view_direction", "")).strip()
            and str(reference.get("imagery_date", "")).strip()
            and _is_iso_date(reference.get("access_date"))
            and reference.get("access_date") == manifest_data.get("research_access_date")
        )
    ]
    record(
        not invalid_references,
        "mandatory_reference_metadata",
        f"invalid={invalid_references!r}",
    )
    routes_value = manifest_data.get("routes", ())
    routes = (
        tuple(route for route in routes_value if isinstance(route, Mapping))
        if isinstance(routes_value, Sequence) and not isinstance(routes_value, (str, bytes))
        else ()
    )
    route_ids = tuple(str(route.get("level_id", "")) for route in routes)
    record(
        route_ids == _LEVEL_IDS,
        "manifest_route_order",
        f"expected={list(_LEVEL_IDS)!r}; actual={list(route_ids)!r}",
    )
    record(
        len(route_ids) == len(set(route_ids)),
        "manifest_route_ids_unique",
        f"route_ids={list(route_ids)!r}",
    )

    stage_chunks_data: Mapping[str, Any] | None = None
    try:
        loaded_stage_chunks = _read_json_file(root / "data" / "stage_chunks.json")
        stage_chunks_data = loaded_stage_chunks
        record(
            loaded_stage_chunks.get("schema_version") == 1,
            "stage_chunk_manifest_schema",
            f"schema_version={loaded_stage_chunks.get('schema_version')!r}",
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        record(False, "stage_chunk_manifest_readable", str(error))
    else:
        record(
            True,
            "stage_chunk_manifest_readable",
            "data/stage_chunks.json is readable",
        )

    raw_gameplay_levels = {
        str(level.get("id", "")): level
        for level in _raw_campaign_levels(gameplay_data)
        if str(level.get("id", "")).startswith("chapter_1_level_")
    }
    chapter_one_containers = tuple(
        chapter
        for chapter in _raw_campaign_chapters(gameplay_data)
        if str(chapter.get("id", "")) == "chapter_1"
    )
    chapter_one_level_ids = tuple(
        str(level.get("id", ""))
        for chapter in chapter_one_containers
        for level in chapter.get("levels", ())
        if isinstance(level, Mapping)
    )
    record(
        len(chapter_one_containers) == 1 and chapter_one_level_ids == _LEVEL_IDS,
        "gameplay_chapter_1_structure",
        (
            f"chapter_1_containers={len(chapter_one_containers)}; "
            f"level_ids={list(chapter_one_level_ids)!r}"
        ),
    )
    runtime_gameplay = deepcopy(gameplay_data)
    if authoritative_manifest is not None:
        location_lock.hydrate_gameplay_locations(runtime_gameplay, authoritative_manifest)
    gameplay_levels = {
        str(level.get("id", "")): level
        for level in _raw_campaign_levels(runtime_gameplay)
        if str(level.get("id", "")).startswith("chapter_1_level_")
    }
    content_levels_value = content_data.get("levels", ())
    content_levels = {
        str(level.get("runtime_level_id", "")): level
        for level in (
            content_levels_value
            if isinstance(content_levels_value, Sequence)
            and not isinstance(content_levels_value, (str, bytes))
            else ()
        )
        if isinstance(level, Mapping)
    }
    record(
        tuple(gameplay_levels) == _LEVEL_IDS,
        "gameplay_route_ids",
        f"actual={list(gameplay_levels)!r}",
    )
    record(
        tuple(content_levels) == _LEVEL_IDS,
        "chapter_content_route_ids",
        f"actual={list(content_levels)!r}",
    )

    for route in routes:
        level_id = str(route.get("level_id", ""))
        theme = str(route.get("theme", ""))
        route_checks_before = len(checks)
        expected_endpoints = _EXPECTED_ENDPOINTS.get(level_id, ("", ""))
        world_width_value = route.get("world_width")
        world_width_valid = (
            isinstance(world_width_value, int)
            and not isinstance(world_width_value, bool)
            and world_width_value >= int(LOGICAL_SIZE[0])
        )
        world_width = int(world_width_value) if world_width_valid else int(LOGICAL_SIZE[0])
        record(
            world_width_valid,
            "route_world_width",
            f"world_width={world_width_value!r}",
            level_id=level_id,
        )
        record(
            route.get("travel_direction") == "northbound"
            and route.get("screen_travel") == "left_to_right"
            and route.get("playable_side") == "west_even",
            "route_orientation",
            (
                f"direction={route.get('travel_direction')!r}, "
                f"screen={route.get('screen_travel')!r}, side={route.get('playable_side')!r}"
            ),
            level_id=level_id,
        )
        record(
            (
                str(route.get("start_anchor_id", "")),
                str(route.get("end_anchor_id", "")),
            )
            == expected_endpoints,
            "route_endpoints",
            (
                f"expected={expected_endpoints!r}; actual="
                f"{(route.get('start_anchor_id'), route.get('end_anchor_id'))!r}"
            ),
            level_id=level_id,
        )
        declared_size = route.get("main_panorama_size")
        record(
            declared_size == [world_width, int(LOGICAL_SIZE[1])],
            "route_declared_panorama_size",
            f"main_panorama_size={declared_size!r}",
            level_id=level_id,
        )
        record(
            route.get("far_asset_size") == [world_width, int(LOGICAL_SIZE[1])]
            and route.get("near_asset_size") == [world_width, int(LOGICAL_SIZE[1])],
            "route_declared_layer_sizes",
            (
                f"far_asset_size={route.get('far_asset_size')!r}; "
                f"near_asset_size={route.get('near_asset_size')!r}"
            ),
            level_id=level_id,
        )
        record(
            route.get("main_world_rate") == 1.0,
            "route_main_world_rate",
            f"main_world_rate={route.get('main_world_rate')!r}",
            level_id=level_id,
        )
        for rate_field, relation in (("far_parallax", "far"), ("near_parallax", "near")):
            value = route.get(rate_field)
            valid = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and (
                    0.0 <= float(value) < 1.0
                    if relation == "far"
                    else 1.0 < float(value) <= 1.15
                )
            )
            record(
                valid,
                f"route_{rate_field}",
                f"{rate_field}={value!r}",
                level_id=level_id,
            )
        record(
            isinstance(route.get("far_max_offset"), (int, float))
            and not isinstance(route.get("far_max_offset"), bool)
            and 0 <= float(route["far_max_offset"]) <= 128
            and isinstance(route.get("near_max_offset"), (int, float))
            and not isinstance(route.get("near_max_offset"), bool)
            and 0 <= float(route["near_max_offset"]) <= 96,
            "route_parallax_offsets",
            (
                f"far_max_offset={route.get('far_max_offset')!r}; "
                f"near_max_offset={route.get('near_max_offset')!r}"
            ),
            level_id=level_id,
        )
        route_projection_profile_id = str(
            route.get("projection_profile_id", "")
        ).strip()
        record(
            route_projection_profile_id == "chapter1_oblique_v2"
            and route_projection_profile_id in projection_profiles,
            "route_projection_profile",
            (
                f"route_profile={route_projection_profile_id!r}; "
                f"active_profile={active_projection_profile_id!r}"
            ),
            level_id=level_id,
        )
        route_sky_profile_id = str(route.get("sky_profile_id", "")).strip()
        mapped_sky_profile_id = str(
            route_atmosphere_profiles.get(level_id, "")
        ).strip()
        record(
            bool(route_sky_profile_id)
            and route_sky_profile_id == mapped_sky_profile_id
            and route_sky_profile_id in atmosphere_profiles,
            "route_atmosphere_profile",
            (
                f"route_sky_profile={route_sky_profile_id!r}; "
                f"mapped_profile={mapped_sky_profile_id!r}"
            ),
            level_id=level_id,
        )
        layered_fields_present = all(
            str(route.get(field, "")).strip()
            and route.get(f"{field}_size")
            == [world_width, int(LOGICAL_SIZE[1])]
            for field in _LAYERED_LOCATION_ASSET_FIELDS
        )
        deprecated_layer_aliases = {
            canonical: alias
            for canonical, alias in _LAYERED_FIELD_ALIASES.items()
            if alias in route and canonical not in route
        }
        record(
            layered_fields_present and not deprecated_layer_aliases,
            "route_layered_runtime_schema",
            (
                f"canonical_fields={list(_LAYERED_LOCATION_ASSET_FIELDS)!r}; "
                f"deprecated_aliases={deprecated_layer_aliases!r}"
            ),
            level_id=level_id,
        )

        landmarks_value = route.get("landmarks", ())
        landmarks = (
            tuple(item for item in landmarks_value if isinstance(item, Mapping))
            if isinstance(landmarks_value, Sequence)
            and not isinstance(landmarks_value, (str, bytes))
            else ()
        )
        landmark_ids = tuple(str(item.get("id", "")) for item in landmarks)
        record(
            bool(landmarks) and len(landmark_ids) == len(set(landmark_ids)) and all(landmark_ids),
            "route_landmark_ids_unique",
            f"landmark_ids={list(landmark_ids)!r}",
            level_id=level_id,
        )
        required_order = _MANDATORY_LANDMARK_ORDER.get(level_id, ())
        record(
            _contains_ordered_subsequence(landmark_ids, required_order),
            "route_mandatory_landmark_order",
            f"required={list(required_order)!r}; actual={list(landmark_ids)!r}",
            level_id=level_id,
        )
        record(
            bool(landmark_ids)
            and landmark_ids[0] == str(route.get("start_anchor_id", ""))
            and landmark_ids[-1] == str(route.get("end_anchor_id", "")),
            "route_anchor_membership",
            (
                f"first={landmark_ids[0] if landmark_ids else None!r}; "
                f"last={landmark_ids[-1] if landmark_ids else None!r}"
            ),
            level_id=level_id,
        )

        distances: list[float] = []
        world_positions: list[int] = []
        for landmark in landmarks:
            landmark_id = str(landmark.get("id", ""))
            label = f"{level_id}:{landmark_id or '<missing>'}"
            numeric_valid = True
            try:
                latitude = float(landmark["latitude"])
                longitude = float(landmark["longitude"])
                normalized = float(landmark["normalized_route_distance"])
                world_x = int(landmark["world_x"])
                numeric_valid = (
                    math.isfinite(latitude)
                    and math.isfinite(longitude)
                    and 0.0 <= normalized <= 1.0
                    and 0 <= world_x <= world_width
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                latitude = longitude = normalized = float("nan")
                world_x = -1
                numeric_valid = False
            record(
                numeric_valid,
                "landmark_coordinates",
                (
                    f"{label}: lat={landmark.get('latitude')!r}, "
                    f"lon={landmark.get('longitude')!r}, "
                    f"distance={landmark.get('normalized_route_distance')!r}, "
                    f"world_x={landmark.get('world_x')!r}"
                ),
                level_id=level_id,
            )
            distances.append(normalized)
            world_positions.append(world_x)
            record(
                landmark.get("street_side") == "west",
                "landmark_street_side",
                f"{label}: street_side={landmark.get('street_side')!r}",
                level_id=level_id,
            )
            record(
                all(str(landmark.get(field, "")).strip() for field in ("real_name", "display_name", "address", "setback")),
                "landmark_identity_metadata",
                f"{label}: identity/address/setback fields are populated",
                level_id=level_id,
            )
            source_urls = landmark.get("source_urls")
            neighboring_anchors = landmark.get("neighboring_anchors")
            metadata_valid = (
                _is_iso_date(landmark.get("source_date"))
                and str(landmark.get("imagery_date", "")).strip()
                and _is_iso_date(landmark.get("access_date"))
                and isinstance(source_urls, Sequence)
                and not isinstance(source_urls, (str, bytes))
                and bool(source_urls)
                and all(isinstance(url, str) and url.startswith("https://") for url in source_urls)
                and str(landmark.get("confidence", "")).lower() in _CONFIDENCE_VALUES
                and all(
                    str(landmark.get(field, "")).strip()
                    for field in (
                        "view_direction",
                        "durable_massing",
                        "parking_setback",
                        "driveway_placement",
                    )
                )
                and isinstance(neighboring_anchors, list)
                and bool(neighboring_anchors)
                and all(str(item).strip() for item in neighboring_anchors)
            )
            record(
                metadata_valid,
                "landmark_source_metadata",
                (
                    f"{label}: required={list(_LANDMARK_SOURCE_FIELDS)!r}; "
                    f"confidence={landmark.get('confidence')!r}"
                ),
                level_id=level_id,
            )

        record(
            all(left <= right for left, right in zip(distances, distances[1:])),
            "landmark_distance_order",
            f"distances={distances!r}",
            level_id=level_id,
        )
        record(
            all(left < right for left, right in zip(world_positions, world_positions[1:])),
            "landmark_world_order",
            f"world_x={world_positions!r}",
            level_id=level_id,
        )
        if len(landmarks) >= 2 and world_positions[-1] > world_positions[0]:
            span = float(world_positions[-1] - world_positions[0])
            missing_reasons = []
            for landmark, normalized, world_x in zip(landmarks, distances, world_positions):
                expected_x = world_positions[0] + normalized * span
                deviation = abs(world_x - expected_x) / span
                if deviation > 0.15 and not str(landmark.get("compression_reason", "")).strip():
                    missing_reasons.append(str(landmark.get("id", "")))
            record(
                not missing_reasons,
                "landmark_compression_reasons",
                f"missing_for={missing_reasons!r}",
                level_id=level_id,
            )

        opposite_value = route.get("opposite_side_landmarks", ())
        opposite = (
            tuple(item for item in opposite_value if isinstance(item, Mapping))
            if isinstance(opposite_value, Sequence)
            and not isinstance(opposite_value, (str, bytes))
            else ()
        )
        record(
            all(
                str(item.get("id", "")).strip()
                and item.get("street_side") == "east"
                and 0 <= int(item.get("world_x", -1)) <= world_width
                and _is_iso_date(item.get("source_date"))
                and str(item.get("imagery_date", "")).strip()
                and _is_iso_date(item.get("access_date"))
                and isinstance(item.get("source_urls"), list)
                and bool(item.get("source_urls"))
                and all(
                    isinstance(url, str) and url.startswith("https://")
                    for url in item.get("source_urls", ())
                )
                and str(item.get("confidence", "")).lower() in _CONFIDENCE_VALUES
                for item in opposite
            ),
            "opposite_side_landmarks",
            f"count={len(opposite)}",
            level_id=level_id,
        )

        asset_results: dict[str, Any] = {}
        for field in _LOCATION_ASSET_FIELDS:
            relative = str(route.get(field, "")).replace("\\", "/")
            asset_path = (root / relative).resolve() if relative else root
            within_root = asset_path == root or root in asset_path.parents
            in_location_folder = relative.startswith(_LOCATION_ASSET_PREFIX)
            exists = within_root and asset_path.is_file()
            record(
                bool(relative) and within_root and in_location_folder and exists,
                f"{field}_path",
                f"{field}={relative!r}; exists={exists}",
                level_id=level_id,
            )
            result: dict[str, Any] = {
                "path": relative,
                "exists": exists,
                "size": None,
                "sha256": None,
                "fully_opaque": None,
                "has_alpha": None,
            }
            if exists:
                try:
                    surface = pygame.image.load(str(asset_path))
                    size = surface.get_size()
                    result["size"] = list(size)
                    result["sha256"] = _sha256_file(asset_path)
                    result["has_alpha"] = surface.get_masks()[3] != 0
                    expected_size = (world_width, int(LOGICAL_SIZE[1]))
                    record(
                        size == expected_size,
                        f"{field}_dimensions",
                        f"{relative}: expected={expected_size!r}; actual={size!r}",
                        level_id=level_id,
                    )
                    if field == "main_panorama_asset":
                        opaque = _surface_is_fully_opaque(surface)
                        result["fully_opaque"] = opaque
                        record(
                            opaque,
                            "main_panorama_fully_opaque",
                            f"{relative}: fully_opaque={opaque}",
                            level_id=level_id,
                        )
                    else:
                        has_alpha = bool(result["has_alpha"])
                        record(
                            has_alpha,
                            f"{field}_has_alpha",
                            f"{relative}: has_alpha={has_alpha}",
                            level_id=level_id,
                        )
                        if field in _LAYERED_LOCATION_ASSET_FIELDS:
                            has_transparency = _surface_has_transparency(surface)
                            result["has_transparency"] = has_transparency
                            record(
                                has_transparency,
                                f"{field}_has_transparency",
                                f"{relative}: has_transparency={has_transparency}",
                                level_id=level_id,
                            )
                        if field == "ground_asset":
                            opaque_from_y = route.get("ground_opaque_from_y")
                            ground_row = (
                                int(opaque_from_y)
                                if isinstance(opaque_from_y, (int, float))
                                and not isinstance(opaque_from_y, bool)
                                else -1
                            )
                            floor_opaque = (
                                0 <= ground_row < int(LOGICAL_SIZE[1])
                                and _alpha_is_opaque_from_row(surface, ground_row)
                            )
                            result["opaque_from_y"] = ground_row
                            result["floor_fully_opaque"] = floor_opaque
                            record(
                                floor_opaque,
                                "ground_asset_floor_coverage",
                                (
                                    f"{relative}: ground_opaque_from_y={ground_row}; "
                                    f"floor_fully_opaque={floor_opaque}"
                                ),
                                level_id=level_id,
                            )
                except (OSError, pygame.error, ValueError) as error:
                    record(
                        False,
                        f"{field}_readable",
                        f"{relative}: {error}",
                        level_id=level_id,
                    )
            asset_results[field] = result

        stage_chunk_results: dict[str, Any] = {}
        if stage_chunks_data is None:
            record(
                False,
                "stage_chunk_route_validation",
                "skipped because data/stage_chunks.json could not be read",
                level_id=level_id,
            )
        else:
            try:
                stage_world = StageWorld.from_route(route, stage_chunks_data)
            except (StageWorldError, TypeError, ValueError) as error:
                record(
                    False,
                    "stage_chunk_route_validation",
                    str(error),
                    level_id=level_id,
                )
            else:
                record(
                    True,
                    "stage_chunk_route_validation",
                    (
                        f"chunks={len(stage_world.chunks)}; "
                        f"world_width={stage_world.world_width}; "
                        "main layers remain world-locked"
                    ),
                    level_id=level_id,
                )
                stage_chunk_results["chunk_count"] = len(stage_world.chunks)
                stage_chunk_results["asset_count"] = 0
                for chunk in stage_world.chunks:
                    for piece in chunk.layer_pieces:
                        relative = piece.asset
                        asset_path = (root / relative).resolve()
                        within_root = asset_path == root or root in asset_path.parents
                        exists = within_root and asset_path.is_file()
                        asset_key = f"stage_chunk.{chunk.chunk_id}.{piece.layer}"
                        record(
                            exists,
                            "stage_chunk_asset_path",
                            f"{asset_key}={relative!r}; exists={exists}",
                            level_id=level_id,
                        )
                        result = {
                            "path": relative,
                            "exists": exists,
                            "size": None,
                            "sha256": None,
                            "has_alpha": None,
                        }
                        if exists:
                            try:
                                chunk_surface = pygame.image.load(str(asset_path))
                                result["size"] = list(chunk_surface.get_size())
                                result["sha256"] = _sha256_file(asset_path)
                                result["has_alpha"] = bool(chunk_surface.get_masks()[3])
                                record(
                                    chunk_surface.get_size() == (piece.width, piece.height),
                                    "stage_chunk_asset_dimensions",
                                    (
                                        f"{asset_key}: expected={(piece.width, piece.height)!r}; "
                                        f"actual={chunk_surface.get_size()!r}"
                                    ),
                                    level_id=level_id,
                                )
                                record(
                                    bool(result["has_alpha"]),
                                    "stage_chunk_asset_has_alpha",
                                    f"{asset_key}: has_alpha={result['has_alpha']}",
                                    level_id=level_id,
                                )
                            except (OSError, pygame.error, ValueError) as error:
                                record(
                                    False,
                                    "stage_chunk_asset_readable",
                                    f"{asset_key}: {error}",
                                    level_id=level_id,
                                )
                        asset_results[asset_key] = result
                        stage_chunk_results["asset_count"] += 1
                for global_layer, relative in stage_world.global_layers.items():
                    asset_path = (root / relative).resolve()
                    within_root = asset_path == root or root in asset_path.parents
                    exists = within_root and asset_path.is_file()
                    asset_key = f"stage_global.{global_layer}"
                    record(
                        exists,
                        "stage_global_asset_path",
                        f"{asset_key}={relative!r}; exists={exists}",
                        level_id=level_id,
                    )
                    result = {
                        "path": relative,
                        "exists": exists,
                        "size": None,
                        "sha256": None,
                    }
                    if exists:
                        try:
                            global_surface = pygame.image.load(str(asset_path))
                            result["size"] = list(global_surface.get_size())
                            result["sha256"] = _sha256_file(asset_path)
                            record(
                                global_surface.get_height() == int(LOGICAL_SIZE[1]),
                                "stage_global_asset_dimensions",
                                f"{asset_key}: size={global_surface.get_size()!r}",
                                level_id=level_id,
                            )
                        except (OSError, pygame.error, ValueError) as error:
                            record(
                                False,
                                "stage_global_asset_readable",
                                f"{asset_key}: {error}",
                                level_id=level_id,
                            )
                    asset_results[asset_key] = result

        physical_objects_value = route.get("physical_scene_objects", ())
        physical_objects = (
            tuple(
                item
                for item in physical_objects_value
                if isinstance(item, Mapping)
            )
            if isinstance(physical_objects_value, Sequence)
            and not isinstance(physical_objects_value, (str, bytes))
            else ()
        )
        object_ids = tuple(str(item.get("id", "")).strip() for item in physical_objects)
        record(
            isinstance(physical_objects_value, list)
            and bool(physical_objects)
            and len(object_ids) == len(set(object_ids))
            and all(object_ids),
            "physical_scene_objects_unique",
            f"object_ids={list(object_ids)!r}",
            level_id=level_id,
        )
        landmark_id_set = set(landmark_ids)
        registered_feature_ids = {
            str(item.get("id", "")).strip()
            for item in route.get("registered_features", ())
            if isinstance(item, Mapping)
        }
        adult_height_m = None
        if isinstance(chapter_projection, Mapping):
            reference_dimensions = chapter_projection.get(
                "reference_physical_dimensions",
                {},
            )
            if isinstance(reference_dimensions, Mapping):
                adult_height_m = _finite_number_or_none(
                    reference_dimensions.get("neutral_adult_height_m")
                )
        physical_asset_results: list[dict[str, Any]] = []
        for object_index, item in enumerate(physical_objects):
            object_id = str(item.get("id", f"<index:{object_index}>")).strip()
            missing_fields = [
                field
                for field in _PHYSICAL_SCENE_OBJECT_FIELDS
                if field not in item
            ]
            record(
                not missing_fields,
                "physical_scene_object_schema",
                f"{object_id}: missing_fields={missing_fields!r}",
                level_id=level_id,
            )
            world_x = _finite_number_or_none(item.get("world_x"))
            depth = _finite_number_or_none(item.get("depth"))
            elevation = _finite_number_or_none(item.get("elevation"))
            physical_height_m = _finite_number_or_none(
                item.get("physical_height_m")
            )
            record(
                world_x is not None
                and 0 <= world_x <= world_width
                and depth is not None
                and 0 <= depth <= int(LOGICAL_SIZE[1])
                and elevation is not None
                and elevation >= 0
                and physical_height_m is not None
                and 0 < physical_height_m <= 12,
                "physical_scene_object_coordinates",
                (
                    f"{object_id}: world_x={world_x!r}; depth={depth!r}; "
                    f"elevation={elevation!r}; height_m={physical_height_m!r}"
                ),
                level_id=level_id,
            )
            anchor = str(item.get("anchor", "")).strip()
            collision_reference = str(
                item.get("collision_feature_reference", "")
            ).strip()
            record(
                anchor in landmark_id_set
                and (
                    not collision_reference
                    or collision_reference in registered_feature_ids
                    or collision_reference in landmark_id_set
                ),
                "physical_scene_object_registration",
                (
                    f"{object_id}: anchor={anchor!r}; "
                    f"collision_reference={collision_reference!r}"
                ),
                level_id=level_id,
            )
            kind = str(item.get("kind", "")).strip().lower()
            ratio_ok = True
            ratio = None
            if adult_height_m and physical_height_m:
                ratio = physical_height_m / adult_height_m
                if kind in {"sedan", "car"}:
                    ratio_ok = 0.70 <= ratio <= 0.90
                elif kind == "door":
                    ratio_ok = 1.05 <= ratio <= 1.20
            record(
                ratio_ok,
                "physical_scene_object_reference_ratio",
                f"{object_id}: kind={kind!r}; adult_ratio={ratio!r}",
                level_id=level_id,
            )
            relative_object_asset = str(item.get("asset", "")).replace("\\", "/")
            object_asset_path = (
                (root / relative_object_asset).resolve()
                if relative_object_asset
                else root
            )
            object_asset_within_root = (
                object_asset_path == root or root in object_asset_path.parents
            )
            object_asset_exists = (
                bool(relative_object_asset)
                and object_asset_within_root
                and relative_object_asset.startswith("assets/")
                and object_asset_path.is_file()
            )
            object_asset_result = {
                "id": object_id,
                "path": relative_object_asset,
                "exists": object_asset_exists,
                "size": None,
                "sha256": None,
            }
            if object_asset_exists:
                try:
                    object_surface = pygame.image.load(str(object_asset_path))
                    object_asset_result["size"] = list(object_surface.get_size())
                    object_asset_result["sha256"] = _sha256_file(object_asset_path)
                    object_asset_exists = (
                        object_surface.get_width() > 0
                        and object_surface.get_height() > 0
                        and object_surface.get_masks()[3] != 0
                    )
                except (OSError, pygame.error, ValueError):
                    object_asset_exists = False
            object_asset_result["exists"] = object_asset_exists
            physical_asset_results.append(object_asset_result)
            record(
                object_asset_exists,
                "physical_scene_object_asset",
                (
                    f"{object_id}: asset={relative_object_asset!r}; "
                    f"exists={object_asset_exists}"
                ),
                level_id=level_id,
            )
        asset_results["physical_scene_object_assets"] = {
            "path": "<per-object>",
            "exists": bool(physical_asset_results)
            and all(item["exists"] for item in physical_asset_results),
            "size": None,
            "sha256": _stable_json_digest(physical_asset_results)
            if physical_asset_results
            else None,
            "items": physical_asset_results,
        }

        features_value = route.get("registered_features", ())
        features = (
            tuple(item for item in features_value if isinstance(item, Mapping))
            if isinstance(features_value, Sequence)
            and not isinstance(features_value, (str, bytes))
            else ()
        )
        feature_map = {
            str(item.get("id", "")): item
            for item in features
            if str(item.get("id", "")).strip()
        }
        record(
            bool(features) and len(feature_map) == len(features),
            "registered_features_unique",
            f"feature_ids={list(feature_map)!r}",
            level_id=level_id,
        )
        record(
            all(
                str(feature.get("kind", "")).strip()
                and isinstance(feature.get("world_x"), int)
                and not isinstance(feature.get("world_x"), bool)
                and 0 <= int(feature["world_x"]) <= world_width
                for feature in features
            ),
            "registered_features_valid",
            f"feature_count={len(features)}",
            level_id=level_id,
        )

        gameplay_level = gameplay_levels.get(level_id)
        record(
            gameplay_level is not None,
            "gameplay_level_exists",
            f"gameplay level {level_id!r} exists",
            level_id=level_id,
        )
        if gameplay_level is not None:
            raw_gameplay_level = raw_gameplay_levels.get(level_id, {})
            record(
                "background_theme" not in raw_gameplay_level
                and "stage_width" not in raw_gameplay_level
                and "landmarks" not in raw_gameplay_level,
                "gameplay_route_facts_manifest_owned",
                (
                    "raw gameplay omits manifest-owned theme, width, and "
                    "materialized landmark records"
                ),
                level_id=level_id,
            )
            gameplay_landmark_ids = gameplay_level.get("landmark_ids")
            record(
                gameplay_landmark_ids == list(landmark_ids),
                "gameplay_landmark_ids_match",
                f"gameplay={gameplay_landmark_ids!r}; manifest={list(landmark_ids)!r}",
                level_id=level_id,
            )
            record(
                str(gameplay_level.get("background_theme", "")) == theme
                and int(gameplay_level.get("stage_width", -1)) == world_width,
                "gameplay_theme_width_match",
                (
                    f"gameplay_theme={gameplay_level.get('background_theme')!r}, "
                    f"gameplay_width={gameplay_level.get('stage_width')!r}"
                ),
                level_id=level_id,
            )
            record(
                str(gameplay_level.get("start", {}).get("id", ""))
                == str(route.get("start_anchor_id", ""))
                and str(gameplay_level.get("end", {}).get("id", ""))
                == str(route.get("end_anchor_id", "")),
                "gameplay_endpoints_match",
                (
                    f"start={gameplay_level.get('start', {}).get('id')!r}, "
                    f"end={gameplay_level.get('end', {}).get('id')!r}"
                ),
                level_id=level_id,
            )
            geometry = gameplay_level.get("stage_geometry", {})
            obstacles = (
                geometry.get("obstacles", ())
                if isinstance(geometry, Mapping)
                and isinstance(geometry.get("obstacles", ()), Sequence)
                else ()
            )
            missing_links: list[str] = []
            misaligned: list[dict[str, Any]] = []
            for obstacle in obstacles:
                if not isinstance(obstacle, Mapping):
                    missing_links.append("<invalid>")
                    continue
                obstacle_id = str(obstacle.get("id", "<missing>"))
                feature_id = str(obstacle.get("location_feature_id", ""))
                feature = feature_map.get(feature_id)
                if feature is None:
                    missing_links.append(obstacle_id)
                    continue
                delta = abs(float(obstacle.get("x", -10_000)) - float(feature["world_x"]))
                if delta > 8.0:
                    misaligned.append(
                        {
                            "obstacle_id": obstacle_id,
                            "feature_id": feature_id,
                            "delta": round(delta, 3),
                        }
                    )
            record(
                not missing_links,
                "obstacle_feature_registration",
                f"missing_links={missing_links!r}",
                level_id=level_id,
            )
            record(
                not misaligned,
                "obstacle_art_alignment",
                f"misaligned={misaligned!r}",
                level_id=level_id,
            )
            rails = (
                geometry.get("rails", ())
                if isinstance(geometry, Mapping)
                and isinstance(geometry.get("rails", ()), Sequence)
                else ()
            )
            rail_cursor = 0.0
            rails_valid = bool(rails)
            for rail in rails:
                if not isinstance(rail, Mapping):
                    rails_valid = False
                    continue
                try:
                    start_x = float(rail["start_x"])
                    end_x = float(rail["end_x"])
                    far_depth = float(rail["far_depth"])
                    near_depth = float(rail["near_depth"])
                except (KeyError, TypeError, ValueError):
                    rails_valid = False
                    continue
                rails_valid &= (
                    abs(start_x - rail_cursor) <= 0.01
                    and end_x > start_x
                    and near_depth > far_depth
                )
                rail_cursor = end_x
            rails_valid &= abs(rail_cursor - world_width) <= 0.01
            record(
                rails_valid,
                "gameplay_rails_continuous",
                f"rail_count={len(rails)}; covered_to={rail_cursor:g}",
                level_id=level_id,
            )
            camera_zones = (
                geometry.get("camera_zones", ())
                if isinstance(geometry, Mapping)
                and isinstance(geometry.get("camera_zones", ()), Sequence)
                else ()
            )
            zones_valid = bool(camera_zones) and all(
                isinstance(zone, Mapping)
                and str(zone.get("name", "")).strip()
                and 0 <= float(zone.get("start_x", -1))
                < float(zone.get("end_x", -1))
                <= world_width
                for zone in camera_zones
            )
            record(
                zones_valid,
                "gameplay_camera_zones",
                f"zone_count={len(camera_zones)}",
                level_id=level_id,
            )

        content_level = content_levels.get(level_id)
        route_content = content_level.get("route", {}) if content_level is not None else {}
        record(
            isinstance(route_content, Mapping)
            and str(route_content.get("start_anchor_id", ""))
            == str(route.get("start_anchor_id", ""))
            and str(route_content.get("end_anchor_id", ""))
            == str(route.get("end_anchor_id", "")),
            "chapter_content_endpoints_match",
            (
                f"start={route_content.get('start_anchor_id') if isinstance(route_content, Mapping) else None!r}, "
                f"end={route_content.get('end_anchor_id') if isinstance(route_content, Mapping) else None!r}"
            ),
            level_id=level_id,
        )

        if level_id == "chapter_1_level_4":
            awaken = next(
                (item for item in landmarks if str(item.get("id", "")) == "awaken_church_lot"),
                {},
            )
            record(
                str(awaken.get("address", "")).strip() == "950 N 2nd St"
                and str(route.get("start_anchor_id", "")) == "awaken_church_lot"
                and str(route.get("end_anchor_id", "")) == "daves_bmx",
                "awaken_location_lock",
                (
                    f"address={awaken.get('address')!r}, start={route.get('start_anchor_id')!r}, "
                    f"end={route.get('end_anchor_id')!r}"
                ),
                level_id=level_id,
            )

        route_slice = checks[route_checks_before:]
        route_results.append(
            {
                "level_id": level_id,
                "theme": theme,
                "world_width": world_width,
                "landmark_count": len(landmarks),
                "opposite_side_landmark_count": len(opposite),
                "registered_feature_count": len(features),
                "assets": asset_results,
                "stage_chunks": stage_chunk_results,
                "passed": all(item["status"] == "pass" for item in route_slice),
            }
        )

    combined_json = json.dumps(
        {"gameplay": gameplay_data, "chapter_content": content_data},
        ensure_ascii=False,
        sort_keys=True,
    ).lower()
    record(
        "1310 broadway" not in combined_json,
        "obsolete_awaken_address_absent",
        "gameplay and chapter content do not contain 1310 Broadway",
    )
    errors = [item for item in checks if item["status"] == "fail"]
    atmosphere_path = root / "data" / "atmosphere.json"
    atmosphere_runtime_file = {
        "path": "data/atmosphere.json",
        "exists": atmosphere_path.is_file(),
        "size_bytes": (
            atmosphere_path.stat().st_size
            if atmosphere_path.is_file()
            else None
        ),
        "sha256": (
            _sha256_file(atmosphere_path)
            if atmosphere_path.is_file()
            else None
        ),
    }
    authoritative_runtime_files = {
        "atmosphere": atmosphere_runtime_file,
    }
    asset_inventory_sha256 = _asset_inventory_digest(
        route_results,
        authoritative_files=authoritative_runtime_files,
    )
    return {
        "classification": "chapter1_location_lock_source_or_package_validation",
        "project_root": str(root),
        "manifest_path": str(root / "data" / "chapter1_location_lock.json"),
        "asset_inventory_sha256": asset_inventory_sha256,
        "authoritative_runtime_files": authoritative_runtime_files,
        "checks": checks,
        "errors": errors,
        "routes": route_results,
        "passed": not errors,
    }


def _non_negative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"{label} must be a non-negative integer")
        return value
    try:
        result = int(value)
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a non-negative integer") from error
    if not math.isfinite(numeric) or result < 0 or result != numeric:
        raise ValueError(f"{label} must be a non-negative integer")
    return result


def build_pacing_report(content: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return exact authored profiles and target checks without estimating playtime."""

    if content is None:
        content = load_chapter_content(gameplay=load_gameplay())
    targets = content["pacing"]["targets"]
    profiles: dict[str, dict[str, Any]] = {}
    for name in _PROFILE_NAMES:
        profile = pace_profile(content, name)
        profiles[name] = {
            "level_minutes": {
                level_id: round(minutes, 3)
                for level_id, minutes in profile.level_minutes
            },
            "travel_dialogue_minutes": round(profile.travel_dialogue_minutes, 3),
            "total_minutes": round(profile.total_minutes, 3),
            "total_seconds": round(profile.total_minutes * 60.0, 3),
        }

    normal = profiles["normal"]
    experienced = profiles["experienced"]
    minimum = profiles["minimum"]
    normal_range = tuple(float(value) for value in targets["normal_minutes"])
    experienced_range = tuple(float(value) for value in targets["experienced_minutes"])
    travel_range = tuple(float(value) for value in targets["normal_travel_dialogue_minutes"])
    per_level_checks = {
        level_id: float(bounds[0]) <= float(normal["level_minutes"][level_id]) <= float(bounds[1])
        for level_id, bounds in targets["level_target_minutes"].items()
    }
    checks = {
        "normal_total_in_target": normal_range[0] <= float(normal["total_minutes"]) <= normal_range[1],
        "experienced_total_in_target": experienced_range[0]
        <= float(experienced["total_minutes"])
        <= experienced_range[1],
        "minimum_total_at_or_above_floor": float(minimum["total_minutes"])
        >= float(targets["minimum_minutes"]),
        "normal_travel_dialogue_in_target": travel_range[0]
        <= float(normal["travel_dialogue_minutes"])
        <= travel_range[1],
        "normal_levels_in_target": all(per_level_checks.values()),
    }
    return {
        "classification": "authored_duration_contract_not_observed_playthrough",
        "source": "data/chapter_content.json:pacing",
        "observed_playthrough_seconds": None,
        "targets": {
            "normal_minutes": list(normal_range),
            "experienced_minutes": list(experienced_range),
            "minimum_minutes": float(targets["minimum_minutes"]),
            "normal_travel_dialogue_minutes": list(travel_range),
            "level_target_minutes": {
                level_id: [float(bounds[0]), float(bounds[1])]
                for level_id, bounds in targets["level_target_minutes"].items()
            },
        },
        "profiles": profiles,
        "per_level_normal_checks": per_level_checks,
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_scene_budget_report(
    content: Mapping[str, Any] | None = None,
    *,
    effect_budget: int = DEFAULT_EFFECT_BUDGET,
    debris_budget: int = DEFAULT_DEBRIS_BUDGET,
) -> dict[str, Any]:
    """Build the fixed four-player/Couch stress-scene composition and budgets."""

    effect_budget = _non_negative_integer(effect_budget, "effect_budget")
    debris_budget = _non_negative_integer(debris_budget, "debris_budget")
    if effect_budget > MAX_EFFECT_BUDGET:
        raise ValueError(f"effect_budget cannot exceed {MAX_EFFECT_BUDGET}")
    if debris_budget > MAX_DEBRIS_BUDGET:
        raise ValueError(f"debris_budget cannot exceed {MAX_DEBRIS_BUDGET}")
    if content is None:
        content = load_chapter_content(gameplay=load_gameplay())
    scaling = content["player_count_scaling"][str(BENCHMARK_PLAYER_COUNT)]
    enemy_budget = int(scaling["max_live_enemies"])
    couch_contract = compile_couch_contract(content, BENCHMARK_PLAYER_COUNT)
    crew_kinds = tuple(
        str(kind)
        for phase in couch_contract["phases"]
        for kind in phase.get("retreat", {}).get("runtime_kinds", ())
    )
    if enemy_budget < 1 or not crew_kinds:
        raise ValueError("the four-player Couch contract must provide an enemy budget and add crew")
    enemy_kinds = ("couch",) + tuple(
        crew_kinds[index % len(crew_kinds)]
        for index in range(enemy_budget - 1)
    )
    return {
        "level_id": BENCHMARK_LEVEL_ID,
        "player_count": BENCHMARK_PLAYER_COUNT,
        "chief_count": 1,
        "active_enemy_budget": enemy_budget,
        "active_effect_budget": effect_budget,
        "active_debris_budget": debris_budget,
        "enemy_budget_source": "data/chapter_content.json:player_count_scaling.4.max_live_enemies",
        "effect_budget_source": (
            "tools/validate_chapter1.py:DEFAULT_EFFECT_BUDGET"
            if effect_budget == DEFAULT_EFFECT_BUDGET
            else "tool_argument:effect_budget"
        ),
        "debris_budget_source": (
            "tools/validate_chapter1.py:DEFAULT_DEBRIS_BUDGET"
            if debris_budget == DEFAULT_DEBRIS_BUDGET
            else "tool_argument:debris_budget"
        ),
        "enemy_kinds": list(enemy_kinds),
        "enemy_composition": dict(sorted(Counter(enemy_kinds).items())),
    }


def _scene_counts(game: FadesGame) -> dict[str, int]:
    return {
        "players": len(game.players),
        "chiefs": len(game.chiefs),
        "active_enemies": sum(enemy.alive for enemy in game.enemies),
        "active_effects": sum(effect.alive for effect in game.effects),
        "active_debris": sum(
            not projectile.spent and projectile.kind in {"debris", "rock"}
            for projectile in game.projectiles
        ),
    }


def _scene_signature(game: FadesGame) -> str:
    snapshot = {
        "players": [
            [player.slot, player.character, round(player.x, 3), round(player.y, 3)]
            for player in game.players
        ],
        "chiefs": [
            [chief.owner.slot, round(chief.x, 3), round(chief.y, 3)]
            for chief in game.chiefs
        ],
        "enemies": [
            [enemy.enemy_id, enemy.kind, round(enemy.x, 3), round(enemy.y, 3)]
            for enemy in game.enemies
        ],
        "effects": [
            [effect.kind, round(effect.x, 3), round(effect.y, 3)]
            for effect in game.effects
        ],
        "debris": [
            [projectile.kind, round(projectile.x, 3), round(projectile.y, 3)]
            for projectile in game.projectiles
            if projectile.kind in {"debris", "rock"}
        ],
    }
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _populate_crowded_scene(
    game: FadesGame,
    budget: Mapping[str, Any],
) -> pygame.Surface:
    game._select_campaign_level(str(budget["level_id"]))
    bindings = (
        {"type": "keyboard"},
        {"type": "controller", "instance_id": 101},
        {"type": "controller", "instance_id": 102},
        {"type": "controller", "instance_id": 103},
    )
    game.select_slots = [
        SelectSlot(dict(binding), character_index=index % 2, confirmed=True)
        for index, binding in enumerate(bindings)
    ]
    game._start_stage()
    camera_x = min(float(game.meta["stage_width"]) - LOGICAL_SIZE[0], 960.0)
    game.camera.pan_to(camera_x, 0.0)
    game.camera_x = camera_x
    game._render_camera_x = camera_x
    game.stage_banner_timer = 0.0
    game.route_card_timer = 0.0
    # The benchmark isolates a fully populated boss arena. Route-card and
    # environmental triggers are marked consumed so they cannot add effects
    # after the explicit stress budgets have been installed.
    content_events = game.runtime_chapter_content.get("environmental_events", ())
    game._content_event_index = len(content_events) if isinstance(content_events, list) else 0
    game.encounter_active = True
    game.encounter_index = 0
    game.spawn_queue.clear()
    game._post_clear_reinforcements.clear()
    game.active_gate = float(game.meta["stage_width"]) - 40.0
    game._encounter_enemy_durability_scale = 1.25
    game._encounter_enemy_damage_scale = 1.15

    player_positions = ((1050.0, 246.0), (1138.0, 282.0), (1230.0, 246.0), (1318.0, 282.0))
    for player, (x, y) in zip(game.players, player_positions):
        player.x = x
        player.y = y
        player.invulnerable = 3600.0
        player.set_state("idle")
    for chief in game.chiefs:
        chief.x = chief.owner.x - 30.0
        chief.y = chief.owner.y + 18.0
        chief.state = "sit"
        chief.attack_cooldown = 3600.0

    game.enemies.clear()
    game.effects.clear()
    enemy_positions = (
        (1010.0, 318.0),
        (1090.0, 300.0),
        (1170.0, 318.0),
        (1250.0, 300.0),
        (1330.0, 318.0),
        (1410.0, 300.0),
        (1490.0, 318.0),
        (1545.0, 286.0),
    )
    for index, kind in enumerate(budget["enemy_kinds"]):
        enemy = game._spawn_enemy(str(kind))
        enemy.x, enemy.y = enemy_positions[index]
        enemy._set_state("idle")
        enemy.cooldown = 3600.0

    game.effects.clear()
    for index in range(int(budget["active_effect_budget"])):
        kind = _EFFECT_KINDS[index % len(_EFFECT_KINDS)]
        game.add_effect(
            kind,
            985.0 + float((index * 47) % 570),
            238.0 + float((index * 19) % 88),
            color=(255, 116 + (index * 13) % 120, 58 + (index * 17) % 170),
            radius=10 + index % 20,
            duration=3600.0,
        )

    game.projectiles.clear()
    for index in range(int(budget["active_debris_budget"])):
        game.projectiles.append(
            Projectile(
                x=990.0 + float((index * 61) % 580),
                y=244.0 + float((index * 23) % 76),
                z=18.0 + float(index % 4) * 4.0,
                vx=0.0,
                vy=0.0,
                vz=6000.0,
                damage=0.0,
                owner_team="qa",
                kind="debris",
                ttl=3600.0,
            )
        )
    return pygame.Surface(LOGICAL_SIZE).convert()


def _percentile(values: Sequence[int], fraction: float) -> int:
    if not values:
        raise ValueError("timing samples cannot be empty")
    ordered = sorted(int(value) for value in values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def summarize_timing_ns(samples: Sequence[int]) -> dict[str, float]:
    """Summarize integer nanosecond samples with deterministic nearest-rank tails."""

    if not samples:
        raise ValueError("timing samples cannot be empty")
    numeric = tuple(int(value) for value in samples)
    if any(value < 0 for value in numeric):
        raise ValueError("timing samples cannot be negative")
    return {
        "mean_ms": round(statistics.fmean(numeric) / 1_000_000.0, 4),
        "median_ms": round(statistics.median(numeric) / 1_000_000.0, 4),
        "p95_ms": round(_percentile(numeric, 0.95) / 1_000_000.0, 4),
        "max_ms": round(max(numeric) / 1_000_000.0, 4),
    }


def _camera_sweep_positions(world_width: int, frame_count: int) -> tuple[int, ...]:
    max_camera = max(0, int(world_width) - int(LOGICAL_SIZE[0]))
    if frame_count <= 1:
        return (0,)
    return tuple(
        int(round(max_camera * index / (frame_count - 1)))
        for index in range(frame_count)
    )


def run_scenery_camera_sweep(
    *,
    frames_per_route: int = DEFAULT_SCENERY_SWEEP_FRAMES,
    warmup_frames: int = 2,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Measure deterministic forward camera travel on every Chapter 1 route."""

    frames_per_route = _non_negative_integer(frames_per_route, "frames_per_route")
    warmup_frames = _non_negative_integer(warmup_frames, "warmup_frames")
    if not 5 <= frames_per_route <= MAX_SCENERY_SWEEP_FRAMES:
        raise ValueError(
            f"frames_per_route must be between 5 and {MAX_SCENERY_SWEEP_FRAMES}"
        )
    if warmup_frames > MAX_WARMUP_FRAMES:
        raise ValueError(f"warmup_frames cannot exceed {MAX_WARMUP_FRAMES}")
    manifest_data = (
        dict(manifest)
        if manifest is not None
        else _read_json_file(PROJECT_ROOT / "data" / "chapter1_location_lock.json")
    )
    routes_value = manifest_data.get("routes", ())
    routes = tuple(
        route for route in routes_value
        if isinstance(route, Mapping)
    )
    if tuple(str(route.get("level_id", "")) for route in routes) != _LEVEL_IDS:
        raise ValueError("the scenery benchmark requires all four Chapter 1 routes in order")

    pygame_was_initialized = pygame.get_init()
    if not pygame_was_initialized:
        pygame.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode(LOGICAL_SIZE)
    video_driver = pygame.display.get_driver()
    canvas = pygame.Surface(LOGICAL_SIZE).convert()
    default_clock = clock_ns is time.perf_counter_ns
    route_reports: list[dict[str, Any]] = []
    saved_frame_cache = dict(getattr(pixel_art, "_STAGE_BACKGROUND_FRAME_CACHE", {}))
    saved_vehicle_cache = dict(getattr(pixel_art, "_AMBIENT_VEHICLE_CACHE", {}))
    try:
        for route in routes:
            level_id = str(route["level_id"])
            theme = str(route["theme"])
            world_width = int(route["world_width"])
            positions = _camera_sweep_positions(world_width, frames_per_route)
            frame_cache = getattr(pixel_art, "_STAGE_BACKGROUND_FRAME_CACHE", None)
            if frame_cache is not None:
                frame_cache.clear()
            vehicle_cache = getattr(pixel_art, "_AMBIENT_VEHICLE_CACHE", None)
            if vehicle_cache is not None:
                vehicle_cache.clear()
            pixel_art.prewarm_ambient_traffic(theme)
            for index in range(warmup_frames):
                warmup_position = positions[index % min(len(positions), 2)]
                pixel_art.draw_stage_background(
                    canvas,
                    warmup_position,
                    world_width,
                    theme=theme,
                )
                pixel_art.draw_stage_foreground(
                    canvas,
                    warmup_position,
                    world_width,
                    theme=theme,
                )

            samples: list[int] = []
            checkpoint_hashes: dict[str, str] = {}
            checkpoint_camera_x: dict[str, int] = {}
            checkpoint_indices = {
                int(round((frames_per_route - 1) * fraction)): f"{fraction:.2f}"
                for fraction in _INTEGRATION_CHECK_CAMERA_FRACTIONS
            }
            for index, camera_x in enumerate(positions):
                started = clock_ns()
                pixel_art.draw_stage_background(
                    canvas,
                    camera_x,
                    world_width,
                    theme=theme,
                )
                pixel_art.draw_stage_foreground(
                    canvas,
                    camera_x,
                    world_width,
                    theme=theme,
                )
                finished = clock_ns()
                elapsed = finished - started
                if elapsed < 0:
                    raise ValueError("benchmark clock must be monotonic")
                samples.append(elapsed)
                if index in checkpoint_indices:
                    marker = checkpoint_indices[index]
                    checkpoint_hashes[marker] = hashlib.sha256(
                        pygame.image.tobytes(canvas, "RGB", False)
                    ).hexdigest()
                    checkpoint_camera_x[marker] = int(round(camera_x))

            timing = summarize_timing_ns(samples)
            distinct_checkpoints = len(set(checkpoint_hashes.values())) == len(
                checkpoint_hashes
            )
            within_budget = float(timing["p95_ms"]) <= FIXED_STEP_BUDGET_MS
            route_reports.append(
                {
                    "level_id": level_id,
                    "theme": theme,
                    "world_width": world_width,
                    "camera_start": positions[0],
                    "camera_end": positions[-1],
                    "frames": frames_per_route,
                    "timing": timing,
                    "checkpoint_sha256": checkpoint_hashes,
                    "checkpoint_camera_x": checkpoint_camera_x,
                    "checkpoints_visually_distinct": distinct_checkpoints,
                    "p95_within_fixed_step_budget": within_budget,
                    "passed": within_budget and distinct_checkpoints,
                }
            )
        return {
            "classification": (
                "actual_headless_scenery_camera_sweep_cpu_measurement"
                if default_clock
                else "deterministic_injected_clock_scenery_measurement"
            ),
            "measurement_scope": (
                "SDL headless 640x360 logical-surface Chapter 1 background plus "
                "post-actor foreground draw across deterministic forward camera positions"
            ),
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "pygame": pygame.version.ver,
                "sdl_video_driver": video_driver,
                "logical_resolution": list(LOGICAL_SIZE),
                "timing_clock": "perf_counter_ns" if default_clock else "injected_clock",
            },
            "fixed_step_budget_ms": round(FIXED_STEP_BUDGET_MS, 4),
            "frames_per_route": frames_per_route,
            "routes": route_reports,
            "passed": all(route["passed"] for route in route_reports),
        }
    finally:
        frame_cache = getattr(pixel_art, "_STAGE_BACKGROUND_FRAME_CACHE", None)
        if frame_cache is not None:
            frame_cache.clear()
            frame_cache.update(saved_frame_cache)
        vehicle_cache = getattr(pixel_art, "_AMBIENT_VEHICLE_CACHE", None)
        if vehicle_cache is not None:
            vehicle_cache.clear()
            vehicle_cache.update(saved_vehicle_cache)
        if not pygame_was_initialized:
            pygame.quit()


def _atmosphere_state_from_game(game: FadesGame) -> Any | None:
    for field in ("atmosphere_state", "atmosphere"):
        value = getattr(game, field, None)
        if value is not None and callable(getattr(value, "snapshot", None)):
            return value
    save_data = getattr(game, "save_data", None)
    value = getattr(save_data, "atmosphere", None)
    if value is not None and callable(getattr(value, "snapshot", None)):
        return value
    return None


def _atmosphere_digest(state: Any | None) -> str:
    if state is None:
        return ""
    snapshot = state.snapshot()
    mapping = snapshot.to_mapping()
    return _stable_json_digest(mapping)


def _source_forwards_non_null_keyword(
    function: Callable[..., Any],
    *,
    callee_name: str,
    keyword_name: str,
) -> bool:
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    except (OSError, TypeError, SyntaxError):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function_name = (
            node.func.attr
            if isinstance(node.func, ast.Attribute)
            else node.func.id
            if isinstance(node.func, ast.Name)
            else ""
        )
        if function_name != callee_name:
            continue
        for keyword in node.keywords:
            if keyword.arg != keyword_name:
                continue
            return not (
                isinstance(keyword.value, ast.Constant)
                and keyword.value.value is None
            )
    return False


def _runtime_integration_probe() -> dict[str, Any]:
    """Observe atmosphere ownership, pause behavior, rendering, and route continuity."""

    manager: InputManager | None = None
    game: FadesGame | None = None
    pygame_was_initialized = pygame.get_init()
    display_was_initialized = pygame.display.get_init()
    font_was_initialized = pygame.font.get_init()
    created_display = pygame.display.get_surface() is None
    try:
        if not pygame_was_initialized:
            pygame.init()
        else:
            if not display_was_initialized:
                pygame.display.init()
            if not font_was_initialized:
                pygame.font.init()
        if created_display:
            pygame.display.set_mode(LOGICAL_SIZE)
        manager = InputManager(max_players=4, discover_controllers=False)
        game = FadesGame(manager, mute=True)
        game._select_campaign_level("chapter_1_level_1")
        game.select_slots = [
            SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True),
        ]
        game._start_stage()
        game.stage_banner_timer = 0.0
        game.route_card_timer = 0.0

        state = _atmosphere_state_from_game(game)
        before_active = _atmosphere_digest(state)
        game.pause = False
        game.update(1.0 / FIXED_HZ)
        after_active = _atmosphere_digest(state)
        advances_during_gameplay = bool(
            before_active
            and after_active
            and before_active != after_active
        )

        before_pause = _atmosphere_digest(state)
        game.pause = True
        game.update(1.0 / FIXED_HZ)
        after_pause = _atmosphere_digest(state)
        freezes_during_pause = bool(
            before_pause and before_pause == after_pause
        )
        game.pause = False

        canvas_before = pygame.Surface(LOGICAL_SIZE).convert()
        canvas_after = pygame.Surface(LOGICAL_SIZE).convert()
        game.draw(canvas_before)
        if state is not None:
            state.advance(30.0, paused=False)
        game.draw(canvas_after)
        sky_rect = pygame.Rect(192, 38, 256, 126)
        sky_before = canvas_before.subsurface(sky_rect)
        sky_after = canvas_after.subsurface(sky_rect)
        rendered_sky_changes = (
            pygame.image.tobytes(sky_before, "RGB", False)
            != pygame.image.tobytes(sky_after, "RGB", False)
        )

        before_route_change = (
            state.snapshot().to_mapping()
            if state is not None
            else {}
        )
        game._select_campaign_level("chapter_1_level_2")
        state_after_route_change = _atmosphere_state_from_game(game)
        after_route_change = (
            state_after_route_change.snapshot().to_mapping()
            if state_after_route_change is not None
            else {}
        )
        route_change_preserves_clock = bool(
            before_route_change
            and after_route_change
            and int(after_route_change.get("seed", -1))
            == int(before_route_change.get("seed", -2))
            and float(after_route_change.get("time_seconds", -1.0))
            >= float(before_route_change.get("time_seconds", 0.0))
        )

        game_source = inspect.getsource(FadesGame)
        renderer_receives_atmosphere = _source_forwards_non_null_keyword(
            getattr(pixel_art, "_draw_location_locked_background"),
            callee_name="render_route_backdrop",
            keyword_name="atmosphere",
        )
        physical_objects_wired = "physical_scene_objects" in game_source
        projection_mode = str(
            getattr(getattr(game, "projection", None), "config", None).mode
            if getattr(getattr(game, "projection", None), "config", None)
            is not None
            else ""
        )
        return {
            "initialized": True,
            "advances_during_gameplay": advances_during_gameplay,
            "freezes_during_pause": freezes_during_pause,
            "rendered_sky_changes_at_fixed_camera": rendered_sky_changes,
            "route_change_preserves_clock": route_change_preserves_clock,
            "renderer_receives_atmosphere": renderer_receives_atmosphere,
            "physical_scene_objects_wired": physical_objects_wired,
            "projection_mode": projection_mode,
            "error": None,
        }
    except Exception as error:
        return {
            "initialized": False,
            "advances_during_gameplay": False,
            "freezes_during_pause": False,
            "rendered_sky_changes_at_fixed_camera": False,
            "route_change_preserves_clock": False,
            "renderer_receives_atmosphere": False,
            "physical_scene_objects_wired": False,
            "projection_mode": "",
            "error": f"{type(error).__name__}: {error}",
        }
    finally:
        if game is not None:
            game.close()
        if manager is not None:
            manager.close()
        if not pygame_was_initialized:
            pygame.quit()
        else:
            if created_display and not display_was_initialized:
                pygame.display.quit()
            if not font_was_initialized:
                pygame.font.quit()


def run_integration_visual_matrix(
    *,
    project_root: Path | str = PROJECT_ROOT,
    manifest: Mapping[str, Any] | None = None,
    gameplay: Mapping[str, Any] | None = None,
    content: Mapping[str, Any] | None = None,
    frames_per_route: int = len(_INTEGRATION_CHECK_CAMERA_FRACTIONS),
) -> dict[str, Any]:
    """Build integration-focused visual checkpoints and route-level reference checks."""

    frames_per_route = _non_negative_integer(frames_per_route, "frames_per_route")
    if not 1 <= frames_per_route <= MAX_SCENERY_SWEEP_FRAMES:
        raise ValueError(
            f"frames_per_route must be between 1 and {MAX_SCENERY_SWEEP_FRAMES}"
        )
    root = Path(project_root).resolve()
    manifest_data = (
        dict(manifest)
        if manifest is not None
        else _read_json_file(root / "data" / "chapter1_location_lock.json")
    )
    if gameplay is None:
        gameplay_data = _read_json_file(root / "data" / "gameplay.json")
    else:
        gameplay_data = dict(gameplay)
    if content is None:
        content_data = _read_json_file(root / "data" / "chapter_content.json")
    else:
        content_data = dict(content)
    stage_chunk_data = _read_json_file(root / "data" / "stage_chunks.json")

    gameplay_routes = tuple(
        route
        for route in manifest_data.get("routes", ())
        if isinstance(route, Mapping)
    )
    if len(gameplay_routes) != len(_LEVEL_IDS):
        raise ValueError("integration matrix requires all four Chapter 1 routes in manifest")
    route_levels = {
        str(level.get("id", "")): level
        for level in _raw_campaign_levels(gameplay_data)
        if isinstance(level, Mapping)
    }
    content_levels = {
        str(level.get("runtime_level_id", "")): level
        for level in (
            content_data.get("levels", ())
            if isinstance(content_data.get("levels", ()), Sequence)
            and not isinstance(content_data.get("levels", ()), (str, bytes))
            else ()
        )
        if isinstance(level, Mapping)
    }
    gameplay_players = gameplay_data.get("players", {})
    player_profiles = {
        str(name).lower(): bool(config)
        for name, config in (
            gameplay_players.items()
            if isinstance(gameplay_players, Mapping)
            else ()
        )
        if str(name).lower() != "global"
    }
    chief_profile_present = bool(gameplay_data.get("chief", {}))
    atmosphere_error = ""
    try:
        atmosphere_data = _read_json_file(root / "data" / "atmosphere.json")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        atmosphere_data = {}
        atmosphere_error = f"{type(error).__name__}: {error}"
    route_atmosphere = atmosphere_data.get("route_profile_map", {})
    if not isinstance(route_atmosphere, Mapping):
        route_atmosphere = {}
    atmosphere_profiles = atmosphere_data.get("profiles", {})
    if not isinstance(atmosphere_profiles, Mapping):
        atmosphere_profiles = {}

    scenery_error = ""
    try:
        scenery_sweep = run_scenery_camera_sweep(
            frames_per_route=frames_per_route,
            warmup_frames=0,
            manifest=manifest_data,
        )
    except Exception as error:
        scenery_error = f"{type(error).__name__}: {error}"
        scenery_sweep = {
            "classification": "failed_scenery_camera_sweep",
            "routes": [],
            "passed": False,
            "error": scenery_error,
        }
    sweeps = {
        str(route["level_id"]): route
        for route in scenery_sweep.get("routes", ())
        if isinstance(route, Mapping)
    }

    checks: list[dict[str, Any]] = []
    route_reports: list[dict[str, Any]] = []
    runtime_probe = _runtime_integration_probe()
    projection_profiles = _projection_profiles(gameplay_data)
    active_projection_profile_id = _active_projection_profile_id(gameplay_data)
    checks.extend(
        [
            {
                "id": "integration_atmosphere_data_readable",
                "status": "pass" if not atmosphere_error else "fail",
                "required": True,
                "detail": atmosphere_error or "data/atmosphere.json loaded",
            },
            {
                "id": "integration_scenery_runtime_renderable",
                "status": "pass" if not scenery_error else "fail",
                "required": True,
                "detail": scenery_error or "all route scenery frames rendered",
            },
            {
                "id": "integration_projection_profile_active",
                "status": (
                    "pass"
                    if active_projection_profile_id == "chapter1_oblique_v2"
                    and isinstance(
                        projection_profiles.get("chapter1_oblique_v2"),
                        Mapping,
                    )
                    else "fail"
                ),
                "required": True,
                "detail": (
                    f"active={active_projection_profile_id!r}; "
                    f"profiles={sorted(str(key) for key in projection_profiles)!r}"
                ),
            },
        ]
    )
    for probe_field, check_id in (
        ("initialized", "integration_runtime_initializes"),
        (
            "advances_during_gameplay",
            "integration_runtime_atmosphere_advances",
        ),
        (
            "freezes_during_pause",
            "integration_runtime_atmosphere_pause_freeze",
        ),
        (
            "rendered_sky_changes_at_fixed_camera",
            "integration_runtime_sky_changes_at_fixed_camera",
        ),
        (
            "route_change_preserves_clock",
            "integration_runtime_atmosphere_route_continuity",
        ),
        (
            "renderer_receives_atmosphere",
            "integration_runtime_renderer_receives_atmosphere",
        ),
        (
            "physical_scene_objects_wired",
            "integration_runtime_physical_scene_objects",
        ),
    ):
        checks.append(
            {
                "id": check_id,
                "status": "pass" if runtime_probe.get(probe_field) else "fail",
                "required": True,
                "detail": (
                    runtime_probe.get("error")
                    or f"{probe_field}={runtime_probe.get(probe_field)!r}"
                ),
            }
        )
    ordered_profiles = [
        str(route_atmosphere.get(str(route.get("level_id", "")), ""))
        for route in gameplay_routes
    ]
    transition_pairs = tuple(
        (ordered_profiles[index], ordered_profiles[index + 1])
        for index in range(len(ordered_profiles) - 1)
        if ordered_profiles[index] and ordered_profiles[index + 1]
    )
    checks.append(
        {
            "id": "integration_atmosphere_route_profile_count",
            "status": "pass"
            if len(ordered_profiles) == len(_LEVEL_IDS)
            else "fail",
            "required": True,
            "detail": f"profiles={ordered_profiles!r}",
        }
    )
    checks.append(
        {
            "id": "integration_atmosphere_route_profile_sequence",
            "status": "pass"
            if all(profile and str(profile) in atmosphere_profiles for profile in ordered_profiles)
            else "fail",
            "required": True,
            "detail": f"profile_sequence={ordered_profiles!r}",
        }
    )
    checks.append(
        {
            "id": "integration_atmosphere_route_profile_transitions",
            "status": "pass" if transition_pairs else "warn",
            "required": False,
            "detail": f"transitions={transition_pairs!r}",
        }
    )

    for route in gameplay_routes:
        level_id = str(route.get("level_id", ""))
        route_check: list[dict[str, Any]] = []
        world_width = int(route.get("world_width", 0))
        gameplay_level = route_levels.get(level_id, {})
        content_level = content_levels.get(level_id, {})
        panel_spec_count = 0
        stage_world: StageWorld | None = None
        try:
            stage_world = StageWorld.from_route(route, stage_chunk_data)
            panel_spec_count = len(stage_world.chunks)
        except (StageWorldError, TypeError, ValueError):
            panel_spec_count = 0

        def record(condition: bool, check_id: str, detail: str, *, required: bool = True) -> None:
            entry = {
                "id": check_id,
                "status": "pass" if condition else ("warn" if required is False else "fail"),
                "required": required,
                "detail": detail,
            }
            route_check.append(entry)

        references = _format_reference_tokens(route, gameplay_level)
        references.extend(sorted(player_profiles))
        if chief_profile_present:
            references.append("chief")
        references = sorted(set(references))
        reference_tokens = set(references)
        required_markers = tuple(_INTEGRATION_REQUIRED_ROUTE_MARKERS.get(level_id, ()))
        missing_markers = [marker for marker in required_markers if marker not in references]
        record(
            not missing_markers,
            "integration_required_reference_markers",
            f"required={list(required_markers)!r}; missing={missing_markers!r}",
        )
        record(
            _contains_token(reference_tokens, _INTEGRATION_REFERENCE_KEYWORDS["environment_pole"]),
            "integration_reference_pole_like_object",
            f"tokens={sorted(reference_tokens)!r}",
            required=False,
        )
        record(
            _contains_token(reference_tokens, _INTEGRATION_REFERENCE_KEYWORDS["environment_curb"]),
            "integration_reference_curb_like_object",
            f"tokens={sorted(reference_tokens)!r}",
            required=False,
        )
        record(
            _contains_token(reference_tokens, _INTEGRATION_REFERENCE_KEYWORDS["environment_door"]),
            "integration_reference_door_like_object",
            f"tokens={sorted(reference_tokens)!r}",
            required=False,
        )
        record(
            _contains_token(reference_tokens, _INTEGRATION_REFERENCE_KEYWORDS["environment_sedan"]),
            "integration_reference_sedan_like_object",
            f"tokens={sorted(reference_tokens)!r}",
            required=False,
        )
        record(
            _contains_token(reference_tokens, _INTEGRATION_REFERENCE_KEYWORDS["actor_dave"]),
            "integration_reference_actor_dave",
            f"tokens={sorted(reference_tokens)!r}",
        )
        record(
            _contains_token(reference_tokens, _INTEGRATION_REFERENCE_KEYWORDS["actor_shelly"]),
            "integration_reference_actor_shelly",
            f"tokens={sorted(reference_tokens)!r}",
        )
        record(
            _contains_token(reference_tokens, _INTEGRATION_REFERENCE_KEYWORDS["actor_chief"]),
            "integration_reference_actor_chief",
            f"tokens={sorted(reference_tokens)!r}",
        )
        record(
            _contains_token(reference_tokens, _INTEGRATION_REFERENCE_KEYWORDS["actor_enemy"]),
            "integration_reference_actor_enemy",
            f"tokens={sorted(reference_tokens)!r}",
            required=False,
        )

        record(
            world_width >= int(LOGICAL_SIZE[0]),
            "integration_world_width_present",
            f"world_width={world_width!r}",
        )

        record(
            str(route.get("start_anchor_id", "")) and str(route.get("end_anchor_id", "")),
            "integration_route_anchor_contract",
            (
                f"start={route.get('start_anchor_id')!r}; "
                f"end={route.get('end_anchor_id')!r}"
            ),
        )
        record(
            bool(str(route.get("theme", "")).strip()),
            "integration_theme_present",
            f"theme={route.get('theme')!r}",
        )

        geometry = (
            gameplay_level.get("stage_geometry", {})
            if isinstance(gameplay_level, Mapping)
            else {}
        )
        camera_zones = geometry.get("camera_zones", ())
        record(
            isinstance(camera_zones, (tuple, list)) and bool(camera_zones),
            "integration_route_camera_zone_progress",
            f"zones={len(camera_zones) if isinstance(camera_zones, Sequence) else 0!r}",
        )
        gameplay_encounters = gameplay_level.get("encounters", ()) if isinstance(gameplay_level, Mapping) else ()
        record(
            isinstance(geometry.get("rails", ()), Sequence)
            and bool(geometry.get("rails", ())),
            "integration_route_rails_defined",
            f"rail_count={len(geometry.get('rails', ())) if isinstance(geometry.get('rails', ()), Sequence) else 0!r}",
        )
        record(
            isinstance(geometry.get("obstacles", ()), Sequence),
            "integration_route_obstacles_defined",
            f"obstacle_count={len(geometry.get('obstacles', ())) if isinstance(geometry.get('obstacles', ()), Sequence) else 0!r}",
        )

        player_refs = set(player_profiles.keys())
        record(
            "black_dave" in player_refs,
            "integration_player_dave_present",
            f"player_profiles={sorted(player_refs)!r}",
        )
        record(
            "shelly" in player_refs,
            "integration_player_shelly_present",
            f"player_profiles={sorted(player_refs)!r}",
        )
        record(
            chief_profile_present,
            "integration_chief_profile_present",
            "chief profile exists in chapter content",
        )

        encounter_base_kinds: list[str] = []
        if isinstance(gameplay_level, Mapping):
            for encounter in gameplay_level.get("encounters", ()):
                if not isinstance(encounter, Mapping):
                    continue
                for kind in _as_sequence(encounter.get("base", ())):
                    encounter_base_kinds.append(str(kind).lower())
        record(
            bool(encounter_base_kinds),
            "integration_encounter_definitions_present",
            f"encounter_base_kinds={sorted(set(encounter_base_kinds))!r}",
        )
        record(
            bool(content_level),
            "integration_level_completion_contract_present",
            f"content_level={level_id!r}",
        )
        if isinstance(content_level, Mapping):
            ending = content_level.get("ending", {})
            record(
                isinstance(ending, Mapping) and bool(str(ending.get("id", "")).strip()),
                "integration_completion_panel_defined",
                f"ending={ending!r}",
            )
        route_level = content_level.get("route", {})
        record(
            bool(route_level),
            "integration_route_summary_present",
            f"route={route_level!r}",
        )
        if not route_level:
            record(
                False,
                "integration_route_contract_match_with_gameplay",
                "content-level route block missing",
            )
        else:
            record(
                len(str(route_level.get("start_anchor_id", ""))) > 0
                and len(str(route_level.get("end_anchor_id", ""))) > 0,
                "integration_route_contract_match_with_gameplay",
                f"content_route={route_level!r}",
            )
            inter_route = route_level.get("stops", ())
            record(
                isinstance(inter_route, Sequence),
                "integration_route_stops_present",
                f"stops={list(inter_route)!r}",
                required=False,
            )

        route_objects_value = route.get("physical_scene_objects", ())
        route_objects = [
            item
            for item in _as_sequence(route_objects_value)
            if isinstance(item, Mapping)
        ]
        route_object_kinds = {str(item.get("kind", "")).strip().lower() for item in route_objects}
        route_object_anchors = [str(item.get("anchor", "")).strip().lower() for item in route_objects]
        landmark_ids = {str(item.get("id", "")).strip().lower() for item in _as_sequence(route.get("landmarks", ())) if isinstance(item, Mapping)}
        record(
            bool(route_objects),
            "integration_physical_scene_objects_present",
            f"physical_object_count={len(route_objects)}",
        )
        record(
            all(
                all(field in item for field in _PHYSICAL_SCENE_OBJECT_FIELDS)
                for item in route_objects
            ),
            "integration_physical_scene_object_asset_contract",
            (
                "objects="
                f"{[(item.get('id'), item.get('asset')) for item in route_objects]}"
            ),
        )
        missing_physical_assets = [
            str(item.get("asset", ""))
            for item in route_objects
            if not (
                str(item.get("asset", "")).startswith("assets/")
                and (root / str(item.get("asset", ""))).is_file()
            )
        ]
        record(
            not missing_physical_assets,
            "integration_physical_scene_object_assets_exist",
            f"missing={missing_physical_assets!r}",
        )
        record(
            any(item in route_object_kinds for item in ("sedan", "car")),
            "integration_physical_sedan_presence",
            f"kinds={sorted(route_object_kinds)!r}",
        )
        route_object_depths = {
            int(round(float(item.get("depth"))))
            for item in route_objects
            if isinstance(item.get("depth"), (int, float))
        }
        route_rail_depths = {
            int(round(float(value)))
            for rail in _as_sequence(geometry.get("rails", ()))
            if isinstance(rail, Mapping)
            for value in (rail.get("near_depth"), rail.get("far_depth"))
            if isinstance(value, (int, float))
        }
        depth_samples = sorted(route_object_depths | route_rail_depths)
        record(
            len(depth_samples) >= 3,
            "integration_far_middle_near_depth_presence",
            f"depth_samples={depth_samples!r}",
        )
        record(
            len(route_object_anchors) == len(route_objects),
            "integration_physical_objects_anchored",
            f"anchors={route_object_anchors!r}",
        )
        record(
            all(anchor in landmark_ids for anchor in route_object_anchors),
            "integration_physical_object_anchor_to_landmark",
            f"anchor_count={len(route_object_anchors)}",
        )
        route_projection_profile = str(
            route.get("projection_profile_id", "")
        ).strip()
        record(
            route_projection_profile == active_projection_profile_id
            and route_projection_profile in projection_profiles,
            "integration_route_projection_profile",
            (
                f"route={route_projection_profile!r}; "
                f"active={active_projection_profile_id!r}"
            ),
        )
        missing_layer_fields = [
            field
            for field in _LAYERED_LOCATION_ASSET_FIELDS
            if not str(route.get(field, "")).strip()
            or route.get(f"{field}_size")
            != [world_width, int(LOGICAL_SIZE[1])]
        ]
        record(
            not missing_layer_fields,
            "integration_route_layer_schema",
            f"missing_or_invalid={missing_layer_fields!r}",
        )
        record(
            panel_spec_count >= 2,
            "integration_panel_seams",
            f"panel_count={panel_spec_count!r}",
            required=False,
        )
        record(
            stage_world is not None
            and all(
                chunk.landmark_ids
                and chunk.seam_anchor
                and chunk.collision_ids is not None
                and chunk.spawn_markers is not None
                for chunk in stage_world.chunks
            ),
            "integration_chunk_ownership",
            (
                f"chunks={panel_spec_count!r}; "
                "each chunk owns landmarks, collisions, spawns, and seam metadata"
            ),
        )
        record(
            any(item in reference_tokens for item in ("curb", "sidewalk", "median")),
            "integration_ground_curb_reference_presence",
            f"tokens={sorted(reference_tokens)!r}",
            required=False,
        )

        if level_id in _INTEGRATION_REQUIRED_ROUTE_MARKERS:
            route_checkpoint_markers = []
            for item in route_object_anchors:
                if item:
                    route_checkpoint_markers.append(item)
            route_checkpoints = tuple(
                marker
                for marker in _INTEGRATION_REQUIRED_ROUTE_MARKERS[level_id]
                if marker in route_object_kinds or marker in reference_tokens
            )
            record(
                len(route_checkpoint_markers) >= 2 or len(route_checkpoints) > 0,
                "integration_route_checkpoint_markers_detected",
                f"anchors={route_checkpoint_markers!r}; token_markers={sorted(route_checkpoints)!r}",
            )

        encounter_camera_lock_count = sum(
            1 for encounter in _as_sequence(gameplay_encounters) if isinstance(encounter, Mapping) and str(encounter.get("name", "")).strip()
        )
        record(
            encounter_camera_lock_count >= 2,
            "integration_encounter_lock_markers",
            f"encounter_like_count={encounter_camera_lock_count}",
        )
        encounter_camera_x_count = sum(
            1 for encounter in _as_sequence(gameplay_encounters)
            if isinstance(encounter, Mapping) and isinstance(encounter.get("camera_x"), (int, float))
        )
        record(
            encounter_camera_x_count > 0,
            "integration_encounter_camera_lock_positions",
            f"camera_x_count={encounter_camera_x_count!r}",
            required=False,
        )
        is_finale = (
            bool(gameplay_level.get("boss_transition"))
            if isinstance(gameplay_level, Mapping)
            else False
        )
        is_finale = is_finale or level_id == "chapter_1_level_4"

        route_encounter_locks = (
            level_id in ("chapter_1_level_1", "chapter_1_level_2", "chapter_1_level_3")
            or encounter_camera_x_count > 0
        )
        record(
            route_encounter_locks or is_finale,
            "integration_encounter_camera_lock_contract",
            f"encounter_camera_x_count={encounter_camera_x_count!r}",
        )

        route_atmosphere_id = str(route_atmosphere.get(level_id, ""))
        atmosphere_profile = (
            atmosphere_profiles.get(route_atmosphere_id, {})
            if isinstance(route_atmosphere_id, str) else {}
        )
        record(
            bool(route_atmosphere_id)
            and str(route.get("sky_profile_id", "")) == route_atmosphere_id,
            "integration_route_atmosphere_profile_map",
            (
                f"route={level_id!r}; profile={route_atmosphere_id!r}; "
                f"manifest={route.get('sky_profile_id')!r}"
            ),
        )
        record(
            isinstance(atmosphere_profile, Mapping)
            and bool(atmosphere_profile),
            "integration_atmosphere_profile_defined",
            f"profile_keys={list(atmosphere_profile)!r}",
        )
        if isinstance(atmosphere_profile, Mapping):
            cloud_speeds = atmosphere_profile.get("cloud_speeds", ())
            record(
                isinstance(cloud_speeds, Sequence)
                and not isinstance(cloud_speeds, (str, bytes))
                and len(cloud_speeds) >= 3,
                "integration_atmosphere_cloud_layers",
                f"cloud_speeds={list(cloud_speeds)!r}",
            )
        route_sky_hashes: set[str] = set()
        atmosphere_runtime_error = ""
        if isinstance(atmosphere_profile, Mapping) and atmosphere_profile:
            try:
                atmosphere_state = AtmosphereState.new(
                    seed=0xFAD35,
                    profile_id=route_atmosphere_id,
                )
                for _ in range(30):
                    atmosphere_state.advance(1.0)
                    route_sky_hashes.add(
                        _stable_json_digest(
                            atmosphere_state.snapshot().to_mapping()
                        )
                    )
            except (KeyError, TypeError, ValueError) as error:
                atmosphere_runtime_error = f"{type(error).__name__}: {error}"
        record(
            not atmosphere_runtime_error and len(route_sky_hashes) >= 2,
            "integration_stationary_camera_sky_30s",
            (
                f"stationary_sky_snapshots={len(route_sky_hashes)}; "
                f"error={atmosphere_runtime_error!r}"
            ),
        )
        record(
            not route_encounter_locks or len(route_sky_hashes) >= 2,
            "integration_clouds_continue_during_encounter_locks",
            f"encounter_camera_locks={route_encounter_locks}; snapshots={len(route_sky_hashes)}",
        )
        if level_id == "chapter_1_level_2":
            architecture_asset = str(
                route.get("architecture_asset", "")
            ).strip()
            underpass_architecture_exists = bool(
                architecture_asset
                and (root / architecture_asset).is_file()
            )
            record(
                "i8_underpass" in landmark_ids
                and underpass_architecture_exists
                and len(route_sky_hashes) >= 2,
                "integration_underpass_masks_sky_without_restart",
                (
                    f"landmark={'i8_underpass' in landmark_ids}; "
                    f"architecture={architecture_asset!r}; "
                    f"sky_snapshots={len(route_sky_hashes)}"
                ),
            )

        record(
            bool(gameplay_level)
            and (bool(gameplay_level.get("travel_to_next")) or is_finale or level_id in ("chapter_1_level_1", "chapter_1_level_2", "chapter_1_level_3")),
            "integration_travel_or_epilogue_state",
            f"travel_to_next={gameplay_level.get('travel_to_next') if isinstance(gameplay_level, Mapping) else None!r}; "
            f"boss_transition={gameplay_level.get('boss_transition') if isinstance(gameplay_level, Mapping) else None!r}",
        )
        record(
            world_width > 0 and world_width >= int(LOGICAL_SIZE[0]),
            "integration_visible_canvas_width",
            f"world_width={world_width!r}",
        )

        route_sweep = sweeps.get(level_id, {})
        if not isinstance(route_sweep, Mapping):
            record(
                False,
                "integration_scenery_sweep_present",
                f"no scenery sweep entry for {level_id!r}",
            )
            cameras_ok = False
            checkpoint_hashes = {}
            checkpoint_camera_x = {}
        else:
            checkpoint_hashes = route_sweep.get("checkpoint_sha256", {})
            checkpoint_camera_x = route_sweep.get("checkpoint_camera_x", {})
            cameras_ok = (
                len(checkpoint_hashes) == len(_INTEGRATION_CHECK_CAMERA_FRACTIONS)
                and all(
                    f"{fraction:.2f}" in checkpoint_hashes
                    for fraction in _INTEGRATION_CHECK_CAMERA_FRACTIONS
                )
            )
            record(
                cameras_ok,
                "integration_camera_checkpoints_covered",
                f"checkpoint_x={checkpoint_camera_x!r}",
            )
            if isinstance(checkpoint_hashes, Mapping) and checkpoint_hashes:
                record(
                    len(set(checkpoint_hashes.values())) == len(checkpoint_hashes),
                    "integration_camera_checkpoint_uniqueness",
                    f"hash_count={len(checkpoint_hashes)}",
                )
            route_sweep_markers = [
                fraction
                for fraction in _INTEGRATION_CHECK_CAMERA_FRACTIONS
                if f"{fraction:.2f}" in checkpoint_hashes
            ]
            record(
                len(route_sweep_markers) == len(_INTEGRATION_CHECK_CAMERA_FRACTIONS),
                "integration_scenery_fractions_recorded",
                f"fractions={route_sweep_markers!r}",
            )

        route_checks = tuple(route_check)
        route_reports.append(
            {
                "level_id": level_id,
                "camera_x": checkpoint_camera_x,
                "camera_checkpoint_count": len(checkpoint_hashes),
                "camera_checkpoint_hashes": checkpoint_hashes,
                "reference_tokens": references,
                "reference_token_count": len(reference_tokens),
                "checks": route_checks,
                "passed": all(
                    item["status"] == "pass"
                    for item in route_checks
                    if item.get("required", True)
                ),
                "required_checks_passed": all(
                    item["status"] == "pass"
                    for item in route_checks
                    if item.get("required", True)
                ),
            }
        )
        checks.extend(route_checks)

    chapter_physical_kinds = {
        str(item.get("kind", "")).strip().lower()
        for route in gameplay_routes
        for item in _as_sequence(route.get("physical_scene_objects", ()))
        if isinstance(item, Mapping)
    }
    checks.append(
        {
            "id": "integration_chapter_physical_sedan_presence",
            "status": (
                "pass"
                if chapter_physical_kinds.intersection({"sedan", "car"})
                else "fail"
            ),
            "required": True,
            "detail": f"kinds={sorted(chapter_physical_kinds)!r}",
        }
    )

    return {
        "classification": "integration_visual_matrix",
        "project_root": str(root),
        "routes": route_reports,
        "scenery_camera_sweep": scenery_sweep,
        "runtime_probe": runtime_probe,
        "camera_fractions": [round(value, 2) for value in _INTEGRATION_CHECK_CAMERA_FRACTIONS],
        "checks": checks,
        "passed": all(item["status"] == "pass" for item in checks if item.get("required", True)),
    }


def run_crowded_benchmark(
    *,
    frames: int = DEFAULT_BENCHMARK_FRAMES,
    warmup_frames: int = DEFAULT_WARMUP_FRAMES,
    effect_budget: int = DEFAULT_EFFECT_BUDGET,
    debris_budget: int = DEFAULT_DEBRIS_BUDGET,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> dict[str, Any]:
    """Measure a fixed 4-player, Couch, eight-enemy headless game workload."""

    frames = _non_negative_integer(frames, "frames")
    warmup_frames = _non_negative_integer(warmup_frames, "warmup_frames")
    if not 1 <= frames <= MAX_BENCHMARK_FRAMES:
        raise ValueError(f"frames must be between 1 and {MAX_BENCHMARK_FRAMES}")
    if warmup_frames > MAX_WARMUP_FRAMES:
        raise ValueError(f"warmup_frames cannot exceed {MAX_WARMUP_FRAMES}")
    content = load_chapter_content(gameplay=load_gameplay())
    budget = build_scene_budget_report(
        content,
        effect_budget=effect_budget,
        debris_budget=debris_budget,
    )
    pygame_was_initialized = pygame.get_init()
    if not pygame_was_initialized:
        pygame.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode(LOGICAL_SIZE)
    video_driver = pygame.display.get_driver()
    manager = InputManager(max_players=BENCHMARK_PLAYER_COUNT, discover_controllers=False)
    game = FadesGame(manager, mute=True)
    try:
        canvas = _populate_crowded_scene(game, budget)
        initial_counts = _scene_counts(game)
        signature = _scene_signature(game)
        expected_counts = {
            "players": BENCHMARK_PLAYER_COUNT,
            "chiefs": int(budget["chief_count"]),
            "active_enemies": int(budget["active_enemy_budget"]),
            "active_effects": int(budget["active_effect_budget"]),
            "active_debris": int(budget["active_debris_budget"]),
        }
        observed_minimums = dict(initial_counts)
        observed_peaks = dict(initial_counts)

        def observe_counts() -> None:
            counts = _scene_counts(game)
            for name, value in counts.items():
                observed_minimums[name] = min(observed_minimums[name], value)
                observed_peaks[name] = max(observed_peaks[name], value)

        dt = 1.0 / FIXED_HZ
        for _ in range(warmup_frames):
            game.update(dt)
            game.draw(canvas)
            observe_counts()

        update_samples: list[int] = []
        draw_samples: list[int] = []
        total_samples: list[int] = []
        for _ in range(frames):
            started = clock_ns()
            game.update(dt)
            after_update = clock_ns()
            game.draw(canvas)
            after_draw = clock_ns()
            update_ns = after_update - started
            draw_ns = after_draw - after_update
            if update_ns < 0 or draw_ns < 0:
                raise ValueError("benchmark clock must be monotonic")
            update_samples.append(update_ns)
            draw_samples.append(draw_ns)
            total_samples.append(update_ns + draw_ns)
            observe_counts()

        update_timing = summarize_timing_ns(update_samples)
        draw_timing = summarize_timing_ns(draw_samples)
        total_timing = summarize_timing_ns(total_samples)
        mean_total = float(total_timing["mean_ms"])
        frame_budget_ms = 1000.0 / FIXED_HZ
        budgets_preserved = (
            initial_counts == expected_counts
            and observed_minimums == expected_counts
            and observed_peaks == expected_counts
        )
        default_clock = clock_ns is time.perf_counter_ns
        return {
            "classification": (
                "actual_headless_cpu_measurement_not_displayed_fps"
                if default_clock
                else "deterministic_injected_clock_test_measurement"
            ),
            "measurement_scope": (
                "SDL headless dummy-video FadesGame.update plus 640x360 logical-surface draw; "
                "not an observed playthrough duration, monitor presentation time, or GPU benchmark"
            ),
            "workload": {
                "level_id": BENCHMARK_LEVEL_ID,
                "fixed_hz": FIXED_HZ,
                "warmup_frames": warmup_frames,
                "measured_frames": frames,
                "scene_signature_sha256": signature,
                "budgets": {
                    "active_enemies": int(budget["active_enemy_budget"]),
                    "active_effects": int(budget["active_effect_budget"]),
                    "active_debris": int(budget["active_debris_budget"]),
                },
                "budget_sources": {
                    "active_enemies": budget["enemy_budget_source"],
                    "active_effects": budget["effect_budget_source"],
                    "active_debris": budget["debris_budget_source"],
                },
                "enemy_composition": budget["enemy_composition"],
            },
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "pygame": pygame.version.ver,
                "sdl_video_driver": video_driver,
                "logical_resolution": list(LOGICAL_SIZE),
                "timing_clock": "perf_counter_ns" if default_clock else "injected_clock",
            },
            "counts": {
                "initial": initial_counts,
                "minimum": observed_minimums,
                "peak": observed_peaks,
                "expected": expected_counts,
                "budgets_preserved": budgets_preserved,
            },
            "timing": {
                "update": update_timing,
                "draw": draw_timing,
                "update_plus_draw": total_timing,
                "fixed_step_budget_ms": round(frame_budget_ms, 4),
                "headless_cpu_p95_within_fixed_step_budget": float(total_timing["p95_ms"])
                <= frame_budget_ms,
                "headless_cpu_equivalent_throughput_fps": (
                    round(1000.0 / mean_total, 2) if mean_total > 0.0 else None
                ),
            },
            "passed": budgets_preserved and float(total_timing["p95_ms"]) <= frame_budget_ms,
        }
    finally:
        game.close()
        manager.close()
        if not pygame_was_initialized:
            pygame.quit()


def build_report(
    *,
    include_benchmark: bool = True,
    include_location_lock: bool = True,
    include_scenery_sweep: bool = True,
    include_integration_matrix: bool = True,
    integration_frames: int = len(_INTEGRATION_CHECK_CAMERA_FRACTIONS),
    frames: int = DEFAULT_BENCHMARK_FRAMES,
    warmup_frames: int = DEFAULT_WARMUP_FRAMES,
    effect_budget: int = DEFAULT_EFFECT_BUDGET,
    debris_budget: int = DEFAULT_DEBRIS_BUDGET,
    scenery_frames: int = DEFAULT_SCENERY_SWEEP_FRAMES,
    project_root: Path | str = PROJECT_ROOT,
) -> dict[str, Any]:
    pacing = build_pacing_report()
    benchmark = (
        run_crowded_benchmark(
            frames=frames,
            warmup_frames=warmup_frames,
            effect_budget=effect_budget,
            debris_budget=debris_budget,
        )
        if include_benchmark
        else None
    )
    location_lock = (
        build_location_lock_report(project_root)
        if include_location_lock
        else None
    )
    scenery_sweep = (
        run_scenery_camera_sweep(frames_per_route=scenery_frames)
        if include_scenery_sweep
        else None
    )
    integration_matrix = (
        run_integration_visual_matrix(
            project_root=project_root,
            frames_per_route=min(max(1, int(integration_frames)), MAX_SCENERY_SWEEP_FRAMES),
        )
        if include_integration_matrix
        else None
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "chapter_id": "chapter_1",
        "pacing": pacing,
        "benchmark": benchmark,
        "location_lock": location_lock,
        "scenery_camera_sweep": scenery_sweep,
        "integration_visual_matrix": integration_matrix,
        "passed": bool(
            pacing["passed"]
            and (benchmark is None or benchmark["passed"])
            and (location_lock is None or location_lock["passed"])
            and (scenery_sweep is None or scenery_sweep["passed"])
            and (integration_matrix is None or integration_matrix["passed"])
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=DEFAULT_BENCHMARK_FRAMES)
    parser.add_argument("--warmup-frames", type=int, default=DEFAULT_WARMUP_FRAMES)
    parser.add_argument("--effects", type=int, default=DEFAULT_EFFECT_BUDGET)
    parser.add_argument("--debris", type=int, default=DEFAULT_DEBRIS_BUDGET)
    parser.add_argument(
        "--scenery-frames",
        type=int,
        default=DEFAULT_SCENERY_SWEEP_FRAMES,
    )
    parser.add_argument(
        "--integration-frames",
        type=int,
        default=len(_INTEGRATION_CHECK_CAMERA_FRACTIONS),
    )
    parser.add_argument("--pacing-only", action="store_true")
    parser.add_argument(
        "--location-only",
        action="store_true",
        help="Validate manifest/data/assets at --project-root without running game benchmarks.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Source, assembled package, or installed package root to validate.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--allow-performance-miss",
        action="store_true",
        help="Exit successfully when contracts/budgets pass even if headless p95 exceeds 16.67 ms.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.location_only:
        report = build_location_lock_report(args.project_root)
    else:
        report = build_report(
            include_benchmark=not args.pacing_only,
            include_location_lock=not args.pacing_only,
            include_scenery_sweep=not args.pacing_only,
            include_integration_matrix=not args.pacing_only,
            integration_frames=args.integration_frames,
            frames=args.frames,
            warmup_frames=args.warmup_frames,
            effect_budget=args.effects,
            debris_budget=args.debris,
            scenery_frames=args.scenery_frames,
            project_root=args.project_root,
        )
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    sys.stdout.write(payload)
    if args.location_only:
        return 0 if report["passed"] else 1
    pacing_ok = bool(report["pacing"]["passed"])
    budget_ok = bool(
        report["benchmark"] is None
        or report["benchmark"]["counts"]["budgets_preserved"]
    )
    location_ok = bool(
        report["location_lock"] is None
        or report["location_lock"]["passed"]
    )
    scenery_visual_ok = bool(
        report["scenery_camera_sweep"] is None
        or all(
            route["checkpoints_visually_distinct"]
            for route in report["scenery_camera_sweep"]["routes"]
        )
    )
    integration_visual_ok = bool(
        report["integration_visual_matrix"] is None
        or report["integration_visual_matrix"]["passed"]
    )
    if (
        not pacing_ok
        or not budget_ok
        or not location_ok
        or not scenery_visual_ok
        or not integration_visual_ok
    ):
        return 1
    if not report["passed"] and not args.allow_performance_miss:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
