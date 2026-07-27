"""End-to-end checks for Black Dave's finite-ammo BB gun."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.entities import AmmoPickup, Enemy
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


class BBGunTests(unittest.TestCase):
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
        self.game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
        self.game._start_stage()
        self.dave, self.shelly = self.game.players
        self.shelly.cpu_action_cooldown = 99.0
        self.shelly.chief_meter = 0.0
        self.shelly.super_meter = 0.0

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def enemy(self, enemy_id: int, x: float, y: float, kind: str = "stick") -> Enemy:
        result = Enemy(enemy_id, kind, x, y, self.game.data["enemies"][kind])
        result.state = "chase"
        result.cooldown = 99.0
        return result

    def test_keyboard_shot_dispatches_during_hitstop_and_obeys_cooldown(self) -> None:
        initial = self.dave.bb_ammo
        self.game.hitstop_remaining = 0.20
        self.manager.process_events(
            (pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_g, "repeat": False}),)
        )

        self.game.update(1.0 / 60.0)

        self.assertEqual(self.dave.bb_ammo, initial - 1)
        self.assertEqual(len(self.game.projectiles), 1)
        self.assertEqual(self.game.projectiles[0].kind, "bb")
        self.assertGreater(self.dave.bb_cooldown, 0.0)
        self.assertFalse(self.game.fire_bb_gun(self.dave))
        self.assertEqual(self.dave.bb_ammo, initial - 1)
        self.assertTrue(any(effect.kind == "text" and effect.text == "BB NOT READY" for effect in self.game.effects))

    def test_controller_left_trigger_uses_live_gameplay_path(self) -> None:
        instance_id = 88
        self.manager.add_synthetic_controller(instance_id)
        binding = {"type": "controller", "instance_id": instance_id}
        self.game.select_slots = [SelectSlot(binding, character_index=0, confirmed=True)]
        self.game._start_stage()
        dave = self.game.players[0]
        initial = dave.bb_ammo
        self.game.hitstop_remaining = 0.20
        self.manager.process_events(
            (
                pygame.event.Event(
                    pygame.CONTROLLERAXISMOTION,
                    {
                        "instance_id": instance_id,
                        "axis": pygame.CONTROLLER_AXIS_TRIGGERLEFT,
                        "value": 24_576,
                    },
                ),
            )
        )

        self.game.update(1.0 / 60.0)

        self.assertEqual(dave.bb_ammo, initial - 1)
        self.assertEqual([projectile.kind for projectile in self.game.projectiles], ["bb"])

    def test_shelly_is_rejected_without_spawning_or_spending_ammo(self) -> None:
        before = len(self.game.projectiles)
        self.assertFalse(self.game.fire_bb_gun(self.shelly))
        self.assertEqual(len(self.game.projectiles), before)
        self.assertEqual(self.shelly.bb_ammo, 0)
        self.assertTrue(any(effect.kind == "text" and effect.text == "DAVE ONLY" for effect in self.game.effects))

    def test_swept_projectile_hits_nearest_aligned_enemy_without_friendly_fire(self) -> None:
        aligned = self.enemy(10, self.dave.x + 90.0, self.dave.y)
        farther = self.enemy(11, self.dave.x + 110.0, self.dave.y)
        off_lane = self.enemy(12, self.dave.x + 75.0, self.dave.y + 32.0)
        self.game.enemies = [farther, off_lane, aligned]
        dave_health = self.dave.health
        shelly_health = self.shelly.health
        before = aligned.health

        self.assertTrue(self.game.fire_bb_gun(self.dave))
        shot = self.game.projectiles[-1]
        start_y = shot.y
        shot.update(self.game, 0.30)

        self.assertTrue(shot.spent)
        self.assertEqual(shot.y, start_y)
        self.assertEqual(aligned.health, before - float(self.game.data["bb_gun"]["damage"]))
        self.assertEqual(farther.health, farther.max_health)
        self.assertEqual(off_lane.health, off_lane.max_health)
        self.assertEqual((self.dave.health, self.shelly.health), (dave_health, shelly_health))

    def test_off_lane_enemy_is_not_hit(self) -> None:
        target = self.enemy(13, self.dave.x + 90.0, self.dave.y + 35.0)
        self.game.enemies = [target]
        self.assertTrue(self.game.fire_bb_gun(self.dave))
        shot = self.game.projectiles[-1]
        shot.update(self.game, 0.30)
        self.assertEqual(target.health, target.max_health)
        self.assertFalse(shot.spent)

    def test_drop_schedule_is_deterministic_and_excludes_boss(self) -> None:
        drops_at: list[int] = []
        for ko_number in range(1, 10):
            defeated = self.enemy(100 + ko_number, 300.0 + ko_number, 270.0)
            self.game.enemy_defeated(defeated, self.dave)
            if len(self.game.ammo_pickups) > len(drops_at):
                drops_at.append(ko_number)
        self.assertEqual(drops_at, [2, 6, 9])
        self.assertEqual(self.game.bb_next_drop_at, 12)

        before_kos = self.game.bb_eligible_kos
        before_drops = len(self.game.ammo_pickups)
        self.game.enemy_defeated(self.enemy(199, 500.0, 270.0, kind="couch"), self.dave)
        self.assertEqual(self.game.bb_eligible_kos, before_kos)
        self.assertEqual(len(self.game.ammo_pickups), before_drops)

    def test_pickup_is_dave_only_clamped_and_non_solid(self) -> None:
        maximum = int(self.game.data["bb_gun"]["max_ammo"])
        pickup = AmmoPickup(self.shelly.x, self.shelly.y, amount=3)
        self.game.ammo_pickups = [pickup]
        pickup.update(self.game, 1.0 / 60.0)
        self.assertFalse(pickup.spent)
        self.assertEqual(self.shelly.bb_ammo, 0)

        self.dave.bb_ammo = maximum - 1
        self.dave.x, self.dave.y = pickup.x, pickup.y
        pickup_position = (pickup.x, pickup.y)
        self.game._resolve_actor_separation()
        self.assertEqual((pickup.x, pickup.y), pickup_position)
        pickup.update(self.game, 1.0 / 60.0)
        self.assertTrue(pickup.spent)
        self.assertEqual(self.dave.bb_ammo, maximum)

    def test_cpu_dave_fires_only_when_aligned_at_sensible_range(self) -> None:
        self.game.select_slots = [
            SelectSlot({"type": "keyboard"}, character_index=1, confirmed=True)
        ]
        self.game._start_stage()
        shelly, dave = self.game.players
        target = self.enemy(300, dave.x + 120.0, dave.y)
        self.game.enemies = [target]
        dave.chief_meter = 0.0
        dave.super_meter = 0.0
        initial = dave.bb_ammo

        snapshot = self.game._cpu_snapshot(dave, 1.0 / 60.0)
        self.assertIn("secondary", snapshot.pressed)
        dave.cpu_action_cooldown = 0.0
        self.game.update(1.0 / 60.0)
        self.assertEqual(dave.bb_ammo, initial - 1)
        self.assertTrue(any(projectile.kind == "bb" for projectile in self.game.projectiles))

    def test_cpu_dave_does_not_spend_a_shot_outside_actual_hit_lane(self) -> None:
        self.game.select_slots = [
            SelectSlot({"type": "keyboard"}, character_index=1, confirmed=True)
        ]
        self.game._start_stage()
        _, dave = self.game.players
        hit_depth = float(self.game.data["bb_gun"]["lane_tolerance"]) + float(
            self.game.data["engine"]["physics"]["enemy_radius_depth"]
        )
        target = self.enemy(301, dave.x + 120.0, dave.y + hit_depth + 0.5)
        self.game.enemies = [target]
        dave.chief_meter = 0.0
        dave.super_meter = 0.0

        snapshot = self.game._cpu_snapshot(dave, 1.0 / 60.0)

        self.assertNotIn("secondary", snapshot.pressed)

    def test_projectile_travel_clamps_to_configured_range_when_dt_overshoots(self) -> None:
        self.game.enemies.clear()
        self.assertTrue(self.game.fire_bb_gun(self.dave))
        shot = self.game.projectiles[-1]
        start_x = shot.x
        configured_range = float(self.game.data["bb_gun"]["range"])

        shot.update(self.game, shot.ttl + 0.75)

        self.assertAlmostEqual(shot.x, start_x + configured_range, places=5)
        self.assertTrue(shot.spent)

    def test_hud_renders_segmented_ammo_row(self) -> None:
        bb_max = max(1, int(self.game.data["bb_gun"]["max_ammo"]))
        self.dave.bb_ammo = max(1, bb_max - 1)
        surface = pygame.Surface((640, 360))
        self.game._draw_hud(surface)
        factor = self.game.options.hud_scale
        card = self.game._compact_hud_rects(len(self.game.players), factor)[0]
        inset = max(4, int(round(5 * factor)))
        health_y = card.y + max(15, int(round(16 * factor)))
        super_y = health_y + max(8, int(round(9 * factor)))
        chief_y = super_y + max(6, int(round(6 * factor)))
        resource_y = chief_y + max(5, int(round(5 * factor)))
        label = f"BB {self.dave.bb_ammo}/{bb_max}"
        bar_x = card.x + inset
        bar_w = card.width - inset * 2
        segment_x = bar_x + min(max(31, self.game.font_tiny.size(label)[0] + 4), max(31, bar_w // 3))
        segment_w = max(2, (card.right - inset - segment_x - (bb_max - 1)) // bb_max)
        filled = surface.get_at((segment_x + max(1, segment_w // 2), resource_y + 2))
        empty_x = segment_x + (bb_max - 1) * (segment_w + 1) + max(1, segment_w // 2)
        empty = surface.get_at((empty_x, resource_y + 2))
        self.assertNotEqual(filled, empty)


if __name__ == "__main__":
    unittest.main()
