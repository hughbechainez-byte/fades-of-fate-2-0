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
from typing import Iterable, Mapping

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


POSE_COUNT = 12
SOURCE_FRAME_INDICES = tuple(range(0, 24, 2))
CELL_SIZE = 128
ROOT_X = 64
GROUND_Y = 126
DAVE_HEIGHT = 112.0
LEG_LENGTH = 50.0
SHOULDER_WIDTH = 18.0
STRIDE_DISTANCE = 120.96
ROOT_STEP = STRIDE_DISTANCE / POSE_COUNT
REFERENCE_PAIR_MAX_CHANGED_PIXELS = 2048
CANONICAL_ATLAS_COLUMNS = 5
CANONICAL_ATLAS_ROWS = 4
CANONICAL_CELL_COLUMN = 0
CANONICAL_CELL_ROW = 1
CANONICAL_PALETTE_COLORS = 40

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


def _stance_leg(phase: int, root_x: int) -> dict[str, Point]:
    contact_x = 28.0 - ROOT_STEP * phase
    heel_y = (126, 126, 126, 126, 120, 116)[phase]
    toe_y = (126, 126, 126, 126, 126, 126)[phase]
    if phase <= 3:
        heel_x = contact_x
        toe_x = contact_x + (22, 23, 23, 22)[phase]
        ankle_x = contact_x + (6, 9, 11, 12)[phase]
        ankle_y = (113, 112, 111, 111)[phase]
    else:
        toe_x = contact_x
        heel_x = contact_x - 18
        ankle_x = contact_x + (-8, -9)[phase - 4]
        ankle_y = (107, 104)[phase - 4]
    knee_x = (15, 17, 12, 5, -5, -12)[phase]
    knee_y = (98, 103, 99, 96, 91, 90)[phase]
    return {
        "knee": _point(root_x + knee_x, knee_y),
        "ankle": _point(root_x + ankle_x, ankle_y),
        "heel": _point(root_x + heel_x, heel_y),
        "toe": _point(root_x + toe_x, toe_y),
    }


def _swing_leg(phase: int, root_x: int) -> dict[str, Point]:
    heel_x = (-42, -36, -22, -8, 10, 27)[phase]
    heel_y = (124, 119, 114, 112, 116, 124)[phase]
    toe_x = (-20, -14, 0, 15, 34, 49)[phase]
    toe_y = (126, 122, 118, 115, 120, 126)[phase]
    ankle_x = (-31, -27, -11, 3, 19, 35)[phase]
    ankle_y = (111, 108, 104, 101, 104, 111)[phase]
    knee_x = (-19, -16, -8, 4, 14, 20)[phase]
    knee_y = (98, 95, 91, 88, 91, 96)[phase]
    return {
        "knee": _point(root_x + knee_x, knee_y),
        "ankle": _point(root_x + ankle_x, ankle_y),
        "heel": _point(root_x + heel_x, heel_y),
        "toe": _point(root_x + toe_x, toe_y),
    }


def _arm_landmarks(shoulder: Point, swing: float, lag: float) -> tuple[Point, Point, Point]:
    sx, sy = shoulder
    elbow = _point(sx + swing * 9.0, sy + 15.0 - abs(swing))
    wrist = _point(sx + swing * 15.0 + lag * 4.0, sy + 29.0 - abs(swing) * 2.0)
    hand = _point(wrist[0] + (2 if swing >= 0 else -2), wrist[1] + 2)
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
    shoulder_spread = 7 + round(abs(yaw) * 5)
    left_shoulder = _point(neck[0] - shoulder_spread, neck[1] + 6 - shoulder_tilt)
    right_shoulder = _point(neck[0] + shoulder_spread, neck[1] + 6 + shoulder_tilt)
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


