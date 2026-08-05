"""Focused Black Dave combo and speaker-super contracts."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from src.entities import Enemy
from src.game import FadesGame, SelectSlot
from src.input_manager import InputManager, InputSnapshot


class DaveCombatTests(unittest.TestCase):
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
        self.shelly.state = "eliminated"

    def tearDown(self) -> None:
        self.game.close()
        self.manager.close()

    def enemy(self, enemy_id: int, x: float, y: float, kind: str = "stick") -> Enemy:
        result = Enemy(enemy_id, kind, x, y, self.game.data["enemies"][kind])
        result.state = "chase"
        return result

    def test_repeated_light_presses_progress_through_four_hit_finisher(self) -> None:
        target = self.enemy(201, self.dave.x + 32.0, self.dave.y, "security")
        self.game.enemies = [target]
        sequence = self.dave._light_sequence()
        self.assertEqual(sequence, (0, 1, 2, 4, 3, 5))
        finisher = self.game.data["moves"]["light_combo"][sequence[-1]]
        self.assertTrue(finisher["knockdown"])
        self.assertTrue(finisher["launch"])

        before = target.health
        hits = self.game.player_attack(self.dave, finisher, "light", already_hit=set())
        self.assertGreaterEqual(hits, 1)
        self.assertLess(target.health, before)
        self.assertEqual(target.state, "down")
        self.assertGreaterEqual(target.knockback_vx, 0.0)

    def test_combo_finisher_and_heavy_keep_the_uppercut_launcher_pose(self) -> None:
        self.assertEqual(
            self.game.data["moves"]["light_combo"][5]["launch"],
            True,
        )
        self.dave.combo_step = 5
        self.assertEqual(self.dave._light_move(), self.game.data["moves"]["light_combo"][5])
        self.assertEqual(self.game.data["moves"]["heavy"]["launch"], True)

    def test_c_combo_sequence_runs_through_uppercuts_before_the_far_push_kick(self) -> None:
        self.dave.combo_style = "c"
        self.assertEqual(self.dave._light_sequence(), (0, 1, 2, 3))
        self.dave.combo_step = 0
        self.assertEqual(
            self.dave._combo_move(),
            self.game.data["moves"]["heavy_combo"][0],
        )
        self.dave.combo_step = 2
        self.assertTrue(self.dave._combo_move()["launch"])
        final_move = self.game.data["moves"]["heavy_combo"][3]
        self.assertGreater(final_move["knockback"], self.game.data["moves"]["heavy_combo"][2]["knockback"])
        self.assertGreater(final_move["knockback"], self.game.data["moves"]["heavy"]["knockback"])
        self.assertTrue(final_move["knockdown"])

    def test_combo_repeat_lock_holds_the_chain_for_five_seconds(self) -> None:
        self.dave.combo_style = "x"
        self.dave.combo_repeat_lock = 5.0
        self.dave.update(
            InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
            self.game,
            1.0 / 60.0,
        )
        self.assertEqual(self.dave.state, "idle")
        self.assertEqual(self.dave.combo_step, 0)
        self.assertGreater(self.dave.combo_repeat_lock, 4.9)
        self.dave.combo_repeat_lock = 0.0
        self.dave.update(
            InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
            self.game,
            1.0 / 60.0,
        )
        self.assertEqual(self.dave.state, "light")

    def test_alt_light_combo_uses_the_authorized_z_chain(self) -> None:
        self.dave.combo_style = "z"
        self.dave.combo_step = 2
        self.assertEqual(self.dave._alt_light_move(), self.game.data["moves"]["light_combo"][3])

    def test_heavy_combo_uses_the_authorized_c_chain(self) -> None:
        self.dave.combo_style = "c"
        self.dave.combo_step = 0
        self.assertEqual(self.dave._combo_move(), self.game.data["moves"]["heavy_combo"][0])

    def test_one_light_press_remains_one_punch(self) -> None:
        target = self.enemy(202, self.dave.x + 32.0, self.dave.y)
        self.game.enemies = [target]
        first_move = self.game.data["moves"]["light_combo"][0]

        self.dave.update(
            InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
            self.game,
            1.0 / 60.0,
        )
        for _ in range(40):
            self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)

        self.assertEqual(target.health, target.max_health - float(first_move["damage"]))
        self.assertNotEqual(target.state, "down")

    def test_early_buffered_press_waits_for_cancel_window_then_chains(self) -> None:
        first_move = self.game.data["moves"]["light_combo"][0]
        self.dave.combo_step = 0
        self.dave.set_state("light", self.dave._move_total(first_move))

        self.dave.update(
            InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
            self.game,
            1.0 / 60.0,
        )
        self.assertEqual(self.dave.combo_step, 0)
        self.assertTrue(self.dave.queued_light)
        for _ in range(20):
            self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)
            if self.dave.combo_step == 1:
                break

        self.assertEqual(self.dave.state, "light")
        self.assertEqual(self.dave.combo_step, 1)
        self.assertFalse(self.dave.queued_light)

    def test_expired_buffer_does_not_create_a_late_attack(self) -> None:
        first_move = self.game.data["moves"]["light_combo"][0]
        original_window = first_move["buffer_window"]
        first_move["buffer_window"] = 0.04
        try:
            self.dave.combo_step = 0
            self.dave.set_state("light", self.dave._move_total(first_move))
            self.dave.update(
                InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
                self.game,
                1.0 / 60.0,
            )
            for _ in range(24):
                self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)
        finally:
            first_move["buffer_window"] = original_window

        self.assertEqual(self.dave.state, "idle")
        self.assertEqual(self.dave.combo_step, 0)
        self.assertFalse(self.dave.queued_light)

    def test_heavy_buffer_branches_once_and_damage_clears_all_queues(self) -> None:
        first_move = self.game.data["moves"]["light_combo"][0]
        self.dave.set_state("light", self.dave._move_total(first_move))
        self.dave.update(
            InputSnapshot(held=frozenset({"heavy"}), pressed=frozenset({"heavy"})),
            self.game,
            1.0 / 60.0,
        )
        for _ in range(20):
            self.dave.update(InputSnapshot(), self.game, 1.0 / 60.0)
            if self.dave.state == "heavy":
                break
        self.assertEqual(self.dave.state, "heavy")
        self.assertEqual(self.dave.combo_step, 0)
        self.assertFalse(self.dave.queued_heavy)

        self.dave.set_state("light", self.dave._move_total(first_move))
        self.dave.update(
            InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
            self.game,
            1.0 / 60.0,
        )
        self.assertTrue(self.dave.queued_light)
        self.assertTrue(self.dave.take_damage(1.0, self.game))
        self.assertEqual(self.dave.state, "hurt")
        self.assertFalse(self.dave.queued_light)
        self.assertFalse(self.dave.queued_heavy)
        self.assertEqual(self.dave.combo_step, 0)

    def test_speaker_bass_drop_is_an_intentional_full_map_wipe(self) -> None:
        self.assertTrue(self.game.data["players"]["black_dave"]["super_full_map"])
        near = self.enemy(203, self.dave.x + 20.0, self.dave.y)
        distant = self.enemy(204, self.dave.x + 1200.0, self.dave.y)
        self.game.enemies = [near, distant]
        self.game.spawn_queue = ["stick"]

        self.game.activate_super(self.dave)

        self.assertEqual((near.state, distant.state), ("dead", "dead"))
        self.assertEqual(self.game.spawn_queue, [])
        self.assertIn("bass_drop", {effect.kind for effect in self.game.effects})

    def test_six_air_presses_ignite_daves_fists_and_boost_damage_twenty_percent(self) -> None:
        """Ignition is input-only: it must not require a target or a hit."""

        self.assertEqual(self.game.enemies, [])
        for press in range(5):
            self.dave.update(
                InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
                self.game,
                1.0 / 60.0,
            )
            self.dave.set_state("idle")
            self.assertFalse(self.dave.flaming_fists, press)
        self.dave.update(
            InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
            self.game,
            1.0 / 60.0,
        )
        self.assertTrue(self.dave.flaming_fists)
        self.assertEqual(self.dave.flaming_fists_ignitions, 1)
        self.assertTrue(any(effect.kind == "flame" for effect in self.game.effects))

        target = self.enemy(205, self.dave.x + 28.0, self.dave.y)
        self.game.enemies = [target]
        move = self.game.data["moves"]["light_combo"][0]
        self.game.player_attack(self.dave, move, "light")
        self.assertAlmostEqual(
            target.health,
            target.max_health - float(move["damage"]) * 1.20,
        )

    def test_flame_timer_needs_a_four_press_burst_to_refresh(self) -> None:
        flames = self.game.data["players"]["black_dave"]["fist_flames"]
        self.dave.flaming_fists_timer = float(flames["active_seconds"])
        for _ in range(3):
            self.dave.update(
                InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
                self.game,
                1.0 / 60.0,
            )
            self.dave.set_state("idle")
        after_three = self.dave.flaming_fists_timer
        self.assertLess(after_three, float(flames["active_seconds"]))
        self.dave.update(
            InputSnapshot(held=frozenset({"light"}), pressed=frozenset({"light"})),
            self.game,
            1.0 / 60.0,
        )
        self.assertAlmostEqual(self.dave.flaming_fists_timer, float(flames["active_seconds"]))

        self.dave.update(InputSnapshot(), self.game, float(flames["active_seconds"]) + 0.05)
        self.assertFalse(self.dave.flaming_fists)
        self.assertTrue(any(effect.text == "FISTS COOLED" for effect in self.game.effects))


if __name__ == "__main__":
    unittest.main()
