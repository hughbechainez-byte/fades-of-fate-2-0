#!/usr/bin/env python3
"""Lead-owned source compiler for rooted playable-character Animation V2.

This deliberately assembles only complete pre-authored body cels on fixed,
generous canvases.  Any documented legacy-size correction is baked once here
with nearest-neighbour pixels; the runtime never scales, morphs, recolors, or
fits a character.  All output is hard-alpha with explicit roots and
pose/socket metadata.
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
DAVE_SOURCE_ROOT = (64, 126)
# Black Dave's approved neutral renderer bakes the 128px source cell at 1.12x
# (134--137px alpha height depending on the breathing key).  V2 must retain
# that full build during combat rather than normalising an undersized legacy
# strike to a smaller 120px silhouette.
DAVE_UNIFORM_BAKE_SCALE = 1.12
SourceCel = tuple[int, int]


def _source_sequence(row: int, columns: tuple[int, ...]) -> tuple[SourceCel, ...]:
    """Declare full authored source cels without hiding their row provenance."""

    return tuple((row, column) for column in columns)

PLAYER_STATES = (
    "idle", "walk", "attack_1", "attack_2", "attack_3", "attack_4", "heavy",
    "ranged", "dodge", "hurt", "down", "super", "air_attack", "jump", "pet",
    "refill", "pants",
)

# Each value is an existing full-body authored source row and five deliberate
# phase cels.  The route contacts and finishers draw from distinct existing
# complete source cels; shared guards only bridge motions.
DAVE_CORE_CLIPS: dict[str, tuple[SourceCel, ...]] = {
    "idle": _source_sequence(0, (0, 2, 4, 6, 8)),
    "guard": _source_sequence(0, (1, 3, 5, 7, 9)),
    "walk_start": _source_sequence(1, (0, 1, 2, 3, 4)),
    "walk": _source_sequence(1, (2, 4, 6, 8, 10)),
    "walk_stop": _source_sequence(1, (10, 9, 8, 7, 6)),
    "walk_reverse": _source_sequence(1, (8, 6, 4, 2, 0)),
    "jump_takeoff": _source_sequence(13, (0, 1, 2, 3, 4)),
    "jump_rise": _source_sequence(13, (1, 2, 3, 4, 5)),
    "jump_apex": _source_sequence(13, (2, 3, 4, 5, 6)),
    "jump_fall": _source_sequence(13, (3, 4, 5, 6, 7)),
    "jump_land": _source_sequence(13, (4, 5, 6, 7, 0)),
    "dodge": _source_sequence(8, (0, 2, 4, 6, 7)),
    "hurt": _source_sequence(9, (0, 2, 4, 5, 7)),
    "down": _source_sequence(10, (0, 2, 4, 6, 7)),
    "recovery": _source_sequence(10, (6, 5, 4, 2, 0)),
    "ranged": _source_sequence(7, (0, 1, 2, 3, 5)),
    "super": _source_sequence(11, (0, 1, 2, 3, 6)),
    "pet": _source_sequence(14, (0, 2, 4, 5, 7)),
    "air_punch": _source_sequence(12, (0, 1, 3, 4, 5)),
    "air_kick": _source_sequence(12, (1, 3, 5, 6, 7)),
}

DAVE_ROUTE_GUARD_OPEN: SourceCel = (6, 0)
DAVE_ROUTE_GUARD_RECOVERY: SourceCel = (6, 7)

DAVE_ROUTE_CLIPS: dict[str, tuple[SourceCel, ...]] = {
    # The first and final phases intentionally use the same right-facing
    # fighting direction.  They bridge every strike without a post-contact
    # turn toward the camera or another attack fragment posing as recovery.
    "black_dave_v2_regular_01": (DAVE_ROUTE_GUARD_OPEN, (2, 4), (2, 0), (2, 1), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_regular_02": (DAVE_ROUTE_GUARD_OPEN, (2, 5), (2, 3), (2, 0), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_regular_03": (DAVE_ROUTE_GUARD_OPEN, (3, 0), (3, 1), (3, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_regular_04": (DAVE_ROUTE_GUARD_OPEN, (3, 6), (3, 0), (3, 1), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_regular_05": (DAVE_ROUTE_GUARD_OPEN, (4, 7), (4, 0), (4, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_regular_06": (DAVE_ROUTE_GUARD_OPEN, (4, 4), (4, 7), (4, 0), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_regular_07": (DAVE_ROUTE_GUARD_OPEN, (4, 7), (4, 4), (4, 0), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_kick_01": (DAVE_ROUTE_GUARD_OPEN, (6, 6), (6, 2), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_kick_02": (DAVE_ROUTE_GUARD_OPEN, (5, 0), (6, 2), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_kick_03": (DAVE_ROUTE_GUARD_OPEN, (5, 3), (6, 6), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_kick_04": (DAVE_ROUTE_GUARD_OPEN, (5, 6), (6, 2), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_kick_05": (DAVE_ROUTE_GUARD_OPEN, (5, 7), (6, 1), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_kick_06": (DAVE_ROUTE_GUARD_OPEN, (6, 1), (6, 2), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_kick_07": (DAVE_ROUTE_GUARD_OPEN, (6, 6), (6, 1), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_power_01": (DAVE_ROUTE_GUARD_OPEN, (2, 4), (2, 3), (2, 1), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_power_02": (DAVE_ROUTE_GUARD_OPEN, (5, 0), (6, 6), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_power_03": (DAVE_ROUTE_GUARD_OPEN, (3, 0), (3, 6), (3, 1), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_power_04": (DAVE_ROUTE_GUARD_OPEN, (5, 3), (6, 2), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_power_05": (DAVE_ROUTE_GUARD_OPEN, (6, 2), (6, 1), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_power_06": (DAVE_ROUTE_GUARD_OPEN, (4, 0), (4, 7), (4, 4), DAVE_ROUTE_GUARD_RECOVERY),
    "black_dave_v2_power_07": (DAVE_ROUTE_GUARD_OPEN, (6, 1), (6, 6), (6, 4), DAVE_ROUTE_GUARD_RECOVERY),
}

# Combat and air cels share the upright neutral's one authored scale.  Their
# alpha bounds deliberately vary with a crouch, high kick, or extended arm;
# using those bounds as a fit target is what made Dave's torso pulse in the
# previous review.  Runtime never rescales any character body.
DAVE_ANATOMY_CALIBRATED_CLIPS = frozenset((*DAVE_ROUTE_CLIPS, "air_punch", "air_kick"))

DAVE_ANATOMY_REFERENCE = {
    "reference": "black_dave_upright_neutral_v2",
    "head_to_pelvis": 55,
    "head_width": 22,
    "shoulder_span": 47,
    "chest_span": 41,
    "pelvis_span": 37,
    "limb_thickness": 14,
    "shoe_width": 27,
}

# These states have a planted combat/walk silhouette. Prone/recovery and
# ballistic jump keys intentionally do not use a sole-to-root calibration.
DAVE_GROUNDED_CORE_CLIPS = frozenset({
    "idle", "guard", "walk_start", "walk", "walk_stop", "walk_reverse",
    "dodge", "hurt", "ranged", "super", "pet",
})
DAVE_GROUNDED_CLIPS = frozenset((*DAVE_GROUNDED_CORE_CLIPS, *DAVE_ROUTE_CLIPS))

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


def _nearest_scale(image: Image.Image, scale: float) -> Image.Image:
    """Bake one uniform nearest-neighbour scale without a runtime resize.

    Pygame is used here because it is the established authored-atlas renderer
    for the foundation heroes.  Using its exact nearest-neighbour sampling in
    the compiler preserves their approved presentation while V2 keeps the
    resulting whole cel native at runtime.
    """

    source = _hard_alpha(image)
    if scale == 1.0:
        return source
    width = max(1, round(source.width * scale))
    height = max(1, round(source.height * scale))
    try:
        import pygame
    except ImportError as exc:  # pragma: no cover - a build-time dependency failure
        raise RuntimeError("pygame is required to bake approved nearest-neighbour cels") from exc
    surface = pygame.image.frombuffer(source.tobytes(), source.size, "RGBA")
    scaled = pygame.transform.scale(surface, (width, height))
    return _hard_alpha(Image.frombytes("RGBA", (width, height), pygame.image.tobytes(scaled, "RGBA")))


def _scaled_point(
    point: tuple[int, int],
    scale: float,
    offset: tuple[int, int] = (0, 0),
) -> tuple[int, int]:
    return (
        round(point[0] * scale) + offset[0],
        round(point[1] * scale) + offset[1],
    )


def _bounds(image: Image.Image) -> list[int]:
    bbox = image.getbbox()
    if bbox is None:
        raise ValueError("missing body bounds")
    return [int(value) for value in bbox]


def _align_opaque_sole_to_root(
    cel: Image.Image,
    root_y: int,
) -> tuple[Image.Image, int]:
    """Integer-translate a planted whole cel so its opaque sole meets its root."""

    bounds = cel.getbbox()
    if bounds is None:
        raise ValueError("cannot align an empty rooted cel")
    offset = int(root_y - bounds[3])
    if not offset:
        return cel, 0
    aligned = Image.new("RGBA", cel.size)
    aligned.alpha_composite(cel, (0, offset))
    aligned_bounds = aligned.getbbox()
    if aligned_bounds is None:
        raise ValueError("root alignment discarded a body cel")
    if (
        aligned_bounds[0] == 0
        or aligned_bounds[1] == 0
        or aligned_bounds[2] == cel.width
        or aligned_bounds[3] == cel.height
    ):
        raise ValueError(f"root alignment clips a body cel: {aligned_bounds} in {cel.size}")
    return aligned, offset


def _event_names(clip_id: str, phase: int) -> list[str]:
    if clip_id.startswith("black_dave_v2_"):
        return (
            ["anticipation"] if phase == 1 else
            ["contact", "flame_contact"] if phase == 3 else
            ["recovery"] if phase == 4 else []
        )
    return ["flame_contact"] if phase == 3 and clip_id in {"air_punch", "air_kick"} else []


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
        "phase_offset": 0.0 if rear else 0.125,
    }


def _dave_pose_metadata(
    source_anchors: dict[str, list[dict[str, object]]],
    source_state: str,
    source_column: int,
    phase: int,
    source_scale: float = 1.0,
    root_alignment_offset: int = 0,
) -> dict[str, object]:
    anchors = source_anchors[source_state][source_column]

    def rooted(point: object) -> tuple[int, int]:
        x, y = (int(value) for value in point)
        return (
            96 + round((x - DAVE_SOURCE_ROOT[0]) * source_scale),
            156 + round((y - DAVE_SOURCE_ROOT[1]) * source_scale) + root_alignment_offset,
        )

    rear = rooted(anchors["rear"])
    lead = rooted(anchors["lead"])
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
        "anatomy": dict(DAVE_ANATOMY_REFERENCE),
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
        for clip_id, source_cels in clips.items()
        for source_row, source_column in source_cels
        if (source_row, source_column) in FORBIDDEN_BODY_EFFECT_CELS
    }
    if invalid:
        raise ValueError(f"V2 body atlas selected an effect-bearing source cel: {sorted(invalid)}")
    destination = Image.new("RGBA", (DAVE_CELL[0] * POSES_PER_CLIP, DAVE_CELL[1] * len(clips)))
    metadata: dict[str, object] = {
        "version": 3,
        "actor": "black_dave",
        "cell_size": list(DAVE_CELL),
        "columns": POSES_PER_CLIP,
        "root": [96, 156],
        "source_hashes": {_relative(atlas_path): _hash(atlas_path)},
        "clips": {},
    }
    for row, (clip_id, source_cels) in enumerate(clips.items()):
        poses: list[dict[str, object]] = []
        for phase, (source_row, source_column) in enumerate(source_cels):
            state = PLAYER_STATES[source_row]
            source = frames[source_row * 12 + source_column]
            source_scale = DAVE_UNIFORM_BAKE_SCALE
            root_alignment_offset = 0
            baked_source = _nearest_scale(source, source_scale)
            cel = _place_rooted(
                baked_source,
                DAVE_CELL,
                (96, 156),
                _scaled_point(DAVE_SOURCE_ROOT, source_scale),
            )
            if clip_id in DAVE_GROUNDED_CLIPS:
                cel, root_alignment_offset = _align_opaque_sole_to_root(cel, 156)
            normalization_method = (
                "reference_anatomy_uniform_nearest_neighbor"
                if clip_id in DAVE_ANATOMY_CALIBRATED_CLIPS
                else "uniform_nearest_neighbor"
            )
            raw_bounds = _hard_alpha(source).getbbox()
            if raw_bounds is None:
                raise ValueError(f"empty Black Dave source cel: {clip_id}/{phase}")
            source_bounds = [int(value) for value in raw_bounds]
            destination.alpha_composite(cel, (phase * DAVE_CELL[0], row * DAVE_CELL[1]))
            record = _dave_pose_metadata(
                source_anchors,
                state,
                source_column,
                phase,
                source_scale,
                root_alignment_offset,
            )
            record["body_bounds"] = _bounds(cel)
            record["events"] = _event_names(clip_id, phase)
            record["source"] = {
                "state": state,
                "row": source_row,
                "column": source_column,
                "alpha_bounds": source_bounds,
                "normalization": {
                    "method": normalization_method,
                    "anatomy_reference": DAVE_ANATOMY_REFERENCE["reference"],
                    "scale": round(source_scale, 6),
                    "root_alignment_offset": root_alignment_offset,
                },
            }
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
    metadata_path.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
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
    source_columns: int,
    source_rows: int,
    cell_size: tuple[int, int],
    root: tuple[int, int],
    state_rows: dict[str, int],
    source_root: tuple[int, int],
    *,
    source_scale: float = 1.0,
    source_root_post_scale_offset: tuple[int, int] = (0, 0),
    incomplete_source_cels: frozenset[tuple[int, int]] = frozenset(),
) -> tuple[Path, Path, Path]:
    source_path = PROJECT_ROOT / source_relative
    source_image = Image.open(source_path).convert("RGBA")
    if source_image.width % source_columns or source_image.height % source_rows:
        raise ValueError(
            f"{actor} source atlas {source_image.size} is not divisible by "
            f"the declared {source_columns}x{source_rows} grid"
        )
    frames = _grid(source_image, source_columns, source_rows)
    baked_source_root = _scaled_point(
        source_root,
        source_scale,
        source_root_post_scale_offset,
    )
    destination = Image.new("RGBA", (cell_size[0] * POSES_PER_CLIP, cell_size[1] * len(PLAYER_STATES)))
    clips: dict[str, object] = {}
    for row, state in enumerate(PLAYER_STATES):
        source_row = state_rows[state]
        if source_row not in range(source_rows):
            raise ValueError(f"{actor}:{state} references source row {source_row}, outside the declared grid")
        available_columns = tuple(
            column
            for column in range(source_columns)
            if (
                (source_row, column) not in incomplete_source_cels
                and frames[source_row * source_columns + column].getbbox() is not None
            )
        )
        if len(available_columns) < POSES_PER_CLIP:
            raise ValueError(
                f"{actor}:{state} has only {len(available_columns)} complete source cels; "
                f"need {POSES_PER_CLIP}"
            )
        # Preserve authored progressive phases.  Each destination phase is a
        # distinct complete source cel rather than a duplicate timing hold.
        selected_columns = tuple(
            available_columns[(row + phase) % len(available_columns)]
            for phase in range(POSES_PER_CLIP)
        )
        poses: list[dict[str, object]] = []
        for phase, source_column in enumerate(selected_columns):
            raw_source = _hard_alpha(frames[source_row * source_columns + source_column])
            raw_bounds = raw_source.getbbox()
            if raw_bounds is None:  # Protected above, kept local for provenance safety.
                raise ValueError(f"{actor}:{state}/{source_column} unexpectedly has no body pixels")
            opaque_pixels = sum(value == 255 for value in raw_source.getchannel("A").get_flattened_data())
            baked_source = _nearest_scale(raw_source, source_scale)
            cel = _place_rooted(
                baked_source,
                cell_size,
                root,
                baked_source_root,
            )
            destination.alpha_composite(cel, (phase * cell_size[0], row * cell_size[1]))
            record = _generic_metadata(cel, root, phase)
            record["source"] = {
                "state": state,
                "row": source_row,
                "column": source_column,
                "alpha_bounds": [int(value) for value in raw_bounds],
                "opaque_pixels": opaque_pixels,
                "uniform_bake_scale": source_scale,
            }
            poses.append(record)
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
        "source_grid": {
            "asset": source_relative,
            "columns": source_columns,
            "rows": source_rows,
            "cell_size": [source_image.width // source_columns, source_image.height // source_rows],
            "source_root": list(source_root),
            "baked_source_root": list(baked_source_root),
            "uniform_bake_scale": source_scale,
            "incomplete_cels_rejected": [list(cel) for cel in sorted(incomplete_source_cels)],
        },
        "source_hashes": {
            source_relative: _hash(source_path),
            _relative(source_output): _hash(source_output),
        },
        "clips": clips,
    }
    metadata_output.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
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
        width = 19 - phase * 3
        # Broken, grounded charcoal/ember strokes read as a scorch mark;
        # deliberately avoid concentric rings that could read as a reticle.
        draw.line((32 - width, 43, 24 - phase, 45), fill=(77, 43, 37, 255), width=3)
        draw.line((29 - phase, 45, 32 + width, 46), fill=(77, 43, 37, 255), width=3)
        draw.rectangle((29 - phase, 41, 34 + phase, 43), fill=(132, 54, 35, 255))
        draw.rectangle((20 + phase * 2, 45, 24 + phase * 2, 46), fill=(207, 77, 38, 255))
        draw.rectangle((38 - phase, 44, 42 - phase, 45), fill=(207, 77, 38, 255))
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
        # A forward, uneven flame plume gives contact weight without a radial
        # targeting-disc silhouette.  The runtime mirrors this complete cel.
        lift = (phase % 3) - 1
        draw.polygon(
            [(11, 43), (18, 36), (24, 37), (27, 26 + lift), (34, 34),
             (41, 17 - lift), (44, 32), (57, 25 + lift), (52, 38),
             (61, 42), (47, 48), (35, 45), (27, 52), (21, 45)],
            fill=outer,
        )
        draw.polygon(
            [(16, 42), (23, 37), (27, 32), (31, 38), (40, 23),
             (42, 37), (53, 30), (48, 40), (56, 42), (43, 45),
             (34, 42), (26, 48)],
            fill=orange,
        )
        draw.polygon([(24, 41), (31, 37), (39, 30), (40, 40), (48, 37), (42, 43), (33, 41)], fill=gold)
        draw.rectangle((35, 37, 39, 41), fill=core)
        return image
    if kind == "ember_release":
        for index, (dx, dy) in enumerate(((-14, 5), (-4, -8), (7, -19), (16, -4), (2, 12))):
            drift = ((phase + index) % 3) - 1
            size = 4 if index == 2 else 3
            draw.rectangle((32 + dx + drift, 34 + dy - phase * 2, 32 + dx + drift + size, 34 + dy - phase * 2 + size), fill=gold if index % 2 else orange)
        return image
    # ignition, idle_loop and anticipation_swell stay hand-sized.  Their
    # footprint is intentionally smaller than Dave's fist so paired sockets
    # read as two live flames, never a cape-like screen effect.
    height = {"ignition": 14 + phase * 2, "idle_loop": 18 + (phase % 2) * 2, "anticipation_swell": 20 + phase * 3}[kind]
    tip = 51 - height
    # An asymmetric three-tongue silhouette reads as fire at gameplay scale,
    # rather than as a symmetric warning triangle or reticle over the hand.
    draw.polygon(
        [(23, 51), (22, 47), (27, 42 + sway), (25, 36), (31, 40),
         (32, tip + 7), (36, tip), (38, 37 - sway), (43, 30 + sway),
         (42, 43), (47, 47), (46, 51)],
        fill=outer,
    )
    draw.polygon(
        [(27, 50), (26, 46), (30, 41 + sway), (30, 35), (34, 40),
         (35, tip + 6), (39, 38), (42, 44), (44, 48), (42, 50)],
        fill=ember,
    )
    draw.polygon([(31, 50), (30, 46), (34, tip + 10), (37, 42), (41, 49), (38, 50)], fill=orange)
    draw.rectangle((35 + sway, 45, 37 + sway, 48), fill=gold)
    draw.point((38 + sway, 43), fill=core)
    draw.polygon([(32, 48), (33, 43), (35, 51 - height + 12), (37, 48)], fill=core)
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
    manifest.write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return source, atlas, manifest


def main() -> None:
    outputs: list[Path] = []
    outputs.extend(_build_dave())
    outputs.extend(_build_vfx())
    outputs.extend(
        _build_migration(
            "shelly", "assets/sprites/shelly_animation_atlas.png", 16, len(PLAYER_STATES), (208, 160), (104, 156), GENERIC_STATE_ROW, (85, 126),
        )
    )
    outputs.extend(
        _build_migration(
            "jermaine", "assets/sprites/jermaine_foundation_atlas.png", 12, 3, (224, 160), (112, 156), FOUNDATION_STATE_ROW, (42, 126),
            source_scale=1.16,
            source_root_post_scale_offset=(0, 1),
            # The foundation source's seventh attack slot contains only a
            # trailing lower-body fragment; it is valid legacy source data but
            # not a complete rooted body cel and must never enter V2.
            incomplete_source_cels=frozenset({(2, 6)}),
        )
    )
    outputs.extend(
        _build_migration(
            "white_dave", "assets/sprites/white_dave_foundation_atlas.png", 12, 3, (176, 160), (88, 156), FOUNDATION_STATE_ROW, (64, 126),
            source_scale=1.16,
            source_root_post_scale_offset=(0, 1),
        )
    )
    for output in outputs:
        print(_relative(output))


if __name__ == "__main__":
    main()
