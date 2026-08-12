"""Gameplay-to-audio routing regressions for character voices and support calls."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.entities import Enemy
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


class GameplayAudioEventTests(unittest.TestCase):
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
        self.game.select_slots = [SelectSlot({"type": "keyboard"}, 0, True)]
        self.game._start_stage()
        self.dave = next(player for player in self.game.players if player.character == "black_dave")

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def test_nonlethal_and_downed_damage_route_distinct_character_voices(self) -> None:
        with mock.patch.object(self.game.audio, "play_character", return_value=True) as voice:
            self.assertTrue(self.dave.take_damage(10.0, self.game))
            voice.assert_called_once_with("black_dave", "hurt")

            self.dave.invulnerable = 0.0
            self.assertTrue(self.dave.take_damage(self.dave.max_health * 2.0, self.game))
            self.assertEqual(voice.call_args_list[-1], mock.call("black_dave", "downed"))

    def test_successful_chief_command_uses_callers_voice(self) -> None:
        target = Enemy(
            enemy_id=999,
            kind="stick",
            x=self.dave.x + 75.0,
            y=self.dave.y,
            stats=dict(self.game.data["enemies"]["stick"]),
            health=100.0,
            max_health=100.0,
            state="idle",
        )
        self.game.enemies = [target]
        with mock.patch.object(self.game.audio, "play_character", return_value=True) as voice:
            self.assertTrue(self.game.command_chief(self.dave))
        voice.assert_called_once_with("black_dave", "chief")


if __name__ == "__main__":
    unittest.main()
