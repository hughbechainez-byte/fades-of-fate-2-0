from __future__ import annotations

import unittest

from src.stage_transition import BossLoadingTransition


class BossLoadingTransitionTests(unittest.TestCase):
    def test_blackout_relocates_once_then_finishes(self) -> None:
        transition = BossLoadingTransition(duration_seconds=2.4, relocate_seconds=1.0)
        first = transition.advance(0.5)
        self.assertAlmostEqual(first.overlay_alpha, 0.5)
        self.assertEqual(first.events, ())
        blackout = transition.advance(0.5)
        self.assertEqual(blackout.events, ("relocate",))
        self.assertAlmostEqual(blackout.overlay_alpha, 1.0)
        done = transition.advance(1.4)
        self.assertEqual(done.events, ("finished",))
        self.assertTrue(done.finished)
        self.assertAlmostEqual(done.overlay_alpha, 0.0)
        self.assertEqual(transition.advance(5.0).events, ())

    def test_large_step_cannot_skip_relocation_or_finish(self) -> None:
        frame = BossLoadingTransition().advance(10.0)
        self.assertEqual(frame.events, ("relocate", "finished"))
        self.assertTrue(frame.finished)

    def test_invalid_durations_fail_early(self) -> None:
        with self.assertRaises(ValueError):
            BossLoadingTransition(duration_seconds=0)
        with self.assertRaises(ValueError):
            BossLoadingTransition(duration_seconds=1, relocate_seconds=1)
        with self.assertRaises(ValueError):
            BossLoadingTransition().advance(-0.01)


if __name__ == "__main__":
    unittest.main()
