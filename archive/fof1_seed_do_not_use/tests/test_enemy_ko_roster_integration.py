"""Combined KO-companion and dedicated-enemy roster regressions."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.animation_manifest import (
    ANIMATION_PLAYBACK_HZ,
    action_segment_tick,
    enemy_animation_actor,
)
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


class EnemyKORosterIntegrationTests(unittest.TestCase):
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
        self.game.select_slots = [
            SelectSlot(
                {"type": "keyboard"},
                character_index=0,
                confirmed=True,
                cpu_companion_index=2,
            )
        ]
        self.game._start_stage()
        self.game.enemies.clear()
        self.enemy = self.game._spawn_enemy("bike_patrol_taser")
        self.enemy.x = self.game.camera_x + 260.0
        self.enemy.y = 250.0
        self.surface = pygame.Surface((640, 360), pygame.SRCALPHA)

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def test_ko_states_use_authored_hurt_and_down_but_recovery_stays_dedicated(self) -> None:
        actor = enemy_animation_actor(self.enemy.kind, self.enemy.variant_id)
        rendered_rect = pygame.Rect(220, 120, 52, 92)
        cases = (
            ("ko_dazed", "hurt", False),
            ("ko_fall", "down", False),
            ("recovery", "recovery", True),
        )

        with (
            mock.patch("src.game.pixel_art.draw_enemy", return_value=rendered_rect) as draw_enemy,
            mock.patch.object(self.game, "_draw_enemy_health_bar") as draw_health_bar,
        ):
            for runtime_state, expected_render_state, expects_health_bar in cases:
                with self.subTest(state=runtime_state):
                    draw_enemy.reset_mock()
                    draw_health_bar.reset_mock()
                    self.enemy.state = runtime_state
                    self.enemy.state_clock = 0.20
                    self.enemy.state_duration = 0.60

                    self.game._draw_gameplay(self.surface)

                    draw_enemy.assert_called_once()
                    call = draw_enemy.call_args
                    self.assertEqual(call.kwargs["state"], expected_render_state)
                    self.assertEqual(
                        call.kwargs["kind"],
                        f"{self.enemy.kind}:{self.enemy.variant_id}",
                    )
                    expected_tick = (
                        action_segment_tick(
                            actor,
                            "attack",
                            "recovery",
                            self.enemy.state_clock,
                            self.enemy.state_duration,
                        )
                        if runtime_state == "recovery"
                        else int(self.enemy.state_clock * ANIMATION_PLAYBACK_HZ)
                    )
                    self.assertEqual(call.kwargs["frame"], expected_tick)
                    self.assertEqual(self.enemy.state, runtime_state)
                    self.assertEqual(
                        draw_health_bar.call_count,
                        1 if expects_health_bar else 0,
                    )

    def test_ko_claim_releases_ranged_attack_token_before_daze_and_fall(self) -> None:
        ko = self.game.ko_companion
        assert ko is not None
        self.enemy.state = "attack"
        self.enemy.attack_pattern = "taser"
        self.enemy.attack_fired = True
        self.enemy.ko_claimed = True
        self.enemy.token_held = 1
        self.game.attack_tokens_used = 1

        self.assertTrue(
            self.enemy.begin_ko_sequence(
                self.game,
                ko.owner,
                daze_seconds=0.20,
                fall_seconds=0.10,
            )
        )
        self.assertEqual(self.enemy.state, "ko_dazed")
        self.assertEqual(self.enemy.token_held, 0)
        self.assertEqual(self.game.attack_tokens_used, 0)
        self.assertFalse(self.enemy.targetable)

        self.enemy.update(self.game, 0.20)
        self.assertEqual(self.enemy.state, "ko_fall")
        self.assertEqual(self.enemy.variant_id, "bike_patrol_taser")


if __name__ == "__main__":
    unittest.main()
