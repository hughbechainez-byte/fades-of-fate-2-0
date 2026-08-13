"""Validate the OpenBOR Black Dave package without requiring the engine binary."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "openbor/data/chars/black_dave"
MANIFEST = MODEL / "black_dave_openbor_manifest.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine"] == "OpenBOR"
    assert manifest["status"] == "engine_ready_authored_pose_package"
    assert manifest["pose_count"] >= 220
    assert manifest["source_canvas"] == [224, 160]
    assert manifest["canvas"] == [192, 160]
    assert manifest["offset"] == [96, 156]
    assert len(manifest["clips"]) >= 40
    required = {"idle", "walk", "attack1", "attack2", "attack3", "attack4", "freespecial1", "freespecial2", "pain", "fall", "rise"}
    model_text = (MODEL / "black_dave.txt").read_text(encoding="utf-8")
    model_animations = {line.split(maxsplit=1)[1] for line in model_text.splitlines() if line.startswith("anim ")}
    assert "name BlackDave" in model_text
    assert required <= {line.split(maxsplit=1)[1] for line in model_text.splitlines() if line.startswith("anim ")}
    assert {
        "guard",
        "walk_start",
        "walk_stop",
        "walk_reverse",
        "jump_takeoff",
        "jump_rise",
        "jump_apex",
        "jump_fall",
        "jump_land",
        "dodge",
        "hurt",
        "down",
        "recovery",
        "ranged",
        "super",
        "pet",
        "air_punch",
        "air_kick",
    } <= set(manifest["clips"])
    registered_names = {line.split(maxsplit=1)[1] for line in model_text.splitlines() if line.startswith("anim ")}
    assert {"idle", "walk", "pain", "fall", "rise", "attack1", "attack2", "attack3", "attack4", "freespecial1"} <= registered_names
    routes = json.loads((MODEL / "black_dave_combat_routes.json").read_text(encoding="utf-8"))
    assert len(routes["routes"]) == 3
    assert sum(len(route["steps"]) for route in routes["routes"]) == 21
    assert all(step["clip_id"] in manifest["clips"] for route in routes["routes"] for step in route["steps"])
    bindings = manifest["native_animation_bindings"]
    assert len(bindings) == 7
    assert all(step["native_animation"] in bindings and step["clip_id"] in bindings[step["native_animation"]] for route in routes["routes"] for step in route["steps"])
    assert all(f"anim {native}" in model_text for native in bindings)
    level_text = (ROOT / "openbor/data/levels/i8_underpass.txt").read_text(encoding="utf-8")
    assert "panel data/levels/i8_underpass/panels/" in level_text
    frame_count = 0
    for clip, record in manifest["clips"].items():
        frames = record["frames"]
        assert len(frames) == 5, clip
        for relative in frames:
            source_image = Image.open(MODEL / relative)
            assert source_image.mode == "P", (clip, relative, source_image.mode)
            assert source_image.info.get("transparency") == 0, (clip, relative)
            image = source_image.convert("RGBA")
            assert image.size == (192, 160), (clip, relative, image.size)
            assert set(image.getchannel("A").get_flattened_data()) <= {0, 255}, (clip, relative)
            assert image.getbbox() is not None, (clip, relative)
            frame_count += 1
    assert frame_count == manifest["pose_count"]
    assert (ROOT / "openbor/data/levels/i8_underpass/background.png").is_file()
    local_setpiece = json.loads((ROOT / "openbor/data/levels/i8_underpass/underpass_manifest.json").read_text(encoding="utf-8"))
    assert local_setpiece["engine"] == "OpenBOR"
    assert all((ROOT / "openbor" / relative).is_file() for relative in local_setpiece["runtime_assets"].values())
    print(json.dumps({"status": "pass", "engine": "OpenBOR", "clips": len(manifest["clips"]), "authored_frames": frame_count}, indent=2))


if __name__ == "__main__":
    main()
