"""Unit tests for the reusable chapter-backed layered backdrop compositor."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

import pygame

import src.backdrop as backdrop


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


def _color_surface(width: int, size: tuple[int, int], color: tuple[int, int, int, int]) -> pygame.Surface:
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill(color)
    return surface


def _find_pixel_x(surface: pygame.Surface, color: tuple[int, int, int, int], y: int) -> int | None:
    for x in range(surface.get_width()):
        if surface.get_at((x, y)) == pygame.Color(*color):
            return x
    return None


class BackdropRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_exact_draw_order(self) -> None:
        route = {
            "far_parallax": 0.6,
            "far_max_offset": 0,
            "near_parallax": 1.1,
            "near_max_offset": 0,
            "projection_profile_id": "",
            "sky_profile_id": "",
            "ground_opaque_from_y": 250,
        }
        world_width = 800
        main = _color_surface(world_width, (world_width, 360), (200, 10, 20, 255))
        far = _color_surface(world_width, (world_width, 360), (20, 20, 220, 128))
        far_skyline = _color_surface(world_width, (world_width, 360), (0, 0, 0, 0))
        pygame.draw.rect(far_skyline, (60, 200, 80, 255), (0, 280, world_width, 60))
        architecture = pygame.Surface((world_width, 360), pygame.SRCALPHA)
        architecture.fill((0, 0, 0, 0))
        pygame.draw.rect(architecture, (210, 180, 80, 255), (180, 40, 140, 120))
        ground = pygame.Surface((world_width, 360), pygame.SRCALPHA)
        ground.fill((0, 0, 0, 0))
        pygame.draw.rect(ground, (200, 0, 140, 255), (0, 220, world_width, 180))

        layers = {
            "main": main,
            "far": far,
            "near": far,
            "far_haze": far,
            "far_skyline": far_skyline,
            "architecture": architecture,
            "ground": ground,
            "near_occluder": None,
        }
        backdrop.clear_backdrop_caches()
        surface = pygame.Surface((640, 360))
        backdrop.render_route_backdrop(
            surface,
            "test",
            route,
            layers,
            camera_x=0,
            world_width=world_width,
            atmosphere=None,
            loader_identity=id(pygame.image.load),
        )
        self.assertEqual(surface.get_at((250, 80)), pygame.Color(210, 180, 80, 255))  # architecture over haze
        self.assertEqual(surface.get_at((500, 40)), pygame.Color(20, 20, 220, 128))  # haze over base sky
        self.assertEqual(surface.get_at((500, 320)), pygame.Color(200, 0, 140, 255))  # ground last

    def test_static_cache_reuses_across_atmosphere_time(self) -> None:
        route = {"far_parallax": 0.6, "far_max_offset": 64, "near_parallax": 1.0, "near_max_offset": 0}
        world_width = 700
        common = _color_surface(world_width, (world_width, 360), (30, 30, 30, 255))
        layers = {
            "main": common,
            "far": common,
            "near": common,
            "far_haze": common,
            "far_skyline": None,
            "architecture": None,
            "ground": None,
            "near_occluder": None,
        }

        backdrop.clear_backdrop_caches()
        first_surface = pygame.Surface((640, 360))
        backdrop.render_route_backdrop(
            first_surface,
            "test",
            route,
            layers,
            100,
            world_width,
            atmosphere={"time_seconds": 0, "seed": 0, "cloud_phases": [], "wind": {"speed": 0, "direction": 0}, "transition_progress": 1.0},
            loader_identity=id(pygame.image.load),
        )
        first_keys = list(backdrop.backdrop_cache().keys())
        first_id = id(backdrop.backdrop_cache()[first_keys[0]][0])

        second_surface = pygame.Surface((640, 360))
        backdrop.render_route_backdrop(
            second_surface,
            "test",
            route,
            layers,
            100,
            world_width,
            atmosphere={"time_seconds": 9.0, "seed": 0, "cloud_phases": [], "wind": {"speed": 0, "direction": 0}, "transition_progress": 1.0},
            loader_identity=id(pygame.image.load),
        )
        second_keys = list(backdrop.backdrop_cache().keys())
        second_id = id(backdrop.backdrop_cache()[second_keys[0]][0])
        self.assertEqual(first_keys, second_keys)
        self.assertEqual(first_id, second_id)

    def test_dynamic_haze_moves_with_time_at_fixed_camera(self) -> None:
        route = {"far_parallax": 0.8, "far_max_offset": 64, "near_parallax": 1.0, "near_max_offset": 0}
        world_width = 900
        main = _color_surface(world_width, (world_width, 360), (25, 25, 25, 255))
        far = _color_surface(world_width, (world_width, 360), (255, 255, 0, 255))
        far.fill((255, 255, 0, 255))
        layers = {
            "main": main,
            "far": far,
            "near": None,
            "far_haze": far,
            "far_skyline": None,
            "architecture": None,
            "ground": None,
            "near_occluder": None,
        }
        backdrop.clear_backdrop_caches()
        first = pygame.Surface((640, 360))
        second = pygame.Surface((640, 360))
        atmosphere_frozen = {
            "time_seconds": 0.0,
            "seed": 31,
            "cloud_phases": [0.0],
            "wind": {"speed": 30.0, "direction": 0.0},
            "transition_progress": 1.0,
        }
        atmosphere_moving = atmosphere_frozen.copy()
        atmosphere_moving["time_seconds"] = 4.0

        backdrop.render_route_backdrop(first, "test", route, layers, 120, world_width, atmosphere=atmosphere_frozen, loader_identity=id(pygame.image.load))
        backdrop.render_route_backdrop(second, "test", route, layers, 120, world_width, atmosphere=atmosphere_moving, loader_identity=id(pygame.image.load))
        self.assertNotEqual(pygame.image.tobytes(first, "RGB"), pygame.image.tobytes(second, "RGB"))

    def test_one_to_one_architecture_and_ground_motion(self) -> None:
        route = {"far_parallax": 0.7, "far_max_offset": 64, "near_parallax": 1.0, "near_max_offset": 0}
        world_width = 960
        main = _color_surface(world_width, (world_width, 360), (10, 10, 10, 255))
        architecture = pygame.Surface((world_width, 360), pygame.SRCALPHA)
        architecture.fill((0, 0, 0, 0))
        pygame.draw.line(architecture, (20, 220, 20, 255), (220, 100), (220, 340))
        ground = pygame.Surface((world_width, 360), pygame.SRCALPHA)
        ground.fill((0, 0, 0, 0))
        pygame.draw.line(ground, (20, 20, 220, 255), (220, 300), (220, 359))
        layers = {
            "main": main,
            "far": main,
            "near": None,
            "far_haze": main,
            "far_skyline": None,
            "architecture": architecture,
            "ground": ground,
            "near_occluder": None,
        }

        first = pygame.Surface((640, 360))
        second = pygame.Surface((640, 360))
        backdrop.clear_backdrop_caches()
        backdrop.render_route_backdrop(first, "test", route, layers, 60, world_width, atmosphere=None, loader_identity=id(pygame.image.load))
        backdrop.render_route_backdrop(second, "test", route, layers, 180, world_width, atmosphere=None, loader_identity=id(pygame.image.load))
        self.assertEqual(_find_pixel_x(first, (20, 220, 20, 255), 120), 160)
        self.assertEqual(_find_pixel_x(second, (20, 220, 20, 255), 120), 40)
        self.assertEqual(_find_pixel_x(first, (20, 20, 220, 255), 320), 160)
        self.assertEqual(_find_pixel_x(second, (20, 20, 220, 255), 320), 40)

    def test_bounded_parallax_limits_far_skyline_and_near_occluder_offsets(self) -> None:
        world_width = 1400
        route = {
            "far_parallax": 0.3,
            "far_max_offset": 64,
            "near_parallax": 1.08,
            "near_max_offset": 96,
        }
        main = _color_surface(world_width, (world_width, 360), (12, 12, 12, 255))
        far = _color_surface(world_width, (world_width, 360), (0, 0, 0, 0))
        skyline = _color_surface(world_width, (world_width, 360), (110, 110, 220, 255))
        pygame.draw.line(skyline, (255, 0, 0, 255), (500, 0), (500, 359), 2)
        near_occluder = _color_surface(world_width, (world_width, 360), (255, 0, 255, 255))

        layers = {
            "main": main,
            "far": far,
            "near": near_occluder,
            "far_haze": far,
            "far_skyline": skyline,
            "architecture": None,
            "ground": None,
            "near_occluder": near_occluder,
        }

        first = pygame.Surface((640, 360))
        second = pygame.Surface((640, 360))
        backdrop.clear_backdrop_caches()
        backdrop.render_route_backdrop(first, "test", route, layers, 0, world_width, atmosphere=None, loader_identity=id(pygame.image.load))
        backdrop.render_route_backdrop(second, "test", route, layers, 1200, world_width, atmosphere=None, loader_identity=id(pygame.image.load))
        skyline_start = backdrop._bounded_location_layer_offset(0, 0.3, 64, world_width, 640)
        skyline_end = backdrop._bounded_location_layer_offset(1200, 0.3, 64, world_width, 640)
        skyline_main_start = backdrop._bounded_location_layer_offset(0, 1.0, 0, world_width, 640)
        skyline_main_end = backdrop._bounded_location_layer_offset(1200, 1.0, 0, world_width, 640)
        self.assertLessEqual(abs(skyline_end - skyline_main_start), 64)
        self.assertLessEqual(abs(skyline_end - skyline_start), 64)
        self.assertNotEqual(skyline_start, skyline_end)

        near_start = backdrop._bounded_location_layer_offset(0, 1.08, 96, world_width, 640)
        near_end = backdrop._bounded_location_layer_offset(1200, 1.08, 96, world_width, 640)
        near_main_start = backdrop._bounded_location_layer_offset(0, 1.0, 0, world_width, 640)
        near_main_end = backdrop._bounded_location_layer_offset(1200, 1.0, 0, world_width, 640)
        self.assertLessEqual(abs((near_end - near_main_end) - (near_start - near_main_start)), 96)

    def test_no_per_frame_fullscreen_reallocations(self) -> None:
        route = {"far_parallax": 0.8, "far_max_offset": 64, "near_parallax": 1.0, "near_max_offset": 0}
        world_width = 700
        layer = _color_surface(world_width, (world_width, 360), (40, 40, 40, 255))
        layers = {
            "main": layer,
            "far": layer,
            "near": None,
            "far_haze": layer,
            "far_skyline": None,
            "architecture": None,
            "ground": None,
            "near_occluder": None,
        }
        atmosphere = {"time_seconds": 0, "seed": 0, "cloud_phases": [], "wind": {"speed": 0, "direction": 0}, "transition_progress": 1.0}
        backdrop.clear_backdrop_caches()
        for camera in (0, 20, 40):
            backdrop.render_route_backdrop(
                pygame.Surface((640, 360)),
                "test",
                route,
                layers,
                camera,
                world_width,
                atmosphere=atmosphere,
                loader_identity=id(pygame.image.load),
            )
        self.assertEqual(len(backdrop.backdrop_cache()), 3)


if __name__ == "__main__":
    unittest.main()
