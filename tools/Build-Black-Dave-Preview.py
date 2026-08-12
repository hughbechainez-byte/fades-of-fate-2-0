#!/usr/bin/env python3
"""Bake the review-only Black Dave preview atlas from the new pose board.

The preview is deliberately small: it proves the new identity, rooted ground
contact, fixed anatomy bake, and reduced screen footprint before the complete
playable-hero pose library is authored.  It never fits each pose to its own
alpha bounds and it never creates in-between drawings.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from statistics import median

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_ROOT / "art_source/black_dave/preview/black_dave_preview_pose_board_v1.png"
ATLAS_PATH = PROJECT_ROOT / "assets/sprites/black_dave_preview_atlas_v1.png"
METADATA_PATH = PROJECT_ROOT / "assets/sprites/black_dave_preview_metadata_v1.json"

BOARD_COLUMNS = 4
BOARD_ROWS = 2
CELL_SIZE = (224, 160)
ROOT = (112, 156)
TARGET_NEUTRAL_HEIGHT = 112

POSES = (
    "guard",
    "idle_shift",
    "walk_contact",
    "walk_pass",
    "walk_recovery",
    "brace",
    "punch",
    "kick",
)

# These are review clips, not the final library.  Each sequence contains only
# complete authored drawings and does not pad a state with copied cels.
CLIPS = {
    "idle": ("guard", "idle_shift"),
    "walk_start": ("idle_shift", "walk_contact"),
    "walk": ("walk_contact", "walk_pass", "walk_recovery"),
    "walk_stop": ("walk_recovery", "idle_shift"),
    "walk_reverse": ("walk_recovery", "walk_contact"),
    "jump_takeoff": ("brace", "walk_recovery"),
    "jump_rise": ("walk_recovery", "kick"),
    "jump_apex": ("brace", "kick"),
    "jump_fall": ("kick", "brace"),
    "jump_land": ("brace", "guard"),
    "dodge": ("walk_recovery", "brace", "walk_contact"),
    "hurt": ("brace", "idle_shift"),
    "down": ("brace",),
    "recovery": ("brace", "idle_shift", "guard"),
    "ranged": ("guard", "punch"),
    "super": ("brace", "punch", "kick"),
    "pet": ("guard", "idle_shift"),
    "air_punch": ("brace", "punch"),
    "air_kick": ("brace", "kick"),
    "light": ("guard", "punch", "idle_shift"),
    "heavy": ("guard", "kick", "brace"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(131_072), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hard_alpha(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    rgba.putalpha(rgba.getchannel("A").point(lambda value: 255 if value >= 128 else 0))
    return rgba


def _cell(image: Image.Image, index: int) -> Image.Image:
    column = index % BOARD_COLUMNS
    row = index // BOARD_COLUMNS
    width = image.width // BOARD_COLUMNS
    height = image.height // BOARD_ROWS
    return _hard_alpha(
        image.crop((column * width, row * height, (column + 1) * width, (row + 1) * height))
    )


def _support_point(image: Image.Image) -> tuple[int, int]:
    alpha = image.getchannel("A")
    occupied_rows = [y for y in range(image.height) if alpha.crop((0, y, image.width, y + 1)).getbbox()]
    if not occupied_rows:
        raise ValueError("preview pose has no opaque pixels")
    bottom = max(occupied_rows)
    support_rows = occupied_rows[max(0, len(occupied_rows) - 4) :]
    support_x: list[int] = []
    for y in support_rows:
        row = alpha.crop((0, y, image.width, y + 1)).getbbox()
        if row is not None:
            support_x.extend(range(row[0], row[2]))
    if not support_x:
        raise ValueError("preview pose has no opaque support pixels")
    return round(float(median(support_x))), bottom


def _place_pose(source: Image.Image, bake_scale: float) -> tuple[Image.Image, dict[str, object]]:
    bounds = source.getbbox()
    if bounds is None:
        raise ValueError("preview pose has no opaque body bounds")
    support_x, support_y = _support_point(source)
    scaled_size = (
        max(1, round(source.width * bake_scale)),
        max(1, round(source.height * bake_scale)),
    )
    scaled = _hard_alpha(source.resize(scaled_size, Image.Resampling.NEAREST))
    canvas = Image.new("RGBA", CELL_SIZE)
    scaled_support = (round(support_x * bake_scale), round(support_y * bake_scale))
    destination = (ROOT[0] - scaled_support[0], ROOT[1] - scaled_support[1])
    canvas.alpha_composite(scaled, destination)
    canvas = _hard_alpha(canvas)
    placed_bounds = canvas.getbbox()
    if placed_bounds is None:
        raise ValueError("preview pose became empty after rooted placement")
    if placed_bounds[0] <= 0 or placed_bounds[1] <= 0 or placed_bounds[2] >= CELL_SIZE[0] or placed_bounds[3] >= CELL_SIZE[1]:
        raise ValueError(f"preview pose clips its declared canvas: {placed_bounds}")
    return canvas, {
        "source_alpha_bounds": list(bounds),
        "source_support_point": [support_x, support_y],
        "body_bounds": list(placed_bounds),
        "root": list(ROOT),
        "normalization": {
            "method": "fixed_neutral_anatomy_nearest_neighbor",
            "target_neutral_height_px": TARGET_NEUTRAL_HEIGHT,
            "uniform_bake_scale": round(bake_scale, 8),
            "pose_specific_fit": False,
        },
    }


def _baseline_neutral_height() -> int | None:
    path = PROJECT_ROOT / "assets/sprites/black_dave_v2_pose_metadata.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    heights = [
        int(pose["body_bounds"][3]) - int(pose["body_bounds"][1])
        for pose in data.get("clips", {}).get("idle", {}).get("poses", [])
    ]
    return round(float(median(heights))) if heights else None


def build() -> dict[str, object]:
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(f"preview source board is missing: {SOURCE_PATH}")
    source = _hard_alpha(Image.open(SOURCE_PATH))
    if source.width % BOARD_COLUMNS or source.height % BOARD_ROWS:
        raise ValueError(f"preview source board is not divisible by {BOARD_COLUMNS}x{BOARD_ROWS}: {source.size}")
    source_cells = [_cell(source, index) for index in range(len(POSES))]
    neutral_bounds = source_cells[0].getbbox()
    if neutral_bounds is None:
        raise ValueError("neutral preview pose is empty")
    neutral_height = neutral_bounds[3] - neutral_bounds[1]
    bake_scale = TARGET_NEUTRAL_HEIGHT / neutral_height

    atlas = Image.new("RGBA", (CELL_SIZE[0] * len(POSES), CELL_SIZE[1]))
    pose_metadata: list[dict[str, object]] = []
    for index, (pose_id, raw_cell) in enumerate(zip(POSES, source_cells)):
        placed, metadata = _place_pose(raw_cell, bake_scale)
        atlas.alpha_composite(placed, (index * CELL_SIZE[0], 0))
        pose_metadata.append({"id": pose_id, "index": index, "source_cell": [index % BOARD_COLUMNS, index // BOARD_COLUMNS], **metadata})

    ATLAS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(ATLAS_PATH)
    atlas_hash = _sha256(ATLAS_PATH)
    source_hash = _sha256(SOURCE_PATH)
    metadata = {
        "schema_version": 1,
        "status": "review_preview",
        "actor": "black_dave",
        "source_path": SOURCE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "source_sha256": source_hash,
        "atlas_path": ATLAS_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "atlas_sha256": atlas_hash,
        "cell_size": list(CELL_SIZE),
        "columns": len(POSES),
        "root": list(ROOT),
        "fixed_anatomy_bake": {
            "source_neutral_height_px": neutral_height,
            "target_neutral_height_px": TARGET_NEUTRAL_HEIGHT,
            "uniform_nearest_scale": round(bake_scale, 8),
            "baseline_v2_neutral_height_px": _baseline_neutral_height(),
            "screen_footprint_ratio_vs_v2": round(TARGET_NEUTRAL_HEIGHT / 133.0, 4),
        },
        "pose_order": list(POSES),
        "poses": pose_metadata,
        "clips": {
            clip_id: {"poses": list(pose_ids), "hold": 2 if clip_id == "walk" else 3, "loop": True}
            for clip_id, pose_ids in CLIPS.items()
        },
        "pose_budget": {
            "class": "playable_hero",
            "minimum_meaningful_drawings": 120,
            "normal_meaningful_drawings": 220,
            "ideal_meaningful_drawings": 350,
            "preview_meaningful_drawings": len(POSES),
            "floor_status": "deferred_pending_review",
            "next_step": "expand approved identity into the complete authored per-state library",
        },
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "source": str(SOURCE_PATH),
        "atlas": str(ATLAS_PATH),
        "metadata": str(METADATA_PATH),
        "source_sha256": source_hash,
        "atlas_sha256": atlas_hash,
        "pose_count": len(POSES),
        "target_neutral_height_px": TARGET_NEUTRAL_HEIGHT,
        "baseline_v2_neutral_height_px": _baseline_neutral_height(),
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, sort_keys=True))
