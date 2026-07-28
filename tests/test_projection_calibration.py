"""Tests for the projection contract used by Section 1 calibration tooling."""

from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.config import load_gameplay, validate_gameplay
from src.world_engine import BeatEmUpProjection, ProjectionConfig, WorldPoint


class ProjectionProfileContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load_gameplay()
        self.profiles = self.data.get("projection_profiles", {})
        if not self.profiles:
            self.profiles = self.data.get("engine", {}).get("projection_profiles", {})

    def _projection_profile(self) -> dict:
        return deepcopy(self.profiles["chapter1_oblique_v2"])

    def test_chapter1_projection_profile_is_present_and_active(self) -> None:
        projection = self.data["engine"]["projection"]
        self.assertEqual(projection.get("profile_id"), "chapter1_oblique_v2")
        self.assertIn("chapter1_oblique_v2", self.profiles)

    def test_profile_has_required_projection_contract_fields(self) -> None:
        profile = self._projection_profile()
        self.assertEqual(profile["logical_resolution"], [640, 360])
        self.assertEqual(profile["mode"], "oblique_orthographic")
        for field in ("screen_origin_x", "screen_y_origin", "depth_origin"):
            self.assertIn(field, profile)
        for field in ("world_x_scale", "depth_scale", "elevation_scale", "oblique_x_shear"):
            self.assertGreater(profile[field], 0.0 if field != "oblique_x_shear" else -1e9)

    def test_profile_depth_rails_are_ordered_and_valid_for_rail_sampling(self) -> None:
        rails = self.profiles["chapter1_oblique_v2"]["playable_depth_rails"]
        for name in ("far", "middle", "near"):
            self.assertIn(name, rails)
        self.assertGreater(rails["near"], rails["middle"])
        self.assertGreater(rails["middle"], rails["far"])

    def test_reference_ratios_pass_the_same_depth_review_windows(self) -> None:
        reference = self.profiles["chapter1_oblique_v2"]["reference_physical_dimensions"]
        adult = reference["neutral_adult_height_m"]
        sedan = reference["sedan_roof_height_m"]
        door = reference["door_height_m"]
        self.assertTrue(math.isfinite(adult) and adult > 0)
        self.assertTrue(0.7 <= sedan / adult <= 0.9)
        self.assertTrue(1.05 <= door / adult <= 1.20)
        # Keep a direct record for calibration scripts.
        self.assertAlmostEqual(sedan / adult, 0.75, places=2)


class ProjectionDeterminismTests(unittest.TestCase):
    def setUp(self) -> None:
        gameplay = load_gameplay()
        profiles = gameplay.get("projection_profiles", {})
        if not profiles:
            profiles = gameplay.get("engine", {}).get("projection_profiles", {})
        profile = profiles["chapter1_oblique_v2"]
        self.projection = BeatEmUpProjection(ProjectionConfig(
            mode=profile["mode"],
            screen_origin_x=profile["screen_origin_x"],
            floor_screen_y=profile["screen_y_origin"],
            pixels_per_world_x=profile["world_x_scale"],
            pixels_per_depth=profile["depth_scale"],
            pixels_per_elevation=profile["elevation_scale"],
            oblique_x_per_depth=profile["oblique_x_shear"],
            pixel_snap=bool(profile["pixel_snap"]),
        ))
        self.camera_depth = float(profile["depth_origin"])

    def test_projection_output_is_deterministic(self) -> None:
        source = WorldPoint(312.5, 276.0, 14.0)
        first = self.projection.project(source, camera_x=100.0, camera_depth=self.camera_depth)
        for _ in range(4):
            self.assertEqual(first, self.projection.project(source, camera_x=100.0, camera_depth=self.camera_depth))

    def test_pixel_snap_is_stable_when_enabled(self) -> None:
        gameplay = load_gameplay()
        profiles = gameplay.get("projection_profiles", {})
        if not profiles:
            profiles = gameplay.get("engine", {}).get("projection_profiles", {})
        profile = profiles["chapter1_oblique_v2"]
        projection = BeatEmUpProjection(ProjectionConfig(
            mode=profile["mode"],
            screen_origin_x=0.0,
            floor_screen_y=profile["screen_y_origin"],
            pixels_per_world_x=profile["world_x_scale"],
            pixels_per_depth=profile["depth_scale"],
            pixels_per_elevation=profile["elevation_scale"],
            oblique_x_per_depth=profile["oblique_x_shear"],
            pixel_snap=True,
        ))
        first = projection.project(WorldPoint(10.2, 280.7, 0.0), camera_x=45.4, camera_depth=self.camera_depth)
        second = projection.project(WorldPoint(10.2, 280.7, 0.0), camera_x=45.4, camera_depth=self.camera_depth)
        self.assertEqual(first.pixel_xy, second.pixel_xy)


class ProjectionCalibrationToolTests(unittest.TestCase):
    def test_tool_runs_directly_and_emits_every_route_checkpoint(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        script = project_root / "tools" / "Render-Projection-Calibration.py"
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--project-root",
                    str(project_root),
                    "--output-dir",
                    temporary,
                ],
                cwd=project_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            report = json.loads(
                (Path(temporary) / "projection_calibration_report.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["projection_profile_id"], "chapter1_oblique_v2")
        self.assertEqual(len(report["locations"]), 20)
        self.assertEqual(
            {location["level_id"] for location in report["locations"]},
            {
                "chapter_1_level_1",
                "chapter_1_level_2",
                "chapter_1_level_3",
                "chapter_1_level_4",
            },
        )


if __name__ == "__main__":
    unittest.main()
