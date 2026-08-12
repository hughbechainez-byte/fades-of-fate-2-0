"""Regression tests for the depth-aware belt-brawler combat engine."""

from __future__ import annotations

from pathlib import Path
import random
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.combat_engine import (  # noqa: E402
    AABB2,
    AttackRejectionReason,
    HitBox,
    HurtBox,
    PushBody,
    SpatialHash,
    StageBounds,
    StageObstacle,
    move_body,
    query_attack,
    query_attack_detailed,
    separate_push_bodies,
    sweep_move,
)


def _has_required_spacing(a: PushBody, b: PushBody, spacing: float = 0.0, tolerance: float = 0.02) -> bool:
    separated_x = abs(a.x - b.x) + tolerance >= a.half_width + b.half_width + spacing
    separated_depth = abs(a.depth - b.depth) + tolerance >= a.half_depth + b.half_depth + spacing
    return separated_x or separated_depth


class SpatialHashTests(unittest.TestCase):
    def test_broadphase_handles_negative_cells_updates_and_stable_order(self) -> None:
        boxes = [
            HurtBox("z", "enemy", -7.0, -3.0, half_width=2.0, half_depth=2.0),
            HurtBox("a", "enemy", 5.0, 2.0, half_width=2.0, half_depth=2.0),
            HurtBox("far", "enemy", 100.0, 100.0),
        ]
        broadphase = SpatialHash(cell_size=8.0)
        for box in reversed(boxes):
            broadphase.insert(box)
        found = broadphase.query(AABB2(-10.0, 10.0, -10.0, 10.0))
        self.assertEqual([box.entity_id for box in found], ["a", "z"])
        self.assertTrue(broadphase.remove("a"))
        self.assertFalse(broadphase.remove("missing"))
        self.assertEqual([box.entity_id for box in broadphase.query(AABB2(-10.0, 10.0, -10.0, 10.0))], ["z"])

    def test_rebuild_uses_current_float_positions(self) -> None:
        bodies = [PushBody("p1", 3.25, 2.5), PushBody("p2", 900.0, 900.0)]
        broadphase = SpatialHash(32.0)
        broadphase.rebuild(bodies)
        self.assertEqual([body.entity_id for body in broadphase.query(AABB2(0, 10, 0, 10))], ["p1"])
        bodies[1].x = 5.5
        bodies[1].depth = 4.25
        broadphase.rebuild(bodies)
        self.assertEqual([body.entity_id for body in broadphase.query(AABB2(0, 10, 0, 10))], ["p1", "p2"])


class SweptMovementTests(unittest.TestCase):
    def test_fast_diagonal_motion_cannot_tunnel_and_slides_along_obstacle(self) -> None:
        body = PushBody("dave", 0.0, 0.0, half_width=1.0, half_depth=1.0, height=4.0)
        obstacle = StageObstacle("dumpster", AABB2(5.0, 7.0, -2.0, 2.0), max_elevation=20.0)
        result = sweep_move(body, 10.0, 5.0, obstacles=[obstacle])
        self.assertAlmostEqual(result.x, 4.0, places=3)
        self.assertAlmostEqual(result.depth, 5.0, places=3)
        self.assertTrue(result.blocked_x)
        self.assertFalse(result.blocked_depth)
        self.assertEqual(result.contacts[0].obstacle_id, "dumpster")
        self.assertEqual((result.contacts[0].normal_x, result.contacts[0].normal_depth), (-1.0, 0.0))
        self.assertEqual((body.x, body.depth), (0.0, 0.0), "sweep_move must be pure")

    def test_move_body_applies_result_and_outer_stage_rails_slide(self) -> None:
        body = PushBody("shelly", 0.0, 0.0, half_width=1.0, half_depth=1.0)
        stage = StageBounds(-10.0, 10.0, -6.0, 6.0)
        result = move_body(body, 20.0, 4.0, bounds=stage)
        self.assertAlmostEqual(body.x, 9.0, places=4)
        self.assertAlmostEqual(body.depth, 4.0, places=4)
        self.assertTrue(result.blocked_x)
        self.assertFalse(result.blocked_depth)
        self.assertIn("stage:right", [contact.obstacle_id for contact in result.contacts])

    def test_low_scenery_rail_blocks_grounded_actor_but_can_be_jumped(self) -> None:
        rail = StageObstacle.rail(
            "curb",
            start=(5.0, -5.0),
            end=(5.0, 5.0),
            thickness=1.0,
            height=4.0,
        )
        grounded = PushBody("grounded", 0.0, 0.0, half_width=1.0, half_depth=1.0, height=10.0)
        airborne = PushBody("airborne", 0.0, 0.0, elevation=4.1, half_width=1.0, half_depth=1.0, height=10.0)
        self.assertLess(sweep_move(grounded, 10.0, 0.0, obstacles=[rail]).x, 5.0)
        self.assertAlmostEqual(sweep_move(airborne, 10.0, 0.0, obstacles=[rail]).x, 10.0)

    def test_bad_spawn_inside_obstacle_is_repaired_deterministically(self) -> None:
        body = PushBody("chief", 5.0, 0.0, half_width=1.0, half_depth=1.0)
        obstacle = StageObstacle("cart", AABB2(4.0, 6.0, -2.0, 2.0))
        result = sweep_move(body, 0.0, 0.0, obstacles=[obstacle])
        self.assertTrue(result.started_overlapping)
        self.assertFalse(obstacle.bounds.expanded(1.0, 1.0).intersects(AABB2(result.x, result.x, result.depth, result.depth), touching=False))


