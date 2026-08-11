"""Render-contract tests for the lead-authored playable Animation V2 atlases."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "data" / "playable_character_animation_v2.json"
LEGACY_DAVE_EFFECT_CELS = frozenset({
    (2, 2), (2, 6),
    (3, 2), (3, 5),
    (4, 1), (4, 5),
    (5, 1), (5, 2), (5, 4), (5, 5),
    (6, 3), (6, 5),
    (7, 4),
    (11, 4), (11, 5),
    (12, 2),
})
DAVE_STATE_ROWS = {
    state: row
    for row, state in enumerate((
        "idle", "walk", "attack_1", "attack_2", "attack_3", "attack_4", "heavy",
        "ranged", "dodge", "hurt", "down", "super", "air_attack", "jump", "pet",
        "refill", "pants",
    ))
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_silhouette(cell: Image.Image) -> bytes:
    bbox = cell.getbbox()
    if bbox is None:
        raise AssertionError("registered body cel is empty")
    alpha = cell.crop(bbox).getchannel("A")
    return alpha.tobytes()


class PlayableAnimationV2AssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))

    def test_all_declared_actor_assets_are_rooted_hard_alpha_and_complete(self) -> None:
        for actor, definition in self.spec["characters"].items():
            with self.subTest(actor=actor):
                atlas_path = ROOT / definition["atlas_path"]
                metadata_path = ROOT / definition["pose_metadata_path"]
                self.assertTrue(atlas_path.is_file())
                self.assertTrue(metadata_path.is_file())
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["actor"], actor)
                self.assertEqual(metadata["cell_size"], definition["actor_canvas"])
                self.assertEqual(metadata["root"], definition["world_root"])
                self.assertEqual(metadata["columns"], 5)
                image = Image.open(atlas_path).convert("RGBA")
                cell_width, cell_height = definition["actor_canvas"]
                self.assertEqual(image.width, cell_width * 5)
                self.assertEqual(image.height, cell_height * len(metadata["clips"]))
                self.assertTrue(set(image.getchannel("A").get_flattened_data()) <= {0, 255})
                for clip_id, clip in metadata["clips"].items():
                    self.assertEqual(len(clip["poses"]), 5, clip_id)
                    self.assertEqual(clip["phases"], ["anticipation", "launch", "contact", "follow_through", "recovery"])
                    silhouettes: set[bytes] = set()
                    for pose_index, pose in enumerate(clip["poses"]):
                        cell = image.crop((
                            pose_index * cell_width,
                            clip["row"] * cell_height,
                            (pose_index + 1) * cell_width,
                            (clip["row"] + 1) * cell_height,
                        ))
                        bounds = cell.getbbox()
                        self.assertIsNotNone(bounds, f"{actor}/{clip_id}/{pose_index}")
                        assert bounds is not None
                        self.assertNotIn(bounds[0], (0,))
                        self.assertNotIn(bounds[1], (0,))
                        self.assertNotIn(bounds[2], (cell_width,))
                        self.assertNotIn(bounds[3], (cell_height,))
                        self.assertEqual(pose["root"], definition["world_root"])
                        self.assertEqual(pose["body_bounds"], list(bounds))
                        silhouette = _normalized_silhouette(cell)
                        self.assertNotIn(silhouette, silhouettes, f"duplicate progressive body cel {actor}/{clip_id}")
                        silhouettes.add(silhouette)

    def test_black_dave_routes_bind_to_unique_registered_body_clips_without_legacy_effect_pixels(self) -> None:
        definition = self.spec["characters"]["black_dave"]
        metadata = json.loads((ROOT / definition["pose_metadata_path"]).read_text(encoding="utf-8"))
        required = set(definition["required_clips"])
        required.update(clip_id for clips in definition["route_clips"].values() for clip_id in clips)
        self.assertTrue(required <= set(metadata["clips"]))
        for clip_id, clip in metadata["clips"].items():
            for pose in clip["poses"]:
                source = pose.get("source", {})
                self.assertIn(source.get("state"), DAVE_STATE_ROWS)
                self.assertNotIn(
                    (DAVE_STATE_ROWS[source["state"]], source.get("column")),
                    LEGACY_DAVE_EFFECT_CELS,
                )

    def test_vfx_atlas_is_separate_native_hard_alpha_content(self) -> None:
        definition = self.spec["characters"]["black_dave"]
        source = ROOT / definition["vfx_source_path"]
        atlas = ROOT / definition["vfx_atlas_path"]
        manifest = ROOT / "assets/sprites/black_dave_v2_flame_vfx_manifest.json"
        self.assertTrue(source.is_file())
        self.assertTrue(atlas.is_file())
        self.assertTrue(manifest.is_file())
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(metadata["source_hashes"][definition["vfx_source_path"]], _sha256(source))
        self.assertEqual(metadata["source_hashes"][definition["vfx_atlas_path"]], _sha256(atlas))
        image = Image.open(atlas).convert("RGBA")
        self.assertEqual(metadata["cell_size"], [64, 64])
        self.assertEqual(metadata["columns"], 4)
        self.assertTrue(set(image.getchannel("A").get_flattened_data()) <= {0, 255})
        self.assertEqual(image.size, (64 * 4, 64 * len(metadata["clips"])))


if __name__ == "__main__":
    unittest.main()
