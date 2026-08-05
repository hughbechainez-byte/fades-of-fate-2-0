from __future__ import annotations

import json
import hashlib
import math
import os
import sys
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from .location_lock import (
    LocationLockError,
    hydrate_gameplay_locations,
    load_location_lock,
    validate_gameplay_locations,
)


GAME_NAME = "The Fades of Fate"
LOGICAL_SIZE = (640, 360)
CONTENT_ROOT_ENV = "FADES_OF_FATE_CONTENT_ROOT"
CONTENT_MANIFEST_PATH = "data/content-manifest.json"


def is_android_runtime() -> bool:
    """Return whether the process is running inside python-for-android."""

    return bool(
        os.environ.get("ANDROID_ARGUMENT")
        or os.environ.get("ANDROID_PRIVATE")
        or os.environ.get("ANDROID_ROOT")
        or sys.platform.startswith("android")
    )


def _is_writable_directory(path: Path) -> bool:
    """Create and probe a directory without allowing storage errors to escape."""

    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".fades-write-test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def android_private_root() -> Path | None:
    """Return a writable python-for-android private directory when available."""

    if not is_android_runtime():
        return None
    candidates: list[Path] = []
    for name in ("ANDROID_PRIVATE", "ANDROID_ARGUMENT", "HOME"):
        value = os.environ.get(name, "").strip()
        if value:
            candidates.append(Path(value).expanduser())
    try:
        candidates.append(Path.home())
    except RuntimeError:
        pass
    seen: set[str] = set()
    for candidate in candidates:
        key = os.path.normcase(os.path.abspath(candidate))
        if key in seen:
            continue
        seen.add(key)
        if _is_writable_directory(candidate):
            return candidate.resolve()
    return None


class ConfigError(ValueError):
    """Raised when editable gameplay data violates the engine contract."""


def content_root() -> Path:
    """Return the writable game-content root used for synchronized updates."""
    candidates: list[Path] = []
    override = os.environ.get(CONTENT_ROOT_ENV)
    if override:
        candidates.append(Path(override).expanduser())

    private_root = android_private_root()
    if private_root is not None:
        candidates.append(private_root / "the-fades-of-fate" / "content")

    if os.name == "nt":
        local_data_root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local_data_root:
            candidates.append(
                Path(local_data_root) / "The Fades of Fate" / "content"
            )
    else:
        local_data_root = os.environ.get("XDG_DATA_HOME")
        if local_data_root:
            candidates.append(Path(local_data_root) / "the-fades-of-fate" / "content")
        else:
            candidates.append(
                Path.home() / ".local" / "share" / "the-fades-of-fate" / "content"
            )

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate.resolve()
        except OSError:
            continue

    return executable_root().resolve()


def executable_root() -> Path:
    """Directory users can edit when running a source or packaged build."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bundled_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", executable_root()))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131_072), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=8)
def _validate_content_override(
    root_text: str,
    manifest_mtime_ns: int,
    manifest_size: int,
) -> Path:
    """Validate one complete updater tree before it can become active.

    The old per-file search order could combine stale updater files with a new
    executable.  A root is now all-or-nothing and every manifest file is
    size/hash checked once per manifest identity.
    """

    del manifest_mtime_ns, manifest_size  # Values deliberately key the cache.
    root = Path(root_text).resolve()
    manifest_path = root / CONTENT_MANIFEST_PATH
    try:
        with manifest_path.open("r", encoding="utf-8-sig") as handle:
            manifest = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"content override manifest is unreadable: {manifest_path}") from exc
    records = manifest.get("files") if isinstance(manifest, Mapping) else None
    if not isinstance(records, list) or not records:
        raise ConfigError(f"content override manifest has no complete file inventory: {manifest_path}")
    for index, value in enumerate(records):
        if not isinstance(value, Mapping):
            raise ConfigError(f"content override files[{index}] must be an object")
        relative = str(value.get("path", "")).replace("\\", "/").strip()
        if not relative or relative.startswith("/") or ".." in Path(relative).parts:
            raise ConfigError(f"content override files[{index}] has an unsafe path")
        candidate = (root / relative).resolve()
        if root not in candidate.parents:
            raise ConfigError(f"content override files[{index}] escapes its root")
        if not candidate.is_file():
            raise ConfigError(f"content override is incomplete; missing {relative}")
        expected_size = int(value.get("size", -1))
        expected_hash = str(value.get("sha256", "")).strip().lower()
        if candidate.stat().st_size != expected_size:
            raise ConfigError(f"content override size mismatch: {relative}")
        if len(expected_hash) != 64 or _sha256_file(candidate) != expected_hash:
            raise ConfigError(f"content override hash mismatch: {relative}")
    return root


def active_resource_root() -> Path:
    """Return the one complete resource tree selected for this launch."""

    override = os.environ.get(CONTENT_ROOT_ENV, "").strip()
    if override:
        root = Path(override).expanduser().resolve()
        manifest = root / CONTENT_MANIFEST_PATH
        try:
            stat = manifest.stat()
        except OSError as exc:
            raise ConfigError(f"content override is missing its manifest: {manifest}") from exc
        return _validate_content_override(str(root), stat.st_mtime_ns, stat.st_size)

    packaged = executable_root().resolve()
    if (packaged / "data" / "gameplay.json").is_file() and (packaged / "assets").is_dir():
        return packaged
    bundled = bundled_root().resolve()
    if (bundled / "data" / "gameplay.json").is_file() and (bundled / "assets").is_dir():
        return bundled
    raise ConfigError("no complete packaged resource root is available")


def clear_resource_root_cache() -> None:
    """Discard validated override identities after an updater activation."""

    _validate_content_override.cache_clear()


def resource_path(relative: str | os.PathLike[str]) -> Path:
    """Resolve a resource inside the single validated root for this launch."""

    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ConfigError(f"resource path must stay relative to the active root: {relative}")
    root = active_resource_root()
    candidate = (root / relative_path).resolve()
    if root not in candidate.parents:
        raise ConfigError(f"resource path escapes the active root: {relative}")
    if not candidate.exists():
        raise FileNotFoundError(f"active resource is missing: {candidate}")
    return candidate


def load_json(relative: str) -> dict[str, Any]:
    path = resource_path(relative)
    # utf-8-sig also accepts ordinary UTF-8 while tolerating editable JSON
    # saved with a Windows/PowerShell byte-order mark.
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_gameplay() -> dict[str, Any]:
    data = load_json("data/gameplay.json")
    return validate_gameplay(data)


def _location_manifest_for_gameplay(data: Mapping[str, Any] | None = None) -> dict[str, Any]:
    relative = str(
        (data or {}).get("campaign", {}).get(
            "location_manifest",
            "data/chapter1_location_lock.json",
        )
    ).strip()
    if relative != "data/chapter1_location_lock.json":
        raise ConfigError(
            "campaign.location_manifest must use data/chapter1_location_lock.json"
        )
    path = resource_path(relative)
    return load_location_lock(
        path,
        project_root=path.parent.parent,
        validate_assets=True,
    )


def campaign_levels(data: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Flatten the authored campaign in stable chapter/level order."""

    levels: list[dict[str, Any]] = []
    for chapter in data.get("campaign", {}).get("chapters", ()):
        levels.extend(level for level in chapter.get("levels", ()) if isinstance(level, dict))
    return tuple(levels)


