"""Normalize a chroma-keyed concept sheet into a compact runtime sprite atlas."""

from __future__ import annotations

import argparse
from pathlib import Path
from statistics import median

from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--columns", required=True, type=int)
    parser.add_argument("--rows", required=True, type=int)
    parser.add_argument("--cell-width", type=int, default=128)
    parser.add_argument("--cell-height", type=int, default=128)
    parser.add_argument("--subject-height", type=int, default=108)
    parser.add_argument("--padding", type=int, default=4)
    parser.add_argument(
        "--clear-cell-left",
        action="append",
        default=[],
        metavar="INDEX:PIXELS",
        help="Clear a generated-sheet spill from the left edge of a zero-based cell.",
    )
    parser.add_argument(
        "--drop-cell-components-below",
        action="append",
        default=[],
        metavar="INDEX:AREA",
        help="Remove disconnected spill components smaller than AREA from a zero-based cell.",
    )
    return parser.parse_args()


def _drop_small_components(cell: Image.Image, maximum_area: int) -> None:
    """Erase small, disconnected generation spill while preserving the main sprite."""

    pixels = cell.load()
    visited: set[tuple[int, int]] = set()
    for start_y in range(cell.height):
        for start_x in range(cell.width):
            start = (start_x, start_y)
            if start in visited or pixels[start_x, start_y][3] == 0:
                continue
            component: list[tuple[int, int]] = []
            pending = [start]
            visited.add(start)
            while pending:
                x, y = pending.pop()
                component.append((x, y))
                for ny in range(max(0, y - 1), min(cell.height, y + 2)):
                    for nx in range(max(0, x - 1), min(cell.width, x + 2)):
                        point = (nx, ny)
                        if point not in visited and pixels[nx, ny][3] > 0:
                            visited.add(point)
                            pending.append(point)
            if len(component) < maximum_area:
                for x, y in component:
                    pixels[x, y] = (0, 0, 0, 0)


def split_projection(alpha: Image.Image, count: int, axis: str) -> list[tuple[int, int]]:
    """Split an alpha mask at its largest transparent gutters."""

    if axis == "y":
        active = [alpha.crop((0, y, alpha.width, y + 1)).getbbox() is not None for y in range(alpha.height)]
    else:
        active = [alpha.crop((x, 0, x + 1, alpha.height)).getbbox() is not None for x in range(alpha.width)]
    indices = [index for index, value in enumerate(active) if value]
    if not indices:
        raise ValueError("sprite sheet contains no visible pixels")
    first, last = indices[0], indices[-1] + 1
    gaps: list[tuple[int, int]] = []
    cursor = first
    while cursor < last:
        if active[cursor]:
            cursor += 1
            continue
        start = cursor
        while cursor < last and not active[cursor]:
            cursor += 1
        gaps.append((start, cursor))
    if len(gaps) < count - 1:
        raise ValueError(f"could not find {count} separated sprite bands on axis {axis}")
    dividers = sorted(
        (start + (end - start) // 2 for start, end in sorted(gaps, key=lambda item: item[1] - item[0], reverse=True)[: count - 1])
    )
    boundaries = [first, *dividers, last]
    return list(zip(boundaries, boundaries[1:]))


def build_atlas(args: argparse.Namespace) -> None:
    if min(args.columns, args.rows, args.cell_width, args.cell_height, args.subject_height) <= 0:
        raise ValueError("grid and target dimensions must be positive")
    source = Image.open(args.input).convert("RGBA")
    crops: list[Image.Image] = []
    heights: list[int] = []
    source_alpha = source.getchannel("A")
    row_ranges = split_projection(source_alpha, args.rows, "y")
    anchor_top, anchor_bottom = row_ranges[0]
    anchor_columns = split_projection(
        source_alpha.crop((0, anchor_top, source.width, anchor_bottom)),
        args.columns,
        "x",
    )
    column_boundaries = [0, *(right for _, right in anchor_columns[:-1]), source.width]
    fallback_column_ranges = list(zip(column_boundaries, column_boundaries[1:]))
    for row, (top, bottom) in enumerate(row_ranges):
        row_alpha = source_alpha.crop((0, top, source.width, bottom))
        try:
            column_ranges = split_projection(row_alpha, args.columns, "x")
        except ValueError:
            column_ranges = fallback_column_ranges
        for column, (left, right) in enumerate(column_ranges):
            cell = source.crop((left, top, right, bottom))
            bbox = cell.getchannel("A").getbbox()
            if bbox is None:
                raise ValueError(f"empty sprite at row {row + 1}, column {column + 1}")
            crop = cell.crop(bbox)
            crops.append(crop)
            heights.append(crop.height)

    common_scale = args.subject_height / max(1.0, float(median(heights)))
    atlas = Image.new(
        "RGBA",
        (args.columns * args.cell_width, args.rows * args.cell_height),
        (0, 0, 0, 0),
    )
    usable_width = args.cell_width - args.padding * 2
    usable_height = args.cell_height - args.padding * 2
    for index, crop in enumerate(crops):
        scale = min(
            common_scale,
            usable_width / crop.width,
            usable_height / crop.height,
        )
        width = max(1, round(crop.width * scale))
        height = max(1, round(crop.height * scale))
        sprite = crop.resize((width, height), Image.Resampling.NEAREST)
        column = index % args.columns
        row = index // args.columns
        x = column * args.cell_width + (args.cell_width - width) // 2
        y = row * args.cell_height + args.cell_height - args.padding - height
        atlas.alpha_composite(sprite, (x, y))

    for value in args.clear_cell_left:
        try:
            index_text, pixels_text = value.split(":", 1)
            index, pixels = int(index_text), int(pixels_text)
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid --clear-cell-left value: {value!r}") from error
        if not 0 <= index < args.columns * args.rows or not 0 <= pixels <= args.cell_width:
            raise ValueError(f"out-of-range --clear-cell-left value: {value!r}")
        column, row = index % args.columns, index // args.columns
        left = column * args.cell_width
        top = row * args.cell_height
        atlas.paste((0, 0, 0, 0), (left, top, left + pixels, top + args.cell_height))

    for value in args.drop_cell_components_below:
        try:
            index_text, area_text = value.split(":", 1)
            index, area = int(index_text), int(area_text)
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid --drop-cell-components-below value: {value!r}") from error
        if not 0 <= index < args.columns * args.rows or area <= 0:
            raise ValueError(f"out-of-range --drop-cell-components-below value: {value!r}")
        column, row = index % args.columns, index // args.columns
        bounds = (
            column * args.cell_width,
            row * args.cell_height,
            (column + 1) * args.cell_width,
            (row + 1) * args.cell_height,
        )
        cell = atlas.crop(bounds)
        _drop_small_components(cell, area)
        atlas.paste(cell, bounds)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(args.output, optimize=True)
    print(
        f"Wrote {args.output} ({args.columns}x{args.rows} cells, "
        f"{args.cell_width}x{args.cell_height}px each)"
    )


if __name__ == "__main__":
    build_atlas(parse_args())
