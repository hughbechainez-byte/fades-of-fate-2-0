"""Contracts for Black Dave's reference-retargeted twelve-pose walk."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from PIL import Image

from src.character_animation import (
    CharacterAnimationSkin,
    CharacterArtModel,
    CharacterCleanupRules,
    CharacterLayerRules,
    CharacterProportionProfile,
    GenericMotionClip,
    load_character_animation_skin,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSE_DATA = PROJECT_ROOT / "data" / "dave_walk_reference_poses.json"
ART_MODEL = PROJECT_ROOT / "data" / "dave_character_art_model.json"
WALK_STRIP = PROJECT_ROOT / "assets" / "sprites" / "black_dave_walk_identity_v1.png"
FIST_DATA = PROJECT_ROOT / "assets" / "sprites" / "black_dave_fist_anchors.json"
APPROVED_MOTION_FINGERPRINT = "6147e92f064bac2204edfe2972e507a6477ec74e9a252487b0461f86a172fa4c"
APPROVED_LOWER_BODY_FINGERPRINT = "945b5c007f9d094a4f29b3802c66e68a8ed10b59f8e5d57eb0f006adbf8f4702"
LOWER_BODY_LANDMARKS = (
    "pelvis",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_toe",
    "right_toe",
)


def _pixels(image: Image.Image):
    getter = getattr(image, "get_flattened_data", None)
    return getter() if getter is not None else image.getdata()


def _alpha_component_sizes(frame: Image.Image) -> list[int]:
    alpha = frame.getchannel("A")
    active = {
        (x, y)
        for y in range(frame.height)
        for x in range(frame.width)
        if alpha.getpixel((x, y)) >= 128
    }
    sizes: list[int] = []
    while active:
        stack = [active.pop()]
        size = 0
        while stack:
            x, y = stack.pop()
            size += 1
            for offset_x in (-1, 0, 1):
                for offset_y in (-1, 0, 1):
                    if offset_x == 0 and offset_y == 0:
                        continue
                    neighbor = (x + offset_x, y + offset_y)
                    if neighbor in active:
                        active.remove(neighbor)
                        stack.append(neighbor)
        sizes.append(size)
    return sorted(sizes, reverse=True)


class DaveWalkRetargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pose_data = json.loads(POSE_DATA.read_text(encoding="utf-8"))
        self.poses = self.pose_data["poses"]
        self.model = load_character_animation_skin(ART_MODEL)

    def test_character_specific_art_model_wraps_the_reusable_motion_clip(self) -> None:
        self.assertIsInstance(self.model, CharacterAnimationSkin)
        self.assertIsInstance(self.model.motion, GenericMotionClip)
        self.assertIsInstance(self.model.proportions, CharacterProportionProfile)
        self.assertIsInstance(self.model.art, CharacterArtModel)
        self.assertIsInstance(self.model.layers, CharacterLayerRules)
        self.assertIsInstance(self.model.cleanup, CharacterCleanupRules)
        self.assertEqual(self.model.character, "black_dave")
        self.assertEqual(self.model.motion.fingerprint_sha256, APPROVED_MOTION_FINGERPRINT)
        self.assertEqual(self.model.layers.mode, "complete_authored_cel_per_phase")
        self.assertEqual(self.model.layers.phase_source_indices, tuple(range(12)))
        self.assertEqual(len(self.model.art.master_palette), 192)
        self.assertIn("generic_ribbon_silhouette_reconstruction", self.model.cleanup.forbidden_methods)

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

    def test_approved_skeleton_and_timing_fingerprint_is_frozen(self) -> None:
        fingerprint = hashlib.sha256(
            json.dumps(
                self.pose_data,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(fingerprint, APPROVED_MOTION_FINGERPRINT)

    def test_compact_gait_below_the_pelvis_is_byte_for_byte_preserved(self) -> None:
        lower_body = [
            {
                "index": pose["index"],
                "duration_ms": pose["duration_ms"],
                "root_distance_px": pose["root_distance_px"],
                "support_foot": pose["support_foot"],
                "contact_landmark": pose["contact_landmark"],
                "foot_contact": pose["foot_contact"],
                "pelvis_height_px": pose["pelvis_height_px"],
                "landmarks_px": {
                    name: pose["landmarks_px"][name]
                    for name in LOWER_BODY_LANDMARKS
                },
            }
            for pose in self.poses
        ]
        fingerprint = hashlib.sha256(
            json.dumps(lower_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(fingerprint, APPROVED_LOWER_BODY_FINGERPRINT)

    def test_counter_motion_pelvis_arcs_and_world_foot_lock(self) -> None:
        for side in ("left", "right"):
            hand_x = [pose["landmarks_px"][f"{side}_hand"][0] for pose in self.poses]
            self.assertGreaterEqual(max(hand_x) - min(hand_x), 24)

        foot_spacing = []
        for pose in self.poses:
            points = pose["landmarks_px"]
            left_center = (points["left_heel"][0] + points["left_toe"][0]) / 2
            right_center = (points["right_heel"][0] + points["right_toe"][0]) / 2
            foot_spacing.append(abs(left_center - right_center))
        self.assertLessEqual(max(foot_spacing), 52.0)

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
        self.assertEqual(len(colors), len(self.model.art.master_palette))
        self.assertTrue(colors.issubset(set(self.model.art.master_palette)))
        self.assertFalse(
            any(0 < pixel[3] < 255 for frame in frames for pixel in _pixels(frame))
        )

    def test_full_authored_frames_have_one_exact_connected_anatomy(self) -> None:
        strip = Image.open(WALK_STRIP).convert("RGBA")
        frames = [strip.crop((index * 128, 0, (index + 1) * 128, 128)) for index in range(12)]
        expected_frames = self.model.identity_validation["expected_frames"]
        for index, (frame, expected) in enumerate(zip(frames, expected_frames, strict=True), start=1):
            with self.subTest(frame=index):
                self.assertEqual(
                    len(_alpha_component_sizes(frame)),
                    1,
                    "the original full cel must remain one coherent silhouette",
                )
                alpha = frame.getchannel("A")
                self.assertEqual(
                    hashlib.sha256(alpha.tobytes()).hexdigest(),
                    expected["registered_alpha_sha256"],
                )
                self.assertEqual(frame.getbbox(), tuple(expected["registered_bbox"]))
                self.assertEqual(
                    sum(value >= 128 for value in _pixels(alpha)),
                    expected["opaque_pixels"],
                )

    def test_authored_fists_and_limbs_follow_the_dave_profile(self) -> None:
        strip = Image.open(WALK_STRIP).convert("RGBA")
        frames = [strip.crop((index * 128, 0, (index + 1) * 128, 128)) for index in range(12)]
        anchors = self.model.art.walk_source["fist_anchors_after_registration"]
        measurements = self.model.proportions.measurements_px
        self.assertGreaterEqual(measurements["upper_arm_thickness"], 13)
        self.assertGreaterEqual(measurements["forearm_thickness"], 11)
        self.assertGreaterEqual(measurements["hand_width"], 11)
        for index, (frame, phase) in enumerate(zip(frames, anchors, strict=True), start=1):
            for side in ("rear", "lead"):
                hand_x, hand_y = phase[side]
                with self.subTest(frame=index, side=side):
                    samples = [
                        frame.getpixel((x, y))
                        for y in range(max(0, hand_y - 5), min(128, hand_y + 6))
                        for x in range(max(0, hand_x - 5), min(128, hand_x + 6))
                    ]
                    self.assertGreaterEqual(sum(pixel[3] >= 128 for pixel in samples), 24)
                    self.assertGreaterEqual(
                        sum(
                            pixel[3] >= 128
                            and pixel[0] > pixel[1] * 1.15
                            and pixel[1] > pixel[2]
                            for pixel in samples
                        ),
                        6,
                    )

    def test_walk_retains_daves_combat_physique_and_authored_texture(self) -> None:
        strip = Image.open(WALK_STRIP).convert("RGBA")
        frames = [strip.crop((index * 128, 0, (index + 1) * 128, 128)) for index in range(12)]
        measurements = self.model.proportions.measurements_px
        self.assertEqual(measurements["total_standing_height"], 125)
        self.assertEqual(measurements["head_width"], 26)
        self.assertEqual(measurements["head_height"], 31)
        self.assertEqual(measurements["shoulder_width"], 36)
        self.assertEqual(measurements["chest_width"], 31)
        self.assertEqual(measurements["waist_width"], 25)
        self.assertEqual(measurements["pelvis_width"], 31)
        bounds = [frame.getbbox() for frame in frames]
        self.assertTrue(all(bound is not None for bound in bounds))
        self.assertGreaterEqual(
            sum(bound[2] - bound[0] for bound in bounds if bound is not None) / len(bounds),
            69.0,
        )
        self.assertGreaterEqual(
            sum(bound[3] - bound[1] for bound in bounds if bound is not None) / len(bounds),
            123.0,
        )
        visible_colors = {
            pixel
            for frame in frames
            for pixel in _pixels(frame)
            if pixel[3] >= 128
        }
        self.assertEqual(
            visible_colors,
            set(self.model.art.master_palette),
            "Dave's approved skin, tank, denim, metal, and shoe ramps drifted",
        )

    def test_walk_fist_metadata_uses_the_approved_full_cel_hands(self) -> None:
        metadata = json.loads(FIST_DATA.read_text(encoding="utf-8"))["states"]["walk"]
        anchors = self.model.art.walk_source["fist_anchors_after_registration"]
        self.assertEqual(len(metadata), 12)
        for index, (entry, expected) in enumerate(zip(metadata, anchors, strict=True)):
            self.assertEqual(entry["source"], index)
            self.assertEqual(entry["rear"], expected["rear"])
            self.assertEqual(entry["lead"], expected["lead"])


if __name__ == "__main__":
    unittest.main()
