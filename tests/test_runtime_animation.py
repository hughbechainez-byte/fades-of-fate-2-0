from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.animation_manifest import action_segment_tick, clip_for, timed_action_tick
from src.entities import ANIMATION_TICKS_PER_SECOND, Enemy, _HERO_STRIDE_DISTANCE, _animation_tick
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager, InputSnapshot
from src import sprite_atlas


class ActionAnimationTimingTests(unittest.TestCase):
    @staticmethod
    def _phase(actor: str, state: str, tick: int) -> str:
        clip = clip_for(actor, state)
        return clip.phases[tick // max(1, clip.hold)]

    def test_contact_and_follow_through_stay_inside_active_move_time(self) -> None:
        for actor, state in (
            ("black_dave", "attack_1"),
            ("black_dave", "heavy"),
            ("shelly", "attack_4"),
            ("stick", "attack"),
            ("couch", "stick_attack"),
        ):
            with self.subTest(actor=actor, state=state):
                startup = 0.23
                active = 0.10
                recovery = 0.27
                before_contact = timed_action_tick(actor, state, startup - 0.0001, startup, active, recovery)
                at_contact = timed_action_tick(actor, state, startup, startup, active, recovery)
                at_follow = timed_action_tick(actor, state, startup + active - 0.0001, startup, active, recovery)
                at_recovery = timed_action_tick(actor, state, startup + active, startup, active, recovery)

                self.assertIn(
                    self._phase(actor, state, before_contact),
                    {"guard", "anticipate", "windup", "launch"},
                )
                self.assertEqual(self._phase(actor, state, at_contact), "contact")
                self.assertEqual(self._phase(actor, state, at_follow), "follow_through")
                self.assertEqual(self._phase(actor, state, at_recovery), "recoil")

    def test_each_action_family_enters_its_semantic_active_pose(self) -> None:
        for actor, state, expected in (
            ("black_dave", "ranged", "fire"),
            ("black_dave", "super", "release"),
            ("shelly", "air_attack", "strike"),
            ("chief", "command", "launch"),
            ("chief", "maul", "bite_contact"),
        ):
            with self.subTest(actor=actor, state=state):
                tick = timed_action_tick(actor, state, 0.2, 0.2, 0.1, 0.3)
                self.assertEqual(self._phase(actor, state, tick), expected)

    def test_segment_helper_exposes_every_authored_attack_pose_in_order(self) -> None:
        expected = {
            "startup": ("guard", "anticipate", "windup", "launch"),
            "active": ("contact", "follow_through"),
            "recovery": ("recoil", "recover"),
        }
        for segment, phases in expected.items():
            sampled = tuple(
                self._phase(
                    "black_dave",
                    "heavy",
                    action_segment_tick(
                        "black_dave",
                        "heavy",
                        segment,
                        index / len(phases),
                        1.0,
                    ),
                )
                for index in range(len(phases))
            )
            self.assertEqual(sampled, phases)

    def test_segment_helper_rejects_invalid_or_nonfinite_timing(self) -> None:
        with self.assertRaises(ValueError):
            action_segment_tick("black_dave", "attack_1", "impact", 0.0, 1.0)
        with self.assertRaises(ValueError):
            action_segment_tick("black_dave", "attack_1", "active", float("nan"), 1.0)
        with self.assertRaises(ValueError):
            timed_action_tick("black_dave", "attack_1", 0.0, 0.2, float("inf"), 0.3)


class RuntimeAnimationClockTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def test_actor_local_idle_phases_are_deterministic_but_not_globally_synchronized(self) -> None:
        first = Enemy(41, "stick", 160.0, 250.0, self.game.data["enemies"]["stick"])
        second = Enemy(42, "stick", 190.0, 250.0, self.game.data["enemies"]["stick"])
        for enemy in (first, second):
            enemy.state = "idle"
            enemy.advance_animation(1.0 / ANIMATION_TICKS_PER_SECOND)

        self.assertNotEqual(first.animation_tick, second.animation_tick)
        stable_tick = first.animation_tick
        self.game.frame += 10_000
        self.assertEqual(first.animation_tick, stable_tick, "render-frame time leaked into actor animation")

    def test_idle_renderers_use_actor_clocks_instead_of_the_global_render_frame(self) -> None:
        dave = next(candidate for candidate in self.game.players if candidate.character == "black_dave")
        chief = self.game.chiefs[0]
        enemy = Enemy(54, "stick", dave.x + 100.0, dave.y, self.game.data["enemies"]["stick"])
        enemy.state = "idle"
        enemy.advance_animation(0.0)
        dave.set_state("idle")
        dave.advance_animation(0.0)
        chief.state = "idle"
        chief.advance_animation(0.0)
        self.game.enemies = [enemy]
        expected = (dave.animation_tick, chief.animation_tick, enemy.animation_tick)
        canvas = pygame.Surface((640, 360), pygame.SRCALPHA)

        observed: list[tuple[int, int, int]] = []
        for global_frame in (7, 113):
            self.game.frame = global_frame
            with (
                mock.patch("src.game.pixel_art.draw_player") as draw_player,
                mock.patch("src.game.pixel_art.draw_chief") as draw_chief,
                mock.patch("src.game.pixel_art.draw_enemy") as draw_enemy,
            ):
                self.game._draw_gameplay(canvas)
            dave_call = next(call for call in draw_player.call_args_list if call.args[6] == "black_dave")
            observed.append(
                (
                    dave_call.args[7],
                    draw_chief.call_args.kwargs["frame"],
                    draw_enemy.call_args.kwargs["frame"],
                )
            )

        self.assertEqual(observed, [expected, expected])

    def test_30_and_60_fps_sampling_observe_the_same_pose_timeline(self) -> None:
        self.assertEqual(ANIMATION_TICKS_PER_SECOND, 30.0)
        ticks_at_30 = [_animation_tick(frame / 30.0) for frame in range(30)]
        ticks_at_60 = [_animation_tick(frame / 60.0) for frame in range(60)]
        self.assertEqual(ticks_at_60[::2], ticks_at_30)
        self.assertTrue(all(next_tick - tick in {0, 1} for tick, next_tick in zip(ticks_at_60, ticks_at_60[1:])))

        frames_at_30 = [
            pygame.image.tobytes(sprite_atlas.player_frame("black_dave", "walk", tick), "RGBA")
            for tick in ticks_at_30
        ]
        frames_at_60_common_times = [
            pygame.image.tobytes(sprite_atlas.player_frame("black_dave", "walk", tick), "RGBA")
            for tick in ticks_at_60[::2]
        ]
        self.assertEqual(frames_at_60_common_times, frames_at_30)

    def test_player_walk_phase_is_distance_driven_and_survives_a_real_stop(self) -> None:
        player = next(candidate for candidate in self.game.players if not candidate.is_cpu)
        held_right = InputSnapshot(move_x=1.0)
        initial_distance = player.locomotion_distance

        with mock.patch.object(self.game, "move_actor", return_value=(2.0, 0.0)):
            for _ in range(12):
                player.update(held_right, self.game, 1.0 / 60.0)
                player.advance_animation(1.0 / 60.0)

        self.assertEqual(player.state, "walk")
        travelled_before_stop = player.locomotion_distance
        walk_tick_before_stop = player.animation_tick
        self.assertAlmostEqual(travelled_before_stop - initial_distance, 24.0, delta=0.001)

        with mock.patch.object(self.game, "move_actor", return_value=(0.0, 0.0)):
            for _ in range(30):
                player.update(held_right, self.game, 1.0 / 60.0)
                player.advance_animation(1.0 / 60.0)

        self.assertEqual(player.state, "idle")
        self.assertEqual(player.animation_state, "idle")
        self.assertEqual(player.locomotion_distance, travelled_before_stop)

        with mock.patch.object(self.game, "move_actor", return_value=(2.0, 0.0)):
            player.update(held_right, self.game, 1.0 / 60.0)
            player.advance_animation(1.0 / 60.0)
        self.assertEqual(player.state, "walk")
        self.assertAlmostEqual(player.locomotion_distance, travelled_before_stop + 2.0)
        self.assertGreaterEqual(player.animation_tick, walk_tick_before_stop)

    def test_normal_hero_speed_presents_thirty_six_smooth_walk_cels_per_second(self) -> None:
        player = next(candidate for candidate in self.game.players if not candidate.is_cpu)
        player.state = "walk"
        player.locomotion_distance = 0.0
        normal_speed = float(player.config["global"]["x_speed"])
        signatures: list[bytes] = []
        for _frame in range(61):
            signatures.append(
                pygame.image.tobytes(
                    sprite_atlas.player_frame(player.character, "walk", player.animation_tick),
                    "RGBA",
                )
            )
            player.locomotion_distance += normal_speed / 60.0

        transitions = sum(first != second for first, second in zip(signatures, signatures[1:]))
        expected = normal_speed * 24.0 / _HERO_STRIDE_DISTANCE
        self.assertAlmostEqual(expected, 36.0, delta=0.01)
        self.assertIn(transitions, {35, 36, 37})

    def test_enemy_chase_clock_stops_cleanly_when_navigation_applies_no_motion(self) -> None:
        enemy = Enemy(77, "stick", 90.0, 260.0, self.game.data["enemies"]["stick"])
        enemy.state = "chase"
        enemy.cooldown = 99.0
        target = next(candidate for candidate in self.game.players if not candidate.is_cpu)
        target.x = 400.0
        target.y = 260.0

        with (
            mock.patch.object(self.game, "nearest_player", return_value=target),
            mock.patch.object(self.game, "move_enemy_toward", return_value=(2.0, 0.0)),
        ):
            enemy.update(self.game, 1.0 / 60.0)
            enemy.advance_animation(1.0 / 60.0)
            first_distance = enemy.locomotion_distance
            enemy.update(self.game, 1.0 / 60.0)
            enemy.advance_animation(1.0 / 60.0)
            second_distance = enemy.locomotion_distance

        self.assertEqual(enemy.state, "chase")
        self.assertAlmostEqual(second_distance - first_distance, 2.0)

        with (
            mock.patch.object(self.game, "nearest_player", return_value=target),
            mock.patch.object(self.game, "move_enemy_toward", return_value=(0.0, 0.0)),
        ):
            enemy.update(self.game, 1.0 / 60.0)
            enemy.advance_animation(1.0 / 60.0)

        self.assertEqual(enemy.state, "idle")
        self.assertEqual(enemy.animation_state, "idle")
        self.assertEqual(enemy.locomotion_distance, second_distance)

    def test_blocked_chief_command_uses_guard_art_until_motion_is_applied(self) -> None:
        chief = self.game.chiefs[0]
        caller = chief.owner
        target = Enemy(91, "stick", chief.x + 180.0, chief.y, self.game.data["enemies"]["stick"])
        target.state = "chase"
        target.cooldown = 99.0
        self.game.enemies = [target]
        self.assertTrue(chief.start_command(caller, target, self.game))

        with mock.patch.object(self.game, "move_actor", return_value=(0.0, 0.0)):
            chief.update(self.game, 1.0 / ANIMATION_TICKS_PER_SECOND)
            chief.advance_animation(1.0 / ANIMATION_TICKS_PER_SECOND)
        self.assertFalse(chief.animation_moving)
        self.assertEqual(chief.visual_animation_state, "guard")

        with mock.patch.object(self.game, "move_actor", return_value=(3.0, 0.0)):
            chief.update(self.game, 1.0 / ANIMATION_TICKS_PER_SECOND)
            chief.advance_animation(1.0 / ANIMATION_TICKS_PER_SECOND)
        self.assertTrue(chief.animation_moving)
        self.assertEqual(chief.visual_animation_state, "command")

    def test_action_state_clock_and_render_tick_remain_authoritative(self) -> None:
        player = next(candidate for candidate in self.game.players if not candidate.is_cpu)
        player.set_state("hurt", 1.0)
        player.animation_clock = 99.0
        player.update(InputSnapshot(), self.game, 0.125)
        player.advance_animation(0.125)

        self.assertAlmostEqual(player.state_clock, 0.125)
        self.game.frame = 9_999
        canvas = pygame.Surface((640, 360), pygame.SRCALPHA)
        with mock.patch("src.game.pixel_art.draw_player") as draw_player:
            self.game._draw_gameplay(canvas)

        dave_call = next(call for call in draw_player.call_args_list if call.args[6] == "black_dave")
        self.assertEqual(dave_call.args[5], "hurt")
        self.assertEqual(dave_call.args[7], int(player.state_clock * ANIMATION_TICKS_PER_SECOND))


if __name__ == "__main__":
    unittest.main()
