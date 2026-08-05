"""Data contract for Chapter 1's authored encounter and pacing content.

The live ``gameplay.json`` remains the compact combat/runtime snapshot.  This
module keeps production-facing content (beats, optional routes, enemy roles,
travel cards, checkpoints, and pacing targets) in a separate editable file so
the campaign can grow without turning the engine configuration into a prose
document or a second hard-coded level script.

``compile_level_content`` is intentionally side-effect free.  The runtime can
call it when a level becomes active, then hand the returned groups to its
existing encounter queue.  It resolves fiction-facing enemy variants to the
engine's stable enemy kinds and applies only explicit, deterministic
player-count additions; it never rolls random reinforcements.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .config import campaign_levels, load_json, resource_path
from .location_lock import (
    LocationLockError,
    load_location_lock,
    validate_chapter_content_locations,
)


class ChapterContentError(ValueError):
    """Raised when the editable Chapter 1 content contract is incomplete."""


_LEVEL_IDS = (
    "chapter_1_level_1",
    "chapter_1_level_2",
    "chapter_1_level_3",
    "chapter_1_level_4",
)
_PROFILE_NAMES = ("normal", "experienced", "minimum")
_PLAYER_COUNTS = (1, 2, 3, 4)
_RUNTIME_ENEMY_KINDS = {"stick", "cart", "whip", "pipe", "security", "homeless", "police", "couch"}
_VARIANT_ATTACK_STYLES = {
    "homeless": {"glass_bottle", "bike_tire"},
    "security": {"security_flashlight"},
    "police": {"nightstick", "taser"},
}


@dataclass(frozen=True)
class PacingProfile:
    """A repeatable authored playtime target, expressed in in-game minutes."""

    name: str
    level_minutes: tuple[tuple[str, float], ...]
    travel_dialogue_minutes: float

    @property
    def total_minutes(self) -> float:
        return sum(minutes for _, minutes in self.level_minutes) + self.travel_dialogue_minutes

    def minutes_for_level(self, level_id: str) -> float:
        for candidate_id, minutes in self.level_minutes:
            if candidate_id == level_id:
                return minutes
        raise KeyError(f"No pacing budget exists for {level_id!r}")


def load_chapter_content(
    relative: str = "data/chapter_content.json",
    *,
    gameplay: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load and validate the editable Chapter 1 production-content file.

    Passing the live gameplay mapping additionally checks that every authored
    content level points at a real campaign level.  That is useful at startup
    and in package self-tests while keeping the loader inexpensive for tools.
    """

    data = load_json(relative)
    return validate_chapter_content(data, gameplay=gameplay)


