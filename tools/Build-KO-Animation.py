"""Build KO's strict authored runtime atlas from horizontal pose sheets.

The seven state sheets plus one genuine super-hook source live in
``art_source/ko`` and use a flat ``#ff00ff`` matte. Each sheet is a horizontal
sequence of complete, right-facing character cels.
This tool keys only the declared matte family, isolates each whole opaque body
without cutting variable-width attacks at arbitrary grid lines, keeps every
owned non-matte source pixel, applies one common nearest-neighbor scale per
state, and registers every result to the same 304x128 ground/root contract. It
never borrows another actor, synthesizes an in-between, decomposes a body, or
mirrors art; facing remains renderer-owned.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import math
import os
from pathlib import Path
import sys
from typing import Sequence

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "art_source" / "ko"
ATLAS_OUTPUT = PROJECT_ROOT / "assets" / "sprites" / "ko_animation_atlas.png"
REPORT_OUTPUT = PROJECT_ROOT / "assets" / "sprites" / "ko_animation_validation.json"

KEY_COLOR = (255, 0, 255)
KEY_TOLERANCE = 8
CELL_WIDTH = 304
CELL_HEIGHT = 128
ROOT_X = CELL_WIDTH // 2
GROUND_Y = 127
TARGET_VISIBLE_HEIGHT = 127


@dataclass(frozen=True, slots=True)
class StateSpec:
    state: str
    filename: str
    pose_count: int
    row: int


STATE_SPECS = (
    StateSpec("idle", "ko_idle_source.png", 8, 0),
    StateSpec("skate", "ko_skate_source.png", 12, 1),
    StateSpec("prepare", "ko_prepare_source.png", 8, 2),
    StateSpec("punch_1", "ko_punch_1_source.png", 8, 3),
    StateSpec("punch_2", "ko_punch_2_source.png", 8, 4),
    StateSpec("kick", "ko_kick_source.png", 8, 5),
    StateSpec("super", "ko_super_source.png", 12, 6),
)
STATE_NAMES = tuple(spec.state for spec in STATE_SPECS)
POSE_COUNTS = {spec.state: spec.pose_count for spec in STATE_SPECS}
ATLAS_COLUMNS = max(spec.pose_count for spec in STATE_SPECS)
ATLAS_ROWS = len(STATE_SPECS)
SUPER_BASE_POSE_COUNT = 11
SUPER_HOOK_FILENAME = "ko_super_hook_source.png"
SUPER_HOOK_INSERT_AFTER = 6


class KOAnimationBuildError(ValueError):
    """Raised when authored KO art cannot pass the runtime contract."""


@dataclass(frozen=True, slots=True)
class OpaqueComponent:
    area: int
    bounds: tuple[int, int, int, int]
    centroid: tuple[float, float]
    pixels: tuple[int, ...]

    @property
    def width(self) -> int:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> int:
        return self.bounds[3] - self.bounds[1]


@dataclass(frozen=True, slots=True)
class SourcePose:
    index: int
    source_pose_index: int
    source_file: str
    crop: Image.Image
    source_bounds: tuple[int, int, int, int]
    source_cell_bounds: tuple[int, int, int, int]
    root_x: float
    opaque_pixels: int
    component_count: int
    source_signature: str
    source_normalization_scale: float = 1.0


def _pixels(image: Image.Image):
    getter = getattr(image, "get_flattened_data", None)
    return getter() if getter is not None else image.getdata()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _normalized_signature(image: Image.Image) -> str:
    bounds = image.getchannel("A").getbbox()
    if bounds is None:
        raise KOAnimationBuildError("cannot sign an empty pose")
    crop = image.crop(bounds)
    header = f"{crop.width}x{crop.height}:".encode("ascii")
    return _sha256_bytes(header + crop.tobytes())


def _is_flat_key(red: int, green: int, blue: int) -> bool:
    """Match only the flat matte and tiny lossless-export deviations."""

    return (
        abs(red - KEY_COLOR[0]) <= KEY_TOLERANCE
        and abs(green - KEY_COLOR[1]) <= KEY_TOLERANCE
        and abs(blue - KEY_COLOR[2]) <= KEY_TOLERANCE
    )


def _is_matte_family(red: int, green: int, blue: int) -> bool:
    """Match the exported magenta matte without treating dark KO accents as key.

    The approved PNG exports retain the declared magenta chroma but their
    encoder shifts ``#ff00ff`` through a narrow high-value magenta ramp.  A
    channel-distance rule is deterministic across that ramp and its bright
    antialiased edge, while the value floor protects KO's dark purple cap and
    glove pixels.  No skin, coat, denim, outline, or effect hue qualifies.
    """

    return _is_flat_key(red, green, blue) or (
        min(red, blue) >= 96
        and red - green >= 42
        and blue - green >= 42
        and abs(red - blue) <= 72
    )


def _is_visible_chroma_spill(red: int, green: int, blue: int) -> bool:
    """Recognize unkeyed matte-like fringe without eating ordinary colors."""

    return (
        red >= 210
        and blue >= 210
        and green <= 72
        and abs(red - blue) <= 28
        and min(red, blue) - green >= 150
    )


def _key_and_harden(source: Image.Image, *, label: str) -> tuple[Image.Image, dict[str, int]]:
    rgba = source.convert("RGBA")
    keyed: list[tuple[int, int, int, int]] = []
    keyed_pixels = 0
    semitransparent_pixels = 0
    hardened_pixels = 0
    for red, green, blue, alpha in _pixels(rgba):
        if 0 < alpha < 255:
            semitransparent_pixels += 1
        if alpha == 0 or _is_matte_family(red, green, blue):
            keyed.append((0, 0, 0, 0))
            keyed_pixels += 1
            continue
        if alpha != 255:
            hardened_pixels += 1
        keyed.append((red, green, blue, 255))
    result = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    result.putdata(keyed)
    if keyed_pixels == 0:
        raise KOAnimationBuildError(
            f"{label}: source contains no flat #ff00ff matte pixels"
        )
    if result.getchannel("A").getbbox() is None:
        raise KOAnimationBuildError(f"{label}: source is empty after chroma keying")
    spill = sum(
        alpha == 255 and _is_visible_chroma_spill(red, green, blue)
        for red, green, blue, alpha in _pixels(result)
    )
    if spill:
        raise KOAnimationBuildError(
            f"{label}: {spill} visible magenta spill pixels remain after conservative keying"
        )
    return result, {
        "keyed_pixels": keyed_pixels,
        "source_semitransparent_pixels": semitransparent_pixels,
        "hard_alpha_coercions": hardened_pixels,
        "visible_chroma_spill_pixels": spill,
    }


def _opaque_components_8(image: Image.Image) -> tuple[OpaqueComponent, ...]:
    """Label hard-alpha components inside one already isolated source cel."""

    width, height = image.size
    alpha = image.getchannel("A").tobytes()
    visited = bytearray(len(alpha))
    components: list[OpaqueComponent] = []
    for start, value in enumerate(alpha):
        if value == 0 or visited[start]:
            continue
        visited[start] = 1
        pending = [start]
        members: list[int] = []
        min_x, min_y = width, height
        max_x = max_y = -1
        sum_x = sum_y = 0
        while pending:
            point = pending.pop()
            members.append(point)
            y, x = divmod(point, width)
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
            sum_x += x
            sum_y += y
            for neighbor_y in range(max(0, y - 1), min(height, y + 2)):
                row = neighbor_y * width
                for neighbor_x in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = row + neighbor_x
                    if alpha[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        pending.append(neighbor)
        area = len(members)
        components.append(
            OpaqueComponent(
                area=area,
                bounds=(min_x, min_y, max_x + 1, max_y + 1),
                centroid=(sum_x / area, sum_y / area),
                pixels=tuple(members),
            )
        )
    return tuple(components)


def _lower_body_root(component: OpaqueComponent, *, image_width: int) -> float:
    """Anchor from the dense lower body so coats/fists cannot drag the root."""

    left, top, right, bottom = component.bounds
    band_top = top + math.floor(component.height * 0.68)
    column_counts: dict[int, int] = {}
    for point in component.pixels:
        y, x = divmod(point, image_width)
        if y >= band_top:
            column_counts[x] = column_counts.get(x, 0) + 1
    if not column_counts:
        return component.centroid[0]
    density_floor = max(1, math.ceil(max(column_counts.values()) * 0.25))
    dense = {x: count for x, count in column_counts.items() if count >= density_floor}
    if not dense:
        return component.centroid[0]
    weight = sum(dense.values())
    root = sum(x * count for x, count in dense.items()) / weight
    return max(float(left), min(float(right - 1), root))


def _extract_poses(
    keyed: Image.Image,
    *,
    spec: StateSpec,
) -> tuple[tuple[SourcePose, ...], dict[str, object]]:
    """Extract complete left-to-right bodies without rectangular cell clipping.

    The authored figures have intentionally different action widths, so their
    X ranges can overlap even though the opaque bodies remain separated by the
    matte.  Connected full-body extraction preserves an extended glove, coat,
    kick, or skateboard that would otherwise be cut at an equal-width divider.
    Small components wholly inside a body's bounds are retained as authored
    detached details; unexplained components in a gutter are rejected as
    contamination.
    """

    components = _opaque_components_8(keyed)
    if not components:
        raise KOAnimationBuildError(f"{spec.state}: source has no opaque poses")
    largest_area = max(component.area for component in components)
    body_area_floor = max(64, math.ceil(largest_area * 0.15))
    body_height_floor = max(8, math.ceil(keyed.height * 0.15))
    bodies = [
        component
        for component in components
        if component.area >= body_area_floor and component.height >= body_height_floor
    ]
    bodies.sort(key=lambda component: (component.bounds[0], component.centroid[0]))
    if len(bodies) != spec.pose_count:
        raise KOAnimationBuildError(
            f"{spec.state}: expected {spec.pose_count} complete full-body poses, "
            f"found {len(bodies)} (area floor={body_area_floor}px, "
            f"height floor={body_height_floor}px)"
        )

    body_ids = {id(component) for component in bodies}
    assigned: list[list[OpaqueComponent]] = [[body] for body in bodies]
    for satellite in components:
        if id(satellite) in body_ids:
            continue
        center_x, center_y = satellite.centroid
        owners = []
        for body_index, body in enumerate(bodies):
            left, top, right, bottom = body.bounds
            if left <= center_x < right and top <= center_y < bottom:
                distance = (
                    (center_x - body.centroid[0]) ** 2
                    + (center_y - body.centroid[1]) ** 2
                )
                owners.append((distance, body_index))
        if not owners:
            raise KOAnimationBuildError(
                f"{spec.state}: isolated spill component is not owned by a full body; "
                f"area={satellite.area}px, bounds={satellite.bounds}"
            )
        assigned[min(owners)[1]].append(satellite)

    poses: list[SourcePose] = []
    signatures: set[str] = set()
    source_pixels = keyed.load()
    for index, (body, pose_components) in enumerate(zip(bodies, assigned)):
        left = min(component.bounds[0] for component in pose_components)
        top = min(component.bounds[1] for component in pose_components)
        right = max(component.bounds[2] for component in pose_components)
        bottom = max(component.bounds[3] for component in pose_components)
        if (
            left <= 0
            or top <= 0
            or right >= keyed.width
            or bottom >= keyed.height
        ):
            raise KOAnimationBuildError(
                f"{spec.state}: pose {index + 1} touches the sheet edge and may be clipped; "
                f"bounds={(left, top, right, bottom)}, sheet={keyed.size}"
            )
        crop = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
        crop_pixels = crop.load()
        for component in pose_components:
            for point in component.pixels:
                y, x = divmod(point, keyed.width)
                crop_pixels[x - left, y - top] = source_pixels[x, y]
        cropped_components = _opaque_components_8(crop)
        main = max(
            cropped_components,
            key=lambda component: (component.height, component.area),
        )
        if main.height < max(8, math.ceil(crop.height * 0.45)):
            raise KOAnimationBuildError(
                f"{spec.state}: pose {index + 1} has no full-body component"
            )
        signature = _normalized_signature(crop)
        if signature in signatures:
            raise KOAnimationBuildError(
                f"{spec.state}: pose {index + 1} duplicates an earlier complete pose"
            )
        signatures.add(signature)
        opaque_pixels = sum(alpha == 255 for alpha in _pixels(crop.getchannel("A")))
        poses.append(
            SourcePose(
                index=index,
                source_pose_index=index,
                source_file=spec.filename,
                crop=crop,
                source_bounds=(left, top, right, bottom),
                source_cell_bounds=(left, top, right, bottom),
                root_x=_lower_body_root(main, image_width=crop.width),
                opaque_pixels=opaque_pixels,
                component_count=len(pose_components),
                source_signature=signature,
            )
        )

    return tuple(poses), {
        "method": "left_to_right_connected_complete_bodies",
        "body_area_floor_px": body_area_floor,
        "body_height_floor_px": body_height_floor,
        "source_component_count": len(components),
        "retained_detail_components": len(components) - len(bodies),
        "pose_order": list(range(1, spec.pose_count + 1)),
    }


def _harden_alpha(image: Image.Image) -> Image.Image:
    hardened = Image.new("RGBA", image.size, (0, 0, 0, 0))
    hardened.putdata([
        (red, green, blue, 255 if alpha else 0)
        for red, green, blue, alpha in _pixels(image.convert("RGBA"))
    ])
    return hardened


def _state_scale(poses: Sequence[SourcePose]) -> tuple[float, str]:
    height_scale = TARGET_VISIBLE_HEIGHT / max(pose.crop.height for pose in poses)
    fit_scales = [height_scale]
    for pose in poses:
        left_extent = max(0.5, pose.root_x)
        right_extent = max(0.5, pose.crop.width - pose.root_x)
        fit_scales.extend((ROOT_X / left_extent, (CELL_WIDTH - ROOT_X) / right_extent))
    scale = min(fit_scales)
    if not math.isfinite(scale) or scale <= 0.0:
        raise KOAnimationBuildError("could not derive a finite positive KO state scale")
    reason = "height_target" if abs(scale - height_scale) <= 1e-9 else "width_limited"
    return scale, reason


def _render_state(
    spec: StateSpec,
    poses: Sequence[SourcePose],
) -> tuple[tuple[Image.Image, ...], dict[str, object]]:
    scale, scale_reason = _state_scale(poses)
    frames: list[Image.Image] = []
    signatures: set[str] = set()
    records: list[dict[str, object]] = []
    for pose in poses:
        width = max(1, math.floor(pose.crop.width * scale + 1e-9))
        height = max(1, math.floor(pose.crop.height * scale + 1e-9))
        if width > CELL_WIDTH or height > CELL_HEIGHT:
            raise KOAnimationBuildError(
                f"{spec.state}: pose {pose.index + 1} cannot fit the 304x128 runtime cell"
            )
        resized = _harden_alpha(
            pose.crop.resize((width, height), Image.Resampling.NEAREST)
        )
        scaled_root = pose.root_x * width / pose.crop.width
        x = round(ROOT_X - scaled_root)
        x = max(0, min(CELL_WIDTH - width, x))
        y = CELL_HEIGHT - height
        frame = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
        frame.alpha_composite(resized, (x, y))
        bounds = frame.getchannel("A").getbbox()
        if bounds is None:
            raise KOAnimationBuildError(f"{spec.state}: pose {pose.index + 1} rendered empty")
        if bounds[0] < 0 or bounds[1] < 0 or bounds[2] > CELL_WIDTH or bounds[3] > CELL_HEIGHT:
            raise KOAnimationBuildError(f"{spec.state}: pose {pose.index + 1} was clipped")
        if bounds[3] != CELL_HEIGHT:
            raise KOAnimationBuildError(
                f"{spec.state}: pose {pose.index + 1} missed the shared ground line"
            )
        alpha_values = set(_pixels(frame.getchannel("A")))
        if not alpha_values <= {0, 255}:
            raise KOAnimationBuildError(
                f"{spec.state}: pose {pose.index + 1} contains soft alpha"
            )
        spill = sum(
            alpha == 255 and _is_visible_chroma_spill(red, green, blue)
            for red, green, blue, alpha in _pixels(frame)
        )
        if spill:
            raise KOAnimationBuildError(
                f"{spec.state}: pose {pose.index + 1} retained {spill} matte spill pixels"
            )
        signature = _normalized_signature(frame)
        if signature in signatures:
            raise KOAnimationBuildError(
                f"{spec.state}: runtime pose {pose.index + 1} duplicates an earlier pose"
            )
        signatures.add(signature)
        rendered_root = x + scaled_root
        if abs(rendered_root - ROOT_X) > 1.01:
            raise KOAnimationBuildError(
                f"{spec.state}: pose {pose.index + 1} root registration drifted "
                f"{abs(rendered_root - ROOT_X):.2f}px"
            )
        frames.append(frame)
        records.append(
            {
                "pose": pose.index + 1,
                "source_file": pose.source_file,
                "source_pose": pose.source_pose_index + 1,
                "source_bounds_px": list(pose.source_bounds),
                "source_cell_bounds_px": list(pose.source_cell_bounds),
                "source_opaque_pixels": pose.opaque_pixels,
                "source_component_count": pose.component_count,
                "source_signature_sha256": pose.source_signature,
                "source_normalization_scale": round(
                    pose.source_normalization_scale,
                    8,
                ),
                "source_root_x": round(pose.root_x, 4),
                "runtime_bounds_px": list(bounds),
                "runtime_visible_height_px": bounds[3] - bounds[1],
                "runtime_root_x": round(rendered_root, 4),
                "runtime_signature_sha256": signature,
                "hard_alpha": True,
                "ground_y": GROUND_Y,
                "clipped": False,
            }
        )

    visible_heights = [record["runtime_visible_height_px"] for record in records]
    maximum_visible_height = max(visible_heights)
    if maximum_visible_height != TARGET_VISIBLE_HEIGHT:
        raise KOAnimationBuildError(
            f"{spec.state}: maximum visible height must be exactly "
            f"{TARGET_VISIBLE_HEIGHT}px, got {maximum_visible_height}px"
        )
    return tuple(frames), {
        "common_nearest_scale": round(scale, 8),
        "scale_limit": scale_reason,
        "target_visible_height_px": TARGET_VISIBLE_HEIGHT,
        "maximum_visible_height_px": maximum_visible_height,
        "target_height_achieved": maximum_visible_height == TARGET_VISIBLE_HEIGHT,
        "ground_line_px": GROUND_Y,
        "root_x_px": ROOT_X,
        "frames": records,
    }


def _generated_utc(value: str | None) -> str:
    if value:
        return str(value)
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch:
        try:
            timestamp = datetime.fromtimestamp(int(source_date_epoch), tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise KOAnimationBuildError("SOURCE_DATE_EPOCH must be an integer timestamp") from error
    else:
        timestamp = datetime.now(timezone.utc)
    return timestamp.isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_source_png(
    source_path: Path,
    *,
    label: str,
    minimum_pose_count: int,
) -> tuple[bytes, Image.Image, Image.Image, dict[str, int]]:
    source_bytes = source_path.read_bytes()
    try:
        with Image.open(BytesIO(source_bytes)) as opened:
            if getattr(opened, "n_frames", 1) != 1:
                raise KOAnimationBuildError(
                    f"{label}: source must be one still horizontal PNG sheet"
                )
            if (opened.format or "").upper() != "PNG":
                raise KOAnimationBuildError(f"{label}: source must be PNG")
            source = opened.convert("RGBA")
    except KOAnimationBuildError:
        raise
    except (OSError, ValueError) as error:
        raise KOAnimationBuildError(
            f"{label}: source PNG cannot be decoded: {source_path}"
        ) from error
    if source.width < minimum_pose_count * 3 or source.height < 3:
        raise KOAnimationBuildError(f"{label}: source sheet is too small")
    keyed, key_metrics = _key_and_harden(source, label=label)
    return source_bytes, source, keyed, key_metrics


def build_ko_animation(
    *,
    source_root: Path = SOURCE_ROOT,
    atlas_output: Path = ATLAS_OUTPUT,
    report_output: Path = REPORT_OUTPUT,
    generated_utc: str | None = None,
) -> dict[str, object]:
    """Validate all seven source sheets and atomically emit atlas + report."""

    source_root = Path(source_root).resolve()
    atlas_output = Path(atlas_output).resolve()
    report_output = Path(report_output).resolve()
    required_filenames = [spec.filename for spec in STATE_SPECS]
    required_filenames.append(SUPER_HOOK_FILENAME)
    missing = [
        source_root / filename
        for filename in required_filenames
        if not (source_root / filename).is_file()
    ]
    if missing:
        raise KOAnimationBuildError(
            "missing KO source sheet(s): " + ", ".join(str(path) for path in missing)
        )

    atlas = Image.new(
        "RGBA",
        (ATLAS_COLUMNS * CELL_WIDTH, ATLAS_ROWS * CELL_HEIGHT),
        (0, 0, 0, 0),
    )
    state_reports: dict[str, object] = {}
    all_runtime_signatures: set[str] = set()
    total_poses = 0
    for spec in STATE_SPECS:
        source_specs = [(spec.filename, spec.pose_count, "primary")]
        if spec.state == "super":
            source_specs = [
                (spec.filename, SUPER_BASE_POSE_COUNT, "base"),
                (SUPER_HOOK_FILENAME, 1, "hook"),
            ]

        extracted_sources: list[dict[str, object]] = []
        source_pose_groups: list[tuple[SourcePose, ...]] = []
        for filename, source_pose_count, role in source_specs:
            source_path = source_root / filename
            source_bytes, source, keyed, key_metrics = _load_source_png(
                source_path,
                label=spec.state if role == "primary" else f"{spec.state} {role}",
                minimum_pose_count=source_pose_count,
            )
            extraction_spec = StateSpec(
                spec.state,
                filename,
                source_pose_count,
                spec.row,
            )
            source_poses, segmentation = _extract_poses(
                keyed,
                spec=extraction_spec,
            )
            source_pose_groups.append(source_poses)
            extracted_sources.append(
                {
                    "role": role,
                    "path": str(source_path),
                    "filename": filename,
                    "sha256": _sha256_bytes(source_bytes),
                    "size_px": list(source.size),
                    "mode": "RGBA",
                    "pose_count": source_pose_count,
                    "keying": key_metrics,
                    "segmentation": segmentation,
                }
            )

        if spec.state == "super":
            base_poses, hook_poses = source_pose_groups
            if len(hook_poses) != 1:
                raise KOAnimationBuildError(
                    f"super hook: expected one genuine full-body pose, got {len(hook_poses)}"
                )
            reference_pose = base_poses[SUPER_HOOK_INSERT_AFTER - 1]
            hook_pose = hook_poses[0]
            hook_scale = reference_pose.crop.height / hook_pose.crop.height
            normalized_width = max(1, round(hook_pose.crop.width * hook_scale))
            normalized_height = max(1, round(hook_pose.crop.height * hook_scale))
            normalized_hook = replace(
                hook_pose,
                crop=_harden_alpha(
                    hook_pose.crop.resize(
                        (normalized_width, normalized_height),
                        Image.Resampling.NEAREST,
                    )
                ),
                root_x=hook_pose.root_x * normalized_width / hook_pose.crop.width,
                source_normalization_scale=hook_scale,
            )
            combined = (
                base_poses[:SUPER_HOOK_INSERT_AFTER]
                + (normalized_hook,)
                + base_poses[SUPER_HOOK_INSERT_AFTER:]
            )
        else:
            combined = source_pose_groups[0]
        poses = tuple(replace(pose, index=index) for index, pose in enumerate(combined))
        if len(poses) != spec.pose_count:
            raise KOAnimationBuildError(
                f"{spec.state}: expected {spec.pose_count} complete cels, got {len(poses)}"
            )
        frames, render_metrics = _render_state(spec, poses)
        for column, frame in enumerate(frames):
            signature = _normalized_signature(frame)
            # Cross-state duplicates usually mean a placeholder row was copied.
            # A production KO atlas must contain independently authored cels.
            if signature in all_runtime_signatures:
                raise KOAnimationBuildError(
                    f"{spec.state}: pose {column + 1} duplicates art from another KO state"
                )
            all_runtime_signatures.add(signature)
            atlas.alpha_composite(frame, (column * CELL_WIDTH, spec.row * CELL_HEIGHT))
        total_poses += len(frames)
        primary_source = extracted_sources[0]
        if spec.state == "super":
            segmentation_report: dict[str, object] = {
                "method": "authored_base_plus_single_hook",
                "base_pose_count": SUPER_BASE_POSE_COUNT,
                "hook_pose_count": 1,
                "hook_insert_after_base_pose": SUPER_HOOK_INSERT_AFTER,
                "hook_normalization": {
                    "method": "uniform_nearest_to_preceding_authored_pose_height",
                    "reference_base_pose": SUPER_HOOK_INSERT_AFTER,
                    "reference_height_px": reference_pose.crop.height,
                    "original_hook_size_px": list(hook_pose.crop.size),
                    "normalized_hook_size_px": list(normalized_hook.crop.size),
                    "scale": round(hook_scale, 8),
                },
                "sources": {
                    str(source["role"]): source["segmentation"]
                    for source in extracted_sources
                },
            }
            keying_report = {
                metric: sum(
                    int(source["keying"][metric])
                    for source in extracted_sources
                )
                for metric in primary_source["keying"]
            }
        else:
            segmentation_report = primary_source["segmentation"]
            keying_report = primary_source["keying"]
        state_reports[spec.state] = {
            "row": spec.row,
            "pose_count": spec.pose_count,
            "source_path": primary_source["path"],
            "source_sha256": primary_source["sha256"],
            "source_size_px": primary_source["size_px"],
            "source_mode": "RGBA",
            "source_matte_rgb": list(KEY_COLOR),
            "sources": extracted_sources,
            "frame_source_map": [
                {
                    "runtime_pose": pose.index + 1,
                    "source_file": pose.source_file,
                    "source_pose": pose.source_pose_index + 1,
                }
                for pose in poses
            ],
            "keying": keying_report,
            "segmentation": segmentation_report,
            "render": render_metrics,
        }

    expected_total = sum(spec.pose_count for spec in STATE_SPECS)
    if total_poses != expected_total:
        raise KOAnimationBuildError(
            f"KO atlas pose count drifted: expected {expected_total}, got {total_poses}"
        )
    alpha_values = set(_pixels(atlas.getchannel("A")))
    if not alpha_values <= {0, 255}:
        raise KOAnimationBuildError("KO atlas contains non-hard alpha")
    atlas_payload = _png_bytes(atlas)
    generator_path = Path(__file__).resolve()
    report: dict[str, object] = {
        "schema_version": 1,
        "actor": "ko",
        "generated_utc": _generated_utc(generated_utc),
        "generator": {
            "path": str(generator_path),
            "sha256": _sha256_bytes(generator_path.read_bytes()),
        },
        "source_contract": {
            "root": str(source_root),
            "layout": "left-to-right connected complete bodies",
            "matte_rgb": list(KEY_COLOR),
            "state_order": list(STATE_NAMES),
            "pose_counts": dict(POSE_COUNTS),
            "super_composition": {
                "base_file": "ko_super_source.png",
                "base_pose_count": SUPER_BASE_POSE_COUNT,
                "hook_file": SUPER_HOOK_FILENAME,
                "hook_pose_count": 1,
                "hook_insert_after_base_pose": SUPER_HOOK_INSERT_AFTER,
            },
            "mirroring": "renderer-owned; sources face right",
            "resampling": "nearest-neighbor only",
        },
        "states": state_reports,
        "output": {
            "atlas_path": str(atlas_output),
            "atlas_sha256": _sha256_bytes(atlas_payload),
            "atlas_size_bytes": len(atlas_payload),
            "atlas_size_px": list(atlas.size),
            "columns": ATLAS_COLUMNS,
            "rows": ATLAS_ROWS,
            "cell_size_px": [CELL_WIDTH, CELL_HEIGHT],
        },
        "validation": {
            "status": "PASS",
            "exact_state_set": list(STATE_NAMES),
            "total_authored_poses": total_poses,
            "hard_alpha": True,
            "complete_cel_resizing": True,
            "duplicate_poses": 0,
            "visible_chroma_spill_pixels": 0,
            "clipped_frames": 0,
            "ground_aligned": True,
            "directional_variants_generated": False,
        },
    }
    report_payload = (
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    _atomic_write(atlas_output, atlas_payload)
    _atomic_write(report_output, report_payload)
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    parser.add_argument("--atlas-output", type=Path, default=ATLAS_OUTPUT)
    parser.add_argument("--report-output", type=Path, default=REPORT_OUTPUT)
    parser.add_argument(
        "--generated-utc",
        default=None,
        help="fixed ISO timestamp for reproducible validation fixtures",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_ko_animation(
            source_root=args.source_root,
            atlas_output=args.atlas_output,
            report_output=args.report_output,
            generated_utc=args.generated_utc,
        )
    except KOAnimationBuildError as error:
        print(f"KO animation build rejected: {error}", file=sys.stderr)
        return 2
    output = report["output"]
    validation = report["validation"]
    print(
        f"KO animation atlas PASS: {validation['total_authored_poses']} poses -> "
        f"{output['atlas_path']} ({output['atlas_sha256']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
