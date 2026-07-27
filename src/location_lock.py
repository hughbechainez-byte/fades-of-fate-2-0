"""Validated Chapter 1 geography shared by data, rendering, and QA.

The location manifest is the only owner of route widths, route endpoints,
landmark world positions, and location-locked art paths.  Runtime gameplay
keeps combat geometry and refers to these records by stable ids.
"""

from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


LOGICAL_HEIGHT = 360
LEVEL_IDS = (
    "chapter_1_level_1",
    "chapter_1_level_2",
    "chapter_1_level_3",
    "chapter_1_level_4",
)
REQUIRED_LANDMARK_ORDERS = {
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
MANDATORY_REFERENCE_URLS = (
    "https://www.openstreetmap.org/#map=16/32.8026/-116.9358",
    "https://www.sprouts.com/stores/ca/",
    "https://www.google.com/maps/search/?api=1&query=Sprouts+Farmers+Market+152+N+2nd+St+El+Cajon+CA",
    "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.7969,-116.93575&heading=90&pitch=0&fov=90",
    "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.79869,-116.93575&heading=270&pitch=0&fov=90",
    "https://www.google.com/maps/search/?api=1&query=El+Cilantro+1285+E+Madison+Ave+El+Cajon+CA",
    "https://www.google.com/maps/search/?api=1&query=7-Eleven+500+N+2nd+St+El+Cajon+CA",
    "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.80115,-116.93570&heading=270&pitch=0&fov=90",
    "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.80275,-116.93582&heading=0&pitch=0&fov=90",
    "https://soapyjoescarwash.com/location/el-cajon-n-2nd-st/",
    "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.80554,-116.93573&heading=270&pitch=0&fov=90",
    "https://www.google.com/maps/search/?api=1&query=Revive+Pathway+1240+Broadway+El+Cajon+CA",
    "https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=32.80844,-116.93570&heading=270&pitch=0&fov=90",
    "https://awakenchurch.com/service-locations/east-campus/",
)
_CONFIDENCE = {"high", "medium", "low"}
_SOURCE_FIELDS = (
    "source_date",
    "imagery_date",
    "access_date",
    "view_direction",
    "durable_massing",
    "parking_setback",
    "driveway_placement",
)


class LocationLockError(ValueError):
    """Raised when Chapter 1 geography or its referenced art drifts."""


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LocationLockError(f"{label} must be an object")
    return value


def _require_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise LocationLockError(f"{label} must be non-empty text")
    return text


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LocationLockError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise LocationLockError(f"{label} must be a finite number")
    return number


def _validate_iso_date(value: Any, label: str) -> str:
    text = _require_text(value, label)
    parts = text.split("-")
    if (
        len(parts) != 3
        or tuple(len(part) for part in parts) != (4, 2, 2)
        or not all(part.isdigit() for part in parts)
    ):
        raise LocationLockError(f"{label} must be an ISO YYYY-MM-DD date")
    year, month, day = (int(part) for part in parts)
    if year < 2000 or not 1 <= month <= 12 or not 1 <= day <= 31:
        raise LocationLockError(f"{label} must be a plausible ISO date")
    return text


def _validate_imagery_date(value: Any, label: str) -> str:
    text = _require_text(value, label)
    if text == "not_exposed_by_public_viewer":
        return text
    parts = text.split("-")
    if (
        len(parts) == 2
        and all(part.isdigit() for part in parts)
        and len(parts[0]) == 4
        and len(parts[1]) == 2
    ):
        year, month = (int(part) for part in parts)
        if year >= 2000 and 1 <= month <= 12:
            return text
        raise LocationLockError(f"{label} must be a plausible ISO month")
    return _validate_iso_date(text, label)


def _haversine_meters(first: tuple[float, float], second: tuple[float, float]) -> float:
    latitude_1, longitude_1 = (math.radians(value) for value in first)
    latitude_2, longitude_2 = (math.radians(value) for value in second)
    delta_latitude = latitude_2 - latitude_1
    delta_longitude = longitude_2 - longitude_1
    half_chord = (
        math.sin(delta_latitude / 2.0) ** 2
        + math.cos(latitude_1)
        * math.cos(latitude_2)
        * math.sin(delta_longitude / 2.0) ** 2
    )
    return 6_371_000.0 * 2.0 * math.asin(math.sqrt(half_chord))


def coordinate_normalized_distances(
    landmarks: Sequence[Mapping[str, Any]],
) -> tuple[float, ...]:
    """Derive cumulative normalized route positions from latitude/longitude."""

    points = [
        (
            _finite(landmark.get("latitude"), f"landmarks[{index}].latitude"),
            _finite(landmark.get("longitude"), f"landmarks[{index}].longitude"),
        )
        for index, landmark in enumerate(landmarks)
    ]
    cumulative = [0.0]
    for first, second in zip(points, points[1:]):
        cumulative.append(cumulative[-1] + _haversine_meters(first, second))
    total = cumulative[-1]
    if total <= 1.0:
        raise LocationLockError("route coordinates must describe at least one meter of travel")
    return tuple(distance / total for distance in cumulative)


def _validate_source_metadata(record: Mapping[str, Any], label: str) -> None:
    _require_text(record.get("real_name"), f"{label}.real_name")
    _require_text(record.get("display_name"), f"{label}.display_name")
    _require_text(record.get("address"), f"{label}.address")
    for field in _SOURCE_FIELDS:
        if field in {"source_date", "access_date"}:
            _validate_iso_date(record.get(field), f"{label}.{field}")
        elif field == "imagery_date":
            _validate_imagery_date(record.get(field), f"{label}.{field}")
        else:
            _require_text(record.get(field), f"{label}.{field}")
    urls = record.get("source_urls")
    if not isinstance(urls, list) or not urls:
        raise LocationLockError(f"{label}.source_urls must contain at least one URL")
    for url_index, url in enumerate(urls):
        parsed = urlparse(_require_text(url, f"{label}.source_urls[{url_index}]"))
        if parsed.scheme != "https" or not parsed.netloc:
            raise LocationLockError(f"{label}.source_urls[{url_index}] must be an HTTPS URL")
    neighbors = record.get("neighboring_anchors")
    if not isinstance(neighbors, list) or not neighbors or not all(str(item).strip() for item in neighbors):
        raise LocationLockError(f"{label}.neighboring_anchors must be a non-empty list")
    if _require_text(record.get("confidence"), f"{label}.confidence").lower() not in _CONFIDENCE:
        raise LocationLockError(f"{label}.confidence must be high, medium, or low")


def _validate_asset(
    project_root: Path,
    relative_asset: str,
    expected_size: tuple[int, int],
    label: str,
    *,
    require_opaque: bool,
    require_alpha: bool,
) -> None:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - dependency is packaged with the game
        raise LocationLockError("Pillow is required to validate location-locked art") from exc

    asset_path = project_root / relative_asset
    if not asset_path.is_file():
        raise LocationLockError(f"{label} is missing: {relative_asset}")
    try:
        with Image.open(asset_path) as image:
            image.load()
            if image.size != expected_size:
                raise LocationLockError(
                    f"{label} must be {expected_size[0]}x{expected_size[1]}, got "
                    f"{image.size[0]}x{image.size[1]}"
                )
            alpha = image.getchannel("A") if "A" in image.getbands() else None
            if require_alpha and alpha is None:
                raise LocationLockError(f"{label} must retain a transparent alpha channel")
            if require_opaque and alpha is not None and alpha.getextrema()[0] != 255:
                raise LocationLockError(f"{label} must be fully opaque")
    except LocationLockError:
        raise
    except Exception as exc:
        raise LocationLockError(f"{label} is unreadable: {relative_asset}") from exc


def validate_location_lock(
    data: dict[str, Any],
    *,
    project_root: str | Path | None = None,
    validate_assets: bool = True,
) -> dict[str, Any]:
    """Validate route geography, source provenance, spacing, and art files."""

    if not isinstance(data, dict):
        raise LocationLockError("location manifest root must be an object")
    if int(data.get("schema_version", 0)) != 2:
        raise LocationLockError("chapter1_location_lock.schema_version must be 2")
    access_date = _validate_iso_date(data.get("research_access_date"), "research_access_date")
    mandatory_references = data.get("mandatory_references")
    if not isinstance(mandatory_references, list):
        raise LocationLockError("mandatory_references must be a list")
    supplied_reference_urls = tuple(
        str(reference.get("url", ""))
        for reference in mandatory_references
        if isinstance(reference, Mapping)
    )
    if supplied_reference_urls != MANDATORY_REFERENCE_URLS:
        raise LocationLockError(
            "mandatory_references must preserve the exact locked live-reference list"
        )
    reference_ids: set[str] = set()
    for reference_index, reference_value in enumerate(mandatory_references):
        label = f"mandatory_references[{reference_index}]"
        reference = _require_mapping(reference_value, label)
        reference_id = _require_text(reference.get("id"), f"{label}.id")
        if reference_id in reference_ids:
            raise LocationLockError(f"mandatory reference id must be unique: {reference_id!r}")
        reference_ids.add(reference_id)
        _require_text(reference.get("address"), f"{label}.address")
        _require_text(reference.get("view_direction"), f"{label}.view_direction")
        _validate_imagery_date(reference.get("imagery_date"), f"{label}.imagery_date")
        if _validate_iso_date(reference.get("access_date"), f"{label}.access_date") != access_date:
            raise LocationLockError(f"{label}.access_date must match research_access_date")
    routes = data.get("routes")
    if not isinstance(routes, list) or len(routes) != len(LEVEL_IDS):
        raise LocationLockError("location manifest must contain exactly four Chapter 1 routes")
    if tuple(str(route.get("level_id", "")) for route in routes if isinstance(route, Mapping)) != LEVEL_IDS:
        raise LocationLockError("location manifest routes must follow Chapter 1 level order")

    root = Path(project_root).resolve() if project_root is not None else Path(__file__).resolve().parents[1]
    global_ids: set[str] = set(reference_ids)
    themes: set[str] = set()
    for route_index, route_value in enumerate(routes):
        label = f"routes[{route_index}]"
        route = _require_mapping(route_value, label)
        level_id = _require_text(route.get("level_id"), f"{label}.level_id")
        theme = _require_text(route.get("theme"), f"{label}.theme")
        _validate_imagery_date(route.get("imagery_date"), f"{label}.imagery_date")
        if _validate_iso_date(route.get("access_date"), f"{label}.access_date") != access_date:
            raise LocationLockError(f"{label}.access_date must match research_access_date")
        if theme in themes:
            raise LocationLockError(f"route theme must be unique: {theme!r}")
        themes.add(theme)
        if route.get("travel_direction") != "northbound":
            raise LocationLockError(f"{label}.travel_direction must be northbound")
        if route.get("screen_travel") != "left_to_right":
            raise LocationLockError(f"{label}.screen_travel must be left_to_right")
        if route.get("playable_side") != "west_even":
            raise LocationLockError(f"{label}.playable_side must be west_even")
        world_width = int(_finite(route.get("world_width"), f"{label}.world_width"))
        if world_width <= 640:
            raise LocationLockError(f"{label}.world_width must exceed the logical viewport")
        if _finite(route.get("main_world_rate"), f"{label}.main_world_rate") != 1.0:
            raise LocationLockError(f"{label}.main_world_rate must be exactly one-to-one")
        far_rate = _finite(route.get("far_parallax"), f"{label}.far_parallax")
        near_rate = _finite(route.get("near_parallax"), f"{label}.near_parallax")
        if not 0.0 <= far_rate < 1.0:
            raise LocationLockError(f"{label}.far_parallax must be bounded below one-to-one")
        if not 1.0 < near_rate <= 1.15:
            raise LocationLockError(f"{label}.near_parallax must be sparse and bounded to at most 1.15")
        if not 0 <= _finite(route.get("far_max_offset"), f"{label}.far_max_offset") <= 128:
            raise LocationLockError(f"{label}.far_max_offset must be between 0 and 128")
        if not 0 <= _finite(route.get("near_max_offset"), f"{label}.near_max_offset") <= 96:
            raise LocationLockError(f"{label}.near_max_offset must be between 0 and 96")

        landmarks_value = route.get("landmarks")
        if not isinstance(landmarks_value, list):
            raise LocationLockError(f"{label}.landmarks must be a list")
        landmarks = tuple(_require_mapping(item, f"{label}.landmarks[{index}]") for index, item in enumerate(landmarks_value))
        ids = tuple(_require_text(item.get("id"), f"{label}.landmarks[{index}].id") for index, item in enumerate(landmarks))
        if ids != REQUIRED_LANDMARK_ORDERS[level_id]:
            raise LocationLockError(f"{label}.landmarks must match the locked geographic order")
        if route.get("start_anchor_id") != ids[0] or route.get("end_anchor_id") != ids[-1]:
            raise LocationLockError(f"{label} start/end anchors must be the first/last landmarks")

        coordinate_positions = coordinate_normalized_distances(landmarks)
        world_positions: list[float] = []
        previous_world_x = -1.0
        for landmark_index, (landmark, derived_position) in enumerate(zip(landmarks, coordinate_positions)):
            landmark_label = f"{label}.landmarks[{landmark_index}]"
            landmark_id = ids[landmark_index]
            if landmark_id in global_ids:
                raise LocationLockError(f"manifest id must be globally unique: {landmark_id!r}")
            global_ids.add(landmark_id)
            _validate_source_metadata(landmark, landmark_label)
            if landmark.get("access_date") != access_date:
                raise LocationLockError(f"{landmark_label}.access_date must match research_access_date")
            if landmark.get("street_side") != "west":
                raise LocationLockError(f"{landmark_label}.street_side must be west")
            _require_text(landmark.get("setback"), f"{landmark_label}.setback")
            supplied_position = _finite(
                landmark.get("normalized_route_distance"),
                f"{landmark_label}.normalized_route_distance",
            )
            if abs(supplied_position - derived_position) > 0.002:
                raise LocationLockError(
                    f"{landmark_label}.normalized_route_distance must be coordinate-derived "
                    f"({derived_position:.6f})"
                )
            world_x = _finite(landmark.get("world_x"), f"{landmark_label}.world_x")
            if not 0 <= world_x <= world_width or world_x <= previous_world_x:
                raise LocationLockError(f"{landmark_label}.world_x must be ordered inside route bounds")
            previous_world_x = world_x
            world_positions.append(world_x)

        world_span = world_positions[-1] - world_positions[0]
        for index in range(1, len(landmarks)):
            real_interval = coordinate_positions[index] - coordinate_positions[index - 1]
            world_interval = (world_positions[index] - world_positions[index - 1]) / world_span
            deviation = abs(world_interval - real_interval) / real_interval
            if deviation > 0.15 and not str(landmarks[index].get("compression_reason", "")).strip():
                raise LocationLockError(
                    f"{label}.landmarks[{index}] changes real spacing by {deviation:.1%} "
                    "and requires compression_reason"
                )

        opposite = route.get("opposite_side_landmarks")
        if not isinstance(opposite, list):
            raise LocationLockError(f"{label}.opposite_side_landmarks must be a list")
        previous_opposite_x = -1.0
        for opposite_index, opposite_value in enumerate(opposite):
            opposite_label = f"{label}.opposite_side_landmarks[{opposite_index}]"
            landmark = _require_mapping(opposite_value, opposite_label)
            landmark_id = _require_text(landmark.get("id"), f"{opposite_label}.id")
            if landmark_id in global_ids:
                raise LocationLockError(f"manifest id must be globally unique: {landmark_id!r}")
            global_ids.add(landmark_id)
            _validate_source_metadata(landmark, opposite_label)
            if landmark.get("access_date") != access_date:
                raise LocationLockError(f"{opposite_label}.access_date must match research_access_date")
            if landmark.get("street_side") != "east":
                raise LocationLockError(f"{opposite_label}.street_side must be east")
            world_x = _finite(landmark.get("world_x"), f"{opposite_label}.world_x")
            if not 0 <= world_x <= world_width or world_x <= previous_opposite_x:
                raise LocationLockError(f"{opposite_label}.world_x must be ordered inside route bounds")
            previous_opposite_x = world_x

        features = route.get("registered_features")
        if not isinstance(features, list) or not features:
            raise LocationLockError(f"{label}.registered_features must be a non-empty list")
        for feature_index, feature_value in enumerate(features):
            feature_label = f"{label}.registered_features[{feature_index}]"
            feature = _require_mapping(feature_value, feature_label)
            feature_id = _require_text(feature.get("id"), f"{feature_label}.id")
            if feature_id in global_ids:
                raise LocationLockError(f"manifest id must be globally unique: {feature_id!r}")
            global_ids.add(feature_id)
            _require_text(feature.get("kind"), f"{feature_label}.kind")
            world_x = _finite(feature.get("world_x"), f"{feature_label}.world_x")
            if not 0 <= world_x <= world_width:
                raise LocationLockError(f"{feature_label}.world_x must be inside route bounds")

        asset_specs = (
            ("main_panorama_asset", "main_panorama_size", True, False),
            ("far_asset", "far_asset_size", False, True),
            ("near_asset", "near_asset_size", False, True),
        )
        for asset_key, size_key, require_opaque, require_alpha in asset_specs:
            relative_asset = _require_text(route.get(asset_key), f"{label}.{asset_key}")
            if "chapter1_location_locked" not in Path(relative_asset).parts:
                raise LocationLockError(f"{label}.{asset_key} must use location-locked Chapter 1 art")
            size = route.get(size_key)
            if not isinstance(size, list) or len(size) != 2:
                raise LocationLockError(f"{label}.{size_key} must declare [width, height]")
            expected_size = (int(size[0]), int(size[1]))
            if expected_size != (world_width, LOGICAL_HEIGHT):
                raise LocationLockError(
                    f"{label}.{size_key} must equal [{world_width}, {LOGICAL_HEIGHT}]"
                )
            if validate_assets:
                _validate_asset(
                    root,
                    relative_asset,
                    expected_size,
                    f"{label}.{asset_key}",
                    require_opaque=require_opaque,
                    require_alpha=require_alpha,
                )

    travel_panels = data.get("travel_panels")
    if not isinstance(travel_panels, list) or len(travel_panels) != len(LEVEL_IDS) - 1:
        raise LocationLockError("travel_panels must describe all three Chapter 1 handoffs")
    for index, panel_value in enumerate(travel_panels):
        label = f"travel_panels[{index}]"
        panel = _require_mapping(panel_value, label)
        panel_id = _require_text(panel.get("id"), f"{label}.id")
        if panel_id in global_ids:
            raise LocationLockError(f"manifest id must be globally unique: {panel_id!r}")
        global_ids.add(panel_id)
        if panel.get("from_level_id") != LEVEL_IDS[index] or panel.get("to_level_id") != LEVEL_IDS[index + 1]:
            raise LocationLockError(f"{label} breaks Chapter 1 route order")
        if panel.get("presentation") not in {"route_card", "moving_panel"}:
            raise LocationLockError(f"{label}.presentation must be route_card or moving_panel")
        _require_text(panel.get("heading"), f"{label}.heading")
        waypoints = panel.get("waypoints")
        if not isinstance(waypoints, list) or len(waypoints) < 2:
            raise LocationLockError(f"{label}.waypoints must contain an ordered travel sequence")
        for waypoint_index, waypoint_value in enumerate(waypoints):
            waypoint_label = f"{label}.waypoints[{waypoint_index}]"
            waypoint = _require_mapping(waypoint_value, waypoint_label)
            waypoint_id = _require_text(waypoint.get("id"), f"{waypoint_label}.id")
            if waypoint_id in global_ids:
                raise LocationLockError(f"manifest id must be globally unique: {waypoint_id!r}")
            global_ids.add(waypoint_id)
            _require_text(waypoint.get("display_name"), f"{waypoint_label}.display_name")
            _require_text(waypoint.get("address"), f"{waypoint_label}.address")
    return data


def _default_manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "chapter1_location_lock.json"


@lru_cache(maxsize=8)
def _load_location_lock_cached(
    path_text: str,
    root_text: str,
    validate_assets: bool,
) -> dict[str, Any]:
    path = Path(path_text)
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except Exception as exc:
        raise LocationLockError(f"unable to load location manifest: {path}") from exc
    return validate_location_lock(
        data,
        project_root=Path(root_text),
        validate_assets=validate_assets,
    )


def load_location_lock(
    path: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
    validate_assets: bool = True,
) -> dict[str, Any]:
    """Load one cached, validated manifest for runtime and QA consumers."""

    manifest_path = Path(path or _default_manifest_path()).resolve()
    root = Path(project_root).resolve() if project_root is not None else manifest_path.parent.parent
    return _load_location_lock_cached(str(manifest_path), str(root), bool(validate_assets))


def location_routes(manifest: Mapping[str, Any] | None = None) -> tuple[Mapping[str, Any], ...]:
    source = manifest if manifest is not None else load_location_lock()
    routes = source.get("routes", ())
    return tuple(route for route in routes if isinstance(route, Mapping))


def route_for_level(
    level_id: str,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    target = str(level_id).strip()
    for route in location_routes(manifest):
        if str(route.get("level_id", "")) == target:
            return route
    raise LocationLockError(f"no location-locked route exists for level {target or '<empty>'}")


def route_for_theme(
    theme: str,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    target = str(theme).strip()
    for route in location_routes(manifest):
        if str(route.get("theme", "")) == target:
            return route
    raise LocationLockError(f"no location-locked route exists for theme {target or '<empty>'}")


def landmark_for_id(route: Mapping[str, Any], landmark_id: str) -> Mapping[str, Any]:
    target = str(landmark_id).strip()
    for field in ("landmarks", "opposite_side_landmarks"):
        for landmark in route.get(field, ()):
            if isinstance(landmark, Mapping) and str(landmark.get("id", "")) == target:
                return landmark
    raise LocationLockError(
        f"route {route.get('level_id', '<unknown>')} has no landmark {target or '<empty>'}"
    )


def registered_feature_for_id(route: Mapping[str, Any], feature_id: str) -> Mapping[str, Any]:
    target = str(feature_id).strip()
    for feature in route.get("registered_features", ()):
        if isinstance(feature, Mapping) and str(feature.get("id", "")) == target:
            return feature
    raise LocationLockError(
        f"route {route.get('level_id', '<unknown>')} has no registered feature "
        f"{target or '<empty>'}"
    )


def travel_panel_between(
    from_level_id: str,
    to_level_id: str,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    source = manifest if manifest is not None else load_location_lock()
    for panel in source.get("travel_panels", ()):
        if (
            isinstance(panel, Mapping)
            and str(panel.get("from_level_id", "")) == str(from_level_id)
            and str(panel.get("to_level_id", "")) == str(to_level_id)
        ):
            return panel
    raise LocationLockError(
        f"no travel panel exists from {from_level_id!r} to {to_level_id!r}"
    )


def hydrate_gameplay_locations(
    gameplay: dict[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Materialize immutable manifest facts into the runtime gameplay snapshot."""

    for chapter in gameplay.get("campaign", {}).get("chapters", ()):
        for level in chapter.get("levels", ()):
            if not isinstance(level, dict) or str(level.get("id", "")) not in LEVEL_IDS:
                continue
            route = route_for_level(str(level["id"]), manifest)
            indexed = {str(item["id"]): item for item in route["landmarks"]}
            level["background_theme"] = str(route["theme"])
            level["stage_width"] = int(route["world_width"])
            level["start"] = dict(indexed[str(route["start_anchor_id"])])
            level["end"] = dict(indexed[str(route["end_anchor_id"])])
            level["landmarks"] = [
                {
                    "id": str(landmark["id"]),
                    "x": int(landmark["world_x"]),
                    "layer": (
                        "intersection"
                        if "intersection" in str(landmark["setback"])
                        else "infrastructure"
                        if str(landmark["id"]) in {"freeway_approach", "i8_underpass"}
                        else "story_prop"
                        if str(landmark["id"]) == "daves_bmx"
                        else "play_side"
                    ),
                    "display_name": str(landmark["display_name"]),
                }
                for landmark in route["landmarks"]
            ]
    return gameplay


def validate_gameplay_locations(
    gameplay: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    """Reject duplicated or drifting Chapter 1 facts in gameplay data."""

    levels = [
        level
        for chapter in gameplay.get("campaign", {}).get("chapters", ())
        for level in chapter.get("levels", ())
        if isinstance(level, Mapping) and str(level.get("id", "")) in LEVEL_IDS
    ]
    if tuple(str(level.get("id", "")) for level in levels) != LEVEL_IDS:
        raise LocationLockError("gameplay must contain the four location-locked levels in order")
    for level in levels:
        level_id = str(level["id"])
        route = route_for_level(level_id, manifest)
        if (
            "background_theme" in level
            and str(level.get("background_theme", "")) != str(route["theme"])
        ):
            raise LocationLockError(f"gameplay {level_id} theme disagrees with location manifest")
        if (
            "stage_width" in level
            and int(float(level.get("stage_width", 0))) != int(route["world_width"])
        ):
            raise LocationLockError(f"gameplay {level_id} width disagrees with location manifest")
        expected_ids = tuple(str(item["id"]) for item in route["landmarks"])
        supplied_ids = tuple(str(item) for item in level.get("landmark_ids", ()))
        if supplied_ids != expected_ids:
            raise LocationLockError(f"gameplay {level_id}.landmark_ids disagrees with location manifest")
        start_record = level.get("start", {})
        end_record = level.get("end", {})
        if str(start_record.get("id", "")) != str(route["start_anchor_id"]):
            raise LocationLockError(f"gameplay {level_id} start id disagrees with location manifest")
        if str(end_record.get("id", "")) != str(route["end_anchor_id"]):
            raise LocationLockError(f"gameplay {level_id} end id disagrees with location manifest")
        for endpoint_name, runtime_endpoint, endpoint_id in (
            ("start", start_record, str(route["start_anchor_id"])),
            ("end", end_record, str(route["end_anchor_id"])),
        ):
            manifest_endpoint = landmark_for_id(route, endpoint_id)
            for field in ("real_name", "display_name", "address"):
                if field in runtime_endpoint and runtime_endpoint[field] != manifest_endpoint[field]:
                    raise LocationLockError(
                        f"gameplay {level_id} {endpoint_name} {field} drifted"
                    )

        hydrated = level.get("landmarks")
        if hydrated is not None:
            if not isinstance(hydrated, list) or tuple(str(item.get("id", "")) for item in hydrated) != expected_ids:
                raise LocationLockError(f"gameplay {level_id} hydrated landmarks drifted")
            for runtime_landmark, manifest_landmark in zip(hydrated, route["landmarks"]):
                if int(float(runtime_landmark.get("x", -1))) != int(manifest_landmark["world_x"]):
                    raise LocationLockError(
                        f"gameplay {level_id} landmark {runtime_landmark.get('id')} x drifted"
                    )
                if str(runtime_landmark.get("display_name", "")) != str(manifest_landmark["display_name"]):
                    raise LocationLockError(
                        f"gameplay {level_id} landmark {runtime_landmark.get('id')} name drifted"
                    )

        obstacles = level.get("stage_geometry", {}).get("obstacles", ())
        if not isinstance(obstacles, list):
            raise LocationLockError(f"gameplay {level_id} obstacles must be a list")
        for obstacle_index, obstacle in enumerate(obstacles):
            feature_id = _require_text(
                obstacle.get("location_feature_id"),
                f"gameplay {level_id}.obstacles[{obstacle_index}].location_feature_id",
            )
            feature = registered_feature_for_id(route, feature_id)
            if abs(float(obstacle.get("x", -1000)) - float(feature["world_x"])) > 8.0:
                raise LocationLockError(
                    f"gameplay {level_id} obstacle {obstacle.get('id')} is more than 8px "
                    f"from manifest feature {feature_id}"
                )


def validate_chapter_content_locations(
    content: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    gameplay: Mapping[str, Any] | None = None,
) -> None:
    """Cross-check narrative endpoints and travel handoffs against geography."""

    levels = content.get("levels", ())
    if not isinstance(levels, Sequence) or len(levels) != len(LEVEL_IDS):
        raise LocationLockError("chapter content must contain four location-locked levels")
    for level, level_id in zip(levels, LEVEL_IDS):
        if not isinstance(level, Mapping) or str(level.get("runtime_level_id", "")) != level_id:
            raise LocationLockError("chapter content level order disagrees with location manifest")
        route = route_for_level(level_id, manifest)
        narrative_route = _require_mapping(level.get("route"), f"chapter content {level_id}.route")
        if narrative_route.get("start_anchor_id") != route["start_anchor_id"]:
            raise LocationLockError(f"chapter content {level_id} start anchor drifted")
        if narrative_route.get("end_anchor_id") != route["end_anchor_id"]:
            raise LocationLockError(f"chapter content {level_id} end anchor drifted")
        start = landmark_for_id(route, str(route["start_anchor_id"]))
        end = landmark_for_id(route, str(route["end_anchor_id"]))
        if str(narrative_route.get("start", "")) != str(start["display_name"]):
            raise LocationLockError(f"chapter content {level_id} start name drifted")
        if str(narrative_route.get("end", "")) != str(end["display_name"]):
            raise LocationLockError(f"chapter content {level_id} end name drifted")
        stops = narrative_route.get("stops", ())
        if not isinstance(stops, list) or stops[0] != start["display_name"] or stops[-1] != end["display_name"]:
            raise LocationLockError(f"chapter content {level_id} route endpoints drifted")

    content_travel = content.get("inter_level_travel", ())
    manifest_travel = manifest.get("travel_panels", ())
    if not isinstance(content_travel, list) or len(content_travel) != len(manifest_travel):
        raise LocationLockError("chapter content travel handoffs disagree with location manifest")
    for index, (content_panel, manifest_panel) in enumerate(zip(content_travel, manifest_travel)):
        for key in ("from_level_id", "to_level_id", "heading"):
            if content_panel.get(key) != manifest_panel.get(key):
                raise LocationLockError(f"chapter content travel handoff {index} {key} drifted")

    if gameplay is not None:
        validate_gameplay_locations(gameplay, manifest)
    finale = route_for_level("chapter_1_level_4", manifest)
    bmx = landmark_for_id(finale, "daves_bmx")
    refuge = content.get("couch_boss_contract", {}).get("bike_refuge", {})
    if int(float(refuge.get("x", -1))) != int(bmx["world_x"]):
        raise LocationLockError("Couch bike refuge must agree with the manifest BMX anchor")