def chapter_levels(data: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return authored levels in their immutable Chapter 1 route order."""

    levels = data.get("levels", ())
    if not isinstance(levels, Sequence):
        raise ChapterContentError("levels must be a list")
    return tuple(level for level in levels if isinstance(level, dict))


def level_content(data: Mapping[str, Any], level_id: str) -> dict[str, Any]:
    """Get one level's content record by its stable runtime level id."""

    target = str(level_id).strip()
    for level in chapter_levels(data):
        if str(level.get("runtime_level_id", "")) == target:
            return level
    raise ChapterContentError(f"No Chapter 1 content exists for level {target or '<empty>'}")


def enemy_variants(data: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Index fictional encounter roles by id without exposing mutable input."""

    variants = data.get("enemy_variants", ())
    if not isinstance(variants, Sequence):
        raise ChapterContentError("enemy_variants must be a list")
    return {
        str(variant["id"]): variant
        for variant in variants
        if isinstance(variant, dict) and str(variant.get("id", "")).strip()
    }


def pace_profile(data: Mapping[str, Any], name: str) -> PacingProfile:
    """Return a deterministic authored pacing profile for diagnostics/QA."""

    profile_name = str(name).strip().lower()
    profiles = data.get("pacing", {}).get("profiles", {})
    if not isinstance(profiles, Mapping) or profile_name not in profiles:
        raise ChapterContentError(f"Unknown pacing profile: {profile_name or '<empty>'}")
    profile = profiles[profile_name]
    if not isinstance(profile, Mapping):
        raise ChapterContentError(f"Pacing profile {profile_name} must be an object")
    level_minutes = profile.get("level_minutes", {})
    if not isinstance(level_minutes, Mapping):
        raise ChapterContentError(f"Pacing profile {profile_name}.level_minutes must be an object")
    return PacingProfile(
        name=profile_name,
        level_minutes=tuple((level_id, float(level_minutes[level_id])) for level_id in _LEVEL_IDS),
        travel_dialogue_minutes=float(profile.get("travel_dialogue_minutes", 0.0)),
    )


def compile_level_content(
    data: Mapping[str, Any],
    level_id: str,
    player_count: int,
) -> dict[str, Any]:
    """Resolve one level's authored content into deterministic runtime waves.

    Returned ``spawn_groups`` retain their content ids, but gain
    ``resolved_variant_ids`` and ``runtime_kinds``.  The engine can therefore
    preserve the authored encounter metadata for dialogue, camera, rewards,
    and replay records while its current enemy factory receives only the
    familiar ``stick/cart/whip/pipe/security/homeless/police/couch`` strings.
    """

    if int(player_count) not in _PLAYER_COUNTS:
        raise ChapterContentError("player_count must be between 1 and 4")
    # Validate before compiling so packaged overrides fail at the menu rather
    # than half-way through an encounter.
    validate_chapter_content(dict(data))
    compiled = deepcopy(level_content(data, level_id))
    variants = enemy_variants(data)
    scale = deepcopy(data["player_count_scaling"][str(int(player_count))])

    scale["player_count"] = int(player_count)
    all_encounters = [
        *compiled.get("major_fights", ()),
        *compiled.get("ambush_or_optional", ()),
        *compiled.get("environmental_events", ()),
    ]
    for encounter in all_encounters:
        if not isinstance(encounter, dict):
            continue
        _compile_spawn_groups(encounter, variants, scale)

    compiled["runtime_player_count"] = int(player_count)
    compiled["runtime_scaling"] = scale
    compiled["pacing_minutes"] = {
        name: pace_profile(data, name).minutes_for_level(str(level_id)) for name in _PROFILE_NAMES
    }
    if str(level_id) == _LEVEL_IDS[-1]:
        compiled["couch_boss"] = compile_couch_contract(data, player_count)
    return compiled


def compile_couch_contract(data: Mapping[str, Any], player_count: int) -> dict[str, Any]:
    """Resolve Couch's two crew calls into the same stable runtime kinds.

    The caller owns when those groups spawn: phase two begins at 67% health
    and phase three begins at 34%.  This helper only turns the authored,
    player-count-aware crew definitions into queue-ready values and preserves
    the exact BMX/targetability contract for the boss controller.
    """

    if int(player_count) not in _PLAYER_COUNTS:
        raise ChapterContentError("player_count must be between 1 and 4")
    validate_chapter_content(dict(data))
    compiled = deepcopy(data["couch_boss_contract"])
    variants = enemy_variants(data)
    scale = data["player_count_scaling"][str(int(player_count))]
    scale = {
        "player_count": int(player_count),
        "max_live_enemies": scale["max_live_enemies"],
        "enemy_health_multiplier": scale["enemy_health_multiplier"],
        "enemy_damage_multiplier": scale["enemy_damage_multiplier"],
    }
    for phase in compiled["phases"]:
        retreat = phase.get("retreat")
        if not isinstance(retreat, dict):
            continue
        base_ids = list(retreat["reinforcement_variants"])
        additions = retreat.get("player_count_additions", {}).get(str(int(player_count)), [])
        resolved_ids = [*base_ids, *additions]
        retreat["resolved_variant_ids"] = tuple(resolved_ids)
        retreat["runtime_kinds"] = tuple(str(variants[variant_id]["runtime_kind"]) for variant_id in resolved_ids)
        retreat["max_live_enemies"] = int(scale["max_live_enemies"])
        retreat["health_multiplier"] = float(scale["enemy_health_multiplier"])
        retreat["damage_multiplier"] = float(scale["enemy_damage_multiplier"])
    return compiled


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ChapterContentError(f"{label} must be an object")
    return value


def _require_text(value: Any, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ChapterContentError(f"{label} must be non-empty")
    return result


def _require_positive(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ChapterContentError(f"{label} must be positive") from exc
    if result <= 0:
        raise ChapterContentError(f"{label} must be positive")
    return result


def _validate_variant_list(
    variants: Any,
    known_variants: Mapping[str, Mapping[str, Any]],
    label: str,
) -> None:
    if not isinstance(variants, list) or not variants:
        raise ChapterContentError(f"{label} must contain at least one enemy variant")
    for variant_id in variants:
        if str(variant_id) not in known_variants:
            raise ChapterContentError(f"{label} references unknown enemy variant {variant_id!r}")


def _validate_spawn_groups(
    encounter: Mapping[str, Any],
    known_variants: Mapping[str, Mapping[str, Any]],
    label: str,
) -> None:
    groups = encounter.get("spawn_groups", ())
    if not isinstance(groups, list) or not groups:
        raise ChapterContentError(f"{label}.spawn_groups must be a non-empty list")
    seen_ids: set[str] = set()
    for group_index, group in enumerate(groups):
        group_label = f"{label}.spawn_groups[{group_index}]"
        group = _require_mapping(group, group_label)
        group_id = _require_text(group.get("id"), f"{group_label}.id")
        if group_id in seen_ids:
            raise ChapterContentError(f"{label}.spawn_groups reuses id {group_id!r}")
        seen_ids.add(group_id)
        _validate_variant_list(group.get("variants"), known_variants, f"{group_label}.variants")
        additions = group.get("player_count_additions", {})
        if not isinstance(additions, Mapping):
            raise ChapterContentError(f"{group_label}.player_count_additions must be an object")
        for player_key, extra_variants in additions.items():
            if str(player_key) not in {str(count) for count in _PLAYER_COUNTS}:
                raise ChapterContentError(f"{group_label} has an invalid player-count key {player_key!r}")
            if not isinstance(extra_variants, list):
                raise ChapterContentError(f"{group_label} additions for {player_key} must be a list")
            if extra_variants:
                _validate_variant_list(
                    extra_variants,
                    known_variants,
                    f"{group_label}.player_count_additions[{player_key!r}]",
                )


def _compile_spawn_groups(
    encounter: Mapping[str, Any],
    variants: Mapping[str, Mapping[str, Any]],
    scale: Mapping[str, Any],
) -> None:
    groups = encounter.get("spawn_groups", ())
    if not isinstance(groups, list):
        return
    for group in groups:
        if not isinstance(group, dict):
            continue
        base_ids = list(group["variants"])
        additions = group.get("player_count_additions", {}).get(str(int(scale["player_count"])), [])
        resolved_ids = [*base_ids, *additions]
        group["resolved_variant_ids"] = tuple(resolved_ids)
        group["runtime_kinds"] = tuple(str(variants[variant_id]["runtime_kind"]) for variant_id in resolved_ids)
        group["max_live_enemies"] = int(scale["max_live_enemies"])
        group["health_multiplier"] = float(scale["enemy_health_multiplier"])
        group["damage_multiplier"] = float(scale["enemy_damage_multiplier"])


def _validate_encounter(
    encounter: Any,
    known_variants: Mapping[str, Mapping[str, Any]],
    label: str,
) -> None:
    encounter = _require_mapping(encounter, label)
    _require_text(encounter.get("id"), f"{label}.id")
    _require_text(encounter.get("title"), f"{label}.title")
    _require_text(encounter.get("runtime_hook"), f"{label}.runtime_hook")
    _require_positive(encounter.get("normal_duration_seconds"), f"{label}.normal_duration_seconds")
    _require_positive(encounter.get("experienced_duration_seconds"), f"{label}.experienced_duration_seconds")
    _validate_spawn_groups(encounter, known_variants, label)


def _validate_level(
    level: Any,
    known_variants: Mapping[str, Mapping[str, Any]],
    expected_number: int,
) -> None:
    label = f"levels[{expected_number - 1}]"
    level = _require_mapping(level, label)
    if int(level.get("number", 0)) != expected_number:
        raise ChapterContentError(f"{label}.number must be {expected_number}")
    expected_id = _LEVEL_IDS[expected_number - 1]
    if _require_text(level.get("runtime_level_id"), f"{label}.runtime_level_id") != expected_id:
        raise ChapterContentError(f"{label}.runtime_level_id must be {expected_id}")
    route = _require_mapping(level.get("route"), f"{label}.route")
    _require_text(route.get("start"), f"{label}.route.start")
    _require_text(route.get("end"), f"{label}.route.end")
    stops = route.get("stops", ())
    if not isinstance(stops, list) or len(stops) < 3:
        raise ChapterContentError(f"{label}.route.stops must contain at least three ordered stops")
    if str(stops[0]) != str(route["start"]) or str(stops[-1]) != str(route["end"]):
        raise ChapterContentError(f"{label}.route.stops must begin/end at the route endpoints")

    establishing = _require_mapping(level.get("establishing_shot"), f"{label}.establishing_shot")
    _require_text(establishing.get("id"), f"{label}.establishing_shot.id")
    _require_text(establishing.get("camera_note"), f"{label}.establishing_shot.camera_note")

    major_fights = level.get("major_fights", ())
    if not isinstance(major_fights, list) or len(major_fights) < 3:
        raise ChapterContentError(f"{label}.major_fights must contain at least three major fights")
    seen_fight_ids: set[str] = set()
    for fight_index, fight in enumerate(major_fights):
        fight_label = f"{label}.major_fights[{fight_index}]"
        _validate_encounter(fight, known_variants, fight_label)
        fight_id = str(fight["id"])
        if fight_id in seen_fight_ids:
            raise ChapterContentError(f"{label}.major_fights reuses id {fight_id!r}")
        seen_fight_ids.add(fight_id)

    optional = level.get("ambush_or_optional", ())
    if not isinstance(optional, list) or not optional:
        raise ChapterContentError(f"{label}.ambush_or_optional must contain an ambush or optional encounter")
    for optional_index, encounter in enumerate(optional):
        optional_label = f"{label}.ambush_or_optional[{optional_index}]"
        _validate_encounter(encounter, known_variants, optional_label)
        encounter_map = _require_mapping(encounter, optional_label)
        _require_text(encounter_map.get("branch_type"), f"{optional_label}.branch_type")
        _require_text(encounter_map.get("reward"), f"{optional_label}.reward")
        _require_text(encounter_map.get("risk"), f"{optional_label}.risk")

    environmental_events = level.get("environmental_events", ())
    if not isinstance(environmental_events, list) or not environmental_events:
        raise ChapterContentError(f"{label}.environmental_events must contain at least one authored beat")
    for index, entry in enumerate(environmental_events):
        entry_label = f"{label}.environmental_events[{index}]"
        entry = _require_mapping(entry, entry_label)
        _require_text(entry.get("id"), f"{entry_label}.id")
        _require_text(entry.get("description"), f"{entry_label}.description")
        if entry.get("spawn_groups") is not None:
            _validate_spawn_groups(entry, known_variants, entry_label)

    for field in ("story_beats", "landmark_set_pieces", "traversal_gaps"):
        entries = level.get(field, ())
        if not isinstance(entries, list) or not entries:
            raise ChapterContentError(f"{label}.{field} must contain at least one authored beat")
        for index, entry in enumerate(entries):
            entry_label = f"{label}.{field}[{index}]"
            entry = _require_mapping(entry, entry_label)
            _require_text(entry.get("id"), f"{entry_label}.id")
            _require_text(entry.get("description"), f"{entry_label}.description")

    ending = _require_mapping(level.get("ending"), f"{label}.ending")
    _require_text(ending.get("id"), f"{label}.ending.id")
    _require_text(ending.get("visual"), f"{label}.ending.visual")
    _require_text(ending.get("narrative"), f"{label}.ending.narrative")
    checkpoints = level.get("checkpoints", ())
    if not isinstance(checkpoints, list) or len(checkpoints) < 3:
        raise ChapterContentError(f"{label}.checkpoints must contain start, mid-level, and finish checkpoints")
    if len({str(checkpoint) for checkpoint in checkpoints}) != len(checkpoints):
        raise ChapterContentError(f"{label}.checkpoints must be unique")


def _validate_pacing(data: Mapping[str, Any]) -> None:
    pacing = _require_mapping(data.get("pacing"), "pacing")
    targets = _require_mapping(pacing.get("targets"), "pacing.targets")
    ranges = {
        "normal": (45.0, 60.0),
        "experienced": (30.0, 40.0),
    }
    for name, expected in ranges.items():
        supplied = targets.get(f"{name}_minutes", ())
        if not isinstance(supplied, list) or len(supplied) != 2:
            raise ChapterContentError(f"pacing.targets.{name}_minutes must be a two-value range")
        if tuple(float(value) for value in supplied) != expected:
            raise ChapterContentError(f"pacing.targets.{name}_minutes must be {list(expected)}")
    if float(targets.get("minimum_minutes", 0)) < 35.0:
        raise ChapterContentError("pacing.targets.minimum_minutes must be at least 35")
    travel_range = targets.get("normal_travel_dialogue_minutes", ())
    if not isinstance(travel_range, list) or tuple(float(value) for value in travel_range) != (4.0, 7.0):
        raise ChapterContentError("pacing.targets.normal_travel_dialogue_minutes must be [4, 7]")
    level_targets = _require_mapping(targets.get("level_target_minutes"), "pacing.targets.level_target_minutes")
    expected_level_ranges = {
        "chapter_1_level_1": (10.0, 13.0),
        "chapter_1_level_2": (10.0, 13.0),
        "chapter_1_level_3": (12.0, 15.0),
        "chapter_1_level_4": (10.0, 15.0),
    }
    if tuple(level_targets.keys()) != _LEVEL_IDS:
        raise ChapterContentError("pacing.targets.level_target_minutes must follow Chapter 1 route order")
    for level_id, expected in expected_level_ranges.items():
        supplied = level_targets[level_id]
        if not isinstance(supplied, list) or tuple(float(value) for value in supplied) != expected:
            raise ChapterContentError(
                f"pacing.targets.level_target_minutes[{level_id!r}] must be {list(expected)}"
            )

    profiles = _require_mapping(pacing.get("profiles"), "pacing.profiles")
    if tuple(profiles.keys()) != _PROFILE_NAMES:
        raise ChapterContentError(f"pacing.profiles must be ordered as {list(_PROFILE_NAMES)}")
    for name in _PROFILE_NAMES:
        profile = pace_profile(data, name)
        if set(level_id for level_id, _ in profile.level_minutes) != set(_LEVEL_IDS):
            raise ChapterContentError(f"pacing profile {name} must budget every Chapter 1 level")
        if any(minutes <= 0 for _, minutes in profile.level_minutes):
            raise ChapterContentError(f"pacing profile {name} level minutes must be positive")
        if profile.travel_dialogue_minutes <= 0:
            raise ChapterContentError(f"pacing profile {name} travel/dialogue minutes must be positive")

    normal = pace_profile(data, "normal")
    experienced = pace_profile(data, "experienced")
    minimum = pace_profile(data, "minimum")
    normal_range = tuple(float(value) for value in targets["normal_minutes"])
    experienced_range = tuple(float(value) for value in targets["experienced_minutes"])
    if not normal_range[0] <= normal.total_minutes <= normal_range[1]:
        raise ChapterContentError("normal pacing profile misses the 45-60 minute target")
    if not experienced_range[0] <= experienced.total_minutes <= experienced_range[1]:
        raise ChapterContentError("experienced pacing profile misses the 30-40 minute target")
    if minimum.total_minutes < float(targets["minimum_minutes"]):
        raise ChapterContentError("minimum pacing profile falls below the 35-minute hard floor")
    for level_id, expected in expected_level_ranges.items():
        normal_minutes = normal.minutes_for_level(level_id)
        if not expected[0] <= normal_minutes <= expected[1]:
            raise ChapterContentError(f"normal pacing for {level_id} misses its authored target range")
    if not float(targets["normal_travel_dialogue_minutes"][0]) <= normal.travel_dialogue_minutes <= float(
        targets["normal_travel_dialogue_minutes"][1]
    ):
        raise ChapterContentError("normal travel/dialogue pacing must stay between 4 and 7 minutes")


def _validate_couch_contract(data: Mapping[str, Any], known_variants: Mapping[str, Mapping[str, Any]]) -> None:
    contract = _require_mapping(data.get("couch_boss_contract"), "couch_boss_contract")
    if _require_text(contract.get("runtime_level_id"), "couch_boss_contract.runtime_level_id") != _LEVEL_IDS[-1]:
        raise ChapterContentError("Couch content must belong to the Level 4 finale")
    if _require_text(contract.get("boss_variant"), "couch_boss_contract.boss_variant") != "couch":
        raise ChapterContentError("couch_boss_contract.boss_variant must be couch")
    refuge = _require_mapping(contract.get("bike_refuge"), "couch_boss_contract.bike_refuge")
    if float(refuge.get("x", -1)) != 1080.0:
        raise ChapterContentError("Couch bike refuge must use the authored BMX x=1080 anchor")
    _require_positive(refuge.get("jump_height"), "couch_boss_contract.bike_refuge.jump_height")
    phases = contract.get("phases", ())
    if not isinstance(phases, list) or len(phases) != 3:
        raise ChapterContentError("Couch requires exactly three combat phases")
    expected_gates = (1.0, 0.67, 0.34)
    for index, phase in enumerate(phases):
        label = f"couch_boss_contract.phases[{index}]"
        phase = _require_mapping(phase, label)
        _require_text(phase.get("id"), f"{label}.id")
        if abs(float(phase.get("starts_at_health_ratio", -1)) - expected_gates[index]) > 0.001:
            raise ChapterContentError(f"{label}.starts_at_health_ratio must be {expected_gates[index]:g}")
        _require_text(phase.get("objective"), f"{label}.objective")
        if index == 0:
            if phase.get("retreat") is not None:
                raise ChapterContentError("Couch phase one must begin targetable in the front lot")
            continue
        retreat = _require_mapping(phase.get("retreat"), f"{label}.retreat")
        if _require_text(retreat.get("destination"), f"{label}.retreat.destination") != "daves_bmx":
            raise ChapterContentError(f"{label}.retreat.destination must be daves_bmx")
        if _require_text(retreat.get("taunt"), f"{label}.retreat.taunt") != "I'LL GIVE YOU DOPE IF YOU BEAT THEM UP!":
            raise ChapterContentError(f"{label}.retreat.taunt must preserve the authored Couch line")
        reinforcements = retreat.get("reinforcement_variants", ())
        _validate_variant_list(reinforcements, known_variants, f"{label}.retreat.reinforcement_variants")
        if any(known_variants[str(variant)]["runtime_kind"] in {"couch", "security", "police"} for variant in reinforcements):
            raise ChapterContentError(f"{label}.retreat reinforcements must be fictional road-raider crew variants")
        additions = retreat.get("player_count_additions", {})
        if not isinstance(additions, Mapping):
            raise ChapterContentError(f"{label}.retreat.player_count_additions must be an object")
        for player_key, extra_variants in additions.items():
            if str(player_key) not in {str(count) for count in _PLAYER_COUNTS}:
                raise ChapterContentError(f"{label}.retreat has an invalid player-count key {player_key!r}")
            if not isinstance(extra_variants, list):
                raise ChapterContentError(f"{label}.retreat additions for {player_key} must be a list")
            if extra_variants:
                _validate_variant_list(extra_variants, known_variants, f"{label}.retreat.player_count_additions")
            if any(known_variants[str(variant)]["runtime_kind"] in {"couch", "security", "police"} for variant in extra_variants):
                raise ChapterContentError(f"{label}.retreat additions must be fictional road-raider crew variants")
        if not bool(retreat.get("returns_targetable_after_clear", False)):
            raise ChapterContentError(f"{label}.retreat must restore Couch targetability after the crew is cleared")


def validate_chapter_content(
    data: dict[str, Any],
    *,
    gameplay: Mapping[str, Any] | None = None,
    location_manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate every production requirement needed by the runtime hook."""

    if not isinstance(data, dict):
        raise ChapterContentError("Chapter content root must be an object")
    if int(data.get("schema_version", 0)) != 1:
        raise ChapterContentError("chapter_content.schema_version must be 1")
    chapter = _require_mapping(data.get("chapter"), "chapter")
    if _require_text(chapter.get("id"), "chapter.id") != "chapter_1":
        raise ChapterContentError("chapter.id must be chapter_1")
    _require_text(chapter.get("title"), "chapter.title")
    if _require_text(chapter.get("direction"), "chapter.direction") != "northbound":
        raise ChapterContentError("Chapter 1 content must retain northbound route direction")
    if _require_text(chapter.get("playable_side"), "chapter.playable_side") != "west_even_address_side":
        raise ChapterContentError("Chapter 1 content must retain the west/even-address playable side")

    variants = data.get("enemy_variants", ())
    if not isinstance(variants, list) or len(variants) < 6:
        raise ChapterContentError("enemy_variants must define the complete street roster")
    known_variants: dict[str, Mapping[str, Any]] = {}
    for index, variant in enumerate(variants):
        label = f"enemy_variants[{index}]"
        variant = _require_mapping(variant, label)
        variant_id = _require_text(variant.get("id"), f"{label}.id")
        if variant_id in known_variants:
            raise ChapterContentError(f"enemy_variants reuses id {variant_id!r}")
        runtime_kind = _require_text(variant.get("runtime_kind"), f"{label}.runtime_kind")
        if runtime_kind not in _RUNTIME_ENEMY_KINDS:
            raise ChapterContentError(f"{label}.runtime_kind is not supported by the enemy factory")
        allowed_attack_styles = _VARIANT_ATTACK_STYLES.get(runtime_kind)
        attack_style = str(variant.get("attack_style", "")).strip()
        if allowed_attack_styles is not None and attack_style and attack_style not in allowed_attack_styles:
            allowed = ", ".join(sorted(allowed_attack_styles))
            raise ChapterContentError(f"{label}.attack_style must be one of: {allowed}")
        if "display_name" in variant:
            _require_text(variant.get("display_name"), f"{label}.display_name")
        _require_text(variant.get("fictional_role"), f"{label}.fictional_role")
        known_variants[variant_id] = variant

    scaling = _require_mapping(data.get("player_count_scaling"), "player_count_scaling")
    if tuple(scaling.keys()) != tuple(str(count) for count in _PLAYER_COUNTS):
        raise ChapterContentError("player_count_scaling must be ordered 1 through 4")
    last_cap = 0
    for count in _PLAYER_COUNTS:
        label = f"player_count_scaling[{count!r}]"
        entry = _require_mapping(scaling[str(count)], label)
        cap = int(entry.get("max_live_enemies", 0))
        if cap < 3 or cap < last_cap:
            raise ChapterContentError("player-count max_live_enemies must be nondecreasing and at least three")
        last_cap = cap
        for field in ("enemy_health_multiplier", "enemy_damage_multiplier", "reward_multiplier"):
            _require_positive(entry.get(field), f"{label}.{field}")

    levels = chapter_levels(data)
    if len(levels) != len(_LEVEL_IDS):
        raise ChapterContentError("Chapter 1 content requires exactly four ordered levels")
    for number, level in enumerate(levels, start=1):
        _validate_level(level, known_variants, number)

    travel = data.get("inter_level_travel", ())
    if not isinstance(travel, list) or len(travel) != 3:
        raise ChapterContentError("inter_level_travel must contain all three route handoffs")
    for index, handoff in enumerate(travel):
        label = f"inter_level_travel[{index}]"
        handoff = _require_mapping(handoff, label)
        if _require_text(handoff.get("from_level_id"), f"{label}.from_level_id") != _LEVEL_IDS[index]:
            raise ChapterContentError(f"{label}.from_level_id breaks Chapter 1 route order")
        if _require_text(handoff.get("to_level_id"), f"{label}.to_level_id") != _LEVEL_IDS[index + 1]:
            raise ChapterContentError(f"{label}.to_level_id breaks Chapter 1 route order")
        _require_text(handoff.get("heading"), f"{label}.heading")
        beats = handoff.get("beats", ())
        if not isinstance(beats, list) or not beats:
            raise ChapterContentError(f"{label}.beats must contain travel storytelling")
        travel_copy = " ".join(str(beat) for beat in beats).lower()
        if index == 1 and not ("690" in travel_copy and "fuel" in travel_copy):
            raise ChapterContentError("I-8 to Soapy Joe's handoff must cover the 690 showroom and fuel corridor")

    _validate_pacing(data)
    _validate_couch_contract(data, known_variants)

    if gameplay is not None:
        gameplay_enemy_kinds = {
            str(kind).strip() for kind in gameplay.get("enemies", {}) if str(kind).strip()
        }
        missing_runtime_kinds = {
            str(variant["runtime_kind"])
            for variant in known_variants.values()
            if str(variant["runtime_kind"]) not in gameplay_enemy_kinds
        }
        if missing_runtime_kinds:
            raise ChapterContentError(
                "gameplay enemies are missing authored runtime kinds: "
                + ", ".join(sorted(missing_runtime_kinds))
            )
        runtime_ids = tuple(str(level.get("id", "")) for level in campaign_levels(dict(gameplay)))
        if runtime_ids[: len(_LEVEL_IDS)] != _LEVEL_IDS:
            raise ChapterContentError("gameplay campaign no longer matches the Chapter 1 content route")
    try:
        if location_manifest is None:
            manifest_path = resource_path("data/chapter1_location_lock.json")
            location_manifest = load_location_lock(
                manifest_path,
                project_root=manifest_path.parent.parent,
                validate_assets=True,
            )
        validate_chapter_content_locations(
            data,
            location_manifest,
            gameplay=gameplay,
        )
    except LocationLockError as exc:
        raise ChapterContentError(f"Chapter 1 location lock: {exc}") from exc
    return data
