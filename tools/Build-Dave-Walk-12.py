"""Build Dave's locked-palette 12-pose walk strip from one unified source sheet."""

from __future__ import annotations

import argparse
from collections import Counter
from functools import lru_cache
from pathlib import Path
from statistics import median

from PIL import Image


GRID_COLUMNS = 4
GRID_ROWS = 3
OUTPUT_CELL = 128
FRAME_COUNT = GRID_COLUMNS * GRID_ROWS
ROOT_X = 64
GROUND_Y = 126
TARGET_HEIGHT = 122
PALETTE_COLORS = 40
# The unified source is an artist's pose pool, not the runtime timeline. Pair
# the strongest silhouettes into two equivalent six-phase steps so contact,
# down, mid-stance, passing, heel-rise and toe-off have matched counterparts.
SOURCE_FRAME_ORDER = (3, 2, 1, 0, 9, 7, 5, 6, 11, 8, 4, 10)


def _pixels(image: Image.Image):
    getter = getattr(image, "get_flattened_data", None)
    return getter() if getter is not None else image.getdata()


def _hard_alpha(image: Image.Image) -> Image.Image:
    hardened = image.convert("RGBA")
    hardened.putdata(
        [
            (red, green, blue, 255) if alpha >= 128 else (0, 0, 0, 0)
            for red, green, blue, alpha in _pixels(hardened)
        ]
    )
    return hardened


def _remove_detached_artifacts(image: Image.Image) -> Image.Image:
    """Remove generated floor dashes and distant flecks without touching Dave."""

    width, height = image.size
    opaque = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if image.getpixel((x, y))[3] >= 128
    }
    components: list[set[tuple[int, int]]] = []
    while opaque:
        seed = opaque.pop()
        component = {seed}
        frontier = [seed]
        while frontier:
            x, y = frontier.pop()
            for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
                for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = (neighbor_x, neighbor_y)
                    if neighbor in opaque:
                        opaque.remove(neighbor)
                        component.add(neighbor)
                        frontier.append(neighbor)
        components.append(component)

    largest = max(components, key=len)
    largest_box = (
        min(x for x, _y in largest),
        min(y for _x, y in largest),
        max(x for x, _y in largest) + 1,
        max(y for _x, y in largest) + 1,
    )
    retained: set[tuple[int, int]] = set()
    minimum_size = max(8, round(len(largest) * 0.003))
    for component in components:
        left = min(x for x, _y in component)
        top = min(y for _x, y in component)
        right = max(x for x, _y in component) + 1
        bottom = max(y for _x, y in component) + 1
        gap_x = max(largest_box[0] - right, left - largest_box[2], 0)
        gap_y = max(largest_box[1] - bottom, top - largest_box[3], 0)
        if component is largest or (len(component) >= minimum_size and gap_x <= 10 and gap_y <= 10):
            retained.update(component)

    cleaned = Image.new("RGBA", image.size)
    for x, y in retained:
        cleaned.putpixel((x, y), image.getpixel((x, y)))
    return cleaned


def _split_grid(source: Image.Image) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for row in range(GRID_ROWS):
        top = round(row * source.height / GRID_ROWS)
        bottom = round((row + 1) * source.height / GRID_ROWS)
        for column in range(GRID_COLUMNS):
            left = round(column * source.width / GRID_COLUMNS)
            right = round((column + 1) * source.width / GRID_COLUMNS)
            frame = _remove_detached_artifacts(
                _hard_alpha(source.crop((left, top, right, bottom)))
            )
            if frame.getbbox() is None:
                raise ValueError(f"frame {len(frames)} is empty")
            frames.append(frame)
    return frames


