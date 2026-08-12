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
    assert manifest["canvas"] == [224, 160]
    assert manifest["offset"] == [112, 156]
    assert len(manifest["clips"]) >= 40
    required = {"idle", "walk", "walk_start", "walk_stop", "jump_rise", "hurt", "down", "recovery", "attack1", "attack2", "attack3", "attack4", "attack5", "special"}
    model_text = (MODEL / "black_dave.txt").read_text(encoding="utf-8")
    assert required <= {line.split(maxsplit=1)[1] for line in model_text.splitlines() if line.startswith("anim ")}
    authored_names = {clip.replace("-", "_") for clip in manifest["clips"]}
    registered_names = {line.split(maxsplit=1)[1] for line in model_text.splitlines() if line.startswith("anim ")}
    assert authored_names <= registered_names
    routes = json.loads((MODEL / "black_dave_combat_routes.json").read_text(encoding="utf-8"))
    assert len(routes["routes"]) == 3
    assert sum(len(route["steps"]) for route in routes["routes"]) == 21
    assert all(step["clip_id"] in manifest["clips"] for route in routes["routes"] for step in route["steps"])
    frame_count = 0
    for clip, record in manifest["clips"].items():
        frames = record["frames"]
        assert len(frames) == 5, clip
        for relative in frames:
            image = Image.open(MODEL / relative).convert("RGBA")
            assert image.size == (224, 160), (clip, relative, image.size)
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
