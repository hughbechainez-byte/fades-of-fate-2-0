from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.config import campaign_levels
from src.game import COUCH_DOPE_OFFER_TAUNT, FadesGame, SelectSlot
from src.input_manager import InputManager


class CouchRetreatTests(unittest.TestCase):
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
        finale = campaign_levels(self.game.data)[-1]
        self.game._select_campaign_level(str(finale["id"]))
        self.game.select_slots = [
            SelectSlot({"type": "keyboard"}, character_index=0, confirmed=True)
        ]
        self.game._start_stage()
        self.game.encounter_index = len(self.game.data["encounters"]) - 1
        encounter = self.game.data["encounters"][self.game.encounter_index]
        self.game.encounter_active = True
        self.game.active_gate = float(encounter["gate_x"])
        self.game.camera_x = float(encounter["camera_x"])
        self.game._render_camera_x = self.game.camera_x
        self.game.spawn_queue.clear()
        self.boss = self.game._spawn_enemy("couch")
        self.boss.update(self.game, self.boss.state_duration)
        self.human = next(player for player in self.game.players if not player.is_cpu)

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def _trigger_next_retreat(self) -> float:
        gate = self.game.next_couch_retreat_health(self.boss)
        self.assertIsNotNone(gate)
        assert gate is not None
        self.assertTrue(
            self.boss.take_damage(
                self.boss.health - gate + 1000.0,
                self.game,
                self.human,
                knockdown=True,
            )
        )
        self.assertAlmostEqual(self.boss.health, gate)
        self.assertEqual(self.boss.state, "bike_retreat")
        self.assertFalse(self.boss.targetable)
        return gate

    def _reach_refuge(self) -> tuple[int, ...]:
        self.boss.update(self.game, 20.0)
        self.assertEqual(self.boss.state, "bike_refuge")
        retreat = self.game.couch_retreat
        self.assertIsNotNone(retreat)
        assert retreat is not None
        self.assertTrue(retreat.add_enemy_ids)
        return retreat.add_enemy_ids

    def _clear_wave_and_return(self) -> None:
        retreat = self.game.couch_retreat
        self.assertIsNotNone(retreat)
        assert retreat is not None
        for enemy in self.game.enemies:
            if enemy.enemy_id not in retreat.add_enemy_ids:
                continue
            enemy._set_state("chase")
            self.assertTrue(enemy.take_damage(100_000.0, self.game, self.human))
        self.boss.update(
            self.game,
            float(self.boss.stats["retreat_minimum_refuge_seconds"]),
        )
        self.assertEqual(self.boss.state, "bike_return")
        self.assertFalse(self.boss.targetable)
        self.boss.update(self.game, 20.0)
        self.assertEqual(self.boss.state, "chase")
        self.assertTrue(self.boss.targetable)
        self.assertIsNone(self.game.couch_retreat)

    def test_two_health_gates_spawn_exact_live_waves_and_fight_completes(self) -> None:
        ratios = self.boss.stats["retreat_health_ratios"]
        waves = self.boss.stats["retreat_add_waves"]
        self.assertEqual(len(ratios), 2)
        self.assertEqual(len(waves), 2)

        for index in range(2):
            with self.subTest(retreat=index + 1):
                self._trigger_next_retreat()
                add_ids = self._reach_refuge()
                adds = [enemy for enemy in self.game.enemies if enemy.enemy_id in add_ids]
                self.assertEqual([enemy.kind for enemy in adds], waves[index])
                self.assertTrue(all(enemy.alive for enemy in adds))
                self.assertEqual(self.boss.couch_retreats_started, index + 1)
                self._clear_wave_and_return()

        self.assertIsNone(self.game.next_couch_retreat_health(self.boss))
        self.assertTrue(self.boss.take_damage(100_000.0, self.game, self.human, knockdown=True))
        self.assertEqual(self.boss.state, "dead")
        self.game._update_encounters(0.0)
        self.assertEqual(self.game.state, "complete")
        self.assertTrue(self.game.level_stats.finished)

    def test_refuge_is_inaccessible_and_uses_exact_taunt_without_hidden_immunity(self) -> None:
        self._trigger_next_retreat()
        self._reach_refuge()
        refuge_health = self.boss.health

        self.assertFalse(self.boss.take_damage(100_000.0, self.game, self.human))
        self.assertEqual(self.boss.health, refuge_health)
        self.assertNotIn(
            ("enemy", self.boss.enemy_id),
            {hurtbox.owner_id for hurtbox in self.game._enemy_hurtboxes()},
        )
        self.assertEqual(
            COUCH_DOPE_OFFER_TAUNT,
            "I'LL GIVE YOU DOPE IF YOU BEAT THEM UP!",
        )
        retreat = self.game.couch_retreat
        self.assertIsNotNone(retreat)
        assert retreat is not None
        self.assertEqual(retreat.taunt, COUCH_DOPE_OFFER_TAUNT)
        canvas = pygame.Surface((640, 360), pygame.SRCALPHA)
        with mock.patch.object(self.game, "_text", wraps=self.game._text) as draw_text:
            self.game._draw_couch_refuge_taunt(canvas)
        self.assertIn(COUCH_DOPE_OFFER_TAUNT, {call.args[2] for call in draw_text.call_args_list})
        self.assertGreater(pygame.mask.from_surface(canvas).count(), 2000)

        self.game.activate_super(self.human)
        self.assertEqual(self.boss.state, "bike_refuge")
        self.assertEqual(self.boss.health, refuge_health)

        self._clear_wave_and_return()
        before = self.boss.health
        self.assertTrue(self.boss.take_damage(1.0, self.game, self.human))
        self.assertEqual(self.boss.health, before - 1.0)

    def test_retreat_jumps_left_to_the_single_authored_bmx(self) -> None:
        self._trigger_next_retreat()
        retreat = self.game.couch_retreat
        self.assertIsNotNone(retreat)
        assert retreat is not None
        expected_refuge_x = float(self.game._landmark_record("daves_bmx")["world_x"])
        self.assertEqual(retreat.refuge_x, expected_refuge_x)
        self.assertGreater(retreat.origin_x, retreat.refuge_x)
        self.assertEqual(self.boss.facing, -1)
        self.assertIn(
            "COUCH JUMPS BACK TO DAVE'S BMX!",
            {effect.text for effect in self.game.effects if effect.kind == "text"},
        )

        halfway_seconds = abs(retreat.origin_x - retreat.refuge_x) / (
            float(self.boss.stats["retreat_jump_speed"]) * 2.0
        )
        self.boss.update(self.game, halfway_seconds)
        self.assertGreater(self.boss.x, retreat.refuge_x)
        self.assertLess(self.boss.x, retreat.origin_x)
        canvas = pygame.Surface((640, 360), pygame.SRCALPHA)
        with mock.patch(
            "src.game.pixel_art.draw_boss",
            return_value=pygame.Rect(0, 0, 1, 1),
        ) as couch:
            self.game._draw_gameplay(canvas)
        self.assertEqual(couch.call_args.kwargs["state"], "walk")
        self.assertGreater(couch.call_args.kwargs["z"], 0.0)

        self._reach_refuge()
        with mock.patch(
            "src.game.pixel_art.draw_boss",
            return_value=pygame.Rect(0, 0, 1, 1),
        ) as couch:
            self.game._draw_gameplay(canvas)
        self.assertEqual(couch.call_args.kwargs["state"], "laugh")

    def test_burn_tick_cannot_skip_a_retreat_health_gate(self) -> None:
        gate = self.game.next_couch_retreat_health(self.boss)
        self.assertIsNotNone(gate)
        assert gate is not None
        self.boss.health = gate + 1.0
        self.boss.burn_time = 1.0
        self.boss.burn_tick = 0.0
        self.boss.last_hitter = self.human

        self.boss.update(self.game, 1.0 / 60.0)

        self.assertAlmostEqual(self.boss.health, gate)
        self.assertEqual(self.boss.state, "bike_retreat")
        self.assertFalse(self.boss.targetable)


if __name__ == "__main__":
    unittest.main()