def active_campaign_level(data: dict[str, Any]) -> dict[str, Any]:
    """Return the level descriptor selected by campaign.active_level_id."""

    active_id = str(data.get("campaign", {}).get("active_level_id", "")).strip()
    for level in campaign_levels(data):
        if str(level.get("id", "")) == active_id:
            return level
    raise ConfigError(f"campaign.active_level_id does not name an authored level: {active_id or '<empty>'}")


def activate_campaign_level(data: dict[str, Any], level_id: str) -> dict[str, Any]:
    """Make an authored campaign level the live runtime stage.

    The editable file retains a Level 1-compatible top-level runtime snapshot
    for direct launch.  A continuing campaign run switches that snapshot in
    memory, keeping the level record itself as the single source for its
    encounters, geometry, camera width, theme, and Couch handoff.
    """

    target_id = str(level_id).strip()
    level = next(
        (candidate for candidate in campaign_levels(data) if str(candidate.get("id", "")) == target_id),
        None,
    )
    if level is None:
        raise ConfigError(f"campaign level does not exist: {target_id or '<empty>'}")
    if str(level.get("status", "")).strip().lower() != "playable":
        raise ConfigError(f"campaign level is not playable: {target_id}")

    data["campaign"]["active_level_id"] = target_id
    meta = data["meta"]
    meta.update(
        {
            "stage": f"Second Street - Level {int(level['number'])}",
            "level_id": target_id,
            "level_title": str(level["title"]),
            "background_theme": str(level["background_theme"]),
            "stage_width": float(level["stage_width"]),
        }
    )
    data["stage_geometry"] = deepcopy(level["stage_geometry"])
    data["encounters"] = deepcopy(level["encounters"])

    # Boss-loading timings are deliberately authored per level so a short
    # finale arena never inherits Level 1's world-space relocation point.
    boss_loading = data.setdefault("transitions", {}).setdefault("boss_loading", {})
    boss_loading.update(deepcopy(level.get("boss_loading", {})))
    boss_loading["enabled"] = bool(level.get("boss_transition", False))
    return validate_gameplay(data)


def _validate_stage_geometry(geometry: Any, stage_width: float, label: str) -> None:
    """Validate a level's full walkable strip and prop collision footprints."""

    if not isinstance(geometry, dict):
        raise ConfigError(f"{label} must be an object")
    rails = geometry.get("rails", [])
    if not rails:
        raise ConfigError(f"{label}.rails must contain at least one segment")
    ordered = sorted(rails, key=lambda item: float(item["start_x"]))
    cursor = 0.0
    for index, segment in enumerate(ordered):
        start_x = float(segment["start_x"])
        end_x = float(segment["end_x"])
        far_depth = float(segment["far_depth"])
        near_depth = float(segment["near_depth"])
        if abs(start_x - cursor) > 0.01:
            raise ConfigError(f"{label}.rails[{index}] leaves a gap before x={start_x:g}")
        if end_x <= start_x or near_depth <= far_depth:
            raise ConfigError(f"{label}.rails[{index}] has invalid bounds")
        cursor = end_x
    if abs(cursor - stage_width) > 0.01:
        raise ConfigError(f"{label}.rails must cover the complete stage width")

    for index, obstacle in enumerate(geometry.get("obstacles", [])):
        if not 0 <= float(obstacle.get("x", -1)) <= stage_width:
            raise ConfigError(f"{label}.obstacles[{index}].x is outside the stage")
        if float(obstacle.get("half_width", 0)) <= 0 or float(obstacle.get("half_depth", 0)) <= 0:
            raise ConfigError(f"{label}.obstacles[{index}] requires positive half extents")


