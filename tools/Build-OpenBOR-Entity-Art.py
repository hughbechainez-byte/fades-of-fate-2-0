"""Build deterministic production pose sprites from approved 5x4 art sheets.

This tool owns only the source-art extraction layer.  It deliberately does not
write OpenBOR models, controllers, AI, combat data, effects, or packages.
"""

from __future__ import annotations

import hashlib
import json
import math
import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ENTITIES = ("black_dave", "homeless_man", "police_officer")
ROWS = 4
COLS = 5
POSES_PER_SHEET = ROWS * COLS
MAIN_COMPONENT_MIN = 100
ATTACH_DISTANCE = 16
CANVAS = (192, 160)
ROOT_POINT = (96, 156)
TRANSPARENT_RGB = (226, 8, 226)
AIRBORNE_GROUPS = {"air_punch", "air_kick"}


ACTION_TYPES = {
    "spawn": "spawn",
    "respawn": "spawn",
    "level_intro": "transition",
    "idle": "idle",
    "walk_start": "transition",
    "walk": "walk",
    "walk_loop": "walk",
    "walk_stop": "transition",
    "pivot": "transition",
    "turn_pivot": "transition",
    "jump_family": "special",
    "block": "block",
    "block_impact": "block_impact",
    "dodge": "dodge",
    "ranged": "special",
    "super": "special",
    "air_punch": "air_attack",
    "air_kick": "air_attack",
    "light_pain": "light_pain",
    "heavy_pain": "heavy_pain",
    "heavy_pain_fall": "knockdown",
    "knockdown_fall": "knockdown",
    "down": "down",
    "rise": "rise",
    "zero_health_lethal_fall": "death",
    "item_pickup": "interaction",
    "alert_aggro": "transition",
    "alert_command": "transition",
    "unarmed_jab": "light_attack",
    "two_hand_shove": "light_attack",
    "heavy_overhand": "heavy_attack",
    "taunt_hesitate": "transition",
    "baton_jab": "light_attack",
    "baton_backhand": "light_attack",
    "baton_overhead": "heavy_attack",
    "death": "death",
}


