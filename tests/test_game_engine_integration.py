from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.combat_engine import HitBox
from src.entities import Effect, Enemy
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager
from src.world_engine import WorldPoint


class GameplayEngineIntegrationTests(unittest.TestCase):
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

    def test_cpu_companion_cannot_drive_camera_or_trigger_encounter(self) -> None:
        human = next(player for player in self.game.players if not player.is_cpu)
        cpu = next(player for player in self.game.players if player.is_cpu)
        human.x = 100.0
        cpu.x = 620.0

        self.game._update_camera(0.5)
        self.game._update_encounters(0.0)

        self.assertEqual(self.game.camera_x, 0.0)
        self.assertFalse(self.game.encounter_active)
        self.assertEqual(self.game.encounter_index, 0)

    def test_shared_world_movement_cannot_cross_sprouts_cart_return(self) -> None:
        human = next(player for player in self.game.players if not player.is_cpu)
        self.game.camera_x = 0.0
        human.x = 420.0
        human.y = 247.0

        self.game.move_actor(human, 120.0, 0.0)

        self.assertLessEqual(human.x, 430.0)
        self.assertTrue(
            self.game.stage_geometry.is_walkable(
                WorldPoint(human.x, human.y, human.z),
                float(self.game.data["engine"]["physics"]["player_radius_depth"]),
            )
        )

    def test_light_punch_breaks_a_cone_and_heavier_props_need_two_hits(self) -> None:
        human = next(player for player in self.game.players if not player.is_cpu)
        cart = next(item for item in self.game.data["stage_geometry"]["obstacles"] if item["kind"] == "cart_return")
        self.game._obstacle_health[cart["id"]] = 2

        cart_hit = HitBox(("player_attack", human.slot, 2, "heavy", 2), ("player", human.slot), "player", float(cart["x"]), float(cart["depth"]), half_width=40.0, half_depth=12.0, damage=1.0)

        self.assertEqual(self.game._damage_obstacles_from_attack(human, cart_hit, {"obstacle_damage": 1}), 1)
        self.assertEqual(self.game._obstacle_health[cart["id"]], 1)
        self.assertEqual(self.game._damage_obstacles_from_attack(human, cart_hit, {"obstacle_damage": 1}), 1)
        self.assertEqual(self.game._obstacle_health[cart["id"]], 0)

    def test_ground_attack_misses_a_high_jumping_player(self) -> None:
        player = next(player for player in self.game.players if not player.is_cpu)
        cpu = next(player for player in self.game.players if player.is_cpu)
        cpu.x = player.x - 180.0
        enemy = Enemy(500, "stick", player.x + 4.0, player.y, self.game.data["enemies"]["stick"])
        enemy.state = "chase"
        enemy.facing = -1
        self.game.enemies = [enemy]
        player.z = 60.0
        before = player.health

        self.assertFalse(self.game.enemy_attack(enemy, range_x=34.0, range_y=18.0, damage=7.0))
        self.assertEqual(player.health, before)

        player.z = 0.0
        self.assertTrue(self.game.enemy_attack(enemy, range_x=34.0, range_y=18.0, damage=7.0))
        self.assertLess(player.health, before)

    def test_encounter_pan_finishes_as_a_camera_lock(self) -> None:
        human = next(player for player in self.game.players if not player.is_cpu)
        human.x = 490.0
        self.game._update_encounters(0.0)
        self.assertTrue(self.game.encounter_active)
        self.assertTrue(self.game.camera.panning)

        for _ in range(90):
            self.game._update_camera(1.0 / 60.0)

        target = float(self.game.data["encounters"][0]["camera_x"])
        self.assertTrue(self.game.camera.encounter_locked)
        self.assertAlmostEqual(self.game.camera_x, target, places=4)

    def test_allied_heroes_pass_through_while_enemy_contact_still_pushes(self) -> None:
        human, cpu = self.game.players
        human.x = cpu.x = 220.0
        human.y = cpu.y = 270.0
        self.game._resolve_actor_separation()

        self.assertEqual((human.x, human.y), (cpu.x, cpu.y))

        enemy = Enemy(901, "stick", human.x, human.y, self.game.data["enemies"]["stick"])
        enemy.state = "chase"
        self.game.enemies = [enemy]
        self.game._resolve_actor_separation()
        self.assertGreater(abs(human.x - enemy.x) + abs(human.y - enemy.y), 8.0)

    def test_confirmed_hit_emits_spark_ring_and_damage_number(self) -> None:
        human = next(player for player in self.game.players if not player.is_cpu)
        enemy = Enemy(902, "stick", human.x + 30.0, human.y, self.game.data["enemies"]["stick"])
        enemy.state = "chase"
        self.game.enemies = [enemy]
        self.game.effects.clear()

        self.assertTrue(enemy.take_damage(8.0, self.game, human))
        self.assertTrue({"hit", "impact", "text"}.issubset({effect.kind for effect in self.game.effects}))
        self.assertIn("-8", {effect.text for effect in self.game.effects if effect.kind == "text"})

        surface = pygame.Surface((640, 360), pygame.SRCALPHA)
        self.game._draw_effects(surface)
        self.assertGreater(pygame.mask.from_surface(surface).count(), 80)

    def test_effect_motion_scale_and_alpha_are_deterministic(self) -> None:
        effect = Effect(
            "spark",
            10.0,
            20.0,
            duration=0.5,
            vx=40.0,
            vy=-12.0,
            gravity=80.0,
            drag=2.0,
            scale_start=0.5,
            scale_end=1.5,
            alpha_start=240,
            alpha_end=0,
        )

        effect.update(0.1)

        self.assertAlmostEqual(effect.x, 14.0)
        self.assertAlmostEqual(effect.y, 18.8)
        self.assertAlmostEqual(effect.vy, -3.2)
        self.assertAlmostEqual(effect.visual_scale, 0.7)
        self.assertEqual(effect.visual_alpha, 192)

    def test_hit_response_uses_attack_direction_and_density_budget(self) -> None:
        self.game.effects.clear()
        self.game.add_effect(
            "hit",
            260.0,
            220.0,
            color=(255, 220, 80),
            radius=18.0,
            duration=0.18,
            direction=-1.0,
        )

        sparks = [effect for effect in self.game.effects if effect.kind == "spark"]
        dust = next(effect for effect in self.game.effects if effect.kind == "dust")
        self.assertEqual(len(sparks), 4)
        self.assertTrue(all(effect.vx < 0.0 for effect in sparks))
        self.assertLess(dust.vx, 0.0)

        self.game.options = self.game.options.with_overrides(particle_density=0.55)
        self.game.effects.clear()
        self.game.add_effect("hit", 260.0, 220.0, duration=0.18)
        self.assertEqual([effect.kind for effect in self.game.effects], ["hit"])


if __name__ == "__main__":
    unittest.main()
