"""Focused contracts for Chapter 1 location QA and packaging gates."""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from typing import Mapping

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from tools.validate_chapter1 import (
    FIXED_STEP_BUDGET_MS,
    build_location_lock_report,
    run_scenery_camera_sweep,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ChapterOneLocationValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_canonical_source_tree_passes_location_and_asset_validation(self) -> None:
        report = build_location_lock_report(PROJECT_ROOT)
        manifest = json.loads(
            (PROJECT_ROOT / "data" / "chapter1_location_lock.json").read_text(
                encoding="utf-8-sig"
            )
        )

        self.assertTrue(report["passed"], report["errors"])
        self.assertEqual(len(report["routes"]), 4)
        self.assertTrue(all(route["passed"] for route in report["routes"]))
        self.assertGreater(
            sum(route["opposite_side_landmark_count"] for route in report["routes"]),
            0,
        )

        routes_by_level = {
            str(route["level_id"]): route
            for route in manifest.get("routes", ())
            if isinstance(route, Mapping)
        }
        for route in report["routes"]:
            self.assertGreater(route["landmark_count"], 2)
            self.assertGreater(route["registered_feature_count"], 0)
            manifest_route = routes_by_level.get(route["level_id"])
            self.assertIsNotNone(manifest_route, route["level_id"])
            assert manifest_route is not None
            self.assertIn("projection_profile_id", manifest_route)
            self.assertIn("sky_profile_id", manifest_route)
            self.assertEqual(manifest_route["projection_profile_id"], "chapter1_oblique_v2")
            self.assertIsInstance(manifest_route["physical_scene_objects"], list)
            self.assertGreater(len(manifest_route["physical_scene_objects"]), 0)
            for field, asset in route["assets"].items():
                with self.subTest(level_id=route["level_id"], field=field):
                    self.assertTrue(asset["exists"])
                    self.assertEqual(asset["size"][1], 360)
                    self.assertEqual(len(asset["sha256"]), 64)
            self.assertTrue(route["assets"]["main_panorama_asset"]["fully_opaque"])
            self.assertTrue(route["assets"]["far_asset"]["has_alpha"])
            self.assertTrue(route["assets"]["near_asset"]["has_alpha"])
            self.assertIn("haze_asset", manifest_route)
            self.assertIn("skyline_asset", manifest_route)
            self.assertIn("architecture_asset", manifest_route)
            self.assertIn("ground_asset", manifest_route)
            self.assertIn("near_occluder_asset", manifest_route)
            layered = (
                manifest_route["haze_asset"],
                manifest_route["skyline_asset"],
                manifest_route["architecture_asset"],
                manifest_route["ground_asset"],
                manifest_route["near_occluder_asset"],
            )
            self.assertEqual(len(set(layered)), len(layered))
            for field in (
                "haze_asset",
                "skyline_asset",
                "architecture_asset",
                "ground_asset",
                "near_occluder_asset",
            ):
                path = PROJECT_ROOT / str(manifest_route[field])
                with self.subTest(level_id=route["level_id"], field=field):
                    self.assertTrue(path.is_file())
                    image = pygame.image.load(str(path)).convert_alpha()
                    self.assertEqual(image.get_size(), (route["world_width"], 360))
                    self.assertEqual(image.get_flags() & pygame.SRCALPHA, pygame.SRCALPHA)
            required_object_fields = (
                "id",
                "kind",
                "asset",
                "x",
                "depth",
                "elevation",
                "anchor",
                "physical_height_m",
            )
            for item in manifest_route["physical_scene_objects"]:
                with self.subTest(level_id=route["level_id"], object_id=item.get("id")):
                    for field in required_object_fields:
                        self.assertIn(field, item)
                    self.assertTrue(item["depth"] <= 360)
                    self.assertTrue(0.0 <= float(item["physical_height_m"]) <= 12.0)

    def test_missing_declared_asset_is_a_real_failure(self) -> None:
        manifest_path = PROJECT_ROOT / "data" / "chapter1_location_lock.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        broken = deepcopy(manifest)
        broken["routes"][0]["main_panorama_asset"] = (
            "assets/stage/chapter1_location_locked/does_not_exist.png"
        )

        report = build_location_lock_report(PROJECT_ROOT, manifest=broken)

        self.assertFalse(report["passed"])
        failed_ids = {item["id"] for item in report["errors"]}
        self.assertIn("authoritative_manifest_validation", failed_ids)
        self.assertIn("main_panorama_asset_path", failed_ids)

    def test_mandatory_reference_ids_retain_the_locked_ref_namespace(self) -> None:
        manifest_path = PROJECT_ROOT / "data" / "chapter1_location_lock.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        broken = deepcopy(manifest)
        broken["mandatory_references"][0]["id"] = "full_corridor_map"

        report = build_location_lock_report(PROJECT_ROOT, manifest=broken)

        self.assertFalse(report["passed"])
        failed_ids = {item["id"] for item in report["errors"]}
        self.assertIn("mandatory_reference_coverage", failed_ids)

    def test_chapter_one_levels_must_live_under_campaign_chapters(self) -> None:
        gameplay_path = PROJECT_ROOT / "data" / "gameplay.json"
        gameplay = json.loads(gameplay_path.read_text(encoding="utf-8-sig"))
        broken = deepcopy(gameplay)
        legacy_levels = broken["campaign"]["chapters"][0]["levels"]
        broken["campaign"]["levels"] = legacy_levels
        broken["campaign"]["chapters"] = []

        report = build_location_lock_report(PROJECT_ROOT, gameplay=broken)

        self.assertFalse(report["passed"])
        failed_ids = {item["id"] for item in report["errors"]}
        self.assertIn("authoritative_gameplay_location_validation", failed_ids)
        self.assertIn("gameplay_chapter_1_structure", failed_ids)
        self.assertIn("gameplay_route_ids", failed_ids)

    def test_injected_camera_sweep_measures_every_route_and_checkpoint(self) -> None:
        frame_count = 5
        measurement_count = 4 * frame_count
        ticks = iter(
            value
            for index in range(measurement_count)
            for value in (index * 10_000_000, index * 10_000_000 + 4_000_000)
        )

        report = run_scenery_camera_sweep(
            frames_per_route=frame_count,
            warmup_frames=0,
            clock_ns=lambda: next(ticks),
        )

        self.assertEqual(
            report["classification"],
            "deterministic_injected_clock_scenery_measurement",
        )
        self.assertEqual(report["fixed_step_budget_ms"], round(FIXED_STEP_BUDGET_MS, 4))
        self.assertEqual(len(report["routes"]), 4)
        self.assertTrue(report["passed"])
        for route in report["routes"]:
            self.assertEqual(route["timing"]["p95_ms"], 4.0)
            self.assertEqual(len(route["checkpoint_sha256"]), 5)
            self.assertTrue(route["checkpoints_visually_distinct"])
            self.assertTrue(route["p95_within_fixed_step_budget"])

    def test_scenery_sweep_rejects_too_few_or_too_many_frames(self) -> None:
        for frame_count in (0, 4, 241):
            with self.subTest(frame_count=frame_count):
                with self.assertRaises(ValueError):
                    run_scenery_camera_sweep(frames_per_route=frame_count)


class ChapterOneWindowsBuildGateTests(unittest.TestCase):
    def test_build_validates_source_package_and_installed_location_assets(self) -> None:
        script = (PROJECT_ROOT / "tools" / "Build-Windows.ps1").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn("Render-Route-Scenery-QA.py", script)
        self.assertIn("chapter1_validation_build.json", script)
        self.assertIn("--location-only", script)
        self.assertIn("--project-root $packageDir", script)
        self.assertIn("--project-root $target", script)
        self.assertIn("'gameplay_render'", script)
        self.assertNotIn("'level_1_background_render'", script)
        self.assertIn("level_3_background_render", script)
        self.assertIn("level_four_runtime_snapshot", script)
        self.assertIn("awaken_refined_sunset_render", script)
        self.assertLess(
            script.index("Render-Route-Scenery-QA.py"),
            script.index("-m PyInstaller"),
        )
        self.assertLess(
            script.index("chapter1_validation_build.json"),
            script.index("-m PyInstaller"),
        )

    def test_visual_qa_renders_panel_handoffs_instead_of_hiding_them_at_edges(
        self,
    ) -> None:
        script = (
            PROJECT_ROOT / "tools" / "Render-Route-Scenery-QA.py"
        ).read_text(encoding="utf-8-sig")

        self.assertIn("chapter1_location_lock_seam_qa.png", script)
        self.assertIn('"authoring_panels": authoring_panels', script)
        self.assertIn('"uniform_cover_scale": scale', script)
        self.assertIn("seam_world_x - width // 2", script)
        self.assertIn("panel_handoffs_are_structurally_masked", script)
        self.assertIn("no_anisotropic_scaling_or_miniature_traffic", script)


if __name__ == "__main__":
    unittest.main()