@dataclass
class Component:
    points: set[int]
    width: int

    @property
    def count(self) -> int:
        return len(self.points)

    @property
    def xs(self) -> list[int]:
        return [point % self.width for point in self.points]

    @property
    def ys(self) -> list[int]:
        return [point // self.width for point in self.points]

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        xs = self.xs
        ys = self.ys
        return min(xs), min(ys), max(xs) + 1, max(ys) + 1

    @property
    def center(self) -> tuple[float, float]:
        return (
            sum(point % self.width for point in self.points) / self.count,
            sum(point // self.width for point in self.points) / self.count,
        )


@dataclass
class SourcePose:
    sheet_path: Path
    sheet_number: int
    cell_number: int
    row: int
    column: int
    rgba: Image.Image
    group: str = ""
    group_index: int = 0
    pose_id: str = ""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def connected_components(alpha: Image.Image) -> list[Component]:
    """Return all 8-connected nontransparent components."""
    width, height = alpha.size
    source = alpha.tobytes()
    seen = bytearray(len(source))
    result: list[Component] = []
    for start, value in enumerate(source):
        if not value or seen[start]:
            continue
        seen[start] = 1
        stack = [start]
        points: set[int] = set()
        while stack:
            point = stack.pop()
            points.add(point)
            y, x = divmod(point, width)
            for dy in (-1, 0, 1):
                next_y = y + dy
                if next_y < 0 or next_y >= height:
                    continue
                row_start = next_y * width
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    next_x = x + dx
                    if next_x < 0 or next_x >= width:
                        continue
                    neighbor = row_start + next_x
                    if source[neighbor] and not seen[neighbor]:
                        seen[neighbor] = 1
                        stack.append(neighbor)
        result.append(Component(points, width))
    return result


def split_at_projection_valley(component: Component) -> tuple[Component, Component]:
    """Split a vertically merged pair at a strong central alpha valley."""
    top = min(component.ys)
    bottom = max(component.ys)
    height = bottom - top + 1
    projection = Counter(component.ys)
    first = top + round(height * 0.35)
    last = top + round(height * 0.65)
    midpoint = (top + bottom) // 2
    cut = min(
        range(first, last + 1),
        key=lambda y: (projection[y] + projection[y + 1], abs(y - midpoint)),
    )
    valley = projection[cut] + projection[cut + 1]
    peak = max(projection.values())
    upper = {point for point in component.points if point // component.width <= cut}
    lower = component.points - upper
    if (
        len(upper) < MAIN_COMPONENT_MIN
        or len(lower) < MAIN_COMPONENT_MIN
        or valley > max(24, round(peak * 0.16))
    ):
        raise ValueError(
            f"ambiguous merged-body split: height={height}, valley={valley}, peak={peak}"
        )
    return Component(upper, component.width), Component(lower, component.width)


def bbox_distance(a: Component, b: Component) -> int:
    a_left, a_top, a_right, a_bottom = a.bounds
    b_left, b_top, b_right, b_bottom = b.bounds
    dx = max(a_left - b_right, b_left - a_right, 0)
    dy = max(a_top - b_bottom, b_top - a_bottom, 0)
    return max(dx, dy)


def isolate_bodies(sheet: Image.Image, source_name: str) -> tuple[list[Component], int]:
    alpha = sheet.getchannel("A")
    if set(alpha.getdata()) - {0, 255}:
        raise ValueError(f"{source_name}: source alpha must be hard 0/255")
    components = connected_components(alpha)
    bodies = [part for part in components if part.count >= MAIN_COMPONENT_MIN]
    details = [part for part in components if part.count < MAIN_COMPONENT_MIN]

    while len(bodies) < POSES_PER_SHEET:
        candidate_index = max(
            range(len(bodies)),
            key=lambda index: (
                bodies[index].bounds[3] - bodies[index].bounds[1],
                bodies[index].count,
            ),
        )
        candidate = bodies.pop(candidate_index)
        if candidate.bounds[3] - candidate.bounds[1] < sheet.height * 0.35:
            raise ValueError(
                f"{source_name}: found {len(bodies) + 1} bodies and no safe tall merge to split"
            )
        bodies.extend(split_at_projection_valley(candidate))
    if len(bodies) != POSES_PER_SHEET:
        raise ValueError(f"{source_name}: expected 20 bodies, found {len(bodies)}")

    discarded = 0
    for detail in details:
        distances = [bbox_distance(detail, body) for body in bodies]
        nearest = min(range(len(bodies)), key=lambda index: distances[index])
        if distances[nearest] <= ATTACH_DISTANCE:
            bodies[nearest].points.update(detail.points)
        else:
            discarded += detail.count

    ordered = sorted(bodies, key=lambda body: body.center[1])
    rows = [ordered[row * COLS : (row + 1) * COLS] for row in range(ROWS)]
    for row_number, row in enumerate(rows, 1):
        if len(row) != COLS:
            raise ValueError(f"{source_name}: row {row_number} does not contain five bodies")
        row.sort(key=lambda body: body.center[0])
    for row_index in range(ROWS - 1):
        upper_max = max(body.center[1] for body in rows[row_index])
        lower_min = min(body.center[1] for body in rows[row_index + 1])
        if lower_min - upper_max < sheet.height * 0.10:
            raise ValueError(f"{source_name}: ambiguous visual-row separation")
    return [body for row in rows for body in row], discarded


def body_image(sheet: Image.Image, component: Component) -> Image.Image:
    left, top, right, bottom = component.bounds
    crop = sheet.crop((left, top, right, bottom))
    mask = Image.new("L", crop.size, 0)
    pixels = mask.load()
    for point in component.points:
        x = point % component.width - left
        y = point // component.width - top
        pixels[x, y] = 255
    crop.putalpha(mask)
    bounds = crop.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("segmented body is empty")
    return crop.crop(bounds)


def allocation_sequence(design: dict) -> list[tuple[str, int, str]]:
    prefix = design["pose_id_rule"].split("<", 1)[0]
    result: list[tuple[str, int, str]] = []
    for group, count in design["pose_allocation"].items():
        for index in range(1, int(count) + 1):
            result.append((group, index, f"{prefix}{group}_{index:03d}"))
    return result


def load_source_poses(entity_dir: Path, design: dict) -> tuple[list[SourcePose], list[dict]]:
    source_dir = entity_dir / "art_source" / "production"
    sheets = sorted(source_dir.glob(f"{design['entity_id']}_pose_sheet_[0-9][0-9].png"))
    target = int(design["exact_unique_pose_target"])
    expected_sheets = math.ceil(target / POSES_PER_SHEET)
    if len(sheets) != expected_sheets or target % POSES_PER_SHEET:
        raise ValueError(
            f"{design['entity_id']}: expected {expected_sheets} complete 20-pose sheets, found {len(sheets)}"
        )
    poses: list[SourcePose] = []
    sheet_records: list[dict] = []
    for sheet_number, path in enumerate(sheets, 1):
        sheet = Image.open(path).convert("RGBA")
        bodies, discarded = isolate_bodies(sheet, path.name)
        sheet_records.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
                "body_count": len(bodies),
                "discarded_unattached_pixels": discarded,
            }
        )
        for cell_index, body in enumerate(bodies):
            poses.append(
                SourcePose(
                    sheet_path=path,
                    sheet_number=sheet_number,
                    cell_number=cell_index + 1,
                    row=cell_index // COLS + 1,
                    column=cell_index % COLS + 1,
                    rgba=body_image(sheet, body),
                )
            )
    assignments = allocation_sequence(design)
    if len(poses) != target or len(assignments) != target:
        raise ValueError(f"{design['entity_id']}: source/allocation count does not equal {target}")
    for pose, (group, group_index, pose_id) in zip(poses, assignments, strict=True):
        pose.group = group
        pose.group_index = group_index
        pose.pose_id = pose_id
    return poses, sheet_records


def pose_fits_at_scale(pose: SourcePose, fixed_scale: float) -> bool:
    """Return whether one pose can keep the common root without clipping."""
    size = (
        max(1, round(pose.rgba.width * fixed_scale)),
        max(1, round(pose.rgba.height * fixed_scale)),
    )
    scaled = pose.rgba.resize(size, Image.Resampling.NEAREST)
    alpha = scaled.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        return False
    left, top, right, bottom = bounds
    origin_y = ROOT_POINT[1] - (bottom - 1)
    if origin_y + top < 0 or origin_y + bottom > CANVAS[1]:
        return False
    if pose.group in AIRBORNE_GROUPS:
        body_center_x = round((left + right - 1) / 2)
        origin_x = ROOT_POINT[0] - body_center_x
        return origin_x + left >= 0 and origin_x + right <= CANVAS[0]
    contact_depth = max(3, round((bottom - top) * 0.025))
    contact_xs = {
        x
        for y in range(max(top, bottom - contact_depth), bottom)
        for x in range(left, right)
        if alpha.getpixel((x, y))
    }
    minimum_support_x = ROOT_POINT[0] + right - CANVAS[0]
    maximum_support_x = ROOT_POINT[0] + left
    return any(minimum_support_x <= x <= maximum_support_x for x in contact_xs)


def scale_and_root(poses: list[SourcePose], design: dict) -> tuple[list[Image.Image], float]:
    idle_heights = [pose.rgba.height for pose in poses if pose.group == "idle"]
    if not idle_heights:
        raise ValueError(f"{design['entity_id']}: no idle poses available for fixed-scale calibration")
    requested_scale = float(design["identity"]["cast_height_px"]) / float(median(idle_heights))
    # Preserve one scale across the entire model.  If an authored extension is
    # wider than the canvas around its support/root, derive the largest global
    # scale that fits every pose instead of shrinking individual drawings.
    low = 0.05
    high = requested_scale
    if not all(pose_fits_at_scale(pose, high) for pose in poses):
        for _ in range(16):
            candidate = (low + high) / 2.0
            if all(pose_fits_at_scale(pose, candidate) for pose in poses):
                low = candidate
            else:
                high = candidate
        fixed_scale = low * 0.998
    else:
        fixed_scale = requested_scale
    rooted: list[Image.Image] = []
    for pose in poses:
        size = (
            max(1, round(pose.rgba.width * fixed_scale)),
            max(1, round(pose.rgba.height * fixed_scale)),
        )
        scaled = pose.rgba.resize(size, Image.Resampling.NEAREST)
        alpha = scaled.getchannel("A")
        bounds = alpha.getbbox()
        if bounds is None:
            raise ValueError(f"{pose.pose_id}: scaled body is empty")
        left, top, right, bottom = bounds
        if pose.group in AIRBORNE_GROUPS:
            support_x = round((left + right - 1) / 2)
            origin_x = ROOT_POINT[0] - support_x
            origin_y = ROOT_POINT[1] - (bottom - 1)
            placed_bounds = (
                origin_x + left,
                origin_y + top,
                origin_x + right,
                origin_y + bottom,
            )
            if (
                placed_bounds[0] < 0
                or placed_bounds[1] < 0
                or placed_bounds[2] > CANVAS[0]
                or placed_bounds[3] > CANVAS[1]
            ):
                raise ValueError(
                    f"{pose.pose_id}: fixed-scale airborne body clips canvas; "
                    f"bounds={placed_bounds}, scale={fixed_scale:.6f}"
                )
            canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
            canvas.alpha_composite(scaled, (origin_x, origin_y))
            rooted.append(canvas)
            continue
        contact_depth = max(3, round((bottom - top) * 0.025))
        contact_xs = [
            x
            for y in range(max(top, bottom - contact_depth), bottom)
            for x in range(left, right)
            if alpha.getpixel((x, y))
        ]
        if not contact_xs:
            raise ValueError(f"{pose.pose_id}: no root contact pixels")
        desired_support_x = round(median(contact_xs))
        minimum_support_x = ROOT_POINT[0] + right - CANVAS[0]
        maximum_support_x = ROOT_POINT[0] + left
        valid_contacts = [
            x for x in contact_xs if minimum_support_x <= x <= maximum_support_x
        ]
        if not valid_contacts:
            raise ValueError(
                f"{pose.pose_id}: fixed-scale body has no non-clipping pixel in its root-contact band"
            )
        support_x = min(valid_contacts, key=lambda x: (abs(x - desired_support_x), x))
        origin_x = ROOT_POINT[0] - support_x
        origin_y = ROOT_POINT[1] - (bottom - 1)
        placed_bounds = (
            origin_x + left,
            origin_y + top,
            origin_x + right,
            origin_y + bottom,
        )
        if (
            placed_bounds[0] < 0
            or placed_bounds[1] < 0
            or placed_bounds[2] > CANVAS[0]
            or placed_bounds[3] > CANVAS[1]
        ):
            raise ValueError(
                f"{pose.pose_id}: fixed-scale rooted body clips canvas; bounds={placed_bounds}, scale={fixed_scale:.6f}"
            )
        canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        canvas.alpha_composite(scaled, (origin_x, origin_y))
        rooted.append(canvas)
    return rooted, fixed_scale


def build_palette(images: list[Image.Image]) -> tuple[list[int], list[tuple[int, int, int]]]:
    opaque = bytearray()
    for image in images:
        rgba = image.convert("RGBA")
        for red, green, blue, alpha in rgba.getdata():
            if alpha:
                opaque.extend((red, green, blue))
    pixel_count = len(opaque) // 3
    if not pixel_count:
        raise ValueError("cannot build palette from empty sprites")
    width = 1024
    height = math.ceil(pixel_count / width)
    opaque.extend(bytes((width * height - pixel_count) * 3))
    sample = Image.frombytes("RGB", (width, height), bytes(opaque))
    quantized = sample.quantize(
        colors=255,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    source_palette = quantized.getpalette()
    used = sorted(set(quantized.getdata()))
    colors = [tuple(source_palette[index * 3 : index * 3 + 3]) for index in used]
    if not colors or len(colors) > 255:
        raise ValueError("invalid opaque master palette")
    padded = [TRANSPARENT_RGB, *colors]
    padded.extend([colors[-1]] * (256 - len(padded)))
    palette = [channel for color in padded for channel in color]
    return palette, colors


def index_image(image: Image.Image, palette: list[int], colors: list[tuple[int, int, int]]) -> Image.Image:
    rgba = image.convert("RGBA")
    output = Image.new("P", rgba.size, 0)
    output.putpalette(palette)
    cache: dict[tuple[int, int, int], int] = {}
    indexed: list[int] = []
    for red, green, blue, alpha in rgba.getdata():
        if not alpha:
            indexed.append(0)
            continue
        rgb = (red, green, blue)
        palette_index = cache.get(rgb)
        if palette_index is None:
            palette_index = 1 + min(
                range(len(colors)),
                key=lambda index: (
                    (red - colors[index][0]) ** 2
                    + (green - colors[index][1]) ** 2
                    + (blue - colors[index][2]) ** 2
                ),
            )
            cache[rgb] = palette_index
        indexed.append(palette_index)
    output.putdata(indexed)
    output.info["transparency"] = 0
    return output


def action_groups(action: dict) -> list[str]:
    if "pose_groups" in action:
        return list(action["pose_groups"])
    return [action["pose_group"]]


def build_clips(design: dict, group_ids: dict[str, list[str]]) -> dict[str, dict]:
    clips: dict[str, dict] = {}
    for action in design["actions"]:
        action_id = action["id"]
        pose_ids = [pose_id for group in action_groups(action) for pose_id in group_ids[group]]
        clips[action_id] = {
            "pose_ids": pose_ids,
            "action_type": ACTION_TYPES[action_id],
            "trigger": action["trigger"],
            "native_animation": action["native_animation"],
        }
    if design["entity_id"] == "black_dave":
        shared = group_ids["combat_shared"]
        for family in ("regular", "kick", "power"):
            for step in range(1, 8):
                specific_group = f"{family}_{step:02d}_specific"
                clip_id = f"{family}_{step:02d}"
                common = shared if family == "power" else shared[:5]
                clips[clip_id] = {
                    "pose_ids": [*common, *group_ids[specific_group]],
                    "action_type": "heavy_attack" if family == "power" else "light_attack",
                    "trigger": f"{family} route input reaches step {step}",
                    "native_animation": f"FREESPECIAL{step}",
                }
    return clips


def write_review(entity_dir: Path, entity_id: str, images: list[Image.Image], poses: list[SourcePose]) -> Path:
    columns = 10
    cell_width, cell_height = 96, 96
    rows = math.ceil(len(images) / columns)
    review = Image.new("RGB", (columns * cell_width, rows * cell_height), (32, 34, 43))
    draw = ImageDraw.Draw(review)
    for index, (image, pose) in enumerate(zip(images, poses, strict=True)):
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        preview = image.resize((96, 80), Image.Resampling.NEAREST)
        review.paste(preview.convert("RGB"), (x, y), preview.getchannel("A"))
        draw.text((x + 2, y + 82), pose.pose_id, fill=(235, 236, 240))
    review_dir = entity_dir / "sprites" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / f"{entity_id}_pose_contact_sheet.png"
    review.save(path, format="PNG", optimize=False)
    return path


def build_entity(entity_id: str) -> dict:
    entity_dir = ROOT / "content" / "characters" / entity_id
    design_path = entity_dir / "metadata" / "production_manifest.json"
    design = load_json(design_path)
    if tuple(design["canvas"]) != CANVAS or tuple(design["root_offset"]) != ROOT_POINT:
        raise ValueError(f"{entity_id}: builder requires canvas {CANVAS} and root {ROOT_POINT}")
    poses, sheet_records = load_source_poses(entity_dir, design)
    rgba_images, fixed_scale = scale_and_root(poses, design)
    palette, colors = build_palette(rgba_images)
    indexed_images = [index_image(image, palette, colors) for image in rgba_images]

    poses_dir = entity_dir / "sprites" / "poses"
    poses_dir.mkdir(parents=True, exist_ok=True)
    expected_names = {f"{pose.pose_id}.png" for pose in poses}
    for stale in poses_dir.glob("*.png"):
        if stale.name not in expected_names:
            stale.unlink()
    for pose, image in zip(poses, indexed_images, strict=True):
        image.save(poses_dir / f"{pose.pose_id}.png", format="PNG", transparency=0, optimize=False)

    group_ids: dict[str, list[str]] = {}
    for group in design["pose_allocation"]:
        group_ids[group] = [pose.pose_id for pose in poses if pose.group == group]
    clips = build_clips(design, group_ids)
    pose_clips: dict[str, list[str]] = {pose.pose_id: [] for pose in poses}
    for clip_id, clip in clips.items():
        for pose_id in clip["pose_ids"]:
            pose_clips[pose_id].append(clip_id)
    pose_actions = {pose_id: list(clip_ids) for pose_id, clip_ids in pose_clips.items()}
    unreferenced = [pose_id for pose_id, clip_ids in pose_clips.items() if not clip_ids]
    if unreferenced:
        raise ValueError(f"{entity_id}: unreferenced poses: {unreferenced[:8]}")

    pose_records = []
    for pose, path_image in zip(poses, indexed_images, strict=True):
        bounds = path_image.convert("RGBA").getchannel("A").getbbox()
        if bounds is None:
            raise ValueError(f"{pose.pose_id}: indexed output is empty")
        output_path = poses_dir / f"{pose.pose_id}.png"
        pose_records.append(
            {
                "id": pose.pose_id,
                "group": pose.group,
                "group_index": pose.group_index,
                "approved": True,
                "root": list(ROOT_POINT),
                "body_bounds": list(bounds),
                "source_sheet": pose.sheet_path.relative_to(ROOT).as_posix(),
                "source_cell": pose.cell_number,
                "source_row": pose.row,
                "source_column": pose.column,
                "path": output_path.relative_to(ROOT).as_posix(),
                "sha256": sha256(output_path),
                "clips": pose_clips[pose.pose_id],
                "actions": pose_actions[pose.pose_id],
            }
        )

    review_path = write_review(entity_dir, entity_id, rgba_images, poses)
    palette_hash = hashlib.sha256(bytes(palette)).hexdigest()
    manifest = {
        "schema_version": 1,
        "entity_id": entity_id,
        "generator": "tools/Build-OpenBOR-Entity-Art.py",
        "source_design": design_path.relative_to(ROOT).as_posix(),
        "source_sheets": sheet_records,
        "canvas": list(CANVAS),
        "root": list(ROOT_POINT),
        "fixed_entity_scale": round(fixed_scale, 8),
        "palette": {
            "entries": 256,
            "transparency_index": 0,
            "opaque_colors": len(colors),
            "sha256": palette_hash,
            "dithering": False,
            "shared_across_model": True,
        },
        "poses": pose_records,
        "clips": clips,
        "near_duplicate_reviews": [],
        "review_contact_sheet": review_path.relative_to(ROOT).as_posix(),
        "runtime": {},
    }
    manifest_path = entity_dir / "sprites" / "pose_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    loaded_palettes = set()
    for pose in poses:
        image = Image.open(poses_dir / f"{pose.pose_id}.png")
        if image.mode != "P" or image.info.get("transparency") != 0:
            raise ValueError(f"{pose.pose_id}: output is not indexed with transparency index 0")
        loaded_palettes.add(bytes(image.getpalette()))
    if len(loaded_palettes) != 1:
        raise ValueError(f"{entity_id}: saved output palette drift")
    return {
        "entity": entity_id,
        "poses": len(poses),
        "clips": len(clips),
        "fixed_scale": round(fixed_scale, 8),
        "palette_sha256": palette_hash,
        "manifest": manifest_path.relative_to(ROOT).as_posix(),
        "review": review_path.relative_to(ROOT).as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity", action="append", choices=ENTITIES)
    args = parser.parse_args()
    selected = tuple(args.entity or ENTITIES)
    reports = [build_entity(entity_id) for entity_id in selected]
    print(json.dumps({"status": "pass", "entities": reports}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
