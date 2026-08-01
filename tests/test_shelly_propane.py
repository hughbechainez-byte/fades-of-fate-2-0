"""Focused tests for Shelly's Super Butane secondary and CPU frenzy use."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.entities import Enemy, SuperButanePickup
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager


class ShellyPropaneTests(unittest.TestCase):
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
        self.game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=1, confirmed=True)]
        self.game._start_stage()
        self.shelly, self.dave = self.game.players
        self.dave.cpu_action_cooldown = 99.0
        self.dave.chief_meter = 0.0
        self.dave.super_meter = 0.0

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def enemy(self, enemy_id: int, x: float, y: float, kind: str = "stick") -> Enemy:
        result = Enemy(enemy_id, kind, x, y, self.game.data["enemies"][kind])
        result.state = "chase"
        result.cooldown = 99.0
        return result

    def test_keyboard_secondary_is_held_flame_with_long_range_lane_hits(self) -> None:
        self.shelly.super_butane_meter = 100.0
        near = self.enemy(1, self.shelly.x + 95.0, self.shelly.y)
        far = self.enemy(2, self.shelly.x + 285.0, self.shelly.y + 20.0)
        off_lane = self.enemy(3, self.shelly.x + 90.0, self.shelly.y + 55.0)
        self.game.enemies = [near, far, off_lane]
        before = self.shelly.super_butane_meter
        self.manager.process_events(
            (pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_g, "repeat": False}),)
        )

        self.game.update(1.0 / 60.0)

        self.assertEqual(self.shelly.state, "propane")
        self.assertLess(self.shelly.super_butane_meter, before)
        self.assertLess(near.health, near.max_health)
        self.assertLess(far.health, far.max_health)
        self.assertEqual(off_lane.health, off_lane.max_health)
        self.assertTrue(any(effect.kind == "flame" for effect in self.game.effects))

        self.manager.consume_pressed()
        self.manager.process_events((pygame.event.Event(pygame.KEYUP, {"key": pygame.K_g}),))
        self.game.update(1.0 / 60.0)
        self.assertEqual(self.shelly.state, "idle")

    def test_controller_left_trigger_dispatches_shelly_secondary(self) -> None:
        instance_id = 93
        self.manager.add_synthetic_controller(instance_id)
        binding = {"type": "controller", "instance_id": instance_id}
        self.game.select_slots = [SelectSlot(binding, character_index=1, confirmed=True)]
        self.game._start_stage()
        shelly = self.game.players[0]
        shelly.super_butane_meter = 100.0
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

        self.assertEqual(shelly.state, "propane")
        self.assertEqual(shelly.super_butane_meter, 100.0)

    def test_super_butane_drop_schedule_and_collection_are_shelly_only(self) -> None:
        drops_at: list[int] = []
        for ko_number in range(1, 8):
            defeated = self.enemy(100 + ko_number, 300.0 + ko_number, 270.0)
            self.game.enemy_defeated(defeated, self.shelly)
            if len(self.game.super_butane_pickups) > len(drops_at):
                drops_at.append(ko_number)
        self.assertEqual(drops_at, [2, 5, 7])

        pickup = self.game.super_butane_pickups[0]
        self.dave.x, self.dave.y = pickup.x, pickup.y
        pickup.update(self.game, 1.0 / 60.0)
        self.assertFalse(pickup.spent)

        maximum = float(self.game.data["shelly_propane"]["meter_max"])
        self.shelly.super_butane_meter = maximum - 3.0
        self.shelly.x, self.shelly.y = pickup.x, pickup.y
        pickup.update(self.game, 1.0 / 60.0)
        self.assertTrue(pickup.spent)
        self.assertEqual(self.shelly.super_butane_meter, maximum)
        self.assertTrue(any(effect.kind == "pickup" for effect in self.game.effects))

    def test_shelly_super_meter_fills_faster_and_cpu_calls_chief_at_range(self) -> None:
        self.assertEqual(self.shelly.gain_super(10.0), 17.0)
        self.assertEqual(self.dave.gain_super(10.0), 10.0)

        self.game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
        self.game._start_stage()
        dave, shelly = self.game.players
        boss = self.enemy(200, shelly.x + 190.0, shelly.y, kind="couch")
        self.game.enemies = [boss]
        shelly.super_meter = float(self.game.data["players"]["global"]["super_cost"])
        snapshot = self.game._cpu_snapshot(shelly, 1.0 / 60.0)
        self.assertIn("super", snapshot.pressed)
        shelly.cpu_action_cooldown = 0.0

        for _ in range(14):
            self.game.update(1.0 / 60.0)
            if self.game.chiefs[0].frenzy > 0.0:
                break

        self.assertGreater(self.game.chiefs[0].frenzy, 0.0)
        self.assertEqual(shelly.super_meter, 0.0)
        self.assertTrue(dave.combat_active)

    def test_shelly_frenzy_burst_wipes_a_non_boss_crowd_and_keeps_couch_intact(self) -> None:
        crowd = [
            self.enemy(300 + index, self.shelly.x + 34.0 + index * 19.0, self.shelly.y + (index % 2) * 7.0)
            for index in range(4)
        ]
        couch = self.enemy(399, self.shelly.x + 52.0, self.shelly.y, kind="couch")
        couch_before = couch.health
        self.game.enemies = [*crowd, couch]

        self.game.activate_super(self.shelly)

        self.assertTrue(all(enemy.state == "dead" for enemy in crowd))
        self.assertEqual(couch.health, couch_before)
        self.assertGreater(self.game.chiefs[0].frenzy, 0.0)
        self.assertIsNotNone(self.game.shelly_frenzy_cinematic)
        self.assertIn("chief_frenzy", {effect.kind for effect in self.game.effects})

        canvas = pygame.Surface((640, 360), pygame.SRCALPHA)
        self.game._draw_gameplay(canvas)
        self.assertGreater(pygame.mask.from_surface(canvas).count(), 1_000)

        cinematic = self.game.shelly_frenzy_cinematic
        assert cinematic is not None
        self.game._advance_shelly_frenzy_cinematic(cinematic.duration_seconds)
        self.assertIsNone(self.game.shelly_frenzy_cinematic)

    def test_cpu_shelly_reserves_two_frenzies_for_two_ordinary_crowds(self) -> None:
        self.game.select_slots = [SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)]
        self.game._start_stage()
        _, shelly = self.game.players

        def crowd(start_id: int) -> list[Enemy]:
            targets = [
                self.enemy(start_id + index, shelly.x + 34.0 + index * 17.0, shelly.y + (index % 2) * 6.0)
                for index in range(4)
            ]
            for target in targets:
                target.cooldown = 99.0
            return targets

        self.game.enemies = crowd(410)
        for _ in range(180):
            self.game.update(1.0 / 60.0)
            if self.game._cpu_shelly_frenzy_uses.get(shelly.slot, 0) >= 1:
                break
        self.assertEqual(self.game._cpu_shelly_frenzy_uses.get(shelly.slot, 0), 1)

        # The cleared-street linger avoids burning the whole first frenzy
        # during travel, then the next live crowd earns the second reserve.
        for _ in range(140):
            self.game.update(1.0 / 60.0)
        self.assertLessEqual(self.game.chiefs[0].frenzy, 0.01)
        self.game.enemies = crowd(430)
        for _ in range(210):
            self.game.update(1.0 / 60.0)
            if self.game._cpu_shelly_frenzy_uses.get(shelly.slot, 0) >= 2:
                break

        self.assertGreaterEqual(self.game._cpu_shelly_frenzy_uses.get(shelly.slot, 0), 2)
        self.assertGreater(self.game.chiefs[0].frenzy, 0.0)
        self.assertEqual(shelly.super_meter, 0.0)


if __name__ == "__main__":
    unittest.main()
