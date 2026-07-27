"""Render Chapter 1 location-lock checkpoints and diagnostic overlays."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
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
from tools.build_chapter1_location_art import (  # noqa: E402
    HEIGHT as PANORAMA_HEIGHT,
    PANEL_SPECS,
    cover_crop_geometry,
)
from tools.validate_chapter1 import build_location_lock_report  # noqa: E402


CHECKPOINTS = (0.0, 0.25, 0.5, 0.75, 1.0)
CONFIDENCE_COLORS = {
    "high": (94, 242, 155),
    "medium": (255, 205, 76),
    "low": (255, 112, 112),
}
RAIL_COLOR = (65, 215, 255)
OBSTACLE_COLOR = (255, 92, 193)
CAMERA_ZONE_COLOR = (177, 129, 255)
FEATURE_COLOR = (255, 151, 66)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _gameplay_levels(gameplay: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    campaign = gameplay.get("campaign", {})
    chapters = campaign.get("chapters", ()) if isinstance(campaign, Mapping) else ()
    if not isinstance(chapters, Sequence) or isinstance(chapters, (str, bytes)):
        return result
    for chapter in chapters:
        if not isinstance(chapter, Mapping):
            continue
        levels = chapter.get("levels", ())
        if not isinstance(levels, Sequence) or isinstance(levels, (str, bytes)):
            continue
        for level in levels:
            if isinstance(level, Mapping):
                result[str(level.get("id", ""))] = level
    return result


def _draw_actor_scale(frame: pygame.Surface) -> None:
    """Place the production heroes and Chief in every route checkpoint."""

    pixel_art.draw_player(
        frame,
        270,
        304,
        0,
        1,
        "idle",
        "black_dave",
        0,
        (217, 72, 64),
    )
    pixel_art.draw_player(
        frame,
        350,
        307,
        0,
        1,
        "idle",
        "shelly",
        0,
        (195, 74, 124),
    )
    pixel_art.draw_chief(frame, 425, 311, 0, 1, "idle", 0)


def _draw_frame_label(
    frame: pygame.Surface,
    font: pygame.font.Font,
    route: Mapping[str, Any],
    fraction: float,
    camera_x: int,
) -> None:
    label = font.render(
        (
            f"{str(route['level_id']).replace('chapter_1_', '').upper()}  "
            f"{fraction:.0%}  CAMERA {camera_x}"
        ),
        False,
        (255, 244, 208),
    )
    pygame.draw.rect(
        frame,
        (12, 16, 28),
        (4, 4, label.get_width() + 8, label.get_height() + 4),
    )
    frame.blit(label, (8, 6))


def _render_checkpoint(
    route: Mapping[str, Any],
    camera_x: int,
    font: pygame.font.Font,
    fraction: float,
) -> pygame.Surface:
    width, height = LOGICAL_SIZE
    frame = pygame.Surface((width, height)).convert()
    world_width = int(route["world_width"])
    theme = str(route["theme"])
    pixel_art.draw_stage_background(
        frame,
        camera_x,
        world_width,
        theme=theme,
    )
    _draw_actor_scale(frame)
    pixel_art.draw_stage_foreground(
        frame,
        camera_x,
        world_width,
        theme=theme,
    )
    _draw_frame_label(frame, font, route, fraction, camera_x)
    return frame


def _draw_overlay(
    frame: pygame.Surface,
    route: Mapping[str, Any],
    gameplay_level: Mapping[str, Any],
    camera_x: int,
    font: pygame.font.Font,
) -> None:
    """Draw all location and gameplay registration in world projection."""

    width, height = frame.get_size()
    diagnostic = pygame.Surface(frame.get_size(), pygame.SRCALPHA)

    geometry = gameplay_level.get("stage_geometry", {})
    if not isinstance(geometry, Mapping):
        geometry = {}
    rails = geometry.get("rails", ())
    if isinstance(rails, Sequence) and not isinstance(rails, (str, bytes)):
        for rail in rails:
            if not isinstance(rail, Mapping):
                continue
            left = int(round(float(rail["start_x"]) - camera_x))
            right = int(round(float(rail["end_x"]) - camera_x))
            visible_left = max(0, left)
            visible_right = min(width - 1, right)
            if visible_right < visible_left:
                continue
            far_depth = int(round(float(rail["far_depth"])))
            near_depth = int(round(float(rail["near_depth"])))
            pygame.draw.line(
                diagnostic,
                (*RAIL_COLOR, 225),
                (visible_left, far_depth),
                (visible_right, far_depth),
                2,
            )
            pygame.draw.line(
                diagnostic,
                (*RAIL_COLOR, 225),
                (visible_left, near_depth),
                (visible_right, near_depth),
                2,
            )
            pygame.draw.line(
                diagnostic,
                (*RAIL_COLOR, 110),
                (visible_left, far_depth),
                (visible_left, near_depth),
                1,
            )

    obstacles = geometry.get("obstacles", ())
    if isinstance(obstacles, Sequence) and not isinstance(obstacles, (str, bytes)):
        for obstacle in obstacles:
            if not isinstance(obstacle, Mapping):
                continue
            sx = int(round(float(obstacle["x"]) - camera_x))
            half_width = max(1, int(round(float(obstacle["half_width"]))))
            half_depth = max(1, int(round(float(obstacle["half_depth"]))))
            depth = int(round(float(obstacle["depth"])))
            rect = pygame.Rect(
                sx - half_width,
                depth - half_depth,
                half_width * 2,
                half_depth * 2,
            )
            pygame.draw.rect(diagnostic, (*OBSTACLE_COLOR, 72), rect)
            pygame.draw.rect(diagnostic, (*OBSTACLE_COLOR, 245), rect, 2)
            if rect.right >= 0 and rect.left < width:
                text = font.render(
                    f"OBS {obstacle.get('id', '?')}",
                    False,
                    OBSTACLE_COLOR,
                )
                diagnostic.blit(text, (max(2, rect.left), max(116, rect.top - 13)))

    camera_zones = geometry.get("camera_zones", ())
    if isinstance(camera_zones, Sequence) and not isinstance(
        camera_zones,
        (str, bytes),
    ):
        for row, zone in enumerate(camera_zones):
            if not isinstance(zone, Mapping):
                continue
            left = int(round(float(zone["start_x"]) - camera_x))
            right = int(round(float(zone["end_x"]) - camera_x))
            visible_left = max(0, left)
            visible_right = min(width - 1, right)
            if visible_right < visible_left:
                continue
            y = 25 + (row % 3) * 10
            pygame.draw.line(
                diagnostic,
                (*CAMERA_ZONE_COLOR, 220),
                (visible_left, y),
                (visible_right, y),
                3,
            )
            zone_text = font.render(
                f"CAM {zone.get('name', '?')}",
                False,
                CAMERA_ZONE_COLOR,
            )
            diagnostic.blit(zone_text, (visible_left + 2, y + 2))

    features = route.get("registered_features", ())
    if isinstance(features, Sequence) and not isinstance(features, (str, bytes)):
        for feature in features:
            if not isinstance(feature, Mapping):
                continue
            sx = int(round(float(feature["world_x"]) - camera_x))
            if -2 <= sx <= width + 2:
                pygame.draw.line(
                    diagnostic,
                    (*FEATURE_COLOR, 230),
                    (sx, 98),
                    (sx, height - 8),
                    1,
                )
                marker = font.render(
                    f"ART {feature.get('id', '?')}",
                    False,
                    FEATURE_COLOR,
                )
                diagnostic.blit(marker, (max(2, min(width - marker.get_width() - 2, sx + 2)), 99))

    landmarks = route.get("landmarks", ())
    if isinstance(landmarks, Sequence) and not isinstance(landmarks, (str, bytes)):
        visible_index = 0
        for landmark in landmarks:
            if not isinstance(landmark, Mapping):
                continue
            sx = int(round(float(landmark["world_x"]) - camera_x))
            if not -4 <= sx <= width + 4:
                continue
            confidence = str(landmark.get("confidence", "low")).lower()
            color = CONFIDENCE_COLORS.get(confidence, CONFIDENCE_COLORS["low"])
            pygame.draw.line(
                diagnostic,
                (*color, 245),
                (sx, 55),
                (sx, height - 4),
                2,
            )
            text = font.render(
                f"{landmark.get('id', '?')} [{confidence.upper()}]",
                False,
                color,
            )
            text_y = 58 + (visible_index % 4) * 13
            text_x = max(2, min(width - text.get_width() - 2, sx + 3))
            diagnostic.blit(text, (text_x, text_y))
            visible_index += 1

    legend = font.render(
        "LANDMARK + CONFIDENCE | ART FEATURE | RAIL | OBSTACLE | CAMERA ZONE",
        False,
        (250, 250, 250),
    )
    pygame.draw.rect(
        diagnostic,
        (8, 10, 18, 220),
        (3, height - legend.get_height() - 7, legend.get_width() + 8, legend.get_height() + 4),
    )
    diagnostic.blit(legend, (7, height - legend.get_height() - 5))
    frame.blit(diagnostic, (0, 0))


def _render_gameplay_screenshot(
    output_path: Path,
    route: Mapping[str, Any],
) -> dict[str, Any]:
    """Render a normal runtime game frame from the route midpoint."""

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
        max_camera = max(0.0, float(route["world_width"]) - LOGICAL_SIZE[0])
        camera_x = max_camera * 0.5
        game.camera.pan_to(camera_x, 0.0)
        game.camera_x = camera_x
        game._render_camera_x = camera_x
        game.stage_banner_timer = 0.0
        game.route_card_timer = 0.0
        for index, player in enumerate(game.players):
            player.x = camera_x + 275.0 + index * 80.0
            player.y = 274.0 + index * 18.0
            player.set_state("idle")
        for chief in game.chiefs:
            chief.x = chief.owner.x + 64.0
            chief.y = chief.owner.y + 14.0
            chief.state = "sit"
        canvas = pygame.Surface(LOGICAL_SIZE).convert()
        game.draw(canvas)
        pygame.image.save(canvas, output_path)
        return {
            "level_id": str(route["level_id"]),
            "path": str(output_path),
            "camera_x": int(round(camera_x)),
            "sha256": hashlib.sha256(
                pygame.image.tobytes(canvas, "RGB", False)
            ).hexdigest(),
            "actors": len(game.players) + len(game.chiefs),
        }
    finally:
        game.close()
        manager.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--visual-review-approved",
        action="store_true",
        help="Record that the generated sheets were compared with the dated references.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    build_dir = project_root / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    manifest = _read_json(project_root / "data" / "chapter1_location_lock.json")
    gameplay = _read_json(project_root / "data" / "gameplay.json")
    routes = tuple(
        route for route in manifest.get("routes", ())
        if isinstance(route, Mapping)
    )
    gameplay_by_id = _gameplay_levels(gameplay)

    pygame.init()
    pygame.display.set_mode((1, 1))
    width, height = LOGICAL_SIZE
    font = pygame.font.Font(None, 14)
    font.set_bold(True)
    normal_sheet = pygame.Surface((width * len(CHECKPOINTS), height * len(routes))).convert()
    overlay_sheet = pygame.Surface(normal_sheet.get_size()).convert()
    max_seams = max(
        (len(PANEL_SPECS[str(route["theme"])]) - 1 for route in routes),
        default=0,
    )
    seam_sheet = pygame.Surface(
        (width * max(1, max_seams), height * len(routes))
    ).convert()
    seam_sheet.fill((15, 16, 20))
    checkpoint_results: list[dict[str, Any]] = []
    seam_results: list[dict[str, Any]] = []
    gameplay_screenshots: list[dict[str, Any]] = []
    try:
        for row, route in enumerate(routes):
            world_width = int(route["world_width"])
            max_camera = max(0, world_width - width)
            route_hashes: list[str] = []
            for column, fraction in enumerate(CHECKPOINTS):
                camera_x = int(round(max_camera * fraction))
                frame = _render_checkpoint(route, camera_x, font, fraction)
                frame_hash = hashlib.sha256(
                    pygame.image.tobytes(frame, "RGB", False)
                ).hexdigest()
                route_hashes.append(frame_hash)
                normal_sheet.blit(frame, (column * width, row * height))
                overlay_frame = frame.copy()
                _draw_overlay(
                    overlay_frame,
                    route,
                    gameplay_by_id.get(str(route["level_id"]), {}),
                    camera_x,
                    font,
                )
                overlay_sheet.blit(
                    overlay_frame,
                    (column * width, row * height),
                )
                checkpoint_results.append(
                    {
                        "level_id": str(route["level_id"]),
                        "fraction": fraction,
                        "camera_x": camera_x,
                        "sha256": frame_hash,
                    }
                )
            checkpoint_results.append(
                {
                    "level_id": str(route["level_id"]),
                    "checkpoint_hashes_unique": len(set(route_hashes)) == len(route_hashes),
                }
            )
            seam_world_x = 0
            specs = PANEL_SPECS[str(route["theme"])]
            for seam_index, spec in enumerate(specs[:-1]):
                seam_world_x += spec.width
                seam_camera_x = max(
                    0,
                    min(max_camera, seam_world_x - width // 2),
                )
                seam_frame = _render_checkpoint(
                    route,
                    seam_camera_x,
                    font,
                    seam_world_x / world_width,
                )
                seam_sheet.blit(
                    seam_frame,
                    (seam_index * width, row * height),
                )
                seam_results.append(
                    {
                        "level_id": str(route["level_id"]),
                        "seam_world_x": seam_world_x,
                        "camera_x": seam_camera_x,
                        "sha256": hashlib.sha256(
                            pygame.image.tobytes(seam_frame, "RGB", False)
                        ).hexdigest(),
                    }
                )
            screenshot_path = (
                build_dir
                / f"chapter1_location_lock_{str(route['level_id'])}_gameplay.png"
            )
            gameplay_screenshots.append(
                _render_gameplay_screenshot(screenshot_path, route)
            )

        qa_path = build_dir / "chapter1_location_lock_qa.png"
        overlay_path = build_dir / "chapter1_location_lock_overlay_qa.png"
        seam_path = build_dir / "chapter1_location_lock_seam_qa.png"
        pygame.image.save(normal_sheet, qa_path)
        pygame.image.save(normal_sheet, build_dir / "route_worldlocked_qa.png")
        pygame.image.save(overlay_sheet, overlay_path)
        pygame.image.save(seam_sheet, seam_path)

        validation = build_location_lock_report(project_root)
        sources: list[dict[str, Any]] = []
        authoring_panels: list[dict[str, Any]] = []
        for route in routes:
            for side_field in ("landmarks", "opposite_side_landmarks"):
                for landmark in route.get(side_field, ()):
                    if not isinstance(landmark, Mapping):
                        continue
                    sources.append(
                        {
                            "level_id": route.get("level_id"),
                            "side": "playable_west" if side_field == "landmarks" else "opposite_east",
                            "id": landmark.get("id"),
                            "address": landmark.get("address"),
                            "source_date": landmark.get("source_date"),
                            "imagery_date": landmark.get("imagery_date"),
                            "access_date": landmark.get("access_date"),
                            "source_urls": landmark.get("source_urls"),
                            "view_direction": landmark.get("view_direction"),
                            "confidence": landmark.get("confidence"),
                        }
                    )
            panel_cursor = 0
            for spec in PANEL_SPECS[str(route["theme"])]:
                source_path = project_root / spec.source
                source_image = pygame.image.load(str(source_path))
                source_size = (
                    spec.source_crop[2:4]
                    if spec.source_crop is not None
                    else source_image.get_size()
                )
                scale, scaled_size, crop = cover_crop_geometry(
                    source_size,
                    (spec.width, PANORAMA_HEIGHT),
                    focal_x=spec.focal_x,
                    focal_y=spec.focal_y,
                )
                authoring_panels.append(
                    {
                        "level_id": route.get("level_id"),
                        "source_asset": spec.source,
                        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                        "source_size": list(source_image.get_size()),
                        "target_world_range": [panel_cursor, panel_cursor + spec.width],
                        "target_size": [spec.width, PANORAMA_HEIGHT],
                        "anchor_ids": list(spec.anchor_ids),
                        "uniform_cover_scale": scale,
                        "scaled_size": list(scaled_size),
                        "crop_rect": [crop.x, crop.y, crop.width, crop.height],
                    }
                )
                panel_cursor += spec.width
        unique_checks_pass = all(
            item.get("checkpoint_hashes_unique", True)
            for item in checkpoint_results
        )
        visual_review = {
            "required": True,
            "status": (
                "completed_by_codex_visual_review"
                if args.visual_review_approved
                else "pending_visual_review"
            ),
            "criteria": {
                "northbound_west_side_orientation_clear": bool(args.visual_review_approved),
                "parking_setbacks_and_driveways_visible": bool(args.visual_review_approved),
                "madison_i8_broadway_and_awaken_transitions_clear": bool(
                    args.visual_review_approved
                ),
                "landmark_massing_and_neighbor_context_distinct": bool(
                    args.visual_review_approved
                ),
                "actors_remain_legible_at_environment_scale": bool(
                    args.visual_review_approved
                ),
                "no_generic_fantasy_or_placeholder_scenery": bool(
                    args.visual_review_approved
                ),
                "no_anisotropic_scaling_or_miniature_traffic": bool(
                    args.visual_review_approved
                ),
                "panel_handoffs_are_structurally_masked": bool(
                    args.visual_review_approved
                ),
            },
            "note": (
                "The all-route actor and overlay sheets were visually inspected "
                "against the dated manifest references."
                if args.visual_review_approved
                else (
                    "Automated checks prove source metadata, registration, dimensions, "
                    "camera movement, and distinct views; geographic visual resemblance "
                    "still requires comparison with the dated references."
                )
            ),
        }
        report = {
            "schema_version": 2,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "classification": "automated_location_source_and_render_validation",
            "automated_validation": validation,
            "checkpoint_results": checkpoint_results,
            "seam_results": seam_results,
            "gameplay_screenshots": gameplay_screenshots,
            "mandatory_references": manifest.get("mandatory_references", ()),
            "sources": sources,
            "authoring_panels": authoring_panels,
            "artifacts": {
                "normal_sheet": str(qa_path),
                "overlay_sheet": str(overlay_path),
                "seam_sheet": str(seam_path),
            },
            "manual_reference_comparison": visual_review,
            "passed": bool(validation["passed"] and unique_checks_pass),
        }
        report_path = build_dir / "chapter1_location_sources_report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(qa_path)
        print(overlay_path)
        print(seam_path)
        print(report_path)
        return 0 if report["passed"] else 1
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
