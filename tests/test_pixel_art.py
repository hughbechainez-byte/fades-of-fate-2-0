"""Smoke and visual-contract tests for the strict authored pixel-art renderer."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import src.pixel_art as pixel_art  # noqa: E402
from src import location_lock, sprite_atlas  # noqa: E402
from src.animation_manifest import ENEMY_STATES, clip_for  # noqa: E402
from src.pixel_art import (  # noqa: E402
    DESIGN_HEIGHT,
    DESIGN_WIDTH,
    draw_boss,
    draw_chief,
    draw_comic_speech_bubble,
    draw_effect,
    draw_effects,
    draw_enemy,
    draw_fist_flames,
    draw_player,
    draw_pickup,
    draw_projectile,
    draw_stage_background,
    draw_stage_foreground,
)


def _has_nontransparent_pixels(surface: pygame.Surface, rect: pygame.Rect) -> bool:
    clipped = rect.clip(surface.get_rect())
    if clipped.w <= 0 or clipped.h <= 0:
        return False
    return any(surface.get_at((x, y)).a for x in range(clipped.left, clipped.right) for y in range(clipped.top, clipped.bottom))


class PixelArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_stage_background_renders_every_progression_zone(self) -> None:
        theme = "awaken_church_finale"
        route_width = pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS[theme]
        zone_images: list[bytes] = []
        for camera_x in (0, 480, route_width - DESIGN_WIDTH):
            with self.subTest(camera_x=camera_x):
                surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
                rect = draw_stage_background(
                    surface,
                    camera_x,
                    route_width,
                    theme=theme,
                )
                self.assertEqual(rect, surface.get_rect())
                self.assertNotEqual(surface.get_at((5, 5)), surface.get_at((5, 320)))
                sampled_colors = {
                    tuple(surface.get_at((x, y)))
                    for x in range(4, DESIGN_WIDTH, 8)
                    for y in range(4, DESIGN_HEIGHT, 8)
                }
                self.assertGreaterEqual(len(sampled_colors), 20)
                zone_images.append(pygame.image.tobytes(surface, "RGB"))
        self.assertEqual(
            len(set(zone_images)),
            3,
            "Awaken lot checkpoints must remain visually distinct",
        )

    def test_composited_background_frame_cache_reuses_only_the_same_camera_frame(self) -> None:
        """Settled cameras may reuse work, but route travel must stay live."""

        saved = dict(pixel_art._STAGE_BACKGROUND_FRAME_CACHE)
        saved_building = set(pixel_art._STAGE_BACKGROUND_FRAME_BUILDING)
        try:
            pixel_art._STAGE_BACKGROUND_FRAME_CACHE.clear()
            pixel_art._STAGE_BACKGROUND_FRAME_BUILDING.clear()
            first = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            settled = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            moved = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            with patch.object(
                pixel_art,
                "_stage_world_surface",
                wraps=pixel_art._stage_world_surface,
            ) as chunk_layers:
                draw_stage_background(first, 900, 1600, theme="awaken_church_finale")
                draw_stage_background(settled, 900, 1600, theme="awaken_church_finale")
                draw_stage_background(moved, 901, 1600, theme="awaken_church_finale")
            self.assertGreater(chunk_layers.call_count, 0)
            self.assertEqual(pygame.image.tobytes(first, "RGB"), pygame.image.tobytes(settled, "RGB"))
            self.assertNotEqual(pygame.image.tobytes(first, "RGB"), pygame.image.tobytes(moved, "RGB"))
            self.assertLessEqual(
                len(pixel_art._STAGE_BACKGROUND_FRAME_CACHE),
                pixel_art._STAGE_BACKGROUND_FRAME_CACHE_LIMIT,
            )
        finally:
            pixel_art._STAGE_BACKGROUND_FRAME_CACHE.clear()
            pixel_art._STAGE_BACKGROUND_FRAME_CACHE.update(saved)
            pixel_art._STAGE_BACKGROUND_FRAME_BUILDING.clear()
            pixel_art._STAGE_BACKGROUND_FRAME_BUILDING.update(saved_building)

    def test_chapter_one_route_themes_are_distinct_and_world_anchored(self) -> None:
        """Each campaign level has a readable, camera-locked streetscape."""

        routes = location_lock.location_routes(pixel_art._location_manifest())
        self.assertEqual(
            tuple(pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS),
            tuple(str(route["theme"]) for route in routes),
        )
        signatures: list[bytes] = []
        for route in routes:
            theme = str(route["theme"])
            route_width = int(route["world_width"])
            with self.subTest(theme=theme):
                self.assertEqual(
                    pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS[theme],
                    route_width,
                )
                self.assertEqual(
                    pixel_art._CHAPTER_ONE_THEME_ANCHORS[theme],
                    {
                        str(landmark["id"]): int(landmark["world_x"])
                        for landmark in route["landmarks"]
                    },
                )
                pixel_art._STAGE_BACKGROUND_FRAME_CACHE.clear()
                surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
                camera_x = max(0, route_width // 2 - DESIGN_WIDTH // 2)
                rect = draw_stage_background(surface, camera_x, route_width, theme=theme)
                self.assertEqual(rect, surface.get_rect())
                self.assertGreaterEqual(
                    len(
                        {
                            tuple(surface.get_at((x, y)))
                            for x in range(4, DESIGN_WIDTH, 8)
                            for y in range(4, DESIGN_HEIGHT, 8)
                        }
                    ),
                    24,
                    "stage lost its layered landmark/detail palette",
                )
                signatures.append(pygame.image.tobytes(surface, "RGB"))
        self.assertEqual(len(set(signatures)), 4, "Chapter 1 routes must not fall back to one generic street")

    def test_chapter_one_anchor_helper_scales_with_authored_stage_width(self) -> None:
        for route in location_lock.location_routes(pixel_art._location_manifest()):
            theme = str(route["theme"])
            width = int(route["world_width"])
            for landmark in route["landmarks"]:
                with self.subTest(theme=theme, landmark=landmark["id"]):
                    self.assertEqual(
                        pixel_art._theme_anchor_world_x(
                            theme,
                            str(landmark["id"]),
                            width,
                        ),
                        int(landmark["world_x"]),
                    )
        self.assertEqual(
            pixel_art._CHAPTER_ONE_THEME_ANCHORS[
                "awaken_church_finale"
            ]["daves_bmx"],
            1080,
        )

    def test_chapter_one_routes_use_their_authored_world_sequences(self) -> None:
        """A route is a contiguous place, not one photograph over a fallback."""

        for theme, stage_width in pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS.items():
            with self.subTest(theme=theme):
                pixel_art._STAGE_ROUTE_PANORAMA_CACHE.clear()
                panorama = pixel_art._chapter_one_route_panorama(pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT)), stage_width, theme)
                self.assertIsNotNone(panorama)
                self.assertEqual(panorama.get_size(), (stage_width, DESIGN_HEIGHT))

    def test_stage_one_uses_only_the_manifest_location_locked_panorama(self) -> None:
        route = pixel_art._location_route("sprouts_el_cilantro")
        self.assertIsNotNone(route)
        assert route is not None
        self.assertIn(
            "chapter1_location_locked",
            Path(str(route["main_panorama_asset"])).parts,
        )
        retired = {
            "second_street_level1_sprouts_el_cilantro_v1.png",
            "second_street_level1_opening_vehicle_free_v1.png",
            "second_street_route_level1_panorama_v1.png",
        }
        self.assertTrue(
            retired.isdisjoint(Path(value).name for value in pixel_art._STAGE_PANEL_FILES.values())
        )
        panorama = pixel_art._chapter_one_route_panorama(
            pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT)),
            int(route["world_width"]),
            str(route["theme"]),
        )
        self.assertEqual(panorama.get_size(), (int(route["world_width"]), DESIGN_HEIGHT))
        self.assertIsNone(panorama.get_alpha())

    def test_location_asset_failure_never_invokes_procedural_chapter_one_fallback(self) -> None:
        theme = "sprouts_el_cilantro"
        route = pixel_art._location_route(theme)
        self.assertIsNotNone(route)
        assert route is not None
        saved_art = dict(pixel_art._LOCATION_ART_CACHE)
        try:
            pixel_art._LOCATION_ART_CACHE.clear()
            with patch.object(
                pixel_art.pygame.image,
                "load",
                side_effect=pygame.error("missing"),
            ):
                with self.assertRaisesRegex(
                    pixel_art.LocationArtError,
                    "missing or unreadable",
                ):
                    pixel_art._location_art_layers(theme)

            pixel_art._LOCATION_ART_CACHE.clear()
            wrong_size = pygame.Surface(
                (int(route["world_width"]) - 1, DESIGN_HEIGHT)
            )
            with patch.object(
                pixel_art.pygame.image,
                "load",
                return_value=wrong_size,
            ):
                with self.assertRaisesRegex(
                    pixel_art.LocationArtError,
                    "must be 3200x360",
                ):
                    pixel_art._location_art_layers(theme)

            with self.assertRaisesRegex(
                pixel_art.LocationArtError,
                "runtime width disagrees",
            ):
                draw_stage_foreground(
                    pygame.Surface(
                        (DESIGN_WIDTH, DESIGN_HEIGHT),
                        pygame.SRCALPHA,
                    ),
                    0,
                    4200,
                    theme=theme,
                )
        finally:
            pixel_art._LOCATION_ART_CACHE.clear()
            pixel_art._LOCATION_ART_CACHE.update(saved_art)

    def test_main_environment_is_one_to_one_while_far_and_near_offsets_stay_bounded(self) -> None:
        surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
        theme = "seven_eleven_underpass"
        route = pixel_art._location_route(theme)
        self.assertIsNotNone(route)
        assert route is not None
        first = pixel_art._chapter_one_stage_layer_offsets(surface, 0, theme)
        second = pixel_art._chapter_one_stage_layer_offsets(surface, 50, theme)
        shifts = {
            band: second[band] - first[band]
            for band in ("far", "main", "mid", "ground", "near")
        }
        self.assertEqual(shifts["main"], -50)
        self.assertEqual(shifts["mid"], -50)
        self.assertEqual(shifts["ground"], -50)
        self.assertLess(abs(shifts["far"]), abs(shifts["main"]))
        self.assertGreater(abs(shifts["near"]), abs(shifts["main"]))

        terminal = pixel_art._chapter_one_stage_layer_offsets(surface, 2200, theme)
        self.assertLessEqual(
            abs(terminal["far"] - terminal["main"]),
            int(route["far_max_offset"]),
        )
        self.assertLessEqual(
            abs(terminal["near"] - terminal["main"]),
            int(route["near_max_offset"]),
        )
        self.assertTrue(all(isinstance(offset, int) for offset in terminal.values()))

    def test_chapter_one_route_plates_share_one_world_rate_not_depth_bands(self) -> None:
        surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
        theme = "seven_eleven_underpass"
        stage_width = pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS[theme]
        first_offsets = pixel_art._chapter_one_stage_layer_offsets(surface, 1700, theme)
        second_offsets = pixel_art._chapter_one_stage_layer_offsets(surface, 1800, theme)
        self.assertEqual(second_offsets["main"] - first_offsets["main"], -100)
        with (
            patch.object(pixel_art, "_stage_panel_band") as legacy_bands,
            patch.object(pixel_art, "_chapter_one_world_panel") as legacy_panel,
        ):
            panorama = pixel_art._chapter_one_route_panorama(surface, stage_width, theme)
        legacy_bands.assert_not_called()
        legacy_panel.assert_not_called()
        self.assertEqual(panorama.get_size(), (stage_width, pixel_art.DESIGN_HEIGHT))

    def test_every_chapter_one_route_changes_visibly_at_camera_quartiles(self) -> None:
        for theme, stage_width in pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS.items():
            frames: list[pygame.Surface] = []
            max_camera = stage_width - DESIGN_WIDTH
            for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
                pixel_art._STAGE_BACKGROUND_FRAME_CACHE.clear()
                surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
                camera_x = int(round(max_camera * fraction))
                draw_stage_background(surface, camera_x, stage_width, theme=theme)
                frames.append(surface)
            signatures = [pygame.image.tobytes(frame, "RGB") for frame in frames]
            self.assertEqual(len(set(signatures)), 5, f"{theme} must visibly respond at every camera quartile")
            for index, (first, second) in enumerate(zip(frames, frames[1:])):
                sampled = [
                    first.get_at((x, y)) != second.get_at((x, y))
                    for x in range(4, DESIGN_WIDTH, 8)
                    for y in range(4, DESIGN_HEIGHT, 8)
                ]
                self.assertGreater(
                    sum(sampled) / len(sampled),
                    0.20,
                    f"{theme} checkpoint {index}->{index + 1} still reads as a static photo",
                )

    def test_finale_uses_the_authored_bmx_without_a_duplicate_overlay(self) -> None:
        theme = "awaken_church_finale"
        route = location_lock.route_for_theme(
            theme,
            pixel_art._location_manifest(),
        )
        bmx = location_lock.landmark_for_id(route, "daves_bmx")
        feature = location_lock.registered_feature_for_id(
            route,
            "l4_daves_bmx_prop",
        )
        self.assertEqual(route["end_anchor_id"], "daves_bmx")
        self.assertEqual(int(bmx["world_x"]), int(feature["world_x"]))
        surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
        with patch.object(pixel_art, "draw_bmx_bike") as duplicate:
            draw_stage_background(
                surface,
                int(route["world_width"]) - DESIGN_WIDTH,
                int(route["world_width"]),
                theme=theme,
            )
        duplicate.assert_not_called()

    def test_public_signatures_stay_game_compatible(self) -> None:
        expected = {
            draw_stage_background: ("surface", "camera_x", "stage_width", "shake_y", "theme", "atmosphere"),
            draw_stage_foreground: ("surface", "camera_x", "stage_width", "shake_y", "theme"),
            pixel_art.draw_physical_scene_object: ("surface", "x", "y", "feature", "frame"),
            draw_player: ("surface", "x", "y", "z", "facing", "state", "character", "frame", "player_color", "hit_flash"),
            draw_chief: ("surface", "x", "y", "z", "facing", "state", "frame"),
            draw_enemy: ("surface", "x", "y", "z", "facing", "state", "kind", "frame", "tint", "hit_flash"),
            draw_boss: ("surface", "x", "y", "z", "facing", "state", "frame", "hit_flash"),
            draw_projectile: ("surface", "x", "y", "z", "facing", "kind", "frame"),
            draw_pickup: ("surface", "x", "y", "z", "kind", "frame"),
            draw_effect: ("surface", "x", "y", "z", "kind", "frame", "color", "radius"),
        }
        for function, names in expected.items():
            with self.subTest(function=function.__name__):
                self.assertEqual(tuple(inspect.signature(function).parameters), names)

    def test_airborne_shadows_contract_and_fade_without_following_sprite_height(self) -> None:
        grounded = pygame.Surface((180, 120), pygame.SRCALPHA)
        airborne = pygame.Surface((180, 120), pygame.SRCALPHA)
        ground_rect = pixel_art._shadow(grounded, 90, 80, 54, 10)
        air_rect = pixel_art._shadow(airborne, 90, 80, 54, 10, elevation=60)

        grounded_rgba = pygame.image.tobytes(grounded, "RGBA")
        airborne_rgba = pygame.image.tobytes(airborne, "RGBA")
        ground_alpha = sum(grounded_rgba[3::4])
        air_alpha = sum(airborne_rgba[3::4])
        self.assertLess(air_rect.w, ground_rect.w)
        self.assertLessEqual(air_rect.h, ground_rect.h)
        self.assertLess(pygame.mask.from_surface(airborne).count(), pygame.mask.from_surface(grounded).count())
        self.assertLess(air_alpha, ground_alpha)
        self.assertLessEqual(abs(air_rect.centery - ground_rect.centery), 4)

    def test_every_actor_shadow_receives_its_world_elevation(self) -> None:
        canvas = pygame.Surface((640, 360), pygame.SRCALPHA)
        with (
            patch.dict(os.environ, {"FADES_KO_PREVIEW": ""}),
            patch.object(pixel_art, "_shadow", wraps=pixel_art._shadow) as shadow,
        ):
            draw_player(canvas, 90, 300, 37, 1, "idle", "black_dave", 0, "#ef5547")
            draw_chief(canvas, 190, 300, 18, 1, "idle", 0)
            draw_enemy(canvas, 290, 300, 29, -1, "idle", "stick", 0)
            draw_boss(canvas, 430, 300, 51, -1, "idle", 0)

        self.assertEqual(
            [call.kwargs.get("elevation") for call in shadow.call_args_list],
            [37, 18, 29, 51],
        )

    def test_actor_hit_flash_preserves_alpha_and_is_zero_strength_compatible(self) -> None:
        painters = {
            "player": lambda surface, **kwargs: draw_player(
                surface,
                100,
                220,
                0,
                1,
                "hurt",
                "black_dave",
                3,
                "#ef5547",
                **kwargs,
            ),
            "enemy": lambda surface, **kwargs: draw_enemy(
                surface,
                100,
                220,
                state="hurt",
                kind="stick",
                frame=3,
                **kwargs,
            ),
            "boss": lambda surface, **kwargs: draw_boss(
                surface,
                100,
                220,
                state="hurt",
                frame=3,
                **kwargs,
            ),
        }
        for name, painter in painters.items():
            with self.subTest(actor=name):
                default = pygame.Surface((220, 240), pygame.SRCALPHA)
                explicit_zero = pygame.Surface((220, 240), pygame.SRCALPHA)
                flashed = pygame.Surface((220, 240), pygame.SRCALPHA)
                painter(default)
                painter(explicit_zero, hit_flash=0.0)
                painter(flashed, hit_flash=0.75)

                default_rgba = pygame.image.tobytes(default, "RGBA")
                zero_rgba = pygame.image.tobytes(explicit_zero, "RGBA")
                flashed_rgba = pygame.image.tobytes(flashed, "RGBA")
                self.assertEqual(default_rgba, zero_rgba)
                self.assertNotEqual(default_rgba, flashed_rgba)
                self.assertEqual(default_rgba[3::4], flashed_rgba[3::4])
                self.assertEqual(
                    pygame.mask.from_surface(default).count(),
                    pygame.mask.from_surface(flashed).count(),
                )

                def visible_luma(raw: bytes) -> int:
                    return sum(
                        red * 3 + green * 4 + blue
                        for red, green, blue, alpha in zip(
                            raw[0::4],
                            raw[1::4],
                            raw[2::4],
                            raw[3::4],
                        )
                        if alpha
                    )

                self.assertGreater(visible_luma(flashed_rgba), visible_luma(default_rgba))

    def test_sunset_epilogue_uses_authored_group_animation_instead_of_block_figures(self) -> None:
        surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT), pygame.SRCALPHA)
        authored_frame = pygame.Surface((256, 144), pygame.SRCALPHA)
        authored_frame.fill((80, 180, 240, 255))
        with (
            patch.object(pixel_art.sprite_atlas, "sunset_frame", return_value=authored_frame) as sunset_frame,
            patch.object(pixel_art, "draw_bmx_bike") as fallback_bike,
        ):
            pixel_art.draw_sunset_epilogue(surface, 1.5)
        sunset_frame.assert_called_once()
        fallback_bike.assert_not_called()

    def test_sunset_epilogue_loads_cached_authored_background_with_bounded_parallax(self) -> None:
        saved = dict(pixel_art._SUNSET_BACKGROUND_CACHE)
        try:
            pixel_art._SUNSET_BACKGROUND_CACHE.clear()
            authored_frame = pygame.Surface((256, 144), pygame.SRCALPHA)
            authored_frame.fill((80, 180, 240, 255))
            first = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            second = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            with (
                patch.object(pixel_art.pygame.image, "load", wraps=pygame.image.load) as loader,
                patch.object(pixel_art.sprite_atlas, "sunset_frame", return_value=authored_frame),
                patch.object(pixel_art, "_draw_sunset_wheel_motion", wraps=pixel_art._draw_sunset_wheel_motion) as wheels,
            ):
                pixel_art.draw_sunset_epilogue(first, 0.0)
                pixel_art.draw_sunset_epilogue(second, 4.5)
            requested = [Path(call.args[0]).name for call in loader.call_args_list]
            self.assertEqual(requested.count("second_street_bmx_sunset_v1.png"), 1)
            self.assertEqual(wheels.call_count, 2)
            offsets = pixel_art._sunset_layer_offsets(first, 1.0)
            self.assertGreater(offsets["far"], offsets["mid"])
            self.assertGreater(offsets["mid"], offsets["ground"])
            self.assertGreater(offsets["ground"], offsets["near"])
            self.assertGreaterEqual(offsets["near"], -(pixel_art._sunset_background_dimensions(first)[0] - DESIGN_WIDTH))
            self.assertNotEqual(pygame.image.tobytes(first, "RGB"), pygame.image.tobytes(second, "RGB"))
        finally:
            pixel_art._SUNSET_BACKGROUND_CACHE.clear()
            pixel_art._SUNSET_BACKGROUND_CACHE.update(saved)

    def test_manifest_art_cache_contains_one_main_far_and_near_layer_per_route(self) -> None:
        for theme, stage_width in pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS.items():
            with self.subTest(theme=theme):
                layers = pixel_art._location_art_layers(theme)
                self.assertIs(layers, pixel_art._location_art_layers(theme))
                self.assertIs(pixel_art._LOCATION_ART_CACHE[theme], layers)
                for required_key in ("main", "far", "near", "far_haze", "near_occluder"):
                    self.assertIn(required_key, layers)
                    self.assertIsNotNone(layers[required_key])
                    self.assertEqual(layers[required_key].get_size(), (stage_width, DESIGN_HEIGHT))
                self.assertIsNone(layers["main"].get_alpha())
                self.assertTrue(layers["far"].get_masks()[3])
                self.assertTrue(layers["near"].get_masks()[3])
                self.assertTrue(layers["far_haze"].get_masks()[3])
                self.assertTrue(layers["near_occluder"].get_masks()[3])
                self.assertIs(
                    pixel_art._STAGE_ROUTE_PANORAMA_CACHE[
                        ("location-lock", theme, stage_width, DESIGN_HEIGHT)
                    ],
                    layers["main"],
                )

    def test_location_locked_palette_preserves_clear_depth_grading(self) -> None:
        def mean_luma(samples: list[pygame.Color]) -> float:
            values = [
                (color.r * 3 + color.g * 4 + color.b) / 8
                for color in samples
            ]
            self.assertTrue(values)
            return sum(values) / len(values)

        def semantic_samples(
            surface: pygame.Surface,
            architecture: pygame.Surface,
            camera_x: int,
            ground_row: int,
        ) -> tuple[list[pygame.Color], list[pygame.Color], list[pygame.Color]]:
            sky: list[pygame.Color] = []
            facade: list[pygame.Color] = []
            ground: list[pygame.Color] = []
            for x in range(4, DESIGN_WIDTH, 8):
                for y in range(4, ground_row, 8):
                    sample = surface.get_at((x, y))
                    authored = architecture.get_at((camera_x + x, y))
                    (facade if authored.a else sky).append(sample)
                for y in range(ground_row + 4, DESIGN_HEIGHT, 8):
                    ground.append(surface.get_at((x, y)))
            return sky, facade, ground

        for theme, stage_width in pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS.items():
            surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            camera_x = (stage_width - DESIGN_WIDTH) // 2
            draw_stage_background(
                surface,
                camera_x,
                stage_width,
                theme=theme,
            )
            route = pixel_art._location_route(theme)
            layers = pixel_art._location_art_layers(theme)
            sky_samples, facade_samples, ground_samples = semantic_samples(
                surface,
                layers["architecture"],
                camera_x,
                int(route["ground_opaque_from_y"]),
            )
            sky = mean_luma(sky_samples)
            facade = mean_luma(facade_samples)
            ground = mean_luma(ground_samples)
            sampled_luma = [
                (color.r * 3 + color.g * 4 + color.b) / 8
                for x in range(4, DESIGN_WIDTH, 8)
                for y in range(4, DESIGN_HEIGHT, 8)
                for color in (surface.get_at((x, y)),)
            ]
            with self.subTest(theme=theme):
                # A dusk route may legitimately put lit storefronts above the
                # dark sky in luma.  What must remain stable is a pronounced
                # depth separation, not one prescribed brightness ordering.
                self.assertGreater(abs(sky - facade), 10)
                self.assertGreater(abs(sky - ground), 5)
                self.assertLess(min(sampled_luma), 30)
                self.assertGreater(max(sampled_luma), 220)
                self.assertGreater(max(sampled_luma) - min(sampled_luma), 180)

    def test_chapter_one_authored_routes_do_not_spawn_tiny_vehicle_overlays(self) -> None:
        """Legacy tiny traffic helpers stay disabled beside calibrated physical cars."""

        for theme, stage_width in pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS.items():
            surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            pixel_art._STAGE_ROUTE_PANORAMA_CACHE.clear()
            with (
                self.subTest(theme=theme),
                patch.object(pixel_art, "_draw_parked_car") as parked_car,
                patch.object(pixel_art, "_draw_ambient_vehicle") as ambient_vehicle,
            ):
                draw_stage_background(surface, 0, stage_width, theme=theme)
                parked_car.assert_not_called()
                ambient_vehicle.assert_not_called()

    def test_physical_sedan_uses_the_same_height_ruler_as_dave(self) -> None:
        route = pixel_art._location_route("sprouts_el_cilantro")
        self.assertIsNotNone(route)
        feature = route["physical_scene_objects"][0]
        sprite = pixel_art._physical_scene_object_sprite(feature)
        surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT), pygame.SRCALPHA)
        dave = pixel_art.draw_player(
            surface,
            180,
            300,
            0,
            1,
            "idle",
            "black_dave",
            0,
            (217, 72, 64),
        )
        expected = round(
            float(feature["physical_height_m"])
            / 1.8
            * dave.height
        )

        self.assertEqual(dave.height, 134)
        self.assertEqual(sprite.get_height(), expected)
        self.assertGreaterEqual(sprite.get_height() / dave.height, 0.70)
        self.assertLessEqual(sprite.get_height() / dave.height, 0.90)

    def test_physical_sedan_has_two_level_wheel_contacts_and_a_shadow(self) -> None:
        route = pixel_art._location_route("sprouts_el_cilantro")
        self.assertIsNotNone(route)
        feature = route["physical_scene_objects"][0]
        sprite = pixel_art._physical_scene_object_sprite(feature)
        contact_x = [
            x
            for x in range(sprite.get_width())
            if any(
                sprite.get_at((x, y)).a > 16
                for y in range(max(0, sprite.get_height() - 4), sprite.get_height())
            )
        ]
        groups: list[list[int]] = []
        for x in contact_x:
            if not groups or x > groups[-1][1] + 1:
                groups.append([x, x])
            else:
                groups[-1][1] = x
        substantial_groups = [
            group for group in groups if group[1] - group[0] + 1 >= 4
        ]
        self.assertGreaterEqual(len(substantial_groups), 2)

        surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT), pygame.SRCALPHA)
        rect = pixel_art.draw_physical_scene_object(
            surface,
            320,
            220,
            feature,
        )
        self.assertEqual(rect.midbottom, (320, 220))
        self.assertGreater(surface.get_at((320, 222)).a, 0)

    def test_ambient_planes_move_independently_at_pixel_aligned_rates(self) -> None:
        first = {plane: pixel_art._ambient_plane_offset(400, plane) for plane in ("far", "mid", "world")}
        second = {plane: pixel_art._ambient_plane_offset(500, plane) for plane in ("far", "mid", "world")}
        shifts = {plane: second[plane] - first[plane] for plane in first}
        self.assertEqual(shifts, {"far": -46, "mid": -74, "world": -100})

    def test_moving_travel_panels_render_distinct_pixel_aligned_progress_frames(self) -> None:
        panels = [
            panel
            for panel in pixel_art._location_manifest()["travel_panels"]
            if panel["presentation"] == "moving_panel"
        ]
        self.assertGreaterEqual(len(panels), 2)
        for panel in panels:
            first = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            middle = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            last = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            with self.subTest(panel=panel["id"]):
                pixel_art.draw_location_travel_panel(first, panel, 0.0)
                pixel_art.draw_location_travel_panel(middle, panel, 0.5)
                pixel_art.draw_location_travel_panel(last, panel, 1.0)
                self.assertEqual(
                    len(
                        {
                            pygame.image.tobytes(first, "RGB"),
                            pygame.image.tobytes(middle, "RGB"),
                            pygame.image.tobytes(last, "RGB"),
                        }
                    ),
                    3,
                )
                offsets = [
                    pixel_art._travel_panel_camera_x(panel, progress, DESIGN_WIDTH)
                    for progress in (0.0, 0.5, 1.0)
                ]
                self.assertEqual(offsets, sorted(offsets))
                self.assertTrue(all(isinstance(offset, int) for offset in offsets))

    def test_procedural_stage_fallback_survives_missing_optional_panels(self) -> None:
        # Seed the exact cache keys as failed loads without moving real assets.
        saved = dict(pixel_art._STAGE_PANEL_CACHE)
        saved_world = dict(pixel_art._STAGE_PANEL_WORLD_CACHE)
        saved_bands = dict(pixel_art._STAGE_PANEL_BAND_CACHE)
        saved_chapter = dict(pixel_art._STAGE_CHAPTER_PANEL_CACHE)
        try:
            pixel_art._STAGE_PANEL_CACHE.clear()
            pixel_art._STAGE_PANEL_WORLD_CACHE.clear()
            pixel_art._STAGE_PANEL_BAND_CACHE.clear()
            pixel_art._STAGE_CHAPTER_PANEL_CACHE.clear()
            for name in pixel_art._STAGE_PANEL_FILES:
                pixel_art._STAGE_PANEL_CACHE[(name, 731, 400)] = None
            surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
            rect = draw_stage_background(surface, 1700, 4200)
            self.assertEqual(rect, surface.get_rect())
            self.assertNotEqual(surface.get_at((12, 20)), surface.get_at((12, 330)))
            self.assertGreater(len({tuple(surface.get_at((x, 220))) for x in range(0, DESIGN_WIDTH, 20)}), 4)
        finally:
            pixel_art._STAGE_PANEL_CACHE.clear()
            pixel_art._STAGE_PANEL_CACHE.update(saved)
            pixel_art._STAGE_PANEL_WORLD_CACHE.clear()
            pixel_art._STAGE_PANEL_WORLD_CACHE.update(saved_world)
            pixel_art._STAGE_PANEL_BAND_CACHE.clear()
            pixel_art._STAGE_PANEL_BAND_CACHE.update(saved_bands)
            pixel_art._STAGE_CHAPTER_PANEL_CACHE.clear()
            pixel_art._STAGE_CHAPTER_PANEL_CACHE.update(saved_chapter)

    def test_landmark_panels_track_world_camera_one_to_one(self) -> None:
        anchors = pixel_art._stage_panel_world_anchors(3600, 731)
        self.assertEqual(anchors, {"pharmacy": 0, "overpass": 1152, "hall": 2869})
        for world_x in anchors.values():
            with self.subTest(world_x=world_x):
                first_screen_x = world_x - 400
                second_screen_x = world_x - 500
                self.assertEqual(second_screen_x - first_screen_x, -100)

    def test_camera_shake_moves_backdrop_floor_as_one_world_layer(self) -> None:
        stable = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
        shaken = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
        draw_stage_background(stable, 1200, 3600)
        draw_stage_background(shaken, 1200, 3600, 3.0)
        stable_overlap = stable.subsurface((0, 0, DESIGN_WIDTH, DESIGN_HEIGHT - 3))
        shaken_overlap = shaken.subsurface((0, 3, DESIGN_WIDTH, DESIGN_HEIGHT - 3))
        self.assertEqual(
            pygame.image.tobytes(stable_overlap, "RGB"),
            pygame.image.tobytes(shaken_overlap, "RGB"),
        )

    def test_camera_shake_overscans_layered_route_with_live_atmosphere(self) -> None:
        theme = "seven_eleven_underpass"
        stage_width = pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS[theme]
        atmosphere = {
            "time_seconds": 7.25,
            "seed": 17,
            "cloud_phases": (0.2, 0.4),
            "wind": {"speed": 2.0, "direction": 0.0},
            "transition_progress": 1.0,
            "current_profile_id": "i8_underpass_dimming",
            "target_profile_id": "i8_underpass_dimming",
            "parallax_factors": (0.15, 0.3, 1.0),
        }
        stable = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
        positive = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
        negative = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
        draw_stage_background(stable, 760, stage_width, theme=theme, atmosphere=atmosphere)
        draw_stage_background(positive, 760, stage_width, 4.0, theme=theme, atmosphere=atmosphere)
        draw_stage_background(negative, 760, stage_width, -4.0, theme=theme, atmosphere=atmosphere)

        self.assertEqual(
            pygame.image.tobytes(stable.subsurface((0, 0, DESIGN_WIDTH, DESIGN_HEIGHT - 4)), "RGB"),
            pygame.image.tobytes(positive.subsurface((0, 4, DESIGN_WIDTH, DESIGN_HEIGHT - 4)), "RGB"),
        )
        self.assertEqual(
            pygame.image.tobytes(stable.subsurface((0, 4, DESIGN_WIDTH, DESIGN_HEIGHT - 4)), "RGB"),
            pygame.image.tobytes(negative.subsurface((0, 0, DESIGN_WIDTH, DESIGN_HEIGHT - 4)), "RGB"),
        )
        stable_top = pygame.image.tobytes(stable.subsurface((0, 0, DESIGN_WIDTH, 1)), "RGB")
        stable_bottom = pygame.image.tobytes(
            stable.subsurface((0, DESIGN_HEIGHT - 1, DESIGN_WIDTH, 1)),
            "RGB",
        )
        for y in range(4):
            self.assertEqual(
                pygame.image.tobytes(positive.subsurface((0, y, DESIGN_WIDTH, 1)), "RGB"),
                stable_top,
            )
            self.assertEqual(
                pygame.image.tobytes(
                    negative.subsurface((0, DESIGN_HEIGHT - 1 - y, DESIGN_WIDTH, 1)),
                    "RGB",
                ),
                stable_bottom,
            )
        self.assertNotEqual(negative.get_at((DESIGN_WIDTH // 2, DESIGN_HEIGHT - 1)), pygame.Color(*pixel_art.SKY_TOP))

    def test_near_foreground_is_separate_occluding_layer_and_shares_camera_shake(self) -> None:
        stable = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT), pygame.SRCALPHA)
        shaken = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT), pygame.SRCALPHA)
        before = pygame.image.tobytes(stable, "RGBA")
        stage_width = pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS["seven_eleven_underpass"]
        draw_stage_foreground(stable, 760, stage_width, theme="seven_eleven_underpass")
        draw_stage_foreground(shaken, 760, stage_width, 3.0, theme="seven_eleven_underpass")
        self.assertNotEqual(before, pygame.image.tobytes(stable, "RGBA"))
        self.assertTrue(
            any(
                stable.get_at((x, y)).a
                for x in range(0, DESIGN_WIDTH, 8)
                for y in range(330, DESIGN_HEIGHT, 2)
            )
        )
        self.assertEqual(
            pygame.image.tobytes(stable.subsurface((0, 0, DESIGN_WIDTH, DESIGN_HEIGHT - 3)), "RGBA"),
            pygame.image.tobytes(shaken.subsurface((0, 3, DESIGN_WIDTH, DESIGN_HEIGHT - 3)), "RGBA"),
        )

    def test_level_one_authored_near_plate_loads_and_moves_independently(self) -> None:
        theme = "sprouts_el_cilantro"
        stage_width = pixel_art._CHAPTER_ONE_THEME_ROUTE_WIDTHS[theme]
        route = pixel_art._location_route(theme)
        self.assertIsNotNone(route)
        assert route is not None
        saved_art = dict(pixel_art._LOCATION_ART_CACHE)
        saved_frames = dict(pixel_art._STAGE_BACKGROUND_FRAME_CACHE)
        saved_worlds = dict(pixel_art._STAGE_WORLD_CACHE)
        saved_chunk_surfaces = dict(pixel_art._STAGE_WORLD_SURFACE_CACHE)
        saved_global_surfaces = dict(pixel_art._STAGE_WORLD_GLOBAL_SURFACE_CACHE)
        try:
            pixel_art._LOCATION_ART_CACHE.clear()
            pixel_art._STAGE_BACKGROUND_FRAME_CACHE.clear()
            pixel_art._STAGE_WORLD_CACHE.clear()
            pixel_art._STAGE_WORLD_SURFACE_CACHE.clear()
            pixel_art._STAGE_WORLD_GLOBAL_SURFACE_CACHE.clear()
            first = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT), pygame.SRCALPHA)
            second = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT), pygame.SRCALPHA)
            with (
                patch.object(pixel_art.pygame.image, "load", wraps=pygame.image.load) as loader,
                patch.object(pixel_art, "_draw_foreground_framing") as fallback,
            ):
                draw_stage_foreground(first, 1250, stage_width, theme=theme)
                draw_stage_foreground(second, 1350, stage_width, theme=theme)
            requested = [Path(call.args[0]).name for call in loader.call_args_list]
            self.assertTrue(any("chunk_" in name and "near_occluder" in name for name in requested))
            self.assertNotIn(Path(str(route["main_panorama_asset"])).name, requested)
            self.assertNotIn(Path(str(route["far_asset"])).name, requested)
            self.assertNotIn(Path(str(route["near_asset"])).name, requested)
            fallback.assert_not_called()

            layer = pixel_art._location_art_layers(theme)["near"]
            assert layer is not None
            visible = layer.get_bounding_rect(min_alpha=1)
            self.assertGreaterEqual(visible.top, 300)
            self.assertTrue(
                any(
                    first.get_at((x, y)).a
                    for x in range(0, DESIGN_WIDTH, 8)
                    for y in range(300, DESIGN_HEIGHT, 2)
                )
            )

            near_first = pixel_art._chapter_one_near_layer_offset(first, 1250, theme)
            near_second = pixel_art._chapter_one_near_layer_offset(second, 1350, theme)
            mid_first = pixel_art._chapter_one_stage_layer_offsets(first, 1250, theme)["main"]
            mid_second = pixel_art._chapter_one_stage_layer_offsets(second, 1350, theme)["main"]
            self.assertEqual(mid_second - mid_first, -100)
            self.assertLessEqual(
                abs(near_first - mid_first),
                int(route["near_max_offset"]),
            )
            self.assertLessEqual(
                abs(near_second - mid_second),
                int(route["near_max_offset"]),
            )
            self.assertTrue(all(isinstance(offset, int) for offset in (near_first, near_second)))
        finally:
            pixel_art._LOCATION_ART_CACHE.clear()
            pixel_art._LOCATION_ART_CACHE.update(saved_art)
            pixel_art._STAGE_BACKGROUND_FRAME_CACHE.clear()
            pixel_art._STAGE_BACKGROUND_FRAME_CACHE.update(saved_frames)
            pixel_art._STAGE_WORLD_CACHE.clear()
            pixel_art._STAGE_WORLD_CACHE.update(saved_worlds)
            pixel_art._STAGE_WORLD_SURFACE_CACHE.clear()
            pixel_art._STAGE_WORLD_SURFACE_CACHE.update(saved_chunk_surfaces)
            pixel_art._STAGE_WORLD_GLOBAL_SURFACE_CACHE.clear()
            pixel_art._STAGE_WORLD_GLOBAL_SURFACE_CACHE.update(saved_global_surfaces)

    def test_player_states_render(self) -> None:
        cases = [
            ("black_dave", "idle", 0, "#ef5547"),
            ("black_dave", "light", 8, "#ef5547"),
            ("black_dave", "air_attack", 10, "#ef5547"),
            ("black_dave", "downed", 11, "#ef5547"),
            ("black_dave", "special", 16, "#ef5547"),
            ("shelly", "idle", 130, "#ca4f83"),  # deterministic butane-refill frame
            ("shelly", "light", 6, "#ca4f83"),
            ("shelly", "super", 8, "#ca4f83"),
            ("shelly", "downed", 12, "#ca4f83"),
        ]
        for character, state, frame, color in cases:
            with self.subTest(character=character, state=state):
                surface = pygame.Surface((160, 100), pygame.SRCALPHA)
                rect = draw_player(surface, 80, 88, 0, -1, state, character, frame, color)
                self.assertGreaterEqual(rect.w, 18)
                self.assertGreaterEqual(rect.h, 18 if state == "downed" else 55)
                self.assertTrue(_has_nontransparent_pixels(surface, rect))
                sprite_colors = {
                    tuple(surface.get_at((x, y)))
                    for x in range(surface.get_width())
                    for y in range(surface.get_height())
                    if surface.get_at((x, y)).a
                }
                self.assertGreaterEqual(len(sprite_colors), 14)

    def test_archetype_silhouettes_are_not_palette_swaps(self) -> None:
        renders: list[bytes] = []
        for kind in ("stick", "cart", "whip", "pipe"):
            surface = pygame.Surface((180, 120), pygame.SRCALPHA)
            draw_enemy(surface, 90, 108, kind=kind, state="attack", frame=7)
            renders.append(pygame.image.tobytes(surface, "RGBA"))
        self.assertEqual(len(set(renders)), 4)

    def test_security_overlay_flames_and_comic_bubble_are_readable_pixel_layers(self) -> None:
        surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT), pygame.SRCALPHA)
        stick = pygame.Surface((180, 120), pygame.SRCALPHA)
        guard = pygame.Surface((180, 120), pygame.SRCALPHA)
        draw_enemy(stick, 90, 108, kind="stick", state="chase", frame=7)
        guard_rect = draw_enemy(guard, 90, 108, kind="security", state="chase", frame=7)
        flame_rect = draw_fist_flames(surface, 190, 286, facing=1, frame=9)
        bubble_rect = draw_comic_speech_bubble(surface, 325, 108, 168, 28, facing=-1)

        self.assertNotEqual(pygame.image.tobytes(stick, "RGBA"), pygame.image.tobytes(guard, "RGBA"))
        self.assertTrue(_has_nontransparent_pixels(guard, guard_rect))
        self.assertTrue(_has_nontransparent_pixels(surface, flame_rect))
        self.assertTrue(_has_nontransparent_pixels(surface, bubble_rect))

    def test_security_uniform_gear_is_readable_in_every_authored_phase(self) -> None:
        output = PROJECT_ROOT / "build" / "security_guard_qa.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        sheet = pygame.Surface((570, 1260))
        sheet.fill((19, 23, 33))
        font = pygame.font.Font(None, 22)

        for row, state in enumerate(ENEMY_STATES):
            clip = clip_for("stick", state)
            sample_phases = (0, clip.frame_count // 2, clip.frame_count - 1)
            for phase in range(clip.frame_count):
                tick = phase * clip.hold
                authored = sprite_atlas.enemy_frame("stick", state, tick)
                self.assertIsNotNone(authored)
                assert authored is not None
                uniform = pixel_art._security_uniform_frame(authored, state)
                lit = pixel_art._material_lit_sprite(uniform, "security_uniform")
                colors = [
                    lit.get_at((x, y))
                    for y in range(lit.get_height())
                    for x in range(lit.get_width())
                    if lit.get_at((x, y)).a
                ]
                navy = sum(color.b >= color.g + 6 and color.b >= color.r + 12 and color.r < 170 for color in colors)
                gold = sum(color.r >= 165 and color.g >= 115 and color.b <= 135 for color in colors)
                flashlight = sum(color.g >= 175 and color.b >= 180 and color.b >= color.r + 20 for color in colors)
                with self.subTest(state=state, phase=phase):
                    self.assertGreater(navy, len(colors) * 0.34, "the full silhouette must read as a dark uniform")
                    self.assertGreaterEqual(gold, 8, "badge, patches and belt buckle must remain visible")
                    self.assertGreaterEqual(flashlight, 3, "the duty flashlight lens must remain visible")
                    self.assertNotEqual(
                        pygame.image.tobytes(authored, "RGBA"),
                        pygame.image.tobytes(lit, "RGBA"),
                    )

            label = font.render(state.upper(), False, (222, 230, 242))
            sheet.blit(label, (8, row * 156 + 8))
            for column, phase in enumerate(sample_phases):
                facing = -1 if column == 1 else 1
                draw_enemy(
                    sheet,
                    105 + column * 180,
                    row * 156 + 146,
                    facing=facing,
                    kind="security",
                    state=state,
                    frame=phase * clip.hold,
                )

        pygame.image.save(sheet, output)
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 18_000)

    def test_material_lighting_is_localized_preserves_alpha_and_adds_both_form_sides(self) -> None:
        cases = (
            (sprite_atlas.player_frame("black_dave", "idle", 0), "dave"),
            (sprite_atlas.player_frame("shelly", "walk", 7), "shelly"),
            (sprite_atlas.chief_frame("move", 5), "fur"),
            (sprite_atlas.enemy_frame("stick", "attack", 6), "enemy_cloth"),
            (sprite_atlas.enemy_frame("cart", "walk", 9), "enemy_cloth"),
            (sprite_atlas.enemy_frame("whip", "hurt", 6), "enemy_cloth"),
            (sprite_atlas.enemy_frame("pipe", "charge", 6), "enemy_cloth"),
            (sprite_atlas.boss_frame("pump_attack", 6), "denim"),
            (sprite_atlas.jerry_frame("talk", 6), "jerry"),
            (sprite_atlas.victory_frame(3), "celebration"),
            (sprite_atlas.sunset_frame(4), "celebration"),
        )
        for original, profile in cases:
            self.assertIsNotNone(original)
            assert original is not None
            lit = pixel_art._material_lit_sprite(original, profile)
            original_mask = pygame.mask.from_surface(original)
            lit_mask = pygame.mask.from_surface(lit)
            self.assertEqual(original_mask.count(), lit_mask.count())
            self.assertEqual(original_mask.overlap_area(lit_mask, (0, 0)), original_mask.count())
            brighter = darker = changed = 0
            brighter_positions: list[int] = []
            darker_positions: list[int] = []
            for y in range(original.get_height()):
                for x in range(original.get_width()):
                    before = original.get_at((x, y))
                    if not before.a:
                        continue
                    after = lit.get_at((x, y))
                    before_luma = before.r * 3 + before.g * 4 + before.b
                    after_luma = after.r * 3 + after.g * 4 + after.b
                    if after != before:
                        changed += 1
                    if after_luma >= before_luma + 16:
                        brighter += 1
                        brighter_positions.append(x + y)
                    if after_luma <= before_luma - 16:
                        darker += 1
                        darker_positions.append(x + y)
            with self.subTest(profile=profile):
                self.assertGreater(brighter, 8)
                self.assertGreater(darker, 8)
                self.assertGreater(changed, original_mask.count() * 0.015)
                self.assertLess(changed, original_mask.count() * 0.52, "lighting must remain a localized edge/form pass")
                self.assertLess(
                    sum(brighter_positions) / len(brighter_positions),
                    sum(darker_positions) / len(darker_positions),
                    "the shared key light must remain above/left of the contact side",
                )

    def test_items_projectiles_and_effects_have_material_shadow_and_specular_ranges(self) -> None:
        painters = (
            ("bb_pickup", lambda canvas: draw_pickup(canvas, 80, 92, kind="bb_ammo", frame=2)),
            ("butane_pickup", lambda canvas: draw_pickup(canvas, 80, 92, kind="super_butane", frame=1)),
            ("bb_projectile", lambda canvas: draw_projectile(canvas, 80, 64, kind="bb", frame=2)),
            ("pipe_projectile", lambda canvas: draw_projectile(canvas, 80, 64, kind="pipe", frame=1)),
            ("rock_projectile", lambda canvas: draw_projectile(canvas, 80, 64, kind="rock", frame=3)),
            ("flame_projectile", lambda canvas: draw_projectile(canvas, 80, 64, kind="flame", frame=2)),
            ("hit", lambda canvas: draw_effect(canvas, 80, 64, kind="hit", frame=2, radius=28)),
            ("shockwave", lambda canvas: draw_effect(canvas, 80, 64, kind="shockwave", frame=2, radius=28)),
            ("flame_trail", lambda canvas: draw_effect(canvas, 80, 64, kind="flame_trail_right", frame=2, radius=28)),
            ("flame_burst", lambda canvas: draw_effect(canvas, 80, 64, kind="flame_burst", frame=2, radius=28)),
            ("scorch", lambda canvas: draw_effect(canvas, 80, 64, kind="scorch", frame=2, radius=28)),
            ("enemy_fire", lambda canvas: draw_effect(canvas, 80, 84, kind="enemy_fire", frame=2, radius=28)),
            ("ember", lambda canvas: draw_effect(canvas, 80, 64, kind="ember", frame=2, radius=12)),
            ("chief_super", lambda canvas: draw_effect(canvas, 80, 64, kind="chief_super", frame=2, radius=28)),
        )
        for label, painter in painters:
            canvas = pygame.Surface((180, 130), pygame.SRCALPHA)
            rect = painter(canvas)
            colors = [
                canvas.get_at((x, y))
                for y in range(canvas.get_height())
                for x in range(canvas.get_width())
                if canvas.get_at((x, y)).a
            ]
            lumas = [(color.r * 3 + color.g * 4 + color.b) / 8.0 for color in colors]
            with self.subTest(label=label):
                self.assertGreater(rect.w * rect.h, 0)
                self.assertGreaterEqual(len({tuple(color) for color in colors}), 3)
                self.assertLess(min(lumas), 105, "deep form/contact shade must remain present")
                self.assertGreater(max(lumas), 172, "rim or material specular must remain present")
                self.assertGreater(max(lumas) - min(lumas), 95)

    def test_pickups_have_deterministic_moving_specular_glints(self) -> None:
        for kind in ("bb_ammo", "super_butane"):
            early = pygame.Surface((96, 96), pygame.SRCALPHA)
            late = pygame.Surface((96, 96), pygame.SRCALPHA)
            draw_pickup(early, 48, 70, kind=kind, frame=0)
            draw_pickup(late, 48, 70, kind=kind, frame=8)
            with self.subTest(kind=kind):
                self.assertNotEqual(pygame.image.tostring(early, "RGBA"), pygame.image.tostring(late, "RGBA"))

        canvas = pygame.Surface((96, 96), pygame.SRCALPHA)
        rect = draw_effect(canvas, 48, 48, kind="pickup", frame=3, color=(111, 255, 190), radius=10)
        self.assertGreater(rect.w, 0)
        self.assertGreaterEqual(len({tuple(canvas.get_at((x, y))) for y in range(96) for x in range(96) if canvas.get_at((x, y)).a}), 3)

    def test_material_shading_qa_covers_actors_items_projectiles_and_effects(self) -> None:
        output = PROJECT_ROOT / "build" / "material_shading_qa.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        sheet = pygame.Surface((1050, 530))
        sheet.fill((22, 26, 37))
        font = pygame.font.Font(None, 24)
        sheet.blit(font.render("MATERIAL-AWARE SUNSET KEY / COOL CONTACT SHADOW", False, (245, 222, 170)), (22, 14))
        actor_specs = (
            ("DAVE", lambda x: draw_player(sheet, x, 230, 0, 1, "idle", "black_dave", 5, "#e95b49")),
            ("SHELLY", lambda x: draw_player(sheet, x, 230, 0, 1, "walk", "shelly", 7, "#c95584")),
            ("CHIEF", lambda x: draw_chief(sheet, x, 230, 0, 1, "move", 5)),
            ("STICK", lambda x: draw_enemy(sheet, x, 230, kind="stick", state="attack", frame=6)),
            ("GUARD", lambda x: draw_enemy(sheet, x, 230, kind="security", state="attack", frame=6)),
            ("CART", lambda x: draw_enemy(sheet, x, 230, kind="cart", state="walk", frame=9)),
            ("WHIP", lambda x: draw_enemy(sheet, x, 230, kind="whip", state="hurt", frame=6)),
            ("PIPE", lambda x: draw_enemy(sheet, x, 230, kind="pipe", state="charge", frame=6)),
            ("COUCH", lambda x: draw_boss(sheet, x, 230, state="pump_attack", frame=6)),
        )
        for index, (label, painter) in enumerate(actor_specs):
            actor_x = 60 + index * 115
            painter(actor_x)
            sheet.blit(font.render(label, False, (208, 217, 231)), (actor_x - 30, 245))

        draw_pickup(sheet, 105, 455, kind="bb_ammo", frame=2)
        draw_pickup(sheet, 165, 455, kind="butane", frame=1)
        draw_projectile(sheet, 245, 420, 0, 1, "bb", 2)
        draw_projectile(sheet, 330, 420, 0, 1, "pipe", 1)
        draw_projectile(sheet, 410, 420, 0, 1, "rock", 3)
        draw_projectile(sheet, 490, 420, 0, 1, "flame", 2)
        effect_specs = (("hit", 590), ("shockwave", 690), ("flame_burst", 800), ("enemy_fire", 920))
        for kind, effect_x in effect_specs:
            draw_effect(sheet, effect_x, 420, kind=kind, frame=3, radius=32)
            sheet.blit(font.render(kind.upper(), False, (208, 217, 231)), (effect_x - 38, 475))

        pygame.image.save(sheet, output)
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 25_000)

    def test_chief_enemy_boss_projectile_and_effect_contracts(self) -> None:
        surface = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT), pygame.SRCALPHA)
        rects = [
            draw_chief(surface, 72, 285, 0, 1, "super", 7),
            draw_enemy(surface, 145, 285, kind="stick", state="attack", frame=4),
            draw_enemy(surface, 225, 285, kind="cart", state="charge", frame=8),
            draw_enemy(surface, 305, 285, kind="whip", state="attack", frame=12),
            draw_enemy(surface, 380, 285, kind="pipe", state="throw", frame=16),
            draw_boss(surface, 475, 285, state="laugh", frame=9),
            draw_boss(surface, 565, 285, state="pump_attack", frame=4),
            draw_projectile(surface, 120, 145, 0, 1, "pipe", 1),
            draw_projectile(surface, 160, 145, 0, -1, "flame", 2),
            draw_projectile(surface, 190, 145, 0, 1, "bb", 2),
            draw_pickup(surface, 205, 285, kind="bb_ammo", frame=2),
            draw_effect(surface, 220, 145, kind="hit", frame=1),
            draw_effect(surface, 285, 145, kind="shockwave", frame=4),
            draw_effects(surface, 355, 145, kind="chief_super", frame=2),
        ]
        self.assertTrue(all(rect.w > 0 and rect.h > 0 for rect in rects))
        self.assertTrue(all(_has_nontransparent_pixels(surface, rect) for rect in rects))

    def test_couch_reads_shorter_and_wider_than_black_dave(self) -> None:
        surface = pygame.Surface((400, 240), pygame.SRCALPHA)
        dave = draw_player(surface, 100, 220, 0, 1, "idle", "black_dave", 0, "#ef5547")
        couch = draw_boss(surface, 280, 220, 0, 1, "idle", 0)
        self.assertLess(couch.h, dave.h)
        self.assertGreater(couch.w, dave.w)

    def test_fast_player_cels_leave_directional_motion_echo(self) -> None:
        trail = pygame.Surface((400, 240), pygame.SRCALPHA)
        clean = pygame.Surface((400, 240), pygame.SRCALPHA)
        draw_player(trail, 150, 220, 0, 1, "attack_3", "black_dave", 5, "#ef5547")
        with patch("src.pixel_art._draw_motion_echo"):
            draw_player(clean, 150, 220, 0, 1, "attack_3", "black_dave", 5, "#ef5547")

        self.assertGreater(
            pygame.mask.from_surface(trail).count(),
            pygame.mask.from_surface(clean).count(),
            "high-speed authored cels should leave a readable trailing silhouette",
        )

    def test_action_ribbons_are_phase_driven_and_state_specific(self) -> None:
        early = pygame.Surface((180, 120), pygame.SRCALPHA)
        late = pygame.Surface((180, 120), pygame.SRCALPHA)
        idle = pygame.Surface((180, 120), pygame.SRCALPHA)
        pixel_art._draw_action_ribbon(early, 90, 100, 0, 1, "attack_3", 90, 0)
        pixel_art._draw_action_ribbon(late, 90, 100, 0, 1, "attack_3", 90, 3)
        pixel_art._draw_action_ribbon(idle, 90, 100, 0, 1, "idle", 90, 0)
        self.assertNotEqual(pygame.image.tobytes(early, "RGBA"), pygame.image.tobytes(late, "RGBA"))
        self.assertEqual(pygame.mask.from_surface(idle).count(), 0)

    def test_locomotion_footfall_ticks_are_phase_locked(self) -> None:
        early = pygame.Surface((180, 120), pygame.SRCALPHA)
        late = pygame.Surface((180, 120), pygame.SRCALPHA)
        idle = pygame.Surface((180, 120), pygame.SRCALPHA)
        pixel_art._draw_footfall_ticks(early, 90, 100, 0, 1, "walk", 1)
        pixel_art._draw_footfall_ticks(late, 90, 100, 0, 1, "walk", 13)
        pixel_art._draw_footfall_ticks(idle, 90, 100, 0, 1, "idle", 1)
        self.assertGreater(pygame.mask.from_surface(early).count(), 0)
        self.assertEqual(pygame.image.tobytes(early, "RGBA"), pygame.image.tobytes(late, "RGBA"))
        self.assertEqual(pygame.mask.from_surface(idle).count(), 0)

    def test_hero_stride_accents_follow_real_contact_and_passing_beats(self) -> None:
        contact = pygame.Surface((180, 120), pygame.SRCALPHA)
        passing = pygame.Surface((180, 120), pygame.SRCALPHA)
        pixel_art._draw_stride_accents(contact, 90, 100, 0, 1, "walk", 0)
        pixel_art._draw_stride_accents(passing, 90, 100, 0, 1, "walk", 6)
        self.assertNotEqual(
            pygame.image.tobytes(contact, "RGBA"),
            pygame.image.tobytes(passing, "RGBA"),
            "stride accents should distinguish heel contact from passing",
        )

    def test_hero_stride_accents_mirror_with_facing(self) -> None:
        right = pygame.Surface((180, 120), pygame.SRCALPHA)
        left = pygame.Surface((180, 120), pygame.SRCALPHA)
        pixel_art._draw_stride_accents(right, 90, 100, 0, 1, "walk", 0)
        pixel_art._draw_stride_accents(left, 90, 100, 0, -1, "walk", 0)
        self.assertNotEqual(
            pygame.image.tobytes(right, "RGBA"),
            pygame.image.tobytes(left, "RGBA"),
            "contact effects must travel with the facing direction",
        )

    def test_hero_stride_bob_is_integer_and_periodic(self) -> None:
        self.assertEqual(pixel_art._walk_bob(0), pixel_art._walk_bob(24))
        self.assertEqual(pixel_art._walk_bob(8), -2)
        self.assertEqual(pixel_art._walk_bob(16), -1)

    def test_cart_return_props_have_deterministic_micro_motion(self) -> None:
        frame_zero = pygame.Surface((180, 140), pygame.SRCALPHA)
        frame_one = pygame.Surface((180, 140), pygame.SRCALPHA)
        pixel_art.draw_stage_prop(frame_zero, 90, 120, "cart_return", frame=0)
        pixel_art.draw_stage_prop(frame_one, 90, 120, "cart_return", frame=1)

        self.assertNotEqual(
            pygame.image.tobytes(frame_zero, "RGBA"),
            pygame.image.tobytes(frame_one, "RGBA"),
            "cart wheels and metal glint should animate without changing prop bounds",
        )

        planter_zero = pygame.Surface((180, 140), pygame.SRCALPHA)
        planter_late = pygame.Surface((180, 140), pygame.SRCALPHA)
        pixel_art.draw_stage_prop(planter_zero, 90, 120, "planter", frame=0)
        pixel_art.draw_stage_prop(planter_late, 90, 120, "planter", frame=4)
        self.assertNotEqual(
            pygame.image.tobytes(planter_zero, "RGBA"),
            pygame.image.tobytes(planter_late, "RGBA"),
            "scenery foliage should carry deterministic wind motion and glints",
        )
        dumpster_zero = pygame.Surface((180, 140), pygame.SRCALPHA)
        dumpster_late = pygame.Surface((180, 140), pygame.SRCALPHA)
        pixel_art.draw_stage_prop(dumpster_zero, 90, 120, "dumpster", frame=0)
        pixel_art.draw_stage_prop(dumpster_late, 90, 120, "dumpster", frame=4)
        self.assertNotEqual(
            pygame.image.tobytes(dumpster_zero, "RGBA"),
            pygame.image.tobytes(dumpster_late, "RGBA"),
            "scenery metal should carry deterministic moving glints",
        )
        bollard_zero = pygame.Surface((180, 140), pygame.SRCALPHA)
        bollard_late = pygame.Surface((180, 140), pygame.SRCALPHA)
        pixel_art.draw_stage_prop(bollard_zero, 90, 120, "bollards", frame=0)
        pixel_art.draw_stage_prop(bollard_late, 90, 120, "bollards", frame=3)
        self.assertNotEqual(
            pygame.image.tobytes(bollard_zero, "RGBA"),
            pygame.image.tobytes(bollard_late, "RGBA"),
            "street props should carry deterministic reflector motion",
        )

    def test_charged_player_states_add_a_rim_without_changing_silhouette(self) -> None:
        authored = sprite_atlas.player_frame("black_dave", "super", 4)
        base = pixel_art._material_lit_sprite(authored, "dave")
        charged = pixel_art._state_rim_sprite(base, "super", (217, 72, 64))

        self.assertEqual(pygame.mask.from_surface(base).count(), pygame.mask.from_surface(charged).count())
        self.assertNotEqual(
            pygame.image.tobytes(base, "RGB"),
            pygame.image.tobytes(charged, "RGB"),
            "super state should carry a deliberate cool rim while preserving authored geometry",
        )

    def test_character_material_sheen_moves_without_changing_silhouette(self) -> None:
        authored = sprite_atlas.player_frame("shelly", "walk", 4)
        base = pixel_art._material_lit_sprite(authored, "shelly")
        early = pixel_art._character_sheen_sprite(base, "shelly", 0)
        late = pixel_art._character_sheen_sprite(base, "shelly", 3)

        self.assertEqual(pygame.mask.from_surface(base).count(), pygame.mask.from_surface(early).count())
        self.assertEqual(pygame.mask.from_surface(base).count(), pygame.mask.from_surface(late).count())
        self.assertNotEqual(
            pygame.image.tobytes(early, "RGB"),
            pygame.image.tobytes(late, "RGB"),
            "character material sheen should travel across the authored cel",
        )

    def test_character_identity_emblem_is_masked_and_profile_colored(self) -> None:
        authored = sprite_atlas.player_frame("black_dave", "idle", 4)
        base = pixel_art._material_lit_sprite(authored, "dave")
        dave = pixel_art._character_emblem_sprite(base, "dave", 0)
        shelly = pixel_art._character_emblem_sprite(base, "shelly", 0)
        self.assertEqual(pygame.mask.from_surface(base).count(), pygame.mask.from_surface(dave).count())
        self.assertEqual(pygame.mask.from_surface(base).count(), pygame.mask.from_surface(shelly).count())
        self.assertNotEqual(pygame.image.tobytes(dave, "RGB"), pygame.image.tobytes(shelly, "RGB"))

    def test_hit_sparks_emit_deterministic_trailing_shards(self) -> None:
        early = pygame.Surface((120, 100), pygame.SRCALPHA)
        late = pygame.Surface((120, 100), pygame.SRCALPHA)
        draw_effect(early, 60, 50, kind="hit", frame=0, radius=12)
        draw_effect(late, 60, 50, kind="hit", frame=4, radius=12)
        self.assertNotEqual(
            pygame.image.tobytes(early, "RGBA"),
            pygame.image.tobytes(late, "RGBA"),
            "hit sparks should carry readable phase-driven shard motion",
        )

    def test_bb_projectile_has_phase_driven_casing_glint(self) -> None:
        early = pygame.Surface((120, 100), pygame.SRCALPHA)
        late = pygame.Surface((120, 100), pygame.SRCALPHA)
        draw_projectile(early, 60, 50, kind="bb", frame=0)
        draw_projectile(late, 60, 50, kind="bb", frame=3)
        self.assertNotEqual(
            pygame.image.tobytes(early, "RGBA"),
            pygame.image.tobytes(late, "RGBA"),
            "BB projectiles should carry a readable moving casing glint",
        )

    def test_dust_impacts_add_a_phase_driven_ground_arc(self) -> None:
        early = pygame.Surface((120, 100), pygame.SRCALPHA)
        late = pygame.Surface((120, 100), pygame.SRCALPHA)
        draw_effect(early, 60, 50, kind="dust", frame=0, radius=18)
        draw_effect(late, 60, 50, kind="dust", frame=4, radius=18)
        self.assertNotEqual(pygame.image.tobytes(early, "RGBA"), pygame.image.tobytes(late, "RGBA"))

    def test_ko_preview_is_opt_in_and_never_replaces_dave_in_normal_play(self) -> None:
        normal_canvas = pygame.Surface((400, 240), pygame.SRCALPHA)
        preview_canvas = pygame.Surface((400, 240), pygame.SRCALPHA)
        with patch.dict(os.environ, {"FADES_KO_PREVIEW": ""}):
            normal = draw_player(normal_canvas, 100, 220, 0, 1, "idle", "black_dave", 0, "#ef5547")
        with patch.dict(os.environ, {"FADES_KO_PREVIEW": "1"}):
            preview = draw_player(preview_canvas, 100, 220, 0, 1, "idle", "black_dave", 0, "#ef5547")
        self.assertGreater(normal.h, preview.h)
        self.assertNotEqual(normal.size, preview.size)

    def test_render_full_preview(self) -> None:
        """Save one stable image that makes regressions easy to inspect by eye."""

        preview = pygame.Surface((DESIGN_WIDTH, DESIGN_HEIGHT))
        draw_stage_background(preview, 2110, 4200)
        draw_player(preview, 105, 294, 0, 1, "special", "black_dave", 12, "#e95b49")
        draw_player(preview, 185, 299, 0, 1, "idle", "shelly", 130, "#c95584")
        draw_chief(preview, 238, 306, 0, 1, "super", 6)
        draw_enemy(preview, 335, 287, kind="stick", state="attack", frame=4)
        draw_enemy(preview, 405, 302, kind="cart", state="charge", frame=9)
        draw_enemy(preview, 480, 283, kind="whip", state="attack", frame=3)
        draw_boss(preview, 565, 299, state="pump_attack", frame=5)
        draw_effect(preview, 278, 274, kind="shockwave", frame=5, radius=30)
        draw_projectile(preview, 298, 244, 4, 1, "pipe", 1)
        draw_projectile(preview, 315, 244, 4, 1, "bb", 1)
        draw_pickup(preview, 310, 304, kind="bb_ammo", frame=2)

        output = PROJECT_ROOT / "build" / "render_preview.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(preview, output)
        self.assertTrue(output.is_file())
        self.assertGreater(output.stat().st_size, 5_000)


if __name__ == "__main__":
    unittest.main()
