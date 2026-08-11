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

# These are the actual authoritative grid layouts, not merely a count of
# nonempty cells.  Regressing either of the first two layouts to a 12-column
# generic split was what created the detached Shelly/Jermaine fragments that
# the first V2 review missed.
MIGRATION_SOURCE_GRIDS = {
    "shelly": {
        "asset": "assets/sprites/shelly_animation_atlas.png",
        "columns": 16,
        "rows": 17,
        "uniform_bake_scale": 1.0,
        "incomplete_cels_rejected": [],
    },
    "jermaine": {
        "asset": "assets/sprites/jermaine_foundation_atlas.png",
        "columns": 12,
        "rows": 3,
        "uniform_bake_scale": 1.16,
        "incomplete_cels_rejected": [[2, 6]],
    },
    "white_dave": {
        "asset": "assets/sprites/white_dave_foundation_atlas.png",
        "columns": 12,
        "rows": 3,
        "uniform_bake_scale": 1.16,
        "incomplete_cels_rejected": [],
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalized_silhouette(cell: Image.Image) -> bytes:
    bbox = cell.getbbox()
    if bbox is None:
        raise AssertionError("registered body cel is empty")
    alpha = cell.crop(bbox).getchannel("A")
    return alpha.tobytes()


def _hard_alpha(cell: Image.Image) -> Image.Image:
    hardened = cell.convert("RGBA")
    hardened.putalpha(hardened.getchannel("A").point(lambda value: 255 if value >= 128 else 0))
    return hardened


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

    def test_source_hashes_and_migration_grids_prove_complete_authored_cels(self) -> None:
        """Reject a plausible-looking atlas split that is not a body-cel grid."""
        for actor, definition in self.spec["characters"].items():
            for relative, expected_hash in definition["source_inputs"].items():
                with self.subTest(actor=actor, source=relative):
                    self.assertEqual(_sha256(ROOT / relative), expected_hash)
        for actor, expected_grid in MIGRATION_SOURCE_GRIDS.items():
            definition = self.spec["characters"][actor]
            metadata = json.loads((ROOT / definition["pose_metadata_path"]).read_text(encoding="utf-8"))
            grid = metadata.get("source_grid")
            self.assertIsInstance(grid, dict)
            assert isinstance(grid, dict)
            for key, expected in expected_grid.items():
                with self.subTest(actor=actor, key=key):
                    self.assertEqual(grid.get(key), expected)
            source_path = ROOT / expected_grid["asset"]
            source = Image.open(source_path).convert("RGBA")
            columns = expected_grid["columns"]
            rows = expected_grid["rows"]
            self.assertEqual(source.size, (128 * columns, 128 * rows))
            rejected = {tuple(cel) for cel in expected_grid["incomplete_cels_rejected"]}
            for state, clip in metadata["clips"].items():
                for pose in clip["poses"]:
                    provenance = pose["source"]
                    source_row = provenance["row"]
                    source_column = provenance["column"]
                    with self.subTest(actor=actor, state=state, column=source_column):
                        self.assertEqual(provenance["state"], state)
                        self.assertIn(source_row, range(rows))
                        self.assertIn(source_column, range(columns))
                        self.assertNotIn((source_row, source_column), rejected)
                        cell = _hard_alpha(source.crop((
                            source_column * 128,
                            source_row * 128,
                            (source_column + 1) * 128,
                            (source_row + 1) * 128,
                        )))
                        bounds = cell.getbbox()
                        self.assertIsNotNone(bounds)
                        self.assertEqual(provenance["alpha_bounds"], list(bounds))
                        self.assertEqual(
                            provenance["opaque_pixels"],
                            sum(value == 255 for value in cell.getchannel("A").get_flattened_data()),
                        )
                        self.assertAlmostEqual(
                            provenance["uniform_bake_scale"],
                            expected_grid["uniform_bake_scale"],
                        )

    def test_idle_calibration_keeps_dave_at_or_above_white_daves_build(self) -> None:
        metadata_by_actor = {
            actor: json.loads((ROOT / definition["pose_metadata_path"]).read_text(encoding="utf-8"))
            for actor, definition in self.spec["characters"].items()
        }
        heights = {
            actor: [
                pose["body_bounds"][3] - pose["body_bounds"][1]
                for pose in metadata["clips"]["idle"]["poses"]
            ]
            for actor, metadata in metadata_by_actor.items()
        }
        self.assertTrue(all(132 <= height <= 138 for height in heights["black_dave"]))
        self.assertTrue(all(116 <= height <= 121 for height in heights["shelly"]))
        self.assertTrue(all(132 <= height <= 139 for height in heights["jermaine"]))
        self.assertTrue(all(height == 133 for height in heights["white_dave"]))
        self.assertGreaterEqual(
            min(heights["black_dave"]),
            max(heights["white_dave"]) - 1,
            "Black Dave may never read smaller than White Dave at shared depth",
        )

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
        route_source_sequences = [
            tuple(
                (pose["source"]["state"], pose["source"]["column"])
                for pose in metadata["clips"][clip_id]["poses"]
            )
            for route in ("regular", "kick", "power")
            for clip_id in definition["route_clips"][route]
        ]
        self.assertEqual(len(route_source_sequences), 21)
        self.assertEqual(
            len(set(route_source_sequences)),
            21,
            "each grounded V2 route step must retain its own authored pose progression",
        )

    def test_black_dave_combat_cels_keep_his_normal_build_in_every_phase(self) -> None:
        """A combo may stretch or crouch, but never swap in a smaller Dave."""
        definition = self.spec["characters"]["black_dave"]
        metadata = json.loads((ROOT / definition["pose_metadata_path"]).read_text(encoding="utf-8"))
        combat_clips = {
            *definition["route_clips"]["regular"],
            *definition["route_clips"]["kick"],
            *definition["route_clips"]["power"],
            "air_punch",
            "air_kick",
        }
        for clip_id in sorted(combat_clips):
            with self.subTest(clip_id=clip_id):
                clip = metadata["clips"][clip_id]
                for pose in clip["poses"]:
                    bounds = pose["body_bounds"]
                    self.assertEqual(bounds[3] - bounds[1], 134)
                    normalization = pose["source"]["normalization"]
                    self.assertEqual(normalization["method"], "alpha_bounds_nearest_neighbor")
                    self.assertEqual(normalization["body_height"], 134)

    def test_grounded_route_cels_keep_the_opaque_sole_at_the_declared_root(self) -> None:
        """Roots are useful only when the rendered planted body honors them."""
        definition = self.spec["characters"]["black_dave"]
        metadata = json.loads((ROOT / definition["pose_metadata_path"]).read_text(encoding="utf-8"))
        root_y = definition["world_root"][1]
        grounded_clips = {
            "idle",
            "guard",
            "walk_start",
            "walk",
            "walk_stop",
            "walk_reverse",
            "dodge",
            "hurt",
            "ranged",
            "super",
            "pet",
            *definition["route_clips"]["regular"],
            *definition["route_clips"]["kick"],
            *definition["route_clips"]["power"],
        }
        for clip_id in sorted(grounded_clips):
            for pose in metadata["clips"][clip_id]["poses"]:
                with self.subTest(clip_id=clip_id, pose=pose["source"]["column"]):
                    self.assertEqual(pose["root"][1], root_y)
                    self.assertLessEqual(
                        abs(root_y - pose["body_bounds"][3]),
                        1,
                        "a grounded body may not drift farther than one logical pixel from its root",
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
