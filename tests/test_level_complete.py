"""Deterministic contracts for level-complete stats and celebration timing."""

from __future__ import annotations

from dataclasses import dataclass
import unittest

from src.level_complete import LevelCompleteTimeline, LevelStatTracker, RankRules


@dataclass
class FakePlayer:
    score: int
    ko_count: int
    hit_count: int


class LevelStatTrackerTests(unittest.TestCase):
    def test_finish_combines_roster_stats_damage_time_and_rank(self) -> None:
        tracker = LevelStatTracker()
        for _ in range(120):
            tracker.advance(1.0 / 60.0)
        tracker.record_damage(18.25)
        tracker.record_damage(31.75)

        stats = tracker.finish(
            (
                FakePlayer(score=2000, ko_count=6, hit_count=64),
                FakePlayer(score=1500, ko_count=4, hit_count=36),
            )
        )

        self.assertEqual(stats.completion_seconds, 2.0)
        self.assertEqual(stats.formatted_time, "00:02")
        self.assertEqual(stats.combined_score, 3500)
        self.assertEqual(stats.kos, 10)
        self.assertEqual(stats.hits_landed, 100)
        self.assertEqual(stats.damage_taken, 50.0)
        self.assertEqual(stats.rating_points, 6194)
        self.assertEqual(stats.rank, "A")
        self.assertEqual(stats.as_dict()["completion_time"], "00:02")

    def test_finished_snapshot_is_idempotent_and_frozen(self) -> None:
        tracker = LevelStatTracker()
        player = FakePlayer(score=1000, ko_count=2, hit_count=10)
        tracker.advance(15.0)
        first = tracker.finish((player,))
        player.score = 99999
        tracker.advance(100.0)

        self.assertIs(tracker.finish((player,)), first)
        self.assertEqual(first.combined_score, 1000)
        self.assertEqual(tracker.elapsed_seconds, 15.0)
        with self.assertRaises(RuntimeError):
            tracker.record_damage(1.0)

    def test_rank_formula_uses_every_tracked_performance_dimension(self) -> None:
        rules = RankRules()
        baseline = rules.rating_points(
            completion_seconds=300,
            combined_score=1000,
            kos=0,
            hits_landed=0,
            damage_taken=0,
        )
        self.assertGreater(
            rules.rating_points(
                completion_seconds=240,
                combined_score=1000,
                kos=1,
                hits_landed=1,
                damage_taken=0,
            ),
            baseline,
        )
        self.assertLess(
            rules.rating_points(
                completion_seconds=360,
                combined_score=1000,
                kos=0,
                hits_landed=0,
                damage_taken=20,
            ),
            baseline,
        )

    def test_rules_are_data_driven_and_invalid_values_fail_early(self) -> None:
        rules = RankRules.from_mapping(
            {
                "hit_value": 10,
                "thresholds": {"S": 1000, "A": 500, "D": 0},
                "unknown_future_key": 123,
            }
        )
        self.assertEqual(rules.hit_value, 10)
        self.assertEqual(rules.rank_for_points(600), "A")
        with self.assertRaises(ValueError):
            RankRules(thresholds=(("A", 100), ("S", 200)))
        with self.assertRaises(ValueError):
            LevelStatTracker().advance(-0.01)


class LevelCompleteTimelineTests(unittest.TestCase):
    def test_sequence_orders_hug_treat_release_then_results_once(self) -> None:
        timeline = LevelCompleteTimeline(hug_seconds=1.25, treat_toss_seconds=1.15, treat_release_seconds=0.38)
        self.assertEqual(timeline.current_frame().phase, "hug")

        toss = timeline.advance(1.25)
        self.assertEqual(toss.phase, "treat_toss")
        self.assertEqual(toss.events, ("hug_complete", "treat_toss"))
        release = timeline.advance(0.40)
        self.assertEqual(release.phase, "treat_toss")
        self.assertEqual(release.events, ("treat_release",))
        results = timeline.advance(0.75)
        self.assertEqual(results.phase, "results")
        self.assertTrue(results.show_results)
        self.assertEqual(results.events, ("results",))
        self.assertEqual(timeline.advance(10.0).events, ())

    def test_large_fixed_step_cannot_skip_or_reorder_milestones(self) -> None:
        timeline = LevelCompleteTimeline()
        frame = timeline.advance(5.0)
        self.assertEqual(
            frame.events,
            ("hug_complete", "treat_toss", "treat_release", "results"),
        )
        self.assertEqual(frame.phase, "results")
        timeline.reset()
        self.assertEqual(timeline.current_frame().phase, "hug")

    def test_phase_progress_is_clamped_and_durations_are_validated(self) -> None:
        timeline = LevelCompleteTimeline(hug_seconds=2.0, treat_toss_seconds=1.0, treat_release_seconds=0.5)
        frame = timeline.advance(1.0)
        self.assertAlmostEqual(frame.phase_progress, 0.5)
        with self.assertRaises(ValueError):
            LevelCompleteTimeline(treat_toss_seconds=0.3, treat_release_seconds=0.5)


if __name__ == "__main__":
    unittest.main()
