from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.config import campaign_levels
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


class EnemyHealthBarTests(unittest.TestCase):
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
            SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
        ]
        self.game._start_stage()
        self.surface = pygame.Surface((640, 360), pygame.SRCALPHA)

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def test_every_regular_enemy_kind_gets_one_world_health_bar(self) -> None:
        kinds = ("stick", "cart", "whip", "pipe", "homeless", "security")
        self.game.enemies.clear()
        for index, kind in enumerate(kinds):
            enemy = self.game._spawn_enemy(kind)
            enemy.x = self.game.camera_x + 110.0 + index * 55.0
            enemy.y = 220.0 + index * 5.0
            enemy.health = enemy.max_health * 0.5

        rendered_rects = [pygame.Rect(70 + index * 60, 120, 48, 72) for index in range(len(kinds))]
        with (
            mock.patch("src.game.pixel_art.draw_enemy", side_effect=rendered_rects),
            mock.patch.object(self.game, "_draw_enemy_health_bar") as draw_health_bar,
        ):
            self.game._draw_gameplay(self.surface)

        self.assertEqual(draw_health_bar.call_count, len(kinds))
        self.assertEqual(
            [call.args[1].kind for call in draw_health_bar.call_args_list],
            list(kinds),
        )
        self.assertEqual(
            [call.args[2] for call in draw_health_bar.call_args_list],
            rendered_rects,
        )

    def test_multiple_enemy_bars_do_not_repeat_transition_or_pause_overlays(self) -> None:
        self.game.enemies.clear()
        for kind in ("stick", "cart", "security"):
            self.game._spawn_enemy(kind)
        self.game.boss_transition = mock.sentinel.transition
        self.game.pause = True

        with (
            mock.patch(
                "src.game.pixel_art.draw_enemy",
                side_effect=[pygame.Rect(80 + index * 70, 110, 48, 72) for index in range(3)],
            ),
            mock.patch.object(self.game, "_draw_boss_loading_overlay") as draw_transition,
            mock.patch.object(self.game, "_draw_pause_menu") as draw_pause,
        ):
            self.game._draw_gameplay(self.surface)

        draw_transition.assert_called_once_with(self.surface)
        draw_pause.assert_called_once_with(self.surface)

    def test_regular_enemy_bar_tracks_sprite_and_clamps_health_fraction(self) -> None:
        enemy = self.game._spawn_enemy("stick")
        enemy.health = enemy.max_health * 1.5
        rendered_rect = pygame.Rect(100, 80, 48, 60)

        with mock.patch.object(self.game, "_bar") as draw_bar:
            self.game._draw_enemy_health_bar(self.surface, enemy, rendered_rect)

        draw_bar.assert_called_once()
        _, bar_rect, fraction, fill, back = draw_bar.call_args.args
        self.assertEqual(bar_rect, pygame.Rect(106, 74, 36, 4))
        self.assertEqual(fraction, 1.0)
        self.assertEqual(fill, (239, 78, 174))
        self.assertEqual(back, (69, 20, 57))

    def test_dead_or_invalid_enemy_does_not_draw_a_health_bar(self) -> None:
        enemy = self.game._spawn_enemy("stick")
        rendered_rect = pygame.Rect(100, 80, 48, 60)
        with mock.patch.object(self.game, "_bar") as draw_bar:
            enemy.state = "dead"
            self.game._draw_enemy_health_bar(self.surface, enemy, rendered_rect)
            enemy.state = "idle"
            enemy.max_health = 0.0
            self.game._draw_enemy_health_bar(self.surface, enemy, rendered_rect)
        draw_bar.assert_not_called()

    def test_couch_keeps_one_boss_hud_bar_without_a_duplicate_world_bar(self) -> None:
        finale = campaign_levels(self.game.data)[-1]
        self.game._select_campaign_level(str(finale["id"]))
        self.game._start_stage()
        self.game.enemies.clear()
        boss = self.game._spawn_enemy("couch")
        boss.health = boss.max_health * 0.4

        with (
            mock.patch("src.game.pixel_art.draw_boss", return_value=pygame.Rect(250, 120, 120, 100)),
            mock.patch.object(self.game, "_draw_enemy_health_bar") as draw_world_bar,
        ):
            self.game._draw_gameplay(self.surface)
        draw_world_bar.assert_not_called()

        with mock.patch.object(self.game, "_bar") as draw_bar:
            self.game._draw_hud(self.surface)
        boss_calls = [
            call
            for call in draw_bar.call_args_list
            if call.args[3] == (239, 78, 174) and call.args[4] == (69, 20, 57)
        ]
        self.assertEqual(len(boss_calls), 1)
        self.assertAlmostEqual(boss_calls[0].args[2], 0.4)


if __name__ == "__main__":
    unittest.main()
