"""Regressions for movement seams, combat reach, and correction jitter."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.entities import Enemy, Projectile
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager, InputSnapshot


class CollisionRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        self.manager = InputManager(max_players=4, discover_controllers=False)
        self.game = FadesGame(self.manager, mute=True)
        self.game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
        self.game._start_stage()
        self.dave, self.shelly = self.game.players

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def enemy(self, enemy_id: int, x: float, y: float, kind: str = "stick") -> Enemy:
        result = Enemy(enemy_id, kind, x, y, self.game.data["enemies"][kind])
        result.state = "chase"
        return result

    def test_attack_queries_full_active_window_and_hits_each_target_once(self) -> None:
        self.shelly.state = "eliminated"
        target = self.enemy(100, self.dave.x + 120.0, self.dave.y)
        self.game.enemies = [target]
        move = self.game.data["moves"]["light_combo"][0]
        self.dave.combo_step = 0
        self.dave.set_state("light", self.dave._move_total(move))

        for _ in range(5):
            self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)
        self.assertEqual(target.health, target.max_health)

        target.x = self.dave.x + 34.0
        for _ in range(5):
            self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)

        self.assertEqual(target.health, target.max_health - float(move["damage"]))
        self.assertEqual(self.dave.attack_hit_ids, {("enemy", target.enemy_id)})

    def test_ally_between_attacker_and_target_does_not_block_lane_assisted_hit(self) -> None:
        self.dave.x, self.dave.y, self.dave.facing = 220.0, 270.0, 1
        self.shelly.x, self.shelly.y = 239.0, 270.0
        target = self.enemy(101, 254.0, 295.0)
        self.game.enemies = [target]

        hits = self.game.player_attack(
            self.dave,
            self.game.data["moves"]["light_combo"][0],
            "light",
            already_hit=set(),
        )

        self.assertEqual(hits, 1)
        self.assertLess(target.health, target.max_health)

    def test_player_attack_hits_when_target_is_slightly_behind_but_crossed_forward(self) -> None:
        self.dave.x, self.dave.y, self.dave.facing = 260.0, 270.0, 1
        move = self.game.data["moves"]["light_combo"][1]
        target = self.enemy(102, self.dave.x - 10.0, self.dave.y)
        target.hitbox_sweep_x = self.dave.x + 14.0
        target.hitbox_sweep_y = self.dave.y
        self.game.enemies = [target]

        hits = self.game.player_attack(self.dave, move, "light", already_hit=set())

        self.assertEqual(hits, 1)
        self.assertLess(target.health, target.max_health)

    def test_player_attack_connects_with_small_depth_mismatch(self) -> None:
        self.dave.x, self.dave.y, self.dave.facing = 260.0, 270.0, 1
        move = self.game.data["moves"]["light_combo"][0]
        target = self.enemy(103, self.dave.x + 24.0, self.dave.y + 20.0)
        self.game.enemies = [target]

        hits = self.game.player_attack(self.dave, move, "light", already_hit=set())

        self.assertEqual(hits, 1)
        self.assertLess(target.health, target.max_health)

    def test_player_attack_centers_depth_assist_across_two_nearby_targets(self) -> None:
        self.dave.x, self.dave.y, self.dave.facing = 260.0, 270.0, 1
        move = self.game.data["moves"]["light_combo"][0]
        upper = self.enemy(104, self.dave.x + 25.0, self.dave.y - 28.0)
        lower = self.enemy(110, self.dave.x + 27.0, self.dave.y + 28.0)
        self.game.enemies = [lower, upper]

        hits = self.game.player_attack(self.dave, move, "light", already_hit=set())

        self.assertEqual(hits, 2)
        self.assertLess(upper.health, upper.max_health)
        self.assertLess(lower.health, lower.max_health)

    def test_player_punch_hits_two_nearest_front_targets_not_rear_targets(self) -> None:
        self.dave.x, self.dave.y, self.dave.facing = 280.0, 270.0, 1
        move = self.game.data["moves"]["light_combo"][1]
        self.dave.combo_step = 1
        nearest = self.enemy(105, self.dave.x + 26.0, self.dave.y)
        side = self.enemy(106, self.dave.x + 18.0, self.dave.y + 17.0)
        rear = self.enemy(107, self.dave.x - 26.0, self.dave.y)
        self.game.enemies = [side, rear, nearest]

        hits = self.game.player_attack(self.dave, move, "light", already_hit=set())

        self.assertEqual(hits, 2)
        self.assertLess(nearest.health, nearest.max_health)
        self.assertLess(side.health, side.max_health)
        self.assertEqual(rear.health, rear.max_health)

    def test_player_attack_sweep_catches_an_enemy_that_crossed_the_fist_lane(self) -> None:
        self.dave.x, self.dave.y, self.dave.facing = 260.0, 270.0, 1
        move = self.game.data["moves"]["light_combo"][0]
        target = self.enemy(108, self.dave.x + 80.0, self.dave.y)
        # The enemy was in the fist lane at the prior authoritative sample,
        # but its current rectangle is already beyond a static jab.
        target.hitbox_sweep_x = self.dave.x + 20.0
        target.hitbox_sweep_y = target.y
        self.game.enemies = [target]

        hits = self.game.player_attack(self.dave, move, "light", already_hit=set())

        self.assertEqual(hits, 1)
        self.assertLess(target.health, target.max_health)

    def test_player_lunge_lane_assist_reaches_slightly_out_of_base_range(self) -> None:
        self.dave.x, self.dave.y, self.dave.facing = 260.0, 270.0, 1
        move = self.game.data["moves"]["heavy"]
        physics = self.game.data["engine"]["physics"]
        sampled = self.game._sample_move_hitbox(move, 0.0)
        base_reach = (
            float(move["range_x"])
            + float(physics.get("player_attack_reach_bonus", 0.0))
            + float(move.get("reach_forgiveness", 0.0))
        ) * sampled["reach_scale"]
        assist_range = base_reach + float(physics.get("player_attack_aim_range_bonus", 0.0))
        target = self.enemy(
            109,
            self.dave.x + assist_range + float(move["lunge"]) - 0.5,
            self.dave.y,
        )
        self.game.enemies = [target]

        hits = self.game.player_attack(self.dave, move, "heavy", already_hit=set())

        self.assertEqual(hits, 1)
        self.assertLess(target.health, target.max_health)

    def test_two_target_cap_applies_to_the_whole_attack_execution(self) -> None:
        self.shelly.state = "eliminated"
        move = self.game.data["moves"]["light_combo"][0]
        first = self.enemy(120, self.dave.x + 25.0, self.dave.y)
        second = self.enemy(121, self.dave.x + 28.0, self.dave.y)
        self.game.enemies = [second, first]
        self.dave.set_state("light", self.dave._move_total(move))

        for _ in range(10):
            self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)

        damaged = [enemy for enemy in (first, second) if enemy.health < enemy.max_health]
        self.assertEqual(len(damaged), 2)
        self.assertEqual(
            self.dave.attack_hit_ids,
            {("enemy", first.enemy_id), ("enemy", second.enemy_id)},
        )

    def test_fourth_combo_strike_is_a_deterministic_two_target_finisher(self) -> None:
        self.shelly.state = "eliminated"
        first = self.enemy(122, self.dave.x + 25.0, self.dave.y)
        second = self.enemy(123, self.dave.x + 29.0, self.dave.y + 2.0)
        rear = self.enemy(124, self.dave.x - 24.0, self.dave.y)
        self.game.enemies = [rear, second, first]
        self.dave.combo_step = 3
        move = self.dave._light_move()
        self.assertEqual(move["max_targets"], 2)
        self.dave.set_state("light", self.dave._move_total(move))

        for _ in range(20):
            self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)

        self.assertLess(first.health, first.max_health)
        self.assertLess(second.health, second.max_health)
        self.assertEqual(rear.health, rear.max_health)
        self.assertEqual(first.state, "down")
        self.assertEqual(second.state, "down")

    def test_downed_and_wakeup_invulnerable_targets_reject_normal_strikes(self) -> None:
        self.shelly.state = "eliminated"
        target = self.enemy(125, self.dave.x + 24.0, self.dave.y)
        self.game.enemies = [target]
        move = self.game.data["moves"]["light_combo"][0]
        target.state = "down"
        before = target.health

        self.assertEqual(self.game.player_attack(self.dave, move, "light"), 0)
        self.assertEqual(self.game._debug_last_rejection, "downed")
        self.assertEqual(target.health, before)

        target.state = "chase"
        target.wake_invulnerable = 0.18
        self.assertEqual(self.game.player_attack(self.dave, move, "light"), 0)
        self.assertEqual(self.game._debug_last_rejection, "invulnerable")
        self.assertEqual(target.health, before)

    def test_enemy_attack_uses_relative_sweep_when_player_crosses_the_strike(self) -> None:
        self.shelly.state = "eliminated"
        enemy = self.enemy(126, self.dave.x - 40.0, self.dave.y)
        enemy.facing = 1
        enemy.attack_instance_id = 7
        self.game.enemies = [enemy]
        self.dave.hitbox_sweep_x = enemy.x + 12.0
        self.dave.hitbox_sweep_y = self.dave.y
        self.dave.x = enemy.x + 95.0
        before = self.dave.health

        self.assertTrue(
            self.game.enemy_attack(
                enemy,
                range_x=34.0,
                range_y=18.0,
                damage=7.0,
            )
        )
        self.assertLess(self.dave.health, before)

    def test_throw_volume_rejects_rear_downed_armored_and_boss_targets(self) -> None:
        self.shelly.state = "eliminated"
        rear = self.enemy(127, self.dave.x - 12.0, self.dave.y)
        self.game.enemies = [rear]
        self.assertFalse(self.game.try_throw(self.dave))
        self.assertEqual(self.game._debug_last_rejection, "behind")

        downed = self.enemy(128, self.dave.x + 12.0, self.dave.y)
        downed.state = "down"
        self.game.enemies = [downed]
        self.assertFalse(self.game.try_throw(self.dave))
        self.assertEqual(self.game._debug_last_rejection, "downed")

        boss = self.enemy(129, self.dave.x + 12.0, self.dave.y, "couch")
        self.game.enemies = [boss]
        self.assertFalse(self.game.try_throw(self.dave))
        self.assertEqual(self.game._debug_last_rejection, "blocked-tags")

        target = self.enemy(130, self.dave.x + 12.0, self.dave.y)
        self.game.enemies = [target]
        self.assertTrue(self.game.try_throw(self.dave))
        self.assertEqual(target.state, "down")

    def test_fast_pipe_projectile_cannot_tunnel_through_player(self) -> None:
        self.shelly.state = "eliminated"
        projectile = Projectile(
            x=self.dave.x - 60.0,
            y=self.dave.y,
            z=15.0,
            vx=1200.0,
            vy=0.0,
            vz=0.0,
            damage=9.0,
            owner_team="enemy",
            owner_id=131,
            attack_instance_id=4,
        )
        before = self.dave.health

        projectile.update(self.game, 0.10)

        self.assertTrue(projectile.spent)
        self.assertLess(self.dave.health, before)

    def test_combat_press_during_hitstop_is_applied_on_first_unfrozen_step(self) -> None:
        self.shelly.state = "eliminated"
        self.game.hitstop_remaining = 1.0 / 60.0
        self.manager.process_events(
            (pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_x, "repeat": False}),)
        )

        self.game.update(1.0 / 60.0)
        self.assertEqual(self.dave.state, "idle")
        self.assertEqual(self.game._hitstop_pressed_by_slot[self.dave.slot], {"light"})
        self.manager.consume_pressed()
        self.game.update(1.0 / 60.0)

        self.assertEqual(self.dave.state, "light")
        self.assertNotIn(self.dave.slot, self.game._hitstop_pressed_by_slot)

    def test_enemy_melee_damage_occurs_during_authored_active_window(self) -> None:
        self.shelly.state = "eliminated"
        enemy = self.enemy(132, self.dave.x + 20.0, self.dave.y)
        enemy.facing = -1
        enemy.target_slot = self.dave.slot
        enemy.attack_pattern = "stick"
        enemy.attack_instance_id = 9
        enemy.state = "windup"
        enemy.state_clock = enemy.state_duration = float(enemy.stats["windup"])
        self.game.enemies = [enemy]
        before = self.dave.health

        enemy.update(self.game, 1.0 / 60.0)
        self.assertEqual(enemy.state, "attack")
        self.assertEqual(self.dave.health, before)

        enemy.update(self.game, 1.0 / 60.0)
        self.assertLess(self.dave.health, before)
        self.assertEqual(enemy.state, "attack")
        self.assertEqual(enemy.attack_hit_ids, {("player", self.dave.slot)})

        for _ in range(20):
            enemy.update(self.game, 1.0 / 60.0)
            if enemy.state == "recovery":
                break
        self.assertEqual(enemy.state, "recovery")

    def test_first_and_final_discrete_active_samples_can_both_connect(self) -> None:
        self.shelly.state = "eliminated"
        move = self.game.data["moves"]["light_combo"][0]
        target = self.enemy(133, self.dave.x + 24.0, self.dave.y)
        self.game.enemies = [target]
        self.dave.set_state("light", self.dave._move_total(move))
        self.dave.state_clock = float(move["startup"]) - 1.0 / 60.0
        self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)
        self.assertLess(target.health, target.max_health)

        target = self.enemy(134, self.dave.x + 24.0, self.dave.y)
        self.game.enemies = [target]
        self.dave.set_state("light", self.dave._move_total(move))
        self.dave.state_clock = (
            float(move["startup"]) + float(move["active"]) - 2.0 / 60.0
        )
        self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)
        self.assertLess(target.health, target.max_health)

    def test_chief_is_non_solid_while_enemy_contact_remains_solid(self) -> None:
        chief = self.game.chiefs[0]
        self.dave.x, self.dave.y = 180.0, 270.0
        self.shelly.x, self.shelly.y = 230.0, 290.0
        enemy = self.enemy(102, 360.0, 270.0)
        chief.x, chief.y = enemy.x, enemy.y
        self.game.enemies = [enemy]

        self.game._resolve_actor_separation()

        self.assertEqual((chief.x, chief.y), (360.0, 270.0))
        self.assertEqual((enemy.x, enemy.y), (360.0, 270.0))

        self.dave.x, self.dave.y = enemy.x, enemy.y
        self.game._resolve_actor_separation()
        self.assertGreater(abs(self.dave.x - enemy.x) + abs(self.dave.y - enemy.y), 8.0)

    def test_enemy_takes_one_deterministic_detour_then_holds_without_jitter(self) -> None:
        self.shelly.state = "eliminated"
        self.game.camera_x = 0.0
        self.dave.x, self.dave.y = 600.0, 247.0
        enemy = self.enemy(104, 360.0, 247.0)
        enemy.cooldown = 99.0
        self.game.enemies = [enemy]
        detour_depths: set[float] = set()
        positions: list[tuple[float, float]] = []

        for _ in range(330):
            enemy.update(self.game, 1.0 / 60.0)
            self.game._resolve_actor_separation()
            positions.append((enemy.x, enemy.y))
            if enemy.nav_detour_depth is not None:
                detour_depths.add(round(enemy.nav_detour_depth, 3))

        self.assertEqual(len(detour_depths), 1)
        self.assertGreater(max(x for x, _ in positions), 520.0)
        tail = positions[-30:]
        self.assertLess(max(x for x, _ in tail) - min(x for x, _ in tail), 0.05)
        self.assertLess(max(y for _, y in tail) - min(y for _, y in tail), 0.05)

    def test_blocked_input_does_not_play_a_walk_cycle_in_place(self) -> None:
        half_width = float(self.game.data["engine"]["physics"]["player_radius_x"])
        self.game.active_gate = self.dave.x + half_width

        self.dave.update(InputSnapshot(move_x=1.0), self.game, 1.0 / 60.0)

        self.assertEqual(self.dave.state, "idle")

    def test_cpu_target_and_lane_are_retained_through_small_distance_swaps(self) -> None:
        first = self.enemy(110, self.shelly.x + 95.0, self.shelly.y)
        second = self.enemy(111, self.shelly.x + 97.0, self.shelly.y + 1.0)
        self.game.enemies = [first, second]

        self.game._cpu_snapshot(self.shelly, 1.0 / 60.0)
        initial_target = self.shelly.cpu_target_enemy_id
        initial_lane = self.shelly.cpu_lane_offset
        first.x += 5.0
        second.x -= 5.0
        self.game._cpu_snapshot(self.shelly, 1.0 / 60.0)

        self.assertEqual(self.shelly.cpu_target_enemy_id, initial_target)
        self.assertEqual(self.shelly.cpu_lane_offset, initial_lane)
        self.assertNotEqual(initial_lane, 0.0)

    def test_debug_rejections_are_structured_and_deduplicated_per_attack_target(self) -> None:
        self.game.debug = True
        target = self.enemy(140, self.dave.x - 140.0, self.dave.y)
        self.game.enemies = [target]
        move = self.game.data["moves"]["light_combo"][0]

        with mock.patch.object(self.game, "log_breadcrumb") as log:
            self.game.player_attack(self.dave, move, "light", play_whiff=False)
            self.game.player_attack(self.dave, move, "light", play_whiff=False)

        rejected = [
            call
            for call in log.call_args_list
            if call.args and call.args[0] == "combat_contact_rejected"
        ]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].kwargs["reason"], "behind")
        self.assertIn("horizontal_gap", rejected[0].kwargs)
        self.assertIn("depth_gap", rejected[0].kwargs)
        self.assertIn("elevation_gap", rejected[0].kwargs)

    def test_attack_lifetime_cap_produces_a_detailed_target_cap_report(self) -> None:
        self.game.debug = True
        prior = self.enemy(141, self.dave.x + 20.0, self.dave.y)
        prior_two = self.enemy(144, self.dave.x + 22.0, self.dave.y)
        waiting = self.enemy(142, self.dave.x + 24.0, self.dave.y)
        self.game.enemies = [prior, prior_two, waiting]
        move = self.game.data["moves"]["light_combo"][0]
        before = waiting.health

        hits = self.game.player_attack(
            self.dave,
            move,
            "light",
            already_hit={("enemy", prior.enemy_id), ("enemy", prior_two.enemy_id)},
            play_whiff=False,
        )

        self.assertEqual(hits, 0)
        self.assertEqual(waiting.health, before)
        self.assertEqual(self.game._debug_last_rejection, "target-cap")
        self.assertEqual(self.game._debug_last_query_frame, self.game.frame)
        self.assertTrue(
            any(
                evaluation.target_id == ("enemy", waiting.enemy_id)
                and evaluation.reason is not None
                and evaluation.reason.value == "target-cap"
                for evaluation in self.game._debug_last_evaluations
            )
        )

    def test_debug_geometry_distinguishes_colliders_and_expires_attack_visuals(self) -> None:
        target = self.enemy(143, self.dave.x + 22.0, self.dave.y)
        target.state = "down"
        target.wake_invulnerable = 0.2
        self.game.enemies = [target]
        self.game.player_attack(
            self.dave,
            self.game.data["moves"]["light_combo"][0],
            "light",
            play_whiff=False,
        )
        canvas = pygame.Surface((640, 360), pygame.SRCALPHA)

        with (
            mock.patch("src.game.pygame.draw.lines", wraps=pygame.draw.lines) as lines,
            mock.patch.object(self.game, "_text", wraps=self.game._text) as text,
        ):
            self.game._draw_debug(canvas)
        colors = {tuple(call.args[1]) for call in lines.call_args_list}
        labels = {str(call.args[2]) for call in text.call_args_list}
        self.assertTrue(
            {
                (72, 158, 255),   # navigation body
                (255, 207, 70),   # push box
                (244, 249, 255),  # invulnerable hurtbox
                (255, 159, 54),   # current attack
                (255, 118, 188),  # previous attack sample
                (255, 65, 218),   # swept attack envelope
            }.issubset(colors)
        )
        self.assertNotIn((255, 90, 90), colors, "invulnerability must outrank downed coloring")
        self.assertIn("ROUTE sprouts_el_cilantro W=3200", labels)
        sprouts = self.game._landmark_record("sprouts_parking_lot")
        self.assertIn(
            f"sprouts_parking_lot X={int(sprouts['world_x'])} {str(sprouts['confidence']).upper()}",
            labels,
        )
        self.assertTrue(any(label.startswith("Sprouts Parking Lot IN") for label in labels))
        self.assertTrue(any(label.startswith("RAIL ") for label in labels))
        self.assertIn("sprouts_cart_return", labels)

        self.game.frame = self.game._debug_last_query_frame + 46
        with mock.patch("src.game.pygame.draw.lines", wraps=pygame.draw.lines) as lines:
            self.game._draw_debug(canvas)
        stale_colors = {tuple(call.args[1]) for call in lines.call_args_list}
        self.assertNotIn((255, 159, 54), stale_colors)
        self.assertNotIn((255, 118, 188), stale_colors)
        self.assertNotIn((255, 65, 218), stale_colors)


if __name__ == "__main__":
    unittest.main()
