"""Regression coverage for Chief's scale and encounter-roster target identity."""

from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src import sprite_atlas
from src.entities import Enemy
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager
from src.pixel_art import draw_chief


class ChiefLiveTargetTests(unittest.TestCase):
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
        self.dave = self.game.players[0]
        self.chief = self.game.chiefs[0]

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def enemy(self, enemy_id: int, x: float, y: float) -> Enemy:
        result = Enemy(
            enemy_id,
            "stick",
            x,
            y,
            self.game.data["enemies"]["stick"],
        )
        result.state = "chase"
        result.cooldown = 99.0
        return result

    def test_maul_uses_standard_chief_art_without_composite_victim_or_scale_jump(self) -> None:
        for tick in range(8):
            with self.subTest(tick=tick):
                maul = sprite_atlas.chief_frame("maul", tick)
                attack = sprite_atlas.chief_frame("attack", tick)
                assert maul is not None and attack is not None
                self.assertEqual(maul.get_size(), attack.get_size())
                self.assertEqual(
                    pygame.image.tobytes(maul, "RGBA"),
                    pygame.image.tobytes(attack, "RGBA"),
                )

        canvas = pygame.Surface((640, 360), pygame.SRCALPHA)
        rendered = draw_chief(canvas, 320, 290, state="maul", frame=3)
        self.assertLessEqual(rendered.w, 128)
        self.assertLessEqual(rendered.h, 88)
        self.assertLess(pygame.mask.from_surface(canvas).count(), 5_000)

    def test_command_rejects_target_object_outside_current_encounter_roster(self) -> None:
        roster_enemy = self.enemy(710, self.chief.x + 60.0, self.chief.y)
        fabricated_same_id = self.enemy(710, self.chief.x + 8.0, self.chief.y)
        self.game.enemies = [roster_enemy]

        self.assertFalse(
            self.chief.start_command(self.dave, fabricated_same_id, self.game)
        )
        self.assertIsNone(self.chief.command_target)
        self.assertEqual(self.chief.command_enemy_id, -1)

    def test_command_retargets_removed_target_then_damages_exact_live_replacement(self) -> None:
        removed = self.enemy(720, self.chief.x + 24.0, self.chief.y)
        replacement = self.enemy(721, self.chief.x + 90.0, self.chief.y)
        self.game.enemies = [removed, replacement]
        self.assertTrue(self.chief.start_command(self.dave, removed, self.game))

        self.game.enemies = [replacement]
        removed_before = removed.health
        replacement_before = replacement.health
        self.chief.update(self.game, 1.0 / 60.0)

        self.assertIs(self.chief.command_target, replacement)
        self.assertEqual(self.chief.command_enemy_id, replacement.enemy_id)
        self.assertEqual(removed.health, removed_before)

        replacement.x, replacement.y = self.chief.x, self.chief.y
        self.chief.update(self.game, 1.0 / 60.0)
        self.assertEqual(
            replacement.health,
            replacement_before - float(self.game.data["chief"]["command_damage"]),
        )
        self.assertEqual(removed.health, removed_before)

    def test_frenzy_cancels_stale_maul_and_hits_a_live_roster_enemy(self) -> None:
        stale = self.enemy(730, self.chief.x, self.chief.y)
        stale.health = 0.0
        stale.state = "dead"
        replacement = self.enemy(731, self.chief.x, self.chief.y)
        self.game.enemies = [stale, replacement]
        self.chief.frenzy = 1.0
        self.chief.attack_cooldown = 0.0
        self.chief.maul_timer = 0.4
        self.chief.maul_target_id = stale.enemy_id
        self.chief.maul_target = stale
        before = replacement.health

        self.chief.update(self.game, 1.0 / 60.0)

        self.assertEqual(
            replacement.health,
            before - float(self.game.data["chief"]["frenzy_damage"]),
        )
        self.assertIs(self.chief.maul_target, replacement)
        self.assertEqual(self.chief.maul_target_id, replacement.enemy_id)
        self.assertEqual(stale.health, 0.0)

    def test_frenzy_does_not_trust_a_fabricated_nearest_enemy_result(self) -> None:
        live = self.enemy(740, self.chief.x, self.chief.y)
        outsider = self.enemy(741, self.chief.x, self.chief.y)
        self.game.enemies = [live]
        self.chief.frenzy = 1.0
        self.chief.attack_cooldown = 0.0
        live_before = live.health
        outsider_before = outsider.health

        with mock.patch.object(self.game, "nearest_enemy", return_value=outsider):
            self.chief.update(self.game, 1.0 / 60.0)

        self.assertLess(live.health, live_before)
        self.assertEqual(outsider.health, outsider_before)


if __name__ == "__main__":
    unittest.main()
