"""Render production-style GIF previews for Black Dave's new combat cels."""

from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from PIL import Image
import pygame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src import pixel_art  # noqa: E402
from src.animation_manifest import clip_for  # noqa: E402


SIZE = (640, 360)
GROUND_Y = 302


def _frame(state: str, phase: int) -> Image.Image:
    surface = pygame.Surface(SIZE)
    surface.fill((22, 29, 45))
    pygame.draw.rect(surface, (30, 42, 60), (0, 230, SIZE[0], 72))
    pygame.draw.rect(surface, (19, 24, 36), (0, GROUND_Y, SIZE[0], SIZE[1] - GROUND_Y))
    pygame.draw.line(surface, (64, 88, 112), (0, GROUND_Y), (SIZE[0], GROUND_Y), 2)
    pygame.draw.line(surface, (44, 58, 78), (0, GROUND_Y + 20), (SIZE[0], GROUND_Y + 20), 1)
    clip = clip_for("black_dave", state)
    pixel_art.draw_player(
        surface,
        320,
        GROUND_Y,
        0,
        1,
        state,
        "black_dave",
        phase * clip.hold,
        "#ef5547",
    )
    return Image.frombytes("RGB", SIZE, pygame.image.tobytes(surface, "RGB"))


def _write(destination: Path, states: tuple[str, ...]) -> None:
    frames = [_frame(state, phase) for state in states for phase in range(clip_for("black_dave", state).frame_count)]
    destination.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        destination,
        save_all=True,
        append_images=frames[1:],
        duration=70,
        loop=0,
        optimize=False,
        disposal=2,
    )
    print(f"Wrote {destination.relative_to(PROJECT_ROOT)} ({len(frames)} production frames)")


def main() -> None:
    pygame.init()
    try:
        output = PROJECT_ROOT / "build"
        _write(output / "black_dave_punch_combo_preview.gif", ("attack_1", "attack_2", "attack_3"))
        _write(output / "black_dave_shockwave_kicks_preview.gif", ("attack_4",))
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