def _finite_number(value: Any, label: str) -> float:
    """Return one strict JSON number or raise a path-specific config error."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ConfigError(f"{label} must be a finite number")
    return result


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{label} must be a positive integer")
    return value


def _validate_hitbox_frames(frames: Any, label: str) -> None:
    """Validate normalized, ordered hitbox animation samples."""

    if not isinstance(frames, list) or len(frames) < 2:
        raise ConfigError(f"{label} must contain at least two frames")

    sample_times: list[float] = []
    for index, frame in enumerate(frames):
        frame_label = f"{label}[{index}]"
        if not isinstance(frame, dict):
            raise ConfigError(f"{frame_label} must be an object")
        at = _finite_number(frame.get("at"), f"{frame_label}.at")
        if not 0.0 <= at <= 1.0:
            raise ConfigError(f"{frame_label}.at must be between zero and one")
        if sample_times and at <= sample_times[-1]:
            raise ConfigError(f"{label} must be strictly ordered by at")
        sample_times.append(at)

        for field in ("reach_scale", "depth_scale", "height_scale"):
            value = _finite_number(frame.get(field), f"{frame_label}.{field}")
            if value <= 0.0:
                raise ConfigError(f"{frame_label}.{field} must be positive")
        for field, value in frame.items():
            if field.startswith("offset_") or field.endswith("_offset"):
                _finite_number(value, f"{frame_label}.{field}")

    if not math.isclose(sample_times[0], 0.0, abs_tol=1e-9):
        raise ConfigError(f"{label} must start at at=0")
    if not math.isclose(sample_times[-1], 1.0, abs_tol=1e-9):
        raise ConfigError(f"{label} must end at at=1")


def _validate_projection_profile(profile: Mapping[str, Any], label: str) -> None:
    if not isinstance(profile, Mapping):
        raise ConfigError(f"{label} must be an object")

    mode = str(profile.get("mode", "")).strip()
    if mode not in {"orthographic", "oblique", "oblique_orthographic"}:
        raise ConfigError(f"{label}.mode must be orthographic or oblique")

    logical_resolution = profile.get("logical_resolution", LOGICAL_SIZE)
    if (
        not isinstance(logical_resolution, (list, tuple))
        or len(logical_resolution) != 2
        or tuple(logical_resolution) != LOGICAL_SIZE
    ):
        raise ConfigError(f"{label}.logical_resolution must be [640, 360]")

    for field in ("depth_scale", "world_x_scale", "elevation_scale"):
        value = _finite_number(
            profile.get(field, 1.0),
            f"{label}.{field}",
        )
        if value <= 0.0:
            raise ConfigError(f"{label}.{field} must be positive")
    _finite_number(
        profile.get("oblique_x_shear", profile.get("oblique_x_per_depth", 0.0)),
        f"{label}.oblique_x_shear|oblique_x_per_depth",
    )

    for field in ("screen_origin_x", "screen_y_origin", "depth_origin"):
        _finite_number(profile.get(field, 0.0), f"{label}.{field}")

    pixel_snap = profile.get("pixel_snap", True)
    if not isinstance(pixel_snap, bool):
        raise ConfigError(f"{label}.pixel_snap must be boolean")

    rails = profile.get("playable_depth_rails")
    if not isinstance(rails, Mapping):
        raise ConfigError(f"{label}.playable_depth_rails must be an object")
    far = _finite_number(rails.get("far"), f"{label}.playable_depth_rails.far")
    middle = _finite_number(rails.get("middle"), f"{label}.playable_depth_rails.middle")
    near = _finite_number(rails.get("near"), f"{label}.playable_depth_rails.near")
    if not (far <= middle <= near):
        raise ConfigError(
            f"{label}.playable_depth_rails must be ordered from far to near"
        )

    reference = profile.get("reference_physical_dimensions")
    if not isinstance(reference, Mapping):
        raise ConfigError(f"{label}.reference_physical_dimensions must be an object")
    adult_height = _finite_number(
        reference.get("neutral_adult_height_m"),
        f"{label}.reference_physical_dimensions.neutral_adult_height_m",
    )
    sedan_height = _finite_number(
        reference.get("sedan_roof_height_m"),
        f"{label}.reference_physical_dimensions.sedan_roof_height_m",
    )
    door_height = _finite_number(
        reference.get("door_height_m"),
        f"{label}.reference_physical_dimensions.door_height_m",
    )
    if not (adult_height > 0 and sedan_height > 0 and door_height > 0):
        raise ConfigError(f"{label}.reference_physical_dimensions must be positive")
    if not 0.7 <= (sedan_height / adult_height) <= 0.9:
        raise ConfigError(
            f"{label}.reference_physical_dimensions.sedan_roof_height_m must stay 0.70-0.90 of "
            "neutral_adult_height_m"
        )
    if not 1.05 <= (door_height / adult_height) <= 1.20:
        raise ConfigError(
            f"{label}.reference_physical_dimensions.door_height_m must stay 1.05-1.20 of "
            "neutral_adult_height_m"
        )


def _merge_projection_settings(
    projection: Mapping[str, Any],
    profiles: Mapping[str, Any],
) -> dict[str, Any]:
    profile_id = str(projection.get("profile_id", "")).strip()
    if not profile_id:
        return dict(projection)
    base = profiles.get(profile_id)
    if not isinstance(base, Mapping):
        raise ConfigError(f"engine.projection profile_id '{profile_id}' does not exist")
    merged = dict(base)
    merged.update({key: value for key, value in projection.items() if key != "profile_id"})
    return merged


def _projection_float(
    projection: Mapping[str, Any],
    names: tuple[str, ...],
    label: str,
    default: float | None = None,
) -> float:
    for name in names:
        if name in projection:
            return _finite_number(projection[name], label)
    if default is None:
        raise ConfigError(f"{label} must be set")
    return _finite_number(default, label)


def _validate_projection_settings(projection: Mapping[str, Any]) -> None:
    mode = str(projection.get("mode", "")).strip()
    if mode not in {"orthographic", "oblique", "oblique_orthographic"}:
        raise ConfigError("engine.projection.mode must be orthographic or oblique")
    _projection_float(
        projection,
        ("screen_origin_x",),
        "engine.projection.screen_origin_x",
        default=0.0,
    )
    screen_y = _projection_float(
        projection,
        ("screen_y_origin", "floor_screen_y"),
        "engine.projection.screen_y_origin",
    )
    _projection_float(
        projection,
        ("depth_origin",),
        "engine.projection.depth_origin",
        default=screen_y,
    )
    _projection_float(
        projection,
        ("pixels_per_world_x", "world_x_scale"),
        "engine.projection.pixels_per_world_x",
        default=1.0,
    )
    _projection_float(
        projection,
        ("pixels_per_depth", "depth_scale"),
        "engine.projection.pixels_per_depth",
        default=1.0,
    )
    _projection_float(
        projection,
        ("pixels_per_elevation", "elevation_scale"),
        "engine.projection.pixels_per_elevation",
        default=1.0,
    )
    _projection_float(
        projection,
        ("oblique_x_per_depth", "oblique_x_shear"),
        "engine.projection.oblique_x_per_depth",
        default=0.0,
    )
    scale_sprites_with_depth = projection.get("scale_sprites_with_depth", False)
    if not isinstance(scale_sprites_with_depth, bool):
        raise ConfigError("engine.projection.scale_sprites_with_depth must be boolean")
    if scale_sprites_with_depth:
        raise ConfigError("engine projection must keep pixel sprites at a constant depth scale")


def _validate_combat_move(move: Any, label: str) -> None:
    """Validate one player move's required payload and optional combat tuning."""

    if not isinstance(move, dict):
        raise ConfigError(f"{label} must be an object")

    timing: dict[str, float] = {}
    for field in ("startup", "active", "recovery"):
        value = _finite_number(move.get(field), f"{label}.{field}")
        if value <= 0.0:
            raise ConfigError(f"{label}.{field} must be positive")
        timing[field] = value
    for field in ("range_x", "range_y"):
        value = _finite_number(move.get(field), f"{label}.{field}")
        if value <= 0.0:
            raise ConfigError(f"{label}.{field} must be positive")
    for field in ("damage", "hitstun", "knockback", "meter"):
        value = _finite_number(move.get(field), f"{label}.{field}")
        if value < 0.0:
            raise ConfigError(f"{label}.{field} must be non-negative")

    if "buffer_window" in move:
        if _finite_number(move["buffer_window"], f"{label}.buffer_window") <= 0.0:
            raise ConfigError(f"{label}.buffer_window must be positive")
    if "cancel_start" in move:
        cancel_start = _finite_number(move["cancel_start"], f"{label}.cancel_start")
        active_end = timing["startup"] + timing["active"]
        total = active_end + timing["recovery"]
        if not active_end <= cancel_start <= total:
            raise ConfigError(
                f"{label}.cancel_start must be between active end and move end"
            )
    if "max_hits_per_target" in move:
        _positive_integer(move["max_hits_per_target"], f"{label}.max_hits_per_target")
    if "max_targets" in move:
        _positive_integer(move["max_targets"], f"{label}.max_targets")
    if "rehit_delay" in move:
        if _finite_number(move["rehit_delay"], f"{label}.rehit_delay") < 0.0:
            raise ConfigError(f"{label}.rehit_delay must be non-negative")
    for field in (
        "reach_forgiveness",
        "depth_forgiveness",
        "elevation_forgiveness",
        "temporal_forgiveness",
        "lane_assist",
        "aim_range_bonus",
        "lunge",
        "rear_tolerance",
    ):
        if field in move and _finite_number(move[field], f"{label}.{field}") < 0.0:
            raise ConfigError(f"{label}.{field} must be non-negative")
    for field in ("hit_downed", "chain_on_whiff", "heavy_cancel"):
        if field in move and not isinstance(move[field], bool):
            raise ConfigError(f"{label}.{field} must be boolean")
    if "hitbox_frames" in move:
        _validate_hitbox_frames(move["hitbox_frames"], f"{label}.hitbox_frames")


