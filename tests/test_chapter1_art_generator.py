"""Regression tests for Chapter 1 panorama composition."""

from __future__ import annotations

import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src import atmosphere, backdrop
from tools import build_chapter1_location_art as art


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ChapterOneArtGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.manifest = json.loads(
            (PROJECT_ROOT / "data" / "chapter1_location_lock.json").read_text(
                encoding="utf-8-sig"
            )
        )

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_panel_widths_exactly_fill_each_world_strip(self) -> None:
        for route in self.manifest["routes"]:
            theme = route["theme"]
            with self.subTest(theme=theme):
                self.assertEqual(
                    sum(spec.width for spec in art.PANEL_SPECS[theme]),
                    route["world_width"],
                )

    def test_layered_manifest_fields_are_present_and_route_specific(self) -> None:
        required_fields = (
            "projection_profile_id",
            "sky_profile_id",
            "ground_opaque_from_y",
            "far_haze_asset",
            "far_haze_asset_size",
            "far_skyline_asset",
            "far_skyline_asset_size",
            "architecture_asset",
            "architecture_asset_size",
            "ground_asset",
            "ground_asset_size",
            "near_occluder_asset",
            "near_occluder_asset_size",
            "physical_scene_objects",
        )
        for route in self.manifest["routes"]:
            with self.subTest(theme=route["theme"]):
                for field in required_fields:
                    self.assertIn(field, route, f"{route['theme']} missing {field}")
                self.assertEqual(route["projection_profile_id"], "chapter1_oblique_v2")

    def test_authored_doors_share_the_runtime_adult_height_ruler(self) -> None:
        profile = json.loads(
            (PROJECT_ROOT / "data" / "gameplay.json").read_text(
                encoding="utf-8-sig"
            )
        )["engine"]["projection_profiles"]["chapter1_oblique_v2"]
        reference = profile["reference_physical_dimensions"]
        expected = round(
            art.REFERENCE_ADULT_HEIGHT_PX
            * reference["door_height_m"]
            / reference["neutral_adult_height_m"]
        )

        self.assertEqual(art.REFERENCE_ADULT_HEIGHT_PX, 134)
        self.assertEqual(art.REFERENCE_DOOR_HEIGHT_PX, expected)
        self.assertTrue(
            1.05
            <= art.REFERENCE_DOOR_HEIGHT_PX / art.REFERENCE_ADULT_HEIGHT_PX
            <= 1.20
        )

    def test_layer_artifacts_are_true_alpha_surfaces(self) -> None:
        for route in self.manifest["routes"]:
            layers = art._build_layered_assets(route)
            with self.subTest(theme=route["theme"]):
                expected_size = (route["world_width"], art.HEIGHT)
                for layer_name, layer in layers.items():
                    self.assertEqual(layer.get_size(), expected_size)
                    self.assertEqual(layer.get_flags() & pygame.SRCALPHA, pygame.SRCALPHA)
                self.assertEqual(layers["haze"].get_size(), expected_size)
                self.assertEqual(layers["ground"].get_size(), expected_size)
                ground_row = int(route["ground_opaque_from_y"])
                self.assertLess(ground_row, art.HEIGHT)
                world_width = int(route["world_width"])
                sampled_x = range(0, world_width, 80)
                ground_alpha = [layers["ground"].get_at((x, ground_row))[3] for x in sampled_x]
                haze_alpha = [
                    layers["haze"].get_at((x, max(0, ground_row - 8)))[3]
                    for x in sampled_x
                ]
                self.assertIn(255, ground_alpha)
                architecture_rows = [
                    max(0, ground_row - 20),
                    max(0, ground_row - 12),
                    max(0, ground_row - 8),
                ]
                self.assertTrue(
                    any(
                        any(layers["architecture"].get_at((x, row))[3] > 0 for x in sampled_x)
                        for row in architecture_rows
                    )
                )
                self.assertTrue(all(alpha == 0 for alpha in haze_alpha))

    def test_haze_assets_repeat_on_the_runtime_cloud_cycle(self) -> None:
        self.assertEqual(
            art.HAZE_REPEAT_WIDTH,
            backdrop.HAZE_REPEAT_WIDTH,
        )
        self.assertEqual(
            art.HAZE_REPEAT_WIDTH,
            int(atmosphere.CLOUD_CYCLE_PIXELS),
        )
        for route in self.manifest["routes"]:
            haze = art._build_layered_assets(route)["haze"]
            self.assertEqual(haze.get_width() % art.HAZE_REPEAT_WIDTH, 0)
            first_tile = pygame.image.tobytes(
                haze.subsurface(
                    pygame.Rect(
                        0,
                        0,
                        art.HAZE_REPEAT_WIDTH,
                        haze.get_height(),
                    )
                ),
                "RGBA",
                False,
            )
            for tile_x in range(
                art.HAZE_REPEAT_WIDTH,
                haze.get_width(),
                art.HAZE_REPEAT_WIDTH,
            ):
                with self.subTest(theme=route["theme"], tile_x=tile_x):
                    self.assertEqual(
                        pygame.image.tobytes(
                            haze.subsurface(
                                pygame.Rect(
                                    tile_x,
                                    0,
                                    art.HAZE_REPEAT_WIDTH,
                                    haze.get_height(),
                                )
                            ),
                            "RGBA",
                            False,
                        ),
                        first_tile,
                    )

    def test_layered_architecture_retains_masked_authored_detail_and_ground_support(
        self,
    ) -> None:
        for route in self.manifest["routes"]:
            layers = art._build_layered_assets(route)
            architecture = layers["architecture"]
            ground = layers["ground"]
            ground_row = int(route["ground_opaque_from_y"])
            sampled_colors = {
                tuple(architecture.get_at((x, y))[:3])
                for x in range(0, architecture.get_width(), 8)
                for y in range(32, ground_row, 4)
                if architecture.get_at((x, y)).a
            }
            with self.subTest(theme=route["theme"]):
                self.assertGreater(
                    len(sampled_colors),
                    128,
                    "masked source detail must not regress to flat facade blocks",
                )
                for feature in route["physical_scene_objects"]:
                    contact = (
                        int(round(float(feature["world_x"]))),
                        int(round(float(feature["depth"]))),
                    )
                    self.assertGreaterEqual(contact[1], ground_row)
                    self.assertEqual(ground.get_at(contact).a, 255)

    def test_panel_anchor_bands_exactly_cover_manifest_order(self) -> None:
        for route in self.manifest["routes"]:
            theme = route["theme"]
            expected_ids = tuple(item["id"] for item in route["landmarks"])
            actual_ids = tuple(
                anchor_id
                for spec in art.PANEL_SPECS[theme]
                for anchor_id in spec.anchor_ids
            )
            with self.subTest(theme=theme):
                self.assertEqual(actual_ids, expected_ids)

            world_x = {
                item["id"]: int(item["world_x"])
                for item in route["landmarks"]
            }
            cursor = 0
            for spec in art.PANEL_SPECS[theme]:
                right = cursor + spec.width
                for anchor_id in spec.anchor_ids:
                    with self.subTest(theme=theme, anchor_id=anchor_id):
                        self.assertGreaterEqual(world_x[anchor_id], cursor)
                        self.assertLessEqual(world_x[anchor_id], right)
                cursor = right

    def test_every_panel_uses_one_uniform_cover_scale(self) -> None:
        for theme, specs in art.PANEL_SPECS.items():
            for spec in specs:
                source = pygame.image.load(str(art.ROOT / spec.source))
                source_size = (
                    spec.source_crop[2:4]
                    if spec.source_crop is not None
                    else source.get_size()
                )
                scale, scaled_size, crop = art.cover_crop_geometry(
                    source_size,
                    (spec.width, art.HEIGHT),
                    focal_x=spec.focal_x,
                    focal_y=spec.focal_y,
                )
                with self.subTest(theme=theme, source=spec.source):
                    self.assertAlmostEqual(
                        scale,
                        max(spec.width / source_size[0], art.HEIGHT / source_size[1]),
                    )
                    self.assertGreaterEqual(scaled_size[0], spec.width)
                    self.assertGreaterEqual(scaled_size[1], art.HEIGHT)
                    self.assertTrue(
                        pygame.Rect((0, 0), scaled_size).contains(crop),
                        (scaled_size, crop),
                    )
                    rounding_error = abs(
                        scaled_size[0] / source_size[0]
                        - scaled_size[1] / source_size[1]
                    )
                    self.assertLessEqual(
                        rounding_error,
                        max(1 / source_size[0], 1 / source_size[1]),
                    )

    def test_miniature_vehicle_and_warped_floor_helpers_cannot_return(self) -> None:
        source = (PROJECT_ROOT / "tools" / "build_chapter1_location_art.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "_draw_car",
            "_draw_driveway",
            "_draw_parking_stripes",
            "_draw_route_road",
            "pygame.transform.scale(crop",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_routes_build_at_declared_size_and_remain_fully_opaque(self) -> None:
        for route in self.manifest["routes"]:
            main, far, near = art._build_route(route)
            expected = (route["world_width"], art.HEIGHT)
            with self.subTest(level_id=route["level_id"]):
                self.assertEqual(main.get_size(), expected)
                self.assertEqual(far.get_size(), expected)
                self.assertEqual(near.get_size(), expected)
                self.assertEqual(main.get_flags() & pygame.SRCALPHA, 0)

    def test_production_panels_are_unique_location_locked_sources(self) -> None:
        sources = [
            spec.source
            for specs in art.PANEL_SPECS.values()
            for spec in specs
        ]
        self.assertEqual(len(sources), len(set(sources)))
        for source in sources:
            with self.subTest(source=source):
                self.assertTrue(
                    source.startswith(
                        "art_source/chapter1_location_locked/source_panels/"
                    )
                )
                self.assertTrue(source.endswith("_source.png"))


if __name__ == "__main__":
    unittest.main()
