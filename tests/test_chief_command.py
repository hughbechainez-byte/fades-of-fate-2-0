"""Focused gameplay tests for the shared, metered Chief command."""

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
from src.world_engine import WorldPoint


class ChiefCommandTests(unittest.TestCase):
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
        self.chief = self.game.chiefs[0]

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def enemy(self, enemy_id: int, x: float, y: float, kind: str = "stick") -> Enemy:
        result = Enemy(enemy_id, kind, x, y, self.game.data["enemies"][kind])
        result.state = "chase"
        return result

    def test_each_player_has_an_independent_ready_meter(self) -> None:
        maximum = float(self.game.data["chief"]["command_meter_max"])
        self.assertEqual(self.dave.chief_meter, maximum)
        self.assertEqual(self.shelly.chief_meter, maximum)

        self.game.enemies = [self.enemy(1, self.dave.x + 35.0, self.dave.y)]
        self.assertTrue(self.game.command_chief(self.dave))
        self.assertEqual(
            self.dave.chief_meter,
            maximum - float(self.game.data["chief"]["command_cost"]),
        )
        self.assertEqual(self.shelly.chief_meter, maximum)

    def test_keyboard_command_edge_is_dispatched_during_hitstop(self) -> None:
        target = self.enemy(2, self.dave.x + 80.0, self.dave.y)
        self.game.enemies = [target]
        self.game.hitstop_remaining = 0.20
        self.manager.process_events(
            (pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r, "repeat": False}),)
        )

        self.game.update(1.0 / 60.0)

        self.assertEqual(self.chief.command_enemy_id, target.enemy_id)
        self.assertEqual(
            self.dave.chief_meter,
            float(self.game.data["chief"]["command_meter_max"])
            - float(self.game.data["chief"]["command_cost"]),
        )

    def test_controller_trigger_command_uses_live_gameplay_path(self) -> None:
        instance_id = 77
        self.manager.add_synthetic_controller(instance_id)
        binding = {"type": "controller", "instance_id": instance_id}
        self.game.select_slots = [SelectSlot(binding, character_index=0, confirmed=True)]
        self.game._start_stage()
        dave = self.game.players[0]
        chief = self.game.chiefs[0]
        target = self.enemy(3, dave.x + 80.0, dave.y)
        self.game.enemies = [target]
        self.game.hitstop_remaining = 0.20
        self.manager.process_events(
            (
                pygame.event.Event(
                    pygame.CONTROLLERAXISMOTION,
                    {
                        "instance_id": instance_id,
                        "axis": pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
                        "value": 24_576,
                    },
                ),
            )
        )

        self.game.update(1.0 / 60.0)

        self.assertEqual(chief.command_enemy_id, target.enemy_id)
        self.assertLess(dave.chief_meter, float(self.game.data["chief"]["command_meter_max"]))

    def test_command_chooses_nearest_enemy_to_caller_then_returns_for_pet(self) -> None:
        near = self.enemy(10, self.dave.x + 24.0, self.dave.y)
        far = self.enemy(11, self.dave.x + 190.0, self.dave.y)
        self.game.enemies = [far, near]
        self.chief.x, self.chief.y = near.x + 74.0, near.y
        before = near.health

        self.assertTrue(self.game.command_chief(self.dave))
        self.assertEqual(self.chief.command_enemy_id, near.enemy_id)
        for _ in range(90):
            self.chief.update(self.game, 1.0 / 60.0)
            self.game._resolve_actor_separation()
            if near.health < before:
                break
        self.assertEqual(near.health, before - float(self.game.data["chief"]["command_damage"]))
        self.assertEqual(far.health, far.max_health)

        for _ in range(90):
            self.chief.update(self.game, 1.0 / 60.0)
            self.game._resolve_actor_separation()
            if self.chief.state == "pet":
                break
        self.assertEqual(self.chief.state, "pet")
        self.assertEqual(self.chief.pet_partner, self.dave)
        self.assertEqual(self.dave.state, "pet")

    def test_active_attack_on_caller_prevents_post_command_pet(self) -> None:
        victim = self.enemy(20, self.dave.x + 20.0, self.dave.y)
        attacker = self.enemy(21, self.dave.x + 100.0, self.dave.y)
        attacker.target_slot = self.dave.slot
        attacker.state = "windup"
        self.game.enemies = [victim, attacker]
        self.chief.x, self.chief.y = victim.x - 10.0, victim.y

        self.assertTrue(self.game.command_chief(self.dave))
        self.chief.update(self.game, 1.0 / 60.0)
        self.assertTrue(self.chief.command_return_pending)
        self.chief.update(self.game, 1.0 / 60.0)

        self.assertIsNone(self.chief.command_caller)
        self.assertNotEqual(self.chief.state, "pet")
        self.assertNotEqual(self.dave.state, "pet")

    def test_no_target_preserves_meter_and_active_command_can_be_retargeted(self) -> None:
        initial_dave = self.dave.chief_meter
        self.assertFalse(self.game.command_chief(self.dave))
        self.assertEqual(self.dave.chief_meter, initial_dave)

        first = self.enemy(30, self.dave.x + 30.0, self.dave.y)
        second = self.enemy(31, self.shelly.x + 22.0, self.shelly.y)
        self.game.enemies = [first, second]
        self.assertTrue(self.game.command_chief(self.dave))
        dave_after_first_call = self.dave.chief_meter
        initial_shelly = self.shelly.chief_meter
        self.assertTrue(self.game.command_chief(self.shelly))
        self.assertIs(self.chief.command_caller, self.shelly)
        self.assertEqual(self.chief.command_enemy_id, second.enemy_id)
        self.assertGreater(self.dave.chief_meter, dave_after_first_call)
        self.assertEqual(
            self.dave.chief_meter,
            float(self.game.data["chief"]["command_meter_max"]),
        )
        self.assertEqual(
            self.shelly.chief_meter,
            initial_shelly - float(self.game.data["chief"]["command_cost"]),
        )

    def test_offscreen_chief_is_recalled_and_commanded_during_hitstop(self) -> None:
        target = self.enemy(32, self.dave.x + 75.0, self.dave.y)
        self.game.enemies = [target]
        self.chief.x = self.game.camera_x + 1800.0
        self.chief.y = self.dave.y
        self.game.hitstop_remaining = 0.20
        self.manager.process_events(
            (pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r, "repeat": False}),)
        )

        self.game.update(1.0 / 60.0)

        self.assertIs(self.chief.command_caller, self.dave)
        self.assertEqual(self.chief.command_enemy_id, target.enemy_id)
        self.assertLess(abs(self.chief.x - self.dave.x), 80.0)
        self.assertLess(abs(self.chief.y - self.dave.y), 40.0)
        chief_depth_radius = self.game._actor_extents(self.chief)[1]
        self.assertTrue(
            self.game.stage_geometry.is_walkable(
                WorldPoint(self.chief.x, self.chief.y),
                radius=chief_depth_radius,
            )
        )
        self.assertGreater(self.game.hitstop_remaining, 0.0)

    def test_meter_recharge_and_shelly_frenzy_remain_data_driven(self) -> None:
        self.dave.chief_meter = 0.0
        self.dave.update(self.game._cpu_snapshot(self.shelly, 0.0), self.game, 2.0)
        self.assertEqual(
            self.dave.chief_meter,
            float(self.game.data["chief"]["command_recharge_per_second"]) * 2.0,
        )

        command_damage = float(self.game.data["chief"]["command_damage"])
        frenzy_total = (
            float(self.game.data["chief"]["frenzy_damage"])
            * float(self.game.data["players"]["shelly"]["chief_frenzy_seconds"])
            / float(self.game.data["chief"]["frenzy_cooldown"])
        )
        self.assertLess(command_damage, frenzy_total * 0.15)
        self.game.activate_super(self.shelly)
        self.assertGreater(self.chief.frenzy, 7.5)

    def test_cpu_companion_uses_its_chief_meter_through_fixed_step_dispatch(self) -> None:
        target = self.enemy(40, self.shelly.x + 100.0, self.shelly.y)
        target.cooldown = 99.0
        self.game.enemies = [target]
        self.shelly.super_meter = 0.0

        self.game.update(1.0 / 60.0)

        self.assertIs(self.chief.command_caller, self.shelly)
        self.assertEqual(self.chief.command_enemy_id, target.enemy_id)
        self.assertAlmostEqual(
            self.shelly.chief_meter,
            float(self.game.data["chief"]["command_meter_max"])
            - float(self.game.data["chief"]["command_cost"])
            + float(self.game.data["chief"]["command_recharge_per_second"]) / 60.0,
            places=5,
        )

    def test_cpu_shelly_supers_against_a_single_boss_when_charged(self) -> None:
        boss = self.enemy(41, self.shelly.x + 28.0, self.shelly.y, kind="couch")
        boss.cooldown = 99.0
        self.game.enemies = [boss]
        self.shelly.super_meter = float(self.game.data["players"]["global"]["super_cost"])

        for _ in range(14):
            self.game.update(1.0 / 60.0)
            if self.chief.frenzy > 0.0:
                break

        self.assertGreater(self.chief.frenzy, 0.0)
        self.assertEqual(self.shelly.super_meter, 0.0)

    def test_autonomous_bite_lands_then_chief_guards_during_cooldown(self) -> None:
        self.dave.x = 400.0
        self.shelly.cpu_action_cooldown = 99.0
        self.dave.chief_meter = self.shelly.chief_meter = 0.0
        target = self.enemy(42, self.chief.x + 72.0, self.chief.y)
        target.cooldown = 99.0
        self.game.enemies = [target]
        self.chief.attack_cooldown = 0.0
        before = target.health

        for _ in range(120):
            self.game.update(1.0 / 60.0)
            if target.health < before:
                break

        self.assertEqual(target.health, before - float(self.game.data["chief"]["passive_damage"]))
        target.x, target.y = self.chief.x + 10.0, self.chief.y
        self.chief.update(self.game, 1.0 / 60.0)
        self.assertEqual(self.chief.state, "guard")

    def test_chief_remains_still_when_dave_and_shelly_are_idle(self) -> None:
        self.game.enemies.clear()
        start = (self.chief.x, self.chief.y)

        for _ in range(90):
            self.game.update(1.0 / 60.0)

        self.assertEqual((self.chief.x, self.chief.y), start)
        self.assertEqual(self.chief.state, "sit")

    def test_unavailable_human_command_has_visible_feedback(self) -> None:
        self.game.enemies.clear()
        self.game.effects.clear()
        self.manager.process_events(
            (pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_r, "repeat": False}),)
        )

        self.game.update(1.0 / 60.0)

        self.assertTrue(any(effect.kind == "text" and effect.text == "NO TARGET" for effect in self.game.effects))


if __name__ == "__main__":
    unittest.main()
