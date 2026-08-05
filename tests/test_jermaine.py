from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src import pixel_art, sprite_atlas
from src.entities import Player
from src.game import FadesGame, PLAYABLE_CHARACTERS, SelectSlot
from src.input_manager import InputManager, InputSnapshot


class JermaineIntegrationTests(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def test_jermaine_is_third_selectable_hero_and_solo_gets_cpu_shelly(self) -> None:
        self.assertEqual(PLAYABLE_CHARACTERS[2], "jermaine")
        self.game.select_slots = [
            SelectSlot({"type": "keyboard"}, character_index=2, confirmed=True)
        ]
        self.assertEqual(
            self.game._selection_footer_lines()[0],
            "YOU CONTROL: JERMAINE  •  CPU COMPANION: SHELLY",
        )
        self.game._start_stage()
        human = next(player for player in self.game.players if not player.is_cpu)
        companion = next(player for player in self.game.players if player.is_cpu)
        self.assertEqual((human.character, companion.character), ("jermaine", "shelly"))

    def test_jermaine_config_is_taller_and_lean_stick_fighter(self) -> None:
        players = self.game.data["players"]
        self.assertGreater(players["jermaine"]["height_scale"], players["black_dave"]["height_scale"])
        self.assertEqual(players["jermaine"]["weapon"], "STICK")
        self.assertGreater(players["jermaine"]["weapon_reach_bonus"], 0)

    def test_jermaine_uses_dedicated_authored_foundation_model(self) -> None:
        self.assertIsNotNone(sprite_atlas.player_frame("jermaine", "idle", 0))
        self.assertEqual(len(sprite_atlas.foundation_character_frames("jermaine", "idle")), 8)
        self.assertEqual(len(sprite_atlas.foundation_character_frames("jermaine", "walk")), 8)
        self.assertEqual(len(sprite_atlas.foundation_character_frames("jermaine", "attack_1")), 8)
        self.assertIsNotNone(sprite_atlas.player_frame("jermaine", "hurt", 0))
        canvas = pygame.Surface((220, 180), pygame.SRCALPHA)
        rect = pixel_art.draw_player(
            canvas, 110, 165, 0, 1, "idle", "jermaine", 0, (255, 218, 76)
        )
        self.assertGreaterEqual(rect.height, 96)
        self.assertLess(rect.width, rect.height + 15)
        self.assertGreater(pygame.mask.from_surface(canvas).count(), 300)
        hurt_canvas = pygame.Surface((220, 180), pygame.SRCALPHA)
        hurt_rect = pixel_art.draw_player(
            hurt_canvas, 110, 165, 0, 1, "hurt", "jermaine", 0, (255, 218, 76)
        )
        self.assertGreaterEqual(hurt_rect.height, rect.height)

    def test_jermaine_loading_pose_has_money_and_cigarette_pixels(self) -> None:
        canvas = pygame.Surface((160, 120), pygame.SRCALPHA)
        rect = pixel_art.draw_jermaine_loading(canvas, 80, 112, frame=2)
        self.assertTrue(rect.colliderect(canvas.get_rect()))
        self.assertGreater(pygame.mask.from_surface(canvas).count(), 250)

    def test_jermaine_repeats_censored_bark_on_bounded_cadence(self) -> None:
        player = Player(
            slot=0,
            character="jermaine",
            binding={"type": "keyboard"},
            x=120.0,
            y=270.0,
            config=self.game.data["players"],
            moves=self.game.data["moves"],
        )
        for _ in range(3):
            player._maybe_bark_as_jermaine(self.game)
        bark = next(effect for effect in self.game.effects if effect.text == "IMA F*** CUZ UP")
        self.assertEqual(bark.kind, "text")
        effect_count = len(self.game.effects)
        for _ in range(6):
            player._maybe_bark_as_jermaine(self.game)
        self.assertEqual(len(self.game.effects), effect_count)


if __name__ == "__main__":
    unittest.main()
