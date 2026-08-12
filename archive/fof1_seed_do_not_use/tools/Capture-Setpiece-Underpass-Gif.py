#!/usr/bin/env python3
"""Capture an in-engine GIF of the ground-up underpass setpiece (no characters).

Uses the real runtime path:
  location-locked setpiece route -> draw_stage_background + atmosphere + ambient
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.atmosphere import AtmosphereState  # noqa: E402
from src.config import LOGICAL_SIZE  # noqa: E402
from src import pixel_art  # noqa: E402

THEME = "underpass_setpiece_v1"
PROFILE = "i8_underpass_dimming"
DEFAULT_DESKTOP = Path("/mnt/c/Users/blowb/Desktop/Fades of Fate 2.0 - Review Photos")


def _surface_to_pil(surface: pygame.Surface) -> Image.Image:
    raw = pygame.image.tobytes(surface, "RGB")
    return Image.frombytes("RGB", surface.get_size(), raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--frames", type=int, default=48)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--desktop", type=Path, default=DEFAULT_DESKTOP)
    parser.add_argument("--no-desktop", action="store_true")
    args = parser.parse_args()

    root = args.project_root.resolve()
    os.chdir(root)
    pygame.init()
    pygame.display.set_mode((1, 1))

    route = pixel_art._location_route(THEME)
    if route is None:
        raise SystemExit(f"setpiece theme missing: {THEME}")
    world_width = int(route["world_width"])
    max_cam = max(0, world_width - LOGICAL_SIZE[0])

    # Clear caches so new assets are loaded cleanly.
    pixel_art._LOCATION_ART_CACHE.clear()
    pixel_art.clear_stage_background_caches() if hasattr(pixel_art, "clear_stage_background_caches") else None
    from src import backdrop

    backdrop.clear_backdrop_caches()

    atm = AtmosphereState.new(seed=20260812, profile_id=PROFILE)
    # Advance a bit so haze/phases are live.
    for _ in range(60):
        atm.advance(1.0 / 30.0)

    frame_count = max(12, args.frames)
    duration = max(1.0, float(args.seconds))
    pil_frames: list[Image.Image] = []
    local_dir = root / "build" / "setpiece_review" / "underpass_engine_gif"
    local_dir.mkdir(parents=True, exist_ok=True)

    for index in range(frame_count):
        t = index / max(1, frame_count - 1)
        # Slow pan across the fight floor + continuous atmosphere time.
        camera_x = max_cam * (0.15 + 0.70 * t)
        atm.advance(duration / frame_count)

        frame = pygame.Surface(LOGICAL_SIZE)
        pixel_art.draw_stage_background(
            frame,
            camera_x,
            world_width,
            0.0,
            theme=THEME,
            atmosphere=atm,
        )
        # Near strip only if available without chunk topology.
        try:
            pixel_art.draw_stage_foreground(
                frame,
                camera_x,
                world_width,
                0.0,
                theme=THEME,
            )
        except Exception:
            # Setpiece has no StageWorld chunks; background + ambient is enough.
            pass

        pil = _surface_to_pil(frame)
        pil_frames.append(pil)
        pil.save(local_dir / f"frame_{index:03d}.png")

    gif_path = local_dir / "underpass_setpiece_v1_engine.gif"
    duration_ms = max(40, int(1000 / max(1, args.fps)))
    pil_frames[0].save(
        gif_path,
        save_all=True,
        append_images=pil_frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=False,
    )

    desktop_gif = None
    if not args.no_desktop and str(args.desktop).strip():
        desk = Path(args.desktop)
        desk.mkdir(parents=True, exist_ok=True)
        desktop_gif = desk / "09_underpass_setpiece_ENGINE.gif"
        pil_frames[0].save(
            desktop_gif,
            save_all=True,
            append_images=pil_frames[1:],
            duration=duration_ms,
            loop=0,
            optimize=False,
        )
        # Still mid-frame for quick open
        mid = pil_frames[len(pil_frames) // 2]
        mid.save(desk / "09_underpass_setpiece_ENGINE_still.png")
        (desk / "SETPIECE_ENGINE_GIF.txt").write_text(
            "\n".join(
                [
                    "In-engine underpass setpiece GIF",
                    "================================",
                    "",
                    f"Theme: {THEME}",
                    "Path: draw_stage_background + atmosphere + ambient life",
                    "No characters / enemies / FoF1 traffic vehicles.",
                    "Wetter road + denser mist enabled for this setpiece.",
                    "",
                    "Open: 09_underpass_setpiece_ENGINE.gif",
                    f"Local: {gif_path}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "ok": True,
                "theme": THEME,
                "world_width": world_width,
                "frames": frame_count,
                "fps": args.fps,
                "gif": str(gif_path),
                "desktop_gif": str(desktop_gif) if desktop_gif else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
