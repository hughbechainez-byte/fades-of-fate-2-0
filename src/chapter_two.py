from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


CHAPTER_ONE_LEVEL_IDS = (
    "chapter_1_level_1",
    "chapter_1_level_2",
    "chapter_1_level_3",
    "chapter_1_level_4",
)

CHAPTER_TWO_LEVEL_IDS = (
    "chapter_2_level_1",
    "chapter_2_level_2",
    "chapter_2_level_3",
    "chapter_2_level_4",
)

CHAPTER_TWO_LEVEL_TITLES = (
    "Bostonia Post Office to I-8 Underpass",
    "I-8 Underpass to Broadway",
    "Broadway to the Promenade",
    "Promenade Showdown",
)

CHAPTER_TWO_ROUTE_STARTS = (
    "Bostonia Post Office",
    "I-8 Underpass",
    "Broadway",
    "Promenade Lot",
)

CHAPTER_TWO_ROUTE_ENDS = (
    "I-8 Underpass",
    "Broadway",
    "Promenade Approach",
    "Promenade Showdown",
)

CHAPTER_TWO_ROUTE_HEADINGS = (
    "BOSTONIA TO I-8",
    "I-8 TO BROADWAY",
    "BROADWAY TO THE PROMENADE",
    "PROMENADE SHOWDOWN",
)

CHAPTER_TWO_ROUTE_DETAILS = (
    "THE PARTY ROLLS SOUTH PAST THE POST OFFICE AND BACK TOWARD THE UNDERPASS.",
    "THE GROUP PUSHES PAST THE RAMP SHADOWS AND INTO THE EAST-SIDE SERVICE ROW.",
    "THE ROUTE KEEPS DESCENDING TOWARD THE PROMENADE FRONTAGE AND LOTS.",
    "DEBO HOLDS THE PROMENADE BLOCK AS THE PARTY PUSHES THROUGH.",
)

CHAPTER_TWO_BOSS_KIND = "debo"

_BASE_LEVEL_INDEX = (1, 2, 0, 3)
_CHAPTER_TWO_ROUTE_LANDMARK_COUNTS = (7, 7, 7, 4)


def chapter_two_level_id(index: int) -> str:
    return CHAPTER_TWO_LEVEL_IDS[index - 1]


def chapter_two_level_title(index: int) -> str:
    return CHAPTER_TWO_LEVEL_TITLES[index - 1]


def chapter_two_route_name(index: int, *, start: bool) -> str:
    return (CHAPTER_TWO_ROUTE_STARTS if start else CHAPTER_TWO_ROUTE_ENDS)[index - 1]


def chapter_two_level_index(level_id: str) -> int | None:
    target = str(level_id).strip()
    if target in CHAPTER_TWO_LEVEL_IDS:
        return CHAPTER_TWO_LEVEL_IDS.index(target) + 1
    return None


def chapter_two_is_level(level_id: str) -> bool:
    return chapter_two_level_index(level_id) is not None


def chapter_two_base_level_index(level_number: int) -> int:
    return _BASE_LEVEL_INDEX[level_number - 1] + 1


