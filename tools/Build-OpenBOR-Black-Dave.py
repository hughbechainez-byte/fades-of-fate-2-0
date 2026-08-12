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


def build_frames(metadata: dict) -> dict[str, list[Path]]:
    atlas = Image.open(ATLAS_PATH).convert("RGBA")
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
            cell = atlas.crop((index * cell_width, row * cell_height, (index + 1) * cell_width, (row + 1) * cell_height))
            cell.save(path, optimize=False)
            frames.append(path)
        frame_map[clip_id] = frames
    return frame_map


def write_model(metadata: dict, frame_map: dict[str, list[Path]]) -> None:
    aliases = {
        "idle": "idle",
        "walk_start": "walk_start",
        "walk": "walk",
        "walk_stop": "walk_stop",
        "walk_reverse": "walk_reverse",
        "jump_takeoff": "jump_takeoff",
        "jump_rise": "jump_rise",
        "jump_apex": "jump_apex",
        "jump_fall": "jump_fall",
        "jump_land": "jump_land",
        "dodge": "dodge",
        "hurt": "hurt",
        "down": "down",
        "recovery": "recovery",
        "ranged": "ranged",
        "super": "super",
        "pet": "pet",
        "air_punch": "air_punch",
        "air_kick": "air_kick",
    }
    lines = [
        "name black_dave",
        "type player",
        "health 100",
        "mp 100",
        "speed 4",
        "jumpheight 5",
        "subject_to_gravity 1",
        "shadow 1",
        "shadow_coords 0 0 0",
        "load black_dave_attack_fx data/chars/black_dave/black_dave_attack_fx.txt",
        "",
    ]
    registered: set[str] = set()
    for clip_id, animation_name in aliases.items():
        if clip_id not in frame_map:
            raise ValueError(f"required OpenBOR animation is missing: {clip_id}")
        clip = metadata["clips"][clip_id]
        lines += [f"anim {animation_name}", "    offset 112 156", "    delay 8"]
        for frame in frame_map[clip_id]:
            lines.append(f"    frame data/chars/black_dave/sprites/{frame.name}")
        if clip_id in {"walk", "idle"}:
            lines += ["    loop 1"]
        lines += [""]
        registered.add(animation_name)
    # Register every authored source clip as a named OpenBOR animation too.
    # The conventional aliases above provide engine-native action IDs; these
    # names preserve the complete source library for review and route binding.
    for clip_id in frame_map:
        animation_name = safe_id(clip_id).lower()
        if animation_name in registered:
            continue
        lines += [f"anim {animation_name}", "    offset 112 156", "    delay 8"]
        for frame in frame_map[clip_id]:
            lines.append(f"    frame data/chars/black_dave/sprites/{frame.name}")
        lines += [""]
        registered.add(animation_name)
    attack_map = {
        "black_dave_v2_regular_01": ("attack1", "fists_close_01", 12, 28, 38, 16),
        "black_dave_v2_regular_02": ("attack2", "fists_close_02", 14, 30, 42, 16),
        "black_dave_v2_regular_03": ("attack3", "uppercut_01", 16, 32, 48, 22),
        "black_dave_v2_kick_01": ("attack4", "kick_low_01", 14, 34, 52, 18),
        "black_dave_v2_kick_02": ("attack5", "kick_low_02", 14, 36, 56, 18),
        "black_dave_v2_power_01": ("special", "power_01", 20, 36, 62, 26),
    }
    for clip_id, (animation_name, hit_id, damage, x, width, height) in attack_map.items():
        clip = metadata["clips"].get(clip_id)
        if clip is None:
            raise ValueError(f"attack source missing: {clip_id}")
        lines += [f"anim {animation_name}", "    offset 112 156", "    delay 8", f"    attack {x} 108 {width} {height} {damage} 0 0"]
        for frame in frame_map[clip_id]:
            lines.append(f"    frame data/chars/black_dave/sprites/{frame.name}")
        lines += [""]
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
        "canvas": metadata["cell_size"],
        "offset": metadata["root"],
        "pose_count": sum(len(frames) for frames in frame_map.values()),
        "clip_count": len(frame_map),
        "clips": {clip: {"frames": [str(path.relative_to(OUT)).replace("\\", "/") for path in frames], "delay_cs": 8} for clip, frames in frame_map.items()},
        "environment_grade": metadata["environment_grade"],
        "combat_routes": "data/chars/black_dave/black_dave_combat_routes.json",
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
    routes = [{"id": name, "steps": steps} for name, steps in route_map.items()]
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
        shutil.copyfile(source_root / name, LEVEL_ART / name)
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
    shutil.copyfile(background, level_background)
    copy_underpass_package()
    write_model(metadata, frame_map)
    write_combat_routes(metadata, frame_map)
    write_manifests(metadata, frame_map)
    print(f"OpenBOR Black Dave package: {sum(map(len, frame_map.values()))} frames / {len(frame_map)} clips")


if __name__ == "__main__":
    main()
