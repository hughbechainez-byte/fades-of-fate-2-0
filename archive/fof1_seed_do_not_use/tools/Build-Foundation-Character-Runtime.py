"""Build the approved Jermaine and White Dave foundation atlases for runtime.

The source atlases are already rooted, ordered, and visually reviewed.  This
tool never synthesizes or retimes animation.  White Dave receives one small
appearance-only pixel pass (softer waist, rounder face, shorter/blonder hair,
thin moustache, and a chin patch), while Jermaine is copied byte-for-pixel into
the common runtime grid.  All resizing is nearest-neighbour and all output
alpha remains hard.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from pathlib import Path
from statistics import median
from typing import Callable, Iterable

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CELL_SIZE = 128
RUNTIME_COLUMNS = 12
RUNTIME_ROWS = 3
WHITE_DAVE_ROW_FRAME_COUNTS = (8, 12, 8)
JERMAINE_ROW_FRAME_COUNTS = (8, 8, 8)
ROW_NAMES = ("idle", "walk", "attacks")
WHITE_DAVE_SOURCE = (
    PROJECT_ROOT
    / "art_source"
    / "white_dave"
    / "white_dave_foundation_motion_locked_v1.png"
)
JERMAINE_SOURCE = (
    PROJECT_ROOT / "art_source" / "jermaine" / "jermaine_foundation_locked_v1.png"
)
WHITE_DAVE_OUTPUT = (
    PROJECT_ROOT / "assets" / "sprites" / "white_dave_foundation_atlas.png"
)
JERMAINE_OUTPUT = (
    PROJECT_ROOT / "assets" / "sprites" / "jermaine_foundation_atlas.png"
)
WHITE_DAVE_PORTRAIT = (
    PROJECT_ROOT / "assets" / "portraits" / "white_dave_portrait_pixel_v2.png"
)
JERMAINE_PORTRAIT = (
    PROJECT_ROOT / "assets" / "portraits" / "jermaine_portrait_pixel_v1.png"
)
VALIDATION_OUTPUT = (
    PROJECT_ROOT / "assets" / "sprites" / "foundation_character_validation.json"
)

# This is the previously reviewed forward contact/down/pass/up/toe-off order.
# The source atlas is already stored in this sequence; the build only records
# the lock and never performs a second reorder.
WHITE_DAVE_LOCKED_WALK_ORDER = (1, 3, 2, 4, 6, 5, 7, 9, 8, 10, 12, 11)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _comparison_bytes(path: Path, payload: bytes) -> bytes:
    """Normalize checkout-only text line endings for deterministic checks."""

    return payload.replace(b"\r\n", b"\n") if path.suffix == ".json" else payload


def _hard_alpha(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = [
        (red, green, blue, 255 if alpha >= 128 else 0)
        for red, green, blue, alpha in rgba.get_flattened_data()
    ]
    rgba.putdata(pixels)
    return rgba


def _skin_like(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, alpha = pixel
    return bool(
        alpha
        and red >= 70
        and red >= green + 18
        and green >= blue + 5
        and red >= blue + 30
    )


def _neutral_shirt(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, alpha = pixel
    brightness = (red + green + blue) / 3.0
    return bool(
        alpha
        and 25 <= brightness <= 190
        and max(red, green, blue) - min(red, green, blue) <= 48
        and abs(red - blue) <= 30
        and abs(green - blue) <= 30
    )


def _warm_dark(pixel: tuple[int, int, int, int]) -> bool:
    red, green, blue, alpha = pixel
    return bool(
        alpha
        and 16 <= red <= 195
        and green <= 145
        and blue <= 120
        and red >= green - 4
        and red >= blue + 8
    )


def _components(
    image: Image.Image,
    predicate: Callable[[tuple[int, int, int, int]], bool],
    *,
    y_limit: int = CELL_SIZE,
) -> list[set[tuple[int, int]]]:
    pixels = image.load()
    remaining = {
        (x, y)
        for y in range(min(CELL_SIZE, y_limit))
        for x in range(CELL_SIZE)
        if predicate(pixels[x, y])
    }
    output: list[set[tuple[int, int]]] = []
    while remaining:
        seed = remaining.pop()
        pending = deque([seed])
        component = {seed}
        while pending:
            x, y = pending.popleft()
            for offset_y in (-1, 0, 1):
                for offset_x in (-1, 0, 1):
                    if not offset_x and not offset_y:
                        continue
                    point = (x + offset_x, y + offset_y)
                    if point in remaining:
                        remaining.remove(point)
                        component.add(point)
                        pending.append(point)
        output.append(component)
    return output


def _bounds(points: Iterable[tuple[int, int]]) -> tuple[int, int, int, int]:
    points = tuple(points)
    xs = tuple(point[0] for point in points)
    ys = tuple(point[1] for point in points)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def _head_bounds(cell: Image.Image) -> tuple[int, int, int, int]:
    candidates: list[tuple[float, set[tuple[int, int]]]] = []
    for component in _components(cell, _skin_like, y_limit=84):
        if len(component) < 45:
            continue
        left, top, right, bottom = _bounds(component)
        if bottom - top < 10:
            continue
        center_x = sum(x for x, _ in component) / len(component)
        score = top * 3.0 + abs(center_x - 64.0) * 0.65 - min(len(component), 250) * 0.02
        candidates.append((score, component))
    if not candidates:
        raise ValueError("could not locate White Dave's head in a populated cel")

    component = min(candidates, key=lambda candidate: candidate[0])[1]
    left, top, right, bottom = _bounds(component)
    if right - left > 22:
        upper_points = tuple((x, y) for x, y in component if y <= top + 22)
        best_left = left
        best_score = float("-inf")
        for window_left in range(left, max(left + 1, right - 17)):
            count = sum(window_left <= x < window_left + 18 for x, _ in upper_points)
            score = count - abs((window_left + 8.5) - 64.0) * 0.35
            if score > best_score:
                best_left = window_left
                best_score = score
        left, right = best_left, best_left + 18
    else:
        left, right = left - 1, right + 1
    center = (left + right) // 2
    width = max(16, min(20, right - left))
    left = center - width // 2
    right = left + width
    bottom = min(CELL_SIZE, max(bottom, top + 20), top + 23)
    return max(0, left), max(0, top), min(CELL_SIZE, right), bottom


def _median_skin(cell: Image.Image, head: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = head
    samples = [
        cell.getpixel((x, y))
        for y in range(top + 6, min(bottom, top + 17))
        for x in range(left + 3, max(left + 4, right - 3))
        if _skin_like(cell.getpixel((x, y)))
    ]
    if not samples:
        return (196, 132, 92, 255)
    return tuple(int(median(channel)) for channel in zip(*samples))  # type: ignore[return-value]


def _round_head(cell: Image.Image, head: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = head
    pixels = cell.load()
    skin_fill = _median_skin(cell, head)
    # Soften the cheek/jaw shadow within the existing silhouette.  Keeping the
    # alpha edge fixed avoids square one-pixel "ears" and leaves the cutter
    # behind the head untouched while making the lower face read rounder.
    cheek_top = top + max(7, round((bottom - top) * 0.40))
    cheek_bottom = min(bottom - 2, top + round((bottom - top) * 0.78))
    for y in range(cheek_top, cheek_bottom + 1):
        skin_xs = [x for x in range(left, right) if _skin_like(pixels[x, y])]
        if len(skin_xs) < 3:
            continue
        for direction, skin_edge in ((-1, min(skin_xs)), (1, max(skin_xs))):
            candidate = skin_edge + direction
            if 0 <= candidate < CELL_SIZE and pixels[candidate, y][3]:
                pixels[candidate, y] = skin_fill


def _shorten_and_blonde_hair(
    cell: Image.Image,
    head: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = head
    center = (left + right) // 2
    skin_fill = _median_skin(cell, head)
    pixels = cell.load()

    for y in range(top, min(bottom, top + 12)):
        for x in range(left, right):
            pixel = pixels[x, y]
            if not _warm_dark(pixel):
                continue
            side = x <= left + 2 or x >= right - 3
            touches_air = any(
                0 <= x + offset_x < CELL_SIZE
                and 0 <= y + offset_y < CELL_SIZE
                and not pixels[x + offset_x, y + offset_y][3]
                for offset_x, offset_y in ((-1, 0), (1, 0), (0, -1))
            )
            if side and y <= top + 7 and touches_air:
                pixels[x, y] = (0, 0, 0, 0)
                continue
            if y == top and abs(x - center) > 3 and touches_air:
                pixels[x, y] = (0, 0, 0, 0)
                continue
            red, green, blue, alpha = pixel
            pixels[x, y] = (
                min(220, int(red * 0.95 + 16)),
                min(184, int(green * 1.10 + 20)),
                min(130, int(blue * 0.98 + 12)),
                alpha,
            )


def _add_reserved_facial_hair(
    cell: Image.Image,
    head: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = head
    center = (left + right) // 2
    height = bottom - top
    moustache_y = min(bottom - 5, top + round(height * 0.66))
    mouth_y = min(bottom - 3, moustache_y + 2)
    chin_y = min(bottom - 2, top + round(height * 0.86))
    skin_fill = _median_skin(cell, head)
    pixels = cell.load()

    # Remove stray dark warm pixels below the mouth so the only beard read is
    # the requested small centered chin patch.  Preserve the mouth and outline.
    for y in range(mouth_y + 1, max(mouth_y + 1, bottom - 1)):
        for x in range(center - 5, center + 6):
            if x in {left, right - 1} or y == chin_y:
                continue
            if _warm_dark(pixels[x, y]):
                pixels[x, y] = skin_fill

    hair = (101, 73, 43, 255)
    for x in (center - 3, center - 2, center + 1, center + 2):
        if pixels[x, moustache_y][3]:
            pixels[x, moustache_y] = hair
    for x in (center - 1, center):
        if pixels[x, chin_y][3]:
            pixels[x, chin_y] = hair
        if chin_y + 1 < bottom and pixels[x, chin_y + 1][3]:
            pixels[x, chin_y + 1] = hair


def _soften_waist(cell: Image.Image, head: tuple[int, int, int, int]) -> None:
    _, _, _, head_bottom = head
    pixels = cell.load()
    for y in range(min(CELL_SIZE - 1, head_bottom + 13), min(CELL_SIZE - 1, head_bottom + 30)):
        neutral = [x for x in range(28, 101) if _neutral_shirt(pixels[x, y])]
        if len(neutral) < 6:
            continue
        middle = int(median(neutral))
        left_candidates = [x for x in neutral if x <= middle]
        right_candidates = [x for x in neutral if x >= middle]
        if not left_candidates or not right_candidates:
            continue
        left_neutral = min(left_candidates)
        right_neutral = max(right_candidates)
        row_fill_samples = [pixels[x, y] for x in neutral]
        fill = tuple(int(median(channel)) for channel in zip(*row_fill_samples))

        left_edge = left_neutral
        for x in range(left_neutral, max(0, left_neutral - 6), -1):
            if not pixels[x, y][3]:
                left_edge = x + 1
                break
        if left_edge > 0 and not pixels[left_edge - 1, y][3]:
            edge = pixels[left_edge, y]
            pixels[left_edge - 1, y] = edge
            pixels[left_edge, y] = fill

        right_edge = right_neutral
        for x in range(right_neutral, min(CELL_SIZE - 1, right_neutral + 6)):
            if not pixels[x, y][3]:
                right_edge = x - 1
                break
        if right_edge + 1 < CELL_SIZE and not pixels[right_edge + 1, y][3]:
            edge = pixels[right_edge, y]
            pixels[right_edge + 1, y] = edge
            pixels[right_edge, y] = fill


def _retouch_white_dave(cell: Image.Image) -> Image.Image:
    if cell.getchannel("A").getbbox() is None:
        return cell.copy()
    output = cell.copy().convert("RGBA")
    head = _head_bounds(output)
    _soften_waist(output, head)
    _round_head(output, head)
    _shorten_and_blonde_hair(output, head)
    _add_reserved_facial_hair(output, head)
    return _hard_alpha(output)


def _split_atlas(source: Image.Image) -> list[list[Image.Image]]:
    if source.height != RUNTIME_ROWS * CELL_SIZE or source.width % CELL_SIZE:
        raise ValueError(f"unexpected foundation atlas size: {source.size}")
    columns = source.width // CELL_SIZE
    if columns not in {8, RUNTIME_COLUMNS}:
        raise ValueError(f"unexpected foundation atlas column count: {columns}")
    return [
        [
            source.crop(
                (
                    column * CELL_SIZE,
                    row * CELL_SIZE,
                    (column + 1) * CELL_SIZE,
                    (row + 1) * CELL_SIZE,
                )
            ).convert("RGBA")
            for column in range(columns)
        ]
        for row in range(RUNTIME_ROWS)
    ]


def _compose_runtime(
    rows: list[list[Image.Image]],
    transform: Callable[[Image.Image], Image.Image],
    frame_counts: tuple[int, int, int],
) -> Image.Image:
    atlas = Image.new(
        "RGBA",
        (RUNTIME_COLUMNS * CELL_SIZE, RUNTIME_ROWS * CELL_SIZE),
        (0, 0, 0, 0),
    )
    for row, frame_count in enumerate(frame_counts):
        if len(rows[row]) < frame_count:
            raise ValueError(f"{ROW_NAMES[row]} row has too few authored frames")
        for column in range(frame_count):
            frame = transform(_hard_alpha(rows[row][column]))
            atlas.alpha_composite(frame, (column * CELL_SIZE, row * CELL_SIZE))
    return atlas


def _alpha_metrics(image: Image.Image) -> dict[str, object]:
    alpha = image.getchannel("A")
    values = tuple(alpha.get_flattened_data())
    return {
        "opaque_pixels": sum(value == 255 for value in values),
        "transparent_pixels": sum(value == 0 for value in values),
        "semitransparent_pixels": sum(value not in {0, 255} for value in values),
    }


def _frame_records(
    image: Image.Image,
    frame_counts: tuple[int, int, int],
) -> list[dict[str, object]]:
    rows = _split_atlas(image)
    records: list[dict[str, object]] = []
    for row, frame_count in enumerate(frame_counts):
        for column in range(frame_count):
            frame = rows[row][column]
            bbox = frame.getchannel("A").getbbox()
            if bbox is None:
                raise ValueError(f"empty authored frame: {ROW_NAMES[row]} {column + 1}")
            records.append(
                {
                    "state": ROW_NAMES[row],
                    "frame": column + 1,
                    "alpha_bbox": list(bbox),
                    "ground_y": bbox[3] - 1,
                    "opaque_pixels": sum(
                        value == 255
                        for value in frame.getchannel("A").get_flattened_data()
                    ),
                }
            )
    return records


def _build_portrait(atlas: Image.Image, crop_box: tuple[int, int, int, int]) -> Image.Image:
    idle = atlas.crop((0, 0, CELL_SIZE, CELL_SIZE)).convert("RGBA")
    # A native-ratio head/torso crop fills the exact 90x145 menu slot.  Keeping
    # the final file at its display size prevents the menu loader from
    # resampling this deliberately chunky portrait.
    crop = idle.crop(crop_box)
    scaled = crop.resize((90, 145), Image.Resampling.NEAREST)
    portrait = Image.new("RGBA", (90, 145), (12, 13, 19, 255))
    draw = ImageDraw.Draw(portrait)
    for y in range(0, 145, 9):
        color = (31, 32, 39, 255) if (y // 9) % 2 else (24, 25, 31, 255)
        draw.rectangle((0, y, 89, min(144, y + 8)), fill=color)
    portrait.alpha_composite(scaled, (0, 0))
    return portrait.convert("RGB")


def build() -> dict[str, object]:
    for source in (WHITE_DAVE_SOURCE, JERMAINE_SOURCE):
        if not source.is_file():
            raise FileNotFoundError(f"foundation source is missing: {source}")

    with Image.open(WHITE_DAVE_SOURCE) as opened:
        white_source = _hard_alpha(opened)
    with Image.open(JERMAINE_SOURCE) as opened:
        jermaine_source = _hard_alpha(opened)

    white_output = _compose_runtime(
        _split_atlas(white_source),
        _retouch_white_dave,
        WHITE_DAVE_ROW_FRAME_COUNTS,
    )
    jermaine_output = _compose_runtime(
        _split_atlas(jermaine_source),
        lambda frame: frame.copy(),
        JERMAINE_ROW_FRAME_COUNTS,
    )
    white_portrait = _build_portrait(white_output, (40, 10, 86, 84))
    jermaine_portrait = _build_portrait(jermaine_output, (34, 10, 89, 86))

    for output in (
        WHITE_DAVE_OUTPUT,
        JERMAINE_OUTPUT,
        WHITE_DAVE_PORTRAIT,
        JERMAINE_PORTRAIT,
        VALIDATION_OUTPUT,
    ):
        output.parent.mkdir(parents=True, exist_ok=True)
    white_output.save(WHITE_DAVE_OUTPUT, optimize=True)
    jermaine_output.save(JERMAINE_OUTPUT, optimize=True)
    white_portrait.save(WHITE_DAVE_PORTRAIT, optimize=True)
    jermaine_portrait.save(JERMAINE_PORTRAIT, optimize=True)

    validation: dict[str, object] = {
        "schema_version": 1,
        "status": "PASS",
        "cell_size": [CELL_SIZE, CELL_SIZE],
        "runtime_grid": [RUNTIME_COLUMNS, RUNTIME_ROWS],
        "row_frame_counts": {
            "white_dave": dict(zip(ROW_NAMES, WHITE_DAVE_ROW_FRAME_COUNTS)),
            "jermaine": dict(zip(ROW_NAMES, JERMAINE_ROW_FRAME_COUNTS)),
        },
        "motion_contract": {
            "appearance_only_build": True,
            "source_walk_order": list(WHITE_DAVE_LOCKED_WALK_ORDER),
            "runtime_reorder_performed": False,
            "nearest_neighbor_only": True,
            "root_or_timing_edit": False,
        },
        "white_dave_appearance": {
            "body_fat_change": "one-pixel softer lower-shirt silhouette",
            "face_change": "rounder cheek shading within the locked head silhouette",
            "hair_change": "shorter tapered sides and slightly blonder warm ramp",
            "facial_hair": "one-pixel thin moustache and centered two-pixel chin patch only",
            "pants_or_weapon_edit": False,
        },
        "sources": {
            "white_dave": {
                "path": str(WHITE_DAVE_SOURCE.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": _sha256(WHITE_DAVE_SOURCE),
            },
            "jermaine": {
                "path": str(JERMAINE_SOURCE.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": _sha256(JERMAINE_SOURCE),
            },
        },
        "outputs": {
            "white_dave": {
                "path": str(WHITE_DAVE_OUTPUT.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": _sha256(WHITE_DAVE_OUTPUT),
                "alpha": _alpha_metrics(white_output),
                "frames": _frame_records(white_output, WHITE_DAVE_ROW_FRAME_COUNTS),
            },
            "jermaine": {
                "path": str(JERMAINE_OUTPUT.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": _sha256(JERMAINE_OUTPUT),
                "alpha": _alpha_metrics(jermaine_output),
                "frames": _frame_records(jermaine_output, JERMAINE_ROW_FRAME_COUNTS),
            },
            "white_dave_portrait": {
                "path": str(WHITE_DAVE_PORTRAIT.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": _sha256(WHITE_DAVE_PORTRAIT),
                "size": list(white_portrait.size),
            },
            "jermaine_portrait": {
                "path": str(JERMAINE_PORTRAIT.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "sha256": _sha256(JERMAINE_PORTRAIT),
                "size": list(jermaine_portrait.size),
            },
        },
    }
    VALIDATION_OUTPUT.write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    return validation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild and fail if tracked outputs were not already identical",
    )
    args = parser.parse_args()
    before = {
        path: path.read_bytes() if path.is_file() else None
        for path in (
            WHITE_DAVE_OUTPUT,
            JERMAINE_OUTPUT,
            WHITE_DAVE_PORTRAIT,
            VALIDATION_OUTPUT,
        )
    }
    validation = build()
    if args.check:
        changed: list[Path] = []
        for path, previous in before.items():
            current = path.read_bytes()
            if previous is None or _comparison_bytes(path, current) != _comparison_bytes(
                path, previous
            ):
                changed.append(path)
            elif current != previous:
                # core.autocrlf may materialize JSON with CRLF.  A successful
                # check must not leave an otherwise-current checkout dirty.
                path.write_bytes(previous)
        if changed:
            raise SystemExit(
                "foundation runtime outputs were stale: "
                + ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in changed)
            )
    print(json.dumps({"status": validation["status"], "validation": str(VALIDATION_OUTPUT)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
