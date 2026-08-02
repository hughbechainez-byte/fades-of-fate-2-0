"""Render a compact reference-versus-runtime walk comparison board."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from src.pixel_art import draw_player


def _font() -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("consola.ttf", 18)
    except OSError:
        return ImageFont.load_default()


def _label(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int]) -> None:
    draw.text(xy, text, fill=(245, 235, 222), font=_font())


def _frame_strip(path: Path, columns: int, rows: int, count: int = 12) -> Image.Image:
    source = Image.open(path).convert("RGBA")
    cell_w = source.width // columns
    cell_h = source.height // rows
    frames = [
        source.crop((index * cell_w, row * cell_h, (index + 1) * cell_w, (row + 1) * cell_h))
        for row in range(rows)
        for index in range(columns)
    ][:count]
    canvas = Image.new("RGBA", (count * cell_w, cell_h), (18, 20, 25, 255))
    for index, frame in enumerate(frames):
        canvas.alpha_composite(frame, (index * cell_w, 0))
    return canvas


def _runtime_strip(character: str, facing: int) -> Image.Image:
    frames: list[Image.Image] = []
    for pose in range(12):
        surface = pygame.Surface((128, 128), pygame.SRCALPHA)
        surface.fill((18, 20, 25, 255))
        draw_player(surface, 64, 116, 0, facing, "walk", character, pose * 2, (217, 72, 64) if character == "black_dave" else (195, 74, 124))
        raw = pygame.image.tobytes(surface, "RGBA")
        frames.append(Image.frombytes("RGBA", surface.get_size(), raw))
    canvas = Image.new("RGBA", (12 * 128, 128), (18, 20, 25, 255))
    for index, frame in enumerate(frames):
        canvas.alpha_composite(frame, (index * 128, 0))
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pygame.init()
    reference = Image.open(args.reference).convert("RGBA")
    reference.thumbnail((420, 250), Image.Resampling.NEAREST)
    dave_right = _runtime_strip("black_dave", 1)
    dave_left = _runtime_strip("black_dave", -1)
    shelly_right = _runtime_strip("shelly", 1)
    shelly_left = _runtime_strip("shelly", -1)
    target_w = 1000
    reference_h = 270
    panel_h = 180
    board = Image.new("RGBA", (target_w, reference_h + panel_h * 4 + 70), (28, 25, 31, 255))
    draw = ImageDraw.Draw(board)
    _label(draw, "REFERENCE GIF — weight, contact, passing, recovery", (18, 12))
    ref_x = (target_w - reference.width) // 2
    board.alpha_composite(reference, (ref_x, 40))
    rows = (
        ("BLACK DAVE — right-facing stride", dave_right),
        ("BLACK DAVE — left-facing stride", dave_left),
        ("SHELLY — right-facing stride", shelly_right),
        ("SHELLY — left-facing stride", shelly_left),
    )
    for row, (label, strip) in enumerate(rows):
        top = reference_h + panel_h * row
        _label(draw, label, (18, top + 12))
        strip.thumbnail((target_w - 36, panel_h - 45), Image.Resampling.NEAREST)
        board.alpha_composite(strip, ((target_w - strip.width) // 2, top + 40))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    board.convert("RGB").save(args.output)
    pygame.quit()


if __name__ == "__main__":
    main()