def render_dave_pose(pose: Pose, rig: CanonicalDaveRig) -> Image.Image:
    lm = pose.landmarks
    image = Image.new("RGBA", (CELL_SIZE, CELL_SIZE))

    def composite(name: str, target_start: Point, target_end: Point) -> None:
        image.alpha_composite(_transform_bone(rig.parts[name], target_start, target_end))

    composite("far_upper_arm", lm["right_shoulder"], lm["right_elbow"])
    composite("far_lower_arm", lm["right_elbow"], lm["right_hand"])
    composite("far_upper_leg", lm["right_hip"], lm["right_knee"])
    composite("far_lower_leg", lm["right_knee"], lm["right_ankle"])
    composite("far_shoe", lm["right_heel"], lm["right_toe"])
    composite("torso", lm["neck"], lm["pelvis"])
    composite("near_upper_leg", lm["left_hip"], lm["left_knee"])
    composite("near_lower_leg", lm["left_knee"], lm["left_ankle"])
    composite("near_shoe", lm["left_heel"], lm["left_toe"])
    composite("pelvis", lm["left_hip"], lm["right_hip"])
    clothing_detail = Image.new("RGBA", (CELL_SIZE, CELL_SIZE))
    detail_draw = ImageDraw.Draw(clothing_detail)
    belt = _canonical_color(rig, (38, 27, 29))
    gold = _canonical_color(rig, (221, 153, 55))
    belt_y = round((lm["left_hip"][1] + lm["right_hip"][1]) / 2) - 1
    _line(detail_draw, ((ROOT_X - 9, belt_y), (ROOT_X + 9, belt_y)), belt, 3)
    detail_draw.rectangle((ROOT_X - 2, belt_y - 2, ROOT_X + 2, belt_y + 2), fill=gold, outline=belt)
    image.alpha_composite(clothing_detail)
    composite("near_upper_arm", lm["left_shoulder"], lm["left_elbow"])
    composite("near_lower_arm", lm["left_elbow"], lm["left_hand"])
    composite("head", lm["neck"], lm["head_center"])

    # The floor is a hard game-space contract. Rigid shoe stamps can carry one
    # source outline pixel below their semantic heel/toe anchors, so clip that
    # source overhang instead of allowing a frame-dependent ground wobble.
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
        draw.text((26, 16), "RETARGETED DAVE WALK", font=_font(18, bold=True), fill=(240, 238, 245, 255))
        draw.text((442, 16), "REFERENCE GIF", font=_font(18, bold=True), fill=(240, 238, 245, 255))
        dave = _comparison_dave_frame(sprites[index // 2], 288)
        canvas.alpha_composite(dave, (72, 54))
        reference = _fit_nearest(reference_frames[index], (544, 264))
        canvas.alpha_composite(reference, (440 + (560 - reference.width) // 2, 54 + (264 - reference.height) // 2))
        frames.append(canvas)
    _save_gif(frames, path, 40)


def _pixel_delta(first: Image.Image, second: Image.Image) -> int:
    return sum(a != b for a, b in zip(_pixels(first.convert("RGBA")), _pixels(second.convert("RGBA"))))


def validate_skeleton(poses: tuple[Pose, ...]) -> dict[str, object]:
    left_hand_x = [pose.landmarks["left_hand"][0] for pose in poses]
    right_hand_x = [pose.landmarks["right_hand"][0] for pose in poses]
    pelvis_y = [pose.landmarks["pelvis"][1] for pose in poses]
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
        "opposed_arm_swing": max(left_hand_x) - min(left_hand_x) >= 36 and max(right_hand_x) - min(right_hand_x) >= 36,
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


def update_walk_fist_anchors(path: Path, poses: tuple[Pose, ...]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    states = payload.get("states")
    if not isinstance(states, dict) or "walk" not in states:
        raise ValueError("Dave fist metadata has no walk state")
    states["walk"] = [
        {
            "source": pose.index,
            # Runtime naming follows the established camera-depth convention:
            # the near anatomical-left arm is rear in frame 1, while the far
            # anatomical-right arm is lead. Their identities stay fixed even
            # when their screen positions cross during the opposite half-step.
            "rear": list(pose.landmarks["left_hand"]),
            "lead": list(pose.landmarks["right_hand"]),
        }
        for pose in poses
    ]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--pose-data-output", type=Path, required=True)
    parser.add_argument("--candidate-output", type=Path, required=True)
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

    # Final art is rendered only after the skeletal gate above succeeds.
    rig = load_canonical_rig(args.canonical_atlas)
    render_canonical_parts_sheet(
        rig,
        args.review_dir / "dave_canonical_rig_parts_contact_sheet.png",
    )
    sprites = [render_dave_pose(pose, rig) for pose in poses]
    final_metrics = validate_final(sprites, poses, rig.palette)
    write_strip(sprites, args.candidate_output)
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

    report = {
        "status": "pass",
        "method": "deterministic landmark retarget and canonical cut-part pixel rig",
        "forbidden_methods_used": [],
        "canonical_rig": {
            "source": args.canonical_atlas.as_posix(),
            "source_sha256": rig.source_sha256,
            "source_cell": [CANONICAL_CELL_COLUMN, CANONICAL_CELL_ROW],
            "part_count": len(rig.parts),
            "palette_color_count": len(rig.palette),
            "resampling": "nearest_neighbor_only",
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
        "artifacts": {
            "reference_contact_sheet": "reference_12_pose_contact_sheet.png",
            "skeleton_contact_sheet": "dave_skeleton_12_pose_contact_sheet.png",
            "canonical_rig_parts_contact_sheet": "dave_canonical_rig_parts_contact_sheet.png",
            "paired_contact_sheet": "final_dave_and_target_paired_contact_sheet.png",
            "normal_speed_gif": "dave_walk_normal_speed.gif",
            "quarter_speed_gif": "dave_walk_quarter_speed.gif",
            "world_foot_lock_gif": "dave_walk_world_foot_lock.gif",
            "world_foot_lock_contact_sheet": "dave_walk_world_foot_lock_contact_sheet.png",
            "side_by_side_gif": "dave_walk_vs_reference.gif",
        },
    }
    report_path = args.review_dir / "dave_walk_validation_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.install_output is not None:
        write_strip(sprites, args.install_output)
        update_walk_fist_anchors(args.fist_anchor_metadata, poses)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
