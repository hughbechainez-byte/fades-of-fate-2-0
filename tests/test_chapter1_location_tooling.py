"""Focused contracts for Chapter 1 location QA and packaging gates."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import unittest
from typing import Mapping
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
import src.pixel_art as pixel_art

from tools.validate_chapter1 import (
    FIXED_STEP_BUDGET_MS,
    _asset_inventory_digest,
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
        self.assertEqual(len(report["asset_inventory_sha256"]), 64)
        atmosphere_file = report["authoritative_runtime_files"]["atmosphere"]
        atmosphere_path = PROJECT_ROOT / "data" / "atmosphere.json"
        self.assertTrue(atmosphere_file["exists"])
        self.assertEqual(atmosphere_file["path"], "data/atmosphere.json")
        self.assertEqual(
            atmosphere_file["size_bytes"],
            atmosphere_path.stat().st_size,
        )
        self.assertEqual(
            atmosphere_file["sha256"],
            hashlib.sha256(atmosphere_path.read_bytes()).hexdigest(),
        )
        self.assertNotEqual(
            report["asset_inventory_sha256"],
            _asset_inventory_digest(report["routes"]),
        )
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
                    if field == "physical_scene_object_assets":
                        self.assertIsNone(asset["size"])
                        self.assertEqual(len(asset["sha256"]), 64)
                        self.assertGreater(len(asset["items"]), 0)
                        continue
                    self.assertEqual(asset["size"][1], 360)
                    self.assertEqual(len(asset["sha256"]), 64)
            self.assertTrue(route["assets"]["main_panorama_asset"]["fully_opaque"])
            self.assertTrue(route["assets"]["far_asset"]["has_alpha"])
            self.assertTrue(route["assets"]["near_asset"]["has_alpha"])
            layered_fields = (
                "far_haze_asset",
                "far_skyline_asset",
                "architecture_asset",
                "ground_asset",
                "near_occluder_asset",
            )
            for field in layered_fields:
                self.assertIn(field, manifest_route)
                self.assertEqual(
                    manifest_route[f"{field}_size"],
                    [route["world_width"], 360],
                )
            layered = (
                manifest_route["far_haze_asset"],
                manifest_route["far_skyline_asset"],
                manifest_route["architecture_asset"],
                manifest_route["ground_asset"],
                manifest_route["near_occluder_asset"],
            )
            self.assertEqual(len(set(layered)), len(layered))
            for field in layered_fields:
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
                "world_x",
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
                    self.assertTrue(str(item["asset"]).startswith("assets/"))
                    self.assertTrue((PROJECT_ROOT / str(item["asset"])).is_file())

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

        saved_vehicle_cache = dict(pixel_art._AMBIENT_VEHICLE_CACHE)
        with patch.object(
            pixel_art,
            "prewarm_ambient_traffic",
            wraps=pixel_art.prewarm_ambient_traffic,
        ) as prewarm:
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
        self.assertEqual(
            [item.args[0] for item in prewarm.call_args_list],
            [route["theme"] for route in report["routes"]],
        )
        self.assertEqual(pixel_art._AMBIENT_VEHICLE_CACHE, saved_vehicle_cache)
        self.assertTrue(report["passed"])
        for route in report["routes"]:
            self.assertEqual(route["timing"]["p95_ms"], 4.0)
            self.assertEqual(len(route["checkpoint_sha256"]), 5)
            self.assertTrue(route["checkpoints_visually_distinct"])
            self.assertTrue(route["p95_within_fixed_step_budget"])

    def test_visual_qa_projects_a_calibrated_prop_into_each_route_sheet(
        self,
    ) -> None:
        script_path = PROJECT_ROOT / "tools" / "Render-Route-Scenery-QA.py"
        spec = importlib.util.spec_from_file_location(
            "render_route_scenery_qa_for_test",
            script_path,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gameplay = json.loads(
            (PROJECT_ROOT / "data" / "gameplay.json").read_text(
                encoding="utf-8-sig"
            )
        )
        manifest = json.loads(
            (PROJECT_ROOT / "data" / "chapter1_location_lock.json").read_text(
                encoding="utf-8-sig"
            )
        )
        projection, camera_depth, profile_id = module._build_active_projection(
            gameplay
        )

        self.assertEqual(profile_id, "chapter1_oblique_v2")
        for route in manifest["routes"]:
            max_camera = max(0, int(route["world_width"]) - 640)
            visible_checkpoints: list[float] = []
            for fraction in module.CHECKPOINTS:
                frame = pygame.Surface((640, 360)).convert()
                placements = module._draw_physical_scene_objects(
                    frame,
                    route,
                    int(round(max_camera * fraction)),
                    projection,
                    camera_depth,
                )
                self.assertGreater(len(placements), 0)
                self.assertTrue(
                    all(
                        item["bottom_center_matches_projection"]
                        for item in placements
                    )
                )
                self.assertTrue(
                    all(item["ground_contact_valid"] for item in placements)
                )
                self.assertTrue(
                    all(
                        item["ground_contact_gap_px"] >= 0
                        for item in placements
                    )
                )
                if any(item["substantially_visible"] for item in placements):
                    visible_checkpoints.append(fraction)
            with self.subTest(level_id=route["level_id"]):
                self.assertGreater(len(visible_checkpoints), 0)

    def test_visual_qa_uses_settled_route_profiles_and_animated_phases(
        self,
    ) -> None:
        script_path = PROJECT_ROOT / "tools" / "Render-Route-Scenery-QA.py"
        spec = importlib.util.spec_from_file_location(
            "render_route_atmosphere_qa_for_test",
            script_path,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gameplay = json.loads(
            (PROJECT_ROOT / "data" / "gameplay.json").read_text(
                encoding="utf-8-sig"
            )
        )
        manifest = json.loads(
            (PROJECT_ROOT / "data" / "chapter1_location_lock.json").read_text(
                encoding="utf-8-sig"
            )
        )
        atmosphere_data = json.loads(
            (PROJECT_ROOT / "data" / "atmosphere.json").read_text(
                encoding="utf-8-sig"
            )
        )
        projection, camera_depth, _ = module._build_active_projection(gameplay)
        font = pygame.font.Font(None, 14)

        for route in manifest["routes"]:
            samples = module._build_route_atmosphere_samples(
                route,
                atmosphere_data,
            )
            steady = samples["steady"]
            animated = samples["animated"]
            self.assertEqual(
                samples["mapped_profile_id"],
                route["sky_profile_id"],
            )
            self.assertEqual(steady.current_profile_id, route["sky_profile_id"])
            self.assertEqual(steady.target_profile_id, route["sky_profile_id"])
            self.assertEqual(steady.transition_progress, 1.0)
            self.assertGreater(animated.time_seconds, steady.time_seconds)
            self.assertNotEqual(animated.cloud_phases, steady.cloud_phases)

            camera_x = max(
                0,
                min(
                    int(route["world_width"]) - 640,
                    int(route["physical_scene_objects"][0]["world_x"]) - 320,
                ),
            )
            steady_frame, _ = module._render_checkpoint(
                route,
                camera_x,
                font,
                0.5,
                projection,
                camera_depth,
                steady,
                "STEADY",
            )
            animated_frame, _ = module._render_checkpoint(
                route,
                camera_x,
                font,
                0.5,
                projection,
                camera_depth,
                animated,
                "STEADY",
            )
            with self.subTest(level_id=route["level_id"]):
                self.assertNotEqual(
                    module._sky_region_sha256(steady_frame),
                    module._sky_region_sha256(animated_frame),
                )
                changed_fraction = module._changed_pixel_fraction(
                    steady_frame,
                    animated_frame,
                    module._sky_region_rect(steady_frame),
                )
                self.assertGreaterEqual(changed_fraction, 0.01)
                self.assertLessEqual(changed_fraction, 0.15)

        script = script_path.read_text(encoding="utf-8-sig")
        self.assertIn('"atmosphere_phase_results"', script)
        self.assertIn('"fixed_camera_phase_hashes_distinct"', script)
        self.assertIn('"sky_region_sha256"', script)
        self.assertIn('"sky_motion_visibly_persistent"', script)

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
        self.assertEqual(script.count("Render-Route-Scenery-QA.py"), 1)
        self.assertIn("Render-Projection-Calibration.py", script)
        self.assertIn("branch --show-current | Out-String", script)
        self.assertIn("$sourceBranchName = 'detached'", script)
        self.assertIn("$VisualReviewApproved", script)
        self.assertIn("Remove-Item -LiteralPath $staleArtifact", script)
        self.assertIn("asset_inventory_sha256", script)
        self.assertIn("Packaged location asset inventory mismatch", script)
        self.assertIn("Installed location asset inventory mismatch", script)
        self.assertIn(
            "Get-FileHash -Algorithm SHA256 -LiteralPath $exe",
            script,
        )
        self.assertIn(
            "Get-FileHash -Algorithm SHA256 -LiteralPath $desktopExe",
            script,
        )
        self.assertIn("Installed executable hash mismatch", script)
        self.assertLess(
            script.index("Installed executable hash mismatch"),
            script.index("Desktop self-test failed"),
        )
        self.assertIn("chapter1_validation_build.json", script)
        self.assertIn("$validationAttemptCount = 5", script)
        self.assertIn("$nonPerformanceValidationPass", script)
        self.assertIn("strict attempts", script)
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
        self.assertIn("failed_location_preflight", script)
        self.assertIn('"completed_by_codex_visual_review"', script)


if __name__ == "__main__":
    unittest.main()