def validate_gameplay(
    data: dict[str, Any],
    *,
    location_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the small set of invariants every engine system relies on."""

    if not isinstance(data, dict):
        raise ConfigError("gameplay root must be an object")
    for section in (
        "meta",
        "campaign",
        "engine",
        "stage_geometry",
        "players",
        "moves",
        "enemies",
        "chief",
        "ko_companion",
        "bb_gun",
        "shelly_propane",
        "audio",
        "transitions",
        "completion",
        "encounters",
    ):
        if section not in data:
            raise ConfigError(f"gameplay is missing required section: {section}")

    try:
        manifest = (
            dict(location_manifest)
            if location_manifest is not None
            else _location_manifest_for_gameplay(data)
        )
        validate_gameplay_locations(data, manifest)
        hydrate_gameplay_locations(data, manifest)
    except LocationLockError as exc:
        raise ConfigError(f"Chapter 1 location lock: {exc}") from exc

    meta = data["meta"]
    if tuple(meta.get("virtual_resolution", ())) != LOGICAL_SIZE:
        raise ConfigError(f"meta.virtual_resolution must be {list(LOGICAL_SIZE)}")
    stage_width = float(meta.get("stage_width", 0))
    if stage_width <= LOGICAL_SIZE[0]:
        raise ConfigError("meta.stage_width must be wider than the logical screen")
    fixed_hz = float(meta.get("fixed_hz", 0))
    if not 30.0 <= fixed_hz <= 240.0:
        raise ConfigError("meta.fixed_hz must be between 30 and 240")
    if float(meta.get("lane_bottom", 0)) <= float(meta.get("lane_top", 0)):
        raise ConfigError("meta lane_bottom must be greater than lane_top")

    campaign = data["campaign"]
    chapters = campaign.get("chapters", ())
    if not isinstance(chapters, list) or not chapters:
        raise ConfigError("campaign.chapters must contain at least one chapter")
    enemy_kinds = {str(kind).strip() for kind in data["enemies"] if str(kind).strip()}
    if not enemy_kinds:
        raise ConfigError("enemies must define at least one enemy archetype")
    seen_level_ids: set[str] = set()
    for chapter_index, chapter in enumerate(chapters):
        chapter_id = str(chapter.get("id", "")).strip()
        levels = chapter.get("levels", ())
        if not chapter_id or not isinstance(levels, list) or not levels:
            raise ConfigError(f"campaign.chapters[{chapter_index}] requires an id and levels")
        ordered_numbers: list[int] = []
        couch_levels: list[dict[str, Any]] = []
        for level_index, level in enumerate(levels):
            level_id = str(level.get("id", "")).strip()
            if not level_id or level_id in seen_level_ids:
                raise ConfigError(f"campaign level id must be non-empty and unique: {level_id!r}")
            seen_level_ids.add(level_id)
            number = int(level.get("number", 0))
            ordered_numbers.append(number)
            level_width = float(level.get("stage_width", 0))
            if level_width <= LOGICAL_SIZE[0]:
                raise ConfigError(f"campaign level {level_id} must be wider than the logical screen")
            if not str(level.get("start", {}).get("id", "")).strip() or not str(level.get("end", {}).get("id", "")).strip():
                raise ConfigError(f"campaign level {level_id} requires start and end landmark ids")
            landmarks = level.get("landmarks", ())
            if not isinstance(landmarks, list) or len(landmarks) < 2:
                raise ConfigError(f"campaign level {level_id} requires at least two ordered landmarks")
            previous_landmark_x = -1.0
            for landmark_index, landmark in enumerate(landmarks):
                landmark_id = str(landmark.get("id", "")).strip()
                landmark_x = float(landmark.get("x", -1.0))
                if not landmark_id or not 0 <= landmark_x <= level_width or landmark_x <= previous_landmark_x:
                    raise ConfigError(
                        f"campaign level {level_id} landmark {landmark_index} must be ordered inside the stage"
                    )
                previous_landmark_x = landmark_x
            _validate_stage_geometry(
                level.get("stage_geometry"),
                level_width,
                f"campaign level {level_id}.stage_geometry",
            )
            encounters = level.get("encounters", ())
            if not isinstance(encounters, list) or not encounters:
                raise ConfigError(f"campaign level {level_id} requires encounters")
            previous_level_trigger = -1.0
            couch_waves = 0
            is_finale = bool(level.get("chapter_finale", False))
            for encounter_index, encounter in enumerate(encounters):
                trigger = float(encounter.get("trigger_x", -1))
                gate = float(encounter.get("gate_x", -1))
                camera_x = float(encounter.get("camera_x", -1))
                if trigger <= previous_level_trigger or not trigger < gate <= level_width:
                    raise ConfigError(
                        f"campaign level {level_id} encounter {encounter_index} has invalid trigger/gate positions"
                    )
                if not 0 <= camera_x <= level_width - LOGICAL_SIZE[0]:
                    raise ConfigError(
                        f"campaign level {level_id} encounter {encounter_index} camera_x is outside bounds"
                    )
                base = encounter.get("base", ())
                if not isinstance(base, list) or not base:
                    raise ConfigError(f"campaign level {level_id} encounter {encounter_index} requires a base wave")
                if any(str(kind) not in enemy_kinds for kind in base):
                    raise ConfigError(f"campaign level {level_id} encounter {encounter_index} references an unknown enemy")
                reinforcements = encounter.get("post_clear_reinforcements", [])
                if not isinstance(reinforcements, list):
                    raise ConfigError(
                        f"campaign level {level_id} encounter {encounter_index} reinforcements must be a list"
                    )
                if "couch" in base and reinforcements:
                    raise ConfigError("Couch final wave cannot have post-clear reinforcements")
                for reinforcement_index, reinforcement in enumerate(reinforcements):
                    if not isinstance(reinforcement, dict):
                        raise ConfigError(
                            f"campaign level {level_id} encounter {encounter_index} reinforcement {reinforcement_index} must be an object"
                        )
                    reinforcement_base = reinforcement.get("base", ())
                    if not isinstance(reinforcement_base, list) or not reinforcement_base:
                        raise ConfigError(
                            f"campaign level {level_id} encounter {encounter_index} reinforcement {reinforcement_index} requires enemies"
                        )
                    if any(str(kind) not in enemy_kinds or str(kind) == "couch" for kind in reinforcement_base):
                        raise ConfigError(
                            f"campaign level {level_id} encounter {encounter_index} reinforcement {reinforcement_index} references an invalid enemy"
                        )
                    if not str(reinforcement.get("speech", "")).strip():
                        raise ConfigError(
                            f"campaign level {level_id} encounter {encounter_index} reinforcement {reinforcement_index} requires speech"
                        )
                if is_finale and (
                    any(kind in {"security", "police"} for kind in base)
                    or any(
                        any(kind in {"security", "police"} for kind in reinforcement["base"])
                        for reinforcement in reinforcements
                    )
                ):
                    raise ConfigError("Couch finale cannot include security or police reinforcements")
                previous_level_trigger = trigger
                couch_waves += sum(1 for kind in base if str(kind) == "couch")
            boss = level.get("boss")
            has_transition = bool(level.get("boss_transition", False))
            if couch_waves:
                couch_levels.append(level)
                if boss != "couch" or couch_waves != 1 or not is_finale or not has_transition:
                    raise ConfigError(f"Couch must be the single boss wave of a chapter-finale level: {level_id}")
            elif boss is not None or has_transition:
                raise ConfigError(f"non-boss campaign level cannot declare a boss transition: {level_id}")
        if ordered_numbers != list(range(1, len(levels) + 1)):
            raise ConfigError(f"campaign chapter {chapter_id} level numbers must be consecutive from 1")
        if chapter_id == "chapter_1":
            if len(couch_levels) != 1 or couch_levels[0] is not levels[-1]:
                raise ConfigError("campaign chapter_1 must place Couch only in its last level")
        elif couch_levels:
            raise ConfigError("Couch is reserved for the Chapter 1 finale")

    active_level = active_campaign_level(data)
    if str(active_level.get("status")) != "playable":
        raise ConfigError("campaign.active_level_id must select a playable level")
    for key in ("level_id", "level_title", "background_theme"):
        expected_key = {"level_id": "id", "level_title": "title", "background_theme": "background_theme"}[key]
        if str(meta.get(key, "")) != str(active_level.get(expected_key, "")):
            raise ConfigError(f"meta.{key} must match the active campaign level")
    if abs(stage_width - float(active_level.get("stage_width", 0))) > 0.01:
        raise ConfigError("meta.stage_width must match the active campaign level")
    if data.get("stage_geometry") != active_level.get("stage_geometry"):
        raise ConfigError("runtime stage_geometry must match the active campaign level")
    if data.get("encounters") != active_level.get("encounters"):
        raise ConfigError("runtime encounters must match the active campaign level")
    if bool(data.get("transitions", {}).get("boss_loading", {}).get("enabled", False)) != bool(
        active_level.get("boss_transition", False)
    ):
        raise ConfigError("boss-loading availability must match the active campaign level")

    couch = data["enemies"].get("couch", {})
    retreat_ratios = couch.get("retreat_health_ratios", ())
    if (
        not isinstance(retreat_ratios, list)
        or len(retreat_ratios) != 2
        or not 0.0 < float(retreat_ratios[1]) < float(retreat_ratios[0]) < 1.0
    ):
        raise ConfigError("enemies.couch.retreat_health_ratios must contain two descending ratios inside 0-1")
    retreat_waves = couch.get("retreat_add_waves", ())
    if not isinstance(retreat_waves, list) or len(retreat_waves) != 2:
        raise ConfigError("enemies.couch.retreat_add_waves must contain exactly two waves")
    for wave_index, wave in enumerate(retreat_waves):
        if (
            not isinstance(wave, list)
            or not wave
            or any(str(kind) not in enemy_kinds or str(kind) in {"couch", "security", "police"} for kind in wave)
        ):
            raise ConfigError(f"enemies.couch.retreat_add_waves[{wave_index}] references an invalid dope-fiend enemy")
    for field in (
        "retreat_jump_speed",
        "retreat_return_speed",
        "retreat_refuge_x",
        "retreat_hop_height",
        "retreat_refuge_visual_offset_x",
        "retreat_minimum_refuge_seconds",
        "retreat_return_cooldown",
        "retreat_taunt_seconds",
    ):
        if float(couch.get(field, 0)) <= 0:
            raise ConfigError(f"enemies.couch.{field} must be positive")
    couch_stage_widths = [
        float(level["stage_width"])
        for chapter in chapters
        for level in chapter["levels"]
        if level.get("boss") == "couch"
    ]
    if not couch_stage_widths or float(couch["retreat_refuge_x"]) > min(couch_stage_widths):
        raise ConfigError("enemies.couch.retreat_refuge_x must stay inside the Couch finale")
    if not float(meta["lane_top"]) <= float(couch.get("retreat_refuge_depth", -1)) <= float(meta["lane_bottom"]):
        raise ConfigError("enemies.couch.retreat_refuge_depth must stay inside the walk lane")

    engine = data["engine"]
    if int(engine.get("schema_version", 0)) != 2:
        raise ConfigError("engine.schema_version must be 2")

    engine = data["engine"]
    projection_profiles = data.get("projection_profiles", {})
    if not projection_profiles:
        projection_profiles = engine.get("projection_profiles", {})
    projection = engine.get("projection", {})
    if not isinstance(projection_profiles, Mapping):
        raise ConfigError("projection_profiles must be an object")
    if "chapter1_oblique_v2" not in projection_profiles:
        raise ConfigError("projection_profiles must define chapter1_oblique_v2")
    for profile_id, profile in projection_profiles.items():
        _validate_projection_profile(profile, f"projection_profiles[{profile_id}]")
    if not isinstance(projection, Mapping):
        raise ConfigError("engine.projection must be an object")
    merged_projection = _merge_projection_settings(projection, projection_profiles)
    _validate_projection_settings(merged_projection)
    camera = engine.get("camera", {})
    left = float(camera.get("dead_zone_left", -1))
    right = float(camera.get("dead_zone_right", -1))
    if not 0 <= left < right <= LOGICAL_SIZE[0]:
        raise ConfigError("engine camera dead zone must be ordered inside the logical screen")
    physics = engine.get("physics", {})
    for field in (
        "spatial_cell_size",
        "player_radius_x",
        "player_radius_depth",
        "enemy_radius_x",
        "enemy_radius_depth",
        "boss_radius_x",
        "boss_radius_depth",
        "chief_radius_x",
        "chief_radius_depth",
        "separation_iterations",
    ):
        if float(physics.get(field, 0)) <= 0:
            raise ConfigError(f"engine.physics.{field} must be positive")
    for field in ("player_attack_max_targets", "enemy_attack_max_targets"):
        if int(physics.get(field, 0)) != 1:
            raise ConfigError(f"engine.physics.{field} must be exactly one for readable contacts")
    for field in (
        "player_attack_reach_bonus",
        "player_attack_aim_range_bonus",
        "player_attack_lane_assist",
        "player_attack_depth_tolerance",
        "player_attack_elevation_forgiveness",
        "player_attack_temporal_forgiveness",
        "player_attack_rear_tolerance",
        "enemy_attack_rear_tolerance",
    ):
        if _finite_number(physics.get(field), f"engine.physics.{field}") < 0.0:
            raise ConfigError(f"engine.physics.{field} must be non-negative")
    for field in ("light_hitstop", "heavy_hitstop", "super_hitstop"):
        if _finite_number(physics.get(field), f"engine.physics.{field}") <= 0.0:
            raise ConfigError(f"engine.physics.{field} must be positive")

    _validate_stage_geometry(data["stage_geometry"], stage_width, "stage_geometry")

    player_global = data["players"].get("global", {})
    dodge_duration = _finite_number(
        player_global.get("dodge_duration"), "players.global.dodge_duration"
    )
    dodge_invulnerable = _finite_number(
        player_global.get("dodge_invulnerable"),
        "players.global.dodge_invulnerable",
    )
    if dodge_duration <= 0.0:
        raise ConfigError("players.global.dodge_duration must be positive")
    if dodge_invulnerable < 0.0:
        raise ConfigError("players.global.dodge_invulnerable must be non-negative")
    if dodge_invulnerable > dodge_duration:
        raise ConfigError(
            "players.global.dodge_invulnerable cannot exceed dodge_duration"
        )

    bb_gun = data["bb_gun"]
    max_ammo = int(bb_gun.get("max_ammo", 0))
    start_ammo = int(bb_gun.get("start_ammo", -1))
    if max_ammo <= 0 or not 0 <= start_ammo <= max_ammo:
        raise ConfigError("bb_gun ammo must satisfy 0 <= start_ammo <= max_ammo")
    for field in (
        "cooldown",
        "animation_seconds",
        "damage",
        "speed",
        "range",
        "lane_tolerance",
        "hit_radius_x",
        "pickup_amount",
        "pickup_radius_x",
        "pickup_radius_depth",
        "pickup_ttl",
    ):
        if float(bb_gun.get(field, 0)) <= 0:
            raise ConfigError(f"bb_gun.{field} must be positive")
    drop_min = int(bb_gun.get("drop_ko_min", 0))
    drop_max = int(bb_gun.get("drop_ko_max", 0))
    if not 2 <= drop_min <= drop_max <= 4:
        raise ConfigError("bb_gun drop interval must stay within 2-4 eligible KOs")

    shelly = data["players"].get("shelly", {})
    if float(shelly.get("super_gain_multiplier", 0)) <= 0:
        raise ConfigError("players.shelly.super_gain_multiplier must be positive")
    for field in (
        "chief_frenzy_seconds",
        "frenzy_burst_radius",
        "frenzy_burst_damage",
        "frenzy_burst_hitstun",
        "frenzy_burst_knockback",
        "frenzy_burst_enemy_radius",
        "frenzy_burst_screen_radius",
        "frenzy_cinematic_seconds",
        "frenzy_camera_strength",
        "frenzy_hitstop_seconds",
        "frenzy_flash_seconds",
    ):
        if float(shelly.get(field, 0)) <= 0:
            raise ConfigError(f"players.shelly.{field} must be positive")
    if int(shelly.get("frenzy_burst_targets", 0)) <= 0:
        raise ConfigError("players.shelly.frenzy_burst_targets must be positive")
    dark_alpha = int(shelly.get("frenzy_cinematic_dark_alpha", -1))
    if not 0 <= dark_alpha <= 255:
        raise ConfigError("players.shelly.frenzy_cinematic_dark_alpha must be an alpha value")
    companion_ai = data.get("companion_ai", {})
    if int(companion_ai.get("cpu_shelly_frenzy_goal", 0)) < 2:
        raise ConfigError("companion_ai.cpu_shelly_frenzy_goal must guarantee at least two uses")
    if int(companion_ai.get("cpu_shelly_frenzy_group_min", 0)) < 2:
        raise ConfigError("companion_ai.cpu_shelly_frenzy_group_min must be at least two")
    for field in ("cpu_shelly_frenzy_charge_seconds", "cpu_shelly_frenzy_rearm_seconds"):
        if float(companion_ai.get(field, 0)) <= 0:
            raise ConfigError(f"companion_ai.{field} must be positive")

    ko_companion = data["ko_companion"]
    if not isinstance(ko_companion, dict):
        raise ConfigError("ko_companion must be an object")
    if not isinstance(ko_companion.get("enabled"), bool):
        raise ConfigError("ko_companion.enabled must be boolean")
    intervals = tuple(
        float(value) for value in ko_companion.get("attack_intervals", ())
    )
    if intervals != (20.0, 25.0, 30.0):
        raise ConfigError("ko_companion.attack_intervals must be [20, 25, 30]")
    attack_cycle = tuple(str(value) for value in ko_companion.get("attack_cycle", ()))
    if attack_cycle != ("punch_1", "punch_2", "kick"):
        raise ConfigError(
            "ko_companion.attack_cycle must be [punch_1, punch_2, kick]"
        )
    if int(ko_companion.get("super_every_actions", 0)) != 4:
        raise ConfigError("ko_companion.super_every_actions must be 4")
    for field in (
        "warmup_seconds",
        "prepare_bubble_seconds",
        "selection_fallback_seconds",
        "recent_damage_seconds",
        "skate_speed",
        "follow_speed",
        "follow_distance",
        "follow_depth_offset",
        "contact_x",
        "contact_depth",
        "attack_seconds",
        "attack_impact_seconds",
        "kick_impact_seconds",
        "daze_seconds",
        "fall_seconds",
        "disappear_seconds",
        "super_step_seconds",
        "super_duration",
        "super_contact_offset",
        "stride_distance",
        "offscreen_recall_distance",
    ):
        if float(ko_companion.get(field, 0)) <= 0.0:
            raise ConfigError(f"ko_companion.{field} must be positive")
    if float(ko_companion["attack_impact_seconds"]) >= float(
        ko_companion["attack_seconds"]
    ):
        raise ConfigError(
            "ko_companion.attack_impact_seconds must precede attack_seconds"
        )
    if float(ko_companion["kick_impact_seconds"]) >= float(
        ko_companion["attack_seconds"]
    ):
        raise ConfigError(
            "ko_companion.kick_impact_seconds must precede attack_seconds"
        )
    if float(ko_companion["prepare_bubble_seconds"]) > float(
        ko_companion["warmup_seconds"]
    ):
        raise ConfigError(
            "ko_companion.prepare_bubble_seconds must not exceed warmup_seconds"
        )
    if float(ko_companion["daze_seconds"]) < 2.0:
        raise ConfigError("ko_companion.daze_seconds must last at least two seconds")

    dave = data["players"].get("black_dave", {})
    if not isinstance(dave.get("super_full_map"), bool):
        raise ConfigError("players.black_dave.super_full_map must be boolean")
    for field in (
        "super_damage",
        "super_radius",
        "super_effect_radius",
        "super_screen_radius",
        "super_screen_seconds",
        "super_hitstun",
        "super_knockback",
        "super_enemy_pulse_radius",
        "super_camera_strength",
        "super_camera_seconds",
        "super_flash_seconds",
    ):
        if float(dave.get(field, 0)) <= 0:
            raise ConfigError(f"players.black_dave.{field} must be positive")
    fist_effects = dave.get("fist_effects", {})
    for field in ("trail_radius", "contact_radius"):
        if float(fist_effects.get(field, 0)) <= 0:
            raise ConfigError(f"players.black_dave.fist_effects.{field} must be positive")
    for field in ("color", "contact_color", "combo_color"):
        color = fist_effects.get(field)
        if not isinstance(color, (list, tuple)) or len(color) != 3 or any(not 0 <= int(value) <= 255 for value in color):
            raise ConfigError(f"players.black_dave.fist_effects.{field} must be an RGB color")
    fist_flames = dave.get("fist_flames", {})
    activation_presses = int(fist_flames.get("activation_presses", 0))
    refresh_presses = int(fist_flames.get("refresh_presses", 0))
    if activation_presses < 6:
        raise ConfigError("players.black_dave.fist_flames.activation_presses must be at least six")
    if refresh_presses < 4:
        raise ConfigError("players.black_dave.fist_flames.refresh_presses must be at least four")
    for field in ("press_window_seconds", "active_seconds"):
        if float(fist_flames.get(field, 0)) <= 0:
            raise ConfigError(f"players.black_dave.fist_flames.{field} must be positive")
    if float(fist_flames.get("damage_multiplier", 0)) < 1.20:
        raise ConfigError("players.black_dave.fist_flames.damage_multiplier must be at least 1.20")

    moves = data["moves"]
    if not isinstance(moves, dict):
        raise ConfigError("moves must be an object")
    light_combo = moves.get("light_combo", ())
    if not isinstance(light_combo, list) or len(light_combo) < 2:
        raise ConfigError("moves.light_combo must contain at least two attacks")
    for index, move in enumerate(light_combo):
        _validate_combat_move(move, f"moves.light_combo[{index}]")
        radius = move.get("combo_radius")
        if radius is not None and _finite_number(
            radius, f"moves.light_combo[{index}].combo_radius"
        ) <= 0.0:
            raise ConfigError(f"moves.light_combo[{index}].combo_radius must be positive")
    for move_name in ("heavy", "air"):
        _validate_combat_move(moves.get(move_name), f"moves.{move_name}")

    jermaine = data["players"].get("jermaine", {})
    for field in (
        "height_scale",
        "speed_scale",
        "max_health",
        "weapon_reach_bonus",
        "weapon_damage_scale",
        "super_damage",
        "super_radius",
        "super_hitstun",
        "super_knockback",
    ):
        if float(jermaine.get(field, 0)) <= 0:
            raise ConfigError(f"players.jermaine.{field} must be positive")
    if str(jermaine.get("weapon", "")).upper() != "STICK":
        raise ConfigError("players.jermaine.weapon must be STICK")

    white_dave = data["players"].get("white_dave", {})
    for field in (
        "height_scale", "speed_scale", "max_health", "weapon_reach_bonus",
        "weapon_damage_scale", "super_damage", "super_radius", "super_hitstun",
        "super_knockback",
    ):
        if float(white_dave.get(field, 0)) <= 0:
            raise ConfigError(f"players.white_dave.{field} must be positive")
    if str(white_dave.get("weapon", "")).upper() != "BOLT CUTTERS":
        raise ConfigError("players.white_dave.weapon must be BOLT CUTTERS")
    if float(white_dave["height_scale"]) != float(jermaine["height_scale"]):
        raise ConfigError("players.white_dave.height_scale must match Jermaine")
    if float(white_dave["speed_scale"]) >= float(jermaine["speed_scale"]):
        raise ConfigError("players.white_dave.speed_scale must be slower than Jermaine")
    if float(white_dave["weapon_damage_scale"]) <= float(jermaine["weapon_damage_scale"]):
        raise ConfigError("players.white_dave.weapon_damage_scale must exceed Jermaine")

    for character in ("black_dave", "shelly", "jermaine", "white_dave"):
        character_config = data["players"].get(character, {})
        sequence = character_config.get("light_combo_sequence")
        if sequence is None:
            continue
        label = f"players.{character}.light_combo_sequence"
        if not isinstance(sequence, list) or not sequence:
            raise ConfigError(f"{label} must be a non-empty list of move indices")
        for index, move_index in enumerate(sequence):
            if (
                isinstance(move_index, bool)
                or not isinstance(move_index, int)
                or not 0 <= move_index < len(light_combo)
            ):
                raise ConfigError(
                    f"{label}[{index}] must index moves.light_combo"
                )

    enemies = data["enemies"]
    if not isinstance(enemies, dict):
        raise ConfigError("enemies must be an object")
    for enemy_name, enemy in enemies.items():
        label = f"enemies.{enemy_name}"
        if not isinstance(enemy, dict):
            raise ConfigError(f"{label} must be an object")
        if _finite_number(enemy.get("active"), f"{label}.active") <= 0.0:
            raise ConfigError(f"{label}.active must be positive")
        if str(enemy_name) == "police" or any(
            field in enemy for field in ("ranged_attack_range", "ranged_depth_range")
        ):
            for field in ("ranged_attack_range", "ranged_depth_range"):
                if _finite_number(enemy.get(field), f"{label}.{field}") <= 0.0:
                    raise ConfigError(f"{label}.{field} must be positive")

    scoring = data.get("scoring", {})
    _positive_integer(scoring.get("combo_step_hits"), "scoring.combo_step_hits")

    scaling = data.get("scaling", {})
    for field in (
        "wave_budget",
        "encounter_density_multiplier",
        "enemy_durability_scale",
        "enemy_damage_scale",
        "enemy_score_scale",
        "focused_enemy_queue_cap",
        "enemy_caps",
        "attack_tokens",
    ):
        values = scaling.get(field)
        if not isinstance(values, list) or len(values) < 4 or any(float(value) <= 0 for value in values):
            raise ConfigError(f"scaling.{field} must contain four positive player-count values")
    density = scaling["encounter_density_multiplier"]
    if any(float(value) < 1.0 for value in density):
        raise ConfigError("scaling.encounter_density_multiplier must not reduce the authored crowd")
    focus_caps = scaling["focused_enemy_queue_cap"]
    live_caps = scaling["enemy_caps"]
    if any(int(queue) < int(live) for queue, live in zip(focus_caps, live_caps)):
        raise ConfigError("scaling.focused_enemy_queue_cap must cover its live-enemy cap")
    if any(float(value) <= 1.0 for value in scaling["enemy_durability_scale"]):
        raise ConfigError("scaling.enemy_durability_scale must keep focused enemies tougher than baseline")

    propane = data["shelly_propane"]
    propane_max = float(propane.get("meter_max", 0))
    propane_start = float(propane.get("start_meter", -1))
    if propane_max <= 0 or not 0 <= propane_start <= propane_max:
        raise ConfigError("shelly_propane meter must satisfy 0 <= start_meter <= meter_max")
    activation_minimum = float(propane.get("activation_minimum", 0))
    if not 0 < activation_minimum <= propane_max:
        raise ConfigError("shelly_propane.activation_minimum must fit inside its meter")
    for field in (
        "drain_per_second",
        "tick_seconds",
        "damage_per_tick",
        "range",
        "lane_tolerance",
        "hitstun",
        "knockback",
        "pickup_amount",
        "pickup_radius_x",
        "pickup_radius_depth",
        "pickup_ttl",
        "cpu_max_range",
        "cpu_lane_tolerance",
        "cpu_action_cooldown",
        "cpu_chief_super_range",
    ):
        if float(propane.get(field, 0)) <= 0:
            raise ConfigError(f"shelly_propane.{field} must be positive")
    if not 0 <= float(propane.get("cpu_min_range", -1)) <= float(propane["cpu_max_range"]):
        raise ConfigError("shelly_propane cpu range must be ordered")
    propane_drop_min = int(propane.get("drop_ko_min", 0))
    propane_drop_max = int(propane.get("drop_ko_max", 0))
    if not 2 <= propane_drop_min <= propane_drop_max <= 4:
        raise ConfigError("shelly_propane drop interval must stay within 2-4 eligible KOs")

    audio = data["audio"]
    menu_music = str(audio.get("menu_music", "")).strip()
    stage_music = str(audio.get("stage_music", "")).strip()
    if not menu_music or not stage_music or menu_music == stage_music:
        raise ConfigError("audio menu_music and stage_music must name distinct files")
    if not all(name.lower().endswith(".ogg") for name in (menu_music, stage_music)):
        raise ConfigError("audio menu_music and stage_music must use packaged OGG files")

    boss_loading = data["transitions"].get("boss_loading", {})
    transition_duration = float(boss_loading.get("duration_seconds", 0))
    relocate_seconds = float(boss_loading.get("relocate_seconds", 0))
    if transition_duration <= 0 or not 0 < relocate_seconds < transition_duration:
        raise ConfigError("transitions.boss_loading relocation must occur inside its positive duration")
    party_x = float(boss_loading.get("party_x", -1))
    party_depth = float(boss_loading.get("party_depth", -1))
    if not 0 <= party_x <= stage_width:
        raise ConfigError("transitions.boss_loading.party_x must be inside the stage")
    if not float(meta["lane_top"]) <= party_depth <= float(meta["lane_bottom"]):
        raise ConfigError("transitions.boss_loading.party_depth must be inside the walk lane")

    completion = data["completion"]
    hug_seconds = float(completion.get("hug_seconds", 0))
    treat_seconds = float(completion.get("treat_toss_seconds", 0))
    release_seconds = float(completion.get("treat_release_seconds", -1))
    if hug_seconds <= 0 or treat_seconds <= 0 or not 0 <= release_seconds <= treat_seconds:
        raise ConfigError("completion celebration durations must be positive and release treats during the toss")
    thresholds = completion.get("rank_rules", {}).get("thresholds", {})
    if not isinstance(thresholds, dict) or not thresholds:
        raise ConfigError("completion.rank_rules.thresholds must be a non-empty object")
    threshold_values = [float(value) for value in thresholds.values()]
    if any(value < 0 for value in threshold_values) or threshold_values != sorted(threshold_values, reverse=True):
        raise ConfigError("completion rank thresholds must be non-negative and ordered highest to lowest")

    if not isinstance(data["encounters"], list) or not data["encounters"]:
        raise ConfigError("encounters must be a non-empty list")
    previous_trigger = -1.0
    for index, encounter in enumerate(data["encounters"]):
        trigger = float(encounter.get("trigger_x", -1))
        gate = float(encounter.get("gate_x", -1))
        camera_x = float(encounter.get("camera_x", -1))
        if trigger <= previous_trigger or not trigger < gate <= stage_width:
            raise ConfigError(f"encounters[{index}] must have ordered trigger and gate positions")
        if not 0 <= camera_x <= stage_width - LOGICAL_SIZE[0]:
            raise ConfigError(f"encounters[{index}].camera_x is outside camera bounds")
        previous_trigger = trigger
    return data
