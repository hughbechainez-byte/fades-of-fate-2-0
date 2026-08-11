from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.entities import AttackExecution, Player


class _Game:
    def __init__(self) -> None:
        self.audio = SimpleNamespace(play=lambda *_: None)


def _player() -> Player:
    config = {
        "global": {"max_health": 100, "lives": 3, "jump_velocity": 200.0, "gravity": 500.0},
        "black_dave": {},
    }
    move = {"startup": 0.1, "active": 0.1, "recovery": 0.2}
    return Player(0, "black_dave", {}, 0.0, 0.0, config, {"air": move, "heavy": move, "light_combo": [move], "alt_light_combo": [move]})


class AirAttackV2Tests(unittest.TestCase):
    def test_route_execution_is_a_frozen_start_snapshot(self) -> None:
        step = SimpleNamespace(route_id="regular", step_index=2, step_id="z03", clip_id="dave_z_03", move_profile={"damage": 8}, timing={"startup": 0.1}, events=("contact",))
        execution = AttackExecution.from_route_step(step)
        step.move_profile["damage"] = 99
        self.assertEqual(execution.move_profile["damage"], 8)
        with self.assertRaises(TypeError):
            execution.timing["startup"] = 9  # type: ignore[index]

    def test_air_shuffle_bag_is_seeded_one_per_jump_and_resets_on_landing(self) -> None:
        game = _Game()
        first = _player()
        second = _player()
        for player in (first, second):
            player._start_jump(game)
            self.assertTrue(player.airborne)
            self.assertTrue(player._start_air_attack())
            self.assertFalse(player._start_air_attack())
        self.assertEqual(first.air_attack_kind, second.air_attack_kind)
        self.assertEqual(first.attack_execution.step_id, f"air_{first.air_attack_kind}")
        first.z, first.vz = 0.0, -1.0
        first._update_jump(game, 1.0 / 60.0)
        self.assertFalse(first.air_attack_used)
        self.assertEqual(first.air_attack_bag, [])


if __name__ == "__main__":
    unittest.main()
