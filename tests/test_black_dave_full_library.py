"""Contract tests for the production Black Dave library."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "assets/sprites/black_dave_full_library_v1.json"
ATLAS = ROOT / "assets/sprites/black_dave_full_library_v1.png"


class BlackDaveFullLibraryTests(unittest.TestCase):
    def test_library_clears_normal_playable_hero_floor(self) -> None:
        metadata = json.loads(META.read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "production_full_library")
        self.assertGreaterEqual(metadata["pose_count"], 220)
        self.assertGreaterEqual(metadata["pose_budget"]["authored"], metadata["pose_budget"]["normal"])

    def test_library_is_fixed_rooted_hard_alpha_and_has_distinct_phases(self) -> None:
        metadata = json.loads(META.read_text(encoding="utf-8"))
        atlas = Image.open(ATLAS).convert("RGBA")
        self.assertEqual(metadata["cell_size"], [224, 160])
        self.assertEqual(metadata["root"], [112, 156])
        self.assertEqual(atlas.size, (1120, 160 * len(metadata["clips"])))
        self.assertEqual(set(atlas.getchannel("A").get_flattened_data()), {0, 255})
        for clip_id, clip in metadata["clips"].items():
            silhouettes = set()
            for index, pose in enumerate(clip["poses"]):
                cell = atlas.crop((index * 224, clip["row"] * 160, (index + 1) * 224, (clip["row"] + 1) * 160))
                bounds = cell.getbbox()
                self.assertIsNotNone(bounds, clip_id)
                assert bounds is not None
                self.assertEqual(pose["body_bounds"], list(bounds), clip_id)
                self.assertEqual(pose["root"], [112, 156])
                self.assertNotIn(cell.getchannel("A").crop(bounds).tobytes(), silhouettes, clip_id)
                silhouettes.add(cell.getchannel("A").crop(bounds).tobytes())


if __name__ == "__main__":
    unittest.main()
