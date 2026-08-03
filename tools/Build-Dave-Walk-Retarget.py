"""Retarget the supplied walk reference onto one deterministic Black Dave rig.

This pipeline intentionally avoids image generation, optical flow, whole-frame
warping, antialiasing and arbitrary interpolation. It extracts the reference's
paired timing, builds a reviewable 12-pose landmark table, validates a skeletal
retarget, and only then renders Dave from one fixed palette and part rig.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from statistics import median
import sys
from typing import Iterable, Mapping

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from src.character_animation import CharacterAnimationSkin, load_character_animation_skin


POSE_COUNT = 12
SOURCE_FRAME_INDICES = tuple(range(0, 24, 2))
CELL_SIZE = 128
ROOT_X = 64
GROUND_Y = 126
DAVE_HEIGHT = 112.0
LEG_LENGTH = 50.0
SHOULDER_WIDTH = 18.0
STRIDE_DISTANCE = 78.0
ROOT_STEP = STRIDE_DISTANCE / POSE_COUNT
REFERENCE_PAIR_MAX_CHANGED_PIXELS = 2048
CANONICAL_ATLAS_COLUMNS = 5
CANONICAL_ATLAS_ROWS = 4
CANONICAL_CELL_COLUMN = 0
CANONICAL_CELL_ROW = 1
CANONICAL_PALETTE_COLORS = 40
APPROVED_MOTION_FINGERPRINT = "6147e92f064bac2204edfe2972e507a6477ec74e9a252487b0461f86a172fa4c"
DEFAULT_ART_MODEL = Path("data/dave_character_art_model.json")

PHASE_NAMES = (
    "left_contact",
    "left_down",
    "left_mid_stance",
    "right_passing",
    "left_up",
    "left_toe_off_reach",
    "right_contact",
    "right_down",
    "right_mid_stance",
    "left_passing",
    "right_up",
    "right_toe_off_reach",
)
PELVIS_Y = (77, 81, 79, 76, 72, 74, 77, 81, 79, 76, 72, 74)
TORSO_YAW = (0.08, 0.24, 0.42, 0.30, 0.10, -0.12, -0.08, -0.24, -0.42, -0.30, -0.10, 0.12)
SHOULDER_ANGLE_DEG = (-6, -4, 1, 6, 8, 3, 6, 4, -1, -6, -8, -3)
HIP_ANGLE_DEG = (5, 6, 3, -2, -6, -4, -5, -6, -3, 2, 6, 4)

LANDMARK_NAMES = (
    "head_center",
    "neck",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hand",
    "right_hand",
    "pelvis",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_toe",
    "right_toe",
)

Point = tuple[int, int]


@dataclass(frozen=True)
class Pose:
    index: int
    name: str
    source_frame: int
    support_foot: str
    near_arm: str
    near_leg: str
    foot_contact: Mapping[str, str]
    torso_yaw: float
    shoulder_angle_deg: float
    hip_angle_deg: float
    pelvis_height: int
    root_distance: float
    contact_landmark: str
    landmarks: Mapping[str, Point]


@dataclass(frozen=True)
class RigPart:
    layer: Image.Image
    source_start: Point
    source_end: Point


@dataclass(frozen=True)
class CanonicalDaveRig:
    source_sha256: str
    palette: tuple[tuple[int, int, int, int], ...]
    source_cell: Image.Image
    parts: Mapping[str, RigPart]


def _font(size: int = 14, bold: bool = False) -> ImageFont.ImageFont:
    name = "consolab.ttf" if bold else "consola.ttf"
    try:
        return ImageFont.truetype(str(Path(r"C:\Windows\Fonts") / name), size)
    except OSError:
        return ImageFont.load_default()


def _point(x: float, y: float) -> Point:
    return round(x), round(y)


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


def _canonical_palette(
    image: Image.Image, colors: int = CANONICAL_PALETTE_COLORS
) -> tuple[tuple[int, int, int, int], ...]:
    counts: Counter[tuple[int, int, int]] = Counter(
        (red, green, blue)
        for red, green, blue, alpha in _pixels(image)
        if alpha >= 128
    )
    if not counts:
        raise ValueError("canonical Dave cell is empty")
    total = sum(counts.values())
    samples: list[tuple[int, int, int]] = []
    for color, count in sorted(counts.items()):
        copies = max(1, round(count * 100_000 / total))
        samples.extend([color] * copies)
    swatch = Image.new("RGB", (len(samples), 1))
    swatch.putdata(samples)
    indexed = swatch.quantize(
        colors=colors,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    raw = indexed.getpalette() or []
    used = sorted(index for _count, index in indexed.getcolors() or [])
    return tuple((*raw[index * 3 : index * 3 + 3], 255) for index in used)


def _apply_palette(
    image: Image.Image, palette: tuple[tuple[int, int, int, int], ...]
) -> Image.Image:
    @lru_cache(maxsize=None)
    def nearest(red: int, green: int, blue: int) -> tuple[int, int, int, int]:
        return min(
            palette,
            key=lambda color: (
                (red - color[0]) * (red - color[0])
                + (green - color[1]) * (green - color[1])
                + (blue - color[2]) * (blue - color[2])
            ),
        )

    locked = image.convert("RGBA")
    locked.putdata(
        [
            nearest(red, green, blue) if alpha >= 128 else (0, 0, 0, 0)
            for red, green, blue, alpha in _pixels(locked)
        ]
    )
    return locked


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_approved_walk_art(
    model: CharacterAnimationSkin,
) -> tuple[list[Image.Image], list[Image.Image], dict[str, object]]:
    """Restore complete approved cels and apply only native-pixel cleanup.

    The generic motion clip selects the phase and owns root travel/timing.  It
    never redraws Dave.  Each phase instead receives one complete authored cel
    whose shoulders, anatomy, clothing, face, and occlusion were already
    resolved together by the original artist.
    """

    source_spec = model.art.walk_source
    source_path = _project_path(str(source_spec["path"]))
    source_bytes = source_path.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if source_sha256 != str(source_spec["sha256"]):
        raise ValueError(
            f"approved Dave art source changed: {source_sha256} != {source_spec['sha256']}"
        )

    atlas = Image.open(source_path).convert("RGBA")
    cell_width, cell_height = (int(value) for value in source_spec["cell_size"])
    if (cell_width, cell_height) != model.proportions.native_cell_size:
        raise ValueError("Dave art source and proportion profile use different cell sizes")
    row = int(source_spec["row"])
    source_indices = model.layers.phase_source_indices
    if source_indices != tuple(int(value) for value in source_spec["source_indices"]):
        raise ValueError("Dave layer rules and approved source phase map disagree")
    if len(source_indices) != model.motion.pose_count:
        raise ValueError("Dave art source does not cover every frozen motion pose")

    raw_cels: list[Image.Image] = []
    final_cels: list[Image.Image] = []
    frame_metrics: list[dict[str, object]] = []
    expected_frames = model.identity_validation.get("expected_frames")
    if not isinstance(expected_frames, list) or len(expected_frames) != len(source_indices):
        raise ValueError("Dave model has incomplete identity frame validation")

    for pose_index, (source_index, expected) in enumerate(
        zip(source_indices, expected_frames, strict=True)
    ):
        left = source_index * cell_width
        top = row * cell_height
        raw = atlas.crop((left, top, left + cell_width, top + cell_height))
        raw_cels.append(raw.copy())
        hard = raw.convert("RGBA")
        threshold = model.cleanup.alpha_threshold
        hard.putdata(
            [
                (red, green, blue, 255) if alpha >= threshold else (0, 0, 0, 0)
                for red, green, blue, alpha in _pixels(hard)
            ]
        )
        bounds = hard.getbbox()
        if bounds is None:
            raise ValueError(f"approved Dave walk cel {pose_index + 1} is empty")
        shift_y = model.cleanup.ground_y_px + 1 - bounds[3]
        registered = Image.new("RGBA", model.proportions.native_cell_size)
        registered.alpha_composite(hard, (0, shift_y))
        registered = _apply_palette(registered, model.art.master_palette)
        registered_bounds = registered.getbbox()
        alpha = registered.getchannel("A")
        alpha_sha256 = hashlib.sha256(alpha.tobytes()).hexdigest()
        opaque_pixels = sum(value >= threshold for value in _pixels(alpha))
        expected_bounds = tuple(int(value) for value in expected["registered_bbox"])
        checks = {
            "alpha_sha256": alpha_sha256 == str(expected["registered_alpha_sha256"]),
            "registered_bbox": registered_bounds == expected_bounds,
            "opaque_pixels": opaque_pixels == int(expected["opaque_pixels"]),
            "ground_shift_y": shift_y == int(expected["ground_shift_y"]),
        }
        if not all(checks.values()):
            failed = [name for name, passed in checks.items() if not passed]
            raise ValueError(
                f"approved Dave walk cel {pose_index + 1} drifted from the model sheet: {failed}"
            )
        final_cels.append(registered)
        frame_metrics.append(
            {
                "pose": pose_index + 1,
                "source_index": source_index,
                "registered_bbox": list(registered_bounds or ()),
                "opaque_pixels": opaque_pixels,
                "alpha_sha256": alpha_sha256,
                "ground_shift_y": shift_y,
                "maximum_proportion_deviation_px": 0,
                "palette_deviation_colors": 0,
            }
        )

    return raw_cels, final_cels, {
        "source": source_path.relative_to(PROJECT_ROOT).as_posix(),
        "source_sha256": source_sha256,
        "source_commit": model.art.source_commit,
        "mode": model.layers.mode,
        "frame_metrics": frame_metrics,
        "maximum_proportion_deviation_px": 0,
        "maximum_palette_deviation_colors": 0,
    }


def _masked_part(
    source: Image.Image,
    polygon: tuple[Point, ...],
    source_start: Point,
    source_end: Point,
) -> RigPart:
    mask = Image.new("L", source.size)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    alpha = ImageChops.multiply(source.getchannel("A"), mask)
    layer = source.copy()
    layer.putalpha(alpha)
    return RigPart(layer=layer, source_start=source_start, source_end=source_end)


def _masked_skin_limb_part(
    source: Image.Image,
    polygon: tuple[Point, ...],
    source_start: Point,
    source_end: Point,
) -> RigPart:
    polygon_mask = Image.new("L", source.size)
    ImageDraw.Draw(polygon_mask).polygon(polygon, fill=255)
    warm_mask = Image.new("L", source.size)
    warm_mask.putdata(
        [
            255
            if alpha >= 128
            and red > 70
            and red > green * 1.15
            and green > blue * 1.06
            else 0
            for red, green, blue, alpha in _pixels(source)
        ]
    )
    # Two native pixels retain the arm's authored dark outline, bracelet, and
    # highlight clusters without admitting the adjacent vest or denim mass.
    limb_mask = ImageChops.multiply(
        polygon_mask,
        warm_mask.filter(ImageFilter.MaxFilter(5)),
    )
    alpha = ImageChops.multiply(source.getchannel("A"), limb_mask)
    layer = source.copy()
    layer.putalpha(alpha)
    return RigPart(layer=layer, source_start=source_start, source_end=source_end)


def load_canonical_rig(path: Path) -> CanonicalDaveRig:
    atlas_bytes = path.read_bytes()
    atlas = Image.open(path).convert("RGBA")
    if atlas.size != (
        CELL_SIZE * CANONICAL_ATLAS_COLUMNS,
        CELL_SIZE * CANONICAL_ATLAS_ROWS,
    ):
        raise ValueError(f"unexpected canonical Dave atlas size: {atlas.size}")
    left = CANONICAL_CELL_COLUMN * CELL_SIZE
    top = CANONICAL_CELL_ROW * CELL_SIZE
    source = _hard_alpha(atlas.crop((left, top, left + CELL_SIZE, top + CELL_SIZE)))
    palette = _canonical_palette(source)
    source = _apply_palette(source, palette)

    # Every polygon and joint below is authored once against the first shipped
    # side-profile walk cell. The final cycle moves these immutable pixel
    # clusters as rigid bones; it never redraws or morphs Dave per frame.
    specifications: dict[
        str, tuple[tuple[Point, ...], Point, Point]
    ] = {
        "head": (
            ((47, 13), (70, 13), (77, 22), (76, 34), (68, 39), (51, 36), (47, 27)),
            (61, 34),
            (64, 24),
        ),
        "torso": (
            ((49, 31), (67, 32), (71, 49), (70, 67), (65, 73), (50, 71), (47, 50)),
            (61, 34),
            (61, 76),
        ),
        "pelvis": (
            ((41, 61), (73, 61), (75, 82), (67, 87), (49, 87), (41, 80)),
            (54, 76),
            (66, 78),
        ),
        "far_upper_arm": (
            ((47, 35), (58, 35), (59, 47), (54, 58), (45, 54), (43, 44)),
            (53, 39),
            (47, 54),
        ),
        "far_lower_arm": (
            ((41, 49), (53, 51), (52, 70), (44, 73), (38, 67)),
            (47, 54),
            (44, 67),
        ),
        "near_upper_arm": (
            ((55, 34), (67, 35), (70, 48), (66, 58), (58, 55), (54, 43)),
            (61, 39),
            (64, 54),
        ),
        "near_lower_arm": (
            ((59, 49), (70, 51), (84, 58), (85, 66), (79, 71), (67, 65), (59, 59)),
            (64, 54),
            (80, 64),
        ),
        "far_upper_leg": (
            ((47, 73), (62, 75), (61, 87), (50, 100), (37, 101), (38, 91)),
            (54, 77),
            (43, 96),
        ),
        "far_lower_leg": (
            ((35, 91), (50, 96), (45, 108), (37, 115), (27, 111), (29, 102)),
            (43, 96),
            (36, 110),
        ),
        "far_shoe": (
            ((27, 106), (49, 106), (56, 113), (55, 122), (29, 123), (26, 116)),
            (29, 120),
            (52, 122),
        ),
        "near_upper_leg": (
            ((57, 73), (70, 73), (78, 94), (74, 102), (65, 103), (58, 88)),
            (65, 78),
            (73, 96),
        ),
        "near_lower_leg": (
            ((66, 92), (79, 92), (84, 109), (79, 116), (70, 113), (67, 104)),
            (73, 96),
            (78, 111),
        ),
        "near_shoe": (
            ((70, 106), (89, 106), (102, 111), (101, 120), (75, 123), (70, 116)),
            (74, 121),
            (99, 112),
        ),
    }
    parts = {}
    for name, (polygon, source_start, source_end) in specifications.items():
        extractor = _masked_skin_limb_part if "arm" in name else _masked_part
        parts[name] = extractor(source, polygon, source_start, source_end)
    for name in ("torso", "pelvis"):
        part = parts[name]
        cleaned = part.layer.copy()
        cleaned.putdata(
            [
                (0, 0, 0, 0)
                if alpha >= 128
                and red > 70
                and red > green * 1.18
                and green > blue * 1.08
                else (red, green, blue, alpha)
                for red, green, blue, alpha in _pixels(cleaned)
            ]
        )
        parts[name] = RigPart(cleaned, part.source_start, part.source_end)
    if any(part.layer.getbbox() is None for part in parts.values()):
        raise ValueError("canonical rig contains an empty part")
    return CanonicalDaveRig(
        source_sha256=hashlib.sha256(atlas_bytes).hexdigest(),
        palette=palette,
        source_cell=source,
        parts=parts,
    )


def _transform_bone(part: RigPart, target_start: Point, target_end: Point) -> Image.Image:
    source_dx = part.source_end[0] - part.source_start[0]
    source_dy = part.source_end[1] - part.source_start[1]
    target_dx = target_end[0] - target_start[0]
    target_dy = target_end[1] - target_start[1]
    source_length = math.hypot(source_dx, source_dy)
    target_length = math.hypot(target_dx, target_dy)
    if source_length <= 0.0 or target_length <= 0.0:
        raise ValueError("rig bone collapsed")
    source_angle = math.atan2(source_dy, source_dx)
    target_angle = math.atan2(target_dy, target_dx)
    angle = target_angle - source_angle
    inverse_scale = source_length / target_length
    cosine = math.cos(angle)
    sine = math.sin(angle)
    a = cosine * inverse_scale
    b = sine * inverse_scale
    d = -sine * inverse_scale
    e = cosine * inverse_scale
    c = part.source_start[0] - a * target_start[0] - b * target_start[1]
    f = part.source_start[1] - d * target_start[0] - e * target_start[1]
    return part.layer.transform(
        (CELL_SIZE, CELL_SIZE),
        Image.Transform.AFFINE,
        (a, b, c, d, e, f),
        resample=Image.Resampling.NEAREST,
        fillcolor=(0, 0, 0, 0),
    )


def render_canonical_parts_sheet(rig: CanonicalDaveRig, path: Path) -> None:
    names = list(rig.parts)
    _contact_sheet(
        [rig.parts[name].layer for name in names],
        names,
        path,
        columns=4,
        cell=(168, 158),
    )


def _approved_reference_image(reference: Mapping[str, object]) -> Image.Image:
    source = Image.open(_project_path(str(reference["path"]))).convert("RGBA")
    if "row" not in reference or "column" not in reference:
        return source
    row = int(reference["row"])
    column = int(reference["column"])
    return source.crop(
        (
            column * CELL_SIZE,
            row * CELL_SIZE,
            (column + 1) * CELL_SIZE,
            (row + 1) * CELL_SIZE,
        )
    )


def render_approved_model_sheet(model: CharacterAnimationSkin, path: Path) -> None:
    references = model.art.approved_reference_frames
    panel_w, panel_h = 320, 280
    columns = 3
    rows = math.ceil(len(references) / columns)
    canvas = Image.new("RGBA", (panel_w * columns, panel_h * rows), (18, 20, 27, 255))
    draw = ImageDraw.Draw(canvas)
    for index, reference in enumerate(references):
        left = (index % columns) * panel_w
        top = (index // columns) * panel_h
        draw.rectangle(
            (left + 5, top + 5, left + panel_w - 6, top + panel_h - 6),
            outline=(99, 80, 120, 255),
            width=2,
        )
        image = _approved_reference_image(reference)
        shown = _fit_nearest(image, (250, 204))
        canvas.alpha_composite(
            shown,
            (left + (panel_w - shown.width) // 2, top + 34 + (204 - shown.height) // 2),
        )
        coordinate = "portrait"
        if "row" in reference:
            coordinate = f"atlas r{int(reference['row'])} c{int(reference['column'])}"
        draw.text(
            (left + 12, top + 10),
            coordinate.upper(),
            font=_font(13, bold=True),
            fill=(245, 239, 226, 255),
        )
        role = str(reference["role"])
        if len(role) > 47:
            role = role[:44] + "..."
        draw.text(
            (left + 12, top + 250),
            role,
            font=_font(10),
            fill=(187, 174, 194, 255),
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(path)


def render_palette_sheet(model: CharacterAnimationSkin, path: Path) -> None:
    palette = model.art.master_palette
    columns = 16
    swatch_w, swatch_h = 64, 52
    rows = math.ceil(len(palette) / columns)
    canvas = Image.new(
        "RGBA",
        (columns * swatch_w, 58 + rows * swatch_h),
        (18, 20, 27, 255),
    )
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (14, 12),
        f"BLACK DAVE MASTER PALETTE — {len(palette)} EXACT COLORS",
        font=_font(18, bold=True),
        fill=(245, 239, 226, 255),
    )
    for index, color in enumerate(palette):
        left = (index % columns) * swatch_w
        top = 58 + (index // columns) * swatch_h
        draw.rectangle((left + 3, top + 3, left + 61, top + 28), fill=color, outline=(128, 120, 137, 255))
        hex_color = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"
        draw.text((left + 4, top + 31), f"{index:03d} {hex_color}", font=_font(8), fill=(215, 207, 220, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(path)


def render_proportion_diagram(
    model: CharacterAnimationSkin,
    ruler_frame: Image.Image,
    path: Path,
) -> None:
    scale = 4
    canvas = Image.new("RGBA", (1040, 760), (18, 20, 27, 255))
    draw = ImageDraw.Draw(canvas)
    shown = ruler_frame.resize((CELL_SIZE * scale, CELL_SIZE * scale), Image.Resampling.NEAREST)
    origin = (30, 70)
    canvas.alpha_composite(shown, origin)
    ruler = model.proportions.ruler_source

    def screen(point: Iterable[int]) -> Point:
        x, y = (int(value) for value in point)
        return origin[0] + x * scale, origin[1] + y * scale

    colors = {
        "head": (255, 203, 79, 255),
        "shoulder": (69, 225, 230, 255),
        "chest": (255, 104, 154, 255),
        "waist": (164, 240, 104, 255),
        "pelvis": (171, 128, 255, 255),
    }
    head = tuple(int(value) for value in ruler["head_bounds"])
    draw.rectangle((*screen(head[:2]), *screen(head[2:])), outline=colors["head"], width=2)
    for name, key in (
        ("shoulder", "shoulder_span"),
        ("chest", "chest_span"),
        ("waist", "waist_span"),
        ("pelvis", "pelvis_span"),
    ):
        start, end = ruler[key]
        draw.line((*screen(start), *screen(end)), fill=colors[name], width=3)
    neck = screen(ruler["neck_anchor"])
    draw.ellipse((neck[0] - 5, neck[1] - 5, neck[0] + 5, neck[1] + 5), fill=(255, 255, 255, 255))
    ground = origin[1] + model.proportions.ground_y_px * scale
    draw.line((origin[0], ground, origin[0] + CELL_SIZE * scale, ground), fill=(236, 170, 65, 255), width=2)
    draw.text((24, 18), "APPROVED DAVE NATIVE-PIXEL PROPORTION RULER", font=_font(20, bold=True), fill=(245, 239, 226, 255))

    x = 580
    draw.text((x, 72), "BASIS: APPROVED WALK CEL R1 C0", font=_font(15, bold=True), fill=(245, 239, 226, 255))
    y = 110
    for name, value in model.proportions.measurements_px.items():
        label = name.replace("_", " ")
        draw.text((x, y), f"{label}: {value}px", font=_font(12), fill=(210, 202, 218, 255))
        y += 25
    y += 8
    draw.text((x, y), "LIMB RATIOS / STANDING HEIGHT", font=_font(13, bold=True), fill=(245, 239, 226, 255))
    y += 28
    for name, value in model.proportions.limb_length_ratios.items():
        draw.text((x, y), f"{name.replace('_', ' ')}: {value:.3f}", font=_font(11), fill=(180, 219, 222, 255))
        y += 22
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(path)


def _flat_color_pose(sprite: Image.Image) -> Image.Image:
    flat = Image.new("RGBA", sprite.size)
    result: list[tuple[int, int, int, int]] = []
    for index, (red, green, blue, alpha) in enumerate(_pixels(sprite.convert("RGBA"))):
        if alpha < 128:
            result.append((0, 0, 0, 0))
            continue
        y = index // sprite.width
        if blue > red * 1.25 and blue > green * 1.08:
            result.append((29, 83, 143, 255))
        elif red > green * 1.22 and green > blue * 1.04:
            result.append((185, 102, 46, 255))
        elif y >= 103 and red + green + blue > 175:
            result.append((230, 230, 232, 255))
        else:
            result.append((29, 30, 28, 255))
    flat.putdata(result)
    return flat


def _adapt_landmarks_to_authored_cel(
    sprite: Image.Image,
    pose: Pose,
) -> tuple[dict[str, Point], dict[str, float]]:
    """Map generic joints onto Dave's complete authored silhouette.

    The generic clip still supplies phase, side, timing, and the intended joint
    targets.  This Dave adapter snaps only the review landmarks into semantic
    body zones in the approved cel; it never moves or redraws art pixels.
    """

    alpha = sprite.getchannel("A")
    visible = [
        (x, y)
        for y in range(CELL_SIZE)
        for x in range(CELL_SIZE)
        if alpha.getpixel((x, y)) >= 128
    ]

    def eligible(name: str, point: Point) -> list[Point]:
        if name == "head_center":
            candidates = [(x, y) for x, y in visible if y <= 42]
        elif name == "neck" or "shoulder" in name:
            candidates = [(x, y) for x, y in visible if 20 <= y <= 58]
        elif any(token in name for token in ("elbow", "wrist", "hand")):
            candidates = [(x, y) for x, y in visible if 28 <= y <= 82]
        elif name == "pelvis" or "hip" in name:
            candidates = [(x, y) for x, y in visible if 52 <= y <= 94]
        elif "knee" in name:
            candidates = [(x, y) for x, y in visible if 72 <= y <= 110]
        elif "ankle" in name:
            candidates = [(x, y) for x, y in visible if y >= 88]
        else:
            candidates = [(x, y) for x, y in visible if y >= 98]
        return candidates or visible

    adapted: dict[str, Point] = {}
    deltas: dict[str, float] = {}
    for name, point in pose.landmarks.items():
        candidates = eligible(name, point)
        selected = min(
            candidates,
            key=lambda candidate: (
                (candidate[0] - point[0]) * (candidate[0] - point[0])
                + (candidate[1] - point[1]) * (candidate[1] - point[1]),
                abs(candidate[1] - point[1]),
                abs(candidate[0] - point[0]),
            ),
        )
        adapted[name] = selected
        deltas[name] = round(math.dist(point, selected), 3)
    return adapted, deltas


def character_adapter_metrics(
    sprites: list[Image.Image], poses: tuple[Pose, ...]
) -> dict[str, object]:
    per_pose: list[dict[str, object]] = []
    all_deltas: list[float] = []
    for sprite, pose in zip(sprites, poses, strict=True):
        _adapted, deltas = _adapt_landmarks_to_authored_cel(sprite, pose)
        all_deltas.extend(deltas.values())
        per_pose.append(
            {
                "pose": pose.index + 1,
                "maximum_joint_adapter_distance_px": max(deltas.values()),
                "mean_joint_adapter_distance_px": round(sum(deltas.values()) / len(deltas), 3),
            }
        )
    return {
        "method": "semantic-zone nearest authored-pixel landmark adapter; artwork is not transformed",
        "maximum_joint_adapter_distance_px": max(all_deltas),
        "mean_joint_adapter_distance_px": round(sum(all_deltas) / len(all_deltas), 3),
        "per_pose": per_pose,
    }


def render_flat_color_over_skeleton(
    sprites: list[Image.Image],
    poses: tuple[Pose, ...],
    path: Path,
) -> None:
    frames: list[Image.Image] = []
    for sprite, pose in zip(sprites, poses, strict=True):
        flat = _flat_color_pose(sprite)
        draw = ImageDraw.Draw(flat)
        landmarks, _deltas = _adapt_landmarks_to_authored_cel(sprite, pose)
        for start, end in (
            ("neck", "pelvis"),
            ("left_shoulder", "left_elbow"),
            ("left_elbow", "left_wrist"),
            ("right_shoulder", "right_elbow"),
            ("right_elbow", "right_wrist"),
            ("left_hip", "left_knee"),
            ("left_knee", "left_ankle"),
            ("right_hip", "right_knee"),
            ("right_knee", "right_ankle"),
            ("left_heel", "left_toe"),
            ("right_heel", "right_toe"),
        ):
            draw.line((*landmarks[start], *landmarks[end]), fill=(255, 47, 218, 255), width=1)
        for point in landmarks.values():
            draw.point(point, fill=(61, 250, 227, 255))
        frames.append(flat)
    _contact_sheet(
        frames,
        [f"{pose.index + 1:02d} {pose.name}" for pose in poses],
        path,
        columns=4,
        cell=(214, 178),
    )


def render_authored_pair_contact_sheet(
    approved: list[Image.Image],
    final: list[Image.Image],
    poses: tuple[Pose, ...],
    path: Path,
) -> None:
    panel_w, panel_h = 360, 226
    canvas = Image.new("RGBA", (panel_w * 3, panel_h * 4), (18, 20, 27, 255))
    draw = ImageDraw.Draw(canvas)
    for index, (source, sprite, pose) in enumerate(zip(approved, final, poses, strict=True)):
        left = (index % 3) * panel_w
        top = (index // 3) * panel_h
        draw.rectangle((left + 4, top + 4, left + 355, top + 221), outline=(99, 80, 120, 255), width=2)
        draw.text((left + 10, top + 9), f"{index + 1:02d} {pose.name}", font=_font(12, bold=True), fill=(245, 239, 226, 255))
        canvas.alpha_composite(_comparison_dave_frame(source, 176), (left + 4, top + 36))
        canvas.alpha_composite(_comparison_dave_frame(sprite, 176), (left + 180, top + 36))
        draw.text((left + 30, top + 205), "APPROVED ORIGINAL", font=_font(10), fill=(222, 196, 132, 255))
        draw.text((left + 222, top + 205), "FINAL CLEAN", font=_font(10), fill=(105, 217, 222, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(path)


def write_asset_inventory(model: CharacterAnimationSkin, path: Path) -> None:
    payload = {
        "character": model.character,
        "audit_status": "complete",
        "canonical_source_commit": model.art.source_commit,
        "assets": [dict(item) for item in model.art.asset_inventory],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _stance_leg(phase: int, root_x: int) -> dict[str, Point]:
    contact_x = 20.0 - ROOT_STEP * phase
    heel_y = (126, 126, 126, 126, 120, 116)[phase]
    toe_y = (126, 126, 126, 126, 126, 126)[phase]
    if phase <= 3:
        heel_x = contact_x
        toe_x = contact_x + (20, 20, 20, 19)[phase]
        ankle_x = contact_x + (5, 7, 8, 9)[phase]
        ankle_y = (113, 112, 111, 111)[phase]
    else:
        toe_x = contact_x
        heel_x = contact_x - 16
        ankle_x = contact_x + (-6, -7)[phase - 4]
        ankle_y = (107, 104)[phase - 4]
    knee_x = (11, 12, 8, 3, -3, -8)[phase]
    knee_y = (98, 103, 99, 96, 91, 90)[phase]
    return {
        "knee": _point(root_x + knee_x, knee_y),
        "ankle": _point(root_x + ankle_x, ankle_y),
        "heel": _point(root_x + heel_x, heel_y),
        "toe": _point(root_x + toe_x, toe_y),
    }


def _swing_leg(phase: int, root_x: int) -> dict[str, Point]:
    heel_x = (-26, -22, -15, -6, 5, 20)[phase]
    heel_y = (124, 119, 114, 112, 116, 124)[phase]
    toe_x = (-7, -3, 4, 13, 24, 40)[phase]
    toe_y = (126, 122, 118, 115, 120, 126)[phase]
    ankle_x = (-17, -14, -6, 2, 13, 28)[phase]
    ankle_y = (111, 108, 104, 101, 104, 111)[phase]
    knee_x = (-12, -10, -5, 2, 8, 12)[phase]
    knee_y = (98, 95, 91, 88, 91, 96)[phase]
    return {
        "knee": _point(root_x + knee_x, knee_y),
        "ankle": _point(root_x + ankle_x, ankle_y),
        "heel": _point(root_x + heel_x, heel_y),
        "toe": _point(root_x + toe_x, toe_y),
    }


def _arm_landmarks(shoulder: Point, swing: float, lag: float) -> tuple[Point, Point, Point]:
    sx, sy = shoulder
    elbow = _point(sx + swing * 7.0, sy + 13.0 - abs(swing))
    wrist = _point(sx + swing * 11.0 + lag * 2.5, sy + 24.0 - abs(swing) * 2.0)
    hand = _point(wrist[0] + (1 if swing >= 0 else -1), wrist[1] + 1)
    return elbow, wrist, hand


def build_pose(index: int) -> Pose:
    phase = index % 6
    second_half = index >= 6
    support = "right" if second_half else "left"
    swing_leg_name = "left" if second_half else "right"
    pelvis_y = PELVIS_Y[index]
    yaw = TORSO_YAW[index]
    shoulder_tilt = round(SHOULDER_ANGLE_DEG[index] / 3.0)
    hip_tilt = round(HIP_ANGLE_DEG[index] / 3.0)

    neck = _point(ROOT_X + yaw * 4.0, pelvis_y - 42)
    # Preserve the approved gait below the pelvis while restoring the combat
    # atlas' compact upper-body ruler.  The former seven-pixel half-span and
    # low shoulder line produced a long neck, collapsed ribcage, and legs that
    # appeared to belong to a much larger character.
    shoulder_spread = 10 + round(abs(yaw) * 4)
    left_shoulder = _point(neck[0] - shoulder_spread, neck[1] + 5 - shoulder_tilt)
    right_shoulder = _point(neck[0] + shoulder_spread, neck[1] + 5 + shoulder_tilt)
    left_hip = _point(ROOT_X - 4, pelvis_y - hip_tilt)
    right_hip = _point(ROOT_X + 4, pelvis_y + hip_tilt)

    cycle = math.tau * index / POSE_COUNT
    left_swing = -math.cos(cycle)
    right_swing = -left_swing
    left_elbow, left_wrist, left_hand = _arm_landmarks(
        left_shoulder, left_swing, math.sin(cycle - 0.45)
    )
    right_elbow, right_wrist, right_hand = _arm_landmarks(
        right_shoulder, right_swing, math.sin(cycle + math.pi - 0.45)
    )

    stance = _stance_leg(phase, ROOT_X)
    swing = _swing_leg(phase, ROOT_X)
    legs = {support: stance, swing_leg_name: swing}
    landmarks: dict[str, Point] = {
        "head_center": _point(neck[0] + 3, neck[1] - 10),
        "neck": neck,
        "left_shoulder": left_shoulder,
        "right_shoulder": right_shoulder,
        "left_elbow": left_elbow,
        "right_elbow": right_elbow,
        "left_wrist": left_wrist,
        "right_wrist": right_wrist,
        "left_hand": left_hand,
        "right_hand": right_hand,
        "pelvis": (ROOT_X, pelvis_y),
        "left_hip": left_hip,
        "right_hip": right_hip,
    }
    for side in ("left", "right"):
        for joint in ("knee", "ankle", "heel", "toe"):
            landmarks[f"{side}_{joint}"] = legs[side][joint]

    if phase <= 3:
        contact_landmark = f"{support}_heel"
        stance_contact = "heel" if phase == 0 else "flat"
    else:
        contact_landmark = f"{support}_toe"
        stance_contact = "heel_rise" if phase == 4 else "toe_off"
    other_contact = ("toe", "airborne", "airborne", "airborne", "airborne", "heel_reach")[phase]
    foot_contact = {
        support: stance_contact,
        swing_leg_name: other_contact,
    }
    return Pose(
        index=index,
        name=PHASE_NAMES[index],
        source_frame=SOURCE_FRAME_INDICES[index],
        support_foot=support,
        near_arm="left",
        near_leg="left",
        foot_contact=foot_contact,
        torso_yaw=yaw,
        shoulder_angle_deg=SHOULDER_ANGLE_DEG[index],
        hip_angle_deg=HIP_ANGLE_DEG[index],
        pelvis_height=GROUND_Y - pelvis_y,
        root_distance=round(index * ROOT_STEP, 4),
        contact_landmark=contact_landmark,
        landmarks=landmarks,
    )


def build_poses() -> tuple[Pose, ...]:
    return tuple(build_pose(index) for index in range(POSE_COUNT))


def _pose_json(poses: Iterable[Pose]) -> dict[str, object]:
    result = []
    for pose in poses:
        pelvis = pose.landmarks["pelvis"]
        normalized = {
            name: [
                round((point[0] - pelvis[0]) / DAVE_HEIGHT, 4),
                round((point[1] - pelvis[1]) / DAVE_HEIGHT, 4),
            ]
            for name, point in pose.landmarks.items()
        }
        result.append(
            {
                "index": pose.index,
                "phase": pose.name,
                "reference_source_frame": pose.source_frame,
                "duration_ms": 80,
                "root_distance_px": pose.root_distance,
                "support_foot": pose.support_foot,
                "contact_landmark": pose.contact_landmark,
                "foot_contact": dict(pose.foot_contact),
                "near_arm": pose.near_arm,
                "near_leg": pose.near_leg,
                "torso_yaw": pose.torso_yaw,
                "shoulder_angle_deg": pose.shoulder_angle_deg,
                "hip_angle_deg": pose.hip_angle_deg,
                "pelvis_height_px": pose.pelvis_height,
                "landmarks_px": {name: list(point) for name, point in pose.landmarks.items()},
                "landmarks_normalized_to_pelvis_and_height": normalized,
            }
        )
    return {
        "schema_version": 1,
        "source": "supplied reference GIF; repeated 40 ms frame pairs reduced to 12 estimated poses",
        "coordinate_system": {
            "origin": "pelvis",
            "x_positive": "facing direction",
            "y_positive": "down",
            "character_height_px": DAVE_HEIGHT,
            "leg_length_px": LEG_LENGTH,
            "shoulder_width_px": SHOULDER_WIDTH,
        },
        "stride_distance_px": STRIDE_DISTANCE,
        "pose_count": POSE_COUNT,
        "loop_duration_ms": 960,
        "required_landmarks": list(LANDMARK_NAMES),
        "poses": result,
    }


def _load_reference(path: Path) -> tuple[list[Image.Image], list[int]]:
    source = Image.open(path)
    frames: list[Image.Image] = []
    durations: list[int] = []
    for index in range(source.n_frames):
        source.seek(index)
        frames.append(source.convert("RGBA").copy())
        durations.append(int(source.info.get("duration", 40) or 40))
    if len(frames) != 24:
        raise ValueError(f"expected 24 reference frames, got {len(frames)}")
    if any(duration != 40 for duration in durations):
        raise ValueError(f"reference timing changed: {sorted(set(durations))}")
    for pair in range(12):
        difference = ImageChops.difference(
            frames[pair * 2].convert("RGB"), frames[pair * 2 + 1].convert("RGB")
        )
        changed = sum(1 for pixel in _pixels(difference) if pixel != (0, 0, 0))
        if changed > REFERENCE_PAIR_MAX_CHANGED_PIXELS:
            raise ValueError(
                f"reference frame pair {pair} changed {changed} pixels; no longer a repeated pose"
            )
    return frames, durations


def _reference_motion_bounds(frames: list[Image.Image]) -> tuple[int, int, int, int]:
    motion = Image.new("L", frames[0].size)
    for frame in frames[1:]:
        difference = ImageChops.difference(frames[0].convert("RGB"), frame.convert("RGB")).convert("L")
        motion = ImageChops.lighter(motion, difference.point(lambda value: 255 if value > 12 else 0))
    bounds = motion.getbbox()
    if bounds is None:
        raise ValueError("reference has no animated pixels")
    left, top, right, bottom = bounds
    padding = 28
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(frames[0].width, right + padding),
        min(frames[0].height, bottom + padding),
    )


def _fit_nearest(image: Image.Image, maximum: tuple[int, int]) -> Image.Image:
    ratio = min(maximum[0] / image.width, maximum[1] / image.height)
    size = (max(1, round(image.width * ratio)), max(1, round(image.height * ratio)))
    return image.resize(size, Image.Resampling.NEAREST)


def _contact_sheet(
    frames: list[Image.Image],
    labels: list[str],
    path: Path,
    *,
    columns: int = 6,
    cell: tuple[int, int] = (240, 250),
    background: tuple[int, int, int, int] = (18, 20, 27, 255),
) -> None:
    rows = math.ceil(len(frames) / columns)
    canvas = Image.new("RGBA", (columns * cell[0], rows * cell[1]), background)
    draw = ImageDraw.Draw(canvas)
    font = _font(13, bold=True)
    for index, frame in enumerate(frames):
        fitted = _fit_nearest(frame, (cell[0] - 16, cell[1] - 38))
        left = (index % columns) * cell[0]
        top = (index // columns) * cell[1]
        canvas.alpha_composite(
            fitted,
            (left + (cell[0] - fitted.width) // 2, top + 28 + (cell[1] - 34 - fitted.height) // 2),
        )
        draw.text((left + 7, top + 6), labels[index], fill=(245, 239, 226, 255), font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(path)


def render_reference_contact_sheet(
    frames: list[Image.Image], bounds: tuple[int, int, int, int], path: Path
) -> list[Image.Image]:
    unique = [frames[index].crop(bounds) for index in SOURCE_FRAME_INDICES]
    labels = [f"{index + 1:02d}  {PHASE_NAMES[index]}" for index in range(POSE_COUNT)]
    _contact_sheet(unique, labels, path)
    return unique


def _line(
    draw: ImageDraw.ImageDraw,
    points: Iterable[Point],
    fill: tuple[int, int, int, int],
    width: int,
) -> None:
    draw.line(list(points), fill=fill, width=width, joint="curve")


def render_skeleton_pose(pose: Pose) -> Image.Image:
    image = Image.new("RGBA", (CELL_SIZE, CELL_SIZE))
    draw = ImageDraw.Draw(image)
    far = (78, 115, 151, 255)
    near = (244, 178, 79, 255)
    torso = (224, 232, 238, 255)
    joint = (255, 93, 91, 255)
    lm = pose.landmarks
    _line(draw, (lm["right_hip"], lm["right_knee"], lm["right_ankle"]), far, 4)
    _line(draw, (lm["right_heel"], lm["right_toe"]), far, 4)
    _line(draw, (lm["right_shoulder"], lm["right_elbow"], lm["right_wrist"]), far, 4)
    draw.polygon(
        [lm["left_shoulder"], lm["right_shoulder"], lm["right_hip"], lm["left_hip"]],
        outline=torso,
    )
    _line(draw, (lm["pelvis"], lm["neck"], lm["head_center"]), torso, 3)
    _line(draw, (lm["left_hip"], lm["left_knee"], lm["left_ankle"]), near, 5)
    _line(draw, (lm["left_heel"], lm["left_toe"]), near, 5)
    _line(draw, (lm["left_shoulder"], lm["left_elbow"], lm["left_wrist"]), near, 5)
    for name in LANDMARK_NAMES:
        x, y = lm[name]
        radius = 2 if name in {"pelvis", "left_heel", "right_heel", "left_toe", "right_toe"} else 1
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=joint)
    return image


def _canonical_color(
    rig: CanonicalDaveRig,
    target: tuple[int, int, int],
) -> tuple[int, int, int, int]:
    return min(
        rig.palette,
        key=lambda color: (
            (target[0] - color[0]) * (target[0] - color[0])
            + (target[1] - color[1]) * (target[1] - color[1])
            + (target[2] - color[2]) * (target[2] - color[2])
        ),
    )


HANDDRAWN_NEAR_ARM_LAYER = (
    "behind",
    "behind",
    "behind",
    "split",
    "front",
    "front",
    "front",
    "front",
    "split",
    "split",
    "behind",
    "behind",
)


def _lerp_point(start: Point, end: Point, amount: float) -> Point:
    return _point(
        start[0] + (end[0] - start[0]) * amount,
        start[1] + (end[1] - start[1]) * amount,
    )


def _normal(start: Point, end: Point) -> tuple[float, float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    if length <= 0.0:
        return 0.0, -1.0
    return -dy / length, dx / length


def _ribbon_polygon(
    points: tuple[Point, ...], widths: tuple[float, ...]
) -> tuple[Point, ...]:
    if len(points) != len(widths) or len(points) < 2:
        raise ValueError("ribbon points and widths must have matching lengths")
    left: list[Point] = []
    right: list[Point] = []
    for index, (point, width) in enumerate(zip(points, widths, strict=True)):
        previous = points[max(0, index - 1)]
        following = points[min(len(points) - 1, index + 1)]
        nx, ny = _normal(previous, following)
        left.append(_point(point[0] + nx * width, point[1] + ny * width))
        right.append(_point(point[0] - nx * width, point[1] - ny * width))
    return tuple(left + list(reversed(right)))


def _draw_ribbon(
    draw: ImageDraw.ImageDraw,
    points: tuple[Point, ...],
    widths: tuple[float, ...],
    *,
    outline: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    outline_padding: float = 1.5,
) -> None:
    draw.polygon(
        _ribbon_polygon(points, tuple(width + outline_padding for width in widths)),
        fill=outline,
    )
    draw.polygon(_ribbon_polygon(points, widths), fill=fill)


def _disc_box(center: Point, radius_x: int, radius_y: int | None = None) -> tuple[int, int, int, int]:
    radius_y = radius_x if radius_y is None else radius_y
    return (
        center[0] - radius_x,
        center[1] - radius_y,
        center[0] + radius_x,
        center[1] + radius_y,
    )


def _draw_joint_disc(
    draw: ImageDraw.ImageDraw,
    center: Point,
    radius_x: int,
    radius_y: int,
    outline: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
) -> None:
    draw.ellipse(_disc_box(center, radius_x + 1, radius_y + 1), fill=outline)
    draw.ellipse(_disc_box(center, radius_x, radius_y), fill=fill)


def _handdrawn_colors(rig: CanonicalDaveRig) -> dict[str, tuple[int, int, int, int]]:
    targets = {
        "outline": (14, 15, 22),
        "deep_outline": (5, 7, 12),
        "skin_deep": (76, 37, 23),
        "skin_shadow": (118, 57, 28),
        "skin_mid": (174, 91, 42),
        "skin_light": (193, 123, 64),
        "skin_high": (217, 198, 183),
        "tank": (19, 24, 29),
        "tank_light": (53, 52, 51),
        "tank_high": (104, 92, 87),
        "tank_shadow": (9, 12, 17),
        "denim_deep": (13, 45, 74),
        "denim_shadow": (17, 69, 108),
        "denim_mid": (24, 96, 150),
        "denim_light": (54, 89, 126),
        "denim_stitch": (135, 164, 178),
        "shoe_dark": (20, 28, 39),
        "shoe_mid": (44, 61, 75),
        "white": (226, 228, 218),
        "white_shadow": (145, 165, 173),
        "belt": (42, 29, 27),
        "gold": (219, 151, 51),
    }
    return {name: _canonical_color(rig, target) for name, target in targets.items()}


def _draw_arm_sections(
    image: Image.Image,
    pose: Pose,
    side: str,
    colors: Mapping[str, tuple[int, int, int, int]],
    *,
    depth: str,
    sections: tuple[str, ...] = ("upper", "lower", "hand"),
) -> None:
    lm = pose.landmarks
    shoulder = lm[f"{side}_shoulder"]
    elbow = lm[f"{side}_elbow"]
    wrist = lm[f"{side}_wrist"]
    hand = lm[f"{side}_hand"]
    draw = ImageDraw.Draw(image)
    near = depth == "near"
    outline = colors["outline"]
    skin = colors["skin_mid"] if near else colors["skin_shadow"]
    shadow = colors["skin_shadow"] if near else colors["skin_deep"]
    light = colors["skin_light"] if near else colors["skin_mid"]

    if "upper" in sections:
        upper_mid = _lerp_point(shoulder, elbow, 0.58)
        upper_points = (shoulder, upper_mid, elbow)
        # Keep the authored shoulder mass, then taper decisively through the
        # upper arm. The landmarks remain fixed; only the visible silhouette
        # is corrected to match Dave's compact concept-art proportions.
        upper_widths = (5.2 if near else 4.5, 5.8 if near else 5.0, 3.6 if near else 3.2)
        _draw_ribbon(draw, upper_points, upper_widths, outline=outline, fill=skin)
        # Fill the insertion inside the already outlined ribbon. A standalone
        # outlined shoulder disc reads as a puppet joint and creates the exact
        # duplicated-deltoid artifact this pass is replacing.
        draw.ellipse(_disc_box(shoulder, 4 if near else 3, 4 if near else 3), fill=skin)
        highlight_start = _lerp_point(shoulder, upper_mid, 0.28)
        highlight_end = _lerp_point(upper_mid, elbow, 0.45)
        draw.line(
            (
                highlight_start[0] - 1,
                highlight_start[1] - 1,
                highlight_end[0] - 1,
                highlight_end[1] - 1,
            ),
            fill=light,
            width=2 if near else 1,
        )
        draw.line(
            (
                upper_mid[0] + 2,
                upper_mid[1] + 1,
                elbow[0] + 1,
                elbow[1],
            ),
            fill=shadow,
            width=2,
        )
        muscle_center = _lerp_point(shoulder, elbow, 0.47)
        draw.line(
            (
                muscle_center[0] - 2,
                muscle_center[1] + 2,
                muscle_center[0] + 1,
                muscle_center[1] + 3,
            ),
            fill=shadow,
            width=1,
        )
        draw.point((muscle_center[0] - 2, muscle_center[1] - 2), fill=light)
        if near:
            draw.point((muscle_center[0] - 3, muscle_center[1] - 2), fill=colors["skin_high"])

    if "lower" in sections:
        lower_mid = _lerp_point(elbow, wrist, 0.58)
        lower_points = (elbow, lower_mid, wrist)
        lower_widths = (3.3 if near else 2.9, 3.8 if near else 3.3, 2.4 if near else 2.1)
        _draw_ribbon(draw, lower_points, lower_widths, outline=outline, fill=skin)
        draw.ellipse(_disc_box(elbow, 3, 3), fill=skin)
        draw.line(
            (
                lower_mid[0] - 1,
                lower_mid[1] - 1,
                wrist[0] - 1,
                wrist[1] - 1,
            ),
            fill=light,
            width=1,
        )
        bend_x = round((shoulder[0] + wrist[0]) / 2)
        draw.line(
            (elbow[0], elbow[1], bend_x, elbow[1] + (1 if wrist[1] >= elbow[1] else -1)),
            fill=shadow,
            width=1,
        )
        forearm_detail = _lerp_point(elbow, wrist, 0.46)
        draw.line(
            (
                forearm_detail[0] + 1,
                forearm_detail[1] + 1,
                wrist[0] + 1,
                wrist[1],
            ),
            fill=shadow,
            width=1,
        )

    if "hand" in sections:
        _draw_ribbon(
            draw,
            (wrist, hand),
            (3.0 if near else 2.6, 3.5 if near else 3.0),
            outline=outline,
            fill=skin,
            outline_padding=1.0,
        )
        fist_center = hand
        fist_radius_x = 5 if near else 4
        fist_radius_y = 4 if near else 3
        direction = 1 if hand[0] >= wrist[0] else -1
        fist_outer = (
            (fist_center[0] - direction * fist_radius_x, fist_center[1] - 1),
            (fist_center[0] - direction * 2, fist_center[1] - fist_radius_y),
            (fist_center[0] + direction * 3, fist_center[1] - fist_radius_y),
            (fist_center[0] + direction * fist_radius_x, fist_center[1]),
            (fist_center[0] + direction * 2, fist_center[1] + fist_radius_y),
            (fist_center[0] - direction * 3, fist_center[1] + fist_radius_y - 1),
        )
        draw.polygon(fist_outer, fill=outline)
        fist_inner = tuple(_lerp_point(point, fist_center, 0.22) for point in fist_outer)
        draw.polygon(fist_inner, fill=skin)
        knuckle_y = fist_center[1] - 1
        draw.line(
            (
                fist_center[0] + direction,
                knuckle_y - 2,
                fist_center[0] + direction * 3,
                knuckle_y,
            ),
            fill=light,
            width=1,
        )
        draw.point((fist_center[0] - direction * 2, fist_center[1] + 2), fill=shadow)


def _draw_shoe(
    image: Image.Image,
    pose: Pose,
    side: str,
    colors: Mapping[str, tuple[int, int, int, int]],
    *,
    depth: str,
) -> None:
    lm = pose.landmarks
    ankle = lm[f"{side}_ankle"]
    heel = lm[f"{side}_heel"]
    toe = lm[f"{side}_toe"]
    dx = toe[0] - heel[0]
    dy = toe[1] - heel[1]
    length = max(1.0, math.hypot(dx, dy))
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    if ny > 0.0:
        nx, ny = -nx, -ny

    def local(along: float, up: float) -> Point:
        return _point(heel[0] + ux * along + nx * up, heel[1] + uy * along + ny * up)

    collar = _lerp_point(ankle, local(4.0, 11.0), 0.34)
    outer = (
        local(-2.0, 0.0),
        collar,
        local(6.0, 11.0),
        local(max(8.0, length - 3.0), 7.0),
        local(length + 2.0, 2.0),
        local(length + 1.0, 0.0),
    )
    draw = ImageDraw.Draw(image)
    # Build a high-top collar from the authored ankle to the shoe body. This
    # closes the airborne heel gap without changing the ankle, heel, or toe
    # landmarks and prevents detached footwear islands.
    draw.line((*ankle, *collar), fill=colors["outline"], width=7)
    draw.line(
        (*ankle, *collar),
        fill=colors["shoe_mid"] if depth == "near" else colors["shoe_dark"],
        width=4,
    )
    draw.polygon(outer, fill=colors["outline"])
    inner = (
        local(-0.5, 1.0),
        _lerp_point(collar, local(5.0, 7.0), 0.36),
        local(6.0, 9.0),
        local(max(8.0, length - 3.0), 6.0),
        local(length, 2.0),
        local(length, 1.0),
    )
    draw.polygon(inner, fill=colors["shoe_mid"] if depth == "near" else colors["shoe_dark"])
    sole = (
        local(-1.0, 0.0),
        local(length + 1.0, 0.0),
        local(length + 0.5, 2.0),
        local(-0.5, 2.0),
    )
    draw.polygon(sole, fill=colors["white"] if depth == "near" else colors["white_shadow"])
    draw.line((*local(-1.0, 0.0), *local(length + 1.0, 0.0)), fill=colors["outline"], width=1)
    toe_cap = local(length - 1.5, 3.0)
    draw.line(
        (*local(length - 6.0, 5.0), *toe_cap),
        fill=colors["white"],
        width=2,
    )
    for lace_offset in (0.0, 3.0):
        lace_a = local(6.0 + lace_offset, 7.0)
        lace_b = local(10.0 + lace_offset, 5.5)
        draw.line((*lace_a, *lace_b), fill=colors["white"], width=1)
    heel_patch = local(1.0, 6.0)
    draw.line((*heel_patch, *local(4.0, 7.0)), fill=colors["white_shadow"], width=2)


def _draw_leg(
    image: Image.Image,
    pose: Pose,
    side: str,
    colors: Mapping[str, tuple[int, int, int, int]],
    *,
    depth: str,
) -> None:
    lm = pose.landmarks
    hip = lm[f"{side}_hip"]
    knee = lm[f"{side}_knee"]
    ankle = lm[f"{side}_ankle"]
    thigh_mid = _lerp_point(hip, knee, 0.52)
    calf_mid = _lerp_point(knee, ankle, 0.54)
    near = depth == "near"
    support = pose.support_foot == side
    fill = colors["denim_mid"] if near else colors["denim_shadow"]
    fold = colors["denim_light"] if near else colors["denim_mid"]
    shadow = colors["denim_shadow"] if near else colors["denim_deep"]
    points = (hip, thigh_mid, knee, calf_mid, ankle)
    widths = (
        7.0 if near else 6.2,
        (8.8 if support else 8.2) if near else (7.8 if support else 7.2),
        6.8 if near else 5.9,
        7.2 if near else 6.3,
        4.4 if near else 3.8,
    )
    draw = ImageDraw.Draw(image)
    _draw_ribbon(draw, points, widths, outline=colors["outline"], fill=fill)
    # The thigh and calf ribbons already overlap at the knee. Fill that union
    # without encircling it, so the compressed joint reads as denim rather
    # than a mechanical hinge.
    draw.ellipse(_disc_box(knee, 5 if near else 4, 4 if near else 3), fill=fill)
    draw.line(
        (
            thigh_mid[0] - 2,
            thigh_mid[1] - 1,
            knee[0] - 1,
            knee[1] - 2,
        ),
        fill=fold,
        width=2 if near else 1,
    )
    inner_shift = 2 if side == "left" else -2
    inner_seam = tuple((point[0] + inner_shift, point[1]) for point in points)
    draw.line(inner_seam, fill=shadow, width=2 if near else 1, joint="curve")
    outer_shift = -2 if side == "left" else 2
    outer_highlight = (
        (thigh_mid[0] + outer_shift, thigh_mid[1] - 2),
        (knee[0] + outer_shift, knee[1] - 2),
        (calf_mid[0] + outer_shift, calf_mid[1] - 1),
    )
    draw.line(outer_highlight, fill=fold, width=2 if near else 1, joint="curve")
    if near:
        stitch = colors["denim_stitch"]
        for amount in (0.28, 0.62):
            stitch_point = _lerp_point(thigh_mid, knee, amount)
            draw.point((stitch_point[0] + outer_shift, stitch_point[1] - 1), fill=stitch)
    knee_fold_end = _lerp_point(knee, calf_mid, 0.26)
    draw.line((*knee, *knee_fold_end), fill=shadow, width=2)
    calf_fold_start = _lerp_point(knee, calf_mid, 0.56)
    calf_fold_end = _lerp_point(calf_mid, ankle, 0.62)
    draw.line(
        (
            calf_fold_start[0] - 1,
            calf_fold_start[1],
            calf_fold_end[0] - 1,
            calf_fold_end[1],
        ),
        fill=fold,
        width=1,
    )
    if support:
        compression = _lerp_point(hip, knee, 0.78)
        draw.line(
            (compression[0] - 3, compression[1], compression[0] + 2, compression[1] + 2),
            fill=shadow,
            width=1,
        )
        draw.line(
            (
                compression[0] - 1,
                compression[1] - 3,
                compression[0] + 4,
                compression[1] - 1,
            ),
            fill=fold,
            width=1,
        )
    else:
        stretch = _lerp_point(hip, knee, 0.34)
        draw.line(
            (stretch[0] - 3, stretch[1] - 1, stretch[0] + 2, stretch[1] + 1),
            fill=fold,
            width=1,
        )
    _draw_shoe(image, pose, side, colors, depth=depth)


def _draw_pelvis_and_belt(
    image: Image.Image,
    pose: Pose,
    colors: Mapping[str, tuple[int, int, int, int]],
) -> None:
    lm = pose.landmarks
    left_hip = lm["left_hip"]
    right_hip = lm["right_hip"]
    pelvis = lm["pelvis"]
    draw = ImageDraw.Draw(image)
    outer = (
        (left_hip[0] - 7, left_hip[1] - 6),
        (right_hip[0] + 7, right_hip[1] - 6),
        (right_hip[0] + 8, right_hip[1] + 7),
        (pelvis[0] + 4, pelvis[1] + 11),
        (pelvis[0] - 5, pelvis[1] + 11),
        (left_hip[0] - 8, left_hip[1] + 7),
    )
    draw.polygon(outer, fill=colors["outline"])
    inner = tuple(
        _lerp_point(point, pelvis, 0.12)
        for point in outer
    )
    draw.polygon(inner, fill=colors["denim_shadow"])
    belt_y = round((left_hip[1] + right_hip[1]) / 2) - 3
    belt_left = pelvis[0] - 12
    belt_right = pelvis[0] + 12
    draw.line((belt_left, belt_y, belt_right, belt_y), fill=colors["outline"], width=4)
    draw.line((belt_left + 1, belt_y - 1, belt_right - 1, belt_y - 1), fill=colors["belt"], width=2)
    draw.rectangle((pelvis[0] - 2, belt_y - 2, pelvis[0] + 2, belt_y + 2), fill=colors["gold"], outline=colors["outline"])
    draw.line((pelvis[0] - 8, belt_y - 2, pelvis[0] - 8, belt_y + 3), fill=colors["gold"], width=1)
    draw.line((pelvis[0] + 8, belt_y - 2, pelvis[0] + 8, belt_y + 3), fill=colors["gold"], width=1)

    pouch_x = right_hip[0] + 7
    pouch_y = right_hip[1] + 4
    draw.rounded_rectangle(
        (pouch_x - 4, pouch_y - 3, pouch_x + 4, pouch_y + 7),
        radius=2,
        fill=colors["denim_deep"],
        outline=colors["outline"],
        width=1,
    )
    draw.rectangle((pouch_x - 2, pouch_y, pouch_x + 2, pouch_y + 4), outline=colors["denim_light"], width=1)
    draw.point((pouch_x, pouch_y + 2), fill=colors["gold"])
    pocket_x = left_hip[0] - 2
    draw.arc((pocket_x - 4, left_hip[1], pocket_x + 5, left_hip[1] + 8), 5, 165, fill=colors["denim_light"], width=1)


def _draw_torso_and_neck(
    image: Image.Image,
    pose: Pose,
    colors: Mapping[str, tuple[int, int, int, int]],
) -> None:
    lm = pose.landmarks
    neck = lm["neck"]
    left_shoulder = lm["left_shoulder"]
    right_shoulder = lm["right_shoulder"]
    pelvis = lm["pelvis"]
    yaw_shift = round(pose.torso_yaw * 4.0)
    waist_y = pelvis[1] - 5
    # Dave's combat art has a broad ribcage tapering into a visible but not
    # pinched waist.  The previous walk redraw narrowed this to a tube and
    # made his pants and arms look borrowed from a larger character.
    waist_left = (pelvis[0] - 10 + yaw_shift, waist_y)
    waist_right = (pelvis[0] + 10 + yaw_shift, waist_y)
    draw = ImageDraw.Draw(image)

    neck_outer = (
        (neck[0] - 5, neck[1] - 4),
        (neck[0] + 5, neck[1] - 4),
        (neck[0] + 6 + yaw_shift, neck[1] + 10),
        (neck[0] - 5 + yaw_shift, neck[1] + 10),
    )
    draw.polygon(neck_outer, fill=colors["outline"])
    neck_inner = (
        (neck[0] - 3, neck[1] - 4),
        (neck[0] + 3, neck[1] - 4),
        (neck[0] + 4 + yaw_shift, neck[1] + 9),
        (neck[0] - 3 + yaw_shift, neck[1] + 9),
    )
    draw.polygon(neck_inner, fill=colors["skin_shadow"])
    draw.line((neck[0] - 2, neck[1] - 3, neck[0] - 1 + yaw_shift, neck[1] + 7), fill=colors["skin_light"], width=1)

    chest_outer = (
        (neck[0] - 4, neck[1] + 2),
        (left_shoulder[0] - 5, left_shoulder[1] - 4),
        (left_shoulder[0] - 5, left_shoulder[1] + 9),
        (waist_left[0] - 2, waist_left[1]),
        (waist_right[0] + 2, waist_right[1]),
        (right_shoulder[0] + 5, right_shoulder[1] + 9),
        (right_shoulder[0] + 5, right_shoulder[1] - 4),
        (neck[0] + 4, neck[1] + 2),
    )
    draw.polygon(chest_outer, fill=colors["outline"])
    chest_inner = tuple(_lerp_point(point, (neck[0] + yaw_shift, neck[1] + 18), 0.05) for point in chest_outer)
    draw.polygon(chest_inner, fill=colors["tank"])

    tank = (
        (neck[0] - 6 + yaw_shift, neck[1] + 4),
        (left_shoulder[0] - 2, left_shoulder[1] - 2),
        (left_shoulder[0] - 3, left_shoulder[1] + 10),
        waist_left,
        waist_right,
        (right_shoulder[0] + 3, right_shoulder[1] + 10),
        (right_shoulder[0] + 2, right_shoulder[1] - 2),
        (neck[0] + 6 + yaw_shift, neck[1] + 4),
        (neck[0] + yaw_shift, neck[1] + 10),
    )
    draw.polygon(tank, fill=colors["tank_shadow"])
    tank_inner = tuple(_lerp_point(point, (pelvis[0] + yaw_shift, neck[1] + 23), 0.10) for point in tank)
    draw.polygon(tank_inner, fill=colors["tank"])
    exposed_chest = (
        (neck[0] - 4 + yaw_shift, neck[1] + 4),
        (neck[0] + yaw_shift, neck[1] + 10),
        (neck[0] + 4 + yaw_shift, neck[1] + 4),
        (neck[0] + 2 + yaw_shift, neck[1] + 1),
        (neck[0] - 2 + yaw_shift, neck[1] + 1),
    )
    draw.polygon(exposed_chest, fill=colors["skin_shadow"])
    draw.line(
        (neck[0] - 2 + yaw_shift, neck[1] + 3, neck[0] + 1 + yaw_shift, neck[1] + 7),
        fill=colors["skin_light"],
        width=1,
    )
    collar = (
        (neck[0] - 4 + yaw_shift, neck[1] + 5),
        (neck[0] + yaw_shift, neck[1] + 11),
        (neck[0] + 4 + yaw_shift, neck[1] + 5),
    )
    draw.line(collar, fill=colors["tank_light"], width=1, joint="curve")
    draw.line(
        (waist_left[0] + 3, waist_y - 11, waist_left[0] + 5, waist_y - 2),
        fill=colors["tank_light"],
        width=1,
    )
    draw.point((waist_left[0] + 4, waist_y - 10), fill=colors["tank_high"])
    draw.line(
        (waist_right[0] - 4, waist_y - 8, waist_right[0] - 2, waist_y - 1),
        fill=colors["tank_shadow"],
        width=2,
    )
    draw.line(
        (neck[0] - 3, neck[1] + 10, neck[0] + 3 + yaw_shift, neck[1] + 12),
        fill=colors["tank_light"],
        width=1,
    )
    # Keep the same chain, ribbed tank, and abdominal read as Dave's authored
    # attack poses.  These marks are locked to body landmarks, so they move
    # with the torso instead of boiling from frame to frame.
    chain_left = (neck[0] - 4 + yaw_shift, neck[1] + 5)
    chain_low = (neck[0] + yaw_shift, neck[1] + 13)
    chain_right = (neck[0] + 4 + yaw_shift, neck[1] + 5)
    draw.line((*chain_left, *chain_low, *chain_right), fill=colors["outline"], width=3, joint="curve")
    draw.line((*chain_left, *chain_low, *chain_right), fill=colors["gold"], width=1, joint="curve")
    draw.point((chain_low[0], chain_low[1] + 1), fill=colors["gold"])
    chest_center_x = pelvis[0] + yaw_shift
    upper_fold_y = neck[1] + 18
    middle_fold_y = neck[1] + 25
    lower_fold_y = neck[1] + 32
    draw.line(
        (chest_center_x - 8, upper_fold_y, chest_center_x - 2, upper_fold_y + 1),
        fill=colors["tank_light"],
        width=2,
    )
    draw.line(
        (chest_center_x + 2, upper_fold_y + 1, chest_center_x + 9, upper_fold_y),
        fill=colors["tank_shadow"],
        width=2,
    )
    draw.line(
        (chest_center_x - 7, middle_fold_y, chest_center_x + 5, middle_fold_y + 1),
        fill=colors["tank_light"],
        width=1,
    )
    draw.line(
        (chest_center_x - 5, lower_fold_y, chest_center_x + 7, lower_fold_y - 1),
        fill=colors["tank_shadow"],
        width=2,
    )
    draw.line(
        (chest_center_x, neck[1] + 15, chest_center_x + 1, waist_y - 2),
        fill=colors["tank_shadow"],
        width=1,
    )
    left_armhole = (
        (left_shoulder[0], left_shoulder[1]),
        (left_shoulder[0] - 1, left_shoulder[1] + 7),
        (waist_left[0] + 1, waist_y - 10),
    )
    right_armhole = (
        (right_shoulder[0], right_shoulder[1]),
        (right_shoulder[0] + 1, right_shoulder[1] + 7),
        (waist_right[0] - 1, waist_y - 10),
    )
    draw.line(left_armhole, fill=colors["tank_light"], width=1)
    draw.line(right_armhole, fill=colors["tank_shadow"], width=2)


def _draw_near_shoulder_insertion(
    image: Image.Image,
    pose: Pose,
    colors: Mapping[str, tuple[int, int, int, int]],
) -> None:
    shoulder = pose.landmarks["left_shoulder"]
    draw = ImageDraw.Draw(image)
    armpit = _lerp_point(shoulder, pose.landmarks["pelvis"], 0.23)
    insertion = (
        (shoulder[0] - 3, shoulder[1] - 3),
        (shoulder[0] + 3, shoulder[1] - 2),
        (shoulder[0] + 4, shoulder[1] + 4),
        (armpit[0] + 1, armpit[1]),
        (shoulder[0] - 3, shoulder[1] + 4),
    )
    draw.polygon(insertion, fill=colors["skin_mid"])
    draw.line(
        (shoulder[0] - 2, shoulder[1] - 2, shoulder[0] + 1, shoulder[1] - 3),
        fill=colors["skin_light"],
        width=1,
    )
    draw.point((shoulder[0] - 2, shoulder[1] - 3), fill=colors["skin_high"])
    draw.line((shoulder[0] + 2, shoulder[1] + 3, armpit[0], armpit[1]), fill=colors["skin_deep"], width=2)
    draw.line((shoulder[0] - 2, shoulder[1], shoulder[0] - 1, shoulder[1] + 4), fill=colors["skin_light"], width=1)


def _composite_head_template(image: Image.Image, pose: Pose, rig: CanonicalDaveRig) -> None:
    part = rig.parts["head"]
    bounds = part.layer.getbbox()
    if bounds is None:
        raise ValueError("canonical Dave head template is empty")
    stamp = part.layer.crop(bounds)
    target = pose.landmarks["head_center"]
    dx = target[0] - part.source_end[0]
    dy = target[1] - part.source_end[1]
    image.alpha_composite(stamp, (bounds[0] + dx, bounds[1] + dy))


def _canonical_texture_layer(
    base: Image.Image,
    rig: CanonicalDaveRig,
    transforms: tuple[tuple[str, Point, Point], ...],
) -> Image.Image:
    """Put authored Dave texture inside one already-approved anatomy mask.

    The old rigid compositor allowed every source part to establish its own
    silhouette, which duplicated shoulders and opened seams.  Here the
    hand-drawn layer remains the sole silhouette authority: canonical pixels
    can add shading, fabric grain, and muscle definition only where that
    finished anatomical layer is already opaque.
    """

    texture = Image.new("RGBA", (CELL_SIZE, CELL_SIZE))
    for name, target_start, target_end in transforms:
        texture.alpha_composite(_transform_bone(rig.parts[name], target_start, target_end))
    texture.putalpha(
        ImageChops.multiply(texture.getchannel("A"), base.getchannel("A"))
    )
    textured = base.copy()
    textured.alpha_composite(texture)
    return _hard_alpha(textured)


def _render_arm_layer(
    pose: Pose,
    rig: CanonicalDaveRig,
    side: str,
    colors: Mapping[str, tuple[int, int, int, int]],
    *,
    depth: str,
    sections: tuple[str, ...] = ("upper", "lower", "hand"),
    shoulder_insertion: bool = False,
) -> Image.Image:
    layer = Image.new("RGBA", (CELL_SIZE, CELL_SIZE))
    _draw_arm_sections(layer, pose, side, colors, depth=depth, sections=sections)
    if shoulder_insertion:
        _draw_near_shoulder_insertion(layer, pose, colors)
    prefix = "near" if depth == "near" else "far"
    transforms: list[tuple[str, Point, Point]] = []
    if "upper" in sections:
        transforms.append(
            (
                f"{prefix}_upper_arm",
                pose.landmarks[f"{side}_shoulder"],
                pose.landmarks[f"{side}_elbow"],
            )
        )
    if "lower" in sections or "hand" in sections:
        transforms.append(
            (
                f"{prefix}_lower_arm",
                pose.landmarks[f"{side}_elbow"],
                pose.landmarks[f"{side}_hand"],
            )
        )
    return _canonical_texture_layer(layer, rig, tuple(transforms))


def _render_leg_layer(
    pose: Pose,
    rig: CanonicalDaveRig,
    side: str,
    colors: Mapping[str, tuple[int, int, int, int]],
    *,
    depth: str,
) -> Image.Image:
    layer = Image.new("RGBA", (CELL_SIZE, CELL_SIZE))
    _draw_leg(layer, pose, side, colors, depth=depth)
    prefix = "near" if depth == "near" else "far"
    return _canonical_texture_layer(
        layer,
        rig,
        (
            (
                f"{prefix}_upper_leg",
                pose.landmarks[f"{side}_hip"],
                pose.landmarks[f"{side}_knee"],
            ),
            (
                f"{prefix}_lower_leg",
                pose.landmarks[f"{side}_knee"],
                pose.landmarks[f"{side}_ankle"],
            ),
            (
                f"{prefix}_shoe",
                pose.landmarks[f"{side}_heel"],
                pose.landmarks[f"{side}_toe"],
            ),
        ),
    )


def render_dave_pose(pose: Pose, rig: CanonicalDaveRig) -> Image.Image:
    image = Image.new("RGBA", (CELL_SIZE, CELL_SIZE))
    colors = _handdrawn_colors(rig)
    near_arm_layer = HANDDRAWN_NEAR_ARM_LAYER[pose.index]

    # Far anatomy is completely established before the body, so the torso and
    # pelvis naturally remove hidden shoulders, chest, hip, and thigh pixels.
    image.alpha_composite(
        _render_arm_layer(pose, rig, "right", colors, depth="far")
    )
    if near_arm_layer == "behind":
        image.alpha_composite(
            _render_arm_layer(pose, rig, "left", colors, depth="near")
        )
    elif near_arm_layer == "split":
        image.alpha_composite(
            _render_arm_layer(
                pose,
                rig,
                "left",
                colors,
                depth="near",
                sections=("upper",),
            )
        )

    image.alpha_composite(_render_leg_layer(pose, rig, "right", colors, depth="far"))
    image.alpha_composite(_render_leg_layer(pose, rig, "left", colors, depth="near"))

    pelvis_layer = Image.new("RGBA", (CELL_SIZE, CELL_SIZE))
    _draw_pelvis_and_belt(pelvis_layer, pose, colors)
    # Keep one clean authored pouch and waistband. The canonical pelvis donor
    # also contains a full pouch, so texturing this already detailed layer
    # would duplicate the accessory and make Dave's hips look swollen.
    image.alpha_composite(pelvis_layer)

    torso_layer = Image.new("RGBA", (CELL_SIZE, CELL_SIZE))
    _draw_torso_and_neck(torso_layer, pose, colors)
    image.alpha_composite(
        _canonical_texture_layer(
            torso_layer,
            rig,
            (("torso", pose.landmarks["neck"], pose.landmarks["pelvis"]),),
        )
    )

    if near_arm_layer == "front":
        image.alpha_composite(
            _render_arm_layer(
                pose,
                rig,
                "left",
                colors,
                depth="near",
                shoulder_insertion=True,
            )
        )
    elif near_arm_layer == "split":
        image.alpha_composite(
            _render_arm_layer(
                pose,
                rig,
                "left",
                colors,
                depth="near",
                sections=("lower", "hand"),
                shoulder_insertion=True,
            )
        )

    _composite_head_template(image, pose, rig)

    # The floor is a hard game-space contract. Rigid shoe stamps can carry one
    # authored outline pixel below their semantic heel/toe anchors, so clip
    # that overhang instead of allowing a frame-dependent ground wobble.
    if GROUND_Y + 1 < CELL_SIZE:
        image.paste((0, 0, 0, 0), (0, GROUND_Y + 1, CELL_SIZE, CELL_SIZE))
    return _hard_alpha(image)


def _save_gif(frames: list[Image.Image], path: Path, durations: int | list[int]) -> None:
    rgb = [frame.convert("RGB") for frame in frames]
    palette = rgb[0].convert("P", palette=Image.Palette.ADAPTIVE, colors=255, dither=Image.Dither.NONE)
    indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in rgb]
    path.parent.mkdir(parents=True, exist_ok=True)
    indexed[0].save(
        path,
        save_all=True,
        append_images=indexed[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=False,
    )


def _presentation_frame(sprite: Image.Image, pose: Pose, *, scale: int = 1) -> Image.Image:
    canvas = Image.new("RGBA", (192 * scale, 192 * scale), (18, 20, 27, 255))
    draw = ImageDraw.Draw(canvas)
    ground = 170 * scale
    root_x = 96 * scale
    draw.ellipse(
        (root_x - 27 * scale, ground - 4 * scale, root_x + 27 * scale, ground + 4 * scale),
        fill=(8, 12, 19, 255),
    )
    shown = sprite.resize((CELL_SIZE * scale, CELL_SIZE * scale), Image.Resampling.NEAREST)
    canvas.alpha_composite(shown, (root_x - ROOT_X * scale, ground - GROUND_Y * scale))
    return canvas


def _comparison_dave_frame(sprite: Image.Image, size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), (18, 20, 27, 255))
    bounds = sprite.getbbox()
    if bounds is None:
        return canvas
    subject = sprite.crop(bounds)
    desired_height = size - 24
    ratio = desired_height / subject.height
    shown = subject.resize(
        (max(1, round(subject.width * ratio)), desired_height),
        Image.Resampling.NEAREST,
    )
    ground = size - 10
    draw = ImageDraw.Draw(canvas)
    draw.ellipse(
        (size // 2 - shown.width // 3, ground - 4, size // 2 + shown.width // 3, ground + 3),
        fill=(8, 12, 19, 255),
    )
    canvas.alpha_composite(shown, ((size - shown.width) // 2, ground - shown.height))
    return canvas


def render_paired_contact_sheet(
    reference: list[Image.Image], sprites: list[Image.Image], poses: tuple[Pose, ...], path: Path
) -> None:
    panel_w, panel_h = 360, 226
    columns = 3
    rows = 4
    canvas = Image.new("RGBA", (columns * panel_w, rows * panel_h), (18, 20, 27, 255))
    draw = ImageDraw.Draw(canvas)
    font = _font(13, bold=True)
    for index, (target, sprite, pose) in enumerate(zip(reference, sprites, poses)):
        left = (index % columns) * panel_w
        top = (index // columns) * panel_h
        draw.rectangle((left + 4, top + 4, left + panel_w - 5, top + panel_h - 5), outline=(99, 80, 120, 255), width=2)
        draw.text((left + 10, top + 9), f"{index + 1:02d} {pose.name}", font=font, fill=(245, 239, 226, 255))
        target_fit = _fit_nearest(target, (166, 176))
        canvas.alpha_composite(target_fit, (left + 9 + (166 - target_fit.width) // 2, top + 38 + (176 - target_fit.height) // 2))
        dave = _comparison_dave_frame(sprite, 176)
        canvas.alpha_composite(dave, (left + 178, top + 38))
        draw.text((left + 14, top + 205), "TARGET", font=_font(11), fill=(178, 164, 188, 255))
        draw.text((left + 244, top + 205), "DAVE", font=_font(11), fill=(178, 164, 188, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(path)


def render_world_preview(
    sprites: list[Image.Image], poses: tuple[Pose, ...], path: Path
) -> list[Image.Image]:
    frames: list[Image.Image] = []
    width, height = 720, 240
    ground = 202
    start_x = 90
    for timeline_index in range(POSE_COUNT * 2):
        cycle = timeline_index // POSE_COUNT
        pose = poses[timeline_index % POSE_COUNT]
        root_distance = cycle * STRIDE_DISTANCE + pose.root_distance
        root_screen = start_x + round(root_distance)
        frame = Image.new("RGBA", (width, height), (18, 20, 27, 255))
        draw = ImageDraw.Draw(frame)
        draw.line((0, ground, width, ground), fill=(111, 94, 83, 255), width=2)
        for marker in range(20, width, 20):
            draw.line((marker, ground - 5, marker, ground + 6), fill=(67, 65, 74, 255), width=1)
        contact = pose.landmarks[pose.contact_landmark]
        contact_world = root_distance + contact[0] - ROOT_X
        marker_x = start_x + round(contact_world)
        draw.line((marker_x, ground - 11, marker_x, ground + 8), fill=(255, 181, 73, 255), width=2)
        draw.ellipse((root_screen - 28, ground - 4, root_screen + 28, ground + 4), fill=(8, 12, 19, 255))
        frame.alpha_composite(sprites[pose.index], (root_screen - ROOT_X, ground - GROUND_Y))
        draw.text((14, 12), "WORLD FOOT-LOCK PREVIEW", font=_font(15, bold=True), fill=(245, 239, 226, 255))
        draw.text(
            (14, 34),
            f"pose {pose.index + 1:02d}  support={pose.support_foot}  root={root_distance:6.2f}px",
            font=_font(12),
            fill=(185, 172, 192, 255),
        )
        frames.append(frame)
    _save_gif(frames, path, 80)
    return frames


def render_side_by_side_gif(
    reference_frames: list[Image.Image], sprites: list[Image.Image], path: Path
) -> None:
    frames: list[Image.Image] = []
    for index in range(24):
        canvas = Image.new("RGBA", (1024, 360), (13, 15, 21, 255))
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle((16, 48, 416, 344), radius=6, fill=(21, 24, 33, 255), outline=(102, 82, 123, 255), width=2)
        draw.rounded_rectangle((432, 48, 1008, 344), radius=6, fill=(21, 24, 33, 255), outline=(102, 82, 123, 255), width=2)
        draw.text((26, 16), "CURRENT DAVE — RESTORED ART", font=_font(18, bold=True), fill=(240, 238, 245, 255))
        draw.text((442, 16), "REFERENCE GIF", font=_font(18, bold=True), fill=(240, 238, 245, 255))
        dave = _comparison_dave_frame(sprites[index // 2], 288)
        canvas.alpha_composite(dave, (72, 54))
        reference = _fit_nearest(reference_frames[index], (544, 264))
        canvas.alpha_composite(reference, (440 + (560 - reference.width) // 2, 54 + (264 - reference.height) // 2))
        frames.append(canvas)
    _save_gif(frames, path, 40)


def load_walk_strip(path: Path) -> list[Image.Image]:
    strip = Image.open(path).convert("RGBA")
    if strip.size != (CELL_SIZE * POSE_COUNT, CELL_SIZE):
        raise ValueError(f"unexpected Dave walk strip size: {strip.size}")
    return [
        strip.crop((index * CELL_SIZE, 0, (index + 1) * CELL_SIZE, CELL_SIZE))
        for index in range(POSE_COUNT)
    ]


def render_old_new_contact_sheet(
    old_frames: list[Image.Image],
    new_frames: list[Image.Image],
    poses: tuple[Pose, ...],
    path: Path,
) -> None:
    panel_w, panel_h = 360, 226
    canvas = Image.new("RGBA", (panel_w * 3, panel_h * 4), (18, 20, 27, 255))
    draw = ImageDraw.Draw(canvas)
    for index, (old, new, pose) in enumerate(zip(old_frames, new_frames, poses, strict=True)):
        left = (index % 3) * panel_w
        top = (index // 3) * panel_h
        draw.rectangle(
            (left + 4, top + 4, left + panel_w - 5, top + panel_h - 5),
            outline=(99, 80, 120, 255),
            width=2,
        )
        draw.text(
            (left + 10, top + 9),
            f"{index + 1:02d} {pose.name}",
            font=_font(13, bold=True),
            fill=(245, 239, 226, 255),
        )
        canvas.alpha_composite(_comparison_dave_frame(old, 176), (left + 4, top + 37))
        canvas.alpha_composite(_comparison_dave_frame(new, 176), (left + 180, top + 37))
        draw.text((left + 50, top + 205), "GENERIC REBUILD", font=_font(11), fill=(222, 125, 122, 255))
        draw.text((left + 224, top + 205), "RESTORED ART", font=_font(11), fill=(105, 217, 222, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(path)


def render_old_new_gif(
    old_frames: list[Image.Image], new_frames: list[Image.Image], path: Path
) -> None:
    frames: list[Image.Image] = []
    for index in range(POSE_COUNT * 2):
        pose_index = index // 2
        canvas = Image.new("RGBA", (720, 300), (18, 20, 27, 255))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((14, 14, 350, 286), outline=(113, 77, 87, 255), width=2)
        draw.rectangle((370, 14, 706, 286), outline=(67, 119, 127, 255), width=2)
        draw.text((28, 24), "GENERIC REBUILT ART", font=_font(15, bold=True), fill=(240, 190, 184, 255))
        draw.text((384, 24), "RESTORED AUTHORED ART", font=_font(15, bold=True), fill=(174, 234, 236, 255))
        canvas.alpha_composite(_comparison_dave_frame(old_frames[pose_index], 256), (54, 38))
        canvas.alpha_composite(_comparison_dave_frame(new_frames[pose_index], 256), (410, 38))
        draw.text((28, 278), f"pose {pose_index + 1:02d}/12", font=_font(11), fill=(174, 157, 181, 255))
        draw.text((384, 278), "same motion data / same timing", font=_font(11), fill=(174, 157, 181, 255))
        frames.append(canvas)
    _save_gif(frames, path, 40)


def render_anatomy_overlay(
    old_frames: list[Image.Image],
    new_frames: list[Image.Image],
    poses: tuple[Pose, ...],
    path: Path,
) -> None:
    overlays: list[Image.Image] = []
    labels: list[str] = []
    for old, new, pose in zip(old_frames, new_frames, poses, strict=True):
        old_alpha = old.getchannel("A")
        new_alpha = new.getchannel("A")
        overlay = Image.new("RGBA", (CELL_SIZE, CELL_SIZE), (228, 225, 218, 255))
        overlay.putdata(
            [
                (58, 54, 61, 255)
                if old_value >= 128 and new_value >= 128
                else (205, 67, 64, 255)
                if old_value >= 128
                else (34, 155, 166, 255)
                if new_value >= 128
                else (228, 225, 218, 255)
                for old_value, new_value in zip(_pixels(old_alpha), _pixels(new_alpha), strict=True)
            ]
        )
        overlay_draw = ImageDraw.Draw(overlay)
        for landmark in pose.landmarks.values():
            overlay_draw.point(landmark, fill=(247, 185, 41, 255))
        overlays.append(overlay)
        labels.append(f"{pose.index + 1:02d} {pose.name}")
    _contact_sheet(overlays, labels, path, columns=4, cell=(214, 178))


def render_silhouette_sheet(
    sprites: list[Image.Image], poses: tuple[Pose, ...], path: Path
) -> None:
    silhouettes: list[Image.Image] = []
    for sprite in sprites:
        alpha = sprite.getchannel("A")
        silhouette = Image.new("RGBA", sprite.size, (226, 224, 218, 255))
        silhouette.putdata(
            [
                (5, 7, 10, 255) if value >= 128 else (226, 224, 218, 255)
                for value in _pixels(alpha)
            ]
        )
        silhouettes.append(silhouette)
    _contact_sheet(
        silhouettes,
        [f"{pose.index + 1:02d} {pose.name}" for pose in poses],
        path,
        columns=4,
        cell=(214, 178),
    )


def _alpha_component_sizes(image: Image.Image) -> list[int]:
    alpha = image.getchannel("A")
    active = {
        (x, y)
        for y in range(image.height)
        for x in range(image.width)
        if alpha.getpixel((x, y)) >= 128
    }
    sizes: list[int] = []
    while active:
        seed = active.pop()
        stack = [seed]
        size = 0
        while stack:
            x, y = stack.pop()
            size += 1
            for offset_x in (-1, 0, 1):
                for offset_y in (-1, 0, 1):
                    if offset_x == 0 and offset_y == 0:
                        continue
                    neighbor = (x + offset_x, y + offset_y)
                    if neighbor in active:
                        active.remove(neighbor)
                        stack.append(neighbor)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def validate_handdrawn_anatomy(
    sprites: list[Image.Image], poses: tuple[Pose, ...]
) -> dict[str, object]:
    component_sizes = [_alpha_component_sizes(sprite) for sprite in sprites]
    silhouette_hashes = [
        hashlib.sha256(sprite.getchannel("A").tobytes()).hexdigest()
        for sprite in sprites
    ]
    uncovered_landmarks: dict[str, list[str]] = {}
    neck_spans: list[int] = []
    for sprite, pose in zip(sprites, poses, strict=True):
        alpha = sprite.getchannel("A")
        missing: list[str] = []
        for name, (x, y) in pose.landmarks.items():
            covered = any(
                alpha.getpixel((probe_x, probe_y)) >= 128
                for probe_y in range(max(0, y - 4), min(CELL_SIZE, y + 5))
                for probe_x in range(max(0, x - 4), min(CELL_SIZE, x + 5))
            )
            if not covered:
                missing.append(name)
        if missing:
            uncovered_landmarks[str(pose.index + 1)] = missing
        neck_y = pose.landmarks["neck"][1]
        pelvis_x = pose.landmarks["pelvis"][0]
        neck_spans.append(
            sum(
                alpha.getpixel((x, neck_y)) >= 128
                for x in range(max(0, pelvis_x - 18), min(CELL_SIZE, pelvis_x + 19))
            )
        )
    checks = {
        "single_connected_character": all(len(sizes) == 1 for sizes in component_sizes),
        "all_skeletal_landmarks_covered": not uncovered_landmarks,
        "twelve_distinct_silhouettes": len(set(silhouette_hashes)) == POSE_COUNT,
        "bounded_neck_geometry": max(neck_spans) <= 30,
        "all_layer_modes_exercised": set(HANDDRAWN_NEAR_ARM_LAYER) == {"behind", "split", "front"},
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"hand-reconstructed Dave anatomy rejected: {failed}")
    return {
        "checks": checks,
        "component_counts": [len(sizes) for sizes in component_sizes],
        "smallest_frame_component_px": min(sizes[0] for sizes in component_sizes),
        "uncovered_landmarks": uncovered_landmarks,
        "neck_span_px": neck_spans,
        "near_arm_layer_by_pose": list(HANDDRAWN_NEAR_ARM_LAYER),
    }


def validate_approved_identity(
    sprites: list[Image.Image],
    model: CharacterAnimationSkin,
    art_metrics: Mapping[str, object],
) -> dict[str, object]:
    expected = model.identity_validation["expected_frames"]
    component_sizes = [_alpha_component_sizes(sprite) for sprite in sprites]
    frame_results: list[dict[str, object]] = []
    visible_colors: set[tuple[int, int, int, int]] = set()
    costume_counts: list[dict[str, int]] = []
    for index, (sprite, frame_expected) in enumerate(zip(sprites, expected, strict=True)):
        alpha = sprite.getchannel("A")
        alpha_sha256 = hashlib.sha256(alpha.tobytes()).hexdigest()
        pixels = list(_pixels(sprite.convert("RGBA")))
        visible = [pixel for pixel in pixels if pixel[3] >= 128]
        visible_colors.update(visible)
        warm_skin = sum(
            red > green * 1.18 and green > blue * 1.03
            for red, green, blue, _alpha in visible
        )
        denim = sum(
            blue > red * 1.22 and blue > green * 1.06
            for red, green, blue, _alpha in visible
        )
        dark_costume = sum(
            red + green + blue < 150
            for red, green, blue, _alpha in visible
        )
        lower_shoe_light = sum(
            alpha_value >= 128
            and y >= 100
            and red + green + blue >= 420
            for y in range(CELL_SIZE)
            for red, green, blue, alpha_value in [sprite.getpixel((index_x, y)) for index_x in range(CELL_SIZE)]
        )
        upper_identity_dark = sum(
            sprite.getpixel((x, y))[3] >= 128
            and sum(sprite.getpixel((x, y))[:3]) < 180
            for y in range(0, 36)
            for x in range(CELL_SIZE)
        )
        costume = {
            "skin_pixels": warm_skin,
            "denim_pixels": denim,
            "dark_tank_outline_hat_beard_pixels": dark_costume,
            "shoe_light_pixels": lower_shoe_light,
            "head_hat_beard_pixels": upper_identity_dark,
        }
        costume_counts.append(costume)
        checks = {
            "alpha_signature": alpha_sha256 == str(frame_expected["registered_alpha_sha256"]),
            "bounds": sprite.getbbox() == tuple(frame_expected["registered_bbox"]),
            "opaque_pixels": sum(value >= 128 for value in _pixels(alpha)) == int(frame_expected["opaque_pixels"]),
            "single_connected_authored_cel": len(component_sizes[index]) == 1,
            "skin_present": warm_skin >= 250,
            "denim_present": denim >= 550,
            "tank_outline_hat_beard_present": dark_costume >= 450,
            "shoe_design_present": lower_shoe_light >= 25,
            "head_hat_beard_present": upper_identity_dark >= 30,
        }
        if not all(checks.values()):
            failed = [name for name, passed in checks.items() if not passed]
            raise ValueError(f"Dave identity validation rejected pose {index + 1}: {failed}")
        frame_results.append({"pose": index + 1, "checks": checks, **costume})

    palette_deviation = visible_colors - set(model.art.master_palette)
    checks = {
        "all_twelve_complete_authored_cels": len(sprites) == model.motion.pose_count,
        "all_silhouettes_exactly_match_approved_sources": all(
            result["checks"]["alpha_signature"] for result in frame_results
        ),
        "all_frames_are_one_coherent_drawing": all(len(sizes) == 1 for sizes in component_sizes),
        "master_palette_exact": not palette_deviation,
        "zero_proportion_deviation": art_metrics["maximum_proportion_deviation_px"] == 0,
        "zero_palette_deviation": art_metrics["maximum_palette_deviation_colors"] == 0,
        "character_specific_full_cel_mode": model.layers.mode == "complete_authored_cel_per_phase",
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"Dave character identity rejected: {failed}")
    return {
        "checks": checks,
        "frame_results": frame_results,
        "component_counts": [len(sizes) for sizes in component_sizes],
        "maximum_proportion_deviation_px": 0,
        "palette_deviation_colors": len(palette_deviation),
        "master_palette_color_count": len(model.art.master_palette),
        "visible_palette_color_count": len(visible_colors),
    }


def _pixel_delta(first: Image.Image, second: Image.Image) -> int:
    return sum(a != b for a, b in zip(_pixels(first.convert("RGBA")), _pixels(second.convert("RGBA"))))


def validate_skeleton(poses: tuple[Pose, ...]) -> dict[str, object]:
    left_hand_x = [pose.landmarks["left_hand"][0] for pose in poses]
    right_hand_x = [pose.landmarks["right_hand"][0] for pose in poses]
    pelvis_y = [pose.landmarks["pelvis"][1] for pose in poses]
    foot_center_spacing = [
        abs(
            (pose.landmarks["left_heel"][0] + pose.landmarks["left_toe"][0]) / 2.0
            - (pose.landmarks["right_heel"][0] + pose.landmarks["right_toe"][0]) / 2.0
        )
        for pose in poses
    ]
    contact_world: dict[str, list[float]] = {"left": [], "right": []}
    for pose in poses:
        point = pose.landmarks[pose.contact_landmark]
        contact_world[pose.support_foot].append(pose.root_distance + point[0] - ROOT_X)
    drift = {
        side: max(values) - min(values)
        for side, values in contact_world.items()
    }
    checks = {
        "pose_count": len(poses) == 12,
        "all_landmarks_present": all(set(pose.landmarks) == set(LANDMARK_NAMES) for pose in poses),
        "opposed_arm_swing": max(left_hand_x) - min(left_hand_x) >= 24 and max(right_hand_x) - min(right_hand_x) >= 24,
        "compact_step_spacing": max(foot_center_spacing) <= 52.0,
        "two_pelvis_arcs": pelvis_y[:6] == pelvis_y[6:] and max(pelvis_y[:6]) - min(pelvis_y[:6]) >= 8,
        "down_is_lowest": pelvis_y[1] == max(pelvis_y[:6]) and pelvis_y[7] == max(pelvis_y[6:]),
        "up_is_highest": pelvis_y[4] == min(pelvis_y[:6]) and pelvis_y[10] == min(pelvis_y[6:]),
        "torso_rotates": max(pose.torso_yaw for pose in poses) - min(pose.torso_yaw for pose in poses) >= 0.8,
        "near_far_identity_stable": all(pose.near_arm == "left" and pose.near_leg == "left" for pose in poses),
        "left_foot_lock": drift["left"] <= 1.0,
        "right_foot_lock": drift["right"] <= 1.0,
        "uniform_root_steps": all(
            abs((poses[index + 1].root_distance - poses[index].root_distance) - ROOT_STEP) <= 0.01
            for index in range(POSE_COUNT - 1)
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"skeletal retarget rejected: {failed}")
    return {
        "checks": checks,
        "left_hand_range_px": max(left_hand_x) - min(left_hand_x),
        "right_hand_range_px": max(right_hand_x) - min(right_hand_x),
        "maximum_foot_center_spacing_px": max(foot_center_spacing),
        "pelvis_vertical_range_px": max(pelvis_y) - min(pelvis_y),
        "maximum_planted_foot_drift_px": max(drift.values()),
    }


def validate_final(
    sprites: list[Image.Image],
    poses: tuple[Pose, ...],
    palette: tuple[tuple[int, int, int, int], ...],
) -> dict[str, object]:
    signatures = [hashlib.sha256(sprite.tobytes()).hexdigest() for sprite in sprites]
    visible_colors = {
        pixel
        for sprite in sprites
        for pixel in _pixels(sprite)
        if pixel[3] >= 128
    }
    semitransparent = sum(
        0 < pixel[3] < 255
        for sprite in sprites
        for pixel in _pixels(sprite)
    )
    bounds = [sprite.getbbox() for sprite in sprites]
    if any(bound is None for bound in bounds):
        raise ValueError("final rig produced an empty pose")
    deltas = [_pixel_delta(sprites[index], sprites[index + 1]) for index in range(POSE_COUNT - 1)]
    loop_delta = _pixel_delta(sprites[-1], sprites[0])
    upper_signatures = {
        hashlib.sha256(sprite.crop((0, 0, CELL_SIZE, 82)).tobytes()).hexdigest()
        for sprite in sprites
    }
    checks = {
        "unique_pose_count": len(set(signatures)) == 12,
        "upper_body_changes": len(upper_signatures) >= 10,
        "hard_alpha": semitransparent == 0,
        "locked_palette": visible_colors.issubset(set(palette)),
        "ground_line": all(bound is not None and bound[3] == GROUND_Y + 1 for bound in bounds),
        "no_canvas_clipping": all(
            bound is not None and bound[0] > 0 and bound[1] > 0 and bound[2] < CELL_SIZE for bound in bounds
        ),
        "loop_delta_normal": loop_delta <= max(deltas) * 1.15,
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise ValueError(f"final Dave rig rejected: {failed}")
    return {
        "checks": checks,
        "unique_pose_count": len(set(signatures)),
        "palette_color_count": len(visible_colors),
        "palette_changes": 0,
        "semitransparent_pixels": semitransparent,
        "pivot_x_px": ROOT_X,
        "ground_y_px": GROUND_Y,
        "final_to_first_pixel_delta": loop_delta,
        "median_adjacent_pixel_delta": median(deltas),
        "maximum_adjacent_pixel_delta": max(deltas),
        "loop_to_max_adjacent_ratio": round(loop_delta / max(1, max(deltas)), 4),
    }


def write_strip(sprites: list[Image.Image], path: Path) -> None:
    strip = Image.new("RGBA", (CELL_SIZE * len(sprites), CELL_SIZE))
    for index, sprite in enumerate(sprites):
        strip.alpha_composite(sprite, (index * CELL_SIZE, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    strip.save(path, optimize=True)


def update_walk_fist_anchors(path: Path, model: CharacterAnimationSkin) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    states = payload.get("states")
    if not isinstance(states, dict) or "walk" not in states:
        raise ValueError("Dave fist metadata has no walk state")
    anchors = model.art.walk_source.get("fist_anchors_after_registration")
    if not isinstance(anchors, list) or len(anchors) != model.motion.pose_count:
        raise ValueError("Dave art model has incomplete walk fist anchors")
    states["walk"] = [
        {
            "source": index,
            "rear": [int(value) for value in anchor["rear"]],
            "lead": [int(value) for value in anchor["lead"]],
        }
        for index, anchor in enumerate(anchors)
    ]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--pose-data-output", type=Path, required=True)
    parser.add_argument("--candidate-output", type=Path, required=True)
    parser.add_argument("--baseline-strip", type=Path)
    parser.add_argument("--art-model", type=Path, default=DEFAULT_ART_MODEL)
    parser.add_argument(
        "--canonical-atlas",
        type=Path,
        default=Path("assets/sprites/black_dave_atlas.png"),
    )
    parser.add_argument("--install-output", type=Path)
    parser.add_argument(
        "--fist-anchor-metadata",
        type=Path,
        default=Path("assets/sprites/black_dave_fist_anchors.json"),
    )
    args = parser.parse_args()

    model = load_character_animation_skin(_project_path(args.art_model))
    if model.character != "black_dave":
        raise ValueError(f"unexpected character art model: {model.character!r}")
    if model.motion.fingerprint_sha256 != APPROVED_MOTION_FINGERPRINT:
        raise ValueError("Dave art model is not bound to the approved walk motion")
    if model.motion.pose_count != POSE_COUNT or model.motion.loop_duration_ms != 960:
        raise ValueError("Dave art model motion dimensions do not match the runtime clip")

    reference_frames, reference_durations = _load_reference(args.reference)
    reference_bounds = _reference_motion_bounds(reference_frames)
    unique_reference = render_reference_contact_sheet(
        reference_frames,
        reference_bounds,
        args.review_dir / "reference_12_pose_contact_sheet.png",
    )
    poses = build_poses()
    skeleton_metrics = validate_skeleton(poses)
    pose_data = _pose_json(poses)
    motion_fingerprint = hashlib.sha256(
        json.dumps(pose_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if motion_fingerprint != APPROVED_MOTION_FINGERPRINT:
        raise ValueError(
            "approved Dave skeleton/timing changed: "
            f"{motion_fingerprint} != {APPROVED_MOTION_FINGERPRINT}"
        )
    args.pose_data_output.parent.mkdir(parents=True, exist_ok=True)
    args.pose_data_output.write_text(json.dumps(pose_data, indent=2) + "\n", encoding="utf-8")

    skeletons = [render_skeleton_pose(pose) for pose in poses]
    _contact_sheet(
        skeletons,
        [f"{pose.index + 1:02d}  {pose.name}" for pose in poses],
        args.review_dir / "dave_skeleton_12_pose_contact_sheet.png",
        cell=(192, 176),
    )
    _save_gif(
        [_presentation_frame(skeleton, pose) for skeleton, pose in zip(skeletons, poses)],
        args.review_dir / "dave_skeleton_normal_speed.gif",
        80,
    )

    # Only after the frozen motion gate succeeds may Dave's character adapter
    # select and clean the complete approved artwork for each phase.
    approved_cels, sprites, art_metrics = load_approved_walk_art(model)
    identity_metrics = validate_approved_identity(sprites, model, art_metrics)
    adapter_metrics = character_adapter_metrics(sprites, poses)
    final_metrics = validate_final(sprites, poses, model.art.master_palette)
    write_strip(sprites, args.candidate_output)
    write_asset_inventory(
        model,
        args.review_dir / "dave_canonical_asset_inventory.json",
    )
    render_approved_model_sheet(
        model,
        args.review_dir / "dave_approved_model_sheet.png",
    )
    render_palette_sheet(
        model,
        args.review_dir / "dave_exact_palette_sheet.png",
    )
    render_proportion_diagram(
        model,
        approved_cels[0],
        args.review_dir / "dave_proportion_diagram.png",
    )
    render_flat_color_over_skeleton(
        sprites,
        poses,
        args.review_dir / "dave_flat_color_over_skeleton.png",
    )
    render_authored_pair_contact_sheet(
        approved_cels,
        sprites,
        poses,
        args.review_dir / "dave_pose_vs_approved_original.png",
    )
    render_silhouette_sheet(
        sprites,
        poses,
        args.review_dir / "dave_walk_silhouette_validation.png",
    )
    _contact_sheet(
        sprites,
        [f"{pose.index + 1:02d} {pose.name}" for pose in poses],
        args.review_dir / "dave_walk_final_frame_review.png",
        columns=3,
        cell=(320, 300),
    )
    render_paired_contact_sheet(
        unique_reference,
        sprites,
        poses,
        args.review_dir / "final_dave_and_target_paired_contact_sheet.png",
    )
    normal_frames = [_presentation_frame(sprite, pose) for sprite, pose in zip(sprites, poses)]
    _save_gif(normal_frames, args.review_dir / "dave_walk_normal_speed.gif", 80)
    _save_gif(normal_frames, args.review_dir / "dave_walk_quarter_speed.gif", 320)
    world_frames = render_world_preview(
        sprites,
        poses,
        args.review_dir / "dave_walk_world_foot_lock.gif",
    )
    _contact_sheet(
        world_frames[:POSE_COUNT],
        [f"{pose.index + 1:02d}  {pose.support_foot} support" for pose in poses],
        args.review_dir / "dave_walk_world_foot_lock_contact_sheet.png",
        columns=3,
        cell=(360, 160),
    )
    render_side_by_side_gif(
        [frame.crop(reference_bounds) for frame in reference_frames],
        sprites,
        args.review_dir / "dave_walk_vs_reference.gif",
    )
    old_frames: list[Image.Image] | None = None
    if args.baseline_strip is not None:
        old_frames = load_walk_strip(args.baseline_strip)
        render_old_new_contact_sheet(
            old_frames,
            sprites,
            poses,
            args.review_dir / "dave_walk_old_vs_new_contact_sheet.png",
        )
        render_old_new_gif(
            old_frames,
            sprites,
            args.review_dir / "dave_walk_old_vs_new.gif",
        )
        render_anatomy_overlay(
            old_frames,
            sprites,
            poses,
            args.review_dir / "dave_walk_corrected_anatomy_overlay.png",
        )

    baseline_dimensions: dict[str, float] | None = None
    if old_frames is not None:
        old_bounds = [frame.getbbox() for frame in old_frames]
        new_bounds = [frame.getbbox() for frame in sprites]
        baseline_dimensions = {
            "old_average_width_px": round(
                sum(bound[2] - bound[0] for bound in old_bounds if bound is not None) / len(old_frames),
                3,
            ),
            "new_average_width_px": round(
                sum(bound[2] - bound[0] for bound in new_bounds if bound is not None) / len(sprites),
                3,
            ),
            "old_average_height_px": round(
                sum(bound[3] - bound[1] for bound in old_bounds if bound is not None) / len(old_frames),
                3,
            ),
            "new_average_height_px": round(
                sum(bound[3] - bound[1] for bound in new_bounds if bound is not None) / len(sprites),
                3,
            ),
        }

    report = {
        "status": "pass",
        "method": "complete approved multi-frame Dave cels selected by the frozen generic motion clip, then hard-alpha registered and locked to the Dave-specific 192-color palette",
        "forbidden_methods_used": [],
        "skeleton_reused": True,
        "lower_body_gait_reused": True,
        "upper_body_change": "the generic reconstructed upper body was removed; approved complete authored Dave cels now own silhouette, anatomy, costume, face, and occlusion",
        "timing_changed": False,
        "motion_changed": False,
        "approved_motion_fingerprint": motion_fingerprint,
        "commits_inspected": [
            "174437aa109360a4c4f24d58d9d17bcd2605f8df",
            "bbd21d6ab01695ad22e7e86d21e3e3b5e7cea1a9",
            "3932865f29e5535d7485ff50bf68536b10b9a026",
            "bdcd5d8980ee2978e572bd8ab549b7d78edcf621",
            "ad09d21c347c0742ecd787efc63759980995d1a0",
            "d13ef964f98770a5896fac941df4466269a460eb",
            "0250f9c991991a326fa98afd38f83ebf1800a064",
            "6f0f8d3c1a577e1696d36e4537d54e358c45126f",
        ],
        "original_assets_used": [
            item["path"]
            for item in model.art.asset_inventory
            if str(item["classification"]).startswith("canonical")
        ],
        "character_dimensions_changed": baseline_dimensions,
        "maximum_proportion_deviation_px": identity_metrics["maximum_proportion_deviation_px"],
        "palette_deviation_colors": identity_metrics["palette_deviation_colors"],
        "character_adapter_validation": adapter_metrics,
        "frames_manually_redrawn": [],
        "frames_native_pixel_cleaned": list(range(1, POSE_COUNT + 1)),
        "silhouette_validation": identity_metrics,
        "hidden_surface_corrections": [
            "each approved original cel supplies one already-resolved shoulder, chest, arm, hip, leg, and shoe silhouette",
            "no generic limb, duplicate shoulder, floating muscle, or overlapping transformed body part remains",
            "the original artist's near/far occlusion and clothing compression are preserved per phase",
        ],
        "layer_order_corrections": model.layers.hidden_surface_policy,
        "anatomy_corrections": [
            "restored the authored muscular shoulders, thick arms, torso depth, head, face, beard, and cap",
            "restored the original tank boundaries, chain, belt, buckle, pouch, denim folds, and shoe construction",
            "removed the 40-color generic ribbon silhouette and retained a single connected full-cel drawing",
        ],
        "character_art_model": {
            "source": args.art_model.as_posix(),
            "name": model.art.name,
            "source_commit": model.art.source_commit,
            "source_sha256": art_metrics["source_sha256"],
            "render_mode": model.layers.mode,
            "palette_color_count": len(model.art.master_palette),
            "resampling": model.cleanup.resampling,
        },
        "reference": {
            "source_frames": len(reference_frames),
            "unique_pose_count": len(unique_reference),
            "frame_duration_ms": sorted(set(reference_durations)),
            "paired_pose_duration_ms": 80,
            "loop_duration_ms": sum(reference_durations),
            "motion_bounds": list(reference_bounds),
        },
        "runtime": {
            "unique_pose_count": POSE_COUNT,
            "pose_duration_ms": 80,
            "displayed_frame_duration_ms": 40,
            "displayed_frames": 24,
            "loop_duration_ms": 960,
            "root_displacement_px": STRIDE_DISTANCE,
            "distance_driven": True,
            "fist_anchor_metadata": args.fist_anchor_metadata.as_posix(),
        },
        "skeleton_validation": skeleton_metrics,
        "final_validation": final_metrics,
        "maximum_planted_foot_drift_px": skeleton_metrics["maximum_planted_foot_drift_px"],
        "pivot_consistency": {"root_x_px": ROOT_X, "ground_y_px": GROUND_Y},
        "remaining_visual_limitations": [
            "The frozen generic skeleton remains the timing, phase, root, and contact authority; internal contour landmarks are represented by the closest approved full authored cel rather than deforming that cel into a generic body template."
        ],
        "artifacts": {
            "canonical_asset_inventory": "dave_canonical_asset_inventory.json",
            "approved_model_sheet": "dave_approved_model_sheet.png",
            "exact_palette_sheet": "dave_exact_palette_sheet.png",
            "proportion_diagram": "dave_proportion_diagram.png",
            "reference_contact_sheet": "reference_12_pose_contact_sheet.png",
            "skeleton_contact_sheet": "dave_skeleton_12_pose_contact_sheet.png",
            "flat_color_over_skeleton": "dave_flat_color_over_skeleton.png",
            "pose_vs_approved_original": "dave_pose_vs_approved_original.png",
            "paired_contact_sheet": "final_dave_and_target_paired_contact_sheet.png",
            "silhouette_validation": "dave_walk_silhouette_validation.png",
            "final_frame_review": "dave_walk_final_frame_review.png",
            "normal_speed_gif": "dave_walk_normal_speed.gif",
            "quarter_speed_gif": "dave_walk_quarter_speed.gif",
            "world_foot_lock_gif": "dave_walk_world_foot_lock.gif",
            "world_foot_lock_contact_sheet": "dave_walk_world_foot_lock_contact_sheet.png",
            "side_by_side_gif": "dave_walk_vs_reference.gif",
            "old_vs_new_contact_sheet": "dave_walk_old_vs_new_contact_sheet.png" if old_frames is not None else None,
            "old_vs_new_gif": "dave_walk_old_vs_new.gif" if old_frames is not None else None,
            "corrected_anatomy_overlay": "dave_walk_corrected_anatomy_overlay.png" if old_frames is not None else None,
            "in_game_preview": "runtime_dave_walk.gif (render after installation)",
        },
    }
    report_path = args.review_dir / "dave_walk_validation_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.install_output is not None:
        write_strip(sprites, args.install_output)
        update_walk_fist_anchors(args.fist_anchor_metadata, model)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