class PushSeparationTests(unittest.TestCase):
    def test_two_exactly_stacked_bodies_are_fully_separated(self) -> None:
        a = PushBody("a", 0.0, 0.0, half_width=5.0, half_depth=3.0)
        b = PushBody("b", 0.0, 0.0, half_width=5.0, half_depth=3.0)
        result = separate_push_bodies([a, b], crowd_spacing=2.0)
        self.assertTrue(_has_required_spacing(a, b, spacing=2.0))
        self.assertIn(("a", "b"), result.resolved_pairs)
        self.assertEqual(result.moved_ids, ("a", "b"))
        self.assertLessEqual(result.max_remaining_overlap, 0.02)

    def test_solver_is_deterministic_when_input_order_changes(self) -> None:
        specs = [("p4", 0.0, 0.0), ("p1", 1.0, 0.2), ("e2", -0.5, 0.4), ("e1", 0.25, -0.1)]

        def solve(order: list[tuple[str, float, float]]) -> dict[str, tuple[float, float]]:
            bodies = [PushBody(entity_id, x, depth, half_width=4.0, half_depth=2.5) for entity_id, x, depth in order]
            separate_push_bodies(bodies, crowd_spacing=0.5, iterations=32)
            return {body.entity_id: (round(body.x, 6), round(body.depth, 6)) for body in bodies}

        self.assertEqual(solve(specs), solve(list(reversed(specs))))

    def test_one_to_four_players_and_enemy_crowd_never_stack(self) -> None:
        for player_count in range(1, 5):
            with self.subTest(players=player_count):
                bodies = [
                    PushBody(f"player:{index}", index * 0.4, index * 0.2, half_width=3.0, half_depth=2.0)
                    for index in range(player_count)
                ]
                bodies.extend(
                    PushBody(f"enemy:{index}", -index * 0.35, index * 0.15, half_width=3.0, half_depth=2.0)
                    for index in range(6)
                )
                result = separate_push_bodies(
                    bodies,
                    crowd_spacing=0.35,
                    bounds=StageBounds(-80.0, 80.0, -40.0, 40.0),
                    iterations=48,
                    tolerance=0.002,
                )
                for index, a in enumerate(bodies):
                    for b in bodies[index + 1 :]:
                        self.assertTrue(_has_required_spacing(a, b, spacing=0.35, tolerance=0.04), (a, b))
                self.assertLessEqual(result.max_remaining_overlap, 0.04)

    def test_immovable_heavy_body_pushes_only_movable_body(self) -> None:
        wall_actor = PushBody("boss", 0.0, 0.0, half_width=5.0, half_depth=4.0, movable=False)
        player = PushBody("player", 2.0, 0.0, half_width=3.0, half_depth=2.0)
        separate_push_bodies([player, wall_actor])
        self.assertEqual((wall_actor.x, wall_actor.depth), (0.0, 0.0))
        self.assertTrue(_has_required_spacing(wall_actor, player))

    def test_high_jump_and_collision_masks_can_pass_through_crowd(self) -> None:
        grounded = PushBody("ground", 0.0, 0.0, height=20.0)
        jumping = PushBody("jump", 0.0, 0.0, elevation=21.0, height=20.0)
        ghost = PushBody("ghost", 0.0, 0.0, layer=2, mask=2)
        result = separate_push_bodies([grounded, jumping, ghost])
        self.assertEqual((grounded.x, grounded.depth), (0.0, 0.0))
        self.assertEqual((jumping.x, jumping.depth), (0.0, 0.0))
        self.assertEqual((ghost.x, ghost.depth), (0.0, 0.0))
        self.assertEqual(result.resolved_pairs, ())


