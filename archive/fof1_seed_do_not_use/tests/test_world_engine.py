"""Deterministic contracts for the reusable 2.5D beat-em-up world engine."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.world_engine import (  # noqa: E402
    BeatEmUpProjection,
    CameraDirector,
    CameraZone,
    ProjectionConfig,
    RectObstacle,
    StageGeometry,
    WalkableRegion,
    WorldPoint,
)


class ProjectionTests(unittest.TestCase):
    def test_orthographic_depth_changes_lane_height_not_size_or_angle(self) -> None:
        projection = BeatEmUpProjection(
            ProjectionConfig(floor_screen_y=200, pixels_per_depth=2, pixel_snap=False)
        )
        back = projection.project(WorldPoint(100, 10))
        front = projection.project(WorldPoint(100, 40))
        self.assertEqual(back.x, front.x)
        self.assertEqual((back.sprite_scale, front.sprite_scale), (1.0, 1.0))
        self.assertEqual((back.sprite_rotation_degrees, front.sprite_rotation_degrees), (0.0, 0.0))
        self.assertEqual((back.y, front.y), (220.0, 280.0))

    def test_elevation_is_independent_from_ground_depth_and_draw_order(self) -> None:
        projection = BeatEmUpProjection(
            ProjectionConfig(floor_screen_y=250, pixels_per_elevation=1.5, pixel_snap=False)
        )
        floor = projection.project(WorldPoint(50, 30, 0))
        airborne = projection.project(WorldPoint(50, 30, 20))
        self.assertEqual(floor.draw_order, airborne.draw_order)
        self.assertEqual(floor.y - airborne.y, 30.0)
        self.assertEqual(projection.depth_sort_key(WorldPoint(50, 30, 500))[0], 30)

    def test_oblique_projection_shears_scenery_without_stretching_billboards(self) -> None:
        projection = BeatEmUpProjection(
            ProjectionConfig(
                mode="oblique",
                screen_origin_x=3,
                floor_screen_y=200,
                pixels_per_world_x=2,
                pixels_per_depth=2,
                pixels_per_elevation=3,
                oblique_x_per_depth=0.5,
                pixel_snap=False,
            )
        )
        result = projection.project(WorldPoint(100, 10, 4), camera_x=20)
        self.assertEqual(result.xy, (168.0, 208.0))
        self.assertEqual(result.sprite_scale, 1.0)
        self.assertEqual(BeatEmUpProjection.sprite_scale_at_depth(10_000), 1.0)

    def test_oblique_orthographic_projection_shears_scenery_without_stretching_billboards(self) -> None:
        projection = BeatEmUpProjection(
            ProjectionConfig(
                mode="oblique_orthographic",
                screen_origin_x=3,
                floor_screen_y=200,
                pixels_per_world_x=2,
                pixels_per_depth=2,
                pixels_per_elevation=3,
                oblique_x_per_depth=0.5,
                pixel_snap=False,
            )
        )
        result = projection.project(WorldPoint(100, 10, 4), camera_x=20)
        self.assertEqual(result.xy, (168.0, 208.0))
        self.assertEqual(result.sprite_scale, 1.0)

    def test_depth_increase_moves_rendered_depth_forward_and_monotonic(self) -> None:
        projection = BeatEmUpProjection(
            ProjectionConfig(
                mode="oblique_orthographic",
                floor_screen_y=220,
                pixels_per_world_x=2.0,
                pixels_per_depth=1.5,
                pixel_snap=False,
            )
        )
        values = [projection.project(WorldPoint(40, depth)).y for depth in (200, 250, 310)]
        self.assertTrue(all(a < b for a, b in zip(values, values[1:])))

    def test_floor_unprojection_round_trips_orthographic_and_oblique_points(self) -> None:
        for mode, shear in (("orthographic", 0.0), ("oblique", -0.35)):
            with self.subTest(mode=mode):
                projection = BeatEmUpProjection(
                    ProjectionConfig(
                        mode=mode,
                        floor_screen_y=172,
                        pixels_per_world_x=1.25,
                        pixels_per_depth=0.8,
                        pixels_per_elevation=1.7,
                        oblique_x_per_depth=shear,
                        pixel_snap=False,
                    )
                )
                original = WorldPoint(431.25, 62.5, 17.0)
                screen = projection.project(
                    original,
                    camera_x=120,
                    camera_depth=7,
                    screen_shake=(2.5, -1.5),
                )
                restored = projection.unproject_floor(
                    screen.x,
                    screen.y,
                    elevation=original.elevation,
                    camera_x=120,
                    camera_depth=7,
                    screen_shake=(2.5, -1.5),
                )
                self.assertAlmostEqual(restored.x, original.x)
                self.assertAlmostEqual(restored.depth, original.depth)
                self.assertAlmostEqual(restored.elevation, original.elevation)

    def test_shadow_stays_on_floor_and_pixel_snap_is_stable(self) -> None:
        projection = BeatEmUpProjection(
            ProjectionConfig(floor_screen_y=100.4, pixels_per_elevation=2.0, pixel_snap=True)
        )
        actor = WorldPoint(10.45, 20.25, 12)
        projected = projection.project(actor)
        shadow = projection.project_shadow(actor)
        self.assertEqual(projected.pixel_xy, (10, 97))
        self.assertEqual(shadow.pixel_xy, (10, 121))
        self.assertEqual(shadow.elevation, 0.0)

    def test_projection_configuration_loads_from_plain_stage_data(self) -> None:
        config = ProjectionConfig.from_dict(
            {
                "mode": "oblique",
                "floor_screen_y": 222,
                "oblique_x_per_depth": 0.2,
                "pixel_snap": False,
                "comment": "unknown keys are ignored",
            }
        )
        self.assertEqual(config.mode, "oblique")
        self.assertEqual(config.floor_screen_y, 222)
        self.assertFalse(config.pixel_snap)


class StageGeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sloped = WalkableRegion(
            x_min=0,
            x_max=100,
            back_rail=((0, 10), (100, 30)),
            front_rail=((0, 80), (100, 100)),
            name="sloped street",
        )

    def test_piecewise_rails_create_a_variable_depth_floor(self) -> None:
        self.assertEqual(self.sloped.depth_bounds(0), (10.0, 80.0))
        self.assertEqual(self.sloped.depth_bounds(50), (20.0, 90.0))
        self.assertEqual(self.sloped.depth_bounds(100), (30.0, 100.0))

    def test_guard_rail_clamp_respects_actor_radius_and_elevation(self) -> None:
        clamped = self.sloped.clamp(WorldPoint(150, -20, 13), radius=5)
        self.assertEqual(clamped.x, 95)
        self.assertAlmostEqual(clamped.depth, 34.0)
        self.assertEqual(clamped.elevation, 13)
        self.assertTrue(self.sloped.contains(clamped, radius=5))

    def test_obstacles_reject_and_eject_floor_points(self) -> None:
        stage = StageGeometry(
            regions=(WalkableRegion.rectangular(0, 100, 0, 100),),
            obstacles=(RectObstacle(40, 60, 40, 60, "dumpster"),),
        )
        blocked = WorldPoint(50, 50, 8)
        self.assertFalse(stage.is_walkable(blocked))
        ejected = stage.clamp_to_walkable(blocked)
        self.assertTrue(stage.is_walkable(ejected))
        self.assertEqual(ejected.elevation, 8)
        self.assertTrue(ejected.x < 40 or ejected.x > 60 or ejected.depth < 40 or ejected.depth > 60)

    def test_nearest_region_is_selected_when_floor_has_separate_sections(self) -> None:
        stage = StageGeometry(
            regions=(
                WalkableRegion.rectangular(0, 100, 0, 80, name="left"),
                WalkableRegion.rectangular(150, 250, 20, 100, name="right"),
            )
        )
        self.assertEqual(stage.clamp_to_walkable(WorldPoint(140, 50)).x, 150)
        self.assertEqual(stage.x_bounds, (0.0, 250.0))

    def test_contiguous_region_handoff_is_not_an_invisible_radius_wall(self) -> None:
        stage = StageGeometry(
            regions=(
                WalkableRegion.rectangular(0, 100, 10, 90, name="left rail segment"),
                WalkableRegion.rectangular(100, 200, 12, 92, name="right rail segment"),
            )
        )
        result = stage.resolve_move(WorldPoint(82, 50), 42, 0, radius=7, max_step=4)
        self.assertAlmostEqual(result.x, 124.0)
        self.assertTrue(stage.is_walkable(result, radius=7))

    def test_second_street_edge_depths_auto_correct_across_rail_handoffs(self) -> None:
        stage = StageGeometry(
            regions=(
                WalkableRegion.rectangular(0, 900, 235, 326, name="town market"),
                WalkableRegion.rectangular(900, 1900, 231, 326, name="underpass"),
                WalkableRegion.rectangular(1900, 2850, 237, 328, name="gas row"),
                WalkableRegion.rectangular(2850, 3600, 229, 326, name="rise hall"),
            )
        )

        cases = (
            (WorldPoint(1885, 238), 40, 1925, 244),
            (WorldPoint(1915, 321), -40, 1875, 319),
            (WorldPoint(2835, 320), 40, 2875, 319),
            (WorldPoint(2865, 236), -40, 2825, 244),
        )
        for start, dx, expected_x, expected_depth in cases:
            with self.subTest(start=start, dx=dx):
                result = stage.resolve_move(start, dx, 0, radius=7, max_step=8)
                self.assertAlmostEqual(result.x, expected_x)
                self.assertAlmostEqual(result.depth, expected_depth)
                self.assertTrue(stage.is_walkable(result, radius=7))

    def test_seam_depth_correction_does_not_bypass_an_obstacle(self) -> None:
        stage = StageGeometry(
            regions=(
                WalkableRegion.rectangular(0, 100, 0, 100, name="left"),
                WalkableRegion.rectangular(100, 200, 6, 98, name="right"),
            ),
            obstacles=(RectObstacle(98, 102, 0, 100, "closed seam gate"),),
        )
        result = stage.resolve_move(WorldPoint(85, 93), 40, 0, radius=7, max_step=8)
        self.assertLess(result.x, 91)
        self.assertEqual(result.depth, 93)
        self.assertTrue(stage.is_walkable(result, radius=7))

    def test_seam_depth_correction_does_not_weaken_outer_stage_boundary(self) -> None:
        stage = StageGeometry(
            regions=(
                WalkableRegion.rectangular(0, 100, 0, 100, name="left"),
                WalkableRegion.rectangular(100, 200, 6, 98, name="right"),
            )
        )
        result = stage.resolve_move(WorldPoint(185, 91), 40, 0, radius=7, max_step=8)
        self.assertAlmostEqual(result.x, 193)
        self.assertEqual(result.depth, 91)
        self.assertTrue(stage.is_walkable(result, radius=7))

    def test_resolve_move_slides_around_a_rectangular_solid(self) -> None:
        stage = StageGeometry(
            regions=(WalkableRegion.rectangular(0, 120, 0, 100),),
            obstacles=(RectObstacle(40, 60, 40, 60),),
        )
        result = stage.resolve_move(WorldPoint(30, 35, 9), 55, 45, max_step=6)
        self.assertTrue(stage.is_walkable(result))
        self.assertGreater(result.x, 60)
        self.assertGreater(result.depth, 60)
        self.assertEqual(result.elevation, 9)

    def test_resolve_move_cannot_tunnel_through_a_thin_wall(self) -> None:
        stage = StageGeometry(
            regions=(WalkableRegion.rectangular(0, 200, 0, 100),),
            obstacles=(RectObstacle(50, 52, 0, 100, "closed gate"),),
        )
        result = stage.resolve_move(WorldPoint(40, 50), 80, 0, max_step=20)
        self.assertLess(result.x, 50)
        self.assertTrue(stage.is_walkable(result))

    def test_stage_geometry_loads_rectangles_rails_and_obstacles_from_data(self) -> None:
        stage = StageGeometry.from_dict(
            {
                "regions": [
                    {"name": "flat", "x_min": 0, "x_max": 100, "depth_min": 10, "depth_max": 90},
                    {
                        "name": "ramp",
                        "x_min": 100,
                        "x_max": 200,
                        "back_rail": [[100, 10], [200, 20]],
                        "front_rail": [[100, 90], [200, 100]],
                    },
                ],
                "obstacles": [
                    {"name": "hydrant", "x_min": 25, "x_max": 30, "depth_min": 30, "depth_max": 40}
                ],
            }
        )
        self.assertEqual(len(stage.regions), 2)
        self.assertEqual(stage.regions[1].depth_bounds(150), (15.0, 95.0))
        self.assertFalse(stage.is_walkable(WorldPoint(27, 35)))

    def test_invalid_crossed_rails_are_rejected_early(self) -> None:
        with self.assertRaises(ValueError):
            WalkableRegion(
                0,
                100,
                back_rail=((0, 10), (100, 90)),
                front_rail=((0, 80), (100, 20)),
            )


class CameraDirectorTests(unittest.TestCase):
    def make_camera(self, **overrides: object) -> CameraDirector:
        values: dict[str, object] = {
            "viewport_width": 100,
            "stage_min_x": 0,
            "stage_max_x": 500,
            "initial_x": 0,
            "dead_zone_left": 30,
            "dead_zone_right": 70,
            "follow_speed": 1000,
            "lookahead_seconds": 0,
            "max_lookahead": 0,
            "pixel_snap": False,
        }
        values.update(overrides)
        return CameraDirector(**values)

    def test_dead_zone_holds_camera_then_tracks_past_edge(self) -> None:
        camera = self.make_camera()
        self.assertEqual(camera.update(1.0, WorldPoint(50, 0)).x, 0)
        self.assertEqual(camera.update(1.0, WorldPoint(90, 0)).x, 20)
        self.assertEqual(camera.update(1.0, WorldPoint(10, 0)).x, 0)

    def test_coop_group_is_framed_by_its_outermost_players(self) -> None:
        camera = self.make_camera()
        view = camera.update(1.0, [20.0, 90.0])
        self.assertEqual(view.x, 5.0)

    def test_motion_lookahead_precedes_a_fast_player(self) -> None:
        camera = self.make_camera(lookahead_seconds=0.2, max_lookahead=30)
        view = camera.update(1.0, 60.0, velocity_x=100.0)
        self.assertEqual(view.x, 10.0)

    def test_zone_clamps_camera_and_overrides_follow_characteristics(self) -> None:
        zone = CameraZone(
            "alley fight",
            0,
            220,
            camera_min_x=10,
            camera_max_x=40,
            dead_zone_left=20,
            dead_zone_right=80,
            follow_speed=2000,
            priority=2,
        )
        camera = self.make_camera(zones=(zone,))
        view = camera.update(1.0, 190.0)
        self.assertEqual(view.zone_name, "alley fight")
        self.assertEqual(view.x, 40)

    def test_scripted_pan_has_deterministic_smoothstep_timing(self) -> None:
        camera = self.make_camera()
        camera.pan_to(100, 2.0)
        halfway = camera.update(1.0, 50.0)
        self.assertEqual(halfway.x, 50.0)
        self.assertTrue(halfway.scripted_pan)
        complete = camera.update(1.0, 50.0)
        self.assertEqual(complete.x, 100.0)
        self.assertFalse(complete.scripted_pan)

    def test_pan_to_world_uses_a_screen_anchor(self) -> None:
        camera = self.make_camera()
        camera.pan_to_world(180, 1.0, anchor_screen_x=40, easing="linear")
        self.assertEqual(camera.update(1.0, 0).x, 140)

    def test_encounter_lock_freezes_camera_until_cleared(self) -> None:
        camera = self.make_camera()
        self.assertEqual(camera.update(1.0, 90).x, 20)
        camera.set_encounter_lock()
        locked = camera.update(1.0, 300)
        self.assertTrue(locked.encounter_locked)
        self.assertEqual(locked.x, 20)
        camera.clear_encounter_lock()
        self.assertEqual(camera.update(1.0, 300).x, 230)

    def test_pixel_snap_keeps_render_camera_on_integer_pixels(self) -> None:
        camera = self.make_camera(follow_speed=3, pixel_snap=True)
        view = camera.update(0.1, 90)
        self.assertAlmostEqual(view.x, 0.3)
        self.assertEqual(view.render_x, 0.0)

    def test_screen_shake_is_deterministic_decays_and_does_not_move_simulation(self) -> None:
        left = self.make_camera(pixel_snap=False)
        right = self.make_camera(pixel_snap=False)
        for camera in (left, right):
            camera.trigger_shake(4, 1.0, vertical_strength=2, frequency=1, phase=0)
        left_view = left.update(0.25, 50)
        right_view = right.update(0.25, 50)
        self.assertEqual(left_view, right_view)
        self.assertAlmostEqual(left_view.shake_x, 3.0)
        self.assertEqual(left_view.x, 0.0)
        self.assertNotEqual(left_view.render_x, left_view.x)
        finished = left.update(0.75, 50)
        self.assertEqual((finished.shake_x, finished.shake_y), (0.0, 0.0))

    def test_entering_zone_can_trigger_a_scripted_pan(self) -> None:
        zones = (
            CameraZone("street", 0, 199),
            CameraZone("boss", 200, 500, entry_pan_seconds=1.0),
        )
        camera = self.make_camera(zones=zones)
        camera.update(0.1, 50)
        view = camera.update(0.25, 250)
        self.assertEqual(view.zone_name, "boss")
        self.assertTrue(view.scripted_pan)
        self.assertGreater(view.x, 0)

    def test_camera_loads_defaults_and_zones_from_plain_stage_data(self) -> None:
        camera = CameraDirector.from_dict(
            {
                "viewport_width": 100,
                "stage_min_x": 0,
                "stage_max_x": 600,
                "initial_x": 20,
                "defaults": {
                    "dead_zone_left": 25,
                    "dead_zone_right": 75,
                    "follow_speed": 500,
                    "pixel_snap": True,
                },
                "zones": [
                    {"name": "underpass", "x_min": 100, "x_max": 300, "camera_max_x": 180}
                ],
            }
        )
        view = camera.update(1, 250)
        self.assertEqual(view.zone_name, "underpass")
        self.assertEqual(view.x, 175)
        self.assertEqual(view.render_x, 175)

    def test_negative_delta_time_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.make_camera().update(-0.1, 50)


if __name__ == "__main__":
    unittest.main()
