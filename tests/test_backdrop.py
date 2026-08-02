"""Unit tests for the reusable chapter-backed layered backdrop compositor."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

import pygame

import src.backdrop as backdrop
from src.atmosphere import AtmosphereState as RuntimeAtmosphereState


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
        far = _color_surface(world_width, (world_width, 360), (20, 20, 220, 255))
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
        self.assertEqual(surface.get_at((500, 40)), pygame.Color(20, 20, 220, 255))  # haze over base sky
        self.assertEqual(surface.get_at((500, 320)), pygame.Color(200, 0, 140, 255))  # ground last

    def test_fallback_profile_palettes_share_atmosphere_authority(self) -> None:
        for profile_id in (
            "chapter_1_sunset",
            "i8_underpass_dimming",
            "awaken_finale",
        ):
            with self.subTest(profile_id=profile_id):
                expected = RuntimeAtmosphereState.new(
                    profile_id=profile_id,
                ).snapshot().sky_palette
                self.assertEqual(
                    backdrop._sky_palette(
                        {"sky_profile_id": profile_id},
                        None,
                    ),
                    expected,
                )

    def test_manifest_route_uses_detailed_main_under_transparent_layers(self) -> None:
        route = {
            "main_panorama_asset": "assets/stage/chapter1_location_locked/ch1_l1_main_v2.png",
            "far_parallax": 0.6,
            "far_max_offset": 0,
            "near_parallax": 1.0,
            "near_max_offset": 0,
        }
        world_width = 800
        main = _color_surface(world_width, (world_width, 360), (200, 10, 20, 255))
        architecture = pygame.Surface((world_width, 360), pygame.SRCALPHA)
        architecture.fill((210, 180, 80, 255))
        ground = pygame.Surface((world_width, 360), pygame.SRCALPHA)
        ground.fill((0, 0, 0, 0))
        pygame.draw.rect(ground, (200, 0, 140, 255), (0, 220, world_width, 140))
        layers = {
            "main": main,
            "far": None,
            "near": None,
            "far_haze": None,
            "far_skyline": None,
            "architecture": architecture,
            "ground": ground,
            "near_occluder": None,
        }
        surface = pygame.Surface((640, 360))
        backdrop.clear_backdrop_caches()
        backdrop.render_route_backdrop(
            surface,
            "sprouts_el_cilantro",
            route,
            layers,
            camera_x=0,
            world_width=world_width,
            atmosphere=None,
            loader_identity=id(pygame.image.load),
        )
        self.assertEqual(surface.get_at((250, 80)), pygame.Color(200, 10, 20, 255))
        self.assertEqual(surface.get_at((500, 320)), pygame.Color(200, 0, 140, 255))

    def test_cache_key_distinguishes_detailed_main_mode(self) -> None:
        layers = {
            name: None
            for name in (
                "main",
                "far",
                "near",
                "far_haze",
                "far_skyline",
                "architecture",
                "ground",
                "near_occluder",
            )
        }
        common = {"far_parallax": 0.6, "near_parallax": 1.0}
        legacy = backdrop._backdrop_cache_key(
            "test", 640, 360, 800, 0, common, layers, "loader"
        )
        authored = backdrop._backdrop_cache_key(
            "test",
            640,
            360,
            800,
            0,
            {**common, "main_panorama_asset": "assets/main.png"},
            layers,
            "loader",
        )
        self.assertNotEqual(legacy, authored)

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
        far = _color_surface(world_width, (world_width, 360), (0, 0, 0, 0))
        pygame.draw.rect(far, (255, 255, 0, 255), (200, 0, 40, 360))
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
        state = RuntimeAtmosphereState.new(
            seed=31,
            profile_id="chapter_1_sunset",
        )
        atmosphere_frozen = state.snapshot()
        state.advance(3.0)
        atmosphere_moving = state.snapshot()

        backdrop.render_route_backdrop(first, "test", route, layers, 120, world_width, atmosphere=atmosphere_frozen, loader_identity=id(pygame.image.load))
        backdrop.render_route_backdrop(second, "test", route, layers, 120, world_width, atmosphere=atmosphere_moving, loader_identity=id(pygame.image.load))
        self.assertNotEqual(pygame.image.tobytes(first, "RGB"), pygame.image.tobytes(second, "RGB"))

    def test_declared_haze_bands_move_independently_at_fixed_camera(self) -> None:
        route = {
            "far_parallax": 0.2,
            "far_max_offset": 64,
            "near_parallax": 1.0,
            "near_max_offset": 0,
            "ground_opaque_from_y": 240,
        }
        world_width = 900
        main = _color_surface(world_width, (world_width, 360), (25, 25, 25, 255))
        haze = _color_surface(world_width, (world_width, 360), (0, 0, 0, 0))
        band_colors = (
            (255, 40, 40, 255),
            (40, 255, 40, 255),
            (40, 40, 255, 255),
        )
        bands = backdrop._haze_band_rects(route, haze)
        for band, color in zip(bands, band_colors, strict=True):
            pygame.draw.rect(
                haze,
                color,
                (120, band.y + 3, 24, max(1, band.height - 6)),
            )
        layers = {
            "main": main,
            "far": haze,
            "near": None,
            "far_haze": haze,
            "far_skyline": None,
            "architecture": None,
            "ground": None,
            "near_occluder": None,
        }
        baseline_state = {
            "time_seconds": 0.0,
            "seed": 0,
            "cloud_phases": (0.0, 0.0, 0.0),
            "wind": {"speed": 1.0, "direction": 0.0},
            "transition_progress": 1.0,
            "parallax_factors": (0.2, 0.45, 0.7),
        }
        baseline = pygame.Surface((640, 360))
        backdrop.clear_backdrop_caches()
        backdrop.render_route_backdrop(
            baseline,
            "test",
            route,
            layers,
            120,
            world_width,
            atmosphere=baseline_state,
            loader_identity=id(pygame.image.load),
        )

        def band_bytes(surface: pygame.Surface, band: pygame.Rect) -> bytes:
            visible = pygame.Rect(0, band.y, surface.get_width(), band.height)
            return pygame.image.tobytes(surface.subsurface(visible), "RGB")

        for moving_index in range(len(bands)):
            phases = [0.0, 0.0, 0.0]
            phases[moving_index] = 0.1
            moving_state = dict(baseline_state)
            moving_state["time_seconds"] = 1.0
            moving_state["cloud_phases"] = tuple(phases)
            rendered = pygame.Surface((640, 360))
            backdrop.render_route_backdrop(
                rendered,
                "test",
                route,
                layers,
                120,
                world_width,
                atmosphere=moving_state,
                loader_identity=id(pygame.image.load),
            )
            for band_index, band in enumerate(bands):
                with self.subTest(
                    moving_band=moving_index,
                    observed_band=band_index,
                ):
                    if band_index == moving_index:
                        self.assertNotEqual(
                            band_bytes(rendered, band),
                            band_bytes(baseline, band),
                        )
                    else:
                        self.assertEqual(
                            band_bytes(rendered, band),
                            band_bytes(baseline, band),
                        )

    def test_60hz_haze_motion_is_slow_monotonic_and_seamless(self) -> None:
        route = {
            "far_parallax": 0.2,
            "far_max_offset": 64,
        }
        state = RuntimeAtmosphereState.new(
            seed=31,
            profile_id="chapter_1_sunset",
        )
        observed = [set() for _ in range(backdrop.HAZE_BAND_COUNT)]
        previous: tuple[int, ...] | None = None
        for _ in range(180):
            snapshot = state.snapshot()
            offsets = tuple(
                backdrop._atmosphere_haze_offset(
                    route,
                    snapshot,
                    camera_x=120,
                    layer_width=3200,
                    viewport_width=640,
                    band_index=band_index,
                )
                for band_index in range(backdrop.HAZE_BAND_COUNT)
            )
            for band_index, offset in enumerate(offsets):
                observed[band_index].add(offset)
            if previous is not None:
                for current, prior in zip(offsets, previous, strict=True):
                    wrapped_step = min(
                        abs(current - prior),
                        abs(current - prior - backdrop.HAZE_REPEAT_WIDTH),
                        abs(current - prior + backdrop.HAZE_REPEAT_WIDTH),
                    )
                    self.assertLessEqual(wrapped_step, 2)
            previous = offsets
            state.advance(1.0 / 60.0)

        for band_index, positions in enumerate(observed):
            with self.subTest(band_index=band_index):
                self.assertGreater(len(positions), 1)
                self.assertLessEqual(
                    max(positions) - min(positions),
                    backdrop.HAZE_REPEAT_WIDTH,
                )

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
        self.assertLessEqual(abs(skyline_end - skyline_main_end), 64)
        self.assertLessEqual(
            abs((skyline_end - skyline_main_end) - (skyline_start - skyline_main_start)),
            64,
        )
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
