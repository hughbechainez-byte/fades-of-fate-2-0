"""Crowd-control, encounter-density, and Chief maul gameplay contracts."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.entities import Enemy
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


class CombatSystemsTests(unittest.TestCase):
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

    def test_bass_drop_wipes_active_map_including_boss_and_pending_wave(self) -> None:
        distant = self.enemy(810, self.dave.x + 1450.0, self.dave.y, "stick")
        couch = self.enemy(811, self.dave.x + 2400.0, self.dave.y, "couch")
        arriving = Enemy(812, "pipe", self.dave.x + 850.0, self.dave.y, self.game.data["enemies"]["pipe"])
        self.game.enemies = [distant, couch, arriving]
        self.game.spawn_queue = ["stick", "pipe"]
        self.game.effects.clear()

        self.game.activate_super(self.dave)

        self.assertEqual((distant.state, couch.state, arriving.state), ("dead", "dead", "dead"))
        self.assertEqual(self.game.spawn_queue, [])
        self.assertGreater(self.game.hitstop_remaining, 0.0)
        self.assertIn("bass_drop", {effect.kind for effect in self.game.effects})
        self.assertIn("shock", {effect.kind for effect in self.game.effects})
        canvas = pygame.Surface((640, 360), pygame.SRCALPHA)
        self.game._draw_effects(canvas)
        self.assertGreater(pygame.mask.from_surface(canvas).count(), 400)

    def test_combo_follow_through_resolves_one_clear_front_target(self) -> None:
        self.dave.x, self.dave.y, self.dave.facing = 300.0, 270.0, 1
        move = self.game.data["moves"]["light_combo"][1]
        front = self.enemy(820, self.dave.x + 34.0, self.dave.y)
        rear = self.enemy(821, self.dave.x - 31.0, self.dave.y)
        side = self.enemy(822, self.dave.x, self.dave.y + 39.0)
        far = self.enemy(823, self.dave.x + float(move["combo_radius"]) + 35.0, self.dave.y)
        self.game.enemies = [front, rear, side, far]
        self.dave.combo_step = 1
        self.game.effects.clear()

        hits = self.game.player_attack(self.dave, move, "light", already_hit=set())

        self.assertEqual(hits, 1)
        self.assertLess(front.health, front.max_health)
        self.assertTrue(all(enemy.health == enemy.max_health for enemy in (rear, side, far)))
        self.assertIn("fist", {effect.kind for effect in self.game.effects})

    def test_focused_wave_caps_queue_and_scales_spawned_enemies_tougher(self) -> None:
        encounter = self.game.data["encounters"][0]
        baseline_count = len(encounter["base"])
        base_stats = self.game.data["enemies"]["stick"]

        self.game._begin_encounter(encounter)
        focus_cap = int(self.game.data["scaling"]["focused_enemy_queue_cap"][0])
        self.assertEqual(len(self.game.spawn_queue), focus_cap)
        self.assertLess(len(self.game.spawn_queue), baseline_count)
        self.assertLessEqual(
            int(self.game.data["scaling"]["enemy_caps"][0]),
            len(self.game.spawn_queue),
        )
        self.game._spawn_enemy("stick")
        spawned = self.game.enemies[-1]

        self.assertAlmostEqual(
            spawned.max_health,
            float(base_stats["health"]) * float(self.game.data["scaling"]["enemy_durability_scale"][0]),
        )
        self.assertGreater(spawned.max_health, float(base_stats["health"]))
        self.assertAlmostEqual(
            float(spawned.stats["damage"]),
            float(base_stats["damage"]) * float(self.game.data["scaling"]["enemy_damage_scale"][0]),
        )
        self.assertAlmostEqual(
            float(spawned.stats["score"]),
            float(base_stats["score"]) * float(self.game.data["scaling"]["enemy_score_scale"][0]),
        )

    def test_chief_frenzy_maul_is_a_short_grounded_hold_without_extra_ticks(self) -> None:
        chief = self.game.chiefs[0]
        target = self.enemy(830, chief.x, chief.y)
        target.health = float(self.game.data["chief"]["frenzy_damage"]) + 1.0
        self.game.enemies = [target]
        chief.frenzy = 1.0
        chief.attack_cooldown = 0.0

        chief.update(self.game, 1.0 / 60.0)

        self.assertEqual(target.state, "down")
        self.assertEqual(chief.visual_animation_state, "maul")
        self.assertGreater(chief.maul_timer, 0.0)
        before = target.health
        chief.update(self.game, 1.0 / 60.0)
        self.assertEqual(target.health, before)


if __name__ == "__main__":
    unittest.main()