def _locked_palette(frames: list[Image.Image]) -> tuple[tuple[int, int, int], ...]:
    counts: Counter[tuple[int, int, int]] = Counter(
        (red, green, blue)
        for frame in frames
        for red, green, blue, alpha in _pixels(frame)
        if alpha >= 128
    )
    # Feed a frequency-preserving but bounded swatch into one deterministic
    # median-cut operation. Every pose is then remapped to this same palette.
    samples: list[tuple[int, int, int]] = []
    total = sum(counts.values())
    for color, count in sorted(counts.items()):
        copies = max(1, round(count * 100_000 / max(1, total)))
        samples.extend([color] * copies)
    swatch = Image.new("RGB", (len(samples), 1))
    swatch.putdata(samples)
    indexed = swatch.quantize(
        colors=PALETTE_COLORS,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    raw_palette = indexed.getpalette() or []
    used = sorted(index for _count, index in indexed.getcolors() or [])
    return tuple(tuple(raw_palette[index * 3 : index * 3 + 3]) for index in used)


def _apply_palette(
    image: Image.Image, palette: tuple[tuple[int, int, int], ...]
) -> Image.Image:
    @lru_cache(maxsize=None)
    def nearest(red: int, green: int, blue: int) -> tuple[int, int, int]:
        return min(
            palette,
            key=lambda color: (
                (red - color[0]) * (red - color[0])
                + (green - color[1]) * (green - color[1])
                + (blue - color[2]) * (blue - color[2])
            ),
        )

    locked = image.copy()
    locked.putdata(
        [
            (*nearest(red, green, blue), 255) if alpha >= 128 else (0, 0, 0, 0)
            for red, green, blue, alpha in _pixels(locked)
        ]
    )
    return locked


def _pelvis_anchor(frame: Image.Image, bounds: tuple[int, int, int, int]) -> int:
    left, top, right, bottom = bounds
    sample_top = top + round((bottom - top) * 0.43)
    sample_bottom = top + round((bottom - top) * 0.66)
    xs = [
        x
        for y in range(sample_top, sample_bottom)
        for x in range(left, right)
        if frame.getpixel((x, y))[3] >= 128
    ]
    if not xs:
        raise ValueError("frame has no pelvis anchor pixels")
    return round(median(xs))


def build(source_path: Path, output_path: Path) -> None:
    source = Image.open(source_path).convert("RGBA")
    pose_pool = _split_grid(source)
    frames = [pose_pool[index] for index in SOURCE_FRAME_ORDER]
    palette = _locked_palette(frames)
    frames = [_apply_palette(frame, palette) for frame in frames]
    bounds = [frame.getbbox() for frame in frames]
    if any(box is None for box in bounds):
        raise ValueError("locked-palette conversion produced an empty frame")
    boxes = [box for box in bounds if box is not None]
    heights = [bottom - top for _left, top, _right, bottom in boxes]
    widths = [right - left for left, _top, right, _bottom in boxes]
    scale = min(
        TARGET_HEIGHT / max(1, median(heights)),
        (OUTPUT_CELL - 4) / max(1, max(widths)),
    )

    strip = Image.new("RGBA", (FRAME_COUNT * OUTPUT_CELL, OUTPUT_CELL))
    for index, (frame, box) in enumerate(zip(frames, boxes)):
        anchor_x = _pelvis_anchor(frame, box)
        subject = frame.crop(box)
        subject = subject.resize(
            (
                max(1, round(subject.width * scale)),
                max(1, round(subject.height * scale)),
            ),
            Image.Resampling.NEAREST,
        )
        scaled_anchor_x = round((anchor_x - box[0]) * scale)
        paste_x = ROOT_X - scaled_anchor_x
        paste_y = GROUND_Y - subject.height
        if paste_x < 0 or paste_x + subject.width > OUTPUT_CELL:
            raise ValueError(
                f"frame {index} exceeds the fixed canvas: x={paste_x}, width={subject.width}"
            )
        registered = Image.new("RGBA", (OUTPUT_CELL, OUTPUT_CELL))
        registered.alpha_composite(subject, (paste_x, paste_y))
        strip.alpha_composite(registered, (index * OUTPUT_CELL, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(output_path, optimize=True)
    print(f"frames={FRAME_COUNT}")
    print(f"palette_colors={len(palette)}")
    print(f"scale={scale:.6f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.source, args.output)


if __name__ == "__main__":
    main()
