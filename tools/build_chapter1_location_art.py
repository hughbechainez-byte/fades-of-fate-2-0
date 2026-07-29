"""Build location-locked fallback panoramas and calibrated 2.5D route layers.

Authored paintings remain available as an explicit fallback and as a material
detail source. Shipping layered routes keep calibrated transparent façades and
an orthographic floor, while masked source color/texture restores route detail
without restoring the paintings' perspective floor, baked sky, or tiny cars.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import pygame


ROOT = Path(__file__).resolve().parents[1]
HEIGHT = 360
WARM_WHITE = (245, 225, 180)

ROUTE_ACCENTS = {
    "sprouts_el_cilantro": (91, 145, 101),
    "seven_eleven_underpass": (207, 100, 64),
    "soapy_joes_revive": (41, 146, 211),
    "awaken_church_finale": (203, 118, 73),
}

LAYER_FIELDS = (
    ("haze", "far_haze_asset"),
    ("skyline", "far_skyline_asset"),
    "architecture",
    "ground",
    "near_occluder",
)
ORTHOGRAPHIC_GROUND_SOURCE = (
    ROOT
    / "art_source"
    / "chapter1_location_locked"
    / "calibration"
    / "chapter1_orthographic_asphalt_v1.png"
)
# Match the actual shipped Dave idle silhouette used by projection QA.  All
# physical references on the authored architecture plane derive from this one
# screen-space ruler.
REFERENCE_ADULT_HEIGHT_PX = 134
REFERENCE_DOOR_HEIGHT_PX = round(REFERENCE_ADULT_HEIGHT_PX * 1.95 / 1.8)
SOURCE_DETAIL_TOP_Y = 58
SOURCE_DETAIL_BOTTOM_Y = 190
GROUND_APRON_HEIGHT = 10
HAZE_REPEAT_WIDTH = 800
ROUTE_LAYER_Y: dict[str, dict[str, int]] = {
    "sprouts_el_cilantro": {
        "haze_max_y": 112,
        "skyline_max_y": 176,
        "architecture_min_y": 96,
        "near_min_y": 190,
    },
    "seven_eleven_underpass": {
        "haze_max_y": 108,
        "skyline_max_y": 182,
        "architecture_min_y": 92,
        "near_min_y": 190,
    },
    "soapy_joes_revive": {
        "haze_max_y": 110,
        "skyline_max_y": 184,
        "architecture_min_y": 99,
        "near_min_y": 192,
    },
    "awaken_church_finale": {
        "haze_max_y": 120,
        "skyline_max_y": 186,
        "architecture_min_y": 106,
        "near_min_y": 198,
    },
}

ART_LABELS = {
    "sprouts_parking_lot": "SPROUTS MARKET",
    "wells_fargo_pad": "WELLS FARGO PAD",
    "walmart_neighborhood_market": "WALMART MARKET",
    "town_country": "TOWN & COUNTRY",
    "goodwill_frontage": "GOODWILL",
    "madison_intersection": "MADISON AVE",
    "el_cilantro_madison": "EL CILANTRO",
    "seven_eleven_pad": "7-ELEVEN",
    "carls_jr_pad": "CARL'S JR PAD",
    "madison_plaza": "MADISON PLAZA",
    "former_union_bank": "FORMER UNION BANK",
    "valvoline": "VALVOLINE",
    "freeway_approach": "I-8 APPROACH",
    "i8_underpass": "I-8 UNDERPASS",
    "soapy_joes": "SOAPY JOE'S",
    "starbucks_pad": "STARBUCKS PAD",
    "marechiaro": "MARECHIARO'S",
    "carls_boot_leather": "CARL'S BOOT + LEATHER",
    "cvs_broadway_corner": "CVS PHARMACY",
    "broadway_turn": "BROADWAY  \u2190 WEST",
    "revive_pathway": "REVIVE PATHWAY",
    "awaken_church_lot": "950 N 2ND",
    "awaken_facade": "AWAKEN CAMPUS",
    "awaken_front_lot": "FRONT LOT",
    "daves_bmx": "DAVE'S BMX",
}


@dataclass(frozen=True)
class PanelSpec:
    """One fixed-width panorama panel and its optional authored source crop."""

    source: str
    width: int = 800
    anchor_ids: tuple[str, ...] = ()
    source_crop: tuple[int, int, int, int] | None = None
    focal_x: float = 0.5
    focal_y: float = 0.5


# Each independently reviewed panel is authored for exactly one contiguous
# route band.  Concatenated anchor_ids must equal the manifest order.
PANEL_SPECS: dict[str, tuple[PanelSpec, ...]] = {
    "sprouts_el_cilantro": (
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l1_p1_sprouts_v3_source.png",
            anchor_ids=("sprouts_parking_lot",),
        ),
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l1_p2_wells_walmart_v3_source.png",
            anchor_ids=("wells_fargo_pad", "walmart_neighborhood_market"),
        ),
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l1_p3_town_country_v3_source.png",
            anchor_ids=("town_country",),
        ),
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l1_p4_madison_el_cilantro_v3_source.png",
            anchor_ids=(
                "goodwill_frontage",
                "madison_intersection",
                "el_cilantro_madison",
            ),
        ),
    ),
    "seven_eleven_underpass": (
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l2_p1_7eleven_carls_v3_source.png",
            anchor_ids=("seven_eleven", "carls_jr_pad"),
        ),
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l2_p2_madison_plaza_bank_v3_source.png",
            anchor_ids=("madison_plaza", "former_union_bank"),
        ),
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l2_p3_valvoline_freeway_v3_source.png",
            anchor_ids=("valvoline",),
        ),
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l2_p4_i8_underpass_v3_source.png",
            anchor_ids=("freeway_approach", "i8_underpass"),
        ),
    ),
    "soapy_joes_revive": (
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l3_p1_soapy_v3_source.png",
            anchor_ids=("soapy_joes", "starbucks_pad"),
        ),
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l3_p2_starbucks_marechiaro_v3_source.png",
            anchor_ids=("marechiaro", "carls_boot_leather"),
        ),
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l3_p3_boot_cvs_v3_source.png",
            anchor_ids=("cvs_broadway_corner", "broadway_turn"),
        ),
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l3_p4_broadway_revive_v3_source.png",
            anchor_ids=("revive_pathway",),
        ),
    ),
    "awaken_church_finale": (
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l4_p1_awaken_lot_v3_source.png",
            anchor_ids=("awaken_church_lot", "awaken_facade"),
        ),
        PanelSpec(
            "art_source/chapter1_location_locked/source_panels/l4_p2_daves_bmx_v3_source.png",
            anchor_ids=("awaken_front_lot", "daves_bmx"),
        ),
    ),
}


def _font(size: int, *, bold: bool = False) -> pygame.font.Font:
    font = pygame.font.Font(None, size)
    font.set_bold(bold)
    return font


def _label(
    surface: pygame.Surface,
    text: str,
    x: int,
    y: int,
    color: tuple[int, int, int],
    size: int,
    *,
    centered: bool = False,
) -> None:
    image = _font(size, bold=True).render(str(text), False, color)
    left = int(x) - image.get_width() // 2 if centered else int(x)
    surface.blit(image, (left, int(y)))


def _alpha_rect(
    surface: pygame.Surface,
    color: tuple[int, int, int, int],
    rect: pygame.Rect | tuple[int, int, int, int],
) -> None:
    overlay = pygame.Surface((int(rect[2]), int(rect[3])), pygame.SRCALPHA)
    overlay.fill(color)
    surface.blit(overlay, (int(rect[0]), int(rect[1])))


def _layer_asset_path(route: Mapping[str, Any], layer: str) -> Path:
    field = {
        "haze": "far_haze_asset",
        "skyline": "far_skyline_asset",
    }.get(layer, f"{layer}_asset")
    route_value = str(route.get(field, "")).strip()
    if route_value:
        return ROOT / route_value
    main_path = Path(str(route["main_panorama_asset"]))
    stem = main_path.stem.replace("_main_", f"_{layer}_")
    return main_path.with_name(f"{stem}{main_path.suffix}")


def cover_crop_geometry(
    source_size: tuple[int, int],
    target_size: tuple[int, int],
    *,
    focal_x: float = 0.5,
    focal_y: float = 0.5,
) -> tuple[float, tuple[int, int], pygame.Rect]:
    """Return one uniform scale and a bounded crop for a target panel."""

    source_width, source_height = source_size
    target_width, target_height = target_size
    if min(source_width, source_height, target_width, target_height) <= 0:
        raise ValueError("cover-crop dimensions must be positive")
    if not 0.0 <= focal_x <= 1.0 or not 0.0 <= focal_y <= 1.0:
        raise ValueError("cover-crop focal points must be in the closed unit interval")

    scale = max(target_width / source_width, target_height / source_height)
    scaled_width = max(target_width, math.ceil(source_width * scale))
    scaled_height = max(target_height, math.ceil(source_height * scale))
    overflow_x = scaled_width - target_width
    overflow_y = scaled_height - target_height
    crop_x = round(overflow_x * focal_x)
    crop_y = round(overflow_y * focal_y)
    crop = pygame.Rect(crop_x, crop_y, target_width, target_height)
    return scale, (scaled_width, scaled_height), crop


def _copy_band(
    source: pygame.Surface,
    destination: pygame.Surface,
    y_start: int,
    y_end: int,
) -> None:
    width, height = source.get_size()
    y0 = max(0, min(height, int(round(y_start))))
    y1 = max(y0, min(height, int(round(y_end))))
    if y1 <= y0:
        return
    if source.get_masks()[3] == 0:
        source_band = pygame.Surface((width, y1 - y0), pygame.SRCALPHA)
        source_band.blit(source, (0, -y0))
        source_band.convert_alpha()
    else:
        source_band = source.subsurface(pygame.Rect(0, y0, width, y1 - y0)).copy()
        source_band = source_band.convert_alpha()
    destination.blit(source_band, (0, y0))


def _load_panel(spec: PanelSpec) -> pygame.Surface:
    source_path = ROOT / spec.source
    if not source_path.is_file():
        raise FileNotFoundError(f"missing Chapter 1 authored panel: {source_path}")
    source = pygame.image.load(str(source_path)).convert()
    if spec.source_crop is not None:
        crop = pygame.Rect(spec.source_crop)
        if not source.get_rect().contains(crop):
            raise ValueError(f"source crop {crop} escapes {source_path.name}")
        source = source.subsurface(crop).copy()

    _, scaled_size, crop = cover_crop_geometry(
        source.get_size(),
        (spec.width, HEIGHT),
        focal_x=spec.focal_x,
        focal_y=spec.focal_y,
    )
    scaled = pygame.transform.scale(source, scaled_size)
    panel = pygame.Surface((spec.width, HEIGHT)).convert()
    panel.blit(scaled, (0, 0), crop)
    return panel


def _draw_structural_handoff(
    surface: pygame.Surface,
    x: int,
    accent: tuple[int, int, int],
    seam_index: int,
) -> None:
    """Mask a panel seam with a narrow, opaque lot-light/median structure."""

    pole = (39, 37, 42)
    top_y = 45 + seam_index * 5
    pygame.draw.rect(surface, pole, (x - 3, top_y, 6, 199 - seam_index * 5))
    pygame.draw.rect(surface, pole, (x - 20, top_y, 40, 5))
    pygame.draw.rect(surface, (238, 214, 150), (x - 17, top_y + 4, 12, 3))
    pygame.draw.rect(surface, (238, 214, 150), (x + 5, top_y + 4, 12, 3))
    pygame.draw.ellipse(surface, (28, 28, 30), (x - 42, 238, 84, 18))
    pygame.draw.rect(surface, (159, 143, 113), (x - 40, 232, 80, 14))
    pygame.draw.rect(surface, (104, 91, 75), (x - 36, 236, 72, 10))
    for offset, height in ((-21, 17), (-7, 24), (8, 20), (22, 15)):
        pygame.draw.line(
            surface,
            accent,
            (x + offset, 236),
            (x + offset + (2 if offset < 0 else -2), 236 - height),
            4,
        )


def _build_panorama_layers(route: Mapping[str, Any]) -> tuple[
    pygame.Surface,
    pygame.Surface,
    pygame.Surface,
]:
    theme = str(route["theme"])
    width = int(route["world_width"])
    specs = PANEL_SPECS.get(theme)
    if specs is None:
        raise ValueError(f"unsupported Chapter 1 route theme: {theme}")
    if sum(spec.width for spec in specs) != width:
        raise ValueError(f"{theme} panel widths do not sum to route width {width}")

    panorama = pygame.Surface((width, HEIGHT)).convert()
    cursor = 0
    seams: list[int] = []
    for index, spec in enumerate(specs):
        panorama.blit(_load_panel(spec), (cursor, 0))
        cursor += spec.width
        if index + 1 < len(specs):
            seams.append(cursor)

    # A single route tint unifies independently authored panels without
    # replacing or bending their native road and parking-lot perspective.
    accent = ROUTE_ACCENTS[theme]
    _alpha_rect(panorama, (*accent, 10), (0, 0, width, HEIGHT))
    _alpha_rect(panorama, (18, 20, 24, 18), (0, 286, width, HEIGHT - 286))
    for seam_index, seam in enumerate(seams):
        _draw_structural_handoff(panorama, seam, accent, seam_index)
    return panorama


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

    for index, landmark in enumerate(route.get("opposite_side_landmarks", ())):
        label = str(landmark["display_name"]).upper()
        label_image = _font(11, bold=True).render(label, False, (197, 178, 145))
        sign_width = min(150, label_image.get_width() + 10)
        sign_x = max(2, min(width - sign_width - 2, int(landmark["world_x"]) - sign_width // 2))
        sign_y = 67 + (index % 2) * 13
        _alpha_rect(surface, (25, 26, 31, 180), (sign_x, sign_y, sign_width, 12))
        surface.blit(label_image, (sign_x + 5, sign_y + 1))


def _draw_far(route: Mapping[str, Any]) -> pygame.Surface:
    far = _draw_haze(route)
    far.blit(_draw_skyline(route), (0, 0))
    return far


def _draw_haze(route: Mapping[str, Any]) -> pygame.Surface:
    width = int(route["world_width"])
    theme = str(route["theme"])
    far = pygame.Surface((width, HEIGHT), pygame.SRCALPHA)
    tile = pygame.Surface((HAZE_REPEAT_WIDTH, HEIGHT), pygame.SRCALPHA)
    seed = sum(ord(character) for character in theme)
    haze_bottom = max(96, int(route.get("ground_opaque_from_y", 220)) // 2)
    # Keep each silhouette within one runtime motion band so independently
    # phased clouds do not tear along a horizontal cut.
    for band_index in range(3):
        band_top = haze_bottom * band_index // 3
        band_bottom = haze_bottom * (band_index + 1) // 3
        band_height = max(1, band_bottom - band_top)
        wash = (
            (67, 57, 101, 24),
            (151, 83, 111, 24),
            (233, 137, 92, 20),
        )[band_index]
        pygame.draw.rect(
            tile,
            wash,
            (0, band_top, HAZE_REPEAT_WIDTH, band_height),
        )
        stride = 214 + band_index * 37
        start = (seed * (band_index + 3)) % stride
        for cloud_index, cloud_x in enumerate(
            range(start, HAZE_REPEAT_WIDTH + stride, stride)
        ):
            cloud_width = 112 + ((seed + cloud_index * 23 + band_index * 31) % 74)
            cloud_height = max(7, min(18, band_height - 5))
            cloud_y = band_top + 2 + (
                (seed + cloud_index * 17 + band_index * 11)
                % max(1, band_height - cloud_height - 3)
            )
            body = (
                (108, 67, 111, 66),
                (145, 75, 111, 61),
                (192, 97, 105, 55),
            )[band_index]
            highlight = (
                (169, 92, 128, 54),
                (205, 105, 119, 48),
                (242, 150, 108, 43),
            )[band_index]
            for wrapped_x in (
                cloud_x - HAZE_REPEAT_WIDTH,
                cloud_x,
                cloud_x + HAZE_REPEAT_WIDTH,
            ):
                pygame.draw.ellipse(
                    tile,
                    body,
                    (
                        wrapped_x,
                        cloud_y + cloud_height // 3,
                        cloud_width,
                        cloud_height * 2 // 3,
                    ),
                )
                pygame.draw.ellipse(
                    tile,
                    highlight,
                    (
                        wrapped_x + cloud_width // 5,
                        cloud_y,
                        cloud_width * 3 // 5,
                        cloud_height * 2 // 3,
                    ),
                )
                pygame.draw.rect(
                    tile,
                    body,
                    (
                        wrapped_x + cloud_width // 9,
                        cloud_y + cloud_height // 2,
                        cloud_width * 7 // 9,
                        max(3, cloud_height // 2),
                    ),
                )
    for tile_x in range(0, width, HAZE_REPEAT_WIDTH):
        far.blit(tile, (tile_x, 0))
    return far


def _draw_skyline(route: Mapping[str, Any]) -> pygame.Surface:
    width = int(route["world_width"])
    theme = str(route["theme"])
    accent = ROUTE_ACCENTS[theme]
    far = pygame.Surface((width, HEIGHT), pygame.SRCALPHA)
    seed = sum(ord(character) for character in theme)
    ridges = (
        (68, 116, (63, 55, 91, 48), 173),
        (82, 127, (*accent, 66), 131),
        (96, 139, (48, 52, 62, 82), 107),
    )
    for ridge_index, (top, bottom, color, stride) in enumerate(ridges):
        points = [(0, bottom)]
        for point_index, hill_x in enumerate(range(-stride, width + stride * 2, stride)):
            variation = (
                seed
                + point_index * (17 + ridge_index * 4)
                + ridge_index * 29
            ) % max(8, bottom - top)
            points.append((hill_x, top + variation))
        points.extend([(width, bottom), (0, bottom)])
        pygame.draw.polygon(far, color, points)

    # El Cajon's distant palms and utility rhythm give the sky a persistent,
    # route-scale silhouette without becoming a repeating foreground prop.
    for palm_index, palm_x in enumerate(range(120 + seed % 211, width, 510)):
        palm_base = 135
        palm_top = 74 + (palm_index * 11 + seed) % 22
        pygame.draw.line(far, (42, 42, 45, 126), (palm_x, palm_base), (palm_x + 2, palm_top), 3)
        for dx, dy in ((-19, 4), (-15, -4), (-6, -8), (8, -7), (17, -1), (20, 6)):
            pygame.draw.line(
                far,
                (31, 46, 42, 116),
                (palm_x + 2, palm_top + 2),
                (palm_x + dx, palm_top + dy),
                3,
            )
    for pole_x in range(68 + seed % 97, width, 430):
        pygame.draw.rect(far, (43, 42, 49, 116), (pole_x, 62, 3, 76))
        pygame.draw.line(far, (43, 42, 49, 104), (pole_x - 17, 70), (pole_x + 19, 70), 2)
        pygame.draw.line(far, (43, 42, 49, 76), (pole_x + 18, 70), (pole_x + 430, 76), 1)
    return far


def _landmark_span(
    landmarks: Sequence[Mapping[str, Any]],
    index: int,
    world_width: int,
) -> tuple[int, int]:
    center = int(landmarks[index]["world_x"])
    previous = int(landmarks[index - 1]["world_x"]) if index else 0
    following = int(landmarks[index + 1]["world_x"]) if index + 1 < len(landmarks) else world_width
    half_left = max(88, min(250, (center - previous) // 2 - 10))
    half_right = max(88, min(250, (following - center) // 2 - 10))
    return max(4, center - half_left), min(world_width - 4, center + half_right)


def _apply_authored_material(
    surface: pygame.Surface,
    detail_source: pygame.Surface | None,
    rect: pygame.Rect,
    *,
    alpha: int = 72,
) -> None:
    """Mask rich source-panel color and edges into calibrated geometry.

    Only the upper source band is sampled. That band contains roofs, wall
    material, trees and utility detail, while excluding the perspective floor
    and the small baked vehicles that motivated the orthographic conversion.
    """

    if detail_source is None or rect.width <= 0 or rect.height <= 0:
        return
    source_rect = pygame.Rect(
        max(0, rect.x),
        SOURCE_DETAIL_TOP_Y,
        min(rect.width, detail_source.get_width() - max(0, rect.x)),
        min(
            SOURCE_DETAIL_BOTTOM_Y - SOURCE_DETAIL_TOP_Y,
            detail_source.get_height() - SOURCE_DETAIL_TOP_Y,
        ),
    )
    if source_rect.width <= 0 or source_rect.height <= 0:
        return
    authored = detail_source.subsurface(source_rect).copy()
    # Reduce the source to broad material swatches before it enters calibrated
    # geometry.  This retains the photographed wall/glass palette without
    # transferring baked signs, miniature vehicles, palms, or perspective
    # edges as readable ghost shapes.
    material_grid = 4
    reduced = pygame.transform.smoothscale(
        authored,
        (
            max(1, math.ceil(rect.width / material_grid)),
            max(1, math.ceil(rect.height / material_grid)),
        ),
    )
    material = pygame.transform.scale(reduced, rect.size)
    material.set_alpha(max(0, min(255, int(alpha))))
    surface.blit(material, rect.topleft)
    shade = pygame.Surface(rect.size, pygame.SRCALPHA)
    shade.fill((26, 20, 24, 22))
    surface.blit(shade, rect.topleft)


def _draw_facade_planter(
    surface: pygame.Surface,
    x: int,
    base_y: int,
    accent: tuple[int, int, int],
) -> None:
    pygame.draw.rect(surface, (58, 48, 43, 255), (x - 13, base_y - 8, 26, 8))
    pygame.draw.rect(surface, (125, 83, 55, 255), (x - 11, base_y - 8, 22, 3))
    for offset, height in ((-8, 14), (-3, 20), (3, 18), (8, 13)):
        pygame.draw.line(
            surface,
            (*accent, 255),
            (x + offset // 2, base_y - 8),
            (x + offset, base_y - height),
            3,
        )


def _draw_glass_pane(
    surface: pygame.Surface,
    rect: pygame.Rect,
    *,
    warm: bool,
) -> None:
    pygame.draw.rect(surface, (28, 33, 39, 255), rect.inflate(6, 6))
    pygame.draw.rect(surface, (31, 55, 68, 255), rect)
    pygame.draw.rect(
        surface,
        (73, 103, 111, 255),
        (rect.x + 3, rect.y + 3, max(1, rect.width - 6), max(3, rect.height // 4)),
    )
    pygame.draw.line(
        surface,
        (137, 174, 180, 255),
        (rect.x + max(3, rect.width // 5), rect.y + 4),
        (rect.x + max(3, rect.width // 5), rect.bottom - 4),
        2,
    )
    if warm and rect.height >= 24:
        shelf_y = rect.bottom - 16
        pygame.draw.rect(
            surface,
            (102, 72, 47, 255),
            (rect.x + 4, shelf_y, max(2, rect.width - 8), 3),
        )
        for light_x in range(rect.x + 7, rect.right - 4, 10):
            pygame.draw.rect(surface, (238, 181, 93, 255), (light_x, shelf_y - 7, 3, 5))


def _draw_facade(
    surface: pygame.Surface,
    route: Mapping[str, Any],
    landmark: Mapping[str, Any],
    index: int,
    left: int,
    right: int,
    base_y: int,
    detail_source: pygame.Surface | None,
) -> None:
    landmark_id = str(landmark["id"])
    accent = ROUTE_ACCENTS[str(route["theme"])]
    width = max(120, right - left)
    center = (left + right) // 2

    if landmark_id == "seven_eleven":
        roof_y = base_y - 143
        pygame.draw.rect(surface, (45, 47, 52, 255), (left - 3, roof_y - 3, width + 6, base_y - roof_y + 3))
        pygame.draw.rect(surface, (214, 211, 194, 255), (left, roof_y, width, base_y - roof_y))
        _apply_authored_material(
            surface,
            detail_source,
            pygame.Rect(left, roof_y, width, base_y - roof_y),
            alpha=48,
        )
        for offset, color in ((8, (53, 132, 78, 255)), (14, (232, 122, 44, 255)), (20, (182, 52, 47, 255))):
            pygame.draw.rect(surface, color, (left, roof_y + offset, width, 5))
        pane_top = base_y - 116
        pane_bottom = base_y - 10
        for pane_x in range(left + 20, right - 35, 42):
            _draw_glass_pane(
                surface,
                pygame.Rect(
                    pane_x,
                    pane_top,
                    min(34, right - 18 - pane_x),
                    pane_bottom - pane_top,
                ),
                warm=True,
            )
        pygame.draw.rect(surface, (234, 232, 211, 255), (left + 8, base_y - 9, width - 16, 9))
        _label(surface, "7-ELEVEN", center, roof_y + 42, WARM_WHITE, 15, centered=True)
        return

    if landmark_id == "valvoline":
        roof_y = base_y - 163
        pygame.draw.rect(surface, (42, 47, 56, 255), (left - 3, roof_y - 3, width + 6, base_y - roof_y + 3))
        pygame.draw.rect(surface, (202, 207, 208, 255), (left, roof_y, width, base_y - roof_y))
        _apply_authored_material(
            surface,
            detail_source,
            pygame.Rect(left, roof_y, width, base_y - roof_y),
            alpha=55,
        )
        pygame.draw.rect(surface, (41, 77, 125, 255), (left, roof_y + 14, width, 17))
        bay_width = max(42, (width - 42) // 3)
        for bay in range(3):
            bay_x = left + 12 + bay * (bay_width + 4)
            pygame.draw.rect(surface, (58, 70, 83, 255), (bay_x, base_y - 140, bay_width, 140))
            pygame.draw.rect(surface, (28, 36, 45, 255), (bay_x + 5, base_y - 128, bay_width - 10, 121))
            pygame.draw.rect(surface, (128, 151, 166, 255), (bay_x + 6, base_y - 132, bay_width - 12, 5))
            for rail_y in range(base_y - 112, base_y - 12, 18):
                pygame.draw.line(
                    surface,
                    (72, 87, 101, 255),
                    (bay_x + 8, rail_y),
                    (bay_x + bay_width - 8, rail_y),
                    2,
                )
            pygame.draw.rect(surface, (210, 173, 76, 255), (bay_x + 3, base_y - 28, 5, 28))
            pygame.draw.rect(surface, (210, 173, 76, 255), (bay_x + bay_width - 8, base_y - 28, 5, 28))
        _label(surface, "VALVOLINE SERVICE BAYS", center, roof_y + 39, WARM_WHITE, 14, centered=True)
        return

    if landmark_id == "soapy_joes":
        roof_y = base_y - 151
        pygame.draw.rect(surface, (33, 52, 78, 255), (left - 3, roof_y - 3, width + 6, base_y - roof_y + 3))
        pygame.draw.rect(surface, (218, 222, 216, 255), (left, roof_y, width, base_y - roof_y))
        _apply_authored_material(
            surface,
            detail_source,
            pygame.Rect(left, roof_y, width, base_y - roof_y),
            alpha=45,
        )
        pygame.draw.rect(surface, (37, 116, 184, 255), (left, roof_y + 12, width, 18))
        pygame.draw.rect(surface, (31, 61, 89, 255), (left + 18, base_y - 94, 92, 94))
        pygame.draw.rect(surface, (83, 177, 224, 255), (left + 26, base_y - 82, 76, 8))
        canopy_left = left + 122
        for arch_x in range(canopy_left, right - 40, 62):
            pygame.draw.arc(surface, (48, 139, 207, 255), (arch_x, base_y - 92, 52, 54), math.pi, math.tau, 6)
            pygame.draw.rect(surface, (54, 75, 91, 255), (arch_x + 3, base_y - 65, 5, 65))
            pygame.draw.rect(surface, (54, 75, 91, 255), (arch_x + 44, base_y - 65, 5, 65))
            pygame.draw.rect(surface, (118, 184, 212, 255), (arch_x + 9, base_y - 17, 34, 4))
        _label(surface, "SOAPY JOE'S CAR WASH", center, roof_y + 43, (31, 64, 108), 14, centered=True)
        return

    if landmark_id == "i8_underpass":
        pygame.draw.rect(surface, (40, 42, 48, 255), (left, 62, width, 63))
        pygame.draw.rect(surface, (92, 87, 80, 255), (left, 112, width, 18))
        _apply_authored_material(
            surface,
            detail_source,
            pygame.Rect(left, 62, width, max(1, base_y - 62)),
            alpha=58,
        )
        pygame.draw.rect(surface, (35, 36, 41, 255), (left, 62, width, 22))
        pygame.draw.line(surface, (128, 119, 102, 255), (left, 111), (right, 111), 3)
        for column_x in range(left + 45, right, 150):
            pygame.draw.rect(surface, (51, 52, 56, 255), (column_x, 126, 36, base_y - 126))
            pygame.draw.rect(surface, (114, 105, 91, 255), (column_x + 4, 126, 6, base_y - 126))
            pygame.draw.rect(surface, (26, 28, 33, 255), (column_x + 27, 126, 9, base_y - 126))
        return

    if landmark_id in {"madison_intersection", "broadway_turn", "freeway_approach"}:
        pole_x = center
        pygame.draw.rect(surface, (39, 39, 45, 255), (pole_x - 4, 78, 8, base_y - 78))
        pygame.draw.rect(surface, (48, 47, 52, 255), (pole_x - 56, 79, 112, 8))
        pygame.draw.rect(surface, (*accent, 255), (pole_x + 41, 87, 12, 31))
        return

    roof_y = max(42, base_y - 174 - (index % 3) * 7)
    facade = (
        134 + (index * 17) % 24,
        121 + (index * 11) % 22,
        108 + (index * 7) % 20,
        255,
    )
    trim = (48, 49, 54, 255)
    glass = (35, 55, 69, 255)
    pygame.draw.rect(surface, trim, (left - 4, roof_y - 7, width + 8, base_y - roof_y + 7))
    pygame.draw.rect(surface, facade, (left, roof_y, width, base_y - roof_y))
    _apply_authored_material(
        surface,
        detail_source,
        pygame.Rect(left, roof_y, width, base_y - roof_y),
        alpha=78,
    )
    pygame.draw.rect(surface, (238, 224, 198, 255), (left - 2, roof_y - 3, width + 4, 5))
    pygame.draw.rect(surface, (*accent, 255), (left, roof_y + 8, width, 7))
    pygame.draw.rect(surface, (54, 50, 49, 255), (left, roof_y + 15, width, 4))
    for panel_x in range(left + 18, right - 12, 44):
        pygame.draw.line(
            surface,
            (
                max(0, facade[0] - 20),
                max(0, facade[1] - 19),
                max(0, facade[2] - 17),
                255,
            ),
            (panel_x, roof_y + 20),
            (panel_x, base_y - 14),
            1,
        )
    for course_y in range(roof_y + 25, base_y - 18, 10):
        pygame.draw.line(
            surface,
            (
                min(255, facade[0] + 17),
                min(255, facade[1] + 15),
                min(255, facade[2] + 12),
                255,
            ),
            (left + 4, course_y),
            (right - 4, course_y),
            1,
        )
    pygame.draw.rect(surface, (190, 175, 148, 255), (left, base_y - 12, width, 12))
    pygame.draw.line(surface, (77, 68, 61, 255), (left, base_y - 13), (right, base_y - 13), 3)

    door_height = min(REFERENCE_DOOR_HEIGHT_PX, base_y - roof_y - 17)
    door_width = max(36, min(54, width // 5))
    door = pygame.Rect(center - door_width // 2, base_y - door_height, door_width, door_height)
    _draw_glass_pane(surface, door, warm=True)
    pygame.draw.line(
        surface,
        (112, 143, 151, 255),
        (door.x + 4, door.centery),
        (door.right - 4, door.centery),
        2,
    )
    pygame.draw.rect(surface, (223, 190, 122, 255), (door.right - 9, door.centery, 4, 4))

    window_top = max(roof_y + 47, base_y - 112)
    window_bottom = base_y - 18
    for window_x in range(left + 14, right - 37, 46):
        if door.left - 8 <= window_x <= door.right:
            continue
        pane = pygame.Rect(
            window_x,
            window_top,
            min(34, right - 10 - window_x),
            max(24, window_bottom - window_top),
        )
        _draw_glass_pane(surface, pane, warm=index % 2 == 0)
        pygame.draw.line(
            surface,
            (91, 116, 122, 255),
            (pane.x + 3, pane.centery),
            (pane.right - 3, pane.centery),
            2,
        )

    if index % 2 == 0:
        awning_y = max(roof_y + 47, window_top - 8)
        pygame.draw.rect(surface, (35, 39, 43, 255), (left + 10, awning_y - 3, width - 20, 4))
        pygame.draw.rect(surface, (*accent, 255), (left + 12, awning_y, width - 24, 6))
        for stripe_x in range(left + 18, right - 16, 24):
            pygame.draw.rect(surface, (235, 216, 181, 255), (stripe_x, awning_y, 8, 6))

    label = ART_LABELS.get(landmark_id, str(landmark.get("display_name", landmark_id)).upper())
    label_image = _font(13, bold=True).render(label, False, WARM_WHITE)
    label_x = max(left + 6, min(right - label_image.get_width() - 6, center - label_image.get_width() // 2))
    _alpha_rect(surface, (18, 21, 25, 235), (label_x - 5, roof_y + 20, label_image.get_width() + 10, 17))
    surface.blit(label_image, (label_x, roof_y + 22))
    if width >= 190:
        _draw_facade_planter(surface, left + 22, base_y, accent)
        _draw_facade_planter(surface, right - 22, base_y, accent)


def _draw_midground_tree(
    surface: pygame.Surface,
    x: int,
    base_y: int,
    seed: int,
) -> None:
    trunk_height = 42 + seed % 17
    pygame.draw.rect(surface, (70, 49, 38, 255), (x - 3, base_y - trunk_height, 6, trunk_height))
    pygame.draw.rect(surface, (118, 74, 45, 255), (x - 1, base_y - trunk_height, 2, trunk_height))
    canopy_color = (39 + seed % 18, 67 + seed % 17, 48 + seed % 13, 255)
    for dx, dy, radius in ((-14, -2, 15), (0, -10, 18), (15, -1, 14), (-4, 7, 16)):
        pygame.draw.circle(
            surface,
            canopy_color,
            (x + dx, base_y - trunk_height + dy),
            radius,
        )
    pygame.draw.circle(
        surface,
        (73, 99, 61, 255),
        (x - 7, base_y - trunk_height - 14),
        8,
    )


def _build_architecture(
    route: Mapping[str, Any],
    detail_source: pygame.Surface | None = None,
) -> pygame.Surface:
    width = int(route["world_width"])
    base_y = int(route.get("ground_opaque_from_y", 238))
    architecture = pygame.Surface((width, HEIGHT), pygame.SRCALPHA)
    landmarks = tuple(route.get("landmarks", ()))
    if detail_source is None:
        detail_source = _build_panorama_layers(route)
    if str(route["theme"]) == "awaken_church_finale":
        left, right = 48, min(width - 48, 1300)
        roof_y = base_y - 166
        pygame.draw.rect(architecture, (42, 45, 51, 255), (left - 4, roof_y - 4, right - left + 8, base_y - roof_y + 4))
        pygame.draw.rect(architecture, (132, 133, 129, 255), (left, roof_y, right - left, base_y - roof_y))
        _apply_authored_material(
            architecture,
            detail_source,
            pygame.Rect(left, roof_y, right - left, base_y - roof_y),
            alpha=74,
        )
        pygame.draw.rect(architecture, (51, 53, 57, 255), (left - 2, roof_y - 5, right - left + 4, 8))
        pygame.draw.line(
            architecture,
            (194, 184, 163, 255),
            (left, roof_y),
            (right, roof_y),
            2,
        )
        pygame.draw.rect(architecture, (45, 65, 77, 255), (left + 188, roof_y + 18, right - left - 310, 75))
        for grid_x in range(left + 196, right - 126, 42):
            pygame.draw.line(architecture, (113, 150, 154, 255), (grid_x, roof_y + 20), (grid_x, roof_y + 91), 2)
        for grid_y in range(roof_y + 23, roof_y + 91, 23):
            pygame.draw.line(architecture, (113, 150, 154, 255), (left + 190, grid_y), (right - 120, grid_y), 2)
        pygame.draw.rect(architecture, (111, 69, 44, 255), (left + 72, roof_y + 18, 86, base_y - roof_y - 18))
        pygame.draw.rect(architecture, (111, 69, 44, 255), (right - 102, roof_y + 18, 70, base_y - roof_y - 18))
        for brick_y in range(roof_y + 24, base_y - 8, 11):
            pygame.draw.line(
                architecture,
                (137, 88, 57, 255),
                (left + 75, brick_y),
                (left + 155, brick_y),
                1,
            )
            pygame.draw.line(
                architecture,
                (137, 88, 57, 255),
                (right - 99, brick_y),
                (right - 35, brick_y),
                1,
            )
        door_height = REFERENCE_DOOR_HEIGHT_PX
        pygame.draw.rect(architecture, (25, 31, 38, 255), (left + 544, base_y - door_height, 94, door_height))
        pygame.draw.rect(architecture, (62, 91, 101, 255), (left + 552, base_y - door_height + 8, 78, door_height - 8))
        pygame.draw.rect(
            architecture,
            (231, 177, 92, 255),
            (left + 558, base_y - door_height + 15, 66, 5),
        )
        _label(architecture, "AWAKEN CAMPUS", (left + right) // 2, roof_y + 110, WARM_WHITE, 18, centered=True)
        _draw_facade_planter(architecture, left + 176, base_y, ROUTE_ACCENTS["awaken_church_finale"])
        _draw_facade_planter(architecture, right - 114, base_y, ROUTE_ACCENTS["awaken_church_finale"])
        _draw_midground_tree(architecture, right - 26, base_y, 43)
        return architecture
    for index, landmark in enumerate(landmarks):
        left, right = _landmark_span(landmarks, index, width)
        _draw_facade(
            architecture,
            route,
            landmark,
            index,
            left,
            right,
            base_y,
            detail_source,
        )
        if str(landmark["id"]) in {
            "sprouts_parking_lot",
            "walmart_neighborhood_market",
            "town_country",
            "madison_plaza",
            "former_union_bank",
            "marechiaro",
            "cvs_broadway_corner",
            "revive_pathway",
        }:
            _draw_midground_tree(
                architecture,
                max(left + 24, right - 24),
                base_y,
                sum(ord(character) for character in str(landmark["id"])),
            )
    return architecture


def _build_ground(route: Mapping[str, Any]) -> pygame.Surface:
    if not ORTHOGRAPHIC_GROUND_SOURCE.is_file():
        raise FileNotFoundError(
            f"missing calibrated orthographic ground source: {ORTHOGRAPHIC_GROUND_SOURCE}"
        )
    width = int(route["world_width"])
    ground_row = int(route.get("ground_opaque_from_y", 238))
    floor_height = HEIGHT - ground_row
    source = pygame.image.load(str(ORTHOGRAPHIC_GROUND_SOURCE)).convert()
    scaled = pygame.transform.smoothscale(source, (960, 540))
    street_route = str(route["theme"]) in {"seven_eleven_underpass", "soapy_joes_revive"}
    source_y = 220 if street_route else 0
    strip = scaled.subsurface(pygame.Rect(0, source_y, 960, floor_height)).copy()
    flipped = pygame.transform.flip(strip, True, False)
    ground = pygame.Surface((width, HEIGHT), pygame.SRCALPHA)
    cursor = 0
    index = 0
    while cursor < width:
        ground.blit(flipped if index % 2 else strip, (cursor, ground_row))
        cursor += strip.get_width()
        index += 1
    accent = ROUTE_ACCENTS[str(route["theme"])]
    _alpha_rect(ground, (*accent, 14), (0, ground_row, width, floor_height))
    # A shallow one-to-one rear apron makes the first visible floor row agree
    # with the world projection. It supports parked scenery behind the far
    # combat rail while the deeper asphalt remains orthographic and playable.
    apron_height = min(GROUND_APRON_HEIGHT, floor_height)
    pygame.draw.rect(
        ground,
        (73, 69, 65, 255),
        (0, ground_row, width, apron_height),
    )
    pygame.draw.line(
        ground,
        (158, 137, 108, 255),
        (0, ground_row),
        (width, ground_row),
        2,
    )
    pygame.draw.rect(
        ground,
        (91, 68, 58, 255),
        (0, ground_row + max(3, apron_height - 4), width, min(4, apron_height)),
    )
    for seam_x in range(36, width, 118):
        pygame.draw.line(
            ground,
            (47, 47, 47, 255),
            (seam_x, ground_row + 1),
            (seam_x, ground_row + apron_height - 1),
            1,
        )
    return ground


def _draw_near(route: Mapping[str, Any]) -> pygame.Surface:
    width = int(route["world_width"])
    theme = str(route["theme"])
    seed = sum(ord(character) for character in theme)
    near = pygame.Surface((width, HEIGHT), pygame.SRCALPHA)
    stride = 470 if width > 2000 else 390
    start = 86 + seed % 143
    for index, shrub_x in enumerate(range(start, width, stride)):
        base_y = 356 - index % 3
        pygame.draw.ellipse(near, (18, 23, 21, 132), (shrub_x - 31, base_y - 10, 63, 17))
        pygame.draw.rect(near, (72, 48, 39, 155), (shrub_x - 23, base_y - 7, 47, 7))
        blade_color = (54 + index % 2 * 12, 91, 60, 184)
        for offset, height in ((-20, 17), (-12, 25), (-4, 20), (5, 27), (14, 21), (21, 15)):
            pygame.draw.line(
                near,
                blade_color,
                (shrub_x + offset // 3, base_y - 7),
                (shrub_x + offset, base_y - height),
                3,
            )
        pygame.draw.ellipse(
            near,
            (77, 112, 67, 162),
            (shrub_x - 17, base_y - 24, 16, 8),
        )
        pygame.draw.ellipse(
            near,
            (73, 105, 62, 150),
            (shrub_x + 4, base_y - 28, 17, 8),
        )
    pygame.draw.rect(near, (22, 21, 24, 68), (0, 356, width, 4))
    return near


def _build_layered_assets(
    route: Mapping[str, Any],
    detail_source: pygame.Surface | None = None,
) -> dict[str, pygame.Surface]:
    width = int(route["world_width"])
    if detail_source is None:
        detail_source = _build_panorama_layers(route)
    near = _draw_near(route)
    layers = {
        "haze": _draw_haze(route),
        "skyline": _draw_skyline(route),
        "architecture": _build_architecture(route, detail_source),
        "ground": _build_ground(route),
        "near_occluder": near,
    }
    return layers


def _build_route(route: Mapping[str, Any]) -> tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
    main = _build_panorama_layers(route)
    _draw_natural_signs(main, route)
    return main, _draw_far(route), _draw_near(route)


def _save(surface: pygame.Surface, relative_asset: str) -> None:
    path = ROOT / relative_asset
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(path))


def _save_layered_assets(
    route: Mapping[str, Any],
    detail_source: pygame.Surface | None = None,
) -> None:
    layers = _build_layered_assets(route, detail_source)
    for item in LAYER_FIELDS:
        layer_name = item[0] if isinstance(item, tuple) else item
        _save(layers[layer_name], str(_layer_asset_path(route, layer_name)))


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    manifest = json.loads(
        (ROOT / "data" / "chapter1_location_lock.json").read_text(encoding="utf-8")
    )
    routes: Iterable[Mapping[str, Any]] = manifest["routes"]
    for route in routes:
        detail_surface = _build_panorama_layers(route)
        main_surface = detail_surface.copy()
        _draw_natural_signs(main_surface, route)
        far_surface = _draw_far(route)
        near_surface = _draw_near(route)
        _save_layered_assets(route, detail_surface)
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
