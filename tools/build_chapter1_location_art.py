"""Build the final, location-locked Chapter 1 pixel panoramas.

The shipped images are deterministic, fully precomposed world strips.  The
original concept plates are used as visual material, then the route-specific
road, lot, intersection, infrastructure, and story anchors are registered at
their manifest coordinates.  Runtime never tiles or slides building panels.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import pygame


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "stage" / "chapter1_location_locked"
CONCEPTS = OUT / "source_concepts"
HEIGHT = 360
INK = (22, 24, 30)
ROAD = (45, 48, 55)
ROAD_EDGE = (194, 185, 163)
LOT_LINE = (218, 207, 180)
WARM_WHITE = (245, 225, 180)

CONCEPT_FILES = {
    "sprouts_el_cilantro": "chapter1_level1_source_concept.png",
    "seven_eleven_underpass": "chapter1_level2_source_concept.png",
    "soapy_joes_revive": "chapter1_level3_source_concept.png",
    "awaken_church_finale": "chapter1_level4_source_concept.png",
}

# Remove excess sky and the very closest foreground while retaining the
# authored massing, parking depth, and cross-street geometry.
CONCEPT_CROPS = {
    "sprouts_el_cilantro": (0.13, 0.91),
    "seven_eleven_underpass": (0.10, 0.90),
    "soapy_joes_revive": (0.12, 0.91),
    "awaken_church_finale": (0.08, 0.90),
}

ROUTE_ACCENTS = {
    "sprouts_el_cilantro": (91, 145, 101),
    "seven_eleven_underpass": (207, 100, 64),
    "soapy_joes_revive": (41, 146, 211),
    "awaken_church_finale": (203, 118, 73),
}

ART_LABELS = {
    "sprouts_parking_lot": "FRESH MARKET",
    "wells_fargo_pad": "BANK PAD",
    "walmart_neighborhood_market": "NEIGHBORHOOD MARKET",
    "town_country": "TOWN & COUNTRY",
    "goodwill_frontage": "THRIFT FRONTAGE",
    "madison_intersection": "MADISON AVE",
    "el_cilantro_madison": "MADISON CORNER",
    "seven_eleven_pad": "FUEL + MARKET",
    "carls_jr_pad": "DRIVE-THRU PAD",
    "madison_plaza": "MADISON PLAZA",
    "former_union_bank": "FORMER BANK",
    "valvoline": "SERVICE BAYS",
    "freeway_approach": "I-8 APPROACH",
    "i8_underpass": "I-8 UNDERPASS",
    "soapy_joes": "EXPRESS WASH",
    "starbucks_pad": "COFFEE DRIVE-THRU",
    "marechiaro": "ITALIAN KITCHEN",
    "carls_boot_leather": "BOOT + LEATHER",
    "cvs_broadway_corner": "PHARMACY CORNER",
    "broadway_turn": "BROADWAY  \u2190 WEST",
    "revive_pathway": "REVIVE PATHWAY",
    "awaken_church_lot": "950 N 2ND",
    "awaken_facade": "AWAKEN CAMPUS",
    "awaken_front_lot": "FRONT LOT",
    "daves_bmx": "DAVE'S BMX",
}


def _font(size: int, *, bold: bool = False) -> pygame.font.Font:
    font = pygame.font.Font(None, size)
    font.set_bold(bold)
    return font


def _text(
    surface: pygame.Surface,
    label: str,
    x: int,
    y: int,
    *,
    size: int = 15,
    color: tuple[int, int, int] = WARM_WHITE,
    bold: bool = True,
) -> pygame.Rect:
    image = _font(size, bold=bold).render(label, False, color)
    rect = image.get_rect(topleft=(int(x), int(y)))
    surface.blit(image, rect)
    return rect


def _alpha_rect(
    surface: pygame.Surface,
    color: tuple[int, int, int, int],
    rect: pygame.Rect | tuple[int, int, int, int],
) -> None:
    overlay = pygame.Surface((int(rect[2]), int(rect[3])), pygame.SRCALPHA)
    overlay.fill(color)
    surface.blit(overlay, (int(rect[0]), int(rect[1])))


def _concept_panorama(route: Mapping[str, Any]) -> pygame.Surface:
    theme = str(route["theme"])
    source_path = CONCEPTS / CONCEPT_FILES[theme]
    if not source_path.is_file():
        raise FileNotFoundError(f"missing original Chapter 1 concept plate: {source_path}")
    source = pygame.image.load(str(source_path)).convert()
    top_ratio, bottom_ratio = CONCEPT_CROPS[theme]
    top = round(source.get_height() * top_ratio)
    bottom = round(source.get_height() * bottom_ratio)
    crop_rect = pygame.Rect(0, top, source.get_width(), max(1, bottom - top))
    crop = pygame.Surface(crop_rect.size).convert()
    crop.blit(source, (0, 0), crop_rect)

    # Author at half logical resolution and nearest-scale exactly once.  This
    # makes a coherent 2x pixel grid while widening real parking intervals for
    # combat without repeating any part of the source plate.
    width = int(route["world_width"])
    low = pygame.transform.scale(crop, (max(1, width // 2), HEIGHT // 2))
    panorama = pygame.transform.scale(low, (width, HEIGHT)).convert()
    if panorama.get_size() != (width, HEIGHT):
        raise RuntimeError(f"failed to precompose {theme} at {(width, HEIGHT)}")
    return panorama


def _landmark(route: Mapping[str, Any], landmark_id: str) -> Mapping[str, Any]:
    for entry in route["landmarks"]:
        if entry["id"] == landmark_id:
            return entry
    raise KeyError(f"{route['level_id']} has no landmark {landmark_id!r}")


def _x(route: Mapping[str, Any], landmark_id: str) -> int:
    return int(_landmark(route, landmark_id)["world_x"])


def _draw_car(
    surface: pygame.Surface,
    x: int,
    y: int,
    color: tuple[int, int, int],
    *,
    facing: int = 1,
    scale: int = 1,
) -> None:
    width = 30 * scale
    pygame.draw.rect(surface, INK, (x, y + 8 * scale, width, 9 * scale))
    pygame.draw.polygon(
        surface,
        color,
        [
            (x + 2 * scale, y + 8 * scale),
            (x + 8 * scale, y + 2 * scale),
            (x + 22 * scale, y + 2 * scale),
            (x + 28 * scale, y + 8 * scale),
            (x + 27 * scale, y + 14 * scale),
            (x + 3 * scale, y + 14 * scale),
        ],
    )
    glass = (90, 119, 133)
    if facing > 0:
        pygame.draw.rect(surface, glass, (x + 15 * scale, y + 4 * scale, 8 * scale, 4 * scale))
    else:
        pygame.draw.rect(surface, glass, (x + 7 * scale, y + 4 * scale, 8 * scale, 4 * scale))
    for wheel_x in (x + 7 * scale, x + 23 * scale):
        pygame.draw.circle(surface, (25, 25, 29), (wheel_x, y + 16 * scale), 3 * scale)
        pygame.draw.circle(surface, (128, 126, 121), (wheel_x, y + 16 * scale), scale)


def _draw_palm(surface: pygame.Surface, x: int, base_y: int, height: int = 74) -> None:
    trunk = (101, 72, 47)
    pygame.draw.polygon(
        surface,
        trunk,
        [(x - 3, base_y), (x + 4, base_y), (x + 2, base_y - height), (x - 1, base_y - height)],
    )
    crown_y = base_y - height
    leaf = (42, 88, 56)
    for dx, dy in ((-30, 4), (-23, -8), (-12, -14), (12, -14), (24, -8), (31, 4)):
        pygame.draw.line(surface, leaf, (x, crown_y), (x + dx, crown_y + dy), 6)
        pygame.draw.line(surface, (74, 113, 61), (x, crown_y), (x + dx, crown_y + dy), 2)


def _draw_light_pole(surface: pygame.Surface, x: int, base_y: int = 286) -> None:
    pygame.draw.rect(surface, (37, 40, 43), (x - 2, base_y - 105, 5, 105))
    pygame.draw.rect(surface, (37, 40, 43), (x - 17, base_y - 108, 34, 5))
    pygame.draw.rect(surface, (238, 214, 150), (x - 15, base_y - 106, 11, 2))
    pygame.draw.rect(surface, (238, 214, 150), (x + 4, base_y - 106, 11, 2))
    pygame.draw.rect(surface, (104, 101, 94), (x - 8, base_y - 3, 16, 4))


def _draw_planter(surface: pygame.Surface, x: int, y: int, width: int = 86) -> None:
    pygame.draw.ellipse(surface, (34, 29, 29), (x - width // 2 + 3, y + 7, width, 11))
    pygame.draw.rect(surface, (192, 177, 148), (x - width // 2, y, width, 12))
    pygame.draw.rect(surface, (142, 125, 98), (x - width // 2 + 4, y + 4, width - 8, 8))
    for offset, height in ((-26, 13), (-9, 19), (10, 15), (27, 11)):
        pygame.draw.line(surface, (57, 104, 61), (x + offset, y + 3), (x + offset - 4, y - height), 4)
        pygame.draw.line(surface, (87, 129, 70), (x + offset, y + 1), (x + offset + 5, y - height + 4), 3)


def _draw_cart_corral(surface: pygame.Surface, x: int, y: int = 267) -> None:
    pygame.draw.rect(surface, (44, 52, 56), (x - 31, y - 4, 62, 28), 3)
    pygame.draw.arc(surface, (57, 128, 105), (x - 33, y - 20, 66, 35), 3.14, 6.28, 4)
    for cart_x in range(x - 23, x + 21, 11):
        pygame.draw.line(surface, (170, 177, 174), (cart_x, y + 3), (cart_x + 8, y + 15), 2)
        pygame.draw.circle(surface, (44, 45, 48), (cart_x + 2, y + 18), 2)
        pygame.draw.circle(surface, (44, 45, 48), (cart_x + 9, y + 18), 2)


def _draw_bmx(surface: pygame.Surface, x: int, ground_y: int = 302) -> None:
    wheel = (27, 28, 34)
    metal = (218, 117, 61)
    pygame.draw.circle(surface, wheel, (x - 23, ground_y - 15), 15, 3)
    pygame.draw.circle(surface, wheel, (x + 25, ground_y - 15), 15, 3)
    pygame.draw.line(surface, metal, (x - 23, ground_y - 15), (x, ground_y - 34), 4)
    pygame.draw.line(surface, metal, (x, ground_y - 34), (x + 25, ground_y - 15), 4)
    pygame.draw.line(surface, metal, (x - 23, ground_y - 15), (x + 5, ground_y - 15), 3)
    pygame.draw.line(surface, metal, (x + 5, ground_y - 15), (x, ground_y - 34), 3)
    pygame.draw.line(surface, metal, (x, ground_y - 34), (x + 10, ground_y - 46), 3)
    pygame.draw.line(surface, metal, (x + 7, ground_y - 46), (x + 20, ground_y - 46), 2)
    pygame.draw.line(surface, metal, (x - 4, ground_y - 36), (x - 17, ground_y - 39), 3)


def _draw_driveway(surface: pygame.Surface, x: int, *, width: int = 82) -> None:
    pygame.draw.polygon(
        surface,
        (53, 55, 59),
        [(x - width // 3, 212), (x + width // 3, 212), (x + width // 2, 360), (x - width // 2, 360)],
    )
    pygame.draw.line(surface, ROAD_EDGE, (x - width // 3, 212), (x - width // 2, 360), 3)
    pygame.draw.line(surface, ROAD_EDGE, (x + width // 3, 212), (x + width // 2, 360), 3)


def _draw_parking_stripes(
    surface: pygame.Surface,
    start: int,
    end: int,
    *,
    y: int = 282,
    spacing: int = 68,
    reverse: bool = False,
) -> None:
    for stripe_x in range(start + 22, end - 10, spacing):
        slant = -28 if reverse else 28
        pygame.draw.line(surface, LOT_LINE, (stripe_x, y), (stripe_x + slant, y + 56), 2)
        pygame.draw.rect(surface, (170, 166, 150), (stripe_x + slant - 9, y + 51, 31, 5))


def _draw_route_road(surface: pygame.Surface, route: Mapping[str, Any]) -> None:
    width = int(route["world_width"])
    _alpha_rect(surface, (30, 33, 40, 210), (0, 146, width, 66))
    pygame.draw.rect(surface, ROAD_EDGE, (0, 143, width, 4))
    pygame.draw.rect(surface, (82, 75, 69), (0, 211, width, 7))
    for line_x in range(-70, width, 170):
        pygame.draw.rect(surface, (229, 190, 92), (line_x, 176, 92, 3))
    colors = ((158, 68, 54), (52, 88, 116), (171, 151, 107), (72, 92, 70))
    for index, car_x in enumerate(range(90, width - 40, 430)):
        _draw_car(surface, car_x, 153 + (index % 2) * 24, colors[index % len(colors)], facing=1)
    # The foreground lot belongs to the west/even side and is intentionally
    # warmer and brighter than the inaccessible east side across the road.
    _alpha_rect(surface, (80, 70, 65, 54), (0, 219, width, 141))
    pygame.draw.rect(surface, (222, 211, 188), (0, 218, width, 4))


def _draw_natural_signs(surface: pygame.Surface, route: Mapping[str, Any]) -> None:
    width = int(route["world_width"])
    accent = ROUTE_ACCENTS[str(route["theme"])]
    for index, landmark in enumerate(route["landmarks"]):
        label = ART_LABELS.get(str(landmark["id"]), str(landmark["display_name"]).upper())
        label_image = _font(14, bold=True).render(label, False, WARM_WHITE)
        sign_width = min(240, label_image.get_width() + 18)
        sign_x = max(4, min(width - sign_width - 4, int(landmark["world_x"]) - sign_width // 2))
        sign_y = 104 + (index % 2) * 20
        _alpha_rect(surface, (18, 21, 25, 215), (sign_x, sign_y, sign_width, 18))
        pygame.draw.rect(surface, accent, (sign_x, sign_y, 4, 18))
        surface.blit(label_image, (sign_x + 10, sign_y + 3))

    # Opposite-side bearings are intentionally small and muted.  They orient
    # the route across traffic without making the east side look walkable.
    for index, landmark in enumerate(route.get("opposite_side_landmarks", ())):
        label = str(landmark["display_name"]).upper()
        label_image = _font(11, bold=True).render(label, False, (197, 178, 145))
        sign_width = min(150, label_image.get_width() + 10)
        sign_x = max(2, min(width - sign_width - 2, int(landmark["world_x"]) - sign_width // 2))
        sign_y = 67 + (index % 2) * 13
        _alpha_rect(surface, (25, 26, 31, 180), (sign_x, sign_y, sign_width, 12))
        surface.blit(label_image, (sign_x + 5, sign_y + 1))


def _draw_level_one(surface: pygame.Surface, route: Mapping[str, Any]) -> None:
    _draw_route_road(surface, route)
    width = int(route["world_width"])
    _draw_parking_stripes(surface, 0, 760, spacing=70)
    _draw_parking_stripes(surface, 930, 2430, spacing=76, reverse=True)
    for driveway in (690, 930, 1440, 2360):
        _draw_driveway(surface, driveway, width=76)
    for car_index, car_x in enumerate((130, 255, 460, 585, 1080, 1290, 1650, 1810, 2050, 2260)):
        _draw_car(
            surface,
            car_x,
            245 + (car_index % 2) * 34,
            ((62, 101, 126), (158, 76, 56), (204, 193, 164))[car_index % 3],
        )
    _draw_cart_corral(surface, 335)
    _draw_cart_corral(surface, 590)
    _draw_planter(surface, 1160, 303, 100)
    _draw_planter(surface, 1770, 299, 120)

    # Remodeled neighborhood-market mural and the long cream/tan Town &
    # Country facade are the level's central massing rulers.
    pygame.draw.rect(surface, (204, 187, 151), (1050, 222, 240, 48))
    pygame.draw.rect(surface, (50, 104, 106), (1062, 231, 216, 7))
    mural = ((215, 105, 72), (226, 157, 80), (69, 135, 139), (91, 92, 127))
    for band, color in enumerate(mural):
        pygame.draw.polygon(
            surface,
            color,
            [(1060 + band * 52, 247), (1100 + band * 48, 226), (1146 + band * 45, 268), (1080 + band * 52, 268)],
        )
    pygame.draw.rect(surface, (205, 181, 141), (1480, 213, 850, 61))
    pygame.draw.rect(surface, (119, 87, 61), (1480, 208, 850, 8))
    for column_x in range(1510, 2300, 74):
        pygame.draw.rect(surface, (151, 117, 81), (column_x, 229, 8, 45))
        pygame.draw.rect(surface, (54, 85, 95), (column_x + 10, 236, 50, 25))

    # Madison is a full signalized gap, followed by an angled corner reveal.
    madison_x = _x(route, "madison_intersection")
    _alpha_rect(surface, (42, 45, 51, 225), (madison_x - 70, 118, 170, 242))
    for stripe in range(madison_x - 55, madison_x + 90, 22):
        pygame.draw.rect(surface, (230, 224, 205), (stripe, 199, 12, 70))
    pygame.draw.rect(surface, (49, 52, 57), (madison_x + 35, 75, 7, 145))
    pygame.draw.rect(surface, (49, 52, 57), (madison_x - 90, 90, 128, 7))
    pygame.draw.rect(surface, (29, 30, 34), (madison_x - 95, 82, 23, 42))
    pygame.draw.circle(surface, (212, 69, 58), (madison_x - 84, 91), 4)
    pygame.draw.circle(surface, (224, 180, 67), (madison_x - 84, 102), 4)
    pygame.draw.circle(surface, (77, 164, 92), (madison_x - 84, 113), 4)
    pygame.draw.polygon(
        surface,
        (65, 58, 58),
        [(madison_x + 70, 218), (width, 218), (width, 360), (madison_x + 120, 360)],
    )
    pygame.draw.line(surface, (231, 205, 99), (madison_x + 92, 270), (width, 270), 4)
    pygame.draw.rect(surface, (166, 127, 94), (2850, 194, 320, 73))
    pygame.draw.polygon(surface, (99, 60, 47), [(2840, 194), (3175, 194), (3158, 180), (2856, 180)])
    for awning_x in range(2880, 3150, 62):
        pygame.draw.polygon(
            surface,
            (67, 112, 103),
            [(awning_x, 225), (awning_x + 50, 225), (awning_x + 43, 238), (awning_x + 7, 238)],
        )
    _draw_natural_signs(surface, route)


def _draw_level_two(surface: pygame.Surface, route: Mapping[str, Any]) -> None:
    _draw_route_road(surface, route)
    width = int(route["world_width"])
    _draw_parking_stripes(surface, 0, 440, spacing=66)
    _draw_parking_stripes(surface, 780, 1800, spacing=74, reverse=True)
    for driveway in (475, 760, 1700, 2250):
        _draw_driveway(surface, driveway, width=80)

    # Fuel pad and separate islands.
    pygame.draw.rect(surface, (224, 218, 196), (60, 211, 390, 18))
    pygame.draw.rect(surface, (47, 122, 162), (60, 211, 390, 5))
    pygame.draw.rect(surface, (192, 63, 52), (60, 218, 390, 4))
    for post_x in (95, 215, 335, 425):
        pygame.draw.rect(surface, (82, 78, 72), (post_x, 226, 7, 49))
    for pump_x in (135, 275, 390):
        pygame.draw.rect(surface, (220, 215, 193), (pump_x, 250, 17, 28))
        pygame.draw.rect(surface, (44, 91, 119), (pump_x + 3, 254, 11, 7))
        pygame.draw.rect(surface, (212, 166, 59), (pump_x - 4, 275, 25, 4))

    # Madison Plaza's broad west-side parking field and warm Petco anchor.
    pygame.draw.rect(surface, (197, 155, 101), (865, 210, 770, 67))
    pygame.draw.rect(surface, (112, 75, 56), (865, 205, 770, 8))
    for bay_x in range(890, 1600, 72):
        pygame.draw.rect(surface, (67, 68, 69), (bay_x, 235, 50, 35))
        pygame.draw.rect(surface, (221, 190, 142), (bay_x - 4, 229, 58, 6))
    _draw_planter(surface, 1120, 304, 112)
    _draw_planter(surface, 1430, 304, 112)

    # Former bank and service-bay progression before the freeway.
    pygame.draw.rect(surface, (185, 174, 151), (1690, 216, 220, 58))
    pygame.draw.polygon(surface, (85, 74, 65), [(1682, 216), (1918, 216), (1888, 197), (1712, 197)])
    pygame.draw.rect(surface, (199, 201, 193), (1940, 204, 320, 72))
    pygame.draw.rect(surface, (38, 100, 135), (1940, 204, 320, 8))
    for bay_x in (1970, 2058, 2146):
        pygame.draw.rect(surface, (49, 57, 62), (bay_x, 222, 72, 51))
        pygame.draw.line(surface, (104, 116, 119), (bay_x + 8, 236), (bay_x + 64, 236), 3)
        pygame.draw.rect(surface, (226, 183, 64), (bay_x - 5, 270, 9, 18))
        pygame.draw.rect(surface, (226, 183, 64), (bay_x + 68, 270, 9, 18))

    # The route visibly expands into retaining walls, creek edge, columns, and
    # then terminates inside the I-8 shadow.
    approach_x = _x(route, "freeway_approach")
    pygame.draw.polygon(
        surface,
        (110, 109, 105),
        [(approach_x - 120, 224), (width, 190), (width, 318), (approach_x - 40, 318)],
    )
    pygame.draw.line(surface, (188, 184, 170), (approach_x - 110, 231), (width, 199), 5)
    pygame.draw.polygon(
        surface,
        (31, 36, 41),
        [(approach_x + 40, 65), (width, 38), (width, 114), (approach_x + 100, 128)],
    )
    pygame.draw.line(surface, (124, 123, 119), (approach_x + 40, 65), (width, 38), 7)
    for column_x in (2585, 2790, 3000, 3170):
        pygame.draw.polygon(
            surface,
            (92, 94, 96),
            [(column_x - 18, 91), (column_x + 23, 88), (column_x + 32, 316), (column_x - 26, 316)],
        )
        pygame.draw.rect(surface, (130, 130, 127), (column_x - 25, 82, 55, 15))
    _alpha_rect(surface, (22, 27, 35, 115), (2670, 82, width - 2670, 278))
    pygame.draw.polygon(
        surface,
        (37, 56, 59),
        [(2330, 321), (width, 304), (width, 360), (2260, 360)],
    )
    for water_x in range(2370, width, 82):
        pygame.draw.line(surface, (58, 116, 139), (water_x, 340), (water_x + 43, 336), 3)
    pygame.draw.line(surface, (151, 139, 116), (2300, 319), (width, 300), 5)
    _draw_natural_signs(surface, route)


def _draw_level_three(surface: pygame.Surface, route: Mapping[str, Any]) -> None:
    _draw_route_road(surface, route)
    width = int(route["world_width"])
    _draw_parking_stripes(surface, 0, 760, spacing=72)
    _draw_parking_stripes(surface, 790, 2010, spacing=70, reverse=True)
    for driveway in (720, 1030, 1770):
        _draw_driveway(surface, driveway, width=78)

    # White-and-blue car wash with a wet apron and a long repeating arched
    # vacuum row; this is deliberately a unique silhouette, not a generic box.
    pygame.draw.rect(surface, (232, 235, 228), (45, 201, 320, 78))
    pygame.draw.rect(surface, (33, 137, 211), (45, 201, 320, 10))
    pygame.draw.rect(surface, (33, 137, 211), (45, 252, 320, 8))
    pygame.draw.rect(surface, (26, 38, 49), (78, 221, 130, 58))
    for arch_x in range(365, 815, 64):
        pygame.draw.arc(surface, (238, 240, 232), (arch_x, 201, 56, 86), 3.14, 6.28, 6)
        pygame.draw.line(surface, (215, 222, 218), (arch_x, 242), (arch_x, 286), 5)
        pygame.draw.line(surface, (215, 222, 218), (arch_x + 55, 242), (arch_x + 55, 286), 5)
        pygame.draw.rect(surface, (29, 115, 177), (arch_x + 5, 258, 9, 27))
    wet = pygame.Surface((840, 102), pygame.SRCALPHA)
    for wet_x in range(20, 820, 86):
        pygame.draw.polygon(
            wet,
            (53, 146, 186, 95),
            [(wet_x, 10), (wet_x + 46, 4), (wet_x + 72, 87), (wet_x + 22, 95)],
        )
        pygame.draw.line(wet, (169, 223, 232, 145), (wet_x + 8, 38), (wet_x + 58, 31), 3)
    surface.blit(wet, (0, 258))
    _draw_palm(surface, 120, 238, 90)
    _draw_palm(surface, 690, 241, 82)

    # The intermediate pads remain separate instead of becoming a continuous
    # fantasy storefront wall.
    facades = (
        (650, 840, (163, 119, 80), (49, 46, 43)),
        (1050, 1320, (192, 154, 112), (107, 62, 43)),
        (1425, 1665, (122, 91, 69), (48, 38, 35)),
        (1810, 2110, (206, 194, 174), (142, 59, 54)),
    )
    for start, end, facade, trim in facades:
        pygame.draw.rect(surface, facade, (start, 218, end - start, 57))
        pygame.draw.rect(surface, trim, (start, 211, end - start, 9))
        for window_x in range(start + 15, end - 25, 58):
            pygame.draw.rect(surface, (49, 66, 69), (window_x, 237, 39, 32))

    # Broadway opens to the west as a receding side road, complete with signal,
    # crosswalk, direction sign, and a distinct medical-office destination.
    turn_x = _x(route, "broadway_turn")
    pygame.draw.polygon(
        surface,
        (47, 50, 57),
        [(turn_x - 78, 211), (turn_x + 90, 211), (2750, 76), (2510, 76)],
    )
    for stripe in range(turn_x - 65, turn_x + 90, 22):
        pygame.draw.polygon(
            surface,
            (233, 228, 211),
            [(stripe, 215), (stripe + 12, 215), (stripe + 7, 280), (stripe - 5, 280)],
        )
    pygame.draw.line(surface, (222, 189, 82), (turn_x + 28, 198), (2630, 82), 4)
    pygame.draw.rect(surface, (43, 47, 51), (turn_x - 45, 78, 7, 139))
    pygame.draw.rect(surface, (43, 47, 51), (turn_x - 92, 84, 54, 6))
    pygame.draw.rect(surface, (24, 27, 31), (turn_x - 94, 75, 19, 38))
    pygame.draw.circle(surface, (211, 64, 54), (turn_x - 85, 84), 3)
    pygame.draw.circle(surface, (222, 174, 56), (turn_x - 85, 94), 3)
    pygame.draw.circle(surface, (61, 157, 84), (turn_x - 85, 104), 3)
    pygame.draw.rect(surface, (178, 181, 176), (2680, 166, 465, 111))
    pygame.draw.rect(surface, (55, 88, 101), (2680, 166, 465, 9))
    pygame.draw.polygon(surface, (117, 119, 116), [(2672, 166), (3154, 166), (3114, 145), (2715, 145)])
    for window_x in range(2710, 3120, 68):
        pygame.draw.rect(surface, (57, 94, 107), (window_x, 198, 48, 39))
        pygame.draw.rect(surface, (78, 68, 62), (window_x + 12, 241, 24, 34))
    _draw_planter(surface, 2770, 295, 104)
    _draw_planter(surface, 3040, 295, 104)
    _draw_natural_signs(surface, route)


def _draw_level_four(surface: pygame.Surface, route: Mapping[str, Any]) -> None:
    width = int(route["world_width"])
    # Preserve the generated broad gray/black/glass/wood facade, then register
    # the large parking field and arena props at their canonical world points.
    _alpha_rect(surface, (55, 55, 56, 35), (0, 204, width, 156))
    pygame.draw.rect(surface, (214, 206, 188), (0, 232, width, 4))
    _draw_parking_stripes(surface, 0, width, y=247, spacing=74)
    _draw_parking_stripes(surface, 20, width, y=309, spacing=82, reverse=True)
    for car_index, car_x in enumerate((80, 245, 520, 690, 1260, 1450)):
        _draw_car(
            surface,
            car_x,
            268 + (car_index % 2) * 38,
            ((73, 91, 105), (172, 81, 60), (176, 160, 126))[car_index % 3],
        )
    _draw_planter(surface, 330, 286, 122)
    _draw_planter(surface, 1010, 292, 132)
    _draw_light_pole(surface, 520, 278)
    _draw_light_pole(surface, 760, 280)
    _draw_light_pole(surface, 1300, 284)
    bmx_x = _x(route, "daves_bmx")
    _draw_bmx(surface, bmx_x, 308)
    pygame.draw.rect(surface, (87, 91, 91), (bmx_x + 46, 250, 54, 4))
    for rack_x in range(bmx_x + 50, bmx_x + 100, 15):
        pygame.draw.arc(surface, (158, 159, 153), (rack_x, 245, 13, 34), 3.14, 6.28, 2)
    _draw_natural_signs(surface, route)


def _draw_far(route: Mapping[str, Any]) -> pygame.Surface:
    width = int(route["world_width"])
    theme = str(route["theme"])
    accent = ROUTE_ACCENTS[theme]
    far = pygame.Surface((width, HEIGHT), pygame.SRCALPHA)
    # Transparent except for genuine distant sky/haze, low foothill contour,
    # and utility silhouettes.  No parcel-defining architecture is duplicated.
    pygame.draw.rect(far, (53, 50, 83, 125), (0, 0, width, 54))
    pygame.draw.rect(far, (226, 132, 87, 80), (0, 54, width, 42))
    points = [(0, 100)]
    seed = sum(ord(character) for character in theme)
    for index, hill_x in enumerate(range(0, width + 260, 260)):
        hill_y = 89 + ((seed + index * 13) % 15)
        points.append((hill_x, hill_y))
    points.extend([(width, 112), (0, 112)])
    pygame.draw.polygon(far, (*accent, 75), points)
    start = 68 + seed % 97
    for pole_x in range(start, width, 430):
        pygame.draw.rect(far, (43, 42, 49, 105), (pole_x, 55, 3, 61))
        pygame.draw.line(far, (43, 42, 49, 95), (pole_x - 17, 64), (pole_x + 19, 64), 2)
        pygame.draw.line(far, (43, 42, 49, 70), (pole_x + 18, 64), (pole_x + 430, 70), 1)
    return far


def _draw_near(route: Mapping[str, Any]) -> pygame.Surface:
    width = int(route["world_width"])
    theme = str(route["theme"])
    seed = sum(ord(character) for character in theme)
    near = pygame.Surface((width, HEIGHT), pygame.SRCALPHA)
    # Sparse decorative framing only.  Route buildings, intersections, road,
    # and collision landmarks remain exclusively in the one-to-one main strip.
    positions = [
        74 + seed % 121,
        width // 2 + seed % 173 - 86,
        width - 155 - seed % 113,
    ]
    for index, shrub_x in enumerate(positions):
        base_y = 354 - index * 3
        pygame.draw.ellipse(near, (21, 28, 25, 110), (shrub_x - 40, base_y - 17, 82, 26))
        pygame.draw.line(near, (54, 91, 56, 145), (shrub_x, base_y), (shrub_x - 18, base_y - 37), 6)
        pygame.draw.line(near, (76, 112, 67, 130), (shrub_x, base_y), (shrub_x + 22, base_y - 31), 5)
    pygame.draw.rect(near, (22, 21, 24, 50), (0, 355, width, 5))
    return near


def _build_route(route: Mapping[str, Any]) -> tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
    main = _concept_panorama(route)
    theme = str(route["theme"])
    if theme == "sprouts_el_cilantro":
        _draw_level_one(main, route)
    elif theme == "seven_eleven_underpass":
        _draw_level_two(main, route)
    elif theme == "soapy_joes_revive":
        _draw_level_three(main, route)
    elif theme == "awaken_church_finale":
        _draw_level_four(main, route)
    else:
        raise ValueError(f"unsupported Chapter 1 route theme: {theme}")
    return main, _draw_far(route), _draw_near(route)


def _save(surface: pygame.Surface, relative_asset: str) -> None:
    path = ROOT / relative_asset
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(path))


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    manifest = json.loads((ROOT / "data" / "chapter1_location_lock.json").read_text(encoding="utf-8"))
    routes: Iterable[Mapping[str, Any]] = manifest["routes"]
    for route in routes:
        main_surface, far_surface, near_surface = _build_route(route)
        _save(main_surface, str(route["main_panorama_asset"]))
        _save(far_surface, str(route["far_asset"]))
        _save(near_surface, str(route["near_asset"]))
        print(
            f"{route['level_id']}: main={main_surface.get_size()} "
            f"far={far_surface.get_size()} near={near_surface.get_size()}"
        )
    pygame.quit()


if __name__ == "__main__":
    main()
