from __future__ import annotations

import math
import unittest

from src.level_outro import JERRY_LEVEL_ONE_BEATS, JerryLevelOneOutro


class JerryLevelOneOutroTests(unittest.TestCase):
    def test_authored_sequence_has_five_distinct_story_and_visual_beats(self) -> None:
        self.assertEqual(
            [beat.name for beat in JERRY_LEVEL_ONE_BEATS],
            ["arrival", "warning", "clarification", "reaction", "finished"],
        )
        self.assertEqual(len({beat.camera_focus for beat in JERRY_LEVEL_ONE_BEATS}), 5)
        self.assertEqual(len({beat.jerry_pose for beat in JERRY_LEVEL_ONE_BEATS}), 5)
        self.assertIn("Couch", JERRY_LEVEL_ONE_BEATS[1].dialogue)
        self.assertIn("7-Eleven", JERRY_LEVEL_ONE_BEATS[1].dialogue)
        clarification = JERRY_LEVEL_ONE_BEATS[2].dialogue
        self.assertIn("El Cilantro", clarification)
        self.assertIn("Mexican food restaurant", clarification)
        self.assertIn("Goodwill", clarification)

    def test_arrival_settles_then_each_story_beat_requires_explicit_advance(self) -> None:
        timeline = JerryLevelOneOutro(
            arrival_seconds=1.0,
            warning_seconds=2.0,
            clarification_seconds=3.0,
            reaction_seconds=1.0,
        )
        self.assertEqual(timeline.current_frame().beat, "arrival")
        arrival_ready = timeline.advance(1.0)
        self.assertEqual(arrival_ready.beat, "arrival")
        self.assertTrue(arrival_ready.awaiting_continue)
        self.assertEqual(arrival_ready.events, ("jerry_settled",))

        # The descriptive arrival panel and the spoken lines all wait without
        # a deadline. The old nominal duration cannot skip the warning.
        still_arriving = timeline.advance(100.0)
        self.assertEqual(still_arriving.beat, "arrival")
        self.assertTrue(still_arriving.awaiting_continue)
        self.assertEqual(still_arriving.events, ())

        warning = timeline.advance(0.0, advance_input=True)
        self.assertEqual(warning.beat, "warning")
        self.assertTrue(warning.awaiting_continue)
        self.assertEqual(warning.events, ("warning_started",))
        timeline.advance(0.0, advance_input=False)

        clarification = timeline.advance(0.0, advance_input=True)
        self.assertEqual(clarification.beat, "clarification")
        self.assertEqual(clarification.events, ("clarification_started",))
        timeline.advance(0.0, advance_input=False)

        reaction = timeline.advance(0.0, advance_input=True)
        self.assertEqual(reaction.beat, "reaction")
        self.assertEqual(reaction.events, ("reaction_started",))
        timeline.advance(0.0, advance_input=False)

        finished = timeline.advance(0.0, advance_input=True)
        self.assertTrue(finished.finished)
        self.assertEqual(finished.events, ("finished",))
        self.assertEqual(timeline.advance(20.0).events, ())

    def test_large_fixed_step_cannot_timer_skip_the_dialogue(self) -> None:
        timeline = JerryLevelOneOutro()
        frame = timeline.advance(100.0)
        self.assertEqual(frame.events, ("jerry_settled",))
        self.assertEqual(frame.beat, "arrival")
        self.assertTrue(frame.awaiting_continue)
        self.assertFalse(frame.finished)
        # Even the old full-scene nominal time cannot change a dialogue beat.
        self.assertEqual(timeline.advance(timeline.total_seconds).beat, "arrival")
        self.assertFalse(timeline.finished)

    def test_held_advance_uses_rising_edges_instead_of_racing_ahead(self) -> None:
        timeline = JerryLevelOneOutro()
        arrival_ready = timeline.advance(timeline.arrival_seconds)
        self.assertTrue(arrival_ready.awaiting_continue)
        warning = timeline.advance(0.0, advance_input=True)
        self.assertEqual(warning.beat, "warning")
        self.assertEqual(warning.events, ("warning_started",))

        still_warning = timeline.advance(20.0, advance_input=True)
        self.assertEqual(still_warning.beat, "warning")
        self.assertEqual(still_warning.events, ())

        timeline.advance(0.0, advance_input=False)
        clarification = timeline.advance(0.0, advance_input=True)
        self.assertEqual(clarification.beat, "clarification")
        self.assertEqual(clarification.events, ("clarification_started",))

    def test_skip_finishes_once_without_firing_unplayed_dialogue(self) -> None:
        timeline = JerryLevelOneOutro()
        frame = timeline.advance(0.25, skip_input=True)
        self.assertEqual(frame.beat, "finished")
        self.assertTrue(frame.finished)
        self.assertEqual(frame.events, ("skipped", "finished"))
        self.assertEqual(timeline.advance(0.0, skip_input=True).events, ())
        self.assertEqual(timeline.advance(0.0, skip_input=False).events, ())

    def test_progress_validation_and_reset_are_deterministic(self) -> None:
        timeline = JerryLevelOneOutro(arrival_seconds=2.0)
        frame = timeline.advance(0.5)
        self.assertAlmostEqual(frame.beat_progress, 0.25)
        timeline.reset()
        self.assertEqual(timeline.current_frame().beat, "arrival")
        self.assertEqual(timeline.elapsed_seconds, 0.0)

        for invalid in (0.0, -1.0, math.inf, math.nan):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    JerryLevelOneOutro(arrival_seconds=invalid)
        with self.assertRaises(ValueError):
            timeline.advance(-0.01)


if __name__ == "__main__":
    unittest.main()
