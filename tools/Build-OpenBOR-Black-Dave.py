"""Build the OpenBOR-ready Black Dave frame package from the approved atlas."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content/characters/black_dave"
META_PATH = CONTENT / "sprites/black_dave_full_library_v1.json"
ATLAS_PATH = CONTENT / "sprites/black_dave_full_library_v1.png"
OUT = ROOT / "openbor/data/chars/black_dave"
FRAME_ROOT = OUT / "sprites"
LEVEL_ART = ROOT / "openbor/data/levels/i8_underpass/art"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_id(value: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in value)


def build_master_palette(image: Image.Image) -> Image.Image:
    """Create the one palette shared by every frame in the model."""
    compatibility_palette = ROOT / "openbor/runtime/data/sprites/black_dave/idle/00.png"
    if compatibility_palette.is_file():
        return Image.open(compatibility_palette).convert("P")
    rgba = image.convert("RGBA")
    opaque = Image.new("RGB", rgba.size, (0, 0, 0))
    opaque.paste(rgba.convert("RGB"), mask=rgba.getchannel("A"))
    return opaque.quantize(colors=255, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)


def indexed_sprite(image: Image.Image, master_palette: Image.Image) -> Image.Image:
    """Return an indexed frame using the model palette and transparent index 0."""
    rgba = image.convert("RGBA")
    opaque = rgba.convert("RGB").quantize(palette=master_palette, dither=Image.Dither.NONE)
    source_indices = opaque.load()
    alpha = rgba.getchannel("A")
    output = Image.new("P", rgba.size, 0)
    output.putpalette([0, 0, 0] + list(master_palette.getpalette()[:765]))
    target_indices = output.load()
    alpha_values = alpha.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            target_indices[x, y] = source_indices[x, y] + 1 if alpha_values[x, y] else 0
    output.info["transparency"] = 0
    return output


def build_frames(metadata: dict) -> dict[str, list[Path]]:
    atlas = Image.open(ATLAS_PATH).convert("RGBA")
    master_palette = build_master_palette(atlas)
    cell_width, cell_height = map(int, metadata["cell_size"])
    columns = int(metadata["columns"])
    FRAME_ROOT.mkdir(parents=True, exist_ok=True)
    for old in FRAME_ROOT.glob("*.png"):
        old.unlink()
    frame_map: dict[str, list[Path]] = {}
    for clip_id, clip in metadata["clips"].items():
        row = int(clip["row"])
        frames: list[Path] = []
        for index in range(columns):
            frame_id = f"{safe_id(clip_id)}_{index:03d}.png"
            path = FRAME_ROOT / frame_id
            source_cell = atlas.crop((index * cell_width, row * cell_height, (index + 1) * cell_width, (row + 1) * cell_height))
            cell = source_cell.crop((16, 0, cell_width - 16, cell_height))
            indexed_sprite(cell, master_palette).save(path, optimize=False)
            frames.append(path)
        frame_map[clip_id] = frames
    return frame_map


def write_model(metadata: dict, frame_map: dict[str, list[Path]]) -> None:
    aliases = {
        "spawn": "idle",
        "idle": "idle",
        "walk": "walk",
        "pain": "hurt",
        "fall": "down",
        "rise": "recovery",
        "attack1": "black_dave_v2_regular_01",
        "attack2": "black_dave_v2_regular_02",
        "attack3": "black_dave_v2_regular_03",
        "attack4": "black_dave_v2_kick_01",
    }
    state_aliases = [
        ("block", "guard"),
        ("run", "walk_start"),
        ("backwalk", "walk_stop"),
        ("turn", "walk_reverse"),
        ("jumpdelay", "jump_takeoff"),
        ("forwardjump", "jump_rise"),
        ("jump", "jump_apex"),
        ("runjump", "jump_fall"),
        ("jumpland", "jump_land"),
        ("dodge", "dodge"),
        ("attackup", "ranged"),
        ("special", "super"),
        ("sleep", "pet"),
        ("jumpattack", "air_punch"),
        ("jumpattack2", "air_kick"),
    ]
    lines = [
        "name BlackDave",
        "type player",
        "health 100",
        "mp 100",
        "speed 4",
        "jumpspeed 2.0",
        "jumpheight 5",
        "grabdistance 34",
        "subject_to_gravity 1",
        "shadow 1",
        "gfxshadow 1",
        "atchain 1 2 3 4",
        "com a2 freespecial1",
        "com a3 freespecial2",
        "com a4 freespecial3",
        "ondoattackscript data/scripts/black_dave_contact.c",
        "",
    ]
    attack_specs = {
        "attack1": (12, 28, 38, 16),
        "attack2": (14, 30, 42, 16),
        "attack3": (16, 32, 48, 22),
        "attack4": (14, 34, 52, 18),
        "freespecial1": (20, 36, 62, 26),
    }
    route_clips = [
        *(f"black_dave_v2_regular_{index:02d}" for index in range(1, 8)),
        *(f"black_dave_v2_kick_{index:02d}" for index in range(1, 8)),
        *(f"black_dave_v2_power_{index:02d}" for index in range(1, 8)),
    ]
    for animation_name, clip_id in aliases.items():
        if clip_id not in frame_map:
            raise ValueError(f"required OpenBOR animation is missing: {clip_id}")
        clip = metadata["clips"][clip_id]
        lines += [f"anim {animation_name}"]
        if animation_name in {"idle", "walk"}:
            lines += ["    loop 1"]
        lines += ["    delay 8", "    offset 96 156", "    bbox 24 18 144 138 18"]
        if animation_name in attack_specs:
            damage, x, width, height = attack_specs[animation_name]
            lines += ["    attack 0", f"    attack {x} 108 {width} {height} {damage} 0 0 0 4 24"]
        for frame in frame_map[clip_id]:
            lines.append(f"    frame data/chars/black_dave/sprites/{frame.name}")
        if animation_name in attack_specs:
            lines += ["    attack 0"]
        lines += [""]
    state_bank_clips = [clip_id for _, clip_id in state_aliases]
    route_banks = [[route_clips[step], route_clips[7 + step], route_clips[14 + step]] for step in range(7)]
    for index, clip_id in enumerate(state_bank_clips):
        route_banks[index % 7].append(clip_id)
    for bank_index, bank_clips in enumerate(route_banks, start=1):
        animation_name = f"freespecial{bank_index}"
        lines += [f"anim {animation_name}", "    offset 96 156", "    bbox 24 18 144 138 18", "    delay 8", "    attack 0", "    attack 28 108 56 24 16 0 0 0 4 24"]
        for clip_id in bank_clips:
            for frame in frame_map[clip_id]:
                lines.append(f"    frame data/chars/black_dave/sprites/{frame.name}")
        lines += ["    attack 0", ""]
    # The full authored library remains manifest-backed; only native action
    # aliases are emitted here because OpenBOR reserves animation identifiers.
    (OUT / "black_dave.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifests(metadata: dict, frame_map: dict[str, list[Path]]) -> None:
    manifest = {
        "version": 1,
        "engine": "OpenBOR",
        "model": "black_dave",
        "status": "engine_ready_authored_pose_package",
        "source": {
            "metadata": "content/characters/black_dave/sprites/black_dave_full_library_v1.json",
            "atlas": "content/characters/black_dave/sprites/black_dave_full_library_v1.png",
            "atlas_sha256": sha256(ATLAS_PATH),
        },
        "source_canvas": metadata["cell_size"],
        "canvas": [192, 160],
        "offset": [96, 156],
        "pose_count": sum(len(frames) for frames in frame_map.values()),
        "clip_count": len(frame_map),
        "clips": {clip: {"frames": [str(path.relative_to(OUT)).replace("\\", "/") for path in frames], "delay_cs": 8} for clip, frames in frame_map.items()},
        "environment_grade": metadata["environment_grade"],
        "combat_routes": "data/chars/black_dave/black_dave_combat_routes.json",
        "native_animation_bindings": {
            f"freespecial{step}": [
                f"black_dave_v2_regular_{step:02d}",
                f"black_dave_v2_kick_{step:02d}",
                f"black_dave_v2_power_{step:02d}",
            ] for step in range(1, 8)
        },
    }
    (OUT / "black_dave_openbor_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text(
        "# Black Dave OpenBOR model\n\n"
        "Generated from the approved rooted whole-cel library. Keep `black_dave_full_library_v1.json` and its source atlas authoritative; regenerate frames with `tools/Build-OpenBOR-Black-Dave.py`.\n\n"
        f"Authored frames: {manifest['pose_count']}\n"
        f"Animations: {manifest['clip_count']}\n"
        f"Canvas/root: {manifest['canvas']} / {manifest['offset']}\n"
        "Grade: cool_underpass_dusk_v1\n",
        encoding="utf-8",
    )


def write_combat_routes(metadata: dict, frame_map: dict[str, list[Path]]) -> None:
    source_path = CONTENT / "metadata/black_dave_v2_routes.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    route_map = source.get("routes", {})
    routes = []
    for name, steps in route_map.items():
        mapped_steps = []
        for step in steps:
            mapped = dict(step)
            mapped["native_animation"] = f"freespecial{len(mapped_steps) + 1}"
            mapped_steps.append(mapped)
        routes.append({"id": name, "steps": mapped_steps})
    for route in routes:
        for step in route["steps"]:
            clip = step.get("clip_id")
            if clip not in frame_map:
                raise ValueError(f"combat route references missing authored clip: {clip}")
    payload = {
        "version": 1,
        "engine": "OpenBOR",
        "model": "black_dave",
        "source": "content/characters/black_dave/metadata/black_dave_v2_routes.json",
        "routes": routes,
        "registered_authored_clips": sorted(frame_map),
        "underpass_grade": "cool_underpass_dusk_v1",
    }
    (OUT / "black_dave_combat_routes.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def copy_underpass_package() -> None:
    source_root = ROOT / "content/setpieces/underpass_i8/art"
    LEVEL_ART.mkdir(parents=True, exist_ok=True)
    for name in ("main.png", "far.png", "near.png", "haze.png", "haze_tile.png"):
        source = Image.open(source_root / name).convert("RGBA")
        indexed_sprite(source, build_master_palette(source)).save(LEVEL_ART / name, optimize=False)
    source_manifest = json.loads((source_root / "manifest.json").read_text(encoding="utf-8"))
    local_manifest = {
        **source_manifest,
        "engine": "OpenBOR",
        "runtime_assets": {name: f"data/levels/i8_underpass/art/{name}" for name in ("main.png", "far.png", "near.png", "haze.png", "haze_tile.png")},
        "source_manifest": "content/setpieces/underpass_i8/art/manifest.json",
    }
    (ROOT / "openbor/data/levels/i8_underpass/underpass_manifest.json").write_text(json.dumps(local_manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    metadata = json.loads(META_PATH.read_text(encoding="utf-8"))
    if metadata.get("status") != "production_full_library" or int(metadata.get("pose_count", 0)) < 220:
        raise SystemExit("Black Dave source library is below the production pose floor")
    frame_map = build_frames(metadata)
    background = ROOT / "content/setpieces/underpass_i8/art/main.png"
    level_background = ROOT / "openbor/data/levels/i8_underpass/background.png"
    level_background.parent.mkdir(parents=True, exist_ok=True)
    background_image = Image.open(background).convert("RGBA")
    indexed_sprite(background_image, build_master_palette(background_image)).save(level_background, optimize=False)
    copy_underpass_package()
    write_model(metadata, frame_map)
    write_combat_routes(metadata, frame_map)
    write_manifests(metadata, frame_map)
    print(f"OpenBOR Black Dave package: {sum(map(len, frame_map.values()))} frames / {len(frame_map)} clips")


if __name__ == "__main__":
    main()
