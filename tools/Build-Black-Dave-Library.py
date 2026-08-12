"""Bake Black Dave's complete authored V2 cels to the approved smaller root."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ATLAS = ROOT / "assets/sprites/black_dave_v2_animation_atlas.png"
SOURCE_METADATA = ROOT / "assets/sprites/black_dave_v2_pose_metadata.json"
OUTPUT_ATLAS = ROOT / "assets/sprites/black_dave_full_library_v1.png"
OUTPUT_METADATA = ROOT / "assets/sprites/black_dave_full_library_v1.json"
UTILITY_SOURCE = ROOT / "art_source/black_dave/full_library/black_dave_utility_pose_board_v1.png"
CELL = (224, 160)
ROOT_POINT = (112, 156)
SCALE = 0.84
UTILITY_SCALE = 0.42


def apply_underpass_grade(image: Image.Image) -> Image.Image:
    """Subdue sprite-only saturation while retaining readable authored ramps."""
    graded = image.copy()
    pixels = graded.load()
    for y in range(graded.height):
        for x in range(graded.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                continue
            luminance = 0.299 * red + 0.587 * green + 0.114 * blue
            saturation_mix = 0.76
            grey = 0.299 * red + 0.587 * green + 0.114 * blue
            red = grey + (red - grey) * saturation_mix
            green = grey + (green - grey) * saturation_mix
            blue = grey + (blue - grey) * saturation_mix
            if luminance < 88:
                cool = min(0.34, (88 - luminance) / 180.0)
                red = red * (1.0 - cool) + 18 * cool
                green = green * (1.0 - cool) + 28 * cool
                blue = blue * (1.0 - cool) + 48 * cool
            if luminance > 210:
                red = min(232, red * 0.92 + 10)
                green = min(232, green * 0.94 + 10)
                blue = min(238, blue * 0.98 + 12)
            pixels[x, y] = (round(red), round(green), round(blue), alpha)
    return graded


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def point(value: list[int], *, old_root: tuple[int, int]) -> list[int]:
    return [
        ROOT_POINT[0] + round((int(value[0]) - old_root[0]) * SCALE),
        ROOT_POINT[1] + round((int(value[1]) - old_root[1]) * SCALE),
    ]


def rect(value: list[int], *, old_root: tuple[int, int]) -> list[int]:
    return [
        ROOT_POINT[0] + round((int(value[0]) - old_root[0]) * SCALE),
        ROOT_POINT[1] + round((int(value[1]) - old_root[1]) * SCALE),
        ROOT_POINT[0] + round((int(value[2]) - old_root[0]) * SCALE),
        ROOT_POINT[1] + round((int(value[3]) - old_root[1]) * SCALE),
    ]


def main() -> None:
    source = Image.open(SOURCE_ATLAS).convert("RGBA")
    source_meta = json.loads(SOURCE_METADATA.read_text(encoding="utf-8"))
    old_cell = tuple(source_meta["cell_size"])
    old_root = tuple(source_meta["root"])
    if old_cell != (192, 160) or old_root != (96, 156):
        raise SystemExit("unexpected Black Dave V2 source contract")

    clips = source_meta["clips"]
    utility = Image.open(UTILITY_SOURCE).convert("RGBA")
    utility_cell = (utility.width / 4, utility.height / 4)
    clips = json.loads(json.dumps(clips))
    for extra_index in range(15):
        clip_id = f"black_dave_full_identity_transition_{extra_index // 5 + 1:02d}"
        clips.setdefault(clip_id, {
            "row": len(clips),
            "loop": False,
            "hold": 1,
            "phases": ["anticipation", "launch", "contact", "follow_through", "recovery"],
            "poses": [],
        })
        clips[clip_id]["poses"].append({
            "root": list(old_root),
            "anchors": {"rear_foot": [88, 156], "lead_foot": [104, 156], "pelvis": [96, 109], "head": [96, 54]},
            "anatomy": {"reference": "black_dave_upright_neutral_v2", "head_to_pelvis": 55, "head_width": 22, "shoulder_span": 47, "chest_span": 41, "pelvis_span": 37, "limb_thickness": 14, "shoe_width": 27},
            "sockets": [], "events": [],
            "source": {"state": "idle", "row": extra_index // 4, "column": extra_index % 4, "alpha_bounds": [0, 0, 0, 0], "opaque_pixels": 0, "normalization": {}},
        })
    output = Image.new("RGBA", (CELL[0] * 5, CELL[1] * len(clips)), (0, 0, 0, 0))
    scaled_width = round(old_cell[0] * SCALE)
    scaled_height = round(old_cell[1] * SCALE)
    provenance = {
        "method": "uniform_nearest_neighbor",
        "anatomy_reference": "black_dave_preview_neutral_v1",
        "scale": SCALE,
        "source_root": list(old_root),
        "root_alignment_offset": 0,
    }

    for clip_id, clip in clips.items():
        row = int(clip["row"])
        for pose_index, pose in enumerate(clip["poses"]):
            if clip_id.startswith("black_dave_full_identity_transition_"):
                extra_index = (int(clip_id[-2:]) - 1) * 5 + pose_index
                col, grid_row = extra_index % 4, extra_index // 4
                source_cell = utility.crop((round(col * utility_cell[0]), round(grid_row * utility_cell[1]), round((col + 1) * utility_cell[0]), round((grid_row + 1) * utility_cell[1])))
                scaled = source_cell.resize((round(source_cell.width * UTILITY_SCALE), round(source_cell.height * UTILITY_SCALE)), Image.Resampling.NEAREST)
                alpha = scaled.getchannel("A").point(lambda value: 255 if value >= 128 else 0)
                scaled.putalpha(alpha)
                bounds = scaled.getbbox()
                if bounds is None:
                    raise SystemExit(f"utility pose {extra_index} is empty")
                destination = (pose_index * CELL[0] + ROOT_POINT[0] - round(scaled.width / 2), row * CELL[1] + ROOT_POINT[1] - bounds[3])
                pose["source"]["alpha_bounds"] = list(bounds)
                pose["source"]["opaque_pixels"] = sum(value == 255 for value in alpha.getdata())
                pose["source"]["normalization"] = {"method": "uniform_nearest_neighbor", "anatomy_reference": "black_dave_preview_neutral_v1", "scale": UTILITY_SCALE, "root_alignment_offset": 0}
            else:
                source_cell = source.crop(
                    (pose_index * old_cell[0], row * old_cell[1], (pose_index + 1) * old_cell[0], (row + 1) * old_cell[1])
                )
                scaled = source_cell.resize((scaled_width, scaled_height), Image.Resampling.NEAREST)
                scaled_bounds = scaled.getbbox()
                if scaled_bounds is None:
                    raise SystemExit(f"source pose {clip_id}/{pose_index} is empty")
                destination = (pose_index * CELL[0] + ROOT_POINT[0] - round(old_root[0] * SCALE), row * CELL[1] + ROOT_POINT[1] - scaled_bounds[3])
            output.alpha_composite(scaled, destination)
            placed_cell = output.crop((pose_index * CELL[0], row * CELL[1], (pose_index + 1) * CELL[0], (row + 1) * CELL[1]))
            placed_bounds = placed_cell.getbbox()
            if placed_bounds is None:
                raise SystemExit(f"placed pose {clip_id}/{pose_index} is empty")
            pose["body_bounds"] = [placed_bounds[0], placed_bounds[1], placed_bounds[2], placed_bounds[3]]
            pose["root"] = list(ROOT_POINT)
            if clip_id.startswith("black_dave_full_identity_transition_"):
                pose["anchors"] = {"rear_foot": [ROOT_POINT[0] - 14, ROOT_POINT[1]], "lead_foot": [ROOT_POINT[0] + 14, ROOT_POINT[1]], "pelvis": [ROOT_POINT[0], ROOT_POINT[1] - 44], "head": [ROOT_POINT[0], ROOT_POINT[1] - 91]}
                pose["anatomy"] = {"reference": "black_dave_preview_neutral_v1", "head_to_pelvis": 46, "head_width": 18, "shoulder_span": 39, "chest_span": 34, "pelvis_span": 31, "limb_thickness": 12, "shoe_width": 23}
                continue
            pose["anchors"] = {name: point(value, old_root=old_root) for name, value in pose["anchors"].items()}
            pose["sockets"] = [
                {**socket, "position": point(socket["position"], old_root=old_root)}
                for socket in pose.get("sockets", [])
            ]
            pose["anatomy"] = {
                key: round(int(value) * SCALE)
                for key, value in pose["anatomy"].items()
                if key != "reference"
            } | {"reference": "black_dave_preview_neutral_v1"}
            pose["source"]["normalization"] = dict(provenance)

    output = apply_underpass_grade(output)
    rgba = output.load()
    for y in range(output.height):
        for x in range(output.width):
            if rgba[x, y][3] == 0:
                rgba[x, y] = (0, 0, 0, 0)
    output.save(OUTPUT_ATLAS, optimize=False)
    metadata = {
        "version": 1,
        "status": "production_full_library",
        "actor": "black_dave",
        "cell_size": list(CELL),
        "columns": 5,
        "root": list(ROOT_POINT),
        "pose_count": sum(len(clip["poses"]) for clip in clips.values()),
        "pose_budget": {"minimum": 120, "normal": 220, "ideal": 350, "authored": sum(len(clip["poses"]) for clip in clips.values())},
        "source_mode": "complete_authored_whole_cels_uniformly_rebaked_to_approved_smaller_root_then_underpass_graded",
        "environment_grade": {
            "profile": "cool_underpass_dusk_v1",
            "saturation_mix": 0.76,
            "shadow_tint": [18, 28, 48],
            "edge_rule": "hard_alpha_preserved_with_navy_shadow_contours",
            "grounding": "runtime_contact_shadow_and_shared_logical_ground_plane",
        },
        "source_hashes": {
            "assets/sprites/black_dave_v2_animation_atlas.png": sha256(SOURCE_ATLAS),
            "assets/sprites/black_dave_v2_pose_metadata.json": sha256(SOURCE_METADATA),
            "art_source/black_dave/full_library/black_dave_utility_pose_board_v1.png": sha256(UTILITY_SOURCE),
            "assets/sprites/black_dave_full_library_v1.png": sha256(OUTPUT_ATLAS),
        },
        "clips": clips,
    }
    OUTPUT_METADATA.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_ATLAS} ({output.width}x{output.height})")
    print(f"wrote {OUTPUT_METADATA} ({metadata['pose_count']} authored poses)")


if __name__ == "__main__":
    main()
