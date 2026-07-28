"""Build the location-locked Chapter 1 panoramas without distorting source art.

Every main strip is assembled from authored, actor-scale scene panels.  Panels
are uniformly cover-scaled and cropped; no source plate is stretched to the
full route width.  The authored floor perspective is retained and Chapter 1
does not add procedural traffic.
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

LAYER_NAMES = (
    "haze",
    "skyline",
    "architecture",
    "ground",
    "near_occluder",
)
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


def _alpha_rect(
    surface: pygame.Surface,
    color: tuple[int, int, int, int],
    rect: pygame.Rect | tuple[int, int, int, int],
) -> None:
    overlay = pygame.Surface((int(rect[2]), int(rect[3])), pygame.SRCALPHA)
    overlay.fill(color)
    surface.blit(overlay, (int(rect[0]), int(rect[1])))

def _layer_asset_path(route: Mapping[str, Any], layer: str) -> Path:
    route_value = str(route.get(f"{layer}_asset", "")).strip()
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


def _panel_panorama(route: Mapping[str, Any]) -> pygame.Surface:
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
    width = int(route["world_width"])
    theme = str(route["theme"])
    accent = ROUTE_ACCENTS[theme]
    far = pygame.Surface((width, HEIGHT), pygame.SRCALPHA)
    pygame.draw.rect(far, (53, 50, 83, 125), (0, 0, width, 54))
    pygame.draw.rect(far, (226, 132, 87, 80), (0, 54, width, 42))
    points = [(0, 100)]
    seed = sum(ord(character) for character in theme)
    for index, hill_x in enumerate(range(0, width + 260, 260)):
        hill_y = 89 + ((seed + index * 13) % 15)
        points.append((hill_x, hill_y))
    points.extend([(width, 112), (0, 112)])
    pygame.draw.polygon(far, (*accent, 75), points)
    for pole_x in range(68 + seed % 97, width, 430):
        pygame.draw.rect(far, (43, 42, 49, 105), (pole_x, 55, 3, 61))
        pygame.draw.line(far, (43, 42, 49, 95), (pole_x - 17, 64), (pole_x + 19, 64), 2)
        pygame.draw.line(far, (43, 42, 49, 70), (pole_x + 18, 64), (pole_x + 430, 70), 1)
    return far


def _draw_near(route: Mapping[str, Any]) -> pygame.Surface:
    width = int(route["world_width"])
    theme = str(route["theme"])
    seed = sum(ord(character) for character in theme)
    near = pygame.Surface((width, HEIGHT), pygame.SRCALPHA)
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


def _build_layered_assets(route: Mapping[str, Any]) -> dict[str, pygame.Surface]:
    main, far, near = _build_route(route)
    width, height = main.get_size()
    ground_row = max(1, min(height, int(route.get("ground_opaque_from_y", 238))))
    layer_profile = ROUTE_LAYER_Y.get(
        str(route["theme"]),
        ROUTE_LAYER_Y["sprouts_el_cilantro"],
    )
    haze_max = min(ground_row, int(layer_profile["haze_max_y"]))
    skyline_max = min(ground_row - 2, int(layer_profile["skyline_max_y"]))
    architecture_min = min(max(0, int(layer_profile["architecture_min_y"])), ground_row - 1)
    near_min = min(max(architecture_min + 2, int(layer_profile["near_min_y"])), height)

    layers = {
        "haze": pygame.Surface((width, height), pygame.SRCALPHA),
        "skyline": pygame.Surface((width, height), pygame.SRCALPHA),
        "architecture": pygame.Surface((width, height), pygame.SRCALPHA),
        "ground": pygame.Surface((width, height), pygame.SRCALPHA),
        "near_occluder": pygame.Surface((width, height), pygame.SRCALPHA),
    }
    _copy_band(far, layers["haze"], 0, haze_max)
    _copy_band(far, layers["skyline"], 0, skyline_max)
    _copy_band(main, layers["architecture"], architecture_min, ground_row)
    _copy_band(main, layers["ground"], ground_row, height)
    _copy_band(near, layers["near_occluder"], near_min, height)
    return layers


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
    accent = ROUTE_ACCENTS[theme]
    _alpha_rect(panorama, (*accent, 10), (0, 0, width, HEIGHT))
    _alpha_rect(panorama, (18, 20, 24, 18), (0, 286, width, HEIGHT - 286))
    for seam_index, seam in enumerate(seams):
        _draw_structural_handoff(panorama, seam, accent, seam_index)

    return panorama


def _build_route(route: Mapping[str, Any]) -> tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
    main = _build_panorama_layers(route)
    _draw_natural_signs(main, route)
    return main, _draw_far(route), _draw_near(route)


def _save(surface: pygame.Surface, relative_asset: str) -> None:
    path = ROOT / relative_asset
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(path))


def _save_layered_assets(route: Mapping[str, Any]) -> None:
    main, far, near = _build_route(route)
    layers = _build_layered_assets(route)
    for layer_name in LAYER_NAMES:
        _save(layers[layer_name], str(_layer_asset_path(route, layer_name)))
    return main, far, near


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    manifest = json.loads(
        (ROOT / "data" / "chapter1_location_lock.json").read_text(encoding="utf-8")
    )
    routes: Iterable[Mapping[str, Any]] = manifest["routes"]
    for route in routes:
        main_surface, far_surface, near_surface = _build_route(route)
        _save_layered_assets(route)
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
