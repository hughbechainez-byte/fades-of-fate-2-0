"""Render projection calibration captures for route cameras and reference samples."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
from typing import Any, Mapping, Sequence
import os
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # type: ignore

from src.config import LOGICAL_SIZE, load_gameplay
from src.world_engine import BeatEmUpProjection, ProjectionConfig, WorldPoint
from src import pixel_art


CHECKPOINTS = (0.0, 0.25, 0.5, 0.75, 1.0)
HIGHLIGHT = {
    "far": (120, 170, 255),
    "middle": (126, 255, 165),
    "near": (255, 193, 95),
}


def _campaign_levels(gameplay: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    campaign = gameplay.get("campaign", {})
    chapters = campaign.get("chapters", ())
    levels: list[dict[str, Any]] = []
    if not isinstance(chapters, Sequence) or isinstance(chapters, (str, bytes)):
        return tuple(levels)
    for chapter in chapters:
        if not isinstance(chapter, Mapping):
            continue
        for level in chapter.get("levels", ()):
            if isinstance(level, Mapping):
                levels.append(dict(level))
    return tuple(levels)


def _build_projection(gameplay: Mapping[str, Any]) -> tuple[BeatEmUpProjection, Mapping[str, Any], Mapping[str, Any]]:
    engine = gameplay.get("engine", {})
    if not isinstance(engine, Mapping):
        raise ValueError("engine must be an object")
    projection_profiles = gameplay.get("projection_profiles", {})
    if not projection_profiles:
        projection_profiles = gameplay.get("engine", {}).get("projection_profiles", {})
    if not isinstance(projection_profiles, Mapping):
        raise ValueError("projection_profiles must be an object")

    projection = engine.get("projection", {})
    if not isinstance(projection, Mapping):
        raise ValueError("engine.projection must be an object")
    profile_id = str(projection.get("profile_id", "")).strip()
    profile = projection_profiles.get(profile_id) if profile_id else None
    if not isinstance(profile, Mapping):
        raise ValueError(f"engine.projection profile '{profile_id or '<missing>'}' is required")

    merged = dict(profile)
    merged.update({key: value for key, value in projection.items() if key != "profile_id"})
    projection_cfg = BeatEmUpProjection(
        ProjectionConfig(
            mode=str(merged.get("mode", "orthographic")),
            screen_origin_x=float(merged.get("screen_origin_x", 0.0)),
            floor_screen_y=float(merged.get("screen_y_origin", merged.get("floor_screen_y", 280.0))),
            pixels_per_world_x=float(merged.get("world_x_scale", merged.get("pixels_per_world_x", 1.0))),
            pixels_per_depth=float(merged.get("depth_scale", merged.get("pixels_per_depth", 1.0))),
            pixels_per_elevation=float(merged.get("elevation_scale", merged.get("pixels_per_elevation", 1.0))),
            oblique_x_per_depth=float(merged.get("oblique_x_shear", merged.get("oblique_x_per_depth", 0.0))),
            pixel_snap=bool(merged.get("pixel_snap", True)),
        )
    )
    return projection_cfg, merged, profile


def _draw_ruler(
    surface: pygame.Surface,
    projection: BeatEmUpProjection,
    camera_x: float,
    camera_depth: float,
    rails: Mapping[str, float],
) -> None:
    width, height = surface.get_size()
    pygame.draw.line(surface, (38, 52, 76), (0, projection.config.floor_screen_y), (width, projection.config.floor_screen_y), 2)
    for depth in rails.values():
        rail_points: list[tuple[int, int]] = []
        for point in range(-80, width + 80, 32):
            world_x = camera_x + point
            projected = projection.project(WorldPoint(world_x, float(depth)), camera_x=camera_x, camera_depth=camera_depth)
            x = int(round(projected.x))
            y = int(round(projected.y))
            if 0 <= x < width and 0 <= y < height:
                rail_points.append((x, y))
        for start, end in zip(rail_points, rail_points[1:]):
            pygame.draw.line(surface, (80, 125, 160), start, end, 1)
    for offset in range(-100, width + 101, 100):
        left_world = camera_x + offset
        top = projection.project(WorldPoint(left_world, max(rails.values())), camera_x=camera_x, camera_depth=camera_depth)
        bottom = projection.project(WorldPoint(left_world, min(rails.values())), camera_x=camera_x, camera_depth=camera_depth)
        pygame.draw.line(
            surface,
            (73, 105, 130),
            (int(round(top.x)), int(round(top.y))),
            (int(round(bottom.x)), int(round(bottom.y))),
            1,
        )


def _draw_reference_object(
    surface: pygame.Surface,
    projection: BeatEmUpProjection,
    camera_x: float,
    camera_depth: float,
    world_x: float,
    depth: float,
    color: tuple[int, int, int],
    label: str,
    profile: Mapping[str, Any],
    marker_x_offset: int,
) -> dict[str, Any]:
    _, height = surface.get_size()
    point = projection.project(WorldPoint(world_x, depth), camera_x=camera_x, camera_depth=camera_depth)
    center_x = int(round(point.x + marker_x_offset))
    center_y = int(round(point.y))

    dave_rect = pixel_art.draw_player(
        surface,
        center_x,
        center_y,
        0,
        1,
        "idle",
        "black_dave",
        0,
        (217, 72, 64),
    )
    shelly_rect = pixel_art.draw_player(
        surface,
        center_x + 26,
        center_y + 1,
        0,
        1,
        "idle",
        "shelly",
        0,
        (195, 74, 124),
    )
    chief_rect = pixel_art.draw_chief(surface, center_x + 56, center_y + 2, 0, -1, "idle", 0)
    enemy_rect = pixel_art.draw_enemy(
        surface,
        center_x + 86,
        center_y,
        0,
        1,
        "idle",
        "security",
        0,
        tint=color,
    )

    ref = profile.get("reference_physical_dimensions", {})
    adult_ratio = float(dave_rect.height or 1)
    door_ratio = float(ref.get("door_height_m", 0.0)) / float(ref.get("neutral_adult_height_m", 1.0))
    sedan_ratio = float(ref.get("sedan_roof_height_m", 0.0)) / float(ref.get("neutral_adult_height_m", 1.0))
    door_height = max(1, int(round(adult_ratio * door_ratio)))
    sedan_height = max(1, int(round(adult_ratio * sedan_ratio)))
    pygame.draw.rect(surface, (185, 168, 132), (center_x + 116, center_y - door_height + 8, 9, door_height), 2)
    pygame.draw.rect(surface, (142, 136, 123), (center_x + 128, center_y - sedan_height + 4, 30, sedan_height), 0)
    pygame.draw.line(surface, (208, 215, 230), (center_x + 6, center_y + 42), (center_x + 66, center_y + 42), 3)
    pygame.draw.rect(surface, (88, 120, 74), (center_x - 12, center_y + 18, 22, 20), 0)
    pygame.draw.polygon(surface, (90, 132, 44), [(center_x + 20, center_y + 4), (center_x + 28, center_y + 20), (center_x + 31, center_y + 38), (center_x + 16, center_y + 24)])
    pygame.draw.rect(surface, color, (center_x + 32, center_y + 4, 2, 45), 1)
    pygame.draw.line(
        surface,
        (255, 255, 255),
        (center_x + 2, int(round(point.y))),
        (center_x + 2, height + 4),
        1,
    )

    font = pygame.font.Font(None, 12)
    sample = font.render(label, False, color)
    surface.blit(sample, (center_x - 20, center_y - 17))
    return {
        "label": label,
        "world_depth": depth,
        "screen_xy": [int(round(point.x)), int(round(point.y))],
        "actors": {
            "dave": {"height_px": int(dave_rect.height)},
            "shelly": {"height_px": int(shelly_rect.height)},
            "chief": {"height_px": int(chief_rect.height)},
            "enemy": {"height_px": int(enemy_rect.height)},
            "door_height_px": door_height,
            "sedan_roof_height_px": sedan_height,
            "curb_px": 3,
            "parking_stall_px": 20,
            "planter_px": 22,
            "light_pole_px": 46,
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=Path("build") / "projection-calibration")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    gameplay = load_gameplay()
    projection, merged_projection, profile = _build_projection(gameplay)
    profile_id = str(gameplay.get("engine", {}).get("projection", {}).get("profile_id", ""))
    levels = _campaign_levels(gameplay)
    rails = profile.get("playable_depth_rails", {})
    camera_depth = float(merged_projection.get("depth_origin", merged_projection.get("screen_y_origin", 280.0)))

    width, height = LOGICAL_SIZE

    results: list[dict[str, Any]] = []
    pygame.init()
    font = pygame.font.Font(None, 13)
    font.set_bold(True)
    pygame.display.set_mode((1, 1))
    try:
        for level in levels:
            if not isinstance(level, Mapping):
                continue
            level_id = str(level.get("id"))
            stage_width = float(level.get("stage_width", 0))
            theme = str(level.get("background_theme", "legacy_second_street"))
            if stage_width <= 0:
                continue
            max_camera = max(0.0, stage_width - width)
            for index, fraction in enumerate(CHECKPOINTS):
                camera_x = float(max_camera * fraction)
                surface = pygame.Surface((width, height)).convert()
                pixel_art.draw_stage_background(surface, camera_x, stage_width, theme=theme)

                far = float(rails.get("far", 235))
                middle = float(rails.get("middle", 280))
                near = float(rails.get("near", 326))
                _draw_ruler(surface, projection, camera_x, camera_depth, {"far": far, "middle": middle, "near": near})

                sample_world_x = float(camera_x + width * 0.38)
                sample_results: list[dict[str, Any]] = []
                samples = (("far", far), ("middle", middle), ("near", near))
                for sample_index, (label, depth) in enumerate(samples):
                    sample_results.append(
                        _draw_reference_object(
                            surface,
                            projection,
                            camera_x,
                            camera_depth,
                            sample_world_x + sample_index * 12.0,
                            float(depth),
                            HIGHLIGHT[label],
                            label,
                            merged_projection,
                            marker_x_offset=sample_index * 10,
                        )
                    )

                banner = font.render(
                    f"{level_id.upper()}  {fraction:.0%}  CAM {int(round(camera_x))}",
                    False,
                    (255, 244, 208),
                )
                pygame.draw.rect(surface, (12, 10, 16), (6, 6, banner.get_width() + 8, banner.get_height() + 4))
                surface.blit(banner, (8, 8))

                output_png = output_dir / f"{level_id}_{int(fraction * 100):03d}_projection_calibration.png"
                pygame.image.save(surface, output_png)

                reference = merged_projection.get("reference_physical_dimensions", {})
                adult_px = sample_results[0]["actors"]["dave"]["height_px"] if sample_results else 1
                adult_physical_m = float(reference.get("neutral_adult_height_m", 1.0))
                measurements = {}
                if adult_px:
                    measurements["door_ratio"] = sample_results[0]["actors"]["door_height_px"] / adult_px
                    measurements["sedan_ratio"] = sample_results[0]["actors"]["sedan_roof_height_px"] / adult_px

                results.append(
                    {
                        "level_id": level_id,
                        "checkpoint_index": index,
                        "fraction": fraction,
                        "camera_x": int(round(camera_x)),
                        "sha256": hashlib.sha256(surface.get_buffer().raw).hexdigest(),
                        "samples": sample_results,
                        "file": str(output_png),
                        "reference_physical_dimensions_m": {
                            "neutral_adult": adult_physical_m,
                            "door": reference.get("door_height_m"),
                            "sedan": reference.get("sedan_roof_height_m"),
                        },
                        "measured_ratios": measurements,
                    }
                )

        report = {
            "schema_version": 1,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "projection_profile_id": profile_id,
            "projection_profile": {
                "mode": merged_projection.get("mode"),
                "depth_rails": {key: float(rails[key]) for key in ("far", "middle", "near") if key in rails},
                "logical_resolution": list(LOGICAL_SIZE),
            },
            "locations": results,
            "reference_ratio_targets": {
                "sedan_over_adult": [0.70, 0.90],
                "door_over_adult": [1.05, 1.20],
            },
            "status": "complete",
        }
        report_path = output_dir / "projection_calibration_report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(report_path)
        return 0
    finally:
        pygame.quit()


if __name__ == "__main__":
    raise SystemExit(main())
