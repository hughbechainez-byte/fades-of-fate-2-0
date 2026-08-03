"""Contracts for Black Dave's reference-retargeted twelve-pose walk."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSE_DATA = PROJECT_ROOT / "data" / "dave_walk_reference_poses.json"
WALK_STRIP = PROJECT_ROOT / "assets" / "sprites" / "black_dave_walk_12.png"
FIST_DATA = PROJECT_ROOT / "assets" / "sprites" / "black_dave_fist_anchors.json"


def _pixels(image: Image.Image):
    getter = getattr(image, "get_flattened_data", None)
    return getter() if getter is not None else image.getdata()


class DaveWalkRetargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pose_data = json.loads(POSE_DATA.read_text(encoding="utf-8"))
        self.poses = self.pose_data["poses"]

    def test_pose_table_preserves_reference_cadence_and_full_landmarks(self) -> None:
        self.assertEqual(self.pose_data["pose_count"], 12)
        self.assertEqual(self.pose_data["loop_duration_ms"], 960)
        self.assertEqual([pose["duration_ms"] for pose in self.poses], [80] * 12)
        self.assertEqual(
            [pose["reference_source_frame"] for pose in self.poses],
            list(range(0, 24, 2)),
        )
        required = set(self.pose_data["required_landmarks"])
        self.assertTrue(
            all(set(pose["landmarks_px"]) == required for pose in self.poses)
        )
        self.assertEqual(
            [pose["support_foot"] for pose in self.poses],
            ["left"] * 6 + ["right"] * 6,
        )

    def test_counter_motion_pelvis_arcs_and_world_foot_lock(self) -> None:
        for side in ("left", "right"):
            hand_x = [pose["landmarks_px"][f"{side}_hand"][0] for pose in self.poses]
            self.assertGreaterEqual(max(hand_x) - min(hand_x), 36)

        pelvis_y = [pose["landmarks_px"]["pelvis"][1] for pose in self.poses]
        self.assertEqual(pelvis_y[:6], pelvis_y[6:])
        self.assertGreaterEqual(max(pelvis_y[:6]) - min(pelvis_y[:6]), 8)
        self.assertEqual(pelvis_y[1], max(pelvis_y[:6]))
        self.assertEqual(pelvis_y[4], min(pelvis_y[:6]))

        contact_world: dict[str, list[float]] = {"left": [], "right": []}
        for pose in self.poses:
            side = pose["support_foot"]
            x = pose["landmarks_px"][pose["contact_landmark"]][0]
            contact_world[side].append(pose["root_distance_px"] + x - 64)
        self.assertLessEqual(
            max(max(values) - min(values) for values in contact_world.values()),
            1.0,
        )

    def test_installed_strip_is_sharp_unique_grounded_and_palette_locked(self) -> None:
        strip = Image.open(WALK_STRIP).convert("RGBA")
        self.assertEqual(strip.size, (128 * 12, 128))
        frames = [strip.crop((index * 128, 0, (index + 1) * 128, 128)) for index in range(12)]
        signatures = {hashlib.sha256(frame.tobytes()).hexdigest() for frame in frames}
        self.assertEqual(len(signatures), 12)
        self.assertEqual(
            {frame.getbbox()[3] for frame in frames if frame.getbbox() is not None},
            {127},
        )
        colors = {
            pixel
            for frame in frames
            for pixel in _pixels(frame)
            if pixel[3] >= 128
        }
        self.assertLessEqual(len(colors), 40)
        self.assertFalse(
            any(0 < pixel[3] < 255 for frame in frames for pixel in _pixels(frame))
        )

    def test_walk_fist_metadata_uses_the_same_retarget_landmarks(self) -> None:
        metadata = json.loads(FIST_DATA.read_text(encoding="utf-8"))["states"]["walk"]
        self.assertEqual(len(metadata), 12)
        for index, (entry, pose) in enumerate(zip(metadata, self.poses, strict=True)):
            self.assertEqual(entry["source"], index)
            self.assertEqual(entry["rear"], pose["landmarks_px"]["left_hand"])
            self.assertEqual(entry["lead"], pose["landmarks_px"]["right_hand"])


if __name__ == "__main__":
    unittest.main()
