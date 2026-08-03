"""Render animated Dave walk/reference comparisons for visual QA."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import pixel_art


def _load_reference(path: Path) -> tuple[list[Image.Image], list[int]]:
    source = Image.open(path)
    frames: list[Image.Image] = []
    durations: list[int] = []
    for index in range(getattr(source, "n_frames", 1)):
        source.seek(index)
        frames.append(source.convert("RGBA").copy())
        durations.append(max(40, min(200, int(source.info.get("duration", 80) or 80))))
    return frames, durations


def _runtime_frames(count: int) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for tick in range(count):
        surface = pygame.Surface((192, 192), pygame.SRCALPHA)
        surface.fill((18, 20, 26, 255))
        pixel_art.draw_player(surface, 96, 170, 0, 1, "walk", "black_dave", tick, (217, 72, 64))
        frames.append(Image.frombytes("RGBA", surface.get_size(), pygame.image.tobytes(surface, "RGBA")))
    return frames


def _save(frames: list[Image.Image], path: Path, durations: list[int]) -> None:
    indexed = [frame.convert("P", palette=Image.Palette.ADAPTIVE) for frame in frames]
    indexed[0].save(path, save_all=True, append_images=indexed[1:], duration=durations, loop=0, disposal=2, optimize=False)


def render_dave(output_path: Path) -> None:
    frames = _runtime_frames(24)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Twelve stable poses, each repeated for two uniform 40 ms exposures,
    # produce the same 0.96-second cadence as the supplied reference.
    _save(frames, output_path, [40] * len(frames))


def render(reference_path: Path, output_path: Path, iteration: int) -> None:
    reference, reference_durations = _load_reference(reference_path)
    runtime = _runtime_frames(max(24, len(reference)))
    font = ImageFont.load_default()
    frames: list[Image.Image] = []
    durations: list[int] = []
    for index in range(max(len(runtime), len(reference))):
        canvas = Image.new("RGBA", (720, 300), (27, 24, 32, 255))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((14, 14, 350, 286), outline=(91, 77, 105, 255), width=2)
        draw.rectangle((370, 14, 706, 286), outline=(91, 77, 105, 255), width=2)
        draw.text((28, 24), "DAVE WALK — CURRENT BUILD", fill=(245, 238, 226, 255), font=font)
        draw.text((384, 24), "TARGET GIF", fill=(245, 238, 226, 255), font=font)
        draw.text((28, 42), "current runtime frame", fill=(174, 157, 181, 255), font=font)
        draw.text((384, 42), "reference frame", fill=(174, 157, 181, 255), font=font)
        left = runtime[index % len(runtime)].resize((256, 256), Image.Resampling.NEAREST)
        canvas.alpha_composite(left, (55, 38))
        right = reference[index % len(reference)]
        scale = min(300 / right.width, 235 / right.height)
        right = right.resize((max(1, round(right.width * scale)), max(1, round(right.height * scale))), Image.Resampling.NEAREST)
        canvas.alpha_composite(right, (538 - right.width // 2, 166 - right.height // 2))
        draw = ImageDraw.Draw(canvas)
        draw.text((28, 278), f"frame {index + 1:02d}/{len(runtime)}", fill=(174, 157, 181, 255), font=font)
        draw.text((384, 278), f"frame {(index % len(reference)) + 1:02d}/{len(reference)}", fill=(174, 157, 181, 255), font=font)
        frames.append(canvas)
        durations.append(reference_durations[index % len(reference_durations)])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save(frames, output_path, durations)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--dave-output", type=Path)
    args = parser.parse_args()
    pygame.init()
    try:
        render(args.reference, args.output, args.iteration)
        if args.dave_output is not None:
            render_dave(args.dave_output)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
