#!/usr/bin/env python3
"""Lead-owned source compiler for rooted playable-character Animation V2.

This deliberately assembles only complete pre-authored body cels on fixed,
generous canvases.  It never scales, morphs, recolors, or fits a character at
runtime; all output is hard-alpha, nearest-neighbor pixel art with explicit
roots and pose/socket metadata.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CELL = (128, 128)
DAVE_CELL = (192, 160)
VFX_CELL = (64, 64)
POSES_PER_CLIP = 5

PLAYER_STATES = (
    "idle", "walk", "attack_1", "attack_2", "attack_3", "attack_4", "heavy",
    "ranged", "dodge", "hurt", "down", "super", "air_attack", "jump", "pet",
    "refill", "pants",
)

# Each value is an existing full-body authored source row and five deliberate
# phase cels.  The route contacts and finishers draw from distinct existing
# complete source cels; shared guards only bridge motions.
DAVE_CORE_CLIPS: dict[str, tuple[int, tuple[int, ...]]] = {
    "idle": (0, (0, 2, 4, 6, 8)),
    "guard": (0, (1, 3, 5, 7, 9)),
    "walk_start": (1, (0, 1, 2, 3, 4)),
    "walk": (1, (2, 4, 6, 8, 10)),
    "walk_stop": (1, (10, 9, 8, 7, 6)),
    "walk_reverse": (1, (8, 6, 4, 2, 0)),
    "jump_takeoff": (13, (0, 1, 2, 3, 4)),
    "jump_rise": (13, (1, 2, 3, 4, 5)),
    "jump_apex": (13, (2, 3, 4, 5, 6)),
    "jump_fall": (13, (3, 4, 5, 6, 7)),
    "jump_land": (13, (4, 5, 6, 7, 0)),
    "dodge": (8, (0, 2, 4, 6, 7)),
    "hurt": (9, (0, 2, 4, 5, 7)),
    "down": (10, (0, 2, 4, 6, 7)),
    "recovery": (10, (6, 5, 4, 2, 0)),
    "ranged": (7, (0, 1, 2, 3, 5)),
    "super": (11, (0, 1, 2, 3, 6)),
    "pet": (14, (0, 2, 4, 5, 7)),
    "air_punch": (12, (0, 1, 3, 4, 5)),
    "air_kick": (12, (1, 3, 5, 6, 7)),
}

DAVE_ROUTE_CLIPS: dict[str, tuple[int, tuple[int, ...]]] = {
    "black_dave_v2_regular_01": (2, (0, 1, 3, 4, 7)),
    "black_dave_v2_regular_02": (2, (0, 1, 3, 4, 5)),
    "black_dave_v2_regular_03": (3, (0, 1, 3, 4, 7)),
    "black_dave_v2_regular_04": (3, (0, 1, 3, 4, 6)),
    "black_dave_v2_regular_05": (4, (0, 2, 3, 4, 6)),
    "black_dave_v2_regular_06": (4, (0, 2, 3, 4, 6)),
    "black_dave_v2_regular_07": (4, (0, 2, 4, 6, 7)),
    "black_dave_v2_kick_01": (6, (0, 1, 2, 4, 7)),
    "black_dave_v2_kick_02": (6, (0, 1, 2, 4, 6)),
    "black_dave_v2_kick_03": (6, (0, 2, 4, 6, 7)),
    "black_dave_v2_kick_04": (6, (0, 1, 2, 4, 7)),
    "black_dave_v2_kick_05": (6, (0, 1, 2, 4, 6)),
    "black_dave_v2_kick_06": (6, (0, 2, 4, 6, 7)),
    "black_dave_v2_kick_07": (6, (0, 1, 2, 4, 6)),
    "black_dave_v2_power_01": (2, (0, 1, 3, 4, 5)),
    "black_dave_v2_power_02": (6, (0, 1, 2, 4, 6)),
    "black_dave_v2_power_03": (3, (0, 1, 3, 4, 6)),
    "black_dave_v2_power_04": (6, (0, 1, 2, 4, 6)),
    "black_dave_v2_power_05": (6, (0, 2, 4, 6, 7)),
    "black_dave_v2_power_06": (4, (0, 2, 3, 4, 6)),
    "black_dave_v2_power_07": (6, (0, 1, 2, 4, 6)),
}

# These legacy source cels visibly contain an old spark, energy disk, or
# ground-impact effect.  A V2 body atlas is intentionally forbidden from
# consuming them; all effect cels live in the dedicated VFX atlas below.
FORBIDDEN_BODY_EFFECT_CELS = frozenset({
    (2, 2), (2, 6),
    (3, 2), (3, 5),
    (4, 1), (4, 5),
    (5, 1), (5, 2), (5, 4), (5, 5),
    (6, 3), (6, 5),
    (7, 4),
    (11, 4), (11, 5),
    (12, 2),
})

GENERIC_STATE_ROW = {state: row for row, state in enumerate(PLAYER_STATES)}
FOUNDATION_STATE_ROW = {
    "idle": 0,
    "walk": 1,
    "attack_1": 2,
    "attack_2": 2,
    "attack_3": 2,
    "attack_4": 2,
    "heavy": 2,
    "ranged": 2,
    "dodge": 1,
    "hurt": 0,
    "down": 0,
    "super": 2,
    "air_attack": 2,
    "jump": 1,
    "pet": 0,
    "refill": 0,
    "pants": 0,
}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    """Emit portable manifest paths independently of the build host."""

    return path.relative_to(PROJECT_ROOT).as_posix()


def _hard_alpha(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
    rgba.putalpha(alpha)
    return rgba


def _grid(image: Image.Image, columns: int, rows: int) -> list[Image.Image]:
    width, height = image.size
    cell_width, cell_height = width // columns, height // rows
    if cell_width <= 0 or cell_height <= 0:
        raise ValueError(f"invalid grid {image.size} / {columns}x{rows}")
    return [
        image.crop((column * cell_width, row * cell_height, (column + 1) * cell_width, (row + 1) * cell_height))
        for row in range(rows)
        for column in range(columns)
    ]


def _place_rooted(
    source: Image.Image,
    cell_size: tuple[int, int],
    root: tuple[int, int],
    source_root: tuple[int, int] = (64, 126),
) -> Image.Image:
    """Place an unscaled whole cel at its declared authored source root."""

    canvas = Image.new("RGBA", cell_size)
    left = root[0] - source_root[0]
    top = root[1] - source_root[1]
    canvas.alpha_composite(_hard_alpha(source), (left, top))
    bbox = canvas.getbbox()
    if bbox is None:
        raise ValueError("source cel has no opaque body pixels")
    if bbox[0] == 0 or bbox[1] == 0 or bbox[2] == cell_size[0] or bbox[3] == cell_size[1]:
        raise ValueError(f"rooted cel touches canvas edge: {bbox} in {cell_size}")
    return canvas


def _bounds(image: Image.Image) -> list[int]:
    bbox = image.getbbox()
    if bbox is None:
        raise ValueError("missing body bounds")
    return [int(value) for value in bbox]


def _event_names(clip_id: str, phase: int) -> list[str]:
    if clip_id.startswith("dave_"):
        return (
            ["anticipation"] if phase == 1 else
            ["contact", "flame_contact"] if phase == 3 else
            ["recovery"] if phase == 4 else []
        )
    return ["contact"] if phase == 3 and clip_id in {"air_punch", "air_kick", "ranged", "super"} else []


def _socket(name: str, point: tuple[int, int], phase: int, *, rear: bool) -> dict[str, object]:
    return {
        "name": name,
        "position": list(point),
        "tangent": [1, -1] if name == "lead_hand" else [-1, -1],
        "size": 12 + (2 if phase in {2, 3} else 0),
        "intensity": 180 + (55 if phase == 3 else 20 if phase == 2 else 0),
        "visibility": "behind_body" if rear else "front_body",
        "contact_anchor": "lead_hand" if phase == 3 else None,
        "release_anchor": "lead_hand" if phase == 3 else None,
    }


def _dave_pose_metadata(
    source_anchors: dict[str, list[dict[str, object]]],
    source_state: str,
    source_column: int,
    phase: int,
) -> dict[str, object]:
    anchors = source_anchors[source_state][source_column]
    rear = tuple(int(value) for value in anchors["rear"])
    lead = tuple(int(value) for value in anchors["lead"])
    rear = (rear[0] + 32, rear[1] + 30)
    lead = (lead[0] + 32, lead[1] + 30)
    return {
        "root": [96, 156],
        "anchors": {
            "rear_foot": [88, 156],
            "lead_foot": [104, 156],
            "pelvis": [96, 109],
            "head": [96, 54],
            "rear_hand": list(rear),
            "lead_hand": list(lead),
        },
        "sockets": [
            _socket("rear_hand", rear, phase, rear=True),
            _socket("lead_hand", lead, phase, rear=False),
        ],
    }


def _build_dave() -> tuple[Path, Path, Path]:
    atlas_path = PROJECT_ROOT / "assets/sprites/black_dave_animation_atlas.png"
    anchors_path = PROJECT_ROOT / "assets/sprites/black_dave_fist_anchors.json"
    atlas = Image.open(atlas_path).convert("RGBA")
    frames = _grid(atlas, 12, len(PLAYER_STATES))
    source_anchors = json.loads(anchors_path.read_text(encoding="utf-8"))["states"]
    clips = {**DAVE_CORE_CLIPS, **DAVE_ROUTE_CLIPS}
    invalid = {
        (clip_id, source_row, source_column)
        for clip_id, (source_row, source_columns) in clips.items()
        for source_column in source_columns
        if (source_row, source_column) in FORBIDDEN_BODY_EFFECT_CELS
    }
    if invalid:
        raise ValueError(f"V2 body atlas selected an effect-bearing source cel: {sorted(invalid)}")
    destination = Image.new("RGBA", (DAVE_CELL[0] * POSES_PER_CLIP, DAVE_CELL[1] * len(clips)))
    metadata: dict[str, object] = {
        "version": 2,
        "actor": "black_dave",
        "cell_size": list(DAVE_CELL),
        "columns": POSES_PER_CLIP,
        "root": [96, 156],
        "source_hashes": {_relative(atlas_path): _hash(atlas_path)},
        "clips": {},
    }
    for row, (clip_id, (source_row, source_columns)) in enumerate(clips.items()):
        state = PLAYER_STATES[source_row]
        poses: list[dict[str, object]] = []
        for phase, source_column in enumerate(source_columns):
            source = frames[source_row * 12 + source_column]
            cel = _place_rooted(source, DAVE_CELL, (96, 156))
            destination.alpha_composite(cel, (phase * DAVE_CELL[0], row * DAVE_CELL[1]))
            record = _dave_pose_metadata(source_anchors, state, source_column, phase)
            record["body_bounds"] = _bounds(cel)
            record["events"] = _event_names(clip_id, phase)
            record["source"] = {"state": state, "column": source_column}
            poses.append(record)
        metadata["clips"][clip_id] = {
            "row": row,
            "loop": clip_id in {"idle", "guard", "walk"},
            "hold": 1,
            "phases": ["anticipation", "launch", "contact", "follow_through", "recovery"],
            "poses": poses,
        }
    source_path = PROJECT_ROOT / "art_source/black_dave/v2/black_dave_v2_cels.png"
    output_path = PROJECT_ROOT / "assets/sprites/black_dave_v2_animation_atlas.png"
    metadata_path = PROJECT_ROOT / "assets/sprites/black_dave_v2_pose_metadata.json"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    destination.save(source_path)
    destination.save(output_path)
    metadata["source_hashes"][_relative(source_path)] = _hash(source_path)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return source_path, output_path, metadata_path


def _generic_metadata(cell: Image.Image, root: tuple[int, int], phase: int) -> dict[str, object]:
    return {
        "root": list(root),
        "body_bounds": _bounds(cell),
        "anchors": {
            "rear_foot": [root[0] - 8, root[1]],
            "lead_foot": [root[0] + 8, root[1]],
            "pelvis": [root[0], root[1] - 46],
            "head": [root[0], root[1] - 100],
            "rear_hand": [root[0] - 17, root[1] - 68],
            "lead_hand": [root[0] + 17, root[1] - 68],
        },
        "sockets": [],
        "events": ["contact"] if phase == 3 else [],
    }


def _build_migration(
    actor: str,
    source_relative: str,
    columns: int,
    rows: int,
    cell_size: tuple[int, int],
    root: tuple[int, int],
    state_rows: dict[str, int],
    source_root: tuple[int, int],
) -> tuple[Path, Path, Path]:
    source_path = PROJECT_ROOT / source_relative
    frames = _grid(Image.open(source_path).convert("RGBA"), columns, rows)
    destination = Image.new("RGBA", (cell_size[0] * POSES_PER_CLIP, cell_size[1] * len(PLAYER_STATES)))
    clips: dict[str, object] = {}
    for row, state in enumerate(PLAYER_STATES):
        source_row = state_rows[state]
        available_columns = tuple(
            column
            for column in range(columns)
            if frames[source_row * columns + column].getbbox() is not None
        )
        if len(available_columns) < POSES_PER_CLIP:
            raise ValueError(
                f"{actor}:{state} has only {len(available_columns)} complete source cels; "
                f"need {POSES_PER_CLIP}"
            )
        # Preserve authored progressive phases.  Each destination phase is a
        # distinct complete source cel rather than a duplicate timing hold.
        source_columns = tuple(
            available_columns[(row + phase) % len(available_columns)]
            for phase in range(POSES_PER_CLIP)
        )
        poses: list[dict[str, object]] = []
        for phase, source_column in enumerate(source_columns):
            cel = _place_rooted(
                frames[source_row * columns + source_column],
                cell_size,
                root,
                source_root,
            )
            destination.alpha_composite(cel, (phase * cell_size[0], row * cell_size[1]))
            poses.append(_generic_metadata(cel, root, phase))
        clips[state] = {
            "row": row,
            "loop": state in {"idle", "walk"},
            "hold": 1,
            "phases": ["anticipation", "launch", "contact", "follow_through", "recovery"],
            "poses": poses,
        }
    source_output = PROJECT_ROOT / f"art_source/{actor}/{actor}_rooted_migration_v2.png"
    atlas_output = PROJECT_ROOT / f"assets/sprites/{actor}_rooted_animation_atlas.png"
    metadata_output = PROJECT_ROOT / f"assets/sprites/{actor}_rooted_pose_metadata.json"
    source_output.parent.mkdir(parents=True, exist_ok=True)
    source_output.parent.mkdir(parents=True, exist_ok=True)
    destination.save(source_output)
    destination.save(atlas_output)
    metadata = {
        "version": 2,
        "actor": actor,
        "cell_size": list(cell_size),
        "columns": POSES_PER_CLIP,
        "root": list(root),
        "source_hashes": {
            source_relative: _hash(source_path),
            _relative(source_output): _hash(source_output),
        },
        "clips": clips,
    }
    metadata_output.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return source_output, atlas_output, metadata_output


def _flame_cell(kind: str, phase: int) -> Image.Image:
    """Draw one hand-authored, static VFX cel into a 64px transparent cell."""

    image = Image.new("RGBA", VFX_CELL)
    draw = ImageDraw.Draw(image)
    outer = (91, 29, 34, 255)
    ember = (186, 57, 34, 255)
    orange = (241, 102, 39, 255)
    gold = (255, 187, 74, 255)
    core = (255, 244, 194, 255)
    sway = (-2, -1, 1, 2)[phase % 4]
    if kind == "scorch_fade":
        radius = 20 - phase * 3
        # The fade is expressed by authored size and palette changes, not
        # semi-transparent antialiasing, to retain the hard-alpha contract.
        draw.ellipse((32 - radius, 41 - radius // 3, 32 + radius, 41 + radius // 3), fill=(77, 43, 37, 255))
        draw.arc((32 - radius, 39 - radius // 3, 32 + radius, 43 + radius // 3), 190, 346, fill=(207, 77, 38, 255), width=2)
        return image
    if kind == "enemy_feedback":
        for index, offset in enumerate((-14, -6, 3, 12)):
            height = 18 + ((phase + index) % 3) * 4
            draw.polygon([(32 + offset - 4, 45), (32 + offset, 45 - height), (32 + offset + 5, 45)], fill=outer)
            draw.polygon([(32 + offset - 2, 44), (32 + offset, 44 - height + 6), (32 + offset + 3, 44)], fill=orange)
        return image
    if kind in {"punch_trail", "power_kick_trail"}:
        reach = 39 if kind == "power_kick_trail" else 29
        draw.polygon([(10, 35), (33, 22 + sway), (59, 30), (33, 43 - sway)], fill=outer)
        draw.polygon([(7, 35), (34, 26 + sway), (59, 31), (34, 40 - sway)], fill=ember)
        draw.polygon([(4, 35), (35, 29 + sway), (59, 32), (35, 37 - sway)], fill=orange)
        draw.line((max(4, 62 - reach), 33, 59, 32), fill=core, width=2)
        return image
    if kind == "contact_burst":
        for index, (dx, dy) in enumerate(((-21, -5), (-11, -20), (5, -23), (20, -8), (21, 9), (4, 20), (-15, 15))):
            radius = 4 + ((phase + index) % 2)
            draw.polygon([(32, 32), (32 + dx - radius, 32 + dy), (32 + dx, 32 + dy - radius), (32 + dx + radius, 32 + dy)], fill=outer)
            draw.line((32, 32, 32 + dx, 32 + dy), fill=gold, width=2)
        draw.rectangle((29, 29, 34, 34), fill=core)
        return image
    if kind == "ember_release":
        for index, (dx, dy) in enumerate(((-14, 5), (-4, -8), (7, -19), (16, -4), (2, 12))):
            drift = ((phase + index) % 3) - 1
            size = 4 if index == 2 else 3
            draw.rectangle((32 + dx + drift, 34 + dy - phase * 2, 32 + dx + drift + size, 34 + dy - phase * 2 + size), fill=gold if index % 2 else orange)
        return image
    # ignition, idle_loop and anticipation_swell are intentionally compact,
    # preserving a readable hand window in front of the actor's complete cel.
    height = {"ignition": 20 + phase * 4, "idle_loop": 24 + (phase % 2) * 3, "anticipation_swell": 27 + phase * 5}[kind]
    draw.polygon([(18, 49), (18, 34), (26, 25 + sway), (31, 9 + sway), (37, 24), (46, 17 - sway), (48, 35), (54, 49)], fill=outer)
    draw.polygon([(21, 48), (22, 35), (28, 30 + sway), (33, 49 - height), (39, 29), (45, 34), (50, 48)], fill=ember)
    draw.polygon([(25, 47), (27, 36), (33, 49 - height + 9), (39, 34), (45, 47)], fill=orange)
    draw.polygon([(30, 46), (32, 38), (34, 49 - height + 16), (38, 46)], fill=core)
    return image


def _build_vfx() -> tuple[Path, Path, Path]:
    clips = ("ignition", "idle_loop", "anticipation_swell", "punch_trail", "power_kick_trail", "contact_burst", "ember_release", "scorch_fade", "enemy_feedback")
    columns = 4
    sheet = Image.new("RGBA", (VFX_CELL[0] * columns, VFX_CELL[1] * len(clips)))
    metadata: dict[str, object] = {"version": 2, "cell_size": list(VFX_CELL), "columns": columns, "clips": {}}
    for row, name in enumerate(clips):
        for phase in range(columns):
            sheet.alpha_composite(_flame_cell(name, phase), (phase * VFX_CELL[0], row * VFX_CELL[1]))
        metadata["clips"][name] = {"row": row, "frame_count": columns, "loop": name in {"idle_loop", "anticipation_swell"}}
    source = PROJECT_ROOT / "art_source/black_dave/v2/black_dave_v2_flame_vfx_cels.png"
    atlas = PROJECT_ROOT / "assets/sprites/black_dave_v2_flame_vfx_atlas.png"
    manifest = PROJECT_ROOT / "assets/sprites/black_dave_v2_flame_vfx_manifest.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(source)
    sheet.save(atlas)
    metadata["source_hashes"] = {
        _relative(source): _hash(source),
        _relative(atlas): _hash(atlas),
    }
    manifest.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return source, atlas, manifest


def main() -> None:
    outputs: list[Path] = []
    outputs.extend(_build_dave())
    outputs.extend(_build_vfx())
    outputs.extend(
        _build_migration(
            "shelly", "assets/sprites/shelly_animation_atlas.png", 12, len(PLAYER_STATES), (208, 160), (104, 156), GENERIC_STATE_ROW, (85, 126),
        )
    )
    outputs.extend(
        _build_migration(
            "jermaine", "art_source/jermaine/jermaine_foundation_locked_v1.png", 12, 3, (160, 160), (80, 156), FOUNDATION_STATE_ROW, (42, 126),
        )
    )
    outputs.extend(
        _build_migration(
            "white_dave", "art_source/white_dave/white_dave_foundation_motion_locked_v1.png", 12, 3, (176, 160), (88, 156), FOUNDATION_STATE_ROW, (64, 126),
        )
    )
    for output in outputs:
        print(_relative(output))


if __name__ == "__main__":
    main()