def _clone_route(base_route: Mapping[str, Any], level_number: int) -> dict[str, Any]:
    route = deepcopy(dict(base_route))
    prefix = f"c2_l{level_number}"
    route["level_id"] = chapter_two_level_id(level_number)
    route["travel_direction"] = "southbound"
    route["playable_side"] = "east_odd"
    route["theme"] = str(route.get("theme", "chapter_1_sunset"))
    landmarks = deepcopy(route.get("landmarks", []))
    for index, landmark in enumerate(landmarks):
        landmark["id"] = f"{prefix}_lm_{index + 1}"
        landmark["street_side"] = "east"
    if landmarks:
        landmarks[0]["display_name"] = chapter_two_route_name(level_number, start=True)
        landmarks[-1]["display_name"] = chapter_two_route_name(level_number, start=False)
    route["landmarks"] = landmarks

    opposite = deepcopy(route.get("opposite_side_landmarks", []))
    for index, landmark in enumerate(opposite):
        landmark["id"] = f"{prefix}_opp_{index + 1}"
        landmark["street_side"] = "west"
    route["opposite_side_landmarks"] = opposite

    features = deepcopy(route.get("registered_features", []))
    for index, feature in enumerate(features):
        feature["id"] = f"{prefix}_feat_{index + 1}"
    route["registered_features"] = features

    objects = deepcopy(route.get("physical_scene_objects", []))
    for index, feature in enumerate(objects):
        feature["id"] = f"{prefix}_obj_{index + 1}"
    route["physical_scene_objects"] = objects

    if route.get("start_anchor_id") and landmarks:
        route["start_anchor_id"] = str(landmarks[0]["id"])
    if route.get("end_anchor_id") and landmarks:
        route["end_anchor_id"] = str(landmarks[-1]["id"])
    return route


