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
