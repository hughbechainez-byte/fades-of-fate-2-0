"""Render isolated and in-game approval sheets for Chapter 1 passing traffic."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import pixel_art  # noqa: E402
from src.game import FadesGame, LOGICAL_SIZE, SelectSlot  # noqa: E402
from src.input_manager import InputManager  # noqa: E402


MODEL_PAINTS = {
    "sedan": (188, 150, 91),
    "hatchback": (52, 112, 119),
    "suv": (73, 105, 132),
    "pickup": (159, 73, 56),
    "delivery_van": (184, 183, 167),
}
NON_SEDAN_DETAIL_LABELS = {
    "hatchback": "LIFTGATE / WIPER / INTERIOR / STEEL WHEELS",
    "suv": "ROOF RACK / THREE-PANE CABIN / DOOR GUTTERS / CLADDING",
    "pickup": "TAILGATE / RECESSED BED / TWO CAB DOORS / STEP BUMPER",
    "delivery_van": "REAR HINGES / SLIDING DOOR / CAB DOOR / GRILLE",
}
SHADING_REVIEW_PAINTS = (
    ("LIGHT DUSK PAINT", (188, 164, 123)),
    ("MID-VALUE PAINT", None),
    ("DARK DUSK PAINT", (52, 68, 86)),
)
INGAME_PREVIEW_SPECS = (
    ("sprouts_el_cilantro", "sedan"),
    ("sprouts_el_cilantro", "hatchback"),
    ("seven_eleven_underpass", "delivery_van"),
    ("soapy_joes_revive", "pickup"),
    ("awaken_church_finale", "suv"),
)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _label(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    x: int,
    y: int,
    color: tuple[int, int, int] = (242, 235, 207),
) -> None:
    surface.blit(font.render(text, False, color), (x, y))


def _render_isolated_sheet(
    project_root: Path,
    output_path: Path,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
) -> None:
    card_width, card_height = 380, 300
    sheet = pygame.Surface((card_width * 3, card_height * 2)).convert()
    sheet.fill((10, 14, 22))
    route = pixel_art._location_route("sprouts_el_cilantro")
    if route is None:
        raise RuntimeError("sprouts route is unavailable")

    cards: list[tuple[str, pygame.Surface, bool]] = [
        (
            model.replace("_", " ").upper(),
            pixel_art._ambient_vehicle_surface(model, MODEL_PAINTS[model]),
            True,
        )
        for model in pixel_art._AMBIENT_VEHICLE_MODELS
    ]
    cards.append(
        (
            "PROMINENT TAN SEDAN REFERENCE",
            pixel_art._physical_scene_object_sprite(
                route["physical_scene_objects"][0]
            ),
            False,
        )
    )

    for index, (name, sprite, show_zoom) in enumerate(cards):
        column, row = index % 3, index // 3
        card = pygame.Rect(
            column * card_width,
            row * card_height,
            card_width,
            card_height,
        )
        fill = (18, 25, 37) if (column + row) % 2 == 0 else (21, 29, 42)
        pygame.draw.rect(sheet, fill, card.inflate(-8, -8))
        pygame.draw.rect(sheet, (69, 91, 112), card.inflate(-8, -8), 2)
        _label(sheet, font, name, card.x + 17, card.y + 15)
        _label(
            sheet,
            small_font,
            f"LOGICAL SIZE {sprite.get_width()} x {sprite.get_height()}",
            card.x + 17,
            card.y + 40,
            (144, 190, 199),
        )
        baseline = card.y + 110
        pygame.draw.line(
            sheet,
            (86, 96, 104),
            (card.x + 18, baseline),
            (card.right - 18, baseline),
            1,
        )
        actual_rect = sprite.get_rect(midbottom=(card.centerx, baseline))
        sheet.blit(sprite, actual_rect)
        _label(sheet, small_font, "ACTUAL IN-GAME PIXELS", card.x + 17, card.y + 118, (170, 172, 166))

        if show_zoom:
            zoom = pygame.transform.scale(
                sprite,
                (sprite.get_width() * 2, sprite.get_height() * 2),
            )
            zoom_baseline = card.bottom - 23
            pygame.draw.line(
                sheet,
                (86, 96, 104),
                (card.x + 18, zoom_baseline),
                (card.right - 18, zoom_baseline),
                1,
            )
            sheet.blit(zoom, zoom.get_rect(midbottom=(card.centerx, zoom_baseline)))
            _label(sheet, small_font, "2X CRISP DETAIL VIEW", card.x + 17, card.y + 146, (170, 172, 166))
        else:
            _label(
                sheet,
                small_font,
                "REFERENCE IS SHOWN AT ITS FULL 1X RUNTIME SCALE",
                card.x + 17,
                card.y + 164,
                (226, 177, 102),
            )
            _label(
                sheet,
                small_font,
                "PASSERS USE THE FAR-TRAFFIC-LANE SCALE;",
                card.x + 17,
                card.y + 184,
                (170, 172, 166),
            )
            _label(
                sheet,
                small_font,
                "THE TAN CAR SITS ON THE CLOSER APRON.",
                card.x + 17,
                card.y + 202,
                (170, 172, 166),
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sheet, output_path)


def _render_non_sedan_detail_sheet(
    output_path: Path,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
) -> None:
    card_width, card_height = 560, 360
    sheet = pygame.Surface((card_width * 2, card_height * 2)).convert()
    sheet.fill((10, 14, 22))
    for index, model in enumerate(NON_SEDAN_DETAIL_LABELS):
        column, row = index % 2, index // 2
        card = pygame.Rect(
            column * card_width,
            row * card_height,
            card_width,
            card_height,
        )
        fill = (18, 25, 37) if (column + row) % 2 == 0 else (21, 29, 42)
        pygame.draw.rect(sheet, fill, card.inflate(-8, -8))
        pygame.draw.rect(sheet, (69, 91, 112), card.inflate(-8, -8), 2)
        _label(sheet, font, model.replace("_", " ").upper(), card.x + 18, card.y + 14)
        _label(
            sheet,
            small_font,
            NON_SEDAN_DETAIL_LABELS[model],
            card.x + 18,
            card.y + 39,
            (144, 190, 199),
        )

        forward = pixel_art._ambient_vehicle_surface(model, MODEL_PAINTS[model])
        reverse = pixel_art._ambient_vehicle_surface(model, MODEL_PAINTS[model], facing=-1)
        actual_baseline = card.y + 105
        pygame.draw.line(
            sheet,
            (86, 96, 104),
            (card.x + 18, actual_baseline),
            (card.right - 18, actual_baseline),
            1,
        )
        sheet.blit(forward, forward.get_rect(midbottom=(card.x + 135, actual_baseline)))
        sheet.blit(reverse, reverse.get_rect(midbottom=(card.right - 135, actual_baseline)))
        _label(
            sheet,
            small_font,
            "BOTH DIRECTIONS AT ACTUAL 1X GAMEPLAY SCALE",
            card.x + 18,
            card.y + 112,
            (170, 172, 166),
        )

        zoom = pygame.transform.scale(
            forward,
            (forward.get_width() * 3, forward.get_height() * 3),
        )
        zoom_baseline = card.bottom - 22
        pygame.draw.line(
            sheet,
            (86, 96, 104),
            (card.x + 18, zoom_baseline),
            (card.right - 18, zoom_baseline),
            1,
        )
        sheet.blit(zoom, zoom.get_rect(midbottom=(card.centerx, zoom_baseline)))
        _label(
            sheet,
            small_font,
            "3X CRISP DETAIL VIEW",
            card.x + 18,
            card.y + 140,
            (226, 177, 102),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sheet, output_path)


def _render_shading_matrix(
    output_path: Path,
    font: pygame.font.Font,
    small_font: pygame.font.Font,
) -> None:
    models = tuple(NON_SEDAN_DETAIL_LABELS)
    card_width, card_height = 380, 220
    sheet = pygame.Surface(
        (card_width * len(models), card_height * len(SHADING_REVIEW_PAINTS))
    ).convert()
    sheet.fill((10, 14, 22))
    for row, (paint_label, shared_paint) in enumerate(SHADING_REVIEW_PAINTS):
        for column, model in enumerate(models):
            card = pygame.Rect(
                column * card_width,
                row * card_height,
                card_width,
                card_height,
            )
            fill = (18, 25, 37) if (column + row) % 2 == 0 else (21, 29, 42)
            pygame.draw.rect(sheet, fill, card.inflate(-6, -6))
            pygame.draw.rect(sheet, (69, 91, 112), card.inflate(-6, -6), 2)
            _label(
                sheet,
                font,
                model.replace("_", " ").upper(),
                card.x + 15,
                card.y + 12,
            )
            _label(
                sheet,
                small_font,
                paint_label,
                card.x + 15,
                card.y + 36,
                (144, 190, 199),
            )
            paint = shared_paint or MODEL_PAINTS[model]
            sprite = pixel_art._ambient_vehicle_surface(model, paint)
            zoom = pygame.transform.scale(
                sprite,
                (sprite.get_width() * 2, sprite.get_height() * 2),
            )
            baseline = card.bottom - 20
            pygame.draw.line(
                sheet,
                (86, 96, 104),
                (card.x + 14, baseline),
                (card.right - 14, baseline),
                1,
            )
            sheet.blit(zoom, zoom.get_rect(midbottom=(card.centerx, baseline)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sheet, output_path)


def _traffic_event(theme: str) -> dict[str, object]:
    return next(
        event
        for event in pixel_art._CHAPTER_ONE_AMBIENT_EVENTS[theme]
        if event["kind"] == "traffic"
    )


def _find_preview_tick(
    camera_x: float,
    event: dict[str, object],
    model: str,
    start_tick: int,
) -> tuple[int, tuple[int, int, tuple[int, int, int], int, str]]:
    speed = max(0.01, float(event.get("speed", 1.0)))
    headway = max(
        pixel_art._AMBIENT_TRAFFIC_MIN_HEADWAY_PX,
        int(event.get("headway", pixel_art._AMBIENT_TRAFFIC_MIN_HEADWAY_PX)),
    )
    period = LOGICAL_SIZE[0] + pixel_art._AMBIENT_VEHICLE_MAX_WIDTH + headway
    search_ticks = math.ceil(period / speed) * (len(pixel_art._AMBIENT_VEHICLE_MODELS) + 2)
    fallback: tuple[int, tuple[int, int, tuple[int, int, int], int, str]] | None = None
    for tick in range(start_tick, start_tick + search_ticks):
        item = pixel_art._ambient_traffic_layout(
            LOGICAL_SIZE[0],
            camera_x,
            event,
            tick,
        )[0]
        x, _, _, _, item_model = item
        width = pixel_art._AMBIENT_VEHICLE_SIZES[item_model][0]
        center = x + width // 2
        if 390 <= center <= 505:
            if fallback is None:
                fallback = (tick, item)
            if item_model == model:
                return tick, item
    if fallback is None:
        raise RuntimeError(f"no visible traffic preview found for {event!r}")
    return fallback


def _route_camera_x(route: Mapping[str, Any], event: Mapping[str, object]) -> float:
    world_width = float(route["world_width"])
    max_camera = max(0.0, world_width - LOGICAL_SIZE[0])
    objects = tuple(
        item
        for item in route.get("physical_scene_objects", ())
        if isinstance(item, Mapping)
    )
    if objects:
        desired = float(objects[0]["world_x"]) - LOGICAL_SIZE[0] * 0.5
        event_start = float(event.get("start", 0.0))
        event_end = float(event.get("end", world_width))
        if desired + LOGICAL_SIZE[0] >= event_start and desired <= event_end:
            return max(0.0, min(max_camera, desired))
    event_midpoint = (
        float(event.get("start", 0.0))
        + float(event.get("end", world_width))
    ) * 0.5
    return max(0.0, min(max_camera, event_midpoint - LOGICAL_SIZE[0] * 0.5))


def _render_route_frame(
    route: Mapping[str, Any],
    font: pygame.font.Font,
    requested_model: str,
) -> pygame.Surface:
    theme = str(route["theme"])
    event = _traffic_event(theme)
    camera_x = _route_camera_x(route, event)
    manager = InputManager(max_players=4, discover_controllers=False)
    game = FadesGame(manager, mute=True)
    try:
        game._select_campaign_level(str(route["level_id"]))
        game.select_slots = [
            SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True),
            SelectSlot(
                {"type": "controller", "instance_id": 9001},
                character_index=1,
                confirmed=True,
            ),
        ]
        game._start_stage()
        game.camera.pan_to(camera_x, 0.0)
        game.camera_x = camera_x
        game._render_camera_x = camera_x
        game.stage_banner_timer = 0.0
        game.route_card_timer = 0.0
        for index, player in enumerate(game.players):
            player.x = camera_x + 135.0 + index * 95.0
            player.y = 286.0 + index * 17.0
            player.set_state("idle")
        for chief in game.chiefs:
            chief.x = chief.owner.x + 62.0
            chief.y = chief.owner.y + 13.0
            chief.state = "sit"

        start_tick = pixel_art._ambient_motion_tick(game.atmosphere)
        preview_tick, preview = _find_preview_tick(
            camera_x,
            event,
            requested_model,
            start_tick,
        )
        game.atmosphere.advance(max(0.0, (preview_tick - start_tick) / 30.0))
        canvas = pygame.Surface(LOGICAL_SIZE).convert()
        game.draw(canvas)

        x, y, _, _, visible_model = preview
        model_width, model_height = pixel_art._AMBIENT_VEHICLE_SIZES[visible_model]
        rect = pygame.Rect(x, y - model_height, model_width, model_height)
        pygame.draw.rect(canvas, (83, 224, 229), rect.inflate(4, 4), 1)
        pygame.draw.rect(canvas, (8, 12, 19), (4, 4, 632, 18))
        _label(
            canvas,
            font,
            (
                f"{str(route['level_id']).replace('chapter_1_', '').upper()}  "
                f"PASSING {visible_model.replace('_', ' ').upper()}  "
                f"ONE-CAR TRAFFIC / {int(event['headway'])}PX OFF-SCREEN HEADWAY"
            ),
            8,
            7,
        )
        return canvas
    finally:
        game.close()
        manager.close()


def _render_ingame_sheet(
    routes: Sequence[Mapping[str, Any]],
    output_path: Path,
    font: pygame.font.Font,
) -> None:
    width, height = LOGICAL_SIZE
    sheet = pygame.Surface((width * 3, height * 2)).convert()
    sheet.fill((8, 10, 16))
    routes_by_theme = {str(route["theme"]): route for route in routes}
    for index, (theme, model) in enumerate(INGAME_PREVIEW_SPECS):
        frame = _render_route_frame(routes_by_theme[theme], font, model)
        sheet.blit(frame, ((index % 3) * width, (index // 3) * height))
    summary = pygame.Rect(width * 2, height, width, height)
    pygame.draw.rect(sheet, (18, 25, 37), summary.inflate(-8, -8))
    pygame.draw.rect(sheet, (69, 91, 112), summary.inflate(-8, -8), 2)
    _label(sheet, font, "ALL FIVE MODELS AT 1X GAMEPLAY SCALE", summary.x + 28, summary.y + 44)
    _label(sheet, font, "ONE PASSER MAXIMUM ON SCREEN", summary.x + 28, summary.y + 82, (144, 190, 199))
    _label(sheet, font, "8+ SECONDS OF EMPTY-ROAD HEADWAY", summary.x + 28, summary.y + 108, (144, 190, 199))
    _label(sheet, font, "CYAN BOXES ARE QA MARKERS ONLY", summary.x + 28, summary.y + 146, (226, 177, 102))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(sheet, output_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else project_root / "build" / "background_traffic_qa"
    )
    manifest = _read_json(project_root / "data" / "chapter1_location_lock.json")
    routes = tuple(
        route
        for route in manifest.get("routes", ())
        if isinstance(route, Mapping)
    )
    if len(routes) != 4:
        raise ValueError("Chapter 1 traffic QA requires exactly four routes")

    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        font = pygame.font.Font(None, 18)
        font.set_bold(True)
        small_font = pygame.font.Font(None, 15)
        isolated_path = output_dir / "background_traffic_models_isolated.png"
        non_sedan_detail_path = output_dir / "background_traffic_nonsedan_detail.png"
        shading_matrix_path = output_dir / "background_traffic_shading_matrix.png"
        ingame_path = output_dir / "background_traffic_ingame.png"
        _render_isolated_sheet(project_root, isolated_path, font, small_font)
        _render_non_sedan_detail_sheet(non_sedan_detail_path, font, small_font)
        _render_shading_matrix(shading_matrix_path, font, small_font)
        _render_ingame_sheet(routes, ingame_path, small_font)
        print(isolated_path)
        print(non_sedan_detail_path)
        print(shading_matrix_path)
        print(ingame_path)
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
