from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src import pixel_art, sprite_atlas
from src.game import FadesGame, PLAYABLE_CHARACTERS, SOLO_CPU_COMPANIONS, SelectSlot
from src.input_manager import InputManager


class WhiteDaveIntegrationTests(unittest.TestCase):
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

    def test_white_dave_is_fourth_selectable_hero(self) -> None:
        self.assertEqual(PLAYABLE_CHARACTERS[3], "white_dave")
        self.game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=3, confirmed=True)]
        self.assertEqual(
            self.game._selection_footer_lines()[0],
            "YOU CONTROL: WHITE DAVE  •  CPU COMPANION: SHELLY",
        )
        self.game._start_stage()
        human = next(player for player in self.game.players if not player.is_cpu)
        self.assertEqual(human.character, "white_dave")

    def test_white_dave_is_jermaine_height_but_slower_and_more_powerful(self) -> None:
        players = self.game.data["players"]
        white_dave, jermaine = players["white_dave"], players["jermaine"]
        self.assertEqual(white_dave["height_scale"], jermaine["height_scale"])
        self.assertLess(white_dave["speed_scale"], jermaine["speed_scale"])
        self.assertGreater(white_dave["weapon_damage_scale"], jermaine["weapon_damage_scale"])
        self.assertGreater(white_dave["max_health"], jermaine["max_health"])
        self.assertEqual(white_dave["weapon"], "BOLT CUTTERS")

    def test_white_dave_is_optional_standard_cpu_support(self) -> None:
        self.assertEqual(SOLO_CPU_COMPANIONS[2], "ko")
        self.assertEqual(SOLO_CPU_COMPANIONS[3], "white_dave")
        self.game.select_slots = [
            SelectSlot(
                {"type": "keyboard"},
                character_index=0,
                confirmed=True,
                cpu_companion_index=3,
            )
        ]
        self.game._start_stage()
        cpu_players = [player for player in self.game.players if player.is_cpu]
        self.assertEqual(len(cpu_players), 1)
        self.assertEqual(cpu_players[0].character, "white_dave")
        self.assertEqual(cpu_players[0].binding, {"type": "cpu", "instance_id": -2})
        self.assertIsNone(self.game.ko_companion)

    def test_white_dave_uses_dedicated_authored_foundation_model(self) -> None:
        self.assertIsNotNone(sprite_atlas.player_frame("white_dave", "idle", 0))
        self.assertEqual(len(sprite_atlas.foundation_character_frames("white_dave", "idle")), 8)
        self.assertEqual(len(sprite_atlas.foundation_character_frames("white_dave", "walk")), 12)
        self.assertEqual(len(sprite_atlas.foundation_character_frames("white_dave", "attack_1")), 8)
        self.assertIsNone(sprite_atlas.player_frame("white_dave", "hurt", 0))
        canvas = pygame.Surface((240, 180), pygame.SRCALPHA)
        rect = pixel_art.draw_player(canvas, 120, 165, 0, 1, "idle", "white_dave", 0, (205, 82, 57))
        jermaine_canvas = pygame.Surface((240, 180), pygame.SRCALPHA)
        jermaine_rect = pixel_art.draw_player(
            jermaine_canvas, 120, 165, 0, 1, "idle", "jermaine", 0, (255, 218, 76)
        )
        self.assertGreaterEqual(rect.height, 100)
        self.assertGreaterEqual(jermaine_rect.height, 100)
        self.assertGreater(pygame.mask.from_surface(canvas).count(), 1_000)

    def test_white_dave_loading_pose_is_visible(self) -> None:
        canvas = pygame.Surface((180, 140), pygame.SRCALPHA)
        rect = pixel_art.draw_white_dave_loading(canvas, 90, 128, frame=2)
        self.assertTrue(rect.colliderect(canvas.get_rect()))
        self.assertGreater(pygame.mask.from_surface(canvas).count(), 650)


if __name__ == "__main__":
    unittest.main()
