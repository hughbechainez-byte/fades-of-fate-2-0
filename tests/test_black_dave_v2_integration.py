from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from src.entities import Enemy
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager, InputSnapshot


class BlackDaveV2IntegrationTests(unittest.TestCase):
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
        self.dave = next(player for player in self.game.players if player.character == "black_dave")

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def test_z_x_c_start_the_declared_three_by_seven_route_clips(self) -> None:
        expected = {
            "regular": "black_dave_v2_regular_01",
            "kick": "black_dave_v2_kick_01",
            "power": "black_dave_v2_power_01",
        }
        for action, clip_id in expected.items():
            with self.subTest(action=action):
                self.dave.set_state("idle")
                self.dave.combo_repeat_lock = 0.0
                self.dave.update(InputSnapshot(pressed={action}), self.game, 1.0 / 60.0)
                assert self.dave.attack_execution is not None
                self.assertEqual(self.dave.attack_execution.route_id, action)
                self.assertEqual(self.dave.attack_execution.clip_id, clip_id)
                self.assertEqual(self.dave.attack_execution.step_index, 0)

    def test_semantic_kick_edge_survives_hitstop_without_changing_legacy_latch(self) -> None:
        self.game.hitstop_remaining = 1.0 / 60.0
        self.manager.process_events(
            (pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_x, "repeat": False}),)
        )

        self.game.update(1.0 / 60.0)

        self.assertEqual(self.game._hitstop_pressed_by_slot[self.dave.slot], {"light"})
        self.assertEqual(self.game._hitstop_v2_pressed_by_slot[self.dave.slot], {"kick"})
        self.manager.consume_pressed()
        self.game.update(1.0 / 60.0)

        assert self.dave.attack_execution is not None
        self.assertEqual(self.dave.attack_execution.route_id, "kick")
        self.assertEqual(self.dave.attack_execution.clip_id, "black_dave_v2_kick_01")

    def test_route_buffer_advances_only_to_the_next_declared_step(self) -> None:
        self.dave.update(InputSnapshot(pressed={"regular"}), self.game, 1.0 / 60.0)
        self.dave.update(InputSnapshot(pressed={"regular"}), self.game, 1.0 / 60.0)
        for _ in range(36):
            self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)
            if self.dave.attack_execution is not None and self.dave.attack_execution.step_index == 1:
                break
        assert self.dave.attack_execution is not None
        self.assertEqual(self.dave.attack_execution.step_index, 1)
        self.assertEqual(self.dave.attack_execution.clip_id, "black_dave_v2_regular_02")

    def test_every_semantic_attack_action_resolves_to_one_air_variant(self) -> None:
        for action in ("regular", "kick", "power"):
            with self.subTest(action=action):
                self.dave._start_jump(self.game)
                self.dave.update(InputSnapshot(pressed={action}), self.game, 1.0 / 60.0)
                assert self.dave.attack_execution is not None
                self.assertEqual(self.dave.state, "air_attack")
                self.assertIn(self.dave.attack_execution.step_id, {"air_punch", "air_kick"})
                self.assertTrue(self.dave.air_attack_used)

    def test_crowd_push_moves_only_unarmored_normal_enemies(self) -> None:
        normal = Enemy(601, "stick", self.dave.x + 38.0, self.dave.y, dict(self.game.data["enemies"]["stick"]))
        armored_stats = dict(self.game.data["enemies"]["stick"])
        armored_stats["armor"] = True
        armored = Enemy(602, "stick", self.dave.x + 46.0, self.dave.y, armored_stats)
        boss = Enemy(603, "couch", self.dave.x + 52.0, self.dave.y, dict(self.game.data["enemies"]["couch"]))
        for enemy in (normal, armored, boss):
            enemy.state = "chase"
        self.game.enemies = [normal, armored, boss]
        self.dave._begin_black_dave_v2_route("power", 2, self.game)
        assert self.dave.attack_execution is not None
        moved = self.game.apply_black_dave_v2_crowd_push(self.dave, self.dave.attack_execution)
        self.assertEqual(moved, ("601",))
        self.assertEqual(normal.state, "hitstun")
        self.assertEqual(armored.state, "chase")
        self.assertEqual(boss.state, "chase")

    def test_v2_route_contact_owns_its_presentation_without_legacy_radial_effects(self) -> None:
        enemy = Enemy(604, "stick", self.dave.x + 34.0, self.dave.y, dict(self.game.data["enemies"]["stick"]))
        enemy.state = "chase"
        self.game.enemies = [enemy]
        self.dave.flaming_fists_timer = 5.0
        self.dave._begin_black_dave_v2_route("regular", 0, self.game)
        move = dict(self.dave.attack_timing_move or {})
        with mock.patch.object(self.game, "_emit_confirmed_hit_feedback") as legacy_feedback:
            hits = self.game.player_attack(
                self.dave,
                move,
                "light",
                attack_time=float(move["startup"]) + 0.01,
            )
        self.assertGreaterEqual(hits, 1)
        legacy_feedback.assert_not_called()
        self.assertIn(enemy.enemy_id, self.game._dave_flame_visuals)
        self.assertFalse(any(effect.kind in {"shock", "fist", "hit", "impact"} for effect in self.game.effects))


if __name__ == "__main__":
    unittest.main()
