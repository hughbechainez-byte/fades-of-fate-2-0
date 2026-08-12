from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PIL import Image

from src.black_dave_preview import BlackDavePreviewLayer
from src.playable_animation_v2 import PlayableAnimationV2Runtime


ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = ROOT / "assets/sprites/black_dave_preview_metadata_v1.json"
SOURCE_PATH = ROOT / "art_source/black_dave/preview/black_dave_preview_pose_board_v1.png"
ATLAS_PATH = ROOT / "assets/sprites/black_dave_preview_atlas_v1.png"
SPEC_PATH = ROOT / "data/playable_character_animation_v2.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BlackDavePreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))
        cls.metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_preview_is_new_hard_alpha_rooted_art_with_one_fixed_bake(self) -> None:
        self.assertEqual(self.metadata["status"], "review_preview")
        self.assertEqual(self.metadata["actor"], "black_dave")
        self.assertEqual(self.metadata["root"], [112, 156])
        self.assertEqual(self.metadata["columns"], 8)
        self.assertEqual(self.metadata["source_sha256"], _sha256(SOURCE_PATH))
        self.assertEqual(self.metadata["atlas_sha256"], _sha256(ATLAS_PATH))
        atlas = Image.open(ATLAS_PATH).convert("RGBA")
        self.assertEqual(atlas.size, (224 * 8, 160))
        self.assertTrue(set(atlas.getchannel("A").get_flattened_data()) <= {0, 255})
        scales = {
            pose["normalization"]["uniform_bake_scale"]
            for pose in self.metadata["poses"]
        }
        self.assertEqual(len(scales), 1)
        self.assertFalse(any(pose["normalization"]["pose_specific_fit"] for pose in self.metadata["poses"]))

    def test_preview_is_declared_as_a_flag_gated_review_layer(self) -> None:
        spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        preview = spec["characters"]["black_dave"]["review_preview"]
        self.assertEqual(preview["enabled_by"], "FADES_BLACK_DAVE_PREVIEW")
        self.assertEqual(preview["metadata_path"], "assets/sprites/black_dave_preview_metadata_v1.json")
        self.assertIn("before_full_pose_library", preview["purpose"])

    def test_preview_pose_cells_are_complete_distinct_and_grounded(self) -> None:
        atlas = Image.open(ATLAS_PATH).convert("RGBA")
        silhouettes: set[bytes] = set()
        for index, pose in enumerate(self.metadata["poses"]):
            with self.subTest(pose=pose["id"]):
                cell = atlas.crop((index * 224, 0, (index + 1) * 224, 160))
                bounds = cell.getbbox()
                self.assertIsNotNone(bounds)
                assert bounds is not None
                self.assertGreater(bounds[0], 0)
                self.assertGreater(bounds[1], 0)
                self.assertLess(bounds[2], 224)
                self.assertEqual(bounds[3], 156)
                self.assertEqual(pose["body_bounds"], list(bounds))
                self.assertEqual(pose["root"], [112, 156])
                silhouette = cell.getchannel("A").crop(bounds).tobytes()
                self.assertNotIn(silhouette, silhouettes)
                silhouettes.add(silhouette)

    def test_preview_sequences_use_only_registered_whole_cels(self) -> None:
        layer = BlackDavePreviewLayer(METADATA_PATH)
        for clip_id, clip in self.metadata["clips"].items():
            with self.subTest(clip=clip_id):
                self.assertTrue(clip["poses"])
                self.assertEqual(len(clip["poses"]), len(set(clip["poses"])))
                for tick in range(len(clip["poses"]) * 3):
                    sample = layer.sample(clip_id, tick)
                    self.assertEqual(sample.root, (112, 156))
                    self.assertTrue(sample.body_surface.get_bounding_rect(min_alpha=1).width)

    def test_runtime_uses_preview_only_when_explicitly_enabled(self) -> None:
        with patch.dict(os.environ, {"FADES_BLACK_DAVE_PREVIEW": "1"}, clear=False):
            preview_runtime = PlayableAnimationV2Runtime(SPEC_PATH)
            preview_sample = preview_runtime.sample("black_dave", "walk", 1)
            self.assertTrue(preview_runtime.black_dave_preview is not None)
            self.assertEqual(preview_sample.clip_id, "black_dave_preview_walk")
        with patch.dict(os.environ, {"FADES_BLACK_DAVE_PREVIEW": ""}, clear=False):
            default_runtime = PlayableAnimationV2Runtime(SPEC_PATH)
            default_sample = default_runtime.sample("black_dave", "walk", 1)
            self.assertIsNone(default_runtime.black_dave_preview)
            self.assertNotEqual(default_sample.clip_id, "black_dave_preview_walk")

    def test_pose_budget_explicitly_stops_before_full_hero_library(self) -> None:
        budget = self.metadata["pose_budget"]
        self.assertEqual(budget["class"], "playable_hero")
        self.assertEqual(budget["preview_meaningful_drawings"], 8)
        self.assertEqual(budget["minimum_meaningful_drawings"], 120)
        self.assertEqual(budget["floor_status"], "deferred_pending_review")


if __name__ == "__main__":
    unittest.main()