def chapter_two_location_routes(base_manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    routes = [deepcopy(route) for route in base_manifest.get("routes", ()) if isinstance(route, Mapping)]
    if any(str(route.get("level_id", "")).startswith("chapter_2_") for route in routes):
        return [dict(route) for route in routes]
    chapter1_routes = [route for route in routes if str(route.get("level_id", "")).startswith("chapter_1_")]
    for level_number, base_index in enumerate(_BASE_LEVEL_INDEX, start=1):
        base_route = chapter1_routes[base_index]
        routes.append(_clone_route(base_route, level_number))
    return routes


def chapter_two_travel_panels(base_manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    panels = [deepcopy(panel) for panel in base_manifest.get("travel_panels", ()) if isinstance(panel, Mapping)]
    if any(str(panel.get("from_level_id", "")).startswith("chapter_2_") for panel in panels):
        return [dict(panel) for panel in panels]
    chapter2_pairs = [
        ("chapter_1_level_4", "chapter_2_level_1", "chapter_2_to_bostonia"),
        ("chapter_2_level_1", "chapter_2_level_2", "chapter_2_bostonia_to_broadway"),
        ("chapter_2_level_2", "chapter_2_level_3", "chapter_2_broadway_to_promenade"),
        ("chapter_2_level_3", "chapter_2_level_4", "chapter_2_promenade_to_boss"),
    ]
    for index, (from_level, to_level, panel_id) in enumerate(chapter2_pairs):
        panel = deepcopy(panels[min(index, len(panels) - 1)])
        panel["id"] = panel_id
        panel["from_level_id"] = from_level
        panel["to_level_id"] = to_level
        panel["heading"] = (
            "CHAPTER 2 - EAST SIDE SOUTHBOUND"
            if index == 0
            else CHAPTER_TWO_ROUTE_HEADINGS[index]
        )
        if panel.get("waypoints"):
            panel["waypoints"] = deepcopy(panel["waypoints"])
            panel["waypoints"][0]["display_name"] = CHAPTER_TWO_ROUTE_STARTS[index]
            panel["waypoints"][-1]["display_name"] = CHAPTER_TWO_ROUTE_ENDS[index]
        panels.append(panel)
    return panels


def chapter_two_gameplay_levels(base_gameplay: Mapping[str, Any]) -> list[dict[str, Any]]:
    chapters = base_gameplay.get("campaign", {}).get("chapters", ())
    chapter1 = next((chapter for chapter in chapters if str(chapter.get("id", "")) == "chapter_1"), None)
    if chapter1 is None:
        return []
    levels = [deepcopy(level) for level in chapter1.get("levels", ()) if isinstance(level, Mapping)]
    if any(str(level.get("id", "")).startswith("chapter_2_") for level in levels):
        return [dict(level) for level in levels]
    chapter2_levels: list[dict[str, Any]] = []
    for level_number, base_index in enumerate(_BASE_LEVEL_INDEX, start=1):
        base_level = deepcopy(levels[base_index])
        base_level["id"] = chapter_two_level_id(level_number)
        base_level["number"] = level_number + 4
        base_level["title"] = chapter_two_level_title(level_number)
        base_level["chapter_id"] = "chapter_2"
        base_level["chapter_number"] = 2
        base_level["status"] = "playable"
        base_level["boss"] = CHAPTER_TWO_BOSS_KIND if level_number == 4 else None
        base_level["boss_transition"] = level_number == 4
        base_level["chapter_finale"] = level_number == 4
        if level_number == 2:
            base_level["outro"] = "wheelchair_chris"
        base_level["travel_to_next"] = (
            {
                "heading": CHAPTER_TWO_ROUTE_HEADINGS[level_number - 1],
                "detail": CHAPTER_TWO_ROUTE_DETAILS[level_number - 1],
            }
            if level_number < 4
            else base_level.get("travel_to_next")
        )
        if level_number == 4 and base_level.get("encounters"):
            first = deepcopy(base_level["encounters"][0])
            first["name"] = "Promenade Intercept"
            boss = deepcopy(base_level["encounters"][-1])
            boss["name"] = "DeBo at the Promenade"
            boss["base"] = [CHAPTER_TWO_BOSS_KIND]
            base_level["encounters"] = [first, boss]
        elif level_number == 1:
            names = (
                "Bostonia Post Office Front Lot",
                "Bank of America Row",
                "I-8 Underpass",
            )
            base_level["encounters"] = [
                {**deepcopy(encounter), "name": name}
                for encounter, name in zip(base_level.get("encounters", ()), names)
            ]
        elif level_number == 2:
            names = (
                "I-8 Underpass Cut",
                "Broadway Ramp",
                "Promenade Edge",
            )
            base_level["encounters"] = [
                {**deepcopy(encounter), "name": name}
                for encounter, name in zip(base_level.get("encounters", ()), names)
            ]
        else:
            names = (
                "Broadway Service Row",
                "Promenade Approach",
                "Promenade Cut",
            )
            base_level["encounters"] = [
                {**deepcopy(encounter), "name": name}
                for encounter, name in zip(base_level.get("encounters", ()), names)
            ]
        chapter2_levels.append(base_level)
    return [*levels, *chapter2_levels]


def chapter_two_chapter_content_levels(base_content: Mapping[str, Any]) -> list[dict[str, Any]]:
    levels = [deepcopy(level) for level in base_content.get("levels", ()) if isinstance(level, Mapping)]
    if any(str(level.get("runtime_level_id", "")).startswith("chapter_2_") for level in levels):
        return [dict(level) for level in levels]
    chapter2: list[dict[str, Any]] = []
    for level_number, base_index in enumerate(_BASE_LEVEL_INDEX, start=1):
        base_level = deepcopy(levels[base_index])
        base_level["number"] = level_number + 4
        base_level["runtime_level_id"] = chapter_two_level_id(level_number)
        route = deepcopy(base_level.get("route", {}))
        route["start_anchor_id"] = f"c2_l{level_number}_lm_1"
        route["end_anchor_id"] = f"c2_l{level_number}_lm_{_CHAPTER_TWO_ROUTE_LANDMARK_COUNTS[level_number - 1]}"
        route["start"] = CHAPTER_TWO_ROUTE_STARTS[level_number - 1]
        route["end"] = CHAPTER_TWO_ROUTE_ENDS[level_number - 1]
        if route.get("stops"):
            route["stops"] = list(route["stops"])
            route["stops"][0] = CHAPTER_TWO_ROUTE_STARTS[level_number - 1]
            route["stops"][-1] = CHAPTER_TWO_ROUTE_ENDS[level_number - 1]
        base_level["route"] = route
        if level_number == 2:
            base_level["outro"] = "wheelchair_chris"
        chapter2.append(base_level)
    return [*levels, *chapter2]