class AttackQueryTests(unittest.TestCase):
    def test_lane_tolerance_is_explicit_and_not_screen_y_guesswork(self) -> None:
        target_in_lane = HurtBox("in", "enemy", 12.0, 7.9, half_width=2.0, half_depth=2.0)
        target_outside_lane = HurtBox("out", "enemy", 12.0, 8.1, half_width=2.0, half_depth=2.0)
        attack = HitBox(
            "jab:1",
            "dave",
            "heroes",
            0.0,
            0.0,
            half_width=12.0,
            half_depth=4.0,
            depth_tolerance=2.0,
        )
        self.assertEqual([result.target_id for result in query_attack(attack, [target_in_lane, target_outside_lane])], ["in"])

    def test_ground_and_air_filters_work_independently_of_vertical_overlap(self) -> None:
        grounded = HurtBox("ground", "enemy", 3.0, 0.0, elevation=0.0, height=20.0)
        airborne = HurtBox("air", "enemy", 3.0, 0.0, elevation=12.0, height=20.0)
        ground_sweep = HitBox(
            "sweep",
            "shelly",
            "heroes",
            0.0,
            0.0,
            height=50.0,
            hit_grounded=True,
            hit_airborne=False,
        )
        anti_air = HitBox(
            "uppercut",
            "dave",
            "heroes",
            0.0,
            0.0,
            height=50.0,
            hit_grounded=False,
            hit_airborne=True,
        )
        self.assertEqual([result.target_id for result in query_attack(ground_sweep, [grounded, airborne])], ["ground"])
        self.assertEqual([result.target_id for result in query_attack(anti_air, [grounded, airborne])], ["air"])

    def test_vertical_volume_rejects_actor_above_attack_even_when_air_hits_enabled(self) -> None:
        high_target = HurtBox("high", "enemy", 0.0, 0.0, elevation=31.0, height=20.0)
        attack = HitBox("low", "dave", "heroes", 0.0, 0.0, elevation=0.0, height=30.0)
        self.assertEqual(query_attack(attack, [high_target]), ())

    def test_vertical_tolerance_allows_actor_slightly_out_of_primary_vertical_overlap(self) -> None:
        high_target = HurtBox("high", "enemy", 0.0, 0.0, elevation=31.0, height=20.0)
        attack = HitBox(
            "low",
            "dave",
            "heroes",
            0.0,
            0.0,
            elevation=0.0,
            height=30.0,
            elevation_tolerance=2.0,
        )
        self.assertEqual([result.target_id for result in query_attack(attack, [high_target])], ["high"])

    def test_temporal_forgiveness_catches_slightly_late_sweep_overlap(self) -> None:
        target = HurtBox("near-late", "enemy", 9.05, 0.0, half_width=2.0, half_depth=2.0)
        attack = HitBox(
            "late-hit",
            "dave",
            "heroes",
            5.0,
            0.0,
            half_width=2.0,
            half_depth=2.0,
            sweep_from_x=0.0,
            sweep_from_depth=0.0,
        )

        self.assertEqual(query_attack(attack, [target]), ())

        forgiving_attack = HitBox(
            "late-hit",
            "dave",
            "heroes",
            5.0,
            0.0,
            half_width=2.0,
            half_depth=2.0,
            sweep_from_x=0.0,
            sweep_from_depth=0.0,
            temporal_forgiveness=0.03,
        )
        self.assertEqual([result.target_id for result in query_attack(forgiving_attack, [target])], ["near-late"])

    def test_results_are_deterministic_nearest_first_and_hash_matches_list(self) -> None:
        targets = [
            HurtBox("tie-b", "enemy", 4.0, 3.0, half_width=1.0, half_depth=1.0),
            HurtBox("near", "enemy", 2.0, 0.0, half_width=1.0, half_depth=1.0),
            HurtBox("tie-a", "enemy", 4.0, -3.0, half_width=1.0, half_depth=1.0),
            HurtBox("ally", "heroes", 1.0, 0.0, half_width=1.0, half_depth=1.0),
        ]
        attack = HitBox("combo:2", "dave", "heroes", 0.0, 0.0, half_width=10.0, half_depth=10.0)
        expected = ["near", "tie-a", "tie-b"]
        self.assertEqual([result.target_id for result in query_attack(attack, reversed(targets))], expected)
        broadphase = SpatialHash(8.0)
        broadphase.rebuild(targets)
        self.assertEqual([result.target_id for result in query_attack(attack, broadphase)], expected)

    def test_attack_memory_tags_target_cap_and_predicate_are_composable(self) -> None:
        targets = [
            HurtBox("armored", "enemy", 1.0, 0.0, tags=frozenset({"enemy", "armor"})),
            HurtBox("one", "enemy", 2.0, 0.0, tags=frozenset({"enemy"})),
            HurtBox("two", "enemy", 3.0, 0.0, tags=frozenset({"enemy"})),
        ]
        attack = HitBox(
            "torch",
            "shelly",
            "heroes",
            0.0,
            0.0,
            half_width=20.0,
            required_tags=frozenset({"enemy"}),
            blocked_tags=frozenset({"armor"}),
            max_targets=1,
        )
        results = query_attack(attack, targets, already_hit={"one"}, predicate=lambda target: target.entity_id != "ignored")
        self.assertEqual([result.target_id for result in results], ["two"])

    def test_directional_strike_rejects_rear_target_and_prefers_clear_front_lane(self) -> None:
        attack = HitBox(
            "dave:jab",
            "dave",
            "heroes",
            22.0,
            0.0,
            half_width=32.0,
            half_depth=14.0,
            facing_x=1.0,
            front_origin_x=0.0,
            front_origin_depth=0.0,
            rear_tolerance=1.0,
            max_targets=1,
        )
        targets = [
            HurtBox("rear", "enemy", -9.0, 0.0, half_width=3.0, half_depth=3.0),
            HurtBox("off-lane", "enemy", 15.0, 12.0, half_width=3.0, half_depth=3.0),
            HurtBox("straight", "enemy", 28.0, 0.0, half_width=3.0, half_depth=3.0),
        ]

        self.assertEqual([result.target_id for result in query_attack(attack, reversed(targets))], ["straight"])

    def test_swept_attack_catches_target_between_active_window_samples(self) -> None:
        attack = HitBox(
            "dave:advance",
            "dave",
            "heroes",
            42.0,
            0.0,
            half_width=5.0,
            half_depth=4.0,
            sweep_from_x=0.0,
            sweep_from_depth=0.0,
        )
        target = HurtBox("crossed", "enemy", 20.0, 0.0, half_width=2.0, half_depth=2.0)

        # The final rectangles do not touch (attack starts at x=37), yet the
        # fist travelled over the target during this active-window sample.
        self.assertEqual([result.target_id for result in query_attack(attack, [target])], ["crossed"])

    def test_relative_sweep_catches_moving_target_that_crossed_a_static_fist(self) -> None:
        attack = HitBox("dave:hold", "dave", "heroes", 0.0, 0.0, half_width=4.0, half_depth=4.0)
        target = HurtBox(
            "runner",
            "enemy",
            18.0,
            0.0,
            half_width=3.0,
            half_depth=3.0,
            sweep_from_x=-18.0,
            sweep_from_depth=0.0,
        )

        self.assertEqual([result.target_id for result in query_attack(attack, [target])], ["runner"])
        self.assertEqual((target.swept_bounds_2d.min_x, target.swept_bounds_2d.max_x), (-21.0, 21.0))
        broadphase = SpatialHash(8.0)
        broadphase.rebuild([target])
        self.assertEqual([result.target_id for result in query_attack(attack, broadphase)], ["runner"])
        self.assertEqual(
            query_attack_detailed(attack, [target]),
            query_attack_detailed(attack, broadphase),
        )

    def test_directional_sweep_keeps_a_front_to_rear_crossing_as_a_valid_contact(self) -> None:
        attack = HitBox(
            "dave:hold",
            "dave",
            "heroes",
            0.0,
            0.0,
            half_width=4.0,
            half_depth=4.0,
            facing_x=1.0,
            front_origin_x=0.0,
            front_origin_depth=0.0,
        )
        crossed = HurtBox(
            "crossed-front",
            "enemy",
            -18.0,
            0.0,
            half_width=3.0,
            half_depth=3.0,
            sweep_from_x=18.0,
            sweep_from_depth=0.0,
        )
        parked_rear = HurtBox("parked-rear", "enemy", -8.0, 0.0, half_width=3.0, half_depth=3.0)

        self.assertEqual([result.target_id for result in query_attack(attack, [parked_rear, crossed])], ["crossed-front"])

    def test_result_carries_damage_hitstop_and_camera_impact_data(self) -> None:
        target = HurtBox("cart-user", "enemy", 6.0, 2.0)
        attack = HitBox(
            "speaker-wave",
            "dave",
            "heroes",
            0.0,
            0.0,
            damage=18.0,
            stun=0.35,
            knockback_x=22.0,
            knockback_depth=4.0,
            launch_elevation=8.0,
            hitstop_seconds=0.09,
            camera_strength=5.5,
            camera_seconds=0.18,
        )
        result = query_attack(attack, [target])[0]
        self.assertEqual((result.damage, result.stun, result.knockback_x, result.launch_elevation), (18.0, 0.35, 22.0, 8.0))
        self.assertEqual(result.hitstop.target_id, "cart-user")
        self.assertEqual(result.hitstop.seconds, 0.09)
        self.assertEqual(result.camera.strength, 5.5)
        self.assertEqual(result.camera.seconds, 0.18)
        self.assertAlmostEqual((result.camera.direction_x**2 + result.camera.direction_depth**2) ** 0.5, 1.0)

    def test_detailed_query_reports_state_tag_and_geometry_rejections(self) -> None:
        def rejected_reason(
            attack: HitBox,
            target: HurtBox,
            **kwargs: object,
        ) -> tuple[AttackRejectionReason | None, object]:
            report = query_attack_detailed(attack, [target], **kwargs)
            self.assertEqual(report.results, ())
            self.assertEqual(len(report.evaluations), 1)
            return report.evaluations[0].reason, report.evaluations[0]

        base_attack = lambda **kwargs: HitBox(  # noqa: E731
            "diagnostic",
            "hero",
            "heroes",
            0.0,
            0.0,
            half_width=5.0,
            half_depth=5.0,
            **kwargs,
        )
        base_target = lambda **kwargs: HurtBox(  # noqa: E731
            "target",
            "enemies",
            0.0,
            0.0,
            half_width=2.0,
            half_depth=2.0,
            **kwargs,
        )

        cases = (
            (base_attack(enabled=False), base_target(), AttackRejectionReason.INACTIVE, {}),
            (base_attack(), base_target(enabled=False), AttackRejectionReason.DISABLED, {}),
            (base_attack(), base_target(defeated=True), AttackRejectionReason.DEFEATED, {}),
            (base_attack(), base_target(vulnerable=False), AttackRejectionReason.INVULNERABLE, {}),
            (base_attack(), HurtBox("hero", "enemies", 0.0, 0.0), AttackRejectionReason.SELF, {}),
            (base_attack(), base_target(), AttackRejectionReason.ALREADY_HIT, {"already_hit": {"target"}}),
            (base_attack(), HurtBox("ally", "heroes", 0.0, 0.0), AttackRejectionReason.WRONG_FACTION, {}),
            (
                base_attack(hit_grounded=False),
                base_target(grounded=True),
                AttackRejectionReason.GROUNDED_MISMATCH,
                {},
            ),
            (
                base_attack(hit_airborne=False),
                base_target(grounded=False),
                AttackRejectionReason.AIRBORNE_MISMATCH,
                {},
            ),
            (
                base_attack(required_tags=frozenset({"boss"})),
                base_target(tags=frozenset({"enemy"})),
                AttackRejectionReason.REQUIRED_TAGS,
                {},
            ),
            (
                base_attack(blocked_tags=frozenset({"downed"})),
                base_target(tags=frozenset({"downed"})),
                AttackRejectionReason.DOWNED,
                {},
            ),
            (
                base_attack(blocked_tags=frozenset({"blocking"})),
                base_target(tags=frozenset({"blocking"})),
                AttackRejectionReason.BLOCKED,
                {},
            ),
            (
                base_attack(blocked_tags=frozenset({"armored"})),
                base_target(tags=frozenset({"armored"})),
                AttackRejectionReason.ARMOR,
                {},
            ),
            (
                base_attack(blocked_tags=frozenset({"ethereal"})),
                base_target(tags=frozenset({"ethereal"})),
                AttackRejectionReason.BLOCKED_TAGS,
                {},
            ),
            (
                base_attack(
                    facing_x=1.0,
                    front_origin_x=0.0,
                    front_origin_depth=0.0,
                ),
                HurtBox("rear", "enemies", -12.0, 0.0, half_width=2.0, half_depth=2.0),
                AttackRejectionReason.BEHIND,
                {},
            ),
            (
                base_attack(),
                HurtBox("far-x", "enemies", 30.0, 0.0, half_width=2.0, half_depth=2.0),
                AttackRejectionReason.HORIZONTAL_RANGE,
                {},
            ),
            (
                base_attack(),
                HurtBox("far-depth", "enemies", 0.0, 30.0, half_width=2.0, half_depth=2.0),
                AttackRejectionReason.DEPTH_RANGE,
                {},
            ),
            (
                base_attack(height=5.0),
                base_target(elevation=20.0, height=5.0),
                AttackRejectionReason.ELEVATION_RANGE,
                {},
            ),
            (
                base_attack(),
                base_target(),
                AttackRejectionReason.PREDICATE,
                {"predicate": lambda _: False},
            ),
        )
        for attack, target, expected, kwargs in cases:
            with self.subTest(reason=expected.value):
                reason, evaluation = rejected_reason(attack, target, **kwargs)
                self.assertEqual(reason, expected)
                self.assertFalse(evaluation.accepted)

        missing = query_attack_detailed(
            base_attack(required_tags=frozenset({"boss", "enemy"})),
            [base_target(tags=frozenset({"enemy"}))],
        ).evaluations[0]
        self.assertEqual(missing.missing_tags, frozenset({"boss"}))
        armored = query_attack_detailed(
            base_attack(blocked_tags=frozenset({"armored"})),
            [base_target(tags=frozenset({"armored"}))],
        ).evaluations[0]
        self.assertEqual(armored.blocked_tags, frozenset({"armored"}))

    def test_detailed_query_enforces_hit_count_and_rehit_delay(self) -> None:
        target = HurtBox("repeat", "enemies", 2.0, 0.0)
        attack = HitBox(
            "multi",
            "hero",
            "heroes",
            0.0,
            0.0,
            max_hits_per_target=3,
            rehit_delay=0.25,
        )
        cooling_down = query_attack_detailed(
            attack,
            [target],
            hit_counts={"repeat": 1},
            last_hit_times={"repeat": 10.0},
            now=10.10,
        )
        evaluation = cooling_down.evaluations[0]
        self.assertEqual(evaluation.reason, AttackRejectionReason.REHIT_DELAY)
        self.assertAlmostEqual(evaluation.rehit_remaining, 0.15)

        ready = query_attack_detailed(
            attack,
            [target],
            hit_counts={"repeat": 2},
            last_hit_times={"repeat": 10.0},
            now=10.25,
        )
        self.assertEqual([result.target_id for result in ready.results], ["repeat"])
        self.assertTrue(ready.evaluations[0].accepted)

        exhausted = query_attack_detailed(
            attack,
            [target],
            hit_counts={"repeat": 3},
            last_hit_times={"repeat": 1.0},
            now=10.0,
        )
        self.assertEqual(exhausted.evaluations[0].reason, AttackRejectionReason.ALREADY_HIT)
        with self.assertRaises(ValueError):
            HitBox("bad-count", "hero", "heroes", 0.0, 0.0, max_hits_per_target=0)
        with self.assertRaises(ValueError):
            HitBox("fractional-count", "hero", "heroes", 0.0, 0.0, max_hits_per_target=1.5)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            HitBox("bad-delay", "hero", "heroes", 0.0, 0.0, rehit_delay=-0.01)

    def test_detailed_query_target_cap_and_evaluation_order_are_deterministic(self) -> None:
        targets = [
            HurtBox("tie-b", "enemies", 4.0, 1.0, half_width=1.0, half_depth=1.0),
            HurtBox("near", "enemies", 2.0, 0.0, half_width=1.0, half_depth=1.0),
            HurtBox("tie-a", "enemies", 4.0, -1.0, half_width=1.0, half_depth=1.0),
        ]
        attack = HitBox(
            "single",
            "hero",
            "heroes",
            0.0,
            0.0,
            half_width=10.0,
            half_depth=10.0,
            max_targets=1,
        )

        forward = query_attack_detailed(attack, targets)
        reverse = query_attack_detailed(attack, reversed(targets))
        self.assertEqual(forward, reverse)
        self.assertEqual([result.target_id for result in forward.results], ["near"])
        self.assertEqual(
            [(evaluation.target_id, evaluation.reason) for evaluation in forward.evaluations],
            [
                ("near", None),
                ("tie-a", AttackRejectionReason.TARGET_CAP),
                ("tie-b", AttackRejectionReason.TARGET_CAP),
            ],
        )
        self.assertEqual(query_attack(attack, targets), forward.results)


if __name__ == "__main__":
    unittest.main()
