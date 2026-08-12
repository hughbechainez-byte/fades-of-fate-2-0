"""Regression coverage for development-mode unlimited lives."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


class DevelopmentLivesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((640, 360))

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        self.manager = InputManager(discover_controllers=False)
        self.game = FadesGame(self.manager, mute=True)
        self.game.select_slots = [
            SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
        ]
        self.game._start_stage()

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def test_repeated_party_knockdowns_respawn_even_with_zero_lives(self) -> None:
        self.assertTrue(self.game.development_unlimited_lives)
        for player in self.game.players:
            self.assertTrue(player.unlimited_lives)
            player.lives = 0

        for _ in range(6):
            for player in self.game.players:
                player.health = player.max_health
                player.invulnerable = 0.0
                player.set_state("idle")
                self.assertTrue(player.take_damage(player.max_health * 2.0, self.game))
                player.down_timer = 0.0

            self.game.update(1.0 / 60.0)
            self.assertEqual(self.game.state, "gameplay")
            self.assertTrue(all(player.state == "dead" for player in self.game.players))
            self.assertTrue(all(player.lives == 0 for player in self.game.players))

            for player in self.game.players:
                player.respawn_timer = 0.0
            self.game.update(1.0 / 60.0)
            self.assertEqual(self.game.state, "gameplay")
            self.assertTrue(all(player.state == "idle" for player in self.game.players))
            self.assertTrue(all(player.health > 0.0 for player in self.game.players))

    def test_hud_marks_unlimited_lives_as_development_mode(self) -> None:
        canvas = pygame.Surface((640, 360))
        with mock.patch.object(self.game, "_text") as draw_text:
            self.game._draw_hud(canvas)

        labels = [
            call.args[2]
            for call in draw_text.call_args_list
            if len(call.args) >= 3 and isinstance(call.args[2], str)
        ]
        self.assertTrue(any("DEV ∞" in label for label in labels), labels)


if __name__ == "__main__":
    unittest.main()
