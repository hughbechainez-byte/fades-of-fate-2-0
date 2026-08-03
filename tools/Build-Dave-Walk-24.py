"""Convert the approved 6x4 Dave walk grid into a rooted 24-cel strip."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


GRID_COLUMNS = 6
GRID_ROWS = 4
SOURCE_CELL = 256
SOURCE_ROW_PITCH = 232
OUTPUT_CELL = 128
FRAME_COUNT = GRID_COLUMNS * GRID_ROWS
ROOT_X = 64
GROUND_Y = 126
TARGET_HEIGHT = 124


def build(source_path: Path, output_path: Path) -> None:
    source = Image.open(source_path).convert("RGBA")
    expected = (GRID_COLUMNS * SOURCE_CELL, 1024)
    if source.size != expected:
        raise ValueError(f"expected {expected[0]}x{expected[1]} source grid, got {source.size}")

    strip = Image.new("RGBA", (FRAME_COUNT * OUTPUT_CELL, OUTPUT_CELL))
    for index in range(FRAME_COUNT):
        column = index % GRID_COLUMNS
        row = index // GRID_COLUMNS
        source_top = row * SOURCE_ROW_PITCH
        band = source.crop(
            (
                column * SOURCE_CELL,
                source_top,
                (column + 1) * SOURCE_CELL,
                source_top + SOURCE_ROW_PITCH,
            )
        )
        source_cell = Image.new("RGBA", (SOURCE_CELL, SOURCE_CELL))
        source_cell.alpha_composite(band, (0, 0))
        cell = source_cell.resize((OUTPUT_CELL, OUTPUT_CELL), Image.Resampling.NEAREST)
        # The game uses hard-edged authored pixels. Collapse the chroma helper's
        # soft matte so no semitransparent green fringe can become motion blur.
        pixels = [
            (red, green, blue, 255) if alpha >= 128 else (0, 0, 0, 0)
            for red, green, blue, alpha in cell.getdata()
        ]
        cell.putdata(pixels)
        bounds = cell.getbbox()
        if bounds is None:
            raise ValueError(f"frame {index} is empty")
        torso_top = bounds[1] + round((bounds[3] - bounds[1]) * 0.18)
        torso_bottom = bounds[1] + round((bounds[3] - bounds[1]) * 0.56)
        torso_x = [
            x
            for y in range(torso_top, torso_bottom)
            for x in range(bounds[0], bounds[2])
            if cell.getpixel((x, y))[3] >= 128
        ]
        if not torso_x:
            raise ValueError(f"frame {index} has no torso anchor")
        torso_x.sort()
        anchor_x = torso_x[len(torso_x) // 2]
        subject = cell.crop(bounds)
        scale = TARGET_HEIGHT / max(1, subject.height)
        subject = subject.resize(
            (max(1, round(subject.width * scale)), TARGET_HEIGHT),
            Image.Resampling.NEAREST,
        )
        scaled_anchor_x = round((anchor_x - bounds[0]) * scale)
        registered = Image.new("RGBA", (OUTPUT_CELL, OUTPUT_CELL))
        registered.alpha_composite(subject, (ROOT_X - scaled_anchor_x, GROUND_Y - TARGET_HEIGHT))
        strip.alpha_composite(registered, (index * OUTPUT_CELL, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(output_path, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.source, args.output)


if __name__ == "__main__":
    main()
